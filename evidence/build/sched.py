#!/usr/bin/env python3
"""Planificador de compilación para el proyecto Lean, alternativo a `lake build`.

Lake, por cada módulo, recorre todo su árbol de imports transitivos (decenas de miles aquí)
para calcular trazas y escribir un setup.json enorme; eso lo vuelve el cuello de botella.
Este planificador solo mira imports DIRECTOS para decidir cuándo un módulo está listo, y lanza
`lean` con LEAN_PATH (Lean resuelve los imports por su cuenta), con las mismas opciones que el
lakefile. La validez de las pruebas la sigue decidiendo el kernel de Lean dentro de `lean`.

Modos:
  verify --n K      recompila K módulos ya compilados por Lake en un directorio aparte y compara
                    los .olean byte a byte con los de Lake (valida que replicamos sus flags).
  build  --jobs N   compila todo lo que falta, reutilizando lo ya compilado.

Uso: python3 -I sched.py <proyecto> {verify,build} [--jobs N] [--n K]
"""
import argparse, heapq, json, os, random, shutil, subprocess, sys, threading, time
from collections import defaultdict

# ---- Configuración replicada del lakefile.toml ----------------------------------------------
PACKAGE = "tree"
MORE_ARGS = ["--tstack=400000"]
# Mismo orden y tipos que el setup.json que genera Lake.
OPTIONS = {
    "relaxedAutoImplicit": False,
    "pp.unicode.fun": True,
    "maxSynthPendingDepth": 3,
    "maxHeartbeats": 4000000,
    "autoImplicit": False,
}
# lean_lib GroundTheoryFields: globs GroundTheory.LocalFields.+ y GroundTheory.GlobalFields.+
EXTRA_OPTIONS = [
    (("GroundTheory.LocalFields.", "GroundTheory.GlobalFields."), {"synthInstance.maxHeartbeats": 400000}),
]
SCHED_MARK = ".sched"  # marcador de "compilado por este planificador"


def options_for(mod):
    opts = dict(OPTIONS)
    for prefixes, extra in EXTRA_OPTIONS:
        if mod.startswith(prefixes):
            opts.update(extra)
    return opts


def write_setup(path, mod):
    """setup.json mínimo: lo mismo que Lake salvo importArts vacío (los imports se
    resuelven por LEAN_PATH), así que pesa ~300 bytes en vez de varios MB."""
    data = {"plugins": [], "package": PACKAGE, "options": options_for(mod), "name": mod,
            "isModule": False, "importArts": {}, "dynlibs": []}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def parse_imports(path):
    res = []
    with open(path, encoding="utf-8", errors="replace") as f:
        in_comment = False
        for line in f:
            s = line.strip()
            if in_comment:
                if "-/" in s:
                    in_comment = False
                continue
            if not s or s.startswith("--"):
                continue
            if s.startswith("/-"):
                if "-/" not in s[2:]:
                    in_comment = True
                continue
            if s.startswith("import "):
                res += s[len("import "):].split()
            elif s.startswith(("prelude", "module")):
                continue
            else:
                break
    return res


def discover(src):
    mods = {}
    for dirpath, _, files in os.walk(src):
        for fn in files:
            if fn.endswith(".lean"):
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, src)[: -len(".lean")]
                mods[".".join(rel.replace("\\", "/").split("/"))] = p
    return mods


def lean_binary(proj):
    out = subprocess.run(["elan", "which", "lean"], cwd=proj, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def lean_path(proj, extra_first=None):
    paths = []
    if extra_first:
        paths.append(extra_first)
    paths.append(os.path.join(proj, ".lake", "build", "lib", "lean"))
    pk = os.path.join(proj, ".lake", "packages")
    for name in sorted(os.listdir(pk)):
        lib = os.path.join(pk, name, ".lake", "build", "lib", "lean")
        if os.path.isdir(lib):
            paths.append(lib)
    return os.pathsep.join(paths)


def out_paths(libdir, mod):
    base = os.path.join(libdir, *mod.split("."))
    return base + ".olean", base + ".ilean"


def compile_one(lean, src, srcfile, mod, libdir, env, logdir):
    olean, ilean = out_paths(libdir, mod)
    os.makedirs(os.path.dirname(olean), exist_ok=True)
    tmp_o, tmp_i, setup = olean + ".tmp", ilean + ".tmp", olean + ".setup.tmp"
    write_setup(setup, mod)
    cmd = [lean, *MORE_ARGS, srcfile, "-o", tmp_o, "-i", tmp_i, "--setup", setup]
    t0 = time.time()
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, errors="replace")
    dt = time.time() - t0
    os.remove(setup)
    if p.returncode == 0 and os.path.exists(tmp_o):
        os.replace(tmp_i, ilean) if os.path.exists(tmp_i) else None
        os.replace(tmp_o, olean)
        return True, dt, ""
    for t in (tmp_o, tmp_i):
        if os.path.exists(t):
            os.remove(t)
    msg = (p.stdout + p.stderr).strip()
    if logdir:
        os.makedirs(logdir, exist_ok=True)
        with open(os.path.join(logdir, mod + ".log"), "w", encoding="utf-8") as f:
            f.write(" ".join(cmd) + "\n\n" + msg + "\n")
    return False, dt, msg


def is_done(libdir, mod):
    olean, _ = out_paths(libdir, mod)
    if not os.path.exists(olean):
        return False
    base = olean[: -len(".olean")]
    return os.path.exists(base + ".trace") or os.path.exists(base + SCHED_MARK)


def log(msg, logfile=None):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    if logfile:
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---- modo verify -------------------------------------------------------------------------------
def cmd_verify(a, proj, src, mods, lean):
    lib = os.path.join(proj, ".lake", "build", "lib", "lean")
    built = [m for m in mods if is_done(lib, m) and os.path.exists(out_paths(lib, m)[0][:-6] + ".trace")]
    random.seed(1)
    sample = random.sample(built, min(a.n, len(built)))
    testdir = os.path.join(a.workdir, "sched-verify")
    shutil.rmtree(testdir, ignore_errors=True)
    env = dict(os.environ, LEAN_PATH=lean_path(proj))
    log(f"verify: recompilando {len(sample)} módulos de {len(built)} ya compilados por Lake, en {testdir}")
    same = diff = fail = 0
    times = []
    lock = threading.Lock()
    it = iter(sample)

    def worker():
        nonlocal same, diff, fail
        while True:
            with lock:
                m = next(it, None)
            if m is None:
                return
            ok, dt, msg = compile_one(lean, src, mods[m], m, testdir, env, os.path.join(testdir, "_fail"))
            with lock:
                times.append(dt)
                if not ok:
                    fail += 1
                    log(f"  FALLO {m}: {msg[:300]}")
                    continue
                a_o = open(out_paths(lib, m)[0], "rb").read()
                b_o = open(out_paths(testdir, m)[0], "rb").read()
                if a_o == b_o:
                    same += 1
                else:
                    diff += 1
                    log(f"  DISTINTO {m}: lake {len(a_o)} B, sched {len(b_o)} B")

    ths = [threading.Thread(target=worker) for _ in range(a.jobs)]
    t0 = time.time()
    [t.start() for t in ths]
    [t.join() for t in ths]
    times.sort()
    log(f"verify: idénticos={same} distintos={diff} fallos={fail} | "
        f"tiempo por módulo mediana {times[len(times)//2]:.1f}s, máx {times[-1]:.1f}s | total {time.time()-t0:.0f}s")
    return 0 if diff == 0 and fail == 0 else 1


# ---- modo build --------------------------------------------------------------------------------
def cmd_build(a, proj, src, mods, lean):
    lib = os.path.join(proj, ".lake", "build", "lib", "lean")
    logfile = a.log
    faildir = os.path.join(a.workdir, "sched-fail")
    deps = {}
    for m, p in mods.items():
        deps[m] = [d for d in parse_imports(p) if d in mods]

    # .olean sin .trace ni marcador = compilación interrumpida: se descarta.
    stale = 0
    for m in mods:
        o, i = out_paths(lib, m)
        if os.path.exists(o) and not is_done(lib, m):
            os.remove(o); stale += 1
        for t in (o + ".tmp", i + ".tmp", o + ".setup.tmp"):
            if os.path.exists(t):
                os.remove(t)
    done = {m for m in mods if is_done(lib, m)}
    todo = [m for m in mods if m not in done]
    log(f"build: {len(mods)} módulos, {len(done)} ya compilados, {len(todo)} por compilar "
        f"({stale} .olean incompletos descartados), {a.jobs} procesos", logfile)

    rdeps = defaultdict(list)
    pending = {}
    for m in todo:
        pending[m] = sum(1 for d in deps[m] if d not in done)
        for d in deps[m]:
            if d not in done:
                rdeps[d].append(m)
    # prioridad: altura en el grafo (camino más largo de dependientes por encima) -> reduce la cola final
    height = {}
    order = []  # orden topológico de todo
    indeg = {m: pending[m] for m in todo}
    q = [m for m in todo if indeg[m] == 0]
    while q:
        m = q.pop()
        order.append(m)
        for r in rdeps[m]:
            indeg[r] -= 1
            if indeg[r] == 0:
                q.append(r)
    if len(order) != len(todo):
        log(f"ERROR: ciclo de imports o dependencia rota ({len(todo)-len(order)} módulos sin ordenar)", logfile)
        return 2
    for m in reversed(order):
        height[m] = 1 + max((height[r] for r in rdeps[m]), default=0)

    env = dict(os.environ, LEAN_PATH=lean_path(proj))
    ready = [(-height[m], m) for m in todo if pending[m] == 0]
    heapq.heapify(ready)
    cv = threading.Condition()
    running = 0
    nok = nfail = 0
    failed = []
    finished_all = threading.Event()
    t_start = time.time()

    def worker():
        nonlocal running, nok, nfail
        while True:
            with cv:
                while not ready and running > 0:
                    cv.wait()
                if not ready:
                    cv.notify_all()
                    return
                _, m = heapq.heappop(ready)
                running += 1
            ok, dt, msg = compile_one(lean, src, mods[m], m, lib, env, faildir)
            if ok:
                open(out_paths(lib, m)[0][:-6] + SCHED_MARK, "w").close()
            with cv:
                running -= 1
                if ok:
                    nok += 1
                    for r in rdeps[m]:
                        pending[r] -= 1
                        if pending[r] == 0:
                            heapq.heappush(ready, (-height[r], r))
                else:
                    nfail += 1
                    failed.append(m)
                    log(f"FALLO {m} ({dt:.0f}s): {msg.splitlines()[0][:300] if msg else 'sin salida'}", logfile)
                cv.notify_all()

    def reporter():
        last_n, last_t = 0, time.time()
        while not finished_all.wait(60):
            now = time.time()
            with cv:
                n, r, f, rd = nok, running, nfail, len(ready)
            rate = (n - last_n) * 60 / (now - last_t)
            last_n, last_t = n, now
            left = len(todo) - n - f
            eta = f"{left / rate / 60:.1f} h" if rate > 0 else "?"
            log(f"sched: {len(done) + n}/{len(mods)} compilados | {rate:.0f}/min | "
                f"en curso {r}, listos {rd}, fallos {f} | faltan ~{eta}", logfile)

    rep = threading.Thread(target=reporter, daemon=True)
    rep.start()
    ths = [threading.Thread(target=worker) for _ in range(a.jobs)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    finished_all.set()
    blocked = len(todo) - nok - nfail
    log(f"build terminado en {(time.time()-t_start)/60:.0f} min: compilados {nok}, fallos {nfail}, "
        f"bloqueados por fallos {blocked}", logfile)
    if failed:
        log("módulos con fallo (logs en " + faildir + "): " + ", ".join(failed[:50]), logfile)
    return 0 if nfail == 0 and blocked == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("proj")
    ap.add_argument("mode", choices=["verify", "build"])
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--log", default=None)
    a = ap.parse_args()
    proj = os.path.abspath(a.proj)
    a.workdir = a.workdir or os.path.dirname(os.path.dirname(proj))
    src = os.path.join(proj, "src")
    lean = lean_binary(proj)
    mods = discover(src)
    log(f"lean: {lean} | módulos en src: {len(mods)}")
    sys.exit(cmd_verify(a, proj, src, mods, lean) if a.mode == "verify" else cmd_build(a, proj, src, mods, lean))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Página de estado de la compilación Lean.

Sirve en 127.0.0.1:<puerto> (Caddy hace de proxy HTTPS):
  /<token>/              página HTML (estática, se actualiza sola por polling)
  /<token>/status.json   estado actual, recalculado cada 15 s
Uso: python3 -I status-web.py <token> [puerto]
"""
import heapq, json, os, re, shutil, sys, threading, time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = sys.argv[1]
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
HOME = os.path.expanduser("~")
PROJ = f"{HOME}/lean-demo/src/lean"
LIB = f"{PROJ}/.lake/build/lib/lean"
LOGS = f"{HOME}/lean-demo/logs"
OUT = f"{HOME}/lean-demo/out"
HIST = f"{HOME}/www-history.csv"
INTERVAL = 15

def count_files(root, ext, newest=None):
    """Cuenta archivos con extensión `ext`. Si `newest` es una lista, la llena con los
    10 más recientes como (mtime, ruta)."""
    n = 0
    heap = []
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.name.endswith(ext):
                        n += 1
                        if newest is not None:
                            try:
                                t = e.stat().st_mtime
                            except FileNotFoundError:
                                continue
                            if len(heap) < 10:
                                heapq.heappush(heap, (t, e.path))
                            elif t > heap[0][0]:
                                heapq.heapreplace(heap, (t, e.path))
        except FileNotFoundError:
            pass
    if newest is not None:
        newest[:] = sorted(heap, reverse=True)
    return n

TOTAL = count_files(f"{PROJ}/src", ".lean")

history = []  # (t, n)
if os.path.exists(HIST):
    with open(HIST) as f:
        for line in f:
            try:
                t, n = line.strip().split(",")
                history.append((int(t), int(n)))
            except ValueError:
                pass

log_offset = 0
err_count = 0
errors = []
last_built = deque(maxlen=10)
built_seen = 0

def scan_build_log():
    global log_offset, err_count, built_seen
    p = f"{LOGS}/build.log"
    try:
        size = os.path.getsize(p)
    except FileNotFoundError:
        return
    if size < log_offset:
        log_offset = 0
    with open(p, "rb") as f:
        f.seek(log_offset)
        data = f.read()
    cut = data.rfind(b"\n")
    if cut < 0:
        return
    log_offset += cut + 1
    for raw in data[: cut + 1].splitlines():
        line = raw.decode("utf-8", "replace")
        if line.startswith("error") or "] FALLO " in line:
            err_count += 1
            if len(errors) < 40:
                errors.append(line[:400])
        elif line.startswith("✔"):
            built_seen += 1
            last_built.append(line[:200])

def tail(path, n, skip=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip("\n") for l in f if not (skip and skip in l)]
        return lines[-n:]
    except FileNotFoundError:
        return []

def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return None

def procs():
    lean = 0
    lake_build = False
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
            if comm == "lean":
                lean += 1
            elif comm in ("lake", "python3") and not lake_build:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    args = f.read().split(b"\0")
                if b"build" in args and (comm == "lake" or any(a.endswith(b"sched.py") for a in args)):
                    lake_build = True
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return lean, lake_build

def meminfo():
    m = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            m[k] = int(v.split()[0]) * 1024
    return m["MemTotal"], m["MemTotal"] - m["MemAvailable"]

def rate(now, n, window):
    for t, c in history:
        if now - t <= window:
            return (n - c) * 60 / (now - t) if now > t else 0.0
    return 0.0

def pipeline_procs():
    """¿Sigue corriendo build-remote.sh? ¿Está en check.lean o leanchecker?"""
    script = False
    checking = None
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        if not args:
            continue
        if any(a.endswith("build-remote.sh") for a in args):
            script = True
        exe = os.path.basename(args[0])
        if exe == "con-leche":
            checking = "conleche"
        elif exe == "nanoda_bin" and checking != "conleche":
            checking = "nanoda"
        elif exe == "lean4export" and checking != "nanoda":
            checking = "lean4export"
            global export_start
            try:
                export_start = os.stat(f"/proc/{pid}").st_ctime
            except FileNotFoundError:
                pass
        elif exe == "leanchecker":
            checking = "leanchecker"
        elif exe == "lean" and any(a.endswith("check.lean") for a in args) and checking is None:
            checking = "check.lean"
    return script, checking


STD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
THEOREMS = ["riemannHypothesis", "LFunction_eq_zero_re", "LFunction_eq_zero_re_of_isPrimitive"]


def verdict(building, script_running, checking, exp):
    """Lista de comprobaciones con estado ok / fail / running / pending y un detalle."""
    out = []
    # 1. Compilación
    plog = "\n".join(tail(f"{LOGS}/progress.log", 400))
    m = re.findall(r"compilados (\d+), fallos (\d+), bloqueados por fallos (\d+)", plog)
    rc = re.findall(r"compilación terminó con código (\d+)", plog)
    if building:
        out.append({"name": "Compilación de los 175 187 módulos", "status": "running",
                    "detail": f"{err_count} fallos hasta ahora" if err_count else "en curso"})
    elif m:
        nok, nf, nb = map(int, m[-1])
        ok = nf == 0 and nb == 0
        out.append({"name": "Compilación de los 175 187 módulos", "status": "ok" if ok else "fail",
                    "detail": "sin errores" if ok else f"{nf} módulos fallaron, {nb} bloqueados por ellos"})
    elif rc:
        out.append({"name": "Compilación de los 175 187 módulos", "status": "ok" if rc[-1] == "0" else "fail",
                    "detail": f"código de salida {rc[-1]}"})
    else:
        out.append({"name": "Compilación de los 175 187 módulos", "status": "pending", "detail": ""})

    # 2-4. check.lean
    co = read(f"{OUT}/check-output.txt")
    names = ["El enunciado usa las definiciones de Mathlib",
             "El enunciado es idéntico a la Hipótesis de Riemann clásica",
             "Axiomas: solo propext, Classical.choice, Quot.sound"]
    if co is None or checking == "check.lean":
        st = "running" if checking == "check.lean" else "pending"
        out += [{"name": n, "status": st, "detail": ""} for n in names]
    else:
        errs = [l for l in co.splitlines() if re.search(r"\berror\b", l)]
        # (a) módulos de definición
        mods = {k: re.sub(r"^\(some (.*)\)$", r"\1", v.strip())
                for k, v in re.findall(r"^(\S+) definido en: (.*)$", co, re.M)}
        okmods = len(mods) == 3 and all(v.startswith("Mathlib.") for v in mods.values())
        out.append({"name": names[0], "status": "ok" if okmods else "fail",
                    "detail": "; ".join(f"{k} → {v}" for k, v in mods.items()) or "no se encontró la salida"})
        # (b) los `example` compilan: no hay ningún error en la salida
        out.append({"name": names[1], "status": "fail" if errs else "ok",
                    "detail": errs[0][:300] if errs else "los dos `example` (Iff.rfl) compilaron sin error"})
        # (c) axiomas
        found = {}
        for thm, lst in re.findall(r"'(\S+)' depends on axioms: \[(.*?)\]", co, re.S):
            found[thm] = {a.strip() for a in lst.replace("\n", " ").split(",") if a.strip()}
        for thm in re.findall(r"'(\S+)' does not depend on any axioms", co):
            found[thm] = set()
        missing = [t for t in THEOREMS if t not in found]
        extra = {t: sorted(a - STD_AXIOMS) for t, a in found.items() if a - STD_AXIOMS}
        if missing or extra:
            det = []
            if missing:
                det.append("sin salida de axiomas para: " + ", ".join(missing))
            for t, a in extra.items():
                det.append(f"{t} usa axiomas NO estándar: {', '.join(a)}")
            out.append({"name": names[2], "status": "fail", "detail": "; ".join(det)})
        else:
            out.append({"name": names[2], "status": "ok",
                        "detail": "; ".join(f"{t}: {', '.join(sorted(found[t])) or 'ninguno'}" for t in THEOREMS)})

    # 5. Exportación para nanoda
    name = "Exportación de la prueba y sus dependencias (lean4export)"
    if exp["running"]:
        det = f"{exp['size_gb']:.1f} GB de ~{EXPORT_EST_GB} GB estimados (techo)"
        if exp["rate"]:
            det += f" · {exp['rate']:.2f} GB/min · faltan ~{exp['eta']}"
        out.append({"name": name, "status": "running", "detail": det})
    elif exp["rc"] is None:
        out.append({"name": name, "status": "pending",
                    "detail": f"{exp['size_gb']:.1f} GB" if exp["size_gb"] else ""})
    else:
        out.append({"name": name, "status": "ok" if exp["rc"] == 0 else "fail",
                    "detail": f"{exp['size_gb']:.1f} GB exportados" + (f" en {exp['elapsed']}" if exp["elapsed"] else "")
                              if exp["rc"] == 0 else f"lean4export terminó con código {exp['rc']}"})

    # 6. nanoda
    name = "nanoda: verificador independiente (Rust) re-verifica toda la prueba"
    nout = read(f"{NANODA}/nanoda-out.txt")
    nerr = read(f"{NANODA}/nanoda-time.err") or ""
    nrc = re.findall(r"NANODA_RC=(\d+)", nerr)
    if checking == "nanoda":
        out.append({"name": name, "status": "running",
                    "detail": "verificando con 180 hilos; solo se permiten propext, Classical.choice, Quot.sound"})
    elif not nrc:
        out.append({"name": name, "status": "pending", "detail": ""})
    else:
        ok = nrc[-1] == "0"
        panic = [l for l in nerr.splitlines() if "panicked" in l or "Error" in l or "error" in l]
        det = ("aceptó todas las declaraciones" if ok else
               (panic[0][:300] if panic else f"código de salida {nrc[-1]}"))
        el = re.findall(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", nerr)
        if ok and el:
            det += f" en {el[-1]}"
        out.append({"name": name, "status": "ok" if ok else "fail", "detail": det})

    for c in out:
        c["group"] = "nanoda" if c["name"].startswith(("Exportación", "nanoda")) else "lean"

    # con-leche
    cl = conleche_info(checking)
    name = "con-leche: verificador con consistencia demostrada re-verifica toda la prueba"
    if cl["running"]:
        det = cl["phase"]
        if cl["pct"] is not None:
            det = f"{cl['phase']} {cl['pct']}% ({cl['n']:,} declaraciones), t={cl['t']}"
        out.append({"name": name, "status": "running", "detail": det, "group": "conleche"})
    elif cl["rc"] is None:
        out.append({"name": name, "status": "pending", "detail": "", "group": "conleche"})
    else:
        ok = cl["rc"] == 0 and re.search(r"accepted \d+ declarations", cl["verdict"]) is not None
        det = (cl["verdict"] or f"código de salida {cl['rc']}") + (f" en {cl['elapsed']}" if cl["elapsed"] else "")
        out.append({"name": name, "status": "ok" if ok else "fail", "detail": det, "group": "conleche"})
    return out


CONLECHE = f"{HOME}/conleche"


def conleche_info(checking):
    info = {"running": checking == "conleche", "phase": "", "pct": None, "n": 0, "t": "",
            "rc": None, "verdict": "", "elapsed": None}
    p = f"{CONLECHE}/progress.err"
    try:
        size = os.path.getsize(p)
        with open(p, "rb") as f:
            f.seek(max(0, size - 65536))
            tailtxt = f.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return info
    lines = [l for l in tailtxt.splitlines() if l.startswith("con-leche:")]
    if lines:
        last = lines[-1]
        m = re.match(r"con-leche: (\w+) (\d+) \((\d+)%\).*?t=([\d.]+s)", last)
        if m:
            info.update(phase={"check": "verificando", "parse": "leyendo"}.get(m.group(1), m.group(1)),
                        n=int(m.group(2)), pct=int(m.group(3)), t=m.group(4))
        else:
            info["phase"] = last[len("con-leche: "):][:120]
    rc = re.findall(r"CONLECHE_RC=(\d+)", tailtxt)
    el = re.findall(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", tailtxt)
    if rc:
        info["rc"] = int(rc[-1])
        info["running"] = False
    if el:
        info["elapsed"] = el[-1]
    out = read(f"{CONLECHE}/out.txt")
    if out:
        info["verdict"] = out.strip().splitlines()[-1][:200]
    return info


def summarize(checks, group):
    items = [c for c in checks if c.get("group") == group]
    sts = [c["status"] for c in items]
    if any(x == "fail" for x in sts):
        st = "fail"
        det = next(c for c in items if c["status"] == "fail")["name"]
    elif sts and all(x == "ok" for x in sts):
        st, det = "ok", ""
    elif any(x == "running" for x in sts):
        st = "running"
        det = next(c for c in items if c["status"] == "running")["name"]
    else:
        st, det = "pending", ""
    return {"status": st, "detail": det}


NANODA = f"{HOME}/nanoda"
EXPORT_EST_GB = 105
export_hist = deque(maxlen=200)
export_start = None
EXP_HIST = f"{HOME}/www-export-history.csv"
export_series = []  # (t, bytes) persistente, para el gráfico
if os.path.exists(EXP_HIST):
    with open(EXP_HIST) as f:
        for line in f:
            try:
                t, b = line.strip().split(",")
                export_series.append((int(t), int(b)))
            except ValueError:
                pass


def export_info(checking):
    path = f"{NANODA}/main.ndjson"
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        size = 0
    now = time.time()
    running = checking == "lean4export"
    if running:
        export_hist.append((now, size))
        new = []
        if not export_series and export_start:
            new.append((int(export_start), 0))
        new.append((int(now), size))
        export_series.extend(new)
        with open(EXP_HIST, "a") as f:
            for t, b in new:
                f.write(f"{t},{b}\n")
    err = read(f"{NANODA}/export.err") or ""
    rc = re.findall(r"EXPORT_RC=(\d+)", err)
    el = re.findall(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", err)
    rate = eta = None
    old = [(t, s) for t, s in export_hist if now - t >= 120]
    if running and old:
        t0, s0 = old[-1]
        rate = (size - s0) / 2**30 / ((now - t0) / 60)
        if rate > 0:
            mins = max(0, (EXPORT_EST_GB - size / 2**30) / rate)
            eta = f"{int(mins // 60)}h {int(mins % 60):02d}m"
    return {"running": running, "size_gb": size / 2**30, "rate": rate, "eta": eta,
            "rc": int(rc[-1]) if rc else None, "elapsed": el[-1] if el else None}


status = {}
lock = threading.Lock()

def update():
    now = int(time.time())
    newest = []
    n = count_files(LIB, ".olean", newest)
    recent = [f"hace {max(0, int(now - t)):>3d}s  " + os.path.relpath(p, LIB)[:-len(".olean")].replace("/", ".")
              for t, p in newest]
    history.append((now, n))
    with open(HIST, "a") as f:
        f.write(f"{now},{n}\n")
    scan_build_log()
    lean, building = procs()
    mem_total, mem_used = meminfo()
    du = shutil.disk_usage("/")
    r10, r60 = rate(now, n, 600), rate(now, n, 3600)
    left = TOTAL - n
    eta = int(left / r10 * 60) if r10 > 0 else None
    script_running, checking = pipeline_procs()
    exp = export_info(checking)
    checks = verdict(building, script_running, checking, exp)
    if building:
        state = "compilando"
    elif script_running or checking in ("lean4export", "nanoda", "conleche"):
        state = "verificando"
    elif any(c["status"] == "fail" for c in checks):
        state = "fallo"
    elif all(c["status"] in ("ok", "skip") for c in checks):
        state = "verificado"
    else:
        state = "detenido"
    # historial reducido para el gráfico (~300 puntos)
    hb = history
    top = max(c for _, c in history)
    if top >= TOTAL:
        cut = next(i for i, (_, c) in enumerate(history) if c >= TOTAL)
        hb = history[: cut + 1]
    step = max(1, len(hb) // 300)
    chart = hb[::step]
    if chart[-1] != hb[-1]:
        chart.append(hb[-1])
    es = export_series
    estep = max(1, len(es) // 300)
    echart = [(t, round(b / 2**30, 2)) for t, b in es[::estep]]
    if es and (not echart or echart[-1][0] != es[-1][0]):
        echart.append((es[-1][0], round(es[-1][1] / 2**30, 2)))
    s = {
        "updated": now, "state": state, "built": n, "total": TOTAL,
        "rate10": round(r10, 1), "rate60": round(r60, 1),
        "eta_seconds": eta, "finish_epoch": now + eta if eta else None,
        "lean_procs": lean, "load": open("/proc/loadavg").read().split()[:3],
        "cpus": os.cpu_count(),
        "mem_used": mem_used, "mem_total": mem_total,
        "disk_used": du.used, "disk_total": du.total,
        "errors_count": err_count, "errors": errors,
        "last_built": recent,
        "progress_log": tail(f"{LOGS}/progress.log", 15, skip="Downloaded:"),
        "check_output": read(f"{OUT}/check-output.txt"),
        "leanchecker": read(f"{OUT}/leanchecker-result.txt"),
        "history": chart,
        "export_history": echart,
        "checks": checks,
        "summary": {"lean": summarize(checks, "lean"), "nanoda": summarize(checks, "nanoda"),
                    "conleche": summarize(checks, "conleche")},
        "conleche": conleche_info(checking),
        "export": {**exp, "est_gb": EXPORT_EST_GB},
    }
    with lock:
        status.clear()
        status.update(s)

def loop():
    while True:
        try:
            update()
        except Exception as e:  # que un fallo puntual no tumbe la página
            with lock:
                status["page_error"] = repr(e)
        time.sleep(INTERVAL)

PAGE = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lean build</title>
<style>
:root{--c:#2563eb}
body{font-family:system-ui,sans-serif;max-width:920px;margin:2em auto;padding:0 1em;color:#1f2937}
h1{font-size:1.4em;margin-bottom:.3em} h2{font-size:1.05em;margin-top:1.6em}
.state{color:var(--c);font-weight:600}
.bar{background:#e5e7eb;border-radius:6px;height:22px;overflow:hidden}
.fill{background:var(--c);height:100%;width:0;transition:width 1s}
.big{font-size:1.3em;margin:.5em 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:1em 0}
.card{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px}
.card .k{color:#6b7280;font-size:.8em} .card .v{font-size:1.15em;font-weight:600;margin-top:2px}
pre{background:#f3f4f6;padding:10px;overflow-x:auto;font-size:12px;white-space:pre-wrap;margin:0}
#meta{color:#6b7280;font-size:.85em} .stale{color:#dc2626!important}
svg{width:100%;height:180px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px}
.hidden{display:none}
#verdict{border-radius:10px;padding:14px 18px;margin:1em 0;font-size:1.15em;font-weight:600;color:#fff}
#verdict small{display:block;font-weight:400;font-size:.8em;opacity:.95;margin-top:4px;color:#fff}
.checks{list-style:none;padding:0;margin:.5em 0}
.checks li{padding:6px 0;border-bottom:1px solid #f3f4f6}
.checks .d{color:#6b7280;font-size:.85em;margin-left:1.8em;word-break:break-word}
.ic{display:inline-block;width:1.6em}
.panels{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:1em 0}
@media(max-width:600px){.panels{grid-template-columns:1fr}}
.panel{border-radius:10px;padding:12px 14px;border:2px solid #e5e7eb;background:#f9fafb}
.panel .pt{font-size:.85em;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.panel .pv{font-size:1.25em;font-weight:700;margin-top:4px}
.panel .pd{font-size:.85em;color:#4b5563;margin-top:4px}
</style></head><body>
<h1>Compilación Lean: <span class="state" id="state">…</span></h1>
<div class="panels">
 <div class="panel" id="p-lean"><div class="pt">Compilador de Lean</div><div class="pv" id="pv-lean">…</div><div class="pd" id="pd-lean"></div></div>
 <div class="panel" id="p-nanoda"><div class="pt">Verificación independiente (nanoda)</div><div class="pv" id="pv-nanoda">…</div><div class="pd" id="pd-nanoda"></div></div>
 <div class="panel" id="p-conleche"><div class="pt">Verificador con consistencia demostrada (con-leche)</div><div class="pv" id="pv-conleche">…</div><div class="pd" id="pd-conleche"></div></div>
</div>
<div id="verdict" class="hidden"></div>
<h2>Comprobaciones</h2><ul class="checks" id="checks"></ul>
<div style="font-weight:600;margin-bottom:4px">Compilación de módulos <span id="buildstate" style="font-weight:400;color:#6b7280"></span></div>
<div class="bar"><div class="fill" id="fill"></div></div>
<div id="clbox" class="hidden" style="margin-top:1em">
 <div style="font-weight:600;margin-bottom:4px">Verificación con con-leche <span id="clstate" style="font-weight:400;color:#6b7280"></span></div>
 <div class="bar"><div class="fill" id="clfill" style="background:#0d9488"></div></div>
 <div id="cltext" style="margin-top:4px"></div>
</div>
<div id="expbox" class="hidden" style="margin-top:1em">
 <div style="font-weight:600;margin-bottom:4px">Exportación para nanoda <span id="expstate" style="font-weight:400;color:#6b7280"></span></div>
 <div class="bar"><div class="fill" id="expfill" style="background:#7c3aed"></div></div>
 <div id="exptext" style="margin-top:4px"></div>
</div>
<div class="big"><b id="built">–</b> / <span id="total">–</span> módulos (<span id="pct">–</span>%)</div>
<div id="meta">Cargando…</div>
<div class="grid">
 <div class="card"><div class="k">Ritmo (últimos 10 min)</div><div class="v" id="rate10">–</div></div>
 <div class="card"><div class="k">Ritmo (última hora)</div><div class="v" id="rate60">–</div></div>
 <div class="card"><div class="k">Tiempo restante</div><div class="v" id="eta">–</div></div>
 <div class="card"><div class="k">Fin estimado (tu hora local)</div><div class="v" id="fin">–</div></div>
 <div class="card"><div class="k">Procesos lean</div><div class="v" id="procs">–</div></div>
 <div class="card"><div class="k">Carga CPU (1/5/15 min)</div><div class="v" id="load">–</div></div>
 <div class="card"><div class="k">RAM</div><div class="v" id="mem">–</div></div>
 <div class="card"><div class="k">Disco</div><div class="v" id="disk">–</div></div>
 <div class="card"><div class="k">Errores</div><div class="v" id="errc">–</div></div>
</div>
<h2>Avance</h2>
<div style="color:#6b7280;font-size:.85em;margin:4px 0">Compilación (módulos)</div>
<svg id="chart" viewBox="0 0 900 180" preserveAspectRatio="none"></svg>
<div id="chart2box" class="hidden"><div style="color:#6b7280;font-size:.85em;margin:10px 0 4px">Exportación para nanoda (GB)</div>
<svg id="chart2" viewBox="0 0 900 180" preserveAspectRatio="none"></svg></div>
<div id="errbox" class="hidden"><h2>Errores</h2><pre id="errors"></pre></div>
<div id="checkbox" class="hidden"><h2>check.lean</h2><pre id="check"></pre></div>
<h2>Últimos módulos compilados</h2><pre id="last"></pre>
<h2>Registro de progreso</h2><pre id="plog"></pre>
<script>
const $=id=>document.getElementById(id);
const GB=b=>(b/2**30).toFixed(0)+' GB';
const dur=s=>{if(s==null)return'–';const h=Math.floor(s/3600),m=Math.floor(s%3600/60);return h+'h '+String(m).padStart(2,'0')+'m'};
let last=null, ok=true;
function chart(id,h,ymax,color,label,refLabel){
  const svg=$(id); if(!h||h.length<2){svg.innerHTML='';return}
  const t0=h[0][0],t1=h[h.length-1][0]||t0+1,W=900,H=180,P=6;
  const x=t=>P+(t-t0)/(t1-t0||1)*(W-2*P), y=n=>H-P-Math.min(n,ymax)/ymax*(H-2*P);
  const pts=h.map(p=>x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)).join(' ');
  const fmt=t=>new Date(t*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  const ref=refLabel?`<line x1="${P}" x2="${W-P}" y1="${y(ymax)}" y2="${y(ymax)}" stroke="#9ca3af" stroke-dasharray="6 4" vector-effect="non-scaling-stroke"/>`+
    `<text x="${W-8}" y="${y(ymax)+14}" font-size="11" fill="#9ca3af" text-anchor="end">${refLabel}</text>`:'';
  svg.innerHTML=ref+`<polyline fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke" points="${pts}"/>`+
    `<text x="8" y="16" font-size="12" fill="#6b7280">${label(h[h.length-1][1])}</text>`+
    `<text x="8" y="${H-10}" font-size="11" fill="#6b7280">${fmt(t0)}</text>`+
    `<text x="${W-8}" y="${H-10}" font-size="11" fill="#6b7280" text-anchor="end">${fmt(t1)}</text>`;
}
function render(s){
  const colors={compilando:'#2563eb',verificando:'#7c3aed',verificado:'#16a34a',fallo:'#dc2626',detenido:'#d97706'};
  document.documentElement.style.setProperty('--c', (s.errors_count>0||s.state==='fallo')?'#dc2626':(colors[s.state]||'#2563eb'));
  const pct=100*s.built/s.total;
  $('state').textContent={compilando:'compilando',verificando:'verificando la prueba',verificado:'VERIFICADA',fallo:'FALLÓ',detenido:'detenida'}[s.state]||s.state;
  const icons={ok:'✔',fail:'✘',running:'⏳',pending:'·',skip:'–'}, icol={ok:'#16a34a',fail:'#dc2626',running:'#7c3aed',pending:'#9ca3af',skip:'#9ca3af'};
  const ul=$('checks'); ul.innerHTML='';
  for(const c of (s.checks||[])){
    const li=document.createElement('li');
    const ic=document.createElement('span'); ic.className='ic'; ic.textContent=icons[c.status]||'?'; ic.style.color=icol[c.status];
    li.appendChild(ic); li.appendChild(document.createTextNode(c.name));
    if(c.detail){const d=document.createElement('div'); d.className='d'; d.textContent=c.detail; li.appendChild(d)}
    ul.appendChild(li);
  }
  const P={
    lean:{ok:['✔ Verificado','Compiló los 175 187 módulos sin errores (cada teorema pasó por el kernel de Lean); el enunciado es la Hipótesis de Riemann de Mathlib y solo usa propext, Classical.choice y Quot.sound.'],
          fail:['✘ Falló',''], running:['⏳ En curso',''], pending:['· Pendiente','']},
    nanoda:{ok:['✔ Verificado','Un verificador de tipos independiente, escrito en Rust, re-verificó toda la cadena de la prueba.'],
          fail:['✘ Falló',''], running:['⏳ En curso',''], pending:['· Pendiente','Empieza al terminar la exportación.']},
    conleche:{ok:['✔ Verificado','con-leche, cuya consistencia está demostrada formalmente en Lean (no acepta pruebas de False), re-verificó toda la cadena de la prueba.'],
          fail:['✘ Falló',''], running:['⏳ En curso',''], pending:['· Pendiente','']}};
  const PC={ok:['#16a34a','#f0fdf4'],fail:['#dc2626','#fef2f2'],running:['#7c3aed','#f5f3ff'],pending:['#9ca3af','#f9fafb']};
  for(const g of ['lean','nanoda','conleche']){
    const sm=(s.summary||{})[g]||{status:'pending',detail:''};
    const [txt,desc]=P[g][sm.status]||['?',''];
    $('pv-'+g).textContent=txt; $('pv-'+g).style.color=PC[sm.status][0];
    $('p-'+g).style.borderColor=PC[sm.status][0]; $('p-'+g).style.background=PC[sm.status][1];
    let d=desc;
    if(sm.status!=='ok'&&sm.detail){ d=sm.detail; }
    if(g==='nanoda'&&sm.status==='running'&&s.export&&s.export.running){ d='Exportando la prueba: '+s.export.size_gb.toFixed(1)+' GB de ~'+s.export.est_gb+' GB estimados'+(s.export.eta?' · faltan ~'+s.export.eta:''); }
    $('pd-'+g).textContent=d;
  }
  const v=$('verdict');
  if(s.state==='verificado'){v.className='';v.style.background='#16a34a';
    v.innerHTML='✔ Prueba verificada<small>Compiló completa, el enunciado es la Hipótesis de Riemann de Mathlib, solo usa los axiomas estándar y nanoda y con-leche (verificadores independientes) re-verificaron toda la cadena de la prueba.</small>'}
  else if(s.state==='fallo'){v.className='';v.style.background='#dc2626';
    v.innerHTML='✘ La verificación falló<small>Mira abajo qué comprobación falló.</small>'}
  else if(s.state==='detenido'){v.className='';v.style.background='#d97706';
    v.innerHTML='⚠ El proceso se detuvo sin terminar<small>No hay compilación ni verificación en curso y faltan comprobaciones.</small>'}
  else v.className='hidden';
  $('fill').style.width=pct.toFixed(2)+'%';
  $('buildstate').textContent=s.built>=s.total?'(terminada)':(s.state==='compilando'?'(en curso)':'');
  const c=s.conleche;
  if(c && (c.running || c.rc!==null)){
    $('clbox').classList.remove('hidden');
    const ok=c.rc===0 && /accepted \d+ declarations/.test(c.verdict||''), bad=c.rc!==null && !ok;
    const cp=ok?100:(c.pct||0);
    $('clfill').style.width=cp+'%';
    $('clfill').style.background=bad?'#dc2626':(ok?'#16a34a':'#0d9488');
    $('clstate').textContent=ok?'(terminada)':(bad?'(falló)':'(en curso)');
    $('cltext').textContent=c.rc!==null?(c.verdict||('código '+c.rc))+(c.elapsed?' · '+c.elapsed:''):(c.phase+(c.pct!==null?' '+c.pct+'% · '+c.n.toLocaleString()+' declaraciones · t='+c.t:''));
  } else $('clbox').classList.add('hidden');
  const e=s.export;
  if(e && (e.running || e.rc!==null || e.size_gb>0)){
    $('expbox').classList.remove('hidden');
    const done=e.rc===0, ep=done?100:Math.min(100,100*e.size_gb/e.est_gb);
    $('expfill').style.width=ep.toFixed(1)+'%';
    $('expfill').style.background=e.rc!==null&&e.rc!==0?'#dc2626':(done?'#16a34a':'#7c3aed');
    $('expstate').textContent=done?'(terminada)':(e.rc!==null?'(falló)':(e.running?'(en curso)':'(detenida)'));
    let t=e.size_gb.toFixed(1)+' GB';
    if(done) t+=' exportados'+(e.elapsed?' en '+e.elapsed:'');
    else { t+=' de ~'+e.est_gb+' GB estimados ('+ep.toFixed(1)+'%; el total real puede ser menor)';
      if(e.rate) t+=' · '+e.rate.toFixed(2)+' GB/min · faltan ~'+e.eta; }
    $('exptext').textContent=t;
  } else $('expbox').classList.add('hidden');
  $('built').textContent=s.built.toLocaleString(); $('total').textContent=s.total.toLocaleString();
  $('pct').textContent=pct.toFixed(2);
  document.title=`${pct.toFixed(1)}% · Lean build`;
  $('rate10').textContent=s.rate10+' /min'; $('rate60').textContent=s.rate60+' /min';
  $('eta').textContent=s.state==='compilando'?dur(s.eta_seconds):'–';
  $('fin').textContent=s.finish_epoch&&s.state==='compilando'?new Date(s.finish_epoch*1000).toLocaleString([], {weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'–';
  $('procs').textContent=s.lean_procs; $('load').textContent=s.load.join(' / ')+' ('+s.cpus+' núcleos)';
  $('mem').textContent=GB(s.mem_used)+' / '+GB(s.mem_total);
  $('disk').textContent=GB(s.disk_used)+' / '+GB(s.disk_total);
  $('errc').textContent=s.errors_count;
  $('errbox').classList.toggle('hidden',!s.errors_count); $('errors').textContent=(s.errors||[]).join('\n');
  $('checkbox').classList.toggle('hidden',!s.check_output); $('check').textContent=s.check_output||'';
  $('last').textContent=(s.last_built||[]).join('\n'); $('plog').textContent=(s.progress_log||[]).join('\n');
  chart('chart',s.history,s.total,'#2563eb',v=>v.toLocaleString()+' módulos');
  const eh=s.export_history||[];
  $('chart2box').classList.toggle('hidden',eh.length<2);
  if(eh.length>=2){
    const est=(s.export&&s.export.est_gb)||105, mx=Math.max(est,...eh.map(p=>p[1]));
    const done=s.export&&s.export.rc===0;
    chart('chart2',eh,mx,done?'#16a34a':'#7c3aed',v=>v.toFixed(1)+' GB',done?'':'~'+est+' GB estimados (techo)');
  }
}
async function poll(){
  try{
    const r=await fetch('status.json',{cache:'no-store'}); if(!r.ok) throw r.status;
    const s=await r.json(); last=s; ok=true; render(s);
  }catch(e){ ok=false }
}
setInterval(()=>{
  if(!last) return;
  const age=Math.round(Date.now()/1000-last.updated);
  $('meta').textContent=(ok?'':'⚠ sin conexión con el servidor · ')+'datos de hace '+age+' s · se actualiza sola';
  $('meta').classList.toggle('stale',!ok||age>90);
},1000);
poll(); setInterval(poll,10000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in (f"/{TOKEN}", f"/{TOKEN}/"):
            if path == f"/{TOKEN}":
                self.send_response(301); self.send_header("Location", f"/{TOKEN}/"); self.end_headers(); return
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        elif path == f"/{TOKEN}/status.json":
            with lock:
                body = json.dumps(status, ensure_ascii=False).encode()
            ctype = "application/json; charset=utf-8"
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    update()
    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()

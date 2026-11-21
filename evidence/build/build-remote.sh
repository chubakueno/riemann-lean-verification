#!/usr/bin/env bash
# Compila y verifica la demostración Lean de https://alpo.ge/lean.tar.gz.part01..14
# en una máquina Linux (Ubuntu 22.04/24.04). Pensado para AWS c7a.48xlarge + 2 TB gp3.
#
# Uso (dentro de tmux, para que sobreviva si se corta el SSH):
#   tmux new -s lean
#   bash build-remote.sh            # todo: descarga, compila, verifica, empaqueta
#   (Ctrl+B y luego D para salir de tmux sin detenerlo; `tmux attach -t lean` para volver)
#
# Es reanudable: si se interrumpe, vuelve a ejecutarlo y sigue donde quedó.
#
# Variables opcionales:
#   WORK=/data/lean-demo   directorio de trabajo (por defecto ~/lean-demo)
#   JOBS=192               procesos de compilación en paralelo (por defecto: nproc)
#   CHECK_THREADS=48       hilos para leanchecker (cada uno carga un entorno completo)
#   SKIP_LEANCHECKER=1     omite la verificación con leanchecker

set -euo pipefail

WORK="${WORK:-$HOME/lean-demo}"
JOBS="${JOBS:-$(nproc)}"
CHECK_THREADS="${CHECK_THREADS:-48}"
EXPECTED_SHA256="9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc"
BASE_URL="https://alpo.ge/lean.tar.gz.part"
PROJ="$WORK/src/lean"
LOGS="$WORK/logs"
OUT="$WORK/out"

mkdir -p "$WORK/dl" "$WORK/src" "$LOGS" "$OUT"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOGS/progress.log"; }

# ---------------------------------------------------------------- 0. Sistema
log "== 0. Preparando el sistema ($(nproc) CPUs, $(free -g | awk '/Mem:/{print $2}') GB RAM)"
if ! command -v git >/dev/null || ! command -v zstd >/dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y git curl zstd tmux
fi
# Cada proceso lean mapea en memoria todos los .olean que importa (aquí >180 000 módulos,
# varios mapeos por módulo). El límite por defecto de Linux (65 530) no alcanza.
sudo sysctl -w vm.max_map_count=4194304
ulimit -n 1048576 2>/dev/null || ulimit -n "$(ulimit -Hn)"

# ---------------------------------------------------------------- 1. Lean
if [ ! -x "$HOME/.elan/bin/lake" ]; then
  log "== 1. Instalando elan"
  curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain none
fi
export PATH="$HOME/.elan/bin:$PATH"

# ---------------------------------------------------------------- 2. Descarga
cd "$WORK"
if [ ! -f "$WORK/lean.tar.gz" ] || ! echo "$EXPECTED_SHA256  $WORK/lean.tar.gz" | sha256sum -c --quiet; then
  log "== 2. Descargando las 14 partes"
  for i in $(seq -w 1 14); do
    curl -sSfL --retry 5 -o "dl/lean.tar.gz.part$i" "$BASE_URL$i"
  done
  cat dl/lean.tar.gz.part* > lean.tar.gz
  echo "$EXPECTED_SHA256  $WORK/lean.tar.gz" | sha256sum -c \
    || { log "ERROR: el archivo descargado NO coincide con el revisado localmente"; exit 1; }
fi
log "Archivo verificado (sha256 coincide con el revisado localmente)"

if [ ! -f "$PROJ/lakefile.toml" ]; then
  log "== 2b. Extrayendo"
  tar -xzf lean.tar.gz -C "$WORK/src"
fi

# ---------------------------------------------------------------- 3. mathlib
cd "$PROJ"
log "== 3. Dependencias y caché de mathlib"
lake exe cache get 2>&1 | tail -3 | tee -a "$LOGS/progress.log"

# ---------------------------------------------------------------- 4. Compilación
# Limpieza en segundo plano: lake escribe un *.setup.json de ~6 MB o más por módulo
# (lista de todos sus imports). Solo se usa al lanzar la compilación de ese módulo, así que
# se borra en cuanto su .olean existe y es más reciente.
IR="$PROJ/.lake/build/ir"; LIB="$PROJ/.lake/build/lib/lean"
cleanup_loop() {
  while true; do
    if [ -d "$IR" ]; then
      find "$IR" -name '*.setup.json' -mmin +1 -print0 2>/dev/null |
      while IFS= read -r -d '' f; do
        rel="${f#$IR/}"; o="$LIB/${rel%.setup.json}.olean"
        if [ -f "$o" ] && [ "$o" -nt "$f" ]; then rm -f "$f"; fi
      done
    fi
    sleep 300
  done
}
cleanup_loop & CLEAN_PID=$!
trap 'kill $CLEAN_PID 2>/dev/null || true' EXIT

progress_loop() {
  local total; total=$(find "$PROJ/src" -name '*.lean' | wc -l)
  while true; do
    sleep 900
    local n; n=$(find "$LIB" -name '*.olean' 2>/dev/null | wc -l)
    log "progreso: $n / $total módulos | disco: $(df -h "$WORK" | awk 'NR==2{print $3" usados, "$4" libres"}') | RAM usada: $(free -g | awk '/Mem:/{print $3}') GB"
  done
}
progress_loop & PROG_PID=$!
trap 'kill $CLEAN_PID $PROG_PID 2>/dev/null || true' EXIT

START=$(date +%s)
set +e
if [ "${BUILDER:-lake}" = "sched" ]; then
  # Planificador propio (sched.py): mismos .olean que Lake (verificado byte a byte),
  # sin el costo de Lake de recorrer el árbol transitivo de imports por módulo.
  log "== 4. sched.py build con $JOBS procesos en paralelo (log: $LOGS/build.log)"
  python3 -I "$HOME/sched.py" "$PROJ" build --jobs "$JOBS" --workdir "$WORK" --log "$LOGS/progress.log" \
    > "$LOGS/build.log" 2>&1
else
  log "== 4. lake build con $JOBS procesos en paralelo (log: $LOGS/build.log)"
  LEAN_NUM_THREADS="$JOBS" lake build > "$LOGS/build.log" 2>&1
fi
BUILD_RC=$?
set -e
log "compilación terminó con código $BUILD_RC en $(( ($(date +%s)-START)/60 )) min"
if [ $BUILD_RC -ne 0 ]; then
  grep -E '^error|FALLO' "$LOGS/build.log" | head -40 | tee -a "$LOGS/progress.log"
  log "La compilación falló. Revisa $LOGS/build.log. Se puede reintentar ejecutando de nuevo el script."
  exit $BUILD_RC
fi

# ---------------------------------------------------------------- 5. Verificación del enunciado
log "== 5. check.lean (enunciado y axiomas)"
cat > "$WORK/check.lean" <<'EOF'
import Main

/-! Verificación del enunciado y de los axiomas usados. -/

-- 1. ¿En qué módulo está definido cada nombre? Deben ser módulos de Mathlib.
open Lean in
#eval show MetaM Unit from do
  for n in [``RiemannHypothesis, ``riemannZeta, ``DirichletCharacter.LFunction] do
    IO.println s!"{n} definido en: {(← findModuleOf? n)}"

-- 2. La definición, tal cual la ve Lean.
#print RiemannHypothesis

-- 3. El enunciado es exactamente el clásico (Iff.rfl solo compila si son idénticos por definición).
example : RiemannHypothesis ↔
    ∀ s : ℂ, riemannZeta s = 0 → (¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2 :=
  Iff.rfl

example : ∀ s : ℂ, riemannZeta s = 0 → (¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2 :=
  riemannHypothesis

-- 4. Axiomas: solo deberían aparecer propext, Classical.choice, Quot.sound.
#print axioms riemannHypothesis
#print axioms LFunction_eq_zero_re
#print axioms LFunction_eq_zero_re_of_isPrimitive
EOF
lake env lean "$WORK/check.lean" 2>&1 | tee "$OUT/check-output.txt" | tee -a "$LOGS/progress.log"

# ---------------------------------------------------------------- 6. Empaquetado
log "== 6. Empaquetando .lake/build/lib para descargar"
tar -C "$PROJ/.lake/build" -cf - lib | zstd -T0 -10 -o "$OUT/lib.tar.zst" -f
sha256sum "$OUT/lib.tar.zst" > "$OUT/lib.tar.zst.sha256"
cp "$LOGS/build.log" "$OUT/" 2>/dev/null || true
log "Paquete: $OUT/lib.tar.zst ($(du -h "$OUT/lib.tar.zst" | cut -f1))"

# ---------------------------------------------------------------- 7. leanchecker
# Vuelve a pasar por el kernel cada declaración de cada módulo del proyecto (mathlib se da
# por bueno: viene de la caché oficial). Detecta cualquier "environment hacking".
if [ "${SKIP_LEANCHECKER:-0}" != "1" ]; then
  log "== 7. leanchecker sobre todos los módulos del proyecto ($CHECK_THREADS hilos)"
  for lib in Statements Main BuildAid Supplements Lemmata PositivityTheory ReciprocityTheory \
             GroundTheory CompanionTheory Formalism Development; do
    log "leanchecker $lib ..."
    if LEAN_NUM_THREADS="$CHECK_THREADS" lake env leanchecker "$lib" >> "$LOGS/leanchecker.log" 2>&1; then
      log "  OK $lib"
    else
      log "  FALLO $lib, ver $LOGS/leanchecker.log"
      tail -20 "$LOGS/leanchecker.log" | tee -a "$LOGS/progress.log"
      echo "FALLO en $lib" >> "$OUT/leanchecker-result.txt"
    fi
  done
  [ -f "$OUT/leanchecker-result.txt" ] || echo "leanchecker: todos los módulos OK" > "$OUT/leanchecker-result.txt"
  cat "$OUT/leanchecker-result.txt" | tee -a "$LOGS/progress.log"
fi

log "== LISTO. Resultados en $OUT:"
ls -lh "$OUT" | tee -a "$LOGS/progress.log"
log "Recuerda descargar lo que necesites y luego TERMINAR la instancia y BORRAR el volumen."

#!/usr/bin/env bash
# Checks, with `con-leche --compare`, that main.ndjson contains proofs of the statements in
# Challenge.lean, whose definitions come from official Mathlib (not from the project).
#
# Usage (Linux x86_64, at least 33 GB of RAM):
#   bash verify.sh /path/to/main.ndjson[.zst]
#
# Uses only public sources at pinned commits:
#   - Mathlib      0df444a360eaa60ab8c11dca51a86af692955474  (via this directory's lakefile.toml)
#   - lean4export  v4.33.0 = 15f6055e299ad5b89345e533cc2192f4cc00f659, built with Lean v4.33.1
#   - con-leche    11d8ff13c86675e6ba4b6ca6cd1e4986154516d9
#
# Environment variables: WORK (scratch directory, default ~/rh-verify), JOBS (default nproc).
set -euo pipefail

SOLUTION="${1:?usage: bash verify.sh /path/to/main.ndjson[.zst]}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$HOME/rh-verify}"
JOBS="${JOBS:-$(nproc)}"
EXPECTED_SOLUTION_SHA256="4301ce4828d397c728e87f3e6a1251aa42abe5e12809bb9e0b73cc3d33072e7e"
EXPECTED_CHALLENGE_SHA256="38ae485659b1b1019061746ece9d2cf404765a1cca47eba618798970edaf2f2a"
LEAN4EXPORT_REV="15f6055e299ad5b89345e533cc2192f4cc00f659"
CONLECHE_REV="11d8ff13c86675e6ba4b6ca6cd1e4986154516d9"
THEOREMS="riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive"

mkdir -p "$WORK"
log() { echo "[$(date '+%F %T')] $*"; }

# 0. Tools
NEED=(git curl cc)
[[ "$SOLUTION" == *.zst ]] && NEED+=(zstd)
for t in "${NEED[@]}"; do
  if ! command -v "$t" >/dev/null; then
    log "Missing $t; installing prerequisites with apt-get"
    sudo apt-get update -y && sudo apt-get install -y git curl zstd build-essential
    break
  fi
done
if [ ! -x "$HOME/.elan/bin/lake" ]; then
  curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain none
fi
export PATH="$HOME/.elan/bin:$PATH"
sudo -n sysctl -w vm.max_map_count=4194304 >/dev/null 2>&1 || true
ulimit -c 0

# 1. The solution: decompress if needed and check its sha256
if [[ "$SOLUTION" == *.zst ]]; then
  log "Decompressing $SOLUTION"
  zstd -d -T0 -f "$SOLUTION" -o "$WORK/main.ndjson"
  SOLUTION="$WORK/main.ndjson"
fi
log "sha256 of the solution (may take a minute or two)"
GOT=$(sha256sum "$SOLUTION" | cut -d' ' -f1)
echo "  $GOT"
if [ "$GOT" != "$EXPECTED_SOLUTION_SHA256" ]; then
  log "WARNING: sha256 differs from the published one ($EXPECTED_SOLUTION_SHA256)."
  log "         Checking anyway, but you are checking a DIFFERENT file."
fi

# 2. The challenge: build Challenge.lean against official Mathlib
log "Building the challenge against Mathlib 0df444a3"
rm -rf "$WORK/challenge" && mkdir -p "$WORK/challenge"
cp "$HERE/Challenge.lean" "$HERE/lakefile.toml" "$HERE/lean-toolchain" "$WORK/challenge/"
cd "$WORK/challenge"
lake exe cache get
lake build Challenge

# 3. Export the challenge with lean4export
if [ ! -x "$WORK/lean4export/.lake/build/bin/lean4export" ]; then
  log "Building lean4export $LEAN4EXPORT_REV with Lean v4.33.1"
  rm -rf "$WORK/lean4export"
  git clone -q https://github.com/leanprover/lean4export "$WORK/lean4export"
  (cd "$WORK/lean4export" && git checkout -q "$LEAN4EXPORT_REV" \
     && echo "leanprover/lean4:v4.33.1" > lean-toolchain && lake build lean4export)
fi
log "Exporting the challenge"
lake env "$WORK/lean4export/.lake/build/bin/lean4export" Challenge -- $THEOREMS > "$WORK/challenge.ndjson"
ls -la "$WORK/challenge.ndjson"
GOTC=$(sha256sum "$WORK/challenge.ndjson" | cut -d' ' -f1)
echo "  $GOTC"
if [ "$GOTC" != "$EXPECTED_CHALLENGE_SHA256" ]; then
  log "NOTE: challenge.ndjson differs from the published one ($EXPECTED_CHALLENGE_SHA256)."
  log "      That is not by itself a problem: the comparison below uses the file you just built."
fi

# 4. con-leche
if [ ! -x "$WORK/con-leche/.lake/build/bin/con-leche" ]; then
  log "Building con-leche $CONLECHE_REV"
  rm -rf "$WORK/con-leche"
  git clone -q https://github.com/leanprover/con-leche "$WORK/con-leche"
  (cd "$WORK/con-leche" && git checkout -q "$CONLECHE_REV" && lake build con-leche)
fi

# 5. The comparison
log "con-leche --compare (challenge = official Mathlib, solution = $SOLUTION)"
set +e
"$WORK/con-leche/.lake/build/bin/con-leche" --verified --jobs="$JOBS" \
  --compare -- "$WORK/challenge.ndjson" "$SOLUTION" | tee "$WORK/compare-out.txt"
RC=${PIPESTATUS[0]}
set -e
log "con-leche exited with code $RC"
if [ "$RC" -eq 0 ]; then
  log "ACCEPTED: the solution proves the challenge statements (official Mathlib)."
else
  log "NOT accepted (0 = accepted, 1 = rejected, 2 = unsupported, 3 = error)."
fi
exit "$RC"

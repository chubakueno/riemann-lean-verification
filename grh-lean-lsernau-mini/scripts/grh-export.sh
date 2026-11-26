#!/bin/bash
# Exporta desafío y prueba de grh-compact y los compara con con-leche.
export PATH="$HOME/.elan/bin:$PATH"
W=~/grh-verify; P=~/grh-lean/grh-compact
L4E=$W/lean4export/.lake/build/bin/lean4export
CL=~/rh-verify/con-leche/.lake/build/bin/con-leche
T="riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive"
log() { echo "[$(date '+%F %T')] $*"; }
sudo -n sysctl -w vm.max_map_count=4194304 >/dev/null 2>&1 || true
ulimit -c 0
cd $P
log "lake build Challenge"; lake build Challenge 2>&1 | tail -2
log "export desafio"; /usr/bin/time -v lake env $L4E Challenge -- $T > $W/challenge.ndjson 2> $W/export-challenge.err; echo "rc=$?"
log "export prueba (Main)"; /usr/bin/time -v lake env $L4E Main -- $T > $W/main.ndjson 2> $W/export-main.err; echo "rc=$?"
grep -E "Elapsed|Maximum resident" $W/export-*.err
ls -la $W/*.ndjson; sha256sum $W/challenge.ndjson $W/main.ndjson | tee $W/SHA256SUMS
head -c 300 $W/main.ndjson; echo
log "con-leche --verified --compare"
/usr/bin/time -v $CL --verified --jobs=$(nproc) --progress=20000 --compare -- $W/challenge.ndjson $W/main.ndjson > $W/compare-out.txt 2> $W/compare.time
echo "con-leche rc=$?" | tee -a $W/compare-out.txt
grep -E "Elapsed|Maximum resident" $W/compare.time
tail -15 $W/compare-out.txt
log FIN

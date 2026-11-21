#!/usr/bin/env bash
export PATH=$HOME/.elan/bin:$PATH
cd ~/lean-demo/src/lean
rm -f ~/nanoda/main.ndjson
/usr/bin/time -v lake env ~/tools/lean4export/.lake/build/bin/lean4export Main -- \
  riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re \
  LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive \
  > ~/nanoda/main.ndjson 2> ~/nanoda/export.err
echo "EXPORT_RC=$?" >> ~/nanoda/export.err

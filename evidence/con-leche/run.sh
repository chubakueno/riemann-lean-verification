#!/usr/bin/env bash
ulimit -c 0
cd ~/conleche
/usr/bin/time -v ~/tools/con-leche/.lake/build/bin/con-leche --verified --jobs=180 --progress -- ~/nanoda/main.ndjson \
  > out.txt 2> progress.err
echo "CONLECHE_RC=$?" >> progress.err

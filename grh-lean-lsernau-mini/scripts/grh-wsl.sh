#!/bin/bash
# Compila grh-compact en WSL: caché de Mathlib, lake build y axiomas.
source ~/.elan/env 2>/dev/null; export PATH=$HOME/.elan/bin:$PATH
cd ~ && [ -d grh-lean ] || mv grh-lean-2 grh-lean
cd ~/grh-lean && git checkout -q 72fead1 && git log --oneline -1 > ~/grh-lean/grh-compact/commit.txt
cd grh-compact
SECONDS=0
lake exe cache get > cache.log 2>&1; echo "cache_exit=$? t=${SECONDS}s" >> cache.log
/usr/bin/time -v lake build > build.log 2> build.time
echo "build_exit=$? t=${SECONDS}s" >> build.log
lake env lean scripts/PrintAxioms.lean > axioms.txt 2>&1
echo FIN >> build.log

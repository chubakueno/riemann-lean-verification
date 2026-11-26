# Independent check of grh-lean (compact edition)

This folder records an independent check of [lsernau/grh-lean](https://github.com/lsernau/grh-lean), a Lean 4
proof of the Riemann Hypothesis (Mathlib's `RiemannHypothesis`) and of the Generalized Riemann Hypothesis for
Dirichlet L-functions. According to its README, it is a shorter rewriting of Levent Alpöge's proof, the one
checked in the [rest of this repository](../README.md). Only the compact edition (`grh-compact/`, about 76,000
lines of code) was checked here. The readable edition `grh/` was not.

The kernel exports (517 MB and 38 MB compressed) are archived on Zenodo:
**[doi:10.5281/zenodo.24548259](https://doi.org/10.5281/zenodo.24548259)**.

**Summary.** At commit `72fead1`, `grh-compact` builds with the pinned Lean and Mathlib, with no errors. All five
theorems depend only on `propext`, `Classical.choice` and `Quot.sound`. Their kernel export passes
`con-leche --verified --compare` against `Challenge.lean`, the five statements with `sorry`, which imports only
`src/Statements.lean`, which in turn imports only Mathlib. The four `Prop` definitions in `Statements.lean` are
identical to the ones in this repository's [`challenge/Challenge.lean`](../challenge/Challenge.lean), so
this development proves the same five statements as the one checked there.

## 1. What is claimed

[`statements/Main.lean`](statements/Main.lean):

```lean
theorem riemannHypothesis : RiemannHypothesis := New.zeta_zeros_on_line New.grh
theorem riemannZeta_eq_zero_re : RiemannZetaZerosOnLine := riemannHypothesis
theorem LFunction_ne_zero_of_half_lt_re : DirichletLNonvanishingRightOfHalf := New.grh
theorem LFunction_eq_zero_re : DirichletLZerosOnLine := New.zeros_on_line New.grh
theorem LFunction_eq_zero_re_of_isPrimitive : PrimitiveDirichletLZerosOnLine :=
  fun N _ χ _ ↦ LFunction_eq_zero_re N χ
```

`RiemannHypothesis` is Mathlib's. The other four types are defined in
[`statements/Statements.lean`](statements/Statements.lean) (16 lines, `import Mathlib` only).

## 2. Results

| Check | Result |
|---|---|
| `lake exe cache get` + `lake build` | `Build completed successfully (9843 jobs)`, no errors, no `sorry` (only linter and deprecation warnings); 56 min 20 s |
| `lake env lean scripts/PrintAxioms.lean` | all five theorems: `[propext, Classical.choice, Quot.sound]` |
| Export (`lean4export Main -- <5 theorems>`) | `main.ndjson`, 5 173 283 067 bytes, sha256 `e4e38359…8297a`; 6 min 35 s, 13.7 GB peak RSS |
| Export of the challenge (`lean4export Challenge -- <5 theorems>`) | `challenge.ndjson`, 354 906 655 bytes, sha256 `36521fa0…ac6b4`; 25 s |
| `con-leche --verified --compare challenge.ndjson main.ndjson` | `accepted 52169 declarations, 5 axioms justified by the solution (204579 declarations accepted)`; exit code 0; 2 min 2 s, 4.9 GB peak RSS |

The con-leche output, verbatim ([`evidence/con-leche-compare/compare-out.txt`](evidence/con-leche-compare/compare-out.txt)):

```
con-leche: accepted 52169 declarations, 5 axioms justified by the solution /home/chubakueno/grh-verify/main.ndjson (204579 declarations accepted) (--verified)
con-leche: theorem riemannHypothesis justified by the solution
con-leche: theorem riemannZeta_eq_zero_re justified by the solution
con-leche: theorem LFunction_ne_zero_of_half_lt_re justified by the solution
con-leche: theorem LFunction_eq_zero_re justified by the solution
con-leche: theorem LFunction_eq_zero_re_of_isPrimitive justified by the solution
```

For comparison, Alpöge's development checked in the rest of this repository has 1 468 414 declarations by the
same count, and its export is 61.6 GB.

**What this does and does not show.** The challenge imports `src/Statements.lean` from the project itself.
Unlike the main check in this repository, the challenge was not built in a separate project with official
Mathlib only. Since `Statements.lean` imports only Mathlib and its four definitions are identical to the ones
checked before, this makes no difference to what is proved. To trust the result, read `Statements.lean` and the
five theorem types. The usual assumptions remain: Mathlib's definitions are the intended ones, the Lean
toolchain and con-leche are correct, and so is con-leche's set-theoretic model.

## 3. Exact versions

- grh-lean `72fead102f663d5c7a407964a13dc0cf9d977207`, folder `grh-compact/`
- Lean `v4.35.0` (commit `eb6cafb7290e8bd5f2937522d8d804f58f02bafc`)
- Mathlib `56a005855ea17e0b0958f73ec801ae140b0a1679` (official cache, `lake exe cache get`)
- lean4export `v4.35.0` = `5a9a355dc6c5fd82b69058d433e2ae2e8dfbf8fe`, built with Lean v4.35.0. Its export format
  (3.1.0) is the one used in the rest of this repository. The only change since v4.33.0 is that `partial`
  definitions are now skipped like `unsafe` ones.
- con-leche `11d8ff13c86675e6ba4b6ca6cd1e4986154516d9` (the same binary as in the rest of this repository)
- Theorems exported: `riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive`

Machine: Intel Core i7-13620H (16 threads), WSL2 Ubuntu on Windows 11 with 56 GB of memory, 2026-11-25.

## 4. Hashes

| File | sha256 |
|---|---|
| `main.ndjson` (decompressed) | `e4e38359ab72d85b9ac058c768ca98c20b0538c9c99e23998e8748fa64b8297a` |
| `challenge.ndjson` (decompressed) | `36521fa07ed71ed1464c27d5639ffe588f6744cf302f1a4c3a3456aab36ac6b4` |
| `main.ndjson.zst` (on Zenodo, zstd 1.5.7 `-19 --long=27`) | `040f2ceee71c844c8ed0f8f3b4b8f3422e068838533bc71c4de44242146f1134` |
| `challenge.ndjson.zst` (on Zenodo, zstd 1.5.7 `-19`) | `22afc08085024ae2a98790a6e9cb93dcbb1984205956ca89ce47ef3f820ebc51` |

The hashes to compare are those of the decompressed files. The `.zst` hashes depend on the zstd version. All
Zenodo files are listed in [`zenodo.SHA256SUMS`](zenodo.SHA256SUMS).

## 5. How to reproduce (Linux or WSL2)

### Hardware requirements

Measured on the run recorded here: 16 threads (i7-13620H), WSL2 Ubuntu with 56 GB of memory.

| Task | RAM | Free disk | Reference time |
|---|---|---|---|
| Build (`lake exe cache get` + `lake build`) | **24 GB recommended** (the upstream README's figure for 12 cores). The largest single `lean` process peaked at 9.7 GB RSS; a sample taken late in the build, with 16 `lean` processes running, showed 12 GB in use | about 18 GB: 7.3 GB for Mathlib and its dependencies (from the cache), 7.6 GB of build output, 3.0 GB for the Lean v4.35.0 toolchain | 1.5 min for the cache, 56 min for the build |
| Exports (`lean4export`) | **16 GB minimum, 24 GB recommended** (peak RSS 13.7 GB for `Main`, 6.9 GB for `Challenge`) | 5.5 GB for `main.ndjson` and `challenge.ndjson` | 6 min 35 s for `Main`, 25 s for `Challenge` |
| `con-leche --compare` | **8 GB minimum, 16 GB recommended** (peak RSS 4.9 GB) | the two `.ndjson` files (5.5 GB), plus about 1 GB for con-leche and a Lean v4.36.0 toolchain to build it | 2 min 2 s; building con-leche takes about 11 min |
| Checking from the Zenodo files only (download, `zstd -d`, `con-leche --compare`) | as for `con-leche --compare` | about 6.1 GB: 0.56 GB for the `.zst` files and 5.5 GB decompressed, plus con-leche | a few minutes plus the download |

In short, 32 GB of RAM and 40 GB of free disk are enough for every step, and the whole check takes about
1 h 10 min on 16 threads. That is much less than for the development in the rest of this repository: its export
is 61.6 GB and its `--compare` needs at least 48 GB of RAM. Times depend on the CPU, the power mode and the
disk.

The scripts that were run are in [`scripts/`](scripts/). In short:

```bash
git clone https://github.com/lsernau/grh-lean && cd grh-lean && git checkout 72fead1 && cd grh-compact
lake exe cache get && lake build                     # about 1 hour on 16 threads
lake env lean scripts/PrintAxioms.lean

git clone https://github.com/leanprover/lean4export ~/lean4export
(cd ~/lean4export && git checkout v4.35.0 && lake build lean4export)
T="riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive"
lake build Challenge
lake env ~/lean4export/.lake/build/bin/lean4export Challenge -- $T > challenge.ndjson
lake env ~/lean4export/.lake/build/bin/lean4export Main      -- $T > main.ndjson
sha256sum challenge.ndjson main.ndjson               # compare with section 4

git clone https://github.com/leanprover/con-leche ~/con-leche
(cd ~/con-leche && git checkout 11d8ff13c86675e6ba4b6ca6cd1e4986154516d9 && lake build con-leche)
~/con-leche/.lake/build/bin/con-leche --verified --jobs=$(nproc) --compare -- challenge.ndjson main.ndjson
echo $?                                              # 0 = accepted
```

Or download the exports from Zenodo, decompress them with `zstd -d`, check their sha256, and run only the last
step.

**On Windows (not WSL),** `lake build` fails with `failed to read file '…olean'` / `'…olean.private'`. Each
`lean` process commits about 7–8 GB of memory when it maps Mathlib, and with 16 in parallel the Windows commit
limit runs out. That error is about memory, not the proof. Setting `LEAN_NUM_THREADS=4` limits Lake to four
`lean` processes at a time and avoids it. The run recorded here used WSL2.

## 6. Contents

| Path | What |
|---|---|
| `statements/` | Copied unchanged from `grh-compact/` at `72fead1`: `Statements.lean`, `Main.lean`, `Challenge.lean`, `PrintAxioms.lean`, `comparator.json`, `lakefile.toml`, `lake-manifest.json`, `lean-toolchain`, `NOTICE` |
| `evidence/build/` | `build.log` (full `lake build` output), `build.time` (`/usr/bin/time -v`), `cache.log`, `commit.txt`, `axioms.txt` |
| `evidence/export/` | `run.log`, `export-*.err` (`/usr/bin/time -v` of each export), `ndjson.SHA256SUMS` |
| `evidence/con-leche-compare/` | `compare-out.txt`, `compare.time` |
| `scripts/` | `grh-wsl.sh` (clone, cache, build, axioms), `grh-export.sh` (challenge build, exports, con-leche) |
| `zenodo.SHA256SUMS` | sha256 of the files on Zenodo |

The files in `statements/` belong to grh-lean: Apache License 2.0, Copyright 2026 Anthropic, PBC (see
`statements/NOTICE` and the [grh-lean repository](https://github.com/lsernau/grh-lean)). The logs, the scripts
and this README are under the same license as the rest of this repository.

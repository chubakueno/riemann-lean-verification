# Independent verification of a Lean 4 proof of the Riemann Hypothesis

This repository records an independent check of a Lean 4 development, published by Levent Alpoge at
`https://alpo.ge/lean.tar.gz.part01` … `part14`, which claims to prove the Riemann Hypothesis
as stated in Mathlib (`RiemannHypothesis`), together with related statements about Dirichlet L-functions.

It contains the statements, the scripts, the logs and the hashes needed to check the result again.
The large artifacts (the kernel export, about 7.6 GB compressed, and the original source) are archived on
Zenodo, [doi:10.5281/zenodo.24414400](https://doi.org/10.5281/zenodo.24414400); see
[Large artifacts](#large-artifacts).

| Archived on Zenodo | DOI |
|---|---|
| Data: kernel export and original source | [10.5281/zenodo.24414400](https://doi.org/10.5281/zenodo.24414400) |
| Data: grh-lean (compact edition) kernel export | [10.5281/zenodo.24548259](https://doi.org/10.5281/zenodo.24548259) |
| This repository, all versions (cite this one) | [10.5281/zenodo.24415504](https://doi.org/10.5281/zenodo.24415504) |
| This repository, release v1.0 | [10.5281/zenodo.24415505](https://doi.org/10.5281/zenodo.24415505) |

**Summary.** The full project (175 187 modules on top of Mathlib) builds with the official Lean
toolchain. Its kernel export passes three checks: nanoda, an independent kernel written in Rust; con-leche
in `--verified` mode; and `con-leche --compare` against a challenge file that imports only official Mathlib.
The comparison shows that the export proves exactly the five statements below, where `RiemannHypothesis`,
`riemannZeta`, `DirichletCharacter.LFunction` and everything else in the statements are the unmodified Mathlib
definitions. The only axioms used are `propext`, `Classical.choice` and `Quot.sound`.

**Also checked: grh-lean.** [`grh-lean-lsernau-mini/`](grh-lean-lsernau-mini/) records the same kind of
check for [lsernau/grh-lean](https://github.com/lsernau/grh-lean). It is a shorter rewriting of this proof
(compact edition, about 76,000 lines, Lean v4.35.0), and it proves the same five statements. Its kernel export
passes `con-leche --verified --compare` and is archived on Zenodo,
[doi:10.5281/zenodo.24548259](https://doi.org/10.5281/zenodo.24548259).

## 1. What is claimed

The project's `Main.lean`:

```lean
theorem riemannHypothesis : RiemannHypothesis := rhOfAll            -- RiemannHypothesis is Mathlib's
theorem riemannZeta_eq_zero_re : RiemannZetaZerosOnLine := rhOfAll
theorem LFunction_ne_zero_of_half_lt_re : DirichletLNonvanishingRightOfHalf := allChi
theorem LFunction_eq_zero_re : DirichletLZerosOnLine := claimAll.2.1
theorem LFunction_eq_zero_re_of_isPrimitive : PrimitiveDirichletLZerosOnLine := critAll
```

The four auxiliary `Prop` definitions come from the project's `src/Statements.lean`, which imports only
Mathlib. They are copied verbatim into [`challenge/Challenge.lean`](challenge/Challenge.lean):

```lean
def RiemannZetaZerosOnLine : Prop :=
  ∀ s : ℂ, riemannZeta s = 0 → (¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2

def DirichletLNonvanishingRightOfHalf : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    1 / 2 < s.re → (χ ≠ 1 ∨ s ≠ 1) → DirichletCharacter.LFunction χ s ≠ 0

def DirichletLZerosOnLine : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    0 < s.re → s.re < 1 → DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2

def PrimitiveDirichletLZerosOnLine : Prop :=
  ∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N), χ.IsPrimitive →
    ∀ s : ℂ, 0 < s.re → s.re < 1 → DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2
```

Mathlib's definition, as printed by Lean ([`evidence/statement-check/check-output.txt`](evidence/statement-check/check-output.txt)):

```lean
def RiemannHypothesis : Prop :=
∀ (s : ℂ), riemannZeta s = 0 → (¬∃ n, s = -2 * (↑n + 1)) → s ≠ 1 → s.re = 1 / 2
```

## 2. Results

| Check | Where | Result | Evidence |
|---|---|---|---|
| Full build with the official Lean kernel (C++) | AWS c7a.48xlarge (192 vCPU) | 175 187 modules, 0 failures | [`evidence/build/`](evidence/build/) |
| `check.lean`: statement and axioms | AWS | `RiemannHypothesis`, `riemannZeta` and `DirichletCharacter.LFunction` are defined in `Mathlib.*` modules. `Iff.rfl` against a hand-written classical statement compiles. The theorems depend only on `[propext, Classical.choice, Quot.sound]` | [`evidence/statement-check/`](evidence/statement-check/) |
| Export with `lean4export` | AWS | `main.ndjson`, 61 571 290 481 bytes, 2 h 16 min, 165 GB RAM | [`evidence/export/`](evidence/export/) |
| [nanoda](https://github.com/ammkrn/nanoda_lib) (independent kernel, Rust) | AWS | `Checked 1484729 declarations with no errors` (39 min 40 s) | [`evidence/nanoda/`](evidence/nanoda/) |
| [con-leche](https://github.com/leanprover/con-leche) `--verified` | AWS | `accepted 1468414 declarations (--verified)` (about 3 min) | [`evidence/con-leche/`](evidence/con-leche/) |
| **con-leche `--verified --compare`**: challenge (official Mathlib only) vs. solution (`main.ndjson`) | Windows 11 laptop (i7-13620H, 16 threads, 64 GB) | `accepted 51688 declarations, 5 axioms justified by the solution (1468414 declarations accepted)`. All five theorems: `justified by the solution` (22 min) | [`evidence/con-leche-compare/`](evidence/con-leche-compare/) |

### Why `--compare` matters

A kernel check alone shows that the export is internally consistent. It does not show that `riemannZeta`
in the export is Mathlib's `riemannZeta`: a modified definition with the same name would also pass.

`con-leche --compare` closes that gap. The *challenge* ([`challenge/Challenge.lean`](challenge/Challenge.lean))
imports only Mathlib at the pinned commit and states the five theorems with `sorry`. The theorems therefore
appear as axioms in `challenge.ndjson`. con-leche accepts only if the *solution* provides each of them under
the same name with the same type, and only if every constant those types mention (transitively) has the same
value in both files. The definitions in the statement therefore cannot have been altered.

Before it was used here, the Windows build of con-leche was run on its own `cmp_hole`, `cmp_def`, `cmp_stmt`,
`cmp_missing` and `cmp_attack` test fixtures. Each one gave the expected exit code, including the rejection of
`attack`.

### On the declaration counts

nanoda reports 1 484 729 declarations and con-leche 1 468 414 for the same export. The difference is a
counting convention: con-leche counts each mutual inductive block as one declaration.

### Remaining trust assumptions

- That Mathlib's definitions (`riemannZeta`, `DirichletCharacter.LFunction`, `Complex`, …) are the
  mathematically intended ones.
- Correctness of the Lean and Rust compilers and runtimes used to build the checkers.
- For con-leche `--verified`: its soundness proof assumes ZF plus an ω-chain of Grothendieck universes.

## 3. Exact versions

| Component | Version |
|---|---|
| Lean | `v4.33.1` (githash `819816b2e0a3bf405af45ae5c7af2491d8f5bee6`) |
| Mathlib | `0df444a360eaa60ab8c11dca51a86af692955474` (no local changes; `.olean` files from the official cache) |
| lean4export | `v4.33.0` = `15f6055e299ad5b89345e533cc2192f4cc00f659`, **built with Lean v4.33.1**. Its `lean-toolchain` must be changed to match the `.olean` files |
| nanoda_lib | `0da9f98feadd3a0a2ef4b3dbcf52a298a6fef929` (rustc 1.100.0) |
| con-leche | `11d8ff13c86675e6ba4b6ca6cd1e4986154516d9` (toolchain Lean v4.36.0) |
| Exported theorems | `riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive` |

## 4. Hashes (sha256)

| File | Size (bytes) | sha256 |
|---|---|---|
| `lean.tar.gz` (original source, the 14 parts joined) | 239 275 554 | `9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc` |
| **`main.ndjson`** (verified export, decompressed) | 61 571 290 481 | **`4301ce4828d397c728e87f3e6a1251aa42abe5e12809bb9e0b73cc3d33072e7e`** |
| `main.ndjson.zst` (zstd -12) | 7 588 466 081 | `048ac2be5f89c05ac1917f6785a471c56f2663491459e880cdafcfa259e928c2` |
| `challenge.ndjson` (challenge export, decompressed) | 350 794 407 | `38ae485659b1b1019061746ece9d2cf404765a1cca47eba618798970edaf2f2a` |
| `lib.tar.zst` (all 175 187 `.olean` files) | 29 087 484 825 | `0e933056e371dbfdd264dcf4e54cb8670e04f5fbbaea67f16156c01df2d29f31` |

Compare against the hash of the **decompressed** `main.ndjson`. Hashes of `.tar` and `.zst` files depend on
timestamps and on the zstd version. The export contains no file paths and is deterministic: re-exporting Mathlib
gave the same sha256. The `.olean` files are not comparable across machines, because about a third of them
embed the absolute path of their source file.

[`SHA256SUMS`](SHA256SUMS) covers every file in this repository.

## 5. Reproducing the comparison

You need the solution file `main.ndjson` (or `main.ndjson.zst`) from the [large artifacts](#large-artifacts).

### Hardware requirements

| Task | RAM | Free disk | Reference time |
|---|---|---|---|
| `verify.sh` / `con-leche --compare` | **48 GB minimum, 64 GB recommended** (con-leche reported a peak RSS of 43.65 GiB, reached while parsing `main.ndjson`) | about 80 GB: 61 GB for `main.ndjson` (plus 7.6 GB if starting from the `.zst`), about 9 GB for Mathlib, lean4export and con-leche, about 6 GB for the Lean toolchains | `--compare`: 22 min on a 16-thread laptop (i7-13620H) in performance mode; building con-leche takes about 11 min |
| nanoda | about 80 GB (maximum RSS on the AWS run) | 61 GB | 40 min on 192 vCPU |
| Rebuilding the project and the export from source | 165 GB or more (the export alone) | well over 1 TB of scratch space with Lake | hours on 192 vCPU |

For the separate check of **grh-lean** ([`grh-lean-lsernau-mini/`](grh-lean-lsernau-mini/#hardware-requirements)),
the requirements are much smaller. They were measured on the same 16-thread laptop, in WSL2 with 56 GB:

| grh-lean task | RAM | Free disk | Reference time |
|---|---|---|---|
| `con-leche --compare` (from the Zenodo files) | 8 GB minimum, 16 GB recommended (peak RSS 4.9 GB) | about 6.5 GB: 5.5 GB for the decompressed `.ndjson` files, plus con-leche | 2 min; building con-leche takes about 11 min |
| Exports (`lean4export`) | 16 GB minimum, 24 GB recommended (peak RSS 13.7 GB) | 5.5 GB | about 7 min |
| Rebuilding the project from source (`lake exe cache get` + `lake build`) | 24 GB recommended | about 18 GB | 56 min |

Times depend heavily on the CPU, the power mode and the disk. `main.ndjson` should be on a fast local disk:
reading it from a slow or network disk (for example a Windows drive seen from WSL) multiplies the time of the
sha256 step and of con-leche's parsing phase.

### Linux (x86_64)

```bash
bash challenge/verify.sh /path/to/main.ndjson.zst
```

The script installs elan if needed. It builds `Challenge.lean` against official Mathlib (from the Mathlib
cache), builds lean4export and con-leche at the pinned commits, exports the challenge and runs
`con-leche --verified --compare`. Exit code `0` means accepted; `1` rejected, `2` unsupported, `3` error.

The script was tested end to end on WSL Ubuntu (16 threads, starting with no Lean toolchain installed). The
challenge it rebuilt from official Mathlib had exactly the published hash `38ae4856…`, and con-leche accepted
the solution. The full log is in [`evidence/verify-sh-wsl/`](evidence/verify-sh-wsl/).

### Windows

This is how the comparison in [`evidence/con-leche-compare/`](evidence/con-leche-compare/) was run.

1. Install [elan](https://github.com/leanprover/elan). Clone con-leche, check out
   `11d8ff13c86675e6ba4b6ca6cd1e4986154516d9`, and run `lake build con-leche` (about 11 min; builds
   `.lake\build\bin\con-leche.exe`).
2. Use the published `challenge.ndjson.zst` (decompress with `zstd -d`), or regenerate it. To regenerate it,
   build `challenge/` with `lake exe cache get && lake build Challenge`, then build lean4export at
   `15f6055e…` with its `lean-toolchain` set to `leanprover/lean4:v4.33.1`. Run it as in
   [`challenge/export-windows.cmd`](challenge/export-windows.cmd) (adjust the paths). Two Windows notes:
   - `lean4export.exe` needs the toolchain's `bin` folder on `PATH`. Otherwise it fails with exit code
     `0xC0000135` (DLL not found).
   - Redirect its output with `cmd.exe` `>`, not a PowerShell pipeline, which can re-encode Unicode and
     change line endings.
3. Decompress `main.ndjson.zst` and check its sha256. Then run, in `cmd.exe`:
   ```
   con-leche.exe --verified --jobs=16 --progress=20000 --compare -- challenge.ndjson main.ndjson
   ```

### Re-running nanoda

Build nanoda_lib at `0da9f98f…` (`cargo build --release`). Set `export_file_path` in
[`evidence/nanoda/config.json`](evidence/nanoda/config.json) to your decompressed `main.ndjson`, and set
`num_threads` to suit your machine. Then run `nanoda_bin config.json`. It needs about 80 GB of RAM
(maximum RSS on the AWS run).

### Rebuilding from source

Rebuilding the project and the export from `lean.tar.gz` needs a large machine. The export alone used 165 GB
of RAM. Lake does not scale to 175 187 modules: it walks the transitive import tree for each module and writes
a 6–11 MB `setup.json` for each one. The build therefore used [`evidence/build/sched.py`](evidence/build/sched.py),
a small scheduler that runs `lean` directly with `LEAN_PATH` and a minimal `--setup`. On a 60-module sample
it produced `.olean` files byte-identical to Lake's. [`evidence/build/build-remote.sh`](evidence/build/build-remote.sh)
is the driver script that was used.

## 6. Repository layout

```
README.md
SHA256SUMS                       hashes of every file below
challenge.ndjson.zst             challenge export (zstd -19); decompressed sha256 38ae4856…
challenge/
  Challenge.lean                 the five statements with `sorry`, importing only Mathlib
  lakefile.toml, lean-toolchain  Mathlib 0df444a3, Lean v4.33.1
  verify.sh                      Linux end-to-end check (see §5)
  export-windows.cmd             how challenge.ndjson was exported on Windows
evidence/
  build/                         sched.py, build-remote.sh, build.log, progress.log, VERSIONES.txt
  statement-check/               check.lean and its output
  export/                        lean4export command, timing, main.ndjson.sha256
  nanoda/                        config, run script, output, timing
  con-leche/                     --verified run on AWS: command, output, version, progress summary
  con-leche-compare/             --verified --compare run on Windows: full output
  verify-sh-wsl/                 end-to-end run of challenge/verify.sh on WSL Ubuntu: full log
  status-page/                   frozen copy of the live build status page (open pagina.html with
                                 status.json next to it) and the progress CSVs
  original-bundle-checksums/     SHA256SUMS of the bundles as produced on AWS
grh-lean-lsernau-mini/           separate check of lsernau/grh-lean (compact edition); see its README
```

Some files (comments in `Challenge.lean`, `check.lean`, `VERSIONES.txt`, the status page and some scripts)
are in Spanish, the working language of this verification. `Challenge.lean` is kept byte-for-byte as it was
when `challenge.ndjson` was exported.

## Large artifacts

Archived on Zenodo: **[doi:10.5281/zenodo.24414400](https://doi.org/10.5281/zenodo.24414400)**

| File | Size | sha256 |
|---|---|---|
| `main.ndjson.zst` | 7 588 466 081 bytes | `048ac2be5f89c05ac1917f6785a471c56f2663491459e880cdafcfa259e928c2` (decompressed: `4301ce48…`) |
| `lean.tar.gz` (original source; first published at `https://alpo.ge/lean.tar.gz.part01` … `part14`) | 239 275 554 bytes | `9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc` |
| `SHA256SUMS` | 238 bytes | `0bf3189364c5f3762dd42d7a13836b63cda1ba9ef6de6789bc28a299e30214e8` |
| `README.txt` | 867 bytes | `e850c69b3a627a9e08dd04af45da15be8399a3003c2f0b842a3da30fa160b521` |

`lib.tar.zst` (all 175 187 `.olean` files, 29.1 GB) is not archived. It is not needed for any of the checks,
and its contents depend on the build machine (see §4).

## License and authorship

The proof is the work of Levent Alpoge, published at `https://alpo.ge`, and must be credited to him. The
author of this repository did not write the proof and is not affiliated with its author.

This repository contains verification material only: statements, scripts, logs and hashes. That material is
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), the same license as the Zenodo
record. The license does not extend to the proof itself.

The files in `grh-lean-lsernau-mini/statements/` are copied from
[lsernau/grh-lean](https://github.com/lsernau/grh-lean) and remain under that project's license (Apache
License 2.0, Copyright 2026 Anthropic, PBC; see the `NOTICE` there).

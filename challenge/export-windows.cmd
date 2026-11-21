@echo off
set ELAN_HOME=D:\lean-demo\elan
set PATH=D:\lean-demo\elan\toolchains\leanprover--lean4---v4.33.1\bin;%PATH%
set LEAN_PATH=D:\lean-demo\challenge\build;D:\lean-demo\src\lean\.lake\packages\aesop\.lake\build\lib\lean;D:\lean-demo\src\lean\.lake\packages\batteries\.lake\build\lib\lean;D:\lean-demo\src\lean\.lake\packages\importGraph\.lake\build\lib\lean;D:\lean-demo\src\lean\.lake\packages\LeanSearchClient\.lake\build\lib\lean;D:\lean-demo\src\lean\.lake\packages\mathlib\.lake\build\lib\lean;D:\lean-demo\src\lean\.lake\packages\plausible\.lake\build\lib\lean;D:\lean-demo\src\lean\.lake\packages\proofwidgets\.lake\build\lib\lean;D:\lean-demo\src\lean\.lake\packages\Qq\.lake\build\lib\lean;D:\lean-demo\elan\toolchains\leanprover--lean4---v4.33.1\lib\lean
cd /d D:\lean-demo\challenge
D:\lean-demo\tools\lean4export\.lake\build\bin\lean4export.exe Challenge -- riemannHypothesis riemannZeta_eq_zero_re LFunction_ne_zero_of_half_lt_re LFunction_eq_zero_re LFunction_eq_zero_re_of_isPrimitive > challenge.ndjson 2> export.err
echo EXPORT_RC=%ERRORLEVEL%>> export.err

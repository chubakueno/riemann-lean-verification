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

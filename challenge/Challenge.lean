/-
Desafío para `con-leche --compare`: los enunciados, sin demostración.

Este archivo solo importa Mathlib (commit 0df444a360eaa60ab8c11dca51a86af692955474).
Cada `sorry` es un hueco que la "solución" (la exportación del proyecto) tiene que llenar con
una constante del mismo nombre y el mismo enunciado, donde todo lo que el enunciado menciona
(RiemannHypothesis, riemannZeta, Complex, DirichletCharacter.LFunction, ...) es la misma
constante, con el mismo valor, que en Mathlib.

Las cuatro definiciones auxiliares son copia literal de `Statements.lean` del proyecto;
con-leche comprueba que la solución usa exactamente estas.
-/
import Mathlib

/-- La Hipótesis de Riemann, tal como la define Mathlib (`Mathlib.NumberTheory.LSeries.RiemannZeta`). -/
theorem riemannHypothesis : RiemannHypothesis := sorry

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

theorem riemannZeta_eq_zero_re : RiemannZetaZerosOnLine := sorry

theorem LFunction_ne_zero_of_half_lt_re : DirichletLNonvanishingRightOfHalf := sorry

theorem LFunction_eq_zero_re : DirichletLZerosOnLine := sorry

theorem LFunction_eq_zero_re_of_isPrimitive : PrimitiveDirichletLZerosOnLine := sorry

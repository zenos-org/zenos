/-!
# Where classified information may go

Every place a copy of a file's content can reach, and one decision for all of them: the level folders and level
windows (Save As, paste into a sealed window), and the places outside the levels (the system clipboard, the
printer, the three kinds of AI). The apps and keyd ask this one decision instead of keeping their own rules.

Principle: content of a level never goes to a place of a lower level ("no write down"). Public content (L1) may go
anywhere. A place outside the levels holds at most its ceiling; the printer's ceiling is configurable
(`/etc/zenos/policy.conf`, `print_max_level`) but never above L4: Specially Designated Secrets are never printed.
-/

namespace Zenos

inductive Sink where
  /-- a level folder on the desktop (L1-L5); other folders count as level 0 -/
  | folder (level : Nat)
  /-- a window showing a sealed file of this level (paste) -/
  | window (level : Nat)
  /-- the desktop's clipboard, readable by every program -/
  | systemClipboard
  | printer
  /-- AI services outside the government -/
  | externalAI
  /-- the government's shared AI -/
  | govAI
  /-- AI isolated inside the ministry -/
  | ministryAI
  deriving Repr, Inhabited, DecidableEq

/-- The highest level a place may ever hold, whatever the configuration says. -/
def hardCap : Sink → Nat
  | .folder l => l
  | .window l => l
  | .systemClipboard => 2
  | .printer => 4
  | .externalAI => 2
  | .govAI => 3
  | .ministryAI => 5

/-- The level a place holds under this configuration. -/
def sinkLevel (printMax : Nat) : Sink → Nat
  | .folder l => l
  | .window l => l
  | .systemClipboard => 2
  | .printer => min printMax 4
  | .externalAI => 2
  | .govAI => 3
  | .ministryAI => 5

def mayFlow (printMax src : Nat) (s : Sink) : Bool :=
  src ≤ 1 || src ≤ sinkLevel printMax s

/-- A copy moved hop by hop through folders and windows: each hop must be allowed from the level the copy has; it
    then has the higher of its level and the place's. `none` when a hop is refused. -/
def carry (printMax : Nat) : Nat → List Sink → Option Nat
  | lvl, [] => some lvl
  | lvl, s :: rest => if mayFlow printMax lvl s then carry printMax (max lvl (hardCap s)) rest else none

theorem mayFlow_iff {pm src : Nat} {s : Sink} : mayFlow pm src s = true ↔ src ≤ 1 ∨ src ≤ sinkLevel pm s := by
  simp [mayFlow]

theorem sinkLevel_le_cap (pm : Nat) (s : Sink) : sinkLevel pm s ≤ hardCap s := by
  cases s <;> simp [sinkLevel, hardCap] <;> omega

/-- Content never goes above a place's ceiling (except public content). -/
theorem flow_within_cap {pm src : Nat} {s : Sink} (h : mayFlow pm src s = true) : src ≤ 1 ∨ src ≤ hardCap s := by
  simp only [mayFlow, Bool.or_eq_true, decide_eq_true_eq] at h
  rcases h with h | h
  · exact Or.inl h
  · exact Or.inr (Nat.le_trans h (sinkLevel_le_cap pm s))

/-- No write down: content of a level reaches only folders and windows of that level or higher. -/
theorem no_write_down {pm src l : Nat} (h : mayFlow pm src (.folder l) = true ∨ mayFlow pm src (.window l) = true) :
    src ≤ 1 ∨ src ≤ l := by
  rcases h with h | h <;> exact flow_within_cap h

/-- L3 and above never reach the system clipboard or an AI outside the government. -/
theorem l3_stays_inside {pm src : Nat} (h3 : 3 ≤ src) :
    mayFlow pm src .systemClipboard = false ∧ mayFlow pm src .externalAI = false := by
  refine ⟨?_, ?_⟩ <;> exact Bool.eq_false_iff.mpr fun h => by rw [mayFlow_iff] at h; simp only [sinkLevel] at h; omega

/-- L4 and above reach no AI but the ministry's own. -/
theorem l4_ministry_ai_only {pm src : Nat} (h4 : 4 ≤ src) :
    mayFlow pm src .govAI = false ∧ mayFlow pm src .externalAI = false := by
  refine ⟨?_, ?_⟩ <;> exact Bool.eq_false_iff.mpr fun h => by rw [mayFlow_iff] at h; simp only [sinkLevel] at h; omega

/-- Specially Designated Secrets (L5) are never printed, whatever the configuration says, and leave the L5 places
    only for the ministry's own AI. -/
theorem l5_stays {pm : Nat} {s : Sink} (h : mayFlow pm 5 s = true) :
    s = .ministryAI ∨ (∃ l, (s = .folder l ∨ s = .window l) ∧ 5 ≤ l) := by
  have := flow_within_cap h
  cases s with
  | folder l => exact Or.inr ⟨l, Or.inl rfl, by simp [hardCap] at this; omega⟩
  | window l => exact Or.inr ⟨l, Or.inr rfl, by simp [hardCap] at this; omega⟩
  | ministryAI => exact Or.inl rfl
  | systemClipboard | printer | externalAI | govAI => simp [hardCap] at this

/-- Moving a copy around never lowers its level: wherever it ends up is at least the level it started with. -/
theorem carry_monotone {pm : Nat} : ∀ {src : Nat} {path : List Sink} {l : Nat},
    carry pm src path = some l → src ≤ l
  | src, [], l, h => by simp [carry] at h; omega
  | src, s :: rest, l, h => by
    simp only [carry] at h
    split at h
    · exact Nat.le_trans (Nat.le_max_left _ _) (carry_monotone h)
    · cases h

end Zenos

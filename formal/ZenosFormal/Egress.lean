/-!
# What leaves the PC

Two decisions. The pre-send check (`decideSend`): a file goes out through the sanctioned path only sealed, with a
signature that verifies, and, above the size line, with an approved transfer. The network sentinel (`egressStep`):
it counts the bytes each program sends to each destination that is not approved, over a sliding window, and cuts the
destination when the count reaches the threshold.

Proved: nothing unsealed passes the pre-send check (`send_sound`); a cut happens exactly when an unapproved,
not yet cut destination reaches the threshold within the window (`egress_cut_iff`); and keeping only the recent part
of the window loses nothing, as long as the sentinel's clock does not go backwards (`prune_prune`).
-/

namespace Zenos

/-! ## Pre-send check -/

structure SendReq where
  /-- the content starts with the ZENOS sealed-file header -/
  sealed : Bool
  /-- the device signature over header and ciphertext verifies (checked by the service) -/
  sigOk : Bool
  size : Nat
  hugeMax : Nat
  /-- an approved transfer plan covers this file -/
  planOk : Bool
  deriving Repr, Inhabited

inductive SendResult where
  | allow
  | deny (reason : String)
  deriving Repr, Inhabited, DecidableEq

def decideSend (r : SendReq) : SendResult :=
  if !r.sealed then .deny "plaintext-or-unsealed"
  else if !r.sigOk then .deny "invalid-or-tampered"
  else if r.hugeMax < r.size && !r.planOk then .deny "too-large-needs-approval"
  else .allow

/-- Nothing unsealed or tampered goes out, and nothing over the size line without an approved transfer. -/
theorem send_sound {r : SendReq} (h : decideSend r = .allow) :
    r.sealed = true ∧ r.sigOk = true ∧ (r.size ≤ r.hugeMax ∨ r.planOk = true) := by
  unfold decideSend at h
  cases hs : r.sealed <;> simp [hs] at h
  cases hg : r.sigOk <;> simp [hg] at h
  refine ⟨rfl, rfl, ?_⟩
  by_cases hl : r.hugeMax < r.size
  · cases hp : r.planOk <;> simp_all
  · exact Or.inl (Nat.le_of_not_lt hl)

/-! ## Network sentinel -/

/-- One outbound send seen by the kernel sensor. `key` names the program and the destination; `allowed`: the
    destination is in an approved network (checked by the service). Times in milliseconds. -/
structure Ev where
  key : String
  dst : String
  allowed : Bool
  t : Nat
  size : Nat
  deriving Repr, Inhabited

structure EState where
  /-- for each program and destination, the recent sends: (time, bytes) -/
  win : List (String × List (Nat × Nat))
  /-- destinations already cut -/
  cut : List String
  deriving Repr, Inhabited

def prune (w t : Nat) (l : List (Nat × Nat)) : List (Nat × Nat) := l.filter (fun e => t - e.1 ≤ w)

def total (l : List (Nat × Nat)) : Nat := l.foldr (fun e acc => e.2 + acc) 0

def recent (st : EState) (key : String) : List (Nat × Nat) := (st.win.lookup key).getD []

/-- The window this send makes for its program and destination. -/
def windowAt (w : Nat) (st : EState) (e : Ev) : List (Nat × Nat) := prune w e.t (recent st e.key ++ [(e.t, e.size)])

/-- One send: the new state, and whether the destination is cut now. -/
def egressStep (w thr : Nat) (st : EState) (e : Ev) : EState × Bool :=
  if e.allowed || st.cut.contains e.dst then (st, false)
  else if thr ≤ total (windowAt w st e) then ({ win := st.win.filter (·.1 != e.key), cut := e.dst :: st.cut }, true)
  else ({ win := (e.key, windowAt w st e) :: st.win.filter (·.1 != e.key), cut := st.cut }, false)

/-- The destination is cut exactly when it is not approved, not already cut, and the bytes sent to it by this program
    within the window reach the threshold. -/
theorem egress_cut_iff (w thr : Nat) (st : EState) (e : Ev) :
    (egressStep w thr st e).2 = true ↔
      ((e.allowed || st.cut.contains e.dst) = false ∧ thr ≤ total (windowAt w st e)) := by
  unfold egressStep
  split
  · rename_i h1
    exact ⟨fun h => by simp at h, fun ⟨hf, _⟩ => absurd (h1.symm.trans hf) (by decide)⟩
  · rename_i h1
    have h1' : (e.allowed || st.cut.contains e.dst) = false := by simpa using h1
    split
    · rename_i ht; exact ⟨fun _ => ⟨h1', ht⟩, fun _ => rfl⟩
    · rename_i ht; exact ⟨fun h => by simp at h, fun ⟨_, h⟩ => absurd h ht⟩

/-- Once a destination is cut it stays cut. -/
theorem egress_cut_stays (w thr : Nat) (st : EState) (e : Ev) (d : String) (h : st.cut.contains d = true) :
    (egressStep w thr st e).1.cut.contains d = true := by
  unfold egressStep
  split
  · exact h
  · split
    · simp only [List.contains_cons, Bool.or_eq_true]
      exact Or.inr h
    · exact h

/-- Dropping the sends that are already older than the window loses nothing later: with a clock that does not go
    backwards, pruning now and again later is the same as pruning once later. -/
theorem prune_prune (w t t' : Nat) (htt : t ≤ t') (l : List (Nat × Nat)) :
    prune w t' (prune w t l) = prune w t' l := by
  unfold prune
  rw [List.filter_filter]
  congr 1
  funext e
  by_cases h : t' - e.1 ≤ w
  · have : t - e.1 ≤ w := by omega
    simp [h, this]
  · simp [h]

end Zenos

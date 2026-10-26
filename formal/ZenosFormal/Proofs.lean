import ZenosFormal.Decide

/-!
# What the ZENOS decisions guarantee

Checked by Lean's kernel on every build. The axioms used are only Lean's standard ones (`propext`,
`Classical.choice`, `Quot.sound`); `Main.lean` prints them for the main theorems with `#print axioms`.

1. `open_sound`: keyd hands out a file's plaintext only when the PC is not stopped, the level is a real level, and
   either the user's clearance covers it or a grant does: for this user, this exact file, a level at least the
   file's, not expired, an access grant, with signed contents, from enough distinct enrolled officers.
2. `grant_needs_officer`: opening above one's clearance needs at least one enrolled officer other than the user;
   the user's own approval never counts (`approvers_not_requester`), nor an officer twice (`approvers_nodup`).
3. `release_sound`: a stop is released only for a pending request signed by at least `required` (and at least one)
   distinct enrolled officers other than the stopped user.
4. `run_open_not_halted`: over any sequence of anomalies, officers' answers, checks and open requests, every file
   keyd opened was opened while the PC was not stopped.
5. `run_release`: over any such sequence, the PC goes from stopped to running only through a release check that
   held (3).
-/

namespace Zenos

/-! ## dedup -/

theorem mem_dedup {x : String} : ∀ {l : List String}, x ∈ dedup l ↔ x ∈ l
  | [] => by simp [dedup]
  | y :: ys => by
    unfold dedup
    split
    · rename_i h
      rw [mem_dedup]
      constructor
      · intro hx; exact List.mem_cons_of_mem _ hx
      · intro hx
        rcases List.mem_cons.mp hx with rfl | hx
        · exact mem_dedup.mp h
        · exact hx
    · rw [List.mem_cons, List.mem_cons, mem_dedup]

theorem dedup_nodup : ∀ (l : List String), (dedup l).Nodup
  | [] => by simp [dedup]
  | y :: ys => by
    unfold dedup
    split
    · exact dedup_nodup ys
    · rename_i h
      exact List.nodup_cons.mpr ⟨h, dedup_nodup ys⟩

/-! ## who counts as an approver -/

theorem mem_approvers {roster : List String} {q n : String} {as : List Approval}
    (h : n ∈ approvers roster q as) :
    n ∈ roster ∧ n ≠ q ∧ ∃ a ∈ as, a.approver = n ∧ a.sigOk = true := by
  unfold approvers at h
  rw [mem_dedup] at h
  obtain ⟨a, ha, rfl⟩ := List.mem_map.mp h
  obtain ⟨ha, he⟩ := List.mem_filter.mp ha
  simp only [eligible, Bool.and_eq_true, List.contains_iff_mem, bne_iff_ne, ne_eq] at he
  exact ⟨he.1.2, he.2, a, ha, rfl, he.1.1⟩

/-- The requester's own approval never counts. -/
theorem approvers_not_requester {roster : List String} {q : String} {as : List Approval} :
    q ∉ approvers roster q as := fun h => (mem_approvers h).2.1 rfl

/-- No officer counts twice. -/
theorem approvers_nodup (roster : List String) (q : String) (as : List Approval) :
    (approvers roster q as).Nodup := dedup_nodup _

/-! ## opening a file -/

theorem grantOk_spec {o : OpenReq} {g : Grant} (h : grantOk o g = true) :
    g.digestOk = true ∧ g.requester = o.user ∧ g.holder = o.user ∧ g.fileHash = o.fileHash ∧ g.kind = none
      ∧ o.level ≤ g.level ∧ o.now ≤ g.expires ∧ required o.level ≤ (approvers o.roster o.user g.approvals).length := by
  simp only [grantOk, Bool.and_eq_true, beq_iff_eq, decide_eq_true_eq, Option.isNone_iff_eq_none] at h
  obtain ⟨⟨⟨⟨⟨⟨⟨h1, h2⟩, h3⟩, h4⟩, h5⟩, h6⟩, h7⟩, h8⟩ := h
  exact ⟨h1, h2, h3, h4, h5, h6, h7, h8⟩

theorem open_sound {o : OpenReq} (h : (decideOpen o).allowed = true) :
    o.halted = false ∧ validLevel o.level = true
      ∧ (o.level ≤ clamp o.clearance ∨ ∃ g, o.grant = some g ∧ grantOk o g = true) := by
  cases hh : o.halted with
  | true => simp [decideOpen, hh, Decision.allowed] at h
  | false =>
    cases hv : validLevel o.level with
    | false => simp [decideOpen, hh, hv, Decision.allowed] at h
    | true =>
      refine ⟨rfl, rfl, ?_⟩
      by_cases hc : o.level ≤ clamp o.clearance
      · exact Or.inl hc
      · right
        cases hg : o.grant with
        | none => simp [decideOpen, hh, hv, hc, hg, Decision.allowed] at h
        | some g =>
          cases hok : grantOk o g with
          | true => exact ⟨g, rfl, hok⟩
          | false => simp [decideOpen, hh, hv, hc, hg, hok, Decision.allowed] at h

theorem required_pos {l : Nat} (hv : validLevel l = true) (h2 : 2 ≤ l) : 1 ≤ required l := by
  simp only [validLevel, Bool.and_eq_true, decide_eq_true_eq] at hv
  have : l = 2 ∨ l = 3 ∨ l = 4 ∨ l = 5 := by omega
  rcases this with rfl | rfl | rfl | rfl <;> decide

theorem clamp_pos (c : Nat) : 1 ≤ clamp c := Nat.le_max_left _ _

/-- Opening a file above one's clearance needs at least one enrolled officer, other than the user, whose signature
    verified. -/
theorem grant_needs_officer {o : OpenReq} (h : decideOpen o = .byGrant) :
    ∃ g, o.grant = some g ∧ grantOk o g = true ∧
      ∃ n, n ∈ o.roster ∧ n ≠ o.user ∧ ∃ a ∈ g.approvals, a.approver = n ∧ a.sigOk = true := by
  obtain ⟨hh, hv, hc⟩ := open_sound (o := o) (by rw [h]; rfl)
  rcases hc with hc | ⟨g, hg, hok⟩
  · simp [decideOpen, hh, hv, hc] at h
  · refine ⟨g, hg, hok, ?_⟩
    have hnot : ¬ o.level ≤ clamp o.clearance := by
      intro hc; simp [decideOpen, hh, hv, hc] at h
    have hlen := (grantOk_spec hok).2.2.2.2.2.2.2
    have hpos : 1 ≤ required o.level := required_pos hv (by have := clamp_pos o.clearance; omega)
    have : 0 < (approvers o.roster o.user g.approvals).length := by omega
    obtain ⟨n, hn⟩ := List.exists_mem_of_length_pos this
    exact ⟨n, mem_approvers hn⟩

/-! ## releasing a stop -/

theorem release_sound {h : Bool} {r : Request} {roster : List String} (hr : decideRelease h r roster = true) :
    h = true ∧ r.status = .pending ∧ 1 ≤ r.required ∧ r.required ≤ (approvers roster r.requester r.approvals).length
      ∧ ∃ n, n ∈ roster ∧ n ≠ r.requester ∧ ∃ a ∈ r.approvals, a.approver = n ∧ a.sigOk = true := by
  simp only [decideRelease, Bool.and_eq_true, decide_eq_true_eq] at hr
  obtain ⟨⟨⟨h1, h2⟩, h3⟩, h4⟩ := hr
  refine ⟨h1, h2, h3, h4, ?_⟩
  have : 0 < (approvers roster r.requester r.approvals).length := by omega
  obtain ⟨n, hn⟩ := List.exists_mem_of_length_pos this
  exact ⟨n, mem_approvers hn⟩

/-! ## over any run -/

theorem snd_step_anomaly (s : State) (r : Request) : (step s (.anomaly r)).2 = none := by
  simp only [step]; split <;> rfl

theorem snd_step_answer (s : State) (who : String) (act : Act) (sigOk codeOk : Bool) (roster : List String) :
    (step s (.answer who act sigOk codeOk roster)).2 = none := by
  simp only [step]
  split
  · split <;> rfl
  · rfl

theorem snd_step_tick (s : State) (roster : List String) : (step s (.tick roster)).2 = none := by
  simp only [step]
  split
  · split <;> rfl
  · rfl

theorem step_open_not_halted {s : State} {e : Event} {d : Decision}
    (h : (step s e).2 = some d) (ha : d.allowed = true) : s.halted = false := by
  cases e with
  | openFile o =>
    simp only [step, Option.some.injEq] at h
    subst h
    exact (open_sound ha).1
  | anomaly r => rw [snd_step_anomaly] at h; cases h
  | answer who act sigOk codeOk roster => rw [snd_step_answer] at h; cases h
  | tick roster => rw [snd_step_tick] at h; cases h

theorem mem_runLog {s : State} {es : List Event} {x : State × Event × Option Decision}
    (hx : x ∈ runLog s es) : x.2.2 = (step x.1 x.2.1).2 := by
  induction es generalizing s with
  | nil => simp [runLog] at hx
  | cons e es ih =>
    simp only [runLog, List.mem_cons] at hx
    rcases hx with rfl | hx
    · rfl
    · exact ih hx

/-- Over any run, every file keyd opened was opened while the PC was not stopped. -/
theorem run_open_not_halted (s : State) (es : List Event) :
    ∀ x ∈ runLog s es, ∀ d, x.2.2 = some d → d.allowed = true → x.1.halted = false := by
  intro x hx d hd ha
  rw [mem_runLog hx] at hd
  exact step_open_not_halted hd ha

theorem step_release {s : State} {e : Event} (hs : s.halted = true) (h' : (step s e).1.halted = false) :
    ∃ roster r, e = .tick roster ∧ s.request = some r ∧ decideRelease true r roster = true := by
  cases e with
  | anomaly r => exfalso; simp only [step] at h'; split at h' <;> simp_all
  | openFile o => exfalso; simp [step, hs] at h'
  | answer who act sigOk codeOk roster =>
    exfalso
    simp only [step] at h'
    split at h'
    · split at h' <;> simp_all
    · simp_all
  | tick roster =>
    simp only [step] at h'
    split at h'
    · rename_i r hh hr
      by_cases hd : decideRelease true r roster = true
      · exact ⟨roster, r, rfl, hr, hd⟩
      · simp [hd] at h'; simp_all
    · simp_all

/-- Over any run, the PC goes from stopped to running only through a release check that held: a pending request
    signed by at least one (and at least `required`) distinct enrolled officers other than the stopped user. -/
theorem run_release (s : State) (es : List Event) :
    ∀ x ∈ runLog s es, x.1.halted = true → (step x.1 x.2.1).1.halted = false →
      ∃ roster r, x.2.1 = .tick roster ∧ x.1.request = some r ∧ decideRelease true r roster = true :=
  fun _ _ hs h' => step_release hs h'

end Zenos

/-!
# The tamper-evident ledger

Each record names the hash of the record before it (`prev`) and its own hash, the SHA-256 of `prev` and its
contents. The services compute that hash (`hashOk`: the stored hash equals the recomputed one; cryptography is
trusted, as everywhere); `chainCheck` is the check they run, on the PC (zledger.verify) and on the audit nodes
(which accept a new batch only if it continues the chain they hold).

Proved: the check accepts exactly the chains whose links and hashes hold (`chainCheck_ok`); a batch an audit node
accepts extends what it held, so held history is never rewritten (`accept_extends`); and, for any hash function
without collisions, two histories that pass the check and end at the same hash are the same history
(`history_unique`). An audit node keeps the last hash; so a PC cannot present an altered past without the node
seeing a different end.
-/

namespace Zenos

/-- The genesis hash: 64 zeros. -/
def genesis : String := "0000000000000000000000000000000000000000000000000000000000000000"

structure Rec where
  prev : String
  hash : String
  /-- the stored hash is SHA-256 of `prev` and the record's contents (computed by the service) -/
  hashOk : Bool
  deriving Repr, Inhabited

/-- Whether a list of records (oldest first) continues the chain from `start`. -/
def chainOk : String → List Rec → Bool
  | _, [] => true
  | s, r :: rs => r.prev == s && r.hashOk && chainOk r.hash rs

/-- The hash at the end of the chain. -/
def chainHead : String → List Rec → String
  | s, [] => s
  | _, r :: rs => chainHead r.hash rs

/-- The check the services run: none if intact, else the index of the first broken record and why. -/
def chainCheck : String → List Rec → Nat → Option (Nat × String)
  | _, [], _ => none
  | s, r :: rs, i =>
    if r.prev != s then some (i, "prev-link broken (record edited or one deleted before it)")
    else if !r.hashOk then some (i, "hash mismatch (this record was altered)")
    else chainCheck r.hash rs (i + 1)

theorem chainCheck_ok : ∀ (s : String) (rs : List Rec) (i : Nat), chainCheck s rs i = none ↔ chainOk s rs = true
  | s, [], i => by simp [chainCheck, chainOk]
  | s, r :: rs, i => by
    simp only [chainCheck, chainOk, Bool.and_eq_true, beq_iff_eq]
    by_cases h1 : r.prev = s
    · by_cases h2 : r.hashOk = true
      · simp [h1, h2, chainCheck_ok r.hash rs (i + 1)]
      · simp [h1, h2]
    · simp [h1]

theorem chainOk_append : ∀ (s : String) (a b : List Rec),
    chainOk s (a ++ b) = (chainOk s a && chainOk (chainHead s a) b)
  | s, [], b => by simp [chainOk, chainHead]
  | s, r :: rs, b => by
    simp only [List.cons_append, chainOk, chainHead, chainOk_append r.hash rs b, Bool.and_assoc]

/-- An audit node accepts a batch only if it continues the chain it holds. -/
def acceptBatch (held batch : List Rec) : Bool := chainOk (chainHead genesis held) batch

/-- What an audit node holds stays an intact chain, and each accepted batch only appends to it. -/
theorem accept_extends {held batch : List Rec} (hh : chainOk genesis held = true)
    (ha : acceptBatch held batch = true) : chainOk genesis (held ++ batch) = true := by
  rw [chainOk_append, hh, Bool.true_and]
  exact ha

/-! ## Uniqueness of a verified history -/

/-- A record as written: its link, its contents, its hash. -/
structure Entry where
  prev : String
  body : String
  hash : String

def Entry.toRec (e : Entry) : Rec := { prev := e.prev, hash := e.hash, hashOk := true }

/-- The hash at the end of a history (oldest record first) under the hash function H. -/
def headFrom (H : String → String → String) : String → List String → String
  | s, [] => s
  | s, b :: bs => headFrom H (H s b) bs

/-- The same, newest record first. -/
def headOf (H : String → String → String) (s : String) : List String → String
  | [] => s
  | b :: older => H (headOf H s older) b

theorem headOf_snoc (H : String → String → String) (s b : String) :
    ∀ (l : List String), headOf H (H s b) l = headOf H s (l ++ [b])
  | [] => by simp [headOf]
  | x :: l => by simp [headOf, headOf_snoc H s b l]

theorem headFrom_eq (H : String → String → String) :
    ∀ (s : String) (bs : List String), headFrom H s bs = headOf H s bs.reverse
  | s, [] => by simp [headFrom, headOf]
  | s, b :: bs => by simp [headFrom, headFrom_eq H (H s b) bs, headOf_snoc]

/-- A chain of entries whose hashes are H of link and contents ends where `headFrom` says. -/
theorem chain_headFrom (H : String → String → String) :
    ∀ (s : String) (es : List Entry), (∀ e ∈ es, e.hash = H e.prev e.body) →
      chainOk s (es.map Entry.toRec) = true →
      chainHead s (es.map Entry.toRec) = headFrom H s (es.map Entry.body)
  | s, [], _, _ => by simp [chainHead, headFrom]
  | s, e :: es, hH, hc => by
    simp only [List.map_cons, chainOk, Entry.toRec, Bool.and_eq_true, beq_iff_eq] at hc
    obtain ⟨⟨hp, _⟩, hc⟩ := hc
    have ih := chain_headFrom H e.hash es (fun x hx => hH x (List.mem_cons_of_mem _ hx)) hc
    have he : e.hash = H s e.body := by rw [hH e (List.mem_cons_self ..), hp]
    simp only [List.map_cons, chainHead, headFrom, Entry.toRec]
    rw [← he]
    exact ih

/-- With a hash function without collisions that never yields the genesis value, a history is determined by the hash
    at its end. -/
theorem headOf_inj (H : String → String → String) (s : String)
    (hinj : ∀ p b p' b', H p b = H p' b' → p = p' ∧ b = b') (hs : ∀ p b, H p b ≠ s) :
    ∀ (bs bs' : List String), headOf H s bs = headOf H s bs' → bs = bs'
  | [], [], _ => rfl
  | [], b' :: _, h => absurd h.symm (hs _ _)
  | b :: _, [], h => absurd h (hs _ _)
  | b :: bs, b' :: bs', h => by
    obtain ⟨h1, h2⟩ := hinj _ _ _ _ h
    rw [h2, headOf_inj H s hinj hs bs bs' h1]

/-- Two histories that pass the ledger check from genesis and end at the same hash are the same history, for any hash
    function without collisions (SHA-256 is assumed to be one). The audit nodes hold that hash. -/
theorem history_unique (H : String → String → String)
    (hinj : ∀ p b p' b', H p b = H p' b' → p = p' ∧ b = b') (hs : ∀ p b, H p b ≠ genesis)
    (es es' : List Entry) (hH : ∀ e ∈ es, e.hash = H e.prev e.body) (hH' : ∀ e ∈ es', e.hash = H e.prev e.body)
    (hc : chainOk genesis (es.map Entry.toRec) = true) (hc' : chainOk genesis (es'.map Entry.toRec) = true)
    (heq : chainHead genesis (es.map Entry.toRec) = chainHead genesis (es'.map Entry.toRec)) :
    es.map Entry.body = es'.map Entry.body := by
  rw [chain_headFrom H _ _ hH hc, chain_headFrom H _ _ hH' hc', headFrom_eq, headFrom_eq] at heq
  exact List.reverse_inj.mp (headOf_inj H genesis hinj hs _ _ heq)

end Zenos

import ZenosFormal.Proofs

/-!
# Officers' signatures cannot be reused

An officer approves a request by signing its digest (SHA-256 of the request's core: id, kind, requester, file,
file hash, level, reason, created time, scope; for a release the scope names the stop). A decline is a signature over
`"decline:"` followed by the digest.

Model: signatures are unforgeable (an officer's signature over a message verifies only if that officer signed that
message: `Signed`), and the digest has no collisions (`hdig`). Both are the standard assumptions about Ed25519 and
SHA-256, stated as hypotheses, not axioms.

Proved: a counted approval for a request was made by that officer for exactly this request: same id, same stop
(`counted_was_signed_for`), so it cannot be replayed onto another request or another stop; and an approval can never
be taken for a decline or a decline for an approval (`approve_ne_decline`).
-/

namespace Zenos

/-- The signed core of a request (`zformat.CORE_KEYS`). -/
structure Core where
  id : String
  kind : String
  requester : String
  file : String
  fileHash : String
  level : Nat
  reason : String
  created : String
  /-- for a release: the stop it releases -/
  scope : String
  deriving Repr, Inhabited, DecidableEq

/-- What an officer signs: the digest for an approval, `"decline:"` ++ digest for a decline. -/
def approveMsg (digest : List UInt8) : List UInt8 := digest
/-- The bytes of `"decline:"` (a test checks they match what the services sign). -/
def declinePrefix : List UInt8 := [100, 101, 99, 108, 105, 110, 101, 58]
def declineMsg (digest : List UInt8) : List UInt8 := declinePrefix ++ digest

/-- SHA-256 digests are 32 bytes, so an approval (32 bytes) and a decline (40 bytes) never coincide. -/
theorem approve_ne_decline (d d' : List UInt8) (hd : d.length = 32) (hd' : d'.length = 32) :
    approveMsg d ≠ declineMsg d' := by
  intro h
  have := congrArg List.length h
  simp only [approveMsg, declineMsg, List.length_append, hd, hd'] at this
  have : declinePrefix.length = 8 := rfl
  omega

/-- The service's verdict on one recorded approval: its signature verifies for that officer over this request's
    digest. Under unforgeability this means the officer signed exactly that message. -/
def countedFor (Signed : String → List UInt8 → Prop) (digest : Core → List UInt8) (c : Core) (a : String) : Prop :=
  Signed a (approveMsg (digest c))

/-- A counted approval was signed by that officer for this very request: if the officer's signature is on the
    approval message of some core `c'` and it counts for `c`, then `c' = c` (same id, same stop). -/
theorem counted_was_signed_for (digest : Core → List UInt8)
    (hdig : ∀ c c', digest c = digest c' → c = c') (c c' : Core)
    (hsame : approveMsg (digest c') = approveMsg (digest c)) :
    c' = c ∧ c'.id = c.id ∧ c'.scope = c.scope := by
  have := hdig _ _ hsame
  exact ⟨this, by rw [this], by rw [this]⟩

/-- So the release decision counts, for a stop, only officers who approved the release of that stop: given that
    every approval it counts has a valid signature over this request's digest, each counted officer signed the core of
    this request, which names this stop. -/
theorem release_counts_only_this_stop (Signed : String → List UInt8 → Prop) (digest : Core → List UInt8)
    (hdig : ∀ c c', digest c = digest c' → c = c')
    (core : Core) (r : Request) (roster : List String)
    (hsig : ∀ a ∈ r.approvals, a.sigOk = true → Signed a.approver (approveMsg (digest core)))
    (hr : decideRelease true r roster = true) :
    ∃ n, n ∈ roster ∧ n ≠ r.requester ∧ Signed n (approveMsg (digest core)) ∧
      ∀ c', approveMsg (digest c') = approveMsg (digest core) → c'.scope = core.scope := by
  obtain ⟨-, -, -, -, n, hn, hne, a, ha, han, hok⟩ := release_sound hr
  refine ⟨n, hn, hne, ?_, fun c' h => (counted_was_signed_for digest hdig core c' h).2.2⟩
  have := hsig a ha hok
  rw [han] at this
  exact this

end Zenos

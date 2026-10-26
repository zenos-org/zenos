/-!
# Signing in with the phone

A password is kept in the vault on the PC, encrypted with a key that only the person's phone can produce (the
phone's passkey, unlocked by fingerprint, face or PIN, derives it for that one entry). When the ZENOS browser asks
for a password, the vault service sends the request to the phone; the person checks the site and the code the
browser shows, and approves; the phone answers with a passkey signature over this request and the entry's key,
encrypted to the service. Saving a password works the same way.

The service checks the facts about the answer (the signature verifies with the registered phone's key, the
signature is over this request's digest, it was made on the registered phone page, the phone verified the person,
the signature counter moved forward) and passes them here; this decides.

Proved:
* `cred_sound`: a password is released only to the page whose verified origin is the one it was saved for, over a
  verified TLS connection, within the time limit, after a phone registered to this person signed this very request
  with the person verified on the phone, and the person picked the code the browser showed.
* `cred_once`: every request is answered at most once: once answered (approved or not), it is refused, so an answer
  cannot be replayed and a wrong code cannot be retried on the same request.
* `ask_bounded`: however a program floods the service with requests, at most `max` of them reach the phone within
  any window (no approval fatigue by a stream of prompts).
-/

namespace Zenos

/-- One request for a vault entry. -/
structure CredReq where
  id : String
  user : String
  /-- the origin (scheme, host, port) of the page that asks, as the browser verified it -/
  origin : String
  /-- the origin the entry was saved for (for a save: the origin of the page that saves) -/
  entryOrigin : String
  /-- the page came over HTTPS with a certificate chain the browser verified and no distrusted authority -/
  tlsOk : Bool
  /-- the code the browser shows -/
  code : Nat
  created : Nat
  deriving Repr, Inhabited

/-- The facts the service checked about the phone's answer. -/
structure CredAnswer where
  /-- the passkey the phone answered with -/
  device : String
  /-- the passkey signature verifies with that passkey's registered public key -/
  sigOk : Bool
  /-- the signed challenge is this request's digest, and it is a sign-in (`webauthn.get`) -/
  challengeOk : Bool
  /-- signed on the registered phone page (client data origin and relying party match the registration) -/
  originOk : Bool
  /-- the phone verified the person (fingerprint, face or PIN) -/
  userVerified : Bool
  /-- the passkey's signature counter moved forward, or the passkey does not count -/
  counterOk : Bool
  /-- the code the person picked on the phone -/
  code : Nat
  deriving Repr, Inhabited

structure CredState where
  /-- requests already answered -/
  used : List String
  /-- registered phones: (passkey, person) -/
  devices : List (String × String)
  deriving Repr, Inhabited

inductive CredResult where
  | allow
  | deny (reason : String)
  deriving Repr, Inhabited, DecidableEq

def decideCred (ttl now : Nat) (st : CredState) (r : CredReq) (a : CredAnswer) : CredResult :=
  if st.used.contains r.id then .deny "already-answered"
  else if !r.tlsOk then .deny "not-verified-https"
  else if r.origin != r.entryOrigin then .deny "origin-mismatch"
  else if now < r.created || r.created + ttl < now then .deny "expired"
  else if !(st.devices.contains (a.device, r.user)) then .deny "unknown-phone"
  else if !a.sigOk then .deny "bad-signature"
  else if !a.challengeOk then .deny "not-for-this-request"
  else if !a.originOk then .deny "wrong-phone-page"
  else if !a.userVerified then .deny "person-not-verified"
  else if !a.counterOk then .deny "cloned-passkey"
  else if a.code != r.code then .deny "code-mismatch"
  else .allow

/-- Answering a request uses it up, whatever the answer. -/
def credStep (st : CredState) (r : CredReq) : CredState := { st with used := r.id :: st.used }

theorem cred_sound {ttl now : Nat} {st : CredState} {r : CredReq} {a : CredAnswer}
    (h : decideCred ttl now st r a = .allow) :
    r.id ∉ st.used ∧ r.tlsOk = true ∧ r.origin = r.entryOrigin ∧ r.created ≤ now ∧ now ≤ r.created + ttl ∧
    (a.device, r.user) ∈ st.devices ∧ a.sigOk = true ∧ a.challengeOk = true ∧ a.originOk = true ∧
    a.userVerified = true ∧ a.counterOk = true ∧ a.code = r.code := by
  unfold decideCred at h
  split at h; · cases h
  rename_i h1
  split at h; · cases h
  rename_i h2
  split at h; · cases h
  rename_i h3
  split at h; · cases h
  rename_i h4
  split at h; · cases h
  rename_i h5
  split at h; · cases h
  rename_i h6
  split at h; · cases h
  rename_i h7
  split at h; · cases h
  rename_i h8
  split at h; · cases h
  rename_i h9
  split at h; · cases h
  rename_i h10
  split at h; · cases h
  rename_i h11
  simp only [Bool.not_eq_true, Bool.not_eq_false', bne_eq_false_iff_eq, Bool.or_eq_false_iff,
    decide_eq_false_iff_not, Nat.not_lt, List.contains_iff_mem] at h1 h2 h3 h4 h5 h6 h7 h8 h9 h10 h11
  simp_all

/-- Once answered, a request is refused: no replay, and one try at the code. -/
theorem cred_once (ttl now : Nat) (st : CredState) (r : CredReq) (a : CredAnswer) :
    decideCred ttl now (credStep st r) r a = .deny "already-answered" := by
  simp [decideCred, credStep]

/-! ## Prompts reaching the phone -/

/-- Prompts sent within the window that ends at `now`. -/
def recentCount (w now : Nat) (log : List Nat) : Nat := (log.filter (fun t => now - t ≤ w)).length

/-- A new prompt goes to the phone only while fewer than `m` went within the window. -/
def decideAsk (w m now : Nat) (log : List Nat) : Bool := recentCount w now log < m

def askStep (w m : Nat) (log : List Nat) (t : Nat) : List Nat := if decideAsk w m t log then t :: log else log

/-- The prompts that went to the phone, for requests arriving at the times `ts` (oldest first). -/
def askRun (w m : Nat) (log : List Nat) : List Nat → List Nat
  | [] => log
  | t :: ts => askRun w m (askStep w m log t) ts

theorem length_filter_mono {α} (p q : α → Bool) (hpq : ∀ x, p x = true → q x = true) :
    ∀ l : List α, (l.filter p).length ≤ (l.filter q).length
  | [] => by simp
  | x :: l => by
    have ih := length_filter_mono p q hpq l
    by_cases hp : p x = true
    · simp [hp, hpq x hp]; omega
    · by_cases hq : q x = true
      · simp [hp, hq]; omega
      · simp [hp, hq]; omega

theorem recentCount_mono (w : Nat) {t now : Nat} (h : t ≤ now) (log : List Nat) :
    recentCount w now log ≤ recentCount w t log :=
  length_filter_mono _ _ (fun x hx => by simp at hx ⊢; omega) log

/-- At most `m` prompts in every window from time `T` on. -/
def Bounded (w m T : Nat) (log : List Nat) : Prop := ∀ now, T ≤ now → recentCount w now log ≤ m

theorem askStep_bounded {w m T t : Nat} {log : List Nat} (hb : Bounded w m T log) (ht : T ≤ t) :
    Bounded w m t (askStep w m log t) := by
  intro now hn
  unfold askStep
  split
  · rename_i ha
    have hm : recentCount w t log < m := by simpa [decideAsk] using ha
    have hmono := recentCount_mono w hn log
    have : recentCount w now (t :: log) ≤ recentCount w now log + 1 := by
      unfold recentCount; simp only [List.filter_cons]; split <;> simp
    omega
  · exact hb now (Nat.le_trans ht hn)

/-- However many requests arrive, and however fast (times not going backwards), at most `m` prompts reach the
    phone within any window. -/
theorem ask_bounded (w m : Nat) : ∀ (ts : List Nat) (T : Nat) (log : List Nat),
    Bounded w m T log → (∀ t ∈ ts, T ≤ t) → List.Pairwise (· ≤ ·) ts →
    ∀ now, (∀ t ∈ ts, t ≤ now) → T ≤ now → recentCount w now (askRun w m log ts) ≤ m
  | [], T, log, hb, _, _, now, _, hT => hb now hT
  | t :: ts, T, log, hb, hts, hp, now, hnow, _ => by
    simp only [askRun]
    have hTt := hts t (List.mem_cons_self ..)
    have hb' := askStep_bounded hb hTt
    have hp' := List.pairwise_cons.mp hp
    exact ask_bounded w m ts t _ hb' hp'.1 hp'.2 now (fun x hx => hnow x (List.mem_cons_of_mem _ hx))
      (hnow t (List.mem_cons_self ..))

end Zenos

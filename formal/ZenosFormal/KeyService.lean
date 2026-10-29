import ZenosFormal.Decide
import ZenosFormal.Proofs
import ZenosFormal.Cred

/-!
# The key service: a sealed file's key leaves a machine the PC does not control

From 0.2 a sealed file's key is not kept on the PC. The key service (`zenos-keysvc`, on a machine the PC's users and
administrator do not control) derives it from a master key for the file's level, and hands it to a PC only for one
file, one request at a time. Someone who takes root on the PC can then read only the files the service agreed to
open while they held it, and every one of those releases is already recorded on the service.

The service checks the facts below and passes them here; this decides.

* the PC is enrolled and the request is signed with its identity key, recent and not seen before;
* the audit node heard from the PC within the silence limit, its last signed status shows every protecting
  service running and the PC not stopped;
* the user is one the service assigned to this PC (root on one PC cannot speak for the users of another);
* not too many releases for this PC and user, and for this PC as a whole, within the rate window;
* from the presence level up, the user confirmed this very request on their own security key or phone (a passkey
  signature over a challenge the service issued for this PC, user and file, with the person verified);
* and then the same decision as on the PC (`decideOpen`), with the clearance, officers and grant as the service
  itself holds them, never as the PC reports them.

Proved:
* `key_sound`: a key is released only when all of the above hold.
* `key_open_sound`: a released key is one `decideOpen` allows, so `open_sound` carries over: the PC is not stopped,
  the level is real, and the service's clearance for the user covers it or a valid grant does.
* `key_silent_refused`, `key_unhealthy_refused`, `key_halted_refused`: a PC that went silent, whose protecting
  services are not all running, or that reported a stop gets no key at all, whoever asks.
* `key_rate_bounded`: however a program on the PC floods the service, at most `rateMax` keys per user are released
  within any rate window (the same counting as `ask_bounded`), with requests decided one at a time (the service
  serialises the count and the decision).
-/

namespace Zenos

/-- The facts about one confirmation on the user's own authenticator (checked by the service with zwebauthn). -/
structure Presence where
  /-- the passkey is registered with the service to this user -/
  registered : Bool
  sigOk : Bool
  /-- the signed challenge is the one the service issued for this PC, user and file, unused and not expired -/
  challengeOk : Bool
  originOk : Bool
  userVerified : Bool
  counterOk : Bool
  deriving Repr, Inhabited

def Presence.ok (p : Presence) : Bool :=
  p.registered && p.sigOk && p.challengeOk && p.originOk && p.userVerified && p.counterOk

structure KeyReq where
  enrolled : Bool
  /-- signed with the PC's enrolled identity key -/
  sigOk : Bool
  /-- the time in the request is within the allowed skew and its nonce was not used before -/
  fresh : Bool
  now : Nat
  /-- when the audit node last heard from the PC (0: never) -/
  lastSeen : Nat
  silence : Nat
  /-- the PC's last signed status: every protecting service active -/
  servicesOk : Bool
  /-- the PC's last signed status: stopped after an anomaly -/
  pcHalted : Bool
  /-- keys released for this PC and user within the rate window -/
  recent : Nat
  rateMax : Nat
  /-- keys released for this PC (all users) within the rate window, and the PC's own limit -/
  machineRecent : Nat
  machineRateMax : Nat
  /-- the user is one the service assigned to this PC -/
  assigned : Bool
  /-- the level from which a confirmation on the user's authenticator is needed (6: never) -/
  presenceFrom : Nat
  presence : Option Presence
  /-- the open request, with the clearance, roster and grant as the service holds them -/
  openReq : OpenReq
  deriving Repr, Inhabited

def presenceOk (k : KeyReq) : Bool :=
  if k.presenceFrom ≤ k.openReq.level then
    match k.presence with
    | some p => p.ok
    | none => false
  else true

def decideKey (k : KeyReq) : Decision :=
  if !k.enrolled then .refuse "machine"
  else if !k.sigOk then .refuse "signature"
  else if !k.fresh then .refuse "replay"
  else if k.lastSeen + k.silence < k.now then .refuse "silent"
  else if !k.servicesOk then .refuse "unhealthy"
  else if k.pcHalted then .refuse "halted"
  else if !k.assigned then .refuse "not-assigned"
  else if k.rateMax ≤ k.recent then .refuse "rate"
  else if k.machineRateMax ≤ k.machineRecent then .refuse "rate"
  else if !presenceOk k then .refuse "presence"
  else decideOpen { k.openReq with halted := k.openReq.halted || k.pcHalted }

theorem key_sound {k : KeyReq} (h : (decideKey k).allowed = true) :
    k.enrolled = true ∧ k.sigOk = true ∧ k.fresh = true ∧ k.now ≤ k.lastSeen + k.silence ∧
    k.servicesOk = true ∧ k.pcHalted = false ∧ k.recent < k.rateMax ∧ presenceOk k = true ∧
    k.assigned = true ∧ k.machineRecent < k.machineRateMax := by
  unfold decideKey at h
  split at h; · simp [Decision.allowed] at h
  rename_i h1
  split at h; · simp [Decision.allowed] at h
  rename_i h2
  split at h; · simp [Decision.allowed] at h
  rename_i h3
  split at h; · simp [Decision.allowed] at h
  rename_i h4
  split at h; · simp [Decision.allowed] at h
  rename_i h5
  split at h; · simp [Decision.allowed] at h
  rename_i h6
  split at h; · simp [Decision.allowed] at h
  rename_i h7
  split at h; · simp [Decision.allowed] at h
  rename_i h8
  split at h; · simp [Decision.allowed] at h
  rename_i h9
  split at h; · simp [Decision.allowed] at h
  rename_i h10
  simp only [Bool.not_eq_true, Bool.not_eq_false', Nat.not_lt, Nat.not_le] at h1 h2 h3 h4 h5 h6 h7 h8 h9 h10
  exact ⟨h1, h2, h3, h4, h5, h6, h8, h10, h7, h9⟩

theorem key_open {k : KeyReq} (h : (decideKey k).allowed = true) :
    (decideOpen { k.openReq with halted := k.openReq.halted || k.pcHalted }).allowed = true := by
  have hs := key_sound h
  unfold decideKey at h
  obtain ⟨e1, e2, e3, e4, e5, e6, e7, e8, e9, e10⟩ := hs
  simp only [e1, e2, e3, e5, e6, e8, e9, Bool.not_true, Bool.false_eq_true,
    ite_false, Nat.not_lt.mpr e4, Nat.not_le.mpr e7, Nat.not_le.mpr e10] at h
  simp only [e6]
  exact h

/-- The open request as the service decides it: stopped if the PC reported a stop. -/
def KeyReq.effOpen (k : KeyReq) : OpenReq := { k.openReq with halted := k.openReq.halted || k.pcHalted }

/-- What `open_sound` gives, for a key the service released. -/
theorem key_open_sound {k : KeyReq} (h : (decideKey k).allowed = true) :
    k.openReq.halted = false ∧ validLevel k.openReq.level = true ∧
    (k.openReq.level ≤ clamp k.openReq.clearance ∨ ∃ g, k.openReq.grant = some g ∧ grantOk k.effOpen g = true) := by
  obtain ⟨h1, h2, h3⟩ := open_sound (key_open h)
  refine ⟨?_, h2, h3⟩
  simp only [Bool.or_eq_false_iff] at h1
  exact h1.1

/-- From the presence level up, a released key always came with a confirmation on the user's own authenticator. -/
theorem key_presence {k : KeyReq} (h : (decideKey k).allowed = true) (hl : k.presenceFrom ≤ k.openReq.level) :
    ∃ p, k.presence = some p ∧ p.ok = true := by
  have hp := (key_sound h).2.2.2.2.2.2.2.1
  unfold presenceOk at hp
  simp only [hl, ite_true] at hp
  cases hk : k.presence with
  | none => simp [hk] at hp
  | some p => exact ⟨p, rfl, by simpa [hk] using hp⟩

theorem key_silent_refused {k : KeyReq} (h : k.lastSeen + k.silence < k.now) : (decideKey k).allowed = false := by
  cases hd : (decideKey k).allowed
  · rfl
  · have := (key_sound hd).2.2.2.1; omega

theorem key_unhealthy_refused {k : KeyReq} (h : k.servicesOk = false) : (decideKey k).allowed = false := by
  cases hd : (decideKey k).allowed
  · rfl
  · have := (key_sound hd).2.2.2.2.1; simp_all

theorem key_halted_refused {k : KeyReq} (h : k.pcHalted = true) : (decideKey k).allowed = false := by
  cases hd : (decideKey k).allowed
  · rfl
  · have := (key_sound hd).2.2.2.2.2.1; simp_all

/-! ## The rate limit over a run -/

/-- The service's step for one request at time `t`: the release times kept for this PC and user grow by `t` exactly
    when the key is released. `recent` is counted from the log over the window `w`. -/
def keyStep (w : Nat) (log : List Nat) (t : Nat) (k : KeyReq) : List Nat :=
  if (decideKey { k with now := t, recent := recentCount w t log }).allowed then t :: log else log

def keyRun (w : Nat) (log : List Nat) : List (Nat × KeyReq) → List Nat
  | [] => log
  | (t, k) :: rs => keyRun w (keyStep w log t k) rs

theorem keyStep_bounded {w m T t : Nat} {log : List Nat} {k : KeyReq} (hm : k.rateMax = m)
    (hb : Bounded w m T log) (ht : T ≤ t) : Bounded w m t (keyStep w log t k) := by
  intro now hn
  unfold keyStep
  split
  · rename_i ha
    have hr := (key_sound ha).2.2.2.2.2.2.1
    simp only at hr
    have hmono := recentCount_mono w hn log
    have : recentCount w now (t :: log) ≤ recentCount w now log + 1 := by
      unfold recentCount; simp only [List.filter_cons]; split <;> simp
    omega
  · exact hb now (Nat.le_trans ht hn)

/-- However many key requests a program on the PC sends for one user, and however fast, at most `m` keys are
    released within any window (requests in time order, all with the service's limit `m`). -/
theorem key_rate_bounded (w m : Nat) : ∀ (rs : List (Nat × KeyReq)) (T : Nat) (log : List Nat),
    Bounded w m T log → (∀ r ∈ rs, T ≤ r.1 ∧ r.2.rateMax = m) → List.Pairwise (fun a b => a.1 ≤ b.1) rs →
    ∀ now, (∀ r ∈ rs, r.1 ≤ now) → T ≤ now → recentCount w now (keyRun w log rs) ≤ m
  | [], T, log, hb, _, _, now, _, hT => hb now hT
  | (t, k) :: rs, T, log, hb, hrs, hp, now, hnow, _ => by
    simp only [keyRun]
    have h0 := hrs (t, k) (List.mem_cons_self ..)
    have hb' := keyStep_bounded h0.2 hb h0.1
    have hp' := List.pairwise_cons.mp hp
    exact key_rate_bounded w m rs t _ hb'
      (fun r hr => ⟨hp'.1 r hr, (hrs r (List.mem_cons_of_mem _ hr)).2⟩) hp'.2 now
      (fun r hr => hnow r (List.mem_cons_of_mem _ hr)) (hnow (t, k) (List.mem_cons_self ..))

end Zenos

/-!
# Organizations reaching each other, and place (docs/FEDERATION.md)

## Federation

Each organization runs its own relay for ZENOS Messages. Relays reach each other only when both organizations are
on the member list. An entry of the list counts only when at least `k` distinct responsible bodies ("authorities")
signed it, and `k` is never below 2: one stolen signing key cannot add an organization. An entry says up to which
level the organization may receive, and whether it is a publish-only member (a disaster information service:
alerts only, never messages).

`decideFederate` decides each request from one relay to another. It is given facts the relay checked: whether the
sending relay's signature verified against the key in its listed entry (`relaySigOk`), whether the request is fresh
and not a replay (`fresh`), and the declared level.

Proved:
* `fed_sound`: an allowed request was signed, fresh, both organizations are listed, and the level is within both
  entries.
* `unlisted_refused`: a request to or from an organization without a valid entry is refused.
* `one_signer_not_enough`: an organization whose entries each carry at most one valid authority signature is not
  listed.
* `level_bound`: an allowed request never carries a level above what the receiving organization may receive.
* `publisher_cannot_message`: a publish-only member never sends or receives messages or key bundles.

## Place

A device's own location (satellite positioning in the phone or browser) can be faked. So location is used to
narrow what a person may do, and only widens it together with a second proof that does not come from the device's
positioning (a beacon or NFC tag in the building, the office network, an official device checked in at a cordon).

`decidePlace` is given the decision without place (`baseAllow`, from clearance and grants), the level, whether the
content requires being inside a zone, the device's own reading (`gpsInside`), the second proof (`proofInside`),
whether the device is outside the country, and, for emergency sharing, whether a disaster is declared.

Proved:
* `abroad_closes`: outside the country, levels from `closeAbroadFrom` up are refused.
* `no_widen_without_emergency`: without a declared disaster, place never allows what the decision without place
  refuses.
* `widen_needs_all`: whatever place allows beyond the decision without place is emergency sharing, while a disaster
  is declared, inside the area by both the device and the second proof.
* `zone_needs_proof`: content that requires a zone is opened only with the second proof.
* `gps_alone_changes_nothing`: without the second proof, the device's location reading does not change the decision
  (faking it gains nothing).
-/

namespace Zenos

/-! ## Federation -/

structure FedSig where
  signer : String
  /-- the signature over the entry verified against that authority's key -/
  ok : Bool
  deriving Repr, Inhabited, DecidableEq

structure Member where
  org : String
  maxLevel : Nat
  publishOnly : Bool
  sigs : List FedSig
  deriving Repr, Inhabited

inductive FedKind where
  | message
  | keys
  | alert
  deriving Repr, Inhabited, DecidableEq

structure FedReq where
  authorities : List String
  k : Nat
  members : List Member
  fromOrg : String
  toOrg : String
  relaySigOk : Bool
  fresh : Bool
  kind : FedKind
  level : Nat
  deriving Repr, Inhabited

/-- The distinct authorities whose signature on the entry verified. -/
def validSigners (auth : List String) (m : Member) : List String :=
  ((m.sigs.filter (fun s => s.ok && auth.contains s.signer)).map (·.signer)).eraseDups

def listedEntry (r : FedReq) (m : Member) : Bool :=
  2 ≤ r.k && r.k ≤ (validSigners r.authorities m).length

/-- The organization's valid entry, if any. -/
def lookup (r : FedReq) (o : String) : Option Member :=
  r.members.find? (fun m => m.org == o && listedEntry r m)

inductive FedDecision where
  | allow
  | refuse (reason : String)
  deriving Repr, Inhabited, DecidableEq

def decideFederate (r : FedReq) : FedDecision :=
  if !r.relaySigOk then .refuse "signature"
  else if !r.fresh then .refuse "replay"
  else match lookup r r.fromOrg, lookup r r.toOrg with
    | some s, some d =>
      if r.kind != .alert && (s.publishOnly || d.publishOnly) then .refuse "publish-only"
      else if r.level ≤ s.maxLevel && r.level ≤ d.maxLevel then .allow
      else .refuse "level"
    | _, _ => .refuse "unlisted"

theorem fed_sound {r : FedReq} (h : decideFederate r = .allow) :
    r.relaySigOk = true ∧ r.fresh = true ∧
    ∃ s d, lookup r r.fromOrg = some s ∧ lookup r r.toOrg = some d ∧ r.level ≤ s.maxLevel ∧ r.level ≤ d.maxLevel := by
  unfold decideFederate at h
  cases hs : r.relaySigOk <;> cases hf : r.fresh <;> simp only [hs, hf] at h <;> try contradiction
  refine ⟨rfl, rfl, ?_⟩
  cases h1 : lookup r r.fromOrg <;> cases h2 : lookup r r.toOrg <;> simp only [h1, h2] at h <;> try contradiction
  rename_i s d
  refine ⟨s, d, rfl, rfl, ?_⟩
  repeat' split at h
  all_goals simp_all

theorem unlisted_refused {r : FedReq} (h : lookup r r.toOrg = none) : decideFederate r ≠ .allow := by
  intro ha
  obtain ⟨_, _, s, d, _, hd, _⟩ := fed_sound ha
  simp_all

theorem unlisted_sender_refused {r : FedReq} (h : lookup r r.fromOrg = none) : decideFederate r ≠ .allow := by
  intro ha
  obtain ⟨_, _, s, d, hs, _, _⟩ := fed_sound ha
  simp_all

theorem one_signer_not_enough {r : FedReq} {o : String}
    (h : ∀ m ∈ r.members, m.org = o → (validSigners r.authorities m).length ≤ 1) : lookup r o = none := by
  unfold lookup
  rw [List.find?_eq_none]
  intro m hm
  simp only [listedEntry, Bool.and_eq_true, beq_iff_eq, decide_eq_true_eq, not_and]
  intro ho hk
  have := h m hm ho
  omega

theorem level_bound {r : FedReq} {d : Member} (h : decideFederate r = .allow) (hd : lookup r r.toOrg = some d) :
    r.level ≤ d.maxLevel := by
  obtain ⟨_, _, s, d', _, hd', _, hl⟩ := fed_sound h
  rw [hd] at hd'
  cases hd'
  exact hl

theorem publisher_cannot_message {r : FedReq} {s d : Member} (h : decideFederate r = .allow) (hk : r.kind ≠ .alert)
    (hs : lookup r r.fromOrg = some s) (hd : lookup r r.toOrg = some d) :
    s.publishOnly = false ∧ d.publishOnly = false := by
  unfold decideFederate at h
  cases h1 : r.relaySigOk <;> cases h2 : r.fresh <;> simp_all
  cases hp : s.publishOnly <;> cases hq : d.publishOnly <;> simp_all

/-! Examples: a ministry, a prefecture and a city; the authorities are the ministry and the prefecture, k = 2. -/

def exAuth : List String := ["ministry", "prefecture"]
def exCity : Member := { org := "city", maxLevel := 3, publishOnly := false, sigs := [⟨"ministry", true⟩, ⟨"prefecture", true⟩] }
def exMinistry : Member := { org := "ministry", maxLevel := 5, publishOnly := false, sigs := [⟨"ministry", true⟩, ⟨"prefecture", true⟩] }
def exGeoid : Member := { org := "geoid", maxLevel := 1, publishOnly := true, sigs := [⟨"ministry", true⟩, ⟨"prefecture", true⟩] }
/-- signed twice by the same authority, and once with a signature that does not verify -/
def exRogue : Member := { org := "rogue", maxLevel := 5, publishOnly := false, sigs := [⟨"ministry", true⟩, ⟨"ministry", true⟩, ⟨"prefecture", false⟩] }

def exReq (f t : String) (kind : FedKind) (level : Nat) : FedReq :=
  { authorities := exAuth, k := 2, members := [exCity, exMinistry, exGeoid, exRogue], fromOrg := f, toOrg := t,
    relaySigOk := true, fresh := true, kind, level }

theorem ex_ministry_to_city : decideFederate (exReq "ministry" "city" .message 3) = .allow := by decide
theorem ex_above_city_level : decideFederate (exReq "ministry" "city" .message 4) = .refuse "level" := by decide
theorem ex_rogue_refused : decideFederate (exReq "rogue" "city" .message 1) = .refuse "unlisted" := by decide
theorem ex_geoid_alert : decideFederate (exReq "geoid" "city" .alert 1) = .allow := by decide
theorem ex_geoid_no_message : decideFederate (exReq "geoid" "city" .message 1) = .refuse "publish-only" := by decide
theorem ex_k1_refused : decideFederate { exReq "ministry" "city" .message 1 with k := 1 } = .refuse "unlisted" := by decide

/-! ## Place -/

structure PlaceReq where
  /-- the decision without place (clearance, grants) -/
  baseAllow : Bool
  level : Nat
  /-- this content may be opened only inside a zone (the office, a meeting room) -/
  zoneRequired : Bool
  /-- the device's own positioning says it is inside -/
  gpsInside : Bool
  /-- a second proof, not from the device's positioning, says it is inside -/
  proofInside : Bool
  abroad : Bool
  closeAbroadFrom : Nat
  /-- a disaster is declared for the area by a listed issuer, and still in force -/
  emergency : Bool
  /-- the request is for emergency sharing (beyond the decision without place) -/
  emergencyShare : Bool
  deriving Repr, Inhabited

def decidePlace (r : PlaceReq) : FedDecision :=
  if r.abroad && r.closeAbroadFrom ≤ r.level then .refuse "abroad"
  else if r.baseAllow then
    if r.zoneRequired && !(r.gpsInside && r.proofInside) then .refuse "outside"
    else .allow
  else if r.emergencyShare && r.emergency && r.gpsInside && r.proofInside then .allow
  else .refuse "clearance"

theorem abroad_closes {r : PlaceReq} (ha : r.abroad = true) (hl : r.closeAbroadFrom ≤ r.level) :
    decidePlace r = .refuse "abroad" := by
  simp [decidePlace, ha, hl]

theorem widen_needs_all {r : PlaceReq} (h : decidePlace r = .allow) (hb : r.baseAllow = false) :
    r.emergencyShare = true ∧ r.emergency = true ∧ r.gpsInside = true ∧ r.proofInside = true := by
  unfold decidePlace at h
  repeat' split at h
  all_goals simp_all

theorem no_widen_without_emergency {r : PlaceReq} (h : decidePlace r = .allow) (he : r.emergency = false) :
    r.baseAllow = true := by
  cases hb : r.baseAllow
  · have := (widen_needs_all h hb).2.1
    simp_all
  · rfl

theorem zone_needs_proof {r : PlaceReq} (h : decidePlace r = .allow) (hz : r.zoneRequired = true)
    (hb : r.baseAllow = true) : r.gpsInside = true ∧ r.proofInside = true := by
  unfold decidePlace at h
  repeat' split at h
  all_goals simp_all

theorem gps_alone_changes_nothing (r : PlaceReq) (g : Bool) (hp : r.proofInside = false) :
    decidePlace { r with gpsInside := g } = decidePlace r := by
  unfold decidePlace
  simp [hp]

end Zenos

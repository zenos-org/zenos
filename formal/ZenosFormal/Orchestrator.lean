import ZenosFormal.Decide

/-!
# The conductor: which provider may receive which piece of a task (design stage, docs/ORCHESTRATOR.md)

ZENOS splits a task's material into fragments and sends each fragment to one frontier-model provider. Every
fragment is described by the data items ("atoms") it carries: which record an atom belongs to, and its role:

* `ident`: what or whom the record is about (a name, an axis label, a legend, a file name);
* `attr`: the value (a diagnosis, the numbers of a chart, an amount);
* `other`: neither.

A record is protected when the task holds both an `ident` and an `attr` atom of it. Example: a chart's numbers go
to provider A with the labels masked, the text that says what the chart shows goes to provider B with the numbers
masked; each provider gets half, neither gets a pair.

The route is let through only when every fragment goes to an allowed provider and no provider would receive an
`ident` and an `attr` atom of the same record.

Proved:
* `route_sound`: an allowed route sends only to allowed providers.
* `no_linked_pair`: under an allowed route no provider (named in the route or not) receives an identifier and a
  value of the same record.
* `one_provider_not_whole`: under an allowed route, for every protected record and every provider, some atom of that
  record never reaches that provider.
* `chart_split_allowed` / `chart_whole_refused`: the chart example, checked.
-/

namespace Zenos

inductive Role where
  | ident
  | attr
  | other
  deriving Repr, Inhabited, DecidableEq

structure Atom where
  record : String
  role : Role
  deriving Repr, Inhabited, DecidableEq

structure Fragment where
  atoms : List Atom
  /-- the provider this fragment would be sent to -/
  to : String
  deriving Repr, Inhabited

structure RouteReq where
  /-- providers the person (or the administrator) allows -/
  allowed : List String
  frags : List Fragment
  deriving Repr, Inhabited

/-- Everything provider `p` would receive. -/
def sees (r : RouteReq) (p : String) : List Atom :=
  (r.frags.filter (fun f => f.to == p)).flatMap (·.atoms)

def allAtoms (r : RouteReq) : List Atom := r.frags.flatMap (·.atoms)

def hasRole (as : List Atom) (rec : String) (role : Role) : Bool :=
  as.any (fun a => a.record == rec && a.role == role)

def linked (as : List Atom) (rec : String) : Bool :=
  hasRole as rec .ident && hasRole as rec .attr

/-- Some provider in the route would receive a linked pair. -/
def anyLinked (r : RouteReq) : Bool :=
  r.frags.any (fun f => (sees r f.to).any (fun a => linked (sees r f.to) a.record))

def protectedRec (r : RouteReq) (rec : String) : Bool := linked (allAtoms r) rec

inductive RouteDecision where
  | allow
  | refuse (reason : String)
  deriving Repr, Inhabited, DecidableEq

def decideRoute (r : RouteReq) : RouteDecision :=
  if !(r.frags.all (fun f => r.allowed.contains f.to)) then .refuse "provider"
  else if anyLinked r then .refuse "linked"
  else .allow

theorem route_sound {r : RouteReq} (h : decideRoute r = .allow) :
    ∀ f ∈ r.frags, f.to ∈ r.allowed := by
  unfold decideRoute at h
  cases h1 : (r.frags.all (fun f => r.allowed.contains f.to)) with
  | false => rw [h1] at h; simp at h
  | true =>
    intro f hf
    have := List.all_eq_true.mp h1 f hf
    simpa using this

private theorem not_anyLinked {r : RouteReq} (h : decideRoute r = .allow) : anyLinked r = false := by
  unfold decideRoute at h
  cases h1 : (r.frags.all (fun f => r.allowed.contains f.to)) with
  | false => rw [h1] at h; simp at h
  | true =>
    rw [h1] at h
    cases h2 : anyLinked r with
    | false => rfl
    | true => rw [h2] at h; simp at h

theorem no_linked_pair {r : RouteReq} (h : decideRoute r = .allow) (p : String) (a b : Atom)
    (ha : a ∈ sees r p) (hb : b ∈ sees r p) (hrec : a.record = b.record)
    (hi : a.role = .ident) (hv : b.role = .attr) : False := by
  have hn := not_anyLinked h
  -- a reached p through some fragment f with f.to = p
  unfold sees at ha
  rcases List.mem_flatMap.mp ha with ⟨f, hf, haf⟩
  rcases List.mem_filter.mp hf with ⟨hfr, hto⟩
  have hto' : f.to = p := by simpa using hto
  have hl : linked (sees r f.to) a.record = true := by
    rw [hto']
    unfold linked hasRole
    simp only [Bool.and_eq_true, List.any_eq_true]
    refine ⟨⟨a, ?_, ?_⟩, ⟨b, hb, ?_⟩⟩
    · unfold sees; exact List.mem_flatMap.mpr ⟨f, hf, haf⟩
    · simp [hi]
    · simp [hrec, hv]
  have : anyLinked r = true := by
    unfold anyLinked
    apply List.any_eq_true.mpr
    refine ⟨f, hfr, List.any_eq_true.mpr ⟨a, ?_, hl⟩⟩
    rw [hto']; unfold sees; exact List.mem_flatMap.mpr ⟨f, hf, haf⟩
  rw [hn] at this
  exact Bool.false_ne_true this

theorem one_provider_not_whole {r : RouteReq} (h : decideRoute r = .allow) (p rec : String)
    (hp : protectedRec r rec = true) : ∃ a ∈ allAtoms r, a.record = rec ∧ a ∉ sees r p := by
  unfold protectedRec linked hasRole at hp
  simp only [Bool.and_eq_true, List.any_eq_true, Bool.and_eq_true, beq_iff_eq] at hp
  rcases hp with ⟨⟨i, hi, hir, hirole⟩, ⟨v, hv, hvr, hvrole⟩⟩
  by_cases hin : i ∈ sees r p
  · by_cases hvn : v ∈ sees r p
    · exact (no_linked_pair h p i v hin hvn (by rw [hir, hvr]) hirole hvrole).elim
    · exact ⟨v, hv, hvr, hvn⟩
  · exact ⟨i, hi, hir, hin⟩

/-! The chart example: provider A gets the numbers, provider B gets what they are about. -/

def chartSplit : RouteReq :=
  { allowed := ["A", "B"],
    frags := [{ atoms := [⟨"chart", .attr⟩], to := "A" },
              { atoms := [⟨"chart", .ident⟩, ⟨"memo", .other⟩], to := "B" }] }

def chartWhole : RouteReq :=
  { allowed := ["A", "B"],
    frags := [{ atoms := [⟨"chart", .attr⟩, ⟨"chart", .ident⟩], to := "A" }] }

def chartElsewhere : RouteReq :=
  { allowed := ["A", "B"],
    frags := [{ atoms := [⟨"chart", .attr⟩], to := "A" }, { atoms := [⟨"chart", .ident⟩], to := "C" }] }

theorem chart_split_allowed : decideRoute chartSplit = .allow := by decide
theorem chart_whole_refused : decideRoute chartWhole = .refuse "linked" := by decide
theorem chart_unlisted_refused : decideRoute chartElsewhere = .refuse "provider" := by decide

/-! ## Weights

Each provider carries a weight per kind of work (measured on the PC: how often its answers passed the local
checks). Weights decide two things only: which allowed route the conductor prefers, and how much a provider's
answer counts when several providers answer the same masked piece. Weights never enter `decideRoute`, so no
weight can let a linked pair through (that is true by construction: `decideRoute` does not read them).

A cross-checked answer is accepted when the providers giving it hold more than half of the weight of all the
providers that answered, and at least two distinct providers give it: however heavy one provider is made, it
never decides alone.
-/

structure Ballot where
  provider : String
  answer : String
  deriving Repr, Inhabited

structure VoteReq where
  weights : List (String × Nat)
  ballots : List Ballot
  /-- the answer about to be accepted -/
  answer : String
  deriving Repr, Inhabited

def weightOf (ws : List (String × Nat)) (p : String) : Nat :=
  match ws.find? (fun x => x.1 == p) with
  | some x => x.2
  | none => 0

def wsum (ws : List (String × Nat)) (ps : List String) : Nat :=
  (ps.map (weightOf ws)).foldr (· + ·) 0

/-- providers, each once, that answered -/
def voters (v : VoteReq) : List String := dedup (v.ballots.map (·.provider))

/-- providers, each once, with some weight, that gave this answer -/
def backers (v : VoteReq) : List String :=
  dedup ((v.ballots.filter (fun b => b.answer == v.answer && weightOf v.weights b.provider > 0)).map (·.provider))

def decideVote (v : VoteReq) : Bool :=
  decide (2 ≤ (backers v).length) && decide (wsum v.weights (voters v) < 2 * wsum v.weights (backers v))

theorem vote_sound {v : VoteReq} (h : decideVote v = true) :
    2 ≤ (backers v).length ∧ wsum v.weights (voters v) < 2 * wsum v.weights (backers v) := by
  unfold decideVote at h
  simp only [Bool.and_eq_true, decide_eq_true_eq] at h
  exact h

/-- However the weights are set, an answer given by one provider only is never accepted. -/
theorem one_provider_never_decides {v : VoteReq} (h : decideVote v = true) : ¬ (backers v).length ≤ 1 := by
  have := (vote_sound h).1
  omega

def heavyA : VoteReq :=
  { weights := [("A", 100), ("B", 1), ("C", 1)],
    ballots := [⟨"A", "x"⟩, ⟨"B", "y"⟩, ⟨"C", "y"⟩], answer := "x" }

def heavyAB : VoteReq :=
  { weights := [("A", 100), ("B", 1), ("C", 1)],
    ballots := [⟨"A", "x"⟩, ⟨"B", "x"⟩, ⟨"C", "y"⟩], answer := "x" }

theorem heavy_alone_refused : decideVote heavyA = false := by decide
theorem heavy_with_second_accepted : decideVote heavyAB = true := by decide

/-! ## Each step of a task

The conductor runs a task as steps. Every step is decided here before it runs:

* `send`: a piece goes to a provider. The provider must be allowed. A task at level `local` sends nothing; at level
  `masked` the payload must be tokens and allowed value classes only (checked on the PC by the masker:
  `payloadMasked`); at level `split` the piece's route must have passed `decideRoute` (`routeOk`).
* `tool`: a tool runs on the PC, in the sandbox. If it reaches the network, the destination must be one the task
  may reach.
* `act`: something that cannot be taken back (send a mail or message, delete, pay, publish). The destination must be
  one the task may reach, and the person must have confirmed it on the phone.

Destinations come from the task as the person set it (`dests`). Once a worker has read outside content (web, mail,
a file from someone else: `tainted`), only the destinations also marked safe after outside content (`afterTaint`)
remain. Nothing a model writes is an input to this decision, so text in that content cannot add a destination.

Proved:
* `masked_only_out`, `local_sends_nothing`, `split_needs_route`, `send_to_allowed`. A send step names no
  destination of its own (`dest` must be empty); its provider is what is checked.
* `taint_narrows`: the destinations open after outside content are a subset of those open before.
* `dest_from_person`: any destination a step reaches was in the task as the person set it.
* `confirm_irreversible`: an act that cannot be taken back runs only after the phone confirmation.
-/

inductive Level where
  | masked
  | split
  | onPC
  deriving Repr, Inhabited, DecidableEq

inductive StepKind where
  | send
  | tool
  | act
  deriving Repr, Inhabited, DecidableEq

structure StepReq where
  kind : StepKind
  level : Level
  provider : String
  allowed : List String
  payloadMasked : Bool
  routeOk : Bool
  /-- "" when the step reaches no destination (a tool with no network) -/
  dest : String
  dests : List String
  afterTaint : List String
  tainted : Bool
  confirmed : Bool
  deriving Repr, Inhabited

def openDests (dests afterTaint : List String) (tainted : Bool) : List String :=
  if tainted then dests.filter (fun d => afterTaint.contains d) else dests

def destOk (r : StepReq) : Bool :=
  r.dest == "" || (openDests r.dests r.afterTaint r.tainted).contains r.dest

def decideStep (r : StepReq) : RouteDecision :=
  match r.kind with
  | .send =>
    if !r.allowed.contains r.provider then .refuse "provider"
    else if r.dest != "" then .refuse "destination"
    else if r.level == .onPC then .refuse "on-pc"
    else if r.level == .masked && !r.payloadMasked then .refuse "unmasked"
    else if r.level == .split && !r.routeOk then .refuse "route"
    else .allow
  | .tool => if destOk r then .allow else .refuse "destination"
  | .act =>
    if r.dest == "" then .refuse "destination"
    else if !destOk r then .refuse "destination"
    else if !r.confirmed then .refuse "confirm"
    else .allow

theorem send_to_allowed {r : StepReq} (h : decideStep r = .allow) (hk : r.kind = .send) :
    r.provider ∈ r.allowed := by
  unfold decideStep at h; rw [hk] at h; simp only at h
  repeat' split at h
  all_goals simp_all

theorem local_sends_nothing {r : StepReq} (h : decideStep r = .allow) (hk : r.kind = .send) :
    r.level ≠ .onPC := by
  intro hl
  unfold decideStep at h; rw [hk, hl] at h; simp only at h
  repeat' split at h
  all_goals simp_all

theorem masked_only_out {r : StepReq} (h : decideStep r = .allow) (hk : r.kind = .send)
    (hl : r.level = .masked) : r.payloadMasked = true := by
  unfold decideStep at h; rw [hk, hl] at h; simp only at h
  repeat' split at h
  all_goals simp_all

theorem split_needs_route {r : StepReq} (h : decideStep r = .allow) (hk : r.kind = .send)
    (hl : r.level = .split) : r.routeOk = true := by
  unfold decideStep at h; rw [hk, hl] at h; simp only at h
  repeat' split at h
  all_goals simp_all

theorem taint_narrows (dests afterTaint : List String) (d : String)
    (h : d ∈ openDests dests afterTaint true) : d ∈ openDests dests afterTaint false := by
  unfold openDests at *
  simp at h
  exact h.1

private theorem destOk_mem {r : StepReq} (h : destOk r = true) (hd : r.dest ≠ "") : r.dest ∈ r.dests := by
  unfold destOk at h
  simp only [Bool.or_eq_true, beq_iff_eq] at h
  rcases h with h | h
  · exact absurd h hd
  · unfold openDests at h
    split at h
    · simp at h; exact h.1
    · simpa using h

theorem dest_from_person {r : StepReq} (h : decideStep r = .allow) (hd : r.dest ≠ "") : r.dest ∈ r.dests := by
  unfold decideStep at h
  cases hk : r.kind <;> rw [hk] at h <;> simp only at h
  · have : (r.dest != "") = true := by simpa using hd
    split at h
    · simp at h
    · simp [this] at h
  · cases h1 : destOk r
    · rw [h1] at h; simp at h
    · exact destOk_mem h1 hd
  · cases h1 : destOk r
    · simp [h1] at h
    · exact destOk_mem h1 hd

theorem confirm_irreversible {r : StepReq} (h : decideStep r = .allow) (hk : r.kind = .act) :
    r.confirmed = true := by
  unfold decideStep at h; rw [hk] at h; simp only at h
  repeat' split at h
  all_goals simp_all

end Zenos

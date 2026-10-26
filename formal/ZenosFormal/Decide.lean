/-!
# ZENOS decision core

The decisions the root services take, as pure functions. `zenos-decide` (Main.lean) runs exactly these functions;
keyd and guardd call it and follow its answer. The properties these functions guarantee are proved in
`ZenosFormal.Proofs`.

What stays outside the proof (checked by the services before they call the decision, and trusted here):
- cryptography: whether an approval's Ed25519 signature verifies with the officer's enrolled key over the request
  digest (`Approval.sigOk`), whether a grant's digest matches its contents (`Grant.digestOk`), the file's own
  signature and its SHA-256;
- the facts read from root-owned files: the user's clearance, the enrolled officers (the roster), whether the PC is
  stopped, the clock.
-/

namespace Zenos

/-! ## Levels -/

/-- A file level is 1 (Public) to 5 (Specially Designated Secret). -/
def validLevel (l : Nat) : Bool := 1 ≤ l && l ≤ 5

/-- Officers' approvals a level needs to be opened without clearance (`zformat.REQUIRED`). -/
def required : Nat → Nat
  | 1 => 0
  | 2 => 1
  | 3 => 1
  | 4 => 2
  | 5 => 3
  | _ => 0

/-- A clearance read from the administrator's file, kept within 1-5. -/
def clamp (c : Nat) : Nat := max 1 (min 5 c)

/-! ## Approvals -/

/-- One officer's approval as recorded in a request or a grant. `sigOk`: the signature verified with that officer's
    enrolled public key over the request digest (checked by the service). -/
structure Approval where
  approver : String
  sigOk : Bool
  deriving Repr, Inhabited

/-- Each name once. -/
def dedup : List String → List String
  | [] => []
  | x :: xs => if x ∈ dedup xs then dedup xs else x :: dedup xs

/-- An approval counts if its signature verified, its officer is enrolled, and it is not the requester's own. -/
def eligible (roster : List String) (requester : String) (a : Approval) : Bool :=
  a.sigOk && roster.contains a.approver && a.approver != requester

/-- The officers whose approvals count, each once. -/
def approvers (roster : List String) (requester : String) (as : List Approval) : List String :=
  dedup ((as.filter (eligible roster requester)).map (·.approver))

/-! ## Opening a sealed file (keyd) -/

/-- A grant: the officers' signed approval for one user to open one exact file. -/
structure Grant where
  /-- the requester named in the signed contents -/
  requester : String
  /-- the user the grant file was issued to -/
  holder : String
  /-- SHA-256 of the sealed file the approval is for -/
  fileHash : String
  /-- the level the approval covers -/
  level : Nat
  /-- a request kind (release, plan); an access grant has none -/
  kind : Option String
  /-- expiry, seconds since the epoch -/
  expires : Nat
  /-- the stored digest equals the digest of the signed contents (checked by the service) -/
  digestOk : Bool
  approvals : List Approval
  deriving Repr, Inhabited

/-- One request to open a sealed file. -/
structure OpenReq where
  user : String
  clearance : Nat
  level : Nat
  fileHash : String
  now : Nat
  halted : Bool
  roster : List String
  grant : Option Grant
  deriving Repr, Inhabited

inductive Decision where
  | byClearance
  | byGrant
  | refuse (reason : String)
  deriving Repr, Inhabited, DecidableEq

def Decision.allowed : Decision → Bool
  | .refuse _ => false
  | _ => true

/-- The grant is for this user, this exact file, a level at least the file's, has not expired, is an access grant,
    its contents are the ones the officers signed, and enough distinct enrolled officers other than the user signed. -/
def grantOk (o : OpenReq) (g : Grant) : Bool :=
  g.digestOk && g.requester == o.user && g.holder == o.user && g.fileHash == o.fileHash && g.kind.isNone
    && decide (o.level ≤ g.level) && decide (o.now ≤ g.expires)
    && decide (required o.level ≤ (approvers o.roster o.user g.approvals).length)

def decideOpen (o : OpenReq) : Decision :=
  if o.halted then .refuse "halted"
  else if !validLevel o.level then .refuse "level"
  else if o.level ≤ clamp o.clearance then .byClearance
  else match o.grant with
    | some g => if grantOk o g then .byGrant else .refuse "grant"
    | none => .refuse "clearance"

/-! ## Releasing a stop (guardd) -/

inductive Status where
  | pending
  | declined
  | approved
  deriving Repr, Inhabited, DecidableEq

/-- A release request: the officers sign its digest from their own devices. -/
structure Request where
  id : String
  requester : String
  level : Nat
  required : Nat
  status : Status
  approvals : List Approval
  deriving Repr, Inhabited

/-- How many officers a release needs: more than opening the file did (at least 2), but no more than the enrolled
    officers other than the stopped user. With no such officer it is 1 and cannot be met: the PC stays stopped. -/
def releaseRequired (roster : List String) (requester : String) (level : Nat) : Nat :=
  min (max 1 ((dedup roster).filter (· != requester)).length) (max 2 (required level + 1))

inductive Act where
  | approve
  | decline
  deriving Repr, Inhabited, DecidableEq

structure ApproveReq where
  request : Request
  roster : List String
  who : String
  act : Act
  sigOk : Bool
  codeOk : Bool
  deriving Repr, Inhabited

inductive ApproveResult where
  | refused (reason : String)
  | declined
  | added
  deriving Repr, Inhabited, DecidableEq

/-- One officer's answer to a pending release request. -/
def decideApprove (a : ApproveReq) : ApproveResult :=
  if a.request.status ≠ .pending then .refused "decided"
  else if !a.roster.contains a.who then .refused "not enrolled"
  else if !a.sigOk then .refused "signature"
  else match a.act with
    | .decline => .declined
    | .approve =>
      if !a.codeOk then .refused "code"
      else if a.who == a.request.requester then .refused "requester"
      else if a.request.approvals.any (·.approver == a.who) then .refused "already"
      else .added

/-- The stop is released when the request is pending and at least `required` (and at least one) distinct enrolled
    officers other than the stopped user have signed it. -/
def decideRelease (halted : Bool) (r : Request) (roster : List String) : Bool :=
  halted && decide (r.status = .pending) && decide (1 ≤ r.required)
    && decide (r.required ≤ (approvers roster r.requester r.approvals).length)

/-! ## The whole machine over time -/

structure State where
  halted : Bool
  request : Option Request
  deriving Repr, Inhabited

inductive Event where
  /-- an anomaly: guardd stops the PC and files this release request -/
  | anomaly (r : Request)
  /-- an officer answers the current release request -/
  | answer (who : String) (act : Act) (sigOk codeOk : Bool) (roster : List String)
  /-- the enforcement loop checks the current release request -/
  | tick (roster : List String)
  /-- a user asks keyd to open a sealed file (the state decides whether the PC is stopped) -/
  | openFile (o : OpenReq)
  deriving Repr, Inhabited

/-- One event. The second component is keyd's answer for `openFile`. -/
def step (s : State) : Event → State × Option Decision
  | .anomaly r =>
    if s.halted then (s, none)
    else ({ halted := true, request := some { r with status := .pending, approvals := [] } }, none)
  | .answer who act sigOk codeOk roster =>
    match s.halted, s.request with
    | true, some r =>
      match decideApprove { request := r, roster, who, act, sigOk, codeOk } with
      | .added => ({ s with request := some { r with approvals := r.approvals ++ [{ approver := who, sigOk }] } }, none)
      | .declined => ({ s with request := some { r with approvals := [] } }, none)   -- a new request goes out
      | .refused _ => (s, none)
    | _, _ => (s, none)
  | .tick roster =>
    match s.halted, s.request with
    | true, some r => if decideRelease true r roster then ({ halted := false, request := none }, none) else (s, none)
    | _, _ => (s, none)
  | .openFile o => (s, some (decideOpen { o with halted := s.halted }))

/-- Every step of a run: the state before, the event, keyd's answer. -/
def runLog : State → List Event → List (State × Event × Option Decision)
  | _, [] => []
  | s, e :: es => (s, e, (step s e).2) :: runLog (step s e).1 es

end Zenos

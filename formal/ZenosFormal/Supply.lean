import ZenosFormal.Decide
import ZenosFormal.Proofs

/-!
# What a PC lets in: the release ledger

Before apt installs a package, ZENOS asks the audit nodes listed on the PC what the release ledger says about that
exact file (its SHA-256). A package goes in only when

* its SHA-256 is the one in the release record (checked by the PC: `hashOk`);
* more than half of the configured audit nodes answered, each with its own signature, with that same record;
* the record carries signatures from at least `required` (and at least one) distinct release officers enrolled on
  the PC, other keys not counting;
* no revocation for it, signed by enough officers, is held by any node (`revoked`, checked by the PC);
* the record's rollout has reached this PC's ring (`ringOpen ≤ now`).

Proved:
* `install_sound`: an installed package satisfied all of the above.
* `one_node_not_enough`: with two or more audit nodes configured, one node vouching (a node taken over, or a fake
  one) never lets a package in.
* `one_key_not_enough`: when two or more officers' signatures are required, one release key (stolen, or held by a
  central service) never lets a package in.
* `revoked_refused`: an agreed revocation keeps a package out whatever else holds.
-/

namespace Zenos

/-- One audit node's signed answer about a package file, as the PC checked it. -/
structure Vote where
  node : String
  /-- the answer's signature verifies with that node's key configured on the PC -/
  sigOk : Bool
  /-- the digest of the release record the node holds for this file ("" when it holds none) -/
  record : String
  deriving Repr, Inhabited

structure InstallReq where
  /-- the audit nodes configured on the PC -/
  nodes : List String
  votes : List Vote
  /-- the release record the PC is about to rely on -/
  record : String
  /-- the file's SHA-256 equals the one in that record -/
  hashOk : Bool
  /-- release officers whose signature over that record verified with keys enrolled on the PC -/
  signers : List String
  officers : List String
  required : Nat
  /-- a revocation of this file, signed by enough officers, held by any node -/
  revoked : Bool
  ringOpen : Nat
  now : Nat
  deriving Repr, Inhabited

/-- Configured nodes, each counted once, that answered with a good signature for this very record. -/
def agreeing (r : InstallReq) : List String :=
  dedup ((r.votes.filter (fun v => v.sigOk && v.record == r.record && r.record != "" && r.nodes.contains v.node)).map (·.node))

/-- Enrolled officers, each counted once, who signed the record. -/
def countedSigners (r : InstallReq) : List String :=
  dedup (r.signers.filter (fun s => r.officers.contains s))

inductive InstallDecision where
  | allow
  | refuse (reason : String)
  deriving Repr, Inhabited, DecidableEq

def decideInstall (r : InstallReq) : InstallDecision :=
  if r.revoked then .refuse "revoked"
  else if !r.hashOk then .refuse "hash"
  else if !(decide ((dedup r.nodes).length < 2 * (agreeing r).length)) then .refuse "ledger"
  else if r.required = 0 then .refuse "policy"
  else if (countedSigners r).length < r.required then .refuse "signatures"
  else if r.now < r.ringOpen then .refuse "ring"
  else .allow

theorem install_sound {r : InstallReq} (h : decideInstall r = .allow) :
    r.revoked = false ∧ r.hashOk = true ∧ (dedup r.nodes).length < 2 * (agreeing r).length ∧
    1 ≤ r.required ∧ r.required ≤ (countedSigners r).length ∧ r.ringOpen ≤ r.now := by
  unfold decideInstall at h
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
  simp only [Bool.not_eq_true, Bool.not_eq_false', decide_eq_true_eq, Nat.not_lt] at h1 h2 h3 h4 h5 h6
  exact ⟨h1, h2, h3, Nat.pos_of_ne_zero h4, h5, h6⟩

theorem agreeing_sub {r : InstallReq} {n : String} (h : n ∈ agreeing r) : n ∈ r.nodes := by
  unfold agreeing at h
  rw [mem_dedup] at h
  obtain ⟨v, hv, rfl⟩ := List.mem_map.mp h
  have := (List.mem_filter.mp hv).2
  simp only [Bool.and_eq_true, List.contains_iff_mem] at this
  exact this.2

/-- With two or more distinct audit nodes configured, a single node never lets a package in. -/
theorem one_node_not_enough {r : InstallReq} (hn : 2 ≤ (dedup r.nodes).length) (ha : (agreeing r).length ≤ 1) :
    decideInstall r ≠ .allow := by
  intro h
  have := (install_sound h).2.2.1
  omega

/-- When two or more officers must sign, one key never lets a package in. -/
theorem one_key_not_enough {r : InstallReq} (hq : 2 ≤ r.required) (hs : (countedSigners r).length ≤ 1) :
    decideInstall r ≠ .allow := by
  intro h
  have := (install_sound h).2.2.2.2.1
  omega

theorem revoked_refused {r : InstallReq} (h : r.revoked = true) : decideInstall r = .refuse "revoked" := by
  simp [decideInstall, h]

end Zenos

/-! ## Who system services may talk to -/

namespace Zenos

/-- One outbound connection, as the network sentinel sees its first byte. -/
structure SysEgress where
  /-- sent by a system account (root or a service account), not by a person's session -/
  system : Bool
  /-- the destination is one of the names in the system list (resolved), the audit nodes, the key service,
      the DNS servers, or an allowed network -/
  listed : Bool
  loopback : Bool
  /-- "enforce" (cut) rather than "monitor" (record) -/
  enforce : Bool
  deriving Repr, Inhabited

/-- Cut the destination? -/
def decideSysEgress (e : SysEgress) : Bool := e.enforce && e.system && !e.listed && !e.loopback

theorem sysegress_cut_only_unlisted {e : SysEgress} (h : decideSysEgress e = true) :
    e.enforce = true ∧ e.system = true ∧ e.listed = false ∧ e.loopback = false := by
  simp only [decideSysEgress, Bool.and_eq_true, Bool.not_eq_true'] at h
  exact ⟨h.1.1.1, h.1.1.2, h.1.2, h.2⟩

/-- A listed destination is never cut, and a person's own programs are never cut by this rule. -/
theorem sysegress_listed_kept {e : SysEgress} (h : e.listed = true ∨ e.system = false) : decideSysEgress e = false := by
  rcases h with h | h <;> simp [decideSysEgress, h]

end Zenos

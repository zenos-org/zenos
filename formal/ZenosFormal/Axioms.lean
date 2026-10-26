import ZenosFormal.Proofs

/-! The main theorems rest only on Lean's standard axioms: no `sorry`, no axiom of our own. The build fails if
    that changes (`#guard_msgs` on the kernel's own report). -/

/-- info: 'Zenos.open_sound' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.open_sound

/-- info: 'Zenos.grant_needs_officer' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.grant_needs_officer

/-- info: 'Zenos.release_sound' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.release_sound

/-- info: 'Zenos.run_open_not_halted' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.run_open_not_halted

/-- info: 'Zenos.run_release' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.run_release

/-- info: 'Zenos.approvers_not_requester' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.approvers_not_requester

/-- info: 'Zenos.approvers_nodup' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.approvers_nodup

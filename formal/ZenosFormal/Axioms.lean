import ZenosFormal.Proofs
import ZenosFormal.Flow
import ZenosFormal.Ledger
import ZenosFormal.Egress
import ZenosFormal.Protocol
import ZenosFormal.Cred
import ZenosFormal.KeyService
import ZenosFormal.Supply

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

/-- info: 'Zenos.flow_within_cap' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.flow_within_cap

/-- info: 'Zenos.no_write_down' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.no_write_down

/-- info: 'Zenos.l3_stays_inside' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.l3_stays_inside

/-- info: 'Zenos.l4_ministry_ai_only' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.l4_ministry_ai_only

/-- info: 'Zenos.l5_stays' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.l5_stays

/-- info: 'Zenos.carry_monotone' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.carry_monotone

/-- info: 'Zenos.chainCheck_ok' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.chainCheck_ok

/-- info: 'Zenos.accept_extends' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.accept_extends

/-- info: 'Zenos.history_unique' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.history_unique

/-- info: 'Zenos.send_sound' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.send_sound

/-- info: 'Zenos.egress_cut_iff' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.egress_cut_iff

/-- info: 'Zenos.egress_cut_stays' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.egress_cut_stays

/-- info: 'Zenos.prune_prune' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.prune_prune

/-- info: 'Zenos.approve_ne_decline' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.approve_ne_decline

/-- info: 'Zenos.release_counts_only_this_stop' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.release_counts_only_this_stop

/-- info: 'Zenos.counted_was_signed_for' does not depend on any axioms -/
#guard_msgs in #print axioms Zenos.counted_was_signed_for

/-- info: 'Zenos.cred_sound' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.cred_sound

/-- info: 'Zenos.cred_once' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.cred_once

/-- info: 'Zenos.ask_bounded' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.ask_bounded

/-- info: 'Zenos.key_sound' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.key_sound

/-- info: 'Zenos.key_open_sound' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.key_open_sound

/-- info: 'Zenos.key_presence' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.key_presence

/-- info: 'Zenos.key_silent_refused' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.key_silent_refused

/-- info: 'Zenos.key_unhealthy_refused' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.key_unhealthy_refused

/-- info: 'Zenos.key_halted_refused' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.key_halted_refused

/-- info: 'Zenos.key_rate_bounded' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.key_rate_bounded

/-- info: 'Zenos.install_sound' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.install_sound

/-- info: 'Zenos.one_node_not_enough' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.one_node_not_enough

/-- info: 'Zenos.one_key_not_enough' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in #print axioms Zenos.one_key_not_enough

/-- info: 'Zenos.revoked_refused' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.revoked_refused

/-- info: 'Zenos.sysegress_cut_only_unlisted' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.sysegress_cut_only_unlisted

/-- info: 'Zenos.sysegress_listed_kept' depends on axioms: [propext] -/
#guard_msgs in #print axioms Zenos.sysegress_listed_kept

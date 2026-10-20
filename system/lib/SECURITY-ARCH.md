# ZENOS security architecture (single source of truth)

5 layers. Each concern has ONE owning module. Do not duplicate crypto, ledger, or firewall logic elsewhere.

## Module ownership
- Crypto (fragment + per-fragment keys): /usr/local/lib/zenos/zfrag.py  (zenos.py delegates; no AES elsewhere)
- Tamper-evident ledger (hash chain): /usr/local/lib/zenos/zledger.py  (audit() delegates)
- Sensor + reflex + agent: /usr/local/sbin/zenos_netsentinel.py (+ zenos-netsense.bt)
- Security monitor feed: /usr/sbin/zenos_secstat.py (zenos-secstat.service). Read-only: counts ZENOS_IN drops (and the rate-limited "ZENOS_IN_DROP " log line for source/port), PAM sign-in failures and sentinel incidents; writes /run/zenos/secstat.json for the System Monitor. Changes no rule.
- Open-time network cut (L4+): /usr/local/sbin/zopenguard.py
- Sensor liveness (dead-man's switch): /usr/local/sbin/zheartbeat.py
- Inbound firewall: /usr/local/sbin/zenos-firewall

## iptables chain map (three separate chains, never overlap)
- ZENOS_IN   : inbound. Owner: zenos-firewall. lo RETURN; ESTABLISHED,RELATED RETURN; new non-lo DROP.
- ZENOS_OUT  : egress reflex. Owner: netsentinel. Per-incident DROP of a destination.
- ZENOS_OPEN : open-time cut. Owner: zopenguard. lo RETURN; ESTABLISHED,RELATED RETURN; else DROP.
Rule: each chain is inserted/removed only by its owner. No module touches another's chain.

## Open sequence (fixed order)
fetch keys (ledger: key-issue) -> cut network (L4+) -> decrypt + view -> re-seal + wipe plaintext -> restore network -> ledger: file-close

## Deliberate interactions
- During an L4+ open window egress is cut, so the agent's external-model call is unavailable; the
  agent falls back to local policy. This is fail-closed and intended, not a bug.
- firewall-watch (netsentinel) re-arms ZENOS_IN only; it does not touch ZENOS_OPEN/ZENOS_OUT.

## Escape routes during use (only two)
- network -> sensor/reflex/agent + open-time cut
- screen  -> clipboard disabled; software screenshot limited; watermark for attribution; camera = physical + watermark

## Attribution chain
key-issue + file-open/close recorded per actor+device in zledger, replicated across grid nodes.
Leak -> ledger names who had access; watermark names whose copy leaked.

## Ledger tiers (edit history: how much to record, where)
Two tiers, so routine edits don't bloat the consortium or the reviewer.
- Local tier (cheap, high-frequency): every save/edit appended to a light per-file hash chain, kept on
  the local grid nodes (fragmented + replicated). Tamper-evident, but a compromised node can rewrite
  its own copy, so this tier is NOT the trust root.
- Consortium tier (authoritative, low-frequency): only the critical events, plus a periodic Merkle-root
  anchor of the local batch. The anchor is the trust root: comparing it against the local chain detects
  any local rewrite. Same pattern as blockchain L2->L1 anchoring and AWS CloudTrail hourly digests.

Recorded individually on the consortium (infrequent, attribution-critical):
  file-open, file-close, key-issue, access-grant, anomaly, agent-decision, external-send.
Batched then anchored (frequent): ordinary edits/saves.
Anchor cadence (default): on file-close, and every N edits or every T minutes, whichever first.

## Cost
Permissioned consortium (ministry nodes) has NO per-transaction gas/fee. Cost = storage + replication +
human review. One record ~ a few hundred bytes; a permissioned chain sustains thousands of tx/sec, so
throughput is not the constraint. Batching+anchoring cuts on-chain rows by ~100x (100 edits -> 1 anchor
row), keeping both storage and the reviewer's view small. Net: negligible cost at government scale.

## Durability (survive sudden shutdown)
Change-point capture is integrated at the viewer/OS level (automatic, like autosave; not user-triggered).
- Local tier is a write-ahead log: fsync to disk (and to local grid nodes) BEFORE the edit is acked, so a
  power loss cannot lose an acknowledged change.
- Consortium anchor is asynchronous; an entry is marked "anchored" only after the consortium confirms receipt.
- Boot reconciler: on startup, any local entries not yet anchored are re-sent to the consortium. Idempotent
  via the entry hash, so re-sending after a crash creates no duplicate.
- Result: a sudden shutdown loses at most an edit the user never durably saved (same as any autosave gap);
  everything acknowledged survives and the consortium catches up after reboot.
Pattern: database write-ahead logging + CloudTrail-style local-then-digest; neither loses committed records.

## New owned modules (send-check + two-tier anchor)
- Pre-send gate: /usr/local/lib/zenos/zsendcheck.py  (plaintext/unsealed/tampered -> block; over the huge
  line -> allowed only with an approved 申請; every decision logged to the ledger)
- Two-tier anchor: /usr/local/lib/zenos/zanchor.py  (local fine-grained chain + periodic Merkle-root anchor
  to the consortium)
Detection split (verified): per-record hash (zledger.verify) catches a single edited record; the consortium
Merkle anchor (zanchor.verify_anchor) catches a full self-consistent re-chain of the local tier.

## Security Note (endpoint audit + double-check)
Module: /usr/local/lib/zenos/zsecnote.py. Periodically, per endpoint: anchor new local edits, then run the
hard checks and emit a verdict (trusted | SUSPECT) logged to the consortium ledger.
- Soft (management metadata, NOT a security root): hostname, kernel, connected devices + models. A
  compromised endpoint can forge these, so they never decide trust on their own.
- Hard (trust root): local ledger integrity, consortium ledger integrity, local<->consortium reconciliation
  (zanchor.verify_anchor), sensor liveness. The reconciliation is the double-check: a kernel-compromised
  endpoint can rebuild a self-consistent local chain but cannot match the anchors it already committed to
  the consortium, so the mismatch exposes the modified OS. Attestation (measured boot) strengthens trust in
  the self-reported inventory but is not yet implemented (target B).
Verified: stealth tamper (self-consistent local rewrite) -> SUSPECT(local-vs-consortium-mismatch).
Remaining wiring: run the audit on a resident timer across endpoints; call zsendcheck at each transfer point.

## Machine health (watch the computer, not the person)
Folded into zsecnote. Framing: resource/behavioral signals are device monitoring, not surveillance of staff.
Collected: GPU utilization + temperature (nvidia-smi), CPU load ratio (loadavg). On real endpoints also add
CPU temperature + fan (lm-sensors/IPMI; not available under WSL).
Takeover signatures flagged: gpu-busy-while-deskwork, gpu-overheat, cpu-sustained-high.
Separation (important): verdict = hard tamper checks (trusted|SUSPECT); attention = soft health alerts that
raise attention / feed the AI audit, never by themselves a tamper verdict. Thresholds tunable; idle deskwork
GPU baseline is ~0%. Verified on real + synthetic readings.

## Machine health: network throughput
Added to zsecnote.health via net_rates() reading /proc/net/dev twice over an interval (Task-Manager
"Network" equivalent): whole-machine tx/rx bytes/sec across non-lo interfaces. Alert
"sustained-outbound-high" when deskwork tx exceeds NET_TX_HI (default 5 MB/s, tunable). This is a coarse
whole-machine corroboration independent of the per-connection eBPF sensor. Verified: idle=0 (no false
positive), live burst measured ~8.3 MB/s, synthetic high -> alert.

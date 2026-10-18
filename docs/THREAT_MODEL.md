# ZENOS threat model (Developer Preview)

This document says what ZENOS is meant to protect, against whom, and — most importantly for a preview — which
protections are real today and which are only demonstrated. It is updated with every release.

## Assets

1. The contents of classified files (levels L1–L5).
2. The keys that decrypt them.
3. The audit trail: who opened, moved or sent what, on which device, when.
4. Availability: files must survive the loss of a building or a node.

## Adversaries considered

- **A careless or coerced insider** who copies files to USB, uploads them, or opens many files at once.
- **A targeted employee** pressured by a foreign service: ZENOS aims to make "the person with access" a poor
  target, because access is per request, recorded, and multi-person approved.
- **Malware on an endpoint** that tries to exfiltrate data or rewrite its own audit trail.
- **A compromised storage node or relay** (sees only ciphertext and fragments).

Out of scope for now: physical attacks on running hardware, hardware implants, and side channels.

## Trust boundaries (target design)

```
user session  ──(cannot touch)──▶  root services: sentinel, firewall, ledger, key agent
key agent     ──(keys never leave)─▶  TPM / FIDO2 device
approvals     ──(signed on)──────▶  each approver's own device
audit log     ──(shipped to)─────▶  consortium nodes outside the endpoint
```

## What is real today and what is not

| Protection | Today | Gap to close |
|---|---|---|
| File sealing (AES-256-GCM, fragmented, signed header) | Real cryptography | Level keys and fragment keys are files on the same disk (mode 600), not in a TPM. |
| Plaintext only in RAM while open | Implemented for viewers | Applications could still write copies; needs mandatory access control (SELinux MLS). |
| Approval-based access | Implemented, signatures verified | All approver keys are on the same machine as the requester, so approval is a demonstration only. |
| Anomaly stop | Detects bulk reads and USB transfers; locks the screen | The stop state (`halt.json`) is writable by the user and the sentinel runs as the user, so a user process can lift a stop. inotify gives no process id. Must move to a root service with fanotify. |
| Network sentinel / firewall | Root service with an eBPF (bpftrace) sensor and iptables chains | Not reviewed; outbound policy is per incident. |
| Tamper-evident ledger | Hash chain + Merkle anchors, verified to detect a self-consistent local rewrite | Consortium tier runs on the same host in the preview. |
| Distributed storage | Fragments replicated to local test nodes | Nodes are local directories; no network transport or node authentication yet. |
| Terminal disabled | Hidden from the UI | Not enforced; a determined user can still start a shell. |
| Messenger E2E | libsignal (Signal protocol) | Relay authentication of devices is not device-bound yet. Test deployments used a Cloudflare quick tunnel, which is for testing only. |
| Level-gated AI | Policy in the launcher | No enforcement at the network or process level yet. |

## Known weaknesses in dependencies

- `xlsx` 0.18.5 (SheetJS, npm) has published vulnerabilities (prototype pollution, ReDoS) that are fixed only in
  builds distributed outside npm. To be replaced or upgraded before any production use.

## Principle

Every claim in the README must be backed by this table. A row moves to "real" only together with a test that
demonstrates it.

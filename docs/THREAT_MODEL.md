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
| Approval-based access | Implemented, signatures verified against officer public keys installed by the administrator (`/etc/zenos/approvers`, root-owned). Release of a stopped PC is signed on the officers' own devices. ZENOS Messages makes an Ed25519 key in the officer's browser (WebCrypto, non-extractable, kept in IndexedDB); the administrator enrolls its public key with `zenos_guardd.py --enroll NAME KEY`. The request reaches the officer end-to-end encrypted, the officer's device recomputes the digest from what it shows and signs it, and the guard verifies the signature against the enrolled key and its own copy of the request. The match code is never sent; the officer reads it off the stopped screen. Tested end to end (wrong code refused, decline renews the request, an old key is refused, three signatures release). | Key issuance approvals still use the demo keys on the same machine; the browser key is software-backed (not yet a FIDO2/secure-element key); an officer who loses the device must be re-enrolled. |
| Anomaly stop | Installed system: `zenos-guardd` runs as root, sees every open of a protected file and every write to the exit with the process id (fanotify), keeps the stop state, release requests and quarantine root-owned, freezes every process of the user (anything new is frozen within a second) and shows the stop notice as root. Release needs the required number of valid officer signatures. Tested end to end: the user cannot write the stop state; a forged signature is refused; three valid signatures release the PC and cancel the operation. | Moves into the exit are seen by inotify (no process id). The display server, the window manager and the messenger keep running during a stop. The development layout (`~/.local/share/zenos`) still uses the old user-level watcher. |
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

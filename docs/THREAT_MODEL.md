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
| File sealing (AES-256-GCM, fragmented, signed header) | Real cryptography. Installed system: the level keys, fragment keys and the signing key belong to root (`zenos-keyd`, `/var/lib/zenos/keys`); every seal and unseal goes through it. It hands out plaintext only up to the user's clearance (set by the administrator in `/etc/zenos/clearance`) or for one exact file with a grant the officers signed (verified against the enrolled keys), and records every unseal and refusal in the root ledger, which is shipped off the PC. Tested: the user cannot read the key files; an L4 file is refused at clearance L2; an officer-approved grant (signed in the officer's browser) opens exactly that file. | The keys are root-owned files, not yet in a TPM; root on the PC can read them. Keys are per PC, so a sealed file opens only on the PC that sealed it (no shared key service yet). Files sealed before the agent was installed (user-held keys) no longer verify. In the development layout keys are still in the user's home. |
| Plaintext only in RAM while open | Implemented for viewers and for the ZENOS office apps (a sealed .docx/.xlsx/.pptx is edited from a RAM copy, saved back only to it and sealed again; web storage is ephemeral) | Applications could still write copies; needs mandatory access control (SELinux MLS). |
| Copy and screen capture of L3+ | Sealed files of L3 and above: nothing can be copied out of the office apps (copy, cut, drag and the clipboard API are refused; pasting in works). Installed system: while any L3+ sealed file is on the user's screen, the guard refuses screen-capture programs (Spectacle, scrot, flameshot, OBS, …). Tested: scrot works with nothing or an L2 file open, is refused with an L4 file open, works again after it closes; Ctrl+C in an L4 sheet leaves the clipboard unchanged. Copy and paste between sealed windows works through a level clipboard in the key agent (RAM only, 30 minutes): an L4 copy pastes into L4 and higher windows, never into lower ones or into other programs, and every copy is logged with its level and length (tested: L4 to L4 works, L4 to L3 pastes the ordinary clipboard instead, the X11 clipboard stays untouched, a later copy in an ordinary program takes over). Selected text in an L3+ window is emptied out of the X11 PRIMARY selection at once, so a middle click elsewhere pastes nothing (tested: an L4 window leaves PRIMARY empty, an L2 window keeps it). Sealed L3+ text opens in a viewer without selection, copy or drag (tested: clipboard and the X11 primary selection unchanged). The image, video and PDF apps refuse copy, drag and the right-click menu for L3+ (tested in the PDF app: Ctrl+A, Ctrl+C on an L4 PDF left the clipboard unchanged). | The level clipboard lives in the key agent's memory for the user's account; another program running as the same user could ask the agent for it. A program the guard does not know, a camera pointed at the screen, or a user-written X11 capture script are not stopped. |
| Printing sealed files | The office apps put a red banner with the level, file name, user and time on every printed page of a sealed file. Files above `print_max_level` (default 3, `/etc/zenos/policy.conf`) cannot be printed from the PC; every print and refused print is written to the audit log. Tested: window.print() in an L4 sealed window shows the refusal and nothing is printed. | A photo of the screen, or printing from a program outside the office apps, is not covered. The banner is a deterrent and a trace, not a protection. |
| Approval-based access | Implemented, signatures verified against officer public keys installed by the administrator (`/etc/zenos/approvers`, root-owned). Release of a stopped PC, access requests (opening above your level) and pre-filed operations are all signed on the officers' own devices; once officers are enrolled, only their enrolled keys count (a key the user makes up is ignored — tested). ZENOS Messages makes an Ed25519 key in the officer's browser (WebCrypto, non-extractable, kept in IndexedDB); the administrator enrolls its public key with `zenos_guardd.py --enroll NAME KEY`. The request reaches the officer end-to-end encrypted, the officer's device recomputes the digest from what it shows and signs it, and the guard verifies the signature against the enrolled key and its own copy of the request. The match code is never sent; the officer reads it off the stopped screen. Tested end to end (wrong code refused, decline renews the request, an old key is refused, three signatures release). | The demo approval page (keys on the same machine) still exists for development without enrolled officers; the browser key is software-backed (not yet a FIDO2/secure-element key); an officer who loses the device must be re-enrolled. |
| Anomaly stop | Installed system: `zenos-guardd` runs as root, sees every open of a protected file and every write to the exit with the process id (fanotify), keeps the stop state, release requests and quarantine root-owned, freezes every process of the user (anything new is frozen within a second) and shows the stop notice as root. Release needs the required number of valid officer signatures. Tested end to end: the user cannot write the stop state; a forged signature is refused; three valid signatures release the PC and cancel the operation. | Moves into the exit are seen by inotify (no process id). The display server, the window manager and the messenger keep running during a stop. The development layout (`~/.local/share/zenos`) still uses the old user-level watcher. |
| Network sentinel / firewall | Root service with an eBPF (bpftrace) sensor and iptables chains | Not reviewed; outbound policy is per incident. |
| Tamper-evident ledger | Hash chain + Merkle anchors, verified to detect a self-consistent local rewrite. Installed system: `zenos-auditship` sends the guard's ledger and every user's ledger to one or more audit nodes (`zenos_auditnode.py`, run on a machine the PC users do not control) every 30 seconds, in batches signed with the PC's root-only audit key. A node accepts only records that continue the chain it holds; a changed past record, a gap, a broken link or a bad signature is refused and alerted, and every accepted batch gets a receipt signed by the node. Tested: unit test (a PC rebuilds a valid local chain without the "halt" record; the node keeps the original and raises "history-rewritten") and end to end on the test system. | A record can still be changed in the seconds before it is shipped, and a PC kept offline ships nothing (the node reports it as silent after 10 minutes, but cannot see what happened meanwhile). User ledgers are writable by that user. The node's alerts are a file, not yet a dashboard or a notification. The multi-party consortium ledger is still one node per ministry, not replicated between organisations. |
| Distributed storage | Fragments replicated to local test nodes | Nodes are local directories; no network transport or node authentication yet. |
| Terminal disabled | Hidden from the UI. Installed system: `zenos-guardd` answers every start of a terminal program (konsole, xterm, gnome-terminal, kitty, …; fanotify exec permission) and refuses it for the desktop user; root and other accounts are allowed. Tested: the user gets "Operation not permitted", root starts it, other programs are unaffected. Policy `terminal = allowed` in `/etc/zenos/policy.conf` turns it off. | Raises the bar only: a copied terminal binary, an interpreter (python3) or KRunner's command mode still give a shell. Closing that needs `noexec` home/tmp mounts and SELinux confinement of the user. |
| Messenger E2E | libsignal (Signal protocol) | Relay authentication of devices is not device-bound yet. Test deployments used a Cloudflare quick tunnel, which is for testing only. |
| Level-gated AI | Policy in the launcher | No enforcement at the network or process level yet. |

## Known weaknesses in dependencies

- `xlsx` (SheetJS) is no longer published on npm; the npm copy (0.18.5) has known vulnerabilities (prototype
  pollution CVE-2023-30533, ReDoS CVE-2024-22363). ZENOS uses 0.20.3 from SheetJS's own CDN, pinned in
  `package-lock.json` by its sha512 integrity, so a changed tarball fails the build. The CDN is a single source:
  watch it for new releases, since `npm audit` cannot see it.
- `mammoth` (Documents, .docx import) pulls `argparse` 1.x → `sprintf-js`, flagged moderate (GHSA-hp3w-g68c-fv3c).
  Both belong to mammoth's command-line tool and are not reached from the browser bundle; the only "fix" npm
  offers is a downgrade to a 2016 mammoth, so it is left until mammoth updates.

## Principle

Every claim in the README must be backed by this table. A row moves to "real" only together with a test that
demonstrates it.

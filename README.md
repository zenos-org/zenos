# ZENOS

ZENOS is a desktop operating system for handling classified information at work, built so that ordinary staff
can use it the way they use any computer today. Every file carries a security level. Opening, moving and sending
files is governed by that level, key issuance goes through an approval request, and anything that looks like a
leak stops the machine until responsible officers release it from their own devices.

> **Status: Developer Preview (proof of concept).** ZENOS is not yet safe for real classified data.
> Several protections are demonstrations that run with ordinary user privileges. Read
> [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) before you evaluate it, and do not describe it as secure.

## What it does

| Area | What exists today | Status |
|---|---|---|
| Levelled, sealed files | Files saved into a level folder (L1–L5) are encrypted into `.zen` with the level in a signed header; plaintext is only ever opened in RAM (`/dev/shm`). | Working PoC |
| Approval-based key issuance | Opening above your level files a request; the required number of approvers grows with the level; approvals are signed with each approver's key. | PoC — approver keys still live on the same machine |
| Anomaly stop | Bulk reads, transfers to removable media and unusual egress freeze the session and lock the screen; release needs several officers. | PoC — enforcement runs as the user |
| Tamper-evident ledger | Hash-chained local log, anchored to a consortium tier with Merkle roots. | PoC (single host) |
| Distributed storage | Sealed files are fragmented and replicated across storage nodes. | PoC (local test nodes) |
| Level-gated AI | Which AI may touch a file depends on its level (external AI hidden at L4+). | UI and policy only |
| Messenger | End-to-end encrypted messages (Signal protocol via libsignal), channels, calls (LiveKit, self-hostable). | Working PoC |
| Apps | Browser (WebKitGTK, tabs, bookmarks), Documents, Sheets, Slides, PDF, Images, Video, file picker. | Working |

Design principles: staff should not need training (Windows-like layout, familiar controls); nothing depends on a
single vendor; the browser engine is WebKitGTK, not Chromium.

## Repository layout

```
core/         ZENOS core: sealing, approvals, sentinel, lock screen, shared app shell, file picker, browser
  bin/        Python modules and launchers
  shell/      HTML chrome for the browser, popovers, bookmark manager, file picker
  icons/
apps/         Documents, Sheets, Slides (Vite + TypeScript), PDF, Images, Video
messenger/    ZENOS Messages: client, relay, web UI, calls
system/       root services: network sentinel, firewall, ledger, fragment crypto, heartbeat (sbin/, lib/, systemd/)
desktop/      KDE Plasma integration: launcher and level indicator plasmoids, .desktop files, session start
third_party/  Modified KDE plasmoids (kept under their original GPL/LGPL licenses)
docs/         Threat model and architecture
```

## Running it

Today ZENOS is developed as a Debian 13 system with KDE Plasma 6 (X11). The development machine runs it inside
WSL2, which is a convenience for development only — ZENOS itself does not depend on Windows. An installable
image for ordinary PCs is the next milestone, and until then setup is manual and undocumented. If you want to try
it, open an issue and we will help.

Main dependencies: Python 3.13, PyGObject with GTK 3 and WebKit2GTK 4.1, GStreamer, `cryptography`, OpenCV
(headless) and NumPy, Node.js (messenger and office apps), KDE Plasma 6, fcitx5 with Anthy, TigerVNC (for remote
desktop during development).

## Roadmap

1. **Foundations**: one repository, secrets removed, licences documented.
2. **Installable OS**: an ISO for existing PCs, packaged components, signed updates. WSL stays as a trial image.
3. **Real enforcement**: sentinel as a root service with fanotify, keys in TPM and FIDO2 devices, approvals on
   approvers' own devices, signed audit log shipped off the machine, networked storage nodes and a multi-party
   consortium ledger, full-disk encryption unlocked by fingerprint + TPM. Enforcement will build on existing
   Linux security (SELinux multi-level security, TPM) instead of reinventing it.
4. **Everyday apps**: Files, Settings, Calendar, notifications, printing with level watermarks, cross-level
   clipboard and screenshot control, Office format compatibility.
5. **External security audit** before any claim of production readiness.

Editions (Government, Academy, Creator, Educational, Hobby) will be configurations of one shared core.

## License

ZENOS is licensed under the [Apache License 2.0](LICENSE). The messenger (`messenger/`) links libsignal and is
therefore licensed under the [AGPL-3.0](messenger/LICENSE). Third-party components keep their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Security

Please report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

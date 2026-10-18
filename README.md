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
| Anomaly stop | Bulk reads, transfers to removable media and unusual egress freeze the session and lock the screen; release needs several officers' signatures. | Enforced by a root service (installed system); officer keys still demo |
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

ZENOS is a Debian 13 ("trixie") system with a KDE Plasma 6 X11 session. It does not depend on Windows.

**Install on an existing Debian 13 system**

```
packaging/build-deb.sh                     # -> build/zenos_<version>_amd64.deb
sudo apt install ./build/zenos_*_amd64.deb
```

Users created after installation get the ZENOS desktop (security folders, level bar, launcher, dark theme,
screen lock). Log in to the "Plasma (X11)" session.

**Build a live / installer image for ordinary PCs**

```
sudo apt install live-build
sudo packaging/iso/build-iso.sh build/zenos_*_amd64.deb   # -> build/iso/zenos-amd64.hybrid.iso
```

The image boots as a live session and installs with Calamares.

Calls use a self-hosted LiveKit server (pinned release, checksum-verified at build time). Each user gets their own
keys at first login; nothing secret is shipped in the package.

The development machine runs ZENOS inside WSL2 for convenience; `dev/` holds the pieces that only make sense there
(VNC desktop service, input-method autostart for WSLg).

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

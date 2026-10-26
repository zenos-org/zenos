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
| Approval-based key issuance | Opening above your level files a request; the required number of approvers grows with the level; approvals are signed with each approver's key. | Officers sign on their own devices (ZENOS Messages); demo keys only without enrolled officers |
| Anomaly stop | Bulk reads, transfers to removable media and unusual egress freeze the session and lock the screen; release needs several officers' signatures. | Enforced by a root service (installed system); officers sign the release on their own devices (ZENOS Messages) |
| Tamper-evident ledger | Hash-chained local log, anchored with Merkle roots and shipped to audit nodes off the PC, which refuse rewritten history. | Working (installed system); one node per ministry, not yet a multi-party consortium |
| Distributed storage | Sealed files are fragmented and replicated across storage nodes. | PoC (local test nodes) |
| Level-gated AI | Which AI may touch a file depends on its level (external AI hidden at L4+). | UI and policy only |
| Messenger | End-to-end encrypted messages (Signal protocol via libsignal), channels, calls (LiveKit, self-hostable). | Working PoC |
| Apps | Browser (WebKitGTK, tabs, bookmarks), Documents, Sheets, Slides, PDF, Images, Video, file picker. | Working |

Design principles: staff should not need training (Windows-like layout, familiar controls); nothing depends on a
single vendor; the browser engine is WebKitGTK, not Chromium.

## Repository layout

```
core/         desktop side: sealed files and approvals (zenos.py), browser, app shell, file picker, lock screen
apps/         Documents, Sheets, Slides (Vite + TypeScript), PDF, Images, Video; apps/common: their local server
messenger/    ZENOS Messages: client, relay, web UI, calls (AGPL-3.0)
desktop/      KDE Plasma integration: launcher, level indicator and monitor plasmoids, .desktop files
system/       root services (sbin/, systemd/) and the shared library installed to /usr/lib/zenos (lib/)
storage/      storage grid nodes (erasure code, certificates, repair)
packaging/    the zenos and zenos-grid packages and the installer image
config/       example configuration for the servers
tests/        unit tests
formal/       the decisions of keyd and guardd in Lean 4, with their proofs (zenos-decide)
third_party/  modified KDE plasmoids (kept under their original GPL/LGPL licenses)
docs/         architecture, security architecture, threat model, release process
```

How the parts fit together and which run as root: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The decisions that
release classified data (opening a file, releasing a stop) are proved in Lean and run as proved:
[docs/FORMAL_VERIFICATION.md](docs/FORMAL_VERIFICATION.md).

## Running it

ZENOS is a Debian 13 ("trixie") system with a KDE Plasma 6 X11 session. It does not depend on Windows.

**Install on an existing Debian 13 system**

```
packaging/build-deb.sh                     # -> build/zenos_<version>_amd64.deb
# ZENOS needs Node.js 24 LTS (Debian 13's Node 20 is past end of life): add NodeSource first
sudo install -m 644 packaging/debian/apt/nodesource-archive-keyring.gpg /usr/share/keyrings/zenos-nodesource.gpg
sudo install -m 644 packaging/debian/apt/zenos-nodesource.sources /etc/apt/sources.list.d/
sudo install -m 644 packaging/debian/apt/zenos-nodesource.pref /etc/apt/preferences.d/zenos-nodesource
sudo apt update
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

**Set each user's clearance**

The level keys belong to root. Each user can open files up to their clearance; anything above goes through an
access request their officers approve. Until set, a user is cleared for L1 only.

```
sudo zenos_keyd.py --clearance <user> <1-5>
```

**Enroll the officers who release a stopped PC**

Each officer opens ZENOS Messages on their own device → Settings → Approval key, makes a key there (it never leaves
that browser) and gives the shown line to the PC administrator, who runs it:

```
sudo zenos_guardd.py --enroll <account> <public key>
```

When the PC stops, the request reaches the enrolled officers in ZENOS Messages. Each one reads the match code off the
stopped screen, approves or declines, and the device signs the answer.

**Keep the audit trail off the PC**

Run an audit node on a server the PC users do not control, and point each PC at it:

```
# on the server
zenos_auditnode.py --store /var/lib/zenos-audit --show-key                  # the node's key
zenos_auditnode.py --store /var/lib/zenos-audit --port 8443 --cert node.crt --key node.key
# on each PC: write /etc/zenos/audit.json (see zenos_auditship.py), then enroll the PC on the node
sudo zenos_auditship.py --show-key     # prints the --enroll line to run on the server
sudo systemctl restart zenos-auditship
```

The PC sends its ledgers every 30 seconds; the node refuses any rewritten history and reports a PC that goes silent.

**Tests**

```
python3 -m unittest discover -s tests     # sealing, request digests, enrollment, the guard's approval rules
```

Calls use a self-hosted LiveKit server (pinned release, checksum-verified at build time). Each user gets their own
keys at first login; nothing secret is shipped in the package.

The development machine runs ZENOS inside WSL2 for convenience; `dev/` holds the pieces that only make sense there
(VNC desktop service, input-method autostart for WSLg).

## Roadmap

Done in this preview: one repository with secrets removed and licences documented; a Debian package, a signed apt
repository and an installer ISO (full-disk encryption checked by default); the guard as a root service with
fanotify; a root key agent with per-user clearance; approvals signed on officers' own devices; ledgers shipped to
audit nodes; messenger accounts bound to their devices; printing with level watermarks and a ceiling; a level
clipboard between sealed windows; screenshot and terminal control; a certified storage grid (encrypted, erasure-coded shards
served only to cleared PCs; packaged as `zenos-grid`) and audit nodes of different parties that catch a forked history.

Still ahead:

1. **Hardware keys**: level keys sealed to the TPM, officer and user keys on FIDO2 devices, disk unlock by TPM +
   fingerprint.
2. **Mandatory access control**: SELinux multi-level security, so no program can write a copy of an open sealed
   file to a lower level.
3. **Shared infrastructure**: a key service so sealed files open on any cleared PC and capabilities are issued
   through the approval flow.
4. **Everyday apps**: Files, Settings, notifications, better Office format compatibility.
5. **External security audit** before any claim of production readiness.

Editions (Government, Academy, Creator, Educational, Hobby) will be configurations of one shared core.

## License

ZENOS is licensed under the [Apache License 2.0](LICENSE). The messenger (`messenger/`) links libsignal and is
therefore licensed under the [AGPL-3.0](messenger/LICENSE). Third-party components keep their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Security

Please report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

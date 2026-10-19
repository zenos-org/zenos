# Changelog

## 0.1.0 Developer Preview (unreleased)

First public preview. Not for real classified data; see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

**System**
- Debian 13 package and a live/installer image (Calamares) for ordinary PCs; KDE Plasma (X11) desktop with the
  ZENOS layout, security folders (L1–L5), level bar and launcher.
- Installer flushes the new system to disk before unmounting it, so a slow disk no longer ends the install with
  "Could not unmount the root of the target system".
- Root key agent (`zenos-keyd`): level keys belong to root; files open up to the user's clearance or with an
  officer-signed grant for that exact file; every unseal is recorded.
- Root guard (`zenos-guardd`): bulk reads, transfers to removable media and similar stop the whole session until
  officers release it; terminals are refused for staff; screen capture is refused while an L3+ file is on screen.
- Officers approve on their own devices: release of a stopped PC, access requests and pre-filed operations are
  signed in ZENOS Messages with a key that never leaves the officer's browser, and checked against
  administrator-enrolled keys.
- Tamper-evident ledgers shipped off the PC to audit nodes, which refuse rewritten history and report silent PCs.
- Signed apt repository tooling; release gate for secrets and real phone numbers; tests and CI.

**Apps**
- ZENOS Browser (WebKitGTK): tabs, bookmarks, persistent sign-in, full-screen video.
- Documents, Sheets, Slides: sealed files are edited from a RAM copy and sealed again on close; text of L3+ files
  is copied only into windows of the same level or higher (level clipboard in the key agent), never to other
  programs or the X11 selections; printed pages carry the level and the user, and files above the policy ceiling
  (default L3) are not printed.
- PDF, Images, Video viewers; ZENOS file picker for every app.
- ZENOS Messages (Signal protocol via libsignal): channels, calls (self-hosted LiveKit), calendar, My requests.
  Accounts are bound to the device that registered them; moving to a new device needs the account's own number.

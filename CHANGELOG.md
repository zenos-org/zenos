# Changelog

## 0.1.0 Developer Preview (unreleased)

First public preview. Not for real classified data; see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

**System**
- Debian 13 package and a live/installer image (Calamares) for ordinary PCs; KDE Plasma (X11) desktop with the
  ZENOS layout, security folders (L1–L5), level bar and launcher.
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
- Documents, Sheets, Slides: sealed files are edited from a RAM copy and sealed again on close; nothing can be
  copied out of L3+ files.
- PDF, Images, Video viewers; ZENOS file picker for every app.
- ZENOS Messages (Signal protocol via libsignal): channels, calls (self-hosted LiveKit), calendar, My requests.

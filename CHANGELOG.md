# Changelog

## 0.1.1 Developer Preview (2026-10-28)

Still a preview for testing and evaluation. Do not use it for real sensitive data; see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

**System**
- Level-gated AI is now also enforced in the packet filter (`zenos-aiguard`, root). The key agent records the
  highest level unsealed on the PC and, from L3, waits for the guard to confirm its rules before it hands out the
  plaintext. For every AI service the administrator lists in `/etc/zenos/ai.json` (external, government or
  ministry AI) or the office apps are pointed at (always counted as external), the guard asks `zenos-decide` and
  rejects the service's addresses in the `ZENOS_AI` chain wherever the flow decision says no, for every program on
  the PC. No answer from the decision is a block. The level falls only on a restart or with
  `sudo zenos_aiguard.py reset`.
- The office apps' AI relay asks the guard before each request and shows its reason when an AI is out of reach.
- Lean: `mayFlow_antitone` (a higher level never reaches a place a lower level cannot).

**Apps**
- Images: a Library (music, pictures, playlists, picture albums, Studio projects, made videos) and a Studio: trim
  a song with fades, put a picture on it and export one MP4 (H.264 + AAC). Motion with AI sends one L1 picture and
  the person's words to a video AI they registered under their own account; ZENOS ships no model. Only plain
  files in L1 places are listed. `studio_ai = off` in `/etc/zenos/policy.conf` turns the AI part off.

## 0.1.0 Developer Preview (2026-10-27)

First public preview. Not for real classified data; see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

**System**
- Debian 13 package and a live/installer image (Calamares) for ordinary PCs; KDE Plasma (X11) desktop with the
  ZENOS layout, security folders (L1–L5), level bar and launcher.
- Installer writes out the new system and drops its cached inodes before unmounting it, so a slow machine no
  longer ends the install with "Could not unmount the root of the target system".
- KRunner's command line (Alt+Space) no longer runs shell commands (KDE Kiosk `shell_access=false`, locked).
- Root key agent (`zenos-keyd`): level keys belong to root; files open up to the user's clearance or with an
  officer-signed grant for that exact file; every unseal is recorded.
- Root guard (`zenos-guardd`): bulk reads, transfers to removable media and similar stop the whole session until
  officers release it; terminals are refused for staff; screen capture is refused while an L3+ file is on screen.
- Officers approve on their own devices: release of a stopped PC, access requests and pre-filed operations are
  signed in ZENOS Messages with a key that never leaves the officer's browser, and checked against
  administrator-enrolled keys.
- Tamper-evident ledgers shipped off the PC to audit nodes, which refuse rewritten history and report silent PCs.
- Storage grid (`storage/`, also shipped as the `zenos-grid` server package): sealed files are encrypted again
  per file, erasure-coded 3-of-5 and spread over storage nodes, at most two shards per zone. Every node and
  every PC holds a certificate from the grid administrator (role, highest level, zone); a node refuses every
  request from a peer without one, serves a file only to a PC cleared for its level, and never takes a level
  above its own clearance. A certified grid refuses to run on the public DHT. Certificates expire; the administrator revokes keys with a
  signed list that every node and PC passes on to the peers it meets, checked on every request. Nodes repair lost shards without
  the key. Storage node, bootstrap and audit node run as hardened systemd services (dynamic user, system-call
  filter). Tested on two machines: files restore with two nodes down; an L1 PC holding the capability is refused.
- Audit consortium: audit nodes run by different parties list each other as peers and compare their copies of
  every PC's ledger; a PC that sends different histories to different parties, or an altered copy, is reported
  as a fork on both sides with both parties' signed statements kept as evidence (once, not on every check). The
  consortium's history is the longest prefix a majority of the audit nodes hold identically, each answer signed.
- Signed apt repository tooling; release gate for secrets and real phone numbers; tests and CI.

**Apps**
- Desktop top bar, taskbar, search fields and open-window buttons in the ZENOS Browser tone.
- ZENOS Browser (WebKitGTK): tabs, bookmarks, persistent sign-in, full-screen video.
- Documents, Sheets, Slides: sealed files are edited from a RAM copy and sealed again on close; text of L3+ files
  is copied only into windows of the same level or higher (level clipboard in the key agent), never to other
  programs or the X11 selections; printed pages carry the level and the user, and files above the policy ceiling
  (default L3) are not printed.
- PDF, Images, Video viewers; ZENOS file picker for every app.
- ZENOS Messages (Signal protocol via libsignal): channels, calls (self-hosted LiveKit), calendar, My requests.
  Accounts are bound to the device that registered them; moving to a new device needs the account's own number.

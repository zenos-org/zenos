# Third-party components

ZENOS's own code is licensed under Apache-2.0. The components below keep their own licenses. Versions are the
ones used in the Developer Preview.

## Bundled in this repository

| Component | Where | License |
|---|---|---|
| KDE Plasma system tray and Kickerdash plasmoids (modified) | `third_party/kde-plasmoids/` | GPL-2.0-or-later / LGPL-2.0-or-later (per file headers; ZENOS modifications are under the same licenses) |
| pdf.js (legacy build) | `apps/pdf/vendor/pdf.min.mjs`, `pdf.worker.min.mjs` | Apache-2.0 |
| pdf-lib 1.17.1 | `apps/pdf/vendor/pdf-lib.min.js` | MIT |
| @pdf-lib/fontkit 1.1.1 | `apps/pdf/vendor/fontkit.umd.min.js` | MIT |

## Installed from package registries (not bundled)

| Component | Used by | License |
|---|---|---|
| @signalapp/libsignal-client 0.105.1 | messenger | **AGPL-3.0-only** — see the note below |
| livekit-client 2.23.0, livekit-server-sdk 2.19.1 | messenger | Apache-2.0 |
| LiveKit server 1.13.10 (bundled in the package, `/usr/lib/zenos/livekit`) | messenger calls | Apache-2.0 |
| pdfjs-dist 6.4.299 | messenger | Apache-2.0 |
| qrcode 1.5.4 | messenger | MIT |
| web-push 3.6.7 | messenger | MPL-2.0 |
| @univerjs/presets, preset-docs-core, preset-sheets-core 1.1.0 | Documents, Sheets | Apache-2.0 |
| mammoth 1.13.0 | Documents | BSD-2-Clause |
| jszip 3.10.2 | Documents, Slides | MIT (dual MIT / GPL-3.0-or-later; used under MIT) |
| xlsx 0.20.3 (SheetJS, from cdn.sheetjs.com) | Sheets | Apache-2.0 |
| vite 8 | build tool | MIT |
| PyGObject, GTK 3, WebKit2GTK 4.1, GStreamer | core | LGPL-2.1-or-later (WebKit parts also BSD) |
| cryptography | core | Apache-2.0 OR BSD-3-Clause |
| opencv-python-headless, NumPy | Images | Apache-2.0, BSD-3-Clause |
| fontTools | PDF | MIT |
| KDE Plasma 6, fcitx5, Anthy | desktop | GPL / LGPL (system packages) |
| BIZ UDPGothic (system font) | PDF export | SIL Open Font License 1.1 |

## The messenger is AGPL-3.0

libsignal is licensed AGPL-3.0-only, so the `messenger/` component is distributed under the GNU Affero General
Public License v3.0 (see `messenger/LICENSE`). Everything outside `messenger/` remains Apache-2.0. The core does
not link the messenger; they talk over local HTTP, so the rest of ZENOS keeps its Apache-2.0 terms.

| Component | Used by | License |
|---|---|---|
| LibreOffice (system package) | opening sealed office files (until the ZENOS office apps take this over) | MPL-2.0 |

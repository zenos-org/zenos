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
| LiveKit server (downloaded at install) | messenger calls | Apache-2.0 |
| pdfjs-dist 6.4.299 | messenger | Apache-2.0 |
| qrcode 1.5.4 | messenger | MIT |
| web-push 3.6.7 | messenger | MPL-2.0 |
| @univerjs/presets, preset-docs-core, preset-sheets-core 1.1.0 | Documents, Sheets | Apache-2.0 |
| mammoth 1.13.0 | Documents | BSD-2-Clause |
| jszip 3.10.2 | Documents, Slides | MIT (dual MIT / GPL-3.0-or-later; used under MIT) |
| xlsx 0.18.5 (SheetJS) | Sheets | Apache-2.0 |
| vite 8 | build tool | MIT |
| PyGObject, GTK 3, WebKit2GTK 4.1, GStreamer | core | LGPL-2.1-or-later (WebKit parts also BSD) |
| cryptography | core | Apache-2.0 OR BSD-3-Clause |
| opencv-python-headless, NumPy | Images | Apache-2.0, BSD-3-Clause |
| fontTools | PDF | MIT |
| KDE Plasma 6, fcitx5, Anthy | desktop | GPL / LGPL (system packages) |
| BIZ UDPGothic (system font) | PDF export | SIL Open Font License 1.1 |

## Note on the messenger and AGPL

libsignal is licensed AGPL-3.0-only. Apache-2.0 code may be combined with it, but the messenger as distributed
(and when offered over a network) must then meet the AGPL's terms, including making its source available to its
users. The project's decision on how to license the `messenger/` component is pending; until then, treat
`messenger/` as subject to AGPL-3.0 obligations.

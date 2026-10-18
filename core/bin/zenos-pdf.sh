#!/bin/bash
# ZENOS PDF - read, write on and create PDFs (pdf.js to read, pdf-lib to write; WebKitGTK, non-Google)
unset WAYLAND_DISPLAY; export GDK_BACKEND=x11
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"   # program files
exec python3 "$R/bin/zenos_app.py" "$R/apps/pdf/index.html" "ZENOS PDF" "$R/icons/zenos-pdf.svg" 1120x780 "$@"

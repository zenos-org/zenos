#!/bin/bash
# ZENOS PDF - read, write on and create PDFs (pdf.js to read, pdf-lib to write; WebKitGTK, non-Google)
unset WAYLAND_DISPLAY; export GDK_BACKEND=x11
exec python3 "$HOME/.local/share/zenos/bin/zenos_app.py" "$HOME/.local/share/zenos/apps/pdf/index.html" "ZENOS PDF" "$HOME/.local/share/zenos/icons/zenos-pdf.svg" 1120x780 "$@"

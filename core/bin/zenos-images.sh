#!/bin/bash
# ZENOS Images - picture viewer (WebKitGTK, non-Google)
unset WAYLAND_DISPLAY; export GDK_BACKEND=x11
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"   # program files
exec python3 "$R/bin/zenos_app.py" "$R/apps/images/index.html" "ZENOS Images" "$R/icons/zenos-images.svg" 1120x720 "$@"

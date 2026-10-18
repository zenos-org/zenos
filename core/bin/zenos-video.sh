#!/bin/bash
# ZENOS Video - plays local videos (WebKitGTK + GStreamer, non-Google)
unset WAYLAND_DISPLAY; export GDK_BACKEND=x11
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"   # program files
exec python3 "$R/bin/zenos_app.py" "$R/apps/video/index.html" "ZENOS Video" "$R/icons/zenos-video.svg" 1120x700 "$@"

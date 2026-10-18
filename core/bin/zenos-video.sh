#!/bin/bash
# ZENOS Video - plays local videos (WebKitGTK + GStreamer, non-Google)
unset WAYLAND_DISPLAY; export GDK_BACKEND=x11
exec python3 "$HOME/.local/share/zenos/bin/zenos_app.py" "$HOME/.local/share/zenos/apps/video/index.html" "ZENOS Video" "$HOME/.local/share/zenos/icons/zenos-video.svg" 1120x700 "$@"

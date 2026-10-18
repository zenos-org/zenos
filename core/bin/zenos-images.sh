#!/bin/bash
# ZENOS Images - picture viewer (WebKitGTK, non-Google)
unset WAYLAND_DISPLAY; export GDK_BACKEND=x11
exec python3 "$HOME/.local/share/zenos/bin/zenos_app.py" "$HOME/.local/share/zenos/apps/images/index.html" "ZENOS Images" "$HOME/.local/share/zenos/icons/zenos-images.svg" 1120x720 "$@"

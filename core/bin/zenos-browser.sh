#!/bin/bash
# ZENOS Browser launcher - WebKitGTK shell (non-Google, level-gated).
# Engine is maintained by the distro (WebKitGTK); we own only this shell.
unset WAYLAND_DISPLAY
export GDK_BACKEND=x11
exec python3 "$HOME/.local/share/zenos/bin/zenos_webkit.py" "$@"

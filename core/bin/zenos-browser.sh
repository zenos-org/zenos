#!/bin/bash
# ZENOS Browser launcher - WebKitGTK shell (non-Google, level-gated).
# Engine is maintained by the distro (WebKitGTK); we own only this shell.
unset WAYLAND_DISPLAY
export GDK_BACKEND=x11
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"   # program files
exec python3 "$R/bin/zenos_webkit.py" "$@"

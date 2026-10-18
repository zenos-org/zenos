#!/bin/bash
# ZENOS guard: watches the security folders. Plain files are sealed; downgrades are blocked.
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"   # program files
inotifywait -m -r -q -e close_write -e moved_to --format '%w%f' "$HOME/Desktop" | while read -r f; do
  python3 -I "$R/bin/zenos.py" check "$f" &
done

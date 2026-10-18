#!/bin/bash
# ZENOS guard: watches the security folders. Plain files are sealed; downgrades are blocked.
Z=$HOME/.local/share/zenos
inotifywait -m -r -q -e close_write -e moved_to --format '%w%f' "$HOME/Desktop" | while read -r f; do
  python3 -I "$Z/bin/zenos.py" check "$f" &
done

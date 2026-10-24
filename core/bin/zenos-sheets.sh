#!/bin/bash
# ZENOS Sheets launcher (dark, local relay server + WebKit window)
unset WAYLAND_DISPLAY
export GDK_BACKEND=x11
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"   # program files
APP=$R/apps/sheets
if ! pgrep -f "zoffice_server.py $APP " >/dev/null 2>&1; then
  setsid python3 "$R/apps/common/zoffice_server.py" "$APP" 5174 >/tmp/zsheets_srv.log 2>&1 < /dev/null &
  sleep 1
fi
exec python3 "$R/bin/zenos-webview.py" "http://127.0.0.1:5174/" "ZENOS Sheets" "$@"

#!/bin/bash
# ZENOS Sheets launcher (dark, local relay server + WebKit window)
unset WAYLAND_DISPLAY
export GDK_BACKEND=x11 DISPLAY=:1 XAUTHORITY=/home/zenos/.Xauthority
APP=/home/zenos/.local/share/zenos/apps/sheets
if ! pgrep -f zsheets_server.py >/dev/null 2>&1; then
  setsid python3 "$APP/server/zsheets_server.py" >/tmp/zsheets_srv.log 2>&1 < /dev/null &
  sleep 1
fi
exec python3 /home/zenos/.local/share/zenos/bin/zenos-webview.py "http://127.0.0.1:5174/" "ZENOS Sheets"

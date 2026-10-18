#!/bin/bash
# ZENOS Docs launcher (dark, local relay server + WebKit window)
unset WAYLAND_DISPLAY
export GDK_BACKEND=x11 DISPLAY=:1 XAUTHORITY=/home/zenos/.Xauthority
APP=/home/zenos/.local/share/zenos/apps/docs
if ! pgrep -f zdocs_server.py >/dev/null 2>&1; then
  setsid python3 "$APP/server/zdocs_server.py" >/tmp/zdocs_srv.log 2>&1 < /dev/null &
  sleep 1
fi
exec python3 /home/zenos/.local/share/zenos/bin/zenos-webview.py "http://127.0.0.1:5175/" "ZENOS Docs"

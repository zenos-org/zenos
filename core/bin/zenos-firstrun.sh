#!/bin/bash
# ZENOS per-user setup, run at every login (idempotent): security folders on the desktop, the session level,
# desktop links, and the messenger's local account. Nothing here overwrites what the user already has.
R="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"   # program files
D="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
C="$HOME/.config/zenos"
DATA="$HOME/.local/share/zenos"
mkdir -p "$D" "$C" "$DATA/msg"

[ -f "$C/level" ] || echo 1 > "$C/level"

folder() {   # name icon
  [ -d "$D/$1" ] && return
  mkdir -p "$D/$1"
  printf '[Desktop Entry]\nIcon=%s/icons/zenos-folder-%s.svg\n' "$R" "$2" > "$D/$1/.directory"
}
folder "Basic · L1" basic
folder "Green · L2-L3" green
folder "Red · L4" red
# PoC stand-in for removable media: copies here are watched like a USB stick
if [ ! -d "$D/USB Drive" ]; then
  mkdir -p "$D/USB Drive"
  printf '[Desktop Entry]\nIcon=%s/icons/zenos-usb.svg\n' "$R" > "$D/USB Drive/.directory"
fi

[ -f "$D/trash.desktop" ] || printf '[Desktop Entry]\nName=Trash\nType=Link\nURL=trash:/\nIcon=%s/icons/zenos-trash.svg\n' "$R" > "$D/trash.desktop"
if [ ! -f "$D/zenos-vault.desktop" ] && [ -f /usr/share/applications/zenos-vault.desktop ]; then
  cp /usr/share/applications/zenos-vault.desktop "$D/" && chmod +x "$D/zenos-vault.desktop"
fi

# this desk's messenger account (demo devices are only started in development)
[ -f "$DATA/msg/ports.env" ] || echo "zenos=8096" > "$DATA/msg/ports.env"
# ZENOS wallpaper, once (Plasma must be running, so this part waits for it in the background)
if [ ! -f "$C/.wallpaper-set" ]; then
  ( for i in $(seq 1 60); do
      if command -v plasma-apply-wallpaperimage >/dev/null && pgrep -u "$(id -u)" -x plasmashell >/dev/null; then
        sleep 3; plasma-apply-wallpaperimage "$R/wallpaper.jpg" >/dev/null 2>&1 && touch "$C/.wallpaper-set"; break
      fi
      sleep 2
    done ) &
fi
exit 0

#!/bin/bash
# Build the ZENOS Debian package (amd64) from this repository.
#   packaging/build-deb.sh            -> build/zenos_<version>_amd64.deb
# Needs: dpkg-deb, nodejs + npm (to build the office apps and install the messenger's runtime modules).
set -euo pipefail
SRC="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
VER="${VER:-0.1.0~preview$(date +%Y%m%d)}"
OUT="${OUT:-$SRC/build}"
B="$OUT/work"; P="$OUT/pkg"
rm -rf "$B" "$P"; mkdir -p "$B" "$P"
Z="$P/usr/share/zenos"

echo "== core"
mkdir -p "$Z/apps"
cp -a "$SRC/core/bin" "$SRC/core/shell" "$SRC/core/icons" "$SRC/core/templates" "$Z/"
cp "$SRC"/core/wallpaper.* "$Z/"
chmod 755 "$Z"/bin/*.sh "$Z"/bin/*.py

echo "== apps"
for a in images video pdf; do cp -a "$SRC/apps/$a" "$Z/apps/"; done
for a in docs sheets slides; do
  cp -a "$SRC/apps/$a" "$B/$a"
  ( cd "$B/$a" && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent )
  mkdir -p "$Z/apps/$a"
  cp -a "$B/$a/dist" "$B/$a/server" "$Z/apps/$a/"
done

echo "== messenger (AGPL-3.0)"
cp -a "$SRC/messenger" "$B/msg"
( cd "$B/msg" && npm ci --omit=dev --no-audit --no-fund --loglevel=error
  # native modules for other platforms are not needed in an amd64 package
  find node_modules/@signalapp/libsignal-client/prebuilds -mindepth 1 -maxdepth 1 ! -name linux-x64 -exec rm -rf {} +
  find node_modules/@napi-rs -mindepth 1 -maxdepth 1 \( -name '*darwin*' -o -name '*win32*' -o -name '*arm*' -o -name '*musl*' -o -name '*android*' -o -name '*freebsd*' -o -name '*riscv*' -o -name '*ppc*' -o -name '*s390*' \) -exec rm -rf {} + 2>/dev/null || true )
cp -a "$B/msg" "$Z/msg"
chmod 755 "$Z"/msg/*.sh

echo "== system services"
mkdir -p "$P/usr/lib/zenos" "$P/usr/sbin" "$P/lib/systemd/system" "$P/usr/lib/systemd/user"
cp -a "$SRC"/system/lib/. "$P/usr/lib/zenos/"
cp -a "$SRC"/system/sbin/. "$P/usr/sbin/"
chmod 755 "$P"/usr/sbin/*
chmod 644 "$P/usr/sbin/zenos-netsense.bt"
cp "$SRC"/system/systemd/*.service "$P/lib/systemd/system/"
cp "$SRC"/system/systemd-user/*.service "$P/usr/lib/systemd/user/"
mkdir -p "$P/etc/zenos"
cat > "$P/etc/zenos/zenos.conf" <<'EOF'
# ZENOS machine settings (KEY=value)
# The desktop user whose files the root services protect. Empty: the first user who has ZENOS data.
#ZENOS_USER=
# Where the ZENOS programs are installed.
ZENOS_ROOT=/usr/share/zenos
EOF

echo "== LiveKit call server (Apache-2.0): pinned release, checksum verified"
LK_VER=1.13.10
LK_SHA=c25a3e45fb922e9a93c6443d10c0ed041ba64342097e38632331736630283165
curl -fsSL -o "$B/livekit.tgz" "https://github.com/livekit/livekit/releases/download/v$LK_VER/livekit_${LK_VER}_linux_amd64.tar.gz"
echo "$LK_SHA  $B/livekit.tgz" | sha256sum -c --quiet -
mkdir -p "$P/usr/lib/zenos/livekit"
tar -xzf "$B/livekit.tgz" -C "$P/usr/lib/zenos/livekit" livekit-server LICENSE
chmod 755 "$P/usr/lib/zenos/livekit/livekit-server"

echo "== desktop"
mkdir -p "$P/usr/share/applications" "$P/etc/xdg/autostart" "$P/usr/share/plasma/plasmoids" "$P/usr/share/plasma/desktoptheme"
cp "$SRC"/desktop/applications/*.desktop "$P/usr/share/applications/"
cp "$SRC"/desktop/autostart/zenos-*.desktop "$P/etc/xdg/autostart/"
cp -a "$SRC"/desktop/plasmoids/jp.zenos.* "$P/usr/share/plasma/plasmoids/"
cp -a "$SRC/third_party/kde-plasma-theme/zenos" "$P/usr/share/plasma/desktoptheme/"
mkdir -p "$P/etc/skel/.local/share/plasma/plasmoids"
cp -a "$SRC/desktop/skel/.config" "$P/etc/skel/"
cp -a "$SRC"/third_party/kde-plasmoids/* "$P/etc/skel/.local/share/plasma/plasmoids/"

echo "== docs"
mkdir -p "$P/usr/share/doc/zenos"
cp "$SRC"/README.md "$SRC"/LICENSE "$SRC"/NOTICE "$SRC"/THIRD_PARTY_NOTICES.md "$SRC"/docs/THREAT_MODEL.md "$P/usr/share/doc/zenos/"
cp "$SRC/messenger/LICENSE" "$P/usr/share/doc/zenos/LICENSE.messenger-AGPL-3.0"

echo "== control"
find "$P" -name __pycache__ -prune -exec rm -rf {} +
mkdir -p "$P/DEBIAN"
SIZE=$(du -sk "$P" | cut -f1)
sed -e "s/@VERSION@/$VER/" -e "s/@SIZE@/$SIZE/" "$SRC/packaging/debian/control.in" > "$P/DEBIAN/control"
for s in postinst prerm postrm; do install -m 755 "$SRC/packaging/debian/$s" "$P/DEBIAN/$s"; done
echo "/etc/zenos/zenos.conf" > "$P/DEBIAN/conffiles"

dpkg-deb --root-owner-group -Zxz --build "$P" "$OUT/zenos_${VER}_amd64.deb" >/dev/null
ls -la "$OUT/zenos_${VER}_amd64.deb"

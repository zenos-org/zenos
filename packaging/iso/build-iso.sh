#!/bin/bash
# Build a ZENOS live / installer ISO (Debian 13 "trixie" + KDE Plasma + ZENOS, Calamares installer).
#   sudo packaging/iso/build-iso.sh build/zenos_<version>_amd64.deb
# The image boots on ordinary PCs (BIOS and UEFI) as a live session; "Install ZENOS" puts it on the disk.
# Needs root and live-build.
set -euo pipefail
DEB="$(readlink -f "${1:?path to zenos_*.deb}")"
SRC="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
W="${WORK:-$SRC/build/iso}"
rm -rf "$W"; mkdir -p "$W"; cd "$W"

lb config \
  --mode debian --distribution trixie --architectures amd64 \
  --archive-areas "main non-free-firmware" \
  --debian-installer none \
  --binary-images iso-hybrid --bootloaders "grub-efi,syslinux" \
  --iso-application "ZENOS" --iso-volume "ZENOS" --iso-publisher "The ZENOS Authors" \
  --image-name zenos \
  --bootappend-live "boot=live components quiet splash username=zenos hostname=zenos locales=en_US.UTF-8" \
  --apt-recommends false \
  --memtest none

mkdir -p config/package-lists config/packages.chroot config/includes.chroot/etc/sddm.conf.d config/hooks/live config/bootloaders
cp "$DEB" config/packages.chroot/
cp "$SRC/packaging/iso/splash.svg" config/bootloaders/splash.svg      # ZENOS boot screen (BIOS and UEFI menus)
cat > config/package-lists/zenos.list.chroot <<'EOF'
# desktop
kde-plasma-desktop
plasma-workspace
kwin-x11
sddm
sddm-theme-breeze
xorg
plasma-nm
network-manager
plasma-pa
pipewire-pulse
wireplumber
kscreen
powerdevil
xdg-user-dirs
sudo
# input: Japanese / English
fcitx5
fcitx5-anthy
kde-config-fcitx5
im-config
# installer and live system
calamares
calamares-settings-debian
live-boot
live-config
live-config-systemd
# hardware
firmware-linux-free
firmware-misc-nonfree
firmware-iwlwifi
firmware-realtek
EOF
cat > config/includes.chroot/etc/sddm.conf.d/zenos.conf <<'EOF'
[Theme]
Current=breeze
[Autologin]
Session=plasmax11.desktop
EOF
cat > config/hooks/live/0100-zenos.hook.chroot <<'EOF'
#!/bin/sh
set -e
# fcitx5 is the input method for every session
im-config -n fcitx5 || true
EOF
chmod +x config/hooks/live/*.hook.chroot

lb build 2>&1 | tee build.log
ls -la "$W"/*.iso

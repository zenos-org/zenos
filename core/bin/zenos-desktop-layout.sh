#!/bin/bash
# ZENOS: desktop icons in a column on the left (Figma frame 33:2), every login.
# Plasma's one-time update script is not enough: Plasma can replace the desktop containment after it ran.
# Debian ships qdbus in /usr/lib/qt6/bin, which is not on PATH
Q=""
for c in qdbus6 qdbus /usr/lib/qt6/bin/qdbus6 /usr/lib/qt6/bin/qdbus; do
    if command -v "$c" >/dev/null 2>&1; then Q=$(command -v "$c"); break; fi
done
[ -n "$Q" ] || exit 0
for i in $(seq 1 60); do "$Q" org.kde.plasmashell /PlasmaShell >/dev/null 2>&1 && break; sleep 1; done
"$Q" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
desktops().forEach(function (d) {
    d.currentConfigGroup = ["General"];
    if (d.readConfig("arrangement") != 1 || d.readConfig("alignment") != 0) {
        d.writeConfig("arrangement", 1);   // 0 = rows, 1 = columns
        d.writeConfig("alignment", 0);     // left
        d.reloadConfig();
    }
});' >/dev/null 2>&1
exit 0

#!/bin/bash
# ZENOS: desktop icons in a column on the left (Figma frame 33:2), every login.
# Plasma's one-time update script is not enough: Plasma can replace the desktop containment after it ran.
Q=$(command -v qdbus6 || command -v qdbus) || exit 0
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

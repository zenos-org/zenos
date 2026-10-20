// ZENOS: desktop icons run top to bottom in a column (Figma frame 33:2), not left to right.
// Plasma runs each update script once per user when plasmashell starts. The skel layout alone is not enough:
// Plasma replaces the skel desktop containment with a fresh one on first login, which defaults to rows.
desktops().forEach(function (d) {
    d.currentConfigGroup = ["General"];
    d.writeConfig("arrangement", 1);   // 0 = rows, 1 = columns
    d.writeConfig("alignment", 0);     // left
    d.reloadConfig();
});

import QtQuick

// A sparkline in the address-field well (Figma 42:19): line plus a fading fill, newest sample on the right.
Rectangle {
    id: g
    property var values: []        // 0..1
    property color tint: "#0A84FF"
    radius: 8
    border.width: 1
    border.color: Qt.rgba(0, 0, 0, 0.5)
    gradient: Gradient {
        GradientStop { position: 0; color: "#141417" }
        GradientStop { position: 1; color: "#1A1A1E" }
    }
    clip: true
    onValuesChanged: canvas.requestPaint()
    Canvas {
        id: canvas
        anchors.fill: parent
        anchors.margins: 1
        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            const v = g.values, n = Math.max(2, v.length), w = width, h = height;
            if (!v.length) return;
            const x = i => w - (v.length - 1 - i) * (w / 59);
            const y = val => h - 3 - Math.max(0, Math.min(1, val)) * (h - 8);
            ctx.beginPath();
            ctx.moveTo(x(0), h);
            for (let i = 0; i < v.length; i++) ctx.lineTo(x(i), y(v[i]));
            ctx.lineTo(w, h);
            ctx.closePath();
            const grad = ctx.createLinearGradient(0, 0, 0, h);
            grad.addColorStop(0, Qt.rgba(g.tint.r, g.tint.g, g.tint.b, 0.45));
            grad.addColorStop(1, Qt.rgba(g.tint.r, g.tint.g, g.tint.b, 0.0));
            ctx.fillStyle = grad;
            ctx.fill();
            ctx.beginPath();
            for (let i = 0; i < v.length; i++) i ? ctx.lineTo(x(i), y(v[i])) : ctx.moveTo(x(i), y(v[i]));
            ctx.strokeStyle = g.tint;
            ctx.lineWidth = 1.5;
            ctx.stroke();
        }
    }
    Rectangle { x: 4; y: 1; width: parent.width - 8; height: 1.5; color: Qt.rgba(0, 0, 0, 0.35) }   // inset edge
}

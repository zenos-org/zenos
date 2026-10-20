import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as P5Support

// ZENOS System Monitor (Figma 42:2 chip, 42:19 panel): CPU, memory, network and disk in the top bar,
// graphs of the last two minutes on click. Reads /proc every 2 s; nothing leaves the machine.
// Security (Tk 2026-10-21): blocked inbound attempts, failed sign-ins and sentinel incidents from
// /run/zenos/secstat.json (zenos-secstat.service); a new alert raises a desktop notification.
PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation

    readonly property int samples: 60
    property var prev: null
    property real cpu: 0
    property int cores: 0
    property real load1: 0
    property real memTotal: 0
    property real memAvail: 0
    property real rxRate: 0
    property real txRate: 0
    property real rxTotal: 0
    property real txTotal: 0
    property real rdRate: 0
    property real wrRate: 0
    property real diskFree: 0
    property var hCpu: []
    property var hMem: []
    property var hNet: []
    property var hDisk: []
    property var sec: ({ firewall: true, inbound_blocked: 0, auth_failed: 0, outbound_contained: 0, h_in: [], alerts: [] })
    property bool secReady: false
    property var secSeen: ({})
    property string secLevel: "ok"     // ok | amber | red (an alert in the last 10 minutes)
    readonly property color secColor: secLevel === "red" ? "#FF453A" : secLevel === "amber" ? "#FFD60A" : "#30D158"

    function human(b) {
        if (b < 1024) return Math.round(b) + " B"
        if (b < 1048576) return (b / 1024).toFixed(b < 10240 ? 1 : 0) + " KB"
        if (b < 1073741824) return (b / 1048576).toFixed(b < 10485760 ? 1 : 0) + " MB"
        return (b / 1073741824).toFixed(1) + " GB"
    }
    function rate(b) { return human(b) + "/s" }
    function push(arr, v) { const a = arr.slice(-(samples - 1)); a.push(v); return a }

    function parse(out) {
        const lines = out.split("\n")
        const now = Date.now() / 1000
        let cpuT = 0, cpuI = 0, nCores = 0, rx = 0, tx = 0, rd = 0, wr = 0
        let mt = 0, ma = 0, df = 0, afterDf = false
        for (const l of lines) {
            const f = l.trim().split(/\s+/)
            if (afterDf) { if (f[0]) df = Number(f[0]); continue }
            if (l === "==DF") { afterDf = true; continue }
            if (f[0] === "cpu") {
                const v = f.slice(1, 9).map(Number)
                cpuT = v.reduce((a, b) => a + b, 0); cpuI = v[3] + v[4]
            } else if (/^cpu\d+$/.test(f[0])) nCores++
            else if (f[0] === "MemTotal:") mt = Number(f[1]) * 1024
            else if (f[0] === "MemAvailable:") ma = Number(f[1]) * 1024
            else if (/^[\w.-]+:$/.test(f[0]) && f.length >= 17 && f[0] !== "lo:") { rx += Number(f[1]); tx += Number(f[9]) }
            else if (f.length >= 14 && /^(sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)$/.test(f[2])) { rd += Number(f[5]) * 512; wr += Number(f[9]) * 512 }
        }
        const cur = { t: now, cpuT, cpuI, rx, tx, rd, wr }
        if (prev) {
            const dt = Math.max(0.5, now - prev.t)
            const dT = cpuT - prev.cpuT
            cpu = dT > 0 ? Math.max(0, Math.min(1, 1 - (cpuI - prev.cpuI) / dT)) : cpu
            rxRate = Math.max(0, (rx - prev.rx) / dt); txRate = Math.max(0, (tx - prev.tx) / dt)
            rdRate = Math.max(0, (rd - prev.rd) / dt); wrRate = Math.max(0, (wr - prev.wr) / dt)
            hCpu = push(hCpu, cpu)
            hMem = push(hMem, mt ? (mt - ma) / mt : 0)
            hNet = push(hNet, rxRate + txRate)
            hDisk = push(hDisk, rdRate + wrRate)
        }
        prev = cur
        cores = nCores; memTotal = mt; memAvail = ma; rxTotal = rx; txTotal = tx; diskFree = df
    }
    function parseSec(out) {
        let s
        try { s = JSON.parse(out) } catch (e) { return }
        const now = Date.now() / 1000
        let lvl = s.firewall ? "ok" : "red"
        const seen = Object.assign({}, secSeen)
        for (const a of (s.alerts || [])) {
            if (now - a.t < 600) lvl = (a.sev === "red" || lvl === "red") ? "red" : "amber"
            if (!seen[a.id]) {
                seen[a.id] = true
                if (secReady && now - a.t < 120)
                    runner.connectSource("notify-send -a 'ZENOS Security' -i " + (a.sev === "red" ? "security-low -u critical" : "security-medium -u normal")
                                         + " '" + a.title + "' '" + a.text + "' #" + a.id)
            }
        }
        secSeen = seen; secLevel = lvl; sec = s; secReady = true
    }
    function ago(t) {
        const d = Math.max(0, Date.now() / 1000 - t)
        return d < 60 ? "just now" : d < 3600 ? Math.round(d / 60) + " min ago" : Math.round(d / 3600) + " h ago"
    }
    // security graph: blocked attempts per 2 s, scaled to the busiest moment (at least 5)
    function scaledN(arr) { const m = Math.max(5, ...arr); return arr.map(v => v / m) }

    // network and disk graphs scale to the busiest moment on screen (at least 1 MB/s)
    function scaled(arr) { const m = Math.max(1048576, ...arr); return arr.map(v => v / m) }

    P5Support.DataSource {
        id: reader
        engine: "executable"
        onNewData: (source, data) => { root.parse(String(data["stdout"])); disconnectSource(source) }
    }
    P5Support.DataSource {
        id: loadReader
        engine: "executable"
        onNewData: (source, data) => { root.load1 = Number(String(data["stdout"]).split(" ")[0]) || 0; disconnectSource(source) }
    }
    P5Support.DataSource {
        id: secReader
        engine: "executable"
        onNewData: (source, data) => { root.parseSec(String(data["stdout"])); disconnectSource(source) }
    }
    Timer {
        interval: 2000; running: true; repeat: true; triggeredOnStart: true
        onTriggered: {
            secReader.connectSource("cat /run/zenos/secstat.json #" + Date.now())
            reader.connectSource("sh -c 'cat /proc/stat /proc/meminfo /proc/net/dev /proc/diskstats; echo ==DF; df -B1 --output=avail / | tail -1' #" + Date.now())
            loadReader.connectSource("cat /proc/loadavg #" + Date.now())
        }
    }
    P5Support.DataSource { id: runner; engine: "executable"; onNewData: (s, d) => disconnectSource(s) }

    // ---- the chip in the top bar: the browser's address-field well ----
    fullRepresentation: MouseArea {
        id: chipArea
        Layout.minimumWidth: chipRow.implicitWidth + 18
        Layout.preferredWidth: chipRow.implicitWidth + 18
        Layout.fillHeight: true
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: panelWin.visible ? panelWin.close() : panelWin.open()
        Rectangle {
            anchors.centerIn: parent
            width: parent.width; height: 20; radius: 6
            border.width: 1; border.color: Qt.rgba(0, 0, 0, 0.5)
            gradient: Gradient {
                GradientStop { position: 0; color: chipArea.containsMouse ? "#1A1A1F" : "#141417" }
                GradientStop { position: 1; color: chipArea.containsMouse ? "#202026" : "#1A1A1E" }
            }
            Rectangle { x: 3; y: 1; width: parent.width - 6; height: 1.5; color: Qt.rgba(0, 0, 0, 0.35) }
            RowLayout {
                id: chipRow
                anchors.centerIn: parent
                spacing: 10
                Repeater {
                    model: [
                        ["CPU", Math.round(root.cpu * 100) + "%", "#0A84FF"],
                        ["MEM", root.human(root.memTotal - root.memAvail) + " / " + root.human(root.memTotal), "#30D158"],
                        ["NET", "↓ " + root.rate(root.rxRate) + "  ↑ " + root.rate(root.txRate), "#BF5AF2"],
                        ["DISK", root.rate(root.rdRate + root.wrRate), "#FF9F0A"],
                        ["SEC", !root.sec.firewall ? "Firewall off" : root.secLevel === "ok" ? root.sec.inbound_blocked + " blocked" : "Alert", root.secColor]
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        spacing: 4
                        Rectangle { width: 6; height: 6; radius: 3; color: modelData[2] }
                        Text { text: modelData[0]; color: "#8E8E93"; font.pixelSize: 10; font.weight: Font.DemiBold; font.family: "Inter" }
                        Text { text: modelData[1]; color: "white"; font.pixelSize: 11; font.weight: Font.Medium; font.family: "Inter" }
                    }
                }
            }
        }
    }

    // ---- the panel with graphs: mirror glass like the Start menu, top right under the bar ----
    Window {
        id: panelWin
        title: "ZENOS System Monitor"
        flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint
        color: "transparent"
        visible: false
        readonly property int pw: 340
        readonly property int topBar: 30
        function open() {
            x = 0; y = 0; width = Screen.width; height = Screen.height
            show(); raise(); requestActivate(); layer.forceActiveFocus()
            const r = [Screen.width - pw - 12, topBar + 8, pw, card.height].join(",")
            runner.connectSource("sh -c 'sleep 0.2; for w in $(xdotool search --name \"^ZENOS System Monitor$\"); do xprop -id $w -f _KDE_NET_WM_BLUR_BEHIND_REGION 32c -set _KDE_NET_WM_BLUR_BEHIND_REGION " + r + "; done' >/dev/null 2>&1")
        }
        function close() { visible = false }

        MouseArea {
            id: layer
            anchors.fill: parent
            onClicked: panelWin.close()
            Keys.onEscapePressed: panelWin.close()
            focus: true

            Rectangle {
                id: card
                x: parent.width - panelWin.pw - 12
                y: panelWin.topBar + 8
                width: panelWin.pw
                height: col.implicitHeight + 32
                radius: 14
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.rgba(0x2C / 255, 0x2C / 255, 0x31 / 255, 0.70) }
                    GradientStop { position: 1; color: Qt.rgba(0x1E / 255, 0x1E / 255, 0x23 / 255, 0.70) }
                }
                border.color: Qt.rgba(0, 0, 0, 0.6)
                border.width: 1
                Rectangle {
                    anchors.fill: parent; anchors.margins: 1; radius: parent.radius - 1
                    gradient: Gradient {
                        GradientStop { position: 0.00; color: Qt.rgba(1, 1, 1, 0.16) }
                        GradientStop { position: 0.18; color: Qt.rgba(1, 1, 1, 0.06) }
                        GradientStop { position: 0.42; color: Qt.rgba(1, 1, 1, 0.0) }
                    }
                }
                Rectangle { x: 10; y: 1; width: parent.width - 20; height: 1; color: Qt.rgba(1, 1, 1, 0.28) }
                MouseArea { anchors.fill: parent }

                ColumnLayout {
                    id: col
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.margins: 16
                    spacing: 14
                    Text { text: "This PC"; color: "white"; font.pixelSize: 14; font.weight: Font.DemiBold; font.family: "Inter" }
                    Repeater {
                        model: [
                            ["CPU", Math.round(root.cpu * 100) + "%", root.cores + " cores · load " + root.load1.toFixed(1), "#0A84FF", root.hCpu],
                            ["Memory", root.human(root.memTotal - root.memAvail) + " of " + root.human(root.memTotal),
                             (root.memTotal ? Math.round(100 * (root.memTotal - root.memAvail) / root.memTotal) : 0) + " % used · " + root.human(root.memAvail) + " available", "#30D158", root.hMem],
                            ["Network", "↓ " + root.rate(root.rxRate) + "   ↑ " + root.rate(root.txRate),
                             "Received " + root.human(root.rxTotal) + " · Sent " + root.human(root.txTotal) + " since start", "#BF5AF2", root.scaled(root.hNet)],
                            ["Disk", root.rate(root.rdRate + root.wrRate),
                             "Read " + root.rate(root.rdRate) + " · Write " + root.rate(root.wrRate) + " · " + root.human(root.diskFree) + " free", "#FF9F0A", root.scaled(root.hDisk)]
                        ]
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 6
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: modelData[0]; color: "#8E8E93"; font.pixelSize: 12; font.weight: Font.DemiBold; font.family: "Inter" }
                                Item { Layout.fillWidth: true }
                                Text { text: modelData[1]; color: "white"; font.pixelSize: 12; font.weight: Font.Medium; font.family: "Inter" }
                            }
                            Graph { Layout.fillWidth: true; Layout.preferredHeight: 44; tint: modelData[3]; values: modelData[4] }
                            Text { text: modelData[2]; color: "#8E8E93"; font.pixelSize: 11; font.family: "Inter" }
                        }
                    }

                    // ---- Security ----
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle { width: 6; height: 6; radius: 3; color: root.secColor }
                            Text { text: "Security"; color: "#8E8E93"; font.pixelSize: 12; font.weight: Font.DemiBold; font.family: "Inter" }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: !root.sec.firewall ? "Firewall off" : root.sec.inbound_blocked + " blocked"
                                color: root.sec.firewall ? "white" : "#FF453A"; font.pixelSize: 12; font.weight: Font.Medium; font.family: "Inter"
                            }
                        }
                        Graph { Layout.fillWidth: true; Layout.preferredHeight: 44; tint: "#FF375F"; values: root.scaledN(root.sec.h_in || []) }
                        Text {
                            text: "Inbound blocked " + root.sec.inbound_blocked + " · Failed sign-ins " + root.sec.auth_failed + " · Contained " + root.sec.outbound_contained
                            color: "#8E8E93"; font.pixelSize: 11; font.family: "Inter"
                        }
                        Repeater {
                            model: (root.sec.alerts || []).slice(-3).reverse()
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.topMargin: 2
                                spacing: 8
                                Rectangle {
                                    Layout.alignment: Qt.AlignTop; Layout.topMargin: 5
                                    width: 6; height: 6; radius: 3; color: modelData.sev === "red" ? "#FF453A" : "#FFD60A"
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: modelData.title; color: "white"; font.pixelSize: 12; font.weight: Font.Medium; font.family: "Inter" }
                                        Item { Layout.fillWidth: true }
                                        Text { text: root.ago(modelData.t); color: "#8E8E93"; font.pixelSize: 11; font.family: "Inter" }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.text; color: "#AEAEB2"; font.pixelSize: 11; font.family: "Inter"; wrapMode: Text.Wrap
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

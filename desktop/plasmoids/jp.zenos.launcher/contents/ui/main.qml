import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support

// ZENOS Launcher: Windows-style Start menu anchored bottom-left. Apps in a vertical list grouped by section.
PlasmoidItem {
    id: root
    readonly property string base: "/home/zenos/.local/share/zenos/icons/"
    property string query: ""
    property int level: 1
    // AI allowed per level (design: L1-L2 all registered, L3 Gov AI + domestic, L4-L5 in-ministry only)
    readonly property var aiAllowed: [["govai","ministryai","externalai"],["govai","ministryai","externalai"],["govai","ministryai"],["ministryai"],["ministryai"]]
    preferredRepresentation: fullRepresentation

    readonly property var groups: [
        { title: "Work", apps: [
            ["Documents", "documents"], ["Sheets", "sheets"], ["Slides", "slides"],
            ["Files", "files"], ["Messenger", "messenger"], ["Calendar", "calendar"],
            ["PDF", "pdf"], ["Images", "images"], ["Video", "video"] ] },
        { title: "Organization", apps: [
            ["Approvals", "approvals"], ["Vault", "vault"], ["External Mail", "mail"], ["Browser", "browser"],
            ["Settings", "settings"] ] },
        { title: "AI", ai: true, apps: [
            ["Gov AI", "govai"], ["Ministry AI", "ministryai"], ["External AI", "externalai"] ] }
    ]

    P5Support.DataSource {
        id: runner
        engine: "executable"
        onNewData: (source, data) => disconnectSource(source)
    }
    P5Support.DataSource {
        id: levelReader
        engine: "executable"
        onNewData: (source, data) => { const n = parseInt(data["stdout"]); if (n >= 1 && n <= 5) root.level = n; disconnectSource(source); }
    }
    function launch(id) {
        runner.connectSource("setsid -f kioclient exec /home/zenos/.local/share/applications/zenos-" + id + ".desktop >> /tmp/zenos-launch.log 2>&1");
        menu.close();
    }

    // Windows-style start area: the ZENOS mark, then a search box; app icons follow to the right
    fullRepresentation: Item {
        Layout.minimumWidth: 280
        Layout.preferredWidth: 280
        Layout.fillHeight: true
        MouseArea {
            id: startBtn
            anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
            width: 44
            hoverEnabled: true
            onClicked: menu.visible ? menu.close() : menu.open()
            Rectangle { anchors.centerIn: parent; width: 36; height: 36; radius: 6; color: Qt.rgba(1, 1, 1, startBtn.containsMouse ? 0.10 : 0) }
            Kirigami.Icon {
                anchors.centerIn: parent
                width: 24; height: 24
                source: root.base + "zenos-mark.svg"
                roundToIconSize: false
            }
        }
        MouseArea {
            id: searchBtn
            anchors.left: startBtn.right; anchors.leftMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            width: 220; height: 30
            hoverEnabled: true
            onClicked: menu.visible ? menu.close() : menu.open()
            Rectangle {
                anchors.fill: parent; radius: 15
                color: Qt.rgba(1, 1, 1, searchBtn.containsMouse ? 0.14 : 0.08)
                border.color: Qt.rgba(1, 1, 1, 0.12); border.width: 1
            }
            Kirigami.Icon {
                id: mag
                anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                width: 16; height: 16
                source: "search"
                color: "white"; isMask: true
                opacity: 0.7
            }
            QQC2.Label {
                anchors.left: mag.right; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                text: "Search"
                color: Qt.rgba(1, 1, 1, 0.6)
                font.pixelSize: 14; font.family: "Inter"
            }
        }
    }

    // full-screen transparent layer catches outside-clicks; the menu panel sits bottom-left
    Window {
        id: menu
        flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint
        color: "transparent"
        visible: false
        readonly property int taskbar: 40
        readonly property int panelW: 380
        readonly property int panelH: Math.min(600, Screen.height - taskbar - 24)
        function open() {
            levelReader.connectSource("cat $HOME/.config/zenos/level 2>/dev/null || echo 1");
            root.query = ""; search.text = "";
            x = 0; y = 0; width = Screen.width; height = Screen.height;
            show(); raise(); requestActivate(); search.forceActiveFocus();
        }
        function close() { visible = false; }

        MouseArea {
            anchors.fill: parent
            onClicked: menu.close()
            Keys.onEscapePressed: menu.close()
            focus: true

            // the Start panel, anchored bottom-left just above the taskbar
            Rectangle {
                id: panel
                x: 8
                y: parent.height - menu.taskbar - menu.panelH - 8
                width: menu.panelW
                height: menu.panelH
                radius: 14
                color: Qt.rgba(0.07, 0.10, 0.18, 0.96)
                border.color: Qt.rgba(1, 1, 1, 0.12)
                border.width: 1
                // swallow clicks inside the panel so it doesn't close
                MouseArea { anchors.fill: parent }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12

                    // header: current user + clearance
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Rectangle {
                            width: 34; height: 34; radius: 17
                            gradient: Gradient {
                                GradientStop { position: 0; color: "#60A5FA" }
                                GradientStop { position: 1; color: "#2563EB" }
                            }
                            Text { anchors.centerIn: parent; text: "Z"; color: "white"; font.bold: true; font.family: "Inter" }
                        }
                        ColumnLayout {
                            spacing: 0
                            Text { text: "ZENOS User"; color: "white"; font.pixelSize: 14; font.weight: Font.DemiBold; font.family: "Inter" }
                            Text { text: "Clearance L" + root.level; color: Qt.rgba(1,1,1,0.55); font.pixelSize: 11; font.family: "Inter" }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    // search
                    Rectangle {
                        Layout.fillWidth: true
                        height: 38; radius: 9
                        color: Qt.rgba(1, 1, 1, 0.08)
                        border.color: Qt.rgba(1, 1, 1, 0.16)
                        QQC2.TextField {
                            id: search
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            placeholderText: "Search apps"
                            background: null
                            color: "white"
                            placeholderTextColor: Qt.rgba(1, 1, 1, 0.55)
                            font.pixelSize: 14
                            font.family: "Inter"
                            onTextChanged: root.query = text.toLowerCase()
                            Keys.onEscapePressed: menu.close()
                        }
                    }

                    // scrollable app list, grouped by section (Windows "all apps" style)
                    QQC2.ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: panel.width - 28
                            spacing: 6

                            Repeater {
                                model: root.groups
                                delegate: ColumnLayout {
                                    id: section
                                    required property var modelData
                                    Layout.fillWidth: true
                                    readonly property var shown: modelData.apps.filter(a => (root.query === "" || a[0].toLowerCase().indexOf(root.query) >= 0) && (!modelData.ai || root.aiAllowed[root.level - 1].indexOf(a[1]) >= 0))
                                    visible: shown.length > 0
                                    spacing: 2

                                    Text {
                                        text: section.modelData.title
                                        color: Qt.rgba(1, 1, 1, 0.5)
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                        font.family: "Inter"
                                        Layout.topMargin: 8
                                        Layout.leftMargin: 4
                                    }

                                    Repeater {
                                        model: section.shown
                                        delegate: Rectangle {
                                            id: rowItem
                                            required property var modelData
                                            Layout.fillWidth: true
                                            height: 42
                                            radius: 8
                                            color: rowHover.containsMouse ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 8
                                                anchors.rightMargin: 8
                                                spacing: 12
                                                Image {
                                                    width: 26; height: 26
                                                    Layout.preferredWidth: 26
                                                    Layout.preferredHeight: 26
                                                    sourceSize: Qt.size(52, 52)
                                                    source: root.base + "zenos-" + rowItem.modelData[1] + ".svg"
                                                }
                                                Text {
                                                    text: rowItem.modelData[0]
                                                    color: "white"
                                                    font.pixelSize: 14
                                                    font.family: "Inter"
                                                    Layout.fillWidth: true
                                                }
                                            }
                                            MouseArea {
                                                id: rowHover
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: root.launch(rowItem.modelData[1])
                                            }
                                        }
                                    }
                                }
                            }

                            // level note at the end of the list
                            Text {
                                Layout.fillWidth: true
                                Layout.topMargin: 10
                                Layout.leftMargin: 4
                                wrapMode: Text.WordWrap
                                text: root.level >= 4 ? "At L" + root.level + ", external AI is hidden. In-ministry AI only." : (root.level === 3 ? "At L3, external AI is hidden. Gov AI and domestic AI only." : "")
                                visible: text.length > 0
                                color: Qt.rgba(1, 1, 1, 0.45)
                                font.pixelSize: 11
                                font.family: "Inter"
                            }
                        }
                    }
                }
            }
        }
    }
}

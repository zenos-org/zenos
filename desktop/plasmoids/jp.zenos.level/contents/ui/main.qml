import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support

// ZENOS level indicator for the graphite top bar.
// Preview build: click the chip to cycle L1-L5. Final build reads the level of the focused document.
PlasmoidItem {
    id: root
    property int level: 1
    readonly property var colors: ["#0A84FF", "#30D158", "#30D158", "#FF453A", "#C7C7CC"]   // same as the ZENOS Browser
    readonly property var notes: [
        "Public · Any registered AI allowed",
        "Confidentiality 2 · No-training AI and Gov AI only",
        "Confidentiality 3 · Gov AI and domestic AI only",
        "Important Economic Security Information · External AI off",
        "Specially Designated Secret · Isolated in-ministry AI only"
    ]
    preferredRepresentation: fullRepresentation
    P5Support.DataSource { id: sh; engine: "executable"; onNewData: (src, d) => disconnectSource(src) }
    onLevelChanged: sh.connectSource("mkdir -p $HOME/.config/zenos && echo " + level + " > $HOME/.config/zenos/level")
    Component.onCompleted: sh.connectSource("mkdir -p $HOME/.config/zenos && echo 1 > $HOME/.config/zenos/level")

    fullRepresentation: RowLayout {
        spacing: 10
        Layout.minimumWidth: implicitWidth
        Rectangle {   // the ZENOS Browser address field look: dark inset well
            Layout.alignment: Qt.AlignVCenter
            radius: 6
            border.width: 1
            border.color: Qt.rgba(0, 0, 0, 0.5)
            gradient: Gradient {
                GradientStop { position: 0; color: "#141417" }
                GradientStop { position: 1; color: "#1A1A1E" }
            }
            implicitWidth: chip.implicitWidth + 16
            implicitHeight: 20
            Rectangle { x: 3; y: 1; width: parent.width - 6; height: 1.5; color: Qt.rgba(0, 0, 0, 0.35) }
            RowLayout {
                id: chip
                anchors.centerIn: parent
                spacing: 6
                Rectangle { width: 7; height: 7; radius: 3.5; color: root.colors[root.level - 1] }
                PlasmaComponents.Label { text: "L" + root.level; font.bold: true; font.pixelSize: 11 }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.level = root.level % 5 + 1
            }
        }
        PlasmaComponents.Label {
            Layout.alignment: Qt.AlignVCenter
            text: root.notes[root.level - 1]
            color: "#C7C7CC"
            font.pixelSize: 12
            font.weight: Font.Medium
        }
    }
}

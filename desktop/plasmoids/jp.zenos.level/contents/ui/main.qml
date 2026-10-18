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
    readonly property var colors: ["#E5E7EB", "#38BDF8", "#22C55E", "#EF4444", "#A1A1AA"]
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
        Rectangle {
            Layout.alignment: Qt.AlignVCenter
            radius: 5
            color: Qt.rgba(1, 1, 1, 0.10)
            implicitWidth: chip.implicitWidth + 16
            implicitHeight: 20
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
            opacity: 0.8
            font.pixelSize: 12
        }
    }
}

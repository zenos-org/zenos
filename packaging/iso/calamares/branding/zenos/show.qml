/* ZENOS installer slideshow (Figma: "Installer — slide while installing"). Calamares slideshow API 2. */
import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation
    function onActivate() { }
    function onLeave() { }

    Rectangle { anchors.fill: parent; color: "#0E0F13"; z: -1 }

    Slide {
        Row {
            id: levels
            spacing: 10
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top; anchors.topMargin: 40
            Repeater {
                model: [ ["L1", "#E5E7EB", "Basic"], ["L2–3", "#38BDF8", "Green"], ["L4", "#EF4444", "Red"], ["L5", "#A1A1AA", "Black"] ]
                Rectangle {
                    width: 120; height: 84; radius: 10
                    color: "#17181D"; border.color: "#25262D"
                    Rectangle { x: 12; y: 12; height: 20; width: chip.implicitWidth + 12; radius: 4; color: modelData[1]; opacity: 0.2 }
                    Text { id: chip; x: 18; y: 15; text: modelData[0]; color: modelData[1]; font.pixelSize: 11; font.bold: true }
                    Text { x: 12; y: 46; text: modelData[2]; color: "#E7E8EC"; font.pixelSize: 15; font.weight: Font.DemiBold }
                }
            }
        }
        Text {
            id: title
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: levels.bottom; anchors.topMargin: 30
            text: "Every file carries its level"
            color: "#F2F4F6"; font.pixelSize: 20; font.weight: Font.DemiBold
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: title.bottom; anchors.topMargin: 12
            width: 480; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
            text: "Files saved into a level folder are sealed. Opening above your level asks your officers, " +
                  "who approve on their own devices. The installation finishes in a few minutes."
            color: "#9AA0AB"; font.pixelSize: 13; lineHeight: 1.3
        }
    }
}

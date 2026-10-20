import QtQuick

// The ZENOS Browser address field, shared by every input on the desktop (Figma 33:2):
// gradient #141417 -> #1A1A1E, black border at 50 %, a darker inner top edge for the inset shadow.
Rectangle {
    property bool lit: false
    radius: 9
    border.width: 1
    border.color: Qt.rgba(0, 0, 0, 0.5)
    gradient: Gradient {
        GradientStop { position: 0; color: lit ? "#1A1A1F" : "#141417" }
        GradientStop { position: 1; color: lit ? "#202026" : "#1A1A1E" }
    }
    Rectangle {   // inset shadow along the top inner edge
        x: parent.radius / 2; y: 1
        width: parent.width - parent.radius; height: 2
        radius: 1
        color: Qt.rgba(0, 0, 0, 0.35)
    }
}

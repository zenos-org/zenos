// ZENOS login screen (Figma: Login). The desktop gradient, clock, the person, one password field.
import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    width: 1280; height: 800
    color: "#0D1430"
    property string user: userModel.lastUser || ""
    property string realName: ""
    property int session: sessionModel.lastIndex

    Image { anchors.fill: parent; source: config.background || ""; fillMode: Image.PreserveAspectCrop; asynchronous: false }

    Repeater {                               // the person to sign in: the last one, else the first
        model: userModel
        delegate: Item {
            Component.onCompleted: {
                if (root.user === "" && index === 0) root.user = model.name
                if (model.name === root.user || (root.realName === "" && index === 0)) root.realName = model.realName || model.name
            }
        }
    }

    function initials(n) {
        var p = (n || "").trim().split(/\s+/)
        return ((p[0] || "").charAt(0) + (p.length > 1 ? p[p.length - 1].charAt(0) : "")).toUpperCase()
    }

    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.14
        spacing: 6
        Text { id: clock; anchors.horizontalCenter: parent.horizontalCenter; color: "white"; font.family: "Inter"; font.weight: Font.Light; font.pixelSize: 88
               text: Qt.formatTime(new Date(), "h:mm") }
        Text { id: day; anchors.horizontalCenter: parent.horizontalCenter; color: "#C9CCD3"; font.family: "Inter"; font.pixelSize: 22
               text: Qt.formatDate(new Date(), "dddd, MMMM d") }
        Timer { interval: 10000; running: true; repeat: true
                onTriggered: { clock.text = Qt.formatTime(new Date(), "h:mm"); day.text = Qt.formatDate(new Date(), "dddd, MMMM d") } }
    }

    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.44
        spacing: 14
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 112; height: 112; radius: 56
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#6E5BFF" } GradientStop { position: 1; color: "#D83AB0" } }
            Text { anchors.centerIn: parent; text: root.initials(root.realName); color: "white"; font.family: "Inter"; font.weight: Font.DemiBold; font.pixelSize: 38 }
        }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.realName; color: "white"; font.family: "Inter"; font.weight: Font.Medium; font.pixelSize: 22 }
        TextField {
            id: pw
            anchors.horizontalCenter: parent.horizontalCenter
            width: 360; height: 46
            echoMode: TextInput.Password
            placeholderText: "Password"
            placeholderTextColor: "#8B8F98"
            color: "white"; font.family: "Inter"; font.pixelSize: 16
            leftPadding: 18
            focus: true
            background: Rectangle { radius: 14; color: Qt.rgba(0.055, 0.06, 0.075, 0.7); border.color: Qt.rgba(1, 1, 1, pw.activeFocus ? 0.35 : 0.18); border.width: 1 }
            Keys.onReturnPressed: sddm.login(root.user, pw.text, root.session)
            Keys.onEnterPressed: sddm.login(root.user, pw.text, root.session)
        }
        Text { id: msg; anchors.horizontalCenter: parent.horizontalCenter; color: "#FCA5A5"; font.family: "Inter"; font.pixelSize: 14; text: "" }
    }

    Connections {
        target: sddm
        function onLoginFailed() { msg.text = "That password did not work. Try again."; pw.text = ""; pw.forceActiveFocus() }
    }

    Text { x: 36; anchors.bottom: parent.bottom; anchors.bottomMargin: 30; text: "ZENOS"; color: Qt.rgba(1, 1, 1, 0.7)
           font.family: "Inter"; font.weight: Font.DemiBold; font.pixelSize: 16 }

    Row {
        anchors.right: parent.right; anchors.rightMargin: 36
        anchors.bottom: parent.bottom; anchors.bottomMargin: 30
        spacing: 32
        Repeater {
            model: [["Sleep", sddm.canSuspend, 0], ["Restart", sddm.canReboot, 1], ["Shut down", sddm.canPowerOff, 2]]
            delegate: Text {
                visible: modelData[1]
                text: modelData[0]; color: area.containsMouse ? "white" : "#C9CCD3"; font.family: "Inter"; font.pixelSize: 15
                MouseArea { id: area; anchors.fill: parent; hoverEnabled: true
                    onClicked: modelData[2] === 0 ? sddm.suspend() : modelData[2] === 1 ? sddm.reboot() : sddm.powerOff() }
            }
        }
    }
    Component.onCompleted: pw.forceActiveFocus()
}

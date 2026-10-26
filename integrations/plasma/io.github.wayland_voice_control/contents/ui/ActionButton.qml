import QtQuick
import QtQuick.Controls

Button {
    id: root
    implicitHeight: Math.max(44, contentItem.implicitHeight + topPadding + bottomPadding,
                             implicitBackgroundHeight + topInset + bottomInset)
    Accessible.name: text
    contentItem: Label {
        text: root.text
        font: root.font
        color: root.palette.buttonText
        enabled: root.enabled
        wrapMode: Text.Wrap
        elide: Text.ElideNone
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}

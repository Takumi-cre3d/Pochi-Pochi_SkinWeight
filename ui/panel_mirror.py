# PochiPochi_SkinWeight/ui/panel_mirror.py

from .qt_compat import (
    QWidget, QHBoxLayout, QGroupBox, QPushButton, QLabel, QtCore
)
from . import style

class MirrorPanel(QWidget):
    # シグナル（main_windowから接続推奨）
    pasteMirrorRequested = QtCore.Signal()
    mirrorPos2NegRequested = QtCore.Signal()
    mirrorNeg2PosRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        group = QGroupBox("ミラー", self)
        group.setStyleSheet(style.group_box)
        hbox = QHBoxLayout(group)

        btn_paste_mirror = QPushButton("Paste Mirror")
        btn_paste_mirror.clicked.connect(self.on_paste_mirror)
        hbox.addWidget(btn_paste_mirror)

        btn_pos2neg = QPushButton("+X→-X")
        btn_pos2neg.clicked.connect(self.on_mirror_pos2neg)
        hbox.addWidget(btn_pos2neg)

        btn_neg2pos = QPushButton("-X→+X")
        btn_neg2pos.clicked.connect(self.on_mirror_neg2pos)
        hbox.addWidget(btn_neg2pos)

        self.status_label = QLabel("", self)
        hbox.addWidget(self.status_label)
        group.setLayout(hbox)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(group)
        self.setLayout(main_layout)

    def on_paste_mirror(self):
        self.pasteMirrorRequested.emit()

    def on_mirror_pos2neg(self):
        self.mirrorPos2NegRequested.emit()

    def on_mirror_neg2pos(self):
        self.mirrorNeg2PosRequested.emit()

    def set_status(self, message):
        self.status_label.setText(message)

    def clear_status(self):
        self.status_label.setText("")
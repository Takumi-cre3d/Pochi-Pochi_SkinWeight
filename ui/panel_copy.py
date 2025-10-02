# PochiPochi_SkinWeight/ui/panel_copy.py

from .qt_compat import (
    QWidget, QHBoxLayout, QGroupBox, QLabel, QPushButton, QtCore
)
from . import style

class CopyPanel(QWidget):
    # シグナル（必要なら）
    copyRequested = QtCore.Signal()
    pasteRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        group = QGroupBox("コピー", self)
        group.setStyleSheet(style.group_box)
        hbox = QHBoxLayout(group)
        hbox.addWidget(QLabel("選択頂点のウェイト:", self))

        btn_copy = QPushButton("Copy")
        btn_copy.clicked.connect(self.on_copy)
        hbox.addWidget(btn_copy)
        btn_paste = QPushButton("Paste")
        btn_paste.clicked.connect(self.on_paste)
        hbox.addWidget(btn_paste)

        #（ペースト状態やステータス表示ラベルを右端に用意しても良い）
        self.status_label = QLabel("", self)
        hbox.addWidget(self.status_label)
        group.setLayout(hbox)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(group)
        self.setLayout(main_layout)

        # UIから外部でステータスを見やすいようにプロパティ化
        self._status_message = ""

    def on_copy(self):
        self.copyRequested.emit()

    def on_paste(self):
        self.pasteRequested.emit()

    def set_status(self, message):
        self.status_label.setText(message)
        self._status_message = message

    def clear_status(self):
        self.status_label.setText("")
        self._status_message = ""
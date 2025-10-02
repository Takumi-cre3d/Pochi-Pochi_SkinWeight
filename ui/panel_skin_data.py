# PochiPochi_SkinWeight/ui/panel_skin_data.py

from .qt_compat import QWidget, QVBoxLayout, QPushButton, QLabel, QtCore
from . import style

class SkinDataPanel(QWidget):
    # シグナル → main_windowで接続し、skinDataノード生成処理へつなげる
    edit_skin_weights_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        vbox = QVBoxLayout(self)

        # ラベル説明（自由に編集可）
        label = QLabel(
            "このオブジェクトにはまだ編集用のスキンデータがありません。\n"
            "下のボタンからskinDataノードを作成してウェイト編集可能にしてください。"
        )
        label.setWordWrap(True)
        vbox.addWidget(label)

        # Edit Skin Weights ボタン
        self.edit_btn = QPushButton("Edit Skin Weights")
        self.edit_btn.setStyleSheet(style.preset_button_style(0.5))  # 例として黄色っぽい色
        self.edit_btn.setMinimumWidth(220)
        self.edit_btn.setMinimumHeight(36)
        self.edit_btn.setFont(self.bold_big_font())
        self.edit_btn.clicked.connect(self.edit_skin_weights_requested)
        vbox.addWidget(self.edit_btn)

        vbox.addStretch()
        self.setLayout(vbox)

    def bold_big_font(self):
        f = self.font()
        f.setPointSize(15)
        f.setBold(True)
        return f
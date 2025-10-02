# PochiPochi_SkinWeight/ui/panel_weight.py

from .qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QGroupBox, QtCore
)
from . import style
from functools import partial
from maya import cmds
from ..core.joint_ops import get_skin_influences, get_vertex_influences
from ..core.weight_ops import set_weight, find_related_skin_cluster

class WeightPanel(QGroupBox):
    weightChanged = QtCore.Signal(float)   # set/preset/relativeで発行

    def __init__(self, parent=None):
        super().__init__("ウェイト設定", parent)
        self.setStyleSheet(style.group_box)
        vbox = QVBoxLayout(self)

        # ジョイント名欄　※編集可能
        joint_hbox = QHBoxLayout()
        self.joint_input = QLineEdit(self)
        self.joint_input.setPlaceholderText("ジョイント名")
        joint_hbox.addWidget(QLabel("ジョイント名:"))
        joint_hbox.addWidget(self.joint_input)
        vbox.addLayout(joint_hbox)

        # プリセットボタンのみ
        preset_hbox = QHBoxLayout()
        for val in [0, 0.1, 0.25, 0.5, 0.75, 1.0]:
            btn = QPushButton(str(val))
            btn.setStyleSheet(style.preset_button_style(val))
            btn.clicked.connect(partial(self.on_set_weight, val))
            preset_hbox.addWidget(btn)
        vbox.addLayout(preset_hbox)

        # ---- 相対増減 ----
        delta_hbox = QHBoxLayout()
        btn_sub = QPushButton("－")
        btn_sub.setStyleSheet(style.relative_button)
        btn_sub.setFont(self.bold_big_font())
        btn_sub.clicked.connect(lambda _=None: self.on_relative_clicked(negative=True))
        delta_hbox.addWidget(btn_sub)

        self.relative_input = QLineEdit(self)
        self.relative_input.setStyleSheet(style.relative_input)
        self.relative_input.setText("0.05")
        self.relative_input.setAlignment(QtCore.Qt.AlignCenter)
        delta_hbox.addWidget(self.relative_input)

        btn_add = QPushButton("＋")
        btn_add.setStyleSheet(style.relative_button)
        btn_add.setFont(self.bold_big_font())
        btn_add.clicked.connect(lambda _=None: self.on_relative_clicked(negative=False))
        delta_hbox.addWidget(btn_add)
        vbox.addLayout(delta_hbox)

    def set_joint_name(self, name):
        self.joint_input.setText(name)
    def get_joint_name(self):
        return self.joint_input.text().strip()

    def on_set_weight(self, value):
        joint = self.get_joint_name()
        verts = cmds.ls(selection=True, flatten=True)
        if not verts or not joint:
            return
        mesh = verts[0].split('.')[0]
        skin = find_related_skin_cluster(mesh)
        for v in verts:
            cmds.skinPercent(skin, v, transformValue=[(joint, value)])
        self.weightChanged.emit(value)

    def get_relative_delta(self):
        try:
            val = float(self.relative_input.text())
            if val < 0:
                val = abs(val)
            return val
        except Exception:
            return 0.05

    def on_relative_clicked(self, negative=False):
        delta = self.get_relative_delta()
        if negative:
            delta = -delta
        joint = self.get_joint_name()
        verts = cmds.ls(selection=True, flatten=True)
        if not verts or not joint:
            return
        mesh = verts[0].split('.')[0]
        skin_cluster = find_related_skin_cluster(mesh)
        for v in verts:
            curr = cmds.skinPercent(skin_cluster, v, query=True, transform=joint)
            new_val = min(max(curr + delta, 0.0), 1.0)
            cmds.skinPercent(skin_cluster, v, transformValue=[(joint, new_val)])
        self.weightChanged.emit(delta)

    def bold_big_font(self):
        f = self.font()
        f.setPointSize(18)
        f.setBold(True)
        return f
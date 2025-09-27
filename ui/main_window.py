from .qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QListWidget,
    QGroupBox, QWidget, wrapinstance, QtCore
)
from maya import OpenMayaUI as omui
from maya import cmds
from functools import partial
from ..core.joint_ops import get_skin_influences, get_vertex_influences
from ..core.weight_ops import set_weight, add_weight, find_related_skin_cluster
from ..core import weight_ops
from . import style

def get_maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapinstance(int(ptr), QDialog)

class PochiPochiSkinWeightWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or get_maya_main_window())
        self.setWindowTitle("Pochi-Pochi SkinWeight")
        self.setMinimumSize(750, 400)

        main_layout = QHBoxLayout(self)

        # 左：influence
        left_widget = QWidget(self)
        left_vbox = QVBoxLayout(left_widget)
        left_vbox.addWidget(QLabel("モデルのジョイント一覧 (Skin Influences)", left_widget))

        self.influence_search = QLineEdit(left_widget)
        self.influence_search.setPlaceholderText("ジョイント名で検索（部分一致）")
        self.influence_search.textChanged.connect(self.apply_influence_filter)
        left_vbox.addWidget(self.influence_search)

        self.influence_list = QListWidget(left_widget)
        self.influence_list.itemClicked.connect(self.on_influence_item_clicked)
        left_vbox.addWidget(self.influence_list)
        main_layout.addWidget(left_widget, 1)

        # 真ん中：weight/copy/mirrorパネル
        center_widget = QWidget(self)
        center_vbox = QVBoxLayout(center_widget)
        center_vbox.addWidget(QLabel("ウェイト操作", center_widget))
        center_vbox.addWidget(self.create_weight_panel())
        center_vbox.addWidget(self.create_copy_panel())
        center_vbox.addWidget(self.create_mirror_panel())
        center_vbox.addStretch()
        self.status = QLabel("", center_widget)
        self.status.setStyleSheet(style.status_label)
        center_vbox.addWidget(self.status)
        main_layout.addWidget(center_widget, 2)

        # 右：頂点influence
        right_widget = QWidget(self)
        right_vbox = QVBoxLayout(right_widget)
        right_vbox.addWidget(QLabel("頂点のウエイト情報 (Vertex Influences)", right_widget))
        self.vertex_weight_list = QListWidget(right_widget)
        self.vertex_weight_list.itemClicked.connect(self.on_vertex_weight_item_clicked)
        right_vbox.addWidget(self.vertex_weight_list)
        main_layout.addWidget(right_widget, 1)

        self.all_influences = []
        self.copied_weights = None

        self.refresh_influence_list()
        self.refresh_vertex_weight_list()
        self.start_selection_monitoring()

    def create_weight_panel(self):
        group = QGroupBox("ウェイト設定", self)
        group.setStyleSheet(style.group_box)
        vbox = QVBoxLayout(group)

        joint_hbox = QHBoxLayout()
        self.joint_input = QLineEdit(self)
        self.joint_input.setPlaceholderText("ジョイント名")
        joint_hbox.addWidget(QLabel("ジョイント名:"))
        joint_hbox.addWidget(self.joint_input)
        vbox.addLayout(joint_hbox)

        # プリセットボタン
        preset_hbox = QHBoxLayout()
        for val in [0, 0.1, 0.25, 0.5, 0.75, 1.0]:
            btn = QPushButton(str(val))
            btn.setStyleSheet(style.preset_button_style(val))
            btn.clicked.connect(partial(self.set_weight_preset, val))
            preset_hbox.addWidget(btn)
        vbox.addLayout(preset_hbox)

        # 相対ボタン＋入力欄
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

        return group

    def create_copy_panel(self):
        group = QGroupBox("コピー", self)
        group.setStyleSheet(style.group_box)
        hbox = QHBoxLayout(group)
        hbox.addWidget(QLabel("選択頂点のウェイト:", self))
        btn_copy = QPushButton("Copy")
        btn_copy.clicked.connect(self.on_copy_clicked)
        btn_paste = QPushButton("Paste")
        btn_paste.clicked.connect(self.on_paste_clicked)
        hbox.addWidget(btn_copy)
        hbox.addWidget(btn_paste)
        return group

    def create_mirror_panel(self):
        group = QGroupBox("ミラー", self)
        group.setStyleSheet(style.group_box)
        hbox = QHBoxLayout(group)
        btn_paste_mirror = QPushButton("Paste Mirror")
        btn_paste_mirror.clicked.connect(self.on_paste_mirror_clicked)
        btn_pos2neg = QPushButton("+X→-X")
        btn_pos2neg.clicked.connect(self.on_mirror_pos2neg)
        btn_neg2pos = QPushButton("-X→+X")
        btn_neg2pos.clicked.connect(self.on_mirror_neg2pos)
        hbox.addWidget(btn_paste_mirror)
        hbox.addWidget(btn_pos2neg)
        hbox.addWidget(btn_neg2pos)
        return group

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
        try:
            verts, joint = self.get_targets()
            mesh = verts[0].split('.')[0]
            skin_cluster = find_related_skin_cluster(mesh)
            for v in verts:
                curr = cmds.skinPercent(skin_cluster, v, query=True, transform=joint)
                new_val = min(max(curr + delta, 0.0), 1.0)
                cmds.skinPercent(skin_cluster, v, transformValue=[(joint, new_val)])
            self.status.setText(f"{delta:+.3f}加減")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.status.setText(str(e))

    def bold_big_font(self):
        f = self.font()
        f.setPointSize(18)
        f.setBold(True)
        return f

    def update_joint_highlight(self, joint_name):
        found = self.influence_list.findItems(joint_name, QtCore.Qt.MatchExactly)
        if found:
            self.influence_list.setCurrentItem(found[0])
        else:
            self.influence_list.setCurrentItem(None)
        for i in range(self.vertex_weight_list.count()):
            item = self.vertex_weight_list.item(i)
            if item.text().split(":", 1)[0].strip() == joint_name:
                self.vertex_weight_list.setCurrentItem(item)
                break
        else:
            self.vertex_weight_list.setCurrentItem(None)

    def refresh_influence_list(self):
        sel = cmds.ls(selection=True, long=True)
        self.all_influences = []
        self.influence_list.clear()
        if not sel:
            self.influence_list.addItem("モデル未選択")
            return
        mesh = sel[0].split('.')[0]
        influences = get_skin_influences(mesh)
        if not influences:
            self.influence_list.addItem("スキンクラスタなし")
            return
        self.all_influences = influences
        phrase = self.influence_search.text().strip().lower()
        for joint in influences:
            if not phrase or phrase in joint.lower():
                self.influence_list.addItem(joint)

    def apply_influence_filter(self):
        self.refresh_influence_list()
        joint_name = self.joint_input.text().strip()
        if joint_name:
            self.update_joint_highlight(joint_name)

    def on_influence_item_clicked(self, item):
        joint_name = item.text()
        if not joint_name or "未選択" in joint_name or "なし" in joint_name or "該当ジョイントがありません" in joint_name:
            return
        self.joint_input.setText(joint_name)
        self.update_joint_highlight(joint_name)

    def on_vertex_weight_item_clicked(self, item):
        text = item.text()
        if ":" not in text or "未選択" in text or "なし" in text:
            return
        joint_name = text.split(":", 1)[0].strip()
        self.joint_input.setText(joint_name)
        self.update_joint_highlight(joint_name)

    def refresh_vertex_weight_list(self):
        sel = cmds.ls(selection=True, flatten=True)
        verts = [s for s in sel if ".vtx[" in s]
        self.vertex_weight_list.clear()
        if not verts:
            self.vertex_weight_list.addItem("頂点未選択")
            self.joint_input.setText("")
            self.update_joint_highlight("")
            return
        vtx = verts[0]
        infos = get_vertex_influences(vtx)
        if not infos:
            self.vertex_weight_list.addItem("skinned頂点でないかウェイトなし")
            self.joint_input.setText("")
            self.update_joint_highlight("")
            return
        for joint, value in infos:
            self.vertex_weight_list.addItem(f"{joint} : {value:.4f}")
        first_joint = infos[0][0]
        self.joint_input.setText(first_joint)
        self.update_joint_highlight(first_joint)

    def get_targets(self):
        verts = cmds.ls(selection=True, flatten=True)
        joint = self.joint_input.text().strip()
        if not verts:
            self.status.setText("頂点を選択してください")
            raise RuntimeError
        if not joint:
            self.status.setText("ジョイント名を入力してください")
            raise RuntimeError
        return verts, joint

    def set_weight_preset(self, value, _checked=None):
        try:
            verts, joint = self.get_targets()
            set_weight(verts, joint, value)
            self.status.setText(f"{value}でセット")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.status.setText(str(e))

    def on_set_clicked(self):
        try:
            value = float(self.set_value_input.text())
        except Exception:
            self.status.setText("数値エラー")
            return
        try:
            verts, joint = self.get_targets()
            set_weight(verts, joint, value)
            self.status.setText(f"{value}でセット")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.status.setText(str(e))

    def on_copy_clicked(self):
        try:
            self.copied_weights = weight_ops.copy_weights()
            self.status.setText("コピー済")
        except Exception as e:
            self.status.setText(str(e))

    def on_paste_clicked(self):
        try:
            weight_ops.paste_weights(self.copied_weights)
            self.status.setText("ペーストOK")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.status.setText(str(e))

    def on_paste_mirror_clicked(self):
        try:
            weight_ops.paste_mirror_weights(self.copied_weights)
            self.status.setText("Paste Mirror OK")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.status.setText(str(e))

    def on_mirror_pos2neg(self):
        try:
            weight_ops.mirror_weights_x_pos2neg()
            self.status.setText("+X→-X 完了")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.status.setText(str(e))

    def on_mirror_neg2pos(self):
        try:
            weight_ops.mirror_weights_x_neg2pos()
            self.status.setText("-X→+X 完了")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.status.setText(str(e))

    def start_selection_monitoring(self):
        import maya.cmds as cmds
        attr = "_ppsw_selection_job"
        if hasattr(self, attr):
            try:
                cmds.scriptJob(kill=getattr(self, attr), force=True)
            except Exception:
                pass
        jobnum = cmds.scriptJob(
            event=["SelectionChanged", self.on_selection_changed],
            killWithScene=True, protected=True
        )
        setattr(self, attr, jobnum)

    def on_selection_changed(self, *args):
        self.refresh_influence_list()
        self.refresh_vertex_weight_list()

    def closeEvent(self, event):
        if hasattr(self, "_ppsw_selection_job"):
            try:
                import maya.cmds as cmds
                cmds.scriptJob(kill=getattr(self, "_ppsw_selection_job"), force=True)
            except Exception:
                pass
        super().closeEvent(event)
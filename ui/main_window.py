from .qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QStackedWidget, QGroupBox, QWidget, wrapinstance, QtCore
)
from maya import OpenMayaUI as omui
from maya import cmds

from .panel_weight import WeightPanel
from .panel_copy import CopyPanel
from .panel_mirror import MirrorPanel
from .panel_skin_data import SkinDataPanel
from .panel_layers import PanelLayers
from . import style
from ..core.joint_ops import get_skin_influences, get_vertex_influences
from ..core.skin_data import (
    find_related_skin_cluster, find_skin_data_node, make_or_get_skin_data_node)
from ..core.weight_ops import (
    set_weight, add_weight, copy_weights, paste_weights, paste_mirror_weights,
    mirror_weights_x_pos2neg, mirror_weights_x_neg2pos
)
from ..core.skin_layer import SkinLayerManager
import json

def get_maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapinstance(int(ptr), QDialog)

class PochiPochiSkinWeightWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or get_maya_main_window())
        self.setWindowTitle("Pochi-Pochi SkinWeight")
        self.setMinimumSize(900, 550)
        main_layout = QHBoxLayout(self)

        # --- 左パネル
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

        # --- 中央パネル
        center_stack = QStackedWidget(self)
        self.empty_panel = SkinDataPanel(self)
        self.edit_panel = QWidget(self)
        edit_vbox = QVBoxLayout(self.edit_panel)
        self.weight_panel = WeightPanel(self)
        self.copy_panel = CopyPanel(self)
        self.mirror_panel = MirrorPanel(self)
        edit_vbox.addWidget(self.weight_panel)
        edit_vbox.addWidget(self.copy_panel)
        edit_vbox.addWidget(self.mirror_panel)
        self.status = QLabel("", self)
        self.status.setStyleSheet(style.status_label)
        edit_vbox.addWidget(self.status)
        self.edit_panel.setLayout(edit_vbox)
        center_stack.addWidget(self.empty_panel)
        center_stack.addWidget(self.edit_panel)
        self.center_stack = center_stack
        main_layout.addWidget(center_stack, 2)

        # --- 右パネル（頂点ウェイトリスト＋レイヤーパネル）
        right_widget = QWidget(self)
        right_vbox = QVBoxLayout(right_widget)
        right_vbox.addWidget(QLabel("頂点のウエイト情報 (Vertex Influences)", right_widget))
        self.vertex_weight_list = QListWidget(right_widget)
        self.vertex_weight_list.itemClicked.connect(self.on_vertex_weight_item_clicked)
        right_vbox.addWidget(self.vertex_weight_list)
        # 最初はLayerManager未定義でPanelLayers生成
        self.layer_manager = None
        self.panel_layers = PanelLayers(None, parent=right_widget)
        self.panel_layers.layerChanged.connect(self.on_panel_layers_changed)
        right_vbox.addWidget(self.panel_layers)
        right_vbox.addStretch()
        main_layout.addWidget(right_widget, 1)

        self.setLayout(main_layout)

        # サブパネルイベント
        self.empty_panel.edit_skin_weights_requested.connect(self.on_edit_skin_weights)
        self.copy_panel.copyRequested.connect(self.on_copy_clicked)
        self.copy_panel.pasteRequested.connect(self.on_paste_clicked)
        self.mirror_panel.pasteMirrorRequested.connect(self.on_paste_mirror_clicked)
        self.mirror_panel.mirrorPos2NegRequested.connect(self.on_mirror_pos2neg_clicked)
        self.mirror_panel.mirrorNeg2PosRequested.connect(self.on_mirror_neg2pos_clicked)
        self.weight_panel.weightChanged.connect(self.refresh_vertex_weight_list)

        self.all_influences = []
        self.copied_weights = None
        self._manual_joint_override = False

        self.selection_monitor_job = None
        self.refresh_panels()
        self.start_selection_monitoring()

    def refresh_panels(self):
        sel = cmds.ls(selection=True, long=True)
        if not sel:
            self.set_edit_mode(False)
            self.layer_manager = None
            self.panel_layers.manager = None
            self.panel_layers.reload_table()
            return
        mesh = sel[0].split('.')[0]
        skin = find_related_skin_cluster(mesh)
        skin_data = find_skin_data_node(skin) if skin else None
        self.is_skin_data_present = bool(skin_data)
        self.set_edit_mode(self.is_skin_data_present)
        self.refresh_influence_list(mesh)
        self.refresh_vertex_weight_list()
        # レイヤデータ：skinDataノードから都度ロード
        if skin_data:
            try:
                json_str = cmds.getAttr(f"{skin_data}.layerData")
                data = json.loads(json_str)
                self.layer_manager = SkinLayerManager(
                    data.get("influences", []), data.get("vertex_count", 0)
                )
                self.layer_manager.import_json(data)
                self.panel_layers.manager = self.layer_manager
                self.panel_layers.reload_table()
            except Exception as e:
                print(f"レイヤデータロード失敗: {e}")
                self.layer_manager = None
                self.panel_layers.manager = None
                self.panel_layers.reload_table()
        else:
            self.layer_manager = None
            self.panel_layers.manager = None
            self.panel_layers.reload_table()

    def save_layers_to_node(self):
        sel = cmds.ls(selection=True, long=True)
        if not sel or not self.layer_manager:
            return
        mesh = sel[0].split('.')[0]
        skin = find_related_skin_cluster(mesh)
        skin_data = find_skin_data_node(skin)
        if skin_data:
            data = self.layer_manager.export_json()
            cmds.setAttr(f"{skin_data}.layerData", json.dumps(data), type='string')

    def set_edit_mode(self, enable):
        if enable:
            self.center_stack.setCurrentWidget(self.edit_panel)
        else:
            self.center_stack.setCurrentWidget(self.empty_panel)

    def on_edit_skin_weights(self):
        sel = cmds.ls(selection=True, long=True)
        if not sel:
            self.status.setText("モデルを選択してください")
            return
        mesh = sel[0].split('.')[0]
        skin = find_related_skin_cluster(mesh)
        node = make_or_get_skin_data_node(skin)
        self.refresh_panels()
        self.status.setText("skinDataノードを作成・編集開始しました。")

    def on_panel_layers_changed(self):
        self.save_layers_to_node()

    def refresh_influence_list(self, mesh=None):
        if not mesh:
            sel = cmds.ls(selection=True, long=True)
            if not sel:
                self.influence_list.clear()
                return
            mesh = sel[0].split('.')[0]
        self.influence_list.clear()
        influences = get_skin_influences(mesh)
        self.all_influences = influences
        for j in influences:
            self.influence_list.addItem(j)
        joint = self.weight_panel.get_joint_name()
        for i in range(self.influence_list.count()):
            item = self.influence_list.item(i)
            if item.text() == joint:
                self.influence_list.setCurrentItem(item)
                break

    def apply_influence_filter(self):
        word = self.influence_search.text().strip().lower()
        self.influence_list.clear()
        if not self.all_influences:
            return
        for inf in self.all_influences:
            if not word or word in inf.lower():
                self.influence_list.addItem(inf)

    def on_influence_item_clicked(self, item):
        joint_name = item.text()
        self._manual_joint_override = True
        self.weight_panel.set_joint_name(joint_name)
        self.refresh_vertex_weight_list()

    def refresh_vertex_weight_list(self):
        sel = cmds.ls(selection=True, flatten=True)
        verts = [s for s in sel if ".vtx[" in s]
        self.vertex_weight_list.clear()
        if not verts:
            self.vertex_weight_list.addItem("頂点未選択")
            if not self._manual_joint_override:
                self.weight_panel.set_joint_name("")
            return
        vtx = verts[0]
        infos = get_vertex_influences(vtx)
        if not infos:
            self.vertex_weight_list.addItem("skinned頂点でないかウェイトなし")
            if not self._manual_joint_override:
                self.weight_panel.set_joint_name("")
            return
        for joint, value in infos:
            self.vertex_weight_list.addItem(f"{joint} : {value:.4f}")
        if not self._manual_joint_override:
            first_joint = infos[0][0]
            self.weight_panel.set_joint_name(first_joint)

    def on_vertex_weight_item_clicked(self, item):
        text = item.text()
        if ":" not in text:
            return
        joint_name = text.split(":", 1)[0].strip()
        self._manual_joint_override = False
        self.weight_panel.set_joint_name(joint_name)
        self.refresh_influence_list(mesh=None)

    def on_copy_clicked(self):
        try:
            self.copied_weights = copy_weights()
            self.copy_panel.set_status("コピー済")
        except Exception as e:
            self.copy_panel.set_status(str(e))

    def on_paste_clicked(self):
        try:
            paste_weights(self.copied_weights)
            self.copy_panel.set_status("ペーストOK")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.copy_panel.set_status(str(e))

    def on_paste_mirror_clicked(self):
        try:
            paste_mirror_weights(self.copied_weights)
            self.mirror_panel.set_status("Paste Mirror OK")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.mirror_panel.set_status(str(e))

    def on_mirror_pos2neg_clicked(self):
        try:
            mirror_weights_x_pos2neg()
            self.mirror_panel.set_status("+X→-X 完了")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.mirror_panel.set_status(str(e))

    def on_mirror_neg2pos_clicked(self):
        try:
            mirror_weights_x_neg2pos()
            self.mirror_panel.set_status("-X→+X 完了")
            self.refresh_vertex_weight_list()
        except Exception as e:
            self.mirror_panel.set_status(str(e))

    def start_selection_monitoring(self):
        if getattr(self, "selection_monitor_job", None):
            try:
                cmds.scriptJob(kill=self.selection_monitor_job, force=True)
            except Exception:
                pass
        self.selection_monitor_job = cmds.scriptJob(
            event=["SelectionChanged", self.on_selection_changed],
            killWithScene=True, protected=True
        )

    def on_selection_changed(self, *args):
        self._manual_joint_override = False
        self.refresh_panels()

    def closeEvent(self, event):
        if getattr(self, "selection_monitor_job", None):
            try:
                cmds.scriptJob(kill=self.selection_monitor_job, force=True)
            except Exception:
                pass
        super().closeEvent(event)
import maya.cmds as cmds
from PySide6 import QtWidgets, QtCore
from maya.app.general.mayaMixin import MayaQWidgetBaseMixin 
from . import bridge_maya

# =========================================================
# UI表示用のモデル (MVCのModel層)
# =========================================================
class LayerListModel(QtCore.QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layers = []

    def set_layers(self, layers):
        self.beginResetModel()
        self._layers = layers
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._layers)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._layers)):
            return None
        
        layer = self._layers[index.row()]
        
        # DisplayRole: リストに表示される文字列
        if role == QtCore.Qt.DisplayRole:
            return f"{index.row()}: {layer['name']} (Opacity: {layer['opacity']:.2f})"
        
        # UserRole: 実際のデータ自体を取り出す用
        if role == QtCore.Qt.UserRole:
            return layer
            
        return None

# =========================================================
# メインUI (MVCのView & Controller層)
# =========================================================
class PochiPochiUI(MayaQWidgetBaseMixin, QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pochi-Pochi Skin Weight")
        self.setWindowFlags(QtCore.Qt.Tool)
        self.resize(300, 500)
        
        self.manager = None
        self.setup_ui()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        self.btn_load = QtWidgets.QPushButton("選択したメッシュをロード")
        self.btn_load.clicked.connect(self.load_mesh)
        main_layout.addWidget(self.btn_load)

        # QListWidget から QListView + QAbstractListModel への変更
        main_layout.addWidget(QtWidgets.QLabel("■ レイヤー (Layers)"))
        self.list_view_layers = QtWidgets.QListView()
        self.layer_model = LayerListModel(self)
        self.list_view_layers.setModel(self.layer_model)
        self.list_view_layers.selectionModel().selectionChanged.connect(self.on_layer_selected)
        main_layout.addWidget(self.list_view_layers)

        row_layer = QtWidgets.QHBoxLayout()
        self.btn_add_layer = QtWidgets.QPushButton("＋ レイヤー追加")
        self.btn_add_layer.clicked.connect(self.add_layer)
        row_layer.addWidget(self.btn_add_layer)
        
        self.slider_opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.sliderReleased.connect(self.change_opacity)
        row_layer.addWidget(self.slider_opacity)
        main_layout.addLayout(row_layer)

        main_layout.addWidget(QtWidgets.QLabel("■ ターゲットボーン (Bones)"))
        self.list_bones = QtWidgets.QListWidget()
        main_layout.addWidget(self.list_bones)

        main_layout.addWidget(QtWidgets.QLabel("■ ウェイト加算/減算"))
        grid_btns = QtWidgets.QGridLayout()
        
        btn_plus_1 = QtWidgets.QPushButton("+0.1")
        btn_plus_1.clicked.connect(lambda: self.apply_weight(0.1))
        btn_plus_05 = QtWidgets.QPushButton("+0.05")
        btn_plus_05.clicked.connect(lambda: self.apply_weight(0.05))
        
        btn_minus_1 = QtWidgets.QPushButton("-0.1")
        btn_minus_1.clicked.connect(lambda: self.apply_weight(-0.1))
        btn_minus_05 = QtWidgets.QPushButton("-0.05")
        btn_minus_05.clicked.connect(lambda: self.apply_weight(-0.05))

        grid_btns.addWidget(btn_plus_1, 0, 0)
        grid_btns.addWidget(btn_plus_05, 0, 1)
        grid_btns.addWidget(btn_minus_1, 1, 0)
        grid_btns.addWidget(btn_minus_05, 1, 1)
        
        main_layout.addLayout(grid_btns)

    def load_mesh(self):
        sel = cmds.ls(selection=True, objectsOnly=True)
        if not sel:
            cmds.warning("メッシュを選択してください。")
            return
            
        if self.manager:
            self.manager.release()
            
        mesh_name = sel[0]
        try:
            self.manager = bridge_maya.SkinLayerManager(mesh_name)
            self.refresh_ui()
            self.setWindowTitle(f"Pochi-Pochi - {mesh_name}")
        except Exception as e:
            cmds.warning(f"ロード失敗: {e}")

    def refresh_ui(self):
        if not self.manager: return
        
        # モデルにレイヤーリストを渡すだけでUIが自動更新される
        self.layer_model.set_layers(self.manager.layers)
        
        self.list_bones.clear()
        bones = cmds.skinCluster(self.manager.skin_name, query=True, influence=True) or []
        for i, bone in enumerate(bones):
            self.list_bones.addItem(f"{i}: {bone}")

    def on_layer_selected(self, selected, deselected):
        indexes = selected.indexes()
        if indexes and self.manager:
            layer_data = self.layer_model.data(indexes[0], QtCore.Qt.UserRole)
            if layer_data:
                self.slider_opacity.setValue(int(layer_data["opacity"] * 100))

    def add_layer(self):
        if self.manager:
            new_idx = self.manager.add_layer(name="Anim_Layer", opacity=1.0)
            self.refresh_ui()
            
            # 追加したレイヤーを選択状態にする
            index = self.layer_model.index(new_idx, 0)
            self.list_view_layers.selectionModel().setCurrentIndex(index, QtCore.QItemSelectionModel.ClearAndSelect)

    def change_opacity(self):
        indexes = self.list_view_layers.selectionModel().selectedIndexes()
        if indexes and self.manager:
            row = indexes[0].row()
            val = self.slider_opacity.value() / 100.0
            self.manager.set_layer_opacity(row, val)
            self.refresh_ui() # モデルを更新して数値を反映

    def apply_weight(self, value):
        if not self.manager: return
        
        indexes = self.list_view_layers.selectionModel().selectedIndexes()
        if not indexes:
            cmds.warning("レイヤーを選択してください。")
            return
        layer_idx = indexes[0].row()
        
        bone_idx = self.list_bones.currentRow()
        if bone_idx < 0:
            cmds.warning("ボーンを選択してください。")
            return

        sel_vtx = cmds.filterExpand(selectionMask=31)
        if not sel_vtx:
            cmds.warning("対象の頂点を選択してください。")
            return
            
        vtx_ids = [int(v.split('[')[1].split(']')[0]) for v in sel_vtx]
        self.manager.edit_layer_weights_batch(layer_idx, vtx_ids, bone_idx, value)
        cmds.refresh()

    def closeEvent(self, event):
        if self.manager:
            self.manager.release()
        super().closeEvent(event)
import maya.cmds as cmds
from PySide6 import QtWidgets, QtCore

# MayaのUIと統合するための専用モジュール
from maya.app.general.mayaMixin import MayaQWidgetBaseMixin 
from . import bridge_maya

class PochiPochiUI(MayaQWidgetBaseMixin, QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pochi-Pochi Skin Weight")
        
        # Qt.Toolを指定することで、Mayaの常に手前に表示され、Maya最小化時に一緒に隠れる
        self.setWindowFlags(QtCore.Qt.Tool)
        self.resize(300, 500)
        
        self.manager = None
        self.setup_ui()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # 1. メッシュ読み込みボタン
        self.btn_load = QtWidgets.QPushButton("選択したメッシュをロード")
        self.btn_load.clicked.connect(self.load_mesh)
        main_layout.addWidget(self.btn_load)

        # 2. レイヤーリスト
        main_layout.addWidget(QtWidgets.QLabel("■ レイヤー (Layers)"))
        self.list_layers = QtWidgets.QListWidget()
        self.list_layers.currentRowChanged.connect(self.on_layer_selected)
        main_layout.addWidget(self.list_layers)

        # レイヤー追加・不透明度スライダー
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

        # 3. ボーン(インフルエンス)リスト
        main_layout.addWidget(QtWidgets.QLabel("■ ターゲットボーン (Bones)"))
        self.list_bones = QtWidgets.QListWidget()
        main_layout.addWidget(self.list_bones)

        # 4. Pochi-Pochi ボタン群
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

    # =========================================================
    # UIのロジック部分
    # =========================================================
    def load_mesh(self):
        sel = cmds.ls(selection=True, objectsOnly=True)
        if not sel:
            cmds.warning("メッシュを選択してください。")
            return
            
        mesh_name = sel[0]
        try:
            self.manager = bridge_maya.SkinLayerManager(mesh_name)
            self.refresh_ui()
            self.setWindowTitle(f"Pochi-Pochi - {mesh_name}")
        except Exception as e:
            cmds.warning(f"ロード失敗: {e}")

    def refresh_ui(self):
        if not self.manager: return
        
        # レイヤーリストの更新
        self.list_layers.clear()
        for i, layer in enumerate(self.manager.layers):
            self.list_layers.addItem(f"{i}: {layer['name']} (Opacity: {layer['opacity']})")
        
        # ボーンリストの更新 (SkinClusterから取得)
        self.list_bones.clear()
        bones = cmds.skinCluster(self.manager.skin_name, query=True, influence=True) or []
        for i, bone in enumerate(bones):
            self.list_bones.addItem(f"{i}: {bone}")

    def on_layer_selected(self, row):
        if row >= 0 and self.manager:
            op = self.manager.layers[row]["opacity"]
            self.slider_opacity.setValue(int(op * 100))

    def add_layer(self):
        if self.manager:
            self.manager.add_layer(name="Anim_Layer", opacity=1.0)
            self.refresh_ui()
            self.list_layers.setCurrentRow(len(self.manager.layers) - 1)

    def change_opacity(self):
        row = self.list_layers.currentRow()
        if row >= 0 and self.manager:
            val = self.slider_opacity.value() / 100.0
            self.manager.set_layer_opacity(row, val)
            self.refresh_ui()

    def apply_weight(self, value):
        if not self.manager: return
        
        layer_idx = self.list_layers.currentRow()
        bone_idx = self.list_bones.currentRow()
        
        if layer_idx < 0 or bone_idx < 0:
            cmds.warning("レイヤーとボーンを選択してください。")
            return

        # Mayaから選択中の頂点IDを取得する
        sel_vtx = cmds.filterExpand(selectionMask=31) # 31 = Polygon Vertex
        if not sel_vtx:
            cmds.warning("対象の頂点を選択してください。")
            return
            
        # "pSphere1.vtx[5]" のような文字列から数字(5)だけを抽出
        vtx_ids = [int(v.split('[')[1].split(']')[0]) for v in sel_vtx]
        
        # C++エンジン経由で一括処理
        self.manager.edit_layer_weights_batch(layer_idx, vtx_ids, bone_idx, value)
        cmds.refresh()
from .qt_compat import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QCheckBox, QSlider, QGroupBox, QLabel, QPushButton, QInputDialog,
    QtCore, QAbstractItemView
)
from ..core.skin_layer import SkinLayerManager

class PanelLayers(QGroupBox):
    # メインUIへ通知用のSignal
    layerChanged = QtCore.Signal()

    def __init__(self, manager=None, parent=None):
        super().__init__("Layers", parent)
        self.manager = manager
        self.setLayout(QVBoxLayout())
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Layer Name", "Enabled", "Opacity"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 120)
        self.layout().addWidget(self.table)

        btn_bar = QHBoxLayout()
        self.btn_add = QPushButton("＋ Add")
        self.btn_del = QPushButton("－ Remove")
        self.btn_undo = QPushButton("Undo")
        self.btn_redo = QPushButton("Redo")
        btn_bar.addWidget(self.btn_add)
        btn_bar.addWidget(self.btn_del)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_undo)
        btn_bar.addWidget(self.btn_redo)
        self.layout().addLayout(btn_bar)

        self.btn_add.clicked.connect(self.on_add)
        self.btn_del.clicked.connect(self.on_delete)
        self.btn_undo.clicked.connect(self.on_undo)
        self.btn_redo.clicked.connect(self.on_redo)

        self.table.cellDoubleClicked.connect(self._rename_cell)
        self.reload_table()

    def reload_table(self):
        self.table.setRowCount(0)
        if self.manager is None:
            return
        for row, layer in enumerate(self.manager.list_layers()):
            self.table.insertRow(row)
            item = QTableWidgetItem(layer["name"])
            self.table.setItem(row, 0, item)
            cbx = QCheckBox()
            cbx.setChecked(layer.get("enabled", True))
            cbx.stateChanged.connect(lambda state, layer_id=layer["id"]: self.set_enabled(layer_id, state))
            self.table.setCellWidget(row, 1, cbx)
            slider = QSlider(QtCore.Qt.Horizontal)
            slider.setMinimum(1)
            slider.setMaximum(100)
            slider.setValue(int(layer.get("opacity", 1.0) * 100))
            slider.valueChanged.connect(lambda val, layer_id=layer["id"]: self.set_opacity(layer_id, val))
            self.table.setCellWidget(row, 2, slider)

    def get_selected_layer_id(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel: return None
        idx = sel[0].row()
        layers = self.manager.list_layers() if self.manager else []
        return layers[idx]["id"] if 0 <= idx < len(layers) else None

    def on_add(self):
        if self.manager:
            self.manager.add_layer()
            self.reload_table()
            self.layerChanged.emit()

    def on_delete(self):
        lid = self.get_selected_layer_id()
        if self.manager and lid:
            self.manager.delete_layer(lid)
            self.reload_table()
            self.layerChanged.emit()

    def on_undo(self):
        if self.manager:
            self.manager.undo()
            self.reload_table()
            self.layerChanged.emit()

    def on_redo(self):
        if self.manager:
            self.manager.redo()
            self.reload_table()
            self.layerChanged.emit()

    def set_enabled(self, lid, state):
        if self.manager:
            self.manager.set_layer_enabled(lid, state)
            self.reload_table()
            self.layerChanged.emit()

    def set_opacity(self, lid, value):
        if self.manager:
            self.manager.set_layer_opacity(lid, value / 100.0)
            self.layerChanged.emit()  # 変更都度通知（reload_tableはしないことでスムーズなUI）

    def _rename_cell(self, row, col):
        if col == 0 and self.manager:
            lid = self.manager.list_layers()[row]["id"]
            old = self.manager.get_layer(lid)["name"]
            new, ok = QInputDialog.getText(self, "Rename", "Layer Name", text=old)
            if ok and new:
                self.manager.rename_layer(lid, new)
                self.reload_table()
                self.layerChanged.emit()
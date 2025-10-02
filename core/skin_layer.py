# core/skin_layer.py

import uuid
import copy
import json

class SkinLayerManager:
    """
    Undo/Redoつきのレイヤ式スキンデータモデル
    レイヤ編集履歴はすべて構造まるごと保存方式
    """
    def __init__(self, influences, vertex_count):
        self.influences = list(influences)  # [{ "path":..., ... }]
        self.vertex_count = vertex_count
        self.layers = []
        self.undo_stack = []
        self.redo_stack = []
        self.push_undo()  # 初期状態積む

    # ==== レイヤ基本 ====
    def add_layer(self, name="New Layer"):
        layer = {
            "id": str(uuid.uuid4()),
            "name": name,
            "enabled": True,
            "opacity": 1.0,
            "index": len(self.layers),
            "influences": {str(i): [0.0]*self.vertex_count for i in range(len(self.influences))}
        }
        self.layers.append(layer)
        self._reindex_layers()
        self.push_undo()
        return layer

    def delete_layer(self, layer_id):
        idx = self._find_layer_index(layer_id)
        if idx is not None:
            del self.layers[idx]
            self._reindex_layers()
            self.push_undo()

    def set_layer_enabled(self, layer_id, enabled):
        ly = self.get_layer(layer_id)
        if ly:
            ly["enabled"] = bool(enabled)
            self.push_undo()

    def set_layer_opacity(self, layer_id, opacity):
        ly = self.get_layer(layer_id)
        if ly:
            ly["opacity"] = float(opacity)
            self.push_undo()

    def rename_layer(self, layer_id, name):
        ly = self.get_layer(layer_id)
        if ly:
            ly["name"] = str(name)
            self.push_undo()

    # ==== 履歴管理 ====
    def push_undo(self):
        state = self.export_json()
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            current = self.undo_stack.pop()
            self.redo_stack.append(current)
            prev = self.undo_stack[-1]
            self.import_json(prev)

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.import_json(state)
            self.undo_stack.append(copy.deepcopy(state))

    # ==== JSON入出力 ====
    def export_json(self):
        return copy.deepcopy({
            "influences": self.influences,
            "vertex_count": self.vertex_count,
            "layers": self.layers
        })
    def import_json(self, data):
        self.influences = copy.deepcopy(data["influences"])
        self.vertex_count = data["vertex_count"]
        self.layers = copy.deepcopy(data["layers"])

    # ==== Layer情報 ====
    def _reindex_layers(self):
        for i, ly in enumerate(self.layers):
            ly["index"] = i

    def list_layers(self):
        return sorted(self.layers, key=lambda l: l.get("index", 0))

    def get_layer(self, layer_id):
        for ly in self.layers:
            if ly["id"] == layer_id:
                return ly
        return None

    def _find_layer_index(self, layer_id):
        for idx, ly in enumerate(self.layers):
            if ly["id"] == layer_id:
                return idx
        return None

    # ==== サンプル:get/編集 ====
    def count_layers(self):
        return len(self.layers)
    def get_layer_names(self):
        return [ly["name"] for ly in self.list_layers()]
    def get_enabled_layers(self):
        return [ly for ly in self.list_layers() if ly.get("enabled", True)]

    # ==== レイヤ編集 ====
    def set_weight(self, layer_id, joint_index, vertex_index, value):
        ly = self.get_layer(layer_id)
        if ly:
            ly["influences"][str(joint_index)][vertex_index] = float(value)
            self.push_undo()

    def add_weight(self, layer_id, joint_index, vertex_index, delta):
        ly = self.get_layer(layer_id)
        if ly:
            ly["influences"][str(joint_index)][vertex_index] += float(delta)
            self.push_undo()

    # ==== (option) Layer順移動 ====
    def move_layer(self, layer_id, to_index):
        idx = self._find_layer_index(layer_id)
        if idx is not None and 0 <= to_index < len(self.layers):
            ly = self.layers.pop(idx)
            self.layers.insert(to_index, ly)
            self._reindex_layers()
            self.push_undo()

if __name__ == "__main__":
    # サンプルテスト
    influences = [{"path": "JNT1", "index": 0}, {"path": "JNT2", "index": 1}]
    mgr = SkinLayerManager(influences, 3)
    l1 = mgr.add_layer("Base")
    mgr.set_layer_opacity(l1["id"], 0.7)
    l2 = mgr.add_layer("Temp")
    mgr.set_layer_enabled(l2["id"], False)
    mgr.rename_layer(l2["id"], "MASK")
    print("\n--- export1 ---")
    print(json.dumps(mgr.export_json(), indent=2))
    mgr.set_weight(l1["id"], 0, 1, 0.55)
    print("\n--- export2 ---")
    print(json.dumps(mgr.export_json(), indent=2))
    mgr.undo()
    print("\n--- undo ---\n", json.dumps(mgr.export_json(), indent=2))
    mgr.redo()
    print("\n--- redo ---\n", json.dumps(mgr.export_json(), indent=2))
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import numpy as np
import json
import traceback

from . import WeightEngine

def get_skin_cluster(mesh_node):
    """メッシュからスキンクラスターを取得する"""
    history = cmds.listHistory(mesh_node, pruneDagObjects=True) or []
    skins = cmds.ls(history, type="skinCluster")
    return skins[0] if skins else None

# 開発中のコールバック重複登録を防ぐためのグローバル辞書
if not hasattr(om, "_pochi_callbacks"):
    om._pochi_callbacks = {}

class SkinLayerManager:
    def __init__(self, mesh_name):
        self.mesh_name = mesh_name
        self.engine = WeightEngine()
        
        self.skin_name = get_skin_cluster(self.mesh_name)
        if not self.skin_name:
            raise ValueError(f"{mesh_name} にスキンクラスターがありません。")

        sel_list = om.MSelectionList()
        sel_list.add(self.skin_name)
        self.skin_obj = sel_list.getDependNode(0)
        self.skin_fn = oma.MFnSkinCluster(self.skin_obj)
        
        sel_list_mesh = om.MSelectionList()
        sel_list_mesh.add(self.mesh_name)
        self.mesh_dag = sel_list_mesh.getDagPath(0)

        self.num_vertices = cmds.polyEvaluate(self.mesh_name, vertex=True)
        self.vtx_comp_all = om.MFnSingleIndexedComponent().create(om.MFn.kMeshVertComponent)
        om.MFnSingleIndexedComponent(self.vtx_comp_all).setCompleteData(self.num_vertices)
        
        # 初期ウェイトの取得（一時保存）
        weights_marray, self.num_influences = self.skin_fn.getWeights(self.mesh_dag, self.vtx_comp_all)
        self._initial_weights = np.array(weights_marray, dtype=np.float32).reshape((self.num_vertices, self.num_influences))
        
        self.layers = []
        self.data_node_name = f"{self.skin_name}_PochiData"
        self._is_editing = False
        
        self._init_data_node()
        self._register_callback()

    def _init_data_node(self):
        if not cmds.objExists(self.data_node_name):
            cmds.createNode("network", name=self.data_node_name)
            cmds.addAttr(self.data_node_name, ln="isPochiData", at="bool")
            cmds.addAttr(self.data_node_name, ln="targetSkin", at="message")
            cmds.connectAttr(f"{self.skin_name}.message", f"{self.data_node_name}.targetSkin", force=True)
            cmds.addAttr(self.data_node_name, ln="layerMetaData", dt="string")
            
            # baseWeights属性を廃止し、最初のレイヤー(layerWeights_0)として初期ウェイトを保存する
            cmds.addAttr(self.data_node_name, ln="layerWeights_0", dt="doubleArray")
            cmds.setAttr(f"{self.data_node_name}.layerWeights_0", self._initial_weights.flatten().tolist(), type="doubleArray")
            
            # メタデータに「BaseLayer」を登録
            metadata = [{"name": "BaseLayer", "opacity": 1.0}]
            cmds.setAttr(f"{self.data_node_name}.layerMetaData", json.dumps(metadata), type="string")
            
        self._load_from_node()

    def _register_callback(self):
        if self.data_node_name in om._pochi_callbacks:
            try:
                om.MMessage.removeCallback(om._pochi_callbacks[self.data_node_name])
            except: pass
            
        sel = om.MSelectionList()
        sel.add(self.data_node_name)
        node_obj = sel.getDependNode(0)
        
        cb_id = om.MNodeMessage.addAttributeChangedCallback(node_obj, self._on_node_changed)
        om._pochi_callbacks[self.data_node_name] = cb_id

    def _on_node_changed(self, msg, plug, otherPlug, clientData):
        if self._is_editing: return
        try:
            if msg & om.MNodeMessage.kAttributeSet:
                attr_name = plug.partialName(useAlias=True)
                if "layerWeights" in attr_name or "layerMetaData" in attr_name:
                    self._load_from_node()
                    self._apply_to_skincluster()
                    cmds.refresh()
        except Exception as e:
            print(f"[PochiPochi] Callback Error: {e}")
            traceback.print_exc()

    def _load_from_node(self):
        metadata_str = cmds.getAttr(f"{self.data_node_name}.layerMetaData")
        if not metadata_str: return
        metadata = json.loads(metadata_str)
        
        self.layers = []
        for i, meta in enumerate(metadata):
            attr_name = f"layerWeights_{i}"
            if cmds.attributeQuery(attr_name, node=self.data_node_name, exists=True):
                weights_flat = cmds.getAttr(f"{self.data_node_name}.{attr_name}")
                if weights_flat:
                    np_weights = np.array(weights_flat, dtype=np.float32).reshape((self.num_vertices, self.num_influences))
                    self.layers.append({"name": meta["name"], "opacity": meta["opacity"], "weights": np_weights})

    def _apply_to_skincluster(self):
        if not self.layers: return
        
        # 合成の起点を BaseLayer (layers[0]) にする
        current_weights = self.layers[0]["weights"].copy() * self.layers[0]["opacity"]
        
        # 2枚目以降のレイヤーをブレンドしていく
        for layer in self.layers[1:]:
            current_weights = self.engine.blend_layers(current_weights, layer["weights"], layer["opacity"])
            
        current_weights_64 = current_weights.astype(np.float64)
        row_sums = current_weights_64.sum(axis=1, keepdims=True)
        final_weights = np.divide(current_weights_64, row_sums, out=np.zeros_like(current_weights_64), where=row_sums!=0)
        
        # ウェイト消失時のフォールバック先も BaseLayer に変更
        zero_mask = (row_sums.flatten() == 0)
        if np.any(zero_mask):
            final_weights[zero_mask] = self.layers[0]["weights"][zero_mask].astype(np.float64)
            
        current_sums = final_weights.sum(axis=1)
        errors = 1.0 - current_sums
        max_indices = np.argmax(final_weights, axis=1)
        row_indices = np.arange(self.num_vertices)
        final_weights[row_indices, max_indices] += errors
        
        new_weights_marray = om.MDoubleArray(final_weights.flatten().tolist())
        inf_indices = om.MIntArray(range(self.num_influences))
        
        norm_attr = f"{self.skin_name}.normalizeWeights"
        current_norm_mode = cmds.getAttr(norm_attr)
        if current_norm_mode != 0: cmds.setAttr(norm_attr, 0)
            
        self.skin_fn.setWeights(self.mesh_dag, self.vtx_comp_all, inf_indices, new_weights_marray, False)
        
        if current_norm_mode != 0: cmds.setAttr(norm_attr, current_norm_mode)
        cmds.dgdirty(self.skin_name)

    def add_layer(self, name="New Layer", opacity=1.0):
        self._is_editing = True
        try:
            layer_idx = len(self.layers)
            # 新規レイヤーはすべて0の配列で初期化
            new_layer_weights = np.zeros_like(self.layers[0]["weights"], dtype=np.float32)
            
            metadata = [{"name": l["name"], "opacity": l["opacity"]} for l in self.layers]
            metadata.append({"name": name, "opacity": opacity})
            
            attr_name = f"layerWeights_{layer_idx}"
            if not cmds.attributeQuery(attr_name, node=self.data_node_name, exists=True):
                cmds.addAttr(self.data_node_name, ln=attr_name, dt="doubleArray")
                
            cmds.setAttr(f"{self.data_node_name}.{attr_name}", new_layer_weights.flatten().tolist(), type="doubleArray")
            cmds.setAttr(f"{self.data_node_name}.layerMetaData", json.dumps(metadata), type="string")
            
            self._load_from_node()
            self._apply_to_skincluster()
            return layer_idx
        finally:
            self._is_editing = False

    def edit_layer_weights_batch(self, layer_index, vertex_ids, bone_id, add_value):
        if 0 <= layer_index < len(self.layers) and vertex_ids:
            self._is_editing = True
            try:
                target_weights = self.layers[layer_index]["weights"].copy()
                for vid in vertex_ids:
                    self.engine.add_weight(target_weights, vid, bone_id, add_value)
                
                attr_name = f"layerWeights_{layer_index}"
                cmds.setAttr(f"{self.data_node_name}.{attr_name}", target_weights.flatten().tolist(), type="doubleArray")
                
                self._load_from_node()
                self._apply_to_skincluster()
            finally:
                self._is_editing = False

    def set_layer_opacity(self, layer_index, opacity):
        if 0 <= layer_index < len(self.layers):
            self._is_editing = True
            try:
                metadata = [{"name": l["name"], "opacity": l["opacity"]} for l in self.layers]
                metadata[layer_index]["opacity"] = opacity
                cmds.setAttr(f"{self.data_node_name}.layerMetaData", json.dumps(metadata), type="string")
                
                self._load_from_node()
                self._apply_to_skincluster()
            finally:
                self._is_editing = False
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

# =========================================================
# om を汚染しないモジュールローカルなコールバック管理辞書
_ACTIVE_CALLBACKS = {}
# =========================================================

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
        """ノードの取得・作成と BaseLayer の初期化"""
        if not cmds.objExists(self.data_node_name):
            cmds.createNode("network", name=self.data_node_name)
            cmds.addAttr(self.data_node_name, ln="isPochiData", at="bool")
            cmds.addAttr(self.data_node_name, ln="targetSkin", at="message")
            cmds.connectAttr(f"{self.skin_name}.message", f"{self.data_node_name}.targetSkin", force=True)
            cmds.addAttr(self.data_node_name, ln="layerMetaData", dt="string")
            
            # 最初のレイヤー(layerWeights_0)として初期ウェイトを保存
            cmds.addAttr(self.data_node_name, ln="layerWeights_0", dt="doubleArray")
            cmds.setAttr(f"{self.data_node_name}.layerWeights_0", self._initial_weights.flatten().tolist(), type="doubleArray")
            
            # メタデータに「BaseLayer」を登録
            metadata = [{"name": "BaseLayer", "opacity": 1.0}]
            cmds.setAttr(f"{self.data_node_name}.layerMetaData", json.dumps(metadata), type="string")
            
        self._load_from_node()

    def _register_callback(self):
        """モジュールローカル辞書を使った安全なコールバック登録"""
        if self.data_node_name in _ACTIVE_CALLBACKS:
            try:
                om.MMessage.removeCallback(_ACTIVE_CALLBACKS[self.data_node_name])
            except: pass
            
        sel = om.MSelectionList()
        sel.add(self.data_node_name)
        node_obj = sel.getDependNode(0)
        
        cb_id = om.MNodeMessage.addAttributeChangedCallback(node_obj, self._on_node_changed)
        _ACTIVE_CALLBACKS[self.data_node_name] = cb_id

    def release(self):
        """メモリリークと多重発火を防ぐための明示的なコールバック解除"""
        if self.data_node_name in _ACTIVE_CALLBACKS:
            try:
                om.MMessage.removeCallback(_ACTIVE_CALLBACKS[self.data_node_name])
                del _ACTIVE_CALLBACKS[self.data_node_name]
                print(f"[PochiPochi] {self.data_node_name} の監視コールバックを安全に解除しました。")
            except Exception as e:
                print(f"[PochiPochi] コールバック解除エラー: {e}")

    def _on_node_changed(self, msg, plug, otherPlug, clientData):
        """Undo等によるノード変更検知"""
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
        """ノードからメモリへデータを同期"""
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
        """レイヤー合成とSkinClusterへの流し込み（誤差吸収・警告回避入り）"""
        if not self.layers: return
        
        # 合成の起点は BaseLayer (layers[0])
        current_weights = self.layers[0]["weights"].copy() * self.layers[0]["opacity"]
        
        # 2枚目以降をブレンド
        for layer in self.layers[1:]:
            current_weights = self.engine.blend_layers(current_weights, layer["weights"], layer["opacity"])
            
        current_weights_64 = current_weights.astype(np.float64)
        row_sums = current_weights_64.sum(axis=1, keepdims=True)
        final_weights = np.divide(current_weights_64, row_sums, out=np.zeros_like(current_weights_64), where=row_sums!=0)
        
        # ゼロ除算対策（BaseLayerへフォールバック）
        zero_mask = (row_sums.flatten() == 0)
        if np.any(zero_mask):
            final_weights[zero_mask] = self.layers[0]["weights"][zero_mask].astype(np.float64)
            
        # 浮動小数点誤差の吸収
        current_sums = final_weights.sum(axis=1)
        errors = 1.0 - current_sums
        max_indices = np.argmax(final_weights, axis=1)
        row_indices = np.arange(self.num_vertices)
        final_weights[row_indices, max_indices] += errors
        
        new_weights_marray = om.MDoubleArray(final_weights.flatten().tolist())
        inf_indices = om.MIntArray(range(self.num_influences))
        
        # Mayaの正規化監視を一時停止して警告を回避
        norm_attr = f"{self.skin_name}.normalizeWeights"
        current_norm_mode = cmds.getAttr(norm_attr)
        if current_norm_mode != 0: cmds.setAttr(norm_attr, 0)
            
        self.skin_fn.setWeights(self.mesh_dag, self.vtx_comp_all, inf_indices, new_weights_marray, False)
        
        if current_norm_mode != 0: cmds.setAttr(norm_attr, current_norm_mode)
        cmds.dgdirty(self.skin_name)

    # =========================================================
    # ユーザー操作 API
    # =========================================================
    def add_layer(self, name="New Layer", opacity=1.0):
        self._is_editing = True
        try:
            layer_idx = len(self.layers)
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

    def edit_layer_weight(self, layer_index, vertex_id, bone_id, add_value):
        """単一の頂点を編集する"""
        if 0 <= layer_index < len(self.layers):
            self._is_editing = True
            try:
                target_weights = self.layers[layer_index]["weights"].copy()
                self.engine.add_weight(target_weights, vertex_id, bone_id, add_value)
                
                attr_name = f"layerWeights_{layer_index}"
                cmds.setAttr(f"{self.data_node_name}.{attr_name}", target_weights.flatten().tolist(), type="doubleArray")
                
                self._load_from_node()
                self._apply_to_skincluster()
            finally:
                self._is_editing = False

    def edit_layer_weights_batch(self, layer_index, vertex_ids, bone_id, add_value):
        """複数の頂点に対する一括処理"""
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
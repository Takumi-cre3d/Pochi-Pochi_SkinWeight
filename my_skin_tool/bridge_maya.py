import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import numpy as np
import traceback

from . import core_engine
from . import model
from . import schema

def get_skin_cluster(mesh_node):
    history = cmds.listHistory(mesh_node, pruneDagObjects=True) or []
    skins = cmds.ls(history, type="skinCluster")
    return skins[0] if skins else None

# =========================================================
# 1. CallbackRegistry: 複数UI対応・参照カウント付きのコールバック管理
# =========================================================
class CallbackRegistry:
    _registry = {}  

    @classmethod
    def register(cls, node_obj, node_name, callback_func):
        if node_name in cls._registry:
            cls._registry[node_name]["ref_count"] += 1
        else:
            cb_id = om.MNodeMessage.addAttributeChangedCallback(node_obj, callback_func)
            cls._registry[node_name] = {"id": cb_id, "ref_count": 1}

    @classmethod
    def release(cls, node_name):
        if node_name in cls._registry:
            cls._registry[node_name]["ref_count"] -= 1
            if cls._registry[node_name]["ref_count"] <= 0:
                om.MMessage.removeCallback(cls._registry[node_name]["id"])
                del cls._registry[node_name]

# =========================================================
# 2. SkinClusterAdapter: MayaのSkinCluster操作
# =========================================================
class SkinClusterAdapter:
    def __init__(self, mesh_name, skin_name):
        self.mesh_name = mesh_name
        self.skin_name = skin_name
        
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
        
        weights_marray, self.num_influences = self.skin_fn.getWeights(self.mesh_dag, self.vtx_comp_all)
        self.initial_weights_marray = weights_marray 

    def get_initial_weights(self):
        return np.array(self.initial_weights_marray, dtype=np.float32).reshape((self.num_vertices, self.num_influences))

    def set_weights(self, final_weights_flat):
        new_weights_marray = om.MDoubleArray(final_weights_flat)
        inf_indices = om.MIntArray(range(self.num_influences))
        
        norm_attr = f"{self.skin_name}.normalizeWeights"
        current_norm_mode = cmds.getAttr(norm_attr)
        if current_norm_mode != 0: cmds.setAttr(norm_attr, 0)
            
        try:
            self.skin_fn.setWeights(self.mesh_dag, self.vtx_comp_all, inf_indices, new_weights_marray, False)
        finally:
            if current_norm_mode != 0: cmds.setAttr(norm_attr, current_norm_mode)
                
        cmds.dgdirty(self.skin_name)

# =========================================================
# 3. DataNodeStore: 堅牢な一意接続探索・I/O管理・マイグレーション
# =========================================================
class DataNodeStore:
    def __init__(self, skin_name):
        self.skin_name = skin_name
        self.node_name = None  
        self.attr_pochi_link = "pochiData"

    def ensure_exists(self, initial_weights_np):
        self.node_name = self._get_or_create_node()
        self._migrate_if_needed(initial_weights_np)
        
        sel = om.MSelectionList()
        sel.add(self.node_name)
        return sel.getDependNode(0)

    def _get_or_create_node(self):
        if not cmds.attributeQuery(self.attr_pochi_link, node=self.skin_name, exists=True):
            cmds.addAttr(self.skin_name, ln=self.attr_pochi_link, at="message")

        # 探索ルート1: 接続から辿る
        connections = cmds.listConnections(f"{self.skin_name}.{self.attr_pochi_link}", source=True, destination=False)
        if connections:
            candidate = connections[0]
            if self._validate_node(candidate):
                return candidate
            else:
                cmds.disconnectAttr(f"{candidate}.message", f"{self.skin_name}.{self.attr_pochi_link}")

        # 探索ルート2: 名前でフォールバック探索
        fallback_name = f"{self.skin_name}_PochiData"
        if cmds.objExists(fallback_name):
            if self._validate_node(fallback_name, allow_empty_target=True):
                # 見つかった正当なノードと双方向接続を結び直す（正規化）
                cmds.connectAttr(f"{fallback_name}.message", f"{self.skin_name}.{self.attr_pochi_link}", force=True)
                
                # ターゲットが空だった場合のために張り直す
                if cmds.attributeQuery("targetSkin", node=fallback_name, exists=True):
                    try:
                        cmds.connectAttr(f"{self.skin_name}.message", f"{fallback_name}.targetSkin", force=True)
                    except RuntimeError:
                        pass # 既に繋がっていれば無視
                        
                om.MGlobal.displayInfo(f"[PochiPochi] 既存ノードを再接続(修復)しました: {fallback_name}")
                return fallback_name

        # 探索ルート3: 完全新規作成
        new_node = cmds.createNode("network", name=fallback_name)
        cmds.addAttr(new_node, ln="isPochiData", at="bool")
        cmds.setAttr(f"{new_node}.isPochiData", True)
        cmds.addAttr(new_node, ln="targetSkin", at="message")
        
        cmds.connectAttr(f"{self.skin_name}.message", f"{new_node}.targetSkin", force=True)
        cmds.connectAttr(f"{new_node}.message", f"{self.skin_name}.{self.attr_pochi_link}", force=True)
        cmds.addAttr(new_node, ln="layerMetaData", dt="string")
        return new_node

    def _validate_node(self, node_name, allow_empty_target=False):
        """ノードが本当にこのSkinCluster用のPochiDataか検証する"""
        
        if not cmds.attributeQuery("isPochiData", node=node_name, exists=True): 
            return False

        if cmds.attributeQuery("targetSkin", node=node_name, exists=True):
            # 【修正】上流（Source）である SkinCluster を取得するように修正
            targets = cmds.listConnections(f"{node_name}.targetSkin", source=True, destination=False) or []
            
            if targets:
                # 別のSkinClusterに繋がっている場合は共有/複製事故として弾く
                if targets[0] != self.skin_name:
                    om.MGlobal.displayWarning(f"[PochiPochi] 共有事故を検知。{node_name} は {targets[0]} のデータです。")
                    return False
            elif not allow_empty_target:
                return False
                
        return True

    def _migrate_if_needed(self, initial_weights_np):
        """古いデータ形式のコンバートと、破損したメタデータの自己修復を行う"""
        
        # 旧ノードだった場合、isPochiDataの値を明示的にTrueに直しておく
        if cmds.attributeQuery("isPochiData", node=self.node_name, exists=True):
            cmds.setAttr(f"{self.node_name}.isPochiData", True)

        has_base_old = cmds.attributeQuery("baseWeights", node=self.node_name, exists=True)
        has_layer_0 = cmds.attributeQuery("layerWeights_0", node=self.node_name, exists=True)
        
        if has_base_old and not has_layer_0:
            om.MGlobal.displayInfo(f"[PochiPochi] 旧フォーマットを移行します: {self.node_name}")
            old_data = cmds.getAttr(f"{self.node_name}.baseWeights")
            cmds.addAttr(self.node_name, ln="layerWeights_0", dt="doubleArray")
            cmds.setAttr(f"{self.node_name}.layerWeights_0", old_data, type="doubleArray")
        elif not has_layer_0:
            cmds.addAttr(self.node_name, ln="layerWeights_0", dt="doubleArray")
            cmds.setAttr(f"{self.node_name}.layerWeights_0", initial_weights_np.flatten().tolist(), type="doubleArray")

        has_meta_attr = cmds.attributeQuery("layerMetaData", node=self.node_name, exists=True)
        if not has_meta_attr: 
            cmds.addAttr(self.node_name, ln="layerMetaData", dt="string")
            
        meta_str = cmds.getAttr(f"{self.node_name}.layerMetaData")
        layers_meta = schema.load_metadata(meta_str)
        
        if not layers_meta:
            rebuilt_meta = []
            i = 0
            while cmds.attributeQuery(f"layerWeights_{i}", node=self.node_name, exists=True):
                rebuilt_meta.append({schema.KEY_NAME: "BaseLayer" if i==0 else f"Layer_{i}", schema.KEY_OPACITY: 1.0})
                i += 1
            if not rebuilt_meta: 
                rebuilt_meta = [{schema.KEY_NAME: "BaseLayer", schema.KEY_OPACITY: 1.0}]
            cmds.setAttr(f"{self.node_name}.layerMetaData", schema.dump_metadata(rebuilt_meta), type="string")

    def load_layers(self, num_vertices, num_influences):
        metadata_str = cmds.getAttr(f"{self.node_name}.layerMetaData")
        metadata = schema.load_metadata(metadata_str)
        expected_size = num_vertices * num_influences
        
        layers = []
        for i, meta in enumerate(metadata):
            attr_name = f"layerWeights_{i}"
            if cmds.attributeQuery(attr_name, node=self.node_name, exists=True):
                weights_flat = cmds.getAttr(f"{self.node_name}.{attr_name}")
                if weights_flat:
                    # インフルエンス増減による配列サイズ不一致(サイレント破壊)の防止
                    if len(weights_flat) != expected_size:
                        om.MGlobal.displayError(f"[PochiPochi] {attr_name} の配列サイズが合いません(頂点やボーン数が変化した可能性があります)。このレイヤーはロードされません。")
                        continue
                        
                    np_weights = np.array(weights_flat, dtype=np.float32).reshape((num_vertices, num_influences))
                    layers.append({
                        schema.KEY_NAME: meta.get(schema.KEY_NAME, f"Layer_{i}"), 
                        schema.KEY_OPACITY: meta.get(schema.KEY_OPACITY, 1.0), 
                        "weights": np_weights
                    })
        return layers

    def save_layer(self, layer_idx, weights_np):
        attr_name = f"layerWeights_{layer_idx}"
        if not cmds.attributeQuery(attr_name, node=self.node_name, exists=True):
            cmds.addAttr(self.node_name, ln=attr_name, dt="doubleArray")
        cmds.setAttr(f"{self.node_name}.{attr_name}", weights_np.flatten().tolist(), type="doubleArray")

    def save_metadata(self, layers_list):
        cmds.setAttr(f"{self.node_name}.layerMetaData", schema.dump_metadata(layers_list), type="string")

# =========================================================
# 5. SkinLayerManager: 統括コントローラー
# =========================================================
class SkinLayerManager:
    def __init__(self, mesh_name):
        self.mesh_name = mesh_name
        self.engine = core_engine.PochiCoreEngine()
        
        skin_name = get_skin_cluster(self.mesh_name)
        if not skin_name:
            raise ValueError(f"{mesh_name} にスキンクラスターがありません。")

        self.adapter = SkinClusterAdapter(self.mesh_name, skin_name)
        self.store = DataNodeStore(skin_name)
        
        self.stack = model.LayerStack(self.engine, self.adapter.num_vertices, self.adapter.num_influences)
        
        self._is_editing = False
        
        node_obj = self.store.ensure_exists(self.adapter.get_initial_weights())
        self._sync_from_store()
        CallbackRegistry.register(node_obj, self.store.node_name, self._on_node_changed)

    def release(self):
        CallbackRegistry.release(self.store.node_name)

    def _sync_from_store(self):
        layers = self.store.load_layers(self.adapter.num_vertices, self.adapter.num_influences)
        self.stack.set_layers(layers)

    def _apply_to_maya(self):
        final_weights_flat = self.stack.blend_all()
        if final_weights_flat:
            self.adapter.set_weights(final_weights_flat)

    def _on_node_changed(self, msg, plug, otherPlug, clientData):
        if self._is_editing: return
        try:
            if msg & om.MNodeMessage.kAttributeSet:
                attr_name = plug.partialName(useAlias=True)
                if "layerWeights" in attr_name or "layerMetaData" in attr_name:
                    self._sync_from_store()
                    self._apply_to_maya()
                    cmds.refresh()
        except Exception as e:
            traceback.print_exc()

    @property
    def layers(self):
        return self.stack.layers

    @property
    def skin_name(self):
        return self.adapter.skin_name

    def add_layer(self, name="New Layer", opacity=1.0):
        self._is_editing = True
        try:
            layer_idx = len(self.stack.layers)
            new_layer_weights = np.zeros_like(self.stack.layers[0]["weights"], dtype=np.float32)
            
            self.stack.layers.append({schema.KEY_NAME: name, schema.KEY_OPACITY: opacity, "weights": new_layer_weights})
            
            self.store.save_layer(layer_idx, new_layer_weights)
            self.store.save_metadata(self.stack.layers)
            
            self._sync_from_store()
            self._apply_to_maya()
            return layer_idx
        finally:
            self._is_editing = False

    def edit_layer_weights_batch(self, layer_index, vertex_ids, bone_id, add_value):
        if 0 <= layer_index < len(self.stack.layers) and vertex_ids:
            self._is_editing = True
            try:
                target_weights = self.stack.layers[layer_index]["weights"].copy()
                for vid in vertex_ids:
                    self.engine.add_weight(target_weights, vid, bone_id, add_value)
                
                self.store.save_layer(layer_index, target_weights)
                self._sync_from_store()
                self._apply_to_maya()
            finally:
                self._is_editing = False

    def set_layer_opacity(self, layer_index, opacity):
        if 0 <= layer_index < len(self.stack.layers):
            self._is_editing = True
            try:
                self.stack.layers[layer_index][schema.KEY_OPACITY] = opacity
                self.store.save_metadata(self.stack.layers)
                
                self._sync_from_store()
                self._apply_to_maya()
            finally:
                self._is_editing = False
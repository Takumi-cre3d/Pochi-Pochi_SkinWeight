# my_skin_tool/bridge_maya.py
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import numpy as np
import traceback

# === 分割したDCC非依存モジュール群のインポート ===
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
# 3. DataNodeStore: networkノードの一意接続探索・I/O管理・マイグレーション
# =========================================================
class DataNodeStore:
    def __init__(self, skin_name):
        self.skin_name = skin_name
        self.node_name = None  # 初期化時は未定 (探索して一意に決定する)
        self.attr_pochi_link = "pochiData" # SkinCluster側に生やすメッセージ属性

    def ensure_exists(self, initial_weights_np):
        """ノードを接続ベースで探索し、なければ作成・修復を行う"""
        
        # 1. ノードの探索または作成
        self.node_name = self._get_or_create_node()
        
        # 2. データのマイグレーションと自己修復
        self._migrate_if_needed(initial_weights_np)
        
        sel = om.MSelectionList()
        sel.add(self.node_name)
        return sel.getDependNode(0)

    def _get_or_create_node(self):
        """SkinClusterのメッセージ接続を真実の情報源(SSOT)としてノードを特定する"""
        
        # SkinCluster側に専用のリンク属性(message)がなければ作る
        if not cmds.attributeQuery(self.attr_pochi_link, node=self.skin_name, exists=True):
            cmds.addAttr(self.skin_name, ln=self.attr_pochi_link, at="message")

        # 探索ルート1: SkinClusterからの接続を辿る (最も確実)
        connections = cmds.listConnections(f"{self.skin_name}.{self.attr_pochi_link}", source=True, destination=False)
        if connections:
            return connections[0]
            
        # 探索ルート2(フォールバック): 繋がっていない場合、古い命名規則のノードを探す
        fallback_name = f"{self.skin_name}_PochiData"
        if cmds.objExists(fallback_name):
            # 見つけた旧ノードをSkinClusterに接続し直し、正規化(修復)する
            cmds.connectAttr(f"{fallback_name}.message", f"{self.skin_name}.{self.attr_pochi_link}", force=True)
            om.MGlobal.displayInfo(f"[PochiPochi] 既存のデータノードをSkinClusterに再接続(修復)しました: {fallback_name}")
            return fallback_name
            
        # 探索ルート3: 完全新規作成
        new_node = cmds.createNode("network", name=fallback_name)
        cmds.addAttr(new_node, ln="isPochiData", at="bool")
        cmds.setAttr(f"{new_node}.isPochiData", True)
        cmds.addAttr(new_node, ln="targetSkin", at="message")
        
        # 双方向のコネクションを結ぶ (SkinCluster <--> PochiData)
        cmds.connectAttr(f"{self.skin_name}.message", f"{new_node}.targetSkin", force=True)
        cmds.connectAttr(f"{new_node}.message", f"{self.skin_name}.{self.attr_pochi_link}", force=True)
        
        cmds.addAttr(new_node, ln="layerMetaData", dt="string")
        return new_node

    def _migrate_if_needed(self, initial_weights_np):
        """古いデータ形式のコンバートと、破損したメタデータの再構築を行う"""
        
        has_base_old = cmds.attributeQuery("baseWeights", node=self.node_name, exists=True)
        has_layer_0 = cmds.attributeQuery("layerWeights_0", node=self.node_name, exists=True)
        
        # 1. ウェイト属性のマイグレーション
        if has_base_old and not has_layer_0:
            # 旧ツールの baseWeights がある場合は layerWeights_0 にコンバート
            om.MGlobal.displayInfo(f"[PochiPochi] 旧フォーマットのウェイトデータを移行します: {self.node_name}")
            old_data = cmds.getAttr(f"{self.node_name}.baseWeights")
            cmds.addAttr(self.node_name, ln="layerWeights_0", dt="doubleArray")
            cmds.setAttr(f"{self.node_name}.layerWeights_0", old_data, type="doubleArray")
            # (旧 baseWeights 属性は安全のため一旦残す方針とします)
            
        elif not has_layer_0:
            # 完全新規のノードの場合は、引数の初期ウェイトを流し込む
            cmds.addAttr(self.node_name, ln="layerWeights_0", dt="doubleArray")
            cmds.setAttr(f"{self.node_name}.layerWeights_0", initial_weights_np.flatten().tolist(), type="doubleArray")

        # 2. メタデータの自己修復
        has_meta_attr = cmds.attributeQuery("layerMetaData", node=self.node_name, exists=True)
        if not has_meta_attr:
            cmds.addAttr(self.node_name, ln="layerMetaData", dt="string")
            
        meta_str = cmds.getAttr(f"{self.node_name}.layerMetaData")
        layers_meta = schema.load_metadata(meta_str)
        
        if not layers_meta:
            # メタデータが空、またはパースに失敗(破損)している場合、アトリビュートの存在から強制再構築する
            om.MGlobal.displayWarning(f"[PochiPochi] メタデータをアトリビュートから再構築します: {self.node_name}")
            rebuilt_meta = []
            i = 0
            while cmds.attributeQuery(f"layerWeights_{i}", node=self.node_name, exists=True):
                name = "BaseLayer" if i == 0 else f"Layer_{i}"
                rebuilt_meta.append({schema.KEY_NAME: name, schema.KEY_OPACITY: 1.0})
                i += 1
                
            if not rebuilt_meta:
                rebuilt_meta = [{schema.KEY_NAME: "BaseLayer", schema.KEY_OPACITY: 1.0}]
                
            cmds.setAttr(f"{self.node_name}.layerMetaData", schema.dump_metadata(rebuilt_meta), type="string")

    # load_layers, save_layer, save_metadata は self.node_name を使う点以外はそのまま
    def load_layers(self, num_vertices, num_influences):
        metadata_str = cmds.getAttr(f"{self.node_name}.layerMetaData")
        metadata = schema.load_metadata(metadata_str)
        
        layers = []
        for i, meta in enumerate(metadata):
            attr_name = f"layerWeights_{i}"
            if cmds.attributeQuery(attr_name, node=self.node_name, exists=True):
                weights_flat = cmds.getAttr(f"{self.node_name}.{attr_name}")
                if weights_flat:
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
        # === core_engine.py からエンジンを取得 ===
        self.engine = core_engine.PochiCoreEngine()
        
        skin_name = get_skin_cluster(self.mesh_name)
        if not skin_name:
            raise ValueError(f"{mesh_name} にスキンクラスターがありません。")

        self.adapter = SkinClusterAdapter(self.mesh_name, skin_name)
        self.store = DataNodeStore(skin_name)
        
        # === model.py から LayerStack を取得 ===
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
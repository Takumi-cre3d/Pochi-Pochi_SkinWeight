# my_skin_tool/bridge_maya.py

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import numpy as np

# スマートローダー経由でC++エンジンを読み込む
from . import WeightEngine

def get_skin_cluster(mesh_node):
    """メッシュからスキンクラスターを取得する"""
    history = cmds.listHistory(mesh_node, pruneDagObjects=True) or []
    skins = cmds.ls(history, type="skinCluster")
    return skins[0] if skins else None

def pochi_pochi_add(bone_id, add_value):
    """
    選択した頂点に対して、指定したボーンIDのウェイトを加算する
    """
    # 1. 現在の選択を取得
    sel = om.MGlobal.getActiveSelectionList()
    if sel.isEmpty():
        om.MGlobal.displayWarning("頂点を選択してください。")
        return

    engine = WeightEngine()

    # 2. 選択されたアイテム（メッシュごと）の処理
    for i in range(sel.length()):
        dag_path, component = sel.getComponent(i)
        
        # メッシュかつ頂点が選択されているかチェック
        if dag_path.apiType() != om.MFn.kMesh or component.isNull():
            continue
            
        mesh_name = dag_path.fullPathName()
        skin_name = get_skin_cluster(mesh_name)
        if not skin_name:
            om.MGlobal.displayWarning(f"{mesh_name} にスキンクラスターが見つかりません。")
            continue

        # スキンクラスターのAPIオブジェクトを取得
        sel_skin = om.MSelectionList()
        sel_skin.add(skin_name)
        skin_obj = sel_skin.getDependNode(0)
        skin_fn = oma.MFnSkinCluster(skin_obj)

        # 選択された頂点インデックスのリストを作成
        vert_iter = om.MItMeshVertex(dag_path, component)
        selected_vids = []
        while not vert_iter.isDone():
            selected_vids.append(vert_iter.index())
            vert_iter.next()

        # 3. メッシュ全体のウェイトを取得し、NumPy配列 (V, B) に変換
        # （部分的な取得も可能ですが、行列計算の恩恵を得るため全体をNumPy化します）
        num_vertices = cmds.polyEvaluate(mesh_name, vertex=True)
        vtx_comp_all = om.MFnSingleIndexedComponent().create(om.MFn.kMeshVertComponent)
        om.MFnSingleIndexedComponent(vtx_comp_all).setCompleteData(num_vertices)
        
        weights_array, num_influences = skin_fn.getWeights(dag_path, vtx_comp_all)
        
        # C++エンジンに渡すための2次元配列 (頂点数 x ボーン数) に変形
        np_weights = np.array(weights_array, dtype=np.float32).reshape((num_vertices, num_influences))

        # 4. C++ エンジンで「Pochi-Pochi」計算を実行！
        for vid in selected_vids:
            # 参照渡しで NumPy 配列の該当箇所が直接書き換わります (超高速)
            engine.add_weight(np_weights, vid, bone_id, add_value)
            
            # ウェイトの合計が1.0になるように正規化 (Normalization)
            # ※本格的なツールではこれもC++側に実装しますが、今回は分かりやすくPythonで処理
            row_sum = np.sum(np_weights[vid])
            if row_sum > 0:
                np_weights[vid] /= row_sum

        # 5. 計算結果を Maya に書き戻す
        new_weights_flat = np_weights.flatten()
        new_weights_marray = om.MDoubleArray(new_weights_flat)
        inf_indices = om.MIntArray(range(num_influences))
        
        # ウェイトの適用
        skin_fn.setWeights(dag_path, vtx_comp_all, inf_indices, new_weights_marray, False)
        
    om.MGlobal.displayInfo(f"Pochi-Pochi 完了: ボーンID {bone_id} に {add_value} を加算しました。")
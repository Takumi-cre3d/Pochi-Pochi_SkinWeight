from maya import cmds

def find_related_skin_cluster(mesh):
    """メッシュノード名からskinCluster名を返す"""
    skin_clusters = cmds.ls(cmds.listHistory(mesh), type='skinCluster')
    if skin_clusters:
        return skin_clusters[0]
    return None

def set_weight(verts, joint, value):
    """選択頂点群のjointのウェイトを絶対値にセット"""
    if not verts:
        raise RuntimeError("頂点が選択されていません")
    mesh = verts[0].split('.')[0]
    skin_cluster = find_related_skin_cluster(mesh)
    if not skin_cluster:
        raise RuntimeError("skinClusterが見つかりません")
    value = max(0.0, min(value, 1.0))
    for v in verts:
        cmds.skinPercent(skin_cluster, v, transformValue=[(joint, value)])

def add_weight(verts, joint, delta):
    if not verts:
        raise RuntimeError("頂点が選択されていません")
    mesh = verts[0].split('.')[0]
    skin_cluster = find_related_skin_cluster(mesh)
    if not skin_cluster:
        raise RuntimeError("skinClusterが見つかりません")
    for v in verts:
        val = cmds.skinPercent(skin_cluster, v, query=True, transform=joint)
        new_val = max(0.0, min(val + delta, 1.0))
        cmds.skinPercent(skin_cluster, v, transformValue=[(joint, new_val)])

# ----- コピー・ペースト機能 -----
def copy_weights():
    sel = cmds.ls(selection=True, flatten=True)
    if not sel:
        raise RuntimeError("頂点を選択してください")
    vtx = sel[0]
    mesh = vtx.split('.')[0]
    skin = find_related_skin_cluster(mesh)
    if not skin:
        raise RuntimeError("skinClusterが見つかりません")
    joints = cmds.skinPercent(skin, vtx, query=True, transform=None)
    weights = cmds.skinPercent(skin, vtx, query=True, value=True)
    return {
        "mesh": mesh,
        "skin": skin,
        "joints": joints,
        "weights": weights
    }

def paste_weights(copied_dict):
    if not copied_dict or "joints" not in copied_dict:
        raise RuntimeError("コピーされているウェイト情報がありません")
    sel = cmds.ls(selection=True, flatten=True)
    if not sel:
        raise RuntimeError("上書き対象の頂点を選択してください")
    mesh = copied_dict["mesh"]
    skin = copied_dict["skin"]
    joints = copied_dict["joints"]
    weights = copied_dict["weights"]
    for vtx in sel:
        tv = list(zip(joints, weights))
        cmds.skinPercent(skin, vtx, transformValue=tv)

# ----- ミラー・リフレクト機能 -----
def paste_mirror_weights(copied_dict):
    if not copied_dict or "mesh" not in copied_dict:
        raise RuntimeError("コピー済みウェイト情報がありません")
    mesh = copied_dict["mesh"]
    joints = copied_dict["joints"]
    weights = copied_dict["weights"]
    # コピーされたときの「頂点座標」を利用
    vtx_src = cmds.ls(selection=True, flatten=True)[0]
    pos = cmds.pointPosition(vtx_src)
    mesh = copied_dict["mesh"]
    skin = find_related_skin_cluster(mesh)
    mirror_pos = (-pos[0], pos[1], pos[2])
    vtx_count = cmds.polyEvaluate(mesh, vertex=True)
    tgt_idx = None
    for i in range(vtx_count):
        vtx_check = "%s.vtx[%d]" % (mesh, i)
        pos_check = cmds.pointPosition(vtx_check)
        if (abs(pos_check[0] - mirror_pos[0]) < 1e-4 and
            abs(pos_check[1] - mirror_pos[1]) < 1e-4 and
            abs(pos_check[2] - mirror_pos[2]) < 1e-4):
            tgt_idx = i
            break
    if tgt_idx is not None:
        tgt_vtx = "%s.vtx[%d]" % (mesh, tgt_idx)
        tv = list(zip(joints, weights))
        cmds.skinPercent(skin, tgt_vtx, transformValue=tv)
    else:
        raise RuntimeError("X反転位置の頂点が見つかりません")

def mirror_weights_x_pos2neg():
    sel = cmds.ls(selection=True)
    if not sel:
        raise RuntimeError("ミラー対象メッシュを選択してください")
    mesh = sel[0].split('.')[0]
    skin = find_related_skin_cluster(mesh)
    if not skin:
        raise RuntimeError("skinClusterが見つかりません")
    cmds.copySkinWeights(ss=skin, ds=skin, mirrorMode="YZ", surfaceAssociation="closestPoint", influenceAssociation="closestJoint")

def mirror_weights_x_neg2pos():
    sel = cmds.ls(selection=True)
    if not sel:
        raise RuntimeError("ミラー対象メッシュを選択してください")
    mesh = sel[0].split('.')[0]
    skin = find_related_skin_cluster(mesh)
    if not skin:
        raise RuntimeError("skinClusterが見つかりません")
    cmds.copySkinWeights(ss=skin, ds=skin, mirrorMode="YZ", mirrorInverse=True,
                         surfaceAssociation="closestPoint", influenceAssociation="closestJoint")
    
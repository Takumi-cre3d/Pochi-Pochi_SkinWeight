import json
import re
from maya import cmds
from ..core.skin_layer import SkinLayerManager  # 必要に合わせて正しいimportパスに

def safe_name(name):
    return re.sub(r'\W', '_', name)

def find_related_skin_cluster(mesh):
    skins = cmds.ls(cmds.listHistory(mesh), type='skinCluster')
    return skins[0] if skins else None

def get_all_weights_for_skin(skin, mesh):
    vtx_count = cmds.polyEvaluate(mesh, vertex=True)
    infs = cmds.skinCluster(skin, query=True, influence=True)
    data = []
    for i in range(vtx_count):
        vtx = f'{mesh}.vtx[{i}]'
        weights = cmds.skinPercent(skin, vtx, query=True, value=True)
        data.append(weights)
    return {"influences": infs, "weights": data}

def make_or_get_skin_data_node(skin):
    node_name = f"skinData_{safe_name(skin)}"
    exists = cmds.ls(node_name)
    created_new = False
    if exists:
        node = exists[0]
    else:
        node = cmds.createNode('network', name=node_name)
        created_new = True
        # message型skinCluster属性（重複時delete）
        if cmds.attributeQuery("skinCluster", node=node, exists=True):
            try:
                cmds.deleteAttr(f"{node}.skinCluster")
            except Exception:
                pass
        cmds.addAttr(node, ln="skinCluster", at="message")
        cmds.addAttr(node, ln="baseWeights", dt="string")
        cmds.addAttr(node, ln="layerData", dt="string")
        cmds.addAttr(node, ln="addInfluence", dt="string")
        mesh = cmds.listConnections(skin, type="mesh")
        mesh = mesh[0] if mesh else ""
        baseweight_dict = get_all_weights_for_skin(skin, mesh)
        cmds.setAttr(f"{node}.baseWeights", json.dumps(baseweight_dict), type="string")
        # ---- BaseレイヤデータをlayerDataに初期化 ----
        influences = baseweight_dict["influences"]
        vertex_count = len(baseweight_dict["weights"])
        mgr = SkinLayerManager(influences, vertex_count)
        layer = mgr.add_layer("Base")
        # baseWeightから反映
        for jidx, joint in enumerate(influences):
            for vtx_i, weight_list in enumerate(baseweight_dict["weights"]):
                layer["influences"][str(jidx)][vtx_i] = weight_list[jidx]
        data = mgr.export_json()
        cmds.setAttr(f"{node}.layerData", json.dumps(data), type="string")

    # skinCluster.message → skinData.skinCluster接続(1:N可)
    conns = cmds.listConnections(f"{node}.skinCluster", s=True, d=False) or []
    if skin not in conns:
        try:
            cmds.connectAttr(f"{skin}.message", f"{node}.skinCluster", force=True)
        except Exception as e:
            print(f"Message connect failed: {e}")

    return node

def find_skin_data_node(skin):
    node_name = f"skinData_{safe_name(skin)}"
    found = cmds.ls(node_name)
    return found[0] if found else None
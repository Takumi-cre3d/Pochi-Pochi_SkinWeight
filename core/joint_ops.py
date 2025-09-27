# PochiPochi_SkinWeight/core/joint_ops.py

from maya import cmds
from ..core.weight_ops import find_related_skin_cluster

def get_skin_influences(mesh):
    """meshについたskinClusterのinfluenceジョイントリスト"""
    skin = find_related_skin_cluster(mesh)
    if not skin:
        return []
    return cmds.skinCluster(skin, query=True, inf=True)

def get_vertex_influences(vertex, min_weight=0.0001):
    """頂点名→(joint, weight)ペアのリスト"""
    mesh = vertex.split('.')[0]
    skin = find_related_skin_cluster(mesh)
    if not skin:
        return []
    joints = cmds.skinPercent(skin, vertex, ignoreBelow=min_weight, query=True, transform=None)
    values = cmds.skinPercent(skin, vertex, ignoreBelow=min_weight, query=True, value=True)   # ←ここ修正
    result = []
    for j, v in zip(joints, values):
        result.append((j, v))
    return result
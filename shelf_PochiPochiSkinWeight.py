# shelf_PochiPochiSkinWeight.py - Pochi-Pochi_SkinWeight
import sys
import os

# 親パスをsys.pathに追加（Mayaのユーザーごとにここを修正）
BASE_PATH = r"D:\TA-Tools"  # 例: 実際の設置親ディレクトリに書き換えてください

if BASE_PATH not in sys.path:
    sys.path.insert(0, BASE_PATH)

try:
    import PochiPochi_SkinWeight
    PochiPochi_SkinWeight.launch()
except Exception as e:
    import traceback
    import maya.cmds as cmds
    cmds.warning("Pochi-Pochi_SkinWeightの起動中にエラー: {}".format(e))
    traceback.print_exc()
# my_skin_tool/schema.py
import json
import maya.api.OpenMaya as om  # 警告出力用

SCHEMA_VERSION = 1

KEY_NAME = "name"
KEY_OPACITY = "opacity"

def load_metadata(json_str):
    """
    JSON文字列からメタデータを安全に読み込む。
    未知のバージョンや破損があっても、無言で [] にせず可能な限り救済する。
    """
    if not json_str:
        return []
        
    try:
        data = json.loads(json_str)
        
        # v0 (旧仕様): 単なるリストだった場合のマイグレーション
        if isinstance(data, list):
            return data
            
        # v1以降: バージョン情報を含む辞書型
        if isinstance(data, dict):
            version = data.get("version", 0)
            
            # 未来のバージョンで作成されたデータを開いた場合
            if version > SCHEMA_VERSION:
                om.MGlobal.displayWarning(
                    f"[PochiPochi] 未知のデータバージョン({version})を検出しました。"
                    f"現在のツール(v{SCHEMA_VERSION})では一部のデータが読み込めない可能性があります。"
                )
            
            # .get()でキーが存在しなくても落ちないようにする
            return data.get("layers", [])
            
        return []
        
    except json.JSONDecodeError:
        om.MGlobal.displayWarning("[PochiPochi] メタデータのJSON解析に失敗しました。データが破損しています。")
        return []

def dump_metadata(layers):
    """レイヤーリストを最新のスキーマバージョンのJSON文字列に変換する"""
    meta_list = []
    for l in layers:
        # 必須キーが欠損していてもデフォルト値で埋めてクラッシュを防ぐ
        meta_list.append({
            KEY_NAME: l.get(KEY_NAME, "UnknownLayer"),
            KEY_OPACITY: l.get(KEY_OPACITY, 1.0)
        })
        
    data = {
        "version": SCHEMA_VERSION,
        "layers": meta_list
    }
    return json.dumps(data)
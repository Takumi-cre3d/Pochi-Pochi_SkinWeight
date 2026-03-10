import json

SCHEMA_VERSION = 1

# キー名の定数化（タイポによるバグを防ぐ）
KEY_NAME = "name"
KEY_OPACITY = "opacity"

def load_metadata(json_str):
    """JSON文字列からメタデータを安全に読み込み、必要なら最新スキーマに移行する"""
    if not json_str:
        return []
        
    try:
        data = json.loads(json_str)
        
        # v0 (以前の実装): 単なるリストだった場合のマイグレーション
        if isinstance(data, list):
            return data
            
        # v1以降: バージョン情報を含む辞書型
        if isinstance(data, dict):
            if data.get("version") == 1:
                return data.get("layers", [])
                
        return []
    except json.JSONDecodeError:
        return []

def dump_metadata(layers):
    """レイヤーリストを最新のスキーマバージョンのJSON文字列に変換する"""
    meta_list = [{KEY_NAME: l[KEY_NAME], KEY_OPACITY: l[KEY_OPACITY]} for l in layers]
    data = {
        "version": SCHEMA_VERSION,
        "layers": meta_list
    }
    return json.dumps(data)
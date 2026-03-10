# my_skin_tool/schema.py
import json
import logging

# DCC非依存のロガーを設定
logger = logging.getLogger("PochiPochi_Schema")

SCHEMA_VERSION = 1
KEY_NAME = "name"
KEY_OPACITY = "opacity"

def load_metadata(json_str):
    if not json_str: return []
    try:
        data = json.loads(json_str)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            version = data.get("version", 0)
            if version > SCHEMA_VERSION:
                logger.warning(
                    f"未知のデータバージョン({version})を検出しました。"
                    f"現在のツール(v{SCHEMA_VERSION})では一部のデータが読み込めない可能性があります。"
                )
            return data.get("layers", [])
        return []
    except json.JSONDecodeError:
        logger.error("メタデータのJSON解析に失敗しました。データが破損しています。")
        return []

def dump_metadata(layers):
    meta_list = []
    for l in layers:
        meta_list.append({
            KEY_NAME: l.get(KEY_NAME, "UnknownLayer"),
            KEY_OPACITY: l.get(KEY_OPACITY, 1.0)
        })
    data = {"version": SCHEMA_VERSION, "layers": meta_list}
    return json.dumps(data)
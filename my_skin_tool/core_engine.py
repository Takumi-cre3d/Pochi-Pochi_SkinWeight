import traceback

class PochiCoreEngine:
    """C++拡張モジュール (skin_core) のラッパー"""
    def __init__(self):
        self.cpp_engine = None
        try:
            # 環境に応じた.pydのロード
            from .core import skin_core
            self.cpp_engine = skin_core.WeightEngine()
        except ImportError as e:
            print(f"[PochiPochi] C++ Core Load Error: {e}")
            traceback.print_exc()
            raise RuntimeError("C++ Skin Core plugin (skin_core.pyd) をロードできませんでした。ビルドと配置を確認してください。")

    def add_weight(self, weights_np, vtx_id, bone_id, add_value):
        self.cpp_engine.add_weight(weights_np, vtx_id, bone_id, add_value)

    def blend_layers(self, base_w, layer_w, opacity):
        return self.cpp_engine.blend_layers(base_w, layer_w, opacity)
        
    # ※ 将来ここに smooth_weights などのラッパーメソッドを追加します
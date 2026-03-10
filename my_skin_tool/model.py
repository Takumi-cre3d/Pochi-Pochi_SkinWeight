import numpy as np

class LayerStack:
    """DCC非依存のレイヤーデータ構造と合成計算"""
    def __init__(self, engine, num_vertices, num_influences):
        self.engine = engine  # PochiCoreEngine
        self.num_vertices = num_vertices
        self.num_influences = num_influences
        self.layers = []

    def set_layers(self, layers):
        self.layers = layers

    def blend_all(self):
        """全レイヤーを合成し、誤差吸収済みのフラットなリストを返す"""
        if not self.layers: 
            return []
        
        # 合成の起点は BaseLayer (layers[0])
        current_weights = self.layers[0]["weights"].copy() * self.layers[0]["opacity"]
        
        # 2枚目以降をブレンド
        for layer in self.layers[1:]:
            current_weights = self.engine.blend_layers(current_weights, layer["weights"], layer["opacity"])
            
        current_weights_64 = current_weights.astype(np.float64)
        row_sums = current_weights_64.sum(axis=1, keepdims=True)
        final_weights = np.divide(current_weights_64, row_sums, out=np.zeros_like(current_weights_64), where=row_sums!=0)
        
        # ゼロ除算対策（BaseLayerへフォールバック）
        zero_mask = (row_sums.flatten() == 0)
        if np.any(zero_mask):
            final_weights[zero_mask] = self.layers[0]["weights"][zero_mask].astype(np.float64)
            
        # 浮動小数点誤差の吸収
        current_sums = final_weights.sum(axis=1)
        errors = 1.0 - current_sums
        max_indices = np.argmax(final_weights, axis=1)
        row_indices = np.arange(self.num_vertices)
        final_weights[row_indices, max_indices] += errors
        
        return final_weights.flatten().tolist()
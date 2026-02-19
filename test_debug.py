import numpy as np
import skin_core

def main():
    vertex_count = 5
    bone_count = 3
    base_layer = np.zeros((vertex_count, bone_count), dtype=np.float32)
    base_layer[:, 0] = 1.0 
    anim_layer = np.zeros((vertex_count, bone_count), dtype=np.float32)
    anim_layer[2, 1] = 1.0 

    engine = skin_core.WeightEngine()

    print("--- 初期状態 (Base Layer) ---")
    print(base_layer)

    print("\n--- レイヤー合成 (Opacity 0.5) ---")
    final_weights = engine.blend_layers(base_layer, anim_layer, 0.5)
    print(final_weights)

    print("\n--- Pochi-Pochi (頂点0のボーン1に +0.3) ---")
    engine.add_weight(final_weights, 0, 1, 0.3)
    print(final_weights)

if __name__ == "__main__":
    main()
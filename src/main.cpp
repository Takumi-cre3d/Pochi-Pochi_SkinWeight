#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <iostream>
#include <algorithm> // for std::clamp

namespace py = pybind11;

class WeightEngine {
public:
    WeightEngine() {}

    /**
     * @brief レイヤー合成計算（簡易版：Base + Layer * Opacity）
     * * @param base_weights  (N, M) のNumPy配列: ベースのウェイト
     * @param layer_weights (N, M) のNumPy配列: 調整レイヤーのウェイト
     * @param opacity       レイヤーの不透明度 (0.0 - 1.0)
     * @return              合成された結果のNumPy配列
     */
    py::array_t<float> blend_layers(
        py::array_t<float> base_weights,
        py::array_t<float> layer_weights,
        float opacity
    ) {
        // バッファ情報の取得（データの整合性チェックなどは省略）
        auto buf_base = base_weights.request();
        auto buf_layer = layer_weights.request();

        // 出力用のNumPy配列を作成 (入力と同じサイズ)
        auto result = py::array_t<float>(buf_base.size);
        result.resize({buf_base.shape[0], buf_base.shape[1]}); // 形状を合わせる
        
        auto buf_result = result.request();

        // 高速アクセスのためのポインタ取得
        float* ptr_base = static_cast<float*>(buf_base.ptr);
        float* ptr_layer = static_cast<float*>(buf_layer.ptr);
        float* ptr_result = static_cast<float*>(buf_result.ptr);

        size_t total_elements = buf_base.size;

        // 【ここが計算のコア】
        // SIMD化などを狙えるループ構造。OpenMPで並列化も容易。
        for (size_t i = 0; i < total_elements; i++) {
            // ブレンド計算式: Base + (Layer * Opacity)
            // 実際はここでOverlayやMultiplyなどの計算式を分岐させる
            float val = ptr_base[i] + (ptr_layer[i] * opacity);
            
            // クランプ (0.0 - 1.0)
            ptr_result[i] = std::clamp(val, 0.0f, 1.0f);
        }

        return result;
    }

    /**
     * @brief Pochi-Pochi機能のコア: 特定頂点への数値加算
     * NumPy配列を直接書き換える（参照渡し）
     */
    void add_weight(py::array_t<float> weights, int vertex_id, int bone_id, float add_value) {
        // uncheckedアクセサを使うと、Python境界チェックをスキップして高速アクセス可能
        // <2> は2次元配列であることを意味する
        auto r = weights.mutable_unchecked<2>(); // 書き込み可能

        // 範囲外チェックはC++側で行う
        if (vertex_id < 0 || vertex_id >= r.shape(0) || bone_id < 0 || bone_id >= r.shape(1)) {
            return; 
        }

        // 加算処理
        float new_val = r(vertex_id, bone_id) + add_value;
        r(vertex_id, bone_id) = std::clamp(new_val, 0.0f, 1.0f);
        
        // ※ 本来はこの後、行（頂点）ごとの合計が1.0になるような正規化(Normalization)処理を入れる
    }
};

// Pythonモジュール定義
PYBIND11_MODULE(skin_core, m) {
    m.doc() = "DCC-Agnostic Skin Weight Engine";

    py::class_<WeightEngine>(m, "WeightEngine")
        .def(py::init<>())
        .def("blend_layers", &WeightEngine::blend_layers, 
             "Blend base and layer weights",
             py::arg("base"), py::arg("layer"), py::arg("opacity"))
        .def("add_weight", &WeightEngine::add_weight, 
             "Add value to specific weight (Pochi-Pochi)",
             py::arg("weights"), py::arg("v_id"), py::arg("b_id"), py::arg("value"));
}
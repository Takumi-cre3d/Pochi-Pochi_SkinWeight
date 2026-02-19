import sys
import os

def _load_core():
    current_dir = os.path.dirname(__file__)
    core_dir = os.path.join(current_dir, "core")
    
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
        
    try:
        import skin_core
        return skin_core
    except ImportError as e:
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        raise RuntimeError(
            f"Failed to load skin_core for Python {version}.\nError: {e}"
        )

engine_module = _load_core()
WeightEngine = engine_module.WeightEngine
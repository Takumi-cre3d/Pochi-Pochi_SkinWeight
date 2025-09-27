# PochiPochi_SkinWeight/__init__.py

from .ui.main_window import PochiPochiSkinWeightWindow

_window_instance = None

def launch():
    global _window_instance
    try:
        if _window_instance is not None:
            _window_instance.close()
            _window_instance = None
    except:
        _window_instance = None
    _window_instance = PochiPochiSkinWeightWindow()
    _window_instance.show()
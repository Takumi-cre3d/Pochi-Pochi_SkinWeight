import sys

qt_binding = None
QtWidgets = None
QtCore = None

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
        QGroupBox
    )
    from PySide6 import QtCore
    import shiboken6
    qt_binding = "PySide6"
except ImportError:
    try:
        from PySide2.QtWidgets import (
            QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
            QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
            QGroupBox
        )
        from PySide2 import QtCore
        import shiboken2
        qt_binding = "PySide2"
    except ImportError:
        try:
            from PyQt6.QtWidgets import (
                QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
                QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
                QGroupBox
            )
            from PyQt6 import QtCore
            import sip
            qt_binding = "PyQt6"
        except ImportError:
            from PyQt5.QtWidgets import (
                QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
                QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
                QGroupBox
            )
            from PyQt5 import QtCore
            import sip
            qt_binding = "PyQt5"

# Qtエイリアスをmoduleローカル用（オプション）
def wrapinstance(ptr, base=None):
    if qt_binding == "PySide6":
        return shiboken6.wrapInstance(int(ptr), base) if base else shiboken6.wrapInstance(int(ptr), QWidget)
    elif qt_binding == "PySide2":
        return shiboken2.wrapInstance(int(ptr), base) if base else shiboken2.wrapInstance(int(ptr), QWidget)
    elif qt_binding in ("PyQt5", "PyQt6"):
        return sip.wrapinstance(int(ptr), base) if base else sip.wrapinstance(int(ptr), QWidget)
    else:
        raise ImportError("No supported Qt binding found")

# QtCore.MatchExactly 用等
QtMatchExactly = QtCore.Qt.MatchExactly

# エイリアスとしてimportしやすいようにエクスポート
__all__ = [
    "QApplication", "QMainWindow", "QWidget", "QDialog", "QVBoxLayout", "QHBoxLayout",
    "QLabel", "QPushButton", "QLineEdit", "QListWidget", "QListWidgetItem",
    "QGroupBox", "wrapinstance", "QtCore", "QtMatchExactly"
]
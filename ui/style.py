# PochiPochi_SkinWeight/ui/style.py

preset_button_map = {
    0.0:   "background-color: #1997e6; color: white;",   # blue
    0.1:   "background-color: #46a5e6; color: white;",
    0.25:  "background-color: #6ec2ea; color: #222;",
    0.5:   "background-color: #ffe875; color: #222;",    # yellow
    0.75:  "background-color: #ff9c66; color: #222;",    # orange
    1.0:   "background-color: #e14b4b; color: white;"    # red
}

def preset_button_style(val):
    base = preset_button_map.get(val, "background-color:#888; color:white;")
    return (
        "QPushButton {"
        f"{base}"
        " font-weight: bold;"
        " min-width: 36px; max-width: 50px;"
        " min-height: 36px;"
        " border-radius: 12px;"
        " font-size: 13px;"
        " }"
    )

relative_button = """
QPushButton {
    background-color: #31345b;
    color: white;
    font-weight: bold;
    font-size: 22px;
    border: none;
    border-radius: 18px;
    min-width: 36px; max-width: 36px;
    min-height: 36px; max-height: 36px;
}
QPushButton:pressed {
    background-color: #181b2f;
}
"""

relative_input = """
QLineEdit {
    background: #22243a;
    color: #ffd700;
    border: 1px solid #888;
    border-radius: 10px;
    font-size: 16px;
    font-weight: bold;
    min-width: 52px; max-width: 70px;
    min-height: 32px; max-height: 36px;
    qproperty-alignment: AlignCenter;
}
"""

group_box = """
QGroupBox {
    border: 1px solid #888;
    border-radius: 10px;
    margin-top: 10px;
    padding: 4px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    color: #ddd;
    font-weight: bold;
    font-size: 13px;
}
"""

status_label = """
QLabel {
    color: #2afaaa;
    font-size: 13px;
    font-weight: bold;
    padding: 4px;
}
"""
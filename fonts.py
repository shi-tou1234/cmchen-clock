"""字体能力：系统字体枚举、从字体文件加载。"""

from PySide6.QtGui import QFontDatabase


def list_system_families():
    """返回系统已安装字体族名列表（已排序）。"""
    return sorted(QFontDatabase.families())


def load_font_file(path):
    """加载字体文件（ttf/otf/ttc），成功返回字体族名，失败返回 None。

    加载后该字体对整个应用生效（QFontDatabase 全局注册）。
    """
    font_id = QFontDatabase.addApplicationFont(path)
    if font_id < 0:
        return None
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return None
    return families[0]

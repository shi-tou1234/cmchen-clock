"""设置持久化：JSON 读写、缺省值、坏文件回退默认。

安全设计：设置文件名固定为 settings.json，位置只由 base 目录决定
（默认 ~/.desktop-clock）。base 先 resolve()，写入前用
relative_to 做白名单包含校验，从结构上排除路径穿越。
"""

import json
from pathlib import Path

SETTINGS_FILENAME = "settings.json"

WINDOW_BEHAVIORS = ("floating", "normal", "desktop")
BEHAVIOR_LABELS = {
    "floating": "浮在其他窗口上方",
    "normal": "普通窗口",
    "desktop": "固定在桌面",
}

# 屏幕位置预设：上/中/下 × 左/中/右 九个锚点及其菜单/面板标签。
POSITION_PRESETS = (
    "top-left", "top-center", "top-right",
    "middle-left", "middle-center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
)
POSITION_LABELS = {
    "top-left": "上方靠左",
    "top-center": "上方居中",
    "top-right": "上方靠右",
    "middle-left": "中间靠左",
    "middle-center": "中间居中",
    "middle-right": "中间靠右",
    "bottom-left": "下方靠左",
    "bottom-center": "下方居中",
    "bottom-right": "下方靠右",
}

DEFAULTS = {
    "font_family": "",        # 空 = 用应用默认字体
    "font_file": "",          # 从字体文件加载的路径；非空且可加载时优先于 font_family
    "font_size": 64,
    "color": "#FFFFFF",
    "show_date": True,
    "show_seconds": True,
    "hour24": True,
    "opacity": 0.9,
    "window_behavior": "desktop",  # floating / normal / desktop
    "pos_locked": False,           # 锁定位置：禁止拖动
    "autostart": False,            # 开机自启动（登录后自动运行）
    "pos_x": None,
    "pos_y": None,
    "pos_preset": "",              # 当前吸附的九宫格预设；"" = 自定义（拖动/手输坐标）
    "pos_anchor": None,            # 摆放时的屏幕可用区 {"x","y","w","h"}，用于识别显示器尺寸变化
}

_FONT_SIZE_MIN, _FONT_SIZE_MAX = 8, 200
_OPACITY_MIN, _OPACITY_MAX = 0.1, 1.0


def normalize_window_behavior(value, default=DEFAULTS["window_behavior"]):
    """校验显示方式取值；非法时回退 default。"""
    if isinstance(value, str) and value in WINDOW_BEHAVIORS:
        return value
    return default


def settings_dir():
    """设置目录：用户主目录下的 .desktop-clock（win/mac/linux 一致）。"""
    return str(Path.home() / ".desktop-clock")


def _base_root(base=None):
    """解析并返回设置根目录（已 resolve 的绝对路径）。"""
    return Path(base).resolve() if base else Path(settings_dir()).resolve()


def settings_path(base=None):
    """设置文件完整路径（base 内固定文件名，无穿越面）。"""
    return _base_root(base) / SETTINGS_FILENAME


def normalize_color(value, default=DEFAULTS["color"]):
    """校验颜色值为 "#RRGGBB"（大写）；非法时回退 default。"""
    if isinstance(value, str) and len(value) == 7 and value[0] == "#":
        try:
            int(value[1:], 16)
        except ValueError:
            return default
        return value.upper()
    return default


def _coerce_int(value, default):
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _coerce_bool(value, default):
    if isinstance(value, bool):
        return value
    return default


def normalize_pos_preset(value, default=DEFAULTS["pos_preset"]):
    """校验九宫格预设键；空串=自定义，非法值回退 default。"""
    if isinstance(value, str) and (value == "" or value in POSITION_PRESETS):
        return value
    return default


def _coerce_anchor(value):
    """校验屏幕可用区锚点：4 个整数键齐全且宽高为正才接受，否则 None。"""
    if not isinstance(value, dict):
        return None
    out = {}
    for key in ("x", "y", "w", "h"):
        num = _coerce_int(value.get(key), None)
        if num is None:
            return None
        out[key] = num
    if out["w"] <= 0 or out["h"] <= 0:
        return None
    return out


def merged_settings(raw):
    """把任意来源的 dict 合并到缺省值上：缺字段补默认，类型不对回退默认。

    旧版设置只有 always_on_top 布尔键，迁移规则：true→floating，
    false→desktop；迁移后结果里不再保留 always_on_top。
    """
    result = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return result
    if "window_behavior" in raw:
        result["window_behavior"] = normalize_window_behavior(raw.get("window_behavior"))
    elif "always_on_top" in raw:
        result["window_behavior"] = "floating" if raw.get("always_on_top") is True else "desktop"
    for key in ("font_family", "font_file"):
        if isinstance(raw.get(key), str):
            result[key] = raw[key]
    size = _coerce_int(raw.get("font_size"), None)
    if size is not None and _FONT_SIZE_MIN <= size <= _FONT_SIZE_MAX:
        result["font_size"] = size
    result["color"] = normalize_color(raw.get("color"), DEFAULTS["color"])
    for key in ("show_date", "show_seconds", "hour24", "pos_locked", "autostart"):
        result[key] = _coerce_bool(raw.get(key), DEFAULTS[key])
    opacity = raw.get("opacity")
    if isinstance(opacity, (int, float)) and not isinstance(opacity, bool):
        if _OPACITY_MIN <= opacity <= _OPACITY_MAX:
            result["opacity"] = float(opacity)
    for key in ("pos_x", "pos_y"):
        result[key] = _coerce_int(raw.get(key), None)
    result["pos_preset"] = normalize_pos_preset(raw.get("pos_preset"))
    result["pos_anchor"] = _coerce_anchor(raw.get("pos_anchor"))
    return result


def load_settings(base=None):
    """读设置；文件缺失、坏 JSON、字段缺失/类型错时逐级回退默认，绝不抛异常。"""
    target = settings_path(base)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    return merged_settings(raw)


def save_settings(settings, base=None):
    """写设置，自动建目录；与 load_settings 严格互逆。

    白名单包含校验：resolved 目标必须仍位于 resolved 的 base 目录内。
    """
    root = _base_root(base)
    root.mkdir(parents=True, exist_ok=True)
    target = (root / SETTINGS_FILENAME).resolve()
    target.relative_to(root)
    merged = merged_settings(settings)
    target.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged

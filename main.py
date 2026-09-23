"""桌面时钟主程序。

用法：
    python main.py            # 运行时钟
    python main.py --selftest # 自检：三种显示方式各建窗渲染一帧后退出

显示方式（window_behavior）：
    floating  浮在其他窗口上方（任务栏可见）
    normal    普通窗口（任务栏可见）
    desktop   固定在桌面：压在其他窗口下方、锁定拖动、不进任务栏（默认）

屏幕位置：右键/托盘菜单「屏幕位置」九宫格预设即时摆放，设置面板里还可
输入精确 X/Y 坐标；拖动（非桌面模式且未锁定）可自由摆放。桌面模式或
勾选「锁定位置」时禁止拖动；系统托盘常驻（显示/隐藏、显示方式、
屏幕位置、锁定位置、设置、退出）。设置持久化到
~/.desktop-clock/settings.json（见 settings.py 的安全设计）。

显示器适配：每次摆放都记下当时的屏幕可用区（pos_anchor）与吸附的预设
（pos_preset）；屏幕插拔、分辨率/缩放或可用区变化（含窗口跨屏）时防抖
触发 _check_screen_fit——先按原预设重摆，没有预设则按旧坐标推断最贴近的
预设，从而自动回到合适位置，不再因换用笔记本内置屏/外接屏而偏移。
"""

import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QDate, QEvent, QPoint, QRect, QTime, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import autostart
import fonts
import settings as settings_mod
from clock_core import format_date, format_time
from settings import (
    BEHAVIOR_LABELS,
    POSITION_LABELS,
    POSITION_PRESETS,
    WINDOW_BEHAVIORS,
)

MSG_TITLE = "桌面时钟"

# 各显示方式的窗口标志：normal/floating 带任务栏条目（真软件感），
# desktop 用 Tool 不进任务栏，并压在其他窗口下方、不接受焦点（点击不上浮）。
MODE_FLAGS = {
    "floating": Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint,
    "normal": Qt.FramelessWindowHint | Qt.Window,
    "desktop": (
        Qt.FramelessWindowHint | Qt.Tool
        | Qt.WindowStaysOnBottomHint | Qt.WindowDoesNotAcceptFocus
    ),
}


POSITION_MARGIN = 24

# 屏幕几何变化（改分辨率、插拔显示器、缩放调整）信号密集，防抖合并成一次处理
SCREEN_FIT_DEBOUNCE_MS = 300
# 重摆后继续自校验的轮数：等窗口管理器/DPI 落定后二次修正（无变化即停）
FIT_VERIFY_ROUNDS = 3

_FIT_STATE = {"inited": False, "last_stay_log": 0.0}


def fit_log(message):
    """位置核对诊断日志 → ~/.desktop-clock/fit.log；每次启动清空，pytest 里静默。"""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        target = Path(settings_mod.settings_dir()) / "fit.log"
        if not _FIT_STATE["inited"]:
            target.write_text("", encoding="utf-8")
            _FIT_STATE["inited"] = True
        with target.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {message}\n")
    except OSError:
        pass  # 日志失败绝不影响时钟本身


def screens_summary():
    """一行概括当前所有屏幕：名称@原点x尺寸/DPR，排障看换屏过程用。"""
    parts = []
    for screen in QApplication.screens():
        geo = screen.geometry()
        parts.append(f"{screen.name()}@{geo.x()},{geo.y()},"
                     f"{geo.width()}x{geo.height()}/dpr{screen.devicePixelRatio()}")
    return "[" + " ".join(parts) + "]"


def asset_path(name):
    """资源目录：源码运行=项目内 assets/；exe 内运行=PyInstaller 解包目录。"""
    if hasattr(sys, "_MEIPASS"):
        root = Path(sys._MEIPASS)
    else:
        root = Path(__file__).resolve().parent
    return root / "assets" / name


def app_icon():
    """应用图标（不存在时返回空 QIcon，调用方自行降级）。"""
    return QIcon(str(asset_path("icon.ico")))


def resolve_font(cfg):
    """优先字体文件，其次所选字体族，最后应用默认。"""
    if cfg.get("font_file"):
        family = fonts.load_font_file(cfg["font_file"])
        if family:
            font = QFont(family)
            font.setPointSize(cfg["font_size"])
            return font
    if cfg.get("font_family"):
        font = QFont(cfg["font_family"])
    else:
        font = QFont()
    font.setPointSize(cfg["font_size"])
    return font


def preset_point(key, width, height, area):
    """按预设锚点把 (width, height) 的窗口摆到屏幕可用区 area 上，返回左上角坐标。

    area 用 QRect availableGeometry（不含任务栏/程序坞），边缘留 POSITION_MARGIN。
    key 形如 "middle-center"：纵向 top/middle/bottom × 横向 left/center/right。
    """
    vertical, horizontal = key.split("-", 1)
    if horizontal == "left":
        x = area.x() + POSITION_MARGIN
    elif horizontal == "right":
        x = area.x() + area.width() - width - POSITION_MARGIN
    else:
        x = area.x() + (area.width() - width) // 2
    if vertical == "top":
        y = area.y() + POSITION_MARGIN
    elif vertical == "bottom":
        y = area.y() + area.height() - height - POSITION_MARGIN
    else:
        y = area.y() + (area.height() - height) // 2
    return x, y


def anchor_of(area):
    """QRect 可用区 → 可持久化的 dict（settings.pos_anchor 格式）。"""
    return {"x": area.x(), "y": area.y(), "w": area.width(), "h": area.height()}


def area_from_anchor(anchor):
    """pos_anchor dict → QRect；None/键不齐返回 None（旧版设置无此键）。"""
    if not isinstance(anchor, dict) or not all(k in anchor for k in ("x", "y", "w", "h")):
        return None
    return QRect(anchor["x"], anchor["y"], anchor["w"], anchor["h"])


def area_contains_window(area, x, y, width, height):
    """按窗口中心点判断是否在可用区内：半悬屏幕边缘不算跑偏，避免误搬。"""
    cx, cy = x + width // 2, y + height // 2
    return area.x() <= cx <= area.x() + area.width() and \
        area.y() <= cy <= area.y() + area.height()


def nearest_preset(width, height, x, y, area):
    """当前位置最贴近的九宫格预设（到九个锚点的欧氏距离取最小）。"""
    best, best_dist = "middle-center", None
    for key in POSITION_PRESETS:
        px, py = preset_point(key, width, height, area)
        dist = (px - x) ** 2 + (py - y) ** 2
        if best_dist is None or dist < best_dist:
            best, best_dist = key, dist
    return best


class SettingsDialog(QDialog):
    """设置面板：显示方式、锁定位置、屏幕位置、字体、字号、颜色、开关、透明度＋实时预览。"""

    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle("时钟设置")
        self.cfg = dict(current)
        self._loaded_file_family = None
        if self.cfg.get("font_file"):
            # 打开面板时同步字体文件状态，加载失败则放弃该文件
            family = fonts.load_font_file(self.cfg["font_file"])
            self._loaded_file_family = family
            if family is None:
                self.cfg["font_file"] = ""

        self._build_preview()
        self._build_form()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.preview)
        layout.addLayout(self.form)
        layout.addWidget(buttons)

        self._refresh_preview()
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(1000)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_timer.start()

    def _build_preview(self):
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(96)
        self.preview.setStyleSheet(
            "background: rgba(30, 32, 48, 230); border-radius: 10px; padding: 8px;")

    def _build_form(self):
        self.behavior_combo = QComboBox()
        for mode in WINDOW_BEHAVIORS:
            self.behavior_combo.addItem(BEHAVIOR_LABELS[mode], mode)
        self.behavior_combo.setCurrentIndex(
            WINDOW_BEHAVIORS.index(self.cfg["window_behavior"]))

        self.font_combo = QComboBox()
        self._fill_font_combo()

        self.font_file_btn = QPushButton("从字体文件加载…")
        self.font_file_btn.clicked.connect(self._pick_font_file)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 200)
        self.size_spin.setValue(self.cfg["font_size"])

        self.color_btn = QPushButton(self.cfg["color"])
        self.color_btn.setFixedWidth(120)
        self._paint_color_button()
        self.color_btn.clicked.connect(self._pick_color)

        self.date_check = QCheckBox("显示日期")
        self.date_check.setChecked(self.cfg["show_date"])
        self.seconds_check = QCheckBox("显示秒")
        self.seconds_check.setChecked(self.cfg["show_seconds"])
        self.h24_check = QCheckBox("24 小时制")
        self.h24_check.setChecked(self.cfg["hour24"])
        for check in (self.date_check, self.seconds_check, self.h24_check):
            check.toggled.connect(self._refresh_preview)

        self.lock_check = QCheckBox("锁定位置（禁止拖动）")
        self.lock_check.setChecked(self.cfg["pos_locked"])

        self.autostart_check = QCheckBox("开机自启动（登录后自动运行）")
        self.autostart_check.setChecked(self.cfg["autostart"])
        self.autostart_check.setEnabled(autostart.is_supported())

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(round(self.cfg["opacity"] * 100))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%"))

        self.form = QFormLayout()
        self.form.addRow("显示方式", self.behavior_combo)
        self.form.addRow("", self.lock_check)
        self.form.addRow("", self.autostart_check)
        self.form.addRow("字体", self.font_combo)
        self.form.addRow("", self.font_file_btn)
        self.form.addRow("字号", self.size_spin)
        self.form.addRow("颜色", self.color_btn)
        self.form.addRow(self.date_check)
        self.form.addRow(self.seconds_check)
        self.form.addRow(self.h24_check)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        self.form.addRow("不透明度", opacity_row)

        self.pos_preset_combo = QComboBox()
        self.pos_preset_combo.addItem("自定义", "")
        for key in POSITION_PRESETS:
            self.pos_preset_combo.addItem(POSITION_LABELS[key], key)

        self.pos_x_spin = QSpinBox()
        self.pos_x_spin.setRange(-20000, 20000)
        self.pos_y_spin = QSpinBox()
        self.pos_y_spin.setRange(-20000, 20000)
        self._load_position_spins()
        # 先回显已存预设再接信号，避免初始化时用预设坐标覆盖当前坐标
        self._syncing_preset = False
        idx = self.pos_preset_combo.findData(self.cfg.get("pos_preset") or "")
        self.pos_preset_combo.setCurrentIndex(max(0, idx))
        self.pos_preset_combo.currentIndexChanged.connect(self._apply_preset_to_spins)
        self.pos_x_spin.valueChanged.connect(self._on_pos_spin_changed)
        self.pos_y_spin.valueChanged.connect(self._on_pos_spin_changed)

        pos_row = QHBoxLayout()
        pos_row.addWidget(self.pos_x_spin)
        pos_row.addWidget(self.pos_y_spin)
        self.form.addRow("屏幕位置", self.pos_preset_combo)
        self.form.addRow("坐标 X / Y", pos_row)

        # 任一影响外观的控件变动 → 实时刷新预览
        self.behavior_combo.currentIndexChanged.connect(self._refresh_preview)
        self.font_combo.currentIndexChanged.connect(self._refresh_preview)
        self.size_spin.valueChanged.connect(self._refresh_preview)

    def _fill_font_combo(self):
        self.font_combo.clear()
        self.font_combo.addItem("系统默认", "")
        for family in fonts.list_system_families():
            self.font_combo.addItem(family, family)
        current = self._loaded_file_family or self.cfg["font_family"]
        if current:
            if self.font_combo.findData(current) < 0:
                self.font_combo.addItem(f"{current}（文件）", current)
            self.font_combo.setCurrentIndex(self.font_combo.findData(current))

    def _pick_font_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择字体文件", "", "字体文件 (*.ttf *.otf *.ttc)")
        if not path:
            return
        family = fonts.load_font_file(path)
        if family is None:
            QMessageBox.warning(self, MSG_TITLE, "无法加载该字体文件")
            return
        self.cfg["font_file"] = path
        self._loaded_file_family = family
        self._fill_font_combo()
        self._refresh_preview()

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.cfg["color"]), self, "选择颜色")
        if color.isValid():
            self.cfg["color"] = color.name()
            self._paint_color_button()
            self._refresh_preview()

    def _paint_color_button(self):
        self.color_btn.setText(self.cfg["color"])
        self.color_btn.setStyleSheet(f"background-color: {self.cfg['color']}; color: #000000;")

    def _refresh_preview(self):
        """用当前字体/字号/颜色/开关即时渲染预览文本。"""
        cfg = self._preview_cfg()
        self.preview.setFont(resolve_font(cfg))
        now = QTime.currentTime()
        date = QDate.currentDate()
        text = format_time(
            now.hour(), now.minute(), now.second(),
            show_seconds=cfg["show_seconds"], hour24=cfg["hour24"])
        if cfg["show_date"]:
            text += "\n" + format_date(date.year(), date.month(), date.day())
        self.preview.setText(text)
        self.preview.setStyleSheet(
            f"background: rgba(30, 32, 48, 230); border-radius: 10px; padding: 8px;"
            f"color: {cfg['color']};")

    def _preview_cfg(self):
        return {
            "font_file": self.cfg["font_file"] if self._loaded_file_family else "",
            "font_family": self.font_combo.currentData() or "",
            "font_size": self.size_spin.value(),
            "color": self.cfg["color"],
            "show_date": self.date_check.isChecked(),
            "show_seconds": self.seconds_check.isChecked(),
            "hour24": self.h24_check.isChecked(),
        }

    def _target_area(self):
        """预设定位用的屏幕可用区：取当前窗口所在屏幕，退化为主屏。"""
        parent = self.parent()
        if parent is not None and hasattr(parent, "screen"):
            screen = parent.screen()
            if screen is not None:
                return screen.availableGeometry()
        return QApplication.primaryScreen().availableGeometry()

    def _load_position_spins(self):
        """初始 X/Y：以时钟当前位置为准（拖动后即时同步），无窗口时用已存坐标。"""
        parent = self.parent()
        if parent is not None and hasattr(parent, "pos"):
            x, y = parent.pos().x(), parent.pos().y()
        else:
            x, y = self.cfg.get("pos_x") or 0, self.cfg.get("pos_y") or 0
        self.pos_x_spin.setValue(x)
        self.pos_y_spin.setValue(y)

    def _on_pos_spin_changed(self, value):
        """手动改坐标即脱离预设；程序回填坐标时由 _syncing_preset 屏蔽。"""
        if self._syncing_preset:
            return
        self.pos_preset_combo.setCurrentIndex(0)  # 「自定义」

    def _apply_preset_to_spins(self):
        """选中预设时按当前屏幕与时钟尺寸算出像素坐标，回填到 X/Y 输入框。"""
        key = self.pos_preset_combo.currentData()
        if not key:
            return
        parent = self.parent()
        if parent is not None and hasattr(parent, "screen") and hasattr(parent, "width"):
            parent.adjustSize()
            width, height = parent.width(), parent.height()
        else:
            width, height = 240, 120
        x, y = preset_point(key, width, height, self._target_area())
        self._syncing_preset = True
        try:
            self.pos_x_spin.setValue(x)
            self.pos_y_spin.setValue(y)
        finally:
            self._syncing_preset = False

    def apply(self):
        """把面板当前值写回 cfg 并返回。"""
        self.cfg["window_behavior"] = self.behavior_combo.currentData()
        self.cfg["font_family"] = self.font_combo.currentData() or ""
        self.cfg["font_size"] = self.size_spin.value()
        self.cfg["show_date"] = self.date_check.isChecked()
        self.cfg["show_seconds"] = self.seconds_check.isChecked()
        self.cfg["hour24"] = self.h24_check.isChecked()
        self.cfg["pos_locked"] = self.lock_check.isChecked()
        self.cfg["autostart"] = self.autostart_check.isChecked()
        self.cfg["opacity"] = self.opacity_slider.value() / 100
        self.cfg["pos_x"] = self.pos_x_spin.value()
        self.cfg["pos_y"] = self.pos_y_spin.value()
        self.cfg["pos_preset"] = self.pos_preset_combo.currentData() or ""
        if not self._loaded_file_family:
            self.cfg["font_file"] = ""
        return self.cfg


class ClockWindow(QWidget):
    """无边框时钟窗口：三种显示方式、拖动锁、右键菜单、可选托盘。"""

    def __init__(self, cfg, enable_tray=True):
        super().__init__()
        self.cfg = cfg
        self._drag_offset = None
        self._drag_start = None
        self._quitting = False
        self._moving_self = False   # 程序自己的 move() 置位，区分系统挪动
        self._fit_trigger = "init"  # 最近一次排定核对的触发源（写日志用）
        self._fit_chain = 0         # 连续重摆轮数（自校验封顶防互搏）
        self._placed = False        # 构造完成前忽略 move/resize/show 事件
        # 屏幕几何变化防抖：改分辨率/插拔显示器会连发信号，合并成一次核对
        self._screen_fit_timer = QTimer(self)
        self._screen_fit_timer.setSingleShot(True)
        self._screen_fit_timer.setInterval(SCREEN_FIT_DEBOUNCE_MS)
        self._screen_fit_timer.timeout.connect(self._check_screen_fit)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, cfg["window_behavior"] == "desktop")

        self.time_label = QLabel()
        self.date_label = QLabel()
        for label in (self.time_label, self.date_label):
            label.setAlignment(Qt.AlignCenter)
            label.setAttribute(Qt.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(self.time_label)
        layout.addWidget(self.date_label)

        self.tray = self._setup_tray() if enable_tray else None
        self._apply_settings()
        self._place_window()
        self._setup_screen_watch()
        # 启动核对一次：设置可能保存在另一块屏或另一分辨率下（换屏后重启也纠偏）；
        # 之后 show 引起的换屏由 ScreenChangeInternal + 屏幕信号防抖接管
        self._check_screen_fit()
        self._tick()
        self._placed = True
        fit_log(f"start behavior={cfg['window_behavior']} {screens_summary()}")

    # ---- 显示方式 / 设置应用 ----

    def _drag_allowed(self):
        return not (self.cfg["pos_locked"] or self.cfg["window_behavior"] == "desktop")

    def _apply_settings(self):
        flags = MODE_FLAGS[self.cfg["window_behavior"]]
        if self.windowFlags() != flags:
            pos = self.pos()
            visible = self.isVisible()
            self.setWindowFlags(flags)
            if visible:
                self.show()
                self.move(pos)
        self.setWindowOpacity(self.cfg["opacity"])

        self.time_label.setFont(resolve_font(self.cfg))
        date_font = QFont(resolve_font(self.cfg))
        date_font.setPointSize(max(12, self.cfg["font_size"] // 3))
        self.date_label.setFont(date_font)

        color = self.cfg["color"]
        self.time_label.setStyleSheet(f"color: {color};")
        dim = QColor(color)
        dim.setAlpha(180)
        self.date_label.setStyleSheet(f"color: {dim.name(QColor.HexArgb)};")

        self.date_label.setVisible(self.cfg["show_date"])
        self._update_text()
        self._refresh_tray_menu()

    def _set_behavior(self, mode):
        if mode == self.cfg["window_behavior"]:
            return
        self.cfg["window_behavior"] = mode
        settings_mod.save_settings(self.cfg)
        pos = self.pos()
        was_visible = self.isVisible()
        self._apply_settings()
        if was_visible:
            self.show()
            self.move(pos)
        self.adjustSize()

    def _apply_preset(self, key):
        """把时钟挪到预设屏幕位置并立即保存（主动摆放，与锁定/桌面模式无关）。"""
        self.adjustSize()
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x, y = preset_point(key, self.width(), self.height(), area)
        self.cfg["pos_x"], self.cfg["pos_y"] = x, y
        self.cfg["pos_preset"] = key
        self.cfg["pos_anchor"] = anchor_of(area)
        self.move(x, y)
        settings_mod.save_settings(self.cfg)

    # ---- 显示器尺寸/插拔变化侦测与自动纠偏 ----

    def _setup_screen_watch(self):
        """监听屏幕插拔与几何变化。

        连接只发生两处且各一次：启动时遍历 app.screens()、之后 screenAdded
        的新对象，天然无重复连接；连接随屏幕对象销毁自动断开。
        """
        app = QApplication.instance()
        if app is None:
            return
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._schedule_screen_fit)
        app.primaryScreenChanged.connect(self._schedule_screen_fit)
        for screen in app.screens():
            self._watch_screen(screen)

    def _on_screen_added(self, screen):
        self._watch_screen(screen)
        self._schedule_screen_fit(f"screen-added:{screen.name()}")

    def _watch_screen(self, screen):
        screen.geometryChanged.connect(self._schedule_screen_fit)
        screen.availableGeometryChanged.connect(self._schedule_screen_fit)

    def _schedule_screen_fit(self, *args):
        """防抖入口：信号可能连发（缩放调整/分辨率切换），300ms 静默后只核对一次。

        触发源记进 _fit_trigger（信号载荷按类型名记，主动调用直接传标签字符串）。
        """
        if args and isinstance(args[0], str):
            trigger = args[0]
        elif args:
            trigger = type(args[0]).__name__
        else:
            trigger = "direct"
        self._fit_trigger = trigger
        if trigger != "resize":  # 文本刷新可能高频触发布局 resize，避免日志刷屏
            fit_log(f"schedule trig={trigger}")
        timer = getattr(self, "_screen_fit_timer", None)
        if timer is not None:
            timer.start()

    def _target_screen(self):
        """窗口中心所在的屏幕；不在任何屏内时取最近的屏幕，兜底主屏。"""
        center = QPoint(self.x() + self.width() // 2, self.y() + self.height() // 2)
        best, best_dist = None, None
        for screen in QApplication.screens():
            geo = screen.geometry()
            if geo.contains(center):
                return screen
            dx = max(geo.x() - center.x(), 0, center.x() - geo.x() - geo.width() + 1)
            dy = max(geo.y() - center.y(), 0, center.y() - geo.y() - geo.height() + 1)
            dist = dx * dx + dy * dy
            if best_dist is None or dist < best_dist:
                best, best_dist = screen, dist
        return best or QApplication.primaryScreen()

    def _check_screen_fit(self):
        """核对时钟是否仍在「该在的地方」，不对就重摆回预设锚点。

        三层判定（只信锚点对比会漏判：两块屏可用区相同时锚点发现不了变化，
        而换屏瞬间系统挪窗/跨屏 DPI 变尺寸已让实际位置偏离预设）：
          1. 拖动中不介入（落点由 _commit_drag 定夺）；
          2. 有预设 → 按当前屏+当前尺寸重算应处坐标，与实际逐像素比对；
          3. 无预设（自定义）→ 锚点变了或已跑出屏外，才按旧锚点反推就近预设。
        重摆后 300ms 再自校验（最多 FIT_VERIFY_ROUNDS 轮），等系统落定后二次修正。
        """
        if self._drag_offset is not None:
            self._schedule_screen_fit("dragging")
            return
        screen = self._target_screen()
        if screen is None:
            fit_log(f"check trig={self._fit_trigger} no-screen")
            return
        area = screen.availableGeometry()
        self.adjustSize()
        x, y, w, h = self.x(), self.y(), self.width(), self.height()
        old_area = area_from_anchor(self.cfg.get("pos_anchor"))
        preset = self.cfg.get("pos_preset") or ""
        inside = area_contains_window(area, x, y, w, h)
        state = (
            f"trig={self._fit_trigger} screens={screens_summary()}"
            f" target={area.x()},{area.y()},{area.width()}x{area.height()}"
            f" anchor={'None' if old_area is None else f'{old_area.x()},{old_area.y()},{old_area.width()}x{old_area.height()}'}"
            f" pos=({x},{y}) size={w}x{h} preset={preset or '-'}")

        if preset:
            nx, ny = preset_point(preset, w, h, area)
            if inside and (x, y) == (nx, ny):
                if old_area != area:  # 位置没错但记录的锚点过期 → 只补记不搬动
                    self.cfg["pos_anchor"] = anchor_of(area)
                    settings_mod.save_settings(self.cfg)
                    self._log_stayed(state + " anchor-updated")
                else:
                    self._log_stayed(state)
                self._fit_chain = 0
                return
            new_preset = preset
        else:
            if inside and old_area in (None, area):
                self._log_stayed(state)
                self._fit_chain = 0
                return
            # 自定义位置：拿旧可用区反推原意最贴近的预设；锚点缺失时按当前区兜底
            new_preset = nearest_preset(w, h, x, y, old_area or area)
            nx, ny = preset_point(new_preset, w, h, area)

        self.move(nx, ny)
        self.cfg["pos_x"], self.cfg["pos_y"] = nx, ny
        self.cfg["pos_preset"] = new_preset
        self.cfg["pos_anchor"] = anchor_of(area)
        settings_mod.save_settings(self.cfg)
        self._fit_chain += 1
        fit_log(f"check {state} -> MOVED ({x},{y})->({nx},{ny})"
                f" preset={new_preset} chain={self._fit_chain}")
        if self._fit_chain <= FIT_VERIFY_ROUNDS:
            self._schedule_screen_fit("verify")

    def _log_stayed(self, state):
        """停留判定也入日志，但 5 秒内只记一次防刷屏（文本刷新会高频核对）。"""
        now = time.monotonic()
        if now - _FIT_STATE["last_stay_log"] < 5:
            return
        _FIT_STATE["last_stay_log"] = now
        fit_log(f"check {state} -> stayed")

    def _commit_drag(self):
        """拖动落点即新的自定义位置：脱离预设、认领所在屏锚点并立即保存。"""
        self.cfg["pos_x"], self.cfg["pos_y"] = self.x(), self.y()
        self.cfg["pos_preset"] = ""
        screen = self._target_screen()
        if screen is not None:
            self.cfg["pos_anchor"] = anchor_of(screen.availableGeometry())
        settings_mod.save_settings(self.cfg)

    def _toggle_lock(self):
        self.cfg["pos_locked"] = not self.cfg["pos_locked"]
        settings_mod.save_settings(self.cfg)
        self._refresh_tray_menu()

    def _toggle_autostart(self):
        desired = not self.cfg["autostart"]
        self.cfg["autostart"] = autostart.sync(desired)
        settings_mod.save_settings(self.cfg)
        self._refresh_tray_menu()

    def _update_text(self):
        now = QTime.currentTime()
        self.time_label.setText(format_time(
            now.hour(), now.minute(), now.second(),
            show_seconds=self.cfg["show_seconds"],
            hour24=self.cfg["hour24"]))
        date = QDate.currentDate()
        self.date_label.setText(format_date(date.year(), date.month(), date.day()))

    def _place_window(self):
        self.adjustSize()
        if self.cfg["pos_x"] is not None and self.cfg["pos_y"] is not None:
            # 沿用已存坐标与它的原锚点，是否换屏交给 _check_screen_fit 判定
            self.move(self.cfg["pos_x"], self.cfg["pos_y"])
            return
        area = (self._target_screen() or QApplication.primaryScreen()).availableGeometry()
        x = area.x() + (area.width() - self.width()) // 2
        y = area.y() + (area.height() - self.height()) // 4
        self.move(x, y)
        self.cfg["pos_x"], self.cfg["pos_y"] = x, y
        self.cfg["pos_anchor"] = anchor_of(area)

    # ---- 每秒刷新（对齐整秒）----

    def _tick(self):
        self._update_text()
        msec_to_next = 1000 - QTime.currentTime().msec() + 5
        QTimer.singleShot(msec_to_next, self._tick)

    # ---- 鼠标拖动（desktop 模式或锁定位置时禁用）----

    def move(self, *args):
        """程序自己挪窗：置位标记，让 moveEvent 能区分系统挪动。"""
        self._moving_self = True
        try:
            super().move(*args)
        finally:
            self._moving_self = False

    def moveEvent(self, event):
        # 系统/窗口管理器把窗口挪走（换屏重排、跨屏 DPI 调整都会这样）：
        # 自定义位置直接退回已保存意图；两种位置都防抖核对一次兜底
        if (self._placed and not self._moving_self and not self._quitting):
            old, new = event.oldPos(), event.pos()
            fit_log(f"external-move ({old.x()},{old.y()})->({new.x()},{new.y()})")
            cfg = self.cfg
            if (not (cfg.get("pos_preset") or "")
                    and cfg.get("pos_x") is not None
                    and (self.x(), self.y()) != (cfg["pos_x"], cfg["pos_y"])):
                # 自定义位置没有可重算的锚点：退回上次保存/提交的意图位置
                fit_log(f"restore custom -> ({cfg['pos_x']},{cfg['pos_y']})")
                self.move(cfg["pos_x"], cfg["pos_y"])
            self._schedule_screen_fit("external-move")
        super().moveEvent(event)

    def resizeEvent(self, event):
        # 字号/DPI 变化会让预设坐标失准（靠下/靠右锚点依赖宽高）
        if self._placed and not self._quitting:
            self._schedule_screen_fit("resize")
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # 显示/唤回时窗口管理器可能微调位置，落定后再核对一次
        if self._placed and not self._quitting:
            self._schedule_screen_fit("show")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_allowed():
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._drag_start = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        moved = (self._drag_offset is not None
                 and self._drag_start is not None
                 and self.pos() != self._drag_start)
        self._drag_offset = None
        self._drag_start = None
        if moved:
            self._commit_drag()
        super().mouseReleaseEvent(event)

    def event(self, ev):
        if ev.type() == QEvent.ScreenChangeInternal:
            # 窗口跨屏（含被系统挪到新主屏上）也纳入核对
            self._schedule_screen_fit("screen-change-event")
        # 双保险：desktop 模式万一被点击激活，立刻压回窗口栈底部
        if (ev.type() == QEvent.WindowActivate
                and self.cfg["window_behavior"] == "desktop"):
            QTimer.singleShot(0, self.lower)
        return super().event(ev)

    # ---- 菜单（窗口右键与托盘共用一份结构）----

    def _build_menu(self):
        """按当前配置构建菜单（QMenu 无 parent：QSystemTrayIcon 不是 QWidget）。"""
        menu = QMenu()
        mode_menu = menu.addMenu("显示方式")
        for mode in WINDOW_BEHAVIORS:
            act = mode_menu.addAction(BEHAVIOR_LABELS[mode])
            act.setCheckable(True)
            act.setChecked(self.cfg["window_behavior"] == mode)
            act.triggered.connect(lambda checked=False, m=mode: self._set_behavior(m))
        pos_menu = menu.addMenu("屏幕位置")
        for key in POSITION_PRESETS:
            act = pos_menu.addAction(POSITION_LABELS[key])
            act.triggered.connect(lambda checked=False, k=key: self._apply_preset(k))
        menu.addSeparator()
        lock_action = menu.addAction("锁定位置")
        lock_action.setCheckable(True)
        lock_action.setChecked(self.cfg["pos_locked"])
        lock_action.triggered.connect(self._toggle_lock)
        if autostart.is_supported():
            autostart_action = menu.addAction("开机自启动")
            autostart_action.setCheckable(True)
            autostart_action.setChecked(self.cfg["autostart"])
            autostart_action.triggered.connect(self._toggle_autostart)
        menu.addSeparator()
        show_action = menu.addAction("隐藏时钟" if self.isVisible() else "显示时钟")
        show_action.triggered.connect(self._toggle_visibility)
        menu.addAction("设置…", self.open_settings)
        menu.addSeparator()
        menu.addAction("退出", self._quit)
        return menu

    def contextMenuEvent(self, event):
        menu = self._build_menu()
        menu.exec(event.globalPos())

    # ---- 系统托盘 ----

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(app_icon(), self)
        tray.setToolTip(MSG_TITLE)
        self._refresh_tray_menu()
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        return tray

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._toggle_visibility()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
        self._refresh_tray_menu()

    def _refresh_tray_menu(self):
        """配置或可见性变化后重建托盘菜单，勾选状态保持新鲜。

        setContextMenu 不转移所有权，菜单须由 self._tray_menu 持有防回收。
        getattr 兼容构造期调用（self.tray 尚未赋值）。
        """
        tray = getattr(self, "tray", None)
        if tray is not None:
            self._tray_menu = self._build_menu()
            tray.setContextMenu(self._tray_menu)

    # ---- 设置与退出 ----

    def open_settings(self):
        dialog = SettingsDialog(self.cfg, self)
        result = dialog.exec()
        if result != QDialog.Accepted:
            return
        self.cfg = settings_mod.merged_settings(dialog.apply())
        autostart.sync(self.cfg["autostart"])
        pos = self.pos()
        was_visible = self.isVisible()
        self._apply_settings()
        if was_visible:
            self.show()
        if self.cfg.get("pos_x") is not None and self.cfg.get("pos_y") is not None:
            self.move(self.cfg["pos_x"], self.cfg["pos_y"])
        else:
            self.move(pos)
        self.adjustSize()
        # 坐标来自面板（预设或手输），按落点所在屏重新认领锚点；
        # 落在所有屏之外则保留旧锚点，留给下一次屏幕核对纠正
        screen = self._target_screen()
        if screen is not None and area_contains_window(
                screen.availableGeometry(), self.x(), self.y(), self.width(), self.height()):
            self.cfg["pos_anchor"] = anchor_of(screen.availableGeometry())
        settings_mod.save_settings(self.cfg)

    def _quit(self):
        self._quitting = True
        self._save_position()
        QApplication.quit()

    def _save_position(self):
        self.cfg["pos_x"] = self.x()
        self.cfg["pos_y"] = self.y()
        # 窗口仍在这块可用区内才认领它的锚点；已跑偏则保留旧锚点，
        # 让下次启动/屏幕变化时的 _check_screen_fit 还能纠正
        screen = self._target_screen()
        if screen is not None and area_contains_window(
                screen.availableGeometry(), self.x(), self.y(), self.width(), self.height()):
            self.cfg["pos_anchor"] = anchor_of(screen.availableGeometry())
        settings_mod.save_settings(self.cfg)

    def closeEvent(self, event):
        # 有托盘时点关闭 = 隐藏到托盘；托盘不可用或主动退出才真关
        self._save_position()
        if self.tray is not None and not self._quitting:
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)


def run_selftest():
    """三种显示方式各建窗渲染一帧；报告图标资源状态；退出码 0。"""
    app = QApplication.instance() or QApplication(sys.argv)
    icon_ok = asset_path("icon.ico").is_file()
    for mode in WINDOW_BEHAVIORS:
        cfg = settings_mod.merged_settings({"window_behavior": mode})
        window = ClockWindow(cfg, enable_tray=False)
        window.show()
        app.processEvents()
        pixmap = window.grab()
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            print(f"SELFTEST_FAIL_{mode}: rendered empty frame")
            return 1
        print(f"SELFTEST_OK_{mode} {pixmap.width()} {pixmap.height()}")
        window.hide()
    print("ICON_OK" if icon_ok else "ICON_MISSING")
    return 0


def main():
    if "--selftest" in sys.argv:
        return run_selftest()
    app = QApplication(sys.argv)
    app.setApplicationName("desktop-clock")
    app.setOrganizationName("desktop-clock")
    app.setWindowIcon(app_icon())
    has_tray = QSystemTrayIcon.isSystemTrayAvailable()
    # 托盘在位时：隐藏时钟不等于退出程序（从托盘唤回或退出）
    app.setQuitOnLastWindowClosed(not has_tray)
    cfg = settings_mod.load_settings()
    if cfg["autostart"]:
        # 每次启动校正自启动命令行（python/脚本路径变化后自动纠正）
        cfg["autostart"] = autostart.sync(True)
    window = ClockWindow(cfg, enable_tray=has_tray)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

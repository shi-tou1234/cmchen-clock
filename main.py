"""桌面时钟主程序。

用法：
    python main.py            # 运行时钟
    python main.py --selftest # 自检：三种显示方式各建窗渲染一帧后退出

显示方式（window_behavior）：
    floating  浮在其他窗口上方（任务栏可见）
    normal    普通窗口（任务栏可见）
    desktop   固定在桌面：压在其他窗口下方、锁定拖动、不进任务栏（默认）

桌面模式或勾选「锁定位置」时禁止拖动；系统托盘常驻（显示/隐藏、
显示方式、锁定位置、设置、退出）。设置持久化到
~/.desktop-clock/settings.json（见 settings.py 的安全设计）。
"""

import sys
from pathlib import Path

from PySide6.QtCore import QDate, QEvent, QTime, Qt, QTimer
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

import fonts
import settings as settings_mod
from clock_core import format_date, format_time
from settings import BEHAVIOR_LABELS, WINDOW_BEHAVIORS

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


class SettingsDialog(QDialog):
    """设置面板：显示方式、锁定位置、字体、字号、颜色、开关、透明度＋实时预览。"""

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

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(round(self.cfg["opacity"] * 100))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%"))

        self.form = QFormLayout()
        self.form.addRow("显示方式", self.behavior_combo)
        self.form.addRow("", self.lock_check)
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

    def apply(self):
        """把面板当前值写回 cfg 并返回。"""
        self.cfg["window_behavior"] = self.behavior_combo.currentData()
        self.cfg["font_family"] = self.font_combo.currentData() or ""
        self.cfg["font_size"] = self.size_spin.value()
        self.cfg["show_date"] = self.date_check.isChecked()
        self.cfg["show_seconds"] = self.seconds_check.isChecked()
        self.cfg["hour24"] = self.h24_check.isChecked()
        self.cfg["pos_locked"] = self.lock_check.isChecked()
        self.cfg["opacity"] = self.opacity_slider.value() / 100
        if not self._loaded_file_family:
            self.cfg["font_file"] = ""
        return self.cfg


class ClockWindow(QWidget):
    """无边框时钟窗口：三种显示方式、拖动锁、右键菜单、可选托盘。"""

    def __init__(self, cfg, enable_tray=True):
        super().__init__()
        self.cfg = cfg
        self._drag_offset = None
        self._quitting = False
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
        self._tick()

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

    def _toggle_lock(self):
        self.cfg["pos_locked"] = not self.cfg["pos_locked"]
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
            self.move(self.cfg["pos_x"], self.cfg["pos_y"])
            return
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(
            area.x() + (area.width() - self.width()) // 2,
            area.y() + (area.height() - self.height()) // 4)

    # ---- 每秒刷新（对齐整秒）----

    def _tick(self):
        self._update_text()
        msec_to_next = 1000 - QTime.currentTime().msec() + 5
        QTimer.singleShot(msec_to_next, self._tick)

    # ---- 鼠标拖动（desktop 模式或锁定位置时禁用）----

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_allowed():
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def event(self, ev):
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
        menu.addSeparator()
        lock_action = menu.addAction("锁定位置")
        lock_action.setCheckable(True)
        lock_action.setChecked(self.cfg["pos_locked"])
        lock_action.triggered.connect(self._toggle_lock)
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
        settings_mod.save_settings(self.cfg)
        pos = self.pos()
        was_visible = self.isVisible()
        self._apply_settings()
        if was_visible:
            self.show()
            self.move(pos)
        self.adjustSize()

    def _quit(self):
        self._quitting = True
        self._save_position()
        QApplication.quit()

    def _save_position(self):
        self.cfg["pos_x"] = self.x()
        self.cfg["pos_y"] = self.y()
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
    window = ClockWindow(settings_mod.load_settings(), enable_tray=has_tray)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

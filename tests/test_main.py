from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent

import settings as settings_mod
from main import (
    POSITION_LABELS,
    POSITION_PRESETS,
    SCREEN_FIT_DEBOUNCE_MS,
    ClockWindow,
    MODE_FLAGS,
    SettingsDialog,
    anchor_of,
    area_contains_window,
    area_from_anchor,
    nearest_preset,
    preset_point,
)
from settings import merged_settings


def make_window(mode, **overrides):
    cfg = merged_settings({"window_behavior": mode, **overrides})
    return ClockWindow(cfg, enable_tray=False)


class FakeScreen:
    """测试用屏幕：只提供几何，不接 Qt 真实屏幕。"""

    def __init__(self, rect):
        self._rect = rect

    def geometry(self):
        return self._rect

    def availableGeometry(self):
        return self._rect


def prepare_fit(window, rect, monkeypatch):
    """固定窗口尺寸并把目标屏换成 FakeScreen(rect)，返回 (width, height)。"""
    monkeypatch.setattr(window, "adjustSize", lambda: None)
    monkeypatch.setattr(window, "_target_screen", lambda: FakeScreen(rect))
    return window.width(), window.height()


def press_event(local, global_):
    return QMouseEvent(QEvent.MouseButtonPress, QPointF(*local), QPointF(*global_),
                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)


def move_event(local, global_):
    return QMouseEvent(QEvent.MouseMove, QPointF(*local), QPointF(*global_),
                       Qt.NoButton, Qt.LeftButton, Qt.NoModifier)


def release_event(local, global_):
    return QMouseEvent(QEvent.MouseButtonRelease, QPointF(*local), QPointF(*global_),
                       Qt.LeftButton, Qt.NoButton, Qt.NoModifier)


class TestWindowBehaviorFlags:
    def test_desktop_mode_flags(self, qapp):
        window = make_window("desktop")
        flags = window.windowFlags()
        assert flags & Qt.WindowStaysOnBottomHint
        assert flags & Qt.Tool          # 不进任务栏
        assert not (flags & Qt.WindowStaysOnTopHint)

    def test_floating_mode_flags(self, qapp):
        window = make_window("floating")
        flags = window.windowFlags()
        assert flags & Qt.WindowStaysOnTopHint
        assert flags & Qt.Window        # 任务栏条目（真软件感）
        assert not (flags & Qt.WindowStaysOnBottomHint)

    def test_normal_mode_flags(self, qapp):
        window = make_window("normal")
        flags = window.windowFlags()
        assert flags & Qt.Window
        assert not (flags & Qt.WindowStaysOnTopHint)
        assert not (flags & Qt.WindowStaysOnBottomHint)

    def test_all_modes_have_frameless(self, qapp):
        for mode in MODE_FLAGS:
            assert make_window(mode).windowFlags() & Qt.FramelessWindowHint


class TestDragLock:
    def test_desktop_mode_locks_drag_even_without_pos_lock(self, qapp):
        assert not make_window("desktop", pos_locked=False)._drag_allowed()

    def test_pos_locked_locks_drag_in_normal_mode(self, qapp):
        assert not make_window("normal", pos_locked=True)._drag_allowed()

    def test_normal_unlocked_allows_drag(self, qapp):
        assert make_window("normal", pos_locked=False)._drag_allowed()

    def test_floating_unlocked_allows_drag(self, qapp):
        assert make_window("floating", pos_locked=False)._drag_allowed()


class TestSettingsDialogPreview:
    def test_preview_exists_with_dark_backdrop(self, qapp):
        dialog = SettingsDialog(merged_settings({}))
        assert dialog.preview.minimumHeight() >= 96
        assert "rgba(30, 32, 48" in dialog.preview.styleSheet()

    def test_preview_font_follows_size_change(self, qapp):
        dialog = SettingsDialog(merged_settings({"font_size": 64}))
        dialog.size_spin.setValue(100)
        assert dialog.preview.font().pointSize() == 100

    def test_preview_style_follows_color_change(self, qapp):
        dialog = SettingsDialog(merged_settings({"color": "#FFFFFF"}))
        dialog.cfg["color"] = "#FF8800"
        dialog._refresh_preview()
        assert "color: #FF8800" in dialog.preview.styleSheet()

    def test_preview_text_has_time_and_date_lines(self, qapp):
        import re

        dialog = SettingsDialog(merged_settings({"show_date": True, "show_seconds": True}))
        lines = dialog.preview.text().split("\n")
        assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", lines[0])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", lines[1])

    def test_preview_hides_date_line_when_disabled(self, qapp):
        dialog = SettingsDialog(merged_settings({"show_date": False}))
        assert "\n" not in dialog.preview.text()

    def test_apply_collects_behavior_and_lock(self, qapp):
        dialog = SettingsDialog(merged_settings({"window_behavior": "desktop"}))
        dialog.behavior_combo.setCurrentIndex(0)  # floating
        dialog.lock_check.setChecked(True)
        cfg = dialog.apply()
        assert cfg["window_behavior"] == "floating"
        assert cfg["pos_locked"] is True

    def test_apply_collects_position_spins(self, qapp):
        dialog = SettingsDialog(merged_settings({"pos_x": 100, "pos_y": 200}))
        assert (dialog.pos_x_spin.value(), dialog.pos_y_spin.value()) == (100, 200)
        dialog.pos_x_spin.setValue(30)
        dialog.pos_y_spin.setValue(40)
        cfg = dialog.apply()
        assert cfg["pos_x"] == 30
        assert cfg["pos_y"] == 40

    def test_position_combo_lists_custom_plus_nine_presets(self, qapp):
        dialog = SettingsDialog(merged_settings({}))
        assert dialog.pos_preset_combo.count() == 10
        assert dialog.pos_preset_combo.itemData(0) == ""  # 自定义
        for i, key in enumerate(POSITION_PRESETS, start=1):
            assert dialog.pos_preset_combo.itemData(i) == key

    def test_position_combo_fills_spins_from_preset(self, qapp, monkeypatch):
        dialog = SettingsDialog(merged_settings({}))

        class FakeWindow:
            def width(self):
                return 200

            def height(self):
                return 100

            def screen(self):
                return None

            def adjustSize(self):
                pass

        monkeypatch.setattr(dialog, "parent", lambda: FakeWindow())
        monkeypatch.setattr(dialog, "_target_area", lambda: QRect(0, 0, 1920, 1080))
        dialog.pos_preset_combo.setCurrentIndex(5)  # middle-center
        assert (dialog.pos_x_spin.value(), dialog.pos_y_spin.value()) == (860, 490)


class TestScreenPresets:
    AREA = QRect(0, 0, 1920, 1080)

    def test_preset_point_covers_nine_grid_positions(self):
        # 边距 24；期望坐标=(1920-200-24, ...)=(1696, ...)、(1080-100-24)=956、居中=(860,490)
        assert preset_point("top-left", 200, 100, self.AREA) == (24, 24)
        assert preset_point("top-center", 200, 100, self.AREA) == (860, 24)
        assert preset_point("top-right", 200, 100, self.AREA) == (1696, 24)
        assert preset_point("middle-left", 200, 100, self.AREA) == (24, 490)
        assert preset_point("middle-center", 200, 100, self.AREA) == (860, 490)
        assert preset_point("middle-right", 200, 100, self.AREA) == (1696, 490)
        assert preset_point("bottom-left", 200, 100, self.AREA) == (24, 956)
        assert preset_point("bottom-center", 200, 100, self.AREA) == (860, 956)
        assert preset_point("bottom-right", 200, 100, self.AREA) == (1696, 956)

    def test_presets_cover_nine_grid_positions_with_labels(self):
        assert len(POSITION_PRESETS) == 9
        assert len(POSITION_LABELS) == 9
        for key in POSITION_PRESETS:
            assert key in POSITION_LABELS

    def test_preset_point_on_secondary_screen_negative_origin(self):
        area = QRect(1920, 0, 1280, 1024)  # 副屏（主屏右侧）
        assert preset_point("top-left", 200, 100, area) == (1920 + 24, 24)
        assert preset_point("bottom-right", 200, 100, area) == (1920 + 1280 - 200 - 24, 1024 - 100 - 24)

    def test_apply_preset_moves_window_and_persists(self, qapp, monkeypatch):
        window = make_window("normal")
        saved = {}
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: saved.update(cfg))

        class FakeScreen:
            def availableGeometry(self):
                return QRect(0, 0, 1920, 1080)

        monkeypatch.setattr(window, "screen", lambda: FakeScreen())
        monkeypatch.setattr(window, "adjustSize", lambda: None)  # 固定窗口尺寸
        # 布局最小尺寸会把 resize 顶回去，按实际尺寸计算期望位置
        expected = preset_point("bottom-center", window.width(), window.height(), QRect(0, 0, 1920, 1080))
        window._apply_preset("bottom-center")
        assert (window.x(), window.y()) == expected
        assert window.cfg["pos_x"] == expected[0]
        assert window.cfg["pos_y"] == expected[1]
        assert saved["pos_x"] == expected[0]
        assert saved["pos_y"] == expected[1]

    def test_apply_preset_records_preset_and_anchor(self, qapp, monkeypatch):
        window = make_window("normal")
        area = QRect(0, 0, 1920, 1080)
        monkeypatch.setattr(window, "screen", lambda: FakeScreen(area))
        monkeypatch.setattr(window, "adjustSize", lambda: None)
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: None)
        window._apply_preset("top-right")
        assert window.cfg["pos_preset"] == "top-right"
        assert window.cfg["pos_anchor"] == anchor_of(area)


class TestAnchorHelpers:
    def test_anchor_roundtrip_and_bad_input(self):
        area = QRect(-2560, 50, 2560, 1440)  # 副屏（主屏左侧）
        assert area_from_anchor(anchor_of(area)) == area
        assert area_from_anchor(None) is None
        assert area_from_anchor({"x": 0, "y": 0, "w": 1920}) is None  # 缺 h

    def test_area_contains_window_uses_center(self):
        area = QRect(0, 0, 1920, 1080)
        assert area_contains_window(area, 100, 100, 200, 100)
        # 右缘悬出 80px 但中心（1900）仍在屏内，不算跑偏
        assert area_contains_window(area, 1800, 100, 200, 100)
        # 整窗在屏外
        assert not area_contains_window(area, 2000, 100, 200, 100)

    def test_nearest_preset_exact_match_for_all_nine(self):
        area = QRect(0, 0, 1920, 1080)
        for key in POSITION_PRESETS:
            x, y = preset_point(key, 200, 100, area)
            assert nearest_preset(200, 100, x, y, area) == key

    def test_nearest_preset_offscreen_lower_right(self):
        area = QRect(0, 0, 1920, 1080)
        assert nearest_preset(200, 100, 5000, 5000, area) == "bottom-right"
        assert nearest_preset(200, 100, -9999, -9999, area) == "top-left"


class TestScreenFit:
    """显示器尺寸变化 → 自动切回合适预设位置。"""

    def test_keeps_position_when_anchor_and_screen_match(self, qapp, monkeypatch):
        window = make_window("normal")
        area = QRect(0, 0, 1920, 1080)
        prepare_fit(window, area, monkeypatch)
        window.cfg["pos_anchor"] = anchor_of(area)
        window.cfg["pos_x"], window.cfg["pos_y"] = 300, 200
        window.move(300, 200)
        saved = {}
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: saved.update(cfg))

        window._check_screen_fit()
        assert (window.x(), window.y()) == (300, 200)
        assert not saved  # 没变化就不动、不写盘

    def test_reapplies_preset_when_screen_size_changes(self, qapp, monkeypatch):
        window = make_window("normal")
        old, new = QRect(0, 0, 2560, 1440), QRect(0, 0, 1920, 1080)
        w, h = prepare_fit(window, new, monkeypatch)
        window.cfg["pos_preset"] = "bottom-right"
        window.cfg["pos_anchor"] = anchor_of(old)
        window.move(*preset_point("bottom-right", w, h, old))
        saved = {}
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: saved.update(cfg))

        window._check_screen_fit()
        expected = preset_point("bottom-right", w, h, new)
        assert (window.x(), window.y()) == expected
        assert (window.cfg["pos_x"], window.cfg["pos_y"]) == expected
        assert window.cfg["pos_preset"] == "bottom-right"
        assert window.cfg["pos_anchor"] == anchor_of(new)
        assert saved["pos_anchor"] == anchor_of(new)

    def test_custom_position_infers_nearest_preset(self, qapp, monkeypatch):
        # 自定义（无预设）位置：按旧可用区反推原意，换屏后落回同款预设
        window = make_window("normal")
        old, new = QRect(0, 0, 2560, 1440), QRect(0, 0, 1920, 1080)
        w, h = prepare_fit(window, new, monkeypatch)
        window.cfg["pos_preset"] = ""
        window.cfg["pos_anchor"] = anchor_of(old)
        window.move(*preset_point("middle-right", w, h, old))
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: None)

        window._check_screen_fit()
        assert (window.x(), window.y()) == preset_point("middle-right", w, h, new)
        assert window.cfg["pos_preset"] == "middle-right"

    def test_legacy_without_anchor_inside_left_untouched(self, qapp, monkeypatch):
        # 升级前的设置没有锚点：窗口还在屏内就没有纠偏依据，保持原位
        window = make_window("normal")
        area = QRect(0, 0, 1920, 1080)
        prepare_fit(window, area, monkeypatch)
        window.cfg["pos_anchor"] = None
        window.cfg["pos_x"], window.cfg["pos_y"] = 300, 200
        window.move(300, 200)
        saved = {}
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: saved.update(cfg))

        window._check_screen_fit()
        assert (window.x(), window.y()) == (300, 200)
        assert not saved

    def test_legacy_without_anchor_outside_snaps_to_nearest(self, qapp, monkeypatch):
        # 没锚点但坐标已跑到屏外（换小屏后）：就近吸附到边缘预设
        window = make_window("normal")
        area = QRect(0, 0, 1920, 1080)
        w, h = prepare_fit(window, area, monkeypatch)
        window.cfg["pos_anchor"] = None
        window.move(3000, 100)
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: None)

        window._check_screen_fit()
        assert window.cfg["pos_preset"] == "top-right"
        assert (window.x(), window.y()) == preset_point("top-right", w, h, area)

    def test_startup_snaps_saved_position_from_other_screen(self, qapp, monkeypatch):
        # 换屏后重启：构造时就按新屏可用区把旧坐标纠回预设
        new = QRect(0, 0, 1920, 1080)
        monkeypatch.setattr(ClockWindow, "_target_screen", lambda self: FakeScreen(new))
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: None)
        cfg = merged_settings({
            "pos_x": 3000, "pos_y": 100,
            "pos_anchor": {"x": 1920, "y": 0, "w": 2560, "h": 1440},
        })
        window = ClockWindow(cfg, enable_tray=False)
        w, h = window.width(), window.height()
        assert (window.x(), window.y()) == preset_point("top-center", w, h, new)
        assert window.cfg["pos_anchor"] == anchor_of(new)

    def test_screen_geometry_signal_starts_debounce(self, qapp):
        window = make_window("normal")
        assert not window._screen_fit_timer.isActive()
        screen = qapp.screens()[0]
        screen.geometryChanged.emit(screen.geometry())  # 模拟分辨率变化信号
        assert window._screen_fit_timer.isActive()
        assert window._screen_fit_timer.interval() == SCREEN_FIT_DEBOUNCE_MS


class TestDragCommit:
    def test_move_then_release_commits_custom_position(self, qapp, monkeypatch):
        window = make_window("normal")
        area = QRect(0, 0, 1920, 1080)
        prepare_fit(window, area, monkeypatch)
        window.cfg["pos_preset"] = "top-left"
        window.move(200, 200)
        saved = {}
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: saved.update(cfg))

        window.mousePressEvent(press_event((50, 50), (250, 250)))
        window.mouseMoveEvent(move_event((70, 70), (270, 270)))
        window.mouseReleaseEvent(release_event((70, 70), (270, 270)))

        assert (window.x(), window.y()) == (220, 220)
        assert window.cfg["pos_preset"] == ""  # 拖动即脱离预设
        assert (window.cfg["pos_x"], window.cfg["pos_y"]) == (220, 220)
        assert window.cfg["pos_anchor"] == anchor_of(area)
        assert saved["pos_preset"] == ""

    def test_click_without_move_keeps_preset(self, qapp, monkeypatch):
        window = make_window("normal")
        area = QRect(0, 0, 1920, 1080)
        prepare_fit(window, area, monkeypatch)
        window.cfg["pos_preset"] = "bottom-right"
        window.move(200, 200)
        saved = {}
        monkeypatch.setattr(settings_mod, "save_settings", lambda cfg: saved.update(cfg))

        window.mousePressEvent(press_event((50, 50), (250, 250)))
        window.mouseReleaseEvent(release_event((50, 50), (250, 250)))

        assert window.cfg["pos_preset"] == "bottom-right"
        assert not saved


class TestDialogPresetBinding:
    def test_initial_preset_shown_without_overwriting_coords(self, qapp):
        dialog = SettingsDialog(merged_settings(
            {"pos_preset": "bottom-left", "pos_x": 1, "pos_y": 2}))
        assert dialog.pos_preset_combo.currentData() == "bottom-left"
        # 初始化不得用预设坐标覆盖已存的精确坐标
        assert (dialog.pos_x_spin.value(), dialog.pos_y_spin.value()) == (1, 2)

    def test_select_preset_fills_spins_and_apply_keeps_it(self, qapp, monkeypatch):
        dialog = SettingsDialog(merged_settings({}))
        monkeypatch.setattr(dialog, "_target_area", lambda: QRect(0, 0, 1920, 1080))
        dialog.pos_preset_combo.setCurrentIndex(9)  # bottom-right
        cfg = dialog.apply()
        assert cfg["pos_preset"] == "bottom-right"
        assert (cfg["pos_x"], cfg["pos_y"]) == preset_point(
            "bottom-right", 240, 120, QRect(0, 0, 1920, 1080))  # 无父窗口按 240×120
        assert dialog.pos_preset_combo.currentIndex() == 9  # 回填坐标不把选择打回自定义

    def test_manual_edit_switches_back_to_custom(self, qapp, monkeypatch):
        dialog = SettingsDialog(merged_settings({}))
        monkeypatch.setattr(dialog, "_target_area", lambda: QRect(0, 0, 1920, 1080))
        dialog.pos_preset_combo.setCurrentIndex(5)  # middle-center
        dialog.pos_x_spin.setValue(123)  # 手动改坐标
        assert dialog.pos_preset_combo.currentIndex() == 0  # 自定义
        assert dialog.apply()["pos_preset"] == ""

from PySide6.QtCore import QRect, Qt

import settings as settings_mod
from main import (
    POSITION_LABELS,
    POSITION_PRESETS,
    ClockWindow,
    MODE_FLAGS,
    SettingsDialog,
    preset_point,
)
from settings import merged_settings


def make_window(mode, **overrides):
    cfg = merged_settings({"window_behavior": mode, **overrides})
    return ClockWindow(cfg, enable_tray=False)


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

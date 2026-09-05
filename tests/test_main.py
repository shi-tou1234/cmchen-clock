from PySide6.QtCore import Qt

from main import ClockWindow, MODE_FLAGS, SettingsDialog
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

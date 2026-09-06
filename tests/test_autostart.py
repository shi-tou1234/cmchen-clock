import sys

import autostart
from settings import DEFAULTS, load_settings, save_settings


class TestBuilders:
    def test_launcher_command_non_empty(self):
        cmd = autostart.launcher_command()
        assert isinstance(cmd, list) and cmd
        assert all(isinstance(part, str) and part for part in cmd)
        if not getattr(sys, "frozen", False):
            assert cmd[-1].endswith("main.py")

    def test_windows_command_quotes_paths_with_spaces(self, monkeypatch):
        monkeypatch.setattr(
            autostart, "launcher_command",
            lambda: ["C:/My App/pythonw.exe", "D:/My Clock/main.py"])
        assert autostart.build_windows_command() == (
            '"C:/My App/pythonw.exe" "D:/My Clock/main.py"')

    def test_macos_plist_structure(self, monkeypatch):
        monkeypatch.setattr(
            autostart, "launcher_command",
            lambda: ["/usr/bin/pythonw", "/app/main.py"])
        plist = autostart.build_macos_plist()
        assert plist["Label"] == autostart.MACOS_LABEL
        assert plist["RunAtLoad"] is True
        assert plist["ProgramArguments"] == ["/usr/bin/pythonw", "/app/main.py"]

    def test_linux_desktop_format(self, monkeypatch):
        monkeypatch.setattr(autostart, "launcher_command", lambda: ["/opt/app/clock"])
        text = autostart.build_linux_desktop()
        assert text.startswith("[Desktop Entry]")
        assert "Type=Application" in text
        assert 'Exec="/opt/app/clock"' in text
        assert "Terminal=false" in text

    def test_linux_desktop_quotes_spaces(self, monkeypatch):
        monkeypatch.setattr(
            autostart, "launcher_command",
            lambda: ["C:/a b/x.exe", "D:/c d/y.py"])
        assert '"C:/a b/x.exe" "D:/c d/y.py"' in autostart.build_linux_desktop()


class TestSettingsAutostart:
    def test_autostart_defaults_false_and_roundtrips(self, tmp_path):
        assert DEFAULTS["autostart"] is False
        assert load_settings(base=tmp_path)["autostart"] is False
        save_settings({"autostart": True}, base=tmp_path)
        assert load_settings(base=tmp_path)["autostart"] is True
        save_settings({"autostart": "yes"}, base=tmp_path)
        assert load_settings(base=tmp_path)["autostart"] is False


class TestPlatform:
    def test_is_supported_matches_known_platforms(self):
        expected = sys.platform in ("win32", "darwin", "linux")
        assert autostart.is_supported() == expected

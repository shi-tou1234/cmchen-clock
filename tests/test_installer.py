"""安装器共享逻辑测试。

纯逻辑（版本解析/路径推导/清单）跨平台可跑；涉及注册表、快捷方式 COM、
install/uninstall 主流程的用例依赖 Windows，只在 win32 下执行。
"""

import json
import sys
from pathlib import Path

import pytest

import installer_common as ic

win32 = sys.platform == "win32"
if win32:  # GUI 外壳只在 Windows 导入（tkinter/PySide6 在 CI 的 Linux  runner 上不可用）
    import setup_app
    import uninstall_app


class TestAppVersion:
    def test_reads_version_from_file(self, tmp_path):
        (tmp_path / "app_version.py").write_text(
            '"""doc"""\n\nAPP_VERSION = "9.9.9"\n', encoding="utf-8")
        assert ic.read_app_version(tmp_path) == "9.9.9"

    def test_missing_or_broken_file_falls_back(self, tmp_path):
        assert ic.read_app_version(tmp_path) == "0.0.0"
        (tmp_path / "app_version.py").write_text("APP_VERSION = None", encoding="utf-8")
        assert ic.read_app_version(tmp_path) == "0.0.0"

    def test_rejects_path_outside_base(self, tmp_path):
        assert ic.read_app_version(tmp_path / ".." / "..") == "0.0.0"

    def test_bundled_version_matches_source(self):
        assert ic.bundled_app_version() == ic.read_app_version(
            Path(ic.__file__).resolve().parent)


class TestPaths:
    def test_default_install_dir_under_localappdata(self):
        path = ic.default_install_dir()
        assert path.is_absolute()
        assert path.parts[-2:] == ("Programs", "DesktopClock")

    def test_start_menu_dir_shape(self):
        path = ic.start_menu_dir()
        assert path.is_absolute()
        assert path.parts[-2] == "Programs"
        assert path.name == "DesktopClock"

    def test_desktop_dir_non_empty(self):
        assert ic.desktop_dir().name

    def test_settings_dir(self):
        assert ic.settings_dir().name == ".desktop-clock"

    def test_shortcut_plan_respects_options(self):
        plan = ic._shortcut_plan(
            {"desktop": True, "start_menu": False}, Path("D:/Apps/DesktopClock"))
        assert len(plan) == 1
        lnk, target, icon, description = plan[0]
        assert lnk.name == "DesktopClock.lnk"
        assert lnk.parent == ic.desktop_dir()
        assert target == Path("D:/Apps/DesktopClock/DesktopClock.exe")
        assert icon == Path("D:/Apps/DesktopClock/icon.ico")
        assert description == ic.DISPLAY_NAME

    def test_shortcut_plan_empty_when_both_off(self):
        assert ic._shortcut_plan({"desktop": False, "start_menu": False},
                                 Path("D:/Apps/DesktopClock")) == []


class TestManifest:
    def test_roundtrip(self, tmp_path):
        ic.write_manifest(tmp_path, "1.0.5",
                          ["uninstall.exe", "DesktopClock.exe"],
                          ["C:/x/DesktopClock.lnk"])
        data = ic.read_manifest(tmp_path)
        assert data["version"] == "1.0.5"
        assert data["files"] == ["DesktopClock.exe", "uninstall.exe"]
        assert data["shortcuts"] == ["C:/x/DesktopClock.lnk"]

    def test_missing_and_corrupt_return_none(self, tmp_path):
        assert ic.read_manifest(tmp_path) is None
        (tmp_path / ic.MANIFEST_FILE).write_text("{broken", encoding="utf-8")
        assert ic.read_manifest(tmp_path) is None

    def test_estimated_size_at_least_one_kb(self, tmp_path):
        (tmp_path / "a.bin").write_bytes(b"x" * 4096)
        assert ic.estimated_size_kb([tmp_path / "a.bin"]) == 4
        assert ic.estimated_size_kb([tmp_path / "missing.bin"]) == 1


@pytest.mark.skipif(not win32, reason="Windows 专用")
class TestShortcuts:
    def test_create_and_read_back(self, tmp_path):
        target_dir = tmp_path / "D 目标"
        target_dir.mkdir()
        target = target_dir / ic.APP_EXE
        target.write_bytes(b"MZ")
        icon = tmp_path / ic.ICON_FILE
        icon.write_bytes(b"icon")
        lnk = tmp_path / "shortcuts" / "DesktopClock.lnk"

        ic.create_shortcut(lnk, target, icon=icon, description="桌面时钟")

        assert lnk.is_file() and lnk.stat().st_size > 400
        raw = lnk.read_bytes()
        # 工作目录/描述以 UTF-16 存入 .lnk
        assert str(target_dir).encode("utf-16-le") in raw
        assert "桌面时钟".encode("utf-16-le") in raw
        # 用同一套 COM 接口回读目标路径，确认 .lnk 是合法 shell link
        assert _read_shortcut_target(lnk) == str(target)

    def test_remove_shortcut(self, tmp_path):
        lnk = tmp_path / "a.lnk"
        lnk.write_bytes(b"x")
        assert ic.remove_shortcut(lnk) is True
        assert ic.remove_shortcut(lnk) is True  # 不存在也视为成功
        folder = tmp_path / "dir.lnk"
        folder.mkdir()
        assert ic.remove_shortcut(folder) is False


@pytest.mark.skipif(not win32, reason="Windows 专用")
class TestFileOps:
    def test_remove_tree_nested(self, tmp_path):
        root = tmp_path / "tree"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "f.txt").write_text("x", encoding="utf-8")
        (root / "ro.txt").write_text("x", encoding="utf-8")
        assert ic.remove_tree(root) is True
        assert not root.exists()

    def test_remove_tree_missing_is_ok(self, tmp_path):
        assert ic.remove_tree(tmp_path / "nope") is True

    def test_remove_file_missing_is_ok(self, tmp_path):
        assert ic.remove_file(tmp_path / "nope") is True


def _read_shortcut_target(lnk_path):
    """用 IShellLinkW::GetPath（vtable[3]）回读快捷方式目标。"""
    import ctypes

    link = ctypes.c_void_p()
    hr = ic._ole32().CoCreateInstance(
        ctypes.byref(ic._guid(ic._CLSID_SHELL_LINK)), None, 1,
        ctypes.byref(ic._guid(ic._IID_ISHELL_LINK_W)), ctypes.byref(link))
    assert hr == 0
    try:
        persist = ctypes.c_void_p()
        hr = ic._com_call(link.value, 0,
                          [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                          ctypes.HRESULT,
                          ctypes.byref(ic._guid(ic._IID_IPERSIST_FILE)),
                          ctypes.byref(persist))
        assert hr == 0
        try:
            hr = ic._com_call(persist.value, 5, [ctypes.c_wchar_p, ctypes.c_uint],
                              ctypes.HRESULT, str(lnk_path), 0)  # IPersistFile::Load
            assert hr == 0
        finally:
            ic._com_call(persist.value, 2, [], None)
        buffer = ctypes.create_unicode_buffer(1024)
        hr = ic._com_call(link.value, 3,
                          [ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p,
                           ctypes.c_uint], ctypes.HRESULT, buffer, 1024, None, 0)
        assert hr == 0
        return buffer.value
    finally:
        ic._com_call(link.value, 2, [], None)


@pytest.mark.skipif(not win32, reason="Windows 专用")
class TestInstallUninstallFlow:
    """用 monkeypatch 把外部依赖（注册表/系统目录/进程/启动）换成临时目录，
    对 install/uninstall 主流程做不碰真实系统的端到端验证。"""

    @pytest.fixture()
    def sandbox(self, tmp_path, monkeypatch):
        payload = tmp_path / "payload"
        payload.mkdir()
        (payload / ic.APP_EXE).write_bytes(b"MZ app")
        (payload / ic.UNINSTALLER_EXE).write_bytes(b"MZ uninstaller")
        (payload / ic.ICON_FILE).write_bytes(b"icon")
        desktop = tmp_path / "desktop"
        start_menu = tmp_path / "startmenu"
        install_dir = tmp_path / "install"
        registry = {}

        monkeypatch.setattr(ic, "payload_dir", lambda: payload)
        monkeypatch.setattr(ic, "desktop_dir", lambda: desktop)
        monkeypatch.setattr(ic, "start_menu_dir", lambda: start_menu)
        monkeypatch.setattr(ic, "app_pids", lambda: [])
        monkeypatch.setattr(ic, "launch_app", lambda _dir: None)
        monkeypatch.setattr(ic, "read_uninstall_entry",
                            lambda: registry.get("entry"))
        monkeypatch.setattr(ic, "write_uninstall_entry",
                            lambda install_dir, version, kb:
                            registry.update(entry={"install_dir": Path(install_dir),
                                                   "display_version": version}))
        monkeypatch.setattr(ic, "delete_uninstall_entry",
                            lambda: registry.pop("entry", None))
        monkeypatch.setattr(ic, "clear_autostart_if_installed", lambda _dir: False)
        return {"install_dir": install_dir, "desktop": desktop,
                "start_menu": start_menu, "registry": registry}

    def test_install_creates_everything(self, sandbox):
        options = {"install_dir": str(sandbox["install_dir"]),
                   "desktop": True, "start_menu": True, "run_after": False}
        result = ic.install(options)

        assert result["version"] == ic.bundled_app_version()
        for name in (ic.APP_EXE, ic.UNINSTALLER_EXE, ic.ICON_FILE, ic.MANIFEST_FILE):
            assert (sandbox["install_dir"] / name).is_file()
        assert (sandbox["desktop"] / "DesktopClock.lnk").is_file()
        assert (sandbox["start_menu"] / "DesktopClock.lnk").is_file()
        assert sandbox["registry"]["entry"]["display_version"] == result["version"]
        assert _read_shortcut_target(
            sandbox["desktop"] / "DesktopClock.lnk") == str(
            sandbox["install_dir"] / ic.APP_EXE)

    def test_uninstall_removes_everything(self, sandbox):
        options = {"install_dir": str(sandbox["install_dir"]),
                   "desktop": True, "start_menu": True, "run_after": False}
        ic.install(options)
        result = ic.uninstall(sandbox["install_dir"], schedule_self=False)

        assert result["install_dir"] == str(sandbox["install_dir"])
        assert not sandbox["install_dir"].exists()
        assert not (sandbox["desktop"] / "DesktopClock.lnk").exists()
        assert not sandbox["start_menu"].exists()  # 空目录一并清掉
        assert "entry" not in sandbox["registry"]

    def test_uninstall_purge_removes_settings(self, sandbox, tmp_path, monkeypatch):
        settings = tmp_path / "home" / ".desktop-clock"
        settings.mkdir(parents=True)
        (settings / "settings.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(ic, "settings_dir", lambda: settings)
        ic.install({"install_dir": str(sandbox["install_dir"]),
                    "desktop": False, "start_menu": False, "run_after": False})
        ic.uninstall(sandbox["install_dir"], remove_settings=True,
                     schedule_self=False)
        assert not settings.exists()

    def test_upgrade_cleans_old_dir(self, sandbox, tmp_path, monkeypatch):
        old_dir = tmp_path / "old-install"
        old_dir.mkdir()
        (old_dir / ic.APP_EXE).write_bytes(b"old")
        (old_dir / "stale-extra.txt").write_bytes(b"stale")
        sandbox["registry"]["entry"] = {"install_dir": old_dir,
                                        "display_version": "1.0.4"}
        ic.install({"install_dir": str(sandbox["install_dir"]),
                    "desktop": True, "start_menu": False, "run_after": False})
        assert not old_dir.exists()
        assert (sandbox["install_dir"] / ic.APP_EXE).is_file()

    def test_install_rejects_relative_dir(self, sandbox):
        with pytest.raises(ic.InstallError):
            ic.install({"install_dir": "relative/path", "desktop": False,
                        "start_menu": False, "run_after": False})

    def test_install_rejects_quote_in_dir(self, sandbox, tmp_path):
        with pytest.raises(ic.InstallError):
            ic.install({"install_dir": f'{tmp_path}/a"b', "desktop": False,
                        "start_menu": False, "run_after": False})

    def test_running_app_blocks_install(self, sandbox, monkeypatch):
        monkeypatch.setattr(ic, "app_pids", lambda: [1234])
        with pytest.raises(ic.AppRunningError):
            ic.install({"install_dir": str(sandbox["install_dir"]),
                        "desktop": False, "start_menu": False,
                        "run_after": False})


@pytest.mark.skipif(not win32, reason="Windows 专用")
class TestSelfCleanup:
    def test_command_shape(self, tmp_path, monkeypatch):
        """收尾命令必须 shell=True 且先 cd  away——两个坑都是本机实测踩过的。"""
        calls = {}

        class FakePopen:
            def __init__(self, args, **kwargs):
                calls["args"] = args
                calls["kwargs"] = kwargs

        monkeypatch.setattr(ic.subprocess, "Popen", FakePopen)
        install_dir = tmp_path / "install"
        leftover = install_dir / ic.UNINSTALLER_EXE
        ic.schedule_self_cleanup(install_dir, [leftover])

        assert calls["kwargs"].get("shell") is True
        command = calls["args"]
        assert "cd /d %TEMP%" in command
        assert f'del /f /q "{leftover}"' in command
        assert f'rmdir /q "{install_dir}"' in command


@pytest.mark.skipif(not win32, reason="Windows 专用")
class TestArgParsing:
    def test_setup_defaults(self):
        silent, options = setup_app.parse_args([])
        assert silent is False
        assert options["desktop"] is True
        assert options["start_menu"] is True
        assert options["run_after"] is False
        assert options["install_dir"] == str(ic.default_install_dir())

    def test_setup_flags(self):
        silent, options = setup_app.parse_args(
            ["--silent", "--dir", "D:/My Apps/Clock", "--no-desktop",
             "--no-start-menu", "--run"])
        assert silent is True
        assert options["install_dir"] == "D:/My Apps/Clock"
        assert options["desktop"] is False
        assert options["start_menu"] is False
        assert options["run_after"] is True

    def test_setup_unknown_arg_exits(self):
        with pytest.raises(SystemExit):
            setup_app.parse_args(["--bogus"])

    def test_setup_dir_without_value_exits(self):
        with pytest.raises(SystemExit):
            setup_app.parse_args(["--dir"])

    def test_uninstall_flags(self):
        assert uninstall_app.parse_args(["--silent"]) == (True, False)
        assert uninstall_app.parse_args(["--silent", "--purge"]) == (True, True)
        assert uninstall_app.parse_args([]) == (False, False)

    def test_uninstall_unknown_arg_exits(self):
        with pytest.raises(SystemExit):
            uninstall_app.parse_args(["--bogus"])


@pytest.mark.skipif(not win32, reason="Windows 专用")
class TestLocateInstallDir:
    def test_returns_none_when_nothing_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ic, "read_uninstall_entry", lambda: None)
        monkeypatch.setattr(ic, "default_install_dir", lambda: tmp_path / "nowhere")
        monkeypatch.setattr(ic, "read_manifest", lambda _dir: None)
        assert uninstall_app.locate_install_dir() is None

    def test_prefers_registry_entry(self, tmp_path, monkeypatch):
        installed = tmp_path / "installed"
        installed.mkdir()
        (installed / ic.APP_EXE).write_bytes(b"MZ")
        monkeypatch.setattr(ic, "read_uninstall_entry",
                            lambda: {"install_dir": installed})
        assert uninstall_app.locate_install_dir() == installed

"""开机自启动管理（跨平台，零第三方依赖）。

机制：
- Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 注册表值（登录时启动，不弹窗）
- macOS:   ~/Library/LaunchAgents/com.desktop-clock.plist（RunAtLoad）
- Linux:   ~/.config/autostart/desktop-clock.desktop（XDG Autostart）

安全设计：写入目标一律由「固定父目录 resolve() + 固定文件名」构造，
落盘前用 relative_to 做包含校验；写操作只落在当前用户作用域。
enable/disable 可反复调用（幂等）。
"""

import plistlib
import subprocess
import sys
from pathlib import Path

APP_NAME = "DesktopClock"
MACOS_LABEL = "com.desktop-clock"
WIN_VALUE_NAME = "DesktopClock"

_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_MACOS_DIR = Path.home() / "Library" / "LaunchAgents"
_LINUX_DIR = Path.home() / ".config" / "autostart"
_MACOS_FILENAME = f"{MACOS_LABEL}.plist"
_LINUX_FILENAME = "desktop-clock.desktop"


def app_root():
    """应用根目录（源码运行=项目根；打包运行=可执行文件所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def launcher_command():
    """登录后拉起本应用的命令行（列表形式）。

    源码运行优先用 pythonw（Windows 下登录启动不弹控制台黑窗）。
    """
    if getattr(sys, "frozen", False):
        return [sys.executable]
    python_exe = Path(sys.executable)
    pythonw = python_exe.with_name("pythonw.exe")
    target = pythonw if pythonw.is_file() else python_exe
    return [str(target), str(app_root() / "main.py")]


def build_windows_command():
    """注册表 Run 值的命令行文本（Windows 引号规则）。"""
    return subprocess.list2cmdline(launcher_command())


def build_macos_plist():
    """LaunchAgents plist 内容。"""
    return {
        "Label": MACOS_LABEL,
        "ProgramArguments": launcher_command(),
        "RunAtLoad": True,
    }


def build_linux_desktop():
    """XDG autostart .desktop 内容。"""
    quoted = " ".join(f'"{part}"' for part in launcher_command())
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={quoted}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _safe_target(directory, filename):
    """固定父目录 resolve + 固定文件名 → 包含校验后返回目标路径。"""
    root = directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / filename).resolve()
    target.relative_to(root)
    return target


def is_supported():
    return sys.platform in ("win32", "darwin", "linux")


def is_enabled():
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
                winreg.QueryValueEx(key, WIN_VALUE_NAME)
                return True
        if sys.platform == "darwin":
            return (_MACOS_DIR / _MACOS_FILENAME).is_file()
        if sys.platform == "linux":
            return (_LINUX_DIR / _LINUX_FILENAME).is_file()
    except OSError:
        return False
    return False


def enable():
    """注册开机自启动（幂等；每次调用刷新命令行，路径变化自动纠正）。"""
    if sys.platform == "win32":
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
            winreg.SetValueEx(key, WIN_VALUE_NAME, 0, winreg.REG_SZ, build_windows_command())
        return True
    if sys.platform == "darwin":
        target = _safe_target(_MACOS_DIR, _MACOS_FILENAME)
        target.write_bytes(plistlib.dumps(build_macos_plist()))
        return True
    if sys.platform == "linux":
        target = _safe_target(_LINUX_DIR, _LINUX_FILENAME)
        target.write_text(build_linux_desktop(), encoding="utf-8")
        return True
    return False


def disable():
    """注销开机自启动（不存在时静默成功）。"""
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, WIN_VALUE_NAME)
            return True
        if sys.platform == "darwin":
            target = _safe_target(_MACOS_DIR, _MACOS_FILENAME)
            target.unlink(missing_ok=True)
            return True
        if sys.platform == "linux":
            target = _safe_target(_LINUX_DIR, _LINUX_FILENAME)
            target.unlink(missing_ok=True)
            return True
    except FileNotFoundError:
        return True
    return False


def sync(enabled):
    """按开关落盘（UI 唯一入口）。返回实际是否处于启用态。"""
    if not is_supported():
        return False
    if enabled:
        return enable()
    disable()
    return False

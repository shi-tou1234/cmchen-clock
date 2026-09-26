"""Windows 安装器/卸载程序共享逻辑（标准库实现，零第三方依赖）。

四块职责：
- 路径：默认装到 %LOCALAPPDATA%\\Programs\\DesktopClock（当前用户作用域，不需要管理员权限）
- 注册表：写 HKCU 卸载条目，软件才会出现在系统「已安装软件」列表并可被卸载
- 快捷方式：桌面 / 开始菜单，ctypes 直调 IShellLinkW + IPersistFile。
  vtable 下标经本机 Win11 真机逐下标实测（文档方法表按字母序、会误导）：
  SetDescription=7 / SetWorkingDirectory=9 / SetArguments=11 /
  SetIconLocation=17 / SetPath=20，IPersistFile::Save=6
- 安装清单 install-manifest.json：卸载时据此删除文件与快捷方式

路径安全约定与 autostart.py 一致：固定文件名 + base resolve() + relative_to 白名单校验。
"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

APP_ID = "DesktopClock"
APP_EXE = "DesktopClock.exe"
UNINSTALLER_EXE = "uninstall.exe"
ICON_FILE = "icon.ico"
MANIFEST_FILE = "install-manifest.json"
PAYLOAD_DIR = "payload"
VERSION_FILE = "app_version.py"
DISPLAY_NAME = "DesktopClock 桌面时钟"
PUBLISHER = "cmchen"
URL_ABOUT = "https://github.com/shi-tou1234/cmchen-clock"
SETTINGS_DIR_NAME = ".desktop-clock"
UNINSTALL_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DesktopClock"
AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
DESKTOP_FOLDER_GUID = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"

WM_CLOSE = 0x0010
CREATE_NO_WINDOW = 0x08000000


class InstallError(RuntimeError):
    """安装/卸载流程失败（可向用户展示的中文消息）。"""


class AppRunningError(InstallError):
    """侦测到时钟仍在运行且未能关闭。"""


def is_windows():
    return sys.platform == "win32"


def _require_windows():
    if not is_windows():
        raise InstallError("安装器仅支持 Windows 平台")


# ---------------------------------------------------------------- 路径推导


def default_install_dir():
    """默认安装目录：%LOCALAPPDATA%\\Programs\\DesktopClock（免管理员）。"""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Programs" / APP_ID


def known_folder(guid_text):
    """SHGetKnownFolderPath 查系统特殊目录（桌面等，兼容 OneDrive 重定向）。"""
    if not is_windows():
        return None
    shell32 = ctypes.windll.shell32
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
    guid = _guid(guid_text)
    ptr = ctypes.c_wchar_p()
    if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr)) != 0:
        return None
    try:
        return Path(ptr.value) if ptr.value else None
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ptr)


def desktop_dir():
    """真实桌面目录（读系统已知文件夹，失败回退 %USERPROFILE%\\Desktop）。"""
    folder = known_folder(DESKTOP_FOLDER_GUID)
    if folder is not None:
        return folder
    profile = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(profile) / "Desktop"


def start_menu_dir():
    """开始菜单程序目录：%APPDATA%\\...\\Start Menu\\Programs\\DesktopClock。"""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / APP_ID)


def settings_dir():
    """应用个人设置目录（与 main.py 的 ~/.desktop-clock 一致）。"""
    return Path.home() / SETTINGS_DIR_NAME


def payload_dir():
    """安装包内 payload 目录（PyInstaller 解包目录/payload；源码运行=项目 dist/）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / PAYLOAD_DIR
    return Path(__file__).resolve().parent / "dist"


# ---------------------------------------------------------------- 版本号

_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def read_app_version(base):
    """从 base/app_version.py 读 APP_VERSION；缺失或解析失败回退 0.0.0。"""
    root = Path(base).resolve()
    target = (root / VERSION_FILE).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return "0.0.0"
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = _VERSION_RE.search(text)
    return match.group(1) if match else "0.0.0"


def bundled_app_version():
    """打包版读包内版本号；源码运行读项目根版本号。"""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent
    return read_app_version(base)


# ---------------------------------------------------------------- COM 快捷方式


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


def _guid(text):
    guid = _GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(guid))
    return guid


_CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
_IID_ISHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPERSIST_FILE = "{0000010b-0000-0000-C000-000000000046}"
_VT_SET_DESCRIPTION = 7
_VT_SET_WORKING_DIRECTORY = 9
_VT_SET_ARGUMENTS = 11
_VT_SET_ICON_LOCATION = 17
_VT_SET_PATH = 20
_VT_PERSIST_SAVE = 6
_VT_RELEASE = 2


def _com_call(ptr, index, argtypes, restype=ctypes.HRESULT, *args):
    """按 vtable 下标调用 COM 方法（ptr 为接口指针地址，WINFUNCTYPE=stdcall）。"""
    obj = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))
    vtbl = ctypes.cast(obj[0], ctypes.POINTER(ctypes.c_void_p))
    method = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
    return method(ptr, *args)


def _ole32():
    ole32 = ctypes.windll.ole32
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.HRESULT
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    return ole32


def create_shortcut(lnk_path, target, *, work_dir=None, icon=None,
                    arguments="", description=""):
    """创建 Windows 快捷方式（.lnk）。目标路径带空格/中文均可。"""
    _require_windows()
    lnk_path = Path(lnk_path)
    target = Path(target)
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    ole32 = _ole32()
    ole32.CoInitialize(None)
    link = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(_guid(_CLSID_SHELL_LINK)), None, 1,  # CLSCTX_INPROC_SERVER
        ctypes.byref(_guid(_IID_ISHELL_LINK_W)), ctypes.byref(link))
    if hr != 0:
        raise InstallError(f"创建快捷方式组件失败（CoCreateInstance {hr:#010x}）")
    try:
        plan = (
            (_VT_SET_PATH, [ctypes.c_wchar_p], (str(target),)),
            (_VT_SET_WORKING_DIRECTORY, [ctypes.c_wchar_p],
             (str(work_dir or target.parent),)),
            (_VT_SET_ARGUMENTS, [ctypes.c_wchar_p], (arguments or "",)),
            (_VT_SET_DESCRIPTION, [ctypes.c_wchar_p], (description or "",)),
            (_VT_SET_ICON_LOCATION, [ctypes.c_wchar_p, ctypes.c_int],
             (str(icon or target), 0)),
        )
        for index, argtypes, values in plan:
            hr = _com_call(link.value, index, argtypes, ctypes.HRESULT, *values)
            if hr != 0:
                raise InstallError(f"设置快捷方式属性失败（vtable[{index}] {hr:#010x}）")
        persist = ctypes.c_void_p()
        hr = _com_call(link.value, 0,
                       [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                       ctypes.HRESULT,
                       ctypes.byref(_guid(_IID_IPERSIST_FILE)),
                       ctypes.byref(persist))
        if hr != 0:
            raise InstallError(f"快捷方式保存组件不可用（{hr:#010x}）")
        try:
            hr = _com_call(persist.value, _VT_PERSIST_SAVE,
                           [ctypes.c_wchar_p, wintypes.BOOL], ctypes.HRESULT,
                           str(lnk_path), True)
            if hr != 0:
                raise InstallError(f"保存快捷方式失败（{hr:#010x}）")
        finally:
            _com_call(persist.value, _VT_RELEASE, [], None)
    finally:
        _com_call(link.value, _VT_RELEASE, [], None)


def remove_shortcut(path):
    """删除快捷方式（不存在视为成功）。"""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


# ---------------------------------------------------------------- 注册表


def read_uninstall_entry():
    """读 HKCU 卸载条目；未安装返回 None。"""
    _require_windows()
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as key:
            def query(name):
                try:
                    return winreg.QueryValueEx(key, name)[0]
                except OSError:
                    return None

            install_dir = query("InstallLocation")
            if not install_dir:
                return None
            return {
                "install_dir": Path(install_dir),
                "display_name": query("DisplayName") or DISPLAY_NAME,
                "display_version": query("DisplayVersion") or "",
                "uninstall_string": query("UninstallString") or "",
            }
    except OSError:
        return None


def write_uninstall_entry(install_dir, version, estimated_kb):
    """写 HKCU 卸载条目：系统「已安装软件」列表显示 + 提供卸载入口。"""
    _require_windows()
    import winreg

    install_dir = Path(install_dir)
    exe = install_dir / APP_EXE
    uninstaller = install_dir / UNINSTALLER_EXE
    values = {
        "DisplayName": DISPLAY_NAME,
        "DisplayIcon": f"{exe},0",
        "DisplayVersion": str(version),
        "Publisher": PUBLISHER,
        "InstallLocation": str(install_dir),
        "UninstallString": f'"{uninstaller}"',
        "QuietUninstallString": f'"{uninstaller}" --silent',
        "EstimatedSize": int(estimated_kb),
        "NoModify": 1,
        "NoRepair": 1,
        "URLInfoAbout": URL_ABOUT,
        "Comments": "像壁纸一样常驻桌面的轻量时钟",
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as key:
        for name, value in values.items():
            winreg.SetValueEx(
                key, name, 0,
                winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ,
                value)


def delete_uninstall_entry():
    """删除卸载条目（不存在视为成功）。"""
    _require_windows()
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise InstallError(f"删除注册表条目失败：{exc}") from exc


def clear_autostart_if_installed(install_dir):
    """Run 键指向本次卸载的安装目录时才清除开机自启动，避免误删其它副本。"""
    _require_windows()
    import winreg
    import autostart

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            command = winreg.QueryValueEx(key, autostart.WIN_VALUE_NAME)[0]
            if str(install_dir).lower() not in str(command).lower():
                return False
            winreg.DeleteValue(key, autostart.WIN_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


# ---------------------------------------------------------------- 安装清单


def write_manifest(install_dir, version, files, shortcuts):
    """写安装清单（卸载依据），返回清单内容。"""
    install_dir = Path(install_dir)
    data = {
        "app_id": APP_ID,
        "version": str(version),
        "install_dir": str(install_dir),
        "files": sorted(str(name) for name in files),
        "shortcuts": sorted(str(path) for path in shortcuts),
    }
    (install_dir / MANIFEST_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def read_manifest(install_dir):
    """读安装清单；缺失或损坏返回 None。"""
    try:
        data = json.loads(
            (Path(install_dir) / MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def estimated_size_kb(paths):
    """估算安装体积（KB，供注册表 EstimatedSize）。"""
    total = 0
    for item in paths:
        try:
            total += Path(item).stat().st_size
        except OSError:
            continue
    return max(1, total // 1024)


# ---------------------------------------------------------------- 进程侦测


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def app_pids():
    """运行中的时钟进程 id 列表（按可执行文件名匹配）。"""
    _require_windows()
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32First.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32)]
    kernel32.Process32First.restype = wintypes.BOOL
    kernel32.Process32Next.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32)]
    kernel32.Process32Next.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == 0xFFFFFFFFFFFFFFFF:
        return []
    try:
        entry = _PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        pids = []
        ok = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile.decode("utf-8", "replace").lower()
            if name == APP_EXE.lower():
                pids.append(int(entry.th32ProcessID))
            ok = kernel32.Process32Next(snapshot, ctypes.byref(entry))
        return pids
    finally:
        kernel32.CloseHandle(snapshot)


def _top_level_windows(pids):
    """属于指定进程的顶层窗口句柄（含隐藏窗口：时钟隐藏到托盘时仍是顶层窗口）。"""
    _require_windows()
    user32 = ctypes.windll.user32
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    targets = set(pids)
    found = []

    def callback(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in targets:
            found.append(hwnd)
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                   wintypes.LPARAM)(callback)
    user32.EnumWindows(enum_proc, 0)
    return found


def request_app_close(pids, timeout=5.0):
    """给时钟窗口发 WM_CLOSE 并等待退出；返回是否已全部退出。"""
    if not pids:
        return True
    _require_windows()
    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    for hwnd in _top_level_windows(pids):
        user32.PostMessageW(hwnd, WM_CLOSE, None, None)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not app_pids():
            return True
        time.sleep(0.2)
    return not app_pids()


def terminate_pids(pids):
    """强制结束进程（用户明确同意后才调用）。"""
    if not pids:
        return
    _require_windows()
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    for pid in pids:
        handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if not handle:
            continue
        try:
            kernel32.TerminateProcess(handle, 1)
            kernel32.WaitForSingleObject(handle, 3000)
        finally:
            kernel32.CloseHandle(handle)


def close_running_app(resolve_running):
    """统一处理「时钟正在运行」：resolve_running() 返回 True 才继续。

    resolve_running 由调用方注入（GUI 弹窗询问 / 静默自动关闭），
    返回 False 表示用户放弃，抛 AppRunningError。
    """
    pids = app_pids()
    if not pids:
        return
    if resolve_running is None or not resolve_running():
        raise AppRunningError("DesktopClock 正在运行，已取消")
    if app_pids():
        raise AppRunningError("DesktopClock 仍未退出，请手动关闭后重试")


# ---------------------------------------------------------------- 文件操作


def remove_file(path):
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def remove_tree(path):
    """删目录树（尽力而为：只读/占用文件清属性后重试）。返回是否已不存在。"""
    path = Path(path)
    if not path.exists():
        return True
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        for child in sorted(path.rglob("*"), reverse=True):
            try:
                if child.is_dir():
                    child.rmdir()
                else:
                    child.unlink()
            except OSError:
                try:
                    child.chmod(0o700)
                    child.unlink()
                except OSError:
                    continue
        try:
            path.rmdir()
        except OSError:
            pass
    return not path.exists()


def copy_payload(install_dir):
    """把安装包 payload 里的程序文件复制到安装目录，返回复制的文件名列表。"""
    source = payload_dir()
    install_dir = Path(install_dir)
    if not source.is_dir():
        raise InstallError(f"安装包内容缺失：{source}")
    install_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for item in sorted(source.iterdir()):
        if not item.is_file():
            continue
        shutil.copy2(item, install_dir / item.name)
        names.append(item.name)
    if APP_EXE not in names or UNINSTALLER_EXE not in names:
        raise InstallError("安装包内容不完整（缺少程序或卸载器）")
    return names


def launch_app(install_dir):
    """启动已安装的时钟。"""
    _require_windows()
    exe = Path(install_dir) / APP_EXE
    if not exe.is_file():
        raise InstallError(f"找不到程序文件：{exe}")
    os.startfile(str(exe))


def schedule_self_cleanup(install_dir, leftovers):
    """卸载收尾：卸载器自身在安装目录内、运行中删不掉自己。

    交给一个隐藏 cmd 子进程在本进程退出后执行：只删白名单残项，
    再 rmdir（不带 /s，目录非空即失败，绝不误删目录里其它文件）。
    必须用 shell=True 传整条命令串：subprocess 列表形式会给命令加外层
    引号，与路径上的内层引号嵌套后 cmd 解析直接失败（本机实测）。
    命令先 cd 到 TEMP：helper 进程的 CWD 不能是安装目录，否则 rmdir
    会报「目录被占用」（任何进程拿目录当 CWD 都会锁住它，同样实测）。
    """
    commands = ["cd /d %TEMP% >nul", "ping 127.0.0.1 -n 3 >nul"]
    for item in leftovers:
        commands.append(f'del /f /q "{item}"')
    commands.append(f'rmdir /q "{install_dir}"')
    subprocess.Popen(
        " && ".join(commands),
        shell=True,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )


# ---------------------------------------------------------------- 安装/卸载主流程


def _shortcut_plan(options, install_dir):
    """按选项算出要创建的快捷方式列表 [(lnk路径, 目标, 图标, 描述)]。"""
    install_dir = Path(install_dir)
    exe = install_dir / APP_EXE
    icon = install_dir / ICON_FILE
    plan = []
    if options.get("desktop"):
        plan.append((desktop_dir() / f"{APP_ID}.lnk", exe, icon, DISPLAY_NAME))
    if options.get("start_menu"):
        plan.append((start_menu_dir() / f"{APP_ID}.lnk", exe, icon, DISPLAY_NAME))
    return plan


def uninstall(install_dir, *, manifest=None, remove_settings=False,
              progress=None, resolve_running=None, schedule_self=False):
    """卸载：按清单删文件与快捷方式，清理注册表与自启动。

    remove_settings=True 时连同 ~/.desktop-clock 个人设置一起删除。
    schedule_self=True 时把「删卸载器自身 + 删空目录」交给隐藏子进程收尾
    （卸载器 exe 正在运行，无法删除自己）。
    """
    _require_windows()
    install_dir = Path(install_dir)
    entry = read_uninstall_entry()
    if manifest is None:
        manifest = read_manifest(install_dir) or {}
    if entry is None and not manifest and not install_dir.exists():
        raise InstallError("没有找到已安装的 DesktopClock")

    def step(done, total, text):
        if progress:
            progress(done, total, text)

    total = 6
    step(0, total, "正在检查运行中的时钟…")
    close_running_app(resolve_running)

    step(1, total, "正在删除程序文件…")
    files = list(manifest.get("files") or [])
    if not files and install_dir.exists():
        files = [APP_EXE, UNINSTALLER_EXE, ICON_FILE, MANIFEST_FILE]
    for name in files:
        remove_file(install_dir / name)

    step(2, total, "正在删除快捷方式…")
    shortcuts = list(manifest.get("shortcuts") or [])
    if not shortcuts:
        shortcuts = [desktop_dir() / f"{APP_ID}.lnk",
                     start_menu_dir() / f"{APP_ID}.lnk"]
    for path in shortcuts:
        remove_shortcut(path)
    start_dir = start_menu_dir()
    if start_dir.is_dir() and not any(start_dir.iterdir()):
        try:
            start_dir.rmdir()
        except OSError:
            pass

    step(3, total, "正在清理注册表…")
    clear_autostart_if_installed(install_dir)
    delete_uninstall_entry()

    step(4, total, "正在删除个人设置…" if remove_settings else "正在清理安装目录…")
    if remove_settings:
        remove_tree(settings_dir())
    remove_file(install_dir / MANIFEST_FILE)

    # 进程的当前目录若在安装目录内，删除会因「目录被占用」失败——
    # 先把 CWD 切到 TEMP（spawn 的 helper 子进程也会继承），后续删除才稳。
    try:
        os.chdir(tempfile.gettempdir())
    except OSError:
        pass
    # 先尽力整树删除（未锁文件、空目录都能删掉）；卸载器自身正在运行时删不动，
    # 残留项交给隐藏 cmd 子进程在本进程退出后收尾。
    remove_tree(install_dir)
    leftovers = [install_dir / name for name in (UNINSTALLER_EXE, APP_EXE, ICON_FILE)
                 if (install_dir / name).exists()]
    if schedule_self and leftovers:
        schedule_self_cleanup(install_dir, leftovers)

    step(5, total, "卸载完成")
    return {"install_dir": str(install_dir),
            "removed_settings": bool(remove_settings)}


def install(options, *, progress=None, resolve_running=None):
    """执行安装。options 键：install_dir / desktop / start_menu / run_after。

    progress: callable(done, total, text)。
    resolve_running: 侦测到时钟在运行时调用，返回 True 表示已关闭可继续。
    """
    _require_windows()
    version = bundled_app_version()
    install_dir = Path(options["install_dir"])
    if not install_dir.is_absolute():
        raise InstallError(f"安装目录必须是绝对路径：{install_dir}")
    if '"' in str(install_dir):
        raise InstallError(f"安装路径不能包含引号：{install_dir}")

    def step(done, total, text):
        if progress:
            progress(done, total, text)

    total = 6
    step(0, total, "正在检查运行中的时钟…")
    close_running_app(resolve_running)

    step(1, total, "正在清理旧版本…")
    entry = read_uninstall_entry()
    if entry and entry["install_dir"] != install_dir:
        uninstall(entry["install_dir"], progress=None, resolve_running=None)

    step(2, total, "正在复制程序文件…")
    names = copy_payload(install_dir)

    step(3, total, "正在写入安装清单…")
    shortcuts = [lnk for lnk, _t, _i, _d in _shortcut_plan(options, install_dir)]
    write_manifest(install_dir, version, names, shortcuts)
    write_uninstall_entry(
        install_dir, version,
        estimated_size_kb(install_dir / name for name in names))

    step(4, total, "正在创建快捷方式…")
    for lnk, target, icon, description in _shortcut_plan(options, install_dir):
        create_shortcut(lnk, target, icon=icon, description=description)

    step(5, total, "安装完成")
    if options.get("run_after"):
        launch_app(install_dir)
    return {"install_dir": str(install_dir), "version": version,
            "files": names, "shortcuts": [str(p) for p in shortcuts]}

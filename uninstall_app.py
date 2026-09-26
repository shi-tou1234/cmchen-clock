"""DesktopClock 卸载程序（安装时随包落到安装目录的 uninstall.exe）。

系统「设置 → 应用 → 已安装的应用」点卸载、或开始菜单里直接运行本程序均可。
界面用标准库 tkinter 实现：卸载器是后台工具，没必要为此多带一整套 Qt 运行时。

用法：
    uninstall.exe            图形卸载
    uninstall.exe --silent   静默卸载（保留个人设置）
    uninstall.exe --silent --purge   同时删除个人设置

退出码：0 成功；1 失败；2 参数错误。静默模式日志写在 %TEMP%\\DesktopClock-Uninstall.log。
"""

import os
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import installer_common as ic

LOG_NAME = "DesktopClock-Uninstall.log"


def icon_path():
    payload_icon = ic.payload_dir() / ic.ICON_FILE
    if payload_icon.is_file():
        return payload_icon
    return Path(__file__).resolve().parent / "assets" / ic.ICON_FILE


def log_path():
    temp = os.environ.get("TEMP") or os.environ.get("TMP") or "."
    return Path(temp) / LOG_NAME


def write_log(text):
    try:
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass


def locate_install_dir():
    """定位安装目录：注册表条目优先，其次卸载器所在目录，最后默认目录。"""
    entry = ic.read_uninstall_entry()
    if entry:
        candidate = entry["install_dir"]
        if ic.read_manifest(candidate) or candidate.exists():
            return candidate
    frozen_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None
    if frozen_dir and (ic.read_manifest(frozen_dir)
                       or (frozen_dir / ic.APP_EXE).is_file()):
        return frozen_dir
    default = ic.default_install_dir()
    if ic.read_manifest(default) or (default / ic.APP_EXE).is_file():
        return default
    return None


def close_running_gui(root):
    """GUI 版「关闭运行中的时钟」：询问 → 优雅关闭 → 必要时强制结束。"""
    pids = ic.app_pids()
    if not pids:
        return True
    answer = messagebox.askyesno(
        "关闭运行中的时钟", "检测到 DesktopClock 正在运行。\n是否关闭它继续卸载？",
        parent=root)
    if not answer:
        return False
    if ic.request_app_close(pids):
        return True
    answer = messagebox.askyesno(
        "强制结束",
        "时钟仍未退出。\n是否强制结束它？（未保存的界面状态会丢失，设置已实时保存不受影响）",
        parent=root)
    if not answer:
        return False
    ic.terminate_pids(ic.app_pids())
    return not ic.app_pids()


def close_running_silent():
    pids = ic.app_pids()
    if not pids:
        return True
    write_log(f"closing running app pids={pids}")
    if ic.request_app_close(pids):
        return True
    ic.terminate_pids(ic.app_pids())
    return not ic.app_pids()


class UninstallWindow:
    def __init__(self, root, install_dir):
        self.root = root
        self.install_dir = Path(install_dir)
        self.done = False
        root.title("卸载 DesktopClock 桌面时钟")
        root.geometry("520x300")
        root.resizable(False, False)
        try:
            root.iconbitmap(str(icon_path()))
        except tk.TclError:
            pass

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=f"将从以下位置卸载 DesktopClock 桌面时钟：\n{self.install_dir}",
            wraplength=480, justify="left").pack(anchor="w")
        ttk.Label(
            frame,
            text="个人设置（字体、颜色、窗口位置等）默认保留，可勾选下方选项一并删除。",
            wraplength=480, justify="left").pack(anchor="w", pady=(6, 10))

        self.settings_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame, text="同时删除个人设置与配置文件（~/.desktop-clock）",
            variable=self.settings_var).pack(anchor="w")

        self.bar = ttk.Progressbar(frame, maximum=100, length=480)
        self.status = ttk.Label(frame, text="", wraplength=480, justify="left")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")
        self.ok_button = ttk.Button(buttons, text="卸载", command=self._start)
        self.ok_button.pack(side="right")
        self.cancel_button = ttk.Button(buttons, text="取消", command=root.destroy)
        self.cancel_button.pack(side="right", padx=(0, 8))

    def _start(self):
        self.ok_button.config(state="disabled")
        self.cancel_button.config(state="disabled")
        self.bar.pack(anchor="w", pady=(12, 4))
        self.status.config(text="正在卸载…")
        self.status.pack(anchor="w")
        self.root.update_idletasks()
        try:
            result = ic.uninstall(
                self._install_dir,
                remove_settings=self.settings_var.get(),
                progress=self._on_progress,
                resolve_running=lambda: close_running_gui(self.root),
                schedule_self=True)
        except Exception as exc:  # 失败一律转成可读提示，不让窗口裸崩
            self._fail(str(exc) or exc.__class__.__name__)
            return
        write_log(f"uninstall ok {result}")
        self.bar.config(value=100)
        self.status.config(text="卸载完成。感谢使用，再见！")
        self.ok_button.config(text="完成", state="normal",
                              command=self.root.destroy)
        self.cancel_button.pack_forget()
        self.done = True

    def _on_progress(self, done, total, text):
        self.bar.config(value=int(done * 100 / max(1, total)))
        self.status.config(text=text)
        self.root.update_idletasks()

    def _fail(self, message):
        write_log(f"uninstall failed {message}")
        self.bar.pack_forget()
        self.status.config(text=message)
        messagebox.showerror("卸载失败", message, parent=self.root)
        self.ok_button.config(state="normal")
        self.cancel_button.config(state="normal")


def run_gui(install_dir):
    root = tk.Tk()
    window = UninstallWindow(root, install_dir)
    root.mainloop()
    return 0 if window.done else 1


def silent_uninstall(remove_settings):
    install_dir = locate_install_dir()
    if install_dir is None:
        write_log("silent uninstall: nothing installed")
        return 1
    write_log(f"silent uninstall start dir={install_dir} purge={remove_settings}")
    try:
        result = ic.uninstall(
            install_dir,
            remove_settings=remove_settings,
            progress=lambda done, total, text: write_log(f"[{done}/{total}] {text}"),
            resolve_running=close_running_silent,
            schedule_self=True)
    except Exception as exc:
        write_log(f"silent uninstall failed {exc!r}")
        return 1
    write_log(f"silent uninstall ok {result}")
    return 0


USAGE = __doc__.strip()


def parse_args(argv):
    silent = False
    purge = False
    for arg in argv:
        if arg == "--silent":
            silent = True
        elif arg == "--purge":
            purge = True
        elif arg in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        else:
            raise SystemExit(f"未知参数 {arg}\n\n{USAGE}")
    return silent, purge


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    silent, purge = parse_args(argv)
    if silent:
        return silent_uninstall(purge)
    install_dir = locate_install_dir()
    if install_dir is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("卸载 DesktopClock", "没有找到已安装的 DesktopClock。")
        root.destroy()
        return 1
    return run_gui(install_dir)


if __name__ == "__main__":
    sys.exit(main())

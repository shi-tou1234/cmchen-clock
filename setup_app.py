"""DesktopClock Windows 安装向导（PySide6）。

用法：
    DesktopClock-Setup.exe          图形安装向导（欢迎 → 选项 → 进度 → 完成）
    DesktopClock-Setup.exe --silent 静默安装（桌面+开始菜单快捷方式，装完不运行）
    DesktopClock-Setup.exe --silent --dir <目录> [--no-desktop] [--no-start-menu] [--run]

退出码：0 成功；1 失败；2 参数错误。静默模式的日志写在 %TEMP%\\DesktopClock-Setup.log。
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QVBoxLayout, QWizard, QWizardPage,
                               QWidget)

import installer_common as ic

LOG_NAME = "DesktopClock-Setup.log"


def icon_path():
    """窗口图标：优先安装包 payload 内的 icon.ico，源码运行回退项目 assets/。"""
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


# ---------------------------------------------------------------- 运行中时钟处理


def close_running_gui(parent):
    """GUI 版「关闭运行中的时钟」：询问 → 优雅关闭 → 必要时强制结束。"""
    pids = ic.app_pids()
    if not pids:
        return True
    answer = QMessageBox.question(
        parent, "关闭运行中的时钟",
        "检测到 DesktopClock 正在运行。\n是否关闭它继续安装？",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
    if answer != QMessageBox.Yes:
        return False
    if ic.request_app_close(pids):
        return True
    answer = QMessageBox.question(
        parent, "强制结束",
        "时钟仍未退出，可能还有未保存的界面状态。\n是否强制结束它？",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if answer != QMessageBox.Yes:
        return False
    ic.terminate_pids(ic.app_pids())
    return not ic.app_pids()


def close_running_silent():
    """静默版：优雅关闭，失败则强制结束（非交互场景不允许卡住）。"""
    pids = ic.app_pids()
    if not pids:
        return True
    write_log(f"closing running app pids={pids}")
    if ic.request_app_close(pids):
        return True
    ic.terminate_pids(ic.app_pids())
    return not ic.app_pids()


# ---------------------------------------------------------------- 向导页面


class IntroPage(QWizardPage):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setTitle("欢迎安装 DesktopClock 桌面时钟")
        self.setSubTitle(f"版本 {ic.bundled_app_version()}　发布者 {ic.PUBLISHER}")
        layout = QVBoxLayout(self)
        icon_label = QLabel()
        pixmap = QPixmap(str(icon_path()))
        if not pixmap.isNull():
            icon_label.setPixmap(pixmap.scaled(
                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        layout.addWidget(QLabel(
            "一款轻量的桌面时钟：像壁纸一样常驻桌面，被打开的窗口自动遮挡。\n"
            "本安装程序会把时钟安装到当前用户目录（不需要管理员权限），\n"
            "并在桌面和开始菜单创建快捷方式。"))
        self._upgrade_label = QLabel()
        self._upgrade_label.setStyleSheet("color: #B8860B;")
        layout.addWidget(self._upgrade_label)
        layout.addStretch(1)

    def initializePage(self):
        entry = ic.read_uninstall_entry()
        if entry and entry["install_dir"].exists():
            self._upgrade_label.setText(
                f"检测到已安装的版本 {entry['display_version'] or '未知'}，"
                f"将继续升级（个人设置会保留）。")
        else:
            self._upgrade_label.setText("")


class OptionsPage(QWizardPage):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self.setTitle("安装选项")
        self.setSubTitle("选择安装位置和要创建的快捷方式。")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("安装位置："))
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit(state["options"]["install_dir"])
        dir_row.addWidget(self._dir_edit)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        dir_row.addWidget(browse)
        layout.addLayout(dir_row)

        self._desktop_cb = QCheckBox("创建桌面快捷方式")
        self._desktop_cb.setChecked(state["options"]["desktop"])
        layout.addWidget(self._desktop_cb)

        self._start_menu_cb = QCheckBox("创建开始菜单快捷方式")
        self._start_menu_cb.setChecked(state["options"]["start_menu"])
        layout.addWidget(self._start_menu_cb)

        self._run_cb = QCheckBox("安装完成后立即运行")
        self._run_cb.setChecked(state["options"]["run_after"])
        layout.addWidget(self._run_cb)

        self._hint = QLabel()
        self._hint.setStyleSheet("color: #B22222;")
        layout.addWidget(self._hint)
        layout.addStretch(1)

    def initializePage(self):
        self._hint.setText("")

    def _browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "选择安装目录", self._dir_edit.text())
        if chosen:
            self._dir_edit.setText(chosen)

    def validatePage(self):
        raw = self._dir_edit.text().strip()
        if not raw:
            self._hint.setText("请选择安装目录。")
            return False
        target = Path(raw)
        if not target.is_absolute():
            self._hint.setText("安装目录必须是绝对路径。")
            return False
        if target.exists() and not target.is_dir():
            self._hint.setText("该路径已存在且不是文件夹。")
            return False
        if '"' in raw:
            self._hint.setText("安装路径不能包含引号。")
            return False
        self._state["options"]["install_dir"] = str(target)
        self._state["options"]["desktop"] = self._desktop_cb.isChecked()
        self._state["options"]["start_menu"] = self._start_menu_cb.isChecked()
        self._state["options"]["run_after"] = self._run_cb.isChecked()
        return True


class ProgressPage(QWizardPage):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self.setTitle("正在安装")
        self.setSubTitle("请稍候，通常只需几秒钟。")
        layout = QVBoxLayout(self)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar)
        self._status = QLabel("准备安装…")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._failed = False

    def initializePage(self):
        wizard = self.wizard()
        wizard.button(QWizard.NextButton).setEnabled(False)
        wizard.button(QWizard.BackButton).setEnabled(False)
        wizard.button(QWizard.CancelButton).setEnabled(False)
        self._failed = False
        self._bar.setValue(0)
        self._status.setText("正在安装…")

        options = dict(self._state["options"])
        options["run_after"] = False  # 完成页再启动，进度页保持可交互
        try:
            result = ic.install(
                options, progress=self._on_progress,
                resolve_running=lambda: close_running_gui(self))
        except ic.AppRunningError as exc:
            self._fail(str(exc))
            return
        except ic.InstallError as exc:
            self._fail(str(exc))
            return
        except OSError as exc:
            self._fail(f"安装失败：{exc}")
            return

        self._state["result"] = result
        write_log(f"install ok {result}")
        self._bar.setValue(100)
        self._status.setText("安装完成。")
        wizard.button(QWizard.NextButton).setEnabled(True)
        wizard.button(QWizard.CancelButton).setEnabled(True)

    def _on_progress(self, done, total, text):
        self._bar.setValue(int(done * 100 / max(1, total)))
        self._status.setText(text)
        QApplication.processEvents()

    def _fail(self, message):
        self._failed = True
        self._status.setText(message)
        write_log(f"install failed {message}")
        QMessageBox.critical(self, "安装失败", message)
        wizard = self.wizard()
        wizard.button(QWizard.BackButton).setEnabled(True)
        wizard.button(QWizard.CancelButton).setEnabled(True)

    def isComplete(self):
        return not self._failed and self._state.get("result") is not None

    def cleanupPage(self):
        self._state["result"] = None


class FinishPage(QWizardPage):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self.setTitle("安装完成")
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)
        self._run_hint = QLabel()
        layout.addWidget(self._run_hint)
        layout.addStretch(1)

    def initializePage(self):
        self.setFinalPage(True)
        self.wizard().button(QWizard.NextButton).setText("完成")
        self.wizard().button(QWizard.FinishButton).setText("完成")
        result = self._state.get("result") or {}
        lines = [
            f"安装位置：{result.get('install_dir', '')}",
            "快捷方式：" + ("、".join(
                "桌面" if "Desktop" in p else "开始菜单"
                for p in result.get("shortcuts", [])) or "未选择"),
            "",
            "之后可以在系统「设置 → 应用 → 已安装的应用」里找到 "
            "DesktopClock 并随时卸载；个人设置不受影响。",
        ]
        self._summary.setText("\n".join(lines))
        self._run_hint.setText(
            "时钟即将启动，可以用右键菜单随时调整显示方式与位置。"
            if self._state["options"].get("run_after") else "")


def build_wizard(options):
    """组装四页向导，返回 (wizard, state)。"""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(icon_path())))
    state = {"options": dict(options), "result": None}
    wizard = QWizard()
    wizard.setWindowTitle("DesktopClock 安装程序")
    wizard.setWindowIcon(QIcon(str(icon_path())))
    wizard.setWizardStyle(QWizard.ModernStyle)
    pixmap = QPixmap(str(icon_path()))
    if not pixmap.isNull():
        wizard.setPixmap(QWizard.LogoPixmap,
                         pixmap.scaled(48, 48, Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))
    wizard.addPage(IntroPage(state, wizard))
    options_id = wizard.addPage(OptionsPage(state, wizard))
    wizard.addPage(ProgressPage(state, wizard))
    wizard.addPage(FinishPage(state, wizard))
    wizard.setButtonText(QWizard.CancelButton, "取消")
    wizard.setButtonText(QWizard.BackButton, "上一步")
    wizard.setButtonText(QWizard.NextButton, "下一步")
    wizard.setButtonText(QWizard.FinishButton, "完成")

    def _sync_next_text(page_id):
        # 选项页的「下一步」变「安装」，提示用户点击即开始装
        wizard.button(QWizard.NextButton).setText(
            "安装" if page_id == options_id else "下一步")

    wizard.currentIdChanged.connect(_sync_next_text)
    return wizard, state


def run_gui(options):
    wizard, state = build_wizard(options)

    accepted = wizard.exec() == QWizard.Accepted
    if accepted and state["options"].get("run_after"):
        result = state.get("result") or {}
        try:
            ic.launch_app(result.get("install_dir") or state["options"]["install_dir"])
        except ic.InstallError as exc:
            write_log(f"launch failed {exc}")
    return 0 if accepted else 1


# ---------------------------------------------------------------- 静默模式


def silent_install(options):
    write_log(f"silent install start options={options}")
    try:
        result = ic.install(
            options,
            progress=lambda done, total, text: write_log(f"[{done}/{total}] {text}"),
            resolve_running=close_running_silent)
    except Exception as exc:  # 静默模式只能靠日志排障
        write_log(f"silent install failed {exc!r}")
        return 1
    write_log(f"silent install ok {result}")
    return 0


# ---------------------------------------------------------------- 入口


USAGE = __doc__.strip()


def parse_args(argv):
    options = {
        "install_dir": str(ic.default_install_dir()),
        "desktop": True,
        "start_menu": True,
        "run_after": False,
    }
    silent = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--silent":
            silent = True
        elif arg == "--dir":
            index += 1
            if index >= len(argv):
                raise SystemExit(f"--dir 缺少参数\n\n{USAGE}")
            options["install_dir"] = argv[index]
        elif arg == "--no-desktop":
            options["desktop"] = False
        elif arg == "--no-start-menu":
            options["start_menu"] = False
        elif arg == "--run":
            options["run_after"] = True
        elif arg in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        else:
            raise SystemExit(f"未知参数 {arg}\n\n{USAGE}")
        index += 1
    return silent, options


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    silent, options = parse_args(argv)
    if silent:
        return silent_install(options)
    return run_gui(options)


if __name__ == "__main__":
    sys.exit(main())

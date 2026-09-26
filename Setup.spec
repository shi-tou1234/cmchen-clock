# -*- mode: python ; coding: utf-8 -*-
"""DesktopClock 安装向导 spec：onefile，内置 payload（程序 + 卸载器 + 图标）。

依赖构建顺序：先出 dist/DesktopClock.exe 与 dist/uninstall.exe，再打本包。
用法：.venv/Scripts/pyinstaller.exe --noconfirm Setup.spec
"""

from pathlib import Path

ROOT = Path(SPECPATH)
block_cipher = None

a = Analysis(
    [str(ROOT / "setup_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "dist" / "DesktopClock.exe"), "payload"),
        (str(ROOT / "dist" / "uninstall.exe"), "payload"),
        (str(ROOT / "assets" / "icon.ico"), "payload"),
        (str(ROOT / "app_version.py"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DesktopClock-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "assets" / "icon.ico")],
)

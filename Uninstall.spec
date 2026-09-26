# -*- mode: python ; coding: utf-8 -*-
"""DesktopClock 卸载程序 spec：onefile，打进安装目录当 uninstall.exe 用。

用法：.venv/Scripts/pyinstaller.exe --noconfirm Uninstall.spec
"""

from pathlib import Path

ROOT = Path(SPECPATH)
block_cipher = None

a = Analysis(
    [str(ROOT / "uninstall_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
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
    name="uninstall",
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

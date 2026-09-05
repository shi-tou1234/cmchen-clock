#!/usr/bin/env bash
# DesktopClock macOS/Linux 打包脚本（脚本就绪，未在真机验证）
set -euo pipefail
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install PySide6-Essentials pyinstaller
.venv/bin/pyinstaller --onefile --windowed --name DesktopClock main.py
echo "产物: dist/DesktopClock.app 内可执行文件 / dist/DesktopClock"
.venv/bin/python -m pytest tests -q

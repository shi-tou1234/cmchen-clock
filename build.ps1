# DesktopClock Windows 打包脚本（实测可用）
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install PySide6-Essentials pyinstaller
.venv\Scripts\pyinstaller.exe --onefile --windowed --name DesktopClock main.py
Write-Host "产物: dist\DesktopClock.exe"
.venv\Scripts\python.exe -m pytest tests -q

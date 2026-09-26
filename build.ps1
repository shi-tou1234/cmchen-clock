# DesktopClock Windows 打包脚本（实测可用）
# 顺序：应用 exe → 卸载器 → 安装包（Setup.spec 会内嵌前两个产物，顺序不能反）
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install PySide6-Essentials pyinstaller

# 旧实例占着 exe 会构建失败（WinError 5），先结束
taskkill /F /IM DesktopClock.exe 2>$null

.venv\Scripts\pyinstaller.exe --noconfirm DesktopClock.spec
.venv\Scripts\pyinstaller.exe --noconfirm Uninstall.spec
.venv\Scripts\pyinstaller.exe --noconfirm Setup.spec

Write-Host "产物: dist\DesktopClock.exe / dist\uninstall.exe / dist\DesktopClock-Setup.exe"
.venv\Scripts\python.exe -m pytest tests -q

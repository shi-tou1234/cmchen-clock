# DesktopClock 桌面时钟

一款轻量的桌面时钟：像壁纸一样常驻桌面、被打开的窗口自动遮挡，也可以置顶或作为普通窗口使用。字体、字号、颜色、透明度全部可自定义，带系统托盘，Windows / macOS / Linux 通吃。

![screenshot](docs/screenshot.png)

## 功能特性

- **三种显示方式**（右键或托盘菜单随时切换，默认「固定在桌面」）：

  | 显示方式 | 行为 | 任务栏 |
  |---|---|---|
  | 固定在桌面 | 像壁纸一样贴在桌面，打开任何软件都会盖住它；锁定拖动防误碰，仍可右键操作 | 不显示 |
  | 浮在其他窗口上方 | 始终置顶，不会被任何窗口遮挡 | 显示 |
  | 普通窗口 | 普通软件行为，可被其他窗口盖住 | 显示 |

- **屏幕位置**：右键/托盘菜单「屏幕位置」一键摆放——上方/中间/下方 × 靠左/居中/靠右 九宫格预设，设置面板还能输入精确 X/Y 坐标
- **换屏/改分辨率自动纠偏**：识别到显示器尺寸变化（外接屏插拔、分辨率/缩放调整、换回笔记本内置屏）后 0.3 秒内自动切回合适的预设位置，时钟不再偏移到屏外或错位。即使两块屏幕分辨率完全相同也能纠偏：按预设逐像素校验实际位置，并侦测系统挪窗、跨屏字号/DPI 尺寸变化，纠偏后还会自校验至多 3 轮等系统落定（v1.0.4 修复电脑屏→显示器方向的漏判）
- **锁定位置**：任何显示方式下都可勾选，防止误拖动
- **字体自定义**：系统字体下拉选择，或从 ttf / otf / ttc 字体文件加载；设置面板内**实时预览**显示效果
- **字号 8–200、任意颜色、不透明度 10%–100%**
- **显示日期、显示秒、12/24 小时制**均可开关
- **系统托盘常驻**：左键单击隐藏/唤回时钟，右键菜单可完成全部操作
- **开机自启动**：设置面板或右键菜单勾选即可（Windows 写用户注册表 Run 键 / macOS LaunchAgents / Linux XDG Autostart，均为当前用户作用域，可随时取消）
- **设置与窗口位置自动记住**（存于 `~/.desktop-clock/settings.json`，连同摆放时的屏幕可用区与预设，换屏后据此自动纠偏）
- **Windows 安装版**：Release 提供 `DesktopClock-Setup.exe` 安装包——装到当前用户目录（免管理员），自动创建桌面/开始菜单快捷方式，在系统「已安装的应用」里可见并可随时卸载（见 [安装为正式软件](#安装为正式软件windows)）
- 每秒整点对齐刷新，几乎不占 CPU；打包后单文件约 36 MB

## 使用方法

### 启动

双击 `dist/DesktopClock.exe`（打包版），或：

```bash
python main.py
```

首次运行时钟出现在桌面中央，拖到你喜欢的位置即可（位置会记住）。

### 日常操作

| 操作 | 方式 |
|---|---|
| 移动位置 | 按住时钟直接拖；或右键 → **屏幕位置** 九宫格一键摆放；设置面板可输入精确 X/Y 坐标（桌面模式或勾选「锁定位置」时禁用拖动） |
| 换显示器/改分辨率 | 无需操作：0.3 秒内自动切回合适的预设位置（见「换屏/改分辨率自动纠偏」） |
| 打开设置 | 时钟上右键 → **设置…** |
| 切换显示方式 | 右键 → **显示方式** 子菜单，或托盘右键菜单 |
| 锁定/解锁位置 | 右键 → **锁定位置** |
| 开机自启动 | 右键 → **开机自启动**（或设置面板勾选） |
| 临时隐藏/唤回 | 左键单击托盘图标，或菜单 → **隐藏时钟** |
| 退出 | 右键/托盘菜单 → **退出** |

### 设置面板

- **显示方式**：三选一（同上表）
- **锁定位置**：等价于右键菜单里的勾选项
- **屏幕位置**：下拉选「上方/中间/下方 × 靠左/居中/靠右」九宫格预设（按当前屏幕与时钟尺寸算出坐标），或直接在 X / Y 输入框填精确坐标（手动改坐标会自动切回「自定义」）
- **字体**：系统字体下拉；「从字体文件加载…」支持 ttf / otf / ttc
- **字号**：8–200
- **颜色**：任意颜色；预览区即时显示效果
- **显示日期 / 显示秒 / 24 小时制**：即时生效
- **开机自启动**：登录后自动运行（等价于右键菜单里的勾选项）
- **不透明度**：10%–100%

点「确定」立即生效并保存。设置文件在 `~/.desktop-clock/settings.json`，删掉它即可恢复全部默认值。

### 开机自启（可选）

在时钟上右键勾选 **开机自启动**（或设置面板勾选）即可，再次点击取消。
实现方式：Windows 用户注册表 Run 键 / macOS `~/Library/LaunchAgents` / Linux XDG Autostart，只影响当前用户，删除设置项即等于关闭。

手动方式（备用）：Windows `Win+R` → `shell:startup` 放入快捷方式；macOS 系统设置 → 登录项；Linux 桌面环境自启动设置。

## 安装为正式软件（Windows）

Release 页面提供 `DesktopClock-Setup.exe` 安装包（约 90 MB，内含单文件时钟程序和卸载器）：

- **双击安装**：图形向导四步（欢迎 → 选项 → 进度 → 完成），可选择安装位置、是否创建桌面/开始菜单快捷方式、是否装完即运行
- **免管理员**：默认装到当前用户目录 `%LOCALAPPDATA%\Programs\DesktopClock`，不需要 UAC 提权
- **桌面快捷方式**：安装后桌面出现「DesktopClock」图标，双击即启动
- **系统软件列表**：安装后可在 **设置 → 应用 → 已安装的应用** 看到「DesktopClock 桌面时钟」（带版本号、发布者、占用体积）
- **随时卸载**：在「已安装的应用」里点卸载，或直接运行安装目录里的 `uninstall.exe`。程序文件、快捷方式、注册表条目全部清干净；个人设置默认保留，卸载界面可勾选一并删除
- **升级覆盖**：直接运行新版本安装包即可，自动覆盖旧文件，个人设置保留
- **静默安装**（脚本/域部署用）：`DesktopClock-Setup.exe --silent [--dir <目录>] [--no-desktop] [--no-start-menu] [--run]`，日志写在 `%TEMP%\DesktopClock-Setup.log`

不想安装也想用：直接下载 `DesktopClock-windows.exe` 单文件，解压即用（没有快捷方式和卸载入口，删文件即卸载）。

## 运行环境

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11、macOS 12+、Linux（X11 桌面；Wayland 下「固定在桌面」受系统限制，自动降级为普通窗口行为） |
| Python | 3.10 – 3.13 |
| 运行时依赖 | 仅 `PySide6-Essentials`（Qt 官方 Python 绑定核心包） |
| 磁盘 | 源码 < 1 MB；虚拟环境约 400 MB；打包单文件 exe 约 36 MB |
| 内存 | 运行时约 60 MB |

> **Windows 已知坑**：把 PySide6 装进系统 Python 的用户目录会因「长路径支持未开启」而安装失败（Qt 内部有超过 260 字符的路径）。解决方式就是本项目默认的做法——使用项目内虚拟环境（路径短），无需修改系统设置。

## 从源码运行

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 安装依赖（Windows 用 .venv\Scripts\python.exe，macOS/Linux 用 .venv/bin/python）
.venv\Scripts\python.exe -m pip install PySide6-Essentials

# 3. 运行
.venv\Scripts\python.exe main.py
```

## 打包发行

```bash
# Windows 应用（产出 dist/DesktopClock.exe，带应用图标）
.venv\Scripts\pyinstaller.exe --noconfirm DesktopClock.spec

# Windows 卸载器 + 安装包（会内嵌前两步产物，顺序不能反）
.venv\Scripts\pyinstaller.exe --noconfirm Uninstall.spec
.venv\Scripts\pyinstaller.exe --noconfirm Setup.spec

# macOS / Linux
.venv/bin/pyinstaller --onefile --windowed --name DesktopClock --icon assets/icon.ico --add-data "assets:assets" main.py
```

或直接使用脚本：`build.ps1`（Windows，一条命令出全部三个 exe）、`build.sh`（macOS/Linux）。

### Release 自动发布

仓库已配置 GitHub Actions（[.github/workflows/release.yml](.github/workflows/release.yml)），照搬 blog-starter 的发布模式：

- **打 tag 自动发布**：`git tag v1.0.0 && git push origin v1.0.0` → 自动在三个平台跑测试、构建、自检，并把安装包挂到 Releases 页
- **手动验证构建**：Actions 页选「Desktop Release」→ Run workflow（只出构建产物，不发布）
- 产物：`DesktopClock-Setup.exe`（Windows 安装包）、`DesktopClock-windows.exe`（Windows 单文件）、`DesktopClock-macos.zip`（未签名）、`DesktopClock-linux.tar.gz`

构建依赖见 `requirements.txt`（PySide6-Essentials / pyinstaller / pytest）。

图标由 `scripts/gen_icon.py` 从 `assets/时钟图标.png` 生成（16/24/32/48/64/128 七尺寸 32bpp DIB + 256px PNG entry，纯 Python 装配 ICO，无额外依赖）。想换图标：替换 PNG 后重跑 `python scripts/gen_icon.py`，回读校验通过会输出 `ICO_OK`。

## 运行测试

```bash
.venv\Scripts\python.exe -m pytest tests -q    # Windows
.venv/bin/python -m pytest tests -q            # macOS / Linux
```

136 条测试覆盖时间/日期格式化、设置迁移与安全读写、字体加载、三种显示方式窗口标志、拖动锁、屏幕位置九宫格与坐标持久化、换屏/改分辨率自动纠偏与预设反推、同可用区换屏漏判回归、系统挪窗侦测、拖动落点提交、开机自启动命令构造、设置面板预览、ICO 装配与回读、安装器路径推导/版本解析/安装清单/快捷方式创建与回读、install/uninstall 主流程（monkeypatch 沙箱，不碰真实系统）等。

## 自检

```bash
python main.py --selftest
```

三种显示方式各渲染一帧并校验图标资源，输出 `SELFTEST_OK_*` 与 `ICON_OK`，退出码 0 即健康。

## 项目结构

```
app_version.py      应用版本号（安装器与 Release 共用的唯一来源）
clock_core.py      时间/日期文本格式化（纯函数）
settings.py        设置读写（JSON、缺省回退、旧配置迁移、防路径穿越）
fonts.py           系统字体枚举、字体文件加载
autostart.py       开机自启动（注册表 Run 键 / LaunchAgents / XDG Autostart）
main.py            主程序（窗口、三显示方式、九宫格屏幕位置、换屏自动纠偏＋fit.log 诊断日志、托盘、设置面板、selftest）
installer_common.py 安装器共享逻辑（注册表卸载条目、快捷方式、安装清单、进程侦测，纯标准库）
setup_app.py       Windows 安装向导（PySide6 四页向导 + --silent 静默安装）
uninstall_app.py   Windows 卸载程序（tkinter 界面 + --silent 静默卸载）
tests/             pytest 测试（136 条）
scripts/gen_icon.py        图标生成（PNG → 多尺寸 ICO 装配）
scripts/make_screenshot.py 生成 README 截图
assets/时钟图标.png        图标源图
assets/icon.ico    应用图标（多尺寸）
DesktopClock.spec / Setup.spec / Uninstall.spec   PyInstaller 打包配置
build.ps1 / build.sh       打包脚本
```

## 常见问题

**时钟怎么被游戏/软件挡住了？**
默认就是「固定在桌面」模式——它设计上就像壁纸，任何窗口都会盖在它上面。想让它一直在最上面：右键 → 显示方式 → 浮在其他窗口上方。

**托盘里怎么退出？**
右键托盘图标 → 退出。托盘模式下点窗口关闭键只是隐藏到托盘，不会退出。

**字体列表里没有我想要的字体？**
用「从字体文件加载…」直接选 ttf/otf 文件，无需安装到系统。

**想恢复默认设置？**
删除 `~/.desktop-clock/settings.json` 后重启程序。

**怎么卸载？**
用安装版：设置 → 应用 → 已安装的应用 →「DesktopClock 桌面时钟」→ 卸载；或运行安装目录里的 `uninstall.exe`。程序文件、快捷方式、注册表条目都会清干净，个人设置默认保留（卸载界面可勾选一并删除）。用的单文件版：直接删掉 exe 即可。

**换屏（电脑屏幕 ↔ 外接显示器）后时钟偏移了？**
v1.0.4 起会在 0.3 秒内自动纠回预设位置，无需手动处理；右键 → 屏幕位置 也可随时手动摆放。若换了新版仍发现偏移，把 `~/.desktop-clock/fit.log`（位置核对诊断日志，记录每次换屏的触发源、各屏幕几何与判定结果）发给维护者即可定位。

## 更新记录

### v1.0.5（2026-09-26）

- **新增 Windows 安装版**：Release 提供 `DesktopClock-Setup.exe` 安装包——PySide6 四页安装向导（位置/快捷方式选项/进度/完成），默认装到当前用户目录（免管理员），桌面与开始菜单自动创建快捷方式，系统「已安装的应用」列表可见（版本号/发布者/体积），随时可卸载；程序文件、快捷方式、注册表条目全部清干净，个人设置默认保留。附带 `--silent` 静默安装/卸载（可脚本化部署）。
- **新图标**：应用图标改用 `assets/时钟图标.png` 源图生成（16/24/32/48/64/128 七尺寸 + 256 PNG entry），exe、快捷方式、安装包、卸载器统一使用。
- 安装器为零第三方依赖的标准库实现（ctypes 直调 IShellLinkW 建快捷方式、winreg 写卸载条目、Toolhelp 侦测运行中进程），新增 40 条测试，总数 96 → 136。

### v1.0.4（2026-09-23）

- **修复**：从电脑屏幕切到外接显示器时时钟仍可能偏移的问题——两块屏幕可用区恰好相同时，旧逻辑对比锚点发现不了变化；换屏瞬间的系统挪窗、跨屏字号/DPI 尺寸变化会让实际位置偏离预设却得不到纠正。现在有三层防护：按预设逐像素校验实际位置、侦测系统挪窗（自定义位置直接退回已保存意图）与 resize、纠偏后自校验至多 3 轮等系统落定。
- **新增**：位置核对诊断日志 `~/.desktop-clock/fit.log`，排查换屏问题直接看它。
- 测试 90 → 96 条（含报障场景回归测试）。

### v1.0.3（2026-09-23）

- **新功能**：换屏/改分辨率自动纠偏——识别显示器尺寸变化后 0.3 秒内自动切回合适的预设位置；自定义位置按旧屏幕可用区反推最贴近的九宫格预设。
- 设置新增 `pos_preset`（吸附的预设）与 `pos_anchor`（摆放时的屏幕可用区）字段，旧配置文件自动兼容。

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

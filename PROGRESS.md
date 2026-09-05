# PROGRESS

## 二轮收口（2026-09-05 晚）
- 交付：三种显示方式（floating/normal/desktop，默认 desktop）＋锁定位置＋设置面板实时预览＋托盘常驻＋任务栏存在感＋应用图标（scripts/gen_icon.py 可再生）＋exe 重建。
- 验收：53 passed skipped=0；selftest 三模式 SELFTEST_OK_*＋ICON_OK rc=0；exe selftest rc=0；gen_icon 回读 (0,1,4) [16,32,48,0]。
- 真机联验抓出并修复 3 个 bug：①QMenu(QSystemTrayIcon) 非法构造（selftest 盲区，真机即崩）②_refresh_tray_menu 构造期访问未赋值的 self.tray ③托盘菜单勾选状态失真（引用被覆盖）→ 均修复并复测全绿。
- 收尾：README 重写＋MIT LICENSE＋git 提交推送 github.com/shi-tou1234/cmchen-clock（领导已授权）。

## 二轮开工回执（2026-09-05 晚）
- 目标：二轮任务书四件套（三种显示方式/图标/锁定位置/字体预览）＋领导追加「最小化在任务栏、做成真正的电脑软件」→ 实现为：normal/floating 模式带任务栏条目，desktop 模式保持桌面挂件不进任务栏，全程配系统托盘图标（显示/隐藏、显示方式、锁定、设置、退出）；随后查 bug、README/MIT、提交 github.com/shi-tou1234/cmchen-clock（领导已明确授权）。
- 顺序：settings 层 → GUI 三模式+预览+托盘 → 图标+打包 → 验收 → README/LICENSE → git 提交。
- 最大风险：desktop 模式（WindowStaysOnBottomHint）与任务栏存在感（Qt.Tool↔Qt.Window 切换需 re-show）交互；托盘隐藏时钟时 setQuitOnLastWindowClosed(False) 防误退出。
- 基线复跑：31 passed / SELFTEST_OK 378 166 rc=0。

## 首轮记录（2026-09-05）
- 理解的目标：PySide6 桌面时钟（时间/秒/日期、字体/字号/颜色自定义、无边框半透明可拖动、设置持久化），任务 0 三步已实测通过（venv 就绪，QT_SMOKE_OK 6.11.2）。
- 顺序：任务 1 纯逻辑+测试 → 任务 2 GUI+selftest → 任务 3 打包+README。
- 最大风险：--windowed exe 的 --selftest 退出码在无控制台下是否正确回传（任务 3 首验点）；offscreen 下字体枚举为 0，selftest 与测试都不断言字体数量。
- 状态：任务 3 完成。全部硬指标实测通过：`main.py --selftest` SELFTEST_OK 366 165/RC=0；pytest 31 passed skipped=0；`dist/DesktopClock.exe --selftest` RC=0（36MB，--windowed 下退出码正确回传，开工回执里的最大风险未发生）。修复一处自查发现的配色小 bug（日期标签透明度丢失）后重建 exe 并复测全绿。交付物：clock_core.py / settings.py / fonts.py / main.py / tests/ / README.md / build.ps1 / build.sh / dist/DesktopClock.exe。BLOCKED.md：无。任务全部完成。

"""生成 README 用截图：时钟渲染帧合成到深色底上。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from main import ClockWindow
from settings import merged_settings


def main():
    app = QApplication(sys.argv)
    window = ClockWindow(merged_settings({}), enable_tray=False)
    window.show()
    app.processEvents()
    frame = window.grab()
    canvas = QPixmap(frame.size())
    canvas.fill(QColor("#1e2030"))
    painter = QPainter(canvas)
    painter.drawPixmap(0, 0, frame)
    painter.end()
    canvas.save("docs/screenshot.png", "PNG")
    print("SCREENSHOT_OK", canvas.width(), canvas.height())
    window.hide()


if __name__ == "__main__":
    main()

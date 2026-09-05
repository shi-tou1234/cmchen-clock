"""生成应用图标 assets/icon.ico（多尺寸：16/32/48 用 DIB，256 用 PNG entry）。

图标设计（极简扁平）：
- 深蓝→紫渐变圆角方块底
- 白色表盘圆环 + 12/3/6/9 短刻度
- 指针指 10:08（钟表广告经典时刻），白针圆头
- 橙色秒针点缀，中心白点收尾

用法：python scripts/gen_icon.py   （退出码 0 即成功，含回读校验）
"""

import math
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen, QBrush
from PySide6.QtWidgets import QApplication

SIZES = [16, 32, 48, 256]
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"


def render_icon(size):
    """按矢量逻辑绘制一枚 size×size 的图标，返回 QImage。"""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        s = size / 256.0

        # 底：圆角方块渐变
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0.0, QColor("#2B4C7E"))
        grad.setColorAt(1.0, QColor("#563C8C"))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, size, size), 48 * s, 48 * s)

        # 顶部柔和高光
        highlight = QLinearGradient(0, 0, 0, size * 0.55)
        highlight.setColorAt(0.0, QColor(255, 255, 255, 46))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(highlight))
        p.drawRoundedRect(QRectF(0, 0, size, size * 0.55), 48 * s, 48 * s)

        # 表盘圆环
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("white"), 9 * s))
        p.drawEllipse(QRectF(52 * s, 52 * s, 152 * s, 152 * s))

        # 12/3/6/9 刻度
        p.setPen(QPen(QColor("white"), 6 * s, Qt.SolidLine, Qt.RoundCap))
        cx = cy = 128 * s
        r_outer, r_inner = 76 * s, 62 * s
        for angle in (0, 90, 180, 270):
            rad = math.radians(angle)
            x1, y1 = cx + r_inner * math.sin(rad), cy - r_inner * math.cos(rad)
            x2, y2 = cx + r_outer * math.sin(rad), cy - r_outer * math.cos(rad)
            p.drawLine(QPoint(round(x1), round(y1)), QPoint(round(x2), round(y2)))

        # 指针：10:08 → 时针 304°、分针 48°、秒针 ~24°（橙）
        def hand(angle_deg, length, width, color):
            rad = math.radians(angle_deg)
            p.setPen(QPen(color, width * s, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(
                QPoint(round(cx), round(cy)),
                QPoint(round(cx + length * s * math.sin(rad)),
                       round(cy - length * s * math.cos(rad))))

        hand(304, 40, 11, QColor("white"))
        hand(48, 58, 9, QColor("white"))
        hand(24, 62, 4, QColor("#FF8A3C"))

        # 中心圆点
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(cx - 8 * s, cy - 8 * s, 16 * s, 16 * s))
    finally:
        p.end()
    return img


def png_bytes(img):
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def dib_bytes(img):
    """32bpp DIB：BITMAPINFOHEADER + 倒序 BGRA + 全 0 AND 掩码（走 alpha 通道）。"""
    w, h = img.width(), img.height()
    argb = img.convertToFormat(QImage.Format_ARGB32)
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            px = argb.pixel(x, y)
            xor += bytes((px & 0xFF, (px >> 8) & 0xFF, (px >> 16) & 0xFF, (px >> 24) & 0xFF))
    and_stride = ((w + 31) // 32) * 4
    and_mask = bytes(and_stride * h)
    header = struct.pack(
        "<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + bytes(xor) + and_mask


def assemble_ico(path):
    blobs = []
    for size in SIZES:
        img = render_icon(size)
        blobs.append(png_bytes(img) if size >= 256 else dib_bytes(img))
    out = struct.pack("<HHH", 0, 1, len(SIZES))
    offset = 6 + 16 * len(SIZES)
    for size, blob in zip(SIZES, blobs):
        out += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size, 0 if size >= 256 else size,
            0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    out += b"".join(blobs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return out


def verify(path):
    raw = path.read_bytes()
    reserved, ico_type, count = struct.unpack("<HHH", raw[:6])
    widths = [raw[6 + 16 * i] for i in range(count)]
    assert reserved == 0 and ico_type == 1, (reserved, ico_type)
    assert widths == [16, 32, 48, 0], widths  # 0 表示 256px
    return ico_type, widths


def main():
    _app = QApplication(sys.argv)  # 光栅绘制兜底环境
    data = assemble_ico(ICON_PATH)
    ico_type, widths = verify(ICON_PATH)
    print(f"ICO_OK {ICON_PATH} bytes={len(data)} type={ico_type} widths={widths}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

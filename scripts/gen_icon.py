"""生成应用图标 assets/icon.ico（源图：assets/时钟图标.png，多尺寸 16~256）。

设计约定（沿用既有 ICO 结构，改由 PNG 缩放而非矢量绘制）：
- 16/24/32/48/64/128px：32bpp DIB（biHeight=2 倍高 + 倒序 BGRA + 全 0 AND 掩码，走 alpha 通道）
- 256px：PNG entry（Vista+ 支持，画质无损）
- 源图固定文件名 + 项目根 resolve() + relative_to 包含校验后才读写（防路径穿越）

用法：python scripts/gen_icon.py   （退出码 0 即成功，含回读校验）
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_SOURCE_NAME = "时钟图标.png"
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def source_png_path():
    """固定文件名 + 项目根包含校验后的源图路径。"""
    root = PROJECT_ROOT.resolve()
    target = (root / "assets" / PNG_SOURCE_NAME).resolve()
    target.relative_to(root)
    return target


def render_icon(size, source):
    """把源图平滑缩放到 size×size（正方形居中裁剪，保持比例不变形）。"""
    src = source.convertToFormat(QImage.Format_ARGB32)
    if src.width() == src.height():
        scaled = src.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return scaled
    # 非正方形源图：按短边居中裁成正方形再缩放，避免拉伸
    side = min(src.width(), src.height())
    x = (src.width() - side) // 2
    y = (src.height() - side) // 2
    cropped = src.copy(x, y, side, side)
    return cropped.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


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


def assemble_ico(path, source):
    blobs = []
    for size in SIZES:
        img = render_icon(size, source)
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
    root = path.parent.resolve()
    path = path.resolve()
    path.relative_to(root)
    path.write_bytes(out)
    return out


def verify(path):
    raw = path.read_bytes()
    reserved, ico_type, count = struct.unpack("<HHH", raw[:6])
    widths = [raw[6 + 16 * i] for i in range(count)]
    assert reserved == 0 and ico_type == 1, (reserved, ico_type)
    assert widths == [16, 24, 32, 48, 64, 128, 0], widths  # 0 表示 256px
    return ico_type, widths


def main():
    source_path = source_png_path()
    if not source_path.is_file():
        print(f"PNG_MISSING {source_path}")
        return 1
    _app = QApplication(sys.argv)  # 光栅缩放兜底环境
    source = QImage(str(source_path))
    if source.isNull():
        print(f"PNG_BROKEN {source_path}")
        return 1
    data = assemble_ico(ICON_PATH, source)
    ico_type, widths = verify(ICON_PATH)
    print(f"ICO_OK {ICON_PATH} bytes={len(data)} type={ico_type} widths={widths} "
          f"src={source.width()}x{source.height()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

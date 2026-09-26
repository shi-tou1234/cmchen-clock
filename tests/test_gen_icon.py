"""scripts/gen_icon.py 的 ICO 组装/回读测试（合成图，不碰真实 assets/）。"""

import struct
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import gen_icon  # noqa: E402


def _solid_source(size=64, color="#2B4C7E"):
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(QColor(color))
    return image


class TestRender:
    def test_render_to_requested_size(self):
        assert gen_icon.render_icon(32, _solid_source()).size().width() == 32

    def test_render_crops_non_square_source(self):
        wide = QImage(80, 40, QImage.Format_ARGB32)
        wide.fill(QColor("red"))
        rendered = gen_icon.render_icon(16, wide)
        assert (rendered.width(), rendered.height()) == (16, 16)


class TestDibBytes:
    def test_header_fields(self):
        image = _solid_source(4)
        raw = gen_icon.dib_bytes(image)
        header = struct.unpack("<IiiHHIIiiII", raw[:40])
        size, width, height, planes, bitcount = header[0], header[1], header[2], \
            header[3], header[4]
        assert (size, width, height, planes, bitcount) == (40, 4, 8, 1, 32)
        # xor = 4×4×4 字节，and 掩码 stride=4 字节 ×4 行
        assert len(raw) == 40 + 64 + 16

    def test_png_bytes_are_real_png(self):
        raw = gen_icon.png_bytes(_solid_source(8))
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"


class TestAssembleAndVerify:
    def test_multi_size_ico_roundtrips(self, tmp_path):
        out = tmp_path / "icon.ico"
        data = gen_icon.assemble_ico(out, _solid_source(128))
        assert out.is_file() and out.read_bytes() == data
        ico_type, widths = gen_icon.verify(out)
        assert (ico_type, widths) == (1, [16, 24, 32, 48, 64, 128, 0])

    def test_verify_rejects_tampered_file(self, tmp_path):
        out = tmp_path / "icon.ico"
        gen_icon.assemble_ico(out, _solid_source(128))
        raw = bytearray(out.read_bytes())
        raw[4] = 2  # 破坏 ICONDIRENTRY 宽度表
        out.write_bytes(bytes(raw))
        with pytest.raises(AssertionError):
            gen_icon.verify(out)

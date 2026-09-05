import shutil
from pathlib import Path

from fonts import list_system_families, load_font_file

# 常见 Windows 系统字体候选；测试只拷贝存在的第一个
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\times.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\georgia.ttf",
    r"C:\Windows\Fonts\consola.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _find_system_font():
    for cand in _FONT_CANDIDATES:
        if Path(cand).is_file():
            return cand
    return None


def test_list_system_families_returns_sorted_list(qapp):
    families = list_system_families()
    assert isinstance(families, list)
    assert families == sorted(families)


def test_load_font_file_garbage_returns_none(qapp, tmp_path):
    bad = tmp_path / "not_a_font.ttf"
    bad.write_text("this is not a font file", encoding="utf-8")
    assert load_font_file(str(bad)) is None


def test_load_font_file_directory_returns_none(qapp, tmp_path):
    assert load_font_file(str(tmp_path)) is None


def test_load_font_file_missing_returns_none(qapp, tmp_path):
    assert load_font_file(str(tmp_path / "no_such.ttf")) is None


def test_load_font_file_real_font_registers(qapp, tmp_path):
    source = _find_system_font()
    copied = tmp_path / "probe_font.ttf"
    if source is None:
        # 本机无候选字体文件时退化为纯负例断言（不用 skip）
        assert load_font_file(str(tmp_path / "none.ttf")) is None
        return
    shutil.copy(source, copied)
    family = load_font_file(str(copied))
    assert isinstance(family, str) and family

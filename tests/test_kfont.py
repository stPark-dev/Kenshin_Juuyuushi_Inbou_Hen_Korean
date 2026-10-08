import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import kfont  # noqa: E402

BDF = """STARTFONT 2.1
FONT test
SIZE 14 75 75
FONTBOUNDINGBOX 14 14 0 0
CHARS 3
STARTCHAR uniAC00
ENCODING 44032
DWIDTH 14 0
BBX 2 2 0 0
BITMAP
C0
40
ENDCHAR
STARTCHAR wide
ENCODING 44033
DWIDTH 14 0
BBX 14 14 0 0
BITMAP
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
FFFC
ENDCHAR
STARTCHAR unencoded
ENCODING -1
BBX 1 1 0 0
BITMAP
80
ENDCHAR
ENDFONT
"""


@pytest.fixture
def bdf(tmp_path):
    p = tmp_path / "t.bdf"
    p.write_text(BDF)
    return kfont.load_bdf(p)


def test_load_skips_unencoded(bdf):
    assert set(bdf) == {"가", "각"}


def test_pixels_roundtrip_through_game_format(bdf):
    g = kfont.render(bdf["가"], box=(14, 14))
    assert len(g) == 32
    px = kfont.pixels(g)
    # 2x2 glyph, bottom-aligned in a 14px box centred in 16: rows 13-14, cols 1-2
    on = {(x, y) for y in range(16) for x in range(16) if px[y][x]}
    assert on == {(1, 13), (2, 13), (2, 14)}


def test_bit15_is_leftmost_and_rows_are_pair_swapped(bdf):
    g = kfont.render(bdf["가"], box=(14, 14))
    row13 = struct.unpack_from("<H", g, 2 * (13 ^ 1))[0]
    assert row13 == (1 << (15 - 1)) | (1 << (15 - 2))


def test_full_box_fits(bdf):
    px = kfont.pixels(kfont.render(bdf["각"], box=(14, 14)))
    assert sum(map(sum, px)) == 14 * 14
    assert not any(px[0]) and not any(px[15])


def test_glyph_larger_than_cell_raises(bdf):
    with pytest.raises(ValueError):
        kfont.render(bdf["각"], box=(18, 14))


GALMURI = Path(os.environ.get("KENSHIN_GALMURI14", Path(__file__).resolve().parents[2] / "galmuri" / "Galmuri14.bdf"))


@pytest.mark.skipif(not GALMURI.is_file(), reason="Galmuri14.bdf not available")
def test_galmuri14_all_hangul_render():
    font = kfont.load_bdf(GALMURI)
    box = kfont.hangul_box(font)
    assert box == (14, 14)
    for cp in range(0xAC00, 0xD7A4):
        g = kfont.render(font[chr(cp)], box)
        assert any(g), hex(cp)

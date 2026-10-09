import glob
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import iso  # noqa: E402
import mainprog  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)


def test_font_list_skips_line_breaks_and_stops_at_eof():
    data = "あい".encode("cp932") + b"\r\n" + "う".encode("cp932") + b"\x1a\0" + "え".encode("cp932")
    assert mainprog.font_list(data, 0) == [c.encode("cp932") for c in "あいう"]


@pytest.mark.skipif(not BIN, reason="disc image not available")
def test_menu_font_codes_from_disc():
    raw = Path(BIN).read_bytes()
    codes = mainprog.menu_font_codes(raw, iso.load(raw))
    assert "愛".encode("cp932") in codes and "炸".encode("cp932") in codes  # main, MAPCODE fonts
    assert not any(c[0] < 0x81 for c in codes)

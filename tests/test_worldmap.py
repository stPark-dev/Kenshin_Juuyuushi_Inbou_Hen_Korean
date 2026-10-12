import glob
import os
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bootlz  # noqa: E402
import grparc  # noqa: E402
import iso  # noqa: E402
import kfont  # noqa: E402
import worldmap  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
GALMURI = ROOT.parent / "galmuri" / "Galmuri11-Bold.bdf"


def _font():
    if not GALMURI.exists():
        pytest.skip("Galmuri not available")
    return kfont.load_bdf(GALMURI)


def test_pack_fits_without_overlap():
    widths = [118, 30, 64, 100, 20, 46, 128, 16]
    slots = worldmap.pack(widths)
    used = np.zeros((worldmap.SHEET_H, worldmap.SHEET_W), int)
    for w, (u, v, n) in zip(widths, slots):
        assert n * 16 >= w and u + n * 16 <= worldmap.SHEET_W and v % 16 == 0
        used[v:v + 16, u:u + n * 16] += 1
    assert used.max() == 1


def test_pack_refuses_overflow():
    with pytest.raises(ValueError):
        worldmap.pack([128] * 17)


def test_pack_refuses_label_wider_than_sheet():
    with pytest.raises(ValueError):
        worldmap.pack([129])


def test_label_is_outlined_white_text():
    font = _font()
    a = worldmap.label("아비코 숲", font)
    assert a.shape[0] == 16 and set(np.unique(a)) <= {0, worldmap.FILL, worldmap.EDGE}
    fill = a == worldmap.FILL
    assert fill.any()
    # every text pixel's neighbours are text or outline: the outline never has a gap
    pad = np.pad(a, 1)
    for y, x in zip(*np.nonzero(fill)):
        assert (pad[y:y + 3, x:x + 3] != 0).all()
    # and the outline is one pixel thick: every outline pixel touches text
    padf = np.pad(fill, 1)
    for y, x in zip(*np.nonzero(a == worldmap.EDGE)):
        assert padf[y:y + 3, x:x + 3].any()


@pytest.fixture(scope="module")
def system():
    if not BIN:
        pytest.skip("disc image not available")
    raw = Path(BIN).read_bytes()
    g = grparc.parse(iso.read_file(raw, iso.load(raw), "SYSTEM.GRP"))
    return g.get("AMAPDAT.BIN"), bootlz.decode(g.get("MAPCODE.Z32"), 0)[0]


def test_records_match_source(system):
    _, mapcode = system
    recs = worldmap.records(mapcode)
    assert len(recs) == len(worldmap.LABELS) == 25
    # 我孫子の森: sheet row 12, five cells; 東京: row 14, two cells
    assert recs[12][1:] == (5, 0, 192) and recs[14][1:] == (2, 0, 224)


def test_apply_redraws_sheet_and_only_label_fields(system):
    amap, mapcode = system
    font = _font()
    new_amap, new_map = worldmap.apply(amap, mapcode, font)
    assert len(new_amap) == len(amap) and len(new_map) == len(mapcode)
    # outside the label sheet, AMAPDAT is untouched
    a0, a1 = worldmap.SHEET_AT, worldmap.SHEET_AT + worldmap.SHEET_BYTES
    assert new_amap[:a0] == amap[:a0] and new_amap[a1:] == amap[a1:]
    diff = [i for i in range(len(mapcode)) if new_map[i] != mapcode[i]]
    t0 = worldmap.TABLE
    assert all(t0 <= i < t0 + 16 * 26 and (i - t0) % 16 in (5, 6, 7) for i in diff)
    sheet = worldmap.sheet(new_amap)
    for text, (_, n, u, v) in zip(worldmap.LABELS, worldmap.records(new_map)):
        want = worldmap.label(text, font)
        assert (sheet[v:v + 16, u:u + want.shape[1]] == want).all()
        assert n * 16 >= want.shape[1]


def test_records_reject_unexpected_table(system):
    _, mapcode = system
    bad = bytearray(mapcode)
    struct.pack_into("<I", bad, worldmap.TABLE + 16 + 12, 0)
    with pytest.raises(ValueError):
        worldmap.records(bytes(bad))

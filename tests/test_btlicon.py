import glob
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bootlz  # noqa: E402
import btlicon  # noqa: E402
import grparc  # noqa: E402
import iso  # noqa: E402
import kfont  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
GALMURI = Path(os.environ.get("KENSHIN_GALMURI14", ROOT.parent / "galmuri" / "Galmuri14.bdf")).parent
pytestmark = pytest.mark.skipif(not BIN, reason="disc image not available")


@pytest.fixture(scope="module")
def btlcode():
    raw = Path(BIN).read_bytes()
    grp = grparc.parse(iso.read_file(raw, iso.load(raw), "SYSTEM.GRP"))
    return bootlz.decode(grp.get("BTLCODE.Z32"), 0)[0]


@pytest.fixture(scope="module")
def fonts():
    paths = [GALMURI / f for f in btlicon.FONT_FILES]
    if not all(p.exists() for p in paths):
        pytest.skip("Galmuri11 Bold / Galmuri9 not available")
    return tuple(kfont.load_bdf(p) for p in paths)


def test_rle_reproduces_source(btlcode):
    at = btlicon.sheet_at(btlcode)
    sheet, size = btlicon.unrle(btlcode, at)
    assert len(sheet) == btlicon.WIDTH * btlicon.HEIGHT
    assert btlicon.rle(sheet, btlicon.WIDTH, btlicon.HEIGHT, esc=btlcode[at + 8]) == btlcode[at:at + size]


def test_rle_escape_literal():
    data = bytes([7, 7, 3, 3, 3, 3, 3, 1]) * 40
    packed = btlicon.rle(data, 1, len(data), esc=7)
    assert btlicon.unrle(packed)[0] == data


def test_apply_changes_only_icon_cells(btlcode, fonts):
    at = btlicon.sheet_at(btlcode)
    old, size = btlicon.unrle(btlcode, at)
    out = btlicon.apply(btlcode, fonts)
    new, _ = btlicon.unrle(out, at)
    cells = {(cx + dx, cy + y) for _, cx, cy in btlicon.ICONS for dx in range(48) for y in range(24)}
    for y in range(btlicon.HEIGHT):
        for x in range(2 * btlicon.WIDTH):
            if (x, y) not in cells:
                i, s = y * btlicon.WIDTH + x // 2, 4 * (x & 1)
                assert (old[i] >> s) & 15 == (new[i] >> s) & 15, (x, y)
    assert new != old
    # nothing after the slot moves
    end = -(-(at + size) // 4) * 4
    assert out[end:] == btlcode[end:] and out[:at] == btlcode[:at]

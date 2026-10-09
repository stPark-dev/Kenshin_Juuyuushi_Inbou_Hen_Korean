import glob
import os
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bootlz  # noqa: E402
import grparc  # noqa: E402
import iso  # noqa: E402
import kfont  # noqa: E402
import titlemenu  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
GALMURI = Path(os.environ.get("KENSHIN_GALMURI14", ROOT.parent / "galmuri" / "Galmuri14.bdf"))
pytestmark = pytest.mark.skipif(not BIN, reason="disc image not available")


@pytest.fixture(scope="module")
def title():
    raw = Path(BIN).read_bytes()
    return grparc.parse(iso.read_file(raw, iso.load(raw), "SYSTEM.GRP")).get("TITLE.BIN")


@pytest.fixture(scope="module")
def font():
    if not GALMURI.exists():
        pytest.skip("Galmuri14 not available")
    return kfont.load_bdf(GALMURI)


def sheet_of(title):
    at, _ = titlemenu.entries(title)[titlemenu.ENTRY]
    return bootlz.decode(title, at + struct.unpack_from("<I", title, at + 4 * titlemenu.SHEET_MEMBER)[0])[0]


def test_source_sheet_layout(title):
    s = sheet_of(title)
    assert len(s) == titlemenu.WIDTH * titlemenu.HEIGHT and set(s) == {0, 1, 2}
    # each word: 8 rows at the top of two strips, the rest of the strip empty
    used = {y for y in range(titlemenu.HEIGHT) if any(s[y * 96:(y + 1) * 96])}
    assert used == {k * 32 + y for k in range(4) for y in range(8)}


def test_apply_keeps_other_entries(title, font):
    out = titlemenu.apply(title, font)
    old, new = titlemenu.entries(title), titlemenu.entries(out)
    for i, ((a, b), (c, d)) in enumerate(zip(old, new)):
        if i != titlemenu.ENTRY:
            assert out[c:d] == title[a:b], i
    assert sheet_of(out) == titlemenu.sheet(font)
    used = {y for y in range(titlemenu.HEIGHT) if any(sheet_of(out)[y * 96:(y + 1) * 96])}
    assert used <= {k * 32 + y for k in range(4) for y in range(8)}

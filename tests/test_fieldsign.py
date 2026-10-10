import glob
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bootlz  # noqa: E402
import fieldsign  # noqa: E402
import grparc  # noqa: E402
import iso  # noqa: E402
import kfont  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
GALMURI = ROOT.parent / "galmuri"


def test_scan_ignores_numbering():
    rng = np.random.default_rng(3)
    tpl = rng.integers(1, 6, (12, 20)).astype(np.uint8)
    blk = rng.integers(0, 250, (64, 64)).astype(np.uint8)
    blk[30:42, 10:30] = tpl + 100  # same picture, other palette numbers
    hits = fieldsign.scan(tpl, blk)
    assert hits and hits[0][1:] == (10, 30) and hits[0][0] < 1e-6


def test_glyph_mask_bold_widens():
    font = {"가": {"bbx": (2, 1, 0, 0), "bits": [0b10]}}
    assert fieldsign.glyph_mask("가", font, False).tolist() == [[True, False]]
    assert fieldsign.glyph_mask("가", font, False, bold=True).tolist() == [[True, True, False]]


@pytest.fixture(scope="module")
def sources():
    if not BIN:
        pytest.skip("disc image not available")
    raw = Path(BIN).read_bytes()
    disc = iso.load(raw)
    out = {}
    for n in ("ZROUP01.GRP",):
        g = grparc.parse(iso.read_file(raw, disc, n))
        names = [e.name for e in g.entries]
        for e in g.entries:
            if e.name.endswith(".MDT") and e.name[:-1] + "S" in names:
                mds = g.entries[names.index(e.name[:-1] + "S")].data
                out[e.name] = (bootlz.decode(e.data, 0)[0], bootlz.decode(mds, 0)[0])
    return out


def test_t001_signs_redrawn(sources):
    if not (GALMURI / "Galmuri9.bdf").exists():
        pytest.skip("Galmuri not available")
    fonts = (kfont.load_bdf(GALMURI / "Galmuri11-Bold.bdf"), kfont.load_bdf(GALMURI / "Galmuri9.bdf"))
    signs = [s for s in fieldsign.SIGNS if s.ref == "T001.MDT"]
    by = {11: fonts[0], 9: fonts[1]}
    refs = [fieldsign.reference(s, *sources["T001.MDT"]) for s in signs]
    masks = {s.name: fieldsign.glyph_mask(s.text, by[s.font], s.vertical, s.bold) for s in signs}
    mdt = sources["T001.MDT"][0]
    new, found = fieldsign.apply(mdt, refs, masks)
    assert {f[0] for f in found} == {s.name for s in signs}
    assert len(new) == len(mdt)
    # only the sign areas change
    diff = np.frombuffer(new, np.uint8) != np.frombuffer(mdt, np.uint8)
    assert 0 < diff.sum() < 4000

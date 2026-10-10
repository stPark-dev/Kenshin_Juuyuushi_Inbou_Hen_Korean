import glob
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import bootlz  # noqa: E402
import credits  # noqa: E402
import grparc  # noqa: E402
import iso  # noqa: E402
import kfont  # noqa: E402
import textio  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
GALMURI = Path(os.environ.get("KENSHIN_GALMURI14", ROOT.parent / "galmuri" / "Galmuri14.bdf"))
CRLF = bytes([13, 10])


def test_expand_slices():
    assert credits.expand("가{1:3}나{4:}", "0123456") == "가12나456"
    assert credits.expand("{:2}", "abc") == "ab"


def test_halves_double_the_glyph():
    g = {"bbx": (2, 1, 0, 0), "bits": [0b11], "code": 0xAC00}
    left, right = credits.halves(g, (16, 16))
    whole = [l + r for l, r in zip(kfont.pixels(left), kfont.pixels(right))]
    small = kfont.pixels(kfont.render(g, (16, 16)))
    assert whole == [[b for b in row for _ in (0, 1)] for row in small]


@pytest.fixture(scope="module")
def roll():
    if not BIN:
        pytest.skip("disc image not available")
    raw = Path(BIN).read_bytes()
    return bootlz.decode(grparc.parse(iso.read_file(raw, iso.load(raw), "SYSTEM.GRP")).get("ROLL.Z32"), 0)[0]


@pytest.fixture(scope="module")
def galmuri():
    if not GALMURI.exists():
        pytest.skip("Galmuri14 not available")
    return kfont.load_bdf(GALMURI)


def test_source_layout(roll):
    credits.check(roll)
    assert len(credits.font(roll)) == 432
    src = credits.lines(roll)
    assert max(credits.columns(raw) for raw in src) <= credits.COLUMNS
    assert {c for raw in src for c in credits.codes(raw)} <= set(credits.font(roll))


def _ko(roll):
    ko = json.loads((ROOT / "text" / "ko" / "ROLL.json").read_text(encoding="utf-8"))
    got, problems = textio.usable_translations(credits.extract(roll), ko, textio.STATUSES)
    assert problems == []
    return got


def _font_at(data):
    lst, g = (credits._hi_lo(data, r) - credits.BASE for r in (credits.LIST_REF, credits.GLYPH_REF))
    codes = []
    while data[lst]:
        if data[lst:lst + 2] != CRLF:
            codes.append(data[lst:lst + 2])
        lst += 2
    return {c: data[g + 32 * i:g + 32 * i + 32] for i, c in enumerate(codes)}


def test_apply(roll, galmuri):
    texts = _ko(roll)
    out, rep = credits.apply(roll, texts, galmuri, kfont.hangul_box(galmuri))
    src = credits.lines(roll)
    at = credits._hi_lo(out, credits.TEXT_REF) - credits.BASE
    new = out[at:out.index(0, at)].split(CRLF)
    assert len(new) == len(src)  # the scroll keeps its line count
    kept = [i for i in range(len(src)) if i not in texts]
    assert [new[i] for i in kept] == [src[i] for i in kept]
    assert max(credits.columns(raw) for raw in new) <= credits.COLUMNS
    font = _font_at(out)
    assert len(font) == rep["glyphs"] and {c for raw in new for c in credits.codes(raw)} == set(font)
    old = credits.font(roll)
    assert all(font[c] == old[c] for i in kept for c in credits.codes(src[i]))
    assert out[credits.TABLE - credits.BASE:len(roll)] == roll[credits.TABLE - credits.BASE:]

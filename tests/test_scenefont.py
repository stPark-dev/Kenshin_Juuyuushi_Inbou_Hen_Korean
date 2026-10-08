import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import scenefont  # noqa: E402
import script  # noqa: E402

A, I, U = ("あ".encode("cp932"), "い".encode("cp932"), "う".encode("cp932"))
H = bytes([0x88, 0x9F])
G = lambda n: bytes([n]) * 32  # noqa: E731


def test_first_appearance_order_and_sources():
    strings = [A + b"^c" + H, I + A, U]
    codes, glyphs = scenefont.build(strings, hangul={H: G(1)}, scene={A: G(2), I: G(3)}, namefont={U: G(4), A: G(9)})
    assert codes == [A, H, I, U]
    assert glyphs == [G(2), G(1), G(3), G(4)]  # scene glyph wins over NAMEFONT for A


def test_missing_glyph_raises_with_codes():
    with pytest.raises(ValueError, match="82a4"):
        scenefont.build([U], hangul={}, scene={}, namefont={})


def test_controls_are_not_glyphs():
    codes, _ = scenefont.build([b"c7" + A + b"N;^s"], hangul={}, scene={A: G(1)}, namefont={})
    assert codes == [A]


def test_load_namefont_pairs_codes_and_glyphs():
    txt = "あい\r\nう".encode("cp932")
    nf = scenefont.load_namefont(txt, G(1) + G(2) + G(3))
    assert nf == {A: G(1), I: G(2), U: G(3)}
    with pytest.raises(ValueError):
        scenefont.load_namefont(txt, G(1))


ROOT = Path(__file__).resolve().parent.parent
GRP_DIR = Path(os.environ.get("KENSHIN_GRP_DIR", ROOT / "work" / "grp"))
CORPUS = sorted(GRP_DIR.glob("ZROUP*/GROUP*.BIN")) if GRP_DIR.is_dir() else []


@pytest.mark.skipif(not CORPUS, reason="extracted GROUP corpus not available")
def test_corpus_rebuilds_every_scene_font_exactly():
    nf_dir = GRP_DIR / "SYSTEM"
    nf = scenefont.load_namefont((nf_dir / "NAMEFONT.TXT").read_bytes(), (nf_dir / "NAMEFONT.BIN").read_bytes())
    assert len(nf) == 6879
    for p in CORPUS:
        g = script.parse_group(p.read_bytes())
        scene = dict(zip(g.font_codes, g.font_glyphs))
        codes, glyphs = scenefont.build([s.raw for s in g.strings], hangul={}, scene=scene, namefont=nf)
        assert codes == g.font_codes, p.name
        assert glyphs == g.font_glyphs, p.name

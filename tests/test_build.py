import glob
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build  # noqa: E402
import kfont  # noqa: E402
import scenefont  # noqa: E402
import script  # noqa: E402
import textio  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GRP = Path(os.environ.get("KENSHIN_GRP_DIR", ROOT / "work" / "grp"))
GALMURI = Path(os.environ.get("KENSHIN_GALMURI14", ROOT.parent / "galmuri" / "Galmuri14.bdf"))
BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)
have_assets = GRP.is_dir() and GALMURI.is_file()


@pytest.fixture(scope="module")
def assets():
    nf = scenefont.load_namefont((GRP / "SYSTEM" / "NAMEFONT.TXT").read_bytes(), (GRP / "SYSTEM" / "NAMEFONT.BIN").read_bytes())
    font = kfont.load_bdf(GALMURI)
    return build.Assets(font=font, box=kfont.hangul_box(font), namefont=nf)


@pytest.mark.skipif(not have_assets, reason="corpus or Galmuri14 not available")
def test_scene_build_translates_in_place_and_by_append(assets):
    data = (GRP / "ZROUP40" / "GROUP40.BIN").read_bytes()
    g = script.parse_group(data)
    rows = {r["offset"]: r for r in textio.extract("ZROUP40", g)}
    short = "불량^c　아야"
    long = "불량^c　" + " ".join(["아주아주긴문장"] * 12)
    out, report = build.scene_build(g, {0xF35C: short, 0xF370: long}, assets)
    g2 = script.parse_group(out)
    by_off = {s.offset: s for s in g2.strings}
    # untranslated strings keep their bytes and offsets
    for s in g.strings:
        if s.offset not in (0xF35C, 0xF370):
            assert by_off[s.offset].raw == s.raw
    assert report["in_place"] == 1 and report["appended"] == 1
    # every code used by the final text has a glyph; Hangul glyphs are not blank
    codes = dict(zip(g2.font_codes, g2.font_glyphs))
    for s in g2.strings:
        for t in script.tokenize(s.raw):
            if t.kind == "char":
                assert t.raw in codes
    assert any(codes[c] != bytes(32) for c in codes if c[0] >= 0x88)
    assert rows[0xF370]["ref"] == "movable"


@pytest.mark.skipif(not have_assets, reason="corpus or Galmuri14 not available")
def test_scene_build_refuses_overlong_unmovable(assets):
    g = script.parse_group((GRP / "ZROUP24" / "GROUP24.BIN").read_bytes())
    rows = textio.extract("ZROUP24", g)
    target = next(r for r in rows if r["ref"] == "unreferenced" and r["speaker"])
    long = target["speaker"] + "^c　" + " ".join(["가나다라마바사"] * 30)
    with pytest.raises(ValueError, match="cannot be moved"):
        build.scene_build(g, {target["offset"]: long}, assets)


@pytest.mark.skipif(not (have_assets and BIN), reason="disc image not available")
def test_full_build_without_translations_is_identical(tmp_path, assets):
    out = tmp_path / "out.bin"
    report = build.build(Path(BIN), tmp_path / "ko-empty", out, statuses={"reviewed"}, assets=assets)
    assert report["problems"] == []
    assert hashlib.sha256(out.read_bytes()).hexdigest() == build.SOURCE_SHA256
    assert (tmp_path / "out.cue").read_text().startswith('FILE "out.bin" BINARY')


def test_source_identity_is_checked(tmp_path):
    p = tmp_path / "wrong.bin"
    p.write_bytes(b"\0" * 2352)
    with pytest.raises(ValueError, match="SHA-256"):
        build.check_source(p.read_bytes())


@pytest.mark.skipif(not have_assets, reason="corpus or Galmuri14 not available")
def test_shared_codes_are_one_table_clear_of_menu_and_kept_japanese():
    g40 = script.parse_group((GRP / "ZROUP40" / "GROUP40.BIN").read_bytes())
    g41 = script.parse_group((GRP / "ZROUP41" / "GROUP41.BIN").read_bytes())
    menu = {"愛".encode("cp932"), "茜".encode("cp932")}
    code_of = build.shared_codes([(g40, {0xF35C: "가나"}), (g41, {})], frozenset(menu))
    assert set(code_of) == {"가", "나"}
    kept = build.reserved_codes(g40, {0xF35C: "가나"}) | build.reserved_codes(g41, {})
    assert not (set(code_of.values()) & (menu | kept))

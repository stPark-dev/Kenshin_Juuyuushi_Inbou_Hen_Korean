import glob
import json
import os
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import exetext  # noqa: E402
import iso  # noqa: E402
import mainprog  # noqa: E402

BIN = os.environ.get("KENSHIN_BIN") or next(iter(sorted(glob.glob(str(ROOT / "original" / "*.bin")))), None)


def test_encode_full_width_and_limit():
    code_of = {"가": b"\x88\x9f", "나": b"\x88\xa0"}
    assert exetext.encode("가 나！", code_of, 4) == b"\x88\x9f\x81\x40\x88\xa0\x81\x49"
    with pytest.raises(ValueError):
        exetext.encode("가나가나가", code_of, 4)
    with pytest.raises(ValueError):
        exetext.encode("가A", code_of, 4)  # half-width has no menu glyph


@pytest.fixture(scope="module")
def main():
    raw = Path(BIN).read_bytes()
    disc = iso.load(raw)
    return mainprog.unpack(iso.read_file(raw, disc, mainprog.exe_name(disc)))


def _lookup(m, code):
    """The game's font lookup: list address from the patched lui/addiu, glyph base fixed."""
    hi, lo = (w & 0xFFFF for w in struct.unpack_from("<2I", m, exetext.LIST_LUI - mainprog.BASE))
    at = (hi << 16) + (lo - 0x10000 if lo & 0x8000 else lo) - mainprog.BASE
    i = 0
    while m[at:at + 2] not in (b"\0\0",):
        if m[at:at + 2] == code:
            o = exetext.FONT_GLYPHS - mainprog.BASE + 32 * i
            return m[o:o + 32]
        at += 2
        i += 1
    return None


@pytest.mark.skipif(not BIN, reason="disc image not available")
def test_apply_repacks_strings_and_font(main):
    texts = {"MAIN:item:001": b"\x88\x9f\x88\xa0", "MAIN:desc:001": b"\x88\x9f" * 14}
    glyphs = {b"\x88\x9f": bytes([1]) * 32, b"\x88\xa0": bytes([2]) * 32, b"\x81\x40": bytes(32)}
    out = exetext.apply(main, texts, glyphs)
    got = dict(exetext.strings(out))
    for sid, raw in exetext.strings(main):
        assert got[sid] == texts.get(sid, raw)
    assert _lookup(out, b"\x88\xa0") == bytes([2]) * 32
    assert _lookup(out, b"\x88\x9f") == bytes([1]) * 32
    assert _lookup(out, "愛".encode("cp932")) is None


@pytest.mark.skipif(not BIN, reason="disc image not available")
def test_translation_file_is_current(main):
    rows = {r["id"]: r for r in exetext.extract(main)}
    ko = json.loads((ROOT / "text" / "ko" / "MAIN.json").read_text(encoding="utf-8"))
    items = {r["id"]: r for r in json.loads((ROOT / "text" / "glossary_items.json").read_text(encoding="utf-8"))["items"]}
    for sid, e in ko.items():
        assert e["src_hash"] == rows[sid]["hash"], sid
        assert len(e["ko"]) <= rows[sid]["limit"], sid
        kind, i = sid.split(":")[1:]
        if kind == "item" and int(i) in items:
            assert e["ko"] == items[int(i)]["ko"], sid  # menu name = glossary name

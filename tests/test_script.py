import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import script  # noqa: E402


def make_group(strings, font_codes=(b"\x82\xa0",)):
    """Synthetic GROUPnn.BIN: 4 section offsets, filler, 4-byte aligned string pool, font block."""
    pool = bytearray()
    for s in strings:
        pool += s + b"\0"
        pool += bytes(-len(pool) % 4)
    h0, h1, h2 = 0x10, 0x14, 0x18
    h3 = h2 + len(pool)
    n = len(font_codes)
    L = (4 + 2 * n + 2 + 3) & ~3
    block = struct.pack("<I", L) + b"".join(font_codes) + bytes(L - 4 - 2 * n) + bytes(32 * n)
    return struct.pack("<4I", h0, h1, h2, h3) + bytes(h2 - 16) + bytes(pool) + block


def test_tokenize_kinds():
    raw = "剣心^c　".encode("cp932") + b"c7" + "あ".encode("cp932") + b"N;" + b"n:" + b"C7" + b"N0^s"
    toks = script.tokenize(raw)
    assert [t.kind for t in toks] == ["char", "char", "ctl", "char", "color", "char", "space", "arg", "color", "space", "ctl"]
    assert b"".join(t.raw for t in toks) == raw


def test_tokenize_rejects_unknown_byte():
    with pytest.raises(ValueError):
        script.tokenize(b"\x20")
    with pytest.raises(ValueError):
        script.tokenize("あ".encode("cp932")[:1])  # truncated double-byte


def test_parse_strings_and_font():
    data = make_group([b"\x82\xa0^c", b"\x82\xa2\x82\xa4"])
    g = script.parse_group(data)
    assert [s.raw for s in g.strings] == [b"\x82\xa0^c", b"\x82\xa2\x82\xa4"]
    assert [s.slot for s in g.strings] == [8, 8]  # bytes up to the next string (terminator + padding)
    assert g.font_codes == [b"\x82\xa0"]


def test_unchanged_serialize_is_identical():
    data = make_group([b"\x82\xa0^c", b"\x82\xa2\x82\xa4\x82\xa6"])
    assert script.serialize_group(script.parse_group(data)) == data


def test_bad_header_raises():
    with pytest.raises(ValueError):
        script.parse_group(struct.pack("<4I", 0x10, 0x14, 0x30, 0x20))


GRP_DIR = Path(os.environ.get("KENSHIN_GRP_DIR", Path(__file__).resolve().parent.parent / "work" / "grp"))
CORPUS = sorted(GRP_DIR.glob("ZROUP*/GROUP*.BIN")) if GRP_DIR.is_dir() else []


@pytest.mark.skipif(not CORPUS, reason="extracted GROUP corpus not available")
def test_corpus_tokenize_and_round_trip_all_groups():
    assert len(CORPUS) == 58
    total = 0
    for p in CORPUS:
        data = p.read_bytes()
        g = script.parse_group(data)
        for s in g.strings:
            assert b"".join(t.raw for t in script.tokenize(s.raw)) == s.raw
        assert script.serialize_group(g) == data, p.name
        total += len(g.strings)
    assert total == 10401

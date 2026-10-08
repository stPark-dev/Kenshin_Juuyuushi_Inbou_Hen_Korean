import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import refs  # noqa: E402
import script  # noqa: E402

A = "あ".encode("cp932")


def make_group(code, strings, h0=None, h1=None):
    """GROUP with code at 0x10, pool after code (4-aligned), one-glyph font block.

    `code` may contain placeholders b"{N}" replaced by the u32 offset of string N.
    """
    code_len = len(code) + code.count(b"{")  # each "{N}" placeholder becomes 4 bytes
    pool_start = (0x10 + code_len + 3) & ~3
    offsets, pool = [], bytearray()
    for s in strings:
        offsets.append(pool_start + len(pool))
        pool += s + b"\0"
        pool += bytes(-len(pool) % 4)
    for i, off in enumerate(offsets):
        code = code.replace(b"{%d}" % i, struct.pack("<I", off))
    assert len(code) <= pool_start - 0x10
    h2 = pool_start
    h3 = h2 + len(pool)
    head = struct.pack("<4I", h0 or 0x10, h1 or h2, h2, h3)
    body = head + code + bytes(h2 - 0x10 - len(code)) + bytes(pool)
    return body + script.build_font_block([A], [bytes(32)]), offsets


def test_classify_contexts():
    # 0x10: text op (site 0x12); 0x16: op 0x40 with kind-7 first operand (site 0x18);
    # 0x1C: zero word so 0x18 is not part of a table; 0x20: aligned table of 3 string starts
    code = b"\x49\x00{0}" + b"\x40\x70{1}" + b"\x00\x00\x00\x00" + b"{2}{3}{4}"
    data, offs = make_group(code, [A + b"^c", A, A + A, A, A + A + A, A])
    c = refs.classify(script.parse_group(data))
    assert c[offs[0]].status == "movable" and c[offs[0]].sites == [0x12]
    assert c[offs[1]].status == "movable" and c[offs[1]].sites == [0x18]
    assert [c[offs[i]].sites for i in (2, 3, 4)] == [[0x20], [0x24], [0x28]]
    assert all(c[offs[i]].status == "movable" for i in (2, 3, 4))
    assert c[offs[5]].status == "unreferenced" and c[offs[5]].sites == []


def test_kind7_needs_exact_type_byte_and_known_opcode():
    for code in (b"\x40\x71{0}", b"\x10\x70{0}"):
        data, offs = make_group(code, [A, A])
        assert refs.classify(script.parse_group(data))[offs[0]].status == "unknown", code


def test_singleton_aligned_reference_is_unknown():
    data, offs = make_group(b"\x00\x00\x00\x00{0}" + b"\x01\x02\x03\x04", [A, A])
    c = refs.classify(script.parse_group(data))
    assert c[offs[0]].status == "unknown"
    assert c[offs[1]].status == "unreferenced"


def test_rebuild_unchanged_is_identical():
    data, _ = make_group(b"\x49\x00{0}\x49\x00{1}", [A + b"^c", A])
    assert refs.rebuild(script.parse_group(data), {}) == data


def test_in_place_when_it_fits():
    data, offs = make_group(b"\x49\x00{0}\x49\x00{1}", [A + A + A, A])
    out = refs.rebuild(script.parse_group(data), {offs[0]: A})
    g = script.parse_group(out)
    assert [s.offset for s in g.strings] == offs
    assert g.strings[0].raw == A
    assert out[:offs[0]] == data[:offs[0]]
    assert len(out) == len(data)


def test_grow_movable_appends_and_patches_all_sites():
    data, offs = make_group(b"\x49\x00{0}\x49\x04{1}\x49\x03{0}", [A, A])
    long = A * 9
    out = refs.rebuild(script.parse_group(data), {offs[0]: long})
    g = script.parse_group(out)
    moved = [s for s in g.strings if s.raw == long]
    assert len(moved) == 1
    new = moved[0].offset
    assert new % 4 == 0 and new > offs[1]
    assert struct.unpack_from("<I", out, 0x12)[0] == new
    assert struct.unpack_from("<I", out, 0x1E)[0] == new  # second text-op site
    assert struct.unpack_from("<I", out, 0x18)[0] == offs[1]  # other reference untouched
    assert [s.offset for s in g.strings][:2] == offs  # old slots keep their offsets
    assert g.font_codes == [A]


def test_grow_unmovable_raises():
    data, offs = make_group(b"\x00\x00\x00\x00{0}", [A, A])
    with pytest.raises(ValueError, match=hex(offs[1])):
        refs.rebuild(script.parse_group(data), {offs[1]: A * 9})


def test_unknown_offset_raises():
    data, _ = make_group(b"\x49\x00{0}", [A])
    with pytest.raises(KeyError):
        refs.rebuild(script.parse_group(data), {0x999: A})


GRP_DIR = Path(os.environ.get("KENSHIN_GRP_DIR", Path(__file__).resolve().parent.parent / "work" / "grp"))
CORPUS = sorted(GRP_DIR.glob("ZROUP*/GROUP*.BIN")) if GRP_DIR.is_dir() else []


@pytest.mark.skipif(not CORPUS, reason="extracted GROUP corpus not available")
def test_corpus_classification_and_identity():
    from collections import Counter

    counts = Counter()
    for p in CORPUS:
        data = p.read_bytes()
        g = script.parse_group(data)
        counts.update(r.status for r in refs.classify(g).values())
        assert refs.rebuild(g, {}) == data, p.name
    assert counts == Counter(movable=9726, unknown=29, unreferenced=646)


def test_coincidental_kind7_byte_blocks_growth():
    data, offs = make_group(b"\x7a{0}", [A, A])
    with pytest.raises(ValueError, match="unknown"):
        refs.rebuild(script.parse_group(data), {offs[0]: A * 9})


@pytest.mark.parametrize("bad", [b"^", b"\x82", b"\x20"], ids=["dangling_ctl", "dangling_lead", "ascii_space"])
def test_invalid_replacement_tokens_raise(bad):
    data, offs = make_group(b"\x49\x00{0}", [A * 4])
    with pytest.raises(ValueError):
        refs.rebuild(script.parse_group(data), {offs[0]: A + bad})


def test_overlapping_sites_raise():
    # string 1's offset bytes start inside string 0's text-op site
    data, offs = make_group(b"\x49\x00{0}\x49\x00{1}", [A, A])
    g = script.parse_group(data)
    real = refs.classify
    fake = {offs[0]: refs.Ref("movable", [0x12]), offs[1]: refs.Ref("movable", [0x14])}
    refs.classify = lambda _g: fake
    try:
        with pytest.raises(ValueError, match="overlap"):
            refs.rebuild(g, {offs[0]: A * 9, offs[1]: A * 9})
    finally:
        refs.classify = real

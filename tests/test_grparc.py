import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import grparc as grp  # noqa: E402

ALIGN = 0x800


def make_grp(files, pad_byte=0x5A):
    """Build a GRP the way the disc's files are laid out, with nonzero padding."""
    n = len(files)
    names = b""
    name_offs = []
    base = 8 + 12 * n
    for name, _unk, _data in files:
        name_offs.append(base + len(names))
        names += name.encode("ascii") + b"\0"
    hs = base + len(names)
    entries = b""
    body = bytearray()
    off = (hs + ALIGN - 1) & ~(ALIGN - 1)
    for (name, unk, data), no in zip(files, name_offs):
        entries += struct.pack("<HHII", no, unk, len(data), off)
        off = (off + len(data) + ALIGN - 1) & ~(ALIGN - 1)
    out = bytearray([pad_byte]) * off
    out[0:hs] = struct.pack("<II", hs, n) + entries + names
    for (name, unk, data), (no, u, sz, o) in zip(
        files, [struct.unpack_from("<HHII", entries, 12 * i) for i in range(n)]
    ):
        out[o : o + sz] = data
    return bytes(out)


FILES = [("A.BIN", 0x1D, b"\x01" * 0x900), ("B.TXT", 0x44, b"\x02" * 3), ("C", 7, b"")]


def test_parse_reads_entries():
    g = grp.parse(make_grp(FILES))
    assert [(e.name, e.unk, e.data) for e in g.entries] == FILES


def test_unchanged_round_trip_is_byte_identical():
    raw = make_grp(FILES)
    assert grp.build(grp.parse(raw)) == raw


def test_grown_entry_relayouts_aligned_and_keeps_others():
    raw = make_grp(FILES)
    g = grp.parse(raw)
    out = grp.build(g.replace("B.TXT", b"\x03" * 0x1000))
    g2 = grp.parse(out)
    assert [e.name for e in g2.entries] == ["A.BIN", "B.TXT", "C"]
    assert g2.get("B.TXT") == b"\x03" * 0x1000
    assert g2.get("A.BIN") == FILES[0][2]
    assert [e.unk for e in g2.entries] == [0x1D, 0x44, 7]
    hs = struct.unpack_from("<I", out, 0)[0]
    offs = [struct.unpack_from("<HHII", out, 8 + 12 * i)[3] for i in range(3)]
    assert offs[0] == (hs + ALIGN - 1) & ~(ALIGN - 1)
    assert all(o % ALIGN == 0 for o in offs)
    assert len(out) % ALIGN == 0
    # the unchanged entry before the grown one keeps its bytes and padding
    assert out[offs[0] : offs[1]] == raw[offs[0] : offs[1]]


def test_replace_unknown_name_raises():
    with pytest.raises(KeyError):
        grp.parse(make_grp(FILES)).replace("NOPE", b"")


def test_replace_does_not_mutate_original():
    g = grp.parse(make_grp(FILES))
    g.replace("B.TXT", b"zz")
    assert g.get("B.TXT") == b"\x02" * 3


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"\x08\0\0\0",
        struct.pack("<II", 8, 5),  # entry table truncated
        struct.pack("<IIHHII", 0x14, 1, 0x14, 0, 0x100, 0x800) + b"\0",  # data out of range
        struct.pack("<IIHHII", 0x14, 1, 0x40, 0, 0, 0x800) + b"\0" * 0x7EC,  # name out of range
    ],
    ids=["empty", "short_header", "truncated_table", "data_out_of_range", "name_out_of_range"],
)
def test_invalid_input_raises(bad):
    with pytest.raises(ValueError):
        grp.parse(bad)


def _patch_offset(raw, index, off):
    out = bytearray(raw)
    struct.pack_into("<I", out, 8 + 12 * index + 8, off)
    return bytes(out)


@pytest.mark.parametrize(
    "index,off",
    [(0, 0), (1, 0x801), (1, 0x800), (2, 0x1000)],
    ids=["inside_header", "misaligned", "overlaps_previous", "unsorted"],
)
def test_layout_violations_raise(index, off):
    with pytest.raises(ValueError):
        grp.parse(_patch_offset(make_grp(FILES), index, off))


def test_duplicate_names_parse_but_name_access_is_ambiguous():
    # ZROUP20.GRP holds 34 names twice (byte-identical copies), so parse must accept them
    raw = bytearray(make_grp(FILES))
    no0 = struct.unpack_from("<H", raw, 8)[0]
    struct.pack_into("<H", raw, 8 + 12, no0)
    g = grp.parse(bytes(raw))
    assert grp.build(g) == bytes(raw)
    with pytest.raises(ValueError):
        g.get("A.BIN")
    with pytest.raises(ValueError):
        g.replace("A.BIN", b"")


def test_shrunk_entry_moves_later_entries_back():
    g = grp.parse(make_grp(FILES))
    out = grp.build(g.replace("A.BIN", b"\x09"))
    g2 = grp.parse(out)
    assert g2.get("A.BIN") == b"\x09"
    assert g2.get("B.TXT") == FILES[1][2]
    assert len(out) == 3 * ALIGN


ISO_DIR = Path(os.environ.get("KENSHIN_ISO_DIR", Path(__file__).resolve().parent.parent / "work" / "iso"))
CORPUS = sorted(ISO_DIR.glob("*.GRP")) if ISO_DIR.is_dir() else []


@pytest.mark.skipif(not CORPUS, reason="extracted GRP corpus not available")
def test_corpus_unchanged_round_trip_all_grp():
    assert len(CORPUS) == 59
    for p in CORPUS:
        raw = p.read_bytes()
        assert grp.build(grp.parse(raw)) == raw, p.name

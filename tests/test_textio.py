import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import script  # noqa: E402
import textio  # noqa: E402

A = "あ".encode("cp932")


def group(strings, code=b""):
    pool_start = (0x10 + len(code) + 3) & ~3
    pool = bytearray()
    offs = []
    for s in strings:
        offs.append(pool_start + len(pool))
        pool += s + b"\0"
        pool += bytes(-len(pool) % 4)
    for i, o in enumerate(offs):
        code = code.replace(b"{%d}" % i, struct.pack("<I", o))
    h2 = pool_start
    head = struct.pack("<4I", 0x10, h2, h2, h2 + len(pool))
    data = head + code + bytes(h2 - 0x10 - len(code)) + bytes(pool) + script.build_font_block([A], [bytes(32)])
    return script.parse_group(data), offs


def test_extract_entries():
    g, offs = group(["剣心^c　あ".encode("cp932"), A], code=b"\x49\x00{0}\x00\x00")
    rows = textio.extract("ZROUP99", g)
    assert [r["id"] for r in rows] == [f"ZROUP99:{offs[0]:x}", f"ZROUP99:{offs[1]:x}"]
    assert rows[0]["src"] == "剣心^c　あ"
    assert rows[0]["speaker"] == "剣心"
    assert rows[1]["speaker"] is None
    assert rows[0]["ref"] == "movable" and rows[1]["ref"] == "unreferenced"
    assert rows[0]["slot"] == offs[1] - offs[0] - 1
    assert rows[0]["hash"] == textio.src_hash("剣心^c　あ".encode("cp932"))


def test_translations_filter_stale_and_status(tmp_path):
    g, offs = group([A, A + A])
    rows = textio.extract("ZROUP99", g)
    ko = {
        rows[0]["id"]: {"src_hash": rows[0]["hash"], "ko": "가", "status": "reviewed", "note": ""},
        rows[1]["id"]: {"src_hash": "deadbeefdead", "ko": "나", "status": "reviewed", "note": ""},
    }
    p = tmp_path / "ZROUP99.json"
    p.write_text(json.dumps(ko, ensure_ascii=False))
    got, problems = textio.usable_translations(rows, json.loads(p.read_text()), statuses={"reviewed"})
    assert got == {offs[0]: "가"}
    assert problems == [f"{rows[1]['id']}: stale (source changed)"]


def test_unknown_id_and_bad_status_are_problems():
    g, offs = group([A])
    rows = textio.extract("ZROUP99", g)
    ko = {
        "ZROUP99:dead": {"src_hash": "x", "ko": "가", "status": "reviewed", "note": ""},
        rows[0]["id"]: {"src_hash": rows[0]["hash"], "ko": "가", "status": "typo", "note": ""},
    }
    got, problems = textio.usable_translations(rows, ko, statuses={"draft", "reviewed"})
    assert got == {}
    assert any("unknown id" in p for p in problems)
    assert any("status" in p for p in problems)


def test_draft_excluded_when_only_reviewed_allowed():
    g, offs = group([A])
    rows = textio.extract("ZROUP99", g)
    ko = {rows[0]["id"]: {"src_hash": rows[0]["hash"], "ko": "가", "status": "draft", "note": ""}}
    got, problems = textio.usable_translations(rows, ko, statuses={"reviewed"})
    assert got == {} and problems == []

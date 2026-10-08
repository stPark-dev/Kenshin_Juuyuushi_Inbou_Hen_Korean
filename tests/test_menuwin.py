import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import menuwin  # noqa: E402


def win(w, h=4, x=10):
    return {"at": 0, "win": 0, "x": x, "y": 1, "w": w, "h": h}


def test_layout_wraps_per_character_and_at_the_edge():
    # 160 px window: a 10-character option fills the line and the next option starts below
    lines = menuwin.render("^4c7성냥에얽힌진기한이야c9자전거^s", 160)
    assert lines == ["c7성냥에얽힌진기한이야", "c9자전거"]
    # a break right after a full line leaves a blank line (runtime, ZROUP95)
    assert menuwin.render("^4ca그림책^cc7퍼즐^s", 48) == ["ca그림책", "", "c7퍼즐"]


def test_source_relying_on_wrap_flags_joined_translation():
    src = "^4c7絵草紙c7パズルc7終わる^s"  # three 48 px options in a 48 px window
    assert menuwin.problems(src, src, win(6)) == []
    bad = menuwin.problems(src, "^4c7그림책c7퍼즐c7끝낸다^s", win(6))
    assert any("share a line" in p or "wrap inside" in p for p in bad)
    # explicit breaks plus one more unit of width lay it out like the source
    fixed = "^4c7그림책^cc7퍼즐^cc7끝낸다^s"
    assert menuwin.problems(src, fixed, win(6)) != []  # blank line after the full first line
    assert menuwin.problems(src, fixed, win(6), win(7)) == []


def test_place_label_must_fit_one_line():
    src = "^4　塩原村^s"
    assert menuwin.problems(src, "^4　시오바라 마을^s", win(10, h=2))
    assert menuwin.problems(src, "^4　시오바라 마을^s", win(10, h=2), win(15, h=2)) == []


def test_explicit_break_inside_an_option_is_not_a_wrap():
    src = "^4ca関原妙^s"
    assert menuwin.problems(src, "^4ca세키하라^c타에^s", win(6, h=6), win(12, h=6)) == []


def _group(code, strings):
    """Minimal parsed-GROUP stand-in: code bytes, then NUL-terminated strings."""
    data = bytearray(code)
    offs = []
    for s in strings:
        offs.append(len(data))
        data += s.encode("cp932") + b"\0"
    class S:
        def __init__(self, off, raw):
            self.offset, self.raw = off, raw
    g = type("G", (), {})()
    g.data = bytes(data)
    g.header = (0, 0, offs[0], len(data))
    g.strings = [S(o, s.encode("cp932")) for o, s in zip(offs, strings)]
    return g


def test_fit_widens_the_window_op_and_keeps_its_centre():
    # 16-byte header, then: 47 03 x=14 y=7 w=10 h=2 ; 49 03 <string offset>
    code = bytearray(16) + bytes([0x47, 3, 14, 7, 10, 2, 0x49, 3]) + bytes(4) + bytes(8)
    struct.pack_into("<I", code, 24, len(code))  # the string follows the code
    g = _group(code, ["^4　塩原村^s"])
    patches, unfit = menuwin.fit(g, {g.strings[0].offset: "^4　시오바라 마을^s"})
    assert unfit == []
    assert patches == [{"at": 16, "old": (14, 10), "new": (12, 15)}]
    out = menuwin.apply(g.data, patches)
    assert out[16:22] == bytes([0x47, 3, 12, 7, 15, 2])
    with pytest.raises(ValueError):
        menuwin.apply(out, patches)  # old bytes no longer match

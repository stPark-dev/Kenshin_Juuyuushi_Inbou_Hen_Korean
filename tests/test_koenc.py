import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import koenc  # noqa: E402

SP = "　"


def codes_for(text):
    return koenc.assign_codes({c for c in text if koenc.is_hangul(c)}, reserved=set())


def enc(ko, src):
    return koenc.encode(ko, src.encode("cp932"), codes_for(ko))


def test_space_becomes_half_width_token():
    out = enc("가나 다", "あい")
    c = codes_for("가나 다")
    assert out == c["가"] + c["나"] + b"N;" + c["다"]


def test_controls_and_punctuation_pass_through():
    out = enc("켄신^c" + SP + "좋소！^s", "剣心^c" + SP + "よし！^s")
    c = codes_for("켄신좋소")
    assert out == c["켄"] + c["신"] + b"^c" + SP.encode("cp932") + c["좋"] + c["소"] + "！".encode("cp932") + b"^s"


def test_non_layout_tokens_must_match_source_order():
    with pytest.raises(ValueError, match="control"):
        enc("가^s", "あ^S")
    with pytest.raises(ValueError, match="control"):
        enc("가", "あc7")
    # ^c and N; are layout tokens and may differ
    enc("가^c" + SP + "나", "あ")


def test_wraps_at_last_space_with_indent():
    words = ["가나다라"] * 6  # 6 words * 64px + spaces exceed 288px
    ko = "화자^c" + SP + " ".join(words)
    out = koenc.layout(ko)
    lines = out.split("^c")
    assert lines[0] == "화자"
    assert all(line.startswith(SP) for line in lines[1:])
    assert all(koenc.width(line) <= 288 for line in lines)
    assert "".join(lines[1:]).replace(SP, "").replace(" ", "") == "가나다라" * 6


def test_unbreakable_overlong_line_raises():
    with pytest.raises(ValueError, match="288"):
        koenc.layout("화자^c" + SP + "가" * 18)


def test_width_counts_space_as_8px():
    assert koenc.width(SP + "가 나") == 16 + 16 + 8 + 16
    assert koenc.width("c7가^s") == 16


@pytest.mark.parametrize("bad", ["a", "가\x01", "가丂é"], ids=["ascii_letter", "control_char", "unencodable"])
def test_bad_characters_raise(bad):
    with pytest.raises(ValueError):
        koenc.encode(bad, b"", codes_for(bad))


def test_assign_codes_skips_reserved_and_invalid_trail_bytes():
    hangul = {chr(0xAC00 + i) for i in range(300)}
    reserved = {bytes([0x88, 0x9F])}
    c = koenc.assign_codes(hangul, reserved)
    vals = set(c.values())
    assert len(vals) == 300
    assert bytes([0x88, 0x9F]) not in vals
    assert all(0x40 <= v[1] <= 0xFC and v[1] != 0x7F for v in vals)
    assert all(0x88 <= v[0] <= 0x9F or 0xE0 <= v[0] <= 0xEA for v in vals)
    # deterministic: sorted syllables get ascending codes
    order = sorted(hangul)
    assert [c[h] for h in order] == sorted(c.values())


def test_assign_codes_capacity_error():
    with pytest.raises(ValueError):
        koenc.assign_codes({chr(0xAC00 + i) for i in range(9000)}, set())

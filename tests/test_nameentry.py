import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import nameentry as ne  # noqa: E402


def test_readings_cover_compound_keys():
    assert ne.readings("간") == {"ㄱㅏㄴ"}
    assert ne.readings("과") == {"ㄱㅘ", "ㄱㅗㅏ"}
    assert "ㄷㅏㄹㄱ" in ne.readings("닭") and "ㄷㅏㄺ" in ne.readings("닭")
    assert ne.syllable("ㄱ", "ㅏ", "ㄴ") == "간"


def test_namedic_longest_reading_first():
    code_of = {c: bytes([0x88 + i // 0xBC, 0x40 + i % 0xBC]) for i, c in enumerate(sorted(ne.chars()))}
    dic = ne.namedic(code_of)
    assert dic.endswith(b"\x1a")
    lines = dic[:-1].split(b"\r\n")[:-1]
    lens = [len(l.split(b"\t")[0]) for l in lines]
    assert lens == sorted(lens, reverse=True)  # 간 (3 jamo) is found before 가 (2)
    enc = lambda t: b"".join(code_of[c] for c in t)
    assert enc("ㄱㅏㄴ") + b"\t" + enc("간") in lines
    assert {l.split(b"\t")[1] for l in lines} == {enc(s) for s in ne.KS}


def test_grid_rows_and_keys():
    rows = ne.grid_texts()
    assert len(rows) == 12 and all(len(r) == 17 for r in rows)
    assert set("".join(ne.PAGE1)) - {ne.SP, *ne.DEL, *ne.OK} <= set(ne.JAMO)
    assert set("".join(ne.PAGE2)) - {ne.SP} <= set(ne.KS)


def test_no_consonant_dependent_particle_after_name():
    # style.md 3.0.1: a typed name may end with or without a final consonant
    bad = re.compile(r"\^N[…！？，　]*(이라|라고|이란|은|는|이|가|을|를|과|와|으로|로|이랑|랑|이야|이오)(?![가-힣])")
    hits = []
    for f in glob.glob(str(ROOT / "text" / "ko" / "*.json")):
        for k, v in json.loads(Path(f).read_text(encoding="utf-8")).items():
            if bad.search(v.get("ko", "")):
                hits.append(k)
    assert not hits

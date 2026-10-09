"""Hangul name entry: the input grid, NAMEFONT and NAMEDIC for MAPCODE's name screen.

Established 2026-10-09 (docs/survey.md §3.1.6), MAPCODE name entry (script op
0x8C path, 0x801BD878):
- It loads \\SYSTEM.GRP\\NAMEFONT.TXT/.BIN and NAMEDIC.TXT and installs NAMEFONT
  as the field text routine's third font (after the main program's and
  MAPCODE's), so grid cells and the name being typed draw from it.
- A grid cell is read from 12 row strings (2 pages x 6 rows of 17 cells, page
  switched with Select). The cells 削除 / 決定 are recognised by their codes,
  compared at 0x801BDEF4..0x801BDF0C (`ori $at, <code as LE halfword>`), and
  U+3000 cells do nothing; any other code goes into a 10-character conversion
  buffer.
- △ looks the buffer up in NAMEDIC (`reading TAB candidate CRLF`, one candidate
  per line): a line matches when its reading is a prefix of the buffer; ○ moves
  the buffer (or the chosen candidate) into the name, at most 6 characters.
- On confirming, each name character's glyph is copied from NAMEFONT to
  0x801AEF50 (32 bytes each, length at 0x801AF026); dialogue (^N), menus and
  battle draw those stored bitmaps, so the name needs no font afterwards.

So Korean input needs no new code: the grid holds jamo, NAMEDIC turns a jamo
sequence into a syllable (ㄱㅏㄴ -> 간, also ㄱㅗㅏ -> 과), NAMEFONT carries the
2,350 KS X 1001 syllables and the jamo under the shared Hangul code table.
"""

import struct

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = ["", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"]
JAMO = sorted(set(CHO + JUNG + "".join(JONG)))
# typing aids: a compound vowel or final cluster may also be keyed as its parts
SPLIT = {"ㅘ": "ㅗㅏ", "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ", "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
         "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ", "ㄽ": "ㄹㅅ",
         "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ"}
KS = [bytes([a, b]).decode("euc-kr") for a in range(0xB0, 0xC9) for b in range(0xA1, 0xFF)]
DEFAULTS = "聖輝"  # default names (male, female) kept as in the source

SP = "　"
DEL, OK = "삭제", "결정"
# page 1: jamo; page 2: syllables common in names, picked directly
PAGE1 = [
    "ㄱㄲㄴㄷㄸ　ㄹㅁㅂㅃㅅ　ㅆㅇㅈㅉㅊ",
    "ㅋㅌㅍㅎㅄ　ㄳㄵㄶㄺㄻ　ㄼㄽㄾㄿㅀ",
    "ㅏㅐㅑㅒㅓ　ㅔㅕㅖㅗㅘ　ㅙㅚㅛㅜㅝ",
    "ㅞㅟㅠㅡㅢ　ㅣ　　　　　　　　　　",
    "　　　　　　　　　　　　　　　　　",
    "　　　　　　　　　　　　삭제　결정",
]
PAGE2 = [
    "가경규근기　김나남다도　동란리린명",
    "무문미민박　범별보빈상　서석선성세",
    "소수숙순승　시신아안연　영예오용우",
    "운원유윤은　의이인재형　조종주준지",
    "진찬창철태　하한해현혜　호화환훈희",
    "효　　　　　　　　　　　삭제　결정",
]
SPECIAL = {DEL[0]: 0x801BDEF4, DEL[1]: 0x801BDEFC, OK[0]: 0x801BDF04, OK[1]: 0x801BDF0C}
SPECIAL_SOURCE = {DEL[0]: "削", DEL[1]: "除", OK[0]: "決", OK[1]: "定"}
MAPCODE_BASE = 0x801AF034
GRID_ROWS = 0x801CB8EC  # pointer table of the 12 row strings


def chars():
    """Every character the name screen can produce (shared code table input)."""
    return set(KS) | set(JAMO)


def syllable(cho, jung, jong=""):
    return chr(0xAC00 + (CHO.index(cho) * 21 + JUNG.index(jung)) * 28 + JONG.index(jong))


def readings(s):
    """Jamo key sequences that convert to syllable `s`."""
    i = ord(s) - 0xAC00
    cho, jung, jong = CHO[i // 588], JUNG[i // 28 % 21], JONG[i % 28]
    out = set()
    for v in {jung, SPLIT.get(jung, jung)}:
        for t in {jong, SPLIT.get(jong, jong)}:
            out.add(cho + v + t)
    return out


def namedic(code_of):
    """NAMEDIC bytes: every KS syllable under each of its key sequences. Longer
    readings come first, so the first prefix match is the whole syllable typed
    (ㄱㅏㄴ gives 간 before 가)."""
    lines = sorted((r, s) for s in KS for r in readings(s))
    lines.sort(key=lambda x: -len(x[0]))
    enc = lambda t: b"".join(code_of[c] for c in t)
    return b"".join(enc(r) + b"\t" + enc(s) + b"\r\n" for r, s in lines) + b"\x1a"


def namefont(source, code_of, render):
    """(NAMEFONT.TXT, NAMEFONT.BIN): the source's kana, digits and symbols, the
    default names, then the name characters under their shared codes."""
    keep = {c: g for c, g in source.items() if c[0] < 0x88}
    keep.update({d.encode("cp932"): source[d.encode("cp932")] for d in DEFAULTS})
    for ch in sorted(chars()):
        keep[code_of[ch]] = render(ch)
    codes = list(keep)
    txt = b""
    for i in range(0, len(codes), 32):
        txt += b"".join(codes[i:i + 32]) + b"\r\n"
    return txt + b"\x1a", b"".join(keep[c] for c in codes)


def grid_texts():
    """The 12 grid row texts in table order. 삭/제/결/정 may only appear as the
    delete/confirm keys: the key check goes by code, not by cell position."""
    rows = PAGE1 + PAGE2
    for i, r in enumerate(rows):
        if len(r) != 17:
            raise ValueError(f"grid row {r!r} is not 17 cells")
        cells = r[:12] if i % 6 == 5 else r
        if any(c in cells for c in SPECIAL) or (i % 6 == 5 and r[12:] != f"{DEL}{SP}{OK}"):
            raise ValueError(f"grid row {r!r}: 삭제/결정 only in the last row's key cells")
    return rows


def le16(code):
    return code[0] | code[1] << 8


def patch_specials(data, code_of):
    """Point the 削除/決定 key checks at the Hangul cells 삭제/결정."""
    d = bytearray(data)
    for ch, at in SPECIAL.items():
        o = at - MAPCODE_BASE
        w = struct.unpack_from("<I", d, o)[0]
        if w >> 16 != 0x3401 or w & 0xFFFF != le16(SPECIAL_SOURCE[ch].encode("cp932")):
            raise ValueError(f"0x{at:x}: not `ori $at, {SPECIAL_SOURCE[ch]}`")
        struct.pack_into("<I", d, o, 0x34010000 | le16(code_of[ch]))
    return bytes(d)

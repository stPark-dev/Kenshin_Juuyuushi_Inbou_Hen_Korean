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
DEFAULTS = ("히지리", "히카루")  # default names (male 聖, female 輝 in the source), at most 6

SP = "　"
DEL, OK = "삭제", "결정"
# Syllables picked directly (no jamo composition, D39): page 1 = the kana sounds in
# gojūon order with voiced ones and contracted sounds, page 2 = ン (final ㄴ),
# the other contracted sounds and ッ (final ㅅ), as Japanese names are written.
PAGE1 = [
    "아이우에오　카키쿠케코　사시스세소",
    "타치츠테토　나니누네노　하히후헤호",
    "마미무메모　라리루레로　야유요와　",
    "가기구게고　자지즈　조　다데도　　",  # no 제: the 삭제 key is found by its code
    "바비부베보　파피푸페포　캬큐쿄샤슈",
    "쇼차추초랴　류료햐휴효　삭제　결정",
]
PAGE2 = [
    "안엔인온운　칸켄킨콘쿤　간겐긴곤군",
    "산센신손슌　잔젠진존준　탄텐톤단덴",
    "돈난넨닌논　한헨혼반벤　본분판펜　",
    "만멘민몬　　란렌린론완　갸규교　　",
    "냐뉴뇨　　　먀뮤묘　　　뱌뷰뵤　　",
    "잇텟핫깃콧　　　　　　　삭제　결정",
]
SPECIAL = {DEL[0]: 0x801BDEF4, DEL[1]: 0x801BDEFC, OK[0]: 0x801BDF04, OK[1]: 0x801BDF0C}
SPECIAL_SOURCE = {DEL[0]: "削", DEL[1]: "除", OK[0]: "決", OK[1]: "定"}
MAPCODE_BASE = 0x801AF034
GRID_ROWS = 0x801CB8EC  # pointer table of the 12 row strings


def chars():
    """Every character the name screen can produce (shared code table input):
    the KS syllables, the jamo and the grid (슌 is not in KS X 1001)."""
    return set(KS) | set(JAMO) | set("".join(PAGE1 + PAGE2)) - {SP}


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
    """(NAMEFONT.TXT, NAMEFONT.BIN): the source's kana, digits and symbols, then
    the name characters under their shared codes."""
    keep = {c: g for c, g in source.items() if c[0] < 0x88}
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


# Direct input (D39). A cell used to go into a 10-character conversion buffer that
# △ looked up in NAMEDIC; with syllables in the grid there is nothing to convert,
# so every cell takes the path a space cell takes on an empty buffer (straight
# into the name, 0x801BDF44). The △ lookup code is then unused: its first words
# become a page switch for △ (R1's code from 0x801BDC50 with v1 = 8) and a routine
# that writes the default name (up to 6 characters) where the source wrote one
# kanji (聖 / 輝 by the gender byte, at two places: entering the screen and
# confirming an empty or all-space name).
DIRECT = 0x801BDF18  # beq $a0, $at(U+3000), 0x801BDF44
CONVERT = 0x801BDD30  # △ handler (bnez $v1 at 0x801BDC40 lands here)
PAGE_SWITCH = 0x801BDC50  # R1: srl $v1, $v1, 3; xor $s1, $s1, $v1; ...
DEFAULT_SITES = (0x801BDA00, 0x801BE094)  # lui $t1 ... sh $t0, 0xe($sp): 10 words each
GENDER = 0x801AF025  # 0 male, 1 female
ZERO, AT, V1, T0, T1, T2, T3, SP_, RA = 0, 1, 3, 8, 9, 10, 11, 29, 31


def _i(op, rs, rt, imm):
    return op << 26 | rs << 21 | rt << 16 | (imm & 0xFFFF)


def _r(rs, rt, rd, sa, fn):
    return rs << 21 | rt << 16 | rd << 11 | sa << 6 | fn


def _hi(a):
    return (a + 0x8000) >> 16 & 0xFFFF


def default_routine(at):
    """Words of the default-name routine at `at` and its table (16 bytes per gender:
    6 name characters, terminator, length), copied over the caller's name buffer
    ($sp + 0 .. 0xf, length at 0xe)."""
    table = at + 0x40
    words = [
        _i(0x0F, 0, T1, _hi(GENDER)),  # lui t1
        _i(0x24, T1, T1, GENDER),  # lbu t1, lo(GENDER)(t1)
        _i(0x0F, 0, T2, _hi(table)),  # lui t2
        _i(0x09, T2, T2, table),  # addiu t2, t2, lo(table)
        _r(0, T1, T1, 4, 0x00),  # sll t1, t1, 4
        _r(T2, T1, T2, 0, 0x21),  # addu t2, t2, t1
        _i(0x23, T2, T0, 0), _i(0x23, T2, T3, 4),  # lw t0 / t3 (load delay kept)
        _i(0x2B, SP_, T0, 0), _i(0x23, T2, T0, 8),
        _i(0x2B, SP_, T3, 4), _i(0x23, T2, T3, 12),
        _i(0x2B, SP_, T0, 8),
        _r(RA, 0, 0, 0, 0x08),  # jr ra
        _i(0x2B, SP_, T3, 12),  # (delay) sw t3, 12(sp)
    ]
    return words, table


def name_entry(code_of, name):
    if not 0 < len(name) <= 6:
        raise ValueError(f"default name {name!r}: 1 to 6 characters")
    body = b"".join(code_of[c] for c in name)
    return body + bytes(12 - len(body)) + b"\0\0" + struct.pack("<H", len(name))


def patch_input(data, code_of):
    """Direct syllable input, △ as a page switch and the Korean default names."""
    d = bytearray(data)

    def word(a):
        return struct.unpack_from("<I", d, a - MAPCODE_BASE)[0]

    def put(a, w):
        struct.pack_into("<I", d, a - MAPCODE_BASE, w)

    w = word(DIRECT)
    if w >> 16 != 0x1081:
        raise ValueError(f"0x{DIRECT:x}: not `beq $a0, $at`")
    put(DIRECT, w & 0xFFFF | 0x10000000)  # beq $zero, $zero: always
    if word(0x801BDC40) >> 16 != 0x1460 or word(CONVERT) != 0x3C08801B:
        raise ValueError("△ handler not where expected")
    put(CONVERT, 0x08000000 | (PAGE_SWITCH >> 2 & 0x3FFFFFF))  # j PAGE_SWITCH
    put(CONVERT + 4, _i(0x0D, ZERO, V1, 8))  # (delay) ori v1, zero, 8: as if R1
    routine = CONVERT + 8
    words, table = default_routine(routine)
    for k, x in enumerate(words):
        put(routine + 4 * k, x)
    d[table - MAPCODE_BASE:table - MAPCODE_BASE + 32] = b"".join(name_entry(code_of, n) for n in DEFAULTS)
    for site in DEFAULT_SITES:
        if word(site) != 0x3C09801B or word(site + 36) != 0xA7A8000E:
            raise ValueError(f"0x{site:x}: default name code not found")
        put(site, 0x0C000000 | (routine >> 2 & 0x3FFFFFF))  # jal routine
        for k in range(1, 10):
            put(site + 4 * k, 0)
    return bytes(d)

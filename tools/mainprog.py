"""Main program (unpacked from SCPS_100.48) and the menu fonts it draws with.

Established 2026-10-09 (docs/survey.md §3.1.5): the boot executable unpacks its
blob at file 0xA48 to 0x8000FFF8. Menus draw through MAPCODE's general text
routine, which looks a code up in the main program's font first, then in
MAPCODE's built-in font, then in the font at *(0x801CD760) (unconfirmed,
likely the scene font). A Hangul code that is
also in either menu font would therefore show that font's character in a menu,
so the shared Hangul code table keeps clear of both lists.
"""

import bootlz
import grparc
import iso

BLOB = 0xA48
BASE = 0x8000FFF8
FONT_LIST = 0x80039044  # SJIS list, CRLF-separated lines, ends at 0 or 0x1A
FONT_GLYPHS, FONT_COUNT = 0x80033C64, 671
MAPCODE_BASE = 0x801AF034
MAPCODE_FONT_LIST = 0x801CEAC4


def exe_name(disc):
    return next(n for n in disc.files if n.startswith("SCPS"))


def unpack(exe):
    return bootlz.decode(exe, BLOB)[0]


def font_list(data, at):
    """Codes (2-byte SJIS) of a font character list at offset `at`."""
    out = []
    while True:
        c = data[at:at + 2]
        if c[:1] in (b"\0", b"\x1a"):
            return out
        if c != b"\r\n":
            out.append(bytes(c))
        at += 2


def menu_font_codes(raw, disc):
    """Every code in the main program's font and in MAPCODE's built-in font."""
    main = unpack(iso.read_file(raw, disc, exe_name(disc)))
    sysgrp = grparc.parse(iso.read_file(raw, disc, "SYSTEM.GRP"))
    mapcode = bootlz.decode(sysgrp.get("MAPCODE.Z32"), 0)[0]
    codes = font_list(main, FONT_LIST - BASE)
    if len(codes) != FONT_COUNT:
        raise ValueError(f"main program font: {len(codes)} characters, expected {FONT_COUNT}")
    return set(codes) | set(font_list(mapcode, MAPCODE_FONT_LIST - MAPCODE_BASE))


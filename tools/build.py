"""Product build: original disc image + text/ko translations -> patched image.

Usage:
  python3 tools/build.py --src original/<image>.bin --out build/kenshin_ko.bin \
      --galmuri ../galmuri/Galmuri14.bdf [--ko-dir text/ko] [--policy dev|release]

dev uses draft and reviewed translations and reports problems; release uses
only reviewed translations and fails on any problem. Every disc change goes
through iso.plan/iso.apply (expected-source checks and final diff audit).
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import bootlz
import exetext
import grparc
import iso
import kfont
import koenc
import mainprog
import nameentry
import ovltext
import menuwin
import refs
import scenefont
import script
import textio

SOURCE_SHA256 = "738f320c105dc7ab63515553112bd78a62041305ee4f3ebfeaf5b7df8bb2abd8"
VERIFIED_MAX_GROUP = 435372  # translated ZROUP24, loaded and shown at runtime (original max 382,396)
POLICIES = {"dev": {"draft", "reviewed"}, "release": {"reviewed"}}


@dataclass(frozen=True)
class Assets:
    font: dict
    box: tuple
    namefont: dict
    menu_codes: frozenset = frozenset()  # codes in the menu fonts, never given to Hangul


def check_source(raw):
    got = hashlib.sha256(raw).hexdigest()
    if got != SOURCE_SHA256:
        raise ValueError(f"source SHA-256 {got} does not match the supported image {SOURCE_SHA256}")


def load_assets(raw, disc, galmuri_path):
    sysgrp = grparc.parse(iso.read_file(raw, disc, "SYSTEM.GRP"))
    nf = scenefont.load_namefont(sysgrp.get("NAMEFONT.TXT"), sysgrp.get("NAMEFONT.BIN"))
    font = kfont.load_bdf(galmuri_path)
    return Assets(font=font, box=kfont.hangul_box(font), namefont=nf,
                  menu_codes=frozenset(mainprog.menu_font_codes(raw, disc)))


def reserved_codes(g, ko_map):
    """SJIS codes a scene keeps as Japanese: untranslated strings and non-Hangul in translations."""
    reserved = set()
    for s in g.strings:
        if s.offset not in ko_map:
            reserved |= {t.raw for t in script.tokenize(s.raw) if t.kind == "char"}
    for t in ko_map.values():
        reserved |= {c.encode("cp932") for c in t if ord(c) >= 0x80 and not koenc.is_hangul(c) and _sjis(c)}
    return reserved


def shared_codes(scenes, menu_codes=frozenset(), extra=()):
    """One Hangul code table for every scene (and the menus): [(g, ko_map)] -> {syllable: code}.
    Menus look codes up in the menu fonts before the scene font, so a code must mean
    the same syllable everywhere and stay clear of every Japanese character in use."""
    hangul, reserved = {c for t in extra for c in t if koenc.is_hangul(c)}, set(menu_codes)
    for g, ko_map in scenes:
        hangul |= {c for t in ko_map.values() for c in t if koenc.is_hangul(c)}
        reserved |= reserved_codes(g, ko_map)
    return koenc.assign_codes(hangul, reserved)


def scene_build(g, ko_map, assets, code_of=None):
    """Apply {offset: korean text} to a parsed GROUP; return (bytes, report).
    `code_of` is the shared Hangul code table; without it the scene gets its own."""
    originals = {s.offset: s.raw for s in g.strings}
    slots = {s.offset: s.slot for s in g.strings}
    hangul = {c for t in ko_map.values() for c in t if koenc.is_hangul(c)}
    if code_of is None:
        code_of = shared_codes([(g, ko_map)], assets.menu_codes)
    raws = {off: koenc.encode(text, originals[off], code_of) for off, text in ko_map.items()}
    missing = sorted(c for c in hangul if c not in assets.font)
    if missing:
        raise ValueError(f"Hangul font has no glyph for {''.join(missing)}")
    hglyphs = {code_of[c]: kfont.render(assets.font[c], assets.box) for c in hangul}
    # a moved string's old slot gets the start of its translation, so a reference we
    # do not know of still finds glyphs, without keeping the source's kanji in the font
    moved = [o for o, r in sorted(raws.items()) if len(r) >= slots[o]]
    old = {o: _prefix(raws[o], slots[o] - 1) for o in moved}
    # font covers the whole final pool: in-place text, old slots, then appended text
    final = [old[s.offset] if s.offset in old else raws.get(s.offset, s.raw) for s in g.strings]
    final += [raws[o] for o in moved]
    codes, glyphs = scenefont.build(final, hglyphs, dict(zip(g.font_codes, g.font_glyphs)), assets.namefont)
    out = refs.rebuild(g, raws, codes, glyphs, old)
    patches, unfit = menuwin.fit(g, ko_map)
    out = menuwin.apply(out, patches)  # code bytes keep their offsets in the rebuilt file
    report = {
        "translated": len(raws),
        "in_place": sum(1 for o, r in raws.items() if len(r) < slots[o]),
        "appended": sum(1 for o, r in raws.items() if len(r) >= slots[o]),
        "glyphs": len(codes),
        "size": len(out),
        "windows": len(patches),
    }
    if unfit:
        report["menu_problems"] = [f"0x{off:x}: {'; '.join(p)}" for off, p in unfit]
    return out, report


MENU_FILES = ("MAIN", "MAPCODE", "BTLCODE")
# the name-entry grid rows are generated (nameentry), not translated
GRID_IDS = [f"MAPCODE:{a:x}" for a in (0x801CBC51, 0x801CBC74, 0x801CBC97, 0x801CBCBA, 0x801CBCDD, 0x801CBD00,
                                       0x801CBD23, 0x801CBD46, 0x801CBD69, 0x801CBD8C, 0x801CBDAF, 0x801CBDD2)]


def menu_sources(raw, disc):
    """Unpacked main program and overlays with their translatable rows."""
    exe = iso.read_file(raw, disc, mainprog.exe_name(disc))
    sysgrp = grparc.parse(iso.read_file(raw, disc, "SYSTEM.GRP"))
    data = {"MAIN": mainprog.unpack(exe)}
    for n in ("MAPCODE", "BTLCODE"):
        data[n] = bootlz.decode(sysgrp.get(f"{n}.Z32"), 0)[0]
    rows = {"MAIN": exetext.extract(data["MAIN"])}
    rows.update({n: ovltext.extract(n, data[n]) for n in ("MAPCODE", "BTLCODE")})
    return exe, sysgrp, data, rows


def menu_build(exe, sysgrp, data, rows, ko, code_of, assets):
    """Menu text of the main program, MAPCODE and BTLCODE plus both menu fonts ->
    {disc file: bytes}. Battle draws with the main program's font only, the field
    with it and then MAPCODE's font, so Hangul of the main program and BTLCODE goes
    into the first and Hangul only MAPCODE uses into the second."""
    limit = {r["id"]: r["limit"] for n in rows for r in rows[n]}
    enc = {n: {sid: exetext.encode(t, code_of, limit[sid]) for sid, t in ko[n].items()} for n in MENU_FILES}
    hangul = {n: {c for t in ko[n].values() for c in t if koenc.is_hangul(c)} for n in MENU_FILES}
    missing = sorted(c for h in hangul.values() for c in h if c not in assets.font)
    if missing:
        raise ValueError(f"Hangul font has no glyph for {''.join(missing)}")

    def render(c):
        return kfont.render(assets.font[c], assets.box)

    main, mapcode = data["MAIN"], data["MAPCODE"]
    btl = ovltext.apply("BTLCODE", data["BTLCODE"], enc["BTLCODE"])
    old = dict(zip(exetext.font_codes(main), _glyphs(main)))
    mold = ovltext.mapcode_font(mapcode)
    # main program font
    efont = {c: old[c] for c in exetext.kept_codes(main, btl)}
    efont.update({code_of[c]: render(c) for c in sorted(hangul["MAIN"] | hangul["BTLCODE"])})

    def fill(font, texts):  # punctuation the source fonts lack (，．) comes from NAMEFONT
        used = {r[i:i + 2] for r in texts for i in range(0, len(r), 2)}
        for c in sorted(used - set(font)):
            g = old.get(c) or mold.get(c) or assets.namefont.get(c)
            if g is None:
                raise ValueError(f"no glyph for {c.decode('cp932')}")
            font[c] = g

    fill(efont, list(enc["MAIN"].values()) + list(enc["BTLCODE"].values()))
    # MAPCODE font: its kana and symbols, then whatever its strings need that the
    # main program font does not have
    new_map = ovltext.apply("MAPCODE", mapcode, enc["MAPCODE"])
    mfont = {c: g for c, g in mold.items() if c[0] < 0x88}
    final = [raw_ for a, raw_, _ in ovltext.movable("MAPCODE", new_map)] + [r for _, r, _ in ovltext.fixed("MAPCODE", new_map)]
    # the grid rows draw from NAMEFONT, which the name screen loads
    grid = {enc["MAPCODE"][g] for g in GRID_IDS}
    need = {r[i:i + 2] for r in final if r not in grid for i in range(0, len(r), 2)} - set(efont) - set(mfont)
    by_code = {code_of[c]: c for c in hangul["MAPCODE"]}
    for c in sorted(need):
        mfont[c] = render(by_code[c]) if c in by_code else (mold.get(c) or old.get(c) or assets.namefont[c])
    new_main = exetext.apply(main, enc["MAIN"], efont)
    new_map = ovltext.set_mapcode_font(new_map, mfont)
    new_map = nameentry.patch_specials(new_map, code_of)
    nf_txt, nf_bin = nameentry.namefont(assets.namefont, code_of, render)
    packed = bootlz.encode(new_main)
    room = len(exe) - mainprog.BLOB
    if len(packed) > room:
        raise ValueError(f"packed main program is {len(packed)} bytes, room {room}")
    grp = sysgrp.replace("MAPCODE.Z32", bootlz.encode(new_map)).replace("BTLCODE.Z32", bootlz.encode(btl))
    grp = grp.replace("NAMEFONT.TXT", nf_txt).replace("NAMEFONT.BIN", nf_bin)
    grp = grp.replace("NAMEDIC.TXT", nameentry.namedic(code_of))
    report = {"translated": {n: len(enc[n]) for n in MENU_FILES}, "main_font": len(efont),
              "mapcode_font": len(mfont), "packed": len(packed)}
    return {"exe": exe[:mainprog.BLOB] + packed + bytes(room - len(packed)), "SYSTEM.GRP": grparc.build(grp)}, report


def _glyphs(main):
    o = mainprog.FONT_GLYPHS - mainprog.BASE
    return [main[o + 32 * i:o + 32 * i + 32] for i in range(len(exetext.font_codes(main)))]


def _prefix(raw, room):
    """The longest run of whole tokens of `raw` that is at most `room` bytes."""
    out = b""
    for t in script.tokenize(raw):
        if len(out) + len(t.raw) > room:
            break
        out += t.raw
    return out


def _sjis(c):
    try:
        return len(c.encode("cp932")) == 2
    except UnicodeEncodeError:
        return False


def build(src, ko_dir, out, statuses, assets=None, galmuri=None):
    raw = Path(src).read_bytes()
    check_source(raw)
    disc = iso.load(raw)
    if assets is None:
        assets = load_assets(raw, disc, galmuri)
    changes, problems, warnings, scenes = {}, [], [], {}
    work = []
    for name in sorted(n for n in disc.files if n.startswith("ZROUP") and n.endswith(".GRP")):
        scene = name[:-4]
        grp = grparc.parse(iso.read_file(raw, disc, name))
        member = scene.replace("ZROUP", "GROUP") + ".BIN"
        g = script.parse_group(grp.get(member))
        rows = textio.extract(scene, g)
        kof = Path(ko_dir) / f"{scene}.json"
        ko = json.loads(kof.read_text(encoding="utf-8")) if kof.is_file() else {}
        ko_map, probs = textio.usable_translations(rows, ko, statuses)
        problems += probs
        if ko_map:
            work.append((name, scene, grp, member, g, ko_map))
    exe, sysgrp, data, menu_rows = menu_sources(raw, disc)
    menu_ko = {}
    for n in MENU_FILES:
        f = Path(ko_dir) / f"{n}.json"
        menu_ko[n], probs = textio.usable_translations(menu_rows[n], json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}, statuses)
        problems += probs
    names = any(menu_ko.values())  # Hangul name entry comes with the menu translation
    if names:
        menu_ko["MAPCODE"].update(dict(zip(GRID_IDS, nameentry.grid_texts())))
    extra = [t for n in MENU_FILES for t in menu_ko[n].values()] + (["".join(sorted(nameentry.chars()))] if names else [])
    reserved_names = frozenset(d.encode("cp932") for d in nameentry.DEFAULTS)
    code_of = shared_codes([(g, ko_map) for *_, g, ko_map in work], assets.menu_codes | reserved_names, extra)
    if any(menu_ko.values()):
        try:
            files, rep = menu_build(exe, sysgrp, data, menu_rows, menu_ko, code_of, assets)
            changes[mainprog.exe_name(disc)] = files["exe"]
            changes["SYSTEM.GRP"] = files["SYSTEM.GRP"]
            scenes["MENU"] = rep
        except (ValueError, KeyError) as e:
            problems.append(f"MENU: {e}")
    for name, scene, grp, member, g, ko_map in work:
        try:
            new, rep = scene_build(g, ko_map, assets, code_of)
        except ValueError as e:
            problems.append(f"{scene}: {e}")
            continue
        scenes[scene] = rep
        problems += [f"{scene}: menu {p}" for p in rep.get("menu_problems", [])]
        if rep["size"] > VERIFIED_MAX_GROUP:
            warnings.append(f"{scene}: {member} is {rep['size']} bytes, above the verified maximum {VERIFIED_MAX_GROUP}")
        changes[name] = grparc.build(grp.replace(member, new))
    image = iso.apply(raw, iso.plan(raw, disc, changes) if changes else [])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)
    out.with_suffix(".cue").write_text(f'FILE "{out.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    return {"problems": problems, "warnings": warnings, "scenes": scenes, "sha256": hashlib.sha256(image).hexdigest()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--galmuri", required=True)
    ap.add_argument("--ko-dir", default="text/ko")
    ap.add_argument("--policy", choices=sorted(POLICIES), default="dev")
    a = ap.parse_args(argv)
    rep = build(a.src, a.ko_dir, a.out, POLICIES[a.policy], galmuri=a.galmuri)
    for p in rep["problems"]:
        print("PROBLEM", p)
    for w in rep["warnings"]:
        print("WARNING", w)
    for s, r in rep["scenes"].items():
        print(s, r)
    print("output sha256", rep["sha256"])
    if a.policy == "release" and rep["problems"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

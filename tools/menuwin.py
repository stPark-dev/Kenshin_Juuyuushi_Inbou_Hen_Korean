"""Menu window widths and the game's own line wrap for menu strings (^4...).

Runtime-established (ZROUP24 reading menu, 2026-10-08): script op 0x47 sets a
window as `47 win x y w h` in 8 px units (dialogue: 01 14 24 06 = 288 px wide,
3 lines), and text that does not fit wraps per character, ignoring words. Some
source menus rely on that wrap instead of a break: `c7マッチにまつわる珍話c9自転車見聞録`
is two 160 px options in a 160 px window. A line that reaches the window edge
wraps by itself, so an explicit break right after it leaves a blank line
(ZROUP95, as in dialogue). A translation must keep every option on its own
line(s) the same way, so menu strings are laid out here with their window, and
windows too narrow for the translation are widened in the script.

A string's window candidates are the nearest preceding 0x47 (same window number)
before each 0x49 that shows it, or for a string table, before each user of the
table. Redraw routines often reuse a window opened elsewhere, so candidates that
share strings are grouped and widened together.
"""

import re
import struct

import koenc

COLOR = re.compile(r"[cC][0-9a-fA-F]")
BREAKS = ("^c", "^C", "^!")
SEARCH = 0x400  # bytes of code searched back for the window op


def _sites(d, value, end):
    pat, out = struct.pack("<I", value), []
    q = d.find(pat, 16, end)
    while q >= 0:
        out.append(q)
        q = d.find(pat, q + 1, end)
    return out


def _window_before(d, code, win=None):
    for a in range(code - 6, max(15, code - SEARCH - 1), -1):
        if d[a] == 0x47 and d[a + 1] <= 4 and (win is None or d[a + 1] == win):
            x, y, w, h = d[a + 2 : a + 6]
            if 0 < w <= 40 and 0 < h <= 30:
                return {"at": a, "win": d[a + 1], "x": x, "y": y, "w": w, "h": h}
    return None


def _window_called(d, user, end):
    """A menu routine that loads a string table and then calls a helper which opens
    the window (ZROUP24 reading menus: `5d 31 4f 70 <table>` then `2d 00 70 <helper>`).
    The helper may first show a line in the standard dialogue box (36 x 6), so that
    window is skipped."""
    for a in range(user + 4, min(end, user + 24)):
        if d[a : a + 3] == bytes((0x2D, 0x00, 0x70)):
            target = struct.unpack_from("<I", d, a + 3)[0]
            if 16 <= target < end:
                for b in range(target, min(end - 6, target + 0x100)):
                    if (d[b] == 0x47 and d[b + 1] <= 4 and 0 < d[b + 4] <= 40 and 0 < d[b + 5] <= 30
                            and (d[b + 4], d[b + 5]) != (0x24, 6)):
                        x, y, w, h = d[b + 2 : b + 6]
                        return {"at": b, "win": d[b + 1], "x": x, "y": y, "w": w, "h": h}
            return None
    return None


def _window_after(d, user, end):
    """A window opened right after the table is loaded (party menu: `31 41 70 <table>`
    `6f 42 51 47 00 01 01 0c 0a`)."""
    for b in range(user + 4, min(end - 6, user + 16)):
        if (d[b] == 0x47 and d[b + 1] <= 4 and 0 < d[b + 4] <= 40 and 0 < d[b + 5] <= 30
                and (d[b + 4], d[b + 5]) != (0x24, 6)):
            x, y, w, h = d[b + 2 : b + 6]
            return {"at": b, "win": d[b + 1], "x": x, "y": y, "w": w, "h": h}
    return None


def windows(g):
    """{string offset: [window dicts]} for menu strings, candidates in site order."""
    d, end = g.data, g.header[2]
    starts = {s.offset for s in g.strings}
    out = {}
    for s in g.strings:
        if not s.raw.startswith(b"^4"):
            continue
        found = []
        for q in _sites(d, s.offset, end):
            if q >= 2 and d[q - 2] == 0x49 and d[q - 1] <= 4:
                found.append(_window_before(d, q - 2, d[q - 1]))
            else:
                t = q  # table entry: walk back to the table start, find its users
                while t - 4 >= 16 and struct.unpack_from("<I", d, t - 4)[0] in starts:
                    t -= 4
                for u in _sites(d, t, end):
                    if u not in range(t, q + 4):
                        found.append(_window_after(d, u, end) or _window_called(d, u, end) or _window_before(d, u))
        found = list({w["at"]: w for w in found if w}.values())
        if found:
            out[s.offset] = found
    return out


def layout(text, width_px, auto=None, name_px=koenc.NAME_PX):
    """Lines as the game draws them, each a list of (option index, token). A
    character that does not fit starts a new line, a line that reaches the edge
    ends by itself, and ^c/^C/^! always break (a blank line after a full one).
    An option starts at each color code that follows text. If `auto` is a list,
    it receives the indexes of lines that ended by wrapping. ^N (a character
    name) is `name_px` wide."""
    body = re.sub(r"\^[sS]$", "", text[2:] if text.startswith("^4") else text)
    lines, cur, x, opt, seen_text = [], [], 0, 0, False
    auto = [] if auto is None else auto
    for t in koenc.tokens(body):
        if t in BREAKS:
            lines.append(cur)
            cur, x = [], 0
            continue
        if COLOR.fullmatch(t) and seen_text:
            opt += 1
            seen_text = False
        w = name_px if t == "^N" else koenc.width(t)
        if w and x and x + w > width_px:
            auto.append(len(lines))
            lines.append(cur)
            cur, x = [], 0
        if w and t != koenc.SP:
            seen_text = True
        cur.append((opt, t))
        x += w
        if w and x >= width_px:
            auto.append(len(lines))
            lines.append(cur)
            cur, x = [], 0
    if cur or not lines:
        lines.append(cur)
    return lines


def _opts(line):
    return {o for o, t in line if koenc.width(t) and t not in (" ", koenc.SP) and not t.startswith("N")}


def problems(src, ko, win, ko_win=None):
    """Layout problems of a translated menu string, judged against the source in its
    original window; `ko_win` is the (possibly widened) window the translation gets."""
    W = (ko_win or win)["w"] * 8
    # the source is judged with a one-character name, the translation with the full budget
    sl, kl = layout(src, win["w"] * 8, name_px=16), layout(ko, W)
    out = []
    room = max(len(sl), win["h"] // 2)  # h counts 8 px rows, a text line is 16 px
    if len(kl) > room:
        out.append(f"{len(kl)} lines in a {W}px window, room for {room}")

    def split(text, width, name_px):  # options cut by the game's own wrap
        auto = []
        lines = layout(text, width, auto, name_px)
        return sum(1 for i in auto if i + 1 < len(lines) and _opts(lines[i]) & _opts(lines[i + 1]))

    ks, ss = split(ko, W, koenc.NAME_PX), split(src, win["w"] * 8, 16)
    if ks > ss:
        out.append(f"{ks} option(s) wrap inside a {W}px window, source {ss}")
    if max((len(_opts(l)) for l in kl), default=0) > max((len(_opts(l)) for l in sl), default=0):
        out.append(f"options share a line in a {W}px window that the source keeps apart")
    return out


def render(text, width_px):
    return ["".join(t for _, t in line) for line in layout(text, width_px)]


SCREEN_UNITS = 40  # 320 px


def fit(g, texts):
    """Widen menu windows so every translated menu string lays out like its source.

    `texts` maps string offset -> translated text (untranslated strings keep the
    source). Returns (patches, unfit): patches are {at, old, new} with (x, w) in
    8 px units for each 0x47 op that must grow; a window keeps its left edge when
    it starts at the screen margin (x <= 1), otherwise it grows around its centre.
    unfit lists (offset, problems) that no width up to the screen fixes."""
    wins = windows(g)
    ops, group = {}, {}  # union of window ops that share a string

    def find(a):
        while group.setdefault(a, a) != a:
            a = group[a]
        return a

    for cands in wins.values():
        for w in cands:
            ops[w["at"]] = w
        for w in cands[1:]:
            group[find(w["at"])] = find(cands[0]["at"])
    members = {}
    for off, cands in wins.items():
        members.setdefault(find(cands[0]["at"]), []).append(off)
    raw = {s.offset: s.raw.decode("cp932") for s in g.strings}
    patches, unfit = [], []
    for root, offs in sorted(members.items()):
        offs = [o for o in offs if o in texts]
        if not offs:
            continue
        mine = [w for a, w in ops.items() if find(a) == root]

        def ok(d):  # every string fits every candidate window grown by d units
            return all(not problems(raw[o], texts[o], w, dict(w, w=w["w"] + d)) for o in offs for w in wins[o])

        room = SCREEN_UNITS - 2 - max(w["w"] for w in mine)
        delta = next((d for d in range(0, room + 1) if ok(d)), None)
        if delta is None:
            unfit += [(o, p) for o in offs for w in wins[o][:1]
                      for p in [problems(raw[o], texts[o], w, dict(w, w=w["w"] + room))] if p]
            continue
        for w in sorted(mine, key=lambda w: w["at"]):
            if not delta:
                break
            nw = w["w"] + delta
            x = w["x"] if w["x"] <= 1 else max(1, w["x"] - delta // 2)
            x = min(x, SCREEN_UNITS - 1 - nw)
            patches.append({"at": w["at"], "old": (w["x"], w["w"]), "new": (x, nw)})
    return patches, unfit


def apply(data, patches):
    """Write fitted window ops (x at +2, w at +4) into GROUP bytes."""
    out = bytearray(data)
    for p in patches:
        at, (ox, ow), (nx, nw) = p["at"], p["old"], p["new"]
        if out[at] != 0x47 or out[at + 2] != ox or out[at + 4] != ow:
            raise ValueError(f"window op at 0x{at:x} is not 47 _ {ox:02x} _ {ow:02x}")
        out[at + 2], out[at + 4] = nx, nw
    return bytes(out)

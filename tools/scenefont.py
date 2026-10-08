"""Scene font block contents from the final strings of a GROUP file.

Code list: every 2-byte character in pool order, first appearance first
(established: matches the stored list in all 58 GROUP files). Glyph sources in
priority order: Hangul glyphs for assigned codes, the scene's original glyph
(keeps game-specific glyphs such as the heart drawn for 0x8197), NAMEFONT.
A code with no glyph fails the build.
"""

import script


def load_namefont(txt, bin_):
    chars = txt.decode("cp932").rstrip("\x1a").replace("\r", "").replace("\n", "")  # DOS EOF marker
    odd = [c for c in chars if len(c.encode("cp932")) != 2]
    if odd:
        raise ValueError(f"NAMEFONT: unexpected characters {odd[:5]!r}")
    if len(bin_) != 32 * len(chars):
        raise ValueError(f"NAMEFONT: {len(chars)} characters but {len(bin_)} glyph bytes")
    return {ch.encode("cp932"): bin_[32 * i : 32 * (i + 1)] for i, ch in enumerate(chars)}


def build(strings, hangul, scene, namefont):
    codes, seen = [], set()
    for raw in strings:
        for t in script.tokenize(raw):
            if t.kind == "char" and t.raw not in seen:
                seen.add(t.raw)
                codes.append(t.raw)
    glyphs, missing = [], []
    for c in codes:
        g = hangul.get(c) or scene.get(c) or namefont.get(c)
        if g is None:
            missing.append(c.hex())
        glyphs.append(g)
    if missing:
        raise ValueError(f"no glyph for codes: {', '.join(missing)}")
    return codes, glyphs

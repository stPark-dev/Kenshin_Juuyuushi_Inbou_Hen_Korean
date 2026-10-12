"""Team battle banners 総当たり戦 / 勝ち抜き戦: export for redrawing, import of the redrawn pictures.

  python tools/battlebanner.py export [OUT]   original banners, upscaled, to redraw elsewhere
  python tools/battlebanner.py check  [OUT]   how the pictures in assets/banners/ come back

Established 2026-10-12 (docs/survey.md §3.1.13):
- The lineup screen before a team battle (script op 0x83: type 0x50, background,
  enemy groups, then field exit 3) shows one of two banners. The lineup is scene
  0's own script (GROUP00.BIN sits at the scene base meanwhile and picks the banner
  at 0xA20-0xA46 from the battle type), and the banners are stored only there,
  raw, each as two blocks of u32 kind, u16 128, u16 32: kind 1 = its own
  256-colour CLUT (512 bytes) at Banner.clut, kind 0 = 128x32 8bpp pixels at
  Banner.image. 総当たり戦 is gold on brown, 勝ち抜き戦 purple and cyan (original
  disc, battle type forced to 0x90). A test image with banner 0 striped showed
  the stripes in ZROUP01's team battle (DuckStation).
- Index 0 (colour 0x0000) is transparent (the lineup draws a plate behind the
  banner, which shows there); each picture uses 33 distinct colours.

A redrawn picture saved as assets/banners/<name>.png (any size, 4:1, RGBA or RGB
with the banner's key colour for transparency) is scaled back to 128x32; each pixel takes the
nearest colour its original already uses, so the CLUTs are never changed.
"""

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "assets" / "banners"
W, H = 128, 32
MAGENTA, GREEN = (255, 0, 255), (0, 255, 0)  # transparency keys where a picture has no alpha
SCALE = 8
assert SCALE >= 4


@dataclass(frozen=True)
class Banner:
    name: str
    clut: int  # block headers (8 bytes) in GROUP00.BIN
    image: int
    key: tuple  # far from every colour of the banner
    jp: str
    ko: str  # as the dialogue names it (ZROUP13/14/42/47, D42)


BANNERS = (
    Banner("league", 0x16F38, 0x17140, MAGENTA, "総当たり戦", "전원대전"),
    Banner("kachinuki", 0x18148, 0x18350, GREEN, "勝ち抜き戦", "승자진출전"),  # purple: magenta would clash
)


def _check(group00):
    for b in BANNERS:
        for at, kind in ((b.clut, 1), (b.image, 0)):
            if struct.unpack_from("<IHH", group00, at) != (kind, W, H):
                raise ValueError(f"GROUP00.BIN: no {b.name} banner block {kind} at 0x{at:x}")
        if struct.unpack_from("<H", group00, b.clut + 8)[0] != 0:
            raise ValueError(f"GROUP00.BIN: {b.name} CLUT entry 0 is not transparent")


def _clut(group00, b):
    return np.frombuffer(group00, "<u2", 256, b.clut + 8).astype(np.int32)


def _pixels(group00, b):
    return np.frombuffer(group00, np.uint8, W * H, b.image + 8).reshape(H, W)


def rgba(idx, group00, b):
    """Colours (RGBA, alpha 0 or 255) of indices under banner b's CLUT; 0x0000 is transparent."""
    c = _clut(group00, b)[idx]
    return np.stack([(c & 31) * 8, (c >> 5 & 31) * 8, (c >> 10 & 31) * 8, np.where(c == 0, 0, 255)], -1).astype(np.uint8)


def export(group00):
    """{name: 32x128 RGBA} of the source banners."""
    _check(group00)
    return {b.name: rgba(_pixels(group00, b), group00, b) for b in BANNERS}


def palette_indices(group00, b):
    """One index per distinct opaque colour banner b uses (the lowest such index)."""
    _check(group00)
    clut = _clut(group00, b)
    used = np.unique(_pixels(group00, b))
    first = {}
    for i in used.tolist():
        if clut[i] != 0:
            first.setdefault(int(clut[i]), i)
    return sorted(first.values())


def indices(img, group00, b):
    """A picture (RGB or RGBA, any size) as 32x128 indices of banner b: scaled back, each
    pixel voted by the centre of its cell, snapped to b's colours; transparent -> 0."""
    img = np.asarray(img)
    k = SCALE
    big = cv2.resize(img.astype(np.float32), (W * k, H * k), interpolation=cv2.INTER_LINEAR)
    rgb = big[..., :3]
    clear = np.abs(rgb - np.array(b.key, np.float32)).max(-1) < 48
    if img.shape[-1] == 4:
        clear |= big[..., 3] < 128
    cand = palette_indices(group00, b)
    pal = rgba(np.array(cand), group00, b)[:, :3].astype(np.float32)
    near = np.argmin(((rgb[:, :, None, :] - pal[None, None]) ** 2).sum(-1), -1)
    label = np.where(clear, len(cand), near)  # last label: transparent
    q = k // 4  # SCALE >= 4, or the centre slice is empty
    cells = label.reshape(H, k, W, k)[:, q:-q, :, q:-q].transpose(0, 2, 1, 3).reshape(H, W, -1)
    votes = np.apply_along_axis(np.bincount, -1, cells, minlength=len(cand) + 1)
    lut = np.array(cand + [0], np.uint8)
    return lut[np.argmax(votes, -1)]


def _read(path):
    """RGB or RGBA uint8 of a picture; refuses one that is not about 4:1 like the banner."""
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise ValueError(f"{path}: not a readable picture")
    if im.dtype == np.uint16:
        im = (im >> 8).astype(np.uint8)
    elif im.dtype != np.uint8:
        raise ValueError(f"{path}: unsupported bit depth {im.dtype}")
    h, w = im.shape[:2]
    if abs(w / h - W / H) > 0.05 * W / H:
        raise ValueError(f"{path}: {w}x{h} is not 4:1 like the {W}x{H} banner; crop it first")
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    code = cv2.COLOR_BGRA2RGBA if im.shape[-1] == 4 else cv2.COLOR_BGR2RGB
    return cv2.cvtColor(im, code)


def apply(group00, art_dir=ART):
    """(GROUP00.BIN with every banner that has a picture in art_dir replaced, [names])."""
    _check(group00)
    out = bytearray(group00)
    done = []
    for b in BANNERS:
        p = Path(art_dir) / f"{b.name}.png"
        if not p.is_file():
            continue
        out[b.image + 8:b.image + 8 + W * H] = indices(_read(p), group00, b).tobytes()
        done.append(b.name)
    return bytes(out), done


def _load():
    import glob

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import grparc
    import iso

    raw = Path(sorted(glob.glob(str(ROOT / "original" / "*.bin")))[0]).read_bytes()
    return grparc.parse(iso.read_file(raw, iso.load(raw), "ZROUP00.GRP")).get("GROUP00.BIN")


def _save(path, pic, key, k=SCALE):
    pic = np.kron(pic, np.ones((k, k, 1), np.uint8))
    pic[pic[..., 3] == 0, :3] = key  # opaque RGB: the transparent part shows in the key colour
    cv2.imwrite(str(path), cv2.cvtColor(pic[..., :3], cv2.COLOR_RGB2BGR))


def cli_export(out):
    out.mkdir(parents=True, exist_ok=True)
    pics = export(_load())
    for b in BANNERS:
        _save(out / f"{b.name}.png", pics[b.name], b.key)
    keys = {MAGENTA: "분홍색 #FF00FF", GREEN: "초록색 #00FF00"}
    rows = "\n".join(f"| `{b.name}.png` | {b.jp} | **{b.ko}** | {keys[b.key]} |" for b in BANNERS)
    (out / "README.md").write_text(PROMPT.format(scale=SCALE, w=W * SCALE, h=H * SCALE, table=rows), encoding="utf-8")
    print(f"{len(BANNERS)} banners -> {out}")


def cli_check(out):
    out = out / "check"
    out.mkdir(parents=True, exist_ok=True)
    g = _load()
    new, done = apply(g)
    before, after = export(g), export(new)
    for b in BANNERS:
        if b.name in done:
            gap = np.zeros((H, 2, 4), np.uint8)
            _save(out / f"{b.name}.png", np.hstack([before[b.name], gap, after[b.name]]), b.key)
    print(f"{len(done)} pictures in {ART} -> {out}")


PROMPT = """# 전투 제목 그림 다시 그리기

`league.png`·`kachinuki.png` = 원본 그림({scale}배 확대, {w}×{h}). 그림마다 투명색이 다릅니다(아래 표:
전원대전은 분홍, 보라색 그림인 승자진출전은 초록). 투명한 곳에는 게임이 뒤에 까는 판이 보입니다.
두 그림은 팔레트가 따로 있어서 전원대전은 금색·갈색, 승자진출전은 보라·하늘색으로만 표현됩니다.

## ChatGPT에 보낼 요청 (그림마다 한 장씩)

> 첨부한 픽셀아트 제목 그림의 일본어 글자를 한국어 "<한국어>"로 바꿔 줘.
> - 이미지 크기와 비율({w}×{h})은 그대로. 잘라내거나 여백을 넣지 말 것.
> - 판과 테두리, 글자의 색·그라데이션·외곽선 스타일은 원본과 같게(원본에 있는 색만 쓸 것).
> - 투명색(<투명색>) 부분은 그 색 그대로 둘 것.
> - 원본은 {scale}배 확대된 저해상도 픽셀아트다. {scale}×{scale} 블록 단위의 계단 모양으로 그릴 것.

## 결과 넣기

받은 그림을 `assets/banners/<이름>.png`로 저장합니다. 크기는 달라도 되지만 가로:세로가 4:1이어야 합니다
(AI가 정사각형 등으로 주면 그림 부분만 4:1로 잘라 저장). 128×32로 줄이고 색은 원본 그림이
쓰던 색 중 가장 가까운 것으로 맞춥니다. `python tools/battlebanner.py check`로 확인한 뒤 빌드합니다.

| 파일 | 원문 | 한국어(대사 표기) | 투명색 |
|---|---|---|---|
{table}
"""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "export"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "work" / "banners"
    {"export": cli_export, "check": cli_check}[cmd](out)

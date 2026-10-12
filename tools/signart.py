"""Field sign pictures for redrawing outside (D36 follow-up).

  python tools/signart.py export [OUT]   original signs, upscaled, to redraw elsewhere
  python tools/signart.py check  [OUT]   how the pictures in assets/signs/ come back

export writes, per sign of fieldsign.SIGNS, <name>.png (the reference window: the
text box plus fieldsign.MARGIN, under its palette row, scaled SCALE times, nearest
neighbour) and <name>_galmuri.png (the current Galmuri redraw, for layout), a
contact sheet and a prompt list. A redrawn picture saved as assets/signs/<name>.png
(any size; it is scaled back to the window) replaces the Galmuri text in the build:
its colours are snapped to those the sign already uses, and only the text box is
taken. check renders each such picture as the build would see it, beside the
original, to <OUT>/check/.
"""

import glob
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fieldsign  # noqa: E402
import iso  # noqa: E402
import kfont  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCALE = 8
JP = {
    "jinrikisha": "人力車帳場", "yado": "宿", "yaoya": "八百屋", "sakana": "魚", "sakaya": "酒屋",
    "gyunabe": "牛鍋", "unagi": "うなぎ", "kahii": "可否茶屋", "shinryo": "診療所", "ezoshi": "絵草紙",
    "ezoshi2": "絵草紙", "meikyo": "明鏡止水", "komamono": "小間物屋", "kuji": "くじ",
    "senkyaku": "千客万来", "yado2": "宿", "dango": "だんご", "akabeko": "赤べこ",
    "shinbun": "新聞社", "kasshin": "神谷活心流", "keisatsu": "警察署",
}


def _load():
    bins = sorted(glob.glob(str(ROOT / "original" / "*.bin")))
    raw = Path(bins[0]).read_bytes()
    sources = fieldsign.load_sources(raw, iso.load(raw))
    g = ROOT.parent / "galmuri"
    fonts = (kfont.load_bdf(g / "Galmuri11-Bold.bdf"), kfont.load_bdf(g / "Galmuri9.bdf"))
    return sources, fonts


def _rgb(idx, ref, mds):
    r = fieldsign.clut_rows(mds)[ref.sign.row]
    return (np.stack([(r & 31), (r >> 5) & 31, (r >> 10) & 31], -1)[idx] * 8).astype(np.uint8)


def _up(rgb, k=SCALE):
    return cv2.resize(rgb, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)


def _save(path, rgb):
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def _galmuri(ref, mask):
    """The reference window redrawn with the Galmuri text (the build without art)."""
    return fieldsign.redraw(ref.tpl.copy(), ref, fieldsign.mapping_at(ref.tpl, ref.tpl), mask, *ref.origin)


def export(out):
    out.mkdir(parents=True, exist_ok=True)
    sources, fonts = _load()
    refs, masks = fieldsign.load_refs(sources, fonts, art_dir=None)
    rows, lines = [], []
    for n, (s, ref) in enumerate(zip(fieldsign.SIGNS, refs), 1):
        mds = sources[s.ref][1]
        h, w = ref.tpl.shape
        orig = _rgb(ref.tpl, ref, mds)
        _save(out / f"{n:02d}_{s.name}.png", _up(orig))
        _save(out / f"{n:02d}_{s.name}_galmuri.png", _up(_rgb(_galmuri(ref, masks[s.name]), ref, mds)))
        rows.append((s, orig))
        way = "세로쓰기" if s.vertical else "가로쓰기"
        lines.append(f"| {n:02d} | `{s.name}` | {JP[s.name]} | **{s.text}** | {way} | {w}×{h} → {w * SCALE}×{h * SCALE} |")
    # contact sheet: every sign at 4x, labelled by number
    k = 4
    pad = 8
    width = max(o.shape[1] for _, o in rows) * k + 60
    tiles = []
    for n, (s, o) in enumerate(rows, 1):
        im = _up(o, k)
        t = np.full((im.shape[0] + pad, width, 3), 32, np.uint8)
        t[pad // 2:pad // 2 + im.shape[0], 52:52 + im.shape[1]] = im
        cv2.putText(t, f"{n:02d}", (4, min(t.shape[0] - 4, 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1)
        tiles.append(t)
    _save(out / "sheet.png", np.vstack(tiles))
    (out / "README.md").write_text(PROMPT.format(scale=SCALE, table="\n".join(lines)), encoding="utf-8")
    print(f"{len(rows)} signs -> {out}")


def check(out):
    out = out / "check"
    out.mkdir(parents=True, exist_ok=True)
    sources, fonts = _load()
    refs, masks = fieldsign.load_refs(sources, fonts)
    done = 0
    for s, ref in zip(fieldsign.SIGNS, refs):
        m = masks[s.name]
        if not isinstance(m, tuple):
            continue
        mds = sources[s.ref][1]
        new = fieldsign.redraw_art(ref.tpl.copy(), ref, m[1], m[2])
        gap = np.full((ref.tpl.shape[0], 2), 0, np.uint8)
        pic = np.hstack([_rgb(ref.tpl, ref, mds), np.zeros(gap.shape + (3,), np.uint8), _rgb(new, ref, mds)])
        _save(out / f"{s.name}.png", _up(pic))
        print(f"{s.name}: {int((new != ref.tpl).sum())} px changed")
        done += 1
    print(f"{done} pictures in {fieldsign.ART} -> {out}")


PROMPT = """# 필드 간판 다시 그리기

`NN_이름.png` = 원본 간판(게임 화면 그대로의 색, {scale}배 확대). `NN_이름_galmuri.png` = 지금 패치의
갈무리 글꼴 버전(글자 배치 참고용). `sheet.png` = 전체 모음.

## ChatGPT에 보낼 요청 (간판마다 한 장씩)

> 첨부한 픽셀아트 간판 이미지에서 일본어 글자만 한국어 "<한국어>"(<가로쓰기/세로쓰기>)로 바꿔 줘.
> - 이미지 크기와 비율은 그대로 ({{가로}}×{{세로}} 픽셀). 잘라내거나 여백을 넣지 말 것.
> - 판의 테두리·무늬·색·질감과 글자 바깥 부분은 그대로 둘 것.
> - 원본 이미지에 이미 있는 색만 쓰고, 그라데이션·안티에일리어싱·그림자 효과를 새로 넣지 말 것.
> - 가로 간판은 왼쪽에서 오른쪽으로 쓸 것(원본 일본어는 오른쪽에서 왼쪽).
> - 원본은 {scale}배 확대된 저해상도 픽셀아트다. 글자도 {scale}×{scale} 픽셀 블록 단위의 계단 모양으로,
>   원래 일본어 글자와 같은 굵기·크기·색으로 그릴 것.

## 결과 넣기

받은 그림을 `assets/signs/<이름>.png`(번호 없이, 예: `assets/signs/yado.png`)로 저장합니다.
크기가 달라도 원래 크기로 줄이고, 색은 그 간판이 쓰던 색 중 가장 가까운 것으로 맞추며,
글자 칸 안만 반영합니다. `python tools/signart.py check`로 결과를 확인한 뒤 빌드합니다.
그림이 없는 간판은 지금처럼 갈무리 글꼴로 그려집니다.

| 번호 | 이름 | 원문 | 한국어 | 방향 | 크기(원본 → 확대) |
|---|---|---|---|---|---|
{table}
"""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "export"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "work" / "signs"
    {"export": export, "check": check}[cmd](out)

"""Release package: release-policy build -> xdelta3 patch, verified by re-applying it.

Usage:
  python tools/release.py --src original/<image>.bin --galmuri ../galmuri/Galmuri14.bdf \
      --xdelta <path to xdelta3> [--version 1.0] [--out dist]

Writes dist/<package>/ (patch, cue, README, checksums, font licence) and
dist/<package>.zip. The disc image itself is never packaged. The patch is
decoded again against the source image and must give the built image byte for
byte; anything else fails the release.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import build

TITLE = "바람의 검심 -메이지 검객 낭만기- 십용사 음모편"
BIN_NAME = "Rurouni Kenshin - Juuyuushi Inbou-hen (Korean)"
SOURCE_SIZE, SOURCE_MD5 = 534856560, "a2a20dc4d977cf828b4136ef92fe1ba4"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def readme(version, patch_name, patched_sha, patched_size, author):
    return f"""{TITLE} 한글 패치 v{version}
{'=' * 40}

플레이스테이션 『るろうに剣心 -明治剣客浪漫譚- 十勇士陰謀編』(일본판, SCPS-10048)의
비공식 한글 패치입니다. 게임 이미지는 들어 있지 않습니다. 직접 소유한 원본 디스크의
이미지가 있어야 합니다.

■ 한글화 범위
- 대사 전부, 메뉴·아이템·기술 이름과 설명, 전투 메시지와 명령 아이콘
- 이름 입력(한글 입력), 타이틀 로고와 메뉴
- 오프닝 영상과 전투 설명 영상의 글자, 필드 간판, 엔딩 크레딧
- 원본 그대로: 저작권 표기, 실제 인물·회사 이름(크레딧), 작은 등롱·깃발 무늬, 전투 게이지 문양

■ 필요한 원본 이미지 (1트랙 MODE2/2352 bin)
- 파일 크기: {SOURCE_SIZE:,} 바이트
- MD5: {SOURCE_MD5}
- SHA-256: {build.SOURCE_SHA256}
  (Redump 'Rurouni Kenshin - Meiji Kenkaku Romantan - Juuyuushi Inbou-hen (Japan)')
  해시가 다른 이미지에는 패치가 적용되지 않거나 깨진 결과가 나옵니다.

■ 적용 방법
1. 원본 .bin 파일과 {patch_name}을(를) 준비합니다.
2. xdelta 패치 도구로 적용합니다. 예:
   - Delta Patcher(Windows, GUI): Original file = 원본 .bin, XDelta patch = {patch_name},
     'Apply patch'를 누릅니다(설정의 'Backup original file'은 켜 두는 것을 권장).
   - xdelta3(명령줄): xdelta3 -d -s "원본.bin" "{patch_name}" "{BIN_NAME}.bin"
3. 결과 파일 이름을 "{BIN_NAME}.bin"으로 하고, 함께 든 "{BIN_NAME}.cue"를
   같은 폴더에 둔 뒤 cue 파일로 실행합니다.
4. 결과 확인(선택): 크기 {patched_size:,} 바이트, SHA-256 {patched_sha}

※ 패치하면 이미지가 원본보다 조금 커집니다(번역문·글꼴·영상이 디스크 끝에 덧붙음).
※ 개발 중 확인은 에뮬레이터 DuckStation에서 했습니다.

■ 만든 사람
- 한글화: {author}
- 번역·기술 작업: Claude(Anthropic의 AI)가 초벌 번역과 검수, 도구 제작을 맡고, 제작자가 표기와 방침을
  확정했습니다. 사람이 문장 하나하나를 검수한 번역은 아닙니다.
- 타이틀 로고: 제작자 제공 그림
- 한글 글꼴: Galmuri (Lee Minseo, SIL Open Font License 1.1, LICENSE-Galmuri.txt)
- 영상 속 한글 일부는 맑은 고딕·궁서 글꼴로 그린 그림입니다.

■ 알림
이 패치는 비공식 팬 번역이며 원작자(和月伸宏 / 集英社)와 게임 제작·판매사
(Sony Computer Entertainment 등)와 관계가 없습니다. 패치 파일만 배포하며,
게임 이미지나 BIOS를 함께 올리거나 요청하지 마십시오.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--galmuri", required=True)
    ap.add_argument("--xdelta", required=True)
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--author", default="stPark-dev")
    ap.add_argument("--ko-dir", default="text/ko")
    ap.add_argument("--out", default="dist")
    a = ap.parse_args(argv)

    package = f"kenshin-juuyuushi-ko-v{a.version}"
    out = Path(a.out) / package
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    work = Path("build") / "release"
    work.mkdir(parents=True, exist_ok=True)
    patched = work / f"{BIN_NAME}.bin"

    print("build (release policy) ...", flush=True)
    rep = build.build(a.src, a.ko_dir, patched, build.POLICIES["release"], galmuri=a.galmuri)
    if rep["problems"]:
        for p in rep["problems"]:
            print("PROBLEM", p)
        return 1
    for w in rep["warnings"]:
        print("WARNING", w)

    patch = out / f"{package}.xdelta"
    print("xdelta3 encode ...", flush=True)
    subprocess.run([a.xdelta, "-e", "-9", "-f", "-B", str(1 << 30), "-s", a.src, str(patched), str(patch)], check=True)
    print("verify ...", flush=True)
    check = work / "verify.bin"
    subprocess.run([a.xdelta, "-d", "-f", "-s", a.src, str(patch), str(check)], check=True)
    patched_sha = sha256(patched)
    if sha256(check) != patched_sha:
        print("the patch does not reproduce the built image")
        return 1
    check.unlink()

    (out / f"{BIN_NAME}.cue").write_text(f'FILE "{BIN_NAME}.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n',
                                         encoding="ascii")
    (out / "README.txt").write_text(readme(a.version, patch.name, patched_sha, patched.stat().st_size, a.author),
                                    encoding="utf-8-sig")
    shutil.copy(Path(a.galmuri).parent / "LICENSE.txt", out / "LICENSE-Galmuri.txt")
    sums = [f"{build.SOURCE_SHA256}  원본.bin", f"{patched_sha}  {BIN_NAME}.bin", f"{sha256(patch)}  {patch.name}"]
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    zpath = Path(a.out) / f"{package}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.iterdir()):
            z.write(f, f"{package}/{f.name}")
    print("patch", patch, patch.stat().st_size, "bytes")
    print("package", zpath, zpath.stat().st_size, "bytes")
    print("patched image sha256", patched_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())

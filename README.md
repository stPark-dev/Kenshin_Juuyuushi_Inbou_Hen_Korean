<p align="center"><img src="cover_ko.png" alt="바람의 검심 -메이지 검객 낭만기- 십용사 음모편 한글화" width="480"></p>

# 바람의 검심 -메이지 검객 낭만기- 십용사 음모편 한글화

플레이스테이션용 『るろうに剣心 -明治剣客浪漫譚- 十勇士陰謀編』(일본판, SCPS-10048)의 한글 패치 제작 프로젝트입니다.

> **현재 상태: v1.0 배포 (검수 진행 중)**
> 대사·메뉴·이름 입력·타이틀·영상 글자·필드 간판·엔딩 크레딧까지 한글화해 [v1.0을 배포](https://github.com/stPark-dev/Kenshin_Juuyuushi_Inbou_Hen_Korean/releases/tag/v1.0)했습니다. 다만 **검수가 아직 끝나지 않았습니다.** 제작자가 실제로 플레이하며 확인하는 중이라 오역·어색한 문장·화면 깨짐·진행 막힘이 남아 있을 수 있습니다. 발견하시면 [이슈](https://github.com/stPark-dev/Kenshin_Juuyuushi_Inbou_Hen_Korean/issues)나 [돈골's 한글팩 제보](https://hangul.dongolpack.workers.dev/reports/?resource=kenshin-juuyuushi)로 알려 주세요.

## 진행 상황

| 항목 | 상태 |
|---|---|
| 대사 (문자열 10,401개, 58개 장면) | 번역 완료 |
| 메뉴·아이템·기술·전투 메시지 | 번역 완료 (D28·D29), 전투 명령 아이콘 (D31) |
| 이름 입력 | 한글 입력 (D30) |
| 타이틀 로고·메뉴 | 완료 (D32·D33) |
| 엔딩 크레딧 | 역할명·인물 이름 번역, 실제 인명·회사명 원문 (D34) |
| 영상 글자 (오프닝 RU12, 전투 설명 RU13) | 완료 (D35) |
| 필드 간판 21종 | 완료 (D36) |
| 원본 유지 | 저작권 표기, 전투 게이지 突 문양, 작은 등롱·깃발 |

자세한 조사 결과와 근거는 [`docs/survey.md`](docs/survey.md), 결정 사항은 [`docs/decisions.md`](docs/decisions.md), 번역 규칙은 [`docs/style.md`](docs/style.md), 작업 인계는 [`docs/HANDOFF.md`](docs/HANDOFF.md)에 있습니다.

## 지원 원본

정당하게 소유한 일본판 디스크 이미지(1트랙 `MODE2/2352` bin/cue)만 지원합니다. 원본 이미지와 게임 데이터는 이 저장소에 없으며 배포하지 않습니다.

| 항목 | 값 |
|---|---|
| bin 크기 | 534,856,560 바이트 |
| bin SHA-256 | `738f320c105dc7ab63515553112bd78a62041305ee4f3ebfeaf5b7df8bb2abd8` |
| bin MD5 | `a2a20dc4d977cf828b4136ef92fe1ba4` |

## 빌드

Python 3와 numpy가 필요합니다. 한글 글꼴은 [Galmuri](https://github.com/quiple/galmuri)의 `Galmuri14.bdf`를 씁니다.

```sh
python3 tools/build.py \
  --src "original/Rurouni Kenshin - Meiji Kenkaku Romantan - Juuyuushi Inbou-hen (Japan).bin" \
  --out build/kenshin_ko.bin \
  --galmuri ../galmuri/Galmuri14.bdf \
  --ko-dir text/ko --policy dev
```

- `--policy dev`: 초벌(draft)과 검수(reviewed) 번역을 모두 넣고 문제를 보고합니다.
- `--policy release`: 검수 완료 번역만 넣고, 문제가 하나라도 있으면 실패합니다.
- 결과로 `build/kenshin_ko.bin`과 `.cue`가 생깁니다. 원본과 다른 이미지에는 빌드를 거부합니다.

배포 패키지(xdelta 패치, cue, 안내문, 글꼴 라이선스)는 다음으로 만듭니다. [xdelta3](https://github.com/jmacd/xdelta-gpl/releases)가 필요하고, 만든 패치를 원본에 다시 적용해 빌드 결과와 같은지 확인합니다.

```sh
python3 tools/release.py --src "original/<원본>.bin" --galmuri ../galmuri/Galmuri14.bdf --xdelta <xdelta3 경로> --version 1.0
```

테스트는 `python3 -m pytest -q tests/`로 돌립니다. 원본 데이터가 필요한 테스트는 `original/`의 이미지와 `work/`의 추출본이 있을 때만 실행됩니다.

## 구조

| 경로 | 내용 |
|---|---|
| `tools/` | 디스크·컨테이너 도구(`iso.py`, `cdsector.py`, `grparc.py`), 대본·참조(`script.py`, `refs.py`), 한글 인코딩·글꼴(`koenc.py`, `kfont.py`, `scenefont.py`), 번역 파일(`textio.py`), 제품 빌드(`build.py`) |
| `tests/` | 위 도구의 테스트 |
| `docs/` | 조사 기록, 결정 기록, 스크립트 VM 명령 정의 |
| `text/ko/` | 한국어 번역. 일본어 원문은 저장소에 넣지 않고 빌드 때 원본에서 다시 뽑습니다 |

## 번역 방침

- 인물명, 지명, 기술명은 한국 정발 만화 『바람의 검심』 표기를 따릅니다.
- 초벌 번역과 검수는 Claude가 맡았고, 제작자가 표기와 방침을 확정했습니다(문장 단위 사람 검수는 아님, 패치 안내문에 밝힘).

## 크레딧

- 한글 글꼴: [Galmuri](https://github.com/quiple/galmuri) by Lee Minseo, SIL Open Font License 1.1
- 원작: 和月伸宏 / 集英社, 게임: Sony Computer Entertainment. 이 프로젝트는 비공식 팬 번역이며 원저작권자와 관계가 없습니다.

# 작업 인계 (2026-10-08 기준)

다른 컴퓨터에서 이 문서만 보고 이어갈 수 있게 정리했다. 근거와 세부 결과는 `docs/survey.md`, 결정은 `docs/decisions.md`(D1–D12), 번역 규칙은 `docs/style.md`에 있다.

## 1. 한눈에 보는 상태

| 영역 | 상태 |
|---|---|
| 디스크·컨테이너 재구성 (ISO, GRP, Form 1 EDC/ECC) | 완료. 번역 없이 빌드하면 원본과 SHA-256 동일 |
| 대사 글꼴 | 장면별 글꼴 블록을 번역문 기준으로 재생성 (Galmuri14) |
| 번역문 길이 증가 | 문자열 풀 끝에 덧붙이고 참조 수정. 10,401개 중 9,726개 가능, 나머지 675개는 원래 칸 안에 맞춰야 함 |
| 제품 빌드 / 장면 검사 | `tools/build.py` / `tools/check_ko.py` |
| 초벌 번역 | 34개 장면 4,917줄: ZROUP00–23, 25–33, 40 (모두 check_ko 0건). 검수 D13(05–12), D14(13–23), D15(25–33) |
| 용어집 | 인물·지명·용어 `text/glossary.json`(자동 추출 후보 59개 검토: 49개 편입, 그중 19개 `check`, 일반어·조각 10개 제외), 아이템 174개 `text/glossary_items.json` |
| 테스트 | 103개 통과 (원본 데이터가 필요한 테스트는 원본이 있을 때만 실행) |

## 2. 집 환경 준비

저장소에 없는 것(저작권·용량 때문에 git 제외)을 직접 준비한다.

| 준비물 | 위치 | 비고 |
|---|---|---|
| 일본판 bin/cue | `original/` | bin SHA-256 `738f320c…abd8` (README 참고). 다르면 빌드가 거부함 |
| Galmuri | 저장소 옆 `../galmuri/Galmuri14.bdf` | https://github.com/quiple/galmuri (OFL) |
| Python 3 + numpy, pytest, Pillow | | 기본 빌드·테스트 |
| python-xlib, capstone | | 런타임 자동 조작, MIPS 디스어셈블(tools/re) |
| DuckStation v0.1-11894 AppImage | 예: `~/.local/opt/duckstation/` | 런타임 확인용 |
| PS1 BIOS SCPH5500 | `~/.local/share/duckstation/bios/scph5500.bin` | MD5 `8dd7d5296a650fac7319bce665a6a53c`. 저장소에 넣지 말 것 |
| Xephyr | | 격리된 화면 `:5`에서 에뮬레이터 실행 |

준비 후:

```sh
python3 tools/setup_work.py --src original/*.bin      # work/iso, work/grp 재생성 (분석·테스트용)
python3 tools/extract.py --src original/*.bin         # text/src (일본어 원문, git 제외)
python3 -m pytest -q tests/                          # 103 passed 기대
```

DuckStation `settings.ini`(`~/.local/share/duckstation/settings.ini`)에 쓰던 설정:

```ini
[Main]
SetupWizardIncomplete = false
ConfirmPowerOff = false
[BIOS]
SearchDirectory = <bios 폴더>
PathNTSCJ = scph5500.bin
[Console]
Region = NTSC-J
[GPU]
Renderer = OpenGL            ; VRAM 쓰기 덤프는 하드웨어 렌더러에서만 동작
[Pad1]
Type = DigitalController
Up = Keyboard/Up
Down = Keyboard/Down
Left = Keyboard/Left
Right = Keyboard/Right
Cross = Keyboard/X
Circle = Keyboard/Z
Square = Keyboard/A
Triangle = Keyboard/S
Start = Keyboard/Return
Select = Keyboard/Backspace
[AutoUpdater]
CheckAtStartup = false       ; 업데이트 창이 화면을 막음
[Debug]
EnableGDBServer = true       ; 런타임 추적(tools/re/rsp.py), 127.0.0.1:2345
GDBServerPort = 2345
; [TextureReplacements] DumpVRAMWrites = true 는 필요할 때만 켠다(덤프가 계속 쌓임)
```

## 3. 자주 쓰는 명령

```sh
# 장면 번역 검사 (이미지를 쓰지 않음, 수 초)
python3 tools/check_ko.py --src original/*.bin --galmuri ../galmuri/Galmuri14.bdf ZROUP40 ZROUP41

# 제품 빌드 (dev: 초벌 포함, release: 검수 완료만 + 문제 있으면 실패)
python3 tools/build.py --src original/*.bin --out build/kenshin_ko.bin \
    --galmuri ../galmuri/Galmuri14.bdf --ko-dir text/ko --policy dev
```

## 4. 번역 작업 흐름 (확정된 방식)

1. 묶음 전에 용어집(인물·지명·아이템·반복 용어)을 먼저 확정한다. 병렬 번역에서 표기가 갈렸던 교훈(D11·D12).
2. 장면마다 번역 에이전트 1개. 지시 내용(첫 묶음에 쓴 것):
   - 먼저 읽기: `docs/style.md`(D9, 2.1 켄신 D10, 3.0 카오루 D11, 3.2 축약 D12), `docs/decisions.md`, `text/glossary.json`, `text/glossary_items.json`, 예시 `text/ko/ZROUP40.json`·`ZROUP00.json`, 원문 `text/src/ZROUPnn.json`
   - 출력: `text/ko/ZROUPnn.json` = `{id: {src_hash, ko, status: "draft", note}}`, 모든 행
   - 제어 기호 순서 보존, 띄어쓰기는 ASCII 공백(빌드가 `N;`로 변환), `，．！？` 뒤 띄어쓰기 없음, `^c`는 의도한 끊김에만, `^N` 뒤 받침 조사 금지, 새 이름은 note에 `NEW NAME: 한자=한글`
   - `check_ko.py`가 0건이 될 때까지 수정. 다른 파일·git은 건드리지 않음. 일본어 원문을 추적 파일·보고서에 옮기지 않음
3. 결과 검수(사람 대신 Claude, D6): check_ko 재실행, 문체 자동 점검(부호 뒤 공백, `^N군` 붙여 쓰기, ~소이다, 남은 가나·한자), 카오루 `씨` 분기 해요체(주인공에게 직접 하는 말만), 용어 통일, 축약 대사 정보 보존.
4. 중요 장면은 런타임 화면 확인.

## 5. 결정 요약 (자세히는 decisions.md)

- D1 고유명사는 한국 정발 만화 『바람의 검심』 기준, D8 이름 표기 규칙(일본어 음, 거센소리 첫소리, 장음 생략, 촉음 반영)
- D2 범위: 대사, 메뉴, 타이틀 그림, 엔딩 크레딧, 영상 자막, 한글 이름 입력 전부
- D4 Galmuri14, D5 띄어쓰기 `N;`
- D6 초벌·검수 Claude, D7 일본어 원문은 저장소에 넣지 않음
- D13 두 번째 묶음 검수(今十勇士=신 십용사 잠정 등)
- D9 문체·무결성, D10 켄신 말투(하오체·소인, 발도재는 나+평서체), D11 용어 통일·카오루 분기·^N 조사·축약 금지, D12 첫 묶음 검수 반영과 다음 작업 조건

## 6. 보류·미해결

| 항목 | 상태 / 다음 증거 |
|---|---|
| 神爪 독음 | 카미즈메로 임시 통일. ZROUP41 퀴즈의 정답 인덱스·스크립트 조건 확인 전 확정 금지 |
| 牛革草 최종명 | 우혁초 잠정. 아이템 설명·효과 확인 후 |
| ZROUP41 (독음 퀴즈) | 별도 현지화 대상. 정답 판정 구조부터 분석 |
| 말장난·수수께끼 | note `PUN-PROVISIONAL` / `LOCALIZE-RIDDLE` 행을 정식 패치 전 현지화 |
| 대형 장면 파일 | ZROUP01이 이미 373KB. 382KB(원본 최대)는 한계로 단정하지 않음. ZROUP24로 포인터·텍스트 인덱스·인코딩·실제 로딩 시험 필요 |
| 메뉴·아이템 이름 | 아이템 표 174개가 실행 파일의 압축 데이터(RAM `0x8003A09C`에 풀림)에 있음 → 메뉴 번역은 실행 파일 압축 해제·재압축(또는 재배치) 경로가 필요. 메뉴가 어떤 글꼴을 쓰는지도 미확인 |
| 참조 없는 문자열 646개 | 미사용 대사일 가능성. 실행으로 확인 전까지 원래 칸 안에 맞춤. 단 ZROUP17 유리·사이조 이벤트 약 60행이 여기에 속해 실제 사용 가능성 높음(D14) → 참조 방식 조사 |
| 이름 입력, 전투, 타이틀 그림, 엔딩 크레딧, 영상 자막 | 미조사. 오프닝 프롤로그 대화는 영상(RU*.MOV)에 박힌 글자로 판단 |
| `^N` 이름 폭 | 96px(6글자) 예산. 이름 입력 조사 후 실제 최대 길이로 조정 |

## 7. 다음에 할 일 (순서)

1. `text/glossary.json`의 `check` 항목(새로 편입한 지명·용어 19개 포함)을 원문 문맥으로 확인 → 불확실한 것은 사용자 확인.
2. `text/glossary_items.json`의 `check` 56개 사용자 확인.
3. 대형 장면 시험(ZROUP24): 원본보다 큰 장면 파일로 빌드 → 실행·대사 확인.
4. 다음 번역 묶음(ZROUP24·41 제외) 전에 새 장면의 화자·이름을 용어집에 먼저 등록 → 에이전트 병렬, 검수, 커밋. 잠정 용어(今十勇士, 南里) 사용자 결정 반영.
5. 메뉴·아이템 이름 경로 조사(실행 파일 압축 형식 해석).

## 8. 런타임 확인 방법

```sh
Xephyr :5 -screen 800x700 -ac -br -noreset &          # 격리 화면 (사용자 화면에 키 입력이 가지 않게)
DISPLAY=:5 duckstation -batch -fastboot build/kenshin_ko.cue &
python3 tools/re/route_town.py :5 work/ref_title_menu_gl.png work/shots 10   # 타이틀 메뉴 감지 → 새 게임 → 마을 대화 캡처
```

- `route_town.py`는 타이틀 메뉴 참조 이미지가 필요하다. 게임 화면에서 나온 이미지라 저장소에 넣지 않았다. OpenGL 렌더러로 타이틀 메뉴(はじめから/つづきから) 화면을 `import -display :5 -window root -crop 800x610+0+23`로 찍은 뒤 Pillow로 `crop((250,330,550,450))` 해서 `work/ref_title_menu_gl.png`로 저장한다(판정 차이 15 미만).
- 마을 대화 = ZROUP40. 경로: 타이틀 메뉴에서 Start → 주인공 선택 ○ → 대화 ○.
- 스크립트 VM 분석: `tools/re/vmspec.py <RAM 덤프> work/vmspec.json`(GDB로 받은 2MB RAM 덤프 필요), 손 검토 명령 정의는 `docs/re/vm_overrides.json`.

## 9. 알려진 함정

- 모듈 이름 `grp`는 표준 라이브러리와 겹친다 → `tools/grparc.py`.
- `pkill -f "duckstation …"`는 그 명령을 실행한 셸까지 죽인다 → 프로세스 이름(`ps -eo pid,comm`)으로 골라 kill.
- Xephyr에는 창 관리자가 없어 포인터 아래 창에 키가 간다 → 입력 전 `warp_pointer(400,300)`(스크립트에 포함).
- ImageMagick `import`의 PNG에는 +0+23 페이지 오프셋이 남는다 → 비교용 잘라내기는 Pillow로.
- VRAM 덤프 `DumpVRAMWriteForceAlphaChannel = true`는 16비트 값의 최상위 비트를 덮어써 4bpp 해석을 망친다 → false.
- 원본 문자열 288px 줄은 모두 마지막 줄이다 → `^c` 앞 줄은 272px 이하(빈 줄 방지).
- 일본어 원문(`text/src`)과 게임 화면 캡처, RAM 덤프는 커밋하지 않는다(.gitignore).

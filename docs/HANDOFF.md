# 작업 인계 (2026-10-08 기준)

다른 컴퓨터에서 이 문서만 보고 이어갈 수 있게 정리했다. 근거와 세부 결과는 `docs/survey.md`, 결정은 `docs/decisions.md`(D1–D23), 번역 규칙은 `docs/style.md`에 있다.

## 1. 한눈에 보는 상태

| 영역 | 상태 |
|---|---|
| 디스크·컨테이너 재구성 (ISO, GRP, Form 1 EDC/ECC) | 완료. 번역 없이 빌드하면 원본과 SHA-256 동일 |
| 대사 글꼴 | 장면별 글꼴 블록을 번역문 기준으로 재생성 (Galmuri14) |
| 번역문 길이 증가 | 문자열 풀 끝에 덧붙이고 참조 수정. 10,401개 중 9,726개 가능, 나머지 675개는 원래 칸 안에 맞춰야 함 |
| 제품 빌드 / 장면 검사 | `tools/build.py` / `tools/check_ko.py` |
| 초벌 번역 | 58개 장면 10,401줄 전부 완료(검수 D13–D20). 크기 초과 ZROUP24(434,672B)도 런타임에서 로딩·표시 확인(D21) |
| 용어집 | 인물·지명·용어 `text/glossary.json`(자동 추출 후보 59개 검토: 49개 편입, 일반어·조각 10개 제외. check는 D24에서 대부분 확정), 아이템 174개 `text/glossary_items.json` |
| 테스트 | 155개 통과 (원본 데이터가 필요한 테스트는 원본이 있을 때만 실행) |

## 2. 집 환경 준비

저장소에 없는 것(저작권·용량 때문에 git 제외)을 직접 준비한다.

| 준비물 | 위치 | 비고 |
|---|---|---|
| 일본판 bin/cue | `original/` | bin SHA-256 `738f320c…abd8` (README 참고). 다르면 빌드가 거부함 |
| Galmuri | 저장소 옆 `../galmuri/Galmuri14.bdf`, 같은 폴더에 `Galmuri11-Bold.bdf`·`Galmuri9.bdf`(전투 아이콘) | https://github.com/quiple/galmuri (OFL), 릴리스 zip에 모두 있음 |
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
| 神爪 독음 | 카미츠메로 확정(D19, ZROUP41 퀴즈 데이터의 정답 かみつめ) |
| 牛革草 최종명 | 우혁초 잠정. 아이템 설명·효과 확인 후 |
| ZROUP41 (퀴즈) | 해결(D23): 데이터 첫 선택지가 정답, 표시 순서는 섞임. 현지화한 문제도 정상 판정 |
| 말장난·수수께끼 | 정리 완료(D26): `PUN-LOCALIZED` / `PUN-ACCEPTED` / `RIDDLE-LOCALIZED` |
| 대형 장면 파일 | 해결(D21): 번역 ZROUP24 434,672B 로딩·대화·덧붙인 문자열 표시 확인. 이보다 커지면 다시 시험 |
| 메뉴·아이템 이름 | 본 프로그램(D28)·MAPCODE·BTLCODE(D29) 메뉴 문자열 번역·빌드 연결 완료. 런타임: 필드 메뉴·전투(도구·필살기 목록, 승리 결과)·상점·저장 화면 한국어 확인. 전투 명령 아이콘도 한글(D31) |
| 참조 없는 문자열 646개 | 미사용 대사일 가능성. 원래 칸 안에 맞춤. ZROUP17 유리·사이조 이벤트 71행은 ZROUP29가 실제로 쓰는 사본으로 확인(D23) |
| 이름 입력 | 한글 입력 완료(D30). 기본 이름 聖·輝는 원작 그대로(사용자 결정) |
| 타이틀 그림, 엔딩 크레딧, 영상 자막, 突 게이지 문양, 필드 간판 | 타이틀 메뉴 글자(D32)·로고(D33, `title_ko.png`) 완료, 저작권 표기는 원본 유지. 엔딩 크레딧 완료(D34: 역할명·인물 이름 번역, 실제 인명·회사명 원문, 한글 가로 2배, 「終」 원본). 오프닝·전투 설명 영상 RU12·RU13 완료(D35, 빌드에 약 6분 추가). 영상 속 전투 명령 아이콘은 원본. 필드 간판 21종 완료(D36), 작은 등롱·깃발은 원본. 전투 명령 아이콘 D31 완료, 突은 의미 미확인으로 유지. RU01~11은 음성뿐(자막 없음) |
| `^N` 이름 폭 | 96px(6글자): 이름 입력 최대 6자 확인(D30) |

## 7. 다음에 할 일 (순서)

1. ~~`text/glossary.json`의 `check` 항목~~ 사용자 확정(D24). 남은 check 4개: 我孫子·前川宮内·焔霊·火産霊神(정발 표기 확인).
2. `text/glossary_items.json`의 `check`: 25개 확정(D24·D25), 남은 31개(추억의 니시키에, 紙力士 30개, 모두 메뉴 전용)는 아이템 메뉴 경로 조사 때 사용자 확인.
3. ~~대형 장면 시험(ZROUP24)~~ 완료(D21).
4. 대사 초벌 완료. 런타임 확인 우선순위(`goto_scene.py`로 장면 바로 진입): ~~가로형 메뉴(D17), 종이 스모 능력치 칸~~ 완료(D22), ~~ZROUP17 참조 없는 이벤트, ZROUP41 퀴즈 정답 판정~~ 완료(D23). ~~PUN-PROVISIONAL·LOCALIZE-RIDDLE 행 정리~~ 완료(D26). 잠정 용어(今十勇士, 南里) 사용자 결정 반영.
5. ~~메뉴·아이템 이름 경로 조사~~ 완료(survey §3.1.5), ~~공통 한글 코드표·이름 6자 제한~~ 완료(D27), ~~본 프로그램 메뉴 번역~~ 완료(D28), ~~MAPCODE·BTLCODE 문자열~~ 완료(D29). 전투·상점·저장 화면 런타임 확인 완료(survey §3.1.5). D27에서 줄인 이름과 D28·D29 번역은 사용자 검토.
6. ~~전투 명령 아이콘~~ 완료(D31), ~~타이틀 메뉴 글자·로고~~ 완료(D32·D33). ~~엔딩 크레딧~~ 완료(D34), ~~오프닝·전투 설명 영상 RU12·RU13~~ 완료(D35), ~~필드 간판~~ 완료(D36). 남은 그림 글자: 突 문양(원본 유지 결정). 그림 찾기는 VRAM 쓰기 덤프(survey §3.1.7)가 빠르다.
7. 배포(D37): `tools/release.py`로 패키지 생성(xdelta3 필요, Windows PC는 tools/xdelta3 폴더). 사용자의 통 플레이 검증 후 배포. 문제가 나오면 고치고 버전을 올려 다시 만든다.

## 8. 런타임 확인 방법

```sh
Xephyr :5 -screen 800x700 -ac -br -noreset &          # 격리 화면 (사용자 화면에 키 입력이 가지 않게)
DISPLAY=:5 duckstation -batch -fastboot build/kenshin_ko.cue &
python3 tools/re/route_town.py :5 work/ref_title_menu_gl.png work/shots 10   # 타이틀 메뉴 감지 → 새 게임 → 마을 대화 캡처
```

- `route_town.py`는 타이틀 메뉴 참조 이미지가 필요하다. 게임 화면에서 나온 이미지라 저장소에 넣지 않았다. OpenGL 렌더러로 타이틀 메뉴(はじめから/つづきから) 화면을 `import -display :5 -window root -crop 800x610+0+23`로 찍은 뒤 Pillow로 `crop((250,330,550,450))` 해서 `work/ref_title_menu_gl.png`로 저장한다(판정 차이 15 미만).
- 마을 대화 = ZROUP40. 경로: 타이틀 메뉴에서 Start → 주인공 선택 ○ → 대화 ○.
- 스크립트 VM 분석: `tools/re/vmspec.py <RAM 덤프> work/vmspec.json`(GDB로 받은 2MB RAM 덤프 필요), 손 검토 명령 정의는 `docs/re/vm_overrides.json`.

## 8.1 Windows에서 런타임 확인 (2026-10-08)

DuckStation 포터블을 `C:\Users\S.T.Park\tools\duckstation\`에 두었다(`portable.txt`, `settings.ini`는 위 설정과 같음, `bios\scph5500.bin`). 키 입력은 창에 PostMessage, 캡처는 PrintWindow라 사용자 화면 포커스를 뺏지 않는다(`tools/re/winds.py`).

```sh
python tools/re/route_win.py build/kenshin_ko.cue work/shots 10          # 새 게임 → ZROUP40 마을 대화 캡처
python tools/re/goto_scene.py build/kenshin_ko.cue 24 work/g24 12 4      # 첫 장면 로딩을 ZROUP24로 돌려 진입
python tools/re/goto_scene.py build/kenshin_ko.cue 40 work/p40 0 --text 888   # 첫 대화 대신 스크립트 0x888(동료 메뉴) 실행
python tools/re/goto_scene.py build/kenshin_ko.cue 41 work/q41 0 --text 3046 --op 30 --skip 300   # 말 걸지 않고 퀴즈 첫 문제
python tools/re/drive.py build/kenshin_ko.cue work/d work/cmd.txt   # 대화형: work/cmd.txt에 k/shot/poke 명령을 덧붙인다(전투 강제 진입 방법은 파일 설명)
python tools/re/drive.py build/kenshin_ko.cue work/d work/cmd.txt --state 2   # 상태 저장 슬롯에서 바로 시작
python tools/re/strdec.py original/*.bin RU12.MOV work/mov/ru12 --every 15   # 영상 프레임 PNG로 보기
python tools/movieart.py   # 영상 한글 오버레이 다시 그리기(Windows 글꼴)
python tools/re/patchmain.py build/kenshin_ko.bin build/endtest.bin 8002e754 a4ba0008 8002eabc 00000000   # 타이틀 대신 엔딩 크레딧 시험 이미지(뒤쪽 패치는 엔딩 영상 생략)
```

- 상태 저장(2026-10-09): 핫키 F1~F4 = 슬롯 1~4(`savestates/savestate_N.sav`, `drive.py`의 `save N`). 현재 슬롯 1 = 첫 마을 자유 이동, 2 = 같은 곳에 조우 표 써 넣음(걸으면 전투), 3 = 전투 시작 직후. 상태에는 RAM 전체가 들어가므로 이미 올라와 있던 것(본 프로그램: 아이템·기술 이름, 설명, 메뉴 글꼴)은 옛 빌드 그대로다. 장면 파일·MAPCODE·BTLCODE는 다음에 읽을 때 새 빌드가 반영되므로, 그 전 시점의 상태(슬롯 1·2)를 쓴다. 본 프로그램을 바꿨으면 타이틀부터 부팅한다. 상태 파일은 저장소 밖(에뮬레이터 폴더)에 있다.

```sh
```

- 타이틀 감지 기준 이미지 `work/ref_title_menu_win.png`(원본)·`work/ref_title_menu_win_ko.png`(한국어 빌드, D32): 타이틀 메뉴 화면을 `winds.grab()`으로 찍어 `crop((150,370,370,510))`. `winds.at_title`이 둘 중 하나와 맞으면 타이틀로 본다.
- 장면 전환 함수 `0x801DFE64`(a0=장면 번호, `0x801AF022`에 저장). 새 게임은 28(프롤로그) → 40(마을).
- 중단점은 재컴파일러가 코드를 컴파일하기 전(타이틀 화면)에 걸어야 한다. 이미 실행된 코드에 나중에 건 중단점은 걸리지 않는다.
- 새 DuckStation GDB 서버는 접속하면 이미 멈춘 상태(`?` → `S02`)라 `\x03` 인터럽트에 답하지 않는다. 메모리 읽기는 0x800바이트 단위.
- GRP 파일 바꿔치기로 장면을 시험하면 원본으로도 멈춘다 → 반드시 `goto_scene.py`처럼 장면 번호를 바꾼다.

## 9. 알려진 함정

- 모듈 이름 `grp`는 표준 라이브러리와 겹친다 → `tools/grparc.py`.
- `pkill -f "duckstation …"`는 그 명령을 실행한 셸까지 죽인다 → 프로세스 이름(`ps -eo pid,comm`)으로 골라 kill.
- Xephyr에는 창 관리자가 없어 포인터 아래 창에 키가 간다 → 입력 전 `warp_pointer(400,300)`(스크립트에 포함).
- ImageMagick `import`의 PNG에는 +0+23 페이지 오프셋이 남는다 → 비교용 잘라내기는 Pillow로.
- VRAM 덤프 `DumpVRAMWriteForceAlphaChannel = true`는 16비트 값의 최상위 비트를 덮어써 4bpp 해석을 망친다 → false.
- 원본 문자열 288px 줄은 모두 마지막 줄이다 → `^c` 앞 줄은 272px 이하(빈 줄 방지).
- 일본어 원문(`text/src`)과 게임 화면 캡처, RAM 덤프는 커밋하지 않는다(.gitignore).

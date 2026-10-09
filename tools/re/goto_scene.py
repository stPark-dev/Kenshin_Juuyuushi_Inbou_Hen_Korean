"""Boot an image and redirect the first scene load to another scene number.

Breaks on the map overlay's set_scene (0x801dfe64, a0 = scene number, stored at
0x801af022 and patched into the ZROUPnn.GRP / GROUPnn.BIN / NO.nn templates),
replaces a0, then presses ○ and captures.
With --text OFFSET, the first dialogue in the new scene instead runs the scene's
script code at OFFSET (e.g. a menu routine): talk to anyone to see it. The switch
happens at the dialogue's window op (0x47), before a window is open, so a routine
that opens its own window shows it where it should.
Breakpoints must be set before the recompiler first compiles the code, so both are
armed at the title screen; one added later to already-run code never fires.
--skip N lets the first N window ops of the new scene pass (a place-name label
on entry is one). --op 30 switches at the next frame yield (VM op 0x30) instead,
so no NPC has to be reached; the scene's own thread then runs the routine.
After the switch, frames a0..a5 are captured at 1 s intervals (quiz choices, menus).
usage: goto_scene.py image.cue scene outdir presses [interval] [from_scene] [--text OFFSET [--skip N]]
"""
import os
import re
import sys
import threading
import time

from PIL import Image, ImageChops, ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winds  # noqa: E402
from rsp import RSP  # noqa: E402

SET_SCENE = 0x801DFE64
TEXT_OP, DISPATCH, BASE_PTR = 0x801D890C, 0x801D7CD8, 0x801DC388  # 0x47 window op; 0x49 adds *BASE_PTR
args = sys.argv[1:]
TEXT = None
if "--text" in args:
    i = args.index("--text")
    TEXT = int(args[i + 1], 16)
    del args[i : i + 2]
OPS = {0x47: 0x801D890C, 0x30: 0x801D84FC}  # VM op -> handler (dispatch table 0x801D7D20)
if "--op" in args:
    i = args.index("--op")
    TEXT_OP = OPS[int(args[i + 1], 16)]
    del args[i : i + 2]
SKIP = 0
if "--skip" in args:
    i = args.index("--skip")
    SKIP = int(args[i + 1])
    del args[i : i + 2]
CUE, SCENE, OUT, PRESSES = args[0], int(args[1]), args[2], int(args[3])
STEP = float(args[4]) if len(args) > 4 else 4
FROM = int(args[5]) if len(args) > 5 else 40
REF = Image.open("work/ref_title_menu_win.png").convert("RGB")
os.makedirs(OUT, exist_ok=True)
p = winds.launch(CUE)
h = winds.game_window(p.pid)


def at_title():
    crop = winds.grab(h).crop((150, 370, 370, 510))
    return sum(ImageStat.Stat(ImageChops.difference(crop, REF)).mean) / 3 < 15


for i in range(120):
    if at_title():
        break
    if i > 8:
        winds.key(h, "Return")
    time.sleep(2)
else:
    raise SystemExit("title menu never appeared")

r = RSP(timeout=30)
r.send("?")
r.send(f"Z0,{SET_SCENE:x},4")
if TEXT is not None:
    r.send(f"Z0,{TEXT_OP:x},4")
r.send("c", wait=False)
hit = []


def reg(n):
    v = r.send(f"p{n:x}")
    while not re.fullmatch(r"[0-9a-f]{8}", v):  # stray packets after the stop reply
        v = r._packet()
    return int.from_bytes(bytes.fromhex(v), "little")


def watch():
    while True:
        r.wait_stop()
        pc = reg(0x25)
        if pc == SET_SCENE:
            a0 = reg(4)
            print(f"set_scene({a0})", flush=True)
            if a0 == FROM and not hit:
                r.send(f"P4={SCENE.to_bytes(4, 'little').hex()}")
                r.send(f"z0,{SET_SCENE:x},4")
                hit.append(a0)
                print(f"  -> {SCENE}", flush=True)
        elif pc == TEXT_OP and hit and len(hit) <= SKIP:
            hit.append(pc)
            print(f"  window op {len(hit) - 1} skipped", flush=True)
        elif pc == TEXT_OP and hit:
            base = int.from_bytes(r.read_mem(BASE_PTR, 4), "little")
            r.send(f"z0,{TEXT_OP:x},4")
            r.send(f"P12={(base + TEXT).to_bytes(4, 'little').hex()}")  # s2: bytecode pointer
            r.send(f"P25={DISPATCH.to_bytes(4, 'little').hex()}")
            print(f"  text -> script 0x{TEXT:x}", flush=True)
            r.send("c", wait=False)
            return
        r.send("c", wait=False)
        if hit and TEXT is None:
            return


t = threading.Thread(target=watch, daemon=True)
t.start()
time.sleep(1)
winds.key(h, "Return")
time.sleep(3)
for _ in range(10):
    if hit:
        break
    winds.key(h, "z")
    time.sleep(3)
for i in range(8):  # early frames: place-name labels show only briefly
    time.sleep(1)
    winds.grab(h).save(f"{OUT}/e{i}.png")
winds.grab(h).save(f"{OUT}/s00.png")
for i in range(1, PRESSES + 1):
    winds.key(h, "z")
    time.sleep(STEP)
    winds.grab(h).save(f"{OUT}/s{i:02d}.png")
if TEXT is not None:
    print("waiting for a dialogue (talk to anyone)", flush=True)
    t.join(1800)
    for i in range(6):  # the routine's own frames (a quiz shows its choices after the question)
        time.sleep(1)
        winds.grab(h).save(f"{OUT}/a{i}.png")
print("done", flush=True)

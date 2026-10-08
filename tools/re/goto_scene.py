"""Boot an image and redirect the first scene load to another scene number.

Breaks on the map overlay's set_scene (0x801dfe64, a0 = scene number, stored at
0x801af022 and patched into the ZROUPnn.GRP / GROUPnn.BIN / NO.nn templates),
replaces a0, then presses ○ and captures.
usage: goto_scene.py image.cue scene outdir presses [interval] [from_scene]
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
CUE, SCENE, OUT, PRESSES = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
STEP = float(sys.argv[5]) if len(sys.argv) > 5 else 4
FROM = int(sys.argv[6]) if len(sys.argv) > 6 else 40
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
r.send("c", wait=False)
hit = []


def watch():
    while True:
        stop = r.wait_stop()
        a0 = r.send("p4")
        while not re.fullmatch(r"[0-9a-f]{8}", a0):  # stray packets after the stop reply
            print("  skip", stop, a0, flush=True)
            a0 = r._packet()
        a0 = int.from_bytes(bytes.fromhex(a0), "little")
        print(f"set_scene({a0})", flush=True)
        if a0 == FROM and not hit:
            r.send(f"P4={SCENE.to_bytes(4, 'little').hex()}")
            r.send(f"z0,{SET_SCENE:x},4")
            hit.append(a0)
            print(f"  -> {SCENE}", flush=True)
        r.send("c", wait=False)
        if hit:
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
time.sleep(8)
winds.grab(h).save(f"{OUT}/s00.png")
for i in range(1, PRESSES + 1):
    winds.key(h, "z")
    time.sleep(STEP)
    winds.grab(h).save(f"{OUT}/s{i:02d}.png")
print("done", flush=True)

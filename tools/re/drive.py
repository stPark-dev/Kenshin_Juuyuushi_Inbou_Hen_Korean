"""Boot an image to the title menu, then follow commands appended to a file.

usage: drive.py image.cue outdir cmdfile
Commands, one per line, read as they are appended:
  k KEY [N] [WAIT]   press KEY N times, WAIT seconds after each (winds key names:
                     z=○ x=× a=□ s=△ Return=Start BackSpace=Select, arrows)
  shot NAME          save the frame as outdir/NAME.png
  poke ADDR HEX      write bytes to RAM through the GDB server (attached on first use)
  quit               close the emulator
Progress lines (title, key, shot, poked) go to stdout, so a caller can wait for them.

Forcing a battle (2026-10-09, docs/survey.md §3.1.5): after the town is free to
walk, `poke 801add2c 040a24250000` writes an encounter table (background 04,
rate 0x0A, enemy groups 24 25 as script op 0x8D sets it in ZROUP04), and a few
dozen steps later a random battle starts. In battle: Left then ○ picks 戦, ○ on an
icon queues that attack (Right moves to the next icon), Up then ○ opens 道 (items).
"""
import os
import sys
import time

from PIL import Image, ImageChops, ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winds  # noqa: E402
from rsp import RSP  # noqa: E402

CUE, OUT, CMD = sys.argv[1:4]
REF = Image.open("work/ref_title_menu_win.png").convert("RGB")
os.makedirs(OUT, exist_ok=True)
open(CMD, "w").close()
p = winds.launch(CUE)
h = winds.game_window(p.pid)
rsp = None


def grab():
    for _ in range(5):  # PrintWindow sometimes returns a short buffer
        try:
            return winds.grab(h)
        except ValueError:
            time.sleep(0.5)
    raise RuntimeError("no frame (is the emulator window minimized?)")


def at_title():
    crop = grab().crop((150, 370, 370, 510))
    return sum(ImageStat.Stat(ImageChops.difference(crop, REF)).mean) / 3 < 15


for i in range(120):
    if at_title():
        break
    if i > 8:
        winds.key(h, "Return")
    time.sleep(2)
else:
    raise SystemExit("title menu never appeared")
print("title", flush=True)
done = 0
while True:
    lines = open(CMD, encoding="utf-8").read().splitlines()
    for ln in lines[done:]:
        a = ln.split()
        if not a:
            continue
        if a[0] == "quit":
            p.kill()
            print("bye", flush=True)
            sys.exit()
        if a[0] == "shot":
            grab().save(f"{OUT}/{a[1]}.png")
            print("shot", a[1], flush=True)
        if a[0] == "poke":
            if rsp is None:
                rsp = RSP(timeout=30)
                rsp.send("?")  # the server reports the target as stopped on connect
            else:
                rsp.interrupt()
            rsp.send(f"M{int(a[1], 16):x},{len(a[2]) // 2}:{a[2]}")
            rsp.send("c", wait=False)
            print("poked", a[1], a[2], flush=True)
        if a[0] == "k":
            n = int(a[2]) if len(a) > 2 else 1
            wait = float(a[3]) if len(a) > 3 else 1
            for _ in range(n):
                winds.key(h, a[1])
                time.sleep(wait)
            print("key", a[1:], flush=True)
    done = len(lines)
    time.sleep(0.3)

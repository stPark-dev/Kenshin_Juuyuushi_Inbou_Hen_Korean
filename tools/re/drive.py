"""Boot an image to the title menu, then follow commands appended to a file.

usage: drive.py image.cue outdir cmdfile [--state N]
--state N boots straight into save-state slot N instead of waiting for the title.
Commands, one per line, read as they are appended:
  k KEY [N] [WAIT]   press KEY N times, WAIT seconds after each (winds key names:
                     z=○ x=× a=□ s=△ Return=Start BackSpace=Select, arrows)
  shot NAME          save the frame as outdir/NAME.png
  wait SECONDS       pause before the next command
  poke ADDR HEX      write bytes to RAM through the GDB server (attached on first use)
  dump FILE          save main RAM (2 MB) to FILE through the GDB server
  save N             save state to slot N (1-4, hotkeys F1-F4 in the portable settings)
  quit               close the emulator

Save states hold all of RAM: whatever was already loaded when the state was saved
(the unpacked main program: item and skill names, descriptions, menu fonts) keeps
the old build's bytes. Scene files and the MAPCODE/BTLCODE overlays are read from
the disc again when the game next loads them, so a state taken before that load
shows the current build. Use a state for navigation, and boot from the title
whenever the main program changed.
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


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winds  # noqa: E402
from rsp import RSP  # noqa: E402

args = sys.argv[1:]
STATE = None
if "--state" in args:
    i = args.index("--state")
    STATE = int(args[i + 1])
    del args[i:i + 2]
CUE, OUT, CMD = args[:3]
os.makedirs(OUT, exist_ok=True)
open(CMD, "w").close()
p = winds.launch(CUE, STATE)
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
    return winds.at_title(grab())


for i in range(120):
    if STATE is not None:
        time.sleep(5)  # the state is restored right after boot
        break
    if at_title():
        break
    if i > 8:
        winds.key(h, "Return")
    time.sleep(2)
else:
    raise SystemExit("title menu never appeared")
print("title" if STATE is None else f"state {STATE}", flush=True)
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
        if a[0] == "save":
            winds.key(h, f"F{int(a[1])}")
            time.sleep(2)
            print("saved", a[1], flush=True)
        if a[0] == "wait":
            time.sleep(float(a[1]))
            print("waited", a[1], flush=True)
        if a[0] == "shot":
            grab().save(f"{OUT}/{a[1]}.png")
            print("shot", a[1], flush=True)
        if a[0] in ("poke", "dump"):
            if rsp is None:
                rsp = RSP(timeout=30)
                rsp.send("?")  # the server reports the target as stopped on connect
            else:
                rsp.interrupt()
            if a[0] == "poke":
                rsp.send(f"M{int(a[1], 16):x},{len(a[2]) // 2}:{a[2]}")
            else:
                with open(a[1], "wb") as f:
                    f.write(rsp.read_mem(0x80000000, 0x200000))
            rsp.send("c", wait=False)
            print(a[0], *a[1:], flush=True)
        if a[0] == "k":
            n = int(a[2]) if len(a) > 2 else 1
            wait = float(a[3]) if len(a) > 3 else 1
            for _ in range(n):
                winds.key(h, a[1])
                time.sleep(wait)
            print("key", a[1:], flush=True)
    done = len(lines)
    time.sleep(0.3)

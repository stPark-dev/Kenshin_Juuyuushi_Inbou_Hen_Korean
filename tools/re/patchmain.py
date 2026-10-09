"""Test image: patch the unpacked main program and repack it.

usage: patchmain.py in.bin out.bin ADDR hex [ADDR hex ...]   (hex = bytes as stored, LE)

Ending credits without playing (2026-10-10, docs/survey.md §3.1.9):
  patchmain.py IMAGE.bin build/endtest.bin 8002e754 a4ba0008
turns the title call in the main loop into `j 0x8002ea90` (the ending path:
ending movie, ROLL credits, clear-data save). After boot the opening movie and the
attract demo still play (~3 min) before the title would come; then the ending
movie (~5 min) and the credits (~6 min). Patch the disc, not RAM: the main loop's
blocks are compiled before the title, so a GDB poke there does not take.
"""
import sys; sys.path.insert(0, "tools")
from pathlib import Path
import iso, mainprog, bootlz
src, out = sys.argv[1:3]
raw = Path(src).read_bytes(); disc = iso.load(raw)
name = mainprog.exe_name(disc)
exe = iso.read_file(raw, disc, name)
main = bytearray(mainprog.unpack(exe))
for at, hx in zip(sys.argv[3::2], sys.argv[4::2]):
    o, new = int(at, 16) - mainprog.BASE, bytes.fromhex(hx)
    print(at, main[o:o + len(new)].hex(), "->", new.hex())
    main[o:o + len(new)] = new
packed = bootlz.encode(bytes(main)); room = len(exe) - mainprog.BLOB
assert len(packed) <= room
image = iso.apply(raw, iso.plan(raw, disc, {name: exe[:mainprog.BLOB] + packed + bytes(room - len(packed))}))
o = Path(out); o.write_bytes(image)
o.with_suffix(".cue").write_text(f'FILE "{o.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')

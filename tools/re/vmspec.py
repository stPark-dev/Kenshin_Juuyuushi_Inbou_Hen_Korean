"""Derive per-opcode operand layout of the script VM from a RAM dump.

Straight-line walk of each handler (and called helpers) counting:
  T = typed operand (call to READ1), raw bytes from `addiu $s2,$s2,k`.
Branches are followed on the fall-through path only and flagged.
"""
import json
import struct
import sys

import capstone

ram = open(sys.argv[1], "rb").read()
R = lambda a: ram[a - 0x80000000 :]
TABLE, DISPATCH, END = 0x801D7D20, 0x801D7CD8, 0x801D8028
READ1, READ2 = 0x801D9F4C, 0x801D9F30
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
cache = {}


def summarize(addr, depth=0):
    """Return (items, flags) consumed by straight-line code from addr until return/dispatch."""
    if addr in cache:
        return cache[addr]
    cache[addr] = ([], {"recursion"})
    body = list(md.disasm(R(addr)[:0x400], addr))
    if depth > 0 and any(i.mnemonic == "sw" and i.op_str.startswith("$s2,") for i in body[:12]):
        cache[addr] = ([], {"saves_s2"})  # helper uses $s2 as a local, not the bytecode pointer
        return cache[addr]
    items, flags = [], set()
    pending_exit = None
    for ins in md.disasm(R(addr)[:0x800], addr):
        m, o = ins.mnemonic, ins.op_str
        if m in ("addiu", "addi") and o.startswith("$s2, $s2,"):
            k = int(o.split(",")[-1], 0)
            items.append(("raw", k))
        elif "$s2" in o and m not in ("lbu", "lb", "lhu", "lh", "lw", "lwr", "lwl", "addiu", "addi"):
            flags.add(f"s2:{m}")
        if m == "jal":
            t = int(o, 0)
            if t == READ1:
                items.append(("T", 1))
            elif t == READ2:
                items.append(("T", 2))
            elif 0x801C0000 <= t < 0x801E4000 and depth < 4:
                sub, sf = summarize(t, depth + 1)
                items += sub
                flags |= {f"via:{x}" for x in sf}
        if m.startswith("b") and m != "break":
            flags.add("branch")
        if pending_exit:
            break
        if m == "j":
            t = int(o, 0)
            pending_exit = "dispatch" if t == DISPATCH else "end" if t == END else f"j:{t:08x}"
            flags.add(pending_exit)
        elif m == "jr":
            pending_exit = "ret"
            flags.add("ret" if o == "$ra" else f"jr:{o}")
    cache[addr] = (items, flags)
    return items, flags


table = [struct.unpack_from("<I", R(TABLE), 4 * i)[0] for i in range(256)]
spec = {}
for op, h in enumerate(table):
    items, flags = summarize(h)
    T = sum(n for k, n in items if k == "T")
    raw = sum(n for k, n in items if k == "raw")
    spec[op] = {"handler": f"{h:08x}", "typed": T, "raw": raw, "order": items, "flags": sorted(flags)}
json.dump(spec, open(sys.argv[2], "w"), indent=1)
clean = [op for op, s in spec.items() if not any(f in ("branch",) or f.startswith(("s2:", "jr:", "j:", "via:")) for f in s["flags"])]
print("opcodes", len(spec), "straight-line (no branch/odd s2 use):", len(clean))

"""Control-flow traversal of GROUP script bytecode from entry 0x10.

Uses the derived spec + hand overrides. Follows jump/call targets (kind-7
operands of flow opcodes), stops paths at terminators. Reports coverage,
failures and the confirmed 0x49 string-reference sites.
"""
import sys

TSIZE = {0: 1, 1: 2, 2: 3, 3: 5, 4: 1, 5: 1, 6: 2, 7: 5, 8: 5}
COND_ALWAYS = 0  # condition code 0 -> always true (0x801E9ED4 table)


class Fail(Exception):
    pass


def typed(d, q):
    t = d[q] >> 4
    if t not in TSIZE:
        raise Fail(f"bad operand type byte 0x{d[q]:02x} at 0x{q:x}")
    val = int.from_bytes(d[q + 1 : q + 5], "little") if t in (3, 7) else None
    return q + TSIZE[t], t, val


def decode(spec, d, p):
    """Return (next, targets, terminal, refs) for the instruction at p."""
    op = d[p]
    s = spec.get(op)
    if s is None or any(f.startswith("jr:$k0") for f in s.get("flags", [])):
        raise Fail(f"invalid opcode 0x{op:02x} at 0x{p:x}")
    q, targets, refs, terminal = p + 1, [], [], False
    if op in (0x2C, 0x2D):  # cond jump / cond call: u8 cond, T target
        cond = d[q]
        q, t, val = typed(d, q + 1)
        if t == 7:
            targets.append(val)
        elif t != 0:
            raise Fail(f"op 0x{op:02x} target kind {t} at 0x{p:x}")
        terminal = op == 0x2C and cond == COND_ALWAYS
    elif op in (0x2E, 0x2F):  # cond return / cond end
        terminal = d[q] == COND_ALWAYS
        q += 1
    elif op == 0x35:
        terminal = True
    elif op in (0x85, 0xA6):  # unconditional jump to one of two targets
        for _ in range(2):
            q, t, val = typed(d, q)
            if t == 7:
                targets.append(val)
        terminal = True
    elif op == 0x92:  # inline NUL-terminated string
        end = d.index(b"\0", q)
        refs.append(("inline", q, end - q))
        q = end + 1
    elif op == 0x49:
        refs.append(("text", q + 1, int.from_bytes(d[q + 1 : q + 5], "little")))
        q += 5
    elif "custom" in s:
        q = CUSTOM[s["custom"]](d, q)
    else:
        for kind, k in s["order"]:
            if kind == "T":
                for _ in range(k):
                    q2, t, val = typed(d, q)
                    if t == 7:
                        refs.append(("k7", q + 1, val))
                    q = q2
            elif kind == "ref":
                refs.append(("ref", q, int.from_bytes(d[q : q + 4], "little")))
                q += 4
            else:
                q += k
    if q <= p:
        raise Fail(f"op 0x{op:02x} non-advancing at 0x{p:x}")
    return q, targets, terminal, refs


def _op34(d, q):
    mode = d[q]
    q, _, _ = typed(d, q + 1)
    if mode < 2:
        return q
    if mode in (2, 4):
        return q + 4
    if mode == 3:
        return typed(d, q + 4)[0]
    return typed(d, q)[0]


CUSTOM = {"op34": _op34}


def traverse(spec, d, limit, entries=(0x10,)):
    seen, refs, fails = {}, [], []
    work = list(entries)
    while work:
        p = work.pop()
        while p not in seen:
            if not (0x10 <= p < limit):
                fails.append(f"target 0x{p:x} outside code area")
                break
            try:
                q, targets, terminal, r = decode(spec, d, p)
            except (Fail, ValueError, IndexError) as e:
                fails.append(str(e))
                break
            seen[p] = (d[p], q - p)
            refs += r
            work += [t for t in targets if t not in seen]
            if terminal:
                break
            p = q
    return seen, refs, fails

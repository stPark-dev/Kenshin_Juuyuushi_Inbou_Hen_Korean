"""Linear walk of script bytecode using a derived opcode spec; stops at the first inconsistency."""
import json, struct, sys
TSIZE = {0: 1, 1: 2, 2: 3, 3: 5, 4: 1, 5: 1, 6: 2, 7: 5, 8: 5}


def load_spec(path, overrides=None):
    spec = {int(k): v for k, v in json.load(open(path)).items()}
    for op, v in (overrides or {}).items():
        spec[op] = dict(v, flags=[], override=True)
    return spec


def _typed(d, q):
    t = d[q] >> 4
    if t not in TSIZE:
        raise ValueError(f"bad operand type byte 0x{d[q]:02x}")
    return q + TSIZE[t]


def _op34(d, q):
    mode = d[q]
    q = _typed(d, q + 1)
    if mode < 2:
        return q
    if mode == 2 or mode == 4:
        return q + 4
    if mode == 3:
        return _typed(d, q + 4)
    return _typed(d, q)


CUSTOM = {"op34": _op34}


def walk(spec, d, start, end):
    p, n, ops = start, 0, []
    while p < end:
        op = d[p]
        s = spec[op]
        if any(f.startswith("jr:$k0") for f in s.get("flags", [])):
            return p, n, ops, f"invalid opcode 0x{op:02x}"
        q = p + 1
        if "custom" in s:
            try:
                q = CUSTOM[s["custom"]](d, q)
            except ValueError as e:
                return p, n, ops, f"op 0x{op:02x}: {e}"
            ops.append((p, op, q - p))
            p, n = q, n + 1
            continue
        for kind, k in s["order"]:
            if kind == "T":
                for _ in range(k):
                    t = d[q] >> 4
                    if t not in TSIZE:
                        return p, n, ops, f"op 0x{op:02x}: bad operand type byte 0x{d[q]:02x} at +{q - p}"
                    q += TSIZE[t]
            elif kind == "ref":  # u32 file-relative offset (relocatable)
                q += 4
            else:
                q += k
        if q <= p:
            return p, n, ops, f"op 0x{op:02x}: non-advancing ({q - p})"
        ops.append((p, op, q - p))
        p, n = q, n + 1
    return p, n, ops, "ok" if p == end else f"overran end by {p - end}"

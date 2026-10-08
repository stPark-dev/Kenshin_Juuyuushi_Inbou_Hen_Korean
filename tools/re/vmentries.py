"""Fixpoint entry discovery + failure statistics for rejected candidates."""
import sys, json, glob, struct, collections
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, 'tools')
import vmflow, vmwalk, script
ov = {int(k, 16): v for k, v in json.load(open('docs/re/vm_overrides.json')).items()}
spec = vmwalk.load_spec('work/vmspec.json', ov)


def analyse(d, h):
    lim = h[2]
    entries, rejected, why = {0x10, h[0]}, set(), collections.Counter()
    cands = set(struct.unpack_from('<I', d, o)[0] for o in range(h[1], h[2] - 3, 4))
    while True:
        seen, refs, fails = vmflow.traverse(spec, d, lim, tuple(entries))
        k7 = {v for k, q, v in refs if k == 'k7'}
        new = False
        for c in (k7 | cands):
            if 0x10 <= c < lim and c not in seen and c not in rejected and c not in entries:
                s2, r2, f2 = vmflow.traverse(spec, d, lim, (c,))
                if not f2 and len(s2) >= 2:
                    entries.add(c); new = True
                else:
                    rejected.add(c)
                    if f2 and len(s2) >= 3:  # looked like code for a while, then failed
                        why[f2[0].split(' at ')[0]] += 1
        if not new:
            return entries, seen, refs, why


if __name__ == '__main__':
    tot, why_all = collections.Counter(), collections.Counter()
    for p in sorted(glob.glob('work/grp/ZROUP*/GROUP*.BIN')):
        d = open(p, 'rb').read(); g = script.parse_group(d); h = g.header
        entries, seen, refs, why = analyse(d, h)
        why_all += why
        starts = {s.offset for s in g.strings}
        conf = {v for k, q, v in refs if k == 'text'}
        tot['strings'] += len(starts); tot['confirmed'] += len(starts & conf); tot['ops'] += len(seen)
    print(dict(tot))
    for k, v in why_all.most_common(20):
        print(v, k)

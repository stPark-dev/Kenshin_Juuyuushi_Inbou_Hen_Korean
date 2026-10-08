"""GRP container (SYSTEM.GRP, ZROUPnn.GRP) parse and rebuild.

Layout, established on all 59 GRP files of SCPS-10048:
  u32 header_size, u32 count
  count x { u16 name_offset, u16 unk, u32 size, u32 offset }
  NUL-terminated names up to header_size
Entries are sorted by offset; the first starts at header_size rounded up to
0x800, each next one at the previous end rounded up to 0x800, and the file
ends on that boundary. Padding is NOT zero, so unchanged entries keep their
original padding bytes. `unk` does not depend on offset or size and is kept.
Names are not unique (ZROUP20.GRP stores 34 names twice as byte-identical
copies), so access by an ambiguous name is refused.
"""

import struct
from dataclasses import dataclass, replace as dc_replace

ALIGN = 0x800
ENTRY = struct.Struct("<HHII")


def _align(n):
    return (n + ALIGN - 1) & ~(ALIGN - 1)


@dataclass(frozen=True)
class Entry:
    name: str
    unk: int
    data: bytes
    name_offset: int
    orig_offset: int
    orig_size: int


@dataclass(frozen=True)
class Grp:
    header: bytes
    entries: tuple
    raw: bytes

    def get(self, name):
        return self._find(name).data

    def replace(self, name, data):
        e = self._find(name)
        entries = tuple(dc_replace(x, data=bytes(data)) if x is e else x for x in self.entries)
        return Grp(self.header, entries, self.raw)

    def _find(self, name):
        found = [e for e in self.entries if e.name == name]
        if not found:
            raise KeyError(name)
        if len(found) > 1:
            raise ValueError(f"{name}: {len(found)} entries share this name")
        return found[0]


def parse(data):
    data = bytes(data)
    if len(data) < 8:
        raise ValueError("GRP shorter than its fixed header")
    hs, n = struct.unpack_from("<II", data, 0)
    if hs > len(data) or 8 + ENTRY.size * n > hs:
        raise ValueError("GRP entry table exceeds header size")
    entries = []
    min_off = _align(hs)
    for i in range(n):
        no, unk, size, off = ENTRY.unpack_from(data, 8 + ENTRY.size * i)
        end = data.find(b"\0", no, hs)
        if not (8 + ENTRY.size * n <= no < hs) or end < 0:
            raise ValueError(f"entry {i}: name offset 0x{no:x} outside name table")
        if off + size > len(data):
            raise ValueError(f"entry {i}: data 0x{off:x}+0x{size:x} beyond file end")
        if off % ALIGN or off < min_off:
            raise ValueError(f"entry {i}: offset 0x{off:x} misaligned, unsorted, or overlapping")
        min_off = _align(off + size)
        name = data[no:end].decode("ascii")
        entries.append(Entry(name, unk, data[off : off + size], no, off, size))
    return Grp(data[:hs], tuple(entries), data)


def build(g):
    """Rebuild the container; byte-identical when nothing changed."""
    out = bytearray(g.header)
    pos = _align(len(g.header))
    out += g.raw[len(g.header) : pos] if len(g.raw) >= pos else bytes(pos - len(g.header))
    for i, e in enumerate(g.entries):
        end = _align(pos + len(e.data))
        unchanged = pos == e.orig_offset and e.data == g.raw[e.orig_offset : e.orig_offset + e.orig_size]
        if unchanged and len(g.raw) >= end:
            out += g.raw[pos:end]
        else:
            out += e.data + bytes(end - pos - len(e.data))
        ENTRY.pack_into(out, 8 + ENTRY.size * i, e.name_offset, e.unk, len(e.data), pos)
        pos = end
    return bytes(out)

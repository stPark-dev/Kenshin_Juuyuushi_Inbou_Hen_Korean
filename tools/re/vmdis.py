"""Disassemble a VM opcode handler (and one level of called helpers) from a RAM dump."""
import json, struct, sys
import capstone
ram = open(sys.argv[1], 'rb').read()
R = lambda a: ram[a - 0x80000000:]
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN)
KNOWN = {0x801d9f4c: 'READ1', 0x801d9f30: 'READ2', 0x801d7cd8: 'DISPATCH', 0x801d8028: 'END'}
def dis(a, n=48, indent=''):
    out = []
    for ins in md.disasm(R(a)[:4 * n], a):
        o = ins.op_str
        if ins.mnemonic in ('jal', 'j') and int(o, 0) in KNOWN:
            o += f'  <{KNOWN[int(o, 0)]}>'
        print(f'{indent}{ins.address:08x} {ins.mnemonic} {o}')
        out.append(ins)
        if ins.mnemonic in ('j', 'jr') and not ins.op_str.startswith('$t'):
            nxt = next(md.disasm(R(ins.address + 4)[:4], ins.address + 4))
            print(f'{indent}{nxt.address:08x} {nxt.mnemonic} {nxt.op_str}')
            break
    return out
for op in sys.argv[2:]:
    op = int(op, 16)
    h = struct.unpack_from('<I', R(0x801d7d20), 4 * op)[0]
    print(f'=== op 0x{op:02x} handler {h:08x}')
    for ins in dis(h, 64):
        if ins.mnemonic == 'jal' and int(ins.op_str, 0) not in KNOWN and 0x801c0000 <= int(ins.op_str, 0) < 0x801e4000:
            print(f'   --- callee {ins.op_str}')
            dis(int(ins.op_str, 0), 40, '      ')

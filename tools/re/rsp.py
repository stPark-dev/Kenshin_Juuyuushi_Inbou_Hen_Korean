"""Minimal GDB remote serial protocol client for DuckStation's GDB server."""
import socket


class RSP:
    def __init__(self, host="127.0.0.1", port=2345, timeout=10):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.buf = b""

    def _read(self):
        chunk = self.s.recv(65536)
        if not chunk:
            raise ConnectionError("gdb server closed")
        self.buf += chunk

    def _packet(self):
        while True:
            while self.buf[:1] in (b"+", b"-"):
                self.buf = self.buf[1:]
            start = self.buf.find(b"$")
            end = self.buf.find(b"#", start + 1) if start >= 0 else -1
            if start >= 0 and end >= 0 and len(self.buf) >= end + 3:
                body = self.buf[start + 1 : end]
                self.buf = self.buf[end + 3 :]
                self.s.sendall(b"+")
                return body.decode("latin-1")
            self._read()

    def send(self, cmd, wait=True):
        data = cmd.encode("latin-1")
        pkt = b"$" + data + b"#" + b"%02x" % (sum(data) & 0xFF)
        self.s.sendall(pkt)
        return self._packet() if wait else None

    def interrupt(self):
        self.s.sendall(b"\x03")
        return self._packet()

    def wait_stop(self, timeout=None):
        old = self.s.gettimeout()
        self.s.settimeout(timeout)
        try:
            return self._packet()
        finally:
            self.s.settimeout(old)

    def read_mem(self, addr, length, chunk=0x800):
        out = bytearray()
        while length > 0:
            n = min(chunk, length)
            r = self.send(f"m{addr:x},{n:x}")
            if r.startswith("E"):
                raise IOError(f"read {addr:#x}: {r}")
            out += bytes.fromhex(r)
            addr += n
            length -= n
        return bytes(out)

    def regs(self):
        r = self.send("g")
        words = [int.from_bytes(bytes.fromhex(r[i : i + 8]), "little") for i in range(0, len(r), 8)]
        return words  # r0..r31, sr, lo, hi, bad, cause, pc (gdb mips order)

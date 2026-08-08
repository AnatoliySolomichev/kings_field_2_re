#!/usr/bin/env python3
"""Minimal GDB remote-serial-protocol client for PCSX-Redux.

The system gdb has no MIPS target, so instead of driving gdb we speak the
remote protocol directly -- enough to halt/resume the emulator, read and write
PlayStation RAM, and read the CPU registers.
"""
import socket
import struct

# MIPS r3000 register order used by PCSX-Redux's GDB stub
REGNAMES = (["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
             "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
             "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
             "t8", "t9", "k0", "k1", "gp", "sp", "s8", "ra"]
            + ["sr", "lo", "hi", "bad", "cause", "pc"])


class Dbg:
    def __init__(self, host="127.0.0.1", port=3333, timeout=10):
        self.s = socket.create_connection((host, port), timeout)
        self.s.settimeout(timeout)
        self.buf = b""
        self.noack = False
        try:
            if self.cmd("QStartNoAckMode") == "OK":
                self.noack = True
        except Exception:
            pass

    # ---- packet plumbing -------------------------------------------------
    def _send(self, data):
        pkt = b"$" + data.encode() + b"#%02x" % (sum(data.encode()) & 0xFF)
        self.s.sendall(pkt)

    def _read(self, n):
        while len(self.buf) < n:
            d = self.s.recv(65536)
            if not d:
                raise EOFError("gdb server closed")
            self.buf += d
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv(self):
        while True:
            c = self._read(1)
            if c == b"+":
                continue
            if c == b"-":
                raise IOError("packet nak")
            if c == b"$":
                break
        body = b""
        while True:
            c = self._read(1)
            if c == b"#":
                break
            body += c
        self._read(2)                      # checksum
        if not self.noack:
            self.s.sendall(b"+")
        return body.decode(errors="replace")

    def cmd(self, data):
        self._send(data)
        return self._recv()

    # ---- operations ------------------------------------------------------
    def halt(self):
        self.s.sendall(b"\x03")
        try:
            return self._recv()
        except socket.timeout:
            return ""

    def cont(self):
        self._send("c")

    def status(self):
        return self.cmd("?")

    def regs(self):
        r = self.cmd("g")
        vals = [struct.unpack("<I", bytes.fromhex(r[i:i + 8]))[0]
                for i in range(0, min(len(r), 38 * 8), 8)]
        return dict(zip(REGNAMES, vals))

    def read(self, addr, length):
        out = b""
        while length:
            n = min(length, 1024)
            r = self.cmd("m%x,%x" % (addr, n))
            if r.startswith("E") or not r:
                raise IOError(f"read error at {addr:#x}: {r!r}")
            out += bytes.fromhex(r)
            addr += n
            length -= n
        return out

    def write(self, addr, data):
        r = self.cmd("M%x,%x:%s" % (addr, len(data), data.hex()))
        if r != "OK":
            raise IOError(f"write error at {addr:#x}: {r!r}")

    def close(self):
        self.s.close()


if __name__ == "__main__":
    d = Dbg()
    print("noack:", d.noack)
    print("status:", d.status())
    r = d.regs()
    print("pc = %08x  sp = %08x  ra = %08x" % (r.get("pc", 0), r.get("sp", 0), r.get("ra", 0)))
    mem = d.read(0x80011000, 64)
    print("RAM @80011000:", mem.hex())
    d.cont()
    d.close()

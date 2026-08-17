#!/usr/bin/env python3
"""MIPS R3000 disassembly of GAME.EXE, driven by the addresses already found.

Capstone is not installed, but PCSX-Redux ships libcapstone.so.4, so it is
bound here through ctypes. Three details cost time getting this right:

  * `cs_arch` puts MIPS at 2 -- 3 is x86, and asking for 3 quietly produces
    plausible-looking x86 output;
  * capstone 4's `cs_insn.bytes` is 16 wide (v5 widened it to 24), and a wrong
    width silently shifts `mnemonic` and `op_str` into garbage;
  * the buffer must be passed as `c_void_p`, since `c_char_p` stops at the
    first NUL and MIPS code is full of them.

The text section opens with the game's filename strings, so disassembly starts
from the entry point and steps over whatever does not decode.

An absolute address is never a single instruction on MIPS: the compiler emits
`lui rX, %hi(addr)` and then a load/store/addiu carrying `%lo(addr)`, so
finding who touches the player position means pairing those two.
"""
import ctypes
import glob
import struct
import sys

CS_ARCH_MIPS = 2
CS_MODE_MIPS32 = 1 << 2
LIB = "emu/squashfs-root/usr/lib/libcapstone.so.4"
EXE = "extract/GAME.EXE"
HDR = 0x800


class CsInsn(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint),
                ("address", ctypes.c_uint64),
                ("size", ctypes.c_uint16),
                ("bytes", ctypes.c_ubyte * 16),
                ("mnemonic", ctypes.c_char * 32),
                ("op_str", ctypes.c_char * 160),
                ("detail", ctypes.c_void_p)]


class Cs:
    def __init__(self):
        path = glob.glob(LIB)
        if not path:
            raise RuntimeError("libcapstone.so.4 not found; unpack the emulator first")
        self.lib = ctypes.CDLL(path[0])
        self.lib.cs_disasm.restype = ctypes.c_size_t
        self.lib.cs_disasm.argtypes = [ctypes.c_size_t, ctypes.c_void_p,
                                       ctypes.c_size_t, ctypes.c_uint64,
                                       ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.POINTER(CsInsn))]
        self.h = ctypes.c_size_t()
        err = self.lib.cs_open(CS_ARCH_MIPS, CS_MODE_MIPS32, ctypes.byref(self.h))
        if err:
            raise RuntimeError(f"cs_open failed: {err}")
        self.buf = None

    def load(self, code, base):
        """Copy the image in once; every later call points into this buffer."""
        self.buf = (ctypes.c_ubyte * len(code)).from_buffer_copy(code)
        self.ptr = ctypes.addressof(self.buf)
        self.size = len(code)
        self.base = base

    def at(self, off, count=0):
        out = ctypes.POINTER(CsInsn)()
        n = self.lib.cs_disasm(self.h, self.ptr + off, self.size - off,
                               self.base + off, count, ctypes.byref(out))
        res = [(out[i].address, out[i].mnemonic.decode("latin-1"),
                out[i].op_str.decode("latin-1")) for i in range(n)]
        if n:
            self.lib.cs_free(out, n)
        return res

    def all(self, start=0):
        """Everything that decodes, stepping a word past anything that does not."""
        out, pos = [], start
        while pos < self.size:
            got = self.at(pos)
            if not got:
                pos += 4
                continue
            out.extend(got)
            pos = (got[-1][0] - self.base) + 4
        return out


def load_text(path=EXE):
    d = open(path, "rb").read()
    base = struct.unpack_from("<I", d, 0x18)[0]
    size = struct.unpack_from("<I", d, 0x1C)[0]
    entry = struct.unpack_from("<I", d, 0x10)[0]
    return base, entry, d[HDR:HDR + size]


LO = ("addiu", "ori", "lw", "sw", "lb", "lbu", "sb", "lh", "lhu", "sh",
      "addu", "lwl", "lwr", "swl", "swr")


def _ops(op):
    return [o.strip() for o in op.split(",")]


def xrefs(insns, targets, window_size=24):
    """Pair each `lui` with a later %lo user and report the address it forms."""
    want = {t: [] for t in targets}
    tset = set(targets)
    pend = {}
    for i, (addr, mn, op) in enumerate(insns):
        if mn == "lui":
            o = _ops(op)
            if len(o) == 2:
                try:
                    pend[o[0]] = (int(o[1], 0) << 16, addr, i)
                except ValueError:
                    pass
            continue
        if mn not in LO or not pend:
            continue
        o = _ops(op)
        for reg, (hi, hiaddr, hidx) in list(pend.items()):
            if i - hidx > window_size:
                del pend[reg]
                continue
            lo = None
            if mn in ("addiu", "ori") and len(o) == 3 and o[1] == reg:
                try:
                    lo = int(o[2], 0)
                except ValueError:
                    pass
            elif len(o) == 2 and o[1].endswith(f"({reg})"):
                try:
                    lo = int(o[1].split("(")[0], 0)
                except ValueError:
                    pass
            if lo is None:
                continue
            if lo > 0x7FFF:
                lo -= 0x10000
            eff = (hi + lo) & 0xFFFFFFFF
            if eff in tset:
                want[eff].append((hiaddr, addr, mn, op))
    return want


def window(insns, addr, before=8, after=20):
    idx = next((i for i, x in enumerate(insns) if x[0] == addr), None)
    if idx is None:
        return []
    return insns[max(0, idx - before): idx + after]


def build():
    cs = Cs()
    base, entry, text = load_text()
    cs.load(text, base)
    return cs, base, entry, cs.all(entry - base)


if __name__ == "__main__":
    cs, base, entry, insns = build()
    print(f"text {base:#010x}..{base + cs.size:#010x}, entry {entry:#010x}")
    print(f"disassembled {len(insns)} instructions "
          f"({len(insns) * 4 * 100 // cs.size}% of the section)")
    import syms
    targets = [int(a, 0) for a in sys.argv[1:]] or [0x801AEC4C, 0x800C85E8]
    for t, lst in xrefs(insns, targets).items():
        print(f"\n=== {syms.label(t)} ({t:#010x}): {len(lst)} references")
        for hiaddr, addr, mn, op in lst[:16]:
            print(f"   {syms.label(addr):28s} {mn:6s} {syms.annotate(op)}")

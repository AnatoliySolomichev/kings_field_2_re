#!/usr/bin/env python3
"""The four executables, and enough MIPS to walk their call graphs.

The disc boots a shell (`SLUS_002.55`) that hands over to one of three
overlays -- `OPEN.EXE`, `GAME.EXE`, `END.EXE` -- and **all three load at the
same address**, `0x80011000`. So an address on its own does not identify code
here: `0x80013a20` is a different routine in each. Everything in this module
therefore takes an executable with it, and the symbol tables are per
executable too (`data/symbols.json` is GAME.EXE's; see tools/syms.py).

    import mips
    exe = mips.load("open")
    exe.word(0x80013a20)          one instruction
    exe.calls(f)                  what a routine calls, in order

Decoding is done here by hand rather than through capstone, because the graph
only needs six opcodes and doing it directly means no dependency on the
emulator's AppImage being unpacked. tools/fdis.py is still the thing to read a
listing with -- it names the GTE registers, which capstone will not decode at
all.
"""
import os
import struct

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# nickname -> (file, what it is). The header carries the load address and the
# entry point, so neither is written down here.
EXES = {
    "boot": ("extract/SLUS_002.55", "the shell: picks which overlay runs next"),
    "open": ("extract/OPEN.EXE", "logos, the opening movie, the title menu"),
    "game": ("extract/GAME.EXE", "the game itself"),
    "end":  ("extract/END.EXE", "the ending"),
}

GPR = ("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 "
       "s7 t8 t9 k0 k1 gp sp fp ra").split()


class Exe:
    """A PS-EXE: its text, where it loads, and where it starts."""

    def __init__(self, path, nick=None):
        d = open(path, "rb").read()
        if d[:8] != b"PS-X EXE":
            raise ValueError(f"{path} is not a PS-EXE")
        self.path, self.nick = path, nick or os.path.basename(path)
        self.entry, self.gp, self.base, self.size = struct.unpack_from("<4I", d, 0x10)
        self.sp = struct.unpack_from("<I", d, 0x30)[0]
        self.text = d[0x800:0x800 + self.size]
        self.end = self.base + self.size

    def __contains__(self, addr):
        return self.base <= addr < self.end

    def word(self, addr):
        """The 32-bit word at an address, or None if it is outside the image."""
        off = addr - self.base
        if not (0 <= off <= len(self.text) - 4):
            return None
        return struct.unpack_from("<I", self.text, off)[0]

    def bytes(self, addr, n):
        off = addr - self.base
        return self.text[off:off + n]

    def string(self, addr, limit=200):
        """A NUL-terminated string, or None if it does not look like text."""
        b = self.bytes(addr, limit)
        if not b:
            return None
        s = b.split(b"\0")[0]
        if not s or any(c > 0x7E or (c < 0x20 and c not in (9, 10, 13)) for c in s):
            return None
        return s.decode("latin-1")

    # --- one instruction ---------------------------------------------------

    def op(self, addr):
        """`(mnemonic-ish kind, operands)` for the opcodes the graph needs.

        Kinds: jal, j, jr, jalr, branch, lui, lo, syscall, other. Everything
        else is `other` on purpose -- this is a control-flow reader, not a
        disassembler.
        """
        w = self.word(addr)
        if w is None:
            return ("none", {})
        op = w >> 26
        rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm > 0x7FFF else imm
        tgt = (addr & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
        if op == 3:
            return ("jal", {"target": tgt})
        if op == 2:
            return ("j", {"target": tgt})
        if op == 0 and (w & 0x3F) == 8:
            return ("jr", {"rs": rs})
        if op == 0 and (w & 0x3F) == 9:
            return ("jalr", {"rs": rs, "rd": rd})
        if op == 0 and (w & 0x3F) == 12:
            return ("syscall", {})
        if op in (4, 5, 6, 7, 1):                      # beq bne blez bgtz regimm
            return ("branch", {"target": addr + 4 + simm * 4, "rs": rs, "rt": rt})
        if op == 15:
            return ("lui", {"rt": rt, "imm": imm})
        if op in (9, 13, 0x23, 0x2B, 0x20, 0x24, 0x28, 0x21, 0x25, 0x29):
            #        addiu ori lw sw lb lbu sb lh lhu sh
            return ("lo", {"rs": rs, "rt": rt, "simm": simm, "op": op})
        return ("other", {})


def load(which="game"):
    """An Exe by nickname (`boot`, `open`, `game`, `end`) or by path."""
    if which in EXES:
        return Exe(os.path.join(ROOT, EXES[which][0]), which)
    return Exe(which)


# Which register an instruction writes, so a pending `lui` can be forgotten
# when something else lands in that register. Leaving it pending is not a small
# error: `lui $a0, 0x8001` followed much later by an unrelated `lw $v0, ($a0)`
# reports a reference to `0x80010000` that the code never makes, and a first
# pass of this produced a hundred of them.
_STORES = (0x28, 0x29, 0x2A, 0x2B, 0x2E, 0x3A)          # sb sh swl sw swr swc2


def dest(w):
    """The register an instruction writes, or None."""
    op = w >> 26
    if op == 0:
        fn = w & 0x3F
        if fn in (8, 12, 13, 0x18, 0x19, 0x1A, 0x1B):   # jr syscall break mult div
            return None
        return (w >> 11) & 31                           # rd
    if op == 1:
        return 31 if ((w >> 16) & 31) in (0x10, 0x11) else None   # bltzal/bgezal
    if op in (2, 4, 5, 6, 7):
        return None                                     # j and the branches
    if op == 3:
        return 31                                       # jal
    if op in _STORES:
        return None
    if op == 0x12:                                      # cop2
        rs = (w >> 21) & 31
        return (w >> 16) & 31 if rs in (0, 2) else None  # mfc2 / cfc2 write rt
    if op == 0x32:
        return None                                     # lwc2 writes a GTE reg
    return (w >> 16) & 31                               # the rest write rt


# $v0..$a3, $t0..$t9 and $ra do not survive a call; $s0..$s7, $gp, $sp and $fp do.
_CLOBBERED = tuple([2, 3, 4, 5, 6, 7] + list(range(8, 16)) + [24, 25, 31])


def resolve(exe):
    """Every `lui`+%lo pair in the image, as `{use address: formed address}`.

    An absolute address is never one instruction on MIPS. Pairing them is what
    turns "this routine touches something" into "this routine touches
    `story_flags`" -- and it is also how the debug strings inside the Sony
    library name the library's own functions, which is where most of the names
    in this project's boot notes came from.
    """
    out, pend = {}, {}
    a = exe.base
    while a < exe.end:
        kind, f = exe.op(a)
        w = exe.word(a)
        if kind == "lo":
            hi = pend.get(f["rs"])
            if hi is not None:
                out[a] = (hi + f["simm"]) & 0xFFFFFFFF
        if kind in ("jal", "jalr", "syscall"):
            for r in _CLOBBERED:
                pend.pop(r, None)
        d = dest(w) if w is not None else None
        if d:
            pend.pop(d, None)
        if kind == "lui":
            pend[f["rt"]] = f["imm"] << 16
        a += 4
    return out

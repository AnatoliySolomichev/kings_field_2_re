#!/usr/bin/env python3
"""MIPS R3000A with the GTE, decoded here in full.

`tools/disasm.py` binds the capstone that ships inside the emulator's
AppImage, and `tools/fdis.py` patches the one hole capstone leaves -- it does
not decode coprocessor 2 at all, which is most of the renderer. Neither can be
*annotated*: capstone hands back a string, and a string is the one thing a
commenting pass cannot work with.

This decodes every instruction the R3000A has into a record that still knows
which registers it reads and writes, so the passes above it can propagate
constants, resolve `lui`/`%lo` pairs across a branch, and say what a jump
table holds. It has no dependency on the AppImage being unpacked.

    import mipsdis
    i = mipsdis.decode(0x27bdffe0, 0x8002ed60)
    i.fmt()            'addiu   $sp, $sp, -0x20'
    i.kind             'alu'
    i.writes, i.reads  (29, [29])

Kinds, which is what the traversal above reads rather than the mnemonic:
nop alu load store branch jump call jr jalr syscall break hilo mult div
gte cop invalid.

The GTE register names are the reason this file exists in the first place:
`ctc2 $t5, L11L12` says "the light matrix" where `ctc2 $t5, $8` says nothing.
"""

GPR = ("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 "
       "s7 t8 t9 k0 k1 gp sp fp ra").split()

# GTE data registers (cop2 r0..r31) and control registers (cop2 c0..c31).
DR = ("VXY0 VZ0 VXY1 VZ1 VXY2 VZ2 RGBC OTZ IR0 IR1 IR2 IR3 SXY0 SXY1 SXY2 SXYP "
      "SZ0 SZ1 SZ2 SZ3 RGB0 RGB1 RGB2 RES1 MAC0 MAC1 MAC2 MAC3 IRGB ORGB LZCS "
      "LZCR").split()
CR = ("R11R12 R13R21 R22R23 R31R32 R33 TRX TRY TRZ L11L12 L13L21 L22L23 L31L32 "
      "L33 RBK GBK BBK LR1LR2 LR3LG1 LG2LG3 LB1LB2 LB3 RFC GFC BFC OFX OFY H "
      "DQA DQB ZSF3 ZSF4 FLAG").split()

# What each GTE command is for, in the words of the hardware manual. These are
# external -- nocash's psx-spx and the Sony documentation -- not read off this
# game, and they are here because the renderer is unreadable without them.
GTE = {
    0x01: ("RTPS",  "perspective-transform one vertex"),
    0x06: ("NCLIP", "cross product of three screen points: winding, for backface"),
    0x0C: ("OP",    "cross product of two vectors"),
    0x10: ("DPCS",  "depth cue one colour"),
    0x11: ("INTPL", "interpolate a vector towards the far colour"),
    0x12: ("MVMVA", "matrix times vector plus translation"),
    0x13: ("NCDS",  "normal colour depth cue, one vertex"),
    0x14: ("CDP",   "colour depth cue"),
    0x16: ("NCDT",  "normal colour depth cue, three vertices"),
    0x1B: ("NCCS",  "normal colour colour, one vertex"),
    0x1C: ("CC",    "colour colour"),
    0x1E: ("NCS",   "normal colour, one vertex"),
    0x20: ("NCT",   "normal colour, three vertices"),
    0x28: ("SQR",   "square of a vector"),
    0x29: ("DCPL",  "depth cue colour light"),
    0x2A: ("DPCT",  "depth cue three colours"),
    0x2D: ("AVSZ3", "average of three Z, for the ordering table"),
    0x2E: ("AVSZ4", "average of four Z, for the ordering table"),
    0x30: ("RTPT",  "perspective-transform three vertices"),
    0x3D: ("GPF",   "general purpose interpolation"),
    0x3E: ("GPL",   "general purpose interpolation with base"),
    0x3F: ("NCCT",  "normal colour colour, three vertices"),
}

SPECIAL = {
    0x00: "sll", 0x02: "srl", 0x03: "sra", 0x04: "sllv", 0x06: "srlv",
    0x07: "srav", 0x08: "jr", 0x09: "jalr", 0x0C: "syscall", 0x0D: "break",
    0x10: "mfhi", 0x11: "mthi", 0x12: "mflo", 0x13: "mtlo", 0x18: "mult",
    0x19: "multu", 0x1A: "div", 0x1B: "divu", 0x20: "add", 0x21: "addu",
    0x22: "sub", 0x23: "subu", 0x24: "and", 0x25: "or", 0x26: "xor",
    0x27: "nor", 0x2A: "slt", 0x2B: "sltu",
}
REGIMM = {0x00: "bltz", 0x01: "bgez", 0x10: "bltzal", 0x11: "bgezal"}
IMM = {0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu", 0x0C: "andi",
       0x0D: "ori", 0x0E: "xori", 0x0F: "lui"}
LOADS = {0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw", 0x24: "lbu",
         0x25: "lhu", 0x26: "lwr"}
STORES = {0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw", 0x2E: "swr"}
# How wide each load and store is, which the annotator needs to say what a
# structure field is: `lbu` off a record reads one byte, and calling that a
# word has mislabelled a field's size more than once in this project.
WIDTH = {"lb": 1, "lbu": 1, "sb": 1, "lh": 2, "lhu": 2, "sh": 2,
         "lw": 4, "sw": 4, "lwl": 4, "lwr": 4, "swl": 4, "swr": 4,
         "lwc2": 4, "swc2": 4}
SIGNED = {"lb", "lh", "lw", "lwl", "lwr"}


class Insn:
    """One decoded instruction.

    `kind` is what control-flow passes read; `reads` and `writes` are what the
    constant propagation reads. `writes` is a GPR number or None -- a store,
    a branch and a GTE move into a coprocessor register all write no GPR.
    """
    __slots__ = ("addr", "word", "mn", "kind", "rs", "rt", "rd", "shamt",
                 "imm", "simm", "target", "reads", "writes", "gte", "cop")

    def __init__(self, addr, word):
        self.addr, self.word = addr, word
        self.mn, self.kind = "invalid", "invalid"
        self.rs = (word >> 21) & 31
        self.rt = (word >> 16) & 31
        self.rd = (word >> 11) & 31
        self.shamt = (word >> 6) & 31
        self.imm = word & 0xFFFF
        self.simm = self.imm - 0x10000 if self.imm > 0x7FFF else self.imm
        self.target = None
        self.reads, self.writes = (), None
        self.gte, self.cop = None, None

    # --- text -----------------------------------------------------------

    def fmt(self, sym=None):
        """The instruction as text. `sym(addr)` names a jump target if given."""
        mn, R = self.mn, GPR
        def s(a):
            return sym(a) if sym else f"{a:#010x}"
        if mn == "nop":
            return "nop"
        if self.kind in ("jump", "call"):
            return f"{mn:8s}{s(self.target)}"
        if mn in ("jr", "jalr"):
            return (f"{mn:8s}${R[self.rs]}" if mn == "jr" or self.rd == 31
                    else f"{mn:8s}${R[self.rd]}, ${R[self.rs]}")
        if self.kind == "branch":
            if mn in ("beq", "bne") and self.rt == 0:
                return f"{'beqz' if mn == 'beq' else 'bnez':8s}${R[self.rs]}, {s(self.target)}"
            if mn in ("beq", "bne"):
                return f"{mn:8s}${R[self.rs]}, ${R[self.rt]}, {s(self.target)}"
            return f"{mn:8s}${R[self.rs]}, {s(self.target)}"
        if mn in LOADS.values() or mn in STORES.values():
            return f"{mn:8s}${R[self.rt]}, {self.simm:#x}(${R[self.rs]})"
        if mn in ("lwc2", "swc2"):
            return f"{mn:8s}{DR[self.rt]}, {self.simm:#x}(${R[self.rs]})"
        if mn in ("mfc2", "mtc2"):
            return f"{mn:8s}${R[self.rt]}, {DR[self.rd]}"
        if mn in ("cfc2", "ctc2"):
            return f"{mn:8s}${R[self.rt]}, {CR[self.rd]}"
        if mn in ("mfc0", "mtc0", "cfc0", "ctc0"):
            return f"{mn:8s}${R[self.rt]}, ${self.rd}"
        if self.kind == "gte":
            return f"{mn:8s}{self.gte or ''}".rstrip()
        if mn == "lui":
            return f"{mn:8s}${R[self.rt]}, {self.imm:#x}"
        if mn in ("addiu", "addi", "slti", "sltiu"):
            if self.rs == 0:
                return f"{'li':8s}${R[self.rt]}, {self.simm:#x}" if mn.startswith("addi") \
                    else f"{mn:8s}${R[self.rt]}, $zero, {self.simm:#x}"
            return f"{mn:8s}${R[self.rt]}, ${R[self.rs]}, {self.simm:#x}"
        if mn in ("andi", "ori", "xori"):
            if mn == "ori" and self.rs == 0:
                return f"{'li':8s}${R[self.rt]}, {self.imm:#x}"
            return f"{mn:8s}${R[self.rt]}, ${R[self.rs]}, {self.imm:#x}"
        if mn in ("sll", "srl", "sra"):
            return f"{mn:8s}${R[self.rd]}, ${R[self.rt]}, {self.shamt}"
        if mn in ("sllv", "srlv", "srav"):
            return f"{mn:8s}${R[self.rd]}, ${R[self.rt]}, ${R[self.rs]}"
        if mn in ("mult", "multu", "div", "divu"):
            return f"{mn:8s}${R[self.rs]}, ${R[self.rt]}"
        if mn in ("mfhi", "mflo"):
            return f"{mn:8s}${R[self.rd]}"
        if mn in ("mthi", "mtlo"):
            return f"{mn:8s}${R[self.rs]}"
        if mn == "move":
            return f"{mn:8s}${R[self.rd]}, ${R[self.rs] if self.rt == 0 else R[self.rt]}"
        if self.kind == "alu" and mn in SPECIAL.values():
            return f"{mn:8s}${R[self.rd]}, ${R[self.rs]}, ${R[self.rt]}"
        if mn in ("syscall", "break", "rfe"):
            return mn
        return f".word   {self.word:#010x}"

    def __repr__(self):
        return f"<{self.addr:#010x} {self.fmt()}>"


def decode(word, addr):
    """One 32-bit word at an address, as an `Insn`."""
    i = Insn(addr, word)
    op = word >> 26
    rs, rt, rd = i.rs, i.rt, i.rd

    if op == 0:                                          # SPECIAL
        fn = word & 0x3F
        mn = SPECIAL.get(fn)
        if mn is None:
            return i
        i.mn = mn
        if mn in ("sll", "srl", "sra"):
            i.kind, i.reads, i.writes = "alu", (rt,), rd
            if word == 0:
                i.mn, i.kind = "nop", "nop"
        elif mn in ("sllv", "srlv", "srav"):
            i.kind, i.reads, i.writes = "alu", (rs, rt), rd
        elif mn == "jr":
            i.kind, i.reads = "jr", (rs,)
        elif mn == "jalr":
            i.kind, i.reads, i.writes = "jalr", (rs,), rd or 31
        elif mn in ("syscall", "break"):
            i.kind = mn
        elif mn in ("mfhi", "mflo"):
            i.kind, i.writes = "hilo", rd
        elif mn in ("mthi", "mtlo"):
            i.kind, i.reads = "hilo", (rs,)
        elif mn in ("mult", "multu", "div", "divu"):
            i.kind, i.reads = ("mult" if mn.startswith("mul") else "div"), (rs, rt)
        else:                                            # the three-register ALU
            i.kind, i.reads, i.writes = "alu", (rs, rt), rd
            if mn in ("addu", "or") and (rt == 0 or rs == 0) and rd:
                i.mn = "move"                            # the compiler's own idiom
        return i

    if op == 1:                                          # REGIMM
        mn = REGIMM.get(rt)
        if mn is None:
            return i
        i.mn, i.kind, i.reads = mn, "branch", (rs,)
        i.target = addr + 4 + i.simm * 4
        if mn.endswith("al"):
            i.writes = 31
        return i

    if op in (2, 3):
        i.mn = "j" if op == 2 else "jal"
        i.kind = "jump" if op == 2 else "call"
        i.target = (addr & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        if op == 3:
            i.writes = 31
        return i

    if op in (4, 5, 6, 7):
        i.mn = {4: "beq", 5: "bne", 6: "blez", 7: "bgtz"}[op]
        i.kind = "branch"
        i.reads = (rs, rt) if op in (4, 5) else (rs,)
        i.target = addr + 4 + i.simm * 4
        return i

    if op in IMM:
        i.mn, i.kind, i.writes = IMM[op], "alu", rt
        i.reads = () if op == 0x0F else (rs,)
        return i

    if op in LOADS:
        i.mn, i.kind, i.reads, i.writes = LOADS[op], "load", (rs,), rt
        return i

    if op in STORES:
        i.mn, i.kind, i.reads = STORES[op], "store", (rs, rt)
        return i

    if op == 0x12:                                       # COP2 -- the GTE
        if rs & 0x10:
            fn = word & 0x3F
            nm, what = GTE.get(fn, (None, None))
            i.mn = nm or "cop2"
            i.kind = "gte"
            i.cop = what
            if nm == "MVMVA":
                i.gte = _mvmva(word)
            elif nm is None:
                i.gte = f"{word & 0x1FFFFFF:#x}"
            return i
        nm = {0: "mfc2", 2: "cfc2", 4: "mtc2", 6: "ctc2"}.get(rs)
        if nm:
            i.mn, i.kind = nm, "cop"
            if nm in ("mfc2", "cfc2"):
                i.writes = rt
            else:
                i.reads = (rt,)
            return i
        return i

    if op == 0x10:                                       # COP0
        if rs == 0x10 and (word & 0x3F) == 0x10:
            i.mn, i.kind = "rfe", "cop"
            return i
        nm = {0: "mfc0", 2: "cfc0", 4: "mtc0", 6: "ctc0"}.get(rs)
        if nm:
            i.mn, i.kind = nm, "cop"
            if nm.startswith("mf") or nm.startswith("cf"):
                i.writes = rt
            else:
                i.reads = (rt,)
        return i

    if op == 0x32:
        i.mn, i.kind, i.reads = "lwc2", "load", (rs,)
        return i
    if op == 0x3A:
        i.mn, i.kind, i.reads = "swc2", "store", (rs,)
        return i
    return i


# MVMVA is the one GTE command whose operands are in the instruction word
# rather than implied, and reading them is the difference between "a matrix
# multiply" and "the *light* matrix times vertex 0, no translation".
_MX = ("rotation", "light", "colour", "reserved")
_VX = ("V0", "V1", "V2", "IR")
_CV = ("TR", "BK", "FC", "none")


def _mvmva(word):
    sf = (word >> 19) & 1
    mx = _MX[(word >> 17) & 3]
    v = _VX[(word >> 15) & 3]
    cv = _CV[(word >> 13) & 3]
    lm = (word >> 10) & 1
    return f"{mx} x {v} + {cv}{'' if sf else ', shift 0'}{', clamp' if lm else ''}"


def stream(exe, start, count):
    """`count` instructions from an `mips.Exe`, decoded."""
    out = []
    for k in range(count):
        w = exe.word(start + 4 * k)
        if w is None:
            break
        out.append(decode(w, start + 4 * k))
    return out

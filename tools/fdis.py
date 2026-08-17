#!/usr/bin/env python3
"""Disassemble a stretch of GAME.EXE, including the GTE that capstone will not.

    python3 tools/fdis.py 0x8003bb04 60      sixty instructions
    python3 tools/fdis.py 0x80011be0 49 t    read it as a pointer table instead

Capstone stops dead at coprocessor 2, which is most of the renderer: a single
`ctc2` at `0x8003bb90` ended every attempt to read the tile drawing routine.
This steps word by word and decodes those itself, naming the GTE registers,
because the names are the point — a store into `R11R12` says "rotation matrix"
where `ctc2 $t5, $0` says nothing.
"""
import struct
import sys

sys.path.insert(0, "tools")
import disasm  # noqa: E402
import syms    # noqa: E402

# GTE data registers, cop2 r0..r31
DR = ("VXY0 VZ0 VXY1 VZ1 VXY2 VZ2 RGBC OTZ IR0 IR1 IR2 IR3 SXY0 SXY1 SXY2 SXYP "
      "SZ0 SZ1 SZ2 SZ3 RGB0 RGB1 RGB2 RES1 MAC0 MAC1 MAC2 MAC3 IRGB ORGB LZCS "
      "LZCR").split()
# GTE control registers, cop2 c0..c31 -- c0..c4 are the rotation matrix
CR = ("R11R12 R13R21 R22R23 R31R32 R33 TRX TRY TRZ L11L12 L13L21 L22L23 L31L32 "
      "L33 RBK GBK BBK LR1LR2 LR3LG1 LG2LG3 LB1LB2 LB3 RFC GFC BFC OFX OFY H "
      "DQA DQB ZSF3 ZSF4 FLAG").split()
CMD = {0x01: "RTPS", 0x06: "NCLIP", 0x0C: "OP", 0x10: "DPCS", 0x11: "INTPL",
       0x12: "MVMVA", 0x13: "NCDS", 0x14: "CDP", 0x16: "NCDT", 0x1B: "NCCS",
       0x1C: "CC", 0x1E: "NCS", 0x20: "NCT", 0x28: "SQR", 0x29: "DCPL",
       0x2A: "DPCT", 0x2D: "AVSZ3", 0x2E: "AVSZ4", 0x30: "RTPT", 0x3D: "GPF",
       0x3E: "GPL", 0x3F: "NCCT"}
GPR = ("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 "
       "s7 t8 t9 k0 k1 gp sp fp ra").split()


def cop2(w):
    """Decode a coprocessor-2 instruction, or None."""
    op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    imm = w & 0xFFFF
    off = imm - 0x10000 if imm > 0x7FFF else imm
    if op == 0x12:
        if rs & 0x10:                                  # a GTE command
            fn = w & 0x3F
            return f"{CMD.get(fn, 'cop2'):8s} {'' if fn in CMD else hex(w & 0x1FFFFFF)}"
        name = {0: "mfc2", 2: "cfc2", 4: "mtc2", 6: "ctc2"}.get(rs)
        if name:
            reg = (CR if name in ("cfc2", "ctc2") else DR)[rd]
            return f"{name:8s} ${GPR[rt]}, {reg}"
    if op in (0x32, 0x3A):
        return (f"{'lwc2' if op == 0x32 else 'swc2':8s} "
                f"{DR[rt]}, {off}(${GPR[rs]})")
    return None


def run(start, n):
    base, _entry, text = disasm.load_text()
    cs = disasm.Cs()
    cs.load(text, base)
    addr = start
    for _ in range(n):
        off = addr - base
        if not (0 <= off < len(text)):
            return
        got = cs.at(off, 1)
        if got:
            _a, mn, ops = got[0]
            print(f"{syms.label(addr):30s} {mn:8s} {syms.annotate(ops)}")
        else:
            w = struct.unpack_from("<I", text, off)[0]
            d = cop2(w)
            print(f"{syms.label(addr):30s} {d if d else f'.word    {w:#010x}'}")
        addr += 4


if __name__ == "__main__":
    a = int(sys.argv[1], 0)
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    if len(sys.argv) > 3:
        base, _e, text = disasm.load_text()
        for i in range(n):
            v = struct.unpack_from("<I", text, a - base + 4 * i)[0]
            print(f"  [{i:2d}] {v:#010x}  {syms.label(v)}")
    else:
        run(a, n)

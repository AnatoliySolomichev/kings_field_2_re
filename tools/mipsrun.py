#!/usr/bin/env python3
"""GAME.EXE's own code, run over a RAM snapshot.

    python3 tools/mipsrun.py --check     the interpreter against the menus'
                                         snapshots: their frames, drawn again
                                         by the game's own routines

A RAM snapshot holds the game's state and, since GAME.EXE is loaded in it, its
code too. This is enough of an R3000 to run that code: the integer
instruction set, the delay slots, the RAM and its mirrors and the scratchpad,
the hardware registers read as zero and written to nowhere. What it cannot run
it is told about: `hooks` maps an address to a Python function that stands in
for the routine there -- ClearOTagR, which the console does with a DMA
channel; the sound; the pad -- and an address that reaches the BIOS (0xa0,
0xb0, 0xc0) stops it unless hooked too.

What it is for is the screens nobody has a snapshot of. A menu's frame is
built by plain code -- labels, numbers, frames, packets linked into an
ordering table -- so running `frame_begin` and the screen's routine over a
snapshot's RAM leaves in that RAM the very packets the game would have sent,
which `tools/gpuframe.py` reads back. `frame()` does that. The menu snapshots
check the machine: their own frames, drawn again from the state they hold,
must come out primitive for primitive.

Not modelled: the load delay slot (the compiler never leans on it), the GTE,
interrupts, exceptions. A routine that needs one stops with the reason.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GP = 0x8009C214
STACK = 0x801FC000          # below the menus' own frames in the snapshots
RETURN = 0x80000000         # a return address nothing executes: the end of a call
CLEAR_OTAG_R = 0x8007A00C
UI_SOUND = 0x8002792C
VSYNC = 0x8007910C
PAD_READ = 0x800785AC
DRAW_SYNC = 0x80079BA0


class Stop(Exception):
    """The machine cannot go on: an instruction or an address it does not do."""


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


class CPU:
    def __init__(self, ram):
        self.ram = bytearray(ram)
        self.scratch = bytearray(0x400)
        self.r = [0] * 32
        self.hi = self.lo = 0
        self.pc = 0
        self.hooks = {}
        self.watch = {}            # address -> fn(cpu), called as it is reached
        self.steps = 0
        self.io_writes = 0
        self.r[28] = GP
        self.r[29] = STACK

    # -- memory --------------------------------------------------------------

    def _where(self, a):
        p = a & 0x1FFFFFFF
        if p < 0x800000:
            return self.ram, p & 0x1FFFFF
        if 0x1F800000 <= p < 0x1F800400:
            return self.scratch, p - 0x1F800000
        return None, p

    def rd(self, a, n):
        m, o = self._where(a)
        if m is None:
            return 0                       # a hardware register reads as 0
        return int.from_bytes(m[o:o + n], "little")

    def wr(self, a, n, v):
        m, o = self._where(a)
        if m is None:
            self.io_writes += 1            # a hardware register: nowhere
            return
        m[o:o + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, "little")

    # -- running -------------------------------------------------------------

    def call(self, addr, *args, limit=20_000_000):
        """Run the routine at addr with args in a0..a3 and the stack, until it
        returns; its v0."""
        sp = self.r[29]
        extra = list(args[4:])
        if extra:
            sp -= 0x10 + 4 * len(extra)
            sp &= ~7
            for i, v in enumerate(extra):
                self.wr(sp + 0x10 + 4 * i, 4, v)
        self.r[29] = sp
        for i, v in enumerate(args[:4]):
            self.r[4 + i] = v & 0xFFFFFFFF
        self.r[31] = RETURN
        self.pc = addr
        n0 = self.steps
        while self.pc != RETURN:
            if self.steps - n0 > limit:
                raise Stop(f"more than {limit} steps in {addr:#x}")
            self.step()
        self.r[29] = STACK
        return self.r[2]

    def _hooked(self):
        fn = self.hooks.get(self.pc)
        if fn is None:
            if (self.pc & 0x1FFFFFFF) in (0xA0, 0xB0, 0xC0):
                raise Stop(f"a BIOS call, {self.pc:#x} function {self.r[9]:#x}, "
                           f"from {self.r[31]:#x}")
            return False
        v = fn(self)
        self.r[2] = 0 if v is None else v & 0xFFFFFFFF
        self.pc = self.r[31]
        return True

    def step(self):
        if self.pc in self.watch:
            self.watch[self.pc](self)
        if self._hooked():
            return
        w = self.rd(self.pc, 4)
        self.steps += 1
        nxt = self.exec(w, self.pc)
        if nxt is None:
            self.pc = (self.pc + 4) & 0xFFFFFFFF
            return
        # a branch or a jump: its delay slot runs first
        slot = self.pc + 4
        self.steps += 1
        if self.exec(self.rd(slot, 4), slot) is not None:
            raise Stop(f"a branch in a delay slot at {slot:#x}")
        self.pc = nxt & 0xFFFFFFFF

    def exec(self, w, pc):
        """One instruction. The target, if it branches or jumps (taken), else
        None -- a branch not taken still runs its delay slot, so it returns
        the address after the slot."""
        r = self.r
        op = w >> 26
        rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        sa, fn = (w >> 6) & 31, w & 63
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm

        def setr(i, v):
            if i:
                r[i] = v & 0xFFFFFFFF

        if op == 0:
            if fn == 0x00:
                setr(rd, r[rt] << sa)
            elif fn == 0x02:
                setr(rd, r[rt] >> sa)
            elif fn == 0x03:
                setr(rd, s32(r[rt]) >> sa)
            elif fn == 0x04:
                setr(rd, r[rt] << (r[rs] & 31))
            elif fn == 0x06:
                setr(rd, r[rt] >> (r[rs] & 31))
            elif fn == 0x07:
                setr(rd, s32(r[rt]) >> (r[rs] & 31))
            elif fn == 0x08:
                return r[rs]
            elif fn == 0x09:
                t = r[rs]
                setr(rd, pc + 8)
                return t
            elif fn in (0x0C, 0x0D):
                raise Stop(f"{'syscall' if fn == 0x0C else 'break'} at {pc:#x}")
            elif fn == 0x10:
                setr(rd, self.hi)
            elif fn == 0x11:
                self.hi = r[rs]
            elif fn == 0x12:
                setr(rd, self.lo)
            elif fn == 0x13:
                self.lo = r[rs]
            elif fn == 0x18:
                p = s32(r[rs]) * s32(r[rt])
                self.lo, self.hi = p & 0xFFFFFFFF, (p >> 32) & 0xFFFFFFFF
            elif fn == 0x19:
                p = r[rs] * r[rt]
                self.lo, self.hi = p & 0xFFFFFFFF, (p >> 32) & 0xFFFFFFFF
            elif fn == 0x1A:
                a, b = s32(r[rs]), s32(r[rt])
                if b == 0:
                    self.lo, self.hi = (1 if a < 0 else 0xFFFFFFFF), a & 0xFFFFFFFF
                else:
                    q = abs(a) // abs(b) * (1 if (a < 0) == (b < 0) else -1)
                    self.lo, self.hi = q & 0xFFFFFFFF, (a - q * b) & 0xFFFFFFFF
            elif fn == 0x1B:
                a, b = r[rs], r[rt]
                if b == 0:
                    self.lo, self.hi = 0xFFFFFFFF, a
                else:
                    self.lo, self.hi = a // b, a % b
            elif fn in (0x20, 0x21):
                setr(rd, r[rs] + r[rt])
            elif fn in (0x22, 0x23):
                setr(rd, r[rs] - r[rt])
            elif fn == 0x24:
                setr(rd, r[rs] & r[rt])
            elif fn == 0x25:
                setr(rd, r[rs] | r[rt])
            elif fn == 0x26:
                setr(rd, r[rs] ^ r[rt])
            elif fn == 0x27:
                setr(rd, ~(r[rs] | r[rt]))
            elif fn == 0x2A:
                setr(rd, 1 if s32(r[rs]) < s32(r[rt]) else 0)
            elif fn == 0x2B:
                setr(rd, 1 if r[rs] < r[rt] else 0)
            else:
                raise Stop(f"SPECIAL {fn:#x} at {pc:#x}")
            return None
        if op == 1:
            v = s32(r[rs])
            take = (v < 0) if rt in (0x00, 0x10) else (v >= 0)
            if rt in (0x10, 0x11):
                r[31] = (pc + 8) & 0xFFFFFFFF
            return pc + 4 + (simm << 2) if take else pc + 8
        if op == 2:
            return ((pc + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
        if op == 3:
            r[31] = (pc + 8) & 0xFFFFFFFF
            return ((pc + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
        if 4 <= op <= 7:
            a, b = s32(r[rs]), s32(r[rt])
            take = (a == b, a != b, a <= 0, a > 0)[op - 4]
            return pc + 4 + (simm << 2) if take else pc + 8
        if op in (8, 9):
            setr(rt, r[rs] + simm)
        elif op == 10:
            setr(rt, 1 if s32(r[rs]) < simm else 0)
        elif op == 11:
            setr(rt, 1 if r[rs] < (simm & 0xFFFFFFFF) else 0)
        elif op == 12:
            setr(rt, r[rs] & imm)
        elif op == 13:
            setr(rt, r[rs] | imm)
        elif op == 14:
            setr(rt, r[rs] ^ imm)
        elif op == 15:
            setr(rt, imm << 16)
        elif op == 16:
            pass                                    # COP0: interrupts aside
        elif op == 18:
            raise Stop(f"the GTE at {pc:#x}")
        elif op >= 0x20:
            a = (r[rs] + simm) & 0xFFFFFFFF
            if op == 0x20:
                v = self.rd(a, 1)
                setr(rt, v - 0x100 if v & 0x80 else v)
            elif op == 0x21:
                v = self.rd(a, 2)
                setr(rt, v - 0x10000 if v & 0x8000 else v)
            elif op == 0x22:                        # lwl: the word's low bytes high
                word = self.rd(a & ~3, 4)
                k = a & 3
                keep = 0x00FFFFFF >> (8 * k)
                setr(rt, (r[rt] & keep) | ((word << (24 - 8 * k)) & 0xFFFFFFFF))
            elif op == 0x23:
                setr(rt, self.rd(a, 4))
            elif op == 0x24:
                setr(rt, self.rd(a, 1))
            elif op == 0x25:
                setr(rt, self.rd(a, 2))
            elif op == 0x26:                        # lwr: the word's high bytes low
                word = self.rd(a & ~3, 4)
                k = a & 3
                keep = 0 if k == 0 else (0xFFFFFFFF ^ (0xFFFFFFFF >> (8 * k)))
                setr(rt, (r[rt] & keep) | (word >> (8 * k)))
            elif op == 0x28:
                self.wr(a, 1, r[rt])
            elif op == 0x29:
                self.wr(a, 2, r[rt])
            elif op == 0x2A:                        # swl
                al = a & ~3
                k = a & 3
                word = self.rd(al, 4)
                keep = 0 if k == 3 else (0xFFFFFFFF << (8 * (k + 1))) & 0xFFFFFFFF
                self.wr(al, 4, (word & keep) | (r[rt] >> (8 * (3 - k))))
            elif op == 0x2B:
                self.wr(a, 4, r[rt])
            elif op == 0x2E:                        # swr
                al = a & ~3
                k = a & 3
                word = self.rd(al, 4)
                keep = 0 if k == 0 else (0xFFFFFFFF >> (8 * (4 - k)))
                self.wr(al, 4, (word & keep) | ((r[rt] << (8 * k)) & 0xFFFFFFFF))
            elif op in (0x32, 0x3A):
                raise Stop(f"the GTE's memory at {pc:#x}")
            else:
                raise Stop(f"opcode {op:#x} at {pc:#x}")
        else:
            raise Stop(f"opcode {op:#x} at {pc:#x}")
        return None


def clear_otag_r(cpu):
    """ClearOTagR(ot, n): the console's DMA channel 6 -- entry k links to
    k - 1 and the first ends the list."""
    ot, n = cpu.r[4], cpu.r[5]
    for k in range(n):
        cpu.wr(ot + 4 * k, 4, 0x00FFFFFF if k == 0 else (ot + 4 * (k - 1)) & 0xFFFFFF)
    return ot


def menu_cpu(ram):
    """A machine on a snapshot's RAM with what a menu frame needs stood in for."""
    cpu = CPU(ram)
    cpu.hooks[CLEAR_OTAG_R] = clear_otag_r
    for a in (UI_SOUND, VSYNC, DRAW_SYNC):
        cpu.hooks[a] = lambda c: 0
    cpu.hooks[PAD_READ] = lambda c: 0
    return cpu


PULSE = (GP + 0x4C) & 0x1FFFFF   # the selection's pulse, which frame_begin steps


def frame(ram, calls, pulse=None):
    """frame_begin and then each (routine, args...) of `calls`, over a copy of
    the RAM; the primitives of the buffer it drew into, as tools/gpuframe.py
    reads them, and the machine. `pulse` is what frame_begin's step makes of
    gp + 0x4c this frame -- a snapshot holds it after its last frame, which
    is not necessarily the frame its other buffer shows."""
    import gpuframe
    cpu = menu_cpu(ram)
    if pulse is not None:
        cpu.wr(0x80000000 | PULSE, 4, (pulse - 1) % 0x60)
        cpu.wr(GP + 0x54, 4, 0xFFFFFFFF)                  # not just moved
    cpu.call(0x80026FE4)                                     # frame_begin
    for c in calls:
        cpu.call(c[0], *c[1:])
    buf = cpu.ram[0x1AEAE8]                                  # draw_buffer_index
    return gpuframe.frame(cpu.ram, buf), cpu


OFFENSE, DEFENSE = 0x801B2538, 0x801B254A      # eight and nine halfwords
RATINGS_PAGE = 0x80023300


def ratings_cases(ram):
    """ui_ratings_page (0x80023300) as the game's own code draws it, over a
    snapshot's RAM with the sixteen ratings and the resistance set to each of
    a few sets: [(offense[8], defense[9], 2D primitives)]."""
    sets = [
        ([39, 32, 9, 0, 0, 0, 0, 0], [13, 6, 4, 0, 0, 0, 0, 0, 0]),
        ([72, 35, 18, 1, 22, 333, 4444, 55555], [27, 10, 6, 7, 8, 9, 10, 11, 25]),
        ([0] * 8, [0] * 9),
        ([999999 % 65536] * 8, [65535, 1, 22, 333, 4444, 55555, 6, 70, 800]),
    ]
    out = []
    for off, dfn in sets:
        r = bytearray(ram)
        for i, v in enumerate(off):
            struct.pack_into("<H", r, (OFFENSE & 0x1FFFFF) + 2 * i, v & 0xFFFF)
        for i, v in enumerate(dfn):
            struct.pack_into("<H", r, (DEFENSE & 0x1FFFFF) + 2 * i, v & 0xFFFF)
        prims, _cpu = frame(r, [(RATINGS_PAGE,)])
        out.append((off, dfn, two_d(prims)))
    return out


MENU_PAGE = 0x800252F4


def page_cases(ram, page, n):
    """sub_800252f4(page, n, sel, 0) -- a page of the menu's lines -- as the
    game's own code draws it over a snapshot's RAM, each line chosen in turn:
    [(sel, the pulse frame_begin left, 2D primitives)]."""
    out = []
    for sel in range(n):
        prims, cpu = frame(ram, [(MENU_PAGE, page, n, sel, 0)])
        out.append((sel, cpu.rd(GP + 0x4C, 4), two_d(prims)))
    return out


def two_d(prims):
    """The 2D part of a frame, as tools/ui.py compares it."""
    out = []
    for d, p in prims:
        if p["kind"] in ("sprite", "quad") and d < 0x100:
            q = {k: v for k, v in p.items() if k not in ("abr", "raw")}
            if q["kind"] == "sprite":
                q.pop("semi", None)
            out.append((d, q))
    return out


def check(out=sys.stdout):
    """menu1's main page drawn again by ui_status_page and sub_800252f4 from
    the snapshot's own state, against the snapshot's own frame: the
    interpreter is right if the two agree, primitive for primitive."""
    import ui
    path = os.path.join(ROOT, "out", "snap", "menu1.ram")
    if not os.path.exists(path):
        print("  no menu1 snapshot to run the code over", file=out)
        return True
    ram = open(path, "rb").read()
    _r, game = ui.snapshot_ui("menu1")
    # The line lit is pause_menu's own; the pulse each buffer was drawn at is
    # read off its lit plate's colour by trying them: the rest is the
    # snapshot's state as it stands.
    found = {}
    for sel in range(6):
        base, _cpu = frame(ram, [(0x800227EC,), (0x800252F4, 0, 6, sel, 0)])
        if not any(len(two_d(base)) == len(g) for g in game):
            continue
        now = int.from_bytes(ram[PULSE:PULSE + 4], "little") % 0x60
        for k in range(0x60):                 # the last frame's pulse, then back
            pulse = (now - k) % 0x60
            prims, cpu = frame(ram, [(0x800227EC,), (0x800252F4, 0, 6, sel, 0)], pulse)
            got = two_d(prims)
            for b, g in enumerate(game):
                if got == g and b not in found:
                    found[b] = (sel, pulse, cpu.steps, len(got))
        if len(found) == len(game):
            break
    for b in range(len(game)):
        if b in found:
            sel, pulse, steps, n = found[b]
            print(f"  menu1 buffer {b}: ui_status_page and the main page, run from the "
                  f"snapshot's RAM by the game's own code ({steps} instructions), are "
                  f"its {n} primitives exactly -- line {sel}, pulse {pulse:#x}", file=out)
        else:
            print(f"  menu1 buffer {b}: the code run from the snapshot does NOT draw it",
                  file=out)
    return len(found) == len(game)


if __name__ == "__main__":
    sys.exit(0 if check() else 1)

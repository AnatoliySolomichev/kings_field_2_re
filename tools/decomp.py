#!/usr/bin/env python3
"""The levels' own code, as something readable.

    python3 tools/decomp.py 0          level 0's overlay, as pseudocode
    python3 tools/decomp.py all        every level, into out/overlays.txt
    python3 tools/decomp.py flags      what sets and what tests each story flag

`FDAT.T` entry `3n + 2` is native MIPS the level ships with it, and
`tools/overlay.py` disassembles it. That is enough to read one routine at a
time and far too much to read twenty-eight levels of. This turns the parts that
are stereotyped into the shape they were written in:

    if (has_item(2) && has_item(130) && has_item(131) && has_item(132))
        story_flags[3] = 1;
    else
        story_flags[3] = 0;

Everything it does not recognise is printed as the instruction it is, with a
`;` in front, so a routine is never quietly half-rendered. The rule is the
project's: a guess presented as a reading is worse than a gap.

What it recognises: calls to the game's own routines with the constants going
into them, stores into `story_flags` and other named globals, and the two
control shapes this code is built out of -- a chain of tests jumping to a
common label, and a single test guarding a block.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, "tools")
import disasm                                                        # noqa: E402
import overlay as ov                                                 # noqa: E402
import syms                                                          # noqa: E402

STORY_FLAGS = 0x801BA988
# 128, not 64: flag_gate masks the gate byte with 0x7f and the cutscene table
# uses indices up to 126. See FORMATS.md, "Where that list lives".
FLAG_COUNT = 0x80

# The game routines a level overlay calls. overlay.py's list, plus the ones a
# first pass over all twenty-eight levels turned up.
CALLS = dict(ov.PRIMITIVES)
CALLS.update({
    0x8005DB30: "spawn_at_player", 0x80046884: "object_op_46884",
    0x800445B8: "object_op_445b8", 0x8002BDC0: "world_op_2bdc0",
    0x80045C7C: "find_object", 0x800796C0: "rand",
    0x80061940: "flag_gate", 0x8005D5F8: "load_area_name",
    0x8005DCC0: "award_gold", 0x80017C78: "object_trigger",
    0x8005E01C: "pickup_gives_type_id", 0x8005D898: "give_item",
})

GPR = ("zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 "
       "s7 t8 t9 k0 k1 gp sp fp ra").split()


def words(raw):
    return [struct.unpack_from("<I", raw, i)[0]
            for i in range(0, len(raw) - 3, 4)]


def flag_name(addr):
    """`story_flags[n]` for an address inside the array, else the best name."""
    if STORY_FLAGS <= addr < STORY_FLAGS + FLAG_COUNT:
        return f"story_flags[{addr - STORY_FLAGS}]"
    nm = syms.label_in("game", addr)
    return nm if nm != f"{addr:#010x}" else f"[{addr:#010x}]"


class Reader:
    """One overlay, turned into statements."""

    def __init__(self, lv):
        self.lv = lv
        raw, ptrs, _insns = ov.overlay(lv)
        self.raw, self.entries = raw, ptrs
        self.w = words(raw) if raw else []
        self.base = ov.BASE
        # Anything the reader does not recognise is printed as the instruction
        # it is, so a routine is never quietly half-rendered.
        self.cs = disasm.Cs()
        if raw:
            self.cs.load(raw, self.base)

    def text(self, a):
        got = self.cs.at(a - self.base, 1)
        if not got:
            return f"{self.w[(a - self.base) // 4]:#010x}"
        return f"{got[0][1]} {syms.annotate(got[0][2])}"

    def addr(self, i):
        return self.base + i * 4

    def effect(self, w, regs, hi):
        """What one instruction does to the constants we are tracking."""
        op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
        imm = w & 0xFFFF
        simm = imm - 0x10000 if imm > 0x7FFF else imm
        if op == 15:
            hi[rt] = imm << 16
            regs.pop(rt, None)
        elif op == 13 and rs == 0:
            regs[rt] = imm
        elif op == 9 and rs == 0:
            regs[rt] = simm
        elif op == 9 and rs in hi:
            regs[rt] = (hi[rs] + simm) & 0xFFFFFFFF
        elif op == 0 and (w & 0x3F) in (0x21, 0x25) and rs == 0 and rt == 0:
            regs[rd] = 0

    def run(self, start, limit=400):
        """Statements from an entry point until the routine returns.

        The instruction after a `jal` or a branch is its **delay slot** and runs
        before the jump takes effect, so the constant a call is given is
        normally sitting there. Reading straight down the instructions instead
        gives every call the argument of the one before it, which is wrong in a
        way that reads perfectly plausibly -- the first version of this printed
        `has_item(0)` where the game asks for item 133.
        """
        out = []
        regs = {}                       # register -> a constant, when known
        hi = {}                         # register -> a pending lui
        i = (start - self.base) // 4
        end = min(len(self.w), i + limit)
        pend_call = None                # the last call, for the branch after it
        skip = set()
        # A `lui` on its own says nothing here: its value always reappears in
        # the load or store that completes the address. When one is consumed
        # the line is dropped, so the listing shows the access and not its
        # two halves; an unconsumed `lui` stays, because then it is doing
        # something this reader has not understood.
        lui_at = {}
        while i < end:
            if i in skip:
                i += 1
                continue
            a, w = self.addr(i), self.w[i]
            op, rs, rt, rd = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
            imm = w & 0xFFFF
            simm = imm - 0x10000 if imm > 0x7FFF else imm
            tgt = (a & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
            st = None

            if op == 15:                                    # lui
                hi[rt] = imm << 16
                regs.pop(rt, None)
                lui_at[rt] = len(out)
            elif op == 13 and rs == 0:                      # ori rt, zero, n
                regs[rt] = imm
            elif op == 9 and rs == 0:                       # addiu rt, zero, n
                regs[rt] = simm
            elif op == 9 and rs in hi:                      # addiu rt, hi, lo
                regs[rt] = (hi[rs] + simm) & 0xFFFFFFFF
            elif op == 0 and (w & 0x3F) in (0x21, 0x25) and rs == 0 and rt == 0:
                regs[rd] = 0                                # move rd, zero
            elif op == 3:                                   # jal
                if i + 1 < end:
                    self.effect(self.w[i + 1], regs, hi)
                    skip.add(i + 1)
                args = [regs.get(4 + k) for k in range(4)]
                pend_call = (CALLS.get(tgt, f"{tgt:#010x}"), args)
                st = ("call", pend_call)
                for r in (2, 3, 4, 5, 6, 7) + tuple(range(8, 16)) + (24, 25, 31):
                    regs.pop(r, None)
                    hi.pop(r, None)
                    lui_at.pop(r, None)
            elif op in (0x28, 0x29, 0x2B) and rs in hi:     # sb/sh/sw to a global
                where = flag_name((hi[rs] + simm) & 0xFFFFFFFF)
                val = regs.get(rt, 0 if rt == 0 else None)
                st = ("store", where, val)
                if rs in lui_at and lui_at[rs] < len(out):
                    out[lui_at[rs]] = (out[lui_at[rs]][0], ("dropped",))
            elif op in (4, 5, 6, 7):                        # beq bne blez bgtz
                t = a + 4 + simm * 4
                st = ("branch", op, rs, rt, t, pend_call)
                pend_call = None
                if i + 1 < end:
                    self.effect(self.w[i + 1], regs, hi)
                    skip.add(i + 1)
            elif op == 2:                                   # j
                st = ("goto", tgt)
                if i + 1 < end:                             # its delay slot too
                    self.effect(self.w[i + 1], regs, hi)
                    skip.add(i + 1)
            elif op == 0 and (w & 0x3F) == 8 and rs == 31:  # jr $ra
                st = ("return",)
            if st is None:
                st = ("raw", a, self.text(a))
            out.append((a, st))
            if st[0] == "return":
                break
            i += 1
        return [(a, st) for a, st in out if st[0] != "dropped"]


def cond_of(st, negate=False):
    """A branch, as a condition on the call before it when there was one."""
    _k, op, rs, rt, _t, call = st
    if call and rs == 2:                       # the call's result in $v0
        name, args = call
        shown = ", ".join(str(a) if a is not None else "?"
                          for a in args if a is not None)
        c = f"{name}({shown})"
        # blez taken means "<= 0", so falling through means the call answered yes
        if op == 6:
            return f"!{c}" if not negate else c
        if op == 7:
            return c if not negate else f"!{c}"
        if op == 4 and rt == 0:
            return f"!{c}" if not negate else c
        if op == 5 and rt == 0:
            return c if not negate else f"!{c}"
    names = {4: "==", 5: "!=", 6: "<=", 7: ">"}
    lhs, rhs = f"${GPR[rs]}", (f"${GPR[rt]}" if op in (4, 5) else "0")
    o = names[op]
    if negate:
        o = {"==": "!=", "!=": "==", "<=": ">", ">": "<="}[o]
    return f"{lhs} {o} {rhs}"


def render(stmts, out):
    for a, text, depth in render_lines(stmts):
        pad = "    " * (depth + (0 if text.endswith(":") else 1))
        print(f"  {a:#010x}  {pad}{text}", file=out)


def render_lines(stmts):
    """Statements as pseudocode, with the two shapes this code is built of."""
    targets = {s[4] for _a, s in stmts if s[0] == "branch"}
    targets |= {s[1] for _a, s in stmts if s[0] == "goto"}
    lines = []
    n = len(stmts)
    i = 0
    while i < n:
        a, st = stmts[i]
        if a in targets:
            lines.append((a, f"L{a:x}:", 0))
        if st[0] == "branch":
            # A chain of tests all jumping to one label, then a block, a jump
            # past a second block, and that label -- an if/else.
            # A test is two statements -- the call, then the branch that reads
            # its answer -- so stepping the chain has to step over the calls the
            # branches consume, or every chain comes out one link long.
            chain, j = [], i
            tgt = st[4]
            while j < n:
                k2 = stmts[j][1]
                if k2[0] == "branch" and k2[4] == tgt:
                    chain.append(cond_of(k2))
                    j += 1
                elif (k2[0] == "call" and j + 1 < n
                      and stmts[j + 1][1][0] == "branch"
                      and stmts[j + 1][1][4] == tgt
                      and stmts[j + 1][1][5] is not None):
                    j += 1                      # the branch below prints it
                else:
                    break
            body, k = [], j
            while k < n and stmts[k][0] < tgt and stmts[k][1][0] not in ("branch",):
                if stmts[k][1][0] == "goto":
                    break
                body.append(stmts[k])
                k += 1
            after = stmts[k][1][1] if k < n and stmts[k][1][0] == "goto" else None
            els = []
            if after is not None:
                m = k + 1
                while m < n and stmts[m][0] < after:
                    if stmts[m][1][0] in ("branch", "goto"):
                        els = None
                        break
                    els.append(stmts[m])
                    m += 1
            if body and after is None and k < n and stmts[k][0] == tgt and \
                    all(s[1][0] in ("store", "call") for s in body):
                guard = " && ".join(c[1:] if c.startswith("!") else f"!({c})"
                                    for c in chain)
                lines.append((a, f"if ({guard}) {{", 0))
                for st2 in body:
                    lines.append((st2[0], one(st2[1]), 1))
                lines.append((a, "}", 0))
                i = k
                continue
            if body and after is not None and els is not None and \
                    all(s[1][0] in ("store", "call") for s in body + els):
                # every test has to fail to reach the label, so the guard is
                # the conjunction of their negations
                guard = " && ".join(c[1:] if c.startswith("!") else f"!({c})"
                                    for c in chain)
                lines.append((a, f"if ({guard}) {{", 0))
                for s in body:
                    lines.append((s[0], one(s[1]), 1))
                lines.append((a, "} else {", 0))
                for s in els:
                    lines.append((s[0], one(s[1]), 1))
                lines.append((a, "}", 0))
                i = m
                continue
            lines.append((a, f"if ({cond_of(st)}) goto L{st[4]:x};", 0))
        elif st[0] == "goto":
            lines.append((a, f"goto L{st[1]:x};", 0))
        elif (st[0] == "call" and i + 1 < n and stmts[i + 1][1][0] == "branch"
              and stmts[i + 1][1][5] is not None):
            pass                                # the branch renders it
        else:
            lines.append((a, one(st), 0))
        i += 1
    return lines


def one(st):
    if st[0] == "call":
        name, args = st[1]
        shown = ", ".join(str(x) for x in args if x is not None)
        return f"{name}({shown});"
    if st[0] == "store":
        return f"{st[1]} = {st[2] if st[2] is not None else '?'};"
    if st[0] == "return":
        return "return;"
    if st[0] == "raw":
        return f"; {st[2]}"
    return str(st)


def level(lv, out=sys.stdout):
    r = Reader(lv)
    if not r.raw:
        return 0
    print(f"=== level {lv}: {len(r.entries)} entry points ===", file=out)
    for e in r.entries:
        print(f"\nroutine at {e:#010x}:", file=out)
        render(r.run(e), out)
    return len(r.entries)


def flags():
    """Every story flag, with what writes it and what the write depends on.

    The condition is taken from the **rendered** block a store sits in, not
    from a window of the tests before it. The first version did the latter and
    attributed the same guard to both halves of an if/else -- so a flag looked
    as though it were set to 1 and to 0 under identical conditions, which reads
    as a finding and is nonsense. Where a store is not inside a block this
    reader structured, the condition is reported as unknown rather than
    guessed.
    """
    wrote = collections.defaultdict(list)
    for lv in range(28):
        r = Reader(lv)
        if not r.raw:
            continue
        for e in r.entries:
            stack = []                  # (condition, in the else half?)
            for a, text, _d in render_lines(r.run(e)):
                t = text.strip()
                if t.startswith("if (") and t.endswith("{"):
                    stack.append([t[4:t.rindex(")")], False])
                elif t == "} else {" and stack:
                    stack[-1][1] = True
                elif t == "}" and stack:
                    stack.pop()
                elif t.startswith("story_flags[") and "=" in t:
                    n = int(t[12:t.index("]")])
                    val = t.split("=", 1)[1].strip().rstrip(";")
                    cond = " && ".join(
                        (f"!({c})" if els else c) for c, els in stack)
                    wrote[n].append((lv, a, val, cond))
    print(f"{len(wrote)} of {FLAG_COUNT} story flags are written by a level "
          f"overlay somewhere:")
    for n in sorted(wrote):
        print(f"\nstory_flags[{n}]")
        for lv, a, val, cond in wrote[n]:
            print(f"   level {lv:2d} at {a:#010x}: = {val:<12s} "
                  f"when {cond or 'unconditionally, in no structured block'}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "0"
    if arg == "flags":
        flags()
    elif arg == "all":
        os.makedirs("out", exist_ok=True)
        with open("out/overlays.txt", "w") as f:
            n = sum(level(lv, f) for lv in range(28))
        print(f"{n} routines across 28 levels -> out/overlays.txt")
    else:
        level(int(arg))

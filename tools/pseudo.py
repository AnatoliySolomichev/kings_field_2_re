#!/usr/bin/env python3
"""A routine as statements instead of as instructions.

    python3 tools/pseudo.py game 0x8002ed60      one routine
    python3 tools/pseudo.py game --all           every routine, into out/pseudo/
    python3 tools/pseudo.py game 0x8002ed60 -r   keep every register assignment

Reading MIPS is reading three instructions to learn that a byte was compared
with 0x20. This folds them: registers carry expressions rather than values, an
absolute address prints as its name, a call prints with its arguments, and a
branch prints as the condition it tests.

    lbu  $v1, 0x25e8($v1)          v1 = player_vstate
    li   $v0, 0x20                 if (player_vstate == 0x20) goto .L3
    beq  $v1, $v0, .L3

What it does **not** do is invent structure. Every branch is `goto`, every
block keeps its label, and the order is the routine's own. Recovering `if` and
`while` from a control flow graph is a separate job with its own failure mode,
and a wrongly recovered loop reads exactly like a correct one -- which is the
worst shape a mistake can take in this project. `goto` is ugly and it cannot
be wrong.

Three things it is careful about, each because the naive version is wrong:

  * **The delay slot runs first.** The instruction after a branch executes
    before the branch does, so it is printed above it -- unless it writes a
    register the branch reads, in which case the branch was reading the old
    value and the two are printed in their real order with a note.
  * **An expression is only folded while it stays true.** Anything a call
    could change is dropped at the call, and everything is dropped at a block
    boundary, because a block reached from two places has two answers.
  * **A load's address prints as a name only when the base was a constant**
    the propagation actually formed. `s0->f10` for anything else, never a
    guess at which structure `$s0` holds.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips                                                          # noqa: E402
import mipsdis                                                       # noqa: E402
import rdis                                                          # noqa: E402
import syms                                                          # noqa: E402
from calltree import bios_at                                         # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
G = mipsdis.GPR

# Registers whose value a call does not preserve, so nothing folded through one
# stays true across it.
CLOBBERED = rdis.CLOBBERED

def _s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def _wrapped(e):
    """Is the whole expression inside one pair of brackets?

    `(a << 1) + (b)` starts with `(` and ends with `)` and is *not*, which a
    naive check reads as wrapped -- and then folds it into a shift, producing a
    different number that reads exactly like a correct one.
    """
    if not e.startswith("(") or not e.endswith(")"):
        return False
    depth = 0
    for n, c in enumerate(e):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return n == len(e) - 1
    return False


def _const(e):
    """The integer an expression is, or None. `lui` then `ori` builds a big
    constant in two halves, and printing it as `0x10000 | 0x86a0` makes the
    reader do the arithmetic the compiler already did."""
    e = e.strip()
    try:
        return int(e, 0)
    except ValueError:
        return None


def _simple(e):
    return all(c.isalnum() or c in "_$[]." for c in e)


def _paren(expr):
    """Wrap an expression in brackets if folding it could change what it means."""
    e = expr.strip()
    if not e or _simple(e) or _wrapped(e):
        return e
    if e[0] in "&*" and (_simple(e[1:]) or _wrapped(e[1:])):
        return e
    return f"({e})"


WIDTH_NAME = {1: "u8", 2: "u16", 4: "u32"}
SIGNED_NAME = {1: "s8", 2: "s16", 4: "s32"}


class Body:
    """One routine's statements, built block by block."""

    def __init__(self, w, fn, raw=False, const_names=None):
        self.w, self.fn, self.raw = w, fn, raw
        self.lin = {}            # reg -> (multiplier, the expression it scales)
        self._force = False      # while true, nothing folds -- see branch()
        self.frame = rdis.frame(w, fn)[0]
        # Which stack slots the prologue saves. Only those are hidden: the
        # first version hid every store of a callee-saved register into the
        # frame, which also hid `sw $s3, 0x10($sp)` -- the fifth argument going
        # to collide_surface, and the one thing that call needed saying about.
        self.saved_off, written = set(), set()
        for a in fn.body[:32]:
            i = w.insns[a]
            if i.mn == "sw" and i.rs == 29 and i.rt in rdis.SAVED \
                    and i.rt not in written:
                self.saved_off.add(i.simm)
            if i.writes is not None:
                written.add(i.writes)
        self.live, self.succ = {}, {}
        self.names = const_names or {}
        self.lab = rdis.labels_for(w, fn)
        self.refs = {}
        for a, addr, mode, width in fn.refs:
            if a not in self.refs or mode != "addr":
                self.refs[a] = (addr, mode, width)
        self.out = []

    # --- naming ---------------------------------------------------------

    def sym(self, addr):
        n = syms.label_in(self.fn.nick, addr)
        return n if n != f"{addr:#010x}" else f"[{addr:#010x}]"

    def num(self, v, mn=""):
        if -9 <= v <= 9:
            return str(v)
        nm = self.names.get(v)
        hit = None
        if isinstance(nm, list):
            here = [n for n, where in nm if not where or self.fn.name in where]
            hit = here[0] if here else None
        elif isinstance(nm, str):
            hit = nm
        txt = f"-{-v:#x}" if v < 0 else f"{v:#x}"
        return f"{hit}" if hit else txt

    # --- expressions ----------------------------------------------------

    def get(self, regs, r):
        if r == 0:
            return "0"
        return regs.get(r, "$" + G[r])

    def arg(self, regs, r):
        """The same, wrapped so it can be folded into a larger expression.

        Without this, `(a >> 11)` folded into a shift comes out as
        `a >> 11 << 5`, which is a different number and reads like a reading.
        """
        return _paren(self.get(regs, r))

    def forget(self, r):
        self.lin.pop(r, None)

    def put(self, regs, r, expr, force=False):
        """Fold an expression into a register, or emit it as a statement."""
        if r == 0 or r is None:
            return
        if self.raw or force or self._force or len(expr) > 44 \
                or r in rdis.SAVED:
            self.emit(f"${G[r]} = {expr};")
            regs[r] = "$" + G[r]
        else:
            regs[r] = expr

    def emit(self, text):
        self.out.append("    " + text)

    def liveness(self):
        """`{block: registers it reads before writing}`, to a fixpoint.

        Without it, an expression folded into `$v0` at the end of one block and
        tested at the top of the next simply vanishes: the reader is shown
        `if ($v0 == 0)` with nothing saying what `$v0` is. Everything live
        across an edge is written out instead.
        """
        fn, w = self.fn, self.w
        gen, kill, succ = {}, {}, {}
        for b, ins in fn.blocks.items():
            g, k = set(), set()
            for a in ins:
                i = w.insns[a]
                for r in getattr(i, "reads", ()):
                    if r and r not in k:
                        g.add(r)
                if i.kind == "call":
                    k |= set(CLOBBERED)
                if i.writes:
                    k.add(i.writes)
            gen[b], kill[b] = g, k
            succ[b] = [t for t in rdis._successors(w, fn, ins)
                       if t in fn.blocks]
        live = {b: set(gen[b]) for b in fn.blocks}
        for _round in range(len(fn.blocks) + 2):
            changed = False
            for b in fn.blocks:
                out = set()
                for t in succ[b]:
                    out |= live[t]
                new = gen[b] | (out - kill[b])
                if new != live[b]:
                    live[b] = new
                    changed = True
            if not changed:
                break
        self.live = live
        self.succ = succ
        return live

    def flush(self, b, regs):
        """Write out every folded value the next block will read.

        Called before the block's branch, because after it the assignment
        reads as something the branch skipped -- which is how a correct list of
        statements gives a wrong account of the routine.
        """
        out = set()
        for t in self.succ.get(b, []):
            out |= self.live.get(t, set())
        for r in sorted(x for x in regs if isinstance(x, int)):
            if r in out and regs[r] != "$" + G[r]:
                self.emit(f"${G[r]} = {regs[r]};")
                regs[r] = "$" + G[r]

    def label(self, text):
        self.out.append(text)

    # --- one instruction ------------------------------------------------

    def mem(self, i, regs, at):
        """The thing a load or store addresses, as text."""
        got = self.refs.get(at)
        width = mipsdis.WIDTH.get(i.mn, 4)
        signed = i.mn in mipsdis.SIGNED
        if got and got[1] in ("read", "write"):
            return self.sym(got[0])
        base = self.arg(regs, i.rs)
        kind = (SIGNED_NAME if signed else WIDTH_NAME)[width]
        off = f"{i.simm:#x}" if i.simm >= 0 else f"-{-i.simm:#x}"
        if i.rs == 29:
            # Anything at or past the frame's own size is the *caller's*
            # stack, which is where the fifth argument onwards arrives.
            if self.frame and i.simm >= self.frame + 0x10:
                return f"arg{4 + (i.simm - self.frame - 0x10) // 4}"
            return f"local_{i.simm:x}"
        return f"*({kind} *)({base} + {off})"

    def step(self, a, regs):
        i = self.w.insns[a]
        mn = i.mn
        if mn == "nop":
            return
        # The frame's own bookkeeping. The header already says how big the
        # frame is and which registers are saved, and repeating it as six
        # assignments at the top and six at the bottom buries the routine.
        if mn == "addiu" and i.rt == 29 and i.rs == 29:
            return
        if mn in ("sw", "lw") and i.rs == 29 and i.simm in self.saved_off:
            return
        if mn == "lui":
            regs[i.rt] = f"{i.imm << 16:#x}"
            return
        if mn in ("addiu", "addi"):
            got = self.refs.get(a)
            if got and got[1] == "addr":
                self.put(regs, i.rt, "&" + self.sym(got[0]))
            elif i.rs == 0:
                self.put(regs, i.rt, self.num(i.simm, mn))
            elif _const(self.get(regs, i.rs)) is not None:
                self.put(regs, i.rt,
                         self.num(_s32(_const(self.get(regs, i.rs)) + i.simm)))
            else:
                op = "+" if i.simm >= 0 else "-"
                self.put(regs, i.rt,
                         f"{self.arg(regs, i.rs)} {op} {self.num(abs(i.simm))}")
            return
        if mn == "ori":
            if i.rs == 0:
                self.put(regs, i.rt, self.num(i.imm, mn))
                return
            got = self.refs.get(a)
            if got and got[1] == "addr":
                self.put(regs, i.rt, "&" + self.sym(got[0]))
                return
            k = _const(self.get(regs, i.rs))
            if k is not None:
                self.put(regs, i.rt, self.num(_s32(k | i.imm), mn))
                return
            self.put(regs, i.rt,
                     f"{self.arg(regs, i.rs)} | {self.num(i.imm)}")
            return
        if mn in ("andi", "xori"):
            op = "&" if mn == "andi" else "^"
            self.put(regs, i.rt,
                     f"{self.arg(regs, i.rs)} {op} {self.num(i.imm)}")
            return
        if mn in ("slti", "sltiu"):
            self.put(regs, i.rt,
                     f"({self.arg(regs, i.rs)} < {self.num(i.imm)})")
            return
        if mn == "move":
            src = i.rs if i.rt == 0 else i.rt
            self.put(regs, i.rd, self.get(regs, src))
            return
        if mn in ("addu", "add", "subu", "sub"):
            x, y = self.lin.get(i.rs), self.lin.get(i.rt)
            sign = -1 if mn.startswith("sub") else 1
            got = None
            if x and y and x[1] == y[1]:
                got = (x[0] + sign * y[0], x[1])
            elif x and self.get(regs, i.rt) == x[1]:
                got = (x[0] + sign, x[1])
            elif y and self.get(regs, i.rs) == y[1]:
                got = (1 + sign * y[0], y[1])
            if got and got[0] > 2:
                self.lin[i.rd] = got
                self.put(regs, i.rd, f"{got[0]} * {_paren(got[1])}")
                return
            self.lin.pop(i.rd, None)
        if mn in ("addu", "add", "subu", "sub", "and", "or", "xor", "slt",
                  "sltu", "sllv", "srlv", "srav"):
            op = {"addu": "+", "add": "+", "subu": "-", "sub": "-",
                  "and": "&", "or": "|", "xor": "^", "slt": "<", "sltu": "<",
                  "sllv": "<<", "srlv": ">>", "srav": ">>"}[mn]
            x, y = self.arg(regs, i.rs), self.arg(regs, i.rt)
            if mn in ("sllv", "srlv", "srav"):
                x, y = y, x
            expr = f"{x} {op} {y}"
            self.put(regs, i.rd, f"({expr})" if op == "<" else expr)
            return
        if mn == "nor":
            self.put(regs, i.rd,
                     f"~({self.arg(regs, i.rs)} | {self.arg(regs, i.rt)})")
            return
        if mn in ("sll", "srl", "sra"):
            op = "<<" if mn == "sll" else ">>"
            if mn == "sll" and i.shamt and i.shamt < 16:
                had = i.rt in self.lin
                k, src = self.lin.get(i.rt, (1, self.get(regs, i.rt)))
                self.lin[i.rd] = (k << i.shamt, src)
                if had and (k << i.shamt) > 2:
                    # The chain was already a multiply; keep it one rather
                    # than showing the shift that continues it.
                    self.put(regs, i.rd,
                             f"{k << i.shamt} * {_paren(src)}")
                    return
            else:
                self.forget(i.rd)
            self.put(regs, i.rd, f"{self.arg(regs, i.rt)} {op} {i.shamt}")
            return
        if i.kind == "load":
            self.put(regs, i.writes, self.mem(i, regs, a))
            return
        if i.kind == "store":
            self.emit(f"{self.mem(i, regs, a)} = {self.get(regs, i.rt)};")
            return
        if mn in ("mult", "multu"):
            regs["lo"] = f"{self.arg(regs, i.rs)} * {self.arg(regs, i.rt)}"
            regs["hi"] = "<high half>"
            return
        if mn in ("div", "divu"):
            regs["lo"] = f"{self.arg(regs, i.rs)} / {self.arg(regs, i.rt)}"
            regs["hi"] = f"{self.arg(regs, i.rs)} % {self.arg(regs, i.rt)}"
            return
        if mn in ("mflo", "mfhi"):
            self.put(regs, i.rd, regs.get("lo" if mn == "mflo" else "hi",
                                          mn[2:]))
            return
        if i.kind == "gte":
            self.emit(f"GTE {i.mn}"
                      + (f"   /* {i.cop} */" if i.cop else "") + ";")
            return
        if i.kind == "cop":
            self.emit(i.fmt() + ";")
            return
        if mn == "jalr":
            self.emit(f"$v0 = ({self.get(regs, i.rs)})(...);")
            for r in CLOBBERED:
                regs.pop(r, None)
            return
        if mn in ("syscall", "break"):
            self.emit(mn + "();")
            return
        self.emit("/* " + i.fmt() + " */")

    def call(self, a, regs):
        i = self.w.insns[a]
        b = bios_at(self.w.exe, a)
        name = f"<{b[2]}>" if b else syms.label_in(self.fn.nick, i.target)
        if not b and i.target in self.w.funcs:
            name = self.w.funcs[i.target].name
        args = []
        for r in (4, 5, 6, 7):
            if r in regs:
                args.append(regs[r])
            elif args:
                args.append("?")
        while args and args[-1] == "?":
            args.pop()
        self.emit(f"$v0 = {name}({', '.join(args)});")
        for r in CLOBBERED:
            regs.pop(r, None)

    def cond(self, a, regs):
        i = self.w.insns[a]
        x = self.arg(regs, i.rs)
        y = self.arg(regs, i.rt)
        return {"beq": f"{x} == {y}", "bne": f"{x} != {y}",
                "blez": f"{x} <= 0", "bgtz": f"{x} > 0",
                "bltz": f"{x} < 0", "bgez": f"{x} >= 0",
                "bltzal": f"{x} < 0", "bgezal": f"{x} >= 0"}[i.mn]

    def target(self, t):
        return self.lab.get(t) or syms.label_in(self.fn.nick, t)

    # --- the whole routine ----------------------------------------------

    def run(self):
        fn = self.fn
        self.liveness()
        for b in sorted(fn.blocks):
            ins = fn.blocks[b]
            if not ins:
                continue
            if b in self.lab:
                self.label(f"{self.lab[b]}:")
            if b in self.w.labels:
                self.label(f"{syms.name_in(fn.nick, b)}:"
                           "   /* a label, not a routine */")
            regs = {}
            n = 0
            while n < len(ins):
                a = ins[n]
                i = self.w.insns[a]
                if i.kind in ("branch", "call", "jump", "jr"):
                    slot = ins[n + 1] if n + 1 < len(ins) else None
                    self.branch(a, slot, regs, b)
                    n += 2
                    continue
                self.step(a, regs)
                n += 1
            else:
                self.flush(b, regs)       # a block that just falls through

    def branch(self, a, slot, regs, b=None):
        """A branch and its delay slot, in the order they really run."""
        i = self.w.insns[a]
        si = self.w.insns.get(slot) if slot is not None else None
        # The delay slot runs before the branch takes effect, so it belongs
        # above -- unless it writes something the branch reads, in which case
        # the branch saw the old value and the two must stay in this order.
        clash = (si is not None and si.writes is not None
                 and si.writes in getattr(i, "reads", ()))
        if si is not None and not clash and si.kind != "nop":
            self.step(slot, regs)
        if b is not None:
            self.flush(b, regs)
        if i.kind == "branch":
            self.emit(f"if ({self.cond(a, regs)}) goto "
                      f"{self.target(i.target)};")
        elif i.kind == "call":
            self.call(a, regs)
        elif i.kind == "jump":
            self.emit(f"goto {self.target(i.target)};")
        elif i.kind == "jr":
            if i.rs == 31:
                self.emit("return $v0;")
            else:
                tb = next((t for t in self.fn.tables if t["at"] == a), None)
                if tb:
                    self.emit(f"switch ({self.get(regs, i.rs)})"
                              f"   /* {len(tb['targets'])} arms from "
                              f"{tb['base']:#010x} */")
                else:
                    self.emit(f"goto *{self.get(regs, i.rs)};")
        if si is not None and clash and si.kind != "nop":
            # The branch read the old value, so the slot is printed after it --
            # and written out rather than folded, because the block is about to
            # end and a folded value would be lost.
            self.emit("/* the delay slot, which the branch above ran first: */")
            self._force = True
            self.step(slot, regs)
            self._force = False


def b_sig(w, fn):
    """The arguments a routine reads, from what it reads before writing.

    `$a0..$a3` that are live on entry are arguments; the stack slots past the
    frame are arguments five onwards. A routine that ignores `$a1` and uses
    `$a2` prints `(a0, ?, a2)` rather than pretending it takes two.
    """
    b = Body(w, fn)
    b.frame = rdis.frame(w, fn)[0]
    live = b.liveness().get(fn.addr, set())
    args = [f"a{r - 4}" if r in live else "?" for r in (4, 5, 6, 7)]
    while args and args[-1] == "?":
        args.pop()
    stack = sorted({i.simm for a in fn.body
                    for i in [w.insns[a]]
                    if i.kind == "load" and i.rs == 29 and b.frame
                    and i.simm >= b.frame + 0x10})
    args += [f"arg{4 + (o - b.frame - 0x10) // 4}" for o in stack]
    return ", ".join(args)


def render(w, fn, out=sys.stdout, const_names=None, raw=False, portmap=None):
    size, saved = rdis.frame(w, fn)
    print(f"/* {fn.name}  --  {fn.nick}:{fn.addr:#010x}, "
          f"{len(fn.body)} instructions in {len(fn.blocks)} blocks", file=out)
    ent = syms.table(fn.nick).get(fn.addr)
    if ent and ent.get("evidence"):
        print(f"   {ent['evidence']}", file=out)
    p = (portmap or {}).get(f"{fn.nick}:{fn.addr:#010x}")
    if p:
        print(f"   port: {p}", file=out)
    print(f"   frame {size:#x}"
          + (f", saves {' '.join('$' + s for s in saved)}" if saved else "")
          + " */", file=out)
    print(f"{fn.name}({b_sig(w, fn)})", file=out)
    print("{", file=out)
    b = Body(w, fn, raw, const_names)
    b.frame = size
    b.run()
    for line in b.out:
        print(line, file=out)
    print("}", file=out)


if __name__ == "__main__":
    argv = sys.argv[1:]
    nick = argv.pop(0) if argv and argv[0] in mips.EXES else "game"
    raw = "-r" in argv
    argv = [x for x in argv if x != "-r"]
    cn = pm = None
    try:
        import consts as _c
        cn = _c.hints()
    except Exception:
        pass
    try:
        import portmap as _p
        pm = _p.by_address()
    except Exception:
        pass
    w = rdis.build(nick)
    if argv and argv[0] == "--all":
        d = os.path.join(ROOT, "out", "pseudo", nick)
        os.makedirs(d, exist_ok=True)
        for f, fn in sorted(w.funcs.items()):
            with open(os.path.join(d, f"{f:08x}_{fn.name}.c"), "w") as fh:
                render(w, fn, fh, cn, raw, pm)
        print(f"wrote {len(w.funcs)} routines into "
              f"{os.path.relpath(d, ROOT)}")
    elif argv:
        a = int(argv[0], 0)
        fn = w.funcs.get(a) or next((g for g in w.funcs.values()
                                     if a in g.body), None)
        if fn is None:
            print(f"{a:#010x} is in no routine the walk reached")
            sys.exit(1)
        render(w, fn, sys.stdout, cn, raw, pm)
    else:
        print(__doc__.strip().splitlines()[0])

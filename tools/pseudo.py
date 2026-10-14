#!/usr/bin/env python3
"""A routine as statements instead of as instructions.

    python3 tools/pseudo.py game 0x8002ed60      one routine
    python3 tools/pseudo.py game --all           every routine, into out/pseudo/
    python3 tools/pseudo.py game 0x8002ed60 -r   keep every register assignment
    python3 tools/pseudo.py --check              every block of the four, its
                                                 statements against its instructions

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

What it is careful about, each because the naive version is wrong (TOOLS.md
has the whole list, and what each cost before it was there):

  * **The delay slot runs first.** The instruction after a branch executes
    before the branch does, so it is printed above it -- unless it writes a
    register the branch reads, in which case the branch was reading the old
    value and the two are printed in their real order with a note.
  * **An expression is only folded while it stays true.** Anything a call
    could change is dropped at the call, and everything is dropped at a block
    boundary, because a block reached from two places has two answers. A
    folded value still to be read is written out as a statement first when
    a store could change memory it read, or when a statement is about to
    give a register it names a new value -- `$a0` in a folded text means
    the `$a0` last written out. Without it, `model_prims` read its primitive
    pointer, advanced it and printed the read after the advance, the pointer
    four bytes on from where the routine had it. lo and hi are registers to
    the liveness, so a multiply whose `mflo` is in the next block is written
    out rather than lost.
  * **A load's address prints as a name only when the base was a constant**
    the propagation actually formed. `s0->f10` for anything else, never a
    guess at which structure `$s0` holds.

`lwc2` and `swc2` move a GTE register to and from memory, and print as that
register -- `VXY0 = *(s32 *)($a0 + 0x0);` -- where they used to vanish and to
print the general register with the same number (`MAC0` as `$t8`).

`--check` prints every block in an exact notation (no names, `>>>` for `srl`,
`<u` for `sltu`, `/u` for `divu`, the frame's bookkeeping kept) and evaluates
its statements over random registers, memory and GTE registers, against the
block's instructions run by a small R3000 over the same: stores, calls and
their arguments, GTE moves, branches and the registers live after must come
out alike, under three ways of folding.
"""
import os
import re
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

# What ends a run of statements and has a delay slot after it.
BRANCHY = ("branch", "call", "jump", "jr", "jalr")

# Why a folded value was written out as a statement before it went stale.
WHY = {"store": "before a store", "write": "before a register they named "
       "was written", "call": "before a call", "gte": "before a GTE move",
       "swap": "as a swap's old value"}

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

    def __init__(self, w, fn, raw=False, const_names=None, exact=False,
                 fold=44):
        self.w, self.fn, self.raw = w, fn, raw
        # `exact` prints what check() evaluates: no names, the frame's own
        # bookkeeping kept, and the operators that otherwise print alike told
        # apart. `fold` is how long a folded text may grow, None for any.
        self.exact, self.fold = exact, fold
        self.lin = {}            # reg -> (multiplier, source reg, its text)
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
        self.names = {} if exact else (const_names or {})
        self.lab = rdis.labels_for(w, fn)
        self.refs = {}
        for a, addr, mode, width in fn.refs:
            if a not in self.refs or mode != "addr":
                self.refs[a] = (addr, mode, width)
        self.mreads = {}         # reg -> the memory its folded text reads
        self.where = {}          # address -> (block, index), for needed()
        self.at = None           # the instruction being stepped
        self.block = None        # and its block
        self.pending = set()     # what the branch still reads, during flush()
        self.kept = {}           # why values were written out, counted
        self.spans = {}          # block -> its lines of `out`, for check()
        self.skip = set()        # the second halves of unaligned pairs
        self.pairing = None      # the pair being stepped
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

    def forget_from(self, r):
        """Writing a register ends its chain and every chain that scales it.

        The second half is the one that matters. A chain remembers which
        register it came from, and once something else lands in that register
        the chain is about a value that is gone.
        """
        if r is None:
            return
        self.lin.pop(r, None)
        for k, v in list(self.lin.items()):
            if v[1] == r:
                self.lin.pop(k, None)

    def put(self, regs, r, expr, force=False):
        """Fold an expression into a register, or emit it as a statement."""
        if r == 0 or r is None:
            return
        regs[r] = expr
        if self.raw or force or self._force or r in rdis.SAVED \
                or (self.fold is not None and len(expr) > self.fold):
            self.pin(r, regs, self.at, chain=True)

    def emit(self, text):
        self.out.append("    " + text)

    # --- keeping a folded value true ------------------------------------

    @staticmethod
    def own(r):
        """How a register prints once its value is written out."""
        return r if r in ("lo", "hi") else "$" + G[r]

    @staticmethod
    def _pattern(r):
        if r in ("lo", "hi"):
            return r"(?<![\w$])" + r + r"(?!\w)"
        return re.escape("$" + G[r]) + r"(?!\w)"

    def mentions(self, text, r):
        """Does a folded text read `r` -- the value last written out to it?"""
        return re.search(self._pattern(r), text) is not None

    @staticmethod
    def _order(keys):
        """Registers by number, then lo and hi."""
        return sorted(keys, key=lambda k: (1, 0, k) if isinstance(k, str)
                      else (0, k, ""))

    def _count(self, why):
        self.kept[why] = self.kept.get(why, 0) + 1

    def _reads(self, i):
        """The registers an instruction reads, a call's arguments and a
        return's value among them."""
        got = set(i.reads)
        if i.kind in ("call", "jalr"):
            got |= {4, 5, 6, 7}
        if i.kind == "jr":
            got |= {2, 3}
        return got

    def needed(self, a, k):
        """Is `k` read again before it is written: by what is still to print
        of the instruction at hand (`self.pending`), after the instruction at
        `a`, or with `a` None after the block?"""
        if k in self.pending:
            return True
        b, after = self.block, []
        if a is not None:
            b, n = self.where[a]
            ins = self.fn.blocks[b]
            if self.w.insns[a].kind in BRANCHY:
                after = ins[n + 2:]           # its own slot has printed
            elif n and self.w.insns[ins[n - 1]].kind in BRANCHY:
                after = [ins[n - 1]]          # a slot: its branch prints next
            else:
                after = ins[n + 1:]
        j = 0
        while j < len(after):
            i = self.w.insns[after[j]]
            slot = (self.w.insns[after[j + 1]]
                    if i.kind in BRANCHY and j + 1 < len(after) else None)
            j += 2 if slot else 1
            if i.kind not in BRANCHY:
                t = self._touch(i, k)
                if t:
                    return t == "read"
                continue
            # A branch reads its own registers, then its slot runs, then a
            # call's callee takes the arguments and a return gives its value.
            if k in i.reads:
                return True
            if slot is not None:
                t = self._touch(slot, k)
                if t:
                    return t == "read"
            if i.kind in ("call", "jalr"):
                if k in (4, 5, 6, 7):
                    return True
                if k in CLOBBERED or k in ("lo", "hi"):
                    return False
            if i.kind == "jr" and k in (2, 3):
                return True
            if i.writes == k:
                return False
        return any(k in self.live.get(t, ()) for t in self.succ.get(b, []))

    @staticmethod
    def _touch(i, k):
        """Does an instruction that is not a branch read `k`, or write it?"""
        if k in ("lo", "hi"):
            if i.mn == "mf" + k:
                return "read"
            if i.kind in ("mult", "div") or i.mn == "mt" + k:
                return "write"
            return None
        if k in i.reads:
            return "read"
        return "write" if i.writes == k else None

    def pin(self, k, regs, a, stack=(), chain=False):
        """Write a folded value out as a statement, the way cleared first so
        that nothing still to be read loses the value it names."""
        text = regs.get(k)
        if text is None or text == self.own(k):
            return
        self.clear(k, regs, a, stack + (k,))
        self.emit(f"{self.own(k)} = {regs[k]};")
        regs[k] = self.own(k)
        self.mreads.pop(k, None)
        if not chain and k not in ("lo", "hi"):
            self.forget_from(k)

    def clear(self, r, regs, a, stack=()):
        """Before `$r = ...` prints: every other folded value that names `$r`
        and is still to be read is written out first. One already half way
        out -- a swap -- keeps the old value as `prev_r` instead."""
        for k, v in list(self.lin.items()):
            if self.mentions(v[2], r):
                self.lin.pop(k, None)
        for k in self._order(x for x in regs if x != r):
            text = regs.get(k)
            if text is None or text == self.own(k) \
                    or not self.mentions(text, r):
                continue
            if k not in stack and not self.needed(a, k):
                continue
            if k in stack:                # it prints after $r, whatever reads it
                keep = "prev_" + (r if r in ("lo", "hi") else G[r])
                self.emit(f"{keep} = {self.own(r)};")
                self._count("swap")
                pat = self._pattern(r)
                for j in list(regs):
                    if j != r and regs[j] != self.own(j):
                        regs[j] = re.sub(pat, keep, regs[j])
                for j, cells in self.mreads.items():
                    self.mreads[j] = {(c[0], re.sub(pat, keep, c[1])) + c[2:]
                                      if c[0] == "rel" else c for c in cells}
                return
            self._count("write")
            self.pin(k, regs, a, stack)

    UNALIGNED = {"lwl": "lwr", "lwr": "lwl", "swl": "swr", "swr": "swl"}

    def pair(self, a):
        """An unaligned word: `lwl` and `lwr` (or `swl` and `swr`) on one
        register and one base, three bytes apart, the second right after the
        first. Their lower half -- (its instruction, its address) -- says
        where the word is; the other's address is returned too, to be passed
        over."""
        i = self.w.insns[a]
        other = self.UNALIGNED.get(i.mn)
        b, n = self.where.get(a, (None, None))
        if other is None or b is None:
            return None
        ins, k = self.fn.blocks[b], n + 1
        if k < len(ins) and self.w.insns[ins[k]].kind in BRANCHY:
            # the other half in the branch's delay slot, which runs next
            if i.kind == "load" and i.rt in self.w.insns[ins[k]].reads:
                return None
            k += 1
        if k >= len(ins):
            return None
        nxt = ins[k]
        j = self.w.insns[nxt]
        if j.mn != other or j.rt != i.rt or j.rs != i.rs \
                or (i.kind == "load" and i.rt == i.rs):
            return None
        low, low_a, high = (j, nxt, i) if j.mn in ("lwr", "swr") \
            else (i, a, j)
        return (low, low_a, nxt) if high.simm == low.simm + 3 else None

    def cell(self, i, a, regs):
        """What a load or store touches: an absolute range, a slot of the
        frame, or an offset from a base as it prints."""
        width = mipsdis.WIDTH.get(i.mn, 4)
        got = self.refs.get(a)
        if got and got[1] in ("read", "write"):
            return ("abs", got[0], width)
        if i.rs == 29:
            return ("stack", i.simm, width)
        return ("rel", self.get(regs, i.rs), i.simm, width)

    @staticmethod
    def overlap(d, c):
        """Can a store to `c` change what a load from `d` read? Through two
        different bases, or a base and anything else, it can."""
        if d[0] == c[0] == "rel" and d[1] == c[1]:
            return d[2] < c[2] + c[3] and c[2] < d[2] + d[3]
        if "rel" in (d[0], c[0]):
            return True
        if d[0] != c[0]:
            return False                  # a slot of the frame is no global
        return d[1] < c[1] + c[2] and c[1] < d[1] + d[2]

    def settle(self, c, a, regs):
        """Before a store to `c`: write out each folded value that read memory
        the store may change and is still to be read -- the store's own
        address and value among what is."""
        self.pending = set(self.w.insns[a].reads)
        for k, v in list(self.lin.items()):
            if any(self.overlap(d, c) for d in self.mreads.get(v[1], ())):
                self.lin.pop(k, None)
        for k in self._order(list(self.mreads)):
            if k in self.mreads and any(self.overlap(d, c)
                                        for d in self.mreads[k]) \
                    and self.needed(a, k):
                self._count("store")
                self.pin(k, regs, a)
        self.pending = set()

    def track(self, i, regs, deps):
        """Which memory each folded value now reads, for the stores to come."""
        if i.kind in ("mult", "div"):
            for h in ("lo", "hi"):
                if deps:
                    self.mreads[h] = set(deps)
                else:
                    self.mreads.pop(h, None)
            return
        w = i.writes
        if w in (None, 0) or i.kind in ("call", "jalr"):
            return
        if not deps or regs.get(w, self.own(w)) == self.own(w):
            self.mreads.pop(w, None)
        else:
            self.mreads[w] = deps

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
                if i.mn in ("mflo", "mfhi") and i.mn[2:] not in k:
                    g.add(i.mn[2:])           # lo and hi are read across
                if i.kind in ("call", "jalr"):    # blocks too
                    k |= set(CLOBBERED) | {"lo", "hi"}
                if i.kind in ("mult", "div"):
                    k |= {"lo", "hi"}
                if i.mn in ("mtlo", "mthi"):
                    k.add(i.mn[2:])
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

    def flush(self, b, regs, also=()):
        """Write out every folded value the next block will read.

        Called before the block's branch, because after it the assignment
        reads as something the branch skipped -- which is how a correct list of
        statements gives a wrong account of the routine. `also` is what the
        branch itself still reads, which nothing written out here may change.
        """
        out = set()
        for t in self.succ.get(b, []):
            out |= self.live.get(t, set())
        self.block, self.pending = b, set(also)
        for r in self._order(regs):
            if r in out:
                self.pin(r, regs, None)
        self.pending = set()

    def label(self, text):
        self.out.append(text)

    # --- one instruction ------------------------------------------------

    def mem(self, i, regs, at):
        """The thing a load or store addresses, as text."""
        got = self.refs.get(at)
        width = mipsdis.WIDTH.get(i.mn, 4)
        signed = i.mn in mipsdis.SIGNED
        kind = (SIGNED_NAME if signed else WIDTH_NAME)[width]
        if got and got[1] in ("read", "write"):
            return f"*({kind} *)({got[0]:#x})" if self.exact \
                else self.sym(got[0])
        base = self.arg(regs, i.rs)
        off = f"{i.simm:#x}" if i.simm >= 0 else f"-{-i.simm:#x}"
        if i.rs == 29 and not self.exact:
            # Anything at or past the frame's own size is the *caller's*
            # stack, which is where the fifth argument onwards arrives.
            if self.frame and i.simm >= self.frame + 0x10:
                return f"arg{4 + (i.simm - self.frame - 0x10) // 4}"
            return f"local_{i.simm:x}"
        return f"*({kind} *)({base} + {off})"

    def step(self, a, regs):
        """One instruction, with what its folded values read kept track of."""
        if a in self.skip:
            return
        i = self.w.insns[a]
        self.at = a
        self.block = self.where.get(a, (self.block,))[0]
        self.pairing = self.pair(a)
        if self.pairing is not None:
            self.skip.add(self.pairing[2])
            c = self.cell(self.pairing[0], self.pairing[1], regs)
        elif i.mn in self.UNALIGNED:
            # Half a word on its own, which nothing here prints: everything
            # around the bytes it may touch is taken as touched.
            c = self.cell(i, a, regs)
            c = c[:-2] + (c[-2] - 3, 7)
        else:
            c = self.cell(i, a, regs) if i.kind in ("load", "store") else None
        if i.kind == "store":
            self.settle(c, a, regs)
        deps = set()
        for r in i.reads:
            deps |= self.mreads.get(r, set())
        if i.mn in ("mflo", "mfhi"):
            deps = set(self.mreads.get(i.mn[2:], ()))
        self._step(a, regs)
        if i.kind == "load" and i.mn != "lwc2":
            deps.add(c)
        self.track(i, regs, deps)

    def _step(self, a, regs):
        i = self.w.insns[a]
        mn = i.mn
        if mn == "nop":
            return
        # The frame's own bookkeeping. The header already says how big the
        # frame is and which registers are saved, and repeating it as six
        # assignments at the top and six at the bottom buries the routine.
        if mn == "addiu" and i.rt == 29 and i.rs == 29 and not self.exact:
            return
        if mn in ("sw", "lw") and i.rs == 29 and i.simm in self.saved_off \
                and not self.exact:
            return
        if mn == "lui":
            self.forget_from(i.rt)
            regs[i.rt] = f"{i.imm << 16:#x}"
            return
        if mn in ("addiu", "addi"):
            self.forget_from(i.rt)
            got = self.refs.get(a)
            if got and got[1] == "addr":
                self.put(regs, i.rt, f"{got[0]:#x}" if self.exact
                         else "&" + self.sym(got[0]))
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
            self.forget_from(i.rt)
            if i.rs == 0:
                self.put(regs, i.rt, self.num(i.imm, mn))
                return
            got = self.refs.get(a)
            if got and got[1] == "addr":
                self.put(regs, i.rt, f"{got[0]:#x}" if self.exact
                         else "&" + self.sym(got[0]))
                return
            k = _const(self.get(regs, i.rs))
            if k is not None:
                self.put(regs, i.rt, self.num(_s32(k | i.imm), mn))
                return
            self.put(regs, i.rt,
                     f"{self.arg(regs, i.rs)} | {self.num(i.imm)}")
            return
        if mn in ("andi", "xori"):
            self.forget_from(i.rt)
            op = "&" if mn == "andi" else "^"
            self.put(regs, i.rt,
                     f"{self.arg(regs, i.rs)} {op} {self.num(i.imm)}")
            return
        if mn in ("slti", "sltiu"):
            # The immediate is sign-extended for both; sltiu then compares
            # without sign, so -1 is 0xffffffff there.
            self.forget_from(i.rt)
            k = i.simm if mn == "slti" else i.simm & 0xFFFFFFFF
            op = "<u" if mn == "sltiu" and self.exact else "<"
            self.put(regs, i.rt,
                     f"({self.arg(regs, i.rs)} {op} {self.num(k)})")
            return
        if mn == "move":
            self.forget_from(i.rd)
            src = i.rs if i.rt == 0 else i.rt
            self.put(regs, i.rd, self.get(regs, src))
            return
        if mn in ("addu", "add", "subu", "sub"):
            x, y = self.lin.get(i.rs), self.lin.get(i.rt)
            sign = -1 if mn.startswith("sub") else 1
            got = None
            if x and y and x[1] == y[1]:
                got = (x[0] + sign * y[0], x[1], x[2])
            elif x and i.rt == x[1]:
                got = (x[0] + sign, x[1], x[2])
            elif y and i.rs == y[1]:
                got = (1 + sign * y[0], y[1], y[2])
            self.forget_from(i.rd)
            if got and got[0] > 2:
                self.lin[i.rd] = got
                self.put(regs, i.rd, f"{got[0]} * {_paren(got[2])}")
                return
        if mn in ("addu", "add", "subu", "sub", "and", "or", "xor", "slt",
                  "sltu", "sllv", "srlv", "srav"):
            self.forget_from(i.rd)
            op = {"addu": "+", "add": "+", "subu": "-", "sub": "-",
                  "and": "&", "or": "|", "xor": "^", "slt": "<", "sltu": "<",
                  "sllv": "<<", "srlv": ">>", "srav": ">>"}[mn]
            if self.exact:
                op = {"sltu": "<u", "srlv": ">>>"}.get(mn, op)
            x, y = self.arg(regs, i.rs), self.arg(regs, i.rt)
            if mn in ("sllv", "srlv", "srav"):
                x, y = y, x
            expr = f"{x} {op} {y}"
            self.put(regs, i.rd, f"({expr})" if op == "<" else expr)
            return
        if mn == "nor":
            self.forget_from(i.rd)
            self.put(regs, i.rd,
                     f"~({self.arg(regs, i.rs)} | {self.arg(regs, i.rt)})")
            return
        if mn in ("sll", "srl", "sra"):
            op = "<<" if mn == "sll" else \
                ">>>" if mn == "srl" and self.exact else ">>"
            if mn == "sll" and i.shamt and i.shamt < 16:
                had = i.rt in self.lin
                k, sr, src = self.lin.get(
                    i.rt, (1, i.rt, self.get(regs, i.rt)))
                self.forget_from(i.rd)
                self.lin[i.rd] = (k << i.shamt, sr, src)
                if had and (k << i.shamt) > 2:
                    # The chain was already a multiply; keep it one rather
                    # than showing the shift that continues it.
                    self.put(regs, i.rd,
                             f"{k << i.shamt} * {_paren(src)}")
                    return
            else:
                self.forget_from(i.rd)
            self.put(regs, i.rd, f"{self.arg(regs, i.rt)} {op} {i.shamt}")
            return
        if mn in self.UNALIGNED:
            if self.pairing is None:
                if i.writes:
                    self.clear(i.writes, regs, a)
                    self.forget_from(i.writes)
                self.emit("/* " + i.fmt() + " */")
                if i.writes:
                    regs[i.writes] = self.own(i.writes)
                return
            low, low_a = self.pairing[0], self.pairing[1]
            if i.kind == "load":
                self.forget_from(i.rt)
                self.put(regs, i.rt, self.mem(low, regs, low_a))
            else:
                self.emit(f"{self.mem(low, regs, low_a)} = "
                          f"{self.get(regs, i.rt)};")
            return
        if mn == "lwc2":                 # into a GTE register, not a GPR
            self.emit(f"{mipsdis.DR[i.rt]} = {self.mem(i, regs, a)};")
            return
        if i.kind == "load":
            self.forget_from(i.writes)
            self.put(regs, i.writes, self.mem(i, regs, a))
            return
        if i.kind == "store":
            val = mipsdis.DR[i.rt] if mn == "swc2" else self.get(regs, i.rt)
            self.emit(f"{self.mem(i, regs, a)} = {val};")
            return
        if mn in ("mult", "multu"):
            regs["lo"] = f"{self.arg(regs, i.rs)} * {self.arg(regs, i.rt)}"
            regs["hi"] = f"hi{'u' if mn == 'multu' else ''}({regs['lo']})"
            return
        if mn in ("div", "divu"):
            u = "u" if mn == "divu" and self.exact else ""
            regs["lo"] = f"{self.arg(regs, i.rs)} /{u} {self.arg(regs, i.rt)}"
            regs["hi"] = f"{self.arg(regs, i.rs)} %{u} {self.arg(regs, i.rt)}"
            return
        if mn in ("mflo", "mfhi"):
            self.forget_from(i.rd)
            self.put(regs, i.rd, regs.get("lo" if mn == "mflo" else "hi",
                                          mn[2:]))
            return
        if i.kind == "gte":
            self.emit(f"GTE {i.mn}"
                      + (f"   /* {i.cop} */" if i.cop else "") + ";")
            return
        if i.kind == "cop":
            # It prints as the instruction, naming its general register, so
            # that register's own value has to be the one written out: a move
            # out of the coprocessor gives it a new one, and a move in reads
            # it.
            if i.writes:
                self.clear(i.writes, regs, a)
                self.forget_from(i.writes)
            self.pending = set(i.reads)
            for r in i.reads:
                if r and regs.get(r, self.own(r)) != self.own(r):
                    self._count("gte")
                    self.pin(r, regs, a)
            self.pending = set()
            self.emit(i.fmt() + ";")
            if i.writes:
                regs[i.writes] = self.own(i.writes)
            return
        if mn in ("syscall", "break"):
            self.emit(mn + "();")
            return
        if i.writes:
            self.clear(i.writes, regs, a)
        if mn in ("mthi", "mtlo"):
            self.clear(mn[2:], regs, a)
            regs.pop(mn[2:], None)
            self.mreads.pop(mn[2:], None)
        self.forget_from(i.writes)
        self.emit("/* " + i.fmt() + " */")
        if i.writes:
            regs[i.writes] = self.own(i.writes)

    def call(self, a, regs):
        i = self.w.insns[a]
        # `$v0 = ...` gives $v0 a new value and the callee may write any
        # memory, so a folded value that outlives the call and reads either is
        # written out first.
        self.pending = self._reads(i)
        for k in self._order(regs):
            text = regs.get(k)
            if k in CLOBBERED or k in ("lo", "hi") or text is None \
                    or text == self.own(k):
                continue
            if (self.mreads.get(k) or self.mentions(text, 2)) \
                    and self.needed(a, k):
                self._count("call")
                self.pin(k, regs, a)
        self.pending = set()
        if i.kind == "jalr":
            name = f"({self.get(regs, i.rs)})"
        elif self.exact:
            name = f"{i.target:#x}"
        else:
            b = bios_at(self.w.exe, a)
            name = f"<{b[2]}>" if b else syms.label_in(self.fn.nick, i.target)
            if not b and i.target in self.w.funcs:
                name = self.w.funcs[i.target].name
        if self.exact:
            name = "call " + name
        # An argument register this block did not set is `?`, the first ones
        # too: leaving them out moved the rest one place left, so that
        # `f($a1, $a2, $a3)` read as a0, a1 and a2.
        args = [regs[r] if r in regs else "?" for r in (4, 5, 6, 7)]
        while args and args[-1] == "?":
            args.pop()
        self.emit(f"$v0 = {name}({', '.join(args)});")
        for r in list(CLOBBERED) + ["lo", "hi"]:
            regs.pop(r, None)
            self.mreads.pop(r, None)
        for k, v in list(self.lin.items()):
            if k in CLOBBERED or v[1] in CLOBBERED:
                self.lin.pop(k, None)

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
        self.where = {a: (b, n) for b, ins in fn.blocks.items()
                      for n, a in enumerate(ins)}
        for b in sorted(fn.blocks):
            ins = fn.blocks[b]
            if not ins:
                continue
            start = len(self.out)
            if b in self.lab:
                self.label(f"{self.lab[b]}:")
            if b in self.w.labels:
                self.label(f"{syms.name_in(fn.nick, b)}:"
                           "   /* a label, not a routine */")
            regs = {}
            self.lin = {}         # a chain never crosses a block: the block
            self.mreads = {}      # may be reached from somewhere else
            self.block = b
            n = 0

            while n < len(ins):
                a = ins[n]
                i = self.w.insns[a]
                if i.kind in BRANCHY:
                    slot = ins[n + 1] if n + 1 < len(ins) else None
                    self.branch(a, slot, regs, b)
                    n += 2
                    continue
                self.step(a, regs)
                n += 1
            else:
                self.flush(b, regs)       # a block that just falls through
            self.spans[b] = (start, len(self.out))

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
            # What the branch reads, and a slot that prints after it.
            self.flush(b, regs, self._reads(i)
                       | (set(si.reads) if clash and si is not None else set()))
        self.at = a
        if i.kind == "branch":
            self.emit(f"if ({self.cond(a, regs)}) goto "
                      f"{self.target(i.target)};")
        elif i.kind in ("call", "jalr"):
            self.call(a, regs)
        elif i.kind == "jump":
            self.emit(f"goto {self.target(i.target)};")
        elif i.kind == "jr":
            if i.rs == 31:
                self.emit(f"return {self.get(regs, 2)};")
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
    try:
        import portmap as _pm
        head, _inline = _pm.listing_notes(portmap, fn.nick, fn.addr, fn.end)
    except Exception:
        head = []
    for h in head:
        print(f"   {h}", file=out)
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
    return b.kept


# --- the check: the statements against the instructions --------------------
#
# Every block is printed in the exact notation and its statements evaluated
# over random registers, memory and GTE registers; the same block's
# instructions are run over the same by a small R3000. Out of both come the
# stores, the calls with their four argument registers, the GTE moves and
# commands, the branches taken, the jumps and returns -- and the registers the
# next blocks read. They have to be the same. A call leaves new values in the
# registers it need not keep, in lo and hi, and in all memory, on both sides.

M32 = 0xFFFFFFFF
REG = {n: k for k, n in enumerate(G)}
DRI = {n: k for k, n in enumerate(mipsdis.DR)}
CRI = {n: k for k, n in enumerate(mipsdis.CR)}
TYPES = {"u8": (1, False), "s8": (1, True), "u16": (2, False),
         "s16": (2, True), "u32": (4, False), "s32": (4, True)}
BINARY = {"*": 10, "/": 10, "%": 10, "/u": 10, "%u": 10, "+": 9, "-": 9,
          "<<": 8, ">>": 8, ">>>": 8, "<": 7, "<=": 7, ">": 7, ">=": 7,
          "<u": 7, "==": 6, "!=": 6, "&": 5, "^": 4, "|": 3}
_TOKEN = re.compile(r"\s*(?:(0x[0-9a-fA-F]+|\d+)|(\$[a-z0-9]+)"
                    r"|([A-Za-z_][A-Za-z0-9_]*)"
                    r"|(>>>|<<|>>|<=|>=|==|!=|/u|%u|<u|[-+*/%&|^~<>()!,]))")


class Unchecked(Exception):
    """An instruction or a statement the check gives no meaning to."""


def _rnd(*key):
    """A 32-bit number fixed by its key: both sides draw the same."""
    import hashlib
    return int.from_bytes(hashlib.blake2b(repr(key).encode(),
                                          digest_size=4).digest(), "little")


def _sx(v, bits=32):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def _div(a, b, signed):
    """(lo, hi) of div or divu, a zero divisor as the R3000 answers it."""
    if signed:
        x, y = _sx(a), _sx(b)
        if y == 0:
            return (M32 if x >= 0 else 1), a & M32
        q = abs(x) // abs(y) * (1 if (x < 0) == (y < 0) else -1)
        return q & M32, (x - q * y) & M32
    if b == 0:
        return M32, a & M32
    return (a // b) & M32, (a % b) & M32


class World:
    """What one side of the check reads and writes, and what it was seen to do."""

    def __init__(self, seed):
        self.seed, self.calls, self.ops = seed, 0, 0
        self.r = [0] + [_rnd(seed, "r", k) for k in range(1, 32)]
        self.lo, self.hi = _rnd(seed, "lo"), _rnd(seed, "hi")
        self.dr = [_rnd(seed, "dr", k) for k in range(32)]
        self.cr = [_rnd(seed, "cr", k) for k in range(32)]
        self.mem, self.names, self.events = {}, {}, []

    def set(self, k, v):
        if k:
            self.r[k] = v & M32

    def load(self, a, width, signed):
        v = 0
        for k in range(width):
            at = (a + k) & M32
            b = self.mem.get(at)
            v |= (b if b is not None
                  else _rnd(self.seed, "m", self.calls, at) & 0xFF) << (8 * k)
        return (_sx(v, 8 * width) if signed else v) & M32

    def store(self, a, width, v):
        v &= (1 << (8 * width)) - 1
        self.events.append(("store", a & M32, width, v))
        for k in range(width):
            self.mem[(a + k) & M32] = (v >> (8 * k)) & 0xFF

    def gte(self, name, v, control=False):
        (self.cr if control else self.dr)[(CRI if control else DRI)[name]] = v
        self.events.append(("gte", name, v & M32))

    def command(self, name):
        self.events.append(("op", name))
        self.ops += 1
        self.dr = [_rnd(self.seed, "op", self.ops, k) for k in range(32)]

    def call(self, target=None):
        self.events.append(("call", target) + tuple(self.r[4:8]))
        self.calls += 1
        for k in CLOBBERED:
            self.r[k] = _rnd(self.seed, "call", self.calls, k)
        self.lo = _rnd(self.seed, "call", self.calls, "lo")
        self.hi = _rnd(self.seed, "call", self.calls, "hi")
        self.mem = {}


def _execute(i, a, x, refs):
    """One instruction that is not a branch, as the R3000 runs it."""
    mn, r = i.mn, x.r
    s, t = r[i.rs], r[i.rt]
    got = refs.get(a)
    if mn == "nop":
        return
    alu = {"addu": lambda: s + t, "add": lambda: s + t,
           "subu": lambda: s - t, "sub": lambda: s - t,
           "and": lambda: s & t, "or": lambda: s | t, "xor": lambda: s ^ t,
           "nor": lambda: ~(s | t), "slt": lambda: int(_sx(s) < _sx(t)),
           "sltu": lambda: int(s < t), "sllv": lambda: t << (s & 31),
           "srlv": lambda: t >> (s & 31), "srav": lambda: _sx(t) >> (s & 31),
           "sll": lambda: t << i.shamt, "srl": lambda: t >> i.shamt,
           "sra": lambda: _sx(t) >> i.shamt,
           "move": lambda: r[i.rs if i.rt == 0 else i.rt]}
    if mn in alu:
        x.set(i.rd, alu[mn]())
    elif mn in ("addiu", "addi"):
        x.set(i.rt, got[0] if got and got[1] == "addr" else s + i.simm)
    elif mn == "ori":
        x.set(i.rt, got[0] if got and got[1] == "addr" else s | i.imm)
    elif mn in ("slti", "sltiu", "andi", "xori", "lui"):
        x.set(i.rt, {"slti": lambda: int(_sx(s) < i.simm),
                     "sltiu": lambda: int(s < (i.simm & M32)),
                     "andi": lambda: s & i.imm, "xori": lambda: s ^ i.imm,
                     "lui": lambda: i.imm << 16}[mn]())
    elif mn in ("mult", "multu"):
        p = _sx(s) * _sx(t) if mn == "mult" else s * t
        x.lo, x.hi = p & M32, (p >> 32) & M32
    elif mn in ("div", "divu"):
        x.lo, x.hi = _div(s, t, mn == "div")
    elif mn in ("mflo", "mfhi"):
        x.set(i.rd, x.lo if mn == "mflo" else x.hi)
    elif mn in ("mtlo", "mthi"):
        if mn == "mtlo":
            x.lo = s
        else:
            x.hi = s
    elif mn in ("lwl", "lwr", "swl", "swr"):
        at = (got[0] if got and got[1] in ("read", "write")
              else s + i.simm) & M32
        k, word = at & 3, x.load(at & ~3, 4, False)
        if mn == "lwl":
            x.set(i.rt, (t & ((1 << (8 * (3 - k))) - 1)) | (word << (8 * (3 - k))))
        elif mn == "lwr":
            x.set(i.rt, (t & ~(M32 >> (8 * k))) | (word >> (8 * k)))
        elif mn == "swl":
            for j in range(k + 1):
                x.store((at & ~3) + j, 1, t >> (8 * (3 - k + j)))
        else:
            for j in range(4 - k):
                x.store(at + j, 1, t >> (8 * j))
    elif i.kind in ("load", "store"):
        at = got[0] if got and got[1] in ("read", "write") else s + i.simm
        width = mipsdis.WIDTH[mn]
        if mn == "lwc2":
            x.gte(mipsdis.DR[i.rt], x.load(at, 4, False))
        elif i.kind == "load":
            x.set(i.rt, x.load(at, width, mn in mipsdis.SIGNED))
        else:
            x.store(at, width, x.dr[i.rt] if mn == "swc2" else t)
    elif mn in ("mtc2", "ctc2"):
        x.gte((mipsdis.DR if mn == "mtc2" else mipsdis.CR)[i.rd], t,
              control=mn == "ctc2")
    elif mn in ("mfc2", "cfc2"):
        x.set(i.rt, (x.dr if mn == "mfc2" else x.cr)[i.rd])
    elif i.kind == "gte":
        x.command(mn)
    elif mn in ("syscall", "break"):
        x.events.append((mn,))
    else:
        raise Unchecked(mn)


def _settled(events):
    """The events, each run of stores as the bytes it leaves: one 4-byte
    store and the two halves of an unaligned one are the same."""
    out, run = [], None
    for e in events:
        if e[0] == "store":
            run = {} if run is None else run
            for k in range(e[2]):
                run[(e[1] + k) & M32] = (e[3] >> (8 * k)) & 0xFF
            continue
        if run is not None:
            out.append(("stores", tuple(sorted(run.items()))))
            run = None
        out.append(e)
    if run is not None:
        out.append(("stores", tuple(sorted(run.items()))))
    return out


def run_block(w, ins, x, refs):
    """A block's instructions over `x`, delay slots and all."""
    n = 0
    while n < len(ins):
        a = ins[n]
        i = w.insns[a]
        if i.kind not in BRANCHY:
            _execute(i, a, x, refs)
            n += 1
            continue
        before = list(x.r)                 # what the branch itself reads
        if n + 1 < len(ins):
            _execute(w.insns[ins[n + 1]], ins[n + 1], x, refs)
        s, t = _sx(before[i.rs]), _sx(before[i.rt])
        if i.kind == "branch":
            if i.mn in ("bltzal", "bgezal"):
                raise Unchecked(i.mn)
            x.events.append(("branch", {"beq": s == t, "bne": s != t,
                                        "blez": s <= 0, "bgtz": s > 0,
                                        "bltz": s < 0, "bgez": s >= 0}[i.mn]))
        elif i.kind in ("call", "jalr"):
            x.call(before[i.rs] if i.kind == "jalr" else None)
        elif i.kind == "jr":
            x.events.append(("return", x.r[2]) if i.rs == 31
                            else ("jump", before[i.rs]))
        n += 2


def _tokens(text):
    out, at = [], 0
    while at < len(text):
        m = _TOKEN.match(text, at)
        if not m or m.end() == at:
            if text[at:].strip() == "":
                break
            raise Unchecked(f"cannot read {text[at:]!r}")
        kind = next(k for k, g in enumerate(m.groups()) if g is not None)
        out.append((("num", "reg", "id", "op")[kind], m.group(kind + 1)))
        at = m.end()
    return out


class _Parse:
    """A printed expression as a tree, C's precedence."""

    def __init__(self, text):
        self.t, self.k = _tokens(text), 0
        self.tree = self.expr()
        if self.k != len(self.t):
            raise Unchecked(f"left over in {text!r}")

    def peek(self):
        return self.t[self.k] if self.k < len(self.t) else (None, None)

    def take(self, want=None):
        tok = self.peek()
        if tok[0] is None or (want is not None and tok[1] != want):
            raise Unchecked(f"wanted {want!r}, found {tok[1]!r}")
        self.k += 1
        return tok

    def expr(self, prec=0):
        left = self.unary()
        while True:
            kind, op = self.peek()
            if kind != "op" or op not in BINARY or BINARY[op] <= prec:
                return left
            self.take()
            left = ("bin", op, left, self.expr(BINARY[op]))

    def unary(self):
        kind, v = self.peek()
        if kind == "op" and v in ("-", "~", "!"):
            self.take()
            return ("un", v, self.unary())
        if kind == "op" and v == "*":
            self.take()
            self.take("(")
            ty = self.take()[1]
            self.take("*")
            self.take(")")
            if ty not in TYPES:
                raise Unchecked(ty)
            return ("load", ty, self.unary())
        if kind == "op" and v == "(":
            self.take()
            e = self.expr()
            self.take(")")
            return e
        if kind == "num":
            self.take()
            return ("num", int(v, 0))
        if kind == "reg":
            self.take()
            return ("reg", REG[v[1:]])
        if kind == "id":
            self.take()
            if v in ("hi", "hiu") and self.peek()[1] == "(":
                self.take("(")
                e = self.expr()
                self.take(")")
                if e[0] != "bin" or e[1] != "*":
                    raise Unchecked("hi of what")
                return ("hi", v == "hiu", e[2], e[3])
            return ("id", v)
        raise Unchecked(f"cannot read {v!r}")


_TREES = {}


def _value(text, x):
    tree = _TREES.get(text)
    if tree is None:
        tree = _TREES[text] = _Parse(text).tree
    return _eval(tree, x)


def _eval(e, x):
    k = e[0]
    if k == "num":
        return e[1] & M32
    if k == "reg":
        return x.r[e[1]]
    if k == "id":
        v = e[1]
        if v in ("lo", "hi"):
            return x.lo if v == "lo" else x.hi
        if v in x.names:
            return x.names[v]
        if v in DRI:
            return x.dr[DRI[v]]
        if v in CRI:
            return x.cr[CRI[v]]
        raise Unchecked(v)
    if k == "load":
        width, signed = TYPES[e[1]]
        return x.load(_eval(e[2], x), width, signed)
    if k == "un":
        v = _eval(e[2], x)
        return {"-": -v, "~": ~v, "!": int(v == 0)}[e[1]] & M32
    if k == "hi":
        a, b = _eval(e[2], x), _eval(e[3], x)
        return (((a * b) if e[1] else (_sx(a) * _sx(b))) >> 32) & M32
    op, a, b = e[1], _eval(e[2], x), _eval(e[3], x)
    if op in ("/", "%", "/u", "%u"):
        return _div(a, b, len(op) == 1)[0 if op[0] == "/" else 1]
    sa, sb = _sx(a), _sx(b)
    return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
            "&": lambda: a & b, "|": lambda: a | b, "^": lambda: a ^ b,
            "<<": lambda: a << (b & 31), ">>": lambda: sa >> (b & 31),
            ">>>": lambda: a >> (b & 31), "<": lambda: int(sa < sb),
            "<=": lambda: int(sa <= sb), ">": lambda: int(sa > sb),
            ">=": lambda: int(sa >= sb), "<u": lambda: int(a < b),
            "==": lambda: int(a == b), "!=": lambda: int(a != b)}[op]() & M32


def _arguments(text):
    """A call's arguments, split where no bracket is open."""
    out, depth, cur = [], 0, ""
    for c in text:
        if c == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        depth += (c == "(") - (c == ")")
        cur += c
    if cur.strip():
        out.append(cur.strip())
    return out


def run_statements(lines, x):
    """A block's printed statements over `x`, in the order they print."""
    for line in lines:
        if not line.startswith("    "):
            continue                                  # a label
        s = line.strip()
        if s.startswith("/* the delay slot"):
            continue
        if s.startswith("/*"):
            raise Unchecked(s)
        s = s[:-1] if s.endswith(";") else s
        m = re.match(r"if \((.*)\) goto \S+$", s)
        if m:
            x.events.append(("branch", _value(m.group(1), x) != 0))
            continue
        m = re.match(r"switch \((.*)\)\s+/\*.*\*/$", s)
        if m or s.startswith("goto *"):
            x.events.append(("jump", _value(m.group(1) if m else s[6:], x)))
            continue
        if s.startswith("goto "):
            continue
        if s.startswith("return "):
            x.events.append(("return", _value(s[7:], x)))
            continue
        if s.startswith("GTE "):
            x.command(s.split()[1])
            continue
        m = re.match(r"(mtc2|ctc2|mfc2|cfc2)\s+\$([a-z0-9]+), (\w+)$", s)
        if m:
            mn, reg, name = m.groups()
            if mn in ("mtc2", "ctc2"):
                x.gte(name, x.r[REG[reg]], control=mn == "ctc2")
            else:
                x.set(REG[reg], x.cr[CRI[name]] if mn == "cfc2"
                      else x.dr[DRI[name]])
            continue
        if s in ("syscall()", "break()"):
            x.events.append((s[:-2],))
            continue
        lhs, eq, rhs = s.partition(" = ")
        if not eq:
            raise Unchecked(s)
        if lhs == "$v0" and rhs.startswith("call "):
            body, target = rhs[5:], None
            if body.startswith("("):                  # jalr: its target
                depth = 0
                for k, c in enumerate(body):
                    depth += (c == "(") - (c == ")")
                    if depth == 0:
                        break
                target, body = _value(body[1:k], x), body[k + 1:]
            else:
                body = body[body.index("("):]
            got = [(k, _value(a, x)) for k, a in
                   enumerate(_arguments(body[1:-1])) if a != "?"]
            for k, v in got:
                x.set(4 + k, v)
            x.call(target)
            continue
        v = _value(rhs, x)
        if lhs.startswith("$"):
            x.set(REG[lhs[1:]], v)
        elif lhs in ("lo", "hi"):
            if lhs == "lo":
                x.lo = v
            else:
                x.hi = v
        elif lhs.startswith("prev_"):
            x.names[lhs] = v
        elif lhs in DRI:
            x.gte(lhs, v)
        elif lhs.startswith("*("):
            tree = _Parse(lhs).tree
            width = TYPES[tree[1]][0]
            x.store(_eval(tree[2], x), width, v)
        else:
            raise Unchecked(lhs)


def check(nicks=None, trials=2, folds=(0, 44, None), out=sys.stdout):
    """Every block of every routine, its statements against its instructions.

    Three ways of folding are checked, because what decides when a value is
    written out is what this is about: `fold` 0 writes every value out at
    once, 44 is the printed rule and None folds as far as anything lets it.
    """
    good, runs, alike = True, 0, 0
    for nick in nicks or mips.EXES:
        w = rdis.build(nick)
        for fold in folds:
            ok = bad = 0
            skipped, shown = {}, 0
            for addr, fn in sorted(w.funcs.items()):
                b = Body(w, fn, exact=True, fold=fold)
                b.frame = rdis.frame(w, fn)[0]
                b.run()
                for blk, (s, e) in sorted(b.spans.items()):
                    succ = b.succ.get(blk, [])
                    live = set().union(*(b.live.get(t, set()) for t in succ))
                    for t in range(trials):
                        m, p = World((nick, addr, blk, t)), \
                            World((nick, addr, blk, t))
                        try:
                            run_block(w, fn.blocks[blk], m, b.refs)
                            run_statements(b.out[s:e], p)
                        except Unchecked as u:
                            why = str(u).split()[0]
                            skipped[why] = skipped.get(why, 0) + 1
                            break
                        same = _settled(m.events) == _settled(p.events) and all(
                            (m.lo, m.hi)[r == "hi"] == (p.lo, p.hi)[r == "hi"]
                            if r in ("lo", "hi") else m.r[r] == p.r[r]
                            for r in live if r)
                        if same:
                            ok += 1
                            continue
                        bad += 1
                        if shown < 3:
                            shown += 1
                            print(f"  {nick} fold {fold}: {fn.name} block "
                                  f"{blk:#010x} differs", file=out)
                            for line in b.out[s:e]:
                                print("      " + line, file=out)
                        break
            good &= bad == 0
            runs, alike = runs + ok + bad, alike + ok
            print(f"  {nick}, fold {fold}: {ok} of {ok + bad} block runs "
                  f"alike, {trials} a block" + (", not run: " + ", ".join(
                      f"{n} {why}" for why, n in sorted(skipped.items()))
                      if skipped else ""), file=out)
    print(f"  every block's statements against its instructions: {alike} of "
          f"{runs} runs alike, {len(folds)} ways of folding", file=out)
    return good


def _fresh(d):
    """An empty directory to write into.

    Renaming a routine renames its file, and without this the old one stays --
    `800422b8_sub_800422b8.c` sitting beside `800422b8_render_frame.c`, both
    looking current, one of them a version behind.
    """
    import shutil
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d, exist_ok=True)

if __name__ == "__main__":
    argv = sys.argv[1:]
    named = bool(argv) and argv[0] in mips.EXES
    nick = argv.pop(0) if named else "game"
    if "--check" in argv:
        sys.exit(0 if check([nick] if named else None) else 1)
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
        pm = _p.listing_index()
    except Exception:
        pass
    w = rdis.build(nick)
    if argv and argv[0] == "--all":
        d = os.path.join(ROOT, "out", "pseudo", nick)
        _fresh(d)
        kept = {}
        for f, fn in sorted(w.funcs.items()):
            with open(os.path.join(d, f"{f:08x}_{fn.name}.c"), "w") as fh:
                for why, n in render(w, fn, fh, cn, raw, pm).items():
                    kept[why] = kept.get(why, 0) + n
        print(f"wrote {len(w.funcs)} routines into "
              f"{os.path.relpath(d, ROOT)}; values written out before they "
              "went stale: " + (", ".join(
                  f"{kept[k]} {WHY[k]}" for k in WHY if k in kept) or "none"))
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

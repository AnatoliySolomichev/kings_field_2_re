#!/usr/bin/env python3
"""Walk an executable from its entry point and write down everything found.

    python3 tools/rdis.py game --build     walk it; write out/rdis/game.json
    python3 tools/rdis.py game 0x8002ed60  one routine, annotated
    python3 tools/rdis.py game --listing   every routine, into out/asm/game/
    python3 tools/rdis.py game --tree entry -d 4      the call tree
    python3 tools/rdis.py game --unnamed   the biggest routines with no name

`tools/calltree.py` finds functions by scanning the whole image for `jal`
targets. That is the right first instrument and it has one flaw that matters
here: the image is code *and* data, so a word inside a texture that happens to
read as `jal` invents a function, and a function's end is taken as "wherever
the next one starts", which runs listings straight into data. Comparing this
decoder against capstone over GAME.EXE, 3161 instructions inside what that
method calls functions are opcodes the R3000A does not have -- all of them past
`0x80080000`, all of them data.

So this walks instead. It starts at the entry point, follows every branch and
every call, and decodes only what control flow actually reaches. A function
ends where its own flow ends, not where its neighbour begins. What that costs
is the routines reached only through a pointer, and they are put back
deliberately: after the walk settles, any word in the image pointing at a
*traversed* function start is a pointer table, its neighbours are candidates
too, and the walk runs again until nothing new turns up.

Three things it resolves that a linear disassembler cannot:

  * **`lui`/`%lo` pairs across branches** -- an absolute address is never one
    instruction on MIPS, and the two halves are often in different basic
    blocks. A constant propagation over the control flow graph pairs them;
    `mips.resolve` only pairs them inside a straight line.
  * **jump tables.** `jr $v0` is where a naive walk stops. The switch idiom
    puts the table's address in a `lui`/`lw` pair and its length in the `sltiu`
    that guards it, and both are recovered, so a switch's arms are code and not
    a hole. Where the guard cannot be found the entries are still read but the
    table is marked `plausible` rather than `sltiu` -- a bound that was guessed
    is never reported as one that was read.
  * **what a call is given.** Arguments that are constants are carried to the
    call site. An argument that is not constant prints nothing rather than a
    stale value; carrying one down four calls that never set it is how an
    earlier tool in this repository reported a finding that was not one.

Everything it writes carries the executable's nickname, because three of the
four programs on the disc load at `0x80011000` and an address alone names
nothing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips                                                          # noqa: E402
import mipsdis                                                       # noqa: E402
import syms                                                          # noqa: E402
from calltree import BIOS, bios_at                                   # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "out", "rdis")

# Registers a call does not preserve. $v0..$a3, $t0..$t9 and $ra are gone
# after a `jal`; $s0..$s7, $gp, $sp and $fp survive it.
CLOBBERED = frozenset([2, 3, 4, 5, 6, 7] + list(range(8, 16)) + [24, 25, 31])
ARGREG = {4: "a0", 5: "a1", 6: "a2", 7: "a3"}
SAVED = {16: "s0", 17: "s1", 18: "s2", 19: "s3", 20: "s4", 21: "s5", 22: "s6",
         23: "s7", 30: "fp", 31: "ra"}


class Scaled:
    """`an unknown register << 2` -- an index on its way into a word table."""
    __slots__ = ("src",)

    def __init__(self, src):
        self.src = src

    def __eq__(self, o):
        return isinstance(o, Scaled) and o.src == self.src

    def __hash__(self):
        return hash(("scaled", self.src))


class Indexed:
    """`a known address + an index` -- a table being indexed, and by what."""
    __slots__ = ("base", "idx")

    def __init__(self, base, idx=None):
        self.base, self.idx = base, idx

    def __eq__(self, o):
        return isinstance(o, Indexed) and o.base == self.base and o.idx == self.idx

    def __hash__(self):
        return hash(("indexed", self.base, self.idx))


class Table:
    """`mem[base + index]` -- a jump table read, and the register indexing it."""
    __slots__ = ("base", "idx")

    def __init__(self, base, idx=None):
        self.base, self.idx = base, idx

    def __eq__(self, o):
        return isinstance(o, Table) and o.base == self.base and o.idx == self.idx

    def __hash__(self):
        return hash(("table", self.base, self.idx))


def prologue(exe, addr):
    """Does a function start here? `addiu $sp, $sp, -n` is the usual sign.

    Leaf routines that touch no stack are missed rather than guessed at, which
    is the right way round: a guessed function start puts a label in the middle
    of another routine and every listing below it reads as a separate function.
    """
    w = exe.word(addr)
    if w is None:
        return False
    i = mipsdis.decode(w, addr)
    return i.mn == "addiu" and i.rt == 29 and i.rs == 29 and i.simm < 0


def looks_like_code(exe, addr, n=6):
    """`n` decodable instructions in a row, and at least one that is not a nop.

    The test for a pointer table entry. Data decodes as R3000A instructions
    surprisingly often -- but rarely six in a row, and a run of six zeroes is
    six valid `nop`s, which is why the second half of the test is there.
    """
    if addr % 4 or addr not in exe:
        return False
    real = 0
    for k in range(n):
        w = exe.word(addr + 4 * k)
        if w is None:
            return False
        i = mipsdis.decode(w, addr + 4 * k)
        if i.kind == "invalid":
            return False
        if i.kind != "nop":
            real += 1
    return real >= 2


class Walk:
    """One executable, walked from its entry point.

    `self.funcs` is `{start: Func}` once `run()` has settled.
    """

    def __init__(self, exe, nick):
        self.exe, self.nick = exe, nick
        self.funcs = {}
        self.insns = {}                  # every address control flow reached
        self.starts = set()
        self.hard = {exe.entry}          # starts something calls: real functions
        self.notes = []                  # anything that had to be guessed

    # --- discovery ------------------------------------------------------

    def run(self, extra_seeds=()):
        e = self.exe
        seeds = {e.entry} | {a for a in extra_seeds if a in e}
        # Addresses already named `code` in the symbol table are seeds too:
        # they were established from live RAM, which reaches what a static walk
        # cannot -- an interrupt handler is never called by anyone.
        for a, s in syms.table(self.nick).items():
            if s.get("kind") == "code" and a in e:
                seeds.add(a)
        self.starts = set(seeds)
        for _round in range(8):
            before = len(self.starts)
            self._sweep()
            found = self._pointer_tables()
            self.starts |= found
            if len(self.starts) == before and not found:
                break
        self._sweep()
        self._callers()
        return self

    def _sweep(self):
        """Walk every known start, discovering calls as it goes, to a fixpoint."""
        pending = list(self.starts)
        done = set()
        while pending:
            f = pending.pop()
            if f in done:
                continue
            done.add(f)
            fn = self._walk_one(f)
            self.funcs[f] = fn
            for _a, t, _args in fn.calls:
                if t in self.exe:
                    self.hard.add(t)
                    if t not in done:
                        self.starts.add(t)
                        pending.append(t)
            for _a, t in fn.tail:
                if t in self.exe:
                    self.hard.add(t)
                    if t not in done:
                        self.starts.add(t)
                        pending.append(t)

    def _pointer_tables(self):
        """Words anywhere in the image that point at a function we have walked.

        A state machine calls its states through a table, so without this the
        opening's sequence of screens is a hole. Neighbours of a hit that look
        like code are taken as well -- that is what finds the *other* states,
        which nothing calls directly.
        """
        e, new = self.exe, set()
        known = set(self.funcs)
        a = e.base
        hits = []
        while a < e.end:
            w = e.word(a)
            if w in known:
                hits.append(a)
            a += 4
        self.ptr_words = {}
        for a in hits:
            self.ptr_words[a] = e.word(a)
            for d in (-8, -4, 4, 8):                  # its neighbours in the table
                w = e.word(a + d)
                if w is None or w in known or w not in e:
                    continue
                if prologue(e, w) and looks_like_code(e, w):
                    new.add(w)
                    self.ptr_words[a + d] = w
        return new

    def _walk_one(self, start):
        """Follow control flow from one entry point until it stops."""
        e = self.exe
        fn = Func(start, self.nick)
        seen, queue = set(), [start]
        while queue:
            a = queue.pop()
            if a in seen or a not in e:
                continue
            if a != start and a in self.hard:
                fn.into_next.append(a)
                continue
            w = e.word(a)
            if w is None:
                continue
            i = mipsdis.decode(w, a)
            if i.kind == "invalid":
                fn.broken.append(a)
                continue
            seen.add(a)
            self.insns[a] = i
            nxt = a + 8                               # past the delay slot
            if i.kind in ("branch",):
                queue.append(i.target)
                queue.append(nxt)
            elif i.kind == "call":
                fn.calls.append((a, i.target, None))
                queue.append(nxt)
            elif i.kind == "jump":
                t = i.target
                inside = t in seen or (start <= t < a + 0x4000 and t not in self.starts)
                if t in self.starts and t != start:
                    fn.tail.append((a, t))
                elif inside or (t not in self.starts and prologue(e, t) is False):
                    queue.append(t)
                else:
                    fn.tail.append((a, t))
            elif i.kind == "jr":
                if i.rs == 31:
                    fn.rets.append(a)
                else:
                    fn.switches.append(a)
            elif i.kind == "jalr":
                fn.indirect.append(a)
                queue.append(nxt)
            elif i.kind in ("syscall", "break"):
                pass
            else:
                queue.append(a + 4)
            if i.kind in ("branch", "call", "jump", "jr", "jalr"):
                if a + 4 in e:                        # the delay slot always runs
                    dw = e.word(a + 4)
                    di = mipsdis.decode(dw, a + 4)
                    if di.kind != "invalid":
                        seen.add(a + 4)
                        self.insns[a + 4] = di
        fn.body = sorted(seen)
        fn.end = (fn.body[-1] + 4) if fn.body else start
        self._analyse(fn)
        # A switch found on the first pass adds code the walk had stopped at,
        # so anything a table reached is walked now and folded in.
        if fn.tables:
            extra = [t for tb in fn.tables for t in tb["targets"]
                     if t not in seen and t in e]
            if extra:
                more = set(fn.body)
                q = list(extra)
                while q:
                    a = q.pop()
                    if a in more or a not in e:
                        continue
                    if a != fn.addr and a in self.hard and a not in extra:
                        continue
                    w = e.word(a)
                    if w is None:
                        continue
                    i = mipsdis.decode(w, a)
                    if i.kind == "invalid":
                        continue
                    more.add(a)
                    self.insns[a] = i
                    if i.kind == "branch":
                        q += [i.target, a + 8]
                    elif i.kind == "call":
                        fn.calls.append((a, i.target, None))
                        q.append(a + 8)
                    elif i.kind == "jump":
                        q.append(i.target)
                    elif i.kind in ("jr", "syscall", "break"):
                        pass
                    else:
                        q.append(a + 4)
                    if i.kind in ("branch", "call", "jump", "jr", "jalr") \
                            and a + 4 in e:
                        di = mipsdis.decode(e.word(a + 4), a + 4)
                        if di.kind != "invalid":
                            more.add(a + 4)
                            self.insns[a + 4] = di
                fn.body = sorted(more)
                fn.end = fn.body[-1] + 4
                self._analyse(fn)
        return fn

    # --- what is inside one function ------------------------------------

    def _analyse(self, fn):
        """Basic blocks, then constants over them, then everything annotated."""
        e = self.exe
        body = set(fn.body)
        leaders = {fn.addr}
        for a in fn.body:
            i = self.insns[a]
            if i.kind in ("branch", "jump"):
                if i.target in body:
                    leaders.add(i.target)
                if a + 8 in body:
                    leaders.add(a + 8)
            elif i.kind in ("call", "jr", "jalr", "syscall"):
                if a + 8 in body:
                    leaders.add(a + 8)
        fn.leaders = sorted(leaders)
        fn.blocks = {}
        for n, s in enumerate(fn.leaders):
            nxt = fn.leaders[n + 1] if n + 1 < len(fn.leaders) else fn.end
            ins = [a for a in fn.body if s <= a < nxt]
            fn.blocks[s] = ins
        fn.preds = {}
        for s in fn.blocks:
            for t in _successors(self, fn, fn.blocks[s]):
                if t in fn.blocks:
                    fn.preds.setdefault(t, []).append(s)
        self._constants(fn)

    def _constants(self, fn):
        """Constant propagation over the blocks, and everything it settles.

        The lattice is small on purpose: an exact integer, a `Table(base)` for
        a load off a known address by an unknown index, or unknown. Merging two
        different values gives unknown. That is enough for the three questions
        asked of it -- what address does this pair form, what is this call
        given, and where does this `jr` go -- and small enough that nothing it
        reports is a guess.
        """
        e = self.exe
        state = {s: None for s in fn.blocks}
        state[fn.addr] = {29: "SP"}
        fn.refs, fn.consts, fn.tables = [], [], []
        fn.argsat = {}
        work = [fn.addr]
        seen_count = {}
        while work:
            b = work.pop()
            seen_count[b] = seen_count.get(b, 0) + 1
            if seen_count[b] > 6:                     # loops settle long before this
                continue
            regs = dict(state.get(b) or {})
            succ = self._run_block(fn, b, regs)
            for s in succ:
                if s not in fn.blocks:
                    continue
                old = state.get(s)
                merged = _merge(old, regs)
                if merged != old:
                    state[s] = merged
                    work.append(s)

    def _run_block(self, fn, b, regs):
        """Interpret one block for its constants; returns its successors."""
        e = self.exe
        succ = []
        ins = fn.blocks[b]
        for n, a in enumerate(ins):
            i = self.insns[a]
            mn = i.mn
            if mn == "lui":
                regs[i.rt] = (i.imm << 16)
            elif mn in ("addiu", "addi"):
                v = regs.get(i.rs)
                if i.rs == 0:
                    regs[i.rt] = i.simm
                elif isinstance(v, int):
                    val = (v + i.simm) & 0xFFFFFFFF
                    regs[i.rt] = val
                    if val in e or 0x80000000 <= val < 0x80200000:
                        fn.refs.append((a, val, "addr", 0))
                elif v == "SP":
                    regs[i.rt] = "SP" if i.rt == 29 else ("SP", i.simm)
                else:
                    regs[i.rt] = None
            elif mn == "ori":
                v = regs.get(i.rs)
                regs[i.rt] = (v | i.imm) if isinstance(v, int) else (
                    i.imm if i.rs == 0 else None)
                if isinstance(regs.get(i.rt), int) and regs[i.rt] in e and i.rs:
                    fn.refs.append((a, regs[i.rt], "addr", 0))
            elif mn in ("andi", "xori", "slti", "sltiu"):
                v = regs.get(i.rs)
                if isinstance(v, int):
                    regs[i.rt] = {"andi": v & i.imm, "xori": v ^ i.imm,
                                  "slti": int(_s32(v) < i.simm),
                                  "sltiu": int(v < (i.simm & 0xFFFFFFFF))}[mn]
                else:
                    regs[i.rt] = None
            elif mn == "move":
                regs[i.rd] = regs.get(i.rs if i.rt == 0 else i.rt)
            elif mn in ("addu", "add", "subu", "sub", "and", "or", "xor", "nor",
                        "slt", "sltu", "sllv", "srlv", "srav"):
                x, y = regs.get(i.rs), regs.get(i.rt)
                if isinstance(x, int) and isinstance(y, int):
                    regs[i.rd] = _alu(mn, x, y)
                elif mn in ("addu", "add") and (isinstance(x, int) or isinstance(y, int)):
                    k = x if isinstance(x, int) else y
                    o = y if isinstance(x, int) else x
                    regs[i.rd] = Indexed(k, o.src if isinstance(o, Scaled) else None)
                else:
                    regs[i.rd] = None
            elif mn in ("sll", "srl", "sra"):
                v = regs.get(i.rt)
                if isinstance(v, int):
                    regs[i.rd] = _alu(mn, v, i.shamt)
                elif mn == "sll" and i.shamt == 2:
                    regs[i.rd] = Scaled(i.rt)       # an index, scaled to words
                else:
                    regs[i.rd] = None
            elif i.kind == "load":
                base = regs.get(i.rs)
                if isinstance(base, int):
                    addr = (base + i.simm) & 0xFFFFFFFF
                    fn.refs.append((a, addr, "read", mipsdis.WIDTH.get(mn, 4)))
                    if i.writes is not None:
                        w = e.word(addr) if mn == "lw" and addr in e else None
                        regs[i.writes] = w if w is not None else None
                elif base == "SP":
                    if i.writes is not None:
                        regs[i.writes] = None
                else:
                    if i.writes is None:
                        pass
                    elif isinstance(base, Indexed) and mn == "lw":
                        # `lui $at,%hi(T)` / `addu $at,$at,$idx` / `lw $v,%lo(T)($at)`
                        # is the switch idiom, and this is the moment the table's
                        # address is whole again.
                        regs[i.writes] = Table((base.base + i.simm) & 0xFFFFFFFF,
                                               base.idx)
                    elif isinstance(base, Table):
                        regs[i.writes] = base
                    else:
                        regs[i.writes] = None
            elif i.kind == "store":
                base = regs.get(i.rs)
                if isinstance(base, int):
                    fn.refs.append((a, (base + i.simm) & 0xFFFFFFFF, "write",
                                    mipsdis.WIDTH.get(mn, 4)))
            elif i.kind == "call":
                args = {r: regs.get(r) for r in ARGREG
                        if isinstance(regs.get(r), int)}
                for k, (sa, t, _o) in enumerate(fn.calls):
                    if sa == a:
                        fn.calls[k] = (a, t, args)
                fn.argsat[a] = args
                for r in CLOBBERED:
                    regs.pop(r, None)
            elif i.kind == "jalr":
                for r in CLOBBERED:
                    regs.pop(r, None)
            elif i.kind == "jr" and i.rs != 31:
                v = regs.get(i.rs)
                if isinstance(v, Table):
                    self._read_table(fn, a, v.base, ins, b, v.idx)
            elif i.writes is not None:
                regs[i.writes] = None
            if mn in ("addiu", "addi", "ori", "li", "andi", "xori", "lui",
                      "slti", "sltiu") or (i.kind == "alu" and i.mn == "lui"):
                fn.consts.append((a, i.imm if mn in ("ori", "andi", "xori", "lui")
                                  else i.simm, mn))
        return _successors(self, fn, ins)

    def _bound(self, fn, block, idx):
        """The `sltiu` guarding a switch, found by the register it tests.

        `sltiu $v0, $index, N` before a branch is how the compiler keeps an
        out-of-range index off the table, so N is the table's length. Taking
        the nearest `sltiu` instead of the one that tests *this* index is what
        an earlier version did, and it read a 236-entry table out of a guard
        belonging to something else: the arms then reached into four unrelated
        routines and swallowed them into one 3965-instruction function.
        """
        if idx is None:
            return None
        seen, layer = {block}, [block]
        for _depth in range(6):
            nxt = []
            for b in layer:
                for a in reversed(fn.blocks.get(b, [])):
                    i = self.insns.get(a)
                    if i is not None and i.mn in ("sltiu", "slti") \
                            and i.rs == idx and i.imm:
                        return i.imm
                for p in fn.preds.get(b, []):
                    if p not in seen:
                        seen.add(p)
                        nxt.append(p)
            layer = nxt
            if not layer:
                break
        return None

    def _read_table(self, fn, at, base, ins, block=None, idx=None):
        """The arms of a switch, and how far the table was known to run.

        Where the guard is found the count is read off it. Where it is not, the
        entries are still taken -- while they point at something that decodes
        as code -- but the table is recorded as `plausible`, because a bound
        that was guessed must never be reported as one that was read.
        """
        e = self.exe
        if any(t["at"] == at for t in fn.tables):
            return
        bound = self._bound(fn, block, idx) if block is not None else None
        targets, a = [], base
        limit = bound if bound else 64
        while len(targets) < limit:
            w = e.word(a)
            if w is None or w not in e or w % 4 or not looks_like_code(e, w):
                break
            targets.append(w)
            a += 4
        if targets:
            fn.tables.append({"at": at, "base": base, "targets": targets,
                              "idx": idx,
                              "bound": "sltiu" if bound else "plausible"})

    def _callers(self):
        self.into = {}
        for f, fn in self.funcs.items():
            for a, t, _args in fn.calls:
                self.into.setdefault(t, []).append((f, a))
            for a, t in fn.tail:
                self.into.setdefault(t, []).append((f, a))
        for f, fn in self.funcs.items():
            fn.callers = sorted(set(c for c, _a in self.into.get(f, [])))


def _s32(v):
    return v - 0x100000000 if v & 0x80000000 else v


def _alu(mn, x, y):
    m = 0xFFFFFFFF
    if mn in ("addu", "add"):
        return (x + y) & m
    if mn in ("subu", "sub"):
        return (x - y) & m
    if mn == "and":
        return x & y
    if mn == "or":
        return x | y
    if mn == "xor":
        return x ^ y
    if mn == "nor":
        return (~(x | y)) & m
    if mn == "slt":
        return int(_s32(x) < _s32(y))
    if mn == "sltu":
        return int(x < y)
    if mn in ("sll", "sllv"):
        return (x << (y & 31)) & m
    if mn in ("srl", "srlv"):
        return (x & m) >> (y & 31)
    if mn in ("sra", "srav"):
        return (_s32(x) >> (y & 31)) & m
    return None


def _successors(walk, fn, ins):
    """Where a block goes, taken from its terminator.

    The terminator is the second-to-last instruction, not the last: the last is
    the delay slot, and reading the block backwards from it says every branch
    falls through. That mistake makes the constant propagation agree with
    itself and be wrong everywhere a branch matters.
    """
    if not ins:
        return []
    for a in (ins[-2] if len(ins) > 1 else None, ins[-1]):
        if a is None:
            continue
        i = walk.insns.get(a)
        if i is None:
            continue
        if i.kind == "branch":
            return [i.target, a + 8]
        if i.kind == "jump":
            return [i.target]
        if i.kind == "jr":
            for tb in fn.tables:
                if tb["at"] == a:
                    return list(tb["targets"])
            return []
    return [ins[-1] + 4]


def _merge(old, new):
    if old is None:
        return dict(new)
    out = {}
    for k, v in old.items():
        if k in new and new[k] == v:
            out[k] = v
    return out


class Func:
    def __init__(self, addr, nick):
        self.addr, self.nick = addr, nick
        self.end = addr
        self.body = []
        self.calls, self.tail, self.indirect, self.rets = [], [], [], []
        self.switches, self.broken, self.tables = [], [], []
        self.into_next = []
        self.blocks, self.leaders = {}, []
        self.refs, self.consts, self.callers, self.argsat = [], [], [], {}

    @property
    def name(self):
        n = syms.name_in(self.nick, self.addr, "")
        return n or f"sub_{self.addr:08x}"

    @property
    def named(self):
        return bool(syms.name_in(self.nick, self.addr, ""))

    def __repr__(self):
        return f"<{self.name} {self.addr:#010x} {len(self.body)} insns>"


# --- what a start actually is ------------------------------------------
#
# Not every address the walk starts from is a function. `object_motion`
# (0x8004b288) and `object_trigger_args` (0x8004a824) were named from live
# analysis and are *arms of a switch* inside the object opcode interpreter at
# 0x80047010 -- one routine with a 236-entry table, which `sltiu $v0, $v1,
# 0xec` states outright. Walking from an arm re-walks the whole routine, which
# is how three "functions" of 3948 instructions each appeared for what is one
# routine of 3965. So each start is classified, and a start that nothing calls
# and that lies inside another routine's body is a **label**, kept as a name in
# that routine's listing rather than promoted to a function of its own.

def classify(w):
    """Split the starts into real functions and labels inside them."""
    jaled = set()
    for fn in w.funcs.values():
        for _a, t, _g in fn.calls:
            jaled.add(t)
        for _a, t in fn.tail:
            jaled.add(t)
    arms = {t for fn in w.funcs.values() for tb in fn.tables
            for t in tb["targets"]}
    tabled = set(getattr(w, "ptr_words", {}).values()) - arms
    w.labels = {}
    for f in sorted(w.funcs):
        if f == w.exe.entry or f in jaled or f in tabled:
            continue
        owner = None
        for o in sorted(w.funcs):
            if o == f or o > f:
                continue
            if f in w.funcs[o].body and len(w.funcs[o].body) > len(w.funcs[f].body):
                owner = o
                break
        if owner is not None:
            w.labels[f] = owner
    for f in w.labels:
        w.funcs.pop(f, None)
    w._jaled = jaled
    w._tabled = tabled
    w._callers()
    return w


def overlay_seeds():
    """Addresses in GAME.EXE that the levels' own code calls.

    `FDAT.T` entry `3n + 2` is native MIPS shipped with each level, and it
    calls into the game. Those targets are entry points no walk of GAME.EXE
    can see -- nothing inside the executable calls them -- and they are the
    game's API surface, so they are worth every one of them. Returns an empty
    set when the disc is not unpacked, rather than failing.
    """
    try:
        import overlay as ov
        import struct
    except Exception:
        return set()
    seeds = set()
    for lv in range(28):
        try:
            raw, _ptrs, _n = ov.overlay(lv)
        except Exception:
            continue
        if not raw:
            continue
        for off in range(0, len(raw) - 3, 4):
            w = struct.unpack_from("<I", raw, off)[0]
            if (w >> 26) == 3:                        # jal
                t = (ov.BASE & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                if 0x80011000 <= t < 0x8009c800:
                    seeds.add(t)
    return seeds


def build(nick, seeds=()):
    """Walk one executable and settle what is a function and what is a label."""
    exe = mips.load(nick)
    extra = set(seeds)
    if nick == "game":
        extra |= overlay_seeds()
    w = Walk(exe, nick).run(extra)
    return classify(w)


# --- reading one routine ------------------------------------------------

def frame(w, fn):
    """The stack frame and the registers a routine saves, off its prologue.

    A register only counts as saved if nothing has written it since the
    routine began: `li $s3, 0x6a4` then `sw $s3, 0x10($sp)` is the fifth
    argument going onto the stack, not $s3 being preserved, and counting it
    put $s3 in `player_vertical`'s save list twice.
    """
    size, saved, written = 0, [], set()
    for a in fn.body[:32]:
        i = w.insns[a]
        if i.mn == "addiu" and i.rt == 29 and i.rs == 29 and i.simm < 0:
            size = -i.simm
        elif i.mn == "sw" and i.rs == 29 and i.rt in SAVED \
                and i.rt not in written:
            saved.append(i.rt)
            written.add(i.rt)
        if i.writes is not None:
            written.add(i.writes)
    return size, [SAVED[r] for r in sorted(saved)]


def labels_for(w, fn):
    """Local names for every branch target inside a routine.

    Numbered in address order, so a listing read twice reads the same twice --
    numbering them in the order the walk happens to reach them does not.
    """
    body = set(fn.body)
    tgts = set()
    for a in fn.body:
        i = w.insns[a]
        if i.kind in ("branch", "jump") and i.target in body and i.target != fn.addr:
            tgts.add(i.target)
    for tb in fn.tables:
        tgts |= {t for t in tb["targets"] if t in body}
    return {t: f".L{n + 1}" for n, t in enumerate(sorted(tgts))}


def comment(w, fn, i, refs, consts, names):
    """What to say about one instruction, or nothing.

    Only what was established: an address the constant propagation formed, the
    string it points at, what a GTE command computes, the constants going into
    a call. A value that is not constant contributes nothing rather than a
    plausible-looking stale one.
    """
    bits = []
    r = refs.get(i.addr)
    if r:
        addr, mode, width = r
        nm = syms.label_in(fn.nick, addr)
        st = w.exe.string(addr) if addr in w.exe else None
        wid = {1: "byte", 2: "half", 4: "word"}.get(width, "")
        kind = {"read": f"reads the {wid}" if wid else "reads",
                "write": f"writes the {wid}" if wid else "writes",
                "addr": "the address of"}[mode]
        piece = f"{kind} [{addr:#010x}]"
        if nm != f"{addr:#010x}":
            piece += f" {nm}"
        if st:
            piece += f'  "{st}"'
        bits.append(piece)
    if i.kind == "call":
        args = fn.argsat.get(i.addr) or {}
        if args:
            bits.append("(" + ", ".join(f"{ARGREG[k]}={_num(v)}"
                                        for k in sorted(args) if k in ARGREG
                                        for v in [args[k]]) + ")")
        b = bios_at(w.exe, i.addr)
        if b:
            bits.append(f"BIOS {b[2]}")
    if i.kind == "gte" and i.cop:
        bits.append(i.cop)
    if i.mn == "sltiu" and i.imm and any(
            i.rs == tb.get("idx") for tb in fn.tables):
        bits.append(f"the switch below has {i.imm} cases")
    c = consts.get(i.addr)
    if c:
        bits.append(c)
    return "; " + "  ".join(bits) if bits else ""


def _num(v):
    if isinstance(v, int):
        return f"{v:#x}" if v > 9 or v < -9 else str(v)
    return "?"


def render(w, fn, out=sys.stdout, const_names=None, portmap=None):
    """One routine, annotated, in the form a person reads."""
    lab = labels_for(w, fn)
    refs = {}
    for a, addr, mode, width in fn.refs:
        if a not in refs or mode != "addr":
            refs[a] = (addr, mode, width)
    consts = {}
    for a, val, mn in fn.consts:
        got = (const_names or {}).get(val)
        if not got or abs(val) <= 8:
            continue
        if isinstance(got, str):                   # a plain {value: name} map
            consts[a] = got
            continue
        here = [nm for nm, where in got if not where or fn.name in where]
        away = [nm for nm, where in got if where and fn.name not in where]
        if here:
            consts[a] = " or ".join(here)
        elif away:
            # Not a claim about this site: the number means that somewhere
            # else, and saying so is the whole use of the cross reference.
            consts[a] = f"= {' or '.join(away)} elsewhere"
    # The numbers the compiler took apart. Without these a listing of
    # `collide_at_cell` shows six shifts and adds and never the word 800.
    chains = {}
    try:
        import consts as _consts
        for a, kind, k, reg in _consts.chains(w, fn):
            nm = ""
            got = (const_names or {}).get(k)
            if isinstance(got, list):
                hit = [n for n, where in got if not where or fn.name in where]
                nm = f"  {' or '.join(hit)}" if hit else ""
            chains.setdefault(a, []).append(
                f"{k} {'times' if kind == 'multiplier' else 'into'} "
                f"${reg}{nm}")
    except Exception:
        pass
    size, saved = frame(w, fn)
    line = "; " + "=" * 68
    print(line, file=out)
    print(f"; {fn.name:<40s}  {fn.nick}:{fn.addr:#010x}", file=out)
    print(f"; {len(fn.body)} instructions in {len(fn.blocks)} blocks, "
          f"{fn.addr:#010x}..{fn.end:#010x}", file=out)
    if size or saved:
        print(f"; frame {size:#x}" + (f", saves {' '.join('$' + s for s in saved)}"
                                      if saved else ""), file=out)
    ent = syms.table(fn.nick).get(fn.addr)
    if ent and ent.get("evidence"):
        print(f"; why the name: {ent['evidence']}", file=out)
    if fn.callers:
        cs = ", ".join(syms.label_in(fn.nick, c) for c in fn.callers[:8])
        print(f"; called by {cs}"
              + (f" and {len(fn.callers) - 8} more" if len(fn.callers) > 8 else ""),
              file=out)
    else:
        print("; called by nothing in this executable "
              "(a table, an overlay or an interrupt reaches it)", file=out)
    inside = [a for a, o in w.labels.items() if o == fn.addr]
    for a in sorted(inside):
        print(f"; contains {syms.name_in(fn.nick, a)} at +{a - fn.addr:#x} "
              "-- a label in this routine, not a routine of its own", file=out)
    for tb in fn.tables:
        print(f"; switch at {tb['at']:#010x}: {len(tb['targets'])} arms from "
              f"{tb['base']:#010x}, bound read off the {tb['bound']}", file=out)
    p = (portmap or {}).get(f"{fn.nick}:{fn.addr:#010x}")
    if p:
        print(f"; port: {p}", file=out)
    print(line, file=out)

    def sym(a):
        if a in lab:
            return lab[a]
        return syms.label_in(fn.nick, a)

    prev = None
    for a in fn.body:
        if prev is not None and a != prev + 4:
            print(f"; ... {(a - prev - 4) // 4} words not reached", file=out)
        if a in lab:
            print(f"{lab[a]}:", file=out)
        if a in w.labels:
            print(f"{syms.name_in(fn.nick, a)}:   ; a label, not a routine",
                  file=out)
        i = w.insns[a]
        c = comment(w, fn, i, refs, consts, None)
        if a in chains:
            c = (c + "  " if c else "; ") + ", ".join(chains[a])
        txt = i.fmt(sym)
        print(f"  {a:#010x}  {txt:<38s}{c}".rstrip(), file=out)
        prev = a


# --- the database -------------------------------------------------------

def to_json(w):
    """Everything the walk settled, as data other tools can read."""
    funcs = {}
    for f, fn in sorted(w.funcs.items()):
        size, saved = frame(w, fn)
        funcs[f"{f:#010x}"] = {
            "name": fn.name,
            "named": fn.named,
            "start": f, "end": fn.end, "insns": len(fn.body),
            "blocks": len(fn.blocks),
            "frame": size, "saves": saved,
            "leaf": not fn.calls and not fn.indirect,
            "calls": [{"at": a, "to": t,
                       "args": {ARGREG[k]: v for k, v in (g or {}).items()
                                if k in ARGREG}}
                      for a, t, g in fn.calls],
            "tail": [{"at": a, "to": t} for a, t in fn.tail],
            "indirect": fn.indirect,
            "callers": fn.callers,
            "switch": fn.tables,
            "reads": sorted({addr for _a, addr, m, _wd in fn.refs if m == "read"}),
            "writes": sorted({addr for _a, addr, m, _wd in fn.refs if m == "write"}),
            "refs": [{"at": a, "addr": addr, "mode": m, "width": wd}
                     for a, addr, m, wd in fn.refs],
            "consts": [{"at": a, "value": v, "mn": mn} for a, v, mn in fn.consts],
            "labels": {f"{a:#010x}": syms.name_in(w.nick, a)
                       for a, o in w.labels.items() if o == f},
        }
    return {
        "exe": w.nick, "path": os.path.relpath(w.exe.path, ROOT),
        "base": w.exe.base, "entry": w.exe.entry, "size": w.exe.size,
        "functions": funcs,
        "labels": {f"{a:#010x}": {"name": syms.name_in(w.nick, a), "inside": o}
                   for a, o in sorted(w.labels.items())},
        "reached": len(w.insns),
        "words": w.exe.size // 4,
    }


def tree(w, root, depth=3, out=sys.stdout, _seen=None, _pre=""):
    _seen = _seen if _seen is not None else set()
    if depth < 0 or root not in w.funcs:
        return
    fn = w.funcs[root]
    kids = []
    for a, t, _g in fn.calls:
        if not kids or kids[-1] != t:
            kids.append(t)
    for _a, t in fn.tail:
        kids.append(t)
    seen_b = [bios_at(w.exe, a) for a in fn.body
              if w.insns[a].kind == "call" and bios_at(w.exe, a)]
    names = []
    for t in kids:
        names.append((w.funcs[t].name if t in w.funcs
                      else syms.label_in(w.nick, t), t))
    for b in seen_b:
        names.append((f"<{b[2]}>", None))
    if fn.indirect:
        names.append((f"({len(fn.indirect)} through a register)", None))
    for n, (nm, t) in enumerate(names):
        last = n == len(names) - 1
        again = t in _seen
        print(f"{_pre}{'`-- ' if last else '|-- '}{nm}"
              + ("  ..." if again and t in w.funcs and w.funcs[t].calls else ""),
              file=out)
        if t is not None and not again:
            _seen.add(t)
            tree(w, t, depth - 1, out, _seen, _pre + ("    " if last else "|   "))


def graph(w, out_dir=None):
    """The call graph, in the two forms that get used.

    A `.dot` for graphviz, and a plain tree from the entry point for reading.
    The tree is the one that answers "what happens before what", which is the
    question a static listing cannot: the shell before the logo, the logo
    before the menu, the menu before the game.
    """
    d = out_dir or os.path.join(OUT)
    os.makedirs(d, exist_ok=True)
    dot = os.path.join(d, f"{w.nick}.dot")
    with open(dot, "w") as fh:
        print(f'digraph {w.nick} {{', file=fh)
        print('  node [shape=box, fontname="monospace", fontsize=9];', file=fh)
        for f, fn in sorted(w.funcs.items()):
            shape = "doubleoctagon" if f == w.exe.entry else "box"
            style = ',style=filled,fillcolor="#e8e8e8"' if not fn.named else ""
            print(f'  "{f:#010x}" [label="{fn.name}\n{len(fn.body)}",'
                  f'shape={shape}{style}];', file=fh)
        seen = set()
        for f, fn in sorted(w.funcs.items()):
            for _a, t, _g in fn.calls:
                if t in w.funcs and (f, t) not in seen:
                    seen.add((f, t))
                    print(f'  "{f:#010x}" -> "{t:#010x}";', file=fh)
            for _a, t in fn.tail:
                if t in w.funcs and (f, t, "tail") not in seen:
                    seen.add((f, t, "tail"))
                    print(f'  "{f:#010x}" -> "{t:#010x}" [style=dashed];',
                          file=fh)
        print("}", file=fh)
    txt = os.path.join(d, f"{w.nick}.tree.txt")
    with open(txt, "w") as fh:
        print(f"{w.nick}: the call tree from {w.exe.entry:#010x}", file=fh)
        print(w.funcs[w.exe.entry].name, file=fh)
        tree(w, w.exe.entry, 12, fh)
        print(file=fh)
        print("Routines no call in this executable reaches -- a pointer table, "
              "a level overlay or an interrupt gets to them:", file=fh)
        for f, fn in sorted(w.funcs.items()):
            if not fn.callers and f != w.exe.entry:
                print(f"  {f:#010x}  {len(fn.body):5d}  {fn.name}", file=fh)
    return dot, txt


def save(nick, seeds=()):
    os.makedirs(OUT, exist_ok=True)
    w = build(nick, seeds)
    path = os.path.join(OUT, f"{nick}.json")
    with open(path, "w") as fh:
        json.dump(to_json(w), fh, indent=1)
    return w, path


def listings(w, const_names=None, portmap=None):
    d = os.path.join(ROOT, "out", "asm", w.nick)
    os.makedirs(d, exist_ok=True)
    n = 0
    for f, fn in sorted(w.funcs.items()):
        with open(os.path.join(d, f"{f:08x}_{fn.name}.s"), "w") as fh:
            render(w, fn, fh, const_names, portmap)
        n += 1
    with open(os.path.join(d, "index.txt"), "w") as fh:
        print(f"{w.nick}: {len(w.funcs)} routines, {len(w.insns)} instructions "
              f"reached from {w.exe.entry:#010x}", file=fh)
        for f, fn in sorted(w.funcs.items(), key=lambda kv: -len(kv[1].body)):
            print(f"  {f:#010x}  {len(fn.body):5d}  {fn.name}", file=fh)
    return d, n


# --- what an unnamed routine is about ------------------------------------
#
# 675 of GAME.EXE's 816 routines have no name, and most of them never will have
# one worth trusting. What they can have is a *profile*: the named globals they
# touch, the named routines they call, and which of the machine's parts they
# use. That is all read off the code, none of it is a guess, and it turns a list
# of `sub_8004a824` into something a person can search.

HARDWARE = {
    (0x1F801810, 0x1F801818): "the GPU",
    (0x1F801820, 0x1F801828): "the MDEC",
    (0x1F801040, 0x1F801060): "the pads and the serial port",
    (0x1F801070, 0x1F801078): "the interrupt controller",
    (0x1F801080, 0x1F801100): "DMA",
    (0x1F801100, 0x1F801130): "the timers",
    (0x1F801800, 0x1F801804): "the CD drive",
    (0x1F801C00, 0x1F802000): "the SPU",
}


def profile(w, fn):
    """One line about a routine, entirely out of what it touches."""
    bits = []
    gte = sum(1 for a in fn.body if w.insns[a].kind in ("gte", "cop")
              and w.insns[a].mn not in ("mfc0", "mtc0", "rfe"))
    if gte:
        cmds = {w.insns[a].mn for a in fn.body if w.insns[a].kind == "gte"}
        bits.append("uses the GTE" + (f" ({', '.join(sorted(cmds))})"
                                      if cmds else ""))
    hw = set()
    for _a, addr, _m, _wd in fn.refs:
        for (lo, hi), what in HARDWARE.items():
            if lo <= addr < hi:
                hw.add(what)
    if hw:
        bits.append("talks to " + " and ".join(sorted(hw)))
    named = []
    for _a, t, _g in fn.calls:
        nm = syms.name_in(w.nick, t, "")
        if nm and nm not in named:
            named.append(nm)
    if named:
        bits.append("calls " + ", ".join(named[:4])
                    + (f" and {len(named) - 4} more" if len(named) > 4 else ""))
    glob = []
    for _a, addr, mode, _wd in fn.refs:
        nm = syms.name_in(w.nick, addr, "")
        if nm and (nm, mode) not in glob and mode in ("read", "write", "addr"):
            glob.append((nm, mode))
    if glob:
        bits.append(", ".join(f"{m}s {n}" if m != "addr" else f"points at {n}"
                              for n, m in glob[:4]))
    b = bios_calls(w, fn)
    if b:
        bits.append("BIOS " + ", ".join(sorted(set(b))[:4]))
    return "; ".join(bits)


def bios_calls(w, fn):
    out = []
    for a in fn.body:
        if w.insns[a].kind == "call":
            got = bios_at(w.exe, a)
            if got:
                out.append(got[2])
    return out


def describe(w, out=sys.stdout, unnamed_only=True):
    rows = []
    for f, fn in sorted(w.funcs.items()):
        if unnamed_only and fn.named:
            continue
        rows.append((len(fn.body), f, fn, profile(w, fn)))
    print(f"{len(rows)} routines" + (" with no name" if unnamed_only else "")
          + f" in {w.nick}", file=out)
    for n, f, fn, p in sorted(rows, reverse=True):
        print(f"{f:#010x}  {n:5d} insns  {len(fn.callers):3d} callers  "
              f"{fn.name}", file=out)
        if p:
            print(f"            {p}", file=out)


if __name__ == "__main__":
    argv = sys.argv[1:]
    nick = argv.pop(0) if argv and argv[0] in mips.EXES else "game"
    depth = 3
    if "-d" in argv:
        k = argv.index("-d")
        depth = int(argv[k + 1])
        del argv[k:k + 2]
    flags = [a for a in argv if a.startswith("--")]
    rest = [a for a in argv if not a.startswith("--")]
    cn, pm = None, None
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

    if "--build" in flags:
        w, path = save(nick)
        print(f"{nick}: {len(w.funcs)} routines, {len(w.labels)} labels inside "
              f"them, {len(w.insns)} of {w.exe.size // 4} words reached")
        print(f"wrote {os.path.relpath(path, ROOT)}")
    elif "--graph" in flags:
        w = build(nick)
        dot, txt = graph(w)
        print(f"wrote {os.path.relpath(dot, ROOT)} and "
              f"{os.path.relpath(txt, ROOT)}")
    elif "--listing" in flags:
        w = build(nick)
        d, n = listings(w, cn, pm)
        print(f"wrote {n} listings into {os.path.relpath(d, ROOT)}")
    elif "--describe" in flags:
        w = build(nick)
        d = os.path.join(ROOT, "out", "rdis")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{nick}.profiles.txt")
        with open(path, "w") as fh:
            describe(w, fh, unnamed_only=False)
        describe(w)
        print(f"\nwrote {os.path.relpath(path, ROOT)}", file=sys.stderr)
    elif "--unnamed" in flags:
        w = build(nick)
        rows = [(len(fn.body), f, fn) for f, fn in w.funcs.items() if not fn.named]
        for n, f, fn in sorted(rows, reverse=True)[:40]:
            print(f"  {f:#010x}  {n:5d} insns  {len(fn.callers):3d} callers  "
                  f"{len(fn.calls):3d} calls")
    elif "--tree" in flags:
        w = build(nick)
        root = w.exe.entry if (not rest or rest[0] == "entry") else int(rest[0], 0)
        print(syms.label_in(nick, root))
        tree(w, root, depth)
    elif rest:
        w = build(nick)
        a = int(rest[0], 0)
        fn = w.funcs.get(a)
        if fn is None:
            owner = next((o for o, g in w.funcs.items()
                          if a in g.body), None)
            if owner is None:
                print(f"{a:#010x} is not in any routine the walk reached")
                sys.exit(1)
            print(f"; {a:#010x} is inside {w.funcs[owner].name}", file=sys.stderr)
            fn = w.funcs[owner]
        render(w, fn, sys.stdout, cn, pm)
    else:
        w = build(nick)
        print(f"{w.exe.path}")
        print(f"  base {w.exe.base:#010x}  entry {w.exe.entry:#010x}  "
              f"size {w.exe.size:#x}")
        print(f"  {len(w.funcs)} routines, {len(w.labels)} labels inside them")
        print(f"  {len(w.insns)} of {w.exe.size // 4} words reached by control flow")
        named = sum(1 for fn in w.funcs.values() if fn.named)
        print(f"  {named} routines have a name; {len(w.funcs) - named} do not")
        print(f"  {sum(len(f.tables) for f in w.funcs.values())} switch tables, "
              f"{sum(len(t['targets']) for f in w.funcs.values() for t in f.tables)}"
              " arms")
        print(f"  {sum(len(f.indirect) for f in w.funcs.values())} calls through "
              "a register")

#!/usr/bin/env python3
"""The same walk `tools/rdis.py` does to GAME.EXE, done to a level's overlay.

    python3 tools/ovdis.py 0            level 0: routines, switches, calls
    python3 tools/ovdis.py 0 --listing  every routine, annotated, to out/asm/ov00/
    python3 tools/ovdis.py --all        every level, one line each

`tools/overlay.py` reads an overlay linearly and `tools/decomp.py` turns what
it recognises into statements. Neither follows control flow, so neither
resolves a jump table, and the overlays are full of them: a level's
conversation hook is a switch, and so is most of what it calls.

An overlay is not a PS-EXE -- it is a length-prefixed archive entry that loads
at a fixed address and is never relocated -- so this wraps it in the same
interface `mips.Exe` presents and hands it to the walker unchanged. The
**32 pointers at entry+4** are the seeds, since nothing inside calls them;
`GAME.EXE` does, through `level_hooks`.

What that buys, level 0 as the example: the walker resolves the six-arm table
the conversation hook switches on, so `tools/quest.py` is checking its own
reading of that table against a second one, and every routine gets the
constant propagation that names `has_item(130)` rather than `jal 0x8005d7bc`.

Addresses outside the overlay are left alone. A `jal` into `GAME.EXE` is
recorded as a call and not followed, which is what `Exe.__contains__` saying
no already does.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips                                                           # noqa: E402
import overlay                                                       # noqa: E402
import rdis                                                          # noqa: E402
import syms                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


class OverlayExe:
    """A level's overlay, presented the way `mips.Exe` presents a PS-EXE."""

    def __init__(self, lv, raw):
        self.lv = lv
        self.nick = f"ov{lv:02d}"
        self.path = f"FDAT.T entry {3 * lv + 2}"
        self.text = raw
        self.base = overlay.BASE
        self.end = self.base + len(raw)
        self.size = len(raw)
        self.gp = 0
        self.sp = 0
        ptrs = [struct.unpack_from("<I", raw, 4 + 4 * i)[0] for i in range(32)]
        self.pointers = [p for p in ptrs if self.base <= p < self.end]
        # The walker wants one entry point. Slot 0 is as good as any; the rest
        # are handed in as seeds.
        self.entry = self.pointers[0] if self.pointers else self.base

    def __contains__(self, addr):
        return self.base <= addr < self.end

    def word(self, addr):
        off = addr - self.base
        if not (0 <= off <= len(self.text) - 4):
            return None
        return struct.unpack_from("<I", self.text, off)[0]

    def bytes(self, addr, n):
        off = addr - self.base
        return self.text[off:off + n] if off >= 0 else b""

    def string(self, addr, limit=200):
        return None            # an overlay carries no strings of its own

    # The control-flow reader `mips.Exe` provides is address-independent, so
    # it is borrowed rather than copied.
    op = mips.Exe.op


def _borrow_names(nick, lo, hi):
    """Let an overlay's listings use GAME.EXE's address book.

    Every call an overlay makes goes into `GAME.EXE`, so without this a
    listing reads `jal 0x8005d7bc` where it could read `jal has_item`.
    Entries that would claim an address *inside* the overlay are dropped:
    the overlay loads into what `GAME.EXE` calls bss, and a game symbol with
    a size could otherwise swallow a routine that is nothing to do with it.
    """
    if nick in syms._TABLES:
        return
    t = {}
    for a, e in syms.table("game").items():
        if lo <= a < hi:
            continue
        if "size" in e and a <= lo < a + e["size"]:
            continue
        t[a] = e
    syms._TABLES[nick] = t


def walk(lv):
    """The walker's result for one level's overlay, or None."""
    raw, _ptrs, _insns = overlay.overlay(lv)
    if not raw:
        return None
    e = OverlayExe(lv, raw)
    if not e.pointers:
        return None
    _borrow_names(e.nick, e.base, e.end)
    w = rdis.Walk(e, e.nick).run(e.pointers)
    # Same step `rdis.build` does: a start that nothing calls and that lies
    # inside another routine is a label in that routine, not a routine.
    return rdis.classify(w)


def report(lv, out=sys.stdout):
    w = walk(lv)
    if w is None:
        return None
    words = sum(len(f.body) for f in w.funcs.values())
    tabs = [(f.addr, tb) for f in w.funcs.values() for tb in f.tables]
    calls = {}
    for f in w.funcs.values():
        for _a, t, _c in f.calls:
            if t not in w.exe:
                calls[t] = calls.get(t, 0) + 1
    print(f"level {lv}: {len(w.funcs)} routines, {words} of "
          f"{w.exe.size // 4} words walked, {len(tabs)} switch tables", file=out)
    for a, tb in tabs:
        print(f"    switch in {a:#010x} at {tb['at']:#010x}: "
              f"{len(tb['targets'])} arms from {tb['base']:#010x}", file=out)
    if calls:
        print("    calls into GAME.EXE: " + ", ".join(
            f"{syms.label(t)}" + (f" x{n}" if n > 1 else "")
            for t, n in sorted(calls.items(), key=lambda x: -x[1])[:10]), file=out)
    return w


def listing(lv):
    """Annotated listings for one overlay, into out/asm/ovNN/."""
    w = walk(lv)
    if w is None:
        return 0
    out = os.path.join(ROOT, "out", "asm", w.exe.nick)
    return rdis.listings(w), out


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "--all" or arg is None:
        print(__doc__ if arg is None else "")
        tot = 0
        for lv in range(28):
            w = walk(lv)
            if w is None:
                continue
            n = sum(len(f.body) for f in w.funcs.values())
            tot += n
            tabs = sum(len(f.tables) for f in w.funcs.values())
            print(f"  level {lv:2d}: {len(w.funcs):3d} routines, {n:5d} of "
                  f"{w.exe.size // 4:5d} words, {tabs} switch tables")
        print(f"\n{tot} words of level code walked")
    else:
        lv = int(arg)
        w = report(lv)
        if w is not None and len(sys.argv) > 2 and sys.argv[2] == "--listing":
            n, where = listing(lv)
            print(f"  {n} listings -> {where}")

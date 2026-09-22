#!/usr/bin/env python3
"""Which part of the game each routine belongs to.

    python3 tools/subsys.py            the map, counted
    python3 tools/subsys.py player     one subsystem, routine by routine
    python3 tools/subsys.py --doc      regenerate MAP.md
    python3 tools/subsys.py 0x8002ed60 what one routine belongs to, and why

816 routines is too many to name one at a time and most of them will never
earn a name. What every one of them can have is a **place**: the part of the
frame it is reachable from.

`game_main` runs sixteen calls in a loop and `render_frame` is twenty-two more
(FORMATS.md, "What a frame is"). Each of those is a root here. A routine
reached from exactly one root belongs to it; a routine reached from several is
**shared**, and one reached from none is either dead or gets there through a
pointer -- which is worth knowing on its own, because that is where the
interrupt handlers and the level overlays' targets are.

Nothing here is a guess: the edges are the call graph `tools/rdis.py` walked,
and the roots are the calls `game_main` and `render_frame` actually make.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rdis                                                          # noqa: E402
import syms                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# The roots, in the order the frame runs them. The name is what to call the
# subsystem; the address is the call game_main or render_frame makes.
ROOTS = [
    ("lighting", 0x800341E8, "the 64 lighting entries, refilled and stepped"),
    ("lighting", 0x80034300, ""),
    ("render_state", 0x80034180, "the eleven render flags"),
    ("objects", 0x80047010, "the object interpreter and its 44 handlers"),
    ("player", 0x80030FCC, "the pad, the turn, the walk and the height"),
    ("actors", 0x80052E5C, "the 199 creature slots"),
    ("ai", 0x8005BC50, "the 128 behaviour slots"),
    ("level", 0x8005EB20, "the level's own code, and the fades"),
    ("level", 0x80018358, "the seven-state load"),
    ("flags", 0x80061940, "the story flags"),
    ("camera", 0x8002B330, "the eye and the three view angles"),
    ("sound", 0x800156BC, "the listener, and the two task servicers"),
    ("sound", 0x80018CD0, ""),
    ("sound", 0x80015A48, ""),
    ("render", 0x800422B8, "everything drawn"),
]

# Roots that are not in the frame but head a subsystem of their own, reached
# through a pointer or from a menu rather than from game_main's loop.
EXTRA = [
    ("menu", 0x8001DD94, "the inventory and the pause screens"),
    ("items", 0x8005CBE0, "use_item and the inventory primitives"),
    ("save", 0x8005F7E0, "the serialiser and its inverse"),
    ("boot", 0x800144F8, "the entry point, before the loop"),
]


# The Sony library, the CD reader, the GPU queue and the memory card. Every
# root reaches all of it -- the first version of this file put 697 of the 816
# routines in one "shared" bucket for exactly that reason, which said nothing.
# A walk stops *at* a library routine: the routine itself is recorded as
# library, and nothing below it is charged to whoever called it.
LIBRARY_PREFIX = ("Draw", "Put", "Set", "Clear", "Load", "Store", "Move",
                  "Reset", "Cd", "CD_", "Dec", "Pad", "card_", "gpu_", "cd_",
                  "mem", "malloc", "free", "heap", "printf", "puts",
                  "block_copy", "block_zero", "rand", "archive_", "read_",
                  "AddPrim", "SetPolyFT4", "frame_begin", "frame_end",
                  "pad_wait", "sound_task")


def is_library(w, f):
    """Is this the Sony library, or something that only talks to hardware?"""
    fn = w.funcs[f]
    if any(fn.name.startswith(p) for p in LIBRARY_PREFIX):
        return True
    prof = rdis.profile(w, fn)
    return "talks to " in prof or prof.startswith("BIOS ")


def distances(w, root, library):
    """`{routine: how many calls from the root}`, stopping at the library."""
    from collections import deque
    d, q = {root: 0}, deque([root])
    while q:
        f = q.popleft()
        if f in library and f != root:
            continue                      # recorded, but not walked through
        for t in [t for _a, t, _g in w.funcs[f].calls] + \
                 [t for _a, t in w.funcs[f].tail]:
            if t in w.funcs and t not in d:
                d[t] = d[f] + 1
                q.append(t)
    return d


def assign(w=None):
    """`(by_routine, by_subsystem)` -- where each routine belongs."""
    w = w or rdis.build("game")
    library = {f for f in w.funcs if is_library(w, f)}
    # Reachability alone says nothing here: every root reaches nearly
    # everything through a handful of shared helpers, and the first version of
    # this put 630 of 816 routines in one bucket. **Nearest root** is the
    # question worth asking -- how many calls from each part of the frame --
    # and ties go to whichever runs first, which is the frame's own order.
    dist = {}
    for name, addr, _why in ROOTS + EXTRA:
        if addr not in w.funcs:
            continue
        for f, n in distances(w, addr, library).items():
            cur = dist.get(f)
            if cur is None or n < cur[0]:
                dist[f] = (n, name)
    owner = collections.defaultdict(set)
    for f, (_n, name) in dist.items():
        owner[f].add(name)
    by_routine = {}
    for f in w.funcs:
        if f in library:
            by_routine[f] = "library"
        elif f in dist:
            by_routine[f] = dist[f][1]
        else:
            by_routine[f] = "unreached"
    globals()["_DIST"] = dist
    groups = collections.defaultdict(list)
    for f, name in by_routine.items():
        groups[name].append(f)
    return by_routine, groups, owner, w


def summary(out=sys.stdout):
    by, groups, owner, w = assign()
    total_i = sum(len(fn.body) for fn in w.funcs.values())
    print(f"{len(w.funcs)} routines, {total_i} instructions", file=out)
    print(f"{'subsystem':14s} {'routines':>9s} {'instructions':>13s}  "
          f"{'named':>6s}", file=out)
    rows = []
    for name, fs in groups.items():
        ins = sum(len(w.funcs[f].body) for f in fs)
        named = sum(1 for f in fs if w.funcs[f].named)
        rows.append((ins, name, len(fs), named))
    for ins, name, n, named in sorted(rows, reverse=True):
        print(f"{name:14s} {n:9d} {ins:13d}  {named:4d}/{n}", file=out)
    return by, groups, owner, w


def show(which, out=sys.stdout):
    by, groups, owner, w = assign()
    fs = groups.get(which)
    if fs is None:
        print(f"no subsystem called {which}; try: "
              + ", ".join(sorted(groups)), file=out)
        return
    ins = sum(len(w.funcs[f].body) for f in fs)
    print(f"{which}: {len(fs)} routines, {ins} instructions", file=out)
    prof = _profiles()
    for f in sorted(fs, key=lambda x: -len(w.funcs[x].body)):
        fn = w.funcs[f]
        print(f"  {f:#010x}  {len(fn.body):5d}  {len(fn.callers):3d} callers  "
              f"{fn.name}", file=out)
        p = prof.get(f)
        if p:
            print(f"                 {p[:100]}", file=out)


def _profiles():
    path = os.path.join(ROOT, "out", "rdis", "game.profiles.txt")
    out, addr = {}, None
    if not os.path.exists(path):
        return out
    for line in open(path):
        if line.startswith("0x"):
            addr = int(line.split()[0], 16)
        elif addr is not None and line.startswith("    "):
            out[addr] = line.strip()
            addr = None
    return out


def one(addr, out=sys.stdout):
    by, groups, owner, w = assign()
    fn = w.funcs.get(addr)
    if fn is None:
        print(f"{addr:#010x} is not a routine the walk found", file=out)
        return
    names = sorted(owner.get(addr, [])) or ["nothing in the frame"]
    print(f"{fn.name} ({addr:#010x}): {by.get(addr)}", file=out)
    d = globals().get("_DIST", {}).get(addr)
    if d:
        print(f"  {d[0]} calls from {d[1]}", file=out)
    print(f"  callers: "
          + ", ".join(syms.label_in("game", c) for c in fn.callers[:8]),
          file=out)


def document(path=None):
    path = path or os.path.join(ROOT, "MAP.md")
    import io
    by, groups, owner, w = assign()
    prof = _profiles()
    with open(path, "w") as fh:
        p = lambda *a: print(*a, file=fh)                           # noqa: E731
        p("# Where each routine belongs")
        p()
        p("Generated by `tools/subsys.py --doc`. Every routine "
          "`tools/rdis.py`")
        p("reached, placed by which part of the frame it is reachable from.")
        p()
        p("`game_main` runs sixteen calls in a loop and `render_frame` is")
        p("twenty-two more; each is a root. A routine reached from exactly one")
        p("root belongs to it, one reached from several is **shared**, and one")
        p("reached from none is either dead or gets there through a pointer —")
        p("which is where the interrupt handlers and the level overlays'")
        p("targets are, so that group is worth reading rather than skipping.")
        p()
        p("| subsystem | routines | instructions | named |")
        p("| --- | --- | --- | --- |")
        rows = sorted(((sum(len(w.funcs[f].body) for f in fs), name, fs)
                       for name, fs in groups.items()), reverse=True)
        for ins, name, fs in rows:
            named = sum(1 for f in fs if w.funcs[f].named)
            p(f"| {name} | {len(fs)} | {ins} | {named} |")
        p()
        for ins, name, fs in rows:
            why = [w for n, _a, w in ROOTS + EXTRA if n == name and w]
            p(f"## {name}")
            p()
            if why:
                p("; ".join(why) + ".")
                p()
            p(f"{len(fs)} routines, {ins} instructions.")
            p()
            p("| address | instructions | callers | name | what it touches |")
            p("| --- | --- | --- | --- | --- |")
            for f in sorted(fs, key=lambda x: -len(w.funcs[x].body)):
                fn = w.funcs[f]
                pr = prof.get(f, "").replace("|", "/")
                p(f"| `{f:#010x}` | {len(fn.body)} | {len(fn.callers)} | "
                  f"{fn.name} | {pr[:120]} |")
            p()
    return path


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--doc":
        print("wrote " + os.path.relpath(document(), ROOT))
    elif a and a[0].startswith("0x"):
        one(int(a[0], 0))
    elif a:
        show(a[0])
    else:
        summary()

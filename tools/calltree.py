#!/usr/bin/env python3
"""Function discovery and the call graph, for any of the four executables.

The reverse engineering so far started from live RAM and worked outwards. This
starts from the entry point instead and walks down, which is the only way to
see the *order* things happen in -- what the shell does before the logo, what
the logo does before the menu, what the menu does before the game.

    python3 tools/calltree.py open                 what is in it
    python3 tools/calltree.py open entry -d 3      the tree from the entry point
    python3 tools/calltree.py open 0x80013a20      the tree from one routine
    python3 tools/calltree.py open 0x80013a20 -u   who calls it instead
    python3 tools/calltree.py open 0x80013a20 -s   its strings and constants
    python3 tools/calltree.py open 0x80011e14 -f   its skeleton: calls and branches
    python3 tools/calltree.py open --tables        pointer tables in the image

How functions are found, in the order they are trusted:

  * the entry point, out of the header;
  * every target of a `jal`, which is a call and cannot be anything else;
  * every word anywhere in the image that points at one of those, which finds
    the **dispatch tables** -- a state machine calls its states through one,
    so the intro's sequence of screens is a table and not a chain of calls;
  * words pointing at something that begins like a function and is never
    `jal`ed, kept separately as a guess, because a texture can hold any bytes.

A function's end is its last `jr $ra` before the next function starts. Nothing
here decides what a routine *is*; `-s` does, by showing the strings and the
addresses it forms, which is how the Sony library's own debug messages name it.
"""
import sys

sys.path.insert(0, "tools")
import mips  # noqa: E402

# The BIOS entry points. A call is `jal 0xa0` with the function number in $t1,
# loaded in the delay slot. Names are from nocash's psx-spx: external, not
# verified here, and only the ones this game actually uses are listed.
BIOS = {
    0xA0: {0x00: "FileOpen", 0x01: "FileSeek", 0x02: "FileRead", 0x03: "FileWrite",
           0x04: "FileClose", 0x06: "exit", 0x13: "SaveState", 0x17: "strcmp",
           0x18: "strncmp", 0x19: "strcpy", 0x1B: "strlen", 0x25: "toupper",
           0x27: "bcopy", 0x28: "bzero", 0x2A: "memcpy", 0x2B: "memset",
           0x2F: "rand", 0x30: "srand", 0x33: "malloc", 0x34: "free",
           0x39: "InitHeap", 0x3F: "printf", 0x40: "SystemErrorUnresolved",
           0x42: "Load", 0x43: "Exec", 0x44: "FlushCache", 0x45: "InitA0B0C0",
           0x49: "GPU_cw", 0x4E: "gpu_sync", 0x51: "LoadExec",
           0x70: "_bu_init", 0x71: "CdInit", 0x72: "CdRemove", 0x78: "CdAsyncSeekL",
           0x7C: "CdAsyncGetStatus", 0x7E: "CdAsyncReadSector",
           0x81: "CdAsyncSetMode", 0x95: "CdGetLbn", 0x96: "AddCDROMDevice",
           0x97: "AddMemCardDevice", 0x99: "AddDummyTtyDevice",
           0x9C: "SetConf", 0x9D: "GetConf", 0x9F: "SetMem", 0xA1: "SystemError",
           0xA2: "EnqueueCdIntr", 0xA3: "DequeueCdIntr"},
    0xB0: {0x00: "alloc_kernel_memory", 0x07: "DeliverEvent", 0x08: "OpenEvent",
           0x09: "CloseEvent", 0x0A: "WaitEvent", 0x0B: "TestEvent",
           0x0C: "EnableEvent", 0x0D: "DisableEvent", 0x12: "InitPad",
           0x13: "StartPad", 0x14: "StopPad", 0x15: "OutdatedPadInitAndStart",
           0x16: "OutdatedPadGetButtons", 0x17: "ReturnFromException",
           0x18: "SetDefaultExitFromException", 0x19: "HookEntryInt",
           0x20: "UnDeliverEvent", 0x32: "FileOpen", 0x33: "FileSeek",
           0x34: "FileRead", 0x35: "FileWrite", 0x36: "FileClose",
           0x3D: "putchar", 0x3F: "puts", 0x42: "firstfile", 0x43: "nextfile",
           0x44: "rename", 0x45: "erase", 0x47: "AddDrv", 0x48: "DelDrv",
           0x4A: "InitCard", 0x4B: "StartCard", 0x4C: "StopCard",
           0x4D: "_card_info", 0x4E: "_card_write", 0x4F: "_card_read",
           0x50: "_new_card", 0x56: "GetC0Table", 0x57: "GetB0Table",
           0x58: "_card_chan", 0x5B: "ChangeClearPad", 0x5C: "_card_status"},
    0xC0: {0x00: "EnqueueTimerAndVblankIrqs", 0x01: "EnqueueSyscallHandler",
           0x02: "SysEnqIntRP", 0x03: "SysDeqIntRP", 0x08: "SysInitMemory",
           0x0A: "ChangeClearRCnt", 0x0C: "InitDefInt", 0x12: "InstallDevices"},
}


def bios_at(exe, addr):
    """`("A0", 0x51, "LoadExec")` if this is a BIOS call, else None.

    The number is in the delay slot, which is easy to miss: the call reads
    `jal 0xa0 / li $t1, 0x51` and the second line is what says which call it is.
    """
    kind, f = exe.op(addr)
    if kind not in ("jal", "j") or f["target"] not in BIOS:
        return None
    tbl = f["target"]
    _k, d = exe.op(addr + 4)                       # the delay slot
    num = d.get("simm") if d.get("rt") == 9 and d.get("rs") == 0 else None
    if num is None:
        return (f"{tbl:#x}", None, f"{tbl:#04x}(?)")
    return (f"{tbl:#04x}", num & 0xFFFF,
            BIOS[tbl].get(num & 0xFFFF, f"{tbl:#04x}[{num:#x}]"))


def prologue(exe, addr):
    """Does this look like the top of a function?

    `addiu $sp, $sp, -n` is the usual one; leaf routines that touch no stack
    are missed on purpose rather than guessed at.
    """
    kind, f = exe.op(addr)
    if kind == "lo" and f.get("op") == 9 and f["rs"] == 29 and f["rt"] == 29:
        return f["simm"] < 0
    return False


class Graph:
    def __init__(self, exe):
        self.exe = exe
        self.called = set()          # jal targets: certainly functions
        self.jumped = set()
        self.tables = {}             # address of a word -> function it points at
        self.guessed = set()
        self._scan()
        self._bounds()
        # A `j` to something that begins like a function is a function: the
        # entry point of an overlay jumps to `main` rather than calling it, so
        # without this the largest routine in the image is missed entirely.
        # The prologue test is what keeps a routine's own internal `j` labels
        # out -- promoting those chopped `open_main` into eight pieces.
        extra = {t for t in self.jumped
                 if self.owner(t) is None and prologue(self.exe, t)}
        if extra:
            self.called |= extra
            self._bounds()
        self._edges()

    def _scan(self):
        e = self.exe
        a = e.base
        while a < e.end:
            kind, f = e.op(a)
            if kind == "jal" and f["target"] in e:
                self.called.add(f["target"])
            elif kind == "j" and f["target"] in e:
                self.jumped.add(f["target"])
            a += 4
        self.called.add(e.entry)
        # Words that point at a known function: dispatch tables.
        a = e.base
        while a < e.end:
            w = e.word(a)
            if w in self.called:
                self.tables[a] = w
            elif w is not None and w in e and w % 4 == 0 and prologue(e, w) \
                    and w not in self.called:
                self.guessed.add(w)
                self.tables[a] = w
            a += 4

    def _bounds(self):
        e = self.exe
        starts = sorted(self.called | self.guessed)
        self.starts = starts
        self.end_of = {}
        for i, s in enumerate(starts):
            limit = starts[i + 1] if i + 1 < len(starts) else e.end
            last = None
            a = s
            while a < limit:
                kind, f = e.op(a)
                if kind == "jr" and f["rs"] == 31:
                    last = a
                a += 4
            self.end_of[s] = (last + 8) if last is not None else limit

    def owner(self, addr):
        """The function an address falls inside, or None."""
        import bisect
        i = bisect.bisect_right(self.starts, addr) - 1
        if i < 0:
            return None
        s = self.starts[i]
        return s if addr < self.end_of[s] else None

    def _edges(self):
        e = self.exe
        self.out = {}
        self.indirect = {}
        self.bios = {}
        for s in self.starts:
            calls, ind, bio = [], [], []
            a = s
            while a < self.end_of[s]:
                b = bios_at(e, a)
                if b:
                    bio.append((a, b))
                    a += 4
                    continue
                kind, f = e.op(a)
                if kind == "jal" and f["target"] in e:
                    calls.append((a, f["target"]))
                elif kind == "j" and f["target"] in e and \
                        not (s <= f["target"] < self.end_of[s]):
                    calls.append((a, f["target"]))     # tail call
                elif kind == "jalr":
                    ind.append(a)
                a += 4
            self.out[s] = calls
            self.indirect[s] = ind
            self.bios[s] = bio
        self.into = {}
        for s, cs in self.out.items():
            for _a, t in cs:
                self.into.setdefault(t, []).append(s)


def tree(g, root, depth=3, out=sys.stdout, names=None, _seen=None, _pre=""):
    names = names or {}
    _seen = _seen if _seen is not None else set()
    if depth < 0:
        return
    kids = []
    for a, t in g.out.get(root, []):
        if not kids or kids[-1][1] != t:
            kids.append((a, t))
    nbios = g.bios.get(root, [])
    nind = g.indirect.get(root, [])
    for i, (site, t) in enumerate(kids):
        last = i == len(kids) - 1 and not nbios and not nind
        stem = "`-- " if last else "|-- "
        seen = t in _seen
        nm = names.get(t, f"{t:#010x}")
        print(f"{_pre}{stem}{nm}{'  ...' if seen and g.out.get(t) else ''}",
              file=out)
        if not seen:
            _seen.add(t)
            tree(g, t, depth - 1, out, names, _seen,
                 _pre + ("    " if last else "|   "))
    for i, (site, b) in enumerate(nbios):
        last = i == len(nbios) - 1 and not nind
        print(f"{_pre}{'`-- ' if last else '|-- '}<{b[2]}>", file=out)
    if nind:
        print(f"{_pre}`-- ({len(nind)} indirect call"
              f"{'s' if len(nind) > 1 else ''} through a register)", file=out)


def facts(exe, g, f):
    """The strings and formed addresses inside one routine.

    This is the naming instrument. The Sony library is linked in with its debug
    messages intact, so the routine that forms the address of `"DrawSync(%d)..."`
    is `DrawSync`, said by the code itself rather than guessed from shape.
    """
    res = mips.resolve(exe)
    out = []
    for a in range(f, g.end_of.get(f, f + 4), 4):
        v = res.get(a)
        if v is None:
            continue
        s = exe.string(v) if v in exe else None
        out.append((a, v, s))
    return out


ARGREG = {4: "a0", 5: "a1", 6: "a2", 7: "a3"}


def flow(exe, g, f, names=None, out=sys.stdout):
    """A routine with everything but its shape taken out.

    Calls with the constants going into them, branches with their targets, and
    every absolute address touched. `open_main` is four hundred instructions of
    which about sixty say what the opening actually does, and this prints those
    sixty. What it does not do is track a value through a register for more
    than the instruction that sets it -- an argument that arrives in `$s0` from
    somewhere earlier prints as `?`, deliberately, rather than as a guess.
    """
    names = names or {}
    res = mips.resolve(exe)
    end = g.end_of.get(f)
    if end is None:
        return
    labels = {}
    a = f
    while a < end:                                  # branch targets, for labels
        kind, d = exe.op(a)
        if kind in ("branch", "j") and f <= d.get("target", 0) < end:
            labels.setdefault(d["target"], f"L{len(labels) + 1}")
        a += 4

    args = {}

    def track(addr):
        """Follow constants into $a0..$a3, and forget anything else put there.

        A stale argument is worse than no argument: the first version of this
        carried `a0=3` down four calls that never set it, which reads as a
        finding and is not one. Anything that is not a constant prints `?`.
        """
        w = exe.word(addr)
        if w is None:
            return
        kind, d = exe.op(addr)
        dst = mips.dest(w)
        if kind == "lo" and d.get("op") in (9, 13) and d["rs"] == 0:
            if d["rt"] in ARGREG:
                args[d["rt"]] = d["simm"] & 0xFFFF
            return
        if (w >> 26) == 0 and (w & 0x3F) in (0x21, 0x25) and dst in ARGREG:
            rs, rt = (w >> 21) & 31, (w >> 16) & 31
            args[dst] = 0 if rs == 0 and rt == 0 else "?"
            return
        if dst in ARGREG:
            args[dst] = "?"

    a = f
    while a < end:
        kind, d = exe.op(a)
        if a in labels:
            print(f"{labels[a]}:", file=out)
        pre = f"  {a:#010x}  "
        if a in res and kind == "lo":
            v = res[a]
            st = exe.string(v) if v in exe else None
            nm = names.get(v)
            print(pre + f"[{v:#010x}]" + (f'  "{st}"' if st else "")
                  + (f"  {nm}" if nm else ""), file=out)
        if kind == "jal" or (kind == "j" and not (f <= d["target"] < end)):
            b = bios_at(exe, a)
            t = d["target"]
            track(a + 4)                            # the delay slot runs first
            shown = ", ".join(
                f"{ARGREG[r]}=" + (args[r] if args[r] == "?" else f"{args[r]:#x}")
                for r in sorted(args) if r in ARGREG)
            nm = f"<{b[2]}>" if b else names.get(t, f"{t:#010x}")
            print(pre + ("tail " if kind == "j" else "") + f"{nm}({shown})",
                  file=out)
            args.clear()
            a += 8
            continue
        if kind == "jalr":
            print(pre + "call through a register", file=out)
            args.clear()
        elif kind in ("branch", "j"):
            t = d.get("target")
            print(pre + f"-> {labels.get(t, f'{t:#010x}')}", file=out)
        elif kind == "jr":
            print(pre + "return", file=out)
        track(a)
        a += 4


def summary(exe, g):
    print(f"{exe.path}  base={exe.base:#010x} entry={exe.entry:#010x} "
          f"size={exe.size:#x}")
    print(f"  {len(g.called)} functions reached by a call, "
          f"{len(g.guessed)} more only through a pointer, "
          f"{len(g.tables)} pointer words")
    runs, cur = [], []
    for a in sorted(g.tables):
        if cur and a == cur[-1] + 4:
            cur.append(a)
        else:
            if len(cur) >= 3:
                runs.append(cur)
            cur = [a]
    if len(cur) >= 3:
        runs.append(cur)
    print(f"  {len(runs)} runs of three or more consecutive pointers "
          f"(dispatch tables):")
    for r in sorted(runs, key=len, reverse=True)[:12]:
        print(f"    {r[0]:#010x} .. {r[-1]:#010x}  {len(r)} entries")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    which = args.pop(0) if args else "game"
    exe = mips.load(which)
    g = Graph(exe)
    depth = 3
    if "-d" in args:
        i = args.index("-d")
        depth = int(args[i + 1])
        del args[i:i + 2]
    flags = {a for a in args if a.startswith("-")}
    rest = [a for a in args if not a.startswith("-")]
    try:
        import syms
        names = {a: syms.label_in(which, a) for a in g.starts}
    except Exception:
        names = {}
    if "--tables" in flags:
        for a in sorted(g.tables):
            print(f"{a:#010x}  ->  {names.get(g.tables[a], f'{g.tables[a]:#010x}')}")
    elif not rest:
        summary(exe, g)
    else:
        root = exe.entry if rest[0] == "entry" else int(rest[0], 0)
        if "-u" in flags:
            for c in sorted(g.into.get(root, [])):
                sites = [a for a, t in g.out[c] if t == root]
                print(f"{names.get(c, f'{c:#010x}'):32s} at "
                      + ", ".join(f"{s:#x}" for s in sites))
        elif "-f" in flags:
            print(names.get(root, f"{root:#010x}"))
            flow(exe, g, root, names)
        elif "-s" in flags:
            for a, v, s in facts(exe, g, root):
                print(f"  {a:#010x}  {v:#010x}"
                      + (f'  "{s}"' if s else "")
                      + (f"  {names[v]}" if v in names else ""))
        else:
            print(names.get(root, f"{root:#010x}"))
            tree(g, root, depth, names=names)

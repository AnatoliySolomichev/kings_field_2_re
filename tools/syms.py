#!/usr/bin/env python3
"""Names for the addresses we have pinned down.

Every finding in FORMATS.md ends up as a bare hex address, which makes both the
notes and the tool output hard to read back. `data/symbols.json` is the single
place those names live; this module loads it and annotates text or listings.

    python3 tools/syms.py                     list what is named
    python3 tools/syms.py 0x8005d7bc          look one up
    python3 tools/syms.py open 0x80013a20     ... in OPEN.EXE's table
    ... | python3 tools/syms.py -             annotate a stream of output

Four executables share one load address, so every table is per executable:
`game` is `data/symbols.json`, and `open`, `boot` and `end` are their own
files. Without a name in front, `game` is meant -- everything written before
the boot chain was read assumes it.
"""
import json
import os
import re
import sys

SYMBOLS = os.path.join(os.path.dirname(__file__), "..", "data", "symbols.json")
ADDR = re.compile(r"\b0x80[0-9a-fA-F]{6}\b")

# The disc has four executables and three of them load at the same address, so
# an address alone does not name code: `0x80013a20` is one routine in OPEN.EXE
# and a different one in GAME.EXE. Each therefore gets its own table, and
# `data/symbols.json` -- the one everything written before this existed reads --
# is GAME.EXE's.
FILES = {"game": "symbols.json", "open": "symbols_open.json",
         "boot": "symbols_boot.json", "end": "symbols_end.json"}


def load(path=SYMBOLS):
    raw = json.load(open(path))
    return {int(k, 16): v for k, v in raw.items() if not k.startswith("_")}


_TABLE = None
_TABLES = {}


def table(exe="game"):
    """The address book for one executable, `{address: entry}`."""
    if exe not in _TABLES:
        path = os.path.join(os.path.dirname(__file__), "..", "data",
                            FILES.get(exe, exe))
        _TABLES[exe] = load(path) if os.path.exists(path) else {}
    return _TABLES[exe]


def label_in(exe, addr):
    """`label`, but in a named executable's table."""
    t = table(exe)
    if addr in t:
        return t[addr]["name"]
    for a, e in t.items():
        if "size" in e and a <= addr < a + e["size"]:
            return f"{e['name']}+{addr - a:#x}"
    return f"{addr:#010x}"


def name_in(exe, addr, default=None):
    e = table(exe).get(addr)
    return e["name"] if e else (f"{addr:#010x}" if default is None else default)


def name(addr, default=None):
    """The name for an address, or `default` (its hex, unless you say otherwise)."""
    global _TABLE
    if _TABLE is None:
        _TABLE = load()
    e = _TABLE.get(addr)
    return e["name"] if e else (f"{addr:#010x}" if default is None else default)


def enclosing(addr):
    """The named routine this address falls inside, with the offset, or None.

    Only routines that carry a `size` can answer, and only within it. Guessing
    from "nearest name below" is worse than useless here: it labelled two
    separate functions as offsets into unrelated neighbours, which reads as a
    fact and is not one.
    """
    global _TABLE
    if _TABLE is None:
        _TABLE = load()
    for a, e in _TABLE.items():
        if "size" in e and a <= addr < a + e["size"]:
            return e["name"], addr - a
    return None


def label(addr):
    """`name` when it is exact, `name+0xNN` inside a routine of known size."""
    global _TABLE
    if _TABLE is None:
        _TABLE = load()
    if addr in _TABLE:
        return _TABLE[addr]["name"]
    got = enclosing(addr)
    return f"{got[0]}+{got[1]:#x}" if got else f"{addr:#010x}"


def annotate(text, exact_only=False):
    """Append names to every address in a block of text."""
    def sub(m):
        a = int(m.group(0), 16)
        nm = name(a, "") if exact_only else label(a)
        return m.group(0) if not nm or nm == m.group(0) else f"{m.group(0)}({nm})"
    return ADDR.sub(sub, text)


if __name__ == "__main__":
    args = sys.argv[1:]
    exe = "game"
    if args and args[0] in FILES:
        exe = args.pop(0)
        globals()["_TABLE"] = table(exe)
    if args == ["-"]:
        sys.stdout.write(annotate(sys.stdin.read()))
    elif args:
        for a in args:
            addr = int(a, 16)
            print(f"{addr:#010x}  {label(addr)}")
            e = table(exe).get(addr)
            if e:
                print(f"            {e['kind']}: {e['evidence']}")
    else:
        t = table(exe)
        for kind in ("code", "data"):
            print(f"=== {kind} ===")
            for a in sorted(k for k, v in t.items() if v["kind"] == kind):
                print(f"  {a:#010x}  {t[a]['name']:24s} {t[a]['evidence']}")

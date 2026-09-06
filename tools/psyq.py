#!/usr/bin/env python3
"""Name the Sony library inside an executable, using the library's own words.

King's Field II ships the PSY-Q libraries with their debug messages intact:
`ResetGraph(%d)...`, `DrawSync(%d)...`, `CD_read`, `CdInit: Init failed`. Each
of those strings is formed inside the very function it describes, so the
function that builds the address of `"PutDrawEnv(%08x)..."` **is** PutDrawEnv.
That is a reading off the code, not a guess from shape, and it is the cheapest
way to make the rest of the call graph legible: once the four hundred library
routines carry names, what is left standing is the game.

    python3 tools/psyq.py open              what it can name
    python3 tools/psyq.py open --write      put those names in the symbol table

What it cannot do: name a library function the game never calls, since an
uncalled routine is never a `jal` target and so has no boundary of its own. A
few of those get folded into a neighbour, and the tool says so rather than
attaching the name to whatever it landed in.
"""
import json
import os
import re
import sys

sys.path.insert(0, "tools")
import calltree  # noqa: E402
import mips      # noqa: E402

# string seen in the image -> the routine that prints it. Everything here is a
# message the library writes about itself; nothing is inferred from behaviour.
MESSAGES = [
    (r"^ResetGraph:jtb", "ResetGraph"),
    (r"^ResetGraph\(%d\)", "ResetGraph"),
    (r"^SetGraphReverse", "SetGraphReverse"),
    (r"^SetGraphDebug", "SetGraphDebug"),
    (r"^SetGrapQue", "SetGraphQueue"),
    (r"^DrawSyncCallback", "DrawSyncCallback"),
    (r"^SetDispMask", "SetDispMask"),
    (r"^DrawSync\(", "DrawSync"),
    (r"^ClearImage$", "ClearImage"),
    (r"^LoadImage$", "LoadImage"),
    (r"^StoreImage$", "StoreImage"),
    (r"^MoveImage$", "MoveImage"),
    (r"^ClearOTag\(", "ClearOTag"),
    (r"^ClearOTagR\(", "ClearOTagR"),
    (r"^DrawOTag\(", "DrawOTag"),
    (r"^PutDrawEnv\(", "PutDrawEnv"),
    (r"^PutDispEnv\(", "PutDispEnv"),
    (r"^GPU timeout", "gpu_timeout_report"),
    (r"^CdInit: Init failed", "CdInit"),
    (r"^CD_init:", "CD_init"),
    (r"^CD_sync$", "CD_sync"),
    (r"^CD_ready$", "CD_ready"),
    (r"^CD_cw$", "CD_cw"),
    (r"^CD_read$", "CD_read"),
    (r"^CD_datasync$", "CD_datasync"),
    (r"^CD read retry", "CD_read_retry"),
    (r"^DiskError: ", "cd_interrupt_callback"),
    (r"^CD001$", "cd_read_directory"),
    # "CdSearchFile error  FileName=%s" is NOT one of these: it is the game's
    # own message, printed by the routine that called CdSearchFile and found it
    # failed. Matching on it named `archive_open` as the library function it
    # calls, which the symbol table's existing entry caught.
    (r"^MDEC_in_sync$", "DecDCTinSync"),
    (r"^MDEC_out_sync$", "DecDCToutSync"),
    (r"^MDEC_rest:bad option", "DecDCTReset"),
    (r"^MDEC_vlec: invalid", "DecDCTvlc"),
]

STR = re.compile(rb"[\x20-\x7e\n\r\t]{4,}\x00")


def strings(exe):
    """Every NUL-terminated string in the image, by address."""
    out = {}
    for m in STR.finditer(exe.text):
        out[exe.base + m.start()] = m.group(0)[:-1].decode("latin-1")
    return out


def pieces(exe, start, end):
    """Split a stretch of code at every `jr $ra`, and return the pieces.

    A library routine nothing calls is never a `jal` target, so it has no
    boundary of its own and the graph folds it into the routine before it --
    which is how `ResetGraph` and `SetGraphReverse` came back as one function
    that prints both their messages. Every `jr $ra` ends something, so cutting
    there separates them again. It over-cuts a routine with two returns; that
    only matters if a message then lands in a piece with no start of its own,
    and the caller checks for exactly that.
    """
    out, cur = [], start
    a = start
    while a < end:
        kind, f = exe.op(a)
        if kind == "jr" and f["rs"] == 31:
            out.append((cur, a + 8))
            cur = a + 8
        a += 4
    if cur < end:
        out.append((cur, end))
    return out


def named(nick):
    """`{address: (name, evidence)}` for everything the messages can name."""
    exe = mips.load(nick)
    g = calltree.Graph(exe)
    strs = strings(exe)
    res = mips.resolve(exe)
    found, clashes = {}, {}
    for site, v in sorted(res.items()):
        s = strs.get(v)
        if s is None:
            continue
        for pat, name in MESSAGES:
            if not re.search(pat, s):
                continue
            f = g.owner(site)
            if f is None:
                continue
            for lo, hi in pieces(exe, f, g.end_of[f]):
                if lo <= site < hi:
                    f = lo
                    break
            if f in found and found[f][0] != name:
                clashes.setdefault(f, {found[f][0]}).add(name)
            found[f] = (name, f'forms the address of "{s.strip()}", '
                              f"which is that routine's own debug message")
    for f in clashes:                       # a boundary swallowed its neighbour
        found.pop(f, None)
    return exe, g, found, clashes


def main(nick, write=False):
    exe, _g, found, clashes = named(nick)
    for f in sorted(found):
        print(f"  {f:#010x}  {found[f][0]}")
    print(f"{len(found)} routines named in {exe.path}")
    for f, names in sorted(clashes.items()):
        print(f"  {f:#010x} left unnamed: {', '.join(sorted(names))} all print "
              f"from inside it, so its boundary covers more than one routine")
    if not write:
        return
    import syms
    path = os.path.join(mips.ROOT, "data", syms.FILES[nick])
    raw = json.load(open(path))
    for f, (name, why) in found.items():
        key = f"{f:#010x}"
        if key in raw and raw[key].get("name") != name:
            print(f"  keeping the existing name for {key}: {raw[key]['name']}")
            continue
        raw[key] = {"name": name, "kind": "code", "evidence": why}
    json.dump(raw, open(path, "w"), indent=1)
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "open", "--write" in sys.argv)

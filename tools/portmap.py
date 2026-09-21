#!/usr/bin/env python3
"""What in the port corresponds to what in the game, and what is still missing.

    python3 tools/portmap.py              the coverage, in one screen
    python3 tools/portmap.py --doc        regenerate PORT.md
    python3 tools/portmap.py --next       what to port next, and why that
    python3 tools/portmap.py 0x8002ed60   what the port does with one routine
    python3 tools/portmap.py --check      every marker resolves; exit 1 if not

The port and the original drifted apart in the obvious way: `godot/player.gd`
opens with forty lines of prose saying it came from `player_vertical` at
`0x8002ed60`, which is exactly right and which no tool can read. So the
correspondence is written in a form both sides can carry.

**In the GDScript**, a marker comment above the thing it corresponds to:

    # @orig game:0x8002ed60 player_vertical
    func vertical_step(y: int, surface: int) -> int:

and, where one line is worth pinning on its own:

        y = surface            # @orig game:0x8002ee1c

**In the listing**, the same pairing comes back the other way: every routine
`tools/rdis.py` prints carries a `; port:` line naming the file and the
function, so reading the MIPS tells you where its copy lives.

The marker says *which executable* as well as which address, and that is not
decoration: three of the four programs on the disc load at `0x80011000`, so
`0x80013a20` names one routine in OPEN.EXE and a different one in GAME.EXE.

A marker is a claim that the port reproduces that routine. It is not a claim
that it reproduces it correctly -- `--check` only verifies that the address
exists and is the start of a routine the walk found. What makes a port right is
a recording it agrees with, which is what `tools/movement.py`, `tools/replay.py`
and `tools/collision.py` are for, and `status` in the marker says which of those
has been done:

    # @orig game:0x8002ed60 player_vertical  status:verified 48/48 bp15
    # @orig game:0x8002e3f8 player_horizontal  status:transcribed
    # @orig game:0x8002fe1c player_turn  status:guessed
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips                                                          # noqa: E402
import syms                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GODOT = os.path.join(ROOT, "godot")
MAP = os.path.join(ROOT, "data", "portmap.json")
DB = os.path.join(ROOT, "out", "rdis")

MARK = re.compile(
    r"#\s*@orig\s+(?P<exe>boot|open|game|end):(?P<addr>0x[0-9a-fA-F]+)"
    # The name must not swallow `status:`. `[\w+]*` stops at the colon, so
    # "status" read as a routine name and the port's own file reported itself
    # broken. The lookahead is the fix and it is cheaper than it looks.
    r"(?:\s+(?!status:)(?P<name>[A-Za-z_][\w+]*))?"
    r"(?:\s+status:(?P<status>\w+))?(?P<rest>[^\n]*)")

STATUS = {
    "verified": "checked against a recording of the game, with a count",
    "transcribed": "read off the MIPS, not yet checked against the game",
    "partial": "part of the routine only",
    "guessed": "neither read nor checked -- a placeholder",
}


def markers(path=GODOT):
    """Every `@orig` in the port, with where it is."""
    out = []
    for fn in sorted(os.listdir(path)):
        if not fn.endswith(".gd"):
            continue
        full = os.path.join(path, fn)
        lines = open(full).read().splitlines()
        for n, line in enumerate(lines):
            m = MARK.search(line)
            if not m:
                continue
            # What it marks: the next `func` if the marker is on its own line,
            # otherwise the line it sits on.
            what = line.split("#")[0].strip()
            if not what:
                for k in range(n + 1, min(n + 4, len(lines))):
                    s = lines[k].strip()
                    if s.startswith(("func ", "const ", "var ", "class ")):
                        what = s.split("(")[0].split(":=")[0].strip()
                        break
            out.append({
                "file": f"godot/{fn}", "line": n + 1,
                "exe": m.group("exe"), "addr": int(m.group("addr"), 16),
                "name": m.group("name") or "",
                "status": m.group("status") or "transcribed",
                "note": (m.group("rest") or "").strip(),
                "what": what or "(the file)",
            })
    return out


def database(nick):
    p = os.path.join(DB, f"{nick}.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def check(out=sys.stdout):
    """Does every marker name a routine the walk actually found?"""
    bad = 0
    dbs = {}
    for m in markers():
        db = dbs.setdefault(m["exe"], database(m["exe"]))
        if db is None:
            print(f"{m['file']}:{m['line']}: no walk of {m['exe']} yet -- "
                  f"run tools/rdis.py {m['exe']} --build", file=out)
            bad += 1
            continue
        key = f"{m['addr']:#010x}"
        fn = db["functions"].get(key)
        if fn is None:
            # A marker may point *inside* a routine, and often should: the
            # death branch of `actor_tick` and `player_bob` are labels, and the
            # port has a function for each. What is broken is an address no
            # routine reaches at all.
            inside = [g for g in db["functions"].values()
                      if g["start"] <= m["addr"] < g["end"]]
            if not inside:
                print(f"{m['file']}:{m['line']}: {m['exe']}:{key} is in no "
                      f"routine the walk reached", file=out)
                bad += 1
            continue
        real = syms.name_in(m["exe"], m["addr"], "")
        if m["name"] and real and m["name"] != real:
            print(f"{m['file']}:{m['line']}: calls {key} {m['name']}, "
                  f"the symbol table calls it {real}", file=out)
            bad += 1
        if m["status"] not in STATUS:
            print(f"{m['file']}:{m['line']}: status:{m['status']} is not one of "
                  + ", ".join(STATUS), file=out)
            bad += 1
    return bad


def by_address():
    """`{"game:0x8002ed60": "godot/player.gd vertical_step"}`, for the listings."""
    out = {}
    for m in markers():
        k = f"{m['exe']}:{m['addr']:#010x}"
        out.setdefault(k, []).append(f"{m['file']}:{m['line']} {m['what']}")
    return {k: "  ".join(v) for k, v in out.items()}


def coverage():
    """How much of what the game spends its time in has a copy in the port."""
    rows = {}
    marked = {}
    for m in markers():
        marked.setdefault(m["exe"], {}).setdefault(m["addr"], []).append(m)
    for nick in ("boot", "open", "game", "end"):
        db = database(nick)
        if db is None:
            continue
        fns = db["functions"]
        done = marked.get(nick, {})
        ins_total = sum(f["insns"] for f in fns.values())
        # Only a marker on a routine's *start* claims the routine. One pointing
        # at a label inside it claims a part, and counting the whole routine for
        # it would overstate the coverage by the size of whatever it sits in --
        # `player_bob` would bring all 368 instructions of `player_vertical`.
        whole = {a for a in done if f"{a:#010x}" in fns}
        ins_done = sum(f["insns"] for k, f in fns.items() if f["start"] in whole)
        rows[nick] = {
            "routines": len(fns), "ported": len(whole),
            "parts": len(done) - len(whole),
            "insns": ins_total, "insns_ported": ins_done,
            "named": sum(1 for f in fns.values() if f["named"]),
        }
    return rows, marked


# Routines the port does not need, because the engine already is them. The
# Sony library, the CD reader, the memory card and the GPU queue are all
# things Godot provides, and leaving them in the ranking buries the game under
# them: the first eight entries were DrawSync and its neighbours.
LIBRARY = ("frame_", "pad_", "Draw", "Put", "Set", "Clear", "Load", "Store", "Move", "Reset",
           "Cd", "CD_", "Dec", "Pad", "card_", "gpu_", "cd_", "mem", "str",
           "malloc", "free", "heap", "rand", "printf", "puts", "Sqrt", "Sin",
           "Cos", "Matrix", "Vector", "Rot", "Trans", "Scale", "Apply")


def _is_library(name):
    return any(name.startswith(p) for p in LIBRARY)


def nxt(out=sys.stdout, limit=25, everything=False):
    """What to port next: reached often, big enough to matter, not done.

    Ranked by callers first. A routine ten other routines call is load-bearing
    whatever its size, and a routine nothing calls is either dead or reached
    through a table -- both worth knowing before spending a day on it.

    The Sony library and the routines that talk to hardware are left out unless
    asked for. The port does not reimplement `DrawSync`; Godot is what
    `DrawSync` was for, and with those in the list the first eight entries were
    the GPU queue rather than the game.
    """
    db = database("game")
    if db is None:
        print("no walk of game yet -- run tools/rdis.py game --build", file=out)
        return
    _rows, marked = coverage()
    done = marked.get("game", {})
    prof = _profiles("game")
    cand, skipped = [], 0
    for k, f in db["functions"].items():
        if f["start"] in done or f["insns"] < 12:
            continue
        p = prof.get(f["start"], "")
        if not everything and (_is_library(f["name"]) or "talks to " in p
                               or "BIOS " in p):
            skipped += 1
            continue
        cand.append((len(f["callers"]), f["insns"], f["start"], f, p))
    print(f"{len(cand)} routines in GAME.EXE with no marker in the port"
          + (f" ({skipped} library or hardware routines left out)"
             if skipped else ""), file=out)
    print("  callers  insns  address     name", file=out)
    for c, n, a, f, p in sorted(cand, reverse=True)[:limit]:
        print(f"  {c:7d}  {n:5d}  {a:#010x}  {f['name']}", file=out)
        if p:
            print(f"                                  {p[:96]}", file=out)


def _profiles(nick):
    """The one-line profiles tools/rdis.py --describe wrote, by address."""
    path = os.path.join(DB, f"{nick}.profiles.txt")
    out = {}
    if not os.path.exists(path):
        return out
    addr = None
    for line in open(path):
        if line.startswith("0x"):
            addr = int(line.split()[0], 16)
        elif addr is not None and line.startswith("    "):
            out[addr] = line.strip()
            addr = None
    return out


def report(addr, out=sys.stdout):
    hits = [m for m in markers() if m["addr"] == addr]
    print(f"{addr:#010x}  {syms.label_in('game', addr)}", file=out)
    if not hits:
        print("  nothing in the port claims this routine", file=out)
        return
    for m in hits:
        print(f"  {m['file']}:{m['line']}  {m['what']}", file=out)
        print(f"    status: {m['status']} -- {STATUS.get(m['status'], '?')}",
              file=out)
        if m["note"]:
            print(f"    {m['note']}", file=out)


def document(path=None):
    """PORT.md: the two codebases side by side."""
    path = path or os.path.join(ROOT, "PORT.md")
    rows, marked = coverage()
    ms = markers()
    with open(path, "w") as fh:
        p = lambda *a: print(*a, file=fh)                          # noqa: E731
        p("# The port, against the game")
        p()
        p("Generated by `tools/portmap.py --doc`. Do not edit it: the markers")
        p("are in the GDScript itself, which is the only place they can stay")
        p("true when the code moves.")
        p()
        p("A marker above a function in `godot/` says which routine of which")
        p("executable it corresponds to:")
        p()
        p("```gdscript")
        p("# @orig game:0x8002ed60 player_vertical  status:verified 48/48 bp15")
        p("func vertical_step(y: int, surface: int) -> int:")
        p("```")
        p()
        p("and `tools/rdis.py game 0x8002ed60` prints the same pairing from the")
        p("other side, as a `; port:` line at the top of the listing.")
        p()
        p("**A marker is a claim that the port reproduces that routine, not")
        p("that it reproduces it correctly.** `status` says how far that went:")
        p()
        for k, v in STATUS.items():
            p(f"* **{k}** — {v}")
        p()
        p("## How much is covered")
        p()
        p("| executable | routines | with a marker | labels marked | "
          "instructions | covered |")
        p("| --- | --- | --- | --- | --- | --- |")
        for nick, r in rows.items():
            pct = 100 * r["insns_ported"] // max(r["insns"], 1)
            p(f"| {nick} | {r['routines']} | {r['ported']} | {r['parts']} | "
              f"{r['insns']} | {r['insns_ported']} ({pct}%) |")
        p()
        p("Those percentages are of *all* the code in the image, which includes")
        p("the Sony library, the CD reader and the memory card. They are a")
        p("floor, not a score.")
        p()
        p("## Every marker")
        p()
        p("| in the port | what it is | in the game | status |")
        p("| --- | --- | --- | --- |")
        for m in sorted(ms, key=lambda m: (m["exe"], m["addr"])):
            nm = m["name"] or syms.label_in(m["exe"], m["addr"])
            p(f"| [`{m['file']}:{m['line']}`]({m['file']}#L{m['line']}) | "
              f"`{m['what']}` | `{m['exe']}:{m['addr']:#010x}` {nm} | "
              f"{m['status']} |")
        p()
        p("## What is not covered, in the order worth doing")
        p()
        p("Ranked by how many routines call it. A routine ten others call is")
        p("load-bearing whatever its size.")
        p()
        p("| callers | instructions | address | name |")
        p("| --- | --- | --- | --- |")
        import io
        buf = io.StringIO()
        nxt(buf, limit=30)
        for line in buf.getvalue().splitlines()[2:]:
            if not line.startswith("  0x") and not line[:9].strip().isdigit():
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            c, n, a, *rest = parts
            p(f"| {c} | {n} | `{a}` | {' '.join(rest)} |")
        p()
    return path


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        rows, marked = coverage()
        ms = markers()
        print(f"{len(ms)} markers in {len({m['file'] for m in ms})} files")
        for nick, r in rows.items():
            pct = 100 * r["insns_ported"] // max(r["insns"], 1)
            print(f"  {nick:5s} {r['ported']:3d} of {r['routines']:4d} routines "
                  f"marked"
                  + (f" and {r['parts']} label{'s' if r['parts'] > 1 else ''} "
                     "inside them" if r["parts"] else "")
                  + f", {r['insns_ported']:6d} of {r['insns']:6d} "
                  f"instructions ({pct}%)")
        bad = check()
        print(f"{'every marker resolves' if not bad else str(bad) + ' broken'}")
    elif argv[0] == "--check":
        sys.exit(1 if check() else 0)
    elif argv[0] == "--doc":
        print(f"wrote {os.path.relpath(document(), ROOT)}")
    elif argv[0] == "--next":
        nxt()
    else:
        report(int(argv[0], 0))

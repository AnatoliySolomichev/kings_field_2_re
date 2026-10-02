#!/usr/bin/env python3
"""What in the port corresponds to what in the game, and what is still missing.

    python3 tools/portmap.py                    the coverage, in one screen
    python3 tools/portmap.py --check            every rule below; exit 1 if not
    python3 tools/portmap.py --doc              regenerate PORT.md
    python3 tools/portmap.py --next             what to port next, and why that
    python3 tools/portmap.py game:0x8002ed60    the game's side: what the port
                                                does with that routine, and every
                                                line of the port that cites it
    python3 tools/portmap.py godot/ai.gd:213    the port's side: what in the game
    python3 tools/portmap.py godot/ai.gd:turn   one function of the port is

A bare address in the last form is taken as GAME.EXE's and said so.

The port and the original drifted apart in the obvious way: `godot/player.gd`
opened with forty lines of prose saying it came from `player_vertical` at
`0x8002ed60`, which was exactly right and which no tool could read. So the
correspondence is written in a form both sides can carry, and **the rule is
that it is written for every function, with no exceptions and no defaults**.

**Every `func` in `godot/` says what it is**, in the comment block directly
above it -- no blank line between -- with one of two markers:

    # @orig game:0x8002ed60 player_vertical  status:verified 48/48 bp15
    func vertical_step(y: int, surface: int) -> int:

    # @port engine -- builds the level's nodes; the game has no scene graph
    func _ready() -> void:

`@orig` says the function reproduces that code of that executable: a routine
by its first instruction, or a stretch inside one by the address that stretch
starts at. A function that folds two routines into one carries two lines; one
that carries a single `@orig` and also does something of the port's own says so
in the note. `@port` says the game has no counterpart, and says which kind of
the port's own code it is:

    engine   Godot's side: nodes, meshes, materials, input plumbing, timing
    data     reads what the tools wrote; the tool is where the game was read
    check    the self-test, the side-by-side comparison, the debug views
    helper   arithmetic the CPU did without being asked -- a 16-bit wrap, a
             sign extension, a truncating divide -- and small utilities

A function carries `@orig` lines or one `@port`, never both. A file that is all
the port's own -- the self-test, the viewer -- may say so once with
`# @port-file check` instead of on every function; an `@orig` on one of its
functions still wins.

**Inside a function**, a marker on its own comment line pins the stretch below
it and one at the end of a line pins that line:

        y = surface            # @orig game:0x8002ee1c player_vertical+0xbc  status:transcribed

**Every marker names what it points at, and the name is checked**: the symbol
table's name for that address, or `routine+0xoffset` inside a routine. Rename
a symbol and `--check` lists every marker that still says the old name.
`status` is not optional either:

    verified      checked against a recording of the game, with a count
    transcribed   read off the MIPS, not yet checked against the game
    partial       part of the routine only; the note says which part
    guessed       neither read nor checked -- a placeholder

**An address without an executable is not a fact.** Three of the four
programs on the disc load at `0x80011000`, so `0x80013a20` names one routine in
OPEN.EXE and a different one in GAME.EXE. A marker always says which. A plain
address in a comment -- `# 0x8004e928`, a constant's `# 0x8002f254` -- takes
the executable the file declares once in its header with `# @exe game`, and one
from another executable in the same file is written `open:0x80013a20`. A file
that cites an address and declares no executable fails `--check`. Those plain
addresses are read too, as citations: `game:0x8002f254` lists every line of the
port that cites it, and the listings print them against the instruction.

**In the listing**, the same pairing comes back the other way: every routine
`tools/rdis.py` and `tools/pseudo.py` print carries a `; port:` line naming the
file and the function, and a line for each stretch of it the port pins.

A marker is a claim that the port reproduces that code. It is not a claim that
it reproduces it correctly -- `--check` verifies that the address exists, that
the name is the one the symbol table gives it and that every function is
accounted for. What makes a port right is a recording it agrees with, which is
what `tools/movement.py`, `tools/replay.py` and `tools/collision.py` are for,
and `status` says which of those has been done.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import syms                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GODOT = os.path.join(ROOT, "godot")
DB = os.path.join(ROOT, "out", "rdis")
EXES = ("boot", "open", "game", "end")

MARK = re.compile(
    r"@orig\s+(?P<exe>\w+):(?P<addr>0x[0-9a-fA-F]+)"
    # The name must not swallow `status:`. `[\w+]*` stops at the colon, so
    # "status" read as a routine name and the port's own file reported itself
    # broken. The lookahead is the fix and it is cheaper than it looks.
    r"(?:\s+(?!status:)(?P<name>[A-Za-z_][\w+]*))?"
    r"(?:\s+status:(?P<status>\w+))?(?P<rest>[^\n]*)")
PORT = re.compile(r"@port(?!-)\s+(?P<kind>\w+)(?P<rest>[^\n]*)")
PORT_FILE = re.compile(r"@port-file\s+(?P<kind>\w+)(?P<rest>[^\n]*)")
EXE = re.compile(r"@exe\s+(?P<exe>\w+)")
# A RAM address, 0x80000000 to 0x801fffff, with or without its executable.
ADDR = re.compile(r"(?<![\w:])(?:(?P<exe>boot|open|game|end):)?"
                  r"(?P<addr>0x80[01][0-9a-fA-F]{5})(?![0-9a-fA-F])")
TOP = re.compile(r"^(?:(?P<static>static\s+)?func\s+(?P<func>\w+)"
                 r"|(?:@\w+(?:\([^)]*\))?\s+)*(?P<kind>const|var|signal|enum|"
                 r"class_name|extends|class)\b\s*(?P<name>\w*))")

STATUS = {
    "verified": "checked against a recording of the game, with a count",
    "transcribed": "read off the MIPS, not yet checked against the game",
    "partial": "part of the routine only; the note says which part",
    "guessed": "neither read nor checked -- a placeholder",
}
KINDS = {
    "engine": "Godot's side: nodes, meshes, materials, input plumbing, timing",
    "data": "reads what the tools wrote; the tool is where the game was read",
    "check": "the self-test, the side-by-side comparison, the debug views",
    "helper": "arithmetic the CPU did without being asked, small utilities",
}


# --- reading the port -----------------------------------------------------

def _comment(line):
    """The comment on a line of GDScript, or None. A `#` in a string is not one."""
    q = None
    i = 0
    while i < len(line):
        c = line[i]
        if q:
            if c == "\\":
                i += 1
            elif c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c == "#":
            return line[i + 1:]
        i += 1
    return None


def parse(full, rel=None):
    """One .gd file: its declarations, what each marker is attached to, and
    every address its comments cite.

    A top-level line (no indentation, not a comment) starts a declaration. The
    *header* of one is the run of column-0 comment lines directly above it,
    with no blank line between. A function's *body* runs from its `func` line
    to the line before the next declaration's header. A marker in a header
    belongs to that declaration, one in a body to that function at that line,
    and one anywhere else to nothing -- which `check` reports.
    """
    rel = rel or os.path.relpath(full, ROOT)
    lines = open(full).read().split("\n")
    top = [n for n, s in enumerate(lines)
           if s and not s[0].isspace() and not s.startswith("#")]
    items = []
    for k, n in enumerate(top):
        m = TOP.match(lines[n])
        h = n
        while h > 0 and lines[h - 1].startswith("#"):
            h -= 1
        if m and m.group("func"):
            kind, name = "func", m.group("func")
        elif m:
            kind, name = m.group("kind"), m.group("name")
        else:
            kind, name = "other", lines[n].split()[0]
        items.append({"kind": kind, "name": name, "line": n, "head": h,
                      "orig": [], "port": [], "parts": []})
    for k, it in enumerate(items):
        nxt = items[k + 1]["head"] if k + 1 < len(items) else len(lines)
        it["end"] = nxt                       # body: line .. end-1
    # Which declaration a line belongs to, and how.
    where = {}
    for it in items:
        for n in range(it["head"], it["line"]):
            where[n] = (it, "head")
        where[it["line"]] = (it, "decl")
        if it["kind"] == "func":
            for n in range(it["line"] + 1, it["end"]):
                if lines[n].strip() and not lines[n].startswith("#"):
                    where[n] = (it, "body")
                elif lines[n].startswith("#"):
                    # A column-0 comment inside a body is the body's, unless it
                    # is the header of what follows -- which `head` covers.
                    where.setdefault(n, (it, "body"))
    f = {"file": rel, "lines": lines, "items": items, "exe": None,
         "port_file": None, "loose": [], "cites": [], "markers": [],
         "errors": []}
    for n, s in enumerate(lines):
        c = _comment(s)
        if c is None:
            continue
        m = EXE.search(c)
        if m:
            f["exe"] = m.group("exe")
        m = PORT_FILE.search(c)
        if m:
            f["port_file"] = {"kind": m.group("kind"),
                              "note": m.group("rest").strip(" -"), "line": n}
            continue
        owner = where.get(n)
        m = mm = MARK.search(c)
        if m:
            mk = {"file": rel, "line": n + 1, "exe": m.group("exe"),
                  "addr": int(m.group("addr"), 16),
                  "name": m.group("name") or "",
                  "status": m.group("status") or "",
                  "note": (m.group("rest") or "").strip().lstrip("- ").strip(),
                  "item": owner[0] if owner else None,
                  "how": owner[1] if owner else None}
            mk["what"] = _what(mk)
            f["markers"].append(mk)
            if owner is None:
                f["loose"].append(mk)
            elif owner[1] in ("head", "decl"):
                owner[0]["orig"].append(mk)
            else:
                owner[0]["parts"].append(mk)
        m = PORT.search(c)
        if m:
            pk = {"kind": m.group("kind"), "line": n + 1,
                  "note": m.group("rest").strip().lstrip("- ").strip()}
            if owner and owner[1] in ("head", "decl") and owner[0]["kind"] == "func":
                owner[0]["port"].append(pk)
            else:
                f["errors"].append(f"{rel}:{n + 1}: @port is on no function -- "
                                   "it goes in the comment block directly above "
                                   "one")
        # Every address the comment cites, but for the marker's own.
        own = mm.start("exe") if mm else -1
        for a in ADDR.finditer(c):
            if a.start() == own:
                continue
            f["cites"].append({"file": rel, "line": n + 1,
                               "exe": a.group("exe"), "addr": int(a.group("addr"), 16),
                               "item": owner[0] if owner else None})
    for c in f["cites"]:
        c["exe"] = c["exe"] or f["exe"]
    return f


def _what(mk):
    it, how = mk["item"], mk["how"]
    if it is None:
        return "(nothing)"
    head = f"{'func' if it['kind'] == 'func' else it['kind']} {it['name']}"
    return head if how in ("head", "decl") else f"{head}, line {mk['line']}"


def files(path=GODOT):
    out = []
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".gd"):
            out.append(parse(os.path.join(path, fn), f"godot/{fn}"))
    return out


def markers(path=GODOT):
    """Every `@orig` in the port, with what it is attached to."""
    return [m for f in files(path) for m in f["markers"]]


# --- reading the game -----------------------------------------------------

_DBS = {}


def database(nick):
    if nick not in _DBS:
        p = os.path.join(DB, f"{nick}.json")
        _DBS[nick] = json.load(open(p)) if os.path.exists(p) else None
    return _DBS[nick]


def _routines(nick):
    db = database(nick)
    if db is None:
        return []
    if "_sorted" not in db:
        db["_sorted"] = sorted((f["start"], f["end"], f["name"])
                               for f in db["functions"].values())
    return db["_sorted"]


def routine_of(nick, addr):
    """(start, end, walk name) of the routine `addr` is in, or None."""
    for s, e, nm in _routines(nick):
        if s <= addr < e:
            return s, e, nm
    return None


def canonical(nick, addr):
    """The name a marker must use: the symbol table's, else the walk's, and
    `routine+0xoff` inside a routine. None if no routine reaches it."""
    t = syms.table(nick)
    if addr in t:
        return t[addr]["name"]
    r = routine_of(nick, addr)
    if r is None:
        return None
    s, _e, nm = r
    base = t[s]["name"] if s in t else nm
    return base if s == addr else f"{base}+{addr - s:#x}"


def describe(nick, addr):
    """`name  game:0x...  (in routine, start..end)` for a person."""
    r = routine_of(nick, addr)
    nm = canonical(nick, addr)
    if r is None:
        e = syms.table(nick).get(addr)
        return (f"{nick}:{addr:#010x}  " + (f"{e['name']} ({e.get('kind', '?')})"
                                             if e else "not code the walk reached"))
    s, e, _ = r
    whole = canonical(nick, s)
    if s == addr:
        return f"{nick}:{addr:#010x}  {nm}  ({(e - s) // 4} instructions, " \
               f"to {e:#010x})"
    return f"{nick}:{addr:#010x}  {nm}  (inside {whole}, {s:#010x}..{e:#010x})"


# --- the rules ------------------------------------------------------------

def problems(fs=None):
    """Everything that makes the correspondence ambiguous, one line each."""
    fs = fs if fs is not None else files()
    bad = []
    for f in fs:
        bad += f["errors"]
        for mk in f["loose"]:
            bad.append(f"{f['file']}:{mk['line']}: @orig {mk['exe']}:"
                       f"{mk['addr']:#010x} is attached to nothing -- put it in "
                       "the comment block directly above a function, or inside one")
        if f["port_file"] and f["port_file"]["kind"] not in KINDS:
            bad.append(f"{f['file']}:{f['port_file']['line'] + 1}: @port-file "
                       f"{f['port_file']['kind']} is not one of " + ", ".join(KINDS))
        if f["exe"] and f["exe"] not in EXES:
            bad.append(f"{f['file']}: @exe {f['exe']} is not one of " + ", ".join(EXES))
        for it in f["items"]:
            if it["kind"] != "func":
                continue
            at = f"{f['file']}:{it['line'] + 1}: func {it['name']}"
            if it["orig"] and it["port"]:
                bad.append(f"{at} is marked both @orig and @port -- it is one or "
                           "the other; say what is the port's own in the note")
            elif len(it["port"]) > 1:
                bad.append(f"{at} carries {len(it['port'])} @port lines")
            elif not it["orig"] and not it["port"] and not f["port_file"]:
                bad.append(f"{at} says nothing about what it is -- give it "
                           "@orig <exe>:<address> <name> status:<s>, or "
                           "@port <kind>")
            for pk in it["port"]:
                if pk["kind"] not in KINDS:
                    bad.append(f"{f['file']}:{pk['line']}: @port {pk['kind']} is "
                               "not one of " + ", ".join(KINDS))
                if not pk["note"]:
                    bad.append(f"{f['file']}:{pk['line']}: @port {pk['kind']} "
                               "says why in a note: `@port engine -- builds ...`")
        for mk in f["markers"]:
            at = f"{f['file']}:{mk['line']}"
            if mk["exe"] not in EXES:
                bad.append(f"{at}: {mk['exe']} is not an executable "
                           "(" + ", ".join(EXES) + ")")
                continue
            if database(mk["exe"]) is None:
                bad.append(f"{at}: no walk of {mk['exe']} yet -- run "
                           f"tools/rdis.py {mk['exe']} --build")
                continue
            want = canonical(mk["exe"], mk["addr"])
            if want is None:
                bad.append(f"{at}: {mk['exe']}:{mk['addr']:#010x} is in no "
                           "routine the walk reached")
                continue
            if mk["name"] != want:
                bad.append(f"{at}: {mk['exe']}:{mk['addr']:#010x} is "
                           f"{want}, the marker says "
                           f"{mk['name'] or 'nothing'}")
            it = mk["item"]
            if (it and it["kind"] != "func" and
                    f"{mk['addr']:#010x}" in database(mk["exe"])["functions"]):
                bad.append(f"{at}: {it['kind']} {it['name']} claims all of {want} "
                           "-- a routine is reproduced by a function; a constant "
                           "cites the instruction it was read off")
            if mk["status"] not in STATUS:
                bad.append(f"{at}: status:{mk['status'] or '(none)'} -- it is one "
                           "of " + ", ".join(STATUS))
        for c in f["cites"]:
            if c["exe"] is None:
                bad.append(f"{f['file']}:{c['line']}: {c['addr']:#010x} names no "
                           "executable -- declare the file's with `# @exe game` "
                           "in its header, or write game:0x...")
    return bad


def check(out=sys.stdout):
    bad = problems()
    for b in bad:
        print(b, file=out)
    return len(bad)


def tally(fs=None):
    fs = fs if fs is not None else files()
    n = {"files": len(fs), "funcs": 0, "orig": 0, "port": {}, "markers": 0,
         "parts": 0, "cites": 0}
    for f in fs:
        n["markers"] += len(f["markers"])
        n["cites"] += len(f["cites"])
        for it in f["items"]:
            if it["kind"] != "func":
                continue
            n["funcs"] += 1
            n["parts"] += len(it["parts"])
            if it["orig"]:
                n["orig"] += 1
            else:
                k = (it["port"][0]["kind"] if it["port"] else
                     f["port_file"]["kind"] if f["port_file"] else "?")
                n["port"][k] = n["port"].get(k, 0) + 1
    return n


# --- the two directions ---------------------------------------------------

def by_address():
    """`{"game:0x8002ed60": "godot/player.gd:1130 func _move"}`: what claims each
    address, for the listings' `; port:` line."""
    out = {}
    for m in markers():
        k = f"{m['exe']}:{m['addr']:#010x}"
        out.setdefault(k, []).append(f"{m['file']}:{m['line']} {m['what']}")
    return {k: "  ".join(v) for k, v in out.items()}


def cited_by_address():
    """`{"game:0x8002f254": ["godot/player.gd:81 const V_START"]}`: every plain
    address the port's comments cite, for the listings' instruction lines."""
    out = {}
    for f in files():
        for c in f["cites"]:
            if c["exe"] is None:
                continue
            it = c["item"]
            what = (f"{'func' if it['kind'] == 'func' else it['kind']} {it['name']}"
                    if it else "the file's notes")
            out.setdefault(f"{c['exe']}:{c['addr']:#010x}", []).append(
                f"{c['file']}:{c['line']} {what}")
    return out


def listing_index():
    """Both of the above in one read of the port, for a listing of every routine:
    `{"marks": by_address(), "cites": {key: "file:line what  file:line what"}}`."""
    return {"marks": by_address(),
            "cites": {k: "  ".join(v) for k, v in cited_by_address().items()}}


def listing_notes(index, nick, start, end):
    """What a listing of [start, end) prints from the port: the header's
    `port:` line for the routine, a line per stretch inside it the port pins,
    and, per address, what to append to that instruction."""
    marks = index.get("marks", index) if index else {}
    cites = index.get("cites", {}) if index else {}
    head = []
    p = marks.get(f"{nick}:{start:#010x}")
    if p:
        head.append(f"port: {p}")
    inline = {}
    for k, v in marks.items():
        exe, _, a = k.partition(":")
        a = int(a, 16)
        if exe == nick and start < a < end:
            head.append(f"port, from +{a - start:#x}: {v}")
            inline[a] = f"port: {v}"
    for k, v in cites.items():
        exe, _, a = k.partition(":")
        a = int(a, 16)
        if exe == nick and start <= a < end:
            inline[a] = (inline[a] + "; " if a in inline else "") + f"cited: {v}"
    n = sum(1 for k in cites if k.startswith(nick + ":")
            and start <= int(k.partition(":")[2], 16) < end)
    if n:
        head.append(f"cited by the port at {n} of its addresses")
    return head, inline


def report_address(nick, addr, out=sys.stdout):
    """The game's side: what the port does with this code."""
    p = lambda *a: print(*a, file=out)                              # noqa: E731
    p(describe(nick, addr))
    r = routine_of(nick, addr)
    lo, hi = (r[0], r[1]) if r else (addr, addr + 1)
    fs = files()
    ms = [m for f in fs for m in f["markers"] if m["exe"] == nick]
    claims = [m for m in ms if m["addr"] == lo]
    parts = [m for m in ms if lo < m["addr"] < hi]
    if not claims and not parts:
        p("  nothing in the port claims this routine")
    for m in claims:
        p(f"  {m['file']}:{m['line']}  {m['what']}")
        p(f"    status: {m['status']} -- {STATUS.get(m['status'], '?')}")
        if m["note"]:
            p(f"    {m['note']}")
    for m in sorted(parts, key=lambda m: m["addr"]):
        p(f"  +{m['addr'] - lo:#x} {m['name']}: {m['file']}:{m['line']}  "
          f"{m['what']}  ({m['status']})")
    cites = sorted(((c["addr"], c) for f in fs for c in f["cites"]
                    if c["exe"] == nick and lo <= c["addr"] < hi),
                   key=lambda t: (t[0], t[1]["file"], t[1]["line"]))
    if cites:
        p(f"  cited by the port, {len(cites)} time{'s' if len(cites) > 1 else ''}:")
        for a, c in cites:
            it = c["item"]
            what = f"{it['kind']} {it['name']}" if it else "the file's notes"
            mark = "  <--" if a == addr and a != lo else ""
            p(f"    {a:#010x}  {c['file']}:{c['line']}  {what}{mark}")


def report_port(spec, out=sys.stdout):
    """The port's side: what in the game one function of the port is."""
    p = lambda *a: print(*a, file=out)                              # noqa: E731
    path, _, what = spec.partition(":")
    f = next((f for f in files() if f["file"] == path
              or f["file"] == f"godot/{os.path.basename(path)}"), None)
    if f is None:
        p(f"{path}: not a file of the port")
        return 1
    if what.isdigit():
        n = int(what) - 1
        it = next((i for i in f["items"] if i["head"] <= n < max(i["end"], i["line"] + 1)), None)
    else:
        it = next((i for i in f["items"] if i["name"] == what), None)
    if it is None:
        p(f"{spec}: no declaration there")
        return 1
    p(f"{f['file']}:{it['line'] + 1}  {it['kind']} {it['name']}")
    for m in it["orig"]:
        p(f"  @orig  {describe(m['exe'], m['addr'])}")
        p(f"         status: {m['status']}" + (f" -- {m['note']}" if m["note"] else ""))
        p(f"         listing: python3 tools/rdis.py {m['exe']} {m['addr']:#010x}")
    for pk in it["port"]:
        p(f"  @port {pk['kind']} -- {pk['note']}")
    if not it["orig"] and not it["port"]:
        if f["port_file"]:
            p(f"  @port-file {f['port_file']['kind']} -- {f['port_file']['note']}")
        elif it["kind"] == "func":
            p("  NOT PLACED -- this function says nothing about what it is")
    for m in it["parts"]:
        p(f"  line {m['line']}: @orig {describe(m['exe'], m['addr'])}  ({m['status']})")
    cs = [c for c in f["cites"] if c["item"] is it]
    if cs:
        p(f"  addresses its comments cite:")
        for c in cs:
            p(f"    line {c['line']}: " + (describe(c["exe"], c["addr"]) if c["exe"]
                                          else f"{c['addr']:#010x}  NO EXECUTABLE"))
    return 0


# --- coverage and what next -----------------------------------------------

def coverage():
    """How much of what the game spends its time in has a copy in the port."""
    rows = {}
    marked = {}
    for m in markers():
        marked.setdefault(m["exe"], {}).setdefault(m["addr"], []).append(m)
    for nick in EXES:
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
        nm = canonical("game", f["start"]) or f["name"]
        if not everything and (_is_library(nm) or "talks to " in p
                               or "BIOS " in p):
            skipped += 1
            continue
        cand.append((len(f["callers"]), f["insns"], f["start"], nm, p))
    print(f"{len(cand)} routines in GAME.EXE with no marker in the port"
          + (f" ({skipped} library or hardware routines left out)"
             if skipped else ""), file=out)
    print("  callers  insns  address     name", file=out)
    for c, n, a, nm, p in sorted(cand, reverse=True)[:limit]:
        print(f"  {c:7d}  {n:5d}  {a:#010x}  {nm}", file=out)
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


# --- PORT.md --------------------------------------------------------------

def document(path=None):
    """PORT.md: the two codebases side by side, function by function."""
    path = path or os.path.join(ROOT, "PORT.md")
    rows, marked = coverage()
    fs = files()
    ms = [m for f in fs for m in f["markers"]]
    n = tally(fs)
    with open(path, "w") as fh:
        p = lambda *a: print(*a, file=fh)                          # noqa: E731
        p("# The port, against the game")
        p()
        p("Generated by `tools/portmap.py --doc`. Do not edit it: the markers")
        p("are in the GDScript itself, which is the only place they can stay")
        p("true when the code moves. The rules are in `tools/portmap.py`'s")
        p("docstring and in AGENT.md, \"The port and the game, one to one\".")
        p()
        p("**Every function in `godot/` says what it is.** One that reproduces")
        p("code of the game names the executable, the address and the routine:")
        p()
        p("```gdscript")
        p("# @orig game:0x8002ed60 player_vertical  status:verified 48/48 bp15")
        p("func vertical_step(y: int, surface: int) -> int:")
        p("```")
        p()
        p("and one with no counterpart in the game says which kind of the")
        p("port's own code it is:")
        p()
        p("```gdscript")
        p("# @port engine -- builds the level's nodes; the game has no scene graph")
        p("func _ready() -> void:")
        p("```")
        p()
        p("`tools/rdis.py game 0x8002ed60` prints the same pairing from the")
        p("other side, as a `; port:` line at the top of the listing, and")
        p("`tools/portmap.py game:0x8002ed60` / `tools/portmap.py")
        p("godot/player.gd:vertical_step` answer either question directly.")
        p()
        p("**A marker is a claim that the port reproduces that code, not")
        p("that it reproduces it correctly.** `status` says how far that went:")
        p()
        for k, v in STATUS.items():
            p(f"* **{k}** — {v}")
        p()
        p("and `@port` says which kind of the port's own code a function is:")
        p()
        for k, v in KINDS.items():
            p(f"* **{k}** — {v}")
        p()
        p("## How much is covered")
        p()
        own = ", ".join(f"{v} {k}" for k, v in sorted(n["port"].items()))
        p(f"{n['funcs']} functions in {n['files']} files: **{n['orig']} reproduce")
        p(f"code of the game** and {n['funcs'] - n['orig']} are the port's own")
        p(f"({own}). {n['markers']} markers, {n['cites']} addresses cited in")
        p("comments, every one of them with its executable.")
        p()
        p("| executable | routines | with a marker | stretches marked inside them | "
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
        p("## Every function, file by file")
        p()
        for f in fs:
            fun = [it for it in f["items"] if it["kind"] == "func"]
            if not fun:
                continue
            p(f"### [`{f['file']}`]({f['file']})")
            p()
            if f["port_file"]:
                p(f"The whole file is the port's own: **{f['port_file']['kind']}**"
                  + (f" — {f['port_file']['note']}" if f["port_file"]["note"] else "")
                  + ".")
                p()
            p("| function | in the game | status |")
            p("| --- | --- | --- |")
            for it in fun:
                ln = it["line"] + 1
                cell = f"[`{it['name']}`]({f['file']}#L{ln})"
                if it["orig"]:
                    for k, m in enumerate(it["orig"]):
                        p(f"| {cell if k == 0 else ''} | `{m['exe']}:{m['addr']:#010x}` "
                          f"{m['name']} | {m['status']} |")
                elif it["port"]:
                    pk = it["port"][0]
                    p(f"| {cell} | — port's own, *{pk['kind']}*: {pk['note']} | |")
                elif f["port_file"]:
                    p(f"| {cell} | — port's own, *{f['port_file']['kind']}* | |")
                else:
                    p(f"| {cell} | **not placed** | |")
            p()
        p("## Every marker, by address")
        p()
        p("| in the game | in the port | what it is | status |")
        p("| --- | --- | --- | --- |")
        for m in sorted(ms, key=lambda m: (m["exe"], m["addr"])):
            p(f"| `{m['exe']}:{m['addr']:#010x}` {m['name']} | "
              f"[`{m['file']}:{m['line']}`]({m['file']}#L{m['line']}) | "
              f"`{m['what']}` | {m['status']} |")
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
            if not line.startswith("  ") or not line.split()[0].isdigit():
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            c, k, a, *rest = parts
            p(f"| {c} | {k} | `{a}` | {' '.join(rest)} |")
        p()
    return path


def summary(out=sys.stdout):
    fs = files()
    n = tally(fs)
    rows, _marked = coverage()
    own = ", ".join(f"{v} {k}" for k, v in sorted(n["port"].items()))
    print(f"{n['funcs']} functions in {n['files']} files: {n['orig']} reproduce "
          f"the game, {n['funcs'] - n['orig']} are the port's own ({own})",
          file=out)
    print(f"{n['markers']} markers, {n['parts']} of them inside functions; "
          f"{n['cites']} addresses cited in comments", file=out)
    for nick, r in rows.items():
        pct = 100 * r["insns_ported"] // max(r["insns"], 1)
        print(f"  {nick:5s} {r['ported']:3d} of {r['routines']:4d} routines "
              f"marked"
              + (f" and {r['parts']} stretch{'es' if r['parts'] > 1 else ''} "
                 "inside them" if r["parts"] else "")
              + f", {r['insns_ported']:6d} of {r['insns']:6d} "
              f"instructions ({pct}%)", file=out)
    bad = problems(fs)
    for b in bad:
        print(b, file=out)
    print("every function placed, every marker resolves, every address has its "
          "executable" if not bad else f"{len(bad)} problems", file=out)
    return len(bad)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        sys.exit(1 if summary() else 0)
    elif argv[0] == "--check":
        sys.exit(1 if check() else 0)
    elif argv[0] == "--doc":
        print(f"wrote {os.path.relpath(document(), ROOT)}")
    elif argv[0] == "--next":
        nxt()
    elif argv[0].endswith(".gd") or ".gd:" in argv[0]:
        sys.exit(report_port(argv[0]))
    else:
        nick, _, a = argv[0].rpartition(":")
        if not nick:
            nick = "game"
            print("(a bare address: GAME.EXE's)")
        if nick not in EXES:
            print(f"{nick} is not one of " + ", ".join(EXES))
            sys.exit(1)
        report_address(nick, int(a, 0))

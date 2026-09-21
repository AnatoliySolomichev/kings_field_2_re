#!/usr/bin/env python3
"""Every number in the game's code, where it appears, and what it is doing.

    python3 tools/consts.py --build      walk all four, write the cross reference
    python3 tools/consts.py 0x800        every site of 2048, with its role
    python3 tools/consts.py --top        the commonest numbers with no name yet
    python3 tools/consts.py --fields 0x44   what is read at +0x44 of something
    python3 tools/consts.py --named      the names, with the evidence for each

A magic number is only a mystery until you can see every place it is used. 2048
is the cell size, and knowing that is worth much less than being able to ask
which routines divide by it, which compare against it, and which pass it to
something else -- because the answer to that is what says whether a routine is
about the world grid at all.

So this indexes them, with the role each site plays, taken off the instruction
and its neighbours rather than assumed:

  * **argument** -- a constant landing in $a0..$a3 before a call, reported with
    the routine it is given to, which is how `give_item(0x68)` becomes
    readable;
  * **mask**, **shift**, **bound** -- `andi`, the shift amount, and the `sltiu`
    or `slti` that limits an index;
  * **compared with** -- a constant loaded and then tested by `beq`/`bne`,
    which is what a state machine's states look like;
  * **field** -- a displacement off a register, which is a structure's layout
    and not a magic number at all. They are counted separately for that reason.

The names live in `data/constants.json`, with the evidence for each, and that
file is the point of the exercise: it is the one place to look up what a number
means, and every entry says which kind of claim it is -- **read** off the code,
**derived** from something read, or **guessed**. A guess presented as a reading
is the worst failure available here.

Addresses are deliberately *not* in here. `lui`/%lo pairs form addresses, not
magic numbers, and they belong in `data/symbols.json`; every instruction that
takes part in forming one is skipped.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mips                                                          # noqa: E402
import rdis                                                          # noqa: E402
import syms                                                          # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
XREF = os.path.join(ROOT, "out", "rdis", "constants.json")
NAMES = os.path.join(ROOT, "data", "constants.json")

# Numbers too small or too structural to be worth indexing as magic. 0 and 1
# are everywhere and mean nothing on their own.
BORING = {0, 1, -1}


def _role(w, fn, a, i):
    """What this constant is being used for, from the instruction and its
    neighbours. Returns `(role, detail)`; detail may be empty."""
    if i.mn in ("andi",):
        return "mask", ""
    if i.mn in ("slti", "sltiu"):
        return "bound", f"on ${rdis.mipsdis.GPR[i.rs]}"
    if i.mn in ("sll", "srl", "sra"):
        return "shift", ""
    # A constant into an argument register, then a call within four
    # instructions: the delay slot is the usual place, and the compiler fills
    # the three before it as well.
    if i.writes in rdis.ARGREG:
        idx = _index(fn, a)
        for j in range(idx + 1, min(idx + 5, len(fn.body))):
            n = w.insns[fn.body[j]]
            if n.kind == "call":
                nm = syms.label_in(fn.nick, n.target)
                return "argument", f"{rdis.ARGREG[i.writes]} of {nm}"
            if n.writes == i.writes:
                break
    # A constant loaded and then compared: a state, an opcode, a kind.
    if i.writes is not None:
        idx = _index(fn, a)
        for j in range(idx + 1, min(idx + 4, len(fn.body))):
            n = w.insns[fn.body[j]]
            if n.mn in ("beq", "bne") and i.writes in (n.rs, n.rt):
                other = n.rt if n.rs == i.writes else n.rs
                return "compared with", f"${rdis.mipsdis.GPR[other]}"
            if n.writes == i.writes:
                break
    if i.mn in ("addiu", "addi") and i.rs not in (0, 29):
        return "added to", f"${rdis.mipsdis.GPR[i.rs]}"
    return "loaded", ""


_INDEX = {}


def _index(fn, a):
    """Where an address sits in a routine's body, cached per routine.

    Keyed by the executable and the routine's address, not by `id(fn)`: two
    walks in one run recycle object ids, and the cache then answers about the
    wrong routine -- which it did, with a KeyError that was the lucky case.
    """
    key = (fn.nick, fn.addr)
    if key not in _INDEX:
        _INDEX[key] = {x: n for n, x in enumerate(fn.body)}
    return _INDEX[key][a]


# --- numbers the compiler took apart --------------------------------------
#
# `collide_at_cell` indexes the terrain grid at `cz * 800 + cx * 10`, and
# neither 800 nor 10 is anywhere in its code. The compiler turns a multiply by
# a constant into shifts and adds -- 800 is `((x*3) << 3 + x) << 5` -- so an
# index of immediates cannot see the two numbers that say what the grid's shape
# is. That is not a corner case: every structure stride in the game is reached
# this way, and so is every division by the cell size.
#
# So the chains are read back. A register holding `k * something` is tracked
# through the shifts and adds that build it, and the multiplier is reported
# where the chain is used. `sra` by n is recorded as a division by 2**n for the
# same reason -- `sra $v0, $a2, 0xb` is "which cell is this coordinate in".


def chains(w, fn):
    """The multipliers and divisors a routine builds out of shifts and adds.

    Returns `[(address, kind, k, register)]`, where kind is `multiplier` or
    `divisor`, so the answer reads as "at 0x80033bc8, 800 times $a2 >> 11".

    The multiplier is reported where the chain is *consumed*, not where it is
    built, and the difference matters: `collide_at_cell` finishes building
    `10 * cx` and then adds the grid's address to it with the same `addu` the
    chain has been using all along. Reading that add as one more step of the
    chain turns 10 into 11 and loses the only place the number appears.
    """
    out, seen = [], set()

    def emit(a, k, src):
        if k > 2 and (a, k) not in seen:
            seen.add((a, k))
            out.append((a, "multiplier", k, rdis.mipsdis.GPR[src]))

    for b, ins in sorted(fn.blocks.items()):
        lin = {}                       # reg -> (k, the register it multiplies)
        for a in ins:
            i = w.insns[a]
            mn, ext = i.mn, False
            if mn == "sll" and i.shamt in (16, 24):
                # A shift of 16 or 24 is a halfword or a byte being widened,
                # not a multiply: this game's fixed point is twelve bits and
                # nothing in it scales by 65536. Reading them as multipliers
                # put 65536 at the top of the index with 977 sites, every one
                # of them half of a sign extension.
                lin.pop(i.rd, None)
                ext = True
            elif mn == "sll" and i.shamt:
                src = lin.get(i.rt)
                lin[i.rd] = ((src[0] << i.shamt, src[1]) if src
                             else (1 << i.shamt, i.rt))
                ext = True
            elif mn in ("addu", "add", "subu", "sub"):
                x, y = lin.get(i.rs), lin.get(i.rt)
                sign = -1 if mn in ("subu", "sub") else 1
                if x and y and x[1] == y[1]:
                    lin[i.rd] = (x[0] + sign * y[0], x[1])
                    ext = True
                elif x and i.rt == x[1]:
                    lin[i.rd] = (x[0] + sign, x[1])
                    ext = True
                elif y and i.rs == y[1]:
                    lin[i.rd] = (1 + sign * y[0], y[1])
                    ext = True
            elif mn in ("sra", "srl") and 4 <= i.shamt < 16 and i.rt not in lin:
                # Below a shift of four this is a field being pulled out of a
                # word, not a division by anything the game names.
                out.append((a, "divisor", 1 << i.shamt, rdis.mipsdis.GPR[i.rt]))
            if not ext:
                for r in i.reads:                  # the chain is being used
                    if r in lin:
                        emit(a, lin[r][0], lin[r][1])
                if i.writes is not None:
                    for r, (k, src) in list(lin.items()):
                        if src == i.writes:        # its source is gone: it is done
                            emit(a, k, src)
                            lin.pop(r, None)
                    lin.pop(i.writes, None)
            if i.kind == "call":
                lin.clear()
    return out


def harvest(w):
    """Every constant and every field displacement in one executable."""
    vals, fields = {}, {}
    for f, fn in sorted(w.funcs.items()):
        for a, kind, k, reg in chains(w, fn):
            if k not in BORING and k > 2:
                vals.setdefault(k, []).append(
                    {"exe": w.nick, "fn": fn.name, "at": a,
                     "mn": "shift/add", "role": kind, "detail": f"of ${reg}"})
        refsites = {a for a, _addr, _m, _wd in fn.refs}
        for a in fn.body:
            i = w.insns[a]
            if i.mn == "lui":
                continue                       # the top half of an address
            if a in refsites and i.kind in ("load", "store", "alu"):
                continue                       # it formed an address, not a number
            v = None
            if i.mn in ("addiu", "addi") and i.rs == 0:
                v = i.simm
            elif i.mn == "ori" and i.rs == 0:
                v = i.imm
            elif i.mn in ("andi", "xori", "slti", "sltiu"):
                v = i.imm
            if v is not None and v not in BORING:
                role, detail = _role(w, fn, a, i)
                vals.setdefault(v, []).append(
                    {"exe": w.nick, "fn": fn.name, "at": a, "mn": i.mn,
                     "role": role, "detail": detail})
            if i.kind in ("load", "store") and i.rs != 29 and a not in refsites:  # noqa: E501
                fields.setdefault(i.simm, []).append(
                    {"exe": w.nick, "fn": fn.name, "at": a, "mn": i.mn,
                     "width": rdis.mipsdis.WIDTH.get(i.mn, 4),
                     "base": rdis.mipsdis.GPR[i.rs]})
    return vals, fields


def build(nicks=("boot", "open", "game", "end")):
    vals, fields = {}, {}
    for n in nicks:
        w = rdis.build(n)
        v, f = harvest(w)
        for k, sites in v.items():
            vals.setdefault(k, []).extend(sites)
        for k, sites in f.items():
            fields.setdefault(k, []).extend(sites)
    os.makedirs(os.path.dirname(XREF), exist_ok=True)
    out = {"values": {hex(k): v for k, v in sorted(vals.items())},
           "fields": {hex(k): v for k, v in sorted(fields.items())}}
    with open(XREF, "w") as fh:
        json.dump(out, fh, indent=0)
    return out


def xref():
    if not os.path.exists(XREF):
        return build()
    return json.load(open(XREF))


def table():
    """The names, with the evidence and the kind of claim each one is."""
    if not os.path.exists(NAMES):
        return {}
    raw = json.load(open(NAMES))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def names():
    """`{value: name}`, for annotating a listing.

    A number with more than one meaning gets them all, joined by `or` -- which
    is honest and is also the point: seeing `0x320  PLAYER_RADIUS or
    GRID_ROW_BYTES` in a listing is what makes a reader check which one the
    routine in front of them means.
    """
    out = {}
    for k, v in table().items():
        nm = " or ".join(m["name"] for m in v["meanings"])
        out[int(k, 0)] = nm
        if int(k, 0) > 0x7FFF:                     # the sign the code sees
            out[int(k, 0) - 0x10000] = nm
    return out


def report(value, out=sys.stdout):
    x = xref()
    key = hex(value)
    sites = x["values"].get(key, [])
    t = table().get(key)
    print(f"{key} ({value})", file=out)
    for m in (t or {}).get("meanings", []):
        print(f"  {m['name']} -- {m['kind']}, from {m['where']}", file=out)
        print(f"      {m['evidence']}", file=out)
    if not sites:
        print("  no site in any of the four executables", file=out)
    else:
        import collections
        by = collections.Counter(s["role"] for s in sites)
        print(f"  {len(sites)} sites: "
              + ", ".join(f"{n} {r}" for r, n in by.most_common()), file=out)
        for s in sites[:40]:
            d = f"  {s['detail']}" if s["detail"] else ""
            print(f"    {s['exe']}:{s['at']:#010x}  {s['fn']:<28s} "
                  f"{s['mn']:<6s} {s['role']}{d}", file=out)
        if len(sites) > 40:
            print(f"    ... and {len(sites) - 40} more", file=out)
    fsites = x["fields"].get(key, [])
    if fsites:
        print(f"  and {len(fsites)} loads or stores at +{key} of a register",
              file=out)


def fields(off, out=sys.stdout):
    x = xref()
    sites = x["fields"].get(hex(off), [])
    print(f"+{off:#x}: {len(sites)} loads and stores off a register", file=out)
    import collections
    by = collections.Counter((s["width"], s["mn"][0] == "s") for s in sites)
    for (wd, st), n in by.most_common():
        what = {1: "a byte", 2: "a half", 4: "a word"}[wd]
        print(f"  {n:5d}  {'store' if st else 'load'} of {what}", file=out)
    seen = {}
    for s in sites:
        seen.setdefault(s["fn"], 0)
        seen[s["fn"]] += 1
    for fn, n in sorted(seen.items(), key=lambda kv: -kv[1])[:25]:
        print(f"    {n:4d}  {fn}", file=out)


def top(out=sys.stdout, limit=40, named_only=False):
    x, t = xref(), table()
    rows = []
    for k, sites in x["values"].items():
        if named_only != (k in t):
            continue
        if not named_only and abs(int(k, 0)) < 16:
            continue                   # 2, 3, 7: small integers, not numbers
        rows.append((len(sites), k, len({s["fn"] for s in sites})))
    for n, k, fns in sorted(rows, reverse=True)[:limit]:
        nm = " or ".join(m["name"] for m in t.get(k, {}).get("meanings", []))
        print(f"  {k:>10s}  {int(k, 0):>10d}  {n:5d} sites in {fns:4d} routines"
              f"  {nm}", file=out)


def switches(out=sys.stdout):
    """Every switch in the game, with the count its guard states.

    This is naming by derivation rather than by hand: a `jr` through a table
    guarded by `sltiu $v0, $index, N` says there are exactly N cases of
    whatever the index is, and N is therefore a number with a meaning --
    0xec is "how many object opcodes there are" because the object
    interpreter's switch has that many arms.
    """
    rows = []
    for nick in ("boot", "open", "game", "end"):
        w = rdis.build(nick)
        for f, fn in sorted(w.funcs.items()):
            for tb in fn.tables:
                rows.append((nick, fn.name, tb))
    print(f"{len(rows)} switch tables in the four executables", file=out)
    for nick, name, tb in sorted(rows, key=lambda r: -len(r[2]["targets"])):
        print(f"  {nick}:{tb['at']:#010x}  {len(tb['targets']):4d} cases  "
              f"table at {tb['base']:#010x}  in {name}", file=out)


def document(path=None, out=None):
    """CONSTANTS.md: every number worth a name, in one file.

    The point of a single file is the question it answers. A number on its own
    means nothing -- 0x320 could be anything -- and the way to find out what it
    is, is to see every other place the game uses it. So each entry carries the
    role mix and the routines, and anything with a name carries the evidence
    for that name and which kind of claim it is.
    """
    import collections
    x, t = xref(), table()
    path = path or os.path.join(ROOT, "CONSTANTS.md")
    fh = out or open(path, "w")
    p = lambda *a: print(*a, file=fh)                              # noqa: E731
    total = sum(len(v) for v in x["values"].values())
    p("# The numbers in the code")
    p()
    p("Generated by `tools/consts.py --doc` from the four executables, walked")
    p("from their entry points by `tools/rdis.py`. Do not edit it: the names and")
    p("the evidence live in `data/constants.json`, and everything else here is")
    p("counted out of the code.")
    p()
    p(f"{len(x['values'])} distinct numbers over {total} sites, and")
    p(f"{len(x['fields'])} distinct displacements off a register over "
      f"{sum(len(v) for v in x['fields'].values())} sites.")
    p()
    p("A number's *role* is read off the instruction and its neighbours:")
    p()
    p("| role | what it means |")
    p("| --- | --- |")
    p("| argument | it lands in $a0..$a3 just before a call, and the call is named |")
    p("| mask | `andi` |")
    p("| bound | the `slti`/`sltiu` that limits an index |")
    p("| compared with | loaded, then tested by `beq`/`bne` -- a state or a kind |")
    p("| multiplier | built out of shifts and adds, e.g. 800 as `((x*3)<<3 + x)<<5` |")
    p("| divisor | an `sra` by 4..15 -- a scale, not a field being pulled out |")
    p("| added to | a displacement onto a pointer |")
    p("| loaded | none of the above: it is just put in a register |")
    p()
    p("Multipliers matter more than they look. `collide_at_cell` indexes the")
    p("terrain grid at `cz * 800 + cx * 10` and **neither number is in its")
    p("code** -- the compiler built both out of shifts and adds. An index of")
    p("immediates alone cannot see the two numbers that say what the grid is.")
    p()
    p("## Named")
    p()
    for k, ent in sorted(t.items(), key=lambda kv: int(kv[0], 0)):
        sites = x["values"].get(k, [])
        by = collections.Counter(s["role"] for s in sites)
        p(f"### `{k}` = {ent['value']}")
        p()
        for m in ent["meanings"]:
            p(f"**{m['name']}** -- *{m['kind']}*, from `{m['where']}`  ")
            p(f"{m['evidence']}")
            p()
        if sites:
            p(f"{len(sites)} sites: "
              + ", ".join(f"{n} {r}" for r, n in by.most_common()) + ".")
            fns = collections.Counter(f"{s['exe']}:{s['fn']}" for s in sites)
            p("In " + ", ".join(f"`{f}`" for f, _n in fns.most_common(12))
              + (f" and {len(fns) - 12} more" if len(fns) > 12 else "") + ".")
        else:
            p("No site: the compiler builds it rather than loading it, or it is "
              "named from data and not from code.")
        p()
        p(f"`python3 tools/consts.py {k}` for every site.")
        p()
    p("## The commonest numbers with no name yet")
    p()
    p("Ordered by how many routines use them, which is a better question than")
    p("how many times: a number in sixty routines is structural, and a number")
    p("used sixty times in one routine is that routine's business.")
    p()
    p("| number | | routines | sites | commonest roles |")
    p("| --- | --- | --- | --- | --- |")
    rows = []
    for k, sites in x["values"].items():
        if k in t or abs(int(k, 0)) < 16:
            continue
        rows.append((len({s["fn"] for s in sites}), len(sites), k, sites))
    for nfn, n, k, sites in sorted(rows, reverse=True)[:60]:
        by = collections.Counter(s["role"] for s in sites)
        p(f"| `{k}` | {int(k, 0)} | {nfn} | {n} | "
          + ", ".join(f"{r} {c}" for r, c in by.most_common(3)) + " |")
    p()
    p("## Displacements off a register")
    p()
    p("These are structure layouts rather than magic numbers, and they are")
    p("counted separately for that reason. `+0x44` being read in fourteen")
    p("routines is the object record's stride showing up as a field.")
    p()
    p("| offset | loads | stores | routines |")
    p("| --- | --- | --- | --- |")
    rows = []
    for k, sites in x["fields"].items():
        ld = sum(1 for s in sites if not s["mn"].startswith("s"))
        st = len(sites) - ld
        rows.append((len(sites), k, ld, st, len({s["fn"] for s in sites})))
    for n, k, ld, st, nfn in sorted(rows, reverse=True)[:40]:
        p(f"| `+{k}` | {ld} | {st} | {nfn} |")
    p()
    if out is None:
        fh.close()
    return path


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        x = xref()
        print(f"{len(x['values'])} distinct numbers, "
              f"{sum(len(v) for v in x['values'].values())} sites")
        print(f"{len(x['fields'])} distinct displacements off a register, "
              f"{sum(len(v) for v in x['fields'].values())} sites")
        print(f"{len(table())} of them have a name in data/constants.json")
    elif argv[0] == "--build":
        out = build()
        print(f"{len(out['values'])} distinct numbers, "
              f"{sum(len(v) for v in out['values'].values())} sites")
        print(f"wrote {os.path.relpath(XREF, ROOT)}")
    elif argv[0] == "--top":
        top()
    elif argv[0] == "--doc":
        path = document()
        print(f"wrote {os.path.relpath(path, ROOT)}")
    elif argv[0] == "--switches":
        switches()
    elif argv[0] == "--named":
        top(named_only=True, limit=500)
    elif argv[0] == "--fields":
        fields(int(argv[1], 0))
    else:
        report(int(argv[0], 0))

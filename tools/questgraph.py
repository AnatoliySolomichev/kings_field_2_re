#!/usr/bin/env python3
"""The quest graph: which NPC opens which, and what has to be carried there.

    python3 tools/questgraph.py          every edge, NPC to NPC
    python3 tools/questgraph.py flags    every flag a conversation reads
    python3 tools/questgraph.py --json   the same for a page or a deck

A conversation reads a story flag in two places -- the `f1` guards that choose
where it starts and the `f9` that jumps mid-conversation -- and those are
fully decoded, so the **reading** end of this graph is complete: 43 flags,
96 branches, no guesswork.

The **writing** end is not, and the difference is worth stating plainly.

* `tools/ovdis.py` walks a level's overlay following control flow, so it finds
  writes inside switch arms: **93 flags** are written somewhere in some level's
  own code. What it gives is the site, not the value or the condition.
* `tools/decomp.py` reads statements and works the condition out by dominance,
  which is what turns a write into `story_flags[3] = 1 when has_item(2) &&
  has_item(130) …`. Seeded from the walker's routines and run through returns,
  it reaches **94** -- it reached 60 when it started only at the 32 entry
  pointers and stopped at the first `jr $ra`.

So an edge is `solid` when both agree -- there is a write and a readable
condition -- and `partial` when only the walker sees it: the level is known,
the condition is not. Neither is a guess; a partial edge is a real edge with
a missing label.

**What is outside this graph entirely**, and it draws a clean line. Doors,
chests and levers write flags through the object interpreter, and the flag's
number comes from the object's own placement record rather than from an
instruction, so no constant scan can see it. Those records are not decoded
(BACKLOG item 2).

The flags with no writer are **123, 124, 126, 135, 137, 140, 143, 144 and
147**, and that is now a settled negative rather than a gap in the method.
Every word of `GAME.EXE` and every word of all 28 overlays has been scanned
linearly for a store landing in the array -- not only the parts control flow
reaches -- and no routine anywhere forms the array's base and then indexes it
by a register, so there is no computed write to hide behind either. Those nine
`f9` branches cannot be taken in a game that starts from `reset_story_flags`.

**Withdrawn:** "doors, chests and levers write flags through the object
interpreter, and the flag's number comes from the object's placement record".
There is no such write. The hypothesis was reasonable and it is wrong, and the
scan that would have supported it is the one that killed it.

**Flag 121 was in that list and is not any more.** `actor_take_hit` sets it
to 1 when a creature dies whose `actor[+1]` is below `0x2b`, and increments
**122** as a counter of the same. So the blacksmith's `flags[121] == 1` start
guard means he greets you differently once you have killed something -- and
`0x801baa2e`, which the array's arithmetic would call flag 166, is
`script_speaker` and not a flag at all. The 256 bytes are not all flags.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decomp                                                        # noqa: E402
import escript                                                       # noqa: E402
import ovdis                                                         # noqa: E402
import quest                                                         # noqa: E402
import strings                                                       # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FLAGS = 0x801BA988
FLAG_SPAN = 0x100
ITEM_ROW = 10              # the string table's row for item 0


def areas():
    with open(os.path.join(ROOT, "data", "area_names.json")) as fh:
        return json.load(fh)


def item(n):
    try:
        return strings.row(ITEM_ROW + int(n)) or f"предмет {n}"
    except Exception:
        return f"предмет {n}"


def writes_seen():
    """{flag: {level}} -- every overlay write the walker reaches."""
    out = collections.defaultdict(set)
    for lv in range(28):
        w = ovdis.walk(lv)
        if w is None:
            continue
        for f in w.funcs.values():
            for r in getattr(f, "refs", []):
                if not (isinstance(r, (tuple, list)) and len(r) >= 3):
                    continue
                addr, kind = r[1], r[2]
                if kind == "write" and isinstance(addr, int) \
                        and FLAGS <= addr < FLAGS + FLAG_SPAN:
                    out[addr - FLAGS].add(lv)
    return out


def writes_read():
    """{flag: [(level, value, [conditions])]} -- the ones with a condition.

    Seeded from every routine `tools/ovdis.py` walks rather than from the 32
    entry pointers, and run through returns, because an overlay routine has
    one return per arm and stopping at the first left most of it unread. With
    that and two fixes inside `tools/decomp.py` -- a spent `lui` is cleared,
    and a store sitting in a delay slot is kept -- this reaches **94** flags
    where it reached 60.
    """
    import ovdis
    out = collections.defaultdict(list)
    for lv in range(28):
        w = ovdis.walk(lv)
        r = decomp.Reader(lv)
        if not r.raw:
            continue
        starts = sorted(w.funcs) if w else list(r.entries)
        seen_site = set()
        for e in starts:
            stmts = r.run(e, limit=900, through_returns=True)
            for idx, (a, st) in enumerate(stmts):
                if st[0] != "store" or not str(st[1]).startswith("story_flags["):
                    continue
                if a in seen_site:
                    continue
                seen_site.add(a)
                f = int(str(st[1])[12:str(st[1]).index("]")])
                g = []
                for _b, prev in stmts[:idx]:
                    if prev[0] == "return":
                        g = []               # a return ends the path
                    elif prev[0] == "branch" and prev[4] > a and prev[5] is not None:
                        c = decomp.cond_of(prev, negate=True)
                        if c not in g:
                            g.append(c)
                out[f].append((lv, st[2], g))
    return out


def writes_in_game_exe():
    """{flag: [routine name]} -- the writes inside GAME.EXE itself.

    Off `tools/rdis.py`'s references rather than a linear `lui`/`%lo` pairing,
    which is what it used first and which missed `actor_take_hit`: the address
    is formed there and stored through with offset 0, and only the walk's
    constant propagation follows that.
    """
    import rdis
    import syms
    w = rdis.build("game")
    out = collections.defaultdict(set)
    for f in w.funcs.values():
        for r in getattr(f, "refs", []):
            if not (isinstance(r, (tuple, list)) and len(r) >= 3):
                continue
            addr, kind = r[1], r[2]
            if kind != "write" or not isinstance(addr, int):
                continue
            if not (FLAGS <= addr < FLAGS + FLAG_SPAN):
                continue
            width = r[3] if len(r) > 3 else 1
            for k in range(width):
                if addr - FLAGS + k < FLAG_SPAN:
                    out[addr - FLAGS + k].add(syms.name(f.addr) or f"{f.addr:#x}")
    # `save_restore` copies the whole array back from the card, so it writes
    # every index and says nothing about any of them.
    return {k: sorted(v) for k, v in out.items() if v != {"save_restore"}}


def readers():
    """{flag: [(level, entity, value, where)]} -- every conversation that reads it."""
    return escript.flag_graph()


def talkers():
    """{(level, entity): first line} -- who each NPC is, in their own words."""
    text = escript.talk_text()
    out = {}
    for lv, k, _rec, h, code in escript.conversations():
        vs = escript.visits(code)
        first = (h["talk"] + vs[0][0]) if vs and vs[0] else None
        out[(lv, k)] = text.get(first, "") if first is not None else ""
    return out


def calls_out():
    """{(level, entity): [flags its own f4 calls write]}."""
    arm_eff = {}
    for lv in range(28):
        _hook, ar = quest.arms(lv)
        if not ar:
            continue
        r = decomp.Reader(lv)
        for n, a in sorted(ar.items()):
            eff = []
            for _at, st in quest.body(r, a, set(ar.values())):
                if st[0] == "store" and str(st[1]).startswith("story_flags["):
                    eff.append(int(str(st[1])[12:str(st[1]).index("]")]))
            arm_eff[(lv, n)] = eff
    out = collections.defaultdict(list)
    for lv, k, _rec, _h, code in escript.conversations():
        for _off, _op, args, mn in escript.decode(code):
            if mn == "call_overlay" and args:
                out[(lv, k)] += arm_eff.get((lv, args[0]), [])
    return out


def graph():
    """Every edge: a flag, where it is written, and which NPC reads it."""
    seen, cond, rd, out_calls = writes_seen(), writes_read(), readers(), calls_out()
    native = writes_in_game_exe()
    edges = []
    for f in sorted(rd):
        who = sorted({(lv, k) for lv, k, _v, _w in rd[f]})
        items = sorted({int(c[c.index("(") + 1:c.index(")")])
                        for lv, _v, g in cond.get(f, []) for c in g
                        if c.startswith("has_item")})
        src_cond = sorted({lv for lv, _v, _g in cond.get(f, [])})
        src_seen = sorted(seen.get(f, set()))
        by_talk = sorted({k for k, fl in out_calls.items() if f in fl})
        nat = native.get(f, [])
        if src_cond:
            state = "solid"
        elif src_seen:
            state = "partial"
        elif nat:
            state = "native"
        else:
            state = "missing"
        edges.append({"flag": f, "state": state, "items": items,
                      "written_on": src_cond or src_seen,
                      "written_by_talker": by_talk,
                      "written_in_game_exe": nat,
                      "read_by": who,
                      "values": sorted({v for _l, _k, v, _w in rd[f]})})
    return edges


def report(out=sys.stdout):
    ar = areas()
    who = talkers()
    eds = graph()
    n = collections.Counter(e["state"] for e in eds)
    print(f"{len(eds)} флагов читают разговоры: {n['solid']} с прочитанным условием, "
          f"{n['partial']} только с местом записи, {n['native']} пишет сама GAME.EXE, "
          f"{n['missing']} без писателя\n", file=out)
    for e in eds:
        f = e["flag"]
        src = ", ".join(f"L{l} {ar[l]}" for l in e["written_on"]) \
            or ", ".join(e["written_in_game_exe"]) or "нигде не найдено"
        print(f"flag {f:3d}  [{e['state']}]  пишут: {src}", file=out)
        if e["items"]:
            print(f"          нужно: {', '.join(item(i) for i in e['items'])}", file=out)
        if e["written_by_talker"]:
            print("          через разговор: "
                  + ", ".join(f"L{l} e{k}" for l, k in e["written_by_talker"]), file=out)
        for lv, k in e["read_by"]:
            line = " ".join((who.get((lv, k)) or "").split())[:64]
            print(f"          читает L{lv} e{k} ({ar[lv]})" + (f" — «{line}…»" if line else ""),
                  file=out)
        print(file=out)
    return eds


def export(path=None):
    ar = areas()
    who = talkers()
    doc = {"_note": "the quest graph tools/questgraph.py builds: every flag a "
                    "conversation reads, where it is written, and what has to be "
                    "carried there. `state` is solid when a condition was read, "
                    "partial when only the write site was found, missing when "
                    "nothing writes it anywhere this project reads",
           "areas": ar,
           "talkers": {f"{lv}.{k}": " ".join((t or "").split())[:200]
                       for (lv, k), t in who.items()},
           "edges": graph()}
    for e in doc["edges"]:
        e["item_names"] = [item(i) for i in e["items"]]
    path = path or os.path.join(ROOT, "out", "questgraph.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    return path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "--json":
        print(export())
    elif arg == "flags":
        print(__doc__)
        report()
    else:
        print(__doc__)
        report()

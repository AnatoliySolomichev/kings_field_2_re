#!/usr/bin/env python3
"""The game's own words: who says what, and what each story flag turns on.

    python3 tools/story.py               every talker in the game -> out/story.txt
    python3 tools/story.py 0             one level, on screen
    python3 tools/story.py flags         each story flag, with what sets and tests it
    python3 tools/story.py cutscenes     the thirteen cutscenes and the flag each waits on

Two things had to be right before any of this could be read, both off
`script_interpreter` (`0x8005c308`):

  * an entity's dialogue counts from a **base** at `+0x0c` of the script block
    its record's `+0x38` points at -- not `+0x0c` of the record, which is where
    `tools/escript.py` used to look and which is zero for every entity on
    level 0;
  * an opcode below `0xf0` drives an animation *and* fetches
    `TALK.T[base + opcode]`. The `0x2b` comparison nearby gates neither: it
    skips a call to `0x800608ec` and the fetch sits past its branch target.

**Only 42 of the game's 265 entities carry a base**, and those 42 hold 267 of
the 12 179 `say` opcodes; 242 of the 267 land on text this project has decoded.
The other 11 912 belong to entities whose base is zero -- monsters, driving
animations. An earlier note here said all 12 179 were dialogue. They are not.
"""
import collections
import os
import sys

sys.path.insert(0, "tools")
import entities                                                      # noqa: E402
import escript                                                       # noqa: E402


def talkers(lv, text):
    """[(entity index, mesh, base, [(script offset, [(entry, line)])])]"""
    raw, base, recs = entities.entry(lv)
    if not recs:
        return []
    flat = sorted(v for _r, o in recs for v in o)
    pieces = entities.cut(raw, base, flat)
    out = []
    for k, (rec, offs) in enumerate(recs):
        b = escript.talk_base(raw, base, rec)
        if not b:
            continue
        scripts = []
        for a in offs[1:]:
            said = []
            for _off, op, _args, mn in escript.decode(pieces[a]):
                if mn == "say":
                    said.append((b + op, text.get(b + op, "")))
            if said:
                scripts.append((a, said))
        out.append((k, rec[0], b, scripts))
    return out


def dump(lv, text, out=sys.stdout):
    got = talkers(lv, text)
    if not got:
        return 0
    print(f"\n=== level {lv} — {len(got)} entities with dialogue ===", file=out)
    for k, mesh, b, scripts in got:
        print(f"\n  entity {k} (mesh {mesh:#04x}, TALK base {b})", file=out)
        for a, said in scripts:
            print(f"    script +{a}:", file=out)
            seen = set()
            for entry, line in said:
                if entry in seen:
                    print(f"      [{entry}] (again)", file=out)
                    continue
                seen.add(entry)
                body = " / ".join(line.split("\n")) if line else "(not decoded)"
                print(f"      [{entry}] {body}", file=out)
    return len(got)


# The cutscene table: 16 records of 52 bytes at 0x801e7edc, unpacked by
# init_level_state out of the seventh length-prefixed block of FDAT entry 97.
CUT_TABLE_ENTRY, CUT_BLOCK, CUT_STRIDE = 97, 6, 52


def flag_writers():
    """{flag: [(level, value)]} -- which level's own code sets each flag."""
    import collections as _c
    import decomp
    out = _c.defaultdict(list)
    for lv in range(28):
        r = decomp.Reader(lv)
        if not r.raw:
            continue
        for e in r.entries:
            for _a, st in r.run(e):
                if st[0] == "store" and st[1].startswith("story_flags["):
                    n = int(st[1][12:st[1].index("]")])
                    out[n].append((lv, st[2]))
    return out


def cutscenes():
    """Each `\\STR\\SNN.S` and the story flag that gates it.

    `0x801e825c` holds a cursor into this table and `build_str_name`
    (a label inside the player at `0x80060d20`) takes the scene number from the
    byte it points at; `flag_gate` reads the byte after it, treats `0xff` as
    "no gate", and lets bit `0x80` pick which way the flag is tested. The
    record number *is* the scene number for 3 to 15 -- exactly the thirteen
    files under `/STR` -- so the table is indexed by scene.

    Byte 0 and byte 1 are what has been read. The other fifty bytes of each
    record are not, and reading them as more scene-and-flag pairs produces
    scene numbers like 158 and 252 that no file on the disc answers to, so
    they are left alone.
    """
    import struct
    from tarc import TArc
    import placement
    raw = TArc(placement.FDAT).raw(CUT_TABLE_ENTRY)
    p, blocks = 0, []
    while p + 4 <= len(raw):
        ln = struct.unpack_from("<I", raw, p)[0]
        if ln == 0 or p + 4 + ln > len(raw):
            break
        blocks.append(raw[p + 4:p + 4 + ln])
        p += 4 + ln
    t = blocks[CUT_BLOCK]
    writers = flag_writers()
    print(f"{len(t) // CUT_STRIDE} records of {CUT_STRIDE} bytes, "
          f"from FDAT[{CUT_TABLE_ENTRY}] block {CUT_BLOCK}\n")
    for i in range(len(t) // CUT_STRIDE):
        r = t[i * CUT_STRIDE:(i + 1) * CUT_STRIDE]
        scene, gate = r[0], r[1]
        if scene != i:
            print(f"  record {i:2d}: does not name itself (byte 0 is {scene}) "
                  f"-- no \\STR\\S{i:02d}.S on the disc either")
            continue
        if gate == 0xFF:
            how = "no gate: it plays whenever it is reached"
        else:
            how = (f"waits on story_flags[{gate & 0x7F}]"
                   + (", skipped once that is set" if gate & 0x80 else ""))
        note = "  <- the opening, started by game_main on a new game" \
            if i == 3 else ""
        print(f"  \\STR\\S{i:02d}.S   {how}{note}")
        if gate != 0xFF:
            who = sorted({lv for lv, _v in writers.get(gate & 0x7F, [])})
            print("      its flag is raised by the overlay of "
                  + (f"level {', '.join(str(x) for x in who)}" if who
                     else "no level -- something else raises it"))


def flags():
    """Every story flag: what writes it, under what condition, and who tests it."""
    import decomp
    import itemtext

    def item(n):
        try:
            t = itemtext.text(int(n))
        except Exception:
            return f"item {n}"
        first = " ".join(str(t).split())[:44]
        return f"item {n} ({first})"

    # The guard is worked out by dominance rather than by folding the code
    # into if/else: this is straight-line MIPS with forward branches, so to
    # *reach* a store every branch that jumps over it must have fallen through.
    # The condition is the conjunction of those fall-throughs. That is sound
    # for this shape and it answers where the structurer cannot -- both halves
    # of level 0's flag 3 jump to a far label, so neither folds, and both are
    # still perfectly readable this way.
    wrote = collections.defaultdict(list)
    for lv in range(28):
        r = decomp.Reader(lv)
        if not r.raw:
            continue
        for e in r.entries:
            stmts = r.run(e)
            for idx, (a, st) in enumerate(stmts):
                if st[0] != "store" or not st[1].startswith("story_flags["):
                    continue
                guards = []
                for b, prev in stmts[:idx]:
                    if prev[0] == "branch" and prev[4] > a and prev[5] is not None:
                        c = decomp.cond_of(prev, negate=True)
                        if c not in guards:
                            guards.append(c)
                if not guards:
                    # The other way in: a store nothing jumps over may be the
                    # place branches jump *to* -- the else half of a test. Then
                    # it is reached exactly when those conditions held.
                    taken = []
                    for b, prev in stmts[:idx]:
                        if prev[0] == "branch" and prev[4] == a \
                                and prev[5] is not None:
                            c = decomp.cond_of(prev)
                            if c not in taken:
                                taken.append(c)
                    guards = taken
                n = int(st[1][12:st[1].index("]")])
                wrote[n].append((lv, a, str(st[2]), " && ".join(guards)))

    tested = collections.defaultdict(list)
    for lv, k, a, code, _rec in escript.walk():
        for _off, _op, args, mn in escript.decode(code):
            if mn == "if_flag" and len(args) == 3:
                tested[args[0]].append(f"level {lv} entity {k} == {args[1]}")

    print(f"{len(wrote)} of 128 story flags are written by a level overlay; "
          f"{len(tested)} are tested by an entity script.\n")
    print("The condition is worked out by dominance, not by folding the code:\n"
          "this is straight-line MIPS with forward branches, so to reach a\n"
          "store every branch jumping over it must have fallen through, and a\n"
          "store that branches jump *to* is reached when they were taken.\n"
          "A comparison this reader could not resolve prints as registers.\n")
    for n in sorted(set(wrote) | set(tested)):
        print(f"story_flags[{n}]")
        for lv, a, val, cond in wrote.get(n, []):
            print(f"   level {lv:2d} {a:#010x}: = {val:<10s} when "
                  f"{cond or 'nothing jumps over it'}")
        for t in tested.get(n, []):
            print(f"   tested by {t}")
        # name the items the condition asks for, once per flag
        names = set()
        for _lv, _a, _v, cond in wrote.get(n, []):
            for part in cond.replace("!", " ").replace("(", " ") \
                            .replace(")", " ").replace("&&", " ").split():
                if part.startswith("has_item"):
                    names.add(part[len("has_item"):].strip("()"))
        for nm in sorted(names, key=lambda x: int(x) if x.isdigit() else 0):
            if nm.isdigit():
                print(f"      needs {item(nm)}")
        print()


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "flags":
        flags()
    elif arg == "cutscenes":
        cutscenes()
    elif arg == "all":
        text = escript.talk_text()
        os.makedirs("out", exist_ok=True)
        with open("out/story.txt", "w") as f:
            n = sum(dump(lv, text, f) for lv in range(28))
        print(f"{n} entities with dialogue across 28 levels -> out/story.txt")
    else:
        dump(int(arg), escript.talk_text())

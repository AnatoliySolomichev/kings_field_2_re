#!/usr/bin/env python3
"""Experience, and what a level gives you.

    python3 tools/levelup.py            the table, and the model checked
    python3 tools/levelup.py 1 1000     what level 1 becomes after 1000 exp
    python3 tools/levelup.py --table    every level, in full

`award_exp` at `0x8002a310` is the whole of it, and it turned out to be short:
add the experience, cap it at 999999, and while it reaches the next threshold,
take a level. What a level gives is not computed -- it is **read out of a
table of 99 records of twelve bytes**, and the table is not in GAME.EXE. It sits
at `0x8009f114`, which is past the end of the image, and it comes off the disc:
**`FDAT.T` entry 97 at offset 12592**, the same shared blob that carries the
cutscene list, the object type table and the spell table.

```
+0  u16   HP maximum at this level          50 at level 1, 999 by level 97
+2  u16   MP maximum                        30 ... 999
+4  u16   added to the stat at +0x36        20 once, then 0, 1 or 2
+8  u32   experience needed for the next    50, 110, 187, ... 999999
```

Checked against every RAM snapshot in `out/snap`: **13 of 13** have the HP
maximum, the MP maximum and the next threshold their level's record says, and
the cumulative third column, 20 then 21, is what `+0x36` holds in each.

Past level 99 the table stops and the routine extrapolates instead, by the
*difference* between the last two records (`0x8002a45c`): the HP and MP maxima
and the threshold each grow by the last step again, forever, and since the
experience is capped at 999999 and record 98 asks for 1000000, that never runs
in an ordinary game.

Five more figures grow by a coin toss -- the **skills**, at `0x801b2518` to
`0x801b2520`: for each one that is not already zero, `rand() < 0x6665` adds one --
about four times in five. That is the only place `rand` is used in levelling,
and it is why two characters at the same level are not the same character.

Everything is then clamped to 999 (`0x3e7`), including the maxima.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tarc import TArc                                                # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FDAT = os.path.join(ROOT, "extract", "CD", "COM", "FDAT.T")
ENTRY, OFFSET, LEVELS, RECORD = 97, 12592, 99, 12

EXP_CAP = 0xF423F            # 999999, at 0x8002a35c
STAT_CAP = 0x3E7             # 999, at 0x8002a52c and the three beside it
GROW_ODDS = 0x6665           # rand() below this adds one, at 0x8002a420
LEVEL_CAP = 0xFF             # the level byte stops here, at 0x8002a3a8
TABLE_LEVELS = 0x63          # 99: above this the routine extrapolates


def table(path=FDAT):
    """The 99 records, as `[(hp_max, mp_max, stat_gain, exp_next)]`."""
    raw = TArc(path).raw(ENTRY)
    out = []
    for i in range(LEVELS):
        o = OFFSET + i * RECORD
        hp, mp, gain = struct.unpack_from("<3H", raw, o)
        nxt = struct.unpack_from("<I", raw, o + 8)[0]
        out.append((hp, mp, gain, nxt))
    return out


def award(state, delta, rng=None):
    """`award_exp` (0x8002a310), on a dict of the player's figures.

    `state` wants `exp`, `exp_next`, `level`, `hp_max`, `mp_max`, `stat36` and
    `grow` (five numbers). `rng` is called for each growth roll and should
    return what the game's `rand` returns, 0..0x7fff; without one the rolls all
    succeed, which is the best case rather than an average.
    """
    t = table()
    s = dict(state)
    s["exp"] = min(s["exp"] + delta, EXP_CAP)
    while s["exp"] >= s["exp_next"] and s["level"] < LEVEL_CAP:
        lv = s["level"]
        s["level"] = lv + 1
        if (lv & 0xFF) < TABLE_LEVELS:
            hp, mp, gain, nxt = t[lv]
            s["hp_max"], s["mp_max"] = hp, mp
            s["stat36"] += gain
            s["exp_next"] = nxt
        else:
            last, prev = t[LEVELS - 1], t[LEVELS - 2]
            s["hp_max"] += last[0] - prev[0]
            s["mp_max"] += last[1] - prev[1]
            s["stat36"] += last[2]
            s["exp_next"] += last[3] - prev[3]
        # The five, from 0x801b2520 downwards. A stat already at zero never
        # grows -- the routine tests it before it rolls.
        for k in range(5):
            if s["grow"][k] and (rng() if rng else 0) < GROW_ODDS:
                s["grow"][k] += 1
        s["hp_max"] = min(s["hp_max"], STAT_CAP)
        s["mp_max"] = min(s["mp_max"], STAT_CAP)
        s["stat36"] = min(s["stat36"], STAT_CAP)
        s["grow"] = [min(g, STAT_CAP) for g in s["grow"]]
    return s


def export(out_dir):
    """The table, where the port can read it.

    The port could carry the ninety-nine records in its source, and that would
    be a copy nobody would ever re-derive. This writes them out of the disc
    instead, beside the level geometry, so the two can only disagree if the
    disc changes.
    """
    import json
    rows = [{"hp": hp, "mp": mp, "gain": g, "next": n}
            for hp, mp, g, n in table()]
    cases(out_dir)
    path = os.path.join(out_dir, "levels.json")
    with open(path, "w") as fh:
        json.dump({"_note": f"FDAT.T entry {ENTRY} at offset {OFFSET}, "
                            f"{LEVELS} records of {RECORD} bytes; "
                            "tools/levelup.py wrote it",
                   "exp_cap": EXP_CAP, "stat_cap": STAT_CAP,
                   "grow_odds": GROW_ODDS, "levels": rows}, fh,
                  separators=(",", ":"))
    return path


def cases(out_dir, n=40):
    """Cases for the port to reproduce, written where selftest.gd reads them.

    The five rolled stats are held at zero on both sides: the game's `rand` is
    not reproduced in the port, so comparing them would be comparing two
    different random sequences. What is left is everything the table decides,
    which is the part worth checking.
    """
    import json
    rows = []
    t = table()
    for k in range(n):
        lv = 1 + (k * 7) % 98
        hp, mp, _g, nxt = t[lv - 1]
        st = {"exp": 0, "exp_next": nxt, "level": lv, "hp_max": hp,
              "mp_max": mp, "stat36": sum(r[2] for r in t[:lv]),
              "grow": [0, 0, 0, 0, 0]}
        delta = (k * 9973) % 200000
        after = award(st, delta)
        row = dict(st)
        row.pop("grow")
        row["award"] = delta
        row["want"] = {key: after[key] for key in
                       ("level", "hp_max", "mp_max", "stat36",
                        "exp", "exp_next")}
        rows.append(row)
    path = os.path.join(out_dir, "levelcheck.json")
    with open(path, "w") as fh:
        json.dump(rows, fh, separators=(",", ":"))
    return path


def check(out=sys.stdout):
    """Hold the table against every snapshot, and report the count."""
    import player
    t = table()
    snaps = os.path.join(ROOT, "out", "snap")
    if not os.path.isdir(snaps):
        print("no snapshots to check against", file=out)
        return 0, 0
    ok = seen = 0
    for f in sorted(os.listdir(snaps)):
        if not f.endswith(".ram"):
            continue
        p = player.read(open(os.path.join(snaps, f), "rb").read())
        lv = p["level"]
        if not 1 <= lv <= LEVELS:
            continue
        hp, mp, _gain, nxt = t[lv - 1]
        hit = (p["hp_max"] == hp and p["mp_max"] == mp
               and p["exp_next"] == nxt)
        seen += 1
        ok += hit
        if not hit:
            print(f"  {f}: level {lv} has {p['hp_max']}/{p['mp_max']}/"
                  f"{p['exp_next']}, the table says {hp}/{mp}/{nxt}", file=out)
    print(f"{ok} of {seen} snapshots match the table exactly", file=out)
    return ok, seen


if __name__ == "__main__":
    argv = sys.argv[1:]
    t = table()
    if argv and argv[0] == "--godot":
        print("wrote " + os.path.relpath(export("out/godot"), ROOT))
    elif argv and argv[0] == "--table":
        print(" level   HP   MP  +0x36   for the next level")
        run = 0
        for i, (hp, mp, gain, nxt) in enumerate(t):
            run += gain
            print(f"  {i + 1:4d} {hp:5d} {mp:4d} {gain:5d} ({run:4d}) {nxt:12d}")
    elif len(argv) >= 2:
        lv, exp = int(argv[0]), int(argv[1])
        hp, mp, _g, nxt = t[lv - 1]
        s = {"exp": 0, "exp_next": nxt, "level": lv, "hp_max": hp,
             "mp_max": mp, "stat36": sum(r[2] for r in t[:lv]),
             "grow": [10, 10, 10, 10, 10]}
        after = award(s, exp)
        print(f"level {lv} with {exp} experience becomes level {after['level']}"
              f": HP {after['hp_max']}, MP {after['mp_max']}, "
              f"next at {after['exp_next']}")
        print("(the five rolled stats are shown at their best: "
              "every roll succeeding)")
    else:
        print(f"{LEVELS} levels, from FDAT.T entry {ENTRY} at offset {OFFSET}")
        print(" level   HP   MP   for the next level")
        for i in (0, 1, 2, 49, 96, 97, 98):
            hp, mp, _g, nxt = t[i]
            print(f"  {i + 1:4d} {hp:5d} {mp:4d} {nxt:12d}")
        print()
        check()

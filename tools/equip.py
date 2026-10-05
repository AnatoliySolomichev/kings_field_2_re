#!/usr/bin/env python3
"""What a weapon and a piece of armour are worth, and the player's ratings.

    python3 tools/equip.py              both tables, with the item names
    python3 tools/equip.py --raw        every record
    python3 tools/equip.py --check      the disc and the formula against a
                                        RAM snapshot
    python3 tools/equip.py --godot      write them out for the port

`player_recalc_stats` (`0x80029500`) is the routine, and it is called from
twelve places -- `award_exp`, `player_take_hit`, `player_action`, equipping
something -- so the ratings are never stored, only ever recomputed. What it
does, in order:

1. **zero** the eight offense ratings at `0x801b2538` and the eight defense
   ratings at `0x801b254a`, and copy the five skills at `0x801b2518` down into
   a working set at `0x801b252e`;
2. when `[0x801b255e]` is set, **halve** the working skills and the effective
   stat at `0x801b2524` -- a curse;
3. add the equipped **weapon**'s eight values: `0x801b25af` is the id, the
   record is 68 bytes at `weapon_table + 68 * id`, and the eight `u16` from
   `+6` to `+0x14` go one per offense rating;
4. add each of the seven equipped **pieces of armour**, `0x801b25d4` through
   `0x801b25da`: the record is 32 bytes at `armour_table + 32 * (id - 34)`,
   and the eight `u16` from `+2` to `+0x12` go one per defense rating;
5. add the flat bonuses: `[0x801b256a]` gives `+0x32` to defense rating 4
   (`0x801b2552` -- this said offense 5 until the listing was read again),
   `[0x801b256e]` gives `+0x1e` to defense ratings 0, 1 and 2, and
   `[0x801b2578]` gives `+5` to every working skill;
6. what thirteen things add by id when worn (`SPECIALS` and `RINGS` below:
   the weapons 0x20 and 0x21, the groundal crown's `+0x14` to the stat, the
   rings 0x51 to 0x5b...), and `+0x32` to skill 3 on level 0x1a while the
   story byte `0x801ba9e9` is 1;
7. clamp: a u16 over `0x7fff` (under zero) is 0, and the stat and the
   working skills stop at 999.

All of it is `recalc()`, held against every snapshot: **437 of 437** values,
the sixteen ratings, the resistance (the armour's `+8`, the hole in the eight
it adds, goes to a ninth defense half, `0x801b255a`), five working skills and
the effective stat of 19 -- one of them, `equip4`, with nothing worn or
wielded, every rating 0.

`0xff` in a slot means nothing is worn, and the routine skips it.

**The tables are FDAT entry 97, blocks 1 and 2**, the second and third of the
ten blocks `init_level_state` scatters at boot: block 1 is 3264 bytes, 48
records of 68, landing at `0x801d37a4`; block 2 is 2112 bytes, 66 records of
32, landing at `0x801e64b8`. The armour helper (`0x800293e4`) addresses that
second table from `0x801e6078`, which is `0x801e64b8 - 34 * 32`, so **armour
ids start at 34** -- weapons are items 0..33 and armour 34..99, one id space
split between two tables of different shapes.

**The id space matches the names.** Rows `10 + id` of the plain-text table at
`0x8007f530` (`tools/strings.py`) run: 0..33 swords, axes, bows and rods;
34..41 helms; 42..49 body armour; 50..60 shields; 61..70 gloves; 71..79 boots;
80..92 rings and amulets; 93..99 maps and notes. Two of the seven slots are
named by code rather than by me: `cast_spell` **doubles** the MP cost when
`0x801b25d4` holds `0x26`, which is *groundal crown*, a **helm**, and
**halves** it when `0x801b25d5` holds `0x2e`, which is *orladin's mail*, a
**body** piece. So slot 0 is the head and slot 1 the body. The other five are
not settled, though the name groups leave little room.

Checked against a RAM snapshot taken while the game was running with
*excellector* and a *leather plate*: **3264 of 3264** weapon bytes and **2112
of 2112** armour bytes are what the disc holds, and **16 of 16** ratings come
out of the two records. Then against five states `emu/bp23.lua` logged while
the player put things on and took them off: **80 of 80**, and between them
they exercise what one snapshot could not -- nothing worn, no weapon, one
piece, the other, and both at once.

**Still unexercised**: the four flat bonuses and the thirteen things. No state
recorded had the byte at `0x801b255e`, `0x801b256a`, `0x801b256e` or
`0x801b2578` set, or one of the things on, so the curse, the `+0x32`, the
`+0x1e`, the `+5` and the specials are read and unseen.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tarc import TArc                                                # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FDAT = os.path.join(ROOT, "extract", "CD", "COM", "FDAT.T")

ENTRY = 97
WEAPON_BLOCK, WEAPON_ROW, WEAPON_LIVE = 1, 68, 0x801D37A4
ARMOUR_BLOCK, ARMOUR_ROW, ARMOUR_LIVE = 2, 32, 0x801E64B8
ARMOUR_FIRST = 34          # 0x801e64b8 - 0x801e6078, over 32 bytes a record
RATINGS = 8                # eight offense and eight defense
WEAPON_AT = 6              # the first of the weapon's eight u16
ARMOUR_AT = (2, 4, 6, 0xA, 0xC, 0xE, 0x10, 0x12)   # the armour's, with a hole
RESIST_AT = 8              # the hole: the ninth defense half, the resistance

OFFENSE = 0x801B2538
DEFENSE = 0x801B254A
SKILLS = 0x801B2518        # five u16, copied down to 0x801b252e to be worked on
WORKING = 0x801B252E
WEAPON_SLOT = 0x801B25AF
ARMOUR_SLOTS = range(0x801B25D4, 0x801B25DB)       # seven of them
NONE = 0xFF

CURSE = 0x801B255E         # halves the working skills
BONUS_OFFENSE = 0x801B256A     # +0x32 to offense 5
BONUS_DEFENSE = 0x801B256E     # +0x1e to defense 0, 1 and 2
BONUS_SKILLS = 0x801B2578      # +5 to every working skill


def blocks(path=FDAT):
    """The length-prefixed blocks of FDAT entry 97, as (offset, length)."""
    raw = TArc(path).raw(ENTRY)
    out, o = [], 0
    while o + 4 <= len(raw):
        n = struct.unpack_from("<I", raw, o)[0]
        out.append((o + 4, n))
        o += 4 + n
        if n == 0:
            break
    return raw, out


def tables(path=FDAT):
    """(weapon records, armour records) straight off the disc."""
    raw, bs = blocks(path)
    o, n = bs[WEAPON_BLOCK]
    weapons = [raw[o + i * WEAPON_ROW:o + (i + 1) * WEAPON_ROW]
               for i in range(n // WEAPON_ROW)]
    o, n = bs[ARMOUR_BLOCK]
    armour = [raw[o + i * ARMOUR_ROW:o + (i + 1) * ARMOUR_ROW]
              for i in range(n // ARMOUR_ROW)]
    return weapons, armour


def weapon_values(rec):
    """The eight offense values a weapon adds."""
    return [struct.unpack_from("<H", rec, WEAPON_AT + 2 * i)[0]
            for i in range(RATINGS)]


def armour_values(rec):
    """The eight defense values a piece of armour adds."""
    return [struct.unpack_from("<H", rec, o)[0] for o in ARMOUR_AT]


STAT_36 = 0x801B2516
STAT_EFFECTIVE = 0x801B2524
WORKING_FIRST = 0x801B2526  # the five working skills, 0x801b2526..0x801b252e
STORY_9E9 = 0x801BA9E9     # a story byte: with it 1 on level 0x1a, +0x32 to skill 3
LEVEL_NOW = 0x8018FAD8
CAP = 0x3E7

# The worn things player_recalc_stats knows by id, after the ratings and the
# flat bonuses: (slot address, id, what it adds). "w0".."w4" are the working
# skills, "stat" the effective stat, "o4" an offense rating, "o*" all eight.
SPECIALS = (
    (WEAPON_SLOT, 0x20, (("w2", 0x14),)),
    (WEAPON_SLOT, 0x21, (("w0", 0x14),)),
    (0x801B25D4, 0x26, (("stat", 0x14),)),
    (0x801B25D4, 0x29, (("w4", 0x14),)),
    (0x801B25D5, 0x31, (("w1", 0x14),)),
    (0x801B25D6, 0x39, (("w4", 0x1E),)),
    (0x801B25D6, 0x3C, (("w2", 0x14),)),
    (0x801B25D7, 0x43, (("o4", 0x14),)),
    (0x801B25D7, 0x44, (("o*", 0xA),)),
    (0x801B25D7, 0x46, (("w0", 0x14),)),
    (0x801B25D8, 0x4F, (("w3", 0x14),)),
    (0x801B25D9, 0x51, (("stat", 5),)),
    (0x801B25DA, 0x51, (("stat", 5),)),
)
# and the two ring slots asked together: either one holding the id
RINGS = (
    (0x52, (("w*", 8), ("stat", -0x1E))),
    (0x55, (("o4", 0xC), ("o5", 0xC), ("o6", 0xC), ("o7", 0xC))),
    (0x59, (("w3", 0x14),)),
    (0x5A, (("w1", 0x14),)),
    (0x5B, (("w4", 0x14),)),
)


def recalc(st, weapons=None, armour=None):
    """`player_recalc_stats` (`0x80029500`), all of it but the word it copies
    from 0x801b2584 to 0x801c12f0. `st` holds what it reads -- "stat36",
    "skills" (five), "curse" (0x801b255e), "b56a", "b56e", "b578" (the three
    flat bonuses' timers), "weapon", "worn" (the seven at 0x801b25d4),
    "story" (0x801ba9e9) and "level" -- and the answer is what it writes:
    "offense", "defense", "working" and "stat"."""
    if weapons is None or armour is None:
        weapons, armour = tables()
    off = [0] * RATINGS
    dfn = [0] * RATINGS
    stat = st["stat36"] & 0xFFFF
    work = [v & 0xFFFF for v in st["skills"]]
    if st.get("curse", 0):
        stat >>= 1
        work = [v >> 1 for v in work]
    weapon = st["weapon"]
    if weapon != NONE and weapon < len(weapons):
        for i, v in enumerate(weapon_values(weapons[weapon])):
            off[i] = (off[i] + v) & 0xFFFF
    resist = 0
    for slot in st["worn"]:
        if slot == NONE:
            continue
        i = slot - ARMOUR_FIRST
        if 0 <= i < len(armour):
            for k, v in enumerate(armour_values(armour[i])):
                dfn[k] = (dfn[k] + v) & 0xFFFF
            # the hole in ARMOUR_AT: +8 goes to the ninth half, 0x801b255a,
            # the resistance player_take_hit rolls against
            resist = (resist + struct.unpack_from("<H", armour[i], RESIST_AT)[0]) & 0xFFFF
    if st.get("b56a", 0):
        dfn[4] = (dfn[4] + 0x32) & 0xFFFF
    if st.get("b56e", 0):
        for k in (0, 1, 2):
            dfn[k] = (dfn[k] + 0x1E) & 0xFFFF
    if st.get("b578", 0):
        work = [(v + 5) & 0xFFFF for v in work]
    slots = {WEAPON_SLOT: weapon}
    for k, a in enumerate(ARMOUR_SLOTS):
        slots[a] = st["worn"][k]

    def give(what):
        nonlocal stat
        for key, n in what:
            if key == "stat":
                stat = (stat + n) & 0xFFFF
            elif key == "w*":
                for k in range(5):
                    work[k] = (work[k] + n) & 0xFFFF
            elif key[0] == "w":
                work[int(key[1])] = (work[int(key[1])] + n) & 0xFFFF
            elif key == "o*":
                for k in range(RATINGS):
                    off[k] = (off[k] + n) & 0xFFFF
            else:
                off[int(key[1])] = (off[int(key[1])] + n) & 0xFFFF
    for addr, ident, what in SPECIALS:
        if slots[addr] == ident:
            give(what)
    for ident, what in RINGS:
        if slots[0x801B25D9] == ident or slots[0x801B25DA] == ident:
            give(what)
    if st.get("story", 0) == 1 and st.get("level", 0) == 0x1A:
        work[3] = (work[3] + 0x32) & 0xFFFF
    # under zero (as a u16, over 0x7fff) is 0, over 999 is 999
    stat = 0 if stat > 0x7FFF else min(stat, CAP)
    work = [0 if v > 0x7FFF else min(v, CAP) for v in work]
    off = [0 if v > 0x7FFF else v for v in off]
    dfn = [0 if v > 0x7FFF else v for v in dfn]
    resist = 0 if resist > 0x7FFF else resist
    return {"offense": off, "defense": dfn, "working": work, "stat": stat,
            "resist": resist}


def state_of(ram):
    """What player_recalc_stats reads, out of a RAM snapshot."""
    def u16(a):
        return struct.unpack_from("<H", ram, a & 0x1FFFFF)[0]
    def s16(a):
        return struct.unpack_from("<h", ram, a & 0x1FFFFF)[0]
    return {"stat36": u16(STAT_36), "skills": [u16(SKILLS + 2 * k) for k in range(5)],
            "curse": s16(CURSE), "b56a": s16(BONUS_OFFENSE), "b56e": s16(BONUS_DEFENSE),
            "b578": s16(BONUS_SKILLS), "weapon": ram[WEAPON_SLOT & 0x1FFFFF],
            "worn": list(ram[ARMOUR_SLOTS.start & 0x1FFFFF:ARMOUR_SLOTS.stop & 0x1FFFFF]),
            "story": ram[STORY_9E9 & 0x1FFFFF], "level": ram[LEVEL_NOW & 0x1FFFFF]}


def written_of(ram):
    """What player_recalc_stats last wrote, out of the same snapshot."""
    def u16s(a, n):
        return list(struct.unpack_from(f"<{n}H", ram, a & 0x1FFFFF))
    return {"offense": u16s(OFFENSE, RATINGS), "defense": u16s(DEFENSE, RATINGS),
            "working": u16s(WORKING_FIRST, 5), "stat": u16s(STAT_EFFECTIVE, 1)[0],
            "resist": u16s(DEFENSE + 2 * RATINGS, 1)[0]}


def check_snapshots(out=sys.stdout, verbose=False):
    """recalc() against every snapshot with a game in it: the sixteen
    ratings, the five working skills and the effective stat it leaves."""
    import glob
    weapons, armour = tables()
    ok = n = 0
    seen = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        ram = open(path, "rb").read()
        st = state_of(ram)
        if st["weapon"] == 0 and not any(st["skills"]) and st["stat36"] == 0:
            continue                       # not a running game
        got = recalc(st, weapons, armour)
        want = written_of(ram)
        seen += 1
        flat = lambda d: d["offense"] + d["defense"] + d["working"] + [d["stat"], d["resist"]]  # noqa: E731
        g, w = flat(got), flat(want)
        same = sum(1 for a, b in zip(g, w) if a == b)
        ok += same
        n += len(w)
        if verbose or same != len(w):
            print(f"  {os.path.basename(path)}: weapon {st['weapon']}, worn {st['worn']}, "
                  f"skills {st['skills']}, stat {st['stat36']} -- {same} of {len(w)}"
                  + ("" if same == len(w) else f"\n    model {got}\n    RAM   {want}"),
                  file=out)
    print(f"  player_recalc_stats over {seen} snapshots: {ok} of {n} values -- the "
          f"sixteen ratings, the resistance, the five working skills and the "
          f"effective stat", file=out)
    return ok == n


def recalc_cases():
    """States that take every branch of recalc(), and its answers, for the
    port's copy (godot/selftest.gd)."""
    weapons, armour = tables()
    base = {"stat36": 20, "skills": [0, 0, 0, 0, 10], "curse": 0, "b56a": 0,
            "b56e": 0, "b578": 0, "weapon": 0, "worn": [0xFF, 42] + [0xFF] * 5,
            "story": 0, "level": 0}
    cases = [dict(base)]
    for key in ("curse", "b56a", "b56e", "b578"):
        cases.append(dict(base, **{key: 1}))
    for addr, ident, _w in SPECIALS:
        if addr == WEAPON_SLOT:
            cases.append(dict(base, weapon=ident))
        else:
            worn = list(base["worn"])
            worn[addr - ARMOUR_SLOTS.start] = ident
            cases.append(dict(base, worn=worn))
    for ident, _w in RINGS:
        for k in (5, 6):
            worn = list(base["worn"])
            worn[k] = ident
            cases.append(dict(base, worn=worn))
    cases.append(dict(base, story=1, level=0x1A))
    cases.append(dict(base, stat36=10, worn=[0xFF, 42, 0xFF, 0xFF, 0xFF, 0x52, 0xFF]))
    cases.append(dict(base, stat36=995, skills=[995, 990, 0, 7, 999],
                      worn=[0x26, 0x31, 0x39, 0x44, 0x4F, 0x52, 0x5B], b578=1))
    cases.append(dict(base, weapon=0xFF, worn=[0xFF] * 7, curse=1, stat36=1,
                      skills=[1, 2, 3, 4, 5]))
    return [{"state": c, "want": recalc(c, weapons, armour)} for c in cases]


def ratings(weapon, worn, weapons=None, armour=None,
            curse=False, bonus_offense=False, bonus_defense=False):
    """`player_recalc_stats`, as far as the equipment goes.

    `weapon` is the id at `0x801b25af` and `worn` the seven at `0x801b25d4`;
    0xff in either means nothing. Returns (offense[8], defense[8]).
    """
    if weapons is None or armour is None:
        weapons, armour = tables()
    off = [0] * RATINGS
    dfn = [0] * RATINGS
    if weapon != NONE and weapon < len(weapons):
        for i, v in enumerate(weapon_values(weapons[weapon])):
            off[i] += v
    for slot in worn:
        if slot == NONE:
            continue
        i = slot - ARMOUR_FIRST
        if 0 <= i < len(armour):
            for k, v in enumerate(armour_values(armour[i])):
                dfn[k] += v
    if bonus_offense:
        off[5] += 0x32
    if bonus_defense:
        for k in (0, 1, 2):
            dfn[k] += 0x1E
    return off, dfn


ITEM_ROW = 10              # the string table's row for item 0 -- tools/strings.py


def item_names():
    """item id -> name, out of the plain-text table at 0x8007f530."""
    try:
        import strings
        rows = strings.table()
        return {n: rows[ITEM_ROW + n].strip()
                for n in range(len(rows) - ITEM_ROW)
                if rows[ITEM_ROW + n].strip()}
    except Exception:
        return {}


def check(ram_path):
    """The disc, and the formula, against a RAM snapshot.

    The snapshot is 2 MB and is not kept in the repository, so without one
    this falls back to `RECORDED`, which is the same case written down.
    """
    if not os.path.exists(ram_path):
        print(f"  no RAM snapshot at {ram_path}; checking the formula against "
              f"RECORDED instead")
        weapons, armour = tables()
        bad = 0
        for r in RECORDED:
            o, f = ratings(r["weapon"], r["worn"], weapons, armour)
            n = sum(1 for a, b in zip(o, r["offense"]) if a == b) \
                + sum(1 for a, b in zip(f, r["defense"]) if a == b)
            print(f"  weapon {r['weapon']}, worn {r['worn']}: "
                  f"{n} of {2 * RATINGS} ratings reproduced from the two records")
            bad += 2 * RATINGS - n
        return bad == 0
    d = open(ram_path, "rb").read()

    def at(a):
        return a - 0x80000000

    weapons, armour = tables()
    ok = bad = 0
    # the two tables, byte for byte
    for name, recs, live in (("weapons", weapons, WEAPON_LIVE),
                             ("armour", armour, ARMOUR_LIVE)):
        blob = b"".join(recs)
        live_blob = d[at(live):at(live) + len(blob)]
        same = sum(1 for a, b in zip(blob, live_blob) if a == b)
        print(f"  {name}: {same} of {len(blob)} bytes match RAM at {live:#x}")
        ok += same
        bad += len(blob) - same
    # and the formula
    weapon = d[at(WEAPON_SLOT)]
    worn = list(d[at(ARMOUR_SLOTS.start):at(ARMOUR_SLOTS.stop)])
    off, dfn = ratings(weapon, worn, weapons, armour)
    live_off = list(struct.unpack_from("<8H", d, at(OFFENSE)))
    live_dfn = list(struct.unpack_from("<8H", d, at(DEFENSE)))
    n = sum(1 for a, b in zip(off, live_off) if a == b) \
        + sum(1 for a, b in zip(dfn, live_dfn) if a == b)
    print(f"  weapon {weapon}, worn {worn}")
    print(f"  offense: {off}  RAM {live_off}")
    print(f"  defense: {dfn}  RAM {live_dfn}")
    print(f"  {n} of {2 * RATINGS} ratings reproduced from the two records")
    for r in RECORDED:
        o, f = ratings(r["weapon"], r["worn"], weapons, armour)
        if o != r["offense"] or f != r["defense"]:
            print(f"  RECORDED disagrees: {o} {f}")
            bad += 1
    return bad == 0 and n == 2 * RATINGS and check_snapshots()


# The equipped ids and the sixteen ratings `player_recalc_stats` left, from a
# RAM snapshot and then from `emu/bp23.lua`, which sat on the routine's last
# instruction while the player put things on and took them off.
#
# Five states, and between them they exercise what one snapshot could not:
# **nothing worn** (every rating zero), **no weapon** (0xff skipped, the
# offense side zero while the defense side stands), one piece, the other, and
# **both at once** -- 14+13, 4+6 and 2+4 giving 27, 10 and 6, which is the sum
# across slots seen rather than assumed.
RECORDED = [
    # a RAM snapshot, and then the five states emu/bp23.lua logged while the
    # player put things on and took them off again
    {"weapon": 0, "worn": [255, 42, 255, 255, 255, 255, 255],
     "offense": [39, 32, 9, 0, 0, 0, 0, 0],
     "defense": [13, 6, 4, 0, 0, 0, 0, 0]},
    {"weapon": 0, "worn": [255, 255, 255, 255, 255, 255, 255],
     "offense": [39, 32, 9, 0, 0, 0, 0, 0],
     "defense": [0, 0, 0, 0, 0, 0, 0, 0]},
    {"weapon": 255, "worn": [255, 42, 255, 255, 255, 255, 255],
     "offense": [0, 0, 0, 0, 0, 0, 0, 0],
     "defense": [13, 6, 4, 0, 0, 0, 0, 0]},
    {"weapon": 0, "worn": [34, 42, 255, 255, 255, 255, 255],
     "offense": [39, 32, 9, 0, 0, 0, 0, 0],
     "defense": [27, 10, 6, 0, 0, 0, 0, 0]},
    {"weapon": 0, "worn": [34, 255, 255, 255, 255, 255, 255],
     "offense": [39, 32, 9, 0, 0, 0, 0, 0],
     "defense": [14, 4, 2, 0, 0, 0, 0, 0]},
]


def export(out_dir):
    weapons, armour = tables()
    rows = {"_note": "FDAT.T entry 97 blocks 1 and 2: the weapon records "
                     "(68 bytes, item ids 0..33) and the armour records "
                     "(32 bytes, ids 34..99), with the eight ratings each "
                     "adds, as player_recalc_stats reads them",
            "armour_first": ARMOUR_FIRST,
            "weapons": [weapon_values(r) for r in weapons],
            "armour": [armour_values(r) for r in armour],
            "resist": [struct.unpack_from("<H", r, RESIST_AT)[0] for r in armour],
            "recorded": RECORDED, "recalc": recalc_cases()}
    path = os.path.join(out_dir, "equip.json")
    with open(path, "w") as fh:
        json.dump(rows, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "--check":
        ram = sys.argv[2] if len(sys.argv) > 2 else "out/ram.bin"
        sys.exit(0 if check(ram) else 1)
    elif arg == "--godot":
        print(export("godot"))
    else:
        weapons, armour = tables()
        names = item_names()
        print(__doc__)
        print(f"{len(weapons)} weapon records of {WEAPON_ROW} bytes, "
              f"{len(armour)} armour records of {ARMOUR_ROW}\n")
        print("weapons (item id 0 up):")
        for i, r in enumerate(weapons):
            v = weapon_values(r)
            if not any(v) and arg != "--raw":
                continue
            print(f"  {i:3d} {names.get(i,''):<24s} offense {v}")
        print("\narmour (item id 34 up):")
        for i, r in enumerate(armour):
            v = armour_values(r)
            if not any(v) and arg != "--raw":
                continue
            print(f"  {i + ARMOUR_FIRST:3d} {names.get(i + ARMOUR_FIRST,''):<24s} "
                  f"defense {v}")

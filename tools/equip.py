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
5. add the flat bonuses: `[0x801b256a]` gives `+0x32` to offense rating 5,
   `[0x801b256e]` gives `+0x1e` to defense ratings 0, 1 and 2,
   `[0x801b2578]` gives `+5` to every working skill, and holding item `0x20`
   or `0x21` gives `+0x14` to `0x801b252a`.

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
out of the two records.
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
    """The disc, and the formula, against a RAM snapshot."""
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
    return bad == 0 and n == 2 * RATINGS


# What a RAM snapshot of the running game held: the equipped ids, and the
# sixteen ratings player_recalc_stats had left in memory. The port is checked
# against this rather than against tools/equip.py alone.
RECORDED = [
    {"weapon": 0, "worn": [255, 42, 255, 255, 255, 255, 255],
     "offense": [39, 32, 9, 0, 0, 0, 0, 0],
     "defense": [13, 6, 4, 0, 0, 0, 0, 0]},
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
            "recorded": RECORDED}
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

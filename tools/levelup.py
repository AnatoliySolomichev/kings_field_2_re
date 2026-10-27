#!/usr/bin/env python3
"""Experience, and what a level gives you.

    python3 tools/levelup.py            the table, and the model checked
    python3 tools/levelup.py 1 1000     what level 1 becomes after 1000 exp
    python3 tools/levelup.py --table    every level, in full
    python3 tools/levelup.py --game     the model against the game's own
                                        award_exp, over every level

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

Past level 99 the table stops and the routine goes on from the *difference*
between record 98 and **record 99** (`0x8002a45c`: `0x8009f5b8` is the table
plus 99 records) -- the twelve bytes after the table, which are zero on the
disc and in every snapshot. So each level past 99 takes 999 off both maxima
(wrapping as the halfwords they are), adds nothing to `+0x36` and a million
less to the threshold. *Withdrawn:* this said the step was the last two
records' (97 and 98), "growing by the last step again, forever"; it was read
one record short, and the game's own award_exp, run past the table, said so
(77 runs). Since the experience is capped at 999999 and record 98 asks for
1000000, none of it runs in an ordinary game.

Five more figures grow by a coin toss -- the **skills**, at `0x801b2518` to
`0x801b2520`: from the fifth down, for each one that is not already zero,
`rand() < 0x6665` adds one -- about four times in five. That is the only place
`rand` is used in levelling, and it is why two characters at the same level
are not the same character. (The model rolled them from the first up until
the game's own was run with a sequence of answers: the order decides which
skill a given roll goes to.)

Everything is then clamped to 999 (`0x3e7`), including the maxima, and
skill_unlock runs for each skill from the fifth down.

**The excellector grows** (`excellector_grow`, 0x8002a210, which award_exp calls with the
experience added and not yet capped). While the pack holds it in its first or
second form (items 0 and 1), the word at `0x801b24ec` -- -1 from
new_character -- is the experience it counts from: the first award takes the
experience then, and once the experience is more than **13000** (`0x32c8`)
past it, the one in hand (equipped weapon 0 or 1) is exchanged for the next
form by equip_weapon, the second form in the pack for the third and the first
for the second (take_item, give_item -- and with them the level's entries 11
and 6, `tools/givetake.py`), banner 4, and the word -1 again, so the next
13000 count from the next award. Holding neither, the word is -1. Every
snapshot past the first kill holds 11 there, the experience of the first
award (8 of 8); the 13 before it hold -1.

**How it is held to the game.** `--game` runs GAME.EXE's own award_exp with
`tools/mipsrun.py` over every level as its loader leaves it -- excellector_grow,
skill_unlock, has_item, take_item, give_item and the level's entries 6 and 11
running as the game's -- with the figures, the level (to 0xff, past the
table), the skills, the spells, the story flags, the pack, the weapon in
hand, the word and the award at random, rand answering a sequence and
announce, equip_weapon and player_recalc_stats logged: the model (award_exp,
at the game's addresses) must make the same calls, draw as many rolls and
leave the same RAM, all of it but the stack.
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


SKILL_THRESHOLDS = 0x80081884   # 12 bytes a skill: s16 thresholds, a 0 ends them
SKILL_UNLOCK_LIST = 0x800818C0  # 7 bytes a skill: spell numbers, 0xff ends them
SKILL_FLAG = 0x6D               # story_flags + 0x6d + k (0x801ba9f5): skills 0..3 unlock only once set
SKILL_UNLOCKED = 0x7B           # story_flags + 0x7b + k (0x801baa03): set when one of k's spells is
SPELLS = 96                     # spell_table's records; +0 is "unlocked"
FIRST_SPELL = 29                # light: new_character unlocks it by hand
LEVEL_UP, NEW_SPELL = 0, 3      # the banners award_exp and skill_unlock raise


def skill_data():
    """(thresholds, unlock lists) of the five skills, out of GAME.EXE."""
    import mips
    e = mips.load("game")
    th = [list(struct.unpack("<6h", e.bytes(SKILL_THRESHOLDS + 12 * k, 12))) for k in range(5)]
    ul = [list(e.bytes(SKILL_UNLOCK_LIST + 7 * k, 7)) for k in range(5)]
    return th, ul


def new_spells():
    """new_character's spell flags: all clear, then light (0x801b7aa4) set."""
    sp = [0] * SPELLS
    sp[FIRST_SPELL] = 1
    return sp


def skill_unlock(s, k, flags, data=None):
    """`skill_unlock` (0x80029f1c): for each threshold of skill k the skill has
    reached, the first spell not yet unlocked among the first (index + 1) of
    the skill's list is, with a "new spell" banner and story flag 0x7b + k.
    Skills 0..3 do nothing until story flag 0x6d + k is set. Returns the
    banners; `s["spells"]` and `flags` change in place."""
    th, ul = data or skill_data()
    out = []
    if k >= 5 or (k != 4 and not flags[SKILL_FLAG + k]):
        return out
    skill = s["grow"][k]
    for i, t in enumerate(th[k]):
        if skill < t or t == 0:
            break
        for j in range(i + 1):
            sp = ul[k][j]
            if sp == 0xFF:
                return out
            if not s["spells"][sp]:
                s["spells"][sp] = 1
                out.append(NEW_SPELL)
                flags[SKILL_UNLOCKED + k] = 1
                break
    return out


# --- award_exp whole, at the game's own addresses ---------------------------------

PLAYER_EXP, EXP_NEXT, EXCEL_MARK = 0x801B24E4, 0x801B24E8, 0x801B24EC
PLAYER_LEVEL, HP_MAX, MP_MAX = 0x801B24F0, 0x801B24FA, 0x801B24FE
STAT36, SKILLS = 0x801B2516, 0x801B2518
EQUIPPED_WEAPON = 0x801B25AF
LEVEL_TABLE = 0x8009F114
SPELL_TABLE, SPELL_STRIDE = 0x801B77EC, 24
STORY_FLAGS, USE_ANSWER = 0x801BA988, 0x801BA984
EXCEL_STEP = 0x32C8          # 13000 past the mark and the excellector grows, 0x8002a254
GROWN = 4                    # its banner, 0x8002a2e0
EXCELLECTOR = (0, 1, 2)      # its three forms, items 0, 1 and 2


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def excellector_grow(m, lv=None):
    """`excellector_grow`, 0x8002a210, which award_exp calls with the experience added and
    not yet capped: the excellector growing. Held in either form short of
    the last (0 or 1), the word at 0x801b24ec is the experience it counts
    from -- -1 (new_character's) takes the experience now; once the
    experience is more than 13000 past it, the excellector in hand (equipped
    weapon 0 or 1) is exchanged for the next form (equip_weapon), the second
    form in the pack for the third and the first for the second (take_item,
    give_item -- the level's entries 11 and 6 after), banner 4, and the word
    -1 again. Holding neither, -1."""
    import givetake
    if not (m.has(0) > 0 or m.has(1) > 0):
        m.wr(EXCEL_MARK, -1, 4)
        return
    mark = s32(m.rd(EXCEL_MARK, 4))
    if mark == -1:
        m.wr(EXCEL_MARK, m.rd(PLAYER_EXP, 4), 4)
        return
    if not s32(mark + EXCEL_STEP) < s32(m.rd(PLAYER_EXP, 4)):
        return
    w = m.rd(EQUIPPED_WEAPON)
    if w < 2:
        m.calls.append(("equip_weapon", (w + 1) & 0xFF))
    if m.has(1) > 0:
        givetake.take_item(lv, m, 1)
        givetake.give_item(lv, m, 2)
    if m.has(0) > 0:
        givetake.take_item(lv, m, 0)
        givetake.give_item(lv, m, 1)
    m.calls.append(("announce", GROWN))
    m.wr(EXCEL_MARK, -1, 4)


def _grow(m, rand):
    """The five skills, from 0x801b2520 down: one not at zero grows by one
    when rand() is below 0x6665."""
    for k in range(4, -1, -1):
        a = SKILLS + 2 * k
        if m.rd(a, 2) and s32(rand()) < GROW_ODDS:
            m.wr(a, m.rd(a, 2) + 1, 2)


def _skill_unlock(m, k, data):
    """skill_unlock (0x80029f1c) over the RAM: the dict form below, which
    tools/useitem.py holds to the game's own, over the skills, the spells'
    +0 and the story flags; each spell it unlocks says so (announce 3) and
    answers (use_answer 1)."""
    st = {"grow": [m.rd(SKILLS + 2 * i, 2) for i in range(5)],
          "spells": [m.rd(SPELL_TABLE + SPELL_STRIDE * i) for i in range(SPELLS)]}
    flags = [m.rd(STORY_FLAGS + i) for i in range(0x100)]
    before = (list(st["spells"]), list(flags))
    for b in skill_unlock(st, k, flags, data):
        m.calls.append(("announce", b))
        m.wr(USE_ANSWER, 1, 4)
    for i in range(SPELLS):
        if st["spells"][i] != before[0][i]:
            m.wr(SPELL_TABLE + SPELL_STRIDE * i, st["spells"][i])
    for i in range(0x100):
        if flags[i] != before[1][i]:
            m.wr(STORY_FLAGS + i, flags[i])


def award_exp(m, delta, rand, lv=None, data=None):
    """`award_exp` (0x8002a310) over the RAM `m` (tools/levelin.py's Mem):
    `delta` as the s16 it is taken as, `rand` what the game's rand answers,
    `lv` the level whose entry 6 give_item calls. The calls it makes that
    are not stores -- announce, equip_weapon, player_recalc_stats -- go to
    `m.calls`."""
    data = data or skill_data()
    m.wr(PLAYER_EXP, m.rd(PLAYER_EXP, 4) + s16(delta), 4)
    excellector_grow(m, lv)
    if s32(m.rd(PLAYER_EXP, 4)) > EXP_CAP:
        m.wr(PLAYER_EXP, EXP_CAP, 4)
    while s32(m.rd(PLAYER_EXP, 4)) >= s32(m.rd(EXP_NEXT, 4)):
        lb = m.rd(PLAYER_LEVEL)
        if lb >= LEVEL_CAP:
            return
        m.wr(PLAYER_LEVEL, lb + 1)
        if lb < TABLE_LEVELS:
            r = LEVEL_TABLE + RECORD * lb
            m.wr(HP_MAX, m.rd(r, 2), 2)
            m.wr(MP_MAX, m.rd(r + 2, 2), 2)
            m.wr(STAT36, m.rd(STAT36, 2) + m.rd(r + 4, 2), 2)
            _grow(m, rand)
            m.wr(EXP_NEXT, m.rd(r + 8, 4), 4)
        else:
            # 0x8002a45c: past the table, by the difference between the
            # record after the last (99, twelve zero bytes) and the last (98)
            last, prev = LEVEL_TABLE + RECORD * LEVELS, LEVEL_TABLE + RECORD * (LEVELS - 1)
            m.wr(HP_MAX, m.rd(HP_MAX, 2) + m.rd(last, 2) - m.rd(prev, 2), 2)
            m.wr(MP_MAX, m.rd(MP_MAX, 2) + m.rd(last + 2, 2) - m.rd(prev + 2, 2), 2)
            m.wr(STAT36, m.rd(STAT36, 2) + m.rd(last + 4, 2), 2)
            _grow(m, rand)
            m.wr(EXP_NEXT, m.rd(EXP_NEXT, 4) + m.rd(last + 8, 4) - m.rd(prev + 8, 4), 4)
        m.calls.append(("announce", LEVEL_UP))
        for a in (HP_MAX, MP_MAX, STAT36):
            if m.rd(a, 2) >= STAT_CAP + 1:
                m.wr(a, STAT_CAP, 2)
        for k in range(4, -1, -1):
            _skill_unlock(m, k, data)
            if m.rd(SKILLS + 2 * k, 2) >= STAT_CAP + 1:
                m.wr(SKILLS + 2 * k, STAT_CAP, 2)
        m.calls.append(("recalc",))


def _ram(data=None, beyond=None):
    """A blank RAM with what award_exp reads of the game's own laid in: the
    level table and the twelve bytes after it (record 99), the skills'
    thresholds and lists."""
    import levelin
    m = levelin.Mem(bytes(0x200000))
    t = table()
    for i, (hp, mp, gain, nxt) in enumerate(t + [beyond or after_table()]):
        r = LEVEL_TABLE + RECORD * i
        m.ram[r & 0x1FFFFF:(r & 0x1FFFFF) + RECORD] = struct.pack("<3HHI", hp, mp, gain, 0, nxt)
    th, ul = data or skill_data()
    for k in range(5):
        a = (SKILL_THRESHOLDS + 12 * k) & 0x1FFFFF
        m.ram[a:a + 12] = struct.pack("<6h", *th[k])
        a = (SKILL_UNLOCK_LIST + 7 * k) & 0x1FFFFF
        m.ram[a:a + 7] = bytes(ul[k])
    return m


def after_table(path=FDAT):
    """Record 99, the twelve bytes after the table, which award_exp reads
    past level 99: (hp, mp, gain, next) -- all zero on the disc and in every
    snapshot."""
    raw = TArc(path).raw(ENTRY)
    o = OFFSET + RECORD * LEVELS
    hp, mp, gain = struct.unpack_from("<3H", raw, o)
    return hp, mp, gain, struct.unpack_from("<I", raw, o + 8)[0]


def award(state, delta, rng=None, flags=None, data=None, lv=None):
    """`award_exp` on a dict of the player's figures, through award_exp
    above over a RAM made of them.

    `state` wants `exp`, `exp_next`, `level`, `hp_max`, `mp_max`, `stat36` and
    `grow` (five numbers); `spells` (the 96 flags) with `flags` the story
    flags for skill_unlock; and for the excellector `excel` (the word at
    0x801b24ec), `weapon` (the one in hand) and `pack` ({item: [count in
    the first array, count in the second]}). `rng` is called for each roll
    and answers what the game's rand would, 0..0x7fff; without one the rolls
    all succeed. What comes back has the figures after, `banners` (what was
    announced, in order), `equip` (the weapon equip_weapon was given, or
    None) and `rolls` (how many were drawn)."""
    import levelin
    m = _ram(data)
    s = dict(state)
    m.wr(PLAYER_EXP, s["exp"], 4)
    m.wr(EXP_NEXT, s["exp_next"], 4)
    m.wr(EXCEL_MARK, s.get("excel", -1), 4)
    m.wr(PLAYER_LEVEL, s["level"])
    m.wr(HP_MAX, s["hp_max"], 2)
    m.wr(MP_MAX, s["mp_max"], 2)
    m.wr(STAT36, s["stat36"], 2)
    for k in range(5):
        m.wr(SKILLS + 2 * k, s["grow"][k], 2)
    m.wr(EQUIPPED_WEAPON, s.get("weapon", 0xFF))
    spells = s.get("spells")
    for i in range(SPELLS):
        m.wr(SPELL_TABLE + SPELL_STRIDE * i, spells[i] if spells else 1)
    for i, v in enumerate(flags or []):
        m.wr(STORY_FLAGS + i, v)
    for item, (a, b) in (s.get("pack") or {}).items():
        m.wr(levelin.INV_A + item, a)
        m.wr(levelin.INV_B + item, b)
    drawn = [0]

    def rand():
        drawn[0] += 1
        return rng() if rng else 0
    award_exp(m, delta, rand, lv, data)
    s["exp"] = s32(m.rd(PLAYER_EXP, 4))
    s["exp_next"] = s32(m.rd(EXP_NEXT, 4))
    s["excel"] = s32(m.rd(EXCEL_MARK, 4))
    s["level"] = m.rd(PLAYER_LEVEL)
    s["hp_max"], s["mp_max"], s["stat36"] = m.rd(HP_MAX, 2), m.rd(MP_MAX, 2), m.rd(STAT36, 2)
    s["grow"] = [m.rd(SKILLS + 2 * k, 2) for k in range(5)]
    if spells:
        s["spells"] = [m.rd(SPELL_TABLE + SPELL_STRIDE * i) for i in range(SPELLS)]
    if flags is not None:
        flags[:] = [m.rd(STORY_FLAGS + i) for i in range(len(flags))]
    if "pack" in s:
        s["pack"] = {item: [m.rd(levelin.INV_A + item), m.rd(levelin.INV_B + item)]
                     for item in s["pack"]}
    s["banners"] = [c[1] for c in m.calls if c[0] == "announce"]
    s["equip"] = next((c[1] for c in m.calls if c[0] == "equip_weapon"), None)
    s["rolls"] = drawn[0]
    return s


# use_item's arms for the things that raise a figure -- verdite, the fruits
# and the crystals -- are tools/useitem.py's now, with the rest of the routine
# and held to the game's own.


def check_spells(out=sys.stdout):
    """The spells each snapshot has unlocked, against new_character's light
    and skill_unlock run over its five skills: what a character that only
    levelled has."""
    import glob
    data = skill_data()
    ok = n = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        ram = open(path, "rb").read()
        skills = list(struct.unpack_from("<5H", ram, 0x1B2518))
        if not any(skills):
            continue
        flags = list(ram[0x1BA988:0x1BA988 + 0x100])
        s = {"grow": skills, "spells": new_spells()}
        for k in range(4, -1, -1):
            skill_unlock(s, k, flags, data)
        live = [ram[(0x801B77EC + 24 * i) & 0x1FFFFF] for i in range(SPELLS)]
        n += 1
        ok += s["spells"] == live
        if s["spells"] != live:
            print(f"  {os.path.basename(path)}: skills {skills}: the model unlocks "
                  f"{[i for i, v in enumerate(s['spells']) if v]}, RAM has "
                  f"{[i for i, v in enumerate(live) if v]}", file=out)
    print(f"{ok} of {n} snapshots have unlocked the spells skill_unlock leaves "
          f"a new character with their skills", file=out)
    return ok == n


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
    th, ul = skill_data()
    path = os.path.join(out_dir, "levels.json")
    with open(path, "w") as fh:
        json.dump({"_note": f"FDAT.T entry {ENTRY} at offset {OFFSET}, "
                            f"{LEVELS} records of {RECORD} bytes; "
                            "tools/levelup.py wrote it",
                   "exp_cap": EXP_CAP, "stat_cap": STAT_CAP,
                   "grow_odds": GROW_ODDS, "levels": rows,
                   # GAME.EXE 0x80081884 and 0x800818c0, for skill_unlock
                   "skills": {"thresholds": th, "unlock": ul},
                   # record 99, the twelve bytes after the table, which
                   # award_exp reads past level 99
                   "beyond": dict(zip(("hp", "mp", "gain", "next"), after_table()))}, fh,
                  separators=(",", ":"))
    return path


def cases(out_dir, n=60, seed=67):
    """Cases for the port to reproduce, written where selftest.gd reads them:
    award over random figures, skills, spells, story flags, the pack's
    excellector and the things the levels' entry 6 asks, the weapon in
    hand, the excellector's word and a level, with the rolls given -- the
    rolls the game's rand would answer, which the port takes in place of
    its own. The model is held to the game's own award_exp (check_game)."""
    import json
    import random
    rng = random.Random(seed)
    data = skill_data()
    t = table()
    rows = []
    for k in range(n):
        lb = rng.choice((rng.randrange(1, 99), rng.randrange(1, 99), 0x62, 0x63, 0x64, 0xFE))
        nxt = t[min(lb, LEVELS) - 1][3]
        if lb >= TABLE_LEVELS and rng.random() < 0.7:
            nxt = rng.randrange(0, 900000)          # past the table, a threshold it can reach
        exp = rng.choice((nxt - 1, nxt - rng.randrange(1, 3000), nxt + rng.randrange(0, 50000),
                          EXP_CAP - rng.randrange(0, 40), 0))
        st = {"exp": exp, "exp_next": nxt, "level": lb,
              "hp_max": rng.choice((rng.randrange(1000), 999)),
              "mp_max": rng.choice((rng.randrange(1000), 999)),
              "stat36": rng.choice((rng.randrange(1000), 998, 999)),
              "grow": [rng.choice((0, 0, 9, 10, 19, 20, 34, 35, 998, rng.randrange(1000)))
                       for _ in range(5)],
              "spells": [rng.choice((0, 0, 1)) for _ in range(SPELLS)],
              "excel": rng.choice((-1, -1, 0, 11, exp - EXCEL_STEP - rng.randrange(-3, 4))),
              "weapon": rng.choice((0, 1, 2, 3, 0xFF)),
              "pack": {i: [rng.choice((0, 0, 1, 2, 0x63)), rng.choice((0, 0, 1, 0x63))]
                       for i in EXCELLECTOR + (0x85, 0x64, 0x4B, 0x83)}}
        flags = [0] * 0x100
        for f in list(range(0x6D, 0x72)) + list(range(0x7B, 0x80)) + [7, 0x11, 0x24]:
            flags[f] = rng.choice((0, 0, 1))
        lv = rng.choice((0, 2, 6, rng.randrange(28)))
        delta = rng.choice((rng.randrange(1, 300), rng.randrange(0x8000), rng.randrange(0x10000), 0))
        rolls = [rng.randrange(0x8000) for _ in range(2000)]
        it = iter(rolls)
        before = {key: (list(v) if isinstance(v, list) else
                        {str(i): list(c) for i, c in v.items()} if isinstance(v, dict) else v)
                  for key, v in st.items()}
        after_flags = list(flags)
        after = award(st, delta, lambda: next(it), after_flags, data, lv)
        rows.append({"state": before, "flags": flags, "level": lv, "award": delta,
                     "rolls": rolls[:after["rolls"]],
                     "want": {"exp": after["exp"], "exp_next": after["exp_next"],
                              "level": after["level"], "hp_max": after["hp_max"],
                              "mp_max": after["mp_max"], "stat36": after["stat36"],
                              "grow": after["grow"], "spells": after["spells"],
                              "excel": after["excel"], "banners": after["banners"],
                              "equip": -1 if after["equip"] is None else after["equip"],
                              "rolls": after["rolls"], "flags": after_flags,
                              "pack": {str(i): c for i, c in after["pack"].items()}}})
    path = os.path.join(out_dir, "levelcheck.json")
    with open(path, "w") as fh:
        json.dump(rows, fh, separators=(",", ":"))
    return path


# --- against the game's own ---------------------------------------------------

AWARD_EXP, RAND = 0x8002A310, 0x800796C0
ANNOUNCE, EQUIP_WEAPON, RECALC = 0x80041EEC, 0x8002BDC0, 0x80029500


def game_run(cpu, delta, rolls):
    """GAME.EXE's own award_exp over the machine's RAM -- excellector_grow,
    skill_unlock, has_item, take_item and give_item (and the level's own
    entries 6 and 11 out of its overlay) run as the game's; rand answers
    `rolls` in turn, announce, equip_weapon and player_recalc_stats logged:
    [the calls], the number of rolls drawn."""
    calls = []
    drawn = [0]

    def rand(c):
        drawn[0] += 1
        return rolls[drawn[0] - 1]
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks.update({
        RAND: rand,
        ANNOUNCE: lambda c: calls.append(("announce", c.r[4])),
        EQUIP_WEAPON: lambda c: calls.append(("equip_weapon", c.r[4])),
        RECALC: lambda c: calls.append(("recalc",)),
    })
    cpu.call(AWARD_EXP, delta & 0xFFFF)
    return calls, drawn[0]


def game_cases(lv, n, rng, snap="a1"):
    """`n` runs on level `lv`: [(the machine, the award, the rolls)], the
    player's figures, skills, spells, flags, pack, weapon and the
    excellector's word laid out at random."""
    import mipsrun
    import useitem
    import levelin
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    t = table()
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        lb = rng.choice((rng.randrange(1, 99), rng.randrange(1, 99), 0x62, 0x63, 0x64,
                         0xFE, 0xFF, rng.randrange(0x100)))
        nxt = t[min(lb, LEVELS) - 1][3] if lb else 50
        nxt = rng.choice((nxt, nxt, rng.randrange(-1000, 1000000), 0x7FFFFFFF))
        exp = rng.choice((nxt - 1, nxt - rng.randrange(1, 3000), nxt + rng.randrange(0, 50000),
                          rng.randrange(0, 1000000), EXP_CAP - rng.randrange(0, 40), 0))
        put(cpu, PLAYER_EXP, 4, exp)
        put(cpu, EXP_NEXT, 4, nxt)
        put(cpu, PLAYER_LEVEL, 1, lb)
        for a in (HP_MAX, MP_MAX, STAT36):
            put(cpu, a, 2, rng.choice((rng.randrange(1000), 997, 998, 999, 1000,
                                       rng.randrange(0x10000))))
        for k in range(5):
            put(cpu, SKILLS + 2 * k, 2, rng.choice((0, 0, 9, 10, 19, 20, 34, 35, 49, 50, 84, 85,
                                                    114, 115, 998, 999, rng.randrange(1000),
                                                    rng.randrange(0x10000))))
        for i in range(SPELLS):
            put(cpu, SPELL_TABLE + SPELL_STRIDE * i, 1, rng.choice((0, 0, 1)))
        for k in list(range(0x6D, 0x72)) + list(range(0x7B, 0x80)) + [7, 0x11, 0x24]:
            put(cpu, STORY_FLAGS + k, 1, rng.choice((0, 0, 1, rng.randrange(0x100))))
        put(cpu, USE_ANSWER, 4, rng.choice((0, 1, rng.randrange(1 << 32))))
        for item in EXCELLECTOR + (0x85, 0x64, 0x4B, 0x83):
            for arr in (levelin.INV_A, levelin.INV_B):
                put(cpu, arr + item, 1, rng.choice((0, 0, 0, 1, 2, 0x62, 0x63, rng.randrange(0x100))))
        put(cpu, EQUIPPED_WEAPON, 1, rng.choice((0, 1, 2, 3, 0xFF, rng.randrange(0x100))))
        put(cpu, EXCEL_MARK, 4, rng.choice((-1, -1, 0, 11, exp - EXCEL_STEP - rng.randrange(-3, 4),
                                            rng.randrange(1 << 32))))
        delta = rng.choice((rng.randrange(1, 300), rng.randrange(0x8000), rng.randrange(0x10000),
                            0, 1))
        rolls = [rng.randrange(0x8000) for _ in range(2000)]
        out.append((cpu, delta, rolls))
    return out


def compare(cpu, lv, delta, rolls):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    import levelin
    m = levelin.Mem(bytes(cpu.ram))
    it = iter(rolls)
    drawn = [0]

    def rand():
        drawn[0] += 1
        return next(it)
    award_exp(m, delta, rand, lv)
    got, n = game_run(cpu, delta, rolls)
    what = (lv, tuple(c[0] if c[0] != "announce" else c for c in m.calls))
    if (m.calls, drawn[0]) != (got, n):
        return what, f"calls: model {m.calls} ({drawn[0]} rolls), game {got} ({n})"
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, levelin.STACK_LO), (levelin.STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x}"
    return what, None


def check_game(out=sys.stdout, per_level=30, seed=61, verbose=False):
    """The model against the game's own award_exp on every level."""
    import random
    rng = random.Random(seed)
    ok = n = 0
    told = False
    count = {"levels": 0, "grown": 0, "spells": 0, "refused": 0, "past": 0, "equip": 0}
    for lv in range(28):
        try:
            runs = game_cases(lv, per_level, rng)
        except Exception as e:                                     # noqa: BLE001
            print(f"  level {lv}: no machine ({e})", file=out)
            continue
        for cpu, delta, rolls in runs:
            n += 1
            past = cpu.rd(PLAYER_LEVEL, 1) >= TABLE_LEVELS
            what, why = compare(cpu, lv, delta, rolls)
            if why is None:
                ok += 1
                calls = what[1]
                count["levels"] += sum(1 for c in calls if c == ("announce", LEVEL_UP))
                count["grown"] += sum(1 for c in calls if c == ("announce", GROWN))
                count["spells"] += sum(1 for c in calls if c == ("announce", NEW_SPELL))
                count["refused"] += sum(1 for c in calls if c == ("announce", 0xB))
                count["equip"] += sum(1 for c in calls if c == "equip_weapon")
                count["past"] += past and ("announce", LEVEL_UP) in calls
            elif not told or verbose:
                told = True
                print(f"  level {lv}, award {delta:#x}: {why}", file=out)
    print(f"  {count['levels']} levels taken ({count['past']} runs past the table), "
          f"{count['spells']} spells unlocked, the excellector grown {count['grown']} times "
          f"({count['equip']} in hand, {count['refused']} with no room for it)", file=out)
    print(f"award_exp, against the game's own with excellector_grow and skill_unlock on every "
          f"level: {ok} of {n} runs agree -- the calls, the rolls drawn and all of RAM but "
          f"the stack", file=out)
    return ok == n


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
    if not check_spells(out):
        seen += 1                       # a failure the caller's count will show
    if not check_excellector(out):
        seen += 1
    return ok, seen


def check_excellector(out=sys.stdout):
    """The excellector's word (0x801b24ec) in every snapshot with a player:
    -1 before the first award, after it the experience of an award at most
    13000 behind -- consistent with excellector_grow, not a proof of it."""
    import glob
    ok = n = took = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        ram = open(path, "rb").read()
        exp, nxt, mark = struct.unpack_from("<iii", ram, PLAYER_EXP & 0x1FFFFF)
        if nxt == 0:
            continue                    # no player in it (probe)
        held = any(ram[(a + i) & 0x1FFFFF] for a in (0x800C85E8, 0x800C867E) for i in (0, 1))
        n += 1
        if not held:
            good = mark == -1
        elif exp == 0:
            good = mark == -1
        else:
            good = 0 <= mark <= exp and exp <= mark + EXCEL_STEP
            took += good
        ok += good
        if not good:
            print(f"  {os.path.basename(path)}: experience {exp}, the word {mark}", file=out)
    print(f"{ok} of {n} snapshots hold the excellector's word excellector_grow leaves "
          f"({n - took} before the first award, -1; {took} after it, the experience then)",
          file=out)
    return ok == n


if __name__ == "__main__":
    argv = sys.argv[1:]
    t = table()
    if argv and argv[0] == "--game":
        sys.exit(0 if check_game(verbose="-v" in argv) else 1)
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
        ok, seen = check()
        sys.exit(0 if ok == seen else 1)

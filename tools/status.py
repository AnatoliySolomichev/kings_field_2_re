#!/usr/bin/env python3
"""What a hit leaves behind besides the damage: the seven effects, and what
the armour and the rings make of them.

    python3 tools/status.py --check      the model against the game's own
                                         player_take_hit, run over every
                                         snapshot by tools/mipsrun.py

`player_take_hit` (`0x8002ab18`) is given eight attacks and an effect
(tools/damage.py has the arithmetic). Before any of it, two things let
nothing through at all: `0x801b25b4` set, and the timer `0x801b256c`
running. Then the five durations the effects use start at

```
paralysis   0xc8     0x801b2568            effect 4
poison      0x384    0x801b255c            effect 3, if the roll goes against
darkness    0xa8c    0x801b2564            effect 2
curse       0x546    0x801b2560            effect 1
slowing     0x1c2    0x801b2566            effect 5, turn_slow_timer
```

and what is worn cuts them, in this order (`0x8002abc4`..`0x8002ad04`) --
the worn bytes are `0x801b25d4` head, `d5` body, `d6` shield, `d7` arms,
`d8` feet, `d9` and `da` the two items:

```
silver arms (0x41)          paralysis = 0x96
silver boots (0x4a)         poison = 0x2a3
groundal boots (0x4c)       paralysis >>= 1, darkness 0x546, curse 0x2a3,
                            slowing 0xe1
silver ring (0x53)          poison >>= 2                     either item
gold ring (0x56)            paralysis >>= 2                  either item
globe amulet (0x58)         darkness, curse, slowing >>= 1   either item
luster wing (0x5b)          darkness, curse, slowing >>= 2   either item
ichrius' helm (0x29)        darkness, curse, slowing >>= 2
ichrius' boots (0x4f)       paralysis, poison >>= 2
```

and some of it takes attacks away (`0x8002ad08`..`0x8002aea8`), each `rand`
drawn only when the piece is worn:

```
fire mail (0x2d)            the fire attack
dragon head (0x27)          slash, blow, stab, one time in four (rand < 0x2000)
the promeus five            slash, blow, stab: helm 0x28, armor 0x2f,
                            shield 0x3b, hands 0x45 (the word at 0x801b25d4
                            is 0x453b2f28) and boots 0x4e
groundal mail (0x30)        slash, blow, stab, one in four
ichrius' armor (0x31)       slash, blow, stab, one in four
groundal shield (0x3a)      the five magic attacks, one in four
ichrius' shield (0x3c)      the five magic attacks, one in four
ebony bracelet (0x55)       the five magic attacks, one in two; either item
```

Then the effect's low nibble, off the table at `0x800117a8`:

```
1  the curse: 0x801b255e = 1, 0x801b2560 = curse, player_recalc_stats --
   before the damage, so a cursing hit meets the halved defence already
2  darkness: 0x801b2564 = darkness, and 0x801b2572 = 0 puts the light out
3  poison: (100 * rand()) >> 15 above the resistance 0x801b255a, and
   0x801b255c = poison
4  paralysis: 0x801b2568 = paralysis
5  slowing: turn_slow_timer = slowing
6  MP loses a sixteenth of its most (to 0)
7  the poison cured
```

and the damage goes to `apply_damage` with the whole effect.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import damage                                                        # noqa: E402
import equip                                                         # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MASK = 0x1FFFFF

TAKE_HIT = 0x8002AB18
APPLY_DAMAGE = 0x8002A6F4
RECALC = 0x80029500
RAND = 0x800796C0

GUARD = 0x801B25B4           # a byte: set, a hit takes nothing
SHIELDED = 0x801B256C        # a half: running, a hit takes nothing
WORN = 0x801B25D4            # seven bytes: head, body, shield, arms, feet, items
RESIST = 0x801B255A
POISON = 0x801B255C
CURSE_LV, CURSE_T = 0x801B255E, 0x801B2560
DARK_LV, DARK_T = 0x801B2562, 0x801B2564
SLOW = 0x801B2566
PARALYSIS = 0x801B2568
LIGHT_LV, LIGHT_T = 0x801B2570, 0x801B2572
MP_MAX, MP = 0x801B24FE, 0x801B2500
DEFENCE = 0x801B254A
STAT = 0x801B2524
SCALE_K = 0x801B24F8

PROMEUS = (0x28, 0x2F, 0x3B, 0x45)   # head, body, shield, arms; and boots 0x4e

# What the check varies and compares: (name, address, size, signed)
FIELDS = (("poison", POISON, 2), ("curse_lv", CURSE_LV, 2), ("curse_t", CURSE_T, 2),
          ("dark_lv", DARK_LV, 2), ("dark_t", DARK_T, 2), ("slow", SLOW, 2),
          ("paralysis", PARALYSIS, 2), ("light_lv", LIGHT_LV, 2),
          ("light_t", LIGHT_T, 2), ("mp", MP, 2))


def u16(ram, a):
    return struct.unpack_from("<H", ram, a & MASK)[0]


def s16(ram, a):
    return struct.unpack_from("<h", ram, a & MASK)[0]


def state_of(ram):
    """What player_take_hit reads and writes, out of RAM."""
    st = {k: u16(ram, a) for k, a, _n in FIELDS}
    st.update({
        "worn": list(ram[WORN & MASK:(WORN & MASK) + 7]),
        "guard": ram[GUARD & MASK], "shielded": s16(ram, SHIELDED),
        "resist": u16(ram, RESIST), "mp_max": u16(ram, MP_MAX),
        "defence": [u16(ram, DEFENCE + 2 * i) for i in range(8)],
        "stat": u16(ram, STAT), "k": s16(ram, SCALE_K),
        "recalc": equip.state_of(ram)})
    return st


def durations(worn):
    """[paralysis, poison, darkness, curse, slowing] as what is worn leaves
    them (0x8002abb4..0x8002ad04)."""
    head, _body, _shield, arms, feet, i1, i2 = worn
    para, poison, dark, curse, slow = 0xC8, 0x384, 0xA8C, 0x546, 0x1C2
    if arms == 0x41:
        para = 0x96
    if feet == 0x4A:
        poison = 0x2A3
    if feet == 0x4C:
        para >>= 1
        dark, curse, slow = 0x546, 0x2A3, 0xE1
    if 0x53 in (i1, i2):
        poison >>= 2
    if 0x56 in (i1, i2):
        para >>= 2
    if 0x58 in (i1, i2):
        dark, curse, slow = dark >> 1, curse >> 1, slow >> 1
    if 0x5B in (i1, i2):
        dark, curse, slow = dark >> 2, curse >> 2, slow >> 2
    if head == 0x29:
        dark, curse, slow = dark >> 2, curse >> 2, slow >> 2
    if feet == 0x4F:
        para >>= 2
        poison >>= 2
    return [para, poison, dark, curse, slow]


def shield(worn, attacks, rand):
    """The attacks after what is worn takes some away (0x8002ad08..
    0x8002aea8); `rand` is drawn exactly where the game draws it."""
    head, body, shld, arms, feet, i1, i2 = worn
    a = list(attacks)
    if body == 0x2D:                              # fire mail
        a[4] = 0
    if head == 0x27 and rand() < 0x2000:          # dragon head
        a[0] = a[1] = a[2] = 0
    if (head, body, shld, arms) == PROMEUS and feet == 0x4E:
        a[0] = a[1] = a[2] = 0
    if body == 0x30 and rand() < 0x2000:          # groundal mail
        a[0] = a[1] = a[2] = 0
    if body == 0x31 and rand() < 0x2000:          # ichrius' armor
        a[0] = a[1] = a[2] = 0
    if shld == 0x3A and rand() < 0x2000:          # groundal shield
        a[3:8] = [0] * 5
    if shld == 0x3C and rand() < 0x2000:          # ichrius' shield
        a[3:8] = [0] * 5
    if 0x55 in (i1, i2) and rand() < 0x4000:      # ebony bracelet
        a[3:8] = [0] * 5
    return a


def take_hit(st, attacks, effect, scale, pct, rand):
    """player_take_hit on `st` (state_of's dict, changed in place): None when
    nothing gets through, else the damage apply_damage is handed. `attacks`
    is slash, blow, stab, dark, fire, earth, wind, water."""
    if st["guard"] or st["shielded"]:
        return None
    para, poison, dark, curse, slow = durations(st["worn"])
    a = shield(st["worn"], attacks, rand)
    e = effect & 0xF
    if e == 1:
        st["curse_t"] = curse
        st["curse_lv"] = 1
        r = equip.recalc(dict(st["recalc"], curse=1))
        st["defence"] = r["defense"]
        st["stat"] = r["stat"]
        st["recalced"] = r
    elif e == 2:
        st["dark_t"] = dark
        st["light_t"] = 0
    elif e == 3:
        if st["resist"] < (100 * rand()) >> 15:
            st["poison"] = poison
    elif e == 4:
        st["paralysis"] = para
    elif e == 5:
        st["slow"] = slow
    elif e == 6:
        cut = st["mp_max"] >> 4
        st["mp"] = st["mp"] - cut if cut < st["mp"] else 0
    elif e == 7:
        st["poison"] = 0
    base = sum(damage.of_type(a[i], st["defence"][i], st["stat"], st["k"])
               for i in range(8))
    s1 = _s32(scale * base + 0x8000) >> 16
    v = _s32(pct * s1)
    return -(-v // 10) if v < 0 else v // 10


def _s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def _cases(rng, n):
    """Hits that take every branch: what is worn drawn from the pieces the
    routine tests (and nothing), the full promeus set now and then, every
    effect, the two ways out."""
    pieces = [[0x27, 0x28, 0x29, 0x26], [0x2D, 0x2F, 0x30, 0x31, 0x2A],
              [0x3A, 0x3B, 0x3C, 0x33], [0x41, 0x45, 0x3F],
              [0x4A, 0x4C, 0x4E, 0x4F, 0x48],
              [0x53, 0x55, 0x56, 0x58, 0x5B, 0x52], [0x53, 0x55, 0x56, 0x58, 0x5B, 0x51]]
    out = []
    for i in range(n):
        worn = [rng.choice(p + [0xFF, 0xFF]) for p in pieces]
        if rng.randrange(8) == 0:
            worn[:5] = list(PROMEUS) + [0x4E]
        attacks = [rng.choice((0, 0, rng.randrange(1, 120), rng.randrange(1, 400)))
                   for _ in range(8)]
        out.append({
            "worn": worn, "attacks": attacks,
            "effect": rng.randrange(0x10) | rng.choice((0, 0, 0x40, 0x80, 0x10)),
            "scale": rng.choice((0x1000, 0x1000, rng.randrange(0x400, 0x1001))),
            "pct": rng.choice((10, 10, rng.randrange(1, 20))),
            "guard": 1 if rng.randrange(16) == 0 else 0,
            "shielded": rng.randrange(1, 300) if rng.randrange(16) == 0 else 0,
            "resist": rng.choice((0, 5, 25, 50, 75, rng.randrange(0, 101))),
            "mp": rng.randrange(0, 200), "mp_max": rng.randrange(0, 200),
            "fields": {k: rng.choice((0, 0, rng.randrange(1, 0x900)))
                       for k, _a, _n in FIELDS if k != "mp"},
            "seed": rng.randrange(1 << 31)})
    return out


def _lay(ram, c):
    """A case's state written into a snapshot's RAM."""
    ram[WORN & MASK:(WORN & MASK) + 7] = bytes(c["worn"])
    ram[GUARD & MASK] = c["guard"]
    struct.pack_into("<h", ram, SHIELDED & MASK, c["shielded"])
    struct.pack_into("<H", ram, RESIST & MASK, c["resist"])
    struct.pack_into("<H", ram, MP & MASK, c["mp"])
    struct.pack_into("<H", ram, MP_MAX & MASK, c["mp_max"])
    for k, a, _n in FIELDS:
        if k in c["fields"]:
            struct.pack_into("<H", ram, a & MASK, c["fields"][k])


def run_game(ram, c):
    """The game's own player_take_hit over `ram` for one case: (the state it
    leaves, apply_damage's damage and effect or None, the rand draws)."""
    import levelstate
    import mipsrun
    cpu = mipsrun.CPU(ram)
    lcg = levelstate.Lcg(c["seed"])
    draws = []

    def rnd(_c):
        v = lcg()
        draws.append(v)
        return v
    cpu.hooks[RAND] = rnd
    got = []
    cpu.hooks[APPLY_DAMAGE] = lambda c2: got.append((mipsrun.s32(c2.r[5]), c2.r[6] & 0xFFFF))
    a = c["attacks"]
    point = 0x801FF100
    cpu.call(TAKE_HIT, a[0], a[1], a[2], c["effect"], a[3], a[4], a[5], a[6], a[7],
             c["scale"], c["pct"], point)
    after = state_of(cpu.ram)
    return after, (got[0] if got else None), draws


def run_model(ram, c):
    import levelstate
    st = state_of(ram)
    lcg = levelstate.Lcg(c["seed"])
    draws = []

    def rnd():
        v = lcg()
        draws.append(v)
        return v
    dmg = take_hit(st, c["attacks"], c["effect"], c["scale"], c["pct"], rnd)
    return st, (None if dmg is None else (dmg, c["effect"] & 0xFFFF)), draws


def check(out=sys.stdout, per=40):
    """take_hit against player_take_hit over every snapshot of a game."""
    import random
    import memcard
    rng = random.Random(0x7A4E417)
    n = ok = calls = 0
    first = None
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        if not any(base[(0x801B2524 & MASK):(0x801B2524 & MASK) + 2]):
            continue                                   # no character
        for c in _cases(rng, per):
            ram = bytearray(base)
            _lay(ram, c)
            g_st, g_hit, g_draws = run_game(ram, c)
            m_st, m_hit, m_draws = run_model(ram, c)
            keys = [k for k, _a, _n in FIELDS] + ["defence", "stat"]
            same = (all(g_st[k] == m_st[k] for k in keys) and g_hit == m_hit
                    and g_draws == m_draws)
            n += 1
            calls += g_hit is not None
            ok += same
            if not same and first is None:
                diff = [k for k in keys if g_st[k] != m_st[k]]
                first = (f"{os.path.basename(path)} worn {[hex(w) for w in c['worn']]} "
                         f"effect {c['effect']:#x}: fields {diff}, game hit {g_hit} "
                         f"model {m_hit}, draws {len(g_draws)}/{len(m_draws)}")
    print(f"player_take_hit: {ok} of {n} hits as the game's own takes them "
          f"({calls} reaching apply_damage), the status, the damage and the rand "
          f"draws", file=out)
    if first:
        print("  first difference: " + first, file=out)
    return ok == n


def export(out_dir, n=300):
    """Cases and what the model makes of them, for godot/selftest.gd. The
    state is a fresh character's (out/snap/b.ram) with each case laid in."""
    import json
    import levelstate
    import random
    path = os.path.join(ROOT, "out", "snap", "b.ram")
    if not os.path.exists(path):
        return None
    base = bytearray(open(path, "rb").read())
    rng = random.Random(0x5747)
    rows = []
    for c in _cases(rng, n):
        ram = bytearray(base)
        _lay(ram, c)
        st = state_of(ram)
        lcg = levelstate.Lcg(c["seed"])
        draws = []

        def rnd():
            v = lcg()
            draws.append(v)
            return v
        before = {k: st[k] for k, _a, _n in FIELDS}
        dmg = take_hit(st, c["attacks"], c["effect"], c["scale"], c["pct"], rnd)
        rows.append({"worn": c["worn"], "attacks": c["attacks"], "effect": c["effect"],
                     "scale": c["scale"], "pct": c["pct"], "guard": c["guard"],
                     "shielded": c["shielded"], "resist": c["resist"],
                     "mp_max": c["mp_max"], "before": before, "draws": draws,
                     "after": {k: st[k] for k, _a, _n in FIELDS},
                     "damage": -1 if dmg is None else dmg})
    st0 = state_of(base)
    out = os.path.join(out_dir, "takehit.json")
    with open(out, "w") as fh:
        json.dump({"_note": "player_take_hit's cases as tools/status.py takes them, "
                            "over a fresh character (out/snap/b.ram); draws are "
                            "the rand values in the order drawn",
                   "defence": st0["defence"], "stat": st0["stat"], "k": st0["k"],
                   "recalc": st0["recalc"], "hits": rows},
                  fh, separators=(",", ":"))
    return out


# --- what is left running: sub_80030e14, once a frame ------------------------

STATUS_TICK = 0x80030E14
TINTS = 0x801AEAFE           # two of 8 bytes: count, mode, r, g, b (s16)
TILE_LOOK = 0x801AEEFC       # the lighting records, 0x6c each
LIT = 48                     # how many sub_800344dc blends
FLASH, FLASH_STEP = 0x801B2658, 0x801B265A
TINT_DEFAULT = bytes([0, 1, 0, 0, 0, 0, 0, 0]) * 2     # render_flags_reset's
TICK_FIELDS = ("dark_lv", "dark_t", "light_lv", "light_t", "curse_lv", "curse_t",
               "flash", "flash_step")
TICK_AT = {"dark_lv": DARK_LV, "dark_t": DARK_T, "light_lv": LIGHT_LV,
           "light_t": LIGHT_T, "curse_lv": CURSE_LV, "curse_t": CURSE_T,
           "flash": FLASH, "flash_step": FLASH_STEP}


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def ramp(lv, t, most, scale):
    """sub_80030b24 on (level, timer): (level, timer, the intensity) -- -1,
    and nothing written, once both are 0. The level climbs a frame at a time
    while it is under the timer; there the timer is zeroed and it falls back,
    so an effect of timer T lasts about 2T frames. The intensity is
    level * scale / most, and scale itself from `most` up."""
    if _s16(lv) == 0 and t & 0xFFFF == 0:
        return lv, t, -1
    if _s16(lv) < _s16(t):
        lv = (lv + 1) & 0xFFFF
    else:
        t = 0
        lv = (lv - 1) & 0xFFFF
    v = _s16(lv)
    if v < most:
        p = _s32(v * scale)
        v = -(-p // most) if p < 0 else p // most
    else:
        v = scale
    return lv, t, _s16(v)


def tint(tints, mode, rgb, k, add):
    """sub_8003d8ec (add) and sub_8003da10 (set) on render_frame's two
    records: mode 1 is drawn adding, 2 subtracting; the count is how many
    asked, and the colour drawn is the sum over it."""
    rec = tints[mode - 1]
    rec[0] = (rec[0] + 1) & 0xFF
    rec[1] = mode
    for i, c in enumerate(rgb):
        d = _s32(c * k) >> 12
        rec[2 + i] = _s16((rec[2 + i] if add else 0) + d)


def light_blend(look, rgb, near, far, k):
    """sub_8003456c over the first 48 lighting records (sub_800344dc,
    sub_80034394): each of the background colour, the near and the far moved
    by fixed_madd toward its target by k / 0x1000 -- a 0xff in the colour or
    0xffff for a distance leaves it alone -- and the two distances kept
    0x1000 apart."""
    def madd(a, b):
        return (a + (_s32((b - a) * k) >> 12)) & 0xFFFFFFFF
    use_rgb = all(c & 0xFF != 0xFF for c in rgb)
    for r in range(LIT):
        o = r * 0x6C
        if use_rgb:
            for i in range(3):
                look[o + 0x64 + i] = madd(look[o + 0x64 + i], rgb[i] & 0xFF) & 0xFF
        if near != 0xFFFF:
            n = madd(struct.unpack_from("<H", look, o + 0x68)[0], near) & 0xFFFF
            struct.pack_into("<H", look, o + 0x68, n)
            f = struct.unpack_from("<H", look, o + 0x6A)[0]
            if f - 0x1000 < n:
                struct.pack_into("<H", look, o + 0x6A, (n + 0x1000) & 0xFFFF)
        if far != 0xFFFF:
            f = madd(struct.unpack_from("<H", look, o + 0x6A)[0], far) & 0xFFFF
            struct.pack_into("<H", look, o + 0x6A, f)
            n = struct.unpack_from("<H", look, o + 0x68)[0]
            if f < n + 0x1000:
                struct.pack_into("<H", look, o + 0x68, (f - 0x1000) & 0xFFFF)


def tick(st, tints, look):
    """sub_80030e14, a frame: the darkness, the light, the hit's flash and
    the curse. `st` holds TICK_FIELDS; `tints` two [count, mode, r, g, b];
    `look` the lighting records' bytes. Returns how many times it ran
    player_recalc_stats (the curse's end)."""
    recalcs = 0
    lv, t, r = ramp(st["dark_lv"], st["dark_t"], 0x40, 0xC00)
    if r != -1:
        st["dark_lv"], st["dark_t"] = lv, t
        light_blend(look, (0xA, 0xA, 0xA), 0x1388, 0x1770, r)
        tint(tints, 2, (0x80, 0x80, 0x80), r >> 2, False)
    lv, t, r = ramp(st["light_lv"], st["light_t"], 0x40, 0xE10)
    if r != -1:
        st["light_lv"], st["light_t"] = lv, t
        light_blend(look, (0xDC, 0xDC, 0xA0), 0xFFFF, 0x4650, r)
    if _s16(st["flash"]) != 0:
        f = (st["flash"] - st["flash_step"]) & 0xFFFF
        if _s16(f) < 0:
            f = 0
        st["flash"] = f
        tint(tints, 1, (0x3C, 0, 0), min(_s16(f), 0x1000), True)
    lv, t, r = ramp(st["curse_lv"], st["curse_t"], 0x40, 0xC00)
    if r != -1:
        st["curse_lv"], st["curse_t"] = lv, t
        if _s16(lv) == 0:
            recalcs += 1
        tint(tints, 1, (0x1E, 0x1E, 0xA), r, True)
    return recalcs


def drawn(tints):
    """What render_frame's two rectangles get (sub_8003d64c, sub_8003d79c):
    for each record asked for, its colour over its count, a byte each, and
    its rate -- [(mode, r, g, b)]."""
    out = []
    for rec in tints:
        if rec[0]:
            q = [(-(-c // rec[0]) if c < 0 else c // rec[0]) & 0xFF for c in rec[2:5]]
            out.append((rec[1] & 3, *q))
    return out


def _tints_of(ram):
    o = TINTS & MASK
    out = []
    for m in range(2):
        b = ram[o + 8 * m:o + 8 * m + 8]
        out.append([b[0], b[1]] + list(struct.unpack_from("<3h", b, 2)))
    return out


def _tick_cases(rng, n):
    out = []
    for _ in range(n):
        c = {}
        for k in ("dark", "light", "curse"):
            on = rng.randrange(3)
            c[k + "_lv"] = rng.randrange(0, 90) if on else 0
            c[k + "_t"] = rng.randrange(0, 130) if on else 0
        c["flash"] = rng.choice((0, 0x960, 0xDAC, rng.randrange(0, 0x1400)))
        c["flash_step"] = rng.choice((0x3C, 0x46, rng.randrange(1, 0x150)))
        c["frames"] = rng.randrange(60, 260)
        out.append(c)
    return out


def tick_check(out=sys.stdout, per=4):
    """tick() against sub_80030e14 itself over the snapshots: each case's
    fields, both tint records and the 48 lighting records after every
    frame, and the curse's player_recalc_stats."""
    import random
    import memcard
    import mipsrun
    rng = random.Random(0x7E1C)
    n = ok = frames = fok = 0
    first = None
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        lo = TILE_LOOK & MASK
        look0 = bytes(base[lo:lo + LIT * 0x6C])
        for c in _tick_cases(rng, per):
            cpu = mipsrun.CPU(base)
            calls = []
            cpu.hooks[RECALC] = lambda c2: calls.append(1)
            for k in TICK_FIELDS:
                cpu.wr(TICK_AT[k], 2, c[k])
            st = {k: c[k] for k in TICK_FIELDS}
            good = True
            n += 1
            for f in range(c["frames"]):
                o = TINTS & MASK
                cpu.ram[o:o + 16] = TINT_DEFAULT
                cpu.ram[lo:lo + len(look0)] = look0
                cpu.call(STATUS_TICK)
                tints = [[0, 1, 0, 0, 0], [0, 1, 0, 0, 0]]
                look = bytearray(look0)
                rc = tick(st, tints, look)
                gst = {k: struct.unpack_from("<H", cpu.ram, TICK_AT[k] & MASK)[0]
                       for k in TICK_FIELDS}
                same = (gst == st and _tints_of(cpu.ram) == tints
                        and bytes(cpu.ram[lo:lo + len(look0)]) == bytes(look)
                        and len(calls) == rc)
                calls.clear()
                frames += 1
                fok += same
                if not same and good:
                    good = False
                    if first is None:
                        first = (f"{os.path.basename(path)} {c} frame {f}: game "
                                 f"{gst} {_tints_of(cpu.ram)}, model {st} {tints}")
            ok += good
    print(f"sub_80030e14: {ok} of {n} runs, {fok} of {frames} frames as the game's "
          f"own leaves them -- the darkness, the light, the flash and the curse, "
          f"both tints and the 48 lighting records", file=out)
    if first:
        print("  first difference: " + first, file=out)
    return ok == n


def export_tick(out_dir, n=40):
    """The tick's frames for godot/selftest.gd: each case, and after every
    frame its fields, what the two rectangles draw, the recalculations and
    the first record's colour and distances."""
    import json
    import random
    path = os.path.join(ROOT, "out", "snap", "b.ram")
    if not os.path.exists(path):
        return None
    ram = open(path, "rb").read()
    lo = TILE_LOOK & MASK
    look0 = bytes(ram[lo:lo + LIT * 0x6C])
    rng = random.Random(0x71C)
    runs = []
    for c in _tick_cases(rng, n):
        st = {k: c[k] for k in TICK_FIELDS}
        rows = []
        for _f in range(c["frames"]):
            tints = [[0, 1, 0, 0, 0], [0, 1, 0, 0, 0]]
            look = bytearray(look0)
            rc = tick(st, tints, look)
            rows.append([[st[k] for k in TICK_FIELDS], [list(t) for t in drawn(tints)], rc,
                         list(look[0x64:0x67]) + list(struct.unpack_from("<2H", look, 0x68))])
        runs.append({"start": {k: c[k] for k in TICK_FIELDS}, "frames": rows})
    out = os.path.join(out_dir, "statuscheck.json")
    with open(out, "w") as fh:
        json.dump({"_note": "sub_80030e14 as tools/status.py runs it: per frame the "
                            "fields " + ",".join(TICK_FIELDS) + ", the rectangles "
                            "[(mode,r,g,b)], the recalculations, and record 0's "
                            "colour, near and far",
                   "look0": list(look0[0x64:0x67]) + list(struct.unpack_from("<2H", look0, 0x68)),
                   "runs": runs}, fh, separators=(",", ":"))
    return out


if __name__ == "__main__":
    if "--check" in sys.argv:
        a = check()
        b = tick_check()
        sys.exit(0 if a and b else 1)
    print(__doc__)

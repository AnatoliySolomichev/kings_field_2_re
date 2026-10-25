#!/usr/bin/env python3
"""Casting: what a button does with the magic in hand, and what keeps
running after it.

    python3 tools/magic.py --check      the model against the game's own
                                        cast_spell, player_action's arms,
                                        player_turn's pending action and the
                                        timers at player_controller's end,
                                        run over every snapshot

**The buttons** (`player_turn`, `0x8002fe1c`). The action button's edge casts
magic A (`0x801b25ab`) -- unless the weapon's own magic is firing
(`0x801b25b2`) or `0x801b25aa` is set; the square button's (`bind_map`)
casts the button's spell (`0x801b25ac`), or uses its thing (`0x801b25ad`),
or says it is gone (announce `0xa`). **The thing** (`0x8002ff28`): with one
or more of it in `inventory_a` it is eaten first by `item_consume` when
`0x8002fddc` says it is one of the eaten -- the herbs and stones `0x68..0x6d`,
the two fruits `0x6f`, `0x70`, the potions `0x77`, `0x78` (seventeen arms
from `0x80011a78`) -- and then handed to `use_item` from `player_pos` and
`player_pitch`, as the menu's "use" does; with none, "Nothing happens".
`button_check()` runs that stretch (`0x8002febc..0x8002ff88`) of the
game's own over the snapshots.

**`cast_spell`** (`0x8002deec`): nothing while an action is pending
(`0x801b25e9` not `0xff`). The cost is the record's `+0x16`, doubled by the
groundal crown (`0x26`, head) and halved by orladin's mail (`0x2e`, body);
short of it, announce 9. Nothing with weapon `0x1f` in hand. Then the eight
healing and protecting spells' conditions (`0x80011920`):

```
0x17 earth heal       HP below its most
0x19 antidote         poisoned
0x1a fire resist      0x801b256a not running
0x1b refusal          0x801b256c not running
0x1c missile shield   0x801b256e not running
0x1d light            0x801b2572 not running: it is set to 0x384, the MP
                      spent, skill_practice -- and that is all, no meter
0x1e blessings        HP below its most, or a curse, darkness, slowing or
                      paralysis on
```

each of them with one shot (`0x801b25ea`, `0x801b25eb` = 1). Every spell but
light then needs **the magic meter full** (5000); the healing five practise
here (`skill_practice`), the rest when they strike. The meter goes to 0, the
swing's pause to 0, MP down by the cost, the spell pending with a delay of
1, `casting_spell` (`0x801b2590`) its record, and the cast's offset from the
eye (`0x801b2630`, `2632`, `2634`) -200, 200, 400 -- which a spell's own arm
of a 77-arm table (`0x80011940`) changes along with how many shots
(`0x801b25ea`) and how many frames apart (`0x801b25eb`).

**The pending action** (`player_turn`, `0x8002ff88`): the delay counts down
and at 0 `player_action(spell)` fires; while shots remain the delay starts
again at the interval, and after the last nothing is pending.

**`skill_practice`** (`0x8002a10c`): for each skill k whose bit `1 << k` the
record's group (`+5`) has, its `+3` is added to the count at `0x801b250a +
2k`; at 400 the count is 0 again and the skill rises by one -- to 999 at most,
announce `0x12 + k` below that -- then `skill_unlock(k)` and the stats.

**`player_action`'s protecting arms**: fire resist (`0x1a`) and missile
shield (`0x1c`) spawn two effects of their kind at the player and set
`0x801b256a` / `0x801b256e` to `0x708`; refusal (`0x1b`) one, and
`0x801b256c` to `0xc8`; each then `player_recalc_stats`. Earth heal,
antidote and blessings only spawn their effect; the healing is the effect's.

**The timers at `player_controller`'s end** (`0x80031f0c`): `0x801b256a`,
`256c` and `256e` count down and recalculate the stats when they reach 0;
`0x801b2576` counts down holding MP at its most every frame, announce `0x1b`
at the end; `0x801b2578` counts down, and at 0 the stats and announce `0x1b`.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MASK = 0x1FFFFF

CAST_SPELL = 0x8002DEEC
PLAYER_ACTION = 0x8002C30C
SKILL_PRACTICE = 0x8002A10C
SKILL_UNLOCK = 0x80029F1C
RECALC = 0x80029500
ANNOUNCE = None              # read off the symbol table below
EFFECT_SPAWN = 0x80053C84
RAND = 0x800796C0
SPELL_TABLE = 0x801B77EC
NONE = 0xFF

PENDING_AT = (0x8002FF88, 0x80030010)     # player_turn's stretch
BUTTON_AT = (0x8002FEBC, 0x8002FF88)      # and its square button's
BIND_MAP = 0x80081880
SPELL_B, ITEM_B = 0x801B25AC, 0x801B25AD
INVENTORY_A = 0x800C85E8
ITEM_CONSUME = 0x8001B254
USE_ITEM = 0x8005CBE0
PLAYER_PITCH = 0x801B2610
EATS = frozenset(list(range(0x68, 0x6E)) + [0x6F, 0x70, 0x77, 0x78])   # 0x8002fddc
TAIL_AT = (0x80031F0C, 0x8003202C)        # player_controller's

# name: (address, bytes, signed)
FIELDS = {
    "pending": (0x801B25E9, 1, False), "count": (0x801B25EA, 1, False),
    "interval": (0x801B25EB, 1, False), "delay": (0x801B25EC, 1, False),
    "mp": (0x801B2500, 2, False), "mp_max": (0x801B24FE, 2, False),
    "hp": (0x801B24FC, 2, False), "hp_max": (0x801B24FA, 2, False),
    "weapon": (0x801B25AF, 1, False),
    "poison": (0x801B255C, 2, True), "curse_lv": (0x801B255E, 2, True),
    "dark_lv": (0x801B2562, 2, True), "slow": (0x801B2566, 2, True),
    "paralysis": (0x801B2568, 2, True),
    "b56a": (0x801B256A, 2, True), "b56c": (0x801B256C, 2, True),
    "b56e": (0x801B256E, 2, True), "b576": (0x801B2576, 2, True),
    "b578": (0x801B2578, 2, True), "light_t": (0x801B2572, 2, True),
    "meter": (0x801B2506, 2, False), "swing_pause": (0x801B24F3, 1, False),
    "off_x": (0x801B2630, 2, True), "off_y": (0x801B2632, 2, True),
    "off_z": (0x801B2634, 2, True), "casting": (0x801B2590, 4, False),
    "run": (0x801B24F5, 1, False), "weapon_meter": (0x801B2502, 2, False),
    "magic_pause": (0x801B24F4, 1, False), "damage_scale": (0x801B24F8, 2, False),
    "b25aa": (0x801B25AA, 1, False), "b258c": (0x801B258C, 4, False),
    "buttons": (0x801B265C, 2, False), "buttons_prev": (0x801B265E, 2, False),
}
WORKING = 0x801B2526
BIND_USE = 0x80081876
USE_AT = (0x80030010, (0x80030464, 0x800302D4))   # player_turn's USE stretch
WORN = 0x801B25D4
PRACTICE = 0x801B250A
SKILLS = 0x801B2518


def _announce():
    import syms
    for a, v in syms.load().items():
        if isinstance(v, dict) and v.get("name") == "announce":
            return a
    return None


def rd(ram, name):
    a, n, signed = FIELDS[name]
    return int.from_bytes(ram[a & MASK:(a & MASK) + n], "little", signed=signed)


def wr(ram, name, v):
    a, n, _s = FIELDS[name]
    ram[a & MASK:(a & MASK) + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, "little")


def state_of(ram):
    st = {k: rd(ram, k) for k in FIELDS}
    st["working"] = list(struct.unpack_from("<5H", ram, WORKING & MASK))
    st["use"] = struct.unpack_from("<H", ram, BIND_USE & MASK)[0]
    st["worn"] = list(ram[WORN & MASK:(WORN & MASK) + 7])
    st["practice"] = list(struct.unpack_from("<5H", ram, PRACTICE & MASK))
    st["skills"] = list(struct.unpack_from("<5H", ram, SKILLS & MASK))
    return st


def record(ram, spell):
    o = (SPELL_TABLE + 24 * spell) & MASK
    return bytes(ram[o:o + 24])


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def skill_practice(st, rec, calls):
    """skill_practice on `st` with a spell record's bytes."""
    group = rec[5] if rec is not None else 0
    for k in range(4, -1, -1):
        if not group & (1 << k):
            continue
        st["practice"][k] = (st["practice"][k] + rec[3]) & 0xFFFF
        if st["practice"][k] < 0x190:
            continue
        st["practice"][k] = 0
        st["skills"][k] = (st["skills"][k] + 1) & 0xFFFF
        if st["skills"][k] >= 0x3E8:
            st["skills"][k] = 0x3E7
        else:
            calls.append(("announce", 0x12 + k))
        calls.append(("unlock", k))
        calls.append(("recalc",))


# What each spell's arm of 0x80011940 sets: (off_x, off_y, off_z) or None to
# leave them, the shots, the interval (None: leave it).
CAST_ARMS = {
    0x04: ((0, -0x200, 0x7D0), 1, 1),
    0x4C: ((0, 0, 0x258), 1, 1),
    0x01: ((-0x7D0, 0x640, 0x3E8), 5, 3),
    0x38: ("y", 3, 1),
    0x0D: ("y", 1, 1),
    0x40: (None, 3, 1),
    0x42: (None, 1, 1),
    0x09: ((0, -0x190, 0x190), 1, 1),
    0x11: ((0, -0x258, 0x258), 1, 1),
    0x14: ("x", 5, 2), 0x47: ("x", 5, 2),
    0x02: (None, 3, 1),
    0x0B: (None, 0xC, 1),
    0x07: ((0, 0, 0), 2, 1),
    0x08: (None, 4, 2),
}
ONE_SHOT = {0x00, 0x05, 0x06, 0x0C, 0x0F, 0x10, 0x13, 0x15, 0x1D, 0x36, 0x37,
            0x3A, 0x3C, 0x3E, 0x44, 0x45, 0x46, 0x48, 0x49, 0x4B}


def cast_spell(st, spell, ram, calls):
    """cast_spell on `st`; `ram` for the spell records."""
    if st["pending"] != NONE or spell == NONE:
        return
    rec = record(ram, spell)
    rec_at = SPELL_TABLE + 24 * spell
    cost = struct.unpack_from("<H", rec, 0x16)[0]
    if st["worn"][0] == 0x26:
        cost <<= 1
    if st["worn"][1] == 0x2E:
        cost >>= 1
    if st["mp"] < cost:
        calls.append(("announce", 9))
        return
    if st["weapon"] == 0x1F:
        return
    one = False
    k = spell - 0x17
    if 0 <= k < 8:
        if k == 0:
            if st["hp"] == st["hp_max"]:
                return
            one = True
        elif k == 2:
            if st["poison"] == 0:
                return
            one = True
        elif k in (3, 4, 5):
            if st[("b56a", "b56c", "b56e")[k - 3]] != 0:
                return
            one = True
        elif k == 6:
            if st["light_t"] != 0:
                return
            st["light_t"] = 0x384
            st["mp"] = (st["mp"] - cost) & 0xFFFF
            skill_practice(st, rec, calls)
            return
        elif k == 7:
            if not (st["hp"] != st["hp_max"] or st["curse_lv"] or st["dark_lv"]
                    or st["slow"] or st["paralysis"]):
                return
            one = True
    if one:
        st["count"] = st["interval"] = 1
    if st["meter"] < 0x1388:
        return
    if spell == 0x17 or 0x19 <= spell <= 0x1C or spell == 0x1E:
        skill_practice(st, rec, calls)
    st["off_x"], st["off_y"], st["off_z"] = -0xC8, 0xC8, 0x190
    st["meter"] = 0
    st["swing_pause"] = 0
    st["pending"] = spell
    st["delay"] = 1
    st["mp"] = (st["mp"] - cost) & 0xFFFF
    if spell in ONE_SHOT:
        st["count"] = st["interval"] = 1
    elif spell in CAST_ARMS:
        offs, n, gap = CAST_ARMS[spell]
        if offs == "y":
            st["off_y"] = 0x1F4
        elif offs == "x":
            st["off_x"] = -0xC8
        elif offs is not None:
            st["off_x"], st["off_y"], st["off_z"] = offs
        st["count"] = n
        if gap is not None:
            st["interval"] = gap
    st["casting"] = rec_at


TIMED = {0x1A: ("b56a", 0x708, 2), 0x1C: ("b56e", 0x708, 2), 0x1B: ("b56c", 0xC8, 1)}
SPAWN_ONLY = (0x17, 0x19, 0x1E)


def action(st, spell, calls):
    """player_action's arms for the healing and protecting spells: the
    effects spawned -- (a0, a1, kind, the point's address, the second stack
    word) -- the timers and the stats."""
    if spell in TIMED:
        name, t, n = TIMED[spell]
        for i in range(n):
            calls.append(("spawn", 0xA, 0x40, spell, 0x801B25F0, i if n == 2 else None))
        st[name] = t
        calls.append(("recalc",))
    elif spell in SPAWN_ONLY:
        calls.append(("spawn", 0xA, 0x40, spell, 0x801B25F0, None))


def pending(st, calls):
    """player_turn's pending action, a frame."""
    if st["pending"] == NONE:
        return
    st["delay"] = (st["delay"] - 1) & 0xFF
    if st["delay"]:
        return
    calls.append(("action", st["pending"]))
    st["count"] = (st["count"] - 1) & 0xFF
    if st["count"] == 0:
        st["pending"] = NONE
    else:
        st["delay"] = st["interval"]


def tail(st, calls):
    """The timers at player_controller's end, a frame."""
    for name in ("b56a", "b56c", "b56e"):
        if st[name] != 0:
            st[name] = _s16(st[name] - 1)
            if st[name] == 0:
                calls.append(("recalc",))
    if st["b576"] != 0:
        st["b576"] = _s16(st["b576"] - 1)
        st["mp"] = st["mp_max"]
        if st["b576"] == 0:
            calls.append(("announce", 0x1B))
    if st["b578"] != 0:
        st["b578"] = _s16(st["b578"] - 1)
        if st["b578"] == 0:
            calls.append(("recalc",))
            calls.append(("announce", 0x1B))


def meter_gain(stat, rate):
    """meter_gain (0x80029390): min((stat << 6) / (rate + 1) + 1, 5000)."""
    a = _s32(stat << 6)
    b = rate + 1
    q = abs(a) // abs(b)
    q = -q if (a < 0) != (b < 0) else q
    return min(q + 1, 0x1388)


def _s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def use_tick(st, ram):
    """player_turn's USE stretch (0x80030010): held this frame and the last,
    and the feet not the groundal boots, it counts the run's flag down, takes
    500 from each meter (an empty one pauses 60 frames -- 1 and 0 with the
    fu-jin or ichrius' boots, 0x4d, 0x4f) and 0x80 from damage_scale down to
    0x400, and player_turn returns there. Otherwise the magic meter's pause
    runs down or it refills by meter_gain(the five working skills' mean, the
    cast record's +1 -- a quarter less with helm 0x25, twice with armour
    0x30), to 5000; damage_scale climbs back by 0x80 to 0x1000; the run's flag
    is 1; and 0x801b25aa counts down, or 0x801b258c is 0x8009c3cc. True when
    the rest of player_turn runs."""
    feet = st["worn"][4]
    held = st["buttons"] & st["use"] and st["buttons_prev"] & st["use"]
    if held and feet != 0x4C:
        if st["run"]:
            st["run"] -= 1
        st["swing_pause"] = 1
        st["weapon_meter"] = (st["weapon_meter"] - 500) & 0xFFFF
        if _s16(st["weapon_meter"]) <= 0:
            st["weapon_meter"] = 0
            st["swing_pause"] = 1 if feet in (0x4D, 0x4F) else 0x3C
        st["magic_pause"] = 1
        st["meter"] = (st["meter"] - 500) & 0xFFFF
        if _s16(st["meter"]) <= 0:
            st["meter"] = 0
            st["magic_pause"] = 0 if feet in (0x4D, 0x4F) else 0x3C
        st["damage_scale"] = (st["damage_scale"] - 0x80) & 0xFFFF
        if _s16(st["damage_scale"]) < 0x400:
            st["damage_scale"] = 0x400
        return False
    total = sum(st["working"])
    avg = total // 5
    if st["magic_pause"]:
        st["magic_pause"] -= 1
    else:
        rate = 0
        if st["casting"]:
            o = st["casting"] & MASK
            rate = ram[o + 1]
            if st["worn"][0] == 0x25:
                rate -= rate >> 2
            if st["worn"][1] == 0x30:
                rate <<= 1
        st["meter"] = (st["meter"] + meter_gain(avg, rate)) & 0xFFFF
    if st["meter"] >= 0x1389:
        st["meter"] = 0x1388
    st["damage_scale"] = (st["damage_scale"] + 0x80) & 0xFFFF
    if _s16(st["damage_scale"]) > 0x1000:
        st["damage_scale"] = 0x1000
    st["run"] = 1
    if st["b25aa"]:
        st["b25aa"] -= 1
    else:
        st["b258c"] = 0x8009C3CC
    return True


# --- the attacking arms of player_action ---------------------------------------

VIEW = 0x801B2608                # view_angles: pitch, yaw, roll
CAST_OFF = 0x801B2630
PLAYER_POS = 0x801B25F0
ACTORS, ACTOR_STRIDE, ACTOR_N = 0x80185DA8, 0x88, 200
CURRENT_ACTOR = 0x8018FAB4
TARGET = 0x8018FAD0
ENTITY_TABLE = 0x8018C7E8
KIND_OP, ACTOR_SWITCH = 0x8004C068, 0x8004B94C
COLLIDE_ACTOR = 0x80033D08
OFFSETS = 0x800818E4             # the weapons' marks: five (x, y, z, 0)
SLOTS, SLOT = 0x801B80EC, 0x4C


def _u32(ram, a):
    return struct.unpack_from("<I", ram, a & MASK)[0]


def _i32(ram, a):
    return struct.unpack_from("<i", ram, a & MASK)[0]


def _h(ram, a):
    return struct.unpack_from("<h", ram, a & MASK)[0]


def sight(ram, point, yaw, pitch, reach, ycone, pcone, noise=0, rand=None):
    """sub_8004d3c4: the awake creature (+9 1, +0xe not 3, not the one
    acting) within `reach` (twice it for flag 0x20000) whose bearing and
    pitch from `point` are nearest `yaw` and `pitch` -- inside the cones, or
    for flag 0x20000 a quarter of the distance and 0x200 off each instead --
    scored by the two differences and the distance / 128. (actor, distance),
    (0, -1) for none."""
    import effects
    import movement
    best, chosen, dist = 0x7530, 0, -1
    cur = _u32(ram, CURRENT_ACTOR)
    for k in range(ACTOR_N):
        a = ACTORS + k * ACTOR_STRIDE
        if ram[(a + 9) & MASK] != 1 or ram[(a + 0xE) & MASK] == 3 or a == cur:
            continue
        flags = _u32(ram, a + 0x28)
        r = reach << 1 if flags & 0x20000 else reach
        pos = (_i32(ram, a + 0x2C), _i32(ram, a + 0x30), _i32(ram, a + 0x34))
        d = movement.in_range(pos, point[0], 0xFFFF, point[2], r, 0, 0)
        if d == -1:
            continue
        ang = effects.vec_to_angles(_s32(pos[0] - point[0]), _s32(pos[1] - point[1]),
                                    _s32(pos[2] - point[2]))
        dy = (ang[1] - yaw) & 0xFFF
        if dy >= 0x800:
            dy = 0x1000 - dy
        dp = (ang[0] - pitch) & 0xFFF
        if dp >= 0x800:
            dp = 0x1000 - dp
        if flags & 0x20000 and noise >= 0:
            d >>= 2
            dy = _s16(dy - 0x200)
            dp = _s16(dp - 0x200)
        elif ycone < dy or pcone < dp:
            continue
        score = dy + dp + (d >> 7)
        if noise > 0:
            score += _s32(rand() * noise) >> 15
        if score < best:
            best, chosen, dist = score, a, d
    return chosen, dist


def spell_aim(st, ram, speed, calls, kind_op):
    """sub_8002c164: the start -- the cast offset turned by the view's
    angles (the pitch negated) from the eye, 0x640 above the feet -- the
    creature in sight within 0x55f0 and 0x200 either way (woken: its
    behaviour 0x82, unless +0x28 has 0x100), the velocity the view's
    direction times `speed`. (point, velocity, the creature, its distance)."""
    import movement
    import weapon
    pitch, yaw, roll = st["view"]
    px, py, pz = st["pos"]
    v = weapon.vec_rotate((_s16(-pitch), yaw, roll), (st["off_x"], st["off_y"], st["off_z"]))
    point = [_s32(v[0] + px), _s32(v[1] - 0x640 + py), _s32(v[2] + pz)]
    chosen, dist = sight(ram, (px, py, pz), _s16(yaw), _s16(pitch), 0x55F0, 0x200, 0x200)
    st["target"] = chosen
    if chosen:
        kind = ENTITY_TABLE + 120 * ram[(chosen + 2) & MASK]
        rec = kind_op(kind, 0x82)
        calls.append(("kind_op", kind, 0x82))
        if rec and not _u32(ram, chosen + 0x28) & 0x100:
            calls.append(("switch", chosen, rec))
    d = movement.direction_from_angles(pitch, yaw)
    vel = [_s16((c * _s16(speed)) >> 12) for c in d]
    return point, vel, chosen, dist


# arm -> (speed, the kind spawned, the arguments after the velocity)
PLAIN = {0x00: (0x384, None, []), 0x06: (0x1F4, None, []), 0x37: (0x1F4, None, []),
         0x40: (0x1B8, None, []), 0x4C: (0x1C2, None, []), 0x3C: (0x140, None, []),
         0x3A: (0x226, None, []), 0x3E: (0x2EE, None, []), 0x4B: (0x2D0, None, []),
         0x46: (0x1F4, None, [0]), 0x15: (0x104, None, []),
         0x38: (0x2BC, None, ["view"]), 0x39: (0x2BC, None, ["view"]),
         0x0D: (0x2BC, None, ["view"]), 0x04: (0xFA, None, ["view"]),
         0x09: (0xFA, None, ["view"]), 0x11: (0xFA, None, ["view"]),
         0x10: (0xFA, None, ["view"]), 0x05: (0xFA, None, ["view"]),
         0x42: (0x384, None, ["view"]), 0x44: (0x3E8, 0x7C, []),
         0x45: (0x3E8, 0x7B, ["view"])}


def attack(st, ram, action, calls, kind_op, collide, spawn_ret, rand):
    """player_action's attacking arms: what each spawns -- ("spawn", a0, a1,
    kind, the point, [the velocity as ("vel", x, y, z), "view" for
    view_angles, or a number]) -- and what it changes."""
    def spawn(a1, kind, point, args):
        calls.append(("spawn", 0xA, a1, kind, tuple(point), args))
        return spawn_ret

    def aim(speed):
        return spell_aim(st, ram, speed, calls, kind_op)

    if action in PLAIN:
        speed, kind, more = PLAIN[action]
        point, vel, _t, _d = aim(speed)
        spawn(0x42, kind if kind is not None else action, point, [("vel", *vel)] + more)
    elif action == 0x36:
        for i in range(4):
            st["off_z"] = _s16(800 * (3 - i))
            point, vel, _t, _d = aim(0x1F4)
            spawn(0x42, 0x36, point, [("vel", *vel), 3 - i])
    elif action == 0x0F:                                    # tornado
        point, vel, _t, _d = aim(0x12C)
        point[1] = _s32(point[1] + 0x540)
        vel[1] = 0
        spawn(0x42, 0x0F, point, [("vel", *vel), "view", 0])
        spawn(0x42, 0x0F, point, [("vel", *vel), "view", 1])
    elif action == 0x07:                                    # earth wave
        spawn(0x43, 0x07, st["pos"], [0, 0x1000, 0x100, 0x1000, 1])
    elif action in (0x08, 0x0C):                            # meteor, bortecth
        point, vel, t, _d = aim(0x1B58)
        if not t:
            point = [_s32(point[0] + vel[0]), st["pos"][1], _s32(point[2] + vel[2])]
        elif action == 0x0C:
            point = [_i32(ram, t + 0x2C), _i32(ram, t + 0x30), _i32(ram, t + 0x34)]
        else:
            ahead = []
            for o, w in ((0x50, 0x2C), (0x52, 0x30), (0x54, 0x34)):
                v = _s32(_h(ram, t + o) << 14)
                q = (v * 0x64D319FF) >> 32
                ahead.append(_s32((q >> 8) - (v >> 31) + _i32(ram, t + w)))
            point = ahead
            if collide(*point, 0xA, 0xA):
                calls.append(("collide", *point))
                point = [_i32(ram, t + 0x2C), _i32(ram, t + 0x30), _i32(ram, t + 0x34)]
            else:
                calls.append(("collide", *point))
        spawn(0x43 if action == 0x08 else 0x42, 0x5F if action == 0x08 else 0x0C, point, [0])
    elif action == 0x0B:                                    # haze
        point, vel, _t, _d = aim(0x104)
        vel[0] = _s16(vel[0] - 0x10 + (rand() >> 10))
        vel[1] = _s16(vel[1] - 0x10 + (rand() >> 10))
        spawn(0x42, 0x0B, point, [("vel", *vel), _s32(0xE - st["count"])])
    elif action == 0x13:                                    # lightning bolt
        point, vel, _t, d = aim(0x258)
        if d != -1:
            d = d // 600 - 8
            if d < 2:
                d = 2
        else:
            d = 0xA
        vel[1] = 0
        spawn(0x42, 0x71, point, [("vel", *vel), d])
    elif action == 0x02:                                    # fire storm
        point, vel, t, _d = aim(0x1F4)
        idx = (t - ACTORS) // ACTOR_STRIDE if t else 0xFF
        spawn(0x42, 0x02, point, [("vel", *vel), idx, st["count"]])
    elif action == 0x01:                                    # fire wall
        point, vel, _t, _d = aim(0x23A)
        spawn(0x42, 0x01, point, [("vel", *vel), "view"])
        st["off_x"] = _s16(st["off_x"] + 0x3E8)
    elif action in (0x14, 0x47):                            # flash
        yaw = st["view"][1]
        st["view"] = (st["view"][0], (yaw - 2 * st["off_x"]) & 0xFFFF, st["view"][2])
        point, vel, _t, _d = aim(0xAA)
        st["off_x"] = _s16(st["off_x"] + 0x64)
        st["view"] = (st["view"][0], yaw, st["view"][2])
        spawn(0x42, action, point, [("vel", *vel), "view", 0x258, 0x3C, 0x80, 0x8C, 0xA0])
    elif action in (0x48, 0x49, 0x4A):                      # a weapon's five
        kind, child = (0x78, 0x5C) if action == 0x48 else (0x7A, 0x5D)
        offs = [struct.unpack_from("<4h", ram, (OFFSETS + 8 * i) & MASK) for i in range(5)]
        st["off_x"], st["off_y"], st["off_z"], st["off_w"] = offs[0]
        point, vel, _t, _d = aim(0x258)
        got = spawn(0x42, kind, point, [("vel", *vel), "view"])
        if got:
            parent = (got - SLOTS) // SLOT
            for i in range(1, 5):
                st["off_x"], st["off_y"], st["off_z"], st["off_w"] = offs[i]
                point, vel, _t, _d = aim(0x258)
                spawn(0x42, child, point, [("vel", *vel), parent])
    return


# --- against the game ---------------------------------------------------------

def _cpu(ram, calls):
    import levelstate
    import mipsrun
    cpu = mipsrun.CPU(ram)
    lcg = levelstate.Lcg()
    cpu.hooks[RAND] = lambda c: lcg()
    cpu.hooks[ANNOUNCE] = lambda c: calls.append(("announce", c.r[4] & 0xFF))
    cpu.hooks[SKILL_UNLOCK] = lambda c: calls.append(("unlock", c.r[4] & 0xFF))
    cpu.hooks[RECALC] = lambda c: calls.append(("recalc",))

    def spawn(c):
        w = c.rd(c.r[29] + 0x14, 4)
        calls.append(("spawn", c.r[4] & 0xFF, c.r[5] & 0xFF, c.r[6] & 0xFF,
                      c.r[7], w if c.r[6] in (0x1A, 0x1C) else None))
        return 0
    cpu.hooks[EFFECT_SPAWN] = spawn
    cpu.hooks[PLAYER_ACTION] = lambda c: calls.append(("action", c.r[4] & 0xFF))
    return cpu


def _stretch(cpu, start, end, limit=200000):
    import mipsrun
    ends = end if isinstance(end, tuple) else (end,)
    cpu.r[29] = mipsrun.STACK - 0x200
    cpu.pc = start
    n = 0
    while cpu.pc not in ends:
        cpu.step()
        n += 1
        if n > limit:
            raise RuntimeError(f"stretch {start:#x} ran away")
    cpu.r[29] = mipsrun.STACK


def eats(thing):
    """0x8002fddc: whether item_consume eats the thing before use_item has
    it -- a switch of seventeen arms on thing - 0x68 (0x80011a78)."""
    return thing in EATS


def button_calls(spell, thing, held):
    """player_turn's square button, once its edge is seen (0x8002fef8): the
    button's spell cast; then its thing -- none held, "Nothing happens";
    else eaten first if it is one item_consume eats, and used."""
    calls = []
    if spell != NONE:
        calls.append(("cast", spell))
    if thing == NONE:
        return calls
    if held == 0:
        calls.append(("announce", 0xA))
        return calls
    if eats(thing):
        calls.append(("consume", thing))
    calls.append(("use", thing))
    return calls


def button(ram):
    """The stretch at 0x8002febc: the button's edge -- bind_map in the
    buttons and not in the last frame's -- and then button_calls."""
    m = struct.unpack_from("<H", ram, BIND_MAP & MASK)[0]
    if not rd(ram, "buttons") & m or rd(ram, "buttons_prev") & m:
        return []
    thing = ram[ITEM_B & MASK]
    held = ram[(INVENTORY_A & MASK) + thing] if thing != NONE else 0
    return button_calls(ram[SPELL_B & MASK], thing, held)


def _vary_button(ram, rng):
    """The square button's edge, its spell, its thing and the count of it."""
    m = struct.unpack_from("<H", ram, BIND_MAP & MASK)[0]
    wr(ram, "buttons", rng.choice((m, m, m | 0x40, 0, 0x40)))
    wr(ram, "buttons_prev", rng.choice((0, 0, 0, m)))
    ram[SPELL_B & MASK] = rng.choice((NONE, NONE, NONE, rng.randrange(0, 0x1F)))
    thing = rng.choice((NONE, rng.randrange(0x65, 0x96), rng.choice(sorted(EATS)),
                        rng.choice((0x6E, 0x71, 0x76, 0x80, 0x82, 0x88))))
    ram[ITEM_B & MASK] = thing
    if thing != NONE:
        ram[(INVENTORY_A & MASK) + thing] = rng.choice((0, 1, 1, rng.randrange(1, 10)))


def button_check(out=sys.stdout, per=60):
    """The game's own stretch, cast_spell, item_consume and use_item stood in
    for and logged, 0x8002fddc run, against button() over every snapshot."""
    import random
    import memcard
    global ANNOUNCE
    ANNOUNCE = ANNOUNCE or _announce()
    rng = random.Random(0xB077)
    ok = n = 0
    first = None
    ways = {}
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        for _ in range(per):
            ram = bytearray(base)
            _vary_button(ram, rng)
            got = []
            cpu = _cpu(ram, got)
            cpu.hooks[CAST_SPELL] = lambda c: got.append(("cast", c.r[4] & 0xFF))
            cpu.hooks[ITEM_CONSUME] = lambda c: got.append(("consume", c.r[4] & 0xFF))

            def use(c):
                if (c.r[4], c.r[5]) == (PLAYER_POS, PLAYER_PITCH):
                    got.append(("use", c.r[6] & 0xFF))
                else:
                    got.append(("use from", c.r[4], c.r[5], c.r[6]))
            cpu.hooks[USE_ITEM] = use
            _stretch(cpu, *BUTTON_AT)
            want = button(ram)
            key = " ".join(c[0] for c in want) or "nothing"
            ways[key] = ways.get(key, 0) + 1
            n += 1
            if got == want:
                ok += 1
            elif first is None:
                first = f"{os.path.basename(path)}: game {got} model {want}"
    print(f"  the square button's thing, against the game's own player_turn stretch "
          f"(0x8002febc): {ok} of {n} runs, the calls in order -- "
          + ", ".join(f"{v} {k}" for k, v in sorted(ways.items())), file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return ok == n


def _vary(ram, rng):
    """A state for casting: the fields that decide, at random."""
    wr(ram, "pending", rng.choice((NONE, NONE, NONE, rng.randrange(0, 0x1F))))
    wr(ram, "count", rng.randrange(0, 6))
    wr(ram, "interval", rng.randrange(0, 4))
    wr(ram, "delay", rng.randrange(0, 4))
    wr(ram, "mp_max", rng.randrange(10, 300))
    wr(ram, "mp", rng.choice((0, 3, rng.randrange(0, 300), 120)))
    hpm = rng.randrange(20, 300)
    wr(ram, "hp_max", hpm)
    wr(ram, "hp", hpm if rng.randrange(2) else rng.randrange(1, hpm + 1))
    wr(ram, "weapon", rng.choice((0, 0, 3, 0x1F)))
    for k in ("poison", "curse_lv", "dark_lv", "slow", "paralysis", "b56a", "b56c",
              "b56e", "b576", "b578", "light_t"):
        wr(ram, k, rng.choice((0, 0, 0, 1, rng.randrange(1, 40))))
    wr(ram, "meter", rng.choice((5000, 5000, 4999, rng.randrange(0, 5001))))
    o = WORN & MASK
    ram[o] = rng.choice((0xFF, 0x26, 0x22, 0x25))
    ram[o + 1] = rng.choice((0xFF, 0x2E, 0x2A, 0x30))
    ram[o + 4] = rng.choice((0xFF, 0x4C, 0x4D, 0x4F, 0x48))
    use = struct.unpack_from("<H", ram, BIND_USE & MASK)[0]
    wr(ram, "buttons", rng.choice((0, use, use | 0x10)))
    wr(ram, "buttons_prev", rng.choice((0, use)))
    wr(ram, "run", rng.randrange(0, 3))
    wr(ram, "weapon_meter", rng.choice((5000, 400, 600, rng.randrange(0, 5001))))
    wr(ram, "magic_pause", rng.choice((0, 0, 1, rng.randrange(0, 61))))
    wr(ram, "damage_scale", rng.choice((0x1000, 0x400, 0x480, rng.randrange(0x400, 0x1001))))
    wr(ram, "b25aa", rng.choice((0, 0, 3)))
    wr(ram, "casting", rng.choice((0, SPELL_TABLE + 24 * rng.randrange(0, 31))))
    for k in range(5):
        struct.pack_into("<H", ram, (WORKING & MASK) + 2 * k, rng.randrange(0, 1000))
    for k in range(5):
        struct.pack_into("<H", ram, (PRACTICE & MASK) + 2 * k, rng.choice((0, 395, 399, rng.randrange(0, 400))))
        struct.pack_into("<H", ram, (SKILLS & MASK) + 2 * k, rng.choice((10, 998, 999, rng.randrange(0, 999))))


def _same(a, b):
    keys = list(FIELDS) + ["practice", "skills", "working"]
    return [k for k in keys if a[k] != b[k]]


ATTACKS = sorted(set(PLAIN) | {0x36, 0x0F, 0x07, 0x08, 0x0C, 0x0B, 0x13, 0x02, 0x01,
                                0x14, 0x47, 0x48, 0x49, 0x4A})
SPAWNED = SLOTS + 7 * SLOT       # what the check's effect_spawn hands back


def _kind_op(kind, op):
    """The check's stand-in for kind_behaviour_with_op: a record for some
    kinds and none for the others, the same on both sides."""
    return 0x80100000 | (kind & 0xFFF) if (kind >> 3) & 1 else 0


def _collide(x, y, z, a3, a4):
    return 1 if ((x ^ z) >> 9) & 1 else 0


def attack_state(ram):
    return {"view": tuple(struct.unpack_from("<3H", ram, VIEW & MASK)),
            "pos": tuple(struct.unpack_from("<3i", ram, PLAYER_POS & MASK)),
            "off_x": _h(ram, CAST_OFF), "off_y": _h(ram, CAST_OFF + 2),
            "off_z": _h(ram, CAST_OFF + 4), "off_w": _h(ram, CAST_OFF + 6),
            "count": ram[0x801B25EA & MASK], "target": _u32(ram, TARGET)}


def _attack_cpu(ram, calls, lcg):
    import mipsrun
    cpu = mipsrun.CPU(ram)
    cpu.hooks[RAND] = lambda c: lcg()

    def spawn(c):
        sp = c.r[29]
        words = [c.rd(sp + 0x10 + 4 * i, 4) for i in range(8)]
        pt = tuple(mipsrun.s32(c.rd(c.r[7] + 4 * i, 4)) for i in range(3))
        calls.append(["spawn", c.r[4] & 0xFF, c.r[5] & 0xFF, c.r[6] & 0xFF, pt, words, sp])
        return SPAWNED
    cpu.hooks[EFFECT_SPAWN] = spawn

    def kind_op(c):
        calls.append(("kind_op", c.r[4], c.r[5]))
        return _kind_op(c.r[4], c.r[5])
    cpu.hooks[KIND_OP] = kind_op
    cpu.hooks[ACTOR_SWITCH] = lambda c: calls.append(("switch", c.r[4], c.r[5]))

    def collide(c):
        x, y, z = (mipsrun.s32(c.r[4]), mipsrun.s32(c.r[5]), mipsrun.s32(c.r[6]))
        calls.append(("collide", x, y, z))
        return _collide(x, y, z, 0, 0)
    cpu.hooks[COLLIDE_ACTOR] = collide
    return cpu


def _same_spawns(game, model, cpu):
    """The game's calls against the model's, a spawn's stack words read as
    the model's arguments say -- the velocity's three halfwords where it
    points, view_angles' address, or a number."""
    import mipsrun
    if len(game) != len(model):
        return False
    for g, m in zip(game, model):
        if g[0] != m[0]:
            return False
        if g[0] != "spawn":
            if tuple(g) != tuple(m):
                return False
            continue
        if tuple(g[1:5]) != tuple(m[1:5]):
            return False
        words = g[5]
        for i, a in enumerate(m[5]):
            w = words[i]
            if isinstance(a, tuple) and a[0] == "vel":
                got = tuple(mipsrun.s32(cpu.rd(w + 2 * k, 2) << 16) >> 16 for k in range(3))
                if got != a[1:]:
                    return False
            elif a == "view":
                if w != VIEW:
                    return False
            elif mipsrun.s32(w) != a:
                return False
    return True


def attack_check(out=sys.stdout, per=40):
    """player_action's attacking arms against the game's own over every
    snapshot -- its creatures in sight or not -- with effect_spawn,
    kind_behaviour_with_op, actor_switch and collide_wrapper_actor stood in
    for and what they are handed compared: the spawns (point, velocity, kind
    and every argument), the creature woken, and the state left."""
    import random
    import memcard
    import levelstate
    rng = random.Random(0xA77AC)
    ok = n = 0
    first = None
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        for _ in range(per):
            ram = bytearray(base)
            struct.pack_into("<3H", ram, VIEW & MASK, rng.choice((0, rng.randrange(-0x180, 0x180) & 0xFFFF)),
                             rng.randrange(0x1000), rng.choice((0, 0, rng.randrange(0x1000))))
            struct.pack_into("<4h", ram, CAST_OFF & MASK, rng.choice((-0xC8, rng.randrange(-0x800, 0x800))),
                             rng.choice((0xC8, 0x1F4, rng.randrange(-0x800, 0x800))),
                             rng.choice((0x190, rng.randrange(0, 0x1000))), 0)
            ram[0x801B25EA & MASK] = rng.randrange(0, 12)
            action = rng.choice(ATTACKS)
            seed = rng.randrange(1 << 30)
            g_calls = []
            cpu = _attack_cpu(ram, g_calls, levelstate.Lcg(seed))
            cpu.call(PLAYER_ACTION, action)
            st = attack_state(ram)
            m_calls = []
            attack(st, ram, action, m_calls, _kind_op, _collide, SPAWNED, levelstate.Lcg(seed))
            g_st = attack_state(cpu.ram)
            same = _same_spawns(g_calls, m_calls, cpu) and g_st == st
            n += 1
            ok += same
            if not same and first is None:
                first = (f"{os.path.basename(path)} action {action:#x}: game {g_calls} {g_st}; "
                         f"model {m_calls} {st}")
    print(f"player_action's attacking arms, against the game's own: {ok} of {n} casts, "
          f"every spawn's point, velocity and arguments, the creature woken and the "
          f"state left", file=out)
    if first:
        print("  first difference: " + first[:1500], file=out)
    return ok == n


def _norm(calls, ram):
    """The model's calls as godot/selftest.gd compares them: a creature by
    its slot, a spawn's arguments as numbers and ["vel", x, y, z] / "view"."""
    out = []
    for c in calls:
        if c[0] == "spawn":
            out.append(["spawn", c[2], c[3], list(c[4]),
                        [list(a) if isinstance(a, tuple) else a for a in c[5]]])
        elif c[0] == "switch":
            out.append(["switch", (c[1] - ACTORS) // ACTOR_STRIDE])
        elif c[0] == "collide":
            out.append(["collide", c[1], c[2], c[3]])
    return out


def export_attacks(out_dir, n=240):
    """attackcheck.json: casts of the attacking arms over the first snapshots,
    each with the creatures awake (slot, +0xe, +0x28, position, +0x50..),
    the answers the stand-ins gave in order, and the calls and state the
    model leaves, for godot/selftest.gd."""
    import json
    import random
    import memcard
    import levelstate
    rng = random.Random(0xA77E)
    cases = []
    paths = memcard._snapshots()[:6]
    for i in range(n):
        ram = bytearray(open(paths[i % len(paths)], "rb").read())
        struct.pack_into("<3H", ram, VIEW & MASK, rng.choice((0, rng.randrange(-0x180, 0x180) & 0xFFFF)),
                         rng.randrange(0x1000), rng.choice((0, 0, rng.randrange(0x1000))))
        struct.pack_into("<4h", ram, CAST_OFF & MASK, rng.choice((-0xC8, rng.randrange(-0x800, 0x800))),
                         rng.choice((0xC8, 0x1F4, rng.randrange(-0x800, 0x800))),
                         rng.choice((0x190, rng.randrange(0, 0x1000))), 0)
        ram[0x801B25EA & MASK] = rng.randrange(0, 12)
        action = ATTACKS[i % len(ATTACKS)]
        actors = []
        for k in range(ACTOR_N):
            a = ACTORS + k * ACTOR_STRIDE
            if ram[(a + 9) & MASK] == 1:
                actors.append([k, ram[(a + 0xE) & MASK], _u32(ram, a + 0x28),
                               _i32(ram, a + 0x2C), _i32(ram, a + 0x30), _i32(ram, a + 0x34),
                               _h(ram, a + 0x50), _h(ram, a + 0x52), _h(ram, a + 0x54)])
        st = attack_state(ram)
        before = dict(st)
        kinds, cols, rands = [], [], []

        def kind_op(kind, op):
            v = _kind_op(kind, op)
            kinds.append(1 if v else 0)
            return v

        def collide(x, y, z, a, b):
            v = _collide(x, y, z, a, b)
            cols.append(v)
            return v
        lcg = levelstate.Lcg(i + 1)

        def rand():
            v = lcg()
            rands.append(v)
            return v
        calls = []
        attack(st, ram, action, calls, kind_op, collide, SPAWNED, rand)
        cases.append({"action": action, "actors": actors,
                      "view": list(before["view"]), "pos": list(before["pos"]),
                      "off": [before["off_x"], before["off_y"], before["off_z"], before["off_w"]],
                      "count": before["count"], "offsets": [list(struct.unpack_from(
                          "<4h", ram, (OFFSETS + 8 * j) & MASK)) for j in range(5)],
                      "kinds": kinds, "collides": cols, "rands": rands,
                      "spawned": (SPAWNED - SLOTS) // SLOT,
                      "calls": _norm(calls, ram),
                      "after": {"off": [st["off_x"], st["off_y"], st["off_z"], st["off_w"]],
                                "view": list(st["view"]),
                                "target": (st["target"] - ACTORS) // ACTOR_STRIDE if st["target"] else -1}})
    path = os.path.join(out_dir, "attackcheck.json")
    with open(path, "w") as fh:
        json.dump({"_note": "player_action's attacking arms as tools/magic.py makes them "
                            "(whose model the game's own holds)", "cases": cases},
                  fh, separators=(",", ":"))
    return path


def check(out=sys.stdout, per=60):
    import random
    import memcard
    global ANNOUNCE
    ANNOUNCE = ANNOUNCE or _announce()
    rng = random.Random(0xCA57)
    tally = {"cast_spell": [0, 0], "player_action": [0, 0], "pending": [0, 0],
             "tail": [0, 0], "use": [0, 0]}
    first = {}
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        for _ in range(per):
            ram = bytearray(base)
            _vary(ram, rng)
            for what in tally:
                g_calls, m_calls = [], []
                cpu = _cpu(ram, g_calls)
                st = state_of(ram)
                if what == "cast_spell":
                    sp = rng.choice(list(range(0x1F)) + [0x36, 0x38, 0x40, 0x47, 0x4C, NONE])
                    cpu.call(CAST_SPELL, sp)
                    cast_spell(st, sp, ram, m_calls)
                elif what == "player_action":
                    sp = rng.choice((0x17, 0x19, 0x1A, 0x1B, 0x1C, 0x1E))
                    del cpu.hooks[PLAYER_ACTION]
                    cpu.call(PLAYER_ACTION, sp)
                    action(st, sp, m_calls)
                elif what == "pending":
                    _stretch(cpu, *PENDING_AT)
                    pending(st, m_calls)
                elif what == "use":
                    _stretch(cpu, *USE_AT)
                    rest = use_tick(st, ram)
                    if rest != (cpu.pc == USE_AT[1][1]):
                        m_calls.append(("rest", rest))
                else:
                    _stretch(cpu, *TAIL_AT)
                    tail(st, m_calls)
                g = state_of(cpu.ram)
                bad = _same(g, st)
                ok = not bad and g_calls == m_calls
                tally[what][0] += ok
                tally[what][1] += 1
                if not ok and what not in first:
                    first[what] = (f"{os.path.basename(path)}: fields {bad} "
                                   f"game {[g[k] for k in bad]} model {[st[k] for k in bad]}; "
                                   f"calls game {g_calls} model {m_calls}")
    names = {"cast_spell": "casts", "player_action": "healing and protecting actions",
             "pending": "frames of the pending action", "tail": "frames of the timers",
             "use": "frames of the USE button's stretch"}
    print("casting, against the game's own code: " + ", ".join(
        f"{tally[k][0]} of {tally[k][1]} {names[k]}" for k in tally), file=out)
    for k, v in first.items():
        print(f"  first difference in {k}: {v}", file=out)
    return all(a == b for a, b in tally.values())


def _port(st):
    """state_of's dict as godot/player.gd keeps it: the record being cast
    by its index, -1 for none."""
    d = dict(st)
    c = st["casting"]
    d["casting"] = (c - SPELL_TABLE) // 24 if SPELL_TABLE <= c < SPELL_TABLE + 96 * 24 else -1
    d["practice"] = list(st["practice"])
    d["skills"] = list(st["skills"])
    d["worn"] = list(st["worn"])
    d["working"] = list(st["working"])
    return d


def export(out_dir, n=200):
    """magiccheck.json: casts, actions, pending frames and timer frames from a
    fresh character (out/snap/b.ram) with the deciding fields at random, and
    what the model makes of each, for godot/selftest.gd."""
    import json
    import random
    path = os.path.join(ROOT, "out", "snap", "b.ram")
    if not os.path.exists(path):
        return None
    base = bytearray(open(path, "rb").read())
    rng = random.Random(0x3A61C)
    rows = []
    for i in range(n):
        ram = bytearray(base)
        _vary(ram, rng)
        for what in ("cast", "action", "pending", "timers", "use", "button"):
            st = state_of(ram)
            before = _port(st)
            calls = []
            sp = args = None
            if what == "button":
                spell = rng.choice((NONE, NONE, rng.randrange(0, 0x1F)))
                thing = rng.choice((NONE, rng.randrange(0x65, 0x96), rng.choice(sorted(EATS))))
                held = rng.choice((0, 1, 3))
                args = [spell, thing, held]
                calls = button_calls(spell, thing, held)
            elif what == "cast":
                sp = rng.choice(list(range(0x1F)) + [0x36, 0x38, 0x40, 0x47, 0x4C, NONE])
                cast_spell(st, sp, ram, calls)
            elif what == "action":
                sp = rng.choice((0x17, 0x19, 0x1A, 0x1B, 0x1C, 0x1E))
                action(st, sp, calls)
            elif what == "pending":
                pending(st, calls)
            elif what == "use":
                calls.append(["rest", 1 if use_tick(st, ram) else 0])
            else:
                tail(st, calls)
            rows.append({"what": what, "spell": sp, "args": args, "before": before,
                         "after": _port(st), "calls": [list(c) for c in calls]})
    out = os.path.join(out_dir, "magiccheck.json")
    with open(out, "w") as fh:
        json.dump({"_note": "tools/magic.py's casting over a fresh character",
                   "rows": rows}, fh, separators=(",", ":"))
    return out


if __name__ == "__main__":
    if "--check" in sys.argv:
        a = check()
        b = attack_check()
        c = button_check()
        sys.exit(0 if a and b and c else 1)
    print(__doc__)

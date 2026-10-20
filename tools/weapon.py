#!/usr/bin/env python3
"""The player's weapon: the swing, what it reaches, and what a hit does.

    python3 tools/weapon.py            every weapon's swing, and the checks
    python3 tools/weapon.py --check    the checks alone
    python3 tools/weapon.py 0 0        weapon 0 against level 0's kind 0

## The swing (held_item_tick, 0x8002d2a0, the melee half)

`player_turn` starts it on the attack button's edge when the pause after the
last blow (`0x801b24f3`) is over, through `0x8002c040`: nothing in the hands
means nothing, and neither does a swing already running (`0x801b25a4` is -1
between swings) or `0x801b2568` set. Phase 0 (`0x801b25ae`) puts the clock
`0x801b25a4` at 0, the hit time `0x801b25a6` at the record's +0x1e and the
sound time `0x801b25a8` at +0x2c, keeps the meter in `0x801b2504` -- **the
strength of the blow is the meter the swing began with** -- and empties the
meter. Weapon records are 68 bytes at `weapon_table` (`tools/equip.py`).

Then `held_item_tick`, at the end of the controller (`0x80032150`), a frame:

    clock += rec+0x1c
    the sound time crossed this frame (t <= clock < t + rate): sound 0x50
    the hit time crossed this frame:
        clock at or past rec+0x1e -- the blow: the hit time to 5000, a pause
        of 10 frames (0x801b24f3), the meter 0, the strength the whole of
        0x801b2504, and the player's point (Y - 0x3e8) to push from
        (phase 1's earlier hits carry a quarter of it and no point)
        then the probe
    clock at 0x1000: -1, the swing is over

and while the clock is -1 and the attack button is up, the meter refills:
after the pause, `2 * min((stat << 6) / (rec+1 + 1) + 1, 5000)` a frame up to
5000 (`0x80029390`), the rate cut a quarter, raised a half or halved by the
ring at `0x801b25d7` (0x42, 0x44, 0x46).

**The probe.** `vec_rotate` turns (0, 0, rec+0x1a) by (-pitch, facing, 0) --
`Ry(facing) Rx(-pitch) Rz(0)`, each product through the GTE's `>> 12` --
the Y is scaled by `(0xe10 - reach) / 1800`, and a quarter of it is walked
four times from the player's point 0x320 above the feet: `actor_spot_taken`
at radius 0x190 and height 0x258, with no creature let through (the
controller clears `actor_skip_mask` before the call). The first creature met
is struck if the view's yaw is within the kind's +0x16 of the bearing to it
and its own yaw within the kind's +0x18 of the bearing back.

## The hit (actor_take_hit, 0x8004c668)

Each of the eight offense ratings against the kind's eight defences
(+0x20..+0x2e) through `0x8004c5ec`, which is `damage_of_type` without the
fifth and with the stat added to the attack:

    A = attack * 16;  0 if A is 0;  A += stat * 16;  D = defence * 16
    d = max(0, A - D) + A * A / (2 * max(D, 0x10))

    sum = min(the eight, 0x68db7)
    dmg = ((sum * strength / 5000) + 0x80) >> 4          0x8004c92c

then the level's hook at `level_hooks+0x48` may change it -- level 0's zeroes
it for actor slot 0x20 unless it would kill. Then, for the player's blow
(flags 0x50): a blow of strength 2500 or more on a creature with HP counts
towards the stat (`0x8002a074`: one in a hundred); `op 0x13` in its sub-state
0x10 takes nothing. What is left comes off +0x1a:

    at 0 or below: award_exp(kind+0x1e) if it had HP, and the kind's
                   opcode-3 behaviour (sub_8004c0b0) -- dying
    else:          the first of the kind's opcode-2 behaviours whose +0xc
                   the damage reaches, and whose chance +2 the roll
                   (rand >> 7) is under -- or 0xff, always -- is switched in
                   (a flinch); a smaller one sets +0x84 to 0 and flag 0x200000

and, with the player's point and a kind whose +2 is under 0xf0, a push away
from it: `isqrt(isqrt(dmg << 11)) << 10`, over +2, `<< 5`, over +2 again, at
most 0x200, along the direction from the point to the creature's middle --
X and Z `>> 3`, Y `>> 6` -- into the velocity, and vertical state 0x10: a
hop, which `actor_move_vertical` lands.

**The flinch** (opcode 2, `0x80050400`): the clock at the record's rate, a
sub-state at +0x70 -- 0 sets the tint, 1 until the clock passes 0x7ff, 2
until 0xfff, 3 `actor_finish`.

## The USE button held

`player_turn` (`0x80030010`): held this frame and the last, both meters lose
500 and their pauses (`0x801b24f3`, `0x801b24f4`) go to 1 -- 60 when a meter
empties -- and `damage_scale` (`0x801b24f8`, the K by which `damage_of_type`
scales the stat's share of the defence) falls by 0x80 to 0x400. Otherwise the
magic meter refills after its pause by `meter_gain(the five working skills'
average, 0)` and K climbs back by 0x80 to 0x1000. A press alone is
`object_interact`, in `0x800305d8`.

## Checked

**69 of 69** awake creatures in 13 snapshots carry their kind's +0x1a as
their HP, which is `actor_copy_kind`'s field. And against `emu/bp25.lua`'s
recording -- a player swinging at the air and at creatures from the front and
the side: **817 of 817** frames of the weapon (clock, meter, pause, hit and
sound times, strength) from the frame before, the USE button's drain
included; **11 of 11** blows land with the HP, the flinch or not, and the
push and vertical state the model gives, from strengths of 214 to 5000; the
probe reaches the creature from where the player stood on all 11; and both
kills give the kind's experience.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movement                                                      # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FULL = 5000                 # 0x1388, both meters
PAUSE = 10                  # 0x8002db0c, frames after a blow
NEVER = 5000                # a hit or sound time that will not come
EYE_DROP = 0x3E8            # the point a blow pushes from, below the feet
PROBE_UP = 0x320            # the probe starts this far above the feet
PROBE_R, PROBE_H = 0x190, 0x258
STRONG = 0x9C4              # 0x8004c9e8
SUM_CAP = 0x68DB7
PUSH_CAP = 0x200
RINGS = {0x42: lambda r: r - (r >> 2), 0x44: lambda r: r + (r >> 1),
         0x46: lambda r: r >> 1}


def u16(raw, o):
    return struct.unpack_from("<H", raw, o)[0]


def s16(v):
    return movement.s16(v)


def trunc(a, b):
    return movement.trunc(a, b)


def records():
    import equip
    weapons, _armour = equip.tables()
    return [bytes(w) for w in weapons]


def gain(stat, rate):
    """0x80029390: a frame's refill before the doubling."""
    return min(trunc(stat << 6, rate + 1) + 1, FULL)


def refill(w, rec, stat, attack_held=False, ring=0xFF):
    """held_item_tick's idle frame (0x8002dde8)."""
    if attack_held:
        return
    if w["pause"]:
        w["pause"] -= 1
        return
    rate = rec[1]
    if ring in RINGS:
        rate = RINGS[ring](rate)
    w["meter"] = (w["meter"] + 2 * gain(stat, rate)) & 0xFFFF
    if w["meter"] > FULL:
        w["meter"] = FULL


def start(w, rec, magic=FULL, phase=0):
    """0x8002c040 (phase): the swing begins -- phase 0 the ordinary swing,
    its hit and sound times +0x1e and +0x2c; phase 1 the combination's,
    +0x26 and +0x2e. Begun on both meters full (0x801b25b3), it carries the
    record's +5 shots of its spell (0x801b25b2)."""
    if w["clock"] != -1:
        return False
    w.update(phase=phase, clock=0, hit=u16(rec, 0x26 if phase else 0x1E),
             sound=u16(rec, 0x2E if phase else 0x2C),
             strength=w["meter"], charged=(w["meter"] == FULL == magic),
             meter=0)
    if w["charged"]:
        w["shots"] = rec[5]
    return True


# The swing's times by phase (held_item_tick 0x8002d7e4, .L21): the rate the
# clock moves, the last blow's time, the time between blows, the last sound's
# time and the time between sounds -- phase 0 has a single blow and sound
FIELDS = ((0x1C, 0x1E, None, 0x2C, None), (0x24, 0x28, 0x2A, 0x30, 0x32))
FLAME_ROD = 0x21
SEATHS_SWORD = 0xD


def swing(w, rec, action_held=False, may=0, weapon=-1, magic=0):
    """One frame of a swing (held_item_tick from 0x8002d7bc). Returns the
    events: ('shot', spell, commit, n) when the weapon's spell is cast --
    phase 0's charged window (magic_window), or phase 1's every blow, +4,
    paid on the last; 'sound'; 'fire' when the flame rod (0x21) strikes on
    a full magic meter, a fire ball from (-200, 200, 400); 'guard' when
    Seath's sword in phase 1 meets its blow with the action button held --
    0x801b25b4 set and the clock held back, the blow waiting; and ('hit',
    strength, pushes) when the blow falls. At the end, the clock -1 and the
    shots gone (.L41)."""
    if w["clock"] == -1:
        return []
    phase = w.get("phase", 0)
    f = FIELDS[1 if phase else 0]
    rate, end, last = u16(rec, f[0]), u16(rec, f[1]), u16(rec, f[3])
    step = u16(rec, f[2]) if f[2] else 0
    sstep = u16(rec, f[4]) if f[4] else 0
    ev = []
    w["clock"] = s16(w["clock"] + rate)
    shot = magic_window(w, rec, action_held, may)
    if shot:
        ev.append(("shot",) + shot)
    c = w["clock"]
    if w["sound"] <= c < w["sound"] + rate:
        if rec[0] != 0xFF:
            ev.append("sound")
        w["sound"] = s16(w["sound"] + sstep) if w["sound"] < last else NEVER
    if w["hit"] <= c < w["hit"] + rate:
        if weapon == FLAME_ROD and magic == FULL:
            ev.append("fire")
        w["guard"] = 0
        if phase == 1:
            if weapon == SEATHS_SWORD and action_held:
                w["guard"] = 1
                w["clock"] = s16(c - rate)
                ev.append("guard")
                return ev
            ev.append(("shot", rec[4], c >= end, trunc(c - u16(rec, 0x26), step)))
        if c >= end:
            w["hit"], w["pause"], w["meter"] = NEVER, PAUSE, 0
            ev.append(("hit", w["strength"], True))
        else:
            w["hit"] = s16(w["hit"] + step)
            ev.append(("hit", w["strength"] >> 2, False))
    if w["clock"] >= 0x1000:
        w["clock"] = -1
        w["shots"] = 0
    return ev


COMBO_END = 0xFFFF
COMBO_TIME = 20             # 0x800303d8


def turn_combo(c, rec, press, attack_edge, binds, may, full, swing_pause):
    """player_turn's tail (0x80030298 on), once the USE stretch has let the
    frame through: the combination and the swing it starts. `c` holds
    0x801b25aa as "time" and the pointer 0x801b258c as "next", an index
    into the table player_turn writes at gp+0x1b8 -- bind_use, bind_attack,
    bind_action, 0xffff (the halves after it read 0: nothing writes them).
    `press` is the button word on a frame that newly presses one of the
    three, else 0; `binds` the three; `may` weapon_may_cast(1); `full` both
    meters 5000. 1 starts the combination's swing, 0 the ordinary one (the
    attack button's edge, no pause, no combination under way), None
    neither."""
    use, attack, action = binds
    table = [use, attack, action, COMBO_END]
    if c["time"]:
        c["time"] = (c["time"] - 1) & 0xFF
    else:
        c["next"] = 0
    if press and u16(rec, 0x24):
        k = c["next"]
        if may and rec[4] != 0xFF and press & (table[k] if k < 4 else 0) \
                and (k != 0 or full):
            c["next"] = k + 1
            if k + 1 < 4 and table[k + 1] == COMBO_END:
                return 1
            c["time"] = COMBO_TIME
        else:
            c["time"] = 0
    if swing_pause or c["time"]:
        return None
    return 0 if attack_edge else None


def rot_z(a):
    """0x80016680."""
    s, c = movement.game_sin(a), movement.game_cos(a)
    return (c, -s, 0, s, c, 0, 0, 0, 0x1000)


def mat_mul(a, b):
    """MulMatrix through the GTE: each entry the row by the column, >> 12."""
    return tuple(sum(a[3 * i + k] * b[3 * k + j] for k in range(3)) >> 12
                 for i in range(3) for j in range(3))


def vec_rotate(angles, v):
    """0x800168a8: Ry(a1) Rx(a0) Rz(a2), then ApplyMatrixLV."""
    m = mat_mul(movement.rot_matrix_x(angles[0]), rot_z(angles[2]))
    m = mat_mul(movement.rot_matrix_y(angles[1]), m)
    return movement.apply_matrix(m, v)


def _div1800(x):
    """0x8002dc34: the multiply by 0x91a2b3c5 and the shift by 10."""
    x = (x & 0xFFFFFFFF) - (0x100000000 if x & 0x80000000 else 0)
    hi = (x * (0x91A2B3C5 - 0x100000000)) >> 32
    return ((hi + x) >> 10) - (x >> 31)


def probe(pitch, facing, reach):
    """The quarter step the probe walks (0x8002dbd8)."""
    x, y, z = vec_rotate((s16(-pitch), facing, 0), (0, 0, reach))
    y = _div1800((0xE10 - reach) * y)
    return trunc(x, 4), trunc(y, 4), trunc(z, 4)


def target(player, pitch, facing, view_yaw, actors, arcs, reach):
    """The creature the blow lands on, or None. `actors` as
    movement.actor_spot_taken takes them, with 'yaw' and 'kind'; `arcs`
    {kind: (+0x16, +0x18)}."""
    d = probe(pitch, facing, reach)
    p = [player[0], player[1] - PROBE_UP, player[2]]
    for _ in range(4):
        p = [p[0] + d[0], p[1] + d[1], p[2] + d[2]]
        a = movement.actor_spot_taken(actors, *p, r=PROBE_R, own=PROBE_H,
                                      mask=0)
        if a is None:
            continue
        b = movement.vec_angle(a["pos"][0] - player[0],
                               a["pos"][2] - player[2])
        face, back = arcs[a["kind"]]
        if _facing(view_yaw, s16(b), face) and \
                _facing(a["yaw"], s16(b + 0x800), back):
            return a
    return None


def _facing(a, b, tol):
    d = (a - b) & 0xFFF
    return d <= tol or d >= 0x1000 - tol


def type_damage(stat, attack, defence):
    """0x8004c5ec: one type against a creature."""
    a = attack * 16
    if a == 0:
        return 0
    a += stat * 16
    d = defence * 16
    over = max(a - d, 0)
    if d == 0:
        d = 0x10
    return over + trunc(a * a, 2 * d)


def _div5000(x):
    """0x8004c93c: the multiply by 0x68db8bad and the shift by 11."""
    x = (x & 0xFFFFFFFF) - (0x100000000 if x & 0x80000000 else 0)
    return (((x * 0x68DB8BAD) >> 32) >> 11) - (x >> 31)


def creature_damage(stat, attacks, defence, strength):
    """actor_take_hit's arithmetic, before the level's hook."""
    s = sum(type_damage(stat, attacks[i], defence[i]) for i in range(8))
    s = min(s, SUM_CAP)
    return (_div5000(s * strength) + 0x80) >> 4


def level_guard(lv):
    """The actor slot level lv's hook at level_hooks+0x48 protects -- damage
    that would not kill it is zeroed -- or None. Read off the overlay: the
    routine divides the actor's offset by 0x88 and compares with an ori."""
    try:
        import overlay
        _hdr, ptrs = overlay.hooks(lv)
        raw, _eps, ins = overlay.overlay(lv)
    except Exception:
        return None
    if not ptrs:
        return None
    at = ptrs[18]
    body = [i for i in ins if at <= i[0] < at + 0x60]
    ops = [i[1] for i in body]
    if ops[:2] != ["lui", "addiu"] or "negu" not in ops:
        return None
    for i in body:
        if i[1] == "ori" and "$zero" in i[2]:
            return int(i[2].split(",")[-1], 0)
    return None


def knock(dmg, weight, point, pos, height):
    """The push a hit gives a creature (0x8004cc10): its velocity, or None."""
    if point is None or weight >= 0xF0:
        return None
    dx = pos[0] - point[0]
    dy = (pos[1] - (height >> 1)) - point[1]
    dz = pos[2] - point[2]
    yaw = movement.vec_angle(dx, dz)
    ln = movement.game_isqrt((dx >> 3) ** 2 + (dz >> 3) ** 2) << 3
    pitch = (-movement.vec_angle(dy, ln)) & 0xFFF
    d = movement.direction_from_angles(pitch, yaw)
    m = movement.game_isqrt(movement.game_isqrt(dmg << 11)) << 10
    m = trunc(trunc(m, weight) << 5, weight)
    m = min(m, PUSH_CAP)
    v = [s16((c * s16(m)) >> 12) for c in d]
    return (s16(v[0]) >> 3, s16(v[1]) >> 6, s16(v[2]) >> 3)


def with_op(kind, op):
    """0x8004c068: the first of the kind's behaviours with that opcode."""
    for rec in kind["behaviours"]:
        if rec["op"] == op:
            return rec
    return None


def take_hit(a, kind, dmg, strength, point, rand, guarded=False):
    """actor_take_hit (0x8004c668) for the player's blow, flags 0x50, after
    the damage: `dmg` as creature_damage gives it, `guarded` when the level's
    hook protects this slot. Changes the actor; returns (the experience it
    gives, whether the blow counts towards the stat)."""
    import ai
    op = a["op"]
    if op == 0x1A or (op == 3 and a["clock"] >= 0x60C):
        return 0, False
    if op == 0x15:
        if a["sub"] == 0:
            a["sub"] = 2
        return 0, False
    if op == 6 and a["sub"] == 0:
        a["sub"] = 2
    if guarded and dmg < a["hp"]:
        dmg = 0
    if dmg == 0:
        return 0, False
    strong = a["hp"] != 0 and strength >= STRONG
    exp = 0
    if not (op == 0x13 and a["sub"] == 0x10):
        left = a["hp"] - dmg
        if left <= 0:
            if a["hp"] != 0:
                exp = kind["exp"]
            ai.switch(a, with_op(kind, 3))
            a["hp"] = 0
        else:
            for rec in kind["behaviours"]:
                if rec["op"] != 2:
                    continue
                if dmg < u16(rec["raw"], 0xC):
                    continue                 # +0x84 = 0, flag 0x200000
                if rec["raw"][2] == 0xFF or (rand() >> 7) < rec["raw"][2]:
                    ai.switch(a, rec)
                    break
            a["hp"] = left
    v = knock(dmg, kind["weight"], point, (a["x"], a["y"], a["z"]), a["height"])
    if v is not None:
        a["vx"], a["vy"], a["vz"] = v
    a["vst"] = 0x10
    return exp, strong


def export(out_dir):
    """weapon.json: the weapon records and cases for godot/selftest.gd."""
    import json
    recs = records()
    swings = []
    for i, r in enumerate(recs[:34]):
        if u16(r, 0x1C) == 0:
            continue
        w = {"clock": -1, "meter": FULL, "pause": 0}
        start(w, r)
        frames = []
        for _ in range(40):
            ev = swing(w, r)
            frames.append([w["clock"], w["meter"], w["pause"],
                           1 if "sound" in ev else 0,
                           next((e[1] for e in ev
                                 if isinstance(e, tuple) and e[0] == "hit"), -1)])
            if w["clock"] == -1:
                break
        for _ in range(40):
            refill(w, r, 20)
            frames.append([w["clock"], w["meter"], w["pause"], 0, -1])
        swings.append([i, frames])
    probes = [[p, f, r, *probe(p, f, r)]
              for p in (0, 0x40, 0x2BC, 0xFD44 & 0xFFF)
              for f in range(0, 0x1000, 0x155)
              for r in (0x3AC, 0x500, 0x726)]
    import ai
    blob = ai.entity_blob(0)
    damages = []
    for wi in (0, 1, 5, 9, 16, 23):
        att = [u16(recs[wi], 6 + 2 * i) for i in range(8)]
        for k in (0, 3, 4, 5, 13, 15):
            e = blob[k * 120:(k + 1) * 120]
            dfn = [u16(e, 0x20 + 2 * i) for i in range(8)]
            for stat in (20, 45):
                for st in (FULL, 3777, 1250, 0):
                    damages.append([stat, *att, *dfn, st,
                                    creature_damage(stat, att, dfn, st)])
    knocks = []
    for dmg in (1, 14, 67, 300):
        for wt in (30, 100, 200, 241):
            for pt in ((100000, -13000, 60000), (101500, -12000, 58000)):
                v = knock(dmg, wt, pt, (100700, -12800, 59300), 1625)
                knocks.append([dmg, wt, *pt, *(v if v else (0, 0, 0)),
                               0 if v is None else 1])
    magic = []
    for i, r in enumerate(recs[:34]):
        if u16(r, 0x1C) == 0 or r[3] == 0xFF:
            continue
        # ACTION held before the window opens loses the shots, so the last
        # two hold it from the window's first frame, every or every other
        lo = -(-u16(r, 0x20) // u16(r, 0x1C)) - 1
        for pat in range(5):
            for may in (0, 1):
                for mag in (FULL, FULL - 1):
                    w = {"clock": -1, "meter": FULL, "pause": 0}
                    start(w, r, mag)
                    frames = []
                    for f in range(40):
                        held = (True, f % 2 == 0, f < 6, f >= lo,
                                f >= lo and (f - lo) % 2 == 0)[pat]
                        ev = swing(w, r, held, may)
                        shot = next((e[1:] for e in ev
                                     if isinstance(e, tuple) and e[0] == "shot"), None)
                        frames.append([int(held), w["clock"], w.get("shots", 0),
                                       *((shot[0], int(shot[1]), shot[2])
                                         if shot else (-1, 0, 0))])
                        if w["clock"] == -1:
                            break
                    magic.append([i, may, mag, frames])
    import random
    rng = random.Random(0xCF0)
    # magic_window alone, on clocks at the window's edges and shots left
    windows = []
    for i, r in enumerate(recs[:34]):
        if r[3] == 0xFF:
            continue
        lo, hi = u16(r, 0x20), u16(r, 0x22)
        for c in (lo - 1, lo, lo + 1, hi - 1, hi, hi + 1, rng.randrange(0x1000)):
            for _ in range(3):
                w = {"phase": rng.choice((0, 0, 0, 1)), "clock": c,
                     "charged": rng.randrange(4) != 0, "shots": rng.randrange(r[5] + 2)}
                held, may = rng.randrange(4) != 0, rng.randrange(4) != 0
                case = [i, w["phase"], c, int(w["charged"]), w["shots"], int(held), int(may)]
                shot = magic_window(w, r, held, may)
                windows.append(case + [w["shots"], *((shot[0], int(shot[1]), shot[2])
                                                     if shot else (-1, 0, 0))])
    # the second swing and the flame rod, frame by frame
    swings2 = []
    for i in (2, 13, 14, 15, 16, 17, FLAME_ROD):
        r = recs[i]
        phase = 0 if i == FLAME_ROD else 1
        for pat in range(4):
            for mag in (FULL, FULL - 1):
                w = {"clock": -1, "meter": FULL, "pause": 0}
                start(w, r, mag, phase)
                frames = []
                for f in range(60):
                    held = (False, True, f < 12, f % 3 == 0)[pat]
                    ev = swing(w, r, held, 0, i, mag)
                    shot = next((e[1:] for e in ev
                                 if isinstance(e, tuple) and e[0] == "shot"), None)
                    hit = next((e[1:] for e in ev
                                if isinstance(e, tuple) and e[0] == "hit"), None)
                    frames.append([int(held), w["clock"], w["hit"], w["sound"], w["pause"],
                                   w["meter"], w.get("guard", 0),
                                   *((shot[0], int(shot[1]), shot[2]) if shot else (-1, 0, 0)),
                                   *((hit[0], int(hit[1])) if hit else (-1, 0)),
                                   int("fire" in ev), int("sound" in ev)])
                    if w["clock"] == -1:
                        break
                swings2.append([i, phase, mag, frames])
    # the combination: runs of presses, frame by frame
    combos = []
    binds = (0x40, 0x80, 0x10)
    for _ in range(200):
        i = rng.choice((2, 13, 14, 15, 16, 17, 7, 0))
        c = {"time": 0, "next": 0}
        frames = []
        for f in range(16):
            press = rng.choice((0, 0, 0x40, 0x80, 0x10, 0xC0)) if rng.randrange(3) else \
                (binds + (0x80,))[min(c["next"], 3)]
            edge = bool(press & 0x80) and rng.randrange(2) == 1
            may, full, pause = rng.randrange(5) != 0, rng.randrange(4) != 0, \
                rng.choice((0, 0, 0, 1))
            got = turn_combo(c, recs[i], press, edge, binds, may, full, pause)
            frames.append([press, int(edge), int(may), int(full), pause,
                           c["time"], c["next"], -1 if got is None else got])
        combos.append([i, frames])
    mays = []
    for _ in range(300):
        wi = rng.choice(list(range(34)) + [0xFF])
        rec = recs[wi] if wi < len(recs) else bytes(68)
        which = rng.randrange(2)
        unlocked = [rng.randrange(2) for _ in range(0x60)]
        stat = rng.choice((0, 0x31, 0x32, 0x63))
        skills = [rng.choice((0x31, 0x32, 0x50)) for _ in range(5)]
        mays.append([wi, which, stat, skills, unlocked,
                     may_cast(wi, rec, which, lambda k: unlocked[k], stat, skills)])
    path = os.path.join(out_dir, "weapon.json")
    with open(path, "w") as fh:
        json.dump({"_note": "FDAT 97 block 1, the 68-byte weapon records, and "
                            "tools/weapon.py's answers for selftest.gd",
                   "records": [list(r) for r in recs],
                   "guard": {"0": level_guard(0)},
                   "swings": swings, "probes": probes, "damages": damages,
                   "knocks": knocks, "magic": magic, "windows": windows,
                   "mays": mays, "swings2": swings2, "combos": combos}, fh,
                  separators=(",", ":"))
    return path


# --- the weapons' own magic --------------------------------------------------------

SHOTS, CHARGED, PHASE = 0x801B25B2, 0x801B25B3, 0x801B25AE
SPELL_TABLE = 0x801B77EC


def may_cast(weapon, rec, which, unlocked, stat, skills):
    """weapon_may_cast(which): may the weapon in hand cast its spell -- +3 for
    which 0, the swing's, +4 for which 1, the second swing's. The spell, if
    the record names one, must be unlocked (its spell_table +0); then
    excellector (2) and weapons 0xd..0x11 may, and every other only with
    the effective stat (0x801b2524) and the least of the five working skills
    both 50 or more. `unlocked(spell)` is that +0."""
    if weapon != 0xFF:
        sp = rec[3 + which]
        if sp != 0xFF and unlocked(sp) == 0:
            return 0
    if weapon == 2 or 0xD <= weapon < 0x12:
        return 1
    least = 0x3E7
    for v in skills:
        if v < least:
            least = v
    return 1 if stat >= 0x32 and least >= 0x32 else 0


def spell_begin(st, spell, commit, n, cost):
    """0x8002d130 (spell, commit, n): with the MP for its cost, the spell's
    record becomes the one cast (casting_spell); on the commit the magic
    meter and its pause go to 0 and the MP pays the cost; the eye's offset
    for the spell -- 0x42's turned by n << 9 (cos, sin >> 3, 0x258 out),
    0x47's 300 n - 300 across, every other (200, 200, 400) -- and then
    player_action, at once. False with too little MP."""
    import movement
    if st["mp"] < cost:
        return False
    st["casting"] = spell
    if commit:
        st["meter"] = 0
        st["magic_pause"] = 0
        st["mp"] = (st["mp"] - cost) & 0xFFFF
    if spell == 0x42:
        a = (n << 9) & 0xFFFFFFFF
        st["off_x"] = s16(movement.game_cos(a) >> 3)
        st["off_y"] = s16(movement.game_sin(a) >> 3)
        st["off_z"] = 0x258
    elif spell == 0x47:
        st["off_x"], st["off_y"], st["off_z"] = 0, s16(300 * n - 300), 0x190
    else:
        st["off_x"], st["off_y"], st["off_z"] = 0xC8, 0xC8, 0x190
    return True


def magic_window(w, rec, action_held, may):
    """held_item_tick's phase-0 stretch (0x8002d81c): after the clock moves,
    with the record's spell +3, the swing begun on both meters full, the
    weapon allowed (may_cast(0)) and ACTION held, a frame inside the window
    +0x20..+0x22 spends a shot -- spell_begin(+3, the first shot, the shots
    left) -- and a frame outside it loses them all. (spell, commit, n) for
    the shot, or None."""
    if w.get("phase", 0) != 0 or rec[3] == 0xFF or not w.get("charged") or not may \
            or not action_held:
        return None
    c = w["clock"]
    if c < u16(rec, 0x20) or u16(rec, 0x22) < c:
        w["shots"] = 0
        return None
    if w["shots"] == 0:
        return None
    shot = (rec[3], w["shots"] == rec[5], w["shots"])
    w["shots"] = (w["shots"] - 1) & 0xFF
    return shot


def magic_check(out=sys.stdout, n=200):
    """The weapons' magic against the game's own code over a snapshot:
    swing_start (both phases) on random meters; weapon_may_cast on random
    weapons, unlocked spells, stats and skills; spell_begin on random MP,
    spells, commits and shots, player_action stood in for; and
    held_item_tick's phase-0 frame on random clocks, shots and buttons, the
    blow and the sound out of reach, spell_begin stood in for."""
    import glob
    import random
    import mipsrun
    snaps = sorted(glob.glob(os.path.join(ROOT, "out", "snap", "a1.ram")))
    if not snaps:
        print("  no snapshot to run the weapons' magic over", file=out)
        return True
    base = bytearray(open(snaps[0], "rb").read())
    table = records()
    rng = random.Random(0x3A61C)
    tally = {}
    first = []

    def note(name, same, detail):
        a, b = tally.get(name, (0, 0))
        tally[name] = (a + same, b + 1)
        if not same and not first:
            first.append(f"{name}: {detail}")

    magic_weapons = [i for i in range(0x22) if table[i][3] != 0xFF or table[i][4] != 0xFF]
    for i in range(n):
        # swing_start
        weapon = rng.choice(magic_weapons + [0, 3])
        rec = table[weapon]
        phase = rng.randrange(2)
        meter = rng.choice((FULL, FULL, 4999, 0, rng.randrange(FULL)))
        magic = rng.choice((FULL, FULL, 4999, rng.randrange(FULL)))
        cpu = mipsrun.CPU(base)
        cpu.wr(0x801B25AF, 1, weapon)
        cpu.wr(0x801B2594, 4, 0x801D37A4 + 68 * weapon)
        cpu.wr(0x801B25A4, 2, 0xFFFF)
        cpu.wr(0x801B2568, 2, 0)
        cpu.wr(0x801B2502, 2, meter)
        cpu.wr(0x801B2506, 2, magic)
        cpu.call(0x8002C040, phase)
        g = (cpu.rd(0x801B25A4, 2), cpu.rd(0x801B25A6, 2), cpu.rd(0x801B25A8, 2),
             cpu.rd(0x801B2504, 2), cpu.rd(0x801B2502, 2), cpu.rd(CHARGED, 1),
             cpu.rd(SHOTS, 1) if meter == FULL == magic else None, cpu.rd(PHASE, 1))
        m = (0, u16(rec, 0x26 if phase else 0x1E), u16(rec, 0x2E if phase else 0x2C), meter, 0,
             1 if meter == FULL == magic else 0, rec[5] if meter == FULL == magic else None, phase)
        note("swing_start", g == m, f"weapon {weapon:#x} phase {phase}: game {g} model {m}")
        # weapon_may_cast
        weapon = rng.choice(magic_weapons + [0xFF, 1])
        rec = table[weapon] if weapon != 0xFF else bytes(68)
        which = rng.randrange(2)
        cpu = mipsrun.CPU(base)
        cpu.wr(0x801B25AF, 1, weapon)
        cpu.wr(0x801B2594, 4, 0x801D37A4 + 68 * (weapon if weapon != 0xFF else 0))
        unl = {}
        for sp in (rec[3], rec[4]):
            if sp != 0xFF:
                unl[sp] = rng.randrange(2)
                cpu.wr(SPELL_TABLE + 24 * sp, 1, unl[sp])
        stat = rng.choice((0x31, 0x32, 0x40, rng.randrange(120)))
        skills = [rng.choice((0x31, 0x32, 60, rng.randrange(120))) for _ in range(5)]
        cpu.wr(0x801B2524, 2, stat)
        for k, v in enumerate(skills):
            cpu.wr(0x801B2526 + 2 * k, 2, v)
        g = cpu.call(0x8002CFE0, which) & 0xFF
        if weapon == 0xFF:
            rec = table[0]
        m = may_cast(weapon, rec if weapon != 0xFF else bytes(68), which,
                     lambda sp: unl.get(sp, 0), stat, skills)
        note("weapon_may_cast", g == m, f"weapon {weapon:#x} which {which}: game {g} model {m}")
        # spell_begin
        spell = rng.choice((0x36, 0x37, 0x38, 0x42, 0x43, 0x47, 0x48, 0x4C, 0x0D, 0x00))
        cost = u16(bytes(base[(SPELL_TABLE & 0x1FFFFF) + 24 * spell:]), 0x16)
        mp = rng.choice((0, cost, cost - 1, cost + 1, 999)) & 0xFFFF
        commit = rng.randrange(2)
        shots = rng.randrange(1, 6)
        cpu = mipsrun.CPU(base)
        cpu.wr(0x801B2500, 2, mp)
        cpu.wr(0x801B2506, 2, 4321)
        cpu.wr(0x801B24F4, 2, 7)
        cpu.wr(0x801B2590, 4, 0)
        called = []
        cpu.hooks[0x8002C30C] = lambda c: called.append(1)
        cpu.hooks[0x8001576C] = lambda c: 0
        cpu.call(0x8002D130, spell, commit, shots)
        g = (cpu.rd(0x801B2500, 2), cpu.rd(0x801B2506, 2), cpu.rd(0x801B24F4, 2),
             cpu.rd(0x801B2590, 4), mipsrun.s32(cpu.rd(0x801B2630, 2) << 16) >> 16,
             mipsrun.s32(cpu.rd(0x801B2632, 2) << 16) >> 16, cpu.rd(0x801B2634, 2), len(called))
        st = {"mp": mp, "meter": 4321, "magic_pause": 7, "casting": None,
              "off_x": None, "off_y": None, "off_z": None}
        did = spell_begin(st, spell, commit, shots, cost)
        m = (st["mp"], st["meter"], st["magic_pause"],
             SPELL_TABLE + 24 * spell if did else 0,
             st["off_x"] if did else g[4], st["off_y"] if did else g[5],
             st["off_z"] if did else g[6], 1 if did else 0)
        note("spell_begin", g == m, f"spell {spell:#x} mp {mp} cost {cost} commit {commit} n {shots}: "
                                     f"game {g} model {m}")
        # held_item_tick's phase-0 window
        weapon = rng.choice([w_ for w_ in magic_weapons if table[w_][3] != 0xFF])
        rec = table[weapon]
        lo, hi = u16(rec, 0x20), u16(rec, 0x22)
        clock0 = rng.choice((lo - u16(rec, 0x1C), hi - u16(rec, 0x1C), lo - 2 * u16(rec, 0x1C),
                             hi, rng.randrange(0, 0xF00))) & 0xFFFF
        if clock0 & 0x8000:
            clock0 = 0
        w = {"phase": 0, "clock": clock0, "charged": rng.choice((1, 1, 0)),
             "shots": rng.choice((0, 1, rec[5], rng.randrange(rec[5] + 1)))}
        action = rng.choice((True, True, False))
        unlocked = rng.choice((1, 1, 0))
        stat, skills = rng.choice((0x60, 0x20)), [rng.choice((0x60, 0x20))] * 5
        cpu = mipsrun.CPU(base)
        cpu.wr(0x801B25AF, 1, weapon)
        cpu.wr(0x801B2594, 4, 0x801D37A4 + 68 * weapon)
        cpu.wr(0x801B25A4, 2, w["clock"])
        cpu.wr(0x801B25A6, 2, 0x1388)
        cpu.wr(0x801B25A8, 2, 0x1388)
        cpu.wr(PHASE, 1, 0)
        cpu.wr(CHARGED, 1, w["charged"])
        cpu.wr(SHOTS, 1, w["shots"])
        cpu.wr(SPELL_TABLE + 24 * rec[3], 1, unlocked)
        cpu.wr(0x801B2524, 2, stat)
        for k, v in enumerate(skills):
            cpu.wr(0x801B2526 + 2 * k, 2, v)
        bind_action = cpu.rd(0x80081874, 2)
        cpu.wr(0x801B265C, 2, bind_action if action else 0)
        begun = []
        cpu.hooks[0x8002D130] = lambda c: begun.append((c.r[4] & 0xFF, c.r[5], c.r[6] & 0xFF))
        cpu.hooks[0x8001576C] = lambda c: 0
        try:
            cpu.call(0x8002D2A0, 0, 0, 0)
        except mipsrun.Stop as ex:
            note("the window", False, f"stopped: {ex}")
            continue
        g = (begun[0] if begun else None, cpu.rd(SHOTS, 1))
        may = may_cast(weapon, rec, 0, lambda sp: unlocked, stat, skills)
        mw = dict(w, hit=NEVER, sound=NEVER)
        ev = swing(mw, rec, action, may)
        shot = next((e[1:] for e in ev if e[0] == "shot"), None)
        m = ((shot[0], 1 if shot[1] else 0, shot[2]) if shot else None, mw["shots"])
        note("the window", g == m, f"weapon {weapon:#x} clock {clock0:#x} {w}: game {g} model {m}")
    combo_runs(base, table, rng, note, n)
    swing_runs(base, table, rng, note, n)
    line = ", ".join(f"{k} {a} of {b}" for k, (a, b) in tally.items())
    print(f"  the weapons' magic against the game's own code over a1: {line}", file=out)
    if first:
        print("  first difference: " + first[0], file=out)
    return all(a == b for a, b in tally.values())


def _weapon_cpu(base, weapon):
    import mipsrun
    cpu = mipsrun.CPU(base)
    cpu.wr(0x801B25AF, 1, weapon)
    cpu.wr(0x801B2594, 4, 0x801D37A4 + 68 * weapon)
    return cpu


def combo_runs(base, table, rng, note, n):
    """player_turn, the game's own, a frame at a time on random buttons,
    combination times and pointers, weapons, meters and unlocked spells:
    cast_spell and swing_start stood in for, what the tail leaves --
    0x801b25aa, the pointer, which swing begins -- against turn_combo, and
    whether magic A was cast."""
    mask_words = (0, 0x40, 0x80, 0x10, 0xC0, 0x50, 0x90)
    for _ in range(n * 2):
        weapon = rng.choice((2, 13, 14, 15, 16, 17, 7, 9, 0))
        rec = table[weapon]
        cpu = _weapon_cpu(base, weapon)
        use, attack, action = (cpu.rd(0x80081876, 2), cpu.rd(0x80081870, 2),
                               cpu.rd(0x80081874, 2))
        now, prev = rng.choice(mask_words), rng.choice(mask_words + (0, 0))
        time = rng.choice((0, 0, 1, 2, 20))
        k = rng.choice((0, 0, 1, 2, 2, 3, 4))
        if rng.randrange(2):                # the right button, newly pressed
            now, prev = (use, attack, action, attack, 0)[k], 0
            time = time or (1 if k else 0)
        full = rng.randrange(3) != 0
        wm, mm = (FULL, FULL) if full else rng.choice(((FULL, 4999), (4999, FULL), (0, FULL)))
        pause = rng.choice((0, 0, 0, 1))
        unlocked = rng.choice((1, 1, 0))
        stat, skills = 0x60, [0x60] * 5
        cpu.wr(0x801B265C, 2, now)
        cpu.wr(0x801B265E, 2, prev)
        cpu.wr(0x801B25AA, 1, time)
        cpu.wr(0x801B258C, 4, 0x8009C3CC + 2 * k)
        cpu.wr(0x801B2502, 2, wm)
        cpu.wr(0x801B2506, 2, mm)
        cpu.wr(0x801B24F4, 1, 5)            # the magic meter's pause: no refill
        cpu.wr(0x801B24F3, 1, pause)
        cpu.wr(0x801B25B2, 1, 0)
        cpu.wr(0x801B25E9, 1, 0xFF)         # no action pending
        cpu.wr(0x801B25D8, 1, 0xFF)
        cpu.wr(0x801B25A4, 2, 0xFFFF)
        if rec[4] != 0xFF:
            cpu.wr(SPELL_TABLE + 24 * rec[4], 1, unlocked)
        cpu.wr(0x801B2524, 2, stat)
        for j, v in enumerate(skills):
            cpu.wr(0x801B2526 + 2 * j, 2, v)
        started, cast = [], []
        cpu.hooks[0x8002C040] = lambda c: started.append(c.r[4])
        cpu.hooks[0x8002DEEC] = lambda c: cast.append(c.r[4] & 0xFF)
        cpu.hooks[0x8001576C] = lambda c: 0
        cpu.call(0x8002FE1C)
        g = (cpu.rd(0x801B25AA, 1), (cpu.rd(0x801B258C, 4) - 0x8009C3CC) // 2,
             started[0] if started else None, len(cast))
        c = {"time": time, "next": k}
        mask = use | attack | action
        cast_a = bool(now & action and not prev & action) and time == 0
        if now & use and prev & use:
            got = None                      # the USE stretch, and back
        else:
            press = now if now & mask and not prev & mask else 0
            got = turn_combo(c, rec, press, bool(now & attack and not prev & attack),
                             (use, attack, action),
                             may_cast(weapon, rec, 1, lambda sp: unlocked, stat, skills),
                             wm == FULL == mm, pause)
        m = (c["time"], c["next"], got, int(cast_a))
        note("player_turn's combination", g == m,
             f"weapon {weapon} now {now:#x} prev {prev:#x} time {time} next {k} "
             f"meters {wm},{mm} pause {pause}: game {g} model {m}")


def swing_runs(base, table, rng, note, n):
    """held_item_tick, the game's own, a frame of a swing: phase 1 of the
    six weapons with a second spell, and phase 0 of the flame rod, on random
    clocks round the blows and sounds, buttons and meters; spell_begin,
    effect_spawn, the aim and actor_take_hit stood in for, the blow's
    strength read where the probe begins (0x8002dbd8). Against swing."""
    import mipsrun
    for _ in range(n * 2):
        weapon = rng.choice((2, 13, 14, 15, 16, 17, FLAME_ROD, FLAME_ROD))
        rec = table[weapon]
        phase = 0 if weapon == FLAME_ROD else 1
        f = FIELDS[phase]
        rate = u16(rec, f[0])
        hit0 = u16(rec, 0x26 if phase else 0x1E)
        step = u16(rec, f[2]) if f[2] else 0
        hit = rng.choice((hit0, hit0 + step, hit0 + 2 * step, NEVER, hit0))
        clock = s16(hit - rng.choice((rate, rate, 1, 0, rate + 1, 3 * rate)))
        if clock < 0:
            clock = 0
        sound = rng.choice((u16(rec, 0x2E if phase else 0x2C), NEVER, clock + rate))
        action = rng.randrange(2) == 1
        magic = rng.choice((FULL, FULL, 4999))
        strength = rng.choice((FULL, 3000, 17))
        w = {"phase": phase, "clock": clock, "hit": hit, "sound": s16(sound),
             "charged": 0, "shots": 0, "pause": 0, "meter": 0, "strength": strength,
             "guard": 0}
        cpu = _weapon_cpu(base, weapon)
        cpu.wr(0x801B25AE, 1, phase)
        cpu.wr(0x801B25A4, 2, clock)
        cpu.wr(0x801B25A6, 2, hit)
        cpu.wr(0x801B25A8, 2, w["sound"])
        cpu.wr(0x801B25B3, 1, 0)
        cpu.wr(0x801B25B2, 1, 0)
        cpu.wr(0x801B25B4, 1, 0)
        cpu.wr(0x801B2504, 2, strength)
        cpu.wr(0x801B2502, 2, 1234)
        cpu.wr(0x801B24F3, 1, 0)
        cpu.wr(0x801B2506, 2, magic)
        bind_action = cpu.rd(0x80081874, 2)
        cpu.wr(0x801B265C, 2, bind_action if action else 0)
        begun, spawned, blows = [], [], []
        cpu.hooks[0x8002D130] = lambda c: begun.append((c.r[4] & 0xFF, c.r[5], c.r[6]))
        cpu.hooks[0x80053C84] = lambda c: spawned.append((c.r[4], c.r[5], c.r[6]))
        cpu.hooks[0x8002C164] = lambda c: 0
        cpu.hooks[0x8004C668] = lambda c: 0
        cpu.hooks[0x8001576C] = lambda c: 0
        cpu.watch[0x8002DBD8] = lambda c: blows.append(
            (c.rd(c.r[29] + 0xB8, 4), int(c.rd(c.r[29] + 0xA8, 4) != 0)))
        try:
            cpu.call(0x8002D2A0, 0, 0, 0)
        except mipsrun.Stop as ex:
            note("held_item_tick's swing", False, f"stopped: {ex}")
            continue
        g = (mipsrun.s32(cpu.rd(0x801B25A4, 2) << 16) >> 16,
             mipsrun.s32(cpu.rd(0x801B25A6, 2) << 16) >> 16,
             mipsrun.s32(cpu.rd(0x801B25A8, 2) << 16) >> 16,
             cpu.rd(0x801B24F3, 1), cpu.rd(0x801B2502, 2), cpu.rd(0x801B25B4, 1),
             begun[0] if begun else None, int(bool(spawned)),
             (cpu.rd(0x801B2630, 2), cpu.rd(0x801B2632, 2), cpu.rd(0x801B2634, 2))
             if spawned else None, blows[0] if blows else None)
        w["meter"] = 1234
        ev = swing(w, rec, action, 0, weapon, magic)
        shot = next((e[1:] for e in ev if isinstance(e, tuple) and e[0] == "shot"), None)
        hitev = next((e[1:] for e in ev if isinstance(e, tuple) and e[0] == "hit"), None)
        m = (w["clock"], w["hit"], w["sound"], w["pause"], w["meter"], w["guard"],
             (shot[0], int(shot[1]), shot[2] & 0xFFFFFFFF) if shot else None,
             int("fire" in ev), (0xFF38, 0xC8, 0x190) if "fire" in ev else None,
             (hitev[0], int(hitev[1])) if hitev else None)
        note("held_item_tick's swing", g == m,
             f"weapon {weapon:#x} phase {phase} clock {clock} hit {hit} sound {sound} "
             f"action {action} magic {magic}: game {g} model {m}")


def check(out=sys.stdout):
    """The HP actor_copy_kind leaves, against every snapshot."""
    import glob
    ok = n = snaps = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        d = open(f, "rb").read()
        seen = False
        for k in range(200):
            a = 0x185DA8 + 0x88 * k
            if d[a + 9] != 1:
                continue
            seen = True
            kind = d[a + 2]
            n += 1
            ok += u16(d, a + 0x1A) == u16(d, 0x18C7E8 + 120 * kind + 0x1A)
        snaps += seen
    print(f"  {ok} of {n} awake creatures over {snaps} snapshots carry their "
          f"kind's +0x1a as their HP", file=out)
    return ok == n


ATTACK_BIT = 0x0080          # SQUARE: bind_attack in the session's scheme
USE_BIT = 0x0040             # CROSS: its bind_use
DRAIN = 0x1F4                # 0x8003006c: 0xfe0c added, a frame
SPENT = 0x3C                 # the pause when it empties
K_FULL, K_LOW, K_STEP = 0x1000, 0x400, 0x80


def use_held(w, ring_b=0xFF):
    """player_turn with the USE button held this frame and the last
    (0x8003002c): the weapon meter and the magic meter each 500 down, their
    pauses (0x801b24f3, 0x801b24f4) 1 -- 60 when one empties, but for the
    rings 0x4d and 0x4f -- and damage_scale (0x801b24f8, the K in
    damage_of_type) 0x80 down to 0x400. Let go, K climbs back 0x80 a frame to
    0x1000 (0x80030264)."""
    empty = 0 if ring_b in (0x4D, 0x4F) else SPENT
    w["pause"] = 1
    m = s16(w["meter"] - DRAIN)
    if m <= 0:
        w["meter"], w["pause"] = 0, (1 if ring_b in (0x4D, 0x4F) else SPENT)
    else:
        w["meter"] = m
    if "magic" in w:
        w["mpause"] = 1
        m = s16(w["magic"] - DRAIN)
        w["magic"], w["mpause"] = ((0, empty) if m <= 0 else (m, 1))
    w["k"] = max(s16(w.get("k", K_FULL) - K_STEP), K_LOW)


def use_released(w):
    w["k"] = min(w.get("k", K_FULL) + K_STEP, K_FULL)
SWING_LINE = None


def load_log(path=None):
    """out/lua_bp25.log: [('SWING', dict)], ('HIT', dict, out), ('EXP', n)."""
    import re
    path = path or os.path.join(ROOT, "out", "lua_bp25.log")
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path):
        tag = line.split(" ", 1)[0]
        kv = dict(re.findall(r"(\w+)=(\S+)", line))
        if tag == "SWING":
            rows.append(("SWING", {k: (int(v, 16) if k == "btn" else
                                       [int(x) for x in v.split(",")] if "," in v
                                       else int(v)) for k, v in kv.items()}))
        elif tag == "HIT":
            d = {}
            for k, v in kv.items():
                if k == "flags":
                    d[k] = int(v, 16)
                elif k == "point":
                    d[k] = None if v == "none" else [int(x) for x in v.split(",")]
                elif "," in v:
                    d[k] = [int(x) for x in v.split(",")]
                else:
                    d[k] = int(v)
            rows.append(("HIT", d))
        elif tag == "HITOUT":
            rows.append(("HITOUT", {k: ([int(x) for x in v.split(",")] if "," in v
                                        else int(v)) for k, v in kv.items()}))
        elif tag == "EXP":
            rows.append(("EXP", int(kv["a0"])))
    return rows


def check_log(out=sys.stdout, verbose=False):
    """emu/bp25.lua's recording: the swing frame by frame, and every blow."""
    import ai
    rows = load_log()
    if not rows:
        print("  no out/lua_bp25.log: ./emu/run.sh debug bp25.lua, and fight",
              file=out)
        return True
    recs = records()
    # the swing, locked: each frame from the one before
    sw = [r[1] for r in rows if r[0] == "SWING"]
    ok = n = 0
    for a, b in zip(sw, sw[1:]):
        if b["vb"] - a["vb"] != 4 or a["wpn"] != b["wpn"]:
            continue
        rec = recs[a["wpn"]]
        w = {"clock": a["clock"], "meter": a["meter"], "pause": a["pause"],
             "hit": a["hit"], "sound": a["snd"], "strength": a["str"]}
        if w["clock"] == -1:
            refill(w, rec, 20, bool(a["btn"] & ATTACK_BIT))
        else:
            swing(w, rec)
        if b["btn"] & USE_BIT and a["btn"] & USE_BIT:
            use_held(w)
        if (b["btn"] & ATTACK_BIT and not a["btn"] & ATTACK_BIT
                and w["pause"] == 0):
            start(w, rec)
        n += 1
        got = (w["clock"], w["meter"], w["pause"], w["hit"], w["sound"],
               w["strength"])
        want = (b["clock"], b["meter"], b["pause"], b["hit"], b["snd"], b["str"])
        if got == want:
            ok += 1
        elif verbose:
            print(f"  vb {a['vb']}: model {got}, game {want}", file=out)
    print(f"  {ok} of {n} frames of the weapon -- clock, meter, pause, hit and "
          f"sound times, strength -- from the frame before", file=out)
    good = ok == n
    # the blows: the damage, the flinch, the push, the experience, the reach
    blob = ai.entity_blob(0)
    kinds = {k["kind"]: k for k in ai.kinds(0)}
    by_vb = {r["vb"]: r for r in sw}
    dm = fl = pu = ex = tg = hits = kills = 0
    exps = [r[1] for r in rows if r[0] == "EXP"]
    ei = 0
    for i, r in enumerate(rows):
        if r[0] != "HIT":
            continue
        h = r[1]
        after = next((x[1] for x in rows[i + 1:i + 4] if x[0] == "HITOUT"), None)
        if after is None:
            continue
        hits += 1
        e = blob[h["kind"] * 120:(h["kind"] + 1) * 120]
        dfn = [u16(e, 0x20 + 2 * j) for j in range(8)]
        dmg = creature_damage(h["stat"], h["att"], dfn, h["str"])
        kd = kinds[h["kind"]]
        a = {"op": h["op"], "sub": h["sub"], "clock": 0, "hp": h["hp"],
             "x": h["pos"][0], "y": h["pos"][1], "z": h["pos"][2],
             "height": u16(e, 0x14), "vx": 0, "vy": 0, "vz": 0, "vst": 0,
             "rec": None, "phase": 0, "prev": 0}
        kind = dict(ai.kind_of(0, h["kind"]), behaviours=kd["behaviours"])
        exp, _strong = take_hit(a, kind, dmg, h["str"], h["point"],
                                lambda: 0)
        dm += a["hp"] == after["hp"]
        fl += a["op"] == after["op"]
        pu += (a["vx"], a["vy"], a["vz"]) == tuple(after["vel"]) and \
            a["vst"] == after["vst"]
        if a["hp"] == 0:
            kills += 1
            ex += ei < len(exps) and exps[ei] == exp
            ei += 1
        # the reach: the probe from where the player stood that frame
        p = by_vb.get(h["vb"])
        if p is not None:
            one = [{"pos": tuple(h["pos"]), "radius": u16(e, 0x12),
                    "height": u16(e, 0x14), "flags": 0, "b0e": h["op"],
                    "yaw": h["yaw"], "kind": h["kind"]}]
            got = target(p["pos"], p["pitch"], p["facing"], p["view"], one,
                         {h["kind"]: (s16f(e, 0x16), s16f(e, 0x18))},
                         u16(recs[p["wpn"]], 0x1A))
            tg += got is not None
        elif verbose:
            print(f"  hit at vb {h['vb']}: no swing line", file=out)
        if verbose and (a["hp"] != after["hp"] or a["op"] != after["op"]):
            print(f"  hit vb {h['vb']}: model hp {a['hp']} op {a['op']}, game "
                  f"{after['hp']} {after['op']}", file=out)
    print(f"  {hits} blows landed: the HP after {dm} of {hits}, the opcode after "
          f"(a flinch or not) {fl} of {hits}, the push and vertical state "
          f"{pu} of {hits}, the probe reaching the creature from where the "
          f"player stood {tg} of {hits}; {ex} of {kills} kills gave the "
          f"kind's experience", file=out)
    good &= dm == fl == pu == tg == hits and ex == kills
    return good


def s16f(raw, o):
    return struct.unpack_from("<h", raw, o)[0]


def table(out=sys.stdout):
    import equip
    names = equip.item_names()
    print(" id  rate  hit  frames blow reach refill  name", file=out)
    for i, r in enumerate(records()[:34]):
        rate = u16(r, 0x1C)
        if rate == 0:
            continue
        hit = u16(r, 0x1E)
        print(f" {i:2d} {rate:#6x} {hit:#6x} {-(-0x1000 // rate):4d} "
              f"{-(-hit // rate):4d} {u16(r, 0x1A):#6x} {r[1]:4d}  "
              f"{names.get(i, '')}", file=out)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--check":
        sys.exit(0 if (check() and check_log() and magic_check()) else 1)
    if a and a[0] == "--log":
        sys.exit(0 if check_log(verbose=True) else 1)
    if len(a) == 2:
        import ai
        w = records()[int(a[0])]
        blob = ai.entity_blob(0)
        e = blob[int(a[1]) * 120:(int(a[1]) + 1) * 120]
        dfn = [u16(e, 0x20 + 2 * i) for i in range(8)]
        att = [u16(w, 6 + 2 * i) for i in range(8)]
        for strength in (FULL, FULL // 2, FULL // 4):
            print(f"  strength {strength}: {creature_damage(20, att, dfn, strength)}"
                  f" of {u16(e, 0x1A)} HP")
    else:
        table()
        check()

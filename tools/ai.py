#!/usr/bin/env python3
"""What a creature does: its kind's behaviours, and the machine that runs them.

    python3 tools/ai.py 0            a level's kinds and their behaviours
    python3 tools/ai.py --check      the tables against every snapshot's RAM

## Where the behaviours are

`FDAT.T` entry `3n + 1`, link 0, is `block_copy`'d to `entity_table`
(`0x8018c7e8`): forty 120-byte records -- a creature's **kind** -- and after
them, at `entity_scripts` (`0x8018daa8`), the kinds' behaviour records. A kind
lists up to sixteen behaviours at +0x38, as offsets into that area on the disc
with 0xffffffff for none; `entity_table_init` (`0x80053084`) walks the kinds in
order to the first whose +0 is 0xff and turns each offset into an address and
each 0xffffffff into 0. Kinds past that one keep their raw words.

A behaviour record opens with its **opcode** -- which arm of `actor_tick`
(`0x800500a8`) runs it -- then the animation it starts (+1), a base score
(+2), a sound (+4), the rate its animation clock runs at (+8) and the
opcode's own parameters. Level 0's two monster kinds, models 50 and 51, list
the same seven: 6, 0, 5, 1, 4, 2, 3.

## How one is chosen

An awake actor (+9 == 1) carries the running behaviour at +0x60, its opcode at
+0xe and a phase at +0xf: 0 just switched in, 0xf0 running, 0xff finished.
`actor_tick_driver` runs `actor_choose` (`0x8004c01c`) on the frames where
`frame & 3 == slot & 3`, and `actor_tick` runs it again when a behaviour ends
(`0x8004c104`). It measures the distance to the player and hands it to
`actor_pick` (`0x8004bf1c`), which -- unless the phase is 0xf0 or 0 -- scores
every behaviour of the kind with `actor_behaviour` (`0x8004b984`, a 133-arm
switch on the opcode), keeps the best above -2, and switches to it with
`actor_switch` (`0x8004b94c`) if it is another one, or the running one has
finished: +0x10 = the old opcode, +0x60 = the record, +0xe = its opcode,
+0xf = 0.

The animation clock is +0x18, 0 to 0xfff: `actor_clock` (`0x8004db3c`) adds
the record's rate (+8) and keeps its size at +0x66, and `actor_clock_passed`
(`0x8004db98`) asks whether a given time was crossed in this frame's step.
`actor_start_anim` (`0x8004c130`) puts the animation at +0xc and the clock
at 0.
"""
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ENTITY_TABLE = 0x8018C7E8
ENTITY_SCRIPTS = 0x8018DAA8
ENTITY, KINDS, SLOTS_PER_KIND = 120, 40, 16
LISTS = 0x38
ACTOR_TABLE, ACTOR_STRIDE, ACTORS = 0x80185DA8, 0x88, 200


def entity_blob(lv):
    """link 0 of the level, as entity_table_init leaves it in RAM."""
    import actors
    raw, ch = actors.links(lv)
    off, n = ch[0]
    blob = bytearray(raw[off:off + n])
    for k in range(KINDS):
        if blob[k * ENTITY] == 0xFF:
            break
        for i in range(SLOTS_PER_KIND):
            o = k * ENTITY + LISTS + 4 * i
            v = struct.unpack_from("<I", blob, o)[0]
            struct.pack_into("<I", blob, o, 0 if v == 0xFFFFFFFF else ENTITY_SCRIPTS + v)
    return blob


def kinds(lv, blob=None):
    """[kind] -- each {'kind', 'model', 'behaviours': [record]} for the used kinds.

    A record is {'addr', 'op', 'anim', 'score', 'raw'}: its bytes run to the next
    record the level holds.
    """
    blob = blob or entity_blob(lv)
    addrs = set()
    out = []
    for k in range(KINDS):
        e = blob[k * ENTITY:(k + 1) * ENTITY]
        if e[0] == 0xFF:
            break
        ptrs = [p for p in struct.unpack_from("<16I", e, LISTS) if p]
        addrs.update(ptrs)
        out.append({"kind": k, "model": struct.unpack_from("<H", e, 0)[0] - 0x400,
                    "ptrs": ptrs})
    order = sorted(addrs) + [ENTITY_TABLE + len(blob)]
    nxt = {a: b for a, b in zip(order, order[1:])}
    for kd in out:
        kd["behaviours"] = []
        for p in kd["ptrs"]:
            o = p - ENTITY_TABLE
            raw = bytes(blob[o:nxt[p] - ENTITY_TABLE])
            kd["behaviours"].append({"addr": p, "op": raw[0], "anim": raw[1],
                                     "score": raw[2], "raw": raw})
    return out


# ---------------------------------------------------------------------------
# The machine: a creature as a dict of the actor fields actor_tick uses.
#
#   x y z      +0x2c +0x30 +0x34       yaw   +0x42     turn  +0x58
#   vx vz      +0x50 +0x54             vy    +0x52     vst   +0xd
#   rec        +0x60 (a behaviour record, or None)     op    +0xe
#   phase      +0xf   0 new, 0xf0 running, 0xff done   prev  +0x10
#   anim       +0xc   clock +0x18   step +0x66         aim   +0x64
#   sub        +0x70  (a behaviour's own state)        n72   +0x72
#   flee, cut  +0x70, +0x71 in opcode 5                 radius +0x1c, height +0x1e
#
# `kind` is the entity record's fields: 'accel' +3, 'turn_accel' +4, 'fall' +5,
# 'radius' +0x12, 'height' +0x14, and the behaviour list.

def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def u16f(raw, off):
    return struct.unpack_from("<H", raw, off)[0] if off + 2 <= len(raw) else 0


def s16f(raw, off):
    return struct.unpack_from("<h", raw, off)[0] if off + 2 <= len(raw) else 0


def rand_score(x, rand):
    """0x800170c0: ((rand() + rand()) * x) >> 15 -- 0 to 2x, most often x."""
    return ((rand() + rand()) * x) >> 15


def facing_test(a, b, tol):
    """0x80016a2c: a within tol of b either way, 0x1000 to the turn."""
    d = (a - b) & 0xFFF
    return d <= tol or d >= 0x1000 - tol


def clock(a, rate):
    """actor_clock (0x8004db3c): +0x18 += rate, 0..0xfff; |rate| at +0x66."""
    rate = s16(rate)
    a["step"] = abs(rate)
    t = s16(a["clock"] + rate)
    a["clock"] = 0xFFF if t >= 0x1000 else (0 if t < 0 else t)


def clock_loop(a, rate):
    """0x8004db08: the same, wrapping at 0x1000 instead of stopping."""
    rate = s16(rate)
    a["step"] = abs(rate)
    a["clock"] = (a["clock"] + rate) & 0xFFF


def clock_passed(a, t):
    """actor_clock_passed (0x8004db98): t crossed in this frame's step."""
    return t < a["clock"] and not t < a["clock"] - a["step"]


def start_anim(a, anim):
    """actor_start_anim (0x8004c130), without the 0x80199148 case."""
    if anim != 0xFF:
        a["anim"], a["clock"] = anim, 0


def switch(a, rec):
    """actor_switch (0x8004b94c)."""
    a["prev"] = a["op"]
    if rec is None:
        a["rec"], a["op"], a["phase"] = None, 0xFF, 0xFF
    else:
        a["rec"], a["op"], a["phase"] = rec, rec["op"], 0


def score(a, rec, dist, player, rand):
    """actor_behaviour (0x8004b984) for the opcodes level 0's kinds use."""
    op, raw, cur = rec["op"], rec["raw"], rec is a["rec"]
    base = raw[3] if cur else raw[2]
    if op == 0:                                   # 0x8004b9e8: idle when far
        return rand_score(base, rand) if u16f(raw, 0xC) < dist else 0
    if op == 1:                                   # 0x8004ba34: wander at middling range
        if not u16f(raw, 0x10) < dist or u16f(raw, 0x12) < dist:
            return 0
        return rand_score(base, rand)
    if op == 5:                                   # 0x8004baa8: close in
        if cur:
            return 0 if u16f(raw, 0x12) < dist else rand_score(raw[3], rand)
        sc = 0 if u16f(raw, 0x10) < dist else rand_score(raw[2], rand)
        if a["op"] in (4, 0x12, 0x17, 0x18, 0x84):
            sc <<= 1
        return sc
    if op == 4:                                   # 0x8004bbd8: strike
        if a["flags"] & 0x100 or u16f(raw, 0x1A) < dist:
            return 0
        if not overlap_y(a["y"], a["height"], player[1] + 0xC8, 0x834):
            return 0
        brg = s16(vec_angle(player[0] - a["x"], player[2] - a["z"]))
        if not facing_test(s16(a["yaw"]), brg, raw[0x10] << 4):
            return 0
        if cur:
            return rand_score(raw[3], rand)
        sc, near = raw[2], raw[0xE] << 6
        if not dist < (near + u16f(raw, 0x1A)) >> 1:
            sc -= sc // 3
        elif not dist < near:
            sc -= sc // 6
        return rand_score(sc, rand)
    if op == 0x19:                                # 0x8004bcdc: at range, facing
        if a["flags"] & 0x100:
            # flag 0x100 (+0x28) holds it back; a record whose +0xc is 0x27
            # lifts it while the player is free to move (0x801b2568 is 0)
            if raw[0xC] == 0x27:
                a["flags"] &= ~0x100
            return 0
        if u16f(raw, 0x16) < dist or dist < u16f(raw, 0x14):
            return 0
        brg = s16(vec_angle(player[0] - a["x"], player[2] - a["z"]))
        if not facing_test(s16(a["yaw"]), brg, raw[0xD] << 4):
            return 0
        return rand_score(base, rand)
    if op in (2, 3):                              # a hit and a death: forced
        return 0
    if op == 0x70:
        return -1
    if op < 0x80:                                 # 0x8004be94 and on
        return rand_score(base, rand)
    return -2                                     # the level's own code: not here


def pick(a, kind, dist, player, rand):
    """actor_pick (0x8004bf1c): the best score above -2, switched to if new."""
    if a["phase"] in (0xF0, 0):
        return
    best, best_rec = -2, None
    for rec in kind["behaviours"]:
        sc = score(a, rec, dist, player, rand)
        if best < sc:
            best, best_rec = sc, rec
    if best_rec is not None and (best_rec is not a["rec"] or a["phase"] == 0xFF):
        switch(a, best_rec)


def entrance(kind):
    """0x8004c068 from actor_activate: 0x15, else 6, else 0x1a, or None."""
    for op in (0x15, 6, 0x1A):
        for rec in kind["behaviours"]:
            if rec["op"] == op:
                return rec
    return None


def overlap_y(y, top, y2, top2):
    """0x80016d0c (as far as opcode 4 needs it): two bodies share height."""
    return not (y - top > y2 or y2 - top2 > y)


def vec_angle(u, v):
    import movement
    return movement.vec_angle(u, v)


# -- moving -------------------------------------------------------------------

def facing_dir(yaw):
    """0x80016240: (-sin, cos) of the yaw, 4096 to one."""
    import movement
    return -movement.game_sin(s16(yaw)), movement.game_cos(s16(yaw))


def scale11(k, v):
    """0x800168f0: each part times k, >> 11."""
    return (s16(k) * v[0]) >> 11, (s16(k) * v[1]) >> 11


def approach(cur, target, step):
    """0x80015fdc: cur towards target by |step|, not past it."""
    if step > 0:
        if cur < target:
            return min(cur + step, target)
        if target < cur:
            return max(cur - step, target)
        return cur
    if target < cur:
        return max(cur + step, target)
    if cur < target:
        return min(cur - step, target)
    return cur


def turn(a, target, most, accel):
    """0x8004e928: the turn rate +0x58 towards +-most by accel, the yaw by it,
    and onto the target if it was crossed."""
    import movement
    target = s16(target)
    yaw = s16(a["yaw"])
    if ((yaw - target) & 0xFFF) == 0:
        a["turn"] = 0
        return
    if ((target - yaw) & 0xFFF) < 0x801:
        r = s16(a["turn"] + accel)
        a["turn"] = s16(most) if s16(most) < r else r
    else:
        r = s16(a["turn"] - accel)
        a["turn"] = -s16(most) if r < -s16(most) else r
    old = yaw
    a["yaw"] = s16(old + a["turn"])

    def gt(p, q):
        return s16(((p + 0x800) & 0xFFF) - ((q + 0x800) & 0xFFF)) > 0
    if a["turn"] > 0:
        if gt(target, old) and not gt(target, a["yaw"]):
            a["yaw"] = target
    else:
        if gt(old, target) and not gt(a["yaw"], target):
            a["yaw"] = target


def drive(a, lvl, yaw, speed, accel, flags, others=(), player=None):
    """0x8004e824: the velocity towards speed along yaw, by accel an axis."""
    d = facing_dir(yaw)
    tx, tz = scale11(speed, d)
    ax, az = scale11(accel, d)
    a["vx"] = s16(approach(a["vx"], tx, ax))
    a["vz"] = s16(approach(a["vz"], tz, az))
    return move_horizontal(a, lvl, flags, others, player)


def walk_to(a, lvl, angle, speed, most, accel, turn_accel, flags, others=(),
            player=None):
    """0x8004ea7c: turn towards angle, then drive along the yaw."""
    turn(a, angle, most, turn_accel)
    return drive(a, lvl, a["yaw"], speed, accel, flags, others, player)


def brake(a, lvl, decel, flags, others=(), player=None):
    """0x8004e6f8: the velocity shrinks by 2 * decel along itself."""
    import movement
    if a["vst"] != 0:
        return move_horizontal(a, lvl, flags, others, player)
    n = movement.game_isqrt(a["vx"] * a["vx"] + a["vz"] * a["vz"])
    if n == 0:
        return 0
    sx = movement.trunc((a["vx"] * decel) << 1, n)
    sz = movement.trunc((a["vz"] * decel) << 1, n)
    a["vx"] = s16(approach(a["vx"], 0, sx))
    a["vz"] = s16(approach(a["vz"], 0, sz))
    return move_horizontal(a, lvl, flags, others, player)


FENCE = 0x40            # a layer's byte +4: no creature may stand on it
FENCED_SURFACE = -100000  # 0xfffe7960, what collide_query writes over the floor
CREATURE_LAYERS = 0x93  # collision_layers (0x8018faac) in play: 3 in two snapshots


def fenced(lvl, x, y, z, body):
    """collide_query's flag 2 (0x80033f94): the layer tile_collision looked at
    -- collision_cell_layer, 0x801e6468 -- has 0x40 at its byte +4. The
    player's 0x31 never asks; the creatures' 0x93 does, so these are walls to
    them alone: the fences that keep a level's creatures in their own ground.
    5006 of 5006 creature positions bp16 logged stand clear of them."""
    import collision
    import movement
    if not (0 <= x <= movement.GRID_MAX and 0 <= z <= movement.GRID_MAX):
        return False
    c = lvl.cell(x >> 11, z >> 11)
    ymid = y - (((body << 4) & 0xFFFFFFFF) >> 5)
    return bool(c[collision.layer_of(c, ymid) + 4] & FENCE)


def creature_query(lvl, a, x, y, z):
    """collide_query for a creature, as far as the tiles go: its radius and
    height, and the fence."""
    import movement
    mask, cur = movement.query(lvl, x, y, z, radius=a["radius"],
                               body=a["height"])
    if CREATURE_LAYERS & 2 and fenced(lvl, x, y, z, a["height"]):
        mask, cur = mask | 1, FENCED_SURFACE
    return mask, cur


def _clear(a, lvl, x, z, others, player):
    """collide_query for an actor: the tiles at its own radius and height,
    the fence, then the other creatures (0x10) and the player (0x80). Returns
    the mask and the thing hit, if any, as (x, z, radius)."""
    import movement
    mask, cur = creature_query(lvl, a, x, a["y"], z)
    thing = None
    for o in others:
        if o is a or o.get("st", 1) != 1:
            continue
        if movement.in_range((o["x"], o["y"], o["z"]), x, a["y"], z,
                             o["radius"] + a["radius"], o["height"],
                             a["height"]) != -1:
            mask |= 0x10
            thing = (o["x"], o["z"], o["radius"])
            break
    if player is not None and thing is None:
        if movement.in_range(player, x, a["y"], z, 0x320 + a["radius"], 0x6A4,
                             a["height"]) != -1:
            mask |= 0x80
            thing = (player[0], player[2], 0x320)
    return mask, cur, thing


def move_horizontal(a, lvl, flags, others=(), player=None):
    """actor_move_horizontal (0x8004dbc8): one step of the velocity.

    Clear (or a step up of at most 0x320 over a wall, with no flag 0x10 and
    the actor's 0x4000 clear) it goes through the ledge test when the actor
    is grounded and flag 0x24 asks: the lowest floor under the target and
    under the points one diameter ahead of the actor on each axis, and a floor
    more than 0x44c below the feet sets 0x100 and, with flag 4, refuses the
    step as a wall does. A creature, the player or an object in the way is
    gone round: a quarter turn off the bearing to it, on the side the step
    leans, at half the step's length, twice at most. A wall: the X part is
    dropped (with flag 1 the Z part takes the whole length), then once more
    -- the Z part only without flag 1, which is the same step again, or the
    X part alone at full length with it -- and then it stops; a diagonal wall
    slides along its diagonal first. Flag 8 writes the step back into the
    velocity. Returns every mask met, with 0x100 for a ledge.
    """
    import movement
    sx, sz = s16(a["vx"]), s16(a["vz"])
    if sx == 0 and sz == 0:
        return 0
    s7, s6 = sx, sz
    seen = things = diag = second = 0

    def full():
        return movement.game_isqrt(s7 * s7 + s6 * s6)
    for _ in range(16):
        tx, tz = a["x"] + sx, a["z"] + sz
        mask, cur, thing = _clear(a, lvl, tx, tz, others, player)
        take = mask == 0
        slide = False
        if not take:                                        # .L11
            seen |= mask
            if flags & 3 == 0:
                break
            if mask & 0xB0:
                things += 1
                if things == 2:
                    break
                ox, oz, _r = thing
                b = vec_angle(ox - a["x"], oz - a["z"])
                step_dir = s16(vec_angle(sx, sz))
                side = b + 0x400 if ((step_dir - s16(b)) & 0xFFF) < 0x801 else b - 0x400
                side &= 0xFFF
                n = movement.game_isqrt(sx * sx + sz * sz)
                sx = (-movement.game_sin(side) * n) >> 13
                sz = (movement.game_cos(side) * n) >> 13
                continue
            if not flags & 0x10:                            # .L13
                if a["flags"] & 0x4000:
                    slide = True
                elif mask & ~0x205 == 0:
                    if cur + 0x320 < a["y"]:
                        slide = True
                    else:
                        take = True                         # a step up, via .L3
            if not take and not slide:                      # .L14
                if mask & 1:
                    slide = True
                elif mask & 2:                              # .L22
                    if diag:
                        slide = True
                    else:
                        cx, cz = tx >> 11, tz >> 11
                        c = lvl.cell(cx, cz) if 0 <= cx < 80 and 0 <= cz < 80 else bytes(10)
                        if c[2] & 3 in (0, 2):
                            sx = sz = (s7 + s6) >> 1
                        else:
                            sx = (s7 - s6) >> 1
                            sz = -sx
                        diag = 1
                        continue
                else:
                    break
        if take:                                            # .L3
            if a["vst"] == 0 and flags & 0x24:
                lowest = cur
                az = (a["radius"] << 1) * (1 if sz > 0 else -1) if sz else 0
                ax = (a["radius"] << 1) * (1 if sx > 0 else -1) if sx else 0
                for px, pz in ((a["x"], a["z"] + az), (a["x"] + ax, a["z"])):
                    _m, c2 = movement.query(lvl, px, a["y"], pz, radius=a["radius"],
                                            body=a["height"])
                    lowest = max(lowest, c2)
                if a["y"] < lowest - 0x44C:
                    seen |= 0x100
                    if flags & 4:
                        slide = True
                        take = False
            if take:                                        # .L10
                a["x"], a["z"] = tx, tz
                break
        if slide:                                           # .L15
            if second:
                sx = sz = 0
                break
            if sx != 0:
                sx = 0
                if flags & 1:
                    n = full()
                    sz = n if s6 > 0 else -n
                else:
                    sz = s6
                continue
            if sz != 0:
                sz = 0
                if flags & 1:
                    n = full()
                    sx = n if s7 > 0 else -n
                else:
                    sz = s6
                second = 1
                continue
            break
    if flags & 8:
        a["vx"], a["vz"] = s16(sx), s16(sz)
    return seen


def move_vertical(a, lvl, kind):
    """actor_move_vertical (0x8004e330), states 0, 0x10 and 0x20.

    0 grounded: a floor above the feet starts a rise at -0x64 (0x20), one
    below a fall (0x10). 0x20 rises by the velocity, which gains 5 a frame,
    until the feet are on the floor. 0x10 falls by the velocity, which gains
    the kind's +5, onto the floor its query meets. Entity flag 0x400 stands
    it on the floor's base instead; the ballistic 0x30 is not here.
    """
    import movement
    _m, surf = movement.query(lvl, a["x"], a["y"], a["z"], radius=a["radius"],
                              body=a["height"], ymid=a["y"] - 0x500)
    st = a["vst"]
    if st == 0:
        d = surf - a["y"]
        if d < 0:
            a["vst"], a["vy"] = 0x20, -0x64
        elif d > 0:
            a["vst"], a["vy"] = 0x10, 0
    elif st == 0x20:
        a["y"] += a["vy"]
        a["vy"] = s16(a["vy"] + 5)
        if not (surf < a["y"] and a["vy"] < 0):
            a["y"], a["vst"] = surf, 0
    elif st == 0x10:
        ny = a["y"] + a["vy"]
        mask, cur = creature_query(lvl, a, a["x"], ny, a["z"])   # 0x8004e488
        if mask == 0:
            a["y"] = ny
            a["vy"] = s16(a["vy"] + kind["fall"])
        elif mask & 4:
            a["y"], a["vy"], a["vst"] = cur, 0, 0
        else:
            a["vst"] = 0


def tick(a, kind, lvl, player, others, rand):
    """One frame of actor_tick (0x800500a8) for opcodes 0, 1, 4, 5 and 6.

    `player` is (x, y, z); `rand` the BIOS rand, 0..0x7fff. Returns what a
    blow struck this frame (opcode 4 at its record's +0x18), or None.
    """
    rec = a["rec"]
    blow = None
    if rec is None:
        return None
    raw = rec["raw"]
    op = a["op"]
    dist = _dist(a, player)
    if op == 0:                                         # 0x800508b4
        if a["phase"] == 0:
            a["phase"] = 0xF0
            start_anim(a, raw[1])
        clock(a, s16f(raw, 8))
        brake(a, lvl, kind["accel"], 0xA, others, player)
        _finish_if_done(a, kind, player, rand)
    elif op == 1:                                       # 0x800508f4
        if a["phase"] == 0:
            a["phase"] = 0xF0
            start_anim(a, raw[1])
            a["aim"] = rand() >> 3
        else:
            hit = walk_to(a, lvl, s16(a["aim"]), u16f(raw, 0xC), u16f(raw, 0xE),
                          kind["accel"], kind["turn_accel"], 5, others, player)
            if hit or (rand() >> 5) < raw[0x14]:
                a["aim"] = rand() >> 3
        clock(a, s16f(raw, 8))
        _finish_if_done(a, kind, player, rand)
    elif op == 5:                                       # 0x80050b20
        if a["phase"] == 0:
            a["phase"] = 0xF0
            start_anim(a, raw[1])
            a["flee"] = 1 if a["prev"] in (4, 0x12, 0x17, 0x18) else 0
            a["cut"] = 0
        if rand() < 0x1770:
            if not dist < u16f(raw, 0x16):
                a["flee"] = 0
            elif not u16f(raw, 0x14) < dist:
                a["flee"] = 1
        brg = s16(vec_angle(player[0] - a["x"], player[2] - a["z"]))
        a["aim"] = brg
        fl = 0x21 if a["cut"] else 5
        if not a["flee"]:
            got = walk_to(a, lvl, brg, u16f(raw, 0xC), u16f(raw, 0xE),
                          kind["accel"], kind["turn_accel"], fl, others, player)
        else:
            got = drive(a, lvl, s16(brg + 0x800), u16f(raw, 0xC), kind["accel"],
                        fl, others, player)
        toggle = False
        if got & 0x100:                                  # a ledge ahead
            if not a["cut"]:
                if rand() < u16f(raw, 0x18):
                    a["cut"] = 1
                else:
                    toggle = True
        else:
            a["cut"] = 0
            toggle = bool(got)
        if toggle:
            a["flee"] = 0 if a["flee"] else 1
        clock(a, s16f(raw, 8))
        _finish_if_done(a, kind, player, rand)
    elif op == 4:                                       # 0x800514f8
        if a["phase"] == 0:
            a["phase"] = 0xF0
            start_anim(a, raw[1])
        clock(a, s16f(raw, 8))
        if clock_passed(a, u16f(raw, 0x18)):
            blow = {"reach": raw[0xE] << 6, "lift": raw[0xF] << 5,
                    "arc": raw[0x10] << 4, "rec": rec}
        if a["clock"] >= 0xFFF:
            finish(a, kind, player, rand)
        brake(a, lvl, raw[0xD], 0xA, others, player)
    elif op == 6:                                       # 0x8005205c
        _burrowed(a, kind, raw, lvl, player, others, rand, dist)
    elif op == 0x19:                                    # 0x800523f0, a volley
        # the clock, and the fire times at +0x70 (+0xe, then +0x12 apart,
        # back to 0 past +0x10) that run the record's list from +0x1a through
        # actor_animation_effects -- the effects themselves are not here
        if a["phase"] == 0:
            a["phase"] = 0xF0
            start_anim(a, raw[1])
            a["sub"], a["n72"] = u16f(raw, 0xE), 0
            if raw[7] == 1:
                a["vst"] = 0x10
        clock(a, s16f(raw, 8))
        if clock_passed(a, a["sub"]):
            a["sub"] = (a["sub"] + u16f(raw, 0x12)) & 0xFFFF
            if u16f(raw, 0x10) < s16(a["sub"]):
                a["sub"] = 0
        if a["clock"] >= 0xFFF:
            finish(a, kind, player, rand)
        brake(a, lvl, kind["accel"], 0xA, others, player)    # 0x80052610
    elif op == 2:                                       # 0x80050400, a flinch
        if a["phase"] == 0:
            a["phase"], a["sub"] = 0xF0, 0
            start_anim(a, raw[1])
        s = a["sub"]
        clock(a, s16f(raw, 8))
        if s == 0:
            a["sub"] = 1                                # the tint set (not kept)
        elif s == 1 and a["clock"] >= 0x7FF:
            a["sub"] = 2
        elif s == 2 and a["clock"] >= 0xFFF:
            a["sub"] = 3
        elif s == 3:
            finish(a, kind, player, rand)
        brake(a, lvl, kind["accel"] << 1, 0xA, others, player)   # 0x80052bd0
    elif op == 3:                                       # 0x800505a4, dying
        if a["phase"] == 0:
            a["phase"], a["sub"] = 0xF0, 0
            start_anim(a, raw[1])
        s = a["sub"]
        if s == 0:
            clock(a, s16f(raw, 8))                      # the drops at 0x800 are not here
            if a["clock"] >= 0xFFF or s16f(raw, 8) == 0:
                a["sub"] = 0xF                          # 0x800507b0
        else:
            a["sub"] = s + 1                            # 0x80050828
            if s >= 0x26:                               # 0x80050868: gone,
                a["retire"] = True                      # by its category
                return blow
        brake(a, lvl, kind["accel"] << 1, 0xA, others, player)
    move_vertical(a, lvl, kind)
    return blow


def _dist(a, player):
    """vec_length_2d (0x80016c08), through the game's own root."""
    import movement
    dx, dz = (player[0] - a["x"]) >> 3, (player[2] - a["z"]) >> 3
    return movement.game_isqrt(dx * dx + dz * dz) << 3


def finish(a, kind, player, rand):
    """actor_finish (0x8004c104): done, and choose again at once."""
    a["phase"] = 0xFF
    pick(a, kind, _dist(a, player), player, rand)


def _finish_if_done(a, kind, player, rand):
    if a["clock"] >= 0xFFF:                             # .L173
        finish(a, kind, player, rand)


def _burrowed(a, kind, raw, lvl, player, others, rand, dist):
    """Opcode 6: under the ground until the player comes near, then up."""
    if a["phase"] == 0:
        a["phase"] = 0xF0
        a["sub"] = 0
        start_anim(a, raw[1])
        a["radius"], a["height"] = u16f(raw, 0x16), u16f(raw, 0x18)
        if u16f(raw, 0xE):
            a["aim"] = rand() >> 3
    sub = a["sub"]
    if sub == 0:
        clock_loop(a, s16f(raw, 8))
        if dist < u16f(raw, 0xC) and not a["clock"] < 0xFFF - u16f(raw, 8):
            a["sub"], a["clock"] = 2, 0
            start_anim(a, raw[0x1A])
        hit = walk_to(a, lvl, s16(a["aim"]), u16f(raw, 0xE), u16f(raw, 0x10),
                      kind["accel"], kind["turn_accel"], 5, others, player)
        if hit or (rand() >> 5) < raw[0x1C]:
            a["aim"] = rand() >> 3
    elif sub == 2:
        clock(a, s16f(raw, 8))
        a["radius"] = lerp(u16f(raw, 0x16), kind["radius"], a["clock"])
        a["height"] = lerp(u16f(raw, 0x18), kind["height"], a["clock"])
        if not a["clock"] < 0xFFF:
            a["radius"], a["height"] = kind["radius"], kind["height"]
            a["sub"], a["n72"] = 3, u16f(raw, 0x12)
    elif sub == 3:
        drive(a, lvl, a["yaw"], u16f(raw, 0xE), 0xFF, 5, others, player)
        a["n72"] = s16(a["n72"] - 1)
        if a["n72"] == -1:
            finish(a, kind, player, rand)
        clock(a, raw[0x1B])


def lerp(a, b, t):
    """fixed_madd (0x80017158): a + ((b - a) * t >> 12)."""
    return a + (((b - a) * t) >> 12)


def kind_of(lv, k, blob=None):
    """The fields of kind k the machine reads, with its behaviours."""
    blob = blob or entity_blob(lv)
    e = blob[k * ENTITY:(k + 1) * ENTITY]
    kd = [x for x in kinds(lv, blob) if x["kind"] == k][0]
    return {"accel": e[3], "turn_accel": e[4], "fall": e[5],
            "radius": u16f(e, 0x12), "height": u16f(e, 0x14),
            "behaviours": kd["behaviours"],
            # what a hit reads (actor_take_hit, held_item_tick): the push's
            # weight +2, the two arcs +0x16 and +0x18, the HP actor_copy_kind
            # copies from +0x1a, the experience +0x1e, the eight defences
            # +0x20..+0x2e and the gold +0x30
            "weight": e[2], "arc_face": s16f(e, 0x16), "arc_back": s16f(e, 0x18),
            "hp": u16f(e, 0x1A), "exp": s16f(e, 0x1E),
            "defence": [u16f(e, 0x20 + 2 * i) for i in range(8)],
            "gold": u16f(e, 0x30)}


def new_actor(x, y, z, yaw, kind, flags=0):
    """What actor_wake leaves, with the entrance behaviour switched in."""
    a = {"x": x, "y": y, "z": z, "yaw": yaw, "turn": 0, "vx": 0, "vz": 0,
         "vy": 0, "vst": 0, "rec": None, "op": 0, "phase": 0xFF, "prev": 0,
         "anim": 0, "clock": 0, "step": 0, "aim": 0, "sub": 0, "n72": 0,
         "flee": 0, "cut": 0, "radius": kind["radius"],
         "height": kind["height"], "flags": flags, "st": 1}
    rec = entrance(kind)
    if rec is not None:
        switch(a, rec)
    return a


def check(out=sys.stdout):
    """The relocated table byte for byte, and every awake actor's behaviour."""
    same = total = awake = ok = snaps = 0
    blobs = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        r = open(path, "rb").read()
        lv = r[0x18FAD9]
        if struct.unpack_from("<I", r, (ENTITY_TABLE & 0x1FFFFF) + LISTS)[0] == 0:
            continue                             # no level ever loaded
        snaps += 1
        if lv not in blobs:
            blobs[lv] = entity_blob(lv)
        blob = blobs[lv]
        base = ENTITY_TABLE & 0x1FFFFF
        live = r[base:base + len(blob)]
        # the kinds' own records and the behaviour area: the table as loaded
        same += sum(a == b for a, b in zip(blob, live))
        total += len(blob)
        ks = {kd["kind"]: kd for kd in kinds(lv, blob)}
        for s in range(ACTORS):
            a = r[(ACTOR_TABLE & 0x1FFFFF) + s * ACTOR_STRIDE:][:ACTOR_STRIDE]
            if a[0] == 0xFF or a[9] != 1:
                continue
            awake += 1
            p60 = struct.unpack_from("<I", a, 0x60)[0]
            kd = ks.get(a[2])
            recs = {b["addr"]: b for b in kd["behaviours"]} if kd else {}
            if p60 in recs and recs[p60]["op"] == a[0xE]:
                ok += 1
            else:
                print(f"  {os.path.basename(path)} actor {s}: +0x60 {p60:#x} "
                      f"op {a[0xE]:#x}", file=out)
    print(f"  {same} of {total} bytes of the kinds and their behaviours as "
          f"entity_table_init leaves them, over {snaps} snapshots; {ok} of "
          f"{awake} awake actors run one of their kind's behaviours, its "
          f"opcode at +0xe", file=out)
    return ok == awake and snaps > 0


def check_log(out=sys.stdout, path=None):
    """What bp16's act= can hold the machine to without its hidden state.

    * **how long a behaviour runs**: to the end of its animation clock,
      ceil(0x1000 / rate) frames, and then actor_finish chooses again -- so
      every run of one opcode fully seen in the log is a whole number of
      cycles;
    * **how fast a creature walks**: drive's target is the record's speed
      (+0xc) times the unit facing >> 11, twice the speed, which a creature
      holds once it is up to it -- the most common step in the log.
    """
    import collections
    import math
    import replay
    rows, _ = replay.load(path) if path else replay.load()
    rows = [r for r in rows if r.get("act") is not None]
    if not rows:
        print("  no bp16 frames with act= to check the machine against", file=out)
        return True
    ks = kinds(rows[0]["lv"])
    rate, speed = {}, {}
    for kd in ks:
        for b in kd["behaviours"]:
            rate.setdefault(b["op"], s16f(b["raw"], 8))
            if b["op"] in (1, 5):
                speed.setdefault(b["op"], u16f(b["raw"], 0xC))
    per = collections.defaultdict(list)
    for r in rows:
        for a in r["act"]:
            per[a["slot"]].append((r["f"], a["b0e"], a["pos"]))
    ok = bad = 0
    steps = collections.defaultdict(collections.Counter)
    for seq in per.values():
        start = None
        for (f0, op0, p0), (f1, op1, p1) in zip(seq, seq[1:]):
            if f1 != f0 + 1:
                start = None
                continue
            if op0 == op1:
                steps[op0][round(math.hypot(p1[0] - p0[0], p1[2] - p0[2]))] += 1
            if op1 != op0:
                if start is not None and rate.get(op0):
                    cyc = -(-0x1000 // rate[op0])
                    if (f1 - start) % cyc == 0:
                        ok += 1
                    else:
                        bad += 1
                start = f1
    walk = []
    for op in (5, 1):
        if steps.get(op) and op in speed:
            walk.append(f"opcode {op} at {steps[op].most_common(1)[0][0]} a frame "
                        f"for a speed of {speed[op]}")
    print(f"  {ok} of {ok + bad} runs of one behaviour last a whole number of "
          f"animation cycles; " + ", ".join(walk), file=out)
    return bad == 0


class NeedsRand(Exception):
    """A step that called rand(), which a recording cannot replay."""


def _no_rand():
    raise NeedsRand()


def check_locked(out=sys.stdout, path=None, verbose=False):
    """bp16's act= with the hidden fields (2026-09-28 on): each creature
    stepped once from what the log says it was, against the next frame.

    Only frames that keep the behaviour (the same record at +0x60) and run it
    (phase 0xf0) -- a switch is a choice, and a choice is rand(). The turn
    rate (+0x58) is not logged: it is taken from the yaw's last step, which
    is the rate unless that step snapped onto a target. A step that calls
    rand() is counted apart. Compared: the position, the yaw, the velocity,
    the clock."""
    import collections
    import movement
    import replay
    rows, _ = replay.load(path) if path else replay.load()
    rows = [r for r in rows if r.get("act") and "phase" in r["act"][0]]
    if not rows:
        print("  no bp16 frames with the full act= to lock the machine to",
              file=out)
        return True
    lv = rows[0]["lv"]
    lvl = movement.level(lv)
    kinds_by = {}
    blob = entity_blob(lv)
    for kd in kinds(lv, blob):
        kinds_by[kd["kind"]] = kind_of(lv, kd["kind"], blob)
    table = __import__("actors").table(lv)
    kind_of_slot = {a["slot"]: a["kind"] for a in table if a}
    by_addr = {}
    for k, kd in kinds_by.items():
        for rec in kd["behaviours"]:
            by_addr[rec["addr"]] = rec
    res = collections.defaultdict(lambda: [0, 0, 0])   # op -> ok, bad, rand
    firsts = []
    prev_yaw = {}
    hidden = {}             # slot -> what the log does not hold, from our step
    last_turn = {}          # slot -> the yaw's last step that was not 0
    for r0, r1 in zip(rows, rows[1:]):
        if r1["f"] != r0["f"] + 1:
            prev_yaw = {}
            hidden = {}
            continue
        after = {a["slot"]: a for a in r1["act"]}
        others = [{"x": a["pos"][0], "y": a["pos"][1], "z": a["pos"][2],
                   "radius": a["radius"], "height": a["height"], "st": 1,
                   "slot": a["slot"]} for a in r0["act"]]
        for a0 in r0["act"]:
            k = a0["slot"]
            a1 = after.get(k)
            py = prev_yaw.get(k)
            prev_yaw[k] = a0["yaw"]
            if py is not None and s16(a0["yaw"] - py):
                last_turn[k] = s16(a0["yaw"] - py)
            if a1 is None or a0["beh"] != a1["beh"] or a0["phase"] != 0xF0 \
                    or a1["phase"] != 0xF0 or a0["beh"] not in by_addr:
                last_turn.pop(k, None)
                hidden.pop(k, None)
                continue
            rec = by_addr[a0["beh"]]
            kind = kinds_by[kind_of_slot[k]]
            a = {"x": a0["pos"][0], "y": a0["pos"][1], "z": a0["pos"][2],
                 "yaw": a0["yaw"], "turn": last_turn.get(k, 0),
                 "vx": a0["vel"][0], "vz": a0["vel"][1], "vy": 0, "vst": 0,
                 "rec": rec, "op": rec["op"], "phase": a0["phase"], "prev": 0,
                 "anim": rec["anim"], "clock": a0["clock"],
                 "step": abs(s16f(rec["raw"], 8)), "aim": 0, "sub": a0["flee"],
                 "n72": 0, "flee": a0["flee"], "cut": a0["turn"],
                 "radius": a0["radius"], "height": a0["height"],
                 "flags": a0["flags"], "st": 1}
            h = hidden.pop(k, None)
            if "rate" in a0:
                # bp16 since 2026-09-29 logs them all: nothing to guess
                a.update({"turn": a0["rate"], "aim": a0["aim"],
                          "vst": a0["vst"], "vy": a0["vy"], "sub": a0["sub"],
                          "n72": a0["n72"]})
            elif h is not None:
                # the vertical state and speed, the turn rate and the aim, as
                # our own step of the frame before left them
                a.update(h)
            me = [o for o in others if o["slot"] != k]
            want = (a1["pos"][0], a1["pos"][2], a1["yaw"] & 0xFFF, a1["vel"][0],
                    a1["vel"][1], a1["clock"])
            # rand(): the first try with none; a step that calls it is tried
            # with every call at 0 and at 0x7fff -- both sides of any one test
            tries, calls = [None], 0
            matched, last = False, None
            while tries:
                pick_ = tries.pop(0)
                b = dict(a)
                seq = []

                def rnd(pick_=pick_, seq=seq):
                    if pick_ is None:
                        seq.append(0)
                        raise NeedsRand()
                    i = len(seq)
                    seq.append(0)
                    return 0x7FFF if (pick_ >> i) & 1 else 0
                try:
                    tick(b, kind, lvl, r1["p"], me, rnd)
                except NeedsRand:
                    calls = 1
                    tries = list(range(1 << 1))
                    continue
                if pick_ is not None and len(seq) > calls and calls < 4:
                    calls = len(seq)
                    tries = list(range(1 << calls))
                    continue
                last = b
                got = (b["x"], b["z"], s16(b["yaw"]) & 0xFFF, b["vx"], b["vz"],
                       b["clock"])
                if got == want:
                    matched = True
                    break
            if last is not None:
                # +0x70 is in the log; these are not. The turn rate too, when
                # our step came out right; else the yaw's last step
                keep = ("vst", "vy", "aim", "n72") + (("turn",) if matched else ())
                hidden[k] = {kk: last[kk] for kk in keep}
            if matched:
                res[rec["op"]][0] += 1
                if calls:
                    res[rec["op"]][2] += 1
            else:
                res[rec["op"]][1] += 1
                if verbose and len(firsts) < 12:
                    firsts.append(f"  f={r0['f']} slot {k} op {rec['op']}: "
                                  f"model {got}, game {want}")
    for line in firsts:
        print(line, file=out)
    tot_ok = sum(v[0] for v in res.values())
    tot = sum(v[0] + v[1] for v in res.values())
    print(f"  {tot_ok} of {tot} creature frames stepped from the log land where "
          f"the game put them -- " + ", ".join(
              f"opcode {op}: {v[0]} of {v[0] + v[1]}" + (f" ({v[2]} of them with rand)" if v[2] else "")
              for op, v in sorted(res.items())), file=out)
    return tot_ok == tot


def bios_rand(seed=1):
    """rand() as the BIOS does it (A0:2F), from a seed: what actors.gd uses."""
    state = [seed]

    def rand():
        state[0] = (state[0] * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
        return (state[0] >> 16) & 0x7FFF
    return rand


def run(lv=0, slot=20, frames=480, seed=1):
    """One creature woken at home and stepped with the player on a set path,
    for godot/selftest.gd to repeat: the start, the path, and every frame's
    position, yaw and opcode."""
    import json
    import movement
    lvl = movement.level(lv)
    rows = json.load(open(os.path.join(ROOT, "godot", "actors.json")))["levels"][str(lv)]
    home = [r for r in rows if r and r["slot"] == slot][0]
    kind = kind_of(lv, home["kind"])
    a = new_actor(home["x"], home["y"], home["z"], home["yaw"], kind,
                  flags=home["eflags"])
    rand = bios_rand(seed)
    path, out = [], []
    for f in range(frames):
        # the player stands off, then walks in, then steps back
        t = min(f, 360)
        p = (home["x"] + 9000 - t * 18, home["y"], home["z"] + 3000 - t * 6)
        path.append(list(p))
        if f & 3 == 0:
            pick(a, kind, _dist(a, p), p, rand)
        tick(a, kind, lvl, p, [a], rand)
        out.append([a["x"], a["y"], a["z"], a["yaw"] & 0xFFFF, a["op"]])
    return {"level": lv, "slot": slot, "kind": home["kind"], "seed": seed,
            "start": [home["x"], home["y"], home["z"], home["yaw"], home["eflags"]],
            "path": path, "frames": out}


def export(out_dir, lv):
    """aiNN.json for godot/ai.gd: each used kind's fields and behaviours."""
    import json
    blob = entity_blob(lv)
    doc = {"_note": "entity_table as entity_table_init leaves it: a kind's "
                    "accel (+3), turn accel (+4), fall (+5), radius (+0x12), "
                    "height (+0x14) and behaviour records, raw; tools/ai.py",
           "kinds": {}}
    for kd in kinds(lv, blob):
        k = kd["kind"]
        kf = kind_of(lv, k, blob)
        doc["kinds"][str(k)] = {
            "accel": kf["accel"], "turn_accel": kf["turn_accel"],
            "fall": kf["fall"], "radius": kf["radius"], "height": kf["height"],
            "weight": kf["weight"], "arc_face": kf["arc_face"],
            "arc_back": kf["arc_back"], "hp": kf["hp"], "exp": kf["exp"],
            "defence": kf["defence"], "gold": kf["gold"],
            "behaviours": [list(b["raw"]) for b in kf["behaviours"]]}
    if lv == 0:
        doc["run"] = run(lv)
        # and a kind-3 creature, whose volley (opcode 0x19) the first never uses
        doc["runs"] = [doc["run"], run(lv, 40)]
    path = os.path.join(out_dir, f"ai{lv:02d}.json")
    with open(path, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    return path


def main():
    a = sys.argv[1] if len(sys.argv) > 1 else "0"
    if a == "--locked":
        sys.exit(0 if check_locked(verbose=True) else 1)
    if a == "--check":
        ok = check() and check_log()
        check_locked()           # a report: the log still hides some fields
        sys.exit(0 if ok else 1)
    lv = int(a)
    for kd in kinds(lv):
        print(f"kind {kd['kind']:2d} model {kd['model']:3d}: " + ", ".join(
            f"{b['op']:#x}" for b in kd["behaviours"]))
    check()


if __name__ == "__main__":
    main()

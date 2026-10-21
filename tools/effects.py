#!/usr/bin/env python3
"""The effects: what a creature's volley throws. So far, the spores.

    python3 tools/effects.py            the checks, with the frames that differ
    python3 tools/effects.py --check    the checks alone

An effect is one of 128 slots of 0x4c bytes at `effect_slots` (`0x801b80ec`);
`effect_driver` (`0x8005bc50`), sixth in the frame, counts each live slot's
life (+0x10) down, frees it (+0 = 0xff) past 0 and otherwise runs
`effect_tick` (`0x800568bc`), a 130-arm switch on its +1. The slot:

    +0   bits: 1 strikes the player, 2 the creatures; & 7 the collision flags
    +1   the kind -- effect_tick's arm, and its spell_table record (24 bytes)
    +6   the percentage player_take_hit is handed      +0xb  a grace count
    +0xd test the half-step too                        +0xe  the model drawn
    +0x10 life   +0x18 x y z (s32)   +0x28 angles   +0x30 scale x y z
    +0x38 velocity x y z (s16)       +0x44 the kind's own count

## The spores (effect 0x26)

Level 0's kind-3 creatures (model 57) cast them: the volley (opcode 0x19)
hands `actor_animation_effects` its list entry 0x2d, which `0x8004ede0` takes
as a vertex of the creature's animated model, and arm 0x26 aims at the player
with a speed of 0 and calls `effect_spawn(10, 0x81, 0x26, point, velocity)`.
`effect_spawn`'s arm 0x26 (`0x80054338`): the scale 0x400, model 0x40, a life
of 0x32, the half-step test, 0x14 frames of growth, 200 higher. Each frame
(`effect_tick` arm 0x26, `0x80056de8`):

    while +0x44: scale x and z += 0x96, +0x44 -= 1
    scale y += 0x96 while under 0x1000
    y += 0x55 once the life is under 0x21, else y -= 0x28
    as 0x81: strike (0x80053850) -- the player within scale x (effect_hurt_player)
    as 0x84: move by the velocity against the tiles, radius 0x64, height 0xc8
             (effect_move), freed if it hits

**The strike** (`0x8002b114`): `in_range_3d` (`0x80016fb4`) -- a box of radius
+ 0x320, then the 3D length through the game's root to the player's middle
(0x6a4 / 2 up), less 0x320 -- must be 0 or more; the scale handed on is
`0x1000 - ((len << 12) / radius) * 0xc00 >> 12`, falling to 0x400 at the rim.
Record 0x26 has no attack, only effect 3, **poison**: `player_take_hit`'s arm
rolls `(100 * rand()) >> 15` against the resistance at `0x801b255a` and sets
`0x801b255c` to 0x384 on a loss. The controller (`0x80031e78`) counts it down
and on every multiple of 30 takes 1 HP -- and 0x384 is one, so **while a
spore keeps striking, the counter is set back to 900 every frame and the
player loses 1 HP every frame**; out of it, one every 30.

## Checked against emu/bp26.lua

Every frame of every spore from the frame before; every strike -- whether it
lands and the scale -- from where the player stood; and the HP the poison
leaves between strikes.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movement                                                      # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SPORE = 0x26
GROW = 0x96
RISE, SINK, TURN = 0x28, 0x55, 0x21
OWN, BODY = 0x320, 0x6A4
EDGE = 0x400
POISON = 0x384
FAR = -0x98967F               # 0xff676981, what in_range_3d gives when out


def s16(v):
    return movement.s16(v)


def slot(raw):
    """The fields effect_tick reads, out of 0x4c bytes."""
    g = lambda f, o: struct.unpack_from(f, raw, o)[0]
    return {"f0": raw[0], "kind": raw[1], "pct": raw[6], "grace": raw[0xB],
            "half": raw[0xD], "model": g("<H", 0xE), "life": g("<h", 0x10),
            "x": g("<i", 0x18), "y": g("<i", 0x1C), "z": g("<i", 0x20),
            "scale": [g("<h", 0x30), g("<h", 0x32), g("<h", 0x34)],
            "vel": [g("<h", 0x38), g("<h", 0x3A), g("<h", 0x3C)],
            "count": g("<h", 0x44)}


def in_range_3d(p, radius, target, own=OWN, height=BODY):
    """0x80016fb4: the length less own -- 0 when it is within own
    (0x80017090) -- or FAR."""
    r = radius + own
    dx = target[0] - p[0]
    if dx < -r or r < dx:
        return FAR
    dz = target[2] - p[2]
    if dz < -r or r < dz:
        return FAR
    dy = target[1] - p[1] - (height >> 1)
    if dy < -r or r < dy:
        return FAR
    ln = movement.game_isqrt((dx >> 3) ** 2 + (dz >> 3) ** 2 + (dy >> 3) ** 2) << 3
    if r < ln:
        return FAR
    return ln - own if own < ln else 0


def strike_scale(p, radius, player, edge=EDGE, scale=0x1000, near=0, mode=0x8000):
    """effect_hurt_player (0x8002b114): None when it misses, else the scale it
    hands player_take_hit. How far: mode 0x8000 in_range_3d to the player's
    middle; 0x8001 the same, a point above the player's top (y less 0x6a4)
    missing; any other in_range (0x8002b8d8) with the player's height 0x6a4
    and the mode as the asker's. Nearer than `near` misses too."""
    if mode == 0x8001 and p[1] < player[1] - 0x6A4:
        d = FAR
    elif mode in (0x8000, 0x8001):
        d = in_range_3d(p, radius, player)
    else:
        d = movement.in_range(player, p[0], p[1], p[2], radius, 0x6A4, mode)
        if d == -1:
            d = FAR
    return _falloff(d, near, radius, edge, scale)


def _falloff(d, near, radius, edge, scale):
    """What effect_hurt_player and 0x8004ceac share past the distance: None
    under `near`, else the scale (its low 15 bits) falling to edge / 0x1000
    at the rim."""
    if d < near:
        return None
    scale &= 0x7FFF
    if edge & 0xFFFF == 0x1000:
        return scale
    lo = movement.trunc(_s32(d << 12), radius) & 0xFFFF
    f = (0x1000 - ((((lo * (0x1000 - (edge & 0xFFFF))) & 0xFFFFFFFF) >> 12))) & 0xFFFF
    return ((scale * f) & 0xFFFFFFFF) >> 12


def strike_creatures(r, point, near, radius, mode, edge, stat, att, scale, flags, record,
                     rand, calls, hook):
    """0x8004ceac, effect_strike's creature half, on RAM `r` (a hit.Ram):
    every awake creature (+9 1) but the one acting, by its distance from the
    point -- mode 0x8000 in_range_3d with its radius (+0x1c) and height
    (+0x1e); 0x8001 the same, a point above its top missing; 0x8002 the same,
    and missing when the bearing to it is within 0x40 of both the point's
    +0xc turned a quarter each way, which never is; any other in_range with
    its height and the mode as the asker's -- not nearer than `near`, then
    actor_take_hit with the scale _falloff gives and the point (none when the
    scale has bit 0x8000)."""
    import hit
    import weapon
    pt = 0 if scale & 0x8000 else point
    p = (r.s32(point), r.s32(point + 4), r.s32(point + 8))
    cur = r.u32(CURRENT_ACTOR)
    for k in range(ACTOR_N):
        a = ACTORS + ACTOR_STRIDE * k
        if r.u8(a + 9) != 1 or a == cur:
            continue
        pos = (r.s32(a + 0x2C), r.s32(a + 0x30), r.s32(a + 0x34))
        own, height = r.u16(a + 0x1C), r.u16(a + 0x1E)
        if mode == 0x8001 and p[1] < _s32(pos[1] - height):
            d = FAR
        elif mode in (0x8000, 0x8001, 0x8002):
            d = in_range_3d(p, radius, pos, own, height)
            if mode == 0x8002:
                b = _s16_(movement.ratan2(_s32(pos[2] - p[2]), _s32(pos[0] - p[0])))
                w = r.u16(point + 0xC)
                if weapon._facing(b, _s16_(w + 0x400), 0x40) and \
                        weapon._facing(b, _s16_(w - 0x400), 0x40):
                    d = FAR
        else:
            d = movement.in_range(pos, p[0], p[1], p[2], radius, height, mode)
            if d == -1:
                d = FAR
        s = _falloff(d, near, radius, edge, scale)
        if s is not None:
            hit.actor_take_hit(r, k, stat, att, s & 0xFFFF, flags, record, pt, rand, calls, hook)


def tick_spore(e, lvl, player):
    """effect_driver's count and effect_tick's arm 0x26 on one slot. Returns
    the strike's scale (or None), and sets e['freed'] when the slot goes."""
    e["life"] -= 1
    if e["life"] == -1:
        e["freed"] = True
        return None
    if e["count"]:
        e["scale"][0] += GROW
        e["scale"][2] += GROW
        e["count"] -= 1
    if e["scale"][1] < 0x1000:
        e["scale"][1] += GROW
    e["y"] += SINK if e["life"] < TURN else -RISE
    e["f0"] = 0x81
    hit = strike_scale((e["x"], e["y"], e["z"]), e["scale"][0], player)
    e["f0"] = 0x84
    # effect_move: the velocity (0 for a spore) and the tiles
    e["x"] += e["vel"][0]
    e["y"] += e["vel"][1]
    e["z"] += e["vel"][2]
    if effect_collides(lvl, e):
        e["freed"] = True
    return hit


def effect_collides(lvl, e, radius=0x64, height=0xC8):
    """effect_move's collide_query with flags 1 (+0 & 7 is 4): the tiles,
    at the point and, with +0xd, half a step back. effect_collide
    (0x80053310) hands collide_query the point's y plus half the height --
    the point is the effect's middle, the query wants its feet."""
    if e.get("grace"):
        e["grace"] -= 1
        return False
    half = (height & 0xFFF) >> 1
    m, _cur = movement.query(lvl, e["x"], e["y"] + half, e["z"], radius=radius,
                             body=height)
    if m == 0 and e["half"]:
        m, _cur = movement.query(lvl, e["x"] - (e["vel"][0] >> 1),
                                 e["y"] - (e["vel"][1] >> 1) + half,
                                 e["z"] - (e["vel"][2] >> 1), radius=radius,
                                 body=height)
    return m != 0


def vertex_point(model, anim_no, clock, vertex, yaw, scale=0x1000):
    """actor_vertex_point (0x8004ede0): vertex `vertex` of the creature's
    animated model, scaled by +0x48 and turned by vec_rotate with the yaw +
    0x800 -- relative to the creature."""
    import anim
    import weapon
    v = anim.vertices(anim.load(model), anim_no, clock)[vertex]
    v = tuple((c * scale) >> 12 for c in v)
    return weapon.vec_rotate((0, (yaw + 0x800) & 0xFFF, 0), v)


def volley(raw, n72):
    """The list at a volley record's +0x1a, as the fire at 0x80052484 walks
    it from +0x72: [(the entries fired)], the new +0x72. 0x8000 goes back to
    the start, 0x8001 n sets how many to fire, 0x8003 n skips n; 0x8002 and
    0x8004 carry three arguments -- not in level 0's records."""
    fired, left, i = [], 1, n72
    while left:
        e = struct.unpack_from("<H", raw, 0x1A + 2 * i)[0]
        i += 1
        if e == 0x8000:
            i = 0
        elif e == 0x8001:
            left = struct.unpack_from("<H", raw, 0x1A + 2 * i)[0]
            i += 1
        elif e == 0x8003:
            i += 1 + struct.unpack_from("<H", raw, 0x1A + 2 * i)[0]
        elif e in (0x8002, 0x8004):
            fired.append((e, struct.unpack_from("<3h", raw, 0x1A + 2 * i)))
            i += 3
            left -= 1
        else:
            fired.append((None, e))
            left -= 1
    return fired, i


def spawn_spore(point, pct):
    """effect_spawn's arm 0x26 (0x80054338) on the point
    actor_animation_effects arm 0x26 aims from, the grace count then 0."""
    return {"f0": 0x81, "kind": SPORE, "pct": pct, "grace": 0, "half": 1,
            "model": 0x40, "life": 0x32, "x": point[0], "y": point[1] - 0xC8,
            "z": point[2], "scale": [0x400, 0x400, 0x400], "vel": [0, 0, 0],
            "count": 0x14}


def load(path=None):
    path = path or os.path.join(ROOT, "out", "lua_bp26.log")
    fx, hurt = [], {}
    if not os.path.exists(path):
        return fx, hurt
    for line in open(path):
        if line.startswith("FX "):
            m = re.match(r"FX vb=(\d+) pos=(-?\d+),(-?\d+),(-?\d+) hp=(\d+) (.*)", line)
            slots = {}
            for item in m.group(6).split():
                k, h = item.split(":")
                slots[int(k)] = slot(bytes.fromhex(h))
            fx.append({"vb": int(m.group(1)),
                       "p": tuple(int(m.group(i)) for i in (2, 3, 4)),
                       "hp": int(m.group(5)), "slots": slots})
        elif line.startswith("HURT "):
            m = re.match(r"HURT vb=(\d+) a=(\S+) m=(\S+) scale=(\d+) pct=(\d+) "
                         r"pt=(\S+) hp=(\d+)", line)
            hurt.setdefault(int(m.group(1)), []).append(
                {"scale": int(m.group(4)), "pct": int(m.group(5)),
                 "pt": tuple(int(x) for x in m.group(6).split(",")),
                 "hp": int(m.group(7)),
                 "a": [int(x) for x in m.group(2).split(",")]})
    return fx, hurt


def check(out=sys.stdout, verbose=False):
    fx, hurt = load()
    if not fx:
        print("  no out/lua_bp26.log: ./emu/run.sh debug bp26.lua, and let a "
              "kind-3 creature cast at you", file=out)
        return True
    lvl = movement.level(0)
    steps = ok = frees = strikes = sok = 0
    firsts = []
    for a, b in zip(fx, fx[1:]):
        if not 3 <= b["vb"] - a["vb"] <= 6:
            continue                 # a frame is four or five blanks
        for k, e in a["slots"].items():
            if e["kind"] != SPORE:
                continue
            nxt = b["slots"].get(k)
            if nxt is not None and nxt["life"] >= e["life"]:
                continue              # a new spore in the same slot
            # the FX line is the head of effect_driver: this frame's tick,
            # with the player where this line has it, gives the next line
            m = dict(e, scale=list(e["scale"]), vel=list(e["vel"]))
            got_hit = tick_spore(m, lvl, a["p"])
            steps += 1
            if m.get("freed"):
                same = nxt is None
                frees += 1
            else:
                same = nxt is not None and all(
                    m[f] == nxt[f] for f in ("f0", "life", "x", "y", "z",
                                             "scale", "count"))
            ok += same
            if not same and verbose and len(firsts) < 8:
                firsts.append(f"  vb {a['vb']} slot {k}: model "
                              f"{ {f: m.get(f) for f in ('life', 'y', 'scale', 'freed')} }, "
                              f"game {None if nxt is None else {f: nxt[f] for f in ('life', 'y', 'scale')}}")
            # the strike this frame: in the log at a's blank, or not at all
            logged = [h for h in hurt.get(a["vb"], [])
                      if h["pt"] == (m["x"] - m["vel"][0], m["y"] - m["vel"][1],
                                     m["z"] - m["vel"][2])]
            strikes += 1
            if got_hit is None:
                sok += not logged
            else:
                sok += len(logged) == 1 and logged[0]["scale"] == got_hit
            if (got_hit is None) != (not logged) and verbose and len(firsts) < 8:
                firsts.append(f"  vb {a['vb']} slot {k}: model strike {got_hit}, "
                              f"game {[h['scale'] for h in logged]}")
    for f in firsts:
        print(f, file=out)
    print(f"  {ok} of {steps} frames of a spore from the frame before -- life, "
          f"position, scale, growth ({frees} freed); {sok} of {strikes} strikes "
          f"on the player land or miss as the model says, with its scale",
          file=out)
    # the poison: HP one down on every frame a strike follows a strike
    hs = sorted(hurt)
    pairs = down = held = 0
    for v0, v1 in zip(hs, hs[1:]):
        if not 3 <= v1 - v0 <= 6:
            continue
        pairs += 1
        d = hurt[v0][0]["hp"] - hurt[v1][0]["hp"]
        down += d == 1
        held += d == 0
    print(f"  {down} of {pairs} strikes a frame after a strike find 1 HP gone -- "
          f"the poison set back to 0x384, a multiple of 30, ticking every frame; "
          f"{held} find none (the roll resisted)", file=out)
    return ok == steps and sok == strikes and down + held == pairs


def export(out_dir):
    """fxrecords.json -- spell_table's 96 records off the disc, which the
    strikes take their attacks from -- and fxcheck.json: runs of the machine
    over snapshots, with every answer the world gave it in order and, after
    every frame, the strikes on the player and an md5 of the 128 slots' hex,
    for godot/selftest.gd to run its copy against with the answers replayed."""
    import hashlib
    import json
    import random
    import memcard
    import spells
    with open(os.path.join(out_dir, "fxrecords.json"), "w") as fh:
        json.dump({"_note": "spell_table off the disc (tools/spells.py): an effect's "
                            "record is its kind's",
                   "records": {str(k): list(r) for k, r in enumerate(spells.rows())}},
                  fh, separators=(",", ":"))
    rng = random.Random(0xEFFEC7)
    runs = []
    for path in memcard._snapshots()[:6]:
        ram = bytearray(open(path, "rb").read())
        lv = ram[0x8018FAD9 & MASK]
        o = SLOTS & MASK
        # zeroed, as the port starts them: what an arm leaves unwritten is
        # whatever the slot held before, in the game as in a snapshot
        ram[o:o + STRIDE * COUNT] = bytes(STRIDE * COUNT)
        for k in range(COUNT):
            ram[o + STRIDE * k] = 0xFF
        for label, spawns in scenarios(bytes(ram), rng, 9):
            m = bytearray(ram)
            world = RamWorld(m, lv)
            layer0 = world.layer_offset
            log = []
            ask = world.collide_query

            def cq(*a, ask=ask, world=world, log=log):
                v = ask(*a)
                log.append([*a, v, world.layer_offset])
                return v
            world.collide_query = cq
            mach = Machine(m, world)
            for sp in spawns:
                mach.spawn(*sp)
            frames = []
            for _f in range(90):
                del log[:]
                world.hurts = []
                mach.driver()
                frames.append({"q": [list(x) for x in log], "h": world.hurts,
                               "md5": hashlib.md5(_slots(m).hex().encode()).hexdigest()})
                if all(m[o + STRIDE * k] == 0xFF for k in range(COUNT)):
                    break
            runs.append({"label": f"{os.path.basename(path)[:-4]} {label}", "layer0": layer0,
                         "spawns": [[a0, a1, kind, point.hex(),
                                     [None if v is None else {"b": v.hex()} if isinstance(v, (bytes, bytearray))
                                      else v for v in args]]
                                    for a0, a1, kind, point, args in spawns],
                         "frames": frames})
    # and the healing and protecting spells' effects, with the player's fields
    # they read and write, the rand values drawn and the lighting asked for
    import levelstate
    names = {"hp": HP, "hp_max": HP_MAX, "poison": POISON, "curse_lv": CURSE_LV,
             "curse_t": CURSE_T, "dark_lv": DARK_LV, "dark_t": DARK_T, "slow": SLOW,
             "paralysis": PARALYSIS, "b56a": B56A, "b56c": B56C, "b56e": B56E}
    heals = []
    for path in memcard._snapshots()[:4]:
        base = bytearray(open(path, "rb").read())
        lv = base[0x8018FAD9 & MASK]
        o = SLOTS & MASK
        base[o:o + STRIDE * COUNT] = bytes(STRIDE * COUNT)
        for k in range(COUNT):
            base[o + STRIDE * k] = 0xFF
        for kind in HEALING:
            ram = bytearray(base)
            hpm = rng.choice((50, rng.randrange(200, 1000)))
            struct.pack_into("<H", ram, HP_MAX & MASK, hpm)
            struct.pack_into("<H", ram, HP & MASK, rng.randrange(1, min(hpm, 120)))
            for a in (POISON, CURSE_LV, CURSE_T, DARK_LV, DARK_T, SLOW, PARALYSIS):
                struct.pack_into("<H", ram, a & MASK, rng.choice((0, 0, rng.randrange(1, 300))))
            for a in (B56A, B56C, B56E):
                struct.pack_into("<H", ram, a & MASK, rng.choice((0, rng.randrange(1, 30))))
            point = bytes(ram[PLAYER_POS & MASK:(PLAYER_POS & MASK) + 16])
            vel = bytes(8)
            spawns = ([(0xA, 0x40, kind, point, [vel, 0]), (0xA, 0x40, kind, point, [vel, 1])]
                      if kind in (0x1A, 0x1C) else [(0xA, 0x40, kind, point, [vel])])
            m = bytearray(ram)
            lcg = levelstate.Lcg()
            drawn, lit = [], []

            def rnd(lcg=lcg, drawn=drawn):
                v = lcg()
                drawn.append(v)
                return v
            mach = Machine(m, RamWorld(m, lv), rnd)
            blend = mach.lighting

            def lighting(rgb, near, far, k, blend=blend, lit=lit):
                lit.append([near, far, k])
                blend(rgb, near, far, k)
            mach.lighting = lighting
            start = {n: struct.unpack_from("<H", m, a & MASK)[0] for n, a in names.items()}
            for sp in spawns:
                mach.spawn(*sp)
            frames = []
            for _f in range(40):
                del drawn[:], lit[:]
                mach.driver()
                frames.append({"md5": hashlib.md5(_slots(m).hex().encode()).hexdigest(),
                               "fields": {n: struct.unpack_from("<H", m, a & MASK)[0]
                                          for n, a in names.items()},
                               "rand": list(drawn), "lit": [list(x) for x in lit]})
                if all(m[o + STRIDE * k] == 0xFF for k in range(COUNT)):
                    break
            heals.append({"label": f"{os.path.basename(path)[:-4]} kind {kind:#x}",
                          "fields": start,
                          "spawns": [[a0, a1, kd, pt.hex(),
                                      [{"b": v.hex()} if isinstance(v, (bytes, bytearray)) else v
                                       for v in args]] for a0, a1, kd, pt, args in spawns],
                          "frames": frames})
    # and the fire ball, collide_query and actor_attack_player stood in for
    # as fire_check stands them in: the answers, and the hits handed over
    fires = []
    frng = random.Random(0xF1E)
    for kind_, speed_, _name, more_, nframes_ in SPELLS_SENT:
      speed_ = speed_ or 0
      for path in memcard._snapshots()[:6]:
          base = bytearray(open(path, "rb").read())
          o = SLOTS & MASK
          base[o:o + STRIDE * COUNT] = bytes(STRIDE * COUNT)
          for k in range(COUNT):
              base[o + STRIDE * k] = 0xFF
          px, py, pz = struct.unpack_from("<3i", base, PLAYER_POS & MASK)
          for _ in range(4):
              m = bytearray(base)
              working = [frng.randrange(0, 200) for _k in range(5)]
              for k in range(5):
                  struct.pack_into("<H", m, (WORKING & MASK) + 2 * k, working[k])
              yaw = frng.randrange(0x1000)
              point = struct.pack("<4i", px + frng.randrange(-0x400, 0x400), py - 0x640,
                                  pz + frng.randrange(-0x400, 0x400), 0)
              d = movement.direction_from_angles(frng.randrange(-0x100, 0x100) & 0xFFF, yaw)
              vel = struct.pack("<4h", *[_s16_((c * speed_) >> 12) for c in d], 0)
              if kind_ in FLAT:
                  x_, y_, z_, _w = struct.unpack("<4i", point)
                  point = struct.pack("<4i", x_, y_ + FLAT[kind_], z_, 0)
                  vel = vel[:2] + bytes(2) + vel[4:]
              m[TICK_SP & MASK:(TICK_SP & MASK) + TICK_FRAME] = bytes(TICK_FRAME)   # the port's start
              vy = frng.randrange(0x1000)
              struct.pack_into("<4H", m, VIEW_ANGLES & MASK, 0, vy, 0, 0)
              if frng.randrange(2) == 0:                       # water just under the path
                  struct.pack_into("<i", m, SURFACE & MASK, py - 0x640 - frng.randrange(0, 0x1F4))
              s18 = struct.unpack_from("<i", m, SURFACE & MASK)[0]
              view = bytes(m[VIEW_ANGLES & MASK:(VIEW_ANGLES & MASK) + 8])
              slot = 0xFF
              if "slot?" in more_:
                  awake = [k for k in range(ACTOR_N)
                           if m[(ACTORS + ACTOR_STRIDE * k + 9) & MASK] == 1] or [0xFF]
                  slot = frng.choice((frng.choice(awake),) * 3 + (0xFE, 0xFF))
              args_ = [vel] + [view if v == "view" else slot if v == "slot?" else v for v in more_
                               if v not in ("back", "anywhere")]
              a1_ = 0x42
              if not speed_:
                  a1_, point, args_ = _placed(m, more_, struct.unpack_from("<3i", point))
              w = StandIn(7, m, quiet=kind_ in QUIET)
              log = []
              ask = w.collide_query

              def cq(x, y, z, r, h, flags, ask=ask, log=log, w=w):
                  v = ask(x, y, z, r, h, flags)
                  log.append([_s32(x), _s32(y), _s32(z), r, h & 0xFFFFFFFF, flags, v, w.layer_offset,
                              w.collide_actor])
                  return v
              w.collide_query = cq
              cws, sfs = [], []
              ask_w, ask_s = w.collide_wrapper, w.surface

              def cw(x, y, z, r, h, ask_w=ask_w, cws=cws):
                  v = ask_w(x, y, z, r, h)
                  cws.append([_s32(x), _s32(y), _s32(z), r, h, v])
                  return v

              def sf(x, y, z, r, h, ask_s=ask_s, sfs=sfs):
                  v = ask_s(x, y, z, r, h)
                  sfs.append([_s32(x), _s32(y), _s32(z), r, h, v])
                  return v
              w.collide_wrapper, w.surface = cw, sf
              sis = []
              ask_si = w.sight

              def si(point, yaw, pitch, reach, yc, pc, noise, rand, ask_si=ask_si, sis=sis):
                  n = [0]

                  def counted(rand=rand, n=n):
                      n[0] += 1
                      return rand()
                  a, d = ask_si(point, yaw, pitch, reach, yc, pc, noise, counted)
                  sis.append([*[_s32(c) for c in point], yaw, pitch, reach, yc, pc, noise,
                              (a - ACTORS) // ACTOR_STRIDE if a else -1, d, n[0]])
                  return a, d
              w.sight = si
              ams = []
              ask_am = w.actor_mid

              def am(t, ask_am=ask_am, ams=ams):
                  v = ask_am(t)
                  ams.append([t, *v])
                  return v
              w.actor_mid = am
              scs, sts, aps = [], [], []
              ask_sc, ask_st, ask_ap = w.surface_ceiling, w.spot_taken, w.actor_point

              def sc(x, y, z, r, h, ask_sc=ask_sc, scs=scs):
                  v = ask_sc(x, y, z, r, h)
                  scs.append([_s32(x), _s32(y), _s32(z), r, h, *v])
                  return v

              def st(x, y, z, r, own, ask_st=ask_st, sts=sts):
                  v = ask_st(x, y, z, r, own)
                  sts.append([_s32(x), _s32(y), _s32(z), r, own, v])
                  return v

              def ap(c, ask_ap=ask_ap, aps=aps):
                  v = ask_ap(c)
                  aps.append([c, *struct.unpack("<4i", v)])
                  return v
              w.surface_ceiling, w.spot_taken, w.actor_point = sc, st, ap
              drawn = []
              lcg = levelstate.Lcg()

              def rnd(lcg=lcg, drawn=drawn):
                  v = lcg()
                  drawn.append(v)
                  return v
              mach = Machine(m, w, rnd)
              try:
                  spawn_rand = []
                  sps = _spawns(a1_, kind_, point, args_)
                  for sp in sps:
                      mach.spawn(*sp)
                  spawn_rand = list(drawn)
                  spawn_ask = {"cw": [list(x) for x in cws], "sf": [list(x) for x in sfs]}
                  frames = []
                  for _f in range(nframes_):
                      del log[:], w.hits[:], drawn[:], w.hurts[:], w.strikes[:], w.released[:]
                      del cws[:], sfs[:], sis[:], ams[:], scs[:], sts[:], aps[:]
                      mach.driver()
                      frames.append({"q": [list(x) for x in log], "rand": list(drawn),
                                     "cw": [list(x) for x in cws], "sf": [list(x) for x in sfs],
                                     "si": [list(x) for x in sis],
                                     "am": [list(x) for x in ams],
                                     "sc": [list(x) for x in scs],
                                     "st": [list(x) for x in sts],
                                     "ap": [list(x) for x in aps],
                                     "hits": [[h[0], h[1], h[2], h[3], h[4],
                                               None if h[5] is None else [_s32(v) for v in h[5]]]
                                              for h in w.hits],
                                     "released": list(w.released),
                                     "hurts": [list(h) for h in w.hurts],
                                     "strikes": [list(x) for x in w.strikes],
                                     "md5": hashlib.md5(_slots(m).hex().encode()).hexdigest()})
                      if all(m[o + STRIDE * k] == 0xFF for k in range(COUNT)):
                          break
              except NotImplementedError:
                  continue
              fires.append({"label": f"{os.path.basename(path)[:-4]} kind {kind_:#x}", "layer0": 7,
                            "spawn_rand": spawn_rand, "spawn_ask": spawn_ask,
                            "fields": dict({"px": px, "py": py, "pz": pz, "s18": s18, "vy": vy,
                                            "pw": struct.unpack_from("<i", m, (PLAYER_POS + 12) & MASK)[0],
                                            "cs": struct.unpack_from("<i", m, 0x801E6474 & MASK)[0]},
                                           **{f"w{k}": working[k] for k in range(5)}),
                            "spawns": [[a0, a1, kd, pt.hex(),
                                        [{"b": v.hex()} if isinstance(v, bytes) else v for v in args]]
                                       for a0, a1, kd, pt, args in sps],
                            "frames": frames})
    # and effect_aim: a creature's angles, the target, the speed, the point and
    # the spread, and the velocity and yaw aim() gives -- the game's own, 600
    # of 600 (aim_check)
    aims = []
    for _ in range(300):
        ang = (rng.randrange(0x1000), rng.randrange(0x1000))
        t = [rng.randrange(0, 0x28000), rng.randrange(-0x8000, 0x1000), rng.randrange(0, 0x28000)]
        p = [t[0] + rng.randrange(-0x2000, 0x2000), t[1] + rng.randrange(-0x2000, 0x1000),
             t[2] + rng.randrange(-0x2000, 0x2000)]
        speed = rng.choice((0x12C, 0x100, 0x200, rng.randrange(1, 0x400)))
        spread = rng.choice((0x400, 0x200, 0x800))
        vel, yaw = aim((ang[0], ang[1], 0), t, speed, p, -1, spread)
        aims.append([ang[0], ang[1], *t, speed, *p, spread, *vel, yaw])
    path = os.path.join(out_dir, "fxcheck.json")
    with open(path, "w") as fh:
        json.dump({"_note": "the effect machine of tools/effects.py over snapshots, the "
                            "world's answers in order; and effect_aim's cases",
                   "runs": runs, "aims": aims, "heals": heals, "fires": fires},
                  fh, separators=(",", ":"))
    return path

def export_strikes(out_dir, n=400):
    """strikecheck.json: 0x8004ceac's cases in godot/actors.gd's form -- the
    awake creatures of a snapshot about one of them, their kinds, a strike
    there of each mode -- and what strike_creatures leaves them, for the
    self-test. Parts and followers, which the port does not pass a hit on
    from, are put to sleep first, and no creature is the one acting."""
    import json
    import random
    import levelstate
    import memcard
    import hit
    rng = random.Random(0x8004CEAC)
    cases = []
    paths = memcard._snapshots()
    tries = 0
    while len(cases) < n and tries < 20 * n:
        tries += 1
        ram = bytearray(open(paths[tries % len(paths)], "rb").read())
        r = hit.Ram(ram)
        r.w32(CURRENT_ACTOR, 0)
        awake = []
        for k in range(ACTOR_N):
            a = ACTORS + ACTOR_STRIDE * k
            if r.u8(a + 9) != 1:
                continue
            if r.u8(a) == 3 or r.u32(a + 0x28) & 0x10:
                r.w8(a + 9, 0)
                continue
            awake.append(k)
        if not awake:
            continue
        a = ACTORS + ACTOR_STRIDE * rng.choice(awake)
        x, y, z = r.s32(a + 0x2C), r.s32(a + 0x30), r.s32(a + 0x34)
        mode = rng.choice((0x8002, 0x800, 0x8000, 0x8001, 0x400))
        radius = rng.choice((0x300, 0x900, 0x1800, 0x3000, rng.randrange(0x100, 0x4000)))
        near = rng.choice((0, (15 * radius) >> 4, (29 * radius) >> 5, rng.randrange(0, radius)))
        p = [x + rng.randrange(-radius, radius + 1), y - rng.randrange(-0x400, 0x800),
             z + rng.randrange(-radius, radius + 1), rng.randrange(-0x800, 0x800)]
        pt = STRIKE_POINT
        struct.pack_into("<4i", ram, pt & MASK, *p)
        stat = rng.randrange(0, 120)
        att = [rng.choice((0, 0, rng.randrange(1, 60))) for _ in range(8)]
        scale = rng.choice((0x1000, 0x1000, rng.randrange(0x100, 0x1000), 0x9000))
        edge = rng.choice((0x400, 0x400, 0x1000, rng.randrange(0, 0x1000)))
        flags = rng.choice((0x60, 0x60, 0xE0, 0x20))
        seed = rng.randrange(1 << 30)
        kinds, klists, before = {}, {}, {}
        for k in awake:
            ak = ACTORS + ACTOR_STRIDE * k
            kn = r.u8(ak + 2)
            if kn not in kinds:
                kind = hit.ENTITY + 120 * kn
                kl = []
                for i in range(16):
                    q = r.u32(kind + 0x38 + 4 * i)
                    if q == 0:
                        break
                    kl.append(q)
                klists[kn] = kl
                kinds[kn] = {"defence": [r.u16(kind + 0x20 + 2 * i) for i in range(8)],
                             "exp": r.s16(kind + 0x1E), "weight": r.u8(kind + 2),
                             "arc_back": r.s16(kind + 0x18),
                             "behaviours": [list(ram[q & MASK:(q & MASK) + 0x20]) for q in kl]}
            d = hit._actor_dict(r, ak, klists[kn])
            d["kind"] = kn
            d["radius"] = r.u16(ak + 0x1C)
            before[k] = d
        kills = [r.u8(hit.KILL_FLAG), r.u8(hit.KILL_COUNT)]
        calls = []
        strike_creatures(r, pt, near, radius, mode, edge, stat, att, scale, flags, 0,
                         levelstate.Lcg(seed), calls, lambda actor, dd: dd)
        after = {}
        for k in awake:
            ak = ACTORS + ACTOR_STRIDE * k
            d = hit._actor_dict(r, ak, klists[r.u8(ak + 2)])
            if d != {key: before[k][key] for key in d}:
                after[str(k)] = d
        cases.append({"actors": {str(k): v for k, v in before.items()},
                      "kinds": {str(k): v for k, v in kinds.items()},
                      "p": p, "near": near, "radius": radius, "mode": mode, "edge": edge,
                      "stat": stat, "att": att, "scale": scale, "flags": flags, "seed": seed,
                      "kills": kills, "after": after,
                      "kills_after": [r.u8(hit.KILL_FLAG), r.u8(hit.KILL_COUNT)],
                      "calls": [[c[0], c[1]] if c[0] == "exp" else [c[0]] for c in calls
                                if c != ("exp", 0)]})
    path = os.path.join(out_dir, "strikecheck.json")
    with open(path, "w") as fh:
        json.dump({"_note": "0x8004ceac, the creatures' strike, as tools/effects.py "
                            "strike_creatures has it (whose model the game's own holds)",
                   "cases": cases}, fh, separators=(",", ":"))
    return path


# --- the machine, byte for byte ---------------------------------------------
#
# What follows is effect_spawn, effect_driver and the arms of effect_tick it
# has, run as the game runs them: over the 128 slots of 0x4c bytes where the
# game keeps them, in RAM. So the game's own code (tools/mipsrun.py) and this
# can be put side by side a byte at a time, and the port can hold its copy to
# this the same way. What an effect asks of the rest of the game --
# collide_query and effect_hurt_player -- goes through `world`, which over a
# snapshot is the snapshot's (RamWorld) and in the port the port's.

SLOTS, STRIDE, COUNT = 0x801B80EC, 0x4C, 128
CURRENT, CURRENT_REC, INDEX = 0x801BA6F0, 0x801BA6EC, 0x801BA6F4
SPELL_TABLE, RECORD = 0x801B77EC, 24
PLAYER_POS, PLAYER_STATE = 0x801B25F0, 0x801B25E5
HP, HP_MAX, POISON = 0x801B24FC, 0x801B24FA, 0x801B255C
CURSE_LV, CURSE_T, DARK_LV, DARK_T = 0x801B255E, 0x801B2560, 0x801B2562, 0x801B2564
SLOW, PARALYSIS = 0x801B2566, 0x801B2568
B56A, B56C, B56E = 0x801B256A, 0x801B256C, 0x801B256E
TILE_LOOK = 0x801AEEFC
FIRE_BALL = 0x00
STONE, WIND_CUTTER = 0x06, 0x0D
# The weapons' spells (FORMATS.md "The weapons' spells") whose arms are in:
# ryu-ga's is wind cutter's two arms, anorium sword's the fire ball's with
# its own particle; capricorn's, vaculacia sword's, Seath's sword's and
# morguline axe's their own
RYU_GA, CAPRICORN, ANORIUM, VACULACIA, SEATHS, MORGULINE = 0x38, 0x3A, 0x3E, 0x40, 0x42, 0x4C
# and the rest: the excellector's two (one tick), 0x3c (no weapon's), triple
# fang's two (0x47 flash's arms), 0x4b (the second moonlight sword's second),
# the moonlight swords' marks (0x78, 0x7a) with their pillars (0x5c, 0x5d)
# and bursts (0x48), dark slayer's two (0x7c, 0x7b) with their spheres (0x44,
# 0x45), and 0x4b's sparks (3)
EXCEL1, EXCEL2, FALLER, FANG, FLASH, MOON = 0x36, 0x37, 0x3C, 0x46, 0x47, 0x4B
MARK, MARK2, PILLAR, PILLAR2, MOON_BURST = 0x78, 0x7A, 0x5C, 0x5D, 0x48
SLAYER2, SLAYER, SPHERE2, SPHERE, SPARK = 0x7C, 0x7B, 0x44, 0x45, 0x03
LIGHTNING = 0x71                    # and the creatures' 0x7d and 0x81; bolts 0x72, 0x7e, 0x80;
                                    # their spheres 0x13, 0x29, 0x2d
HAZE, SHUDOM, WALWIND, RING, WAVE = 0x0B, 0x09, 0x11, 0x5E, 0x59
EARTH_WAVE, BORTECTH, HOLD = 0x07, 0x0C, 0x65
METEOR, BLAST = 0x5F, 0x5A
ORLADIN, BURST, RAY = 0x15, 0x58, 0x5B
TORNADO, FIRE_WALL, FIRE_STORM, FLAME = 0x0F, 0x01, 0x02, 0x04
BREATH = 0x6E                       # what flame breathes: the empty arm
EMPTY = frozenset((0x08, 0x0A, 0x0E, 0x18, 0x1D, 0x2B, 0x39, 0x3B, 0x3D, 0x3F, 0x41, 0x43,
                   0x49, 0x4A, 0x4D, 0x4E, 0x4F, 0x54, 0x57, 0x60, 0x61, 0x62, 0x63, 0x68,
                   0x69, 0x6A, 0x6B, 0x6D, 0x6E, 0x73, 0x75, 0x76, 0x77, 0x79, 0x7F))
"""The 35 kinds whose arm of effect_spawn is 0x80055b18 (the switch table
at 0x80012cb4): the slot set up and freed again, its bytes left; their arm
of effect_tick is 0x8005bbd0, nothing."""
ZERO_VEC = 0x8009C33C               # BSS: eight bytes of 0, a velocity
COLLIDE_MASK = 0x801E6488           # collide_query's last answer, kept
TICK_SP, TICK_FRAME = 0x801FBC20, 0x2B8  # effect_tick's sp, as the check's driver runs it
STRIKE_POINT = 0x801FF0D0           # the machine's stand-in for an arm's point on its stack
VIEW_ANGLES = 0x801B2608
SCRATCH_POINT = 0x801FF0C0          # where the check lays a hit's point back
SPLASH = 0x70
VBLANK, SPLASH_SOUND = 0x801C12E8, 0x8009C214 + 0x1DC   # vblank_count, gp + 0x1dc
WORKING = 0x801B2526             # the five working skills
SURFACE = 0x801E647C             # surface_plane_18, the water's top
COLLIDE_QUERY, ATTACK_HIT, SOUND_AT = 0x80033F38, 0x800533E8, 0x80015688
ACTORS, ACTOR_STRIDE, ACTOR_N = 0x80185DA8, 0x88, 200
ACTOR_SKIP, CURRENT_ACTOR, COLLIDE_ACTOR = 0x8018FAA8, 0x8018FAB4, 0x801E648C
PLAYER_FIELDS = (HP, POISON, CURSE_LV, CURSE_T, DARK_LV, DARK_T, SLOW, PARALYSIS)
LAYER_OFFSET = 0x801E646E        # collision_layer_offset, select_cell_layer's answer
GRID, CELL_BYTES = 0x801D4464, 10
OBJECT_TABLE, OBJECT_STRIDE, OBJECT_TYPES = 0x80191A5C, 0x44, 0x8018FB3C
SPAWN, DRIVER, AIM, HURT_PLAYER = 0x80053C84, 0x8005BC50, 0x8004F1D0, 0x8002B114
RAND = 0x800796C0
MASK = 0x1FFFFF
FAST = 0xC5C10                   # a speed squared past it gets the half-step test
TRAIL = 0x6F                     # the puff 0x23 and 0x24 leave every frame
TRAIL_ARGS = [0xE10, -0x80, 5, 0x16, 0, 1, 3]   # 0x80058f50's, after the velocity
QUERY = {1: 0xA1, 2: 0x31, 3: 0xB1, 4: 0x01}    # effect_collide: +0 & 7 -> flags


def _s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def _div7fff(x):
    """x / 0x7fff as the compiler builds it (0x80010003, the high word added
    back, a shift of 14, the sign): toward 0."""
    x = _s32(x)
    return (_s32(((x * _s32(0x80010003)) >> 32) + x) >> 14) - (x >> 31)


def div5(x):
    """x / 5 as the compiler builds it (0x66666667, a shift, the sign): toward 0."""
    q = (_s32(x) * 0x66666667) >> 32
    return (q >> 1) + (1 if _s32(x) < 0 else 0)


class Machine:
    """effect_spawn (0x80053c84), effect_driver (0x8005bc50) and effect_tick's
    arms 0x23/0x24, 0x26 and 0x6f, over RAM `m`."""

    def __init__(self, m, world, rand=None):
        import levelstate
        self.m, self.w = m, world
        self.rand = rand or levelstate.Lcg()

    def u8(self, a):
        return self.m[a & MASK]

    def u16(self, a):
        return struct.unpack_from("<H", self.m, a & MASK)[0]

    def s16(self, a):
        return struct.unpack_from("<h", self.m, a & MASK)[0]

    def s32(self, a):
        return struct.unpack_from("<i", self.m, a & MASK)[0]

    def w8(self, a, v):
        self.m[a & MASK] = v & 0xFF

    def w16(self, a, v):
        struct.pack_into("<H", self.m, a & MASK, v & 0xFFFF)

    def w32(self, a, v):
        struct.pack_into("<I", self.m, a & MASK, v & 0xFFFFFFFF)

    def put(self, a, data):
        o = a & MASK
        self.m[o:o + len(data)] = data

    def get(self, a, n):
        o = a & MASK
        return bytes(self.m[o:o + n])

    def out_words(self, words):
        """The stack arguments a call effect_tick makes leaves in its frame
        from sp+0x10: the next call that hands fewer and reads more takes
        them -- flash's second burst (0x80059c90) takes five. A pointer is
        laid as 0: no reader takes one."""
        for i, v in enumerate(words):
            self.w32(TICK_SP + 0x10 + 4 * i, v)

    # effect_alloc (0x80053b64): the first slot from the top whose +0 is 0xff
    def alloc(self):
        for k in range(COUNT):
            if self.u8(SLOTS + STRIDE * k) == 0xFF:
                return SLOTS + STRIDE * k
        return 0

    def spawn(self, a0, a1, kind, point, args, direct=False):
        """effect_spawn(a0, a1, kind, point, ...): `point` the 16 bytes a3
        points at, or None; `args` the stack arguments from the fifth on, a
        pointer as the bytes it points at. The slot, or 0 when none is free.
        `direct`: called by effect_tick itself, whose frame keeps the words
        (out_words)."""
        if direct:
            self.out_words([0 if v is None or isinstance(v, (bytes, bytearray)) else v
                            for v in args])
        s = self.alloc()
        if not s:
            return 0
        self.w8(s, a1)
        self.w8(s + 1, kind)
        if point is not None:
            self.put(s + 0x18, point[:16])
        self.w8(s + 0xA, 3)
        vel = args[0] if args else None
        if vel is not None:
            self.put(s + 0x38, vel[:8])
        else:
            for o in (0x3C, 0x3A, 0x38):
                self.w16(s + o, 0)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0x1000)
        f0 = self.u8(s)
        self.w8(s + 7, 0)
        self.w8(s + 6, a0)
        for o in (0x2C, 0x2A, 0x28, 0x14):
            self.w16(s + o, 0)
        self.w8(s + 5, 0)
        self.w8(s + 8, 1)
        self.w8(s + 0xB, 8 if f0 & 0x40 and self.u8(PLAYER_STATE) == 1 else 1)
        vx, vy, vz = self.s16(s + 0x38), self.s16(s + 0x3A), self.s16(s + 0x3C)
        self.w16(s + 0x12, 0)
        self.w8(s + 9, 0)
        self.w8(s + 0xC, 0xFF)
        self.w16(s + 0x10, -1)
        self.w8(s + 0xD, 1 if FAST < _s32(vx * vx + vy * vy + vz * vz) else 0)
        self.w16(s + 0xE, 0)
        if kind >= 0x82 or kind in EMPTY:
            self.w8(s, 0xFF)
            return s
        arm = {0x1F: self._spawn_1f, 0x22: self._spawn_22, 0x23: self._spawn_23,
               0x24: self._spawn_24, 0x26: self._spawn_26, TRAIL: self._spawn_6f,
               0x17: self._spawn_17, 0x19: self._spawn_19, 0x1A: self._spawn_1a,
               0x1B: self._spawn_1b, 0x1C: self._spawn_1c, 0x1E: self._spawn_1e,
               FIRE_BALL: self._spawn_00, SPLASH: self._spawn_70,
               STONE: self._spawn_06, WIND_CUTTER: self._spawn_0d,
               HAZE: self._spawn_0b, SHUDOM: self._spawn_09, WALWIND: self._spawn_11,
               RING: self._spawn_5e, WAVE: self._spawn_59, EARTH_WAVE: self._spawn_07,
               0x16: self._spawn_07, BORTECTH: self._spawn_0c, HOLD: self._spawn_65,
               METEOR: self._spawn_5f, BLAST: self._spawn_5a, ORLADIN: self._spawn_15,
               BURST: self._spawn_58, RAY: self._spawn_5b, TORNADO: self._spawn_0f,
               FIRE_WALL: self._spawn_01, FIRE_STORM: self._spawn_02,
               FLAME: self._spawn_04, RYU_GA: self._spawn_0d, ANORIUM: self._spawn_3e,
               CAPRICORN: self._spawn_3a, SEATHS: self._spawn_42,
               MORGULINE: self._spawn_4c, VACULACIA: self._spawn_40,
               EXCEL1: self._spawn_36, EXCEL2: self._spawn_37, FALLER: self._spawn_3c,
               FANG: self._spawn_46, FLASH: self._spawn_47, 0x14: self._spawn_47,
               0x12: self._spawn_47, MOON: self._spawn_4b, SPARK: self._spawn_03,
               MARK: self._spawn_78, MARK2: self._spawn_78, PILLAR: self._spawn_5c,
               PILLAR2: self._spawn_5c, MOON_BURST: self._spawn_48, SPHERE2: self._spawn_44,
               SPHERE: self._spawn_44, SLAYER2: self._spawn_7c, SLAYER: self._spawn_7b,
               LIGHTNING: self._spawn_71, 0x7D: self._spawn_71, 0x81: self._spawn_71,
               0x72: self._spawn_72, 0x7E: self._spawn_72, 0x80: self._spawn_72,
               0x13: self._spawn_13, 0x29: self._spawn_13, 0x2D: self._spawn_13}.get(kind)
        if arm is None:
            raise NotImplementedError(f"effect_spawn's arm {kind:#x}")
        arm(s, args)
        return s

    def _spawn_06(self, s, args):           # 0x800541f4, stone
        self.w16(s + 0xE, 0x40)
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0xF)
        self.w8(s + 3, 0xF)
        self.w8(s + 0x44, 0)
        self.w16(s + 0x10, 0x46)            # and its sound (sub_800532d4, 0x32)

    def _tick_06(self, s):                  # 0x800569e4, stone
        """Flying (+0x44 0) it spins its pitch 0xc8 a frame; its first hit
        strikes, steps it back and drops it from -0x64, falling by 0xd a
        frame (+0x44 1); the next hit strikes again and it lies (+0x44 2),
        +9 5, +0xc 0x32, fading +0x12 by 0x100 a frame from 0x400 to 0x1000.
        A splash a frame while it is in the water."""
        b44 = self.u8(s + 0x44)
        if b44 == 2:
            v = (self.u16(s + 0x12) + 0x100) & 0xFFFF
            self.w16(s + 0x12, v)
            if _s16_(v) >= 0x1000:
                self.w8(s, 0xFF)
            return
        if b44 == 1:
            self.w16(s + 0x3A, self.u16(s + 0x3A) + 0xD)
        self.w16(s + 0x28, self.u16(s + 0x28) + 0xC8)
        hit = self.move(0x1F4, 0x1F4, 0xFA)
        if hit:
            self.attack(s, hit)
            if self.u8(s + 0x44) == 1:
                self.w8(s + 0x44, 2)
                self.w8(s + 9, 5)
                self.w8(s + 0xC, 0x32)
                self.w16(s + 0x12, 0x400)
                return
            self.undo(s)
            self.w8(s + 0x44, 1)
            self.w16(s + 0x3C, 0)
            self.w16(s + 0x38, 0)
            self.w16(s + 0x3A, -0x64)
        self.splash_one(s + 0x18, 0x4000, 0x4000, 0x1F4)

    def _spawn_0d(self, s, args):           # 0x800544b8, wind cutter
        self.setup(s, 0xD, 0x1400, 5)       # after its sound (0x2b)
        self.w16(s + 0x10, 0x2D)
        self.w8(s + 0x44, 0)
        self.w8(s + 0xD, 1)
        self.put(s + 0x28, self.get(VIEW_ANGLES, 8))
        self.w16(s + 0x30, 0x1800)
        self.w16(s + 0x32, 0x1000)
        self.w16(s + 0x28, 0)
        self.w16(s + 0x2C, 0)
        self.w16(s + 0x34, 0x2000)

    def _tick_0d(self, s):                  # 0x800574b4, wind cutter
        """Flat, its yaw the view's turning 0x2bc a frame: each thing it
        passes it strikes once (+0x44 the latch, cleared on a clear frame),
        and the tiles (any of the low four bits) end it."""
        hit = self.move(0xB4, 0x80000000, 0)
        if hit:
            if hit & 0xF:
                self.w8(s, 0xFF)
            if self.u8(s + 0x44) == 0:
                self.w8(s + 0x44, 1)
                self.attack(s, hit)
        else:
            self.w8(s + 0x44, 0)
        self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x2BC)

    def _spawn_0b(self, s, args):           # 0x80054b08, haze
        self.particle(s, 0x16, 0x1000, 5)
        self.w16(s + 0x10, 0x46)
        self.w16(s + 0xE, 0xC0)             # its sound (0x94) with the third of a cast's

    def _tick_0b(self, s):                  # 0x80058164, haze
        """Each thing it meets it strikes once (+0x44 the latch, cleared on
        a clear frame), and the tiles end it -- the wind cutter's way, with
        nothing turned and no splash."""
        hit = self.move(0xB4, 0, 0)
        if hit:
            if hit & 0xF:
                self.w8(s, 0xFF)
            if self.u8(s + 0x44) == 0:
                self.attack(s, hit)
                self.w8(s + 0x44, 1)
        else:
            self.w8(s + 0x44, 0)

    def _flat(self, s, model, scale, args):
        """What shudom's and walwind's arms share (0x80054e54, 0x80054804):
        model `model`, mode 5, the yaw of the angles args[1] points at (the
        view's), level, a life of 0x96."""
        self.w8(s + 8, 1)
        self.w8(s + 9, 5)
        self.w8(s + 2, model)
        self.w8(s + 3, model)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w8(s + 4, 0)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, scale)
        self.put(s + 0x28, args[1][:8])
        self.w16(s + 0x28, 0)
        self.w16(s + 0x2C, 0)
        self.w16(s + 0x3A, 0)
        self.w16(s + 0x10, 0x96)
        self.w16(s + 0x44, 0)

    def _spawn_09(self, s, args):           # 0x80054e54, shudom
        self._flat(s, 0x33, 0x4B0, args)
        self.w16(s + 0xE, 0)
        self.w16(s + 0x46, self.u16(VIEW_ANGLES + 2))   # and its sound, 0x92

    def _spawn_11(self, s, args):           # 0x80054804, walwind
        self._flat(s, 0x32, 0xBB8, args)    # and its sound, 0x98

    def _tick_09(self, s):                  # 0x800581b8, shudom
        """Level through anything, the tiles ending it; at counts 12, 18,
        24 ... (11 or more, a multiple of 6) a ring (0x5e) where it is,
        turned as the view was when it was cast."""
        hit = self.move(0xFA, 0x80000000, 0)
        if hit & 0xF:
            self.w8(s, 0xFF)
        n = self.s16(s + 0x44)
        if n >= 0xB and n % 6 == 0:
            self.spawn(0xA, 0x42, RING, self.get(s + 0x18, 16), [None, self.s16(s + 0x46)], direct=True)
        self._spin(s)

    def _tick_11(self, s):                  # 0x80058248, walwind
        """Level, striking whatever it meets every frame, the tiles ending
        it; at counts 20, 30, 40 ... (16 or more, a multiple of 10) a wave
        (0x59) falling from where it is."""
        hit = self.move(0xFA, 0x80000000, 0)
        if hit:
            if hit & 0xF:
                self.w8(s, 0xFF)
            self.attack(s, hit)
        n = self.s16(s + 0x44)
        if n >= 0x10 and n % 10 == 0:
            self.spawn(0xA, 0x42, WAVE, self.get(s + 0x18, 16), [struct.pack("<4h", 0, 0x54, 0, 0)], direct=True)
        self._spin(s)

    def _spin(self, s):                     # 0x800582f4
        self.w16(s + 0x44, self.u16(s + 0x44) + 1)
        self.w16(s + 0x14, (self.u16(s + 0x14) + 0x80) & 0xFFF)

    def _spawn_5e(self, s, args):           # 0x80054b7c, shudom's ring
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0x1E)
        self.w8(s + 3, 0x1E)
        self.w16(s + 0x10, 0x1E)
        self.w16(s + 0x32, 0x1000)
        self.w8(s + 9, 0)
        self.w16(s + 0x30, 0xA)
        self.w16(s + 0x34, 0xA)
        self.w16(s + 0x28, 0x400)
        self.w16(s + 0x2C, 0)
        self.w16(s + 0xE, 0)
        self.w16(s + 0x2A, args[1])         # and its sound, 0x26

    def _tick_5e(self, s):                  # 0x80059adc, shudom's ring
        """Growing 0xc0 a frame; from 0x300 it strikes the creatures between
        15/16 and 9/8 of it from its middle, 0x3e8 under it; past 0xc80 gone."""
        self.w16(s + 0x34, self.u16(s + 0x34) + 0xC0)
        self.w16(s + 0x30, self.u16(s + 0x30) + 0xC0)
        sc = self.s16(s + 0x30)
        if sc >= 0x300:
            self.put(STRIKE_POINT, struct.pack("<4i", self.s32(s + 0x18), _s32(self.s32(s + 0x1C) + 0x3E8),
                                               self.s32(s + 0x20), self.s16(s + 0x2A)))
            self.strike(STRIKE_POINT, (15 * sc) >> 4, (9 * sc) >> 3, 0x8002, 0x400, 0x1000)
        if self.s16(s + 0x30) >= 0xC81:
            self.w8(s, 0xFF)

    def _spawn_59(self, s, args):           # 0x80054894, walwind's wave
        self.w8(s + 8, 1)
        self.w8(s + 2, 0x1F)
        self.w8(s + 3, 0x1F)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w16(s + 0x32, 0x7D0)
        self.w8(s + 4, 0)
        self.w8(s + 9, 5)
        self.w16(s + 0x30, 0x28)
        self.w16(s + 0x34, 0x28)
        self.w16(s + 0x10, 0x50)
        self.w16(s + 0x44, 0)
        self.w8(s + 0xB, 5)

    def _tick_59(self, s):                  # 0x80058314, walwind's wave
        """Turning 0x140 a frame. Falling until the tiles stop it (+0x44 0,
        its sound 0x27 then); up 0xa0 once (1); then growing 0x280 a frame
        (2), from 0x300 striking the creatures between 29/32 and 35/32 of it
        -- and gone past 0x36b0, striking once more as +0 0xff: the player
        too, and the creatures as a spell of nobody's."""
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x140)
        n = self.s16(s + 0x44)
        if n == 0:
            hit = self.move(0xB4, 0x80000000, 0)
            if hit & 0xF:
                self.w16(s + 0x44, self.u16(s + 0x44) + 1)
        elif n == 1:
            self.w16(s + 0x44, self.u16(s + 0x44) + 1)
            self.w32(s + 0x1C, self.s32(s + 0x1C) - 0xA0)
        elif n == 2:
            self.w16(s + 0x30, self.u16(s + 0x30) + 0x280)
            self.w16(s + 0x34, self.u16(s + 0x34) + 0x280)
            sc = self.s16(s + 0x30)
            if sc >= 0x36B1:
                self.w8(s, 0xFF)
            if sc >= 0x300:
                self.put(STRIKE_POINT, struct.pack("<4i", self.s32(s + 0x18),   # the fourth word
                                                   _s32(self.s32(s + 0x1C) + 0x3E8),   # the stack's,
                                                   self.s32(s + 0x20), 0))             # read by none
                self.strike(STRIKE_POINT, (29 * sc) >> 5, (35 * sc) >> 5, 0x800, 0x400, 0x1000)

    def attack(self, s, hit):               # 0x800537e8
        """What was hit, handed to actor_attack_player from 8 velocities
        back, with 0x1388 and the caster's strength."""
        back = [self.s32(s + o) - (self.s16(s + v) << 3)
                for o, v in ((0x18, 0x38), (0x1C, 0x3A), (0x20, 0x3C))]
        self.hand(s, hit, 0x1388, back)

    def hand(self, s, code, strength, point):   # 0x800536f8
        """actor_attack_player(code, +0, the record, strength, the caster's
        strength, +6, the point -- None for none)."""
        self.w.attack_hit(code, self.u8(s), self.u8(s + 1), strength,
                          self.magic_strength(s), self.u8(s + 6), point)

    def _spawn_5f(self, s, args):           # 0x8005593c, meteor
        """Put down where it is to land -- +0x48 that y -- then moved to a
        point within 0x514 of it each way by two rands, unless
        collide_wrapper_actor finds that point blocked; and from there
        0x9d8 back in x and z and 0x4000 up, falling (0x64, 0x28a, 0x64)."""
        y = self.s32(s + 0x1C)
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0xF)
        self.w8(s + 3, 0xF)
        self.w16(s + 0x10, 0x2D)
        self.w32(s + 0x48, y)
        x = _s32(self.s32(s + 0x18) - 0x514 + ((self.rand() * 2600) >> 15))
        z = _s32(self.s32(s + 0x20) - 0x514 + ((self.rand() * 2600) >> 15))
        if self.w.collide_wrapper(x, y, z, 0xA, 0xA):
            x, z = self.s32(s + 0x18), self.s32(s + 0x20)
        self.w32(s + 0x18, x - 0x9D8)
        self.w16(s + 0x38, 0x64)
        self.w16(s + 0x3C, 0x64)
        self.w32(s + 0x1C, y - 0x4000)
        self.w16(s + 0x3A, 0x28A)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0x1000)
        self.w16(s + 0xE, 0x80)
        self.w32(s + 0x20, z - 0x9D8)       # and its sound, 0x2d

    def _tick_5f(self, s):                  # 0x8005b8f8, meteor
        """Falling, turning 0x100 a frame, asking collide_query for the
        creatures, objects and player within 0xa; meeting none, the floor
        under it at +0x48 (collide_surface): above it, six puffs a frame
        behind it; at or past it, set on it. Then the impact: what it met
        struck (sub_800537e8), a blast (0x5a) with its own +0 -- 0x640 at
        0x64 a frame, scale 0x800 -- four puffs about it, and gone."""
        for o, v in ((0x18, 0x38), (0x1C, 0x3A), (0x20, 0x3C)):
            self.w32(s + o, self.s32(s + o) + self.s16(s + v))
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x100)
        x, z = self.s32(s + 0x18), self.s32(s + 0x20)
        mask = self.w.collide_query(x, self.s32(s + 0x1C), z, 0xA, 0xA, 0xB0)
        if mask == 0:
            surf = self.w.surface(x, self.s32(s + 0x48), z, 0, 0)
            if self.s32(s + 0x1C) < surf:
                vel = self.get(s + 0x38, 8)
                scale = 0xB86
                for k in range(5, -1, -1):
                    v = [(_s16_(struct.unpack_from("<H", vel, 2 * i)[0]) >> 3) * (k + 1)
                         for i in range(3)]
                    self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                               [struct.pack("<3h", *[_s16_(c) for c in v]) + vel[6:8],
                                scale, -0x80, 5, 0x1C, 0, 1, 2], direct=True)
                    scale -= 0x15E
                return
            self.w32(s + 0x1C, surf)
        point = self.get(s + 0x18, 16)
        self.attack(s, mask)
        self.spawn(0xA, self.u8(s), BLAST, point, [struct.pack("<4h", 0, -0x20, 0, 0),
                                                  0x640, 0x64, 0x800], direct=True)
        for _k in range(4):
            px, py, pz, pw = struct.unpack("<4i", self.get(s + 0x18, 16))
            px = _s32(px - 0x1F4 + ((self.rand() * 1000) >> 15))
            pz = _s32(pz - 0x1F4 + ((self.rand() * 1000) >> 15))
            self.spawn(0xA, 0, TRAIL, struct.pack("<4i", px, py, pz, pw),
                       [struct.pack("<4h", 0, -0x168, 0, 0), 0x4000, -0x80, 5, 0x1D, 0, 1, 2], direct=True)
        self.w8(s, 0xFF)

    def _spawn_5a(self, s, args):           # 0x800553a8, meteor's blast
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0x1E)
        self.w8(s + 3, 0x1E)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w16(s + 0x30, 0xA)
        self.w16(s + 0x34, 0xA)
        self.w16(s + 0x44, args[1])         # how far it goes
        self.w16(s + 0x46, args[2])         # how fast
        self.w16(s + 0xE, 0)
        self.w16(s + 0x48, args[3])         # the strike's scale; and its sound, 0x23

    def _tick_5a(self, s):                  # 0x80059a28, meteor's blast
        """Earth wave's ring (0x80057c34) but its two sizes kept apart, and
        turning 0x200 a frame."""
        self.w16(s + 0x30, self.u16(s + 0x30) + self.u16(s + 0x46))
        self.w16(s + 0x34, self.u16(s + 0x34) + self.u16(s + 0x46))
        sc = self.s16(s + 0x30)
        if sc >= 0x300:
            self.put(STRIKE_POINT, struct.pack("<4i", self.s32(s + 0x18),
                                               _s32(self.s32(s + 0x1C) + 0x3E8),
                                               self.s32(s + 0x20), 0))
            self.strike(STRIKE_POINT, (sc - self.s16(s + 0x46)) << 2, (sc << 2) - 1, 0x7D0,
                        0x1000, self.s16(s + 0x48))
        if self.s16(s + 0x44) < self.s16(s + 0x30):
            self.w8(s, 0xFF)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x200)

    def _spawn_07(self, s, args):           # 0x80054ef4, earth wave (and 0x16)
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0xE)
        self.w8(s + 3, 0xE)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w16(s + 0x34, 0)
        self.w16(s + 0x30, 0)
        self.w16(s + 0x44, args[1])         # how far it goes
        self.w16(s + 0x46, args[2])         # how fast
        self.w16(s + 0x48, args[3])         # the strike's scale
        self.w16(s + 0xE, (args[4] & 0xFFFF) << 6)   # and its sound, 0x23

    def _tick_07(self, s):                  # 0x80057c34, earth wave (and 0x16)
        """A ring growing +0x46 a frame; from 0x300 it strikes between four
        times its last size and four times its size less one, 0x3e8 under its
        point, mode 0x7d0, at +0x48 throughout; gone past +0x44."""
        v = self.u16(s + 0x30) + self.u16(s + 0x46)
        self.w16(s + 0x30, v)
        self.w16(s + 0x34, v)
        sc = self.s16(s + 0x30)
        if sc >= 0x300:
            self.put(STRIKE_POINT, struct.pack("<4i", self.s32(s + 0x18),     # the fourth
                                               _s32(self.s32(s + 0x1C) + 0x3E8),  # word the
                                               self.s32(s + 0x20), 0))            # stack's
            self.strike(STRIKE_POINT, (sc - self.s16(s + 0x46)) << 2, (sc << 2) - 1, 0x7D0,
                        0x1000, self.s16(s + 0x48))
        if self.s16(s + 0x44) < self.s16(s + 0x30):
            self.w8(s, 0xFF)

    def _spawn_0c(self, s, args):           # 0x80054a84, bortecth
        self.setup(s, 0x1F, 0xAF0, 5)
        self.w16(s + 0x10, 0x3C)
        self.w16(s + 0x32, 0x1400)
        for o in (0x4A, 0x48, 0x46, 0x44):
            self.w16(s + o, 0)
        self.w16(s + 0xE, 0x80)             # and its sound, 0x95

    def _tick_0c(self, s):                  # 0x80057cd0, bortecth
        """Its first frame asks collide_query for the creatures and objects
        within 0x400 of its point, its height its scale; a creature alone
        (the mask 0x10 exactly) is handed actor_attack_player with code
        0x10010 -- the hit, and +0x28 bit 0x800, the hold -- 0x1388 and no
        point. Then its child 0x65 with the creature's slot (or -1). It
        turns 0x1a4 a frame."""
        if self.s16(s + 0x44) == 0:
            mask = self.w.collide_query(self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20),
                                        0x400, self.s16(s + 0x30), 0x30)
            if mask == 0x10:
                self.hand(s, 0x10010, 0x1388, None)
            self.w16(s + 0x44, self.u16(s + 0x44) + 1)
            self.spawn(0xA, 0, HOLD, self.get(s + 0x18, 16), [None, self.w.collide_actor], direct=True)
            self.w16(s + 0x48, 0)
            self.w16(s + 0x4A, 0)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x1A4)

    def _spawn_65(self, s, args):           # 0x80054ac8, bortecth's hold
        self.setup(s, 0x20, 0x1B58, 5)
        self.w16(s + 0x10, 0x3C)
        for o in (0x4A, 0x48, 0x44):
            self.w16(s + o, 0)
        self.w16(s + 0x32, 0)
        self.w16(s + 0xE, 0x40)
        self.w16(s + 0x46, args[1])         # the creature held, or -1

    def _tick_65(self, s):                  # 0x80057d74, bortecth's hold
        """Rising 0x1b8 a frame for 12 frames; from count 48 sinking again
        and letting the creature go (its +0x28 bit 0x800 cleared); from 12
        to 47 a puff (0x6f) a frame, its velocity three rands. It turns
        -0x190 a frame."""
        n = self.s16(s + 0x44)
        if n < 0xC:
            self.w16(s + 0x32, self.u16(s + 0x32) + 0x1B8)
        if n >= 0x30:
            self.w16(s + 0x32, self.u16(s + 0x32) - 0x1B8)
            c = self.s16(s + 0x46)
            if c != -1:
                self.w.release(c)
        if (self.u16(s + 0x44) - 0xC) & 0xFFFFFFFF < 0x24:
            vx = _div7fff(self.rand() << 9) - 0x100
            vy = _div7fff(-(self.rand() << 8))
            vz = _div7fff(self.rand() << 9) - 0x100
            self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                       [struct.pack("<4h", _s16_(vx), _s16_(vy), _s16_(vz), 0),
                        0x1000, -0x80, 5, 0xC, 0, 1, 0], direct=True)
        self.w16(s + 0x44, self.u16(s + 0x44) + 1)
        self.w16(s + 0x2A, self.u16(s + 0x2A) - 0x190)

    def splash_one(self, point, size, bob, depth):  # 0x80056268
        """One splash (kind 0x70) on the surface the last query found, when
        the point is within `depth` under it."""
        y, surf = self.s32(point + 4), self.s32(SURFACE)
        if y < surf or surf + depth < y:
            return 0
        pt = struct.pack("<3i", self.s32(point), surf, self.s32(point + 8)) + bytes(4)
        self.spawn(0xA, 0, SPLASH, pt, [bytes(8), size, bob])
        return 1

    def _spawn_70(self, s, args):           # 0x800557dc, a splash
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0x2A)
        self.w8(s + 3, 0x2A)
        self.w16(s + 0x32, 0)
        self.w16(s + 0x34, args[1])
        self.w16(s + 0x30, args[1])
        self.w16(s + 0x44, args[2])
        now = self.s32(VBLANK)                # its sound, at most every 30 blanks
        if _s32(self.s32(SPLASH_SOUND) - now) < 0:
            self.w32(SPLASH_SOUND, now + 0x1E)

    def _tick_70(self, s):                  # 0x8005b598, a splash
        """Eight frames rising and falling: its height scale sin(phase << 8)
        times +0x44."""
        ph = (self.u8(s + 7) + 1) & 0xFF
        self.w8(s + 7, ph)
        self.w16(s + 0x32, _s32(movement.game_sin(ph << 8) * self.s16(s + 0x44)) >> 12)
        if ph >= 8:
            self.w8(s, 0xFF)

    def _spawn_00(self, s, args):           # 0x80053e98, the fire ball
        self.particle(s, 9, 0x1000, 5)
        self.w16(s + 0xE, 0x40)
        self.w16(s + 0x10, 0x32)            # sub_800532d4's sound between
        self.w8(s + 0xD, 1)

    def _spawn_3e(self, s, args):           # 0x80053e8c, anorium sword's
        """The fire ball's arm with particle 0x3b."""
        self.particle(s, 0x3B, 0x1000, 5)
        self.w16(s + 0xE, 0x40)
        self.w16(s + 0x10, 0x32)            # sub_800532d4's sound between
        self.w8(s + 0xD, 1)

    def _spawn_3a(self, s, args):           # 0x800543b4, capricorn's
        self.particle(s, 0xA, 0xC00, 5)
        self.w16(s + 0x10, 0x32)
        self.w8(s + 0xD, 1)
        self.w16(s + 0xE, 0x40)             # with its sound (0x64)

    def _tick_3a(self, s):                  # 0x80057f78, capricorn's
        """+0xe flips 0x40 every frame; effect_move at radius 0xb4, no
        height, turning 0x258 a frame; what it meets it strikes and is gone
        (freed first when the tiles stopped it)."""
        self.w16(s + 0xE, (self.u16(s + 0xE) + 0x40) & 0x40)
        hit = self.move(0xB4, 0, -0x258)
        if not hit:
            return
        if hit & 0xF:
            self.w8(s, 0xFF)
        self.attack(s, hit)
        self.w8(s, 0xFF)

    def _spawn_42(self, s, args):           # 0x80054940, Seath's sword's
        """After its sound (0x62 when +0 & 0x40, else 0x2c): set up as model
        0x2d, scale 0x1000 and +0x34 0x1400, the life 0x32, and the angles
        off the velocity as _aimed has them."""
        self.setup(s, 0x2D, 0x1000, 5)
        vx, vz = self.s16(s + 0x38), self.s16(s + 0x3C)
        self.w16(s + 0x34, 0x1400)
        self.w16(s + 0x10, 0x32)
        self.w8(s + 0x44, 0)
        self.w8(s + 0xD, 1)
        ln = vec_length_2d(vx, vz)
        self.w16(s + 0x28, movement.ratan2(self.s16(s + 0x3A), ln))
        self.w16(s + 0x2C, 0)
        self.w16(s + 0x2A, movement.ratan2(self.s16(s + 0x3C), self.s16(s + 0x38)) - 0x400)
        self.w16(s + 0xE, 0x40)

    def _tick_42(self, s):                  # 0x80058a00, Seath's sword's
        """effect_move at radius 0x64, height 0xc8; in flight a splash on
        water just under it (sub_80056268), and what it meets it strikes and
        is gone."""
        hit = self.move(0x64, 0xC8, 0)
        if not hit:
            self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
            return
        self.attack(s, hit)
        self.w8(s, 0xFF)

    def _spawn_4c(self, s, args):           # 0x8005422c, morguline axe's
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0xF)
        self.w8(s + 3, 0xF)
        self.w16(s + 0x10, 0x50)
        self.w16(s + 0xE, 0x80)             # with its sound (0x36)

    def _tick_4c(self, s):                  # 0x8005758c, morguline axe's
        """Turning 0xc8 a frame on two axes, falling by 5 a frame more, a
        still puff at its point (0xc00, -0x100, 8, 0x1c, 0, 1, 2), then
        effect_move at radius 0xb4, the height's top bit: what it meets it
        strikes and is gone."""
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0xC8)
        self.w16(s + 0x3A, self.u16(s + 0x3A) + 5)
        self.w16(s + 0x28, self.u16(s + 0x28) + 0xC8)
        self.spawn(10, 0, TRAIL, self.get(s + 0x18, 16),
                   [bytes(8), 0xC00, -0x100, 8, 0x1C, 0, 1, 2], direct=True)
        hit = self.move(0xB4, 0x80000000, 0)
        if hit:
            self.w8(s, 0xFF)
            self.attack(s, hit)

    def _spawn_40(self, s, args):           # 0x8005474c, vaculacia sword's
        self.particle(s, 0x43, 0x1400, 5)
        self.w16(s + 0x10, 0x46)
        self.w8(s + 0x44, 0)
        self.w8(s + 0xD, 0)
        self.w16(s + 0xE, 0)                # with its sound (0x67)

    def _tick_40(self, s):                  # 0x8005763c, vaculacia sword's
        """effect_move at radius 0xb4, the height's top bit, turning 0x1f4 a
        frame; what it meets it strikes and is gone in sixteen puffs flung
        from its point, each axis rand() * 500 >> 15 less 0xfa (0x1400,
        -0x18, 0xa, 0x26, 0, 1, 2)."""
        hit = self.move(0xB4, 0x80000000, -0x1F4)
        if not hit:
            return
        self.w8(s, 0xFF)
        self.attack(s, hit)
        for _ in range(16):
            v = [((500 * self.rand()) >> 15) - 0xFA for _ in range(3)]
            self.spawn(10, 0, TRAIL, self.get(s + 0x18, 16),
                       [struct.pack("<4h", *v, 0), 0x1400, -0x18, 0xA, 0x26, 0, 1, 2], direct=True)

    def face(self, s):
        """+0x28 the pitch and +0x2a the yaw of the velocity, the yaw a
        quarter back -- ratan2(vy, vec_length_2d(vx, vz)), ratan2(vz, vx) -
        0x400 -- as the creatures' bolts are aimed."""
        vx, vy, vz = self.s16(s + 0x38), self.s16(s + 0x3A), self.s16(s + 0x3C)
        self.w16(s + 0x28, movement.ratan2(vy, vec_length_2d(vx, vz)))
        self.w16(s + 0x2A, movement.ratan2(vz, vx) - 0x400)

    def _spawn_36(self, s, args):           # 0x80054538, the excellector's first
        """Model 0x3d, its size by its place in the cast (args[1], 3 down to
        0): 0x1800 across and 0xc00 high, 0x400 more each; the view's angles."""
        self.setup(s, 0x3D, 0x1000, 5)
        n = _s32(args[1])
        self.w16(s + 0x30, (n << 10) + 0x1800)
        self.w16(s + 0x34, (n << 10) + 0x1800)
        self.w16(s + 0x10, 0x28)
        self.w8(s + 0x44, 0)
        self.w8(s + 0xD, 0)
        self.w16(s + 0x32, (n << 10) + 0xC00)
        self.put(s + 0x28, self.get(VIEW_ANGLES, 8))
        self.w16(s + 0xE, 0x40)

    def _spawn_37(self, s, args):           # 0x800545c4, the excellector's second
        self.setup(s, 0x39, 0x1B58, 5)
        self.w16(s + 0x10, 0x30)
        self.w8(s + 0x44, 0)
        self.w8(s + 0xD, 0)
        self.w16(s + 0xE, 0x40)
        self.face(s)
        self.w16(s + 0x2C, 0)               # and its sound, 0x63

    def _tick_36(self, s):                  # 0x80057aa8, both of the excellector's (and 0x31)
        """effect_move at radius 0xb4, the height's top bit; the tiles end
        it. Each thing it meets it strikes once (+0x44 the latch, cleared on a
        clear frame), in seven puffs flung from its point, each axis rand() *
        240 >> 15 less 0x78 (0x1400, 0, 7, 0xc, 0, 1, 1). A splash a frame
        on water just under it."""
        hit = self.move(0xB4, 0x80000000, 0)
        if not hit:
            self.w8(s + 0x44, 0)
        else:
            if hit & 0xF:
                self.w8(s, 0xFF)
            if self.u8(s + 0x44) == 0:
                self.w8(s + 0x44, 1)
                self.attack(s, hit)
                for _k in range(7):
                    v = [((240 * self.rand()) >> 15) - 0x78 for _i in range(3)]
                    struct.pack_into("<3h", self.m, (TICK_SP + 0xA0) & MASK, *v)
                    self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                               [self.get(TICK_SP + 0xA0, 8), 0x1400, 0, 7, 0xC, 0, 1, 1],
                               direct=True)
        self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)

    def _spawn_3c(self, s, args):           # 0x8005477c, 0x3c (no weapon's)
        """Model 0x1e, 0x64 across and 0x800 high, falling from 0xc8 above
        the point at 0x1e a frame up, five frames' grace."""
        self.setup(s, 0x1E, 0x64, 0)
        self.w16(s + 0x32, 0x800)
        self.w16(s + 0x30, 0x64)
        self.w16(s + 0x34, 0x64)
        self.w16(s + 0x10, 0x2D)
        self.put(s + 0x28, self.get(VIEW_ANGLES, 8))
        self.w16(s + 0x3A, -0x1E)
        self.w16(s + 0x28, 0)
        self.w16(s + 0x2C, 0)
        self.w8(s + 0xB, 5)
        self.w16(s + 0xE, 0)
        self.w16(s + 0x44, 0)
        self.w32(s + 0x1C, self.s32(s + 0x1C) - 0xC8)

    def _tick_3c(self, s):                  # 0x80057ba8, 0x3c
        """Falling 5 a frame faster until effect_move (0xb4, the height's top
        bit) meets something; then spreading 0x100 a frame across, gone past
        0x1000. It strikes nothing."""
        n = self.s16(s + 0x44)
        if n == 0:
            if self.move(0xB4, 0x80000000, 0):
                self.w16(s + 0x44, self.u16(s + 0x44) + 1)
            self.w16(s + 0x3A, self.u16(s + 0x3A) + 5)
        elif n == 1:
            self.w16(s + 0x30, self.u16(s + 0x30) + 0x100)
            self.w16(s + 0x34, self.u16(s + 0x34) + 0x100)
            if self.s16(s + 0x30) >= 0x1001:
                self.w8(s, 0xFF)

    def _spawn_46(self, s, args):           # 0x80054690, triple fang's first
        """Model 0x3f, 0x800 across and 0xc00 long, the view's angles, three
        frames' grace; +0x46 args[1] -- 0 for the cast, 1 for the two it
        splits into."""
        self.setup(s, 0x3F, 0x800, 5)
        self.w16(s + 0x34, 0xC00)
        self.w16(s + 0x10, 0x3C)
        self.w8(s + 0xD, 1)
        self.w8(s + 0xB, 3)
        self.put(s + 0x28, self.get(VIEW_ANGLES, 8))
        self.w16(s + 0x44, 0)
        self.w16(s + 0xE, 0x100)
        self.w16(s + 0x46, args[1])         # and its sound, 0x2d

    def _tick_46(self, s):                  # 0x8005773c, triple fang's first
        """Rolling 0x190 a frame, aimed along its velocity. At a life of 0x2d
        -- fifteen frames out -- the cast's (+0x46 0) splits: two more (+0x46
        1) at its point, the
        velocity turned an eighth either way -- ((2vx - vz) >> 1, vy, (vx +
        2vz) >> 1) and ((2vx + vz) >> 1, vy, (2vz - vx) >> 1). Then
        effect_move (0xb4, the height's top bit): what it meets it strikes,
        and it becomes a burst (0x58, 0x28 frames from nothing) with another
        beside it (+0 3, 0x80 across, the player struck too); else a puff
        behind it (0x1000, -0x280, 5, 0xc, 0, 1, 0)."""
        self.w16(s + 0x2C, self.u16(s + 0x2C) + 0x190)
        self.face(s)
        if self.s16(s + 0x10) == 0x2D and self.s16(s + 0x46) == 0:
            vx, vy, vz = self.s16(s + 0x38), self.s16(s + 0x3A), self.s16(s + 0x3C)
            for x, z in (((vx - vz + vx) >> 1, (vx + vz + vz) >> 1),
                         ((vz + vx + vx) >> 1, (vz - vx + vz) >> 1)):
                struct.pack_into("<3h", self.m, (TICK_SP + 0xD8) & MASK, _s16_(x), vy, _s16_(z))
                self.spawn(0xA, 0x43, FANG, self.get(s + 0x18, 16),
                           [self.get(TICK_SP + 0xD8, 8), 1], direct=True)
        hit = self.move(0xB4, 0x80000000, 0)
        if hit:
            self.attack(s, hit)
            self.w8(s + 1, BURST)
            self.w8(s + 8, 1)
            self.w8(s + 9, 5)
            self.w8(s + 2, 0x15)
            self.w8(s + 3, 0x15)
            self.w8(s + 0xC, 0x34)
            self.w16(s + 0x12, 0x1000)
            self.w16(s + 0x10, 0x28)
            self.w8(s + 4, 0)
            for o in (0x30, 0x32, 0x34, 0x28, 0x2A, 0x2C):
                self.w16(s + o, 0)
            self.w16(s + 0xE, 0x40)             # and the sound, 0x28
            self.spawn(0xA, 3, BURST, self.get(s + 0x18, 16), [None, 0x80, 1], direct=True)
            return
        v = [((20 * self.rand()) >> 15) - 0xA for _i in range(3)]
        struct.pack_into("<3h", self.m, (TICK_SP + 0xD8) & MASK, *v)
        self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                   [self.get(TICK_SP + 0xD8, 8), 0x1000, -0x280, 5, 0xC, 0, 1, 0], direct=True)

    def _spawn_47(self, s, args):           # 0x80055424, flash (0x14), triple fang's second (0x47); 0x12 at 0x80055414
        """Model 0x23, mode 0x39, the angles args[1] points at; the homing's
        four numbers out of args[2..5] -- the most, the pull, the turn, the
        pull up close -- and the life out of args[6]. 0x12: three frames'
        grace and +0xe 0x140."""
        if self.u8(s + 1) == 0x12:
            self.w8(s + 0xB, 3)
            self.w16(s + 0xE, 0x140)
        else:
            self.w16(s + 0xE, 0x100)
        self.w8(s + 8, 1)
        self.w8(s + 9, 5)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0x23)
        self.w8(s + 3, 0x23)
        self.w8(s + 0xC, 0x39)
        self.w16(s + 0x12, 0x1000)
        self.put(s + 0x28, args[1][:8])
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0x1000)
        for i, o in enumerate((0x44, 0x46, 0x48, 0x4A, 0x10)):
            self.w16(s + o, args[2 + i])

    def _tick_47(self, s):                  # 0x80059ba8, flash, triple fang's second, 0x12
        """Phase +7. Under 0x64 it homes (seek: the most +0x44, the pull
        +0x46, the turn +0x48, radius 0xa0, no height, the pull +0x4a within
        0x1770, cones 0x800), counting +7 up -- in flight a splash on water
        under it, rolling 0x80 a frame and a still puff (0xe10, -0x80, 3,
        0x25, 0, 1, and 0 for 0x12, 1 for the others). Meeting something, or
        at 0x64, another of its kind where it is -- +0 | 3, handed its angles
        and the stack's last five words for the rest, +7 0x65, so it bursts
        two frames on -- and it bursts: model 0x15, +7 0x6e, +0 | 3 (the
        player struck too), growing from nothing 0x46 a frame, striking a
        shell twice it (effect_grow 0x2000, 0x31f, 0xc00, 0x8000), turning
        0x40 a frame."""
        kind = self.u8(s + 1)
        ph = self.u8(s + 7)
        if ph == 0x65:
            self.w8(s + 7, 0x66)
            return
        if ph == 0x6E:
            self._flash_grow(s, kind)
            return
        if ph != 0x66:
            if ph != 0x64:
                if ph == 0:                     # its sound, 0x2c: sub_80015688's two words
                    self.out_words([0x7148, 0])
                self.w8(s + 7, ph + 1)
                r = self.seek(self.s16(s + 0x44), self.s16(s + 0x46), self.s16(s + 0x48), 0xA0, 0,
                              0x1770, self.s16(s + 0x4A), 0x800)
                if r != -1:
                    self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
                    self.w16(s + 0x2C, self.u16(s + 0x2C) + 0x80)
                    struct.pack_into("<3h", self.m, (TICK_SP + 0x170) & MASK, 0, 0, 0)
                    self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                               [self.get(TICK_SP + 0x170, 8), 0xE10, -0x80, 3, 0x25, 0, 1,
                                0 if kind == 0x12 else 1], direct=True)
                    return
            rest = [self.u32(TICK_SP + 0x18 + 4 * i) for i in range(5)]
            c = self.spawn(0xA, self.u8(s) | 3, kind, self.get(s + 0x18, 16),
                           [None, self.get(s + 0x28, 8)] + rest, direct=True)
            self.w8(c + 7, 0x65)                # at address 7 when no slot was free
        self.w8(s + 3, 0x15)
        self.w8(s + 7, 0x6E)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0)
        self.w16(s + 0xE, 0x40)
        self.w8(s, self.u8(s) | 3)              # and the sound, 0x28
        self._flash_grow(s, kind)

    def _flash_grow(self, s, kind):         # 0x80059be0
        if kind == 0x12:
            self.w16(s + 0xE, 0)
        self.out_words([0x8000])
        self.grow(0x2000, 0x31F, 0x46, 0xC00, 0x8000)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x40)

    def seek(self, most, accel, turn, radius, height, near, near_accel, cone):  # 0x80055db0, effect_seek
        """effect_seek: a player's effect (+0 & 0x40) turns its angles
        towards the creature sub_8004d3c4 finds along them (0x5dc0, the cones,
        no noise) -- its middle -- by `turn` each (angle_approach), and is
        steered along them (effect_steer: `accel`, `near_accel` once the
        creature is within `near`; at most `most`). -1 when the move met
        something. The other effects look for the player (sub_8002b80c), not
        read."""
        s = self.u32(CURRENT)
        self.out_words([height, near, near_accel, cone])
        if not self.u8(s) & 0x40:
            raise NotImplementedError("sub_80055db0's other half, sub_8002b80c")
        import chests
        point = (self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20))
        a, dist = self.w.sight(point, self.s16(s + 0x2A), self.s16(s + 0x28), 0x5DC0, cone, cone,
                               0, self.rand)
        if a:
            t = self.w.actor_mid((a - ACTORS) // ACTOR_STRIDE)
            ang = vec_to_angles(_s32(t[0] - point[0]), _s32(t[1] - point[1]), _s32(t[2] - point[2]))
            turn = _s16_(turn)
            self.w16(s + 0x28, chests.approach_angle(self.s16(s + 0x28), _s16_(ang[0]), turn))
            self.w16(s + 0x2A, chests.approach_angle(self.s16(s + 0x2A), _s16_(ang[1]), turn))
        d = movement.direction_from_angles(self.s16(s + 0x28), self.s16(s + 0x2A))
        if dist >= 0 and not near < dist:
            accel = near_accel
        return self.steer(accel, most, radius, height, [_s16_(c) for c in d])

    def _spawn_4b(self, s, args):           # 0x80054188, the second moonlight sword's second
        self.setup(s, 0x44, 0x1400, 5)
        self.put(s + 0x28, self.get(VIEW_ANGLES, 8))
        self.w8(s + 0xD, 1)
        self.w16(s + 0x10, 0x64)
        self.w8(s + 0xB, 5)
        self.w8(s + 0x44, 0)
        self.w16(s + 0xE, 0)                # and its sound, 0x66

    def _tick_4b(self, s):                  # 0x80056c7c
        """Aimed along its velocity, rolling 0xc8 a frame; effect_move at
        0xb4, no height. Meeting something: a creature or an object (no
        tile bit) struck; gone in three bursts (0x58, +0 3, 0, 0x40 and 0x80
        across, +0xe 0x80). Every frame a splash on water under it, and on
        every third of its life a spark (3) where it is."""
        self.face(s)
        self.w16(s + 0x2C, self.u16(s + 0x2C) + 0xC8)
        hit = self.move(0xB4, 0, 0)
        if hit:
            if not hit & 0xF:
                self.attack(s, hit)
            self.w8(s, 0xFF)                    # and the sound, 0x27
            for size in (0, 0x40, 0x80):
                self.spawn(0xA, 3, BURST, self.get(s + 0x18, 16), [None, size, 2], direct=True)
        self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
        struct.pack_into("<3h", self.m, (TICK_SP + 0x68) & MASK, 0, 0, 0)
        life = self.s16(s + 0x10)
        if (life - 3 * int(life / 3)) & 0xFFFF == 0:
            self.spawn(0xA, 0, SPARK, self.get(s + 0x18, 16), [self.get(TICK_SP + 0x68, 8)],
                       direct=True)

    def _spawn_03(self, s, args):           # 0x8005415c, a spark
        self.particle(s, 0x45, 0x1000, 5)
        self.w16(s + 0x10, 0xC)
        self.w16(s + 0x32, 0)
        self.w16(s + 0xE, 0x40)

    def _tick_03(self, s):                  # 0x8005699c, a spark
        """0x4b0 taller a frame, flickering: +4 0x80 or 0x81 and +0xe 0 or
        0x40 by its life's last bit (the remainder's sign kept)."""
        self.w16(s + 0x32, self.u16(s + 0x32) + 0x4B0)
        life = self.s16(s + 0x10)
        self.w8(s + 4, (self.u8(s + 0x10) & 1) - 0x80)
        self.w16(s + 0xE, (life - 2 * int(life / 2)) << 6)

    def _spawn_78(self, s, args):           # 0x80055524, a moonlight sword's mark (0x78, 0x7a)
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 9, 5)
        self.w8(s + 2, 0x3A)
        self.w8(s + 3, 0x3A)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w16(s + 0x10, 0x2D)
        self.put(s + 0x28, args[1][:8])
        self.w16(s + 0x30, 0x1800)
        self.w16(s + 0x32, 0xA00)
        self.w16(s + 0x34, 0xC00)
        self.w16(s + 0xE, 0)                # and its sound, 0x66

    def _moon_burst(self, s):
        """Three bursts (0x48) where it is, +0 | 3, a frame apart; gone."""
        for i in range(3):
            self.spawn(0xA, self.u8(s) | 3, MOON_BURST, self.get(s + 0x18, 16), [None, i],
                       direct=True)
        self.w8(s, 0xFF)                        # with the sound, 0x27

    def _tick_78(self, s):                  # 0x8005857c, the first moonlight sword's mark
        """effect_move at 0xb4, 0x168 high; meeting something, or with a
        frame left, three bursts; else a splash on water under it."""
        if self.move(0xB4, 0x168, 0) or self.s16(s + 0x10) < 2:
            self._moon_burst(s)
            return
        self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)

    def _tick_7a(self, s):                  # 0x800584a4, the second moonlight sword's mark
        """Homing (seek: 0x258 at most, pulled 0x28 -- 0x104 within 0x1000
        -- turning 0x24, radius 0xb4, 0x168 high, cones 0x800); meeting
        something, or with a frame left, the move taken back and three
        bursts; else a splash on water under it."""
        r = self.seek(0x258, 0x28, 0x24, 0xB4, 0x168, 0x1000, 0x104, 0x800)
        if r == -1 or self.s16(s + 0x10) < 2:
            self.undo(s)
            self._moon_burst(s)
            return
        self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)

    def _spawn_5c(self, s, args):           # 0x800555b4 (0x5c), 0x800555e8 (0x5d): a mark's pillar
        """Particle 0xb, 0x1800 across and nothing high, flat; +0x45 the
        mark's slot (args[1]); +0xe 0x40 for 0x5c, 0 for 0x5d."""
        self.particle(s, 0xB, 0x1800, 5)
        self.w16(s + 0x32, 0)
        self.w8(s + 0x44, 0)
        self.w16(s + 0x3A, 0)
        self.w16(s + 0xE, 0x40 if self.u8(s + 1) == PILLAR else 0)
        self.w8(s + 0x45, args[1])

    def _tick_5c(self, s):                  # 0x80058624, a mark's pillar
        """Following on the ground under its mark: across by its velocity;
        while the mark lives (+0x44 0) striking what stands in it (no
        tiles, radius 0xa, its height), set on the floor under the mark's
        height (collide_surface) and half as high as the room there, 0x4000
        at most; once the mark is gone (+0x44 1) shrinking from that height
        to nothing in eight frames (fixed_madd by 0x200 a frame), then gone."""
        import ai
        self.w32(s + 0x18, self.s32(s + 0x18) + self.s16(s + 0x38))
        self.w32(s + 0x20, self.s32(s + 0x20) + self.s16(s + 0x3C))
        k = self.u8(s + 0x45)
        parent = SLOTS + STRIDE * (k - 0x100 if k >= 0x80 else k)
        ph = self.u8(s + 0x44)
        if ph == 0:
            x, y, z = self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20)
            self.out_words([self.s16(s + 0x32), 0x30])
            mask = self.w.collide_query(x, y, z, 0xA, self.s16(s + 0x32), 0x30)
            self.attack(s, mask)
            self.out_words([0])
            surf, ceil = self.w.surface_ceiling(x, self.s32(parent + 0x1C), z, 0, 0)
            self.w32(s + 0x1C, surf)
            d = _s32(surf - ceil)
            self.w16(s + 0x32, 0x4000 if 0x7FFF < d else d >> 1)
            if self.u8(parent) == 0xFF:
                self.w8(s + 0x44, 1)
                self.w16(s + 0x46, 0)
                self.w16(s + 0x36, self.u16(s + 0x32))
        elif ph == 1:
            self.w16(s + 0x32, ai.lerp(self.s16(s + 0x36), 0, self.s16(s + 0x46)))
            self.w16(s + 0x46, self.u16(s + 0x46) + 0x200)
            if self.s16(s + 0x46) >= 0x1000:
                self.w8(s, 0xFF)

    def _spawn_48(self, s, args):           # 0x800554d0, a mark's burst
        """Model 0x15 from nothing; +0x44 args[1], the frames it waits."""
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 9, 5)
        self.w8(s + 2, 0x15)
        self.w8(s + 3, 0x15)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0)
        self.w16(s + 0xE, 0x40)
        self.w8(s + 0x44, args[1])

    def _tick_48(self, s):                  # 0x80058464, a mark's burst
        """Waiting +0x44 frames, then growing 0x46 a frame to 0x1f8,
        striking a shell 3.5 times it (effect_grow 0x3800, 0x800, 0x8000)."""
        n = self.u8(s + 0x44)
        if n:
            self.w8(s + 0x44, n - 1)
            return
        self.out_words([0x8000])
        self.grow(0x3800, 0x1F8, 0x46, 0x800, 0x8000)

    def _spawn_44(self, s, args):           # 0x80055618, dark slayer's spheres (0x44, 0x45)
        """Model 0x15 from nothing, growing to args[1]."""
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 9, 5)
        self.w8(s + 2, 0x15)
        self.w8(s + 3, 0x15)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0)
        self.w16(s + 0xE, 0xC0)
        self.w16(s + 0x44, args[1])

    def _tick_44(self, s):                  # 0x8005876c, dark slayer's spheres
        self.out_words([0x8000])
        self.grow(0x4000, self.s16(s + 0x44), 0x46, 0x800, 0x8000)

    def _spawn_7c(self, s, args):           # 0x8005566c, dark slayer's second
        """Model 0x20, 0x15e across and 0x2000 high, flat, its yaw the
        view's, 0x960 under the point, a life of 0x32."""
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 9, 5)
        self.w8(s + 2, 0x20)
        self.w8(s + 3, 0x20)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w16(s + 0x10, 0x32)
        self.put(s + 0x28, self.get(VIEW_ANGLES, 8))
        self.w16(s + 0x32, 0x2000)
        self.w16(s + 0x30, 0x15E)
        self.w16(s + 0x34, 0x15E)
        self.w16(s + 0x28, 0)
        self.w16(s + 0x2C, 0)
        self.w16(s + 0x3A, 0)
        self.w16(s + 0xE, 0x40)
        self.w32(s + 0x1C, self.s32(s + 0x1C) + 0x960)   # and its sound, 0x65

    def _tick_7c(self, s):                  # 0x80058898, dark slayer's second
        """Turning 0x190 a frame, on by its velocity through anything. A
        column 0x2710 high about its point, 0x1388 under it: the first
        creature standing in it (actor_spot_taken, 0x64) gets a sphere
        (0x44, growing to 0x4ec) where it stands; with none, the player
        alone in it (collide_query 0xb0 answering 0x80) gets one at the
        feet. Every frame it does. A splash on water within 0x2710 under
        the column's foot."""
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x190)
        for o, v in ((0x1C, 0x3A), (0x18, 0x38), (0x20, 0x3C)):
            self.w32(s + o, self.s32(s + o) + self.s16(s + v))
        x, y, z = self.s32(s + 0x18), _s32(self.s32(s + 0x1C) + 0x1388), self.s32(s + 0x20)
        self.put(TICK_SP + 0x30, struct.pack("<3i", x, y, z))
        self.out_words([0x2710])
        a = self.w.spot_taken(x, y, z, 0x64, 0x2710)
        if a != -1:                             # the sound, 0x27
            self.spawn(0xA, self.u8(s), SPHERE2, self.w.actor_point(a), [None, 0x4EC], direct=True)
        else:
            self.out_words([0x2710, 0xB0])
            self.w.collide_query(x, y, z, 0x64, 0x2710, 0xB0)
            if self.w.collide_mask == 0x80:     # the sound, 0x27
                self.spawn(self.u8(s + 6), self.u8(s), SPHERE2, self.w.player_point(),
                           [None, 0x4EC], direct=True)
        self.splash_one(TICK_SP + 0x30, 0x2000, 0x7FFF, 0x2710)

    def _spawn_7b(self, s, args):           # 0x80055718, dark slayer's first
        self.w8(s + 8, 0)
        self.w16(s + 0x10, 0x14)            # and its sound, 0x65

    def _tick_7b(self, s):                  # 0x80058790, dark slayer's first
        """Not drawn: on by its velocity, the tiles asked half a step back
        and where it is (collide_wrapper_actor, 5, 0xa) -- either met, it is
        freed -- and a sphere (0x45, growing to 0x1a4) where it is every
        frame regardless, +0 its own (0xff once freed, so the sphere's slot
        stays free)."""
        half = [_s32(self.s32(s + 0x18 + 4 * i) + (self.s16(s + 0x38 + 2 * i) >> 1))
                for i in range(3)]
        for i in range(3):
            self.w32(s + 0x18 + 4 * i, self.s32(s + 0x18 + 4 * i) + self.s16(s + 0x38 + 2 * i))
        self.out_words([0xA])
        if self.w.collide_wrapper(*half, 5, 0xA):
            self.w8(s, 0xFF)
        elif self.w.collide_wrapper(self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20),
                                    5, 0xA):
            self.w8(s, 0xFF)
        f = self.u8(s)
        self.spawn(0xA if f & 0x40 else self.u8(s + 6), f, SPHERE, self.get(s + 0x18, 16),
                   [None, 0x1A4], direct=True)

    def _spawn_71(self, s, args):           # 0x80055290 (0x71), 0x80055258 (0x7d), 0x80055274 (0x81): lightning
        """Particle 0xa -- 0x800 across for the player's 0x71, 0x1000 for
        the creatures' 0x7d and 0x81 -- +0xe 0x40, 0 and 0xc0; a life of
        0x64 and +0x44 the frames it flies level, args[1]."""
        kind = self.u8(s + 1)
        self.particle(s, 0xA, 0x800 if kind == LIGHTNING else 0x1000, 5)
        self.w16(s + 0xE, {LIGHTNING: 0x40, 0x7D: 0, 0x81: 0xC0}[kind])
        self.w16(s + 0x10, 0x64)
        self.w16(s + 0x44, args[1])         # and its sound, 0x2e

    def _tick_71(self, s):                  # 0x8005917c, lightning (and 0x7d, 0x81)
        """+7 0: level, effect_move at 0x32 (the height's top bit, turning
        0x12c a frame), counting +0x44 down; the tiles stop it (the move
        taken back, the level speed zeroed) and it falls, +7 1. 1: falling
        0x46 a frame faster, the level speed to 0xbb8/0x1000 each frame;
        with the floor under it -- the nearer of the surface and the water
        the last query found -- 0x1b58 or more below, over a drop, or once
        the tiles stop it (the move taken back, collide_surface asked), it
        strikes: +7 2, a bolt
        (0x72, 0x7e, 0x81's 0x80; +0 | 3) standing on the floor as high as it
        fell, and an earth wave (0x16) there, half that far at a sixteenth a
        frame; their velocity the last puff's. 2: shrinking 0x80 a frame,
        gone at nothing. While 0 or 1, four puffs a frame where it is."""
        kind = self.u8(s + 1)
        ph = self.u8(s + 7)
        if ph == 2:
            v = (self.u16(s + 0x30) - 0x80) & 0xFFFF
            self.w16(s + 0x30, v)
            self.w16(s + 0x32, v)
            if _s16_(v) <= 0:
                self.w8(s, 0xFF)
            return
        hit = self.move(0x32, 0x80000000, -0x12C)
        drop = None
        if hit:
            if hit & 0xF:
                self.undo(s)
                if ph == 0:
                    self.w16(s + 0x3C, 0)
                    self.w16(s + 0x38, 0)
                else:
                    self.out_words([0])
                    self.w.surface(self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20),
                                   0x32, 0)
                    drop = self._floor_under(s)
            if drop is None:
                self.w8(s + 7, 1)
        if drop is None:
            if ph == 1:
                self.w16(s + 0x3A, self.u16(s + 0x3A) - 0x46)
                import ai
                self.w16(s + 0x38, ai.lerp(0, self.s16(s + 0x38), 0xBB8))
                self.w16(s + 0x3C, ai.lerp(0, self.s16(s + 0x3C), 0xBB8))
                drop = self._floor_under(s)
                if drop < 0x1B58:
                    drop = None
            elif ph == 0:
                c = self.u16(s + 0x44)
                self.w16(s + 0x44, c - 1)
                if _s16_(c) <= 0:
                    self.w8(s + 7, 1)
        if drop is not None:
            self.w8(s + 7, 2)
            floor = _s32(drop + self.s32(s + 0x1C))
            point = struct.pack("<3i", self.s32(s + 0x18), floor, self.s32(s + 0x20)) + \
                self.get(TICK_SP + 0x15C, 4)
            self.put(TICK_SP + 0x150, point)
            vel = self.get(TICK_SP + 0x160, 8)
            bolt, last = {LIGHTNING: (0x72, 1), 0x7D: (0x7E, 3), 0x81: (0x80, 0)}[kind]
            self.spawn(0xA, self.u8(s) | 3, bolt, point, [vel, drop], direct=True)
            self.spawn(0xA, self.u8(s), 0x16, point, [vel, drop >> 1, drop >> 4, 0x800, last],
                       direct=True)                 # and the sound, 0x27
        for _k in range(4):
            v = [(self.rand() >> 7) - 0x80 for _i in range(3)]
            struct.pack_into("<3h", self.m, (TICK_SP + 0x160) & MASK, *v)
            self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                       [self.get(TICK_SP + 0x160, 8), 0x800, -0x80, 5, 0xC, 0, 1, 1], direct=True)

    def _floor_under(self, s):
        """The nearer (higher) of collision_surface and surface_plane_18, as
        the last query left them, less the point's height (0x80059210)."""
        surf, water = self.s32(0x801E6474), self.s32(SURFACE)
        f = surf if surf < water else water
        self.w32(TICK_SP + 0x154, f)
        return _s32(f - self.s32(s + 0x1C))

    def _spawn_72(self, s, args):           # 0x800552d0, a lightning's bolt (0x72, 0x7e, 0x80)
        """Particle 0xb, 0x1000; as high as args[1]; twelve frames."""
        self.particle(s, 0xB, 0x1000, 5)
        self.w16(s + 0xE, 0x40)
        self.w16(s + 0x10, 0xC)
        self.w16(s + 0x32, args[1])

    def _tick_72(self, s):                  # 0x80059518, a lightning's bolt
        """Its first three frames (+7 0..2) a sphere (0x72's 0x13, 0x7e's
        0x29, 0x80's 0x2d; +0 | 3) where it stands, as large as the cube of
        its height under two roots, an eighth (SquareRoot12 twice); its
        velocity the stack's. Flickering (+4 0x80 and 0x81) and, while +7
        is under 9, a flash of light (0xc8, 0xb4, 0xa0) out to 0x7d00 when
        the player is nearer than that -- (sin(+7 << 8) / 2 + 0x400) times
        how much nearer, over 0x7d00. +7 counts."""
        kind = self.u8(s + 1)
        ph = self.u8(s + 7)
        if ph < 3:
            h = self.s16(s + 0x32)
            a = _s32(h * (_s32(h * h) >> 12))
            r = movement.sqrt12(movement.sqrt12(a)) >> 3
            child = {0x72: 0x13, 0x7E: 0x29, 0x80: 0x2D}[kind]
            self.spawn(0xA, self.u8(s) | 3, child, self.get(s + 0x18, 16),
                       [self.get(TICK_SP + 0x168, 8), r], direct=True)
        self.w8(s + 4, (ph & 1) - 0x80)
        if self.u8(s + 7) < 9:
            px, py, pz = struct.unpack_from("<3i", self.m, PLAYER_POS & MASK)
            d = vec_length_3d(_s32(px - self.s32(s + 0x18)), _s32(py - self.s32(s + 0x1C)),
                              _s32(pz - self.s32(s + 0x20)))
            if d < 0x7D01:
                v = _s32(((movement.game_sin(self.u8(s + 7) << 8) >> 1) + 0x400) * (0x7D00 - d))
                k = int(v / 0x7D00)
                self.out_words([0x7D00, _s16_(k)])
                self.lighting((0xC8, 0xB4, 0xA0), 0, 0x7D00, _s16_(k))
        self.w8(s + 7, self.u8(s + 7) + 1)

    def _spawn_13(self, s, args):           # 0x80055328 (0x13), 0x80055300 (0x29), 0x80055314 (0x2d)
        """Model 0x15 from nothing, growing to a quarter of args[1]; +0xe
        0x40, 0xc0 and 0."""
        kind = self.u8(s + 1)
        self.w8(s + 2, 0x15)
        self.w8(s + 3, 0x15)
        self.w16(s + 0xE, {0x13: 0x40, 0x29: 0xC0, 0x2D: 0}[kind])
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 9, 5)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        for o in (0x34, 0x32, 0x30, 0x2C, 0x2A, 0x28):
            self.w16(s + o, 0)
        self.w16(s + 0x44, int(_s32(args[1]) / 4))   # and its sound, 0x26

    def _tick_13(self, s):                  # 0x80059688, a bolt's sphere (0x13, 0x29, 0x2d)
        """Growing 0x80 a frame to +0x44, striking a shell 3.5 times it
        (effect_grow 0x3800, 0x400, 0x8000); a puff rising from it, each
        axis rand >> 6 less 0x100 across, -(rand >> 7) - 0x80 up (0x2000,
        -0x80, 0xf, 0xc, 0xa, 1, 1); turning 0x40 a frame."""
        self.out_words([0x8000])
        self.grow(0x3800, self.s16(s + 0x44), 0x80, 0x400, 0x8000)
        vx = (self.rand() >> 6) - 0x100
        vz = (self.rand() >> 6) - 0x100
        vy = -(self.rand() >> 7) - 0x80
        struct.pack_into("<3h", self.m, (TICK_SP + 0x168) & MASK, vx, vy, vz)
        self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                   [self.get(TICK_SP + 0x168, 8), 0x2000, -0x80, 0xF, 0xC, 0xA, 1, 1], direct=True)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x40)

    def _spawn_0f(self, s, args):           # 0x80054294, tornado
        """The first of a cast's two (args[2] 0) is 0xc80 across and turned
        nothing, the second 2000 wider and turned half; the view's angles in
        args[1] are not read."""
        i = args[2]
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 8)
        self.w8(s + 3, 8)
        self.w8(s + 9, 5)
        self.w16(s + 0x10, 0x32)
        self.w16(s + 0x32, 0xC80)
        self.w8(s + 8, 1)
        self.w8(s + 0x44, 0)
        self.w8(s + 0xD, 1)
        self.w16(s + 0xE, 0x40)
        self.w16(s + 0x30, 2000 * i + 0xC80)
        self.w16(s + 0x34, 2000 * i + 0xC80)
        self.w16(s + 0x2A, i << 11)         # and the first, its sound 0x96

    def _tick_0f(self, s):                  # 0x80056ac4, tornado
        """effect_move at 0xb4 with no height and no turn: the tiles (the
        hit's low two bits) take the move back and end it; what it meets it
        strikes once (sub_800537e8, +0x44 the latch a clear frame lifts).
        Then a strike about its point -- radius its scale x / 8, mode its
        height / 2 (0x640, in_range's asker's height), edge 0x400 -- but the
        point is offset by the three halfwords at effect_tick's sp+0x50,
        which this arm writes only after: the last tornado's puff velocity,
        or what the rest of the frame left there. A puff (0x6f) a frame,
        velocity three rands over 0x7fff, and a splash in the water. It
        turns 0x15e a frame."""
        hit = self.move(0xB4, 0, 0)
        if hit:
            if hit & 3:
                self.undo(s)
                self.w8(s, 0xFF)
            if self.u8(s + 0x44) == 0:
                self.w8(s + 0x44, 1)
                self.attack(s, hit)
        else:
            self.w8(s + 0x44, 0)
        off = struct.unpack_from("<3h", self.m, (TICK_SP + 0x50) & MASK)
        self.put(STRIKE_POINT, struct.pack("<3i", *[_s32(self.s32(s + 0x18 + 4 * i) + off[i])
                                                    for i in range(3)]))
        self.strike(STRIKE_POINT, 0, self.s16(s + 0x30) >> 3, self.s16(s + 0x32) >> 1, 0x400,
                    0x1000)
        v = [_div7fff(self.rand() << 9) - 0x100]
        v.append(_div7fff(-(self.rand() << 8)))
        v.append(_div7fff(self.rand() << 9) - 0x100)
        struct.pack_into("<3h", self.m, (TICK_SP + 0x50) & MASK, *[_s16_(c) for c in v])
        self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                   [self.get(TICK_SP + 0x50, 8), 0x270F, -0x80, 5, 0x16, 0, 1, 1], direct=True)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x15E)
        self.splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)

    def _spawn_01(self, s, args):           # 0x80053fa8, fire wall
        """Model 0x28, scale (0x7d0, 0xa, 0x7d0), the view's yaw (args[1]
        points at its angles; pitch and roll zeroed), level, life 0x78."""
        self.w8(s + 9, 5)
        self.w8(s + 2, 0x28)
        self.w8(s + 3, 0x28)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w8(s + 8, 1)
        self.w8(s + 4, 0)
        self.w16(s + 0x30, 0x7D0)
        self.w16(s + 0x32, 0xA)
        self.w16(s + 0x34, 0x7D0)
        self.put(s + 0x28, args[1][:8])
        self.w16(s + 0x28, 0)
        self.w16(s + 0x2C, 0)
        self.w16(s + 0x3A, 0)
        self.w16(s + 0x44, 0)
        self.w16(s + 0x10, 0x78)
        self.w16(s + 0xE, 0)
        self.w8(s + 0xD, 1)                 # and its sound, 0x31

    def _tick_01(self, s):                  # 0x8005a070, fire wall
        """effect_move at 0xb4 and the height's top bit: walls do not stop
        it; a creature it meets it strikes (sub_800537e8), every frame.
        Then a strike about its point, radius its scale x / 4, mode its
        height -- the point offset by the three halfwords at effect_tick's
        sp+0x170, which flash, fire storm and this arm write their puffs'
        velocities to, this one only after. Rising (+0x44 0) 0x1f4 a frame
        and 0x230 wider to 0x1069, standing three frames (1), sinking back
        (2) and gone under 0x64; turning 0x1f4 a frame throughout. A puff
        (0x6f) a frame, rising 0x64 to 0xc8."""
        hit = self.move(0xB4, 0x80000000, 0)
        if hit & 0x10:
            self.attack(s, hit)
        off = struct.unpack_from("<3h", self.m, (TICK_SP + 0x170) & MASK)
        self.put(STRIKE_POINT, struct.pack("<3i", *[_s32(self.s32(s + 0x18 + 4 * i) + off[i])
                                                    for i in range(3)]))
        self.strike(STRIKE_POINT, 0, self.s16(s + 0x30) >> 2, self.s16(s + 0x32), 0x400, 0x1000)
        n = self.s16(s + 0x44)
        if n == 0:
            for o, d in ((0x30, 0x230), (0x32, 0x1F4), (0x34, 0x230), (0x2A, 0x1F4)):
                self.w16(s + o, self.u16(s + o) + d)
            if self.s16(s + 0x32) >= 0x1069:
                self.w16(s + 0x46, 0)
                self.w16(s + 0x44, self.u16(s + 0x44) + 1)
        elif n == 1:
            self.w16(s + 0x46, self.u16(s + 0x46) + 1)
            self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x1F4)
            if self.s16(s + 0x46) >= 3:
                self.w16(s + 0x44, self.u16(s + 0x44) + 1)
        elif n == 2:
            for o, d in ((0x32, 0x1F4), (0x34, 0x230), (0x30, 0x230)):
                self.w16(s + o, self.u16(s + o) - d)
            self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x1F4)
            if self.s16(s + 0x32) < 0x64:
                self.w8(s, 0xFF)
        vy = -((100 * self.rand()) >> 15) - 0x64
        struct.pack_into("<3h", self.m, (TICK_SP + 0x170) & MASK, 0, vy, 0)
        self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                   [self.get(TICK_SP + 0x170, 8), 0x1000, 0, 8, 0x1C, 2, 1, 2], direct=True)

    def _spawn_02(self, s, args):           # 0x800540b8, fire storm
        """particle(9, 0x1b58, 5), its velocity jittered by (rand >> 8) -
        0x40 each way, life 0x50, a grace of 3, +0x44 the creature it goes
        for (args[1]: its slot, 0xfe the player, 0xff none); the last of a
        cast's three (args[2] 2) its sound, 0x2d."""
        self.particle(s, 9, 0x1B58, 5)
        for o in (0x38, 0x3A, 0x3C):
            self.w16(s + o, self.u16(s + o) - 0x40 + (self.rand() >> 8))
        self.w16(s + 0x10, 0x50)
        self.w8(s + 0xB, 3)
        self.w16(s + 0xE, 0x40)
        self.w8(s + 0x44, args[1])

    def _tick_02(self, s):                  # 0x80059db8, fire storm
        """At a creature (+0x44 its slot) it homes on its middle, effect_home
        at most 0x1c2, slowing within 0x64; at the player (0xfe) on the eye,
        0x1f4, within 0xbb8; with none (0xff) it falls, 0xa a frame more,
        through effect_move. Meeting anything: what collide_query last
        answered (collide_mask) struck, six puffs about it, splashes in the
        water, gone. Else from its seventh frame a puff a frame behind."""
        t = self.u8(s + 0x44)
        if t == 0xFF:
            self.w16(s + 0x3A, self.u16(s + 0x3A) + 0xA)
            met = self.move(0xA, 0x80000000, 0) != 0
        else:
            if t == 0xFE:
                x, y, z = struct.unpack_from("<3i", self.m, PLAYER_POS & MASK)
                target, most, near = (x, _s32(y - 0x640), z), 0x1F4, 0xBB8
            else:
                target = self.w.actor_mid(t)
                most, near = 0x1C2, 0x64
            self.out_words([0, 0xA, 0x80000000])
            met = self.home(target, most, 0x3C, near, 0, 0xA, 0x80000000) == -1
        if met:
            self.attack(s, self.w.collide_mask)
            for _k in range(6):
                vx = ((400 * self.rand()) >> 15) - 0xC8
                vz = ((400 * self.rand()) >> 15) - 0xC8
                vy = ((400 * self.rand()) >> 15) - 0xC8
                struct.pack_into("<3h", self.m, (TICK_SP + 0x170) & MASK, vx, vy, vz)
                self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                           [self.get(TICK_SP + 0x170, 8), 0x1D4C, -0x2EE, 8, 0x16, 0xA, 1, 2], direct=True)
            self.splash(s + 0x18, 5, 0x400, 0x2000, 0x4000, 0x1000)
            self.w8(s, 0xFF)
            return
        if self.s16(s + 0x10) < 0x4A:
            v = [((60 * self.rand()) >> 15) - 0x1E for _k in range(3)]
            struct.pack_into("<3h", self.m, (TICK_SP + 0x170) & MASK, *v)
            self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                       [self.get(TICK_SP + 0x170, 8), 0x1000, -0x100, 0xD, 0x1C, 0xA, 1, 2], direct=True)

    def home(self, target, most, accel, near, reach, radius, height):  # 0x80055f74
        """effect_home: from the point to the target, vec_length_3d; -2
        when not past `reach`; within `near` the velocity to three
        quarters (fixed_madd(0, v, 0xc00)); then effect_steer along the
        direction, each axis << 12 over the length."""
        s = self.u32(CURRENT)
        d = [_s32(target[i] - self.s32(s + 0x18 + 4 * i)) for i in range(3)]
        ln = vec_length_3d(*d)
        if not reach < ln:
            return -2
        if not near < ln:
            for o in (0x38, 0x3A, 0x3C):
                self.w16(s + o, (self.s16(s + o) * 0xC00) >> 12)
        dirv = [_s16_(movement.trunc(_s32(c << 12), ln)) for c in d]
        return self.steer(accel, most, radius, height, dirv)

    def steer(self, accel, most, radius, height, dirv):     # 0x80055bd8
        """effect_steer: the velocity += vec_scale(accel, dir), cut to
        `most` when longer, the point moved; then effect_collide there --
        -1 met, 0 not; nothing asked with a height of -1."""
        s = self.u32(CURRENT)
        accel = _s16_(accel)
        for i in range(3):
            o = s + 0x38 + 2 * i
            self.w16(o, self.u16(o) + ((dirv[i] * accel) >> 12))
        v = [self.s16(s + 0x38 + 2 * i) for i in range(3)]
        ln = vec_length_3d(*v)
        if most < ln:
            for i in range(3):
                self.w16(s + 0x38 + 2 * i, movement.trunc(v[i] * most, ln))
        for i in range(3):
            self.w32(s + 0x18 + 4 * i, self.s32(s + 0x18 + 4 * i) + self.s16(s + 0x38 + 2 * i))
        if height == -1:
            return 0
        p = (self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20))
        return -1 if self.collide(p, radius, height) else 0

    def _spawn_04(self, s, args):           # 0x80054dd4, flame
        """Model 0x29 -- a head, animated by +0x14 -- scale 0xbb8, the angles
        args[1] points at (the view's, pitch and all), life 0x96, +0xe 0x80,
        +0x45 0; its sound 0x90."""
        self.w8(s + 8, 1)
        self.w8(s + 9, 5)
        self.w8(s + 2, 0x29)
        self.w8(s + 3, 0x29)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        self.w8(s + 4, 0)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0xBB8)
        self.put(s + 0x28, args[1][:8])
        self.w16(s + 0x10, 0x96)
        self.w8(s + 0x45, 0)
        self.w16(s + 0xE, 0x80)

    def _tick_04(self, s):                  # 0x8005a39c, flame
        """By +7: 0 flying -- effect_move at 0xfa and the height's top bit,
        the head's clock (+0x14) 0x80 a frame; with a creature marked
        (+0x45 frames left of five) a fire ball from the head's vertex 0 at
        it, 0x320 a frame; else one time in sixteen a look for one within
        0x61a8 (sub_8004d3c4, noise 0x200), and one in thirty-two within
        0x7530, two breaths (0x6e, the empty arm) from vertices 0x2f and
        0x32. Meeting anything, or at the end of its life, splashes, a second
        flame (+0 | 3) set at +7 2 to burst three frames on, and it bursts
        itself: +7 1, model 0x15, +0 | 3 -- effect_grow(0x4000, 0x800, 0x4b,
        0x400, 0x8000) and a turn of 0x40 a frame, the player struck too.
        2..4 count up to 5, which bursts."""
        ph = self.u8(s + 7)
        if ph == 0:
            hit = self.move(0xFA, 0x80000000, 0)
            if hit or self.s16(s + 0x10) < 2:
                self.splash(s + 0x18, 8, 0x190, 0x2000, 0x8000, 0x400)
                c = self.spawn(0xA, self.u8(s) | 3, FLAME, self.get(s + 0x18, 16),
                               [None, self.get(s + 0x28, 8)], direct=True)
                self.w8(c + 7, 2)                   # and the sound, 0x27
                self._burst_04(s)
                return
            self.w16(s + 0x14, (self.u16(s + 0x14) + 0x80) & 0xFFF)
            if self.u8(s + 0x45):
                point = self.head(s, 0)
                self.put(TICK_SP + 0x1D0, struct.pack("<3i", *point))
                target = self.w.actor_mid(self.u8(s + 0x44))
                self.put(TICK_SP + 0x1C0, struct.pack("<3i", *target))
                self.put(TICK_SP + 0x1B8, struct.pack("<3h", *vec_toward(point, target, 0x320)))
                self.spawn(0xA, self.u8(s), FIRE_BALL, self.get(TICK_SP + 0x1D0, 16),
                           [self.get(TICK_SP + 0x1B8, 8)], direct=True)
                self.w8(s + 0x45, self.u8(s + 0x45) - 1)
            elif self.rand() < 0x800:
                a = self.look(s, 0x61A8)
                if a:
                    self.w8(s + 0x44, (a - ACTORS) // ACTOR_STRIDE)
                    self.w8(s + 0x45, 5)
            if self.rand() < 0x400:
                a = self.look(s, 0x7530)
                if a:
                    self.breath(s, 0x2F)
                    self.breath(s, 0x32)
            return
        if ph == 1:
            self._grow_04(s)
        elif ph == 5:
            self._burst_04(s)
        else:
            self.w8(s + 7, ph + 1)

    def _burst_04(self, s):                 # 0x8005a458
        self.w8(s + 7, 1)
        self.w8(s + 3, 0x15)
        self.w8(s + 0xC, 0x34)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0)
        self.w16(s + 0x10, -1)
        self.w8(s, self.u8(s) | 3)
        self._grow_04(s)

    def _grow_04(self, s):                  # 0x8005a628
        self.grow(0x4000, 0x800, 0x4B, 0x400, 0x8000)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x40)

    def look(self, s, reach):
        """sub_8004d3c4 from the point along the angles, cones 0x320, the
        noise 0x200 -- a rand for each creature in them -- its distance
        left at effect_tick's sp+0x1e0. The creature, or 0."""
        self.out_words([0x320, 0x320, TICK_SP + 0x1E0, 0x200])
        a, d = self.w.sight((self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20)),
                            self.s16(s + 0x2A), self.s16(s + 0x28), reach, 0x320, 0x320, 0x200,
                            self.rand)
        self.w32(TICK_SP + 0x1E0, d)
        return a

    def head(self, s, vertex):              # 0x80053af4, through 0x80053a0c
        """Vertex `vertex` of the effect's animated model (model_table[+3 +
        0x28], animation +4, clock +0x14), each axis scaled by +0x30.., turned
        by its angles with the yaw a half turn on (vec_rotate), from its
        point."""
        import anim
        import weapon
        model = self.u8(s + 3) + 0x28
        v = anim.vertices(_bank_anim(model), self.u8(s + 4), self.u16(s + 0x14))[vertex]
        v = [_s16_((v[i] * self.s16(s + 0x30 + 2 * i)) >> 12) for i in range(3)]
        r = weapon.vec_rotate((self.s16(s + 0x28), _s16_(self.u16(s + 0x2A) + 0x800),
                               self.s16(s + 0x2C)), v)
        return [_s32(r[i] + self.s32(s + 0x18 + 4 * i)) for i in range(3)]

    def breath(self, s, vertex):            # 0x800561d8
        """From vertex `vertex` of the head, at its angles, the yaw jittered
        by (rand >> 7) - 0x80: effect_spawn(10, +0, 0x6e, ...) -- the empty
        arm, so the slot is set up and freed -- and +7 2 written in it."""
        point = self.head(s, vertex)
        ang = struct.pack("<3H", self.u16(s + 0x28),
                          (self.u16(s + 0x2A) + (self.rand() >> 7) - 0x80) & 0xFFFF,
                          self.u16(s + 0x2C))
        c = self.spawn(0xA, self.u8(s), BREATH, struct.pack("<3i", *point) + bytes(4),
                       [self.get(ZERO_VEC, 8), ang + bytes(2)])    # the angles unread
        if c:
            self.w8(c + 7, 2)

    def _spawn_15(self, s, args):           # 0x800543e8, orladin
        self.particle(s, 0x37, 0x1800, 5)
        self.w16(s + 0x10, 0x78)
        self.w8(s + 0xD, 1)
        self.w16(s + 0x44, 0)
        self.w16(s + 0xE, 0x40)             # and its sound, 0x9a

    def _tick_15(self, s):                  # 0x80057fc0, orladin
        """A puff a frame where it was (velocity three rands, +-0x10), then
        effect_move at 0xb4 with no height and no turn; the tiles end it.
        Meeting a creature (bit 0x10) -- and it goes on through -- two
        bursts (0x58) where it is, with +0 0x43, sized 0 and 0x80, and
        sixteen rays (0x5b) 0x4b0 above, flying out at 360 a frame."""
        v = [((self.rand() << 5) >> 15) - 0x10 for _k in range(3)]
        self.spawn(0xA, 0, TRAIL, self.get(s + 0x18, 16),
                   [struct.pack("<4h", *v, 0), 0x1A90, -0x3E8, 4, 0x25, 0, 1, 1], direct=True)
        hit = self.move(0xB4, 0, 0)
        if not hit:
            return
        if hit & 0xF:
            self.w8(s, 0xFF)
        if not hit & 0x10:
            return
        point = self.get(s + 0x18, 16)
        self.spawn(0xA, 0x43, BURST, point, [None, 0, 1], direct=True)
        self.spawn(0xA, 0x43, BURST, point, [None, 0x80, 1], direct=True)      # and the sound, 0x25
        x, y, z = self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20)
        for a in range(0, 0x1000, 0x100):
            vx = (45 * movement.game_sin(a)) >> 9
            vz = (45 * movement.game_cos(a)) >> 9
            self.spawn(0xA, 0, RAY, struct.pack("<3i", x, _s32(y + 0x4B0), z) + bytes(4),
                       [struct.pack("<4h", _s16_(vx), 0, _s16_(vz), 0)], direct=True)

    def _spawn_58(self, s, args):           # 0x800548ec, orladin's burst
        self.setup(s, 0x15, 0, 5)
        for o in (0x30, 0x32):
            self.w16(s + o, args[1])
        self.w16(s + 0x10, 0x2D)
        for o in (0x28, 0x2A, 0x2C):
            self.w16(s + o, 0)
        self.w16(s + 0x34, args[1])
        self.w16(s + 0xE, (args[2] & 0xFFFF) << 6)

    def _tick_58(self, s):                  # 0x80059b84, orladin's burst
        """Growing 0x80 a frame from its size, striking a shell four times
        it; gone at 0x600. Then fire resist's mark's tail (0x8005b5fc): it
        turns 0x40 a frame."""
        self.grow(0x4000, 0x600, 0x80, 0x400, 0x8000)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + 0x40)

    def grow(self, mult, limit, step, edge, mode):      # 0x80056134
        """A sphere growing `step` a frame, all three scales alike; it
        strikes between mult times its last size and mult times its size
        less one, `mode`, `edge`, at 0x1000; gone at `limit`."""
        s = self.u32(CURRENT)
        v = (self.u16(s + 0x30) + step) & 0xFFFF
        for o in (0x30, 0x34, 0x32):
            self.w16(s + o, v)
        sc = self.s16(s + 0x30)
        r = _s32(mult * sc) >> 12
        self.strike(s + 0x18, r - (_s32(mult * step) >> 12), r - 1, mode, edge, 0x1000)
        if self.s16(s + 0x30) >= limit:
            self.w8(s, 0xFF)

    def _spawn_5b(self, s, args):           # 0x80055788, orladin's ray
        self.w8(s + 4, 0x80)
        self.w8(s + 2, 0xB)
        self.w8(s + 3, 0xB)
        self.w8(s + 8, 5)
        self.w8(s + 9, 5)
        self.w8(s + 0xC, 0x33)
        self.w16(s + 0x32, 0xC00)
        self.w16(s + 0x10, 0x14)
        self.w16(s + 0x12, 0x1000)
        self.w16(s + 0x30, 0x1000)
        self.w16(s + 0x34, 0x1000)
        self.w16(s + 0xE, 0x40)

    def _tick_5b(self, s):                  # 0x8005b4b8, orladin's ray
        """Out by its velocity while its life is 10 or more, back by it and
        0x200 taller after; flickering (+4 0x80 and 0x81). It strikes from a
        step ahead within its scale, mode 0x8000 -- but its +0 is 0, so it
        strikes nothing."""
        sign = 1 if self.s16(s + 0x10) >= 0xA else -1
        self.w32(s + 0x18, self.s32(s + 0x18) + sign * self.s16(s + 0x38))
        self.w32(s + 0x20, self.s32(s + 0x20) + sign * self.s16(s + 0x3C))
        if sign < 0:
            self.w16(s + 0x32, self.u16(s + 0x32) + 0x200)
        self.w8(s + 4, (self.u8(s + 0x10) & 1) - 0x80)
        self.put(STRIKE_POINT, struct.pack("<3i", *[_s32(self.s32(s + o) + self.s16(s + v))
                                                    for o, v in ((0x18, 0x38), (0x1C, 0x3A),
                                                                 (0x20, 0x3C))]))
        self.strike(STRIKE_POINT, 0, self.s16(s + 0x30), 0x8000, 0x400, 0x1000)

    def orbit(self, s, model, angle, y):    # 0x80053c20
        """What the three protecting spells' marks share: drawn by mode 0xe,
        in front of the eye, at (0xa0, y + 0x78, 0), scale 0x100, turned by
        `angle`."""
        self.w8(s + 8, 0xE)
        self.w8(s + 4, 0x80)
        self.w8(s + 9, 5)
        self.w8(s + 0xC, 0x34)
        self.w16(s + 0x12, 0x1000)
        for o in (0x32, 0x34, 0x30):
            self.w16(s + o, 0x100)
        self.w8(s + 2, model)
        self.w8(s + 3, model)
        self.w32(s + 0x18, 0xA0)
        self.w32(s + 0x1C, y + 0x78)
        self.w32(s + 0x20, 0)
        self.w16(s + 0x28, angle)
        self.w16(s + 0x2C, 0)
        self.w16(s + 0x2A, 0)

    def _spawn_1a(self, s, args):           # 0x8005585c, fire resist's mark
        i = args[1]
        self.orbit(s, 0x18, i << 11, 14 * i - 7)
        self.w16(s + 0xE, 0xC0)

    def _spawn_1b(self, s, args):           # 0x8005588c, refusal's
        self.orbit(s, 0x2F, 0, 0)
        self.w16(s + 0xE, 0x80)

    def _spawn_1c(self, s, args):           # 0x800558a8, missile shield's
        i = args[1]
        self.orbit(s, 0x18, i << 11, 14 * i - 7)
        self.w16(s + 0xE, 0x80)

    def _spawn_17(self, s, args):           # 0x800558d4, earth heal
        self.w8(s + 8, 0)
        self.w16(s + 0x10, 8)

    def _spawn_19(self, s, args):           # 0x800558f4, antidote
        self.w8(s + 8, 0)
        self.w16(s + 0x10, 0x10)
        self.w16(s + 0xE, 0x80)

    def _spawn_1e(self, s, args):           # 0x80055918, blessings
        self.w8(s + 8, 0)
        self.w16(s + 0x10, 0x10)
        self.w16(s + 0xE, 0x40)

    def _aimed(self, s, model):
        """0x80054cf4 and 0x80054d68: +8 1, +4 0x80, +2 and +3 the model,
        the life 0x46, the scale 0x1800, and the angles off the velocity --
        +0x28 its pitch, ratan2(vy, vec_length_2d(vx, vz)), +0x2a its yaw less
        a quarter, ratan2(vz, vx) - 0x400."""
        vx, vz = self.s16(s + 0x38), self.s16(s + 0x3C)
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 2, model)
        self.w8(s + 3, model)
        self.w16(s + 0x10, 0x46)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, 0x1800)
        ln = vec_length_2d(vx, vz)
        self.w16(s + 0x28, movement.ratan2(self.s16(s + 0x3A), ln))
        self.w16(s + 0x2C, 0)
        self.w16(s + 0x2A, movement.ratan2(self.s16(s + 0x3C), self.s16(s + 0x38)) - 0x400)

    def _spawn_1f(self, s, args):           # 0x80054d50, a bobbing bolt
        self._aimed(s, 0x22)
        self.w8(s + 9, 0)
        self.w16(s + 0x3A, 0)
        self.w16(s + 0x44, 1)
        self.w16(s + 0x46, 0)

    def _spawn_22(self, s, args):           # 0x80054b5c
        self._aimed(s, 0x21)
        self.w8(s + 9, 5)

    def _spawn_23(self, s, args):           # 0x80054be4
        self.w8(s + 8, 0)
        self.w16(s + 0x10, 0x14)
        self.put(s + 0x28, args[1][:8])
        self.w16(s + 0xE, 0xC0)
        self.w8(s + 0xD, 1)

    def _spawn_24(self, s, args):           # 0x80054c2c
        self.w8(s + 8, 0)
        self.w16(s + 0x10, 0x3C)
        self.put(s + 0x28, args[1][:8])
        self.w16(s + 0xE, 0xC0)

    def _spawn_26(self, s, args):           # 0x80054338
        self.setup(s, 0x24, 0x400, 5)
        self.w16(s + 0xE, 0x40)
        self.w16(s + 0x10, 0x32)
        self.w8(s + 0xD, 1)
        self.w16(s + 0x44, 0x14)
        self.w32(s + 0x1C, self.s32(s + 0x1C) - 0xC8)

    def _spawn_6f(self, s, args):           # 0x80055738
        self.particle(s, args[4], args[1], args[6] | 4)
        self.w16(s + 0x44, args[2])
        self.w16(s + 0x10, args[3])
        self.w16(s + 0x46, args[5])
        self.w16(s + 0xE, (args[7] & 0xFFFF) << 6)

    def setup(self, s, a, scale, b):        # effect_setup (0x80053ba8)
        self.w8(s + 8, 1)
        self.w8(s + 4, 0x80)
        self.w8(s + 0xC, 0x34)
        self.w8(s + 2, a)
        self.w8(s + 3, a)
        self.w8(s + 9, b)
        self.w16(s + 0x12, 0x1000)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, scale)

    def particle(self, s, a, scale, b):     # 0x80053be4
        self.w8(s + 8, 5)
        self.w8(s + 4, 0x80)
        self.w8(s + 0xC, 0x33)
        self.w8(s + 2, a)
        self.w8(s + 3, a)
        self.w8(s + 9, b)
        self.w16(s + 0x12, 0x1000)
        for o in (0x34, 0x32, 0x30):
            self.w16(s + o, scale)

    def driver(self):
        """effect_driver: each live slot in turn -- its record published, its
        life counted down, freed at -1, else its arm."""
        self.w32(INDEX, 0)
        for k in range(COUNT):
            s = SLOTS + STRIDE * k
            if self.u8(s) != 0xFF:
                self.w32(CURRENT, s)
                self.w32(CURRENT_REC, SPELL_TABLE + RECORD * self.u8(s + 1))
                life = (self.u16(s + 0x10) - 1) & 0xFFFF
                self.w16(s + 0x10, life)
                if life == 0xFFFF:
                    self.w8(s, 0xFF)
                else:
                    self.tick(s)
            self.w32(INDEX, k + 1)

    def tick(self, s):
        kind = self.u8(s + 1)
        if kind >= 0x82:
            return
        arm = {0x1F: self._tick_1f, 0x22: self._tick_22, 0x23: self._tick_23,
               0x24: self._tick_23, 0x26: self._tick_26, TRAIL: self._tick_6f,
               0x17: self._tick_17, 0x19: self._tick_19, 0x1A: self._tick_1a,
               0x1B: self._tick_1b, 0x1C: self._tick_1c, 0x1E: self._tick_1e,
               FIRE_BALL: self._tick_00, SPLASH: self._tick_70,
               STONE: self._tick_06, WIND_CUTTER: self._tick_0d,
               HAZE: self._tick_0b, SHUDOM: self._tick_09, WALWIND: self._tick_11,
               RING: self._tick_5e, WAVE: self._tick_59, EARTH_WAVE: self._tick_07,
               0x16: self._tick_07, BORTECTH: self._tick_0c, HOLD: self._tick_65,
               METEOR: self._tick_5f, BLAST: self._tick_5a, ORLADIN: self._tick_15,
               BURST: self._tick_58, RAY: self._tick_5b, TORNADO: self._tick_0f,
               FIRE_WALL: self._tick_01, FIRE_STORM: self._tick_02,
               FLAME: self._tick_04, RYU_GA: self._tick_0d, ANORIUM: self._tick_00,
               CAPRICORN: self._tick_3a, SEATHS: self._tick_42,
               MORGULINE: self._tick_4c, VACULACIA: self._tick_40,
               EXCEL1: self._tick_36, EXCEL2: self._tick_36, 0x31: self._tick_36,
               FALLER: self._tick_3c, FANG: self._tick_46, FLASH: self._tick_47,
               0x14: self._tick_47, 0x12: self._tick_47, MOON: self._tick_4b,
               SPARK: self._tick_03, MARK: self._tick_78, MARK2: self._tick_7a,
               PILLAR: self._tick_5c, PILLAR2: self._tick_5c, MOON_BURST: self._tick_48,
               SPHERE2: self._tick_44, SPHERE: self._tick_44, SLAYER2: self._tick_7c,
               SLAYER: self._tick_7b, LIGHTNING: self._tick_71, 0x7D: self._tick_71,
               0x81: self._tick_71, 0x72: self._tick_72, 0x7E: self._tick_72,
               0x80: self._tick_72, 0x13: self._tick_13, 0x29: self._tick_13,
               0x2D: self._tick_13}.get(kind)
        if arm is None:
            raise NotImplementedError(f"effect_tick's arm {kind:#x}")
        arm(s)

    def _puff(self, s, b, e):
        """The puff a bolt leaves at its point, two fifths of its velocity:
        effect_spawn(10, 0, 0x6f, point, v, 0xe10, -0x80, 5, 0x16, 0, b, e).
        The velocity's fourth halfword is whatever the stack held: not kept."""
        v = [div5(2 * self.s16(s + o)) for o in (0x38, 0x3A, 0x3C)]
        self.spawn(10, 0, TRAIL, self.get(s + 0x18, 16),
                   [struct.pack("<4h", *v, 0)] + TRAIL_ARGS[:5] + [b, e], direct=True)

    def _tick_1f(self, s):                  # 0x80058a2c, a bolt that bobs
        self.w8(s, 0x81)
        d = 0xA if self.s16(s + 0x44) != 0 else -0xA
        self.w16(s + 0x46, self.u16(s + 0x46) + d)
        self.w32(s + 0x1C, self.s32(s + 0x1C) + self.s16(s + 0x46))
        if self.s16(s + 0x46) < -0x45 and self.s16(s + 0x44) == 0:
            self.w16(s + 0x44, 1)
        if self.s16(s + 0x46) >= 0x46 and self.s16(s + 0x44) == 1:
            self.w16(s + 0x44, 0)
        self.strike(s + 0x18, 0, self.s16(s + 0x30) >> 4, 0x8000, 0x400, 0x1000)
        self.w8(s, 0x84)
        if self.move(0x64, 0xC8, 0):
            self.w8(s, 0xFF)
        self._puff(s, 2, 5)

    def _tick_22(self, s):                  # 0x80058bb4
        self.w8(s, 0x81)
        self.strike(s + 0x18, 0, self.s16(s + 0x30) >> 4, 0x8000, 0x400, 0x1000)
        self.w8(s, 0x84)
        if self.move(0x64, 0xC8, 0):
            self.undo(s)
            self.w8(s, 0xFF)
        self._puff(s, 1, 4)

    def _tick_23(self, s):                  # 0x80058f3c, kinds 0x23 and 0x24
        self.w8(s, 0x81)
        self.strike(s + 0x18, 0, self.s16(s + 0x30) >> 3, 0x8000, 0x400, 0x1000)
        self.w8(s, 0x81)
        if self.move(0x64, 0xC8, 0):
            self.undo(s)
            self.w8(s, 0xFF)
        self._puff(s, 1, 3)

    def _tick_26(self, s):                  # 0x80056de8, the spores
        if self.s16(s + 0x44) != 0:
            self.w16(s + 0x44, self.u16(s + 0x44) - 1)
            self.w16(s + 0x30, self.u16(s + 0x30) + GROW)
            self.w16(s + 0x34, self.u16(s + 0x34) + GROW)
        if self.s16(s + 0x32) < 0x1000:
            self.w16(s + 0x32, self.s16(s + 0x32) + GROW)
        self.w32(s + 0x1C, self.s32(s + 0x1C) + (-RISE if self.s16(s + 0x10) >= TURN else SINK))
        self.w8(s, 0x81)
        self.strike(s + 0x18, 0, self.s16(s + 0x30), 0x8000, 0x400, 0x1000)
        self.w8(s, 0x84)
        if self.move(0x64, 0xC8, 0):
            self.w8(s, 0xFF)

    def _tick_6f(self, s):                  # 0x8005b45c, a puff
        vy = (self.u16(s + 0x3A) + self.u16(s + 0x46)) & 0xFFFF
        self.w32(s + 0x18, self.s32(s + 0x18) + self.s16(s + 0x38))
        self.w16(s + 0x3A, vy)
        self.w32(s + 0x20, self.s32(s + 0x20) + self.s16(s + 0x3C))
        sc = self.u16(s + 0x30) + self.u16(s + 0x44)
        for o in (0x30, 0x34, 0x32):
            self.w16(s + o, sc)
        self.w32(s + 0x1C, self.s32(s + 0x1C) + self.s16(s + 0x3A))

    def _tick_00(self, s):                  # 0x80056910, the fire ball
        """In flight (+7 0) effect_move at radius 0xb4, the height's top bit,
        turning 0x12c a frame; a hit splashes on water within 0x1f4 under its
        surface, steps the ball back -- half its velocity when (x - the
        player's x) ^ 2, the compiler's xor, has a root under 0x400, all of it
        otherwise -- and hands what it hit to actor_attack_player from 8
        velocities back with 0x1388 and the caster's strength; then it grows by
        0x800 two frames (+7 2 and 3), +4 0x80 + the phase, and is gone."""
        ph = self.u8(s + 7)
        if ph == 0:
            hit = self.move(0xB4, 0x80000000, -0x12C)
            if not hit:
                return
            self.splash(s + 0x18, 3, 0x190, 0x2000, 0x2000, 0x400)
            dx = (self.s32(s + 0x18) - self.s32(PLAYER_POS)) & 0xFFFFFFFF
            if movement.game_isqrt(dx ^ 2) < 0x400:
                for o, v in ((0x18, 0x38), (0x1C, 0x3A), (0x20, 0x3C)):
                    h = self.s16(s + v)
                    self.w32(s + o, self.s32(s + o) - (int(h / 2) if h < 0 else h >> 1))
            else:
                self.undo(s)
            self.attack(s, hit)
            self.w8(s + 7, 1)
        elif ph >= 3:
            self.w8(s, 0xFF)
            return
        self.w8(s + 4, (ph - 0x80) & 0xFF)
        sc = (self.u16(s + 0x30) + 0x800) & 0xFFFF
        for o in (0x30, 0x32, 0x34):
            self.w16(s + o, sc)
        self.w8(s + 7, self.u8(s + 7) + 1)

    def magic_strength(self, s):            # 0x80053624
        """A player's effect (+0 0x40): the mean of the working skills whose
        bit its spell's group has; any other, 5."""
        if not self.u8(s) & 0x40:
            return 5
        group = self.u8(SPELL_TABLE + RECORD * self.u8(s + 1) + 5)
        n = total = 0
        for k in range(4, -1, -1):
            if group & (1 << k):
                n += 1
                total += self.u16(WORKING + 2 * k)
        return ((total & 0xFFFF) // n) & 0xFFFF if n else total & 0xFFFF

    def splash(self, point, n, spread, size, bob, wobble):   # 0x80056580
        """Splashes on the water, when the point is within 0x1f4 under the
        surface the last query found (surface_plane_18): n of kind 0x70 on
        the surface, the first at the point and the rest within `spread` of
        it, each sized by random_spread(wobble) + 0x1000 -- `size` across,
        `bob` its rise. Their velocity is the stack's leftover."""
        y, surf = self.s32(point + 4), self.s32(SURFACE)
        if y < surf or surf + 0x1F4 < y:
            return 0
        dx = dz = 0
        for _ in range(n):
            pt = struct.pack("<3i", self.s32(point) + dx, surf, self.s32(point + 8) + dz) + bytes(4)
            r = ((self.rand() + self.rand() - 0x8000) * wobble) >> 15
            v = r + 0x1000
            self.spawn(0xA, 0, SPLASH, pt, [bytes(8), _s32(size * v) >> 12, _s32(bob * v) >> 12])
            dx = ((self.rand() * spread) >> 14) - spread
            dz = ((self.rand() * spread) >> 14) - spread
        return 1

    def _mark(self, s, timer, turn):
        if self.s16(timer) == 0:
            self.w8(s, 0xFF)
        self.w16(s + 0x2A, self.u16(s + 0x2A) + turn)

    def _tick_1a(self, s):                  # 0x8005b5e4: gone with 0x801b256a
        self._mark(s, B56A, 0x40)

    def _tick_1b(self, s):                  # 0x8005b610: with 0x801b256c
        self._mark(s, B56C, -0x100)

    def _tick_1c(self, s):                  # 0x8005b63c: with 0x801b256e
        self._mark(s, B56E, -0x40)

    def _heal(self, n):
        hp = (self.u16(HP) + n) & 0xFFFF
        self.w16(HP, hp)
        if self.u16(HP_MAX) < hp:
            self.w16(HP, self.u16(HP_MAX))

    def lighting(self, rgb, near, far, k):  # sub_8003456c on the 48 records
        import status
        o = TILE_LOOK & MASK
        look = bytearray(self.m[o:o + 48 * 0x6C])
        status.light_blend(look, rgb, near, far, k)
        self.m[o:o + len(look)] = look

    def _sparkle(self, vel, b, e):
        """A sparkle in front of the eye: a puff at (rand >> 5 - 0x200,
        rand >> 8 + 0xc8, 0x400) drawn by mode 0xe, its +0xa 1."""
        x = (self.rand() >> 5) - 0x200
        y = (self.rand() >> 8) + 0xC8
        t = self.spawn(0xA, 0, TRAIL, struct.pack("<3i", x, y, 0x400) + bytes(4),
                       [vel, 0x2BC, -0x1E, 0xA, 0x26, -0xA, b, e], direct=True)
        self.w8(t + 0xA, 1)
        self.w8(t + 8, 0xE)

    def _tick_17(self, s):                  # 0x8005b668, earth heal
        if self.s16(s + 0x10) == 4:
            self._heal(0x50)
        k = movement.game_sin((self.s16(s + 0x10) << 8) & 0xFFFFFFFF)
        self.lighting((0xE6, 0xC8, 0xA0), 0, 0x59D8, _s16_(k))

    def _tick_19(self, s):                  # 0x8005b6d4, antidote
        if self.s16(s + 0x10) == 0xC:
            self.w16(POISON, 0)
        self._sparkle(bytes(8), 1, 2)
        k = movement.game_sin((self.s16(s + 0x10) << 7) & 0xFFFFFFFF)
        self.lighting((0xA0, 0xB4, 0xDC), 0, 0x4650, _s16_(k))

    def _tick_1e(self, s):                  # 0x8005b7a4, blessings
        if self.s16(s + 0x10) == 0xC:
            self._heal(0xC8)
            cure(self, 7)
        for _ in range(3):
            self._sparkle(bytes(8), 1, 1)
        k = movement.game_sin((self.s16(s + 0x10) << 7) & 0xFFFFFFFF)
        self.lighting((0xF0, 0xF0, 0xA0), 0, 0x4650, _s16_(k))

    def undo(self, s):                      # 0x80056800: the move taken back
        for o, v in ((0x18, 0x38), (0x1C, 0x3A), (0x20, 0x3C)):
            self.w32(s + o, self.s32(s + o) - self.s16(s + v))

    def strike(self, point, a1, radius, mode, edge, scale):
        """effect_strike (0x80053850): bit 1 of +0 strikes the player through
        effect_hurt_player with the kind's record; bit 2 the creatures through
        0x8004ceac (strike_creatures), with the caster's strength and the
        flags +0 & 0xc0 and 0x20."""
        s = self.u32(CURRENT)
        rec = self.u32(CURRENT_REC)
        if self.u8(s) & 1:
            self.w.hurt_player([self.s32(point), self.s32(point + 4), self.s32(point + 8)],
                               a1, radius, mode, edge & 0xFFFF,
                               [self.u16(rec + o) for o in (6, 8, 0xA)], self.u8(rec + 4),
                               [self.u16(rec + o) for o in (0xC, 0xE, 0x10, 0x12, 0x14)],
                               scale & 0xFFFF, self.u8(s + 6))
        if self.u8(s) & 2:
            self.w.strike_creatures(point, a1, radius, mode, edge & 0xFFFF,
                                    self.magic_strength(s) & 0xFFFF,
                                    [self.u16(rec + o) for o in (6, 8, 0xA, 0xC, 0xE, 0x10, 0x12, 0x14)],
                                    scale & 0xFFFF, (self.u8(s) & 0xC0) | 0x20, rec)

    def u32(self, a):
        return struct.unpack_from("<I", self.m, a & MASK)[0]

    def collide(self, point, radius, height):
        """effect_collide (0x80053310): a grace count first; then
        collide_query at the point, its y plus half the height, with the flags
        +0 & 7 chooses -- 0 answers 1 and 5..7 answer 4 without asking."""
        s = self.u32(CURRENT)
        g = self.u8(s + 0xB)
        if g:
            self.w8(s + 0xB, g - 1)
            return 0
        f = self.u8(s) & 7
        if f not in QUERY:
            return 1 if f == 0 else 4
        return self.w.collide_query(point[0], point[1] + ((height & 0xFFF) >> 1), point[2],
                                    radius, height, QUERY[f])

    def move(self, radius, height, spin):
        """effect_move (0x800566d4): the velocity added, effect_collide there
        and with +0xd half a step back too; +0xa the layer, +0x2c turned."""
        s = self.u32(CURRENT)
        for o, v in ((0x18, 0x38), (0x1C, 0x3A), (0x20, 0x3C)):
            self.w32(s + o, self.s32(s + o) + self.s16(s + v))
        p = (self.s32(s + 0x18), self.s32(s + 0x1C), self.s32(s + 0x20))
        hit = self.collide(p, radius, height)
        if self.u8(s + 0xD) and not hit:
            q = tuple(p[i] - (self.s16(s + 0x38 + 2 * i) >> 1) for i in range(3))
            hit = self.collide(q, radius, height)
        self.w8(s + 0xA, 2 if self.w.layer_offset else 1)
        self.w16(s + 0x2C, (self.u16(s + 0x2C) - spin) & 0xFFF)
        return hit


# effect_aim (0x8004f1d0) and what it takes from: the bearing from a point to
# the target's eye, pulled towards the creature's own facing the further off
# it is, and a velocity along it.

def cure(mach, mask):
    """sub_8002aa54: bit 1 the curse, 2 the darkness -- the level cut to 0x40
    and the timer 0, so it ramps out -- either of them the poison, 1 or 4 the
    slowing cut to 0x40, 4 the paralysis."""
    for bit, lv, t in ((1, CURSE_LV, CURSE_T), (2, DARK_LV, DARK_T)):
        if mask & bit:
            if mach.s16(lv) >= 0x41:
                mach.w16(lv, 0x40)
            mach.w16(t, 0)
    if mask & 3:
        mach.w16(POISON, 0)
    if mask & 5 and mach.s16(SLOW) >= 0x41:
        mach.w16(SLOW, 0x40)
    if mask & 4:
        mach.w16(PARALYSIS, 0)


def vec_to_angles(dx, dy, dz):
    """0x80016c90: [pitch, yaw, 0] of a vector."""
    yaw = movement.vec_angle(dx, dz) & 0xFFFF
    ln = vec_length_2d(dx, dz)
    pitch = (-movement.vec_angle(dy, ln)) & 0xFFF
    return [pitch, _s16_(yaw), 0]


_BANK = {}


def _actor_mid(m, t):
    a = (ACTORS + ACTOR_STRIDE * t) & MASK
    x, y, z = struct.unpack_from("<3i", m, a + 0x2C)
    return (x, _s32(y - (struct.unpack_from("<H", m, a + 0x1E)[0] >> 1)), z)


def _bank_anim(index):
    """anim's model of model_table[index], the resident bank's, kept."""
    import anim
    if index not in _BANK:
        _BANK[index] = anim.load_bank(index)
    return _BANK[index]


def vec_toward(a, b, speed):
    """0x80016044: from a to b, `speed` long -- each axis times the speed
    over vec_length_3d, toward 0."""
    d = [_s32(b[i] - a[i]) for i in range(3)]
    ln = vec_length_3d(*d)
    return [_s16_(movement.trunc(_s32(c * speed), ln)) for c in d]


def vec_length_3d(x, y, z):
    """0x80016c44: each >> 3, the squares summed in a word, the game's root,
    << 3."""
    return movement.game_isqrt(_s32((x >> 3) ** 2 + (y >> 3) ** 2 + (z >> 3) ** 2)) << 3


def vec_length_2d(a, b):
    """0x80016c08: through the game's own root, which comes back one short of
    a square -- movement.vlen's math.isqrt does not."""
    return movement.game_isqrt(_s32((a >> 3) * (a >> 3) + (b >> 3) * (b >> 3)) & 0xFFFFFFFF) << 3


def _s16_(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def angle_lerp(a, b, t):
    """0x80017170: a towards b, the short way round, t in 4096ths."""
    d = (_s16_(b) - _s16_(a)) & 0xFFF
    if d > 0x800:
        d -= 0x1000
    return (a + ((d * t) >> 12)) & 0xFFF


def aim(actor_angles, target, speed, point, pitch=-1, spread=0x400):
    """effect_aim with one pass (no lead): the velocity [x, y, z] and the
    yaw. `actor_angles` the creature's +0x40 and +0x42, `target` the player's
    x y z, `point` where the effect starts."""
    ang = vec_to_angles(target[0] - point[0], target[1] - (point[1] + 0x640),
                        target[2] - point[2])
    d = (ang[1] - actor_angles[1]) & 0xFFF
    if d >= 0x800:
        d = 0x1000 - d
    t = movement.trunc(d << 12, _s16_(spread))
    if t > 0x1000:
        t = 0x1000
    ang[1] = _s16_(angle_lerp(ang[1], actor_angles[1], t))
    if pitch == -1:
        d = (ang[0] - actor_angles[0]) & 0xFFF
        if d >= 0x800:
            d = 0x1000 - d
        ang[0] = _s16_(angle_lerp(ang[0], actor_angles[0], d))
    else:
        ang[0] = _s16_(pitch)
    v = movement.direction_from_angles(ang[0], ang[1])
    sp = _s16_(speed)
    return [_s16_((c * sp) >> 12) for c in v], ang[1]


class RamWorld:
    """The rest of the game as a snapshot's RAM has it, for the check:
    collide_query's tiles (the grid in RAM), the occupancy byte, the objects
    and the player, and effect_hurt_player's calls, kept."""

    def __init__(self, m, lv):
        import collision
        self.m = m
        o = GRID & MASK
        self.lvl = collision.Level(lv, grid=bytes(m[o:o + 64000]))
        self.layer_offset = struct.unpack_from("<H", m, LAYER_OFFSET & MASK)[0]
        self.player = struct.unpack_from("<3i", m, PLAYER_POS & MASK)
        self.objs = self._solids()
        self.hurts = []
        self.strikes = []
        self.collide_mask = struct.unpack_from("<I", m, COLLIDE_MASK & MASK)[0]

    def _solids(self):
        import objcoll
        out = []
        for k in range(396):
            r = (OBJECT_TABLE & MASK) + OBJECT_STRIDE * k
            typ = struct.unpack_from("<H", self.m, r + 6)[0]
            if typ == 0xFF or self.m[r] == 0:
                continue
            row = bytes(self.m[(OBJECT_TYPES & MASK) + 24 * typ:][:24])
            kind, a, b = objcoll.shape(row, self.m[r + 0x38], self.m[r + 3])
            if kind == "none":
                continue
            x, y, z = struct.unpack_from("<3i", self.m, r + 0x14)
            out.append({"slot": k, "kind": kind, "a": a, "b": b, "pos": (x, y, z),
                        "top": struct.unpack_from("<h", self.m, r + 0xC)[0],
                        "ang": struct.unpack_from("<h", self.m, r + 0x26)[0]})
        return out

    def actor_mid(self, t):
        """Creature t's middle: its place, half its +0x1e up."""
        return _actor_mid(self.m, t)

    def sight(self, point, yaw, pitch, reach, ycone, pcone, noise, rand):
        """sub_8004d3c4 over the snapshot's creatures: (actor, distance)."""
        import magic
        return magic.sight(self.m, point, yaw, pitch, reach, ycone, pcone, noise, rand)

    def collide_query(self, x, y, z, r, h, flags):
        """collide_query, its answer kept as collide_mask (0x80034148)."""
        self.collide_mask = self._query(x, y, z, r, h, flags)
        return self.collide_mask

    def _query(self, x, y, z, r, h, flags):
        import collision
        mask = 0
        cx, cz = x >> 11, z >> 11
        inside = 0 <= x <= movement.GRID_MAX and 0 <= z <= movement.GRID_MAX
        hm = h & 0x0FFFFFFF                 # the top bits are flags (0x80033f9c)
        if flags & 1:
            extra = {}
            mask, cur = movement.query(self.lvl, x, y, z, radius=r, body=h,   # its flags too
                                       extra=extra)
            self._planes(cur, extra)
            ymid = y - (((h << 4) & 0xFFFFFFFF) >> 5)
            self.layer_offset = collision.layer_of(self.lvl.cell(cx, cz), ymid) if inside else 0
        if flags & 6:
            raise NotImplementedError("collide_query's fence")
        self.collide_actor = -1
        if not inside or not self.lvl.cell(cx, cz)[2] & 0xFC:
            return mask
        if flags & 0x10:
            self.collide_actor = self.spot_taken(x, y, z, r, hm)
            if self.collide_actor != -1:
                mask |= 0x10
        elif flags & 0x40:
            raise NotImplementedError("collide_query's actor_in_range")
        if flags & 0x20 and movement.object_collide(self.objs, x, y, z, r, hm) is not None:
            mask |= 0x20
        if flags & 0x80 and movement.in_range(self.player, x, y, z, r + 0x320, 0x6A4, hm) != -1:
            mask |= 0x80
        return mask

    def spot_taken(self, x, y, z, r, own):
        """actor_spot_taken (0x8004d644): the first awake creature, not
        dying, not masked by actor_skip_mask, not the one acting, whose place
        -- +0x26 higher for a follower not the one 0x8018fac0 names -- is
        within the asker's radius and its own +0x1c, heights +0x1e and the
        asker's. The slot, or -1."""
        m = self.m

        def u(a, n=4, signed=False):
            return int.from_bytes(m[a & MASK:(a & MASK) + n], "little", signed=signed)
        skip = m[ACTOR_SKIP & MASK]
        cur = u(CURRENT_ACTOR)
        named = u(0x8018FAC0, 4, True)
        for k in range(ACTOR_N):
            a = ACTORS + ACTOR_STRIDE * k
            if m[(a + 9) & MASK] != 1 or m[(a + 0xE) & MASK] == 3:
                continue
            flags = u(a + 0x28)
            if skip & flags or a == cur:
                continue
            pos = [u(a + 0x2C, 4, True), u(a + 0x30, 4, True), u(a + 0x34, 4, True)]
            if flags & 0x10:
                if u(a + 0x22, 2, True) == named:
                    continue
                pos[1] += u(a + 0x26, 2, True)
            elif flags & 0x400000:
                raise NotImplementedError("a creature tracked by a model's vertex")
            if movement.in_range(pos, x, y, z, u(a + 0x1C, 2) + r, u(a + 0x1E, 2), own) != -1:
                return k
        return -1

    def hurt_player(self, point, a1, radius, mode, edge, attacks, effect, more, scale, pct):
        self.hurts.append([point[0], point[1], point[2], a1, radius, mode, edge,
                           list(attacks), effect, list(more), scale, pct])

    def strike_creatures(self, point, near, radius, mode, edge, stat, att, scale, flags, rec):
        self.strikes.append(_strike_row(self.m, point, near, radius, mode, edge, stat, scale, flags))

    def release(self, c):
        """0x80057dd0: the creature in slot c let go -- its +0x28 bit 0x800."""
        _release(self.m, c)

    def _planes(self, cur, extra):
        """What tile_collision leaves in RAM: the nearest surface
        (collision_surface, 0x801e6474), the ceiling (0x801e6478) and the
        three planes it found, seeded 100000 (0x8003265c)."""
        struct.pack_into("<i", self.m, 0x801E6474 & MASK, _s32(cur))
        if 0x801E6478 in extra:
            struct.pack_into("<i", self.m, 0x801E6478 & MASK, _s32(extra[0x801E6478]))
        for a in (0x801E647C, 0x801E6480, 0x801E6484):
            struct.pack_into("<i", self.m, a & MASK, extra.get(a, 100000))

    def collide_wrapper(self, x, y, z, r, h):
        """collide_wrapper_actor (0x80033d08): the tiles alone, the mask; the
        planes it finds left in RAM."""
        extra = {}
        mask, cur = movement.query(self.lvl, x, y, z, radius=r, body=h, extra=extra)
        self._planes(cur, extra)
        return mask

    def surface(self, x, y, z, r, h):
        """collide_surface (0x80033b10): the nearest surface, 0x801e6474."""
        return self.surface_ceiling(x, y, z, r, h)[0]

    def actor_point(self, t):
        """Creature t's place, the 16 bytes from its +0x2c."""
        return _actor_point(self.m, t)

    def player_point(self):
        """player_pos, its 16 bytes (the fourth word 0x801b25fc, which only
        save_restore writes)."""
        return _player_point(self.m)

    def surface_ceiling(self, x, y, z, r, h):
        """collide_surface, and the ceiling tile_collision leaves beside the
        surface (collision_ceiling, 0x801e6478)."""
        extra = {}
        _mask, cur = movement.query(self.lvl, x, y, z, r, h, ymid=y - 0x500, extra=extra)
        self._planes(cur, extra)
        return cur, extra[0x801E6478]


def _actor_point(m, t):
    a = (ACTORS + ACTOR_STRIDE * t + 0x2C) & MASK
    return bytes(m[a:a + 16])


def _player_point(m):
    a = PLAYER_POS & MASK
    return bytes(m[a:a + 16])


def _release(m, c):
    a = (ACTORS + ACTOR_STRIDE * c + 0x28) & MASK
    struct.pack_into("<I", m, a, struct.unpack_from("<I", m, a)[0] & ~0x800 & 0xFFFFFFFF)


def _strike_row(m, point, near, radius, mode, edge, stat, scale, flags):
    """A strike on the creatures as the checks keep it: the point (its fourth
    word, the bearing 0x8002 turns from), and what effect_strike hands on but
    the record."""
    return [*struct.unpack_from("<4i", m, point & MASK), near, radius, mode, edge, stat, scale, flags]


# --- the machine against the game's own code -----------------------------------

SCRATCH = 0x801FF100              # free RAM above the overlay, below mipsrun's stack


def _game(ram):
    """A machine over `ram` with the BIOS's rand an Lcg from 1."""
    import levelstate
    import mipsrun
    cpu = mipsrun.CPU(ram)
    lcg = levelstate.Lcg()
    cpu.hooks[RAND] = lambda c: lcg()
    return cpu


def _call(cpu, addr, args, stack=()):
    """addr(args...) with the words `stack` from sp+0x10, the game's way."""
    import mipsrun
    sp = mipsrun.STACK - 0x100
    cpu.r[29] = sp
    for i, v in enumerate(stack):
        cpu.wr(sp + 0x10 + 4 * i, 4, v & 0xFFFFFFFF)
    for i, v in enumerate(args):
        cpu.r[4 + i] = v & 0xFFFFFFFF
    cpu.r[31] = mipsrun.RETURN
    cpu.pc = addr
    while cpu.pc != mipsrun.RETURN:
        cpu.step()
    cpu.r[29] = mipsrun.STACK
    return cpu.r[2]


def game_spawn(cpu, a0, a1, kind, point, args):
    """effect_spawn over the game's own code: the point and every pointer
    argument laid in scratch RAM first."""
    at = SCRATCH
    words = []

    def lay(data):
        nonlocal at
        p = at
        for i in range(0, len(data), 4):
            cpu.wr(p + i, 4, int.from_bytes(data[i:i + 4].ljust(4, b"\0"), "little"))
        at += (len(data) + 7) & ~7
        return p
    pp = lay(point) if point is not None else 0
    for v in args:
        words.append(0 if v is None else lay(v) if isinstance(v, (bytes, bytearray)) else v)
    return _call(cpu, SPAWN, [a0, a1, kind, pp], words)


def _hurt_watch(cpu, out):
    def at(c):
        sp = c.r[29]
        st = [c.rd(sp + 0x10 + 4 * i, 4) for i in range(12)]
        p = c.r[4]
        out.append([_s32(c.rd(p, 4)), _s32(c.rd(p + 4, 4)), _s32(c.rd(p + 8, 4)),
                    _s32(c.r[5]), _s32(c.r[6]), _s32(c.r[7]), st[0], st[1:4], st[4],
                    st[5:10], st[10], st[11]])
    cpu.watch[HURT_PLAYER] = at


def _slots(m):
    o = SLOTS & MASK
    return bytes(m[o:o + STRIDE * COUNT])


def _leftover(x, i):
    """Whether byte i of the game's slot x is the stack's leftover the
    machine cannot know: a puff's velocity's fourth halfword and a sparkle's
    point's fourth word while it lives; a splash's velocity, the half-step
    flag made of it and its point's fourth word, freed or not; meteor's
    blast's velocity's fourth halfword (0x8005b9c4 writes three), freed or
    not."""
    if x[1] == TRAIL and x[0] != 0xFF:
        return i in (0x3E, 0x3F, 0x24, 0x25, 0x26, 0x27)
    if x[1] == SPLASH:
        return i in (0x24, 0x25, 0x26, 0x27, 0xD) or 0x38 <= i < 0x40
    if x[1] == BLAST:
        return i in (0x3E, 0x3F)
    if x[1] == RAY:
        return i in (0x3E, 0x3F, 0x24, 0x25, 0x26, 0x27)
    if x[1] == BREATH:                      # its point's fourth word, sub_800561d8's stack
        return i in (0x24, 0x25, 0x26, 0x27)
    return False


def _take_leftovers(game, m):
    """The game's leftovers (_leftover) into the machine's slots, so that a
    slot spawned over one later starts from the same bytes as the game's."""
    o = SLOTS & MASK
    for k in range(COUNT):
        x = game[o + STRIDE * k:o + STRIDE * (k + 1)]
        for i in range(STRIDE):
            if _leftover(x, i):
                m[o + STRIDE * k + i] = x[i]


def _differ(a, b):
    """The bytes of two slot arrays that differ, leaving out the stack's
    leftovers (_leftover)."""
    bad = []
    for k in range(COUNT):
        x, y = a[k * STRIDE:(k + 1) * STRIDE], b[k * STRIDE:(k + 1) * STRIDE]
        if x == y:
            continue
        for i in range(STRIDE):
            if x[i] != y[i] and not _leftover(x, i):
                bad.append((k, i, x[i], y[i]))
    return bad


def scenarios(ram, rng, n=24):
    """[(label, [(a0, a1, kind, point, args)])]: bolts (0x1f, 0x22, 0x23,
    0x24) at the player from round about, aimed as the volley aims them and
    not, and spores (0x26) beside them."""
    px, py, pz = struct.unpack_from("<3i", ram, PLAYER_POS & MASK)
    out = []
    for i in range(n):
        kind = (0x23, 0x24, 0x26, 0x1F, 0x22)[i % 5]
        d = rng.choice((900, 1600, 2600, 4200))
        yaw = rng.randrange(0x1000)
        x = px + ((movement.game_sin(yaw) * d) >> 12)
        z = pz + ((movement.game_cos(yaw) * d) >> 12)
        y = py - rng.randrange(0x200, 0x900)
        point = struct.pack("<4i", x, y, z, rng.randrange(-5, 5))
        if kind == 0x26:
            spawns = [(rng.randrange(1, 100), 0x81, 0x26, point, [None])]
        else:
            angles = (rng.randrange(0x1000), rng.randrange(0x1000), 0)
            if rng.randrange(3):
                vel, _ = aim(angles, (px, py, pz), 0x12C, (x, y, z))
            else:
                vel = [rng.randrange(-0x400, 0x400) for _ in range(3)]
            spawns = [(rng.randrange(1, 100), 0x83, kind, point,
                       [struct.pack("<4h", *vel, 0), struct.pack("<4h", *angles, 0)])]
        out.append((f"{kind:#x} from {d} at {yaw:#x}", spawns))
    return out


def machine_check(out=sys.stdout, frames=90):
    """The machine against effect_spawn and effect_driver themselves, run by
    tools/mipsrun.py over every snapshot of a level: each scenario's slots,
    all 128 of them, after every frame, and every strike on the player."""
    import random
    import memcard
    rng = random.Random(0xEFFEC7)
    runs = good = nframes = fgood = nhurt = hgood = 0
    first = []
    for path in memcard._snapshots():
        ram = bytearray(open(path, "rb").read())
        lv = ram[0x8018FAD9 & MASK]
        o = SLOTS & MASK
        for k in range(COUNT):
            ram[o + STRIDE * k] = 0xFF
        for label, spawns in scenarios(bytes(ram), rng, 9):
            cpu = _game(bytes(ram))
            hurts = []
            _hurt_watch(cpu, hurts)
            m = bytearray(ram)
            world = RamWorld(m, lv)
            mach = Machine(m, world)
            for sp in spawns:
                game_spawn(cpu, *sp)
                mach.spawn(*sp)
            runs += 1
            ok = True
            for f in range(frames):
                del hurts[:]
                world.hurts = []
                _call(cpu, DRIVER, [])
                mach.driver()
                bad = _differ(_slots(cpu.ram), _slots(m))
                nframes += 1
                fgood += not bad
                nhurt += max(len(hurts), len(world.hurts))
                same = [h for h, w in zip(hurts, world.hurts) if h == w]
                hgood += len(same) if len(hurts) == len(world.hurts) else 0
                if (bad or len(same) != len(hurts) or len(hurts) != len(world.hurts)) and ok:
                    ok = False
                    if len(first) < 6:
                        first.append(f"  {os.path.basename(path)} {label}, frame {f}: "
                                     + (f"slot {bad[0][0]} +{bad[0][1]:#x} game {bad[0][2]:#x} here {bad[0][3]:#x}"
                                        if bad else f"strikes {hurts} here {world.hurts}"))
                if all(cpu.rd(SLOTS + STRIDE * k, 1) == 0xFF for k in range(COUNT)):
                    break
            good += ok
    for line in first:
        print(line, file=out)
    print(f"  effect_spawn and effect_driver, the game's own, over {runs} runs on "
          f"the snapshots: {good} of {runs} runs, {fgood} of {nframes} frames with all "
          f"128 slots as the machine leaves them, {hgood} of {nhurt} strikes on the "
          f"player handed the same", file=out)
    return good == runs


HEALING = (0x17, 0x19, 0x1A, 0x1B, 0x1C, 0x1E)


def magic_check(out=sys.stdout, per=6, frames=40):
    """The healing and protecting spells' effects against effect_spawn and
    effect_driver themselves over every snapshot: spawned as player_action
    spawns them, with the player hurt, poisoned, cursed or not and the timers
    running or not -- every frame all 128 slots, the player's fields and the
    48 lighting records."""
    import random
    import memcard
    import levelstate
    rng = random.Random(0x4EA1)
    runs = good = nframes = fgood = 0
    first = []
    lo = TILE_LOOK & MASK
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        o = SLOTS & MASK
        for k in range(COUNT):
            base[o + STRIDE * k] = 0xFF
        lv = base[0x8018FAD9 & MASK]
        for _ in range(per):
            ram = bytearray(base)
            hpm = rng.choice((50, rng.randrange(200, 1000)))
            struct.pack_into("<H", ram, HP_MAX & MASK, hpm)
            struct.pack_into("<H", ram, HP & MASK, rng.randrange(1, min(hpm, 120)))
            for a in (POISON, CURSE_LV, CURSE_T, DARK_LV, DARK_T, SLOW, PARALYSIS):
                struct.pack_into("<H", ram, a & MASK, rng.choice((0, 0, rng.randrange(1, 300))))
            for a in (B56A, B56C, B56E):
                struct.pack_into("<H", ram, a & MASK, rng.choice((0, rng.randrange(1, 30))))
            kind = rng.choice(HEALING)
            point = bytes(ram[PLAYER_POS & MASK:(PLAYER_POS & MASK) + 16])
            vel = bytes(rng.randrange(256) for _ in range(8))
            spawns = ([(0xA, 0x40, kind, point, [vel, 0]), (0xA, 0x40, kind, point, [vel, 1])]
                      if kind in (0x1A, 0x1C) else [(0xA, 0x40, kind, point, [vel])])
            cpu = _game(bytes(ram))
            cpu.hooks[0x8001576C] = lambda c: 0            # the sound
            m = bytearray(ram)
            mach = Machine(m, RamWorld(m, lv), levelstate.Lcg())
            for sp in spawns:
                game_spawn(cpu, *sp)
                mach.spawn(*sp)
            runs += 1
            ok = True
            for f in range(frames):
                _call(cpu, DRIVER, [])
                mach.driver()
                bad = _differ(_slots(cpu.ram), _slots(m))
                fields = [a for a in PLAYER_FIELDS
                          if cpu.rd(a, 2) != struct.unpack_from("<H", m, a & MASK)[0]]
                look = bytes(cpu.ram[lo:lo + 48 * 0x6C]) == bytes(m[lo:lo + 48 * 0x6C])
                nframes += 1
                same = not bad and not fields and look
                fgood += same
                if not same and ok:
                    ok = False
                    if len(first) < 4:
                        first.append(f"  {os.path.basename(path)} kind {kind:#x}, frame {f}: "
                                     + (f"slot {bad[0][0]} +{bad[0][1]:#x} game {bad[0][2]:#x} here {bad[0][3]:#x}"
                                        if bad else f"fields {[hex(a) for a in fields]}" if fields
                                        else "the lighting records"))
                if all(cpu.rd(SLOTS + STRIDE * k, 1) == 0xFF for k in range(COUNT)):
                    break
            good += ok
    for line in first:
        print(line, file=out)
    print(f"  the healing and protecting spells' effects, the game's own over the "
          f"snapshots: {good} of {runs} runs, {fgood} of {nframes} frames with all 128 "
          f"slots, the player's fields and the 48 lighting records as the machine "
          f"leaves them", file=out)
    return good == runs


class StandIn:
    """collide_query and actor_attack_player as the fire ball's check stands
    them in on both sides: a hit now and then, by where it asks, and what is
    handed over, kept."""

    def __init__(self, layer, m=None, quiet=False):
        self.layer_offset = layer
        self.quiet = quiet
        self.asked = []
        self.hits = []
        self.hurts = []
        self.strikes = []
        self.released = []
        self.collide_actor = -1
        self.collide_mask = 0
        self.m = m

    @staticmethod
    def answer(x, y, z):
        return (0, 0, 0, 0, 0, 0, 1, 0x10, 0x20, 0, 0, 0)[((x ^ y ^ z) >> 6) % 12]

    def collide_query(self, x, y, z, r, h, flags):
        self.asked.append([x & 0xFFFFFFFF, y & 0xFFFFFFFF, z & 0xFFFFFFFF, r, h & 0xFFFFFFFF, flags])
        v = self.answer(_s32(x), _s32(y), _s32(z))
        if flags == 0xB0 and v == 0 and (_s32(z) >> 8) % 9 == 0:   # the player, now and then
            v = 0x80
        if self.quiet:                      # one ask in 48 meets the tiles
            v = 1 if ((_s32(x) ^ _s32(y) ^ _s32(z)) >> 6) % 48 == 7 else 0
        self.collide_actor = (_s32(x) >> 8) % 200 if v & 0x10 else -1
        self.collide_mask = v
        return v

    def release(self, c):
        self.released.append(c)

    def sight(self, point, yaw, pitch, reach, ycone, pcone, noise, rand):
        import magic
        return magic.sight(self.m, point, yaw, pitch, reach, ycone, pcone, noise, rand)

    def actor_mid(self, t):
        return _actor_mid(self.m, t)

    def collide_wrapper(self, x, y, z, r, h):
        return 1 if ((_s32(x) ^ _s32(z)) >> 7) % 5 == 0 else 0

    @staticmethod
    def _floor(x, y):
        return _s32(y) + (0x80 if (_s32(x) >> 9) & 1 else 0)

    def surface(self, x, y, z, r, h):
        return self._floor(x, y)

    def surface_ceiling(self, x, y, z, r, h):
        f = self._floor(x, y)
        return f, f - (0x400, 0x1800, 0x9000)[(_s32(z) >> 9) % 3]

    def spot_taken(self, x, y, z, r, own):
        return (_s32(x) >> 8) % 200 if ((_s32(x) ^ _s32(z)) >> 7) % 7 == 0 else -1

    def actor_point(self, t):
        return _actor_point(self.m, t)

    def player_point(self):
        return _player_point(self.m)

    def attack_hit(self, code, flags, kind, strength, stat, pct, back):
        self.hits.append([code, flags, strength, stat, pct,
                          None if back is None else [v & 0xFFFFFFFF for v in back]])

    def hurt_player(self, point, a1, radius, mode, edge, attacks, effect, more, scale, pct):
        self.hurts.append([point[0], point[1], point[2], a1, radius, mode, edge,
                           list(attacks), effect, list(more), scale, pct])

    def strike_creatures(self, point, near, radius, mode, edge, stat, att, scale, flags, rec):
        self.strikes.append(_strike_row(self.m, point, near, radius, mode, edge, stat, scale, flags))


SPELLS_SENT = ((FIRE_BALL, 0x384, "the fire ball", (), 80), (STONE, 0x1F4, "stone", (), 80),
               (WIND_CUTTER, 0x2BC, "wind cutter", (), 80), (HAZE, 0x104, "haze", (3,), 80),
               (SHUDOM, 0xFA, "shudom", ("view",), 160), (WALWIND, 0xFA, "walwind", ("view",), 240),
               (EARTH_WAVE, None, "earth wave", ("player", 0x43, None, 0x1000, 0x100, 0x1000, 1), 40),
               (BORTECTH, None, "bortecth", ("creature", 0x42, None), 80),
               (METEOR, None, "meteor", ("creature", 0x43, None), 60),
               (ORLADIN, 0x104, "orladin", (), 120),
               (TORNADO, 0x12C, "tornado", ("view", (0, 1)), 60),
               (FIRE_WALL, 0x23A, "fire wall", ("view",), 60),
               (FIRE_STORM, 0x1F4, "fire storm", ("slot?", 2), 90),
               (FLAME, 0xFA, "flame", ("view",), 200),
               (RYU_GA, 0x2BC, "ryu-ga's", ("view",), 80),
               (CAPRICORN, 0x226, "capricorn's", (), 80),
               (ANORIUM, 0x2EE, "anorium sword's", (), 80),
               (VACULACIA, 0x1B8, "vaculacia sword's", (), 80),
               (SEATHS, 0x384, "Seath's sword's", ("view",), 80),
               (MORGULINE, 0x1C2, "morguline axe's", (), 80),
               (EXCEL1, 0x1F4, "the excellector's first", ((3, 2, 1, 0),), 60),
               (EXCEL2, 0x1F4, "the excellector's second", (), 60),
               (FALLER, 0x140, "0x3c", (), 60),
               (FANG, 0x1F4, "triple fang's first", (0,), 80),
               (FLASH, 0xAA, "triple fang's second", ("view", 0x258, 0x3C, 0x80, 0x8C, 0xA0), 200),
               (0x14, 0xAA, "flash", ("view", 0x258, 0x3C, 0x80, 0x8C, 0xA0), 200),
               (MOON, 0x2D0, "the second moonlight sword's second", (), 120),
               (MARK, 0x258, "the first moonlight sword's", ("view", "kids"), 80),
               (MARK2, 0x258, "the second moonlight sword's", ("view", "kids"), 80),
               (SLAYER, 0x3E8, "dark slayer's first", ("view",), 60),
               (SLAYER, 0x3E8, "dark slayer's first, anywhere", ("view", "anywhere"), 30),
               (SLAYER2, 0x3E8, "dark slayer's second", (), 80),
               (SLAYER2, 0x3E8, "dark slayer's second, back at the player", ("back",), 40),
               (LIGHTNING, 0x258, "lightning", (6,), 120),
               (LIGHTNING, 0x258, "lightning, anywhere", (2, "anywhere"), 120),
               (0x7D, 0x258, "0x7d", (6,), 120),
               (0x81, 0x258, "0x81", (6,), 120))
"""The attacking spells the checks send: the kind, the speed its arm of
player_action gives it, its name, what follows the velocity ("view" a
pointer to view_angles; "slot?" the creature in sight, now and then the
player (0xfe) or none (0xff); a tuple, one spawn for each of its values, as
the arm spawns them) and the frames to run. With no speed it is put down, not
sent: at the player's feet or a creature's, its +0 and its arguments
after. "kids": the moonlight swords' four pillars (KIDS) after the mark, each
handed the mark's slot -- 0, the slots all free -- and a point of its own
about the mark's."""

KIDS = {MARK: PILLAR, MARK2: PILLAR2}

FLAT = {TORNADO: 0x540, LIGHTNING: 0, 0x7D: 0, 0x81: 0}

QUIET = {FLAME}
"""The spells the export's stand-in lets fly long -- one ask in 48 meets
something -- so what they do in flight is in the self-test."""
"""The spells whose arm lowers the cast point by this and zeroes the
velocity's y: they go level, along the ground."""


def _spawns(a1, kind, point, args):
    """The effect_spawn calls of one cast: (10, a1, kind, point, args), once,
    or once for each value of a tuple among the arguments; a mark's four
    pillars after it ("kids")."""
    if "kids" in args:
        args = [v for v in args if v != "kids"]
        x, y, z, w = struct.unpack("<4i", point)
        out = [(0xA, a1, kind, point, args)]
        for dx, dz in ((-0x200, 0x100), (0x200, 0x100), (-0x100, -0x200), (0x100, -0x200)):
            out.append((0xA, a1, KIDS[kind], struct.pack("<4i", x + dx, y, z + dz, w),
                        [args[0], 0]))
        return out
    for i, v in enumerate(args):
        if isinstance(v, tuple):
            return [(0xA, a1, kind, point, args[:i] + [x] + args[i + 1:]) for x in v]
    return [(0xA, a1, kind, point, args)]


def _placed(ram, more, creature):
    """A put-down spell's spawn: (a1, the point's 16 bytes, the arguments)."""
    where, a1, *args = more
    if where == "player":
        point = bytes(ram[PLAYER_POS & MASK:(PLAYER_POS & MASK) + 16])
    else:
        point = struct.pack("<4i", *creature, 0)
    return a1, point, list(args)


def spell_hit_check(out=sys.stdout, per=6, frames=None):
    """The attacking spells end to end -- fire_hit_check for each, sent at
    the speed its arm of player_action gives it."""
    good = True
    for kind, speed, name, more, n in SPELLS_SENT:
        good = fire_hit_check(out, per, frames or n, kind, speed, name, more) and good
    return good


def fire_hit_check(out=sys.stdout, per=10, frames=60, kind=None, speed=0x384, name="the fire ball",
                   more=()):
    """The fire ball end to end in the game's own world: collide_query,
    actor_attack_player and actor_take_hit the game's, over every snapshot,
    the balls sent at its creatures; only rand's seed shared and the leaves
    -- skill_practice, award_exp, strong_blow, player_take_hit, the level's
    hook, the sound -- stood in for. All 128 slots and all 200 creatures
    every frame, and every call out."""
    import random
    import memcard
    import levelstate
    import hit
    rng = random.Random(0xF1E2)
    runs = good = nframes = fgood = skipped = 0
    hurt = killed = player = 0
    first = []
    oa = ACTORS & MASK
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        o = SLOTS & MASK
        base[o:o + STRIDE * COUNT] = bytes(STRIDE * COUNT)
        for k in range(COUNT):
            base[o + STRIDE * k] = 0xFF
        lv = base[0x8018FAD9 & MASK]
        hook_at = hit._level_hook(base)
        px, py, pz = struct.unpack_from("<3i", base, PLAYER_POS & MASK)
        awake = [k for k in range(ACTOR_N) if base[(ACTORS + ACTOR_STRIDE * k + 9) & MASK] == 1]
        if not awake:
            continue
        for _ in range(per):
            ram = bytearray(base)
            for k in range(5):
                struct.pack_into("<H", ram, (WORKING & MASK) + 2 * k, rng.randrange(0, 200))
            start = (px + rng.randrange(-0x200, 0x200), py - 0x640, pz + rng.randrange(-0x200, 0x200))
            a = ACTORS + ACTOR_STRIDE * rng.choice(awake)
            t = struct.unpack_from("<3i", ram, (a + 0x2C) & MASK)
            if "back" in more:                          # from the creature, at the player
                start, t = (t[0], t[1] - 0x640, t[2]), (px, py, pz)
            ang = vec_to_angles(t[0] - start[0], t[1] - 0x300 - start[1], t[2] - start[2])
            if "anywhere" in more:                      # into the walls as often as not
                ang = [rng.randrange(-0x80, 0x80) & 0xFFF, rng.randrange(0x1000), 0]
            d = movement.direction_from_angles(ang[0], ang[1])
            vel = struct.pack("<4h", *[_s16_((c * (speed or 0)) >> 12) for c in d], 0)
            if kind in FLAT:
                start = (start[0], start[1] + FLAT[kind], start[2])
                vel = vel[:2] + bytes(2) + vel[4:]
            point = struct.pack("<4i", *start, 0)
            struct.pack_into("<3H", ram, VIEW_ANGLES & MASK, ang[0] & 0xFFFF, ang[1] & 0xFFFF, 0)
            view = bytes(ram[VIEW_ANGLES & MASK:(VIEW_ANGLES & MASK) + 8])
            slot = (a - ACTORS) // ACTOR_STRIDE
            if "slot?" in more:
                slot = rng.choice((slot, slot, slot, 0xFE, 0xFF))
            sps = _spawns(0x42, FIRE_BALL if kind is None else kind, point,
                          [vel] + [view if v == "view" else slot if v == "slot?" else v
                                   for v in more if v not in ("back", "anywhere")])
            if speed is None:
                a1, point, args = _placed(ram, more, t)
                sps = _spawns(a1, kind, point, args)
            if rng.randrange(4) == 0:                       # water just under the path
                struct.pack_into("<i", ram, SURFACE & MASK, py - 0x640 - rng.randrange(0, 0x1F4))
            seed = rng.randrange(1 << 30)
            cpu = _game(bytes(ram))
            lcg = levelstate.Lcg(seed)
            cpu.hooks[RAND] = lambda c, lcg=lcg: lcg()
            g_calls = []
            cpu.hooks[SOUND_AT] = lambda c: 0
            cpu.hooks[hit.SKILL_PRACTICE] = lambda c, g=g_calls: g.append(("practice", c.r[4]))
            cpu.hooks[hit.STRONG_BLOW] = lambda c, g=g_calls: g.append(("strong",))
            cpu.hooks[hit.AWARD_EXP] = lambda c, g=g_calls: g.append(("exp", hit._s16(c.r[4])))
            cpu.hooks[hit.PLAYER_TAKE_HIT] = lambda c, g=g_calls: g.append(("player",))
            cpu.hooks[hook_at] = lambda c: None
            m = bytearray(ram)
            w = RamWorld(m, lv)
            m_calls = []
            r = hit.Ram(m)
            mlcg = levelstate.Lcg(seed)

            def attack_hit(code, flags, kind, strength, stat, pct, back, w=w, r=r,
                           m_calls=m_calls, mlcg=mlcg):
                struct.pack_into("<i", r.m, COLLIDE_ACTOR & MASK, w.collide_actor)
                pt = 0
                if back is not None:
                    pt = SCRATCH_POINT
                    struct.pack_into("<3i", r.m, pt & MASK, *[_s32(v) for v in back])
                hit.actor_attack_player(r, code, flags, SPELL_TABLE + RECORD * kind, strength,
                                        stat, pct, pt, mlcg, m_calls, lambda actor, dd: dd)
                m_calls[:] = [c if c[0] != "player" else ("player",) for c in m_calls]
            w.attack_hit = attack_hit

            def strike(point, near, radius, mode, edge, stat, att, scale, flags, rec, r=r,
                       m_calls=m_calls, mlcg=mlcg):
                strike_creatures(r, point, near, radius, mode, edge, stat, att, scale, flags, rec,
                                 mlcg, m_calls, lambda actor, dd: dd)
            w.strike_creatures = strike

            def hurt_player(point, a1, radius, mode, edge, attacks, effect, more_, scale, pct,
                            w=w, m_calls=m_calls):
                if strike_scale(point, radius, w.player, edge, scale, a1, mode) is not None:
                    m_calls.append(("player",))
            w.hurt_player = hurt_player
            mach = Machine(m, w, mlcg)
            try:
                for sp in sps:
                    game_spawn(cpu, *sp)
                for sp in sps:
                    mach.spawn(*sp)
                runs += 1
                ok = True
                for f in range(frames):
                    del g_calls[:], m_calls[:]
                    before = bytes(cpu.ram[oa:oa + ACTOR_STRIDE * ACTOR_N])
                    _call(cpu, DRIVER, [])
                    mach.driver()
                    bad = _differ(_slots(cpu.ram), _slots(m))
                    acts = bytes(cpu.ram[oa:oa + ACTOR_STRIDE * ACTOR_N]) == bytes(m[oa:oa + ACTOR_STRIDE * ACTOR_N])
                    if before != bytes(cpu.ram[oa:oa + ACTOR_STRIDE * ACTOR_N]):
                        hurt += 1
                    killed += sum(1 for c in g_calls if c[0] == "exp")
                    player += sum(1 for c in g_calls if c[0] == "player")
                    same = not bad and acts and g_calls == m_calls
                    _take_leftovers(cpu.ram, m)
                    nframes += 1
                    fgood += same
                    if not same and ok:
                        ok = False
                        if len(first) < 4:
                            first.append(f"  {os.path.basename(path)} frame {f}: " + (
                                f"slot {bad[0][0]} +{bad[0][1]:#x} game {bad[0][2]:#x} here {bad[0][3]:#x}"
                                if bad else "the creatures differ" if not acts
                                else f"calls {g_calls} / {m_calls}"))
                    if all(cpu.rd(SLOTS + STRIDE * k, 1) == 0xFF for k in range(COUNT)):
                        break
                good += ok
            except NotImplementedError:
                skipped += 1
                runs -= 1
    for line in first:
        print(line, file=out)
    print(f"  {name} end to end, the game's own collide_query, actor_attack_player "
          f"and actor_take_hit: {good} of {runs} runs, {fgood} of {nframes} frames with all "
          f"128 slots, all 200 creatures and every call alike; {hurt} frames a creature "
          f"was struck, {killed} killed" + (f", the player struck {player} times" if player else ""),
          file=out)
    return good == runs


def fire_world_check(out=sys.stdout, per=10, frames=60):
    """The fire ball in the game's own world: effect_spawn, effect_driver and
    collide_query the game's, over every snapshot, each ball sent at one of
    its creatures or anywhere; only the sound and actor_attack_player stood
    in for. All 128 slots every frame, and every hit -- what it met, the
    creature collide_query left at 0x801e648c, the strength and the point."""
    import random
    import memcard
    import levelstate
    rng = random.Random(0xF1E1D)
    runs = good = nframes = fgood = skipped = creature_hits = 0
    first = []
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        o = SLOTS & MASK
        base[o:o + STRIDE * COUNT] = bytes(STRIDE * COUNT)
        for k in range(COUNT):
            base[o + STRIDE * k] = 0xFF
        lv = base[0x8018FAD9 & MASK]
        px, py, pz = struct.unpack_from("<3i", base, PLAYER_POS & MASK)
        awake = [k for k in range(ACTOR_N) if base[(ACTORS + ACTOR_STRIDE * k + 9) & MASK] == 1]
        for _ in range(per):
            ram = bytearray(base)
            for k in range(5):
                struct.pack_into("<H", ram, (WORKING & MASK) + 2 * k, rng.randrange(0, 200))
            start = (px + rng.randrange(-0x200, 0x200), py - 0x640, pz + rng.randrange(-0x200, 0x200))
            if awake and rng.randrange(3):
                a = ACTORS + ACTOR_STRIDE * rng.choice(awake)
                t = struct.unpack_from("<3i", ram, (a + 0x2C) & MASK)
                ang = vec_to_angles(t[0] - start[0], t[1] - 0x300 - start[1], t[2] - start[2])
                pitch, yaw = ang[0], ang[1]
            else:
                pitch, yaw = rng.randrange(-0x100, 0x100) & 0xFFF, rng.randrange(0x1000)
            d = movement.direction_from_angles(pitch, yaw)
            vel = struct.pack("<4h", *[_s16_((c * 0x384) >> 12) for c in d], 0)
            point = struct.pack("<4i", *start, 0)
            sp = (0xA, 0x42, FIRE_BALL, point, [vel])
            cpu = _game(bytes(ram))
            g_hits = []
            cpu.hooks[SOUND_AT] = lambda c: 0

            def hit(c, g_hits=g_hits):
                sp_ = c.r[29]
                pt = c.rd(sp_ + 0x3C, 4)
                code = c.r[4]
                g_hits.append([code, c.r[5] & 0xFF, c.r[7], c.rd(sp_ + 0x10, 4),
                               c.rd(sp_ + 0x14, 4), [c.rd(pt + 4 * i, 4) for i in range(3)],
                               _s32(c.rd(COLLIDE_ACTOR, 4)) if code & 0x10 else None])
                return 0
            cpu.hooks[ATTACK_HIT] = hit
            m = bytearray(ram)
            w = RamWorld(m, lv)
            w.hits = []

            def attack_hit(code, flags, kind, strength, stat, pct, back, w=w):
                w.hits.append([code, flags, strength, stat, pct, [v & 0xFFFFFFFF for v in back],
                               w.collide_actor if code & 0x10 else None])
            w.attack_hit = attack_hit
            mach = Machine(m, w, levelstate.Lcg())
            try:
                game_spawn(cpu, *sp)
                mach.spawn(*sp)
                runs += 1
                ok = True
                for f in range(frames):
                    del g_hits[:], w.hits[:]
                    _call(cpu, DRIVER, [])
                    mach.driver()
                    bad = _differ(_slots(cpu.ram), _slots(m))
                    same = not bad and g_hits == w.hits
                    creature_hits += sum(1 for h in g_hits if h[6] is not None and h[6] != -1)
                    nframes += 1
                    fgood += same
                    if not same and ok:
                        ok = False
                        if len(first) < 4:
                            first.append(f"  {os.path.basename(path)} frame {f}: " + (
                                f"slot {bad[0][0]} +{bad[0][1]:#x} game {bad[0][2]:#x} here {bad[0][3]:#x}"
                                if bad else f"hits {g_hits} / {w.hits}"))
                    if all(cpu.rd(SLOTS + STRIDE * k, 1) == 0xFF for k in range(COUNT)):
                        break
                good += ok
            except NotImplementedError:
                skipped += 1
                runs -= 1
    for line in first:
        print(line, file=out)
    print(f"  the fire ball in the game's own world (collide_query and its creatures): "
          f"{good} of {runs} runs, {fgood} of {nframes} frames with all 128 slots and every "
          f"hit alike, {creature_hits} of them on a creature" + (
              f" ({skipped} splashing on water, not in the machine)" if skipped else ""), file=out)
    return good == runs


def fire_check(out=sys.stdout, per=8, frames=60, kind=FIRE_BALL, speed=0x384,
               name="the fire ball", more=()):
    """The fire ball (kind 0) against the game's own effect_spawn and
    effect_driver over every snapshot, collide_query, its sound and
    actor_attack_player stood in for on both sides: all 128 slots every frame,
    every query asked and every hit handed over. The stand-in's water under
    the path stays, which the game's collide_query rewrites, so a splash in
    flight is checked here; another bolt by `kind` and the rest as in
    SPELLS_SENT."""
    import random
    import memcard
    import levelstate
    import mipsrun
    rng = random.Random(0xF12E)
    runs = good = nframes = fgood = skipped = 0
    first = []
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        o = SLOTS & MASK
        base[o:o + STRIDE * COUNT] = bytes(STRIDE * COUNT)
        for k in range(COUNT):
            base[o + STRIDE * k] = 0xFF
        px, py, pz = struct.unpack_from("<3i", base, PLAYER_POS & MASK)
        layer = struct.unpack_from("<H", base, LAYER_OFFSET & MASK)[0]
        for _ in range(per):
            ram = bytearray(base)
            for k in range(5):
                struct.pack_into("<H", ram, (WORKING & MASK) + 2 * k, rng.randrange(0, 200))
            yaw = rng.randrange(0x1000)
            point = struct.pack("<4i", px + rng.randrange(-0x400, 0x400), py - 0x640,
                                pz + rng.randrange(-0x400, 0x400), 0)
            d = movement.direction_from_angles(rng.randrange(-0x100, 0x100) & 0xFFF, yaw)
            vel = struct.pack("<4h", *[_s16_((c * speed) >> 12) for c in d], 0)
            view = bytes(ram[VIEW_ANGLES & MASK:(VIEW_ANGLES & MASK) + 8])
            sp = (0xA, 0x42, kind, point, [vel] + [view if v == "view" else v for v in more])
            if rng.randrange(3) == 0:                       # water just under the path
                struct.pack_into("<i", ram, SURFACE & MASK, py - 0x640 - rng.randrange(0, 0x1F4))
            cpu = _game(bytes(ram))
            g_asked, g_hits = [], []

            def query(c, g_asked=g_asked):
                sp_ = c.r[29]
                x, y, z = c.r[4], c.r[5], c.r[6]
                g_asked.append([x, y, z, c.r[7], c.rd(sp_ + 0x10, 4), c.rd(sp_ + 0x14, 4)])
                return StandIn.answer(mipsrun.s32(x), mipsrun.s32(y), mipsrun.s32(z))
            cpu.hooks[COLLIDE_QUERY] = query
            cpu.hooks[SOUND_AT] = lambda c: 0

            def hit(c, g_hits=g_hits):
                sp_ = c.r[29]
                pt = c.rd(sp_ + 0x3C, 4)
                g_hits.append([c.r[4], c.r[5] & 0xFF, c.r[7], c.rd(sp_ + 0x10, 4),
                               c.rd(sp_ + 0x14, 4), [c.rd(pt + 4 * i, 4) for i in range(3)]])
                return 0
            cpu.hooks[ATTACK_HIT] = hit
            m = bytearray(ram)
            w = StandIn(layer)
            mach = Machine(m, w, levelstate.Lcg())
            try:
                game_spawn(cpu, *sp)
                mach.spawn(*sp)
                runs += 1
                ok = True
                for f in range(frames):
                    del g_asked[:], g_hits[:], w.asked[:], w.hits[:]
                    _call(cpu, DRIVER, [])
                    mach.driver()
                    bad = _differ(_slots(cpu.ram), _slots(m))
                    same = not bad and g_asked == w.asked and g_hits == w.hits
                    nframes += 1
                    fgood += same
                    if not same and ok:
                        ok = False
                        if len(first) < 4:
                            first.append(f"  {os.path.basename(path)} frame {f}: " + (
                                f"slot {bad[0][0]} +{bad[0][1]:#x} game {bad[0][2]:#x} here {bad[0][3]:#x}"
                                if bad else f"queries {g_asked} / {w.asked}, hits {g_hits} / {w.hits}"))
                    if all(cpu.rd(SLOTS + STRIDE * k, 1) == 0xFF for k in range(COUNT)):
                        break
                good += ok
            except NotImplementedError:
                skipped += 1
                runs -= 1
    for line in first:
        print(line, file=out)
    print(f"  {name}, the game's own effect_spawn and effect_driver over the "
          f"snapshots: {good} of {runs} runs, {fgood} of {nframes} frames with all 128 "
          f"slots, every query and every hit alike" + (f" ({skipped} splashing on water, "
                                                       f"not in the machine)" if skipped else ""),
          file=out)
    return good == runs


def aim_check(out=sys.stdout, n=600):
    """effect_aim, the game's, against aim() on random creatures, targets and
    points: the velocity and the yaw it answers."""
    import random
    import memcard
    rng = random.Random(0xA1)
    ram = open(memcard._snapshots()[0], "rb").read()
    cpu = _game(ram)
    actor, target, point, vel = SCRATCH, SCRATCH + 0x100, SCRATCH + 0x120, SCRATCH + 0x140
    ok = 0
    first = None
    for _ in range(n):
        ang = (rng.randrange(0x1000), rng.randrange(0x1000), 0)
        t = [rng.randrange(0, 0x28000), rng.randrange(-0x8000, 0x1000), rng.randrange(0, 0x28000)]
        p = [t[0] + rng.randrange(-0x2000, 0x2000), t[1] + rng.randrange(-0x2000, 0x1000),
             t[2] + rng.randrange(-0x2000, 0x2000)]
        speed = rng.choice((0x12C, 0x100, 0x200, rng.randrange(1, 0x400)))
        spread = rng.choice((0x400, 0x200, 0x800))
        cpu.wr(actor + 0x40, 2, ang[0])
        cpu.wr(actor + 0x42, 2, ang[1])
        for i in range(3):
            cpu.wr(target + 4 * i, 4, t[i] & 0xFFFFFFFF)
            cpu.wr(point + 4 * i, 4, p[i] & 0xFFFFFFFF)
        cpu.wr(target + 12, 4, 0)
        yaw = _s16_(_call(cpu, AIM, [actor, target, speed, point], [vel, -1, spread, 1]) & 0xFFFF)
        got = [_s16_(cpu.rd(vel + 2 * i, 2)) for i in range(3)]
        want, wyaw = aim(ang, t, speed, p, -1, spread)
        if got == want and yaw == wyaw:
            ok += 1
        elif first is None:
            first = f"  angles {ang} target {t} point {p} speed {speed:#x}: game {got} {yaw:#x}, here {want} {wyaw:#x}"
    if first:
        print(first, file=out)
    print(f"  effect_aim, the game's own, on {n} random creatures, targets and points: "
          f"{ok} of {n} velocities and yaws as aim() makes them", file=out)
    return ok == n

def parts():
    """The checks one at a time, by name, for tools/build.py to run side by
    side: the spores, effect_aim, the machine, the healing spells, the fire
    ball against stand-ins and in the world, Seath's sword's spell against the
    stand-ins (its splash in flight), and each attacking spell sent."""
    out = [("spores", lambda: check(verbose=False)), ("aim", aim_check),
           ("machine", machine_check), ("magic", magic_check), ("fire", fire_check),
           ("fire_seaths", lambda: fire_check(kind=SEATHS, speed=0x384, name="Seath's sword's",
                                              more=("view",))),
           ("fire_world", fire_world_check)]
    for kind, speed, name, more, n in SPELLS_SENT:
        tag = f"{kind:#x}" + "".join("-" + v for v in more if v in ("back", "anywhere"))
        out.append((tag, lambda kind=kind, speed=speed, name=name, more=more, n=n:
                    fire_hit_check(sys.stdout, 6, n, kind, speed, name, more)))
    return out


if __name__ == "__main__":
    if "--parts" in sys.argv:                       # the names --part takes
        print(" ".join(name for name, _f in parts()))
        sys.exit(0)
    if "--part" in sys.argv:
        want = sys.argv[sys.argv.index("--part") + 1]
        sys.exit(0 if dict(parts())[want]() else 1)
    good = check(verbose="--check" not in sys.argv)
    good = aim_check() and good
    good = machine_check() and good
    good = magic_check() and good
    good = fire_check() and good
    good = fire_check(kind=SEATHS, speed=0x384, name="Seath's sword's", more=("view",)) and good
    good = fire_world_check() and good
    good = spell_hit_check() and good
    sys.exit(0 if good else 1)

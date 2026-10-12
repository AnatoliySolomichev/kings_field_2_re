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
    """0x80016fb4: the length less own, or FAR."""
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
    return ln - own


def strike_scale(p, radius, player, edge=EDGE, scale=0x1000):
    """effect_hurt_player (0x8002b114) with mode 0x8000 and near 0: None
    when it misses, else the scale it hands player_take_hit."""
    d = in_range_3d(p, radius, player)
    if d < 0:
        return None
    if edge == 0x1000:
        return scale
    lo = movement.trunc(d << 12, radius) & 0xFFFF
    f = (0x1000 - ((lo * (0x1000 - edge)) >> 12)) & 0xFFFF
    return (scale * f) >> 12


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
            vel = struct.pack("<4h", *[_s16_((c * 0x384) >> 12) for c in d], 0)
            w = StandIn(7)
            log = []
            ask = w.collide_query

            def cq(x, y, z, r, h, flags, ask=ask, log=log, w=w):
                v = ask(x, y, z, r, h, flags)
                log.append([_s32(x), _s32(y), _s32(z), r, h & 0xFFFFFFFF, flags, v, w.layer_offset])
                return v
            w.collide_query = cq
            mach = Machine(m, w)
            try:
                mach.spawn(0xA, 0x42, FIRE_BALL, point, [vel])
                frames = []
                for _f in range(60):
                    del log[:], w.hits[:]
                    mach.driver()
                    frames.append({"q": [list(x) for x in log],
                                   "hits": [[h[0], h[1], h[2], h[3], h[4], [_s32(v) for v in h[5]]]
                                            for h in w.hits],
                                   "md5": hashlib.md5(_slots(m).hex().encode()).hexdigest()})
                    if all(m[o + STRIDE * k] == 0xFF for k in range(COUNT)):
                        break
            except NotImplementedError:
                continue
            fires.append({"label": f"{os.path.basename(path)[:-4]} fire ball", "layer0": 7,
                          "fields": dict({"px": px}, **{f"w{k}": working[k] for k in range(5)}),
                          "spawns": [[0xA, 0x42, FIRE_BALL, point.hex(), [{"b": vel.hex()}]]],
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
WORKING = 0x801B2526             # the five working skills
SURFACE = 0x801E647C             # surface_plane_18, the water's top
COLLIDE_QUERY, ATTACK_HIT, SOUND_AT = 0x80033F38, 0x800533E8, 0x80015688
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

    # effect_alloc (0x80053b64): the first slot from the top whose +0 is 0xff
    def alloc(self):
        for k in range(COUNT):
            if self.u8(SLOTS + STRIDE * k) == 0xFF:
                return SLOTS + STRIDE * k
        return 0

    def spawn(self, a0, a1, kind, point, args):
        """effect_spawn(a0, a1, kind, point, ...): `point` the 16 bytes a3
        points at, or None; `args` the stack arguments from the fifth on, a
        pointer as the bytes it points at. The slot, or 0 when none is free."""
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
        if kind >= 0x82:
            self.w8(s, 0xFF)
            return s
        arm = {0x1F: self._spawn_1f, 0x22: self._spawn_22, 0x23: self._spawn_23,
               0x24: self._spawn_24, 0x26: self._spawn_26, TRAIL: self._spawn_6f,
               0x17: self._spawn_17, 0x19: self._spawn_19, 0x1A: self._spawn_1a,
               0x1B: self._spawn_1b, 0x1C: self._spawn_1c, 0x1E: self._spawn_1e,
               FIRE_BALL: self._spawn_00}.get(kind)
        if arm is None:
            raise NotImplementedError(f"effect_spawn's arm {kind:#x}")
        arm(s, args)
        return s

    def _spawn_00(self, s, args):           # 0x80053e98, the fire ball
        self.particle(s, 9, 0x1000, 5)
        self.w16(s + 0xE, 0x40)
        self.w16(s + 0x10, 0x32)            # sub_800532d4's sound between
        self.w8(s + 0xD, 1)

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
               FIRE_BALL: self._tick_00}.get(kind)
        if arm is None:
            raise NotImplementedError(f"effect_tick's arm {kind:#x}")
        arm(s)

    def _puff(self, s, b, e):
        """The puff a bolt leaves at its point, two fifths of its velocity:
        effect_spawn(10, 0, 0x6f, point, v, 0xe10, -0x80, 5, 0x16, 0, b, e).
        The velocity's fourth halfword is whatever the stack held: not kept."""
        v = [div5(2 * self.s16(s + o)) for o in (0x38, 0x3A, 0x3C)]
        self.spawn(10, 0, TRAIL, self.get(s + 0x18, 16),
                   [struct.pack("<4h", *v, 0)] + TRAIL_ARGS[:5] + [b, e])

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
            back = [self.s32(s + o) - (self.s16(s + v) << 3)
                    for o, v in ((0x18, 0x38), (0x1C, 0x3A), (0x20, 0x3C))]
            self.w.attack_hit(hit, self.u8(s), self.u8(s + 1), 0x1388,
                              self.magic_strength(s), self.u8(s + 6), back)
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

    def splash(self, point, n, spread, a, b, c):   # 0x80056580
        """Splashes on the water when the point is within 0x1f4 under its
        surface (0x801e647c); not in the machine yet."""
        y, surf = self.s32(point + 4), self.s32(SURFACE)
        if y < surf or surf + 0x1F4 < y:
            return 0
        raise NotImplementedError("the fire ball's splash (kind 0x70)")

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
                       [vel, 0x2BC, -0x1E, 0xA, 0x26, -0xA, b, e])
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
        effect_hurt_player with the kind's record; bit 2 the creatures."""
        s = self.u32(CURRENT)
        rec = self.u32(CURRENT_REC)
        if self.u8(s) & 1:
            self.w.hurt_player([self.s32(point), self.s32(point + 4), self.s32(point + 8)],
                               a1, radius, mode, edge & 0xFFFF,
                               [self.u16(rec + o) for o in (6, 8, 0xA)], self.u8(rec + 4),
                               [self.u16(rec + o) for o in (0xC, 0xE, 0x10, 0x12, 0x14)],
                               scale & 0xFFFF, self.u8(s + 6))
        if self.u8(s) & 2:
            raise NotImplementedError("effect_strike on the creatures (0x8004ceac)")

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

    def collide_query(self, x, y, z, r, h, flags):
        import collision
        mask = 0
        cx, cz = x >> 11, z >> 11
        inside = 0 <= x <= movement.GRID_MAX and 0 <= z <= movement.GRID_MAX
        if flags & 1:
            mask, _cur = movement.query(self.lvl, x, y, z, radius=r, body=h)
            ymid = y - (((h << 4) & 0xFFFFFFFF) >> 5)
            self.layer_offset = collision.layer_of(self.lvl.cell(cx, cz), ymid) if inside else 0
        if flags & 6:
            raise NotImplementedError("collide_query's fence and creatures")
        if not inside or not self.lvl.cell(cx, cz)[2] & 0xFC:
            return mask
        if flags & 0x10 or flags & 0x40:
            raise NotImplementedError("collide_query's creatures")
        if flags & 0x20 and movement.object_collide(self.objs, x, y, z, r, h) is not None:
            mask |= 0x20
        if flags & 0x80 and movement.in_range(self.player, x, y, z, r + 0x320, 0x6A4, h) != -1:
            mask |= 0x80
        return mask

    def hurt_player(self, point, a1, radius, mode, edge, attacks, effect, more, scale, pct):
        self.hurts.append([point[0], point[1], point[2], a1, radius, mode, edge,
                           list(attacks), effect, list(more), scale, pct])


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


def _differ(a, b):
    """The bytes of two slot arrays that differ, leaving out a puff's +0x3e
    and +0x24 -- the stack's leftovers its velocity and a sparkle's point
    carry."""
    bad = []
    for k in range(COUNT):
        x, y = a[k * STRIDE:(k + 1) * STRIDE], b[k * STRIDE:(k + 1) * STRIDE]
        if x == y:
            continue
        for i in range(STRIDE):
            if x[i] != y[i] and not (i in (0x3E, 0x3F, 0x24, 0x25, 0x26, 0x27)
                                     and x[1] == TRAIL and x[0] != 0xFF):
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

    def __init__(self, layer):
        self.layer_offset = layer
        self.asked = []
        self.hits = []

    @staticmethod
    def answer(x, y, z):
        return (0, 0, 0, 0, 0, 0, 1, 0x10, 0x20, 0, 0, 0)[((x ^ y ^ z) >> 6) % 12]

    def collide_query(self, x, y, z, r, h, flags):
        self.asked.append([x & 0xFFFFFFFF, y & 0xFFFFFFFF, z & 0xFFFFFFFF, r, h & 0xFFFFFFFF, flags])
        return self.answer(_s32(x), _s32(y), _s32(z))

    def attack_hit(self, code, flags, kind, strength, stat, pct, back):
        self.hits.append([code, flags, strength, stat, pct, [v & 0xFFFFFFFF for v in back]])


def fire_check(out=sys.stdout, per=8, frames=60):
    """The fire ball (kind 0) against the game's own effect_spawn and
    effect_driver over every snapshot, collide_query, its sound and
    actor_attack_player stood in for on both sides: all 128 slots every frame,
    every query asked and every hit handed over."""
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
            vel = struct.pack("<4h", *[_s16_((c * 0x384) >> 12) for c in d], 0)
            sp = (0xA, 0x42, FIRE_BALL, point, [vel])
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
    print(f"  the fire ball, the game's own effect_spawn and effect_driver over the "
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

if __name__ == "__main__":
    good = check(verbose="--check" not in sys.argv)
    good = aim_check() and good
    good = machine_check() and good
    good = magic_check() and good
    good = fire_check() and good
    sys.exit(0 if good else 1)

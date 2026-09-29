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
    """effectcheck.json: every spore bp26 recorded, from its first frame, with
    the player where the log has them, for selftest.gd -- each frame's life,
    height, scale, growth and strike (-1 for a miss), to where it goes."""
    import json
    fx, _hurt = load()
    lvl = movement.level(0)
    runs, seen = [], set()
    for i, f in enumerate(fx):
        for k, e in f["slots"].items():
            if e["kind"] != SPORE or e["life"] != 0x32 or (k, f["vb"]) in seen:
                continue
            seen.add((k, f["vb"]))
            m = dict(e, scale=list(e["scale"]), vel=list(e["vel"]))
            start = dict(m, scale=list(m["scale"]), vel=list(m["vel"]))
            path, frames = [], []
            for g in fx[i:]:
                hit = tick_spore(m, lvl, g["p"])
                path.append(list(g["p"]))
                frames.append([m["life"], m["y"], *m["scale"], m["count"],
                               -1 if hit is None else hit,
                               1 if m.get("freed") else 0])
                if m.get("freed"):
                    break
            runs.append({"start": {kk: start[kk] for kk in
                                   ("x", "y", "z", "life", "scale", "count",
                                    "grace", "half", "pct", "vel")},
                         "path": path, "frames": frames})
    p = os.path.join(out_dir, "effectcheck.json")
    with open(p, "w") as fh:
        json.dump({"_note": "the spores of emu/bp26.lua through tools/effects.py",
                   "runs": runs}, fh, separators=(",", ":"))
    return p


if __name__ == "__main__":
    sys.exit(0 if check(verbose="--check" not in sys.argv) else 1)

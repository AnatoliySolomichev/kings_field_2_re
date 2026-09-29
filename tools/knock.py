#!/usr/bin/env python3
"""Knock-back: what a blow does to the player after the HP, and the recording
that holds it to account.

    python3 tools/knock.py            the check, frame by frame where it differs
    python3 tools/knock.py --check    the check alone
    python3 tools/knock.py 14 50      the push, shake and length of a 14 on 50 HP

## The blow

`actor_blow` (`0x8004d254`) is opcode 4's strike: `(0, rec+0xe, rec+0xf,
rec+0x10)` for the nearest, the reach, the lift and the arc, and on the stack
`rec+0x12`, `+0x14`, `+0x16` -- slash, blow, stab -- and `rec+0x11`. It hands
`player_take_hit` (`0x8002ab18`) **three** attacks in a0..a2 and `rec+0x11` in
a3, the five magic types zero, the scales 0x1000 and 0xa, and a pointer to the
creature's position lifted by `rec+0xf << 5`. **a3 is not an attack.** The
routine calls `damage_of_type` eight times -- a0, a1, a2 and arg4..arg8, against
the eight halves at `0x801b254a`..`0x801b2558` -- and a3 goes to a seven-arm
switch on its low nibble (the effects: `0x801b2560`, `0x801b2564`, the resisted
one at `0x801b255a`/`0x801b255c`, `0x801b2568`, `turn_slow_timer`, a cure, MP
drain) and on to `apply_damage` as its third argument. Its 0x40 and 0x80 bits
are read there.

## apply_damage (0x8002a6f4)

    nothing in player state 0x11, nothing for a damage of 0
    hp  = max(hp - dmg, 0)
    s2  = min((dmg << 12) / hp_max, 0x3b6)           the hit as a share of the HP
    s1  = s2 >> 2
    with an attacker:
      angles from it to the player, its Y raised by 0x352 (sub_80016c90:
        yaw = vec_angle(dx, dz), pitch = -vec_angle(dy, vec_length_2d) & 0xfff)
      s1  = max(s1, 0x50); kind & 0x40: min(s1 * 5, 0x258), else min(s1, 0x1c2)
      push = direction_from_angles(pitch, yaw) * s1 >> 12, its Y held to +-0xc8
    n   = max((0x514 - (s2 >> 1)) >> 2, 0x46)
    hp now 0          player_throw(push); 0x801b2658 = 0xdac, 0x801b265a = n
    no attacker       0x801b2658 = 0xdac, 0x801b265a = n and nothing else
    else  shake = isqrt(s2 << 2) held to 0x10..0x2a, doubled for kind & 0x40
      kind & 0x80     (0, 0, -shake or +shake on rand() < 0x4001) and
                      player_knock_hard (0x800309c8): state 0x12
      else            one of eight by ((yaw - view yaw 0x801b260a) + 0x100) >> 9:
                      (-s,0) (-s,s) (0,s) (s,s) (s,0) (s,-s) (0,-s) (-s,-s)
                      as (pitch, roll), and player_knock (0x80030908)

`player_knock`, unless the player is in state 7, 8 or 9: state 0x10, the push
into `player_velocity` (`0x801b266c`), the shake into the tilt velocity
(`0x801b2674`), vertical state 0x40 with the push's Y as its velocity.

## State 0x10 (the controller's arm at 0x80031b98)

    player_turn, player_look, player_walk          the player still steers
    player_velocity.y = 1
    player_move                                    the push, below
    0x8003047c                                     the tilt spring
    all three tilts 0: 0x8003078c                  state 0, both speeds 0, the
                                                   tilts and the angle offsets 0
    player_vertical

`player_move` (`0x8002f320`), with the collision at the player's radius, body
and 0x31:

    n = p + v                          clear: commit
    n.y = p.y                          clear: v.y = 1, shorten by 0x20, commit
    anything outside 0x205, or the surface more than 0x100 above the feet:
                                       stay, v unchanged
    else n.y = surface                 shorten by 0x38, commit
    shorten by c: L = vec_length_2d(v.x, v.z); L <= c: v = 0 and stay,
                  else v.xz = v.xz * (L - c) / L
    commit: p = n, v.y += 0x20

so on the ground the push loses 0x20 of length a frame and the player keeps
the step it had -- the shortened velocity is next frame's.

The tilt spring, per axis (`0x80016168` with target 0, 8 and 4):

    within 4 of the target and |vel| <= 8:  vel = target - tilt   (snap)
    else  vel -+= 8 towards the target, then 4 of friction off it
    tilt += vel

The view adds the tilts to its angles (`0x80032028`): pitch at `0x801b2608` is
`player_pitch + tilt.x + 0x801b2620 + 0x801b2628`, the yaw adds `tilt.y`, the
roll at `0x801b260c` adds `tilt.z`. A shake of 0x2a settles in **28 frames**;
0x10 in 4, 0x20 in 16.

## Checked

`emu/bp16.lua`'s recording has two knock-backs, both from level 0's first
kind (blow 40, stab 30), both 28 frames in state 0x10 -- what the spring gives
a shake of 0x2a, the cap every hit of 12 or more on 50 HP reaches. The landing
out of state 0x40 falls through into 0x50 in the same frame: 15 -> -285 with a
crouch of 4 in one, 22 -> -278 and 6 in the other, then 0 and 0, as
`movement.walk_step` now has it. The first push, where no button is held, is
reproduced frame by frame from its first step; the second is predicted from the
creature's logged position before it happens.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movement                                                      # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

SHARE_CAP = 0x3B6        # 0x8002a790
PUSH_MIN = 0x50          # 0x8002a7e4
PUSH_CAP = 0x1C2         # 0x8002a814
PUSH_CAP_HEAVY = 0x258   # 0x8002a800
PUSH_Y = 0xC8            # 0x8002a848
RAISE = 0x352            # 0x8002a7cc: the attacker's point, raised
SHAKE_MIN, SHAKE_MAX = 0x10, 0x2A
FLASH = 0xDAC            # 0x801b2658
FLASH_BASE, FLASH_MIN = 0x514, 0x46
HEAVY, HARD = 0x40, 0x80
SHAKES = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))
SPRING_ACCEL, SPRING_FRICTION = 8, 4      # 0x80030488, 0x800304b0
CUT, CUT_STEP = 0x20, 0x38                # 0x8002f4a0, 0x8002f590
STEP = 0x100                              # 0x8002f578
GRAVITY = 0x20                            # 0x8002f408
SOFT = 0x205                              # what player_move lets it step onto


def s16(v):
    return movement.s16(v)


def vec_length_2d(a, b):
    """0x80016c08: through the game's own root, not a true one."""
    return movement.game_isqrt((a >> 3) ** 2 + (b >> 3) ** 2) << 3


def angles(dx, dy, dz):
    """sub_80016c90: (pitch, yaw) of a vector, 0x1000 to the turn."""
    yaw = movement.vec_angle(dx, dz)
    pitch = (-movement.vec_angle(dy, vec_length_2d(dx, dz))) & 0xFFF
    return pitch, yaw


def apply_damage(hp, hp_max, dmg, player=None, attacker=None, kind=0,
                 view_yaw=0, rand=None, state=0):
    """apply_damage's arithmetic. Returns a dict: hp, and when it knocks,
    push (x, y, z), shake (pitch, roll), state (0x10 or 0x12), flash."""
    if state == 0x11 or dmg == 0:
        return {"hp": hp}
    left = max(hp - dmg, 0)
    s2 = min(movement.trunc(dmg << 12, hp_max), SHARE_CAP)
    s1 = s2 >> 2
    push = (0, 0, 0)
    yaw = 0
    if attacker is not None:
        pitch, yaw = angles(player[0] - attacker[0],
                            player[1] - (attacker[1] + RAISE),
                            player[2] - attacker[2])
        s1 = max(s1, PUSH_MIN)
        s1 = min(s1 * 5, PUSH_CAP_HEAVY) if kind & HEAVY else min(s1, PUSH_CAP)
        d = movement.direction_from_angles(pitch, yaw)
        push = [s16((c * s16(s1)) >> 12) for c in d]
        push[1] = max(-PUSH_Y, min(PUSH_Y, push[1]))
        push = tuple(push)
    n = max((FLASH_BASE - (s2 >> 1)) >> 2, FLASH_MIN)
    out = {"hp": left, "flash": (FLASH, n), "push": push}
    if left == 0:                        # player_throw (0x80030a6c): state
        out["thrown"] = True             # 0x11 with the push as the velocity
        out["state"], out["shake"] = 0x11, (0, 0)
        return out
    if attacker is None:
        return out
    s = max(SHAKE_MIN, min(SHAKE_MAX, movement.game_isqrt(s2 << 2)))
    if kind & HEAVY:
        s <<= 1
    if kind & HARD:
        out["shake"] = (0, -s if rand() < 0x4001 else s)
        out["state"] = 0x12
    else:
        i = (((yaw - s16(view_yaw)) + 0x100) >> 9) & 7
        out["shake"] = (SHAKES[i][0] * s, SHAKES[i][1] * s)
        out["state"] = 0x10
    return out


def fall_damage(v):
    """0x8002ef80: a landing at 0x1e0 or faster costs t^3 / 118000, t = v^2 >>
    12 -- the multiply by 0x8e2e0727 and the shift by 16 are that division."""
    t = (v * v) >> 12
    c = t * t * t
    c = (c & 0xFFFFFFFF) - (0x100000000 if c & 0x80000000 else 0)
    hi = (c * (0x8E2E0727 - 0x100000000)) >> 32
    return ((hi + c) >> 16) - (c >> 31)


def facing_test(a, b, tol):
    d = (a - b) & 0xFFF
    return d <= tol or d >= 0x1000 - tol


def spring(target, cur, vel, accel=SPRING_ACCEL, friction=SPRING_FRICTION):
    """0x80016168: the velocity that takes `cur` towards `target`."""
    if facing_test(target, cur, accel >> 1) and -accel <= vel <= accel:
        return target - cur
    if cur != target:
        vel += -accel if ((cur - target) & 0xFFF) < 0x801 else accel
    if vel > 0:
        return vel - friction
    if vel < 0:
        return vel + friction
    return vel


def tilt_step(tilt, vel):
    """0x8003047c on the three axes; returns the new (tilt, vel)."""
    vel = [s16(spring(0, s16(t), v)) for t, v in zip(tilt, vel)]
    tilt = [s16(t + v) for t, v in zip(tilt, vel)]
    return tilt, vel


def settle(shake):
    """How many frames a shake of (pitch, roll) keeps the player in 0x10."""
    tilt, vel = [0, 0, 0], [shake[0], 0, shake[1]]
    n = 0
    while True:
        n += 1
        tilt, vel = tilt_step(tilt, vel)
        if tilt == [0, 0, 0]:
            return n


def player_move(lvl, p, v, actors=None):
    """0x8002f320. Returns (position, velocity, moved)."""
    x, y, z = p
    vx, vy, vz = v
    n = [x + vx, y + vy, z + vz]
    mask, surf, _o = movement.query_all(lvl, *n, actors=actors)
    if mask:
        n[1] = y
        mask, surf, _o = movement.query_all(lvl, *n, actors=actors)
        cut = CUT
        if mask == 0:
            vy = 1
        elif mask & ~SOFT or surf + STEP < y:
            return p, (vx, vy, vz), False
        else:
            n[1] = surf
            cut = CUT_STEP
        length = vec_length_2d(vx, vz)
        if not cut < length:
            return p, (0, vy, 0), False
        vx = movement.trunc(vx * (length - cut), length)
        vz = movement.trunc(vz * (length - cut), length)
    return tuple(n), (vx, s16(vy + GRAVITY), vz), True


def frame(lvl, r, nxt, v):
    """One frame of state 0x10 from the logged `r` towards `nxt`: the walk,
    player_move with v.y = 1, and player_vertical. Returns (position, v).

    The facing and the speeds the walk used are the ones logged at the next
    frame's start -- except on the frame the state ends, whose 0x8003078c
    zeroes both speeds after the walk; that frame ramps them itself."""
    import replay
    fwd, stf = nxt["fwd"], nxt["stf"]
    if nxt["pst"] != 0x10:
        B = replay.BIND
        fwd = movement.accelerate(r["fwd"], r["btn"] & B["forward"],
                                  r["btn"] & B["back"], r["max"])
        stf = movement.accelerate(r["stf"], r["btn"] & B["strafe_pos"],
                                  r["btn"] & B["strafe_neg"], r["max"], 2)
    # player_horizontal takes no step up outside player state 0 (0x8002e5cc)
    p = replay.step_horizontal(lvl, r["p"], nxt["ang"], fwd, stf, r.get("act"),
                               state=r["pst"])
    p, v, _moved = player_move(lvl, p, (v[0], 1, v[2]), r.get("act"))
    p, _st, _vv = movement.walk_step(lvl, p, 0, 0, r["vst"], r["vv"], r["mag"])
    return p, v


_RECS = {}


def onset(r, lv=0):
    """The push at the first frame of a knock-back: the logged velocity when
    the log has it (bp16's pv=), else apply_damage's from the creature in
    r's act= that struck, with the damage a fresh character takes from it;
    None when neither is there."""
    if r.get("pv"):
        return r["pv"]
    if lv not in _RECS:
        _RECS[lv] = strike_records(lv)
    att, rec = _attacker(r, _RECS[lv])
    if att is None:
        return None
    return apply_damage(50, 50, 14, r["p"], att, rec[0x11], r["ang"])["push"]


def episodes(rows):
    """The runs of frames in player state 0x10, with the frame before."""
    out, cur = [], None
    for i, r in enumerate(rows):
        if r["pst"] == 0x10:
            if cur is None:
                cur = [rows[i - 1]] if i else []
            cur.append(r)
        elif cur is not None:
            cur.append(r)
            out.append(cur)
            cur = None
    return out


def _attacker(r, recs):
    """The creature in r's act= that struck, and its record: the one running
    opcode 4 (+0xe) with the player inside its record's reach (rec+0xe << 6
    from its point raised by rec+0xf << 5, actor_blow's in_range)."""
    for a in r.get("act") or ():
        rec = recs.get(a["slot"])
        if rec is None or a["b0e"] != 4:
            continue
        ax, ay, az = a["pos"]
        pt = (ax, ay - (rec[0xF] << 5), az)
        if movement.in_range(r["p"], pt[0], pt[1], pt[2], rec[0xE] << 6,
                             0x6A4, 0) != -1:
            return pt, rec
    return None, None


def strike_records(lv=0):
    """{slot: the bytes of its kind's opcode-4 record}, for the level's
    placed creatures."""
    import ai
    import actors
    kinds = {k["kind"]: k for k in ai.kinds(lv)}
    out = {}
    for slot, a in enumerate(actors.table(lv)):
        if a is None:
            continue
        kd = kinds.get(a["kind"])
        if kd is None:
            continue
        for b in kd["behaviours"]:
            if b and b["op"] == 4:
                out[slot] = bytes(b["raw"])
                break
    return out


def check(out=sys.stdout, verbose=False):
    import replay
    rows, _binds = replay.load(os.path.join(ROOT, "out", "lua_bp16.log"))
    eps = episodes(rows)
    if not eps:
        print("  no knock-back in out/lua_bp16.log: ./emu/run.sh debug "
              "bp16.lua and let something hit you", file=out)
        return True
    lvl = movement.level(0)
    good = True
    want = settle((SHAKE_MAX, 0))
    lengths = [sum(1 for r in e if r["pst"] == 0x10) for e in eps]
    ok_len = sum(1 for n in lengths if n == want)
    print(f"  {len(eps)} knock-backs, {lengths} frames in state 0x10; the "
          f"spring settles a shake of {SHAKE_MAX:#x} in {want}: "
          f"{ok_len} of {len(eps)}", file=out)
    good &= ok_len == len(eps)
    # the landing: state 0x40 with the push's Y, into 0x50 in the same frame
    land_ok = land_n = 0
    for e in eps:
        a, b, c = e[1], e[2], e[3]
        if a["vst"] != 0x40:
            continue
        land_n += 1
        cam = {"crouch": 0, "dip": 0}
        _p, st, vv = movement.walk_step(lvl, a["p"], 0, 0, a["vst"], a["vv"],
                                        a["mag"], cam)
        cam2 = dict(cam)
        _p, st2, vv2 = movement.walk_step(lvl, b["p"], 0, 0, st, vv, b["mag"],
                                          cam2)
        if (st, vv, st2, vv2) == (b["vst"], b["vv"], c["vst"], c["vv"]):
            land_ok += 1
        elif verbose:
            print(f"  landing f={a['f']}: model {(st, vv, st2, vv2)}, game "
                  f"{(b['vst'], b['vv'], c['vst'], c['vv'])}", file=out)
    print(f"  {land_ok} of {land_n} landings out of state 0x40: the state and "
          f"velocity after it and the frame after that", file=out)
    good &= land_ok == land_n
    # the push itself, frame by frame with the walk the controller still runs:
    # predicted from the creature where the log names it, else taken from the
    # first frame's step
    recs = strike_records(0)
    steps_ok = steps = vel_ok = vels = 0
    for e in eps:
        att, rec = _attacker(e[1], recs)
        v = None
        if att is not None:
            v = apply_damage(50, 50, 14, e[1]["p"], att, rec[0x11],
                             e[1]["ang"])["push"]
        for i, (r, nxt) in enumerate(zip(e[1:], e[2:])):
            if r["pst"] != 0x10:
                break
            first = v is None
            if first:
                v = (nxt["p"][0] - r["p"][0], 1, nxt["p"][2] - r["p"][2])
            p = frame(lvl, r, nxt, v)
            p, v = p
            if nxt.get("pv") and nxt["pst"] == 0x10:
                vels += 1                 # bp16's pv=, from 2026-09-28 on
                vel_ok += tuple(v) == nxt["pv"]
            if first:
                continue
            steps += 1
            if p == nxt["p"]:
                steps_ok += 1
            elif verbose:
                print(f"  f={r['f']}: model {p}, game {nxt['p']}", file=out)
    print(f"  {steps_ok} of {steps} frames of a knock-back land where the game "
          f"put the player -- the walk, player_move and player_vertical, the "
          f"push carried across the whole episode", file=out)
    good &= steps_ok == steps
    if vels:
        print(f"  {vel_ok} of {vels} frames leave player_velocity what the "
              f"game logged (pv=)", file=out)
        good &= vel_ok == vels
    # the push predicted from the creature, where the log names it
    pred_ok = pred_n = 0
    for e in eps:
        r1 = e[1]
        att, rec = _attacker(r1, recs)
        if att is None:
            continue
        pred_n += 1
        # the damage off the record against a fresh character: 14 on 50
        hit = apply_damage(50, 50, 14, r1["p"], att, rec[0x11], r1["ang"])
        if hit["push"][1] == r1["vv"]:
            pred_ok += 1
        elif verbose:
            print(f"  f={r1['f']}: push {hit['push']}, the game's Y {r1['vv']}",
                  file=out)
    print(f"  {pred_ok} of {pred_n} pushes predicted from the creature's "
          f"logged position: the Y the game put into player_vvel", file=out)
    good &= pred_ok == pred_n
    return good


def export(out_dir, lv=0):
    """knockcheck.json: cases for godot/selftest.gd -- apply_damage over a
    spread of hits, the spring's length for every shake, fall damage, and
    player_move from every position of the recorded knock-backs."""
    import json
    hits = []
    for dmg in (1, 3, 7, 12, 14, 30, 49, 50, 60):
        for hp_max in (50, 57, 120):
            for eff in (0, 0x40):
                for k, (ax, ay, az) in enumerate(((1500, -600, 0),
                                                  (-900, 0, 1300),
                                                  (200, 800, -1700))):
                    player = (100000, -12800, 60000)
                    att = (player[0] - ax, player[1] - ay, player[2] - az)
                    facing = (k * 0x2A7 + dmg * 0x31) & 0xFFF
                    h = apply_damage(40, hp_max, dmg, player, att, eff, facing)
                    st = h.get("state", 0)
                    push = h["push"] if st else (0, 0, 0)
                    sh = h["shake"] if st else (0, 0)
                    hits.append([40, hp_max, dmg, *player, *att, eff, facing,
                                 h["hp"], st, *push, *sh, h["flash"][1]])
    springs = [[sh, settle((sh, 0))] for sh in range(0, 0x60)]
    falls = [[v, fall_damage(v)] for v in range(0x1E0, 0x900, 0x1C)]
    moves = []
    try:
        import replay
        rows, _b = replay.load(os.path.join(ROOT, "out", "lua_bp16.log"))
        lvl = movement.level(lv)
        for e in episodes(rows):
            for r in e:
                for d in range(8):
                    for ln in (0x50, 0xE0, 0x1C2):
                        a = d * 0x200
                        v = ((movement.game_cos(a) * ln) >> 12, 1,
                             (movement.game_sin(a) * ln) >> 12)
                        p, v2, _m = player_move(lvl, r["p"], v)
                        moves.append([*r["p"], v[0], v[2], *p, v2[0], v2[1],
                                      v2[2]])
    except Exception as ex:                                  # noqa: BLE001
        print(f"  knockcheck: no player_move cases ({ex})")
    path = os.path.join(out_dir, "knockcheck.json")
    with open(path, "w") as fh:
        json.dump({"_note": "tools/knock.py's answers, for selftest.gd",
                   "hits": hits, "springs": springs, "falls": falls,
                   "moves": moves}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0].lstrip("-").isdigit():
        dmg, hp_max = int(a[0]), int(a[1])
        s2 = min(movement.trunc(dmg << 12, hp_max), SHARE_CAP)
        s = max(SHAKE_MIN, min(SHAKE_MAX, movement.game_isqrt(s2 << 2)))
        print(f"  push {min(max(s2 >> 2, PUSH_MIN), PUSH_CAP)}, shake {s}, "
              f"{settle((s, 0))} frames in state 0x10, flash "
              f"{max((FLASH_BASE - (s2 >> 1)) >> 2, FLASH_MIN)}")
    else:
        sys.exit(0 if check(verbose="--check" not in a) else 1)

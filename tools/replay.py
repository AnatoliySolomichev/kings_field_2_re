#!/usr/bin/env python3
"""Play a recorded session back through the model and say where it parts company.

    ./emu/run.sh debug bp16.lua       record: play normally for a minute
    python3 tools/replay.py           then replay it, and read the numbers

`emu/bp16.lua` writes one line a frame: the buttons you pressed and the whole
player state the game had. This runs the port's own model over the same input
and reports, per frame, whether it reached the same place.

## Why there are three rungs and not one comparison

A free-running copy is the honest end-to-end test and a useless diagnostic. The
first frame the model gets wrong leaves it standing somewhere else, asking about
different cells, so every frame after that disagrees too and only one of the
disagreements is real. So each rung is run **locked** as well: take the state the
game actually had, run exactly one frame, compare, then throw the answer away and
take the game's state again. Locked, every disagreement is its own bug and
carries a cell you can go and look at.

The rungs release one layer at a time, so a disagreement can only be blamed on
the layer just released:

1. **height** — the game's own next X and Z are given; only `player_vertical` is
   asked. This is the layer with numbers behind it already.
2. **ground and height** — the game's facing and speed are given; the step
   itself is computed, so `player_horizontal` and the collision join in.
3. **from the buttons** — the speed is derived from the buttons too. The facing
   is still the game's: the turn rate is in `0x8002fe1c` and is not transcribed,
   so claiming otherwise would put an unread layer under a checked one.

The speed ramp is checked on its own besides, because it is a pure function of
the buttons and can be scored without any geometry at all.

## What it cannot do yet

`player_horizontal` is in whole (`movement.horizontal`) but for the creatures:
its refusal, its shorter retries, its slides, the objects -- the rectangle
slide and the push-out round a circle, 447 of the 455 frames that touch one --
and a steep ramp's push with the ceiling that gates a step up. That took the
ground rung from 117 686 to 118 288 of 118 500. What is left is counted in
three heaps rather than one total:

* **a door**: the player was within reach of a swinging door (opcode 1), which
  shoves whoever stands in its sweep by 0x4c a frame while it opens and
  restamps the grid when it has -- neither of which a recording of the player
  alone can replay;
* **a wall**: the model turned the step away and the game did not;
* **the rest**, where the model took the step whole: a creature the log did
  not hold -- `emu/bp16.lua` logs the awake ones near the player as `act=`
  since 2026-09-26 -- or a creature's blow, which knocks the player back
  through the creature's own code. In the first session with `act=`, 76 of 76
  frames that ran into a logged creature came out exact, and the six that did
  not are one knock-back: a push of 224, 193, 162, 131, 100 and 66 in one
  direction, falling about 31 a frame, with creature 33 two thousand away.
"""
import collections
import os
import re
import sys

sys.path.insert(0, "tools")
import movement  # noqa: E402

LINE = re.compile(
    r"f=\s*(\d+) t=\s*([\d.]+) btn=([0-9a-f]{4}) prev=([0-9a-f]{4}) "
    r"ang=\s*(-?\d+) fwd=\s*(-?\d+) mag=\s*(-?\d+) max=\s*(-?\d+) "
    r"pos=\s*(-?\d+)\s+(-?\d+)\s+(-?\d+) vst=\s*(\d+) vv=\s*(-?\d+) "
    r"pst=\s*(\d+) lv=\s*(\d+) ra=([0-9a-f]{8})")
BINDS = re.compile(r"binds (.*)")


def load(path="out/lua_bp16.log"):
    """The frames, and the key bindings the session was played with."""
    rows, binds = [], {}
    if not os.path.exists(path):
        return rows, binds
    for line in open(path):
        m = BINDS.match(line)
        if m:
            for pair in m.group(1).split():
                k, v = pair.split("=")
                binds[k] = int(v, 16)
            continue
        m = LINE.match(line)
        if not m:
            continue
        g = m.groups()
        blk = []
        b = re.search(r"blk=(\S+)", line)
        if b:
            blk = [movement.s16(int(v, 16)) for v in b.group(1).split(",")]
        v = re.search(r" vb=(\d+)", line)
        act = re.search(r" act=(\S*)", line)
        rows.append({
            "vb": int(v.group(1)) if v else None,
            "act": actors_of(act.group(1)) if act else None,
            "f": int(g[0]), "t": float(g[1]),
            "btn": int(g[2], 16), "prev": int(g[3], 16),
            "ang": int(g[4]), "fwd": int(g[5]), "mag": int(g[6]),
            "max": int(g[7]),
            "p": (int(g[8]), int(g[9]), int(g[10])),
            "vst": int(g[11]), "vv": int(g[12]), "pst": int(g[13]),
            "lv": int(g[14]), "ra": g[15],
            "stf": blk[3] if len(blk) > 3 else 0,
            "prate": blk[7] if len(blk) > 7 else None,       # 0x801b264e
        })
    return rows, binds


def actors_of(field):
    """`act=` from emu/bp16.lua: the awake creatures near the player.

    Each is `slot:x:y:z:radius:height:flags:b0e:lift`, flags in hex, which is
    what movement.actor_spot_taken asks of an actor.
    """
    out = []
    for item in field.split(","):
        if not item:
            continue
        k, x, y, z, r, h, fl, b0e, lift = item.split(":")
        out.append({"slot": int(k), "pos": (int(x), int(y), int(z)),
                    "radius": int(r), "height": int(h), "flags": int(fl, 16),
                    "b0e": int(b0e), "lift": int(lift)})
    return out


def runs_of(rows):
    """Split at anything that is not one continuous stretch of ordinary play."""
    out, cur = [], []
    for r in rows:
        if cur and (r["f"] != cur[-1]["f"] + 1 or r["lv"] != cur[-1]["lv"]
                    or r["pst"] != cur[-1]["pst"]):
            if len(cur) > 2:
                out.append(cur)
            cur = []
        cur.append(r)
    if len(cur) > 2:
        out.append(cur)
    return out


def step_horizontal(lvl, p, ang, fwd_speed, strafe_speed, actors=None):
    """The two calls `0x8002f9bc` makes, in its own order and its own directions.

    Forward goes along `facing + 0x400` and the strafe along `facing` — the
    facing at `0x801b2612` is a quarter turn off the direction of travel, which
    the recording settled: at facing 0 the game moves in +Z, not +X. And the
    distances are not the speeds but `speed^2 / isqrt(sum of squares)`.

    Both calls are made whatever the distances: `player_walk` falls through
    into `player_step_distances`, which calls `player_horizontal` twice with
    no test (`0x8002fda0`, `0x8002fdb4`). A step of nothing still asks the
    collision and still takes a steep ramp's push, so a player standing on one
    slides down it, and by two pushes a frame.
    """
    fd, sd = movement.step_distances(strafe_speed, fwd_speed)
    p, _ok = movement.horizontal(lvl, p, (ang + 0x400) & 0xFFF, fd, actors=actors)
    p, _ok = movement.horizontal(lvl, p, ang & 0xFFF, sd, actors=actors)
    return p


def frame(lvl, r, nxt, rung):
    """One frame of the model at the given rung, from `r` towards `nxt`.

    Returns the predicted position.
    """
    p = r["p"]
    if rung == 1:
        p = (nxt["p"][0], p[1], nxt["p"][2])          # the game's own ground move
    else:
        # The controller turns before it steps and 0x8002f9bc accelerates before
        # it steps, so the facing and the speeds this frame used are the ones
        # logged at the *next* frame's start.
        fwd, stf = nxt["fwd"], nxt["stf"]
        if rung == 3:
            fwd = movement.accelerate(r["fwd"], r["btn"] & BIND["forward"],
                                      r["btn"] & BIND["back"], r["max"])
            stf = movement.accelerate(r["stf"], r["btn"] & BIND["strafe_pos"],
                                      r["btn"] & BIND["strafe_neg"], r["max"], 2)
        p = step_horizontal(lvl, p, nxt["ang"], fwd, stf, r.get("act"))
    p, _st, _v = movement.walk_step(lvl, p, 0, 0, r["vst"], r["vv"], r["mag"])
    return p


# The defaults out of GAME.EXE; a log that carries the live table overrides them.
BIND = {"forward": 0x1000, "back": 0x4000,
        "strafe_pos": 0x0008, "strafe_neg": 0x0004}


# How near a swinging door a frame has to be to be put down to it: its sweep is
# a leaf of 0x800 turning about the hinge, and the shove reaches past that.
DOOR_REACH = 0x1000


def doors(lv):
    """The swinging doors of a level, out of tools/objload.py: opcode 1."""
    import objload
    return [r for r in objload.Load(lv).recs.values() if r["op"] == 1]


def touches_creature(lvl, r, nxt):
    """Does either of the frame's two steps run into a logged creature?"""
    if not r.get("act"):
        return False
    fd, sd = movement.step_distances(nxt["stf"], nxt["fwd"])
    p = r["p"]
    for ang, dist in (((nxt["ang"] + 0x400) & 0xFFF, fd), (nxt["ang"] & 0xFFF, sd)):
        tx = p[0] + ((movement.game_cos(ang) * dist) >> 12)
        tz = p[2] + ((movement.game_sin(ang) * dist) >> 12)
        ex = {}
        movement.query_all(lvl, tx, p[1], tz, extra=ex, actors=r["act"])
        if ex.get(0x801E648C) is not None:
            return True
    return False


TOUCH = collections.Counter()      # (rung, exact?) over the frames that touch one


def check(lvl, run, rung, objs=()):
    """Locked and free, over one continuous run. Returns a line of numbers."""
    locked = bad = walled = objected = 0
    cells = collections.Counter()
    for r, nxt in zip(run, run[1:]):
        got = frame(lvl, r, nxt, rung)
        if rung == 2 and touches_creature(lvl, r, nxt):
            TOUCH[got == nxt["p"]] += 1
        if got == nxt["p"]:
            locked += 1
            continue
        bad += 1
        cells[(r["p"][0] >> 11, r["p"][2] >> 11)] += 1
        # Did the model itself turn the step away? Then a wall had a say, and
        # the frame is the wall's; if it took the step whole and the game did
        # not, something the model cannot see was in the way.
        fd, sd = movement.step_distances(nxt["stf"], nxt["fwd"])
        a, b = (nxt["ang"] + 0x400) & 0xFFF, nxt["ang"] & 0xFFF
        straight = (r["p"][0] + ((movement.game_cos(a) * fd) >> 12)
                    + ((movement.game_cos(b) * sd) >> 12),
                    r["p"][2] + ((movement.game_sin(a) * fd) >> 12)
                    + ((movement.game_sin(b) * sd) >> 12))
        took = step_horizontal(lvl, r["p"], nxt["ang"], nxt["fwd"], nxt["stf"],
                               r.get("act"))
        # The door first: a closed door is a wall in the model's grid, and a
        # frame spent walking through it after it opened is the door's.
        if any(abs(o["x"] - r["p"][0]) < DOOR_REACH
               and abs(o["z"] - r["p"][2]) < DOOR_REACH for o in objs):
            objected += 1
        elif (took[0], took[2]) != straight:
            walled += 1

    # free: carry our own position, take only the input from the log
    p = run[0]["p"]
    state, vel = run[0]["vst"], run[0]["vv"]
    first, worst = None, 0
    for r, nxt in zip(run, run[1:]):
        if rung == 1:
            p = (nxt["p"][0], p[1], nxt["p"][2])
        else:
            fwd, stf = nxt["fwd"], nxt["stf"]
            if rung == 3:
                fwd = movement.accelerate(r["fwd"], r["btn"] & BIND["forward"],
                                          r["btn"] & BIND["back"], r["max"])
                stf = movement.accelerate(r["stf"], r["btn"] & BIND["strafe_pos"],
                                          r["btn"] & BIND["strafe_neg"], r["max"], 2)
            p = step_horizontal(lvl, p, nxt["ang"], fwd, stf, r.get("act"))
        p, state, vel = movement.walk_step(lvl, p, 0, 0, state, vel, r["mag"])
        d = max(abs(a - b) for a, b in zip(p, nxt["p"]))
        if d and first is None:
            first = nxt["f"]
        worst = max(worst, d)
    return locked, bad, walled, objected, cells, first, worst


def ramp(rows):
    """Does `accelerate` reproduce the speed the game arrived at? No geometry."""
    ok = bad = 0
    for r, nxt in zip(rows, rows[1:]):
        if nxt["f"] != r["f"] + 1:
            continue
        got = movement.accelerate(r["fwd"], r["btn"] & BIND["forward"],
                                  r["btn"] & BIND["back"], r["max"])
        if got == nxt["fwd"]:
            ok += 1
        else:
            bad += 1
    return ok, bad


def look_rate(rows, binds):
    """The pitch rate `player_look` (`0x8002f5c0`) drives, frame by frame.

    look_b (the `b11` slot, R2 in scheme A) adds 3 up to 0x20, look_a (`b9`,
    L2) takes 3 down to -0x20, neither decays by 3 to 0. Both at once recentre
    by the pitch, which the log does not carry, so those frames are left out.
    The rate is the eighth halfword of the logged block, `0x801b264e`.
    """
    la, lb = binds.get("b9") or 1, binds.get("b11") or 2
    ok = n = active = 0
    for a, b in zip(rows, rows[1:]):
        if b["f"] != a["f"] + 1 or a["prate"] is None or b["prate"] is None:
            continue
        up, down = a["btn"] & la, a["btn"] & lb
        if up and down:
            continue
        r = a["prate"]
        want = (min(r + 3, 0x20) if down else max(r - 3, -0x20) if up
                else max(r - 3, 0) if r > 0 else min(r + 3, 0) if r < 0 else 0)
        n += 1
        active += bool(r or b["prate"] or up or down)
        ok += want == b["prate"]
    print(f"pitch rate: {ok} of {n} frames predicted by player_look's rule, "
          f"{active} of them with a look button or the rate active")


def blanks(rows):
    """How many vertical blanks each frame took, off the game's own clock.

    `frame_limit` holds a frame to at least four -- 15 a second -- and a frame
    whose work overruns takes more. `vb` is `vblank_count`, which bp16.lua logs
    from 2026-09-25 on; older sessions do not have it.
    """
    per = collections.Counter()
    for a, b in zip(rows, rows[1:]):
        if a["vb"] is None or b["vb"] is None or b["f"] != a["f"] + 1:
            continue
        per[b["vb"] - a["vb"]] += 1
    if not per:
        print("vertical blanks a frame: not in this log (bp16.lua logs vb= now)")
        return
    n = sum(per.values())
    mean = sum(k * v for k, v in per.items()) / n
    print(f"vertical blanks a frame over {n} frames: "
          + ", ".join(f"{k}: {v}" for k, v in sorted(per.items()))
          + f" -- {60 / mean:.2f} frames a second on average")


def report(path="out/lua_bp16.log"):
    rows, binds = load(path)
    if len(rows) < 3:
        print(f"no frames in {path}.\n"
              "Record one: ./emu/run.sh debug bp16.lua, then play for a minute —\n"
              "flat ground, stairs, a bridge, and a drop.")
        return
    # bp16 logged the binding table at arming time, which is before the game has
    # loaded GAME.EXE, so an all-zero table means "not read" rather than "no
    # buttons bound". Fall back to the defaults in the executable.
    for k in BIND:
        if binds.get(k):
            BIND[k] = binds[k]
    lv = collections.Counter(r["lv"] for r in rows).most_common(1)[0][0]
    # Wall clock is not reported: under the interpreter the emulator runs at
    # its own speed, and a log can hold several sessions. The game's rate is
    # read off the code (frame_limit, 15 a second) and measured below by vb.
    print(f"{len(rows)} frames")
    print(f"buttons: forward {BIND['forward']:#06x}, back {BIND['back']:#06x}")
    blanks(rows)
    look_rate(rows, binds)

    ok, bad = ramp(rows)
    print(f"speed ramp: {ok} of {ok + bad} frames reproduced by accelerate()")

    runs = [r for r in runs_of(rows) if r[0]["lv"] == lv]
    if not runs:
        print("no continuous run to replay")
        return
    lvl = movement.level(lv)
    try:
        objs = doors(lv)
    except Exception:
        objs = []
    print(f"level {lv}, {len(runs)} continuous run(s), "
          f"{sum(len(r) for r in runs)} frames")
    names = {1: "height only          ", 2: "ground and height    ",
             3: "from the buttons     "}
    for rung in (1, 2, 3):
        tl = tb = tw = to = 0
        cells = collections.Counter()
        first, worst = None, 0
        for run in runs:
            a, b, wl, ob, c, f, w = check(lvl, run, rung, objs)
            tl += a
            tb += b
            tw += wl
            to += ob
            cells += c
            if f is not None and first is None:
                first = f
            worst = max(worst, w)
        pct = tl * 100 // max(tl + tb, 1)
        print(f"rung {rung} {names[rung]} locked {tl} of {tl + tb} exact "
              f"({pct} %)   free: "
              + (f"first drift at frame {first}, worst {worst} units"
                 if first is not None else "no drift"))
        if tb:
            rest = tb - tw - to
            print(f"     of the {tb} that differ, {to} are within reach of a "
                  f"swinging door, {tw} the model turned away at a wall"
                  + ("" if rest <= 0 else f" and {rest} it took whole "
                     "(a creature's blow, or a creature the log did not hold)"))
        if rung == 2 and TOUCH:
            print(f"     {TOUCH[True]} of {TOUCH[True] + TOUCH[False]} frames that "
                  f"run into a logged creature come out exact")
            for (cx, cz), n in cells.most_common(3):
                print(f"     cell ({cx},{cz}) {n}x")


if __name__ == "__main__":
    report(sys.argv[1] if len(sys.argv) > 1 else "out/lua_bp16.log")

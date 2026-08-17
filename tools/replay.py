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

Two things, and the report counts each separately rather than burying them in a
total:

* `player_horizontal` refuses a blocked step where the game **slides along the
  wall**, turning it by the wall's own facing out of `0x801e6498` and
  `0x801e649c`, which `tools/collision.py` does not compute.
* the player also collides with **objects** — `collide_query`'s flag `0x10`,
  through `0x8004d644` — and nothing here models that at all, so the port walks
  through a cart the game stops at. Frames that disagree while standing within a
  radius of a placed object are almost certainly this: in one recording, 209 of
  the 225 that the wall slide did not explain were, and the objects were types
  287, 325 and 324.
"""
import collections
import os
import re
import sys

sys.path.insert(0, "tools")
import movement  # noqa: E402
import placement  # noqa: E402

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
        rows.append({
            "f": int(g[0]), "t": float(g[1]),
            "btn": int(g[2], 16), "prev": int(g[3], 16),
            "ang": int(g[4]), "fwd": int(g[5]), "mag": int(g[6]),
            "max": int(g[7]),
            "p": (int(g[8]), int(g[9]), int(g[10])),
            "vst": int(g[11]), "vv": int(g[12]), "pst": int(g[13]),
            "lv": int(g[14]), "ra": g[15],
            "stf": blk[3] if len(blk) > 3 else 0,
        })
    return rows, binds


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


def step_horizontal(lvl, p, ang, fwd_speed, strafe_speed):
    """The two calls `0x8002f9bc` makes, in its own order and its own directions.

    Forward goes along `facing + 0x400` and the strafe along `facing` — the
    facing at `0x801b2612` is a quarter turn off the direction of travel, which
    the recording settled: at facing 0 the game moves in +Z, not +X. And the
    distances are not the speeds but `speed^2 / isqrt(sum of squares)`.
    """
    fd, sd = movement.step_distances(strafe_speed, fwd_speed)
    if fd:
        p, _ok = movement.horizontal(lvl, p, (ang + 0x400) & 0xFFF, fd)
    if sd:
        p, _ok = movement.horizontal(lvl, p, ang & 0xFFF, sd)
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
        p = step_horizontal(lvl, p, nxt["ang"], fwd, stf)
    p, _st, _v = movement.walk_step(lvl, p, 0, 0, r["vst"], r["vv"], r["mag"])
    return p


# The defaults out of GAME.EXE; a log that carries the live table overrides them.
BIND = {"forward": 0x1000, "back": 0x4000,
        "strafe_pos": 0x0008, "strafe_neg": 0x0004}


def check(lvl, run, rung, objs=()):
    """Locked and free, over one continuous run. Returns a line of numbers."""
    locked = bad = walled = objected = 0
    cells = collections.Counter()
    for r, nxt in zip(run, run[1:]):
        got = frame(lvl, r, nxt, rung)
        if got == nxt["p"]:
            locked += 1
            continue
        bad += 1
        cells[(r["p"][0] >> 11, r["p"][2] >> 11)] += 1
        # Was the step blocked? Then this is the slide, which is not modelled,
        # and saying so is the difference between a known gap and a bug.
        fd, _sd = movement.step_distances(nxt["stf"], nxt["fwd"])
        a = (nxt["ang"] + 0x400) & 0xFFF
        tx = r["p"][0] + ((movement.game_cos(a) * fd) >> 12)
        tz = r["p"][2] + ((movement.game_sin(a) * fd) >> 12)
        if movement.query(lvl, tx, r["p"][1], tz)[0]:
            walled += 1
        elif any(abs(o["x"] - r["p"][0]) < 1600 and abs(o["z"] - r["p"][2]) < 1600
                 for o in objs):
            objected += 1

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
            p = step_horizontal(lvl, p, nxt["ang"], fwd, stf)
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
    span = rows[-1]["t"] - rows[0]["t"]
    rate = (len(rows) - 1) / span if span > 0 else 0
    lv = collections.Counter(r["lv"] for r in rows).most_common(1)[0][0]
    print(f"{len(rows)} frames over {span:.1f} s — {rate:.1f} a second, in this "
          "session under the interpreter, which runs slower than the console")
    print(f"buttons: forward {BIND['forward']:#06x}, back {BIND['back']:#06x}")

    ok, bad = ramp(rows)
    print(f"speed ramp: {ok} of {ok + bad} frames reproduced by accelerate()")

    runs = [r for r in runs_of(rows) if r[0]["lv"] == lv]
    if not runs:
        print("no continuous run to replay")
        return
    lvl = movement.level(lv)
    try:
        objs = placement.objects(lv)
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
            print(f"     of the {tb} that differ, {tw} are the wall slide and "
                  f"{to} are within reach of a placed object — neither modelled"
                  + ("" if rest <= 0 else f", leaving {rest} unexplained"))
            for (cx, cz), n in cells.most_common(3):
                print(f"     cell ({cx},{cz}) {n}x")


if __name__ == "__main__":
    report(sys.argv[1] if len(sys.argv) > 1 else "out/lua_bp16.log")

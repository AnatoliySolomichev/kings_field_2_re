#!/usr/bin/env python3
"""Record where the player goes, and what the game's collision said about it.

    python3 tools/walk.py rec <name>     record until interrupted, into out/walk/<name>.jsonl
    python3 tools/walk.py stop           stop a recorder started in the background
    python3 tools/walk.py edges <name>   the cell edges the walk crossed

The point of a trace is the **negatives**. Every cell boundary the player walks
across is an edge that carries no collision surface at that height, and a
candidate wall decode that predicts a wall there is falsified outright. A few
minutes of walking covers hundreds of edges, which no amount of staring at the
game's own hand-drawn map can.

Each sample also carries the live output of `tile_collision` (`0x8003260c`),
which returns a bitmask of the surfaces the player is up against and leaves its
working values in the struct at `0x801e6470`. That turns a sample taken while
pressing into a wall into a **positive** with the game's own label on it.
"""
import json
import os
import struct
import sys
import time

sys.path.insert(0, "tools")
import psxlive as L                                                   # noqa: E402

OUT = "out/walk"
PID = "out/walk.pid"
POS = 0x801AEC4C          # s32 X, Y, Z
LEVEL = 0x8018FAD9        # u8 current level
GRID = 0x801D4464         # the level grid, live: 97% identical to the disc,
                          # the rest being what the level state has changed
CELLPTR = 0x801E6464      # u32, the cell the collision routine was last given
LAYER = 0x801E646E        # u16, the layer offset inside it -- always 5, which
                          # is why cell +7 and +8 reach the handlers as +2, +3
COLL = 0x801E6470         # the collision routine's working struct
CELL = 10                 # bytes per cell
W = 80


def sample(ram):
    x, y, z = struct.unpack("<3i", L.at(ram, POS, 12))
    cx, cz = x // 2048, z // 2048
    s = {"t": round(time.time(), 3),
         "lv": L.at(ram, LEVEL, 1)[0],
         "x": x, "y": y, "z": z,
         "cx": cx, "cz": cz,
         "tx": x & 0x7FF, "tz": z & 0x7FF,
         "ptr": struct.unpack("<I", L.at(ram, CELLPTR, 4))[0],
         "coll": L.at(ram, COLL, 0x30).hex()}
    if 0 <= cz < W and 0 <= cx < W:
        s["cell"] = L.at(ram, GRID + (cz * W + cx) * CELL, CELL).hex()
    return s


def grid(ram=None):
    """The level grid as it stands now, level state and all."""
    return L.at(ram if ram is not None else L.ram(), GRID, W * W * CELL)


def rec(name, hz=20):
    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/{name}.jsonl"
    open(PID, "w").write(str(os.getpid()))
    n, last = 0, None
    with open(path, "a") as f:
        try:
            while True:
                s = sample(L.ram())
                key = (s["x"], s["y"], s["z"], s["coll"])
                if key != last:                       # standing still adds nothing
                    f.write(json.dumps(s) + "\n")
                    f.flush()
                    last, n = key, n + 1
                time.sleep(1.0 / hz)
        except KeyboardInterrupt:
            pass
    print(f"{n} samples -> {path}")


def load(name):
    return [json.loads(l) for l in open(f"{OUT}/{name}.jsonl")]


def edges(name):
    """Every cell boundary the trace crosses: (level, x, z, dx, dz)."""
    out, prev = {}, None
    for s in load(name):
        if prev and s["lv"] == prev["lv"]:
            dx, dz = s["cx"] - prev["cx"], s["cz"] - prev["cz"]
            if (dx, dz) != (0, 0) and abs(dx) + abs(dz) == 1:
                out.setdefault((prev["lv"], prev["cx"], prev["cz"], dx, dz), 0)
                out[(prev["lv"], prev["cx"], prev["cz"], dx, dz)] += 1
        prev = s
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "rec"
    if what == "stop":
        if os.path.exists(PID):
            os.kill(int(open(PID).read()), 2)
            print("stopped")
        else:
            print("not running")
    elif what == "edges":
        e = edges(sys.argv[2])
        for (lv, x, z, dx, dz), n in sorted(e.items()):
            print(f"level {lv}  ({x:2d},{z:2d}) -> ({x + dx:2d},{z + dz:2d})   {n}x")
        print(f"\n{len(e)} distinct edges crossed — none of them carries a wall")
    else:
        rec(sys.argv[2] if len(sys.argv) > 2 else "walk")

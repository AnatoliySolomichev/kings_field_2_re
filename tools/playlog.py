#!/usr/bin/env python3
"""A playthrough, recorded in the emulator and played back there.

    python3 tools/playlog.py                     the sessions recorded
    python3 tools/playlog.py replay [S] [--key N] [--until F]
                                                 the emulator with no window over the
                                                 session's buttons: does it come out the same
    python3 tools/playlog.py dump [S] A B        frames A..B's tables whole, out of a replay
    python3 tools/playlog.py events [S]          what happened: creatures killed, things
                                                 taken, doors, chests, flags, levels, by frame
    python3 tools/playlog.py mark "text"         a note at the frame bp29.lua is on
    python3 tools/playlog.py notes [S]           the session's notes
    python3 tools/playlog.py note [S] N          what note N was looking at: the place, the
                                                 objects and the creatures, nearest first

`emu/bp29.lua` writes a session into `out/run/<date>/`, and `S` is its name, or
the end of it, the latest by default. `emu/replay.lua` runs it back under
`AppRun -no-ui` in the session's `replay/`, with copies of `emu/pcsx.json` (no web
server, no GDB stub) and of the keyframe's memory cards, so nothing of the
emulator a person plays in is touched and no window opens.

**The game repeats, and that is what makes this worth doing.** The same state and
the same words out of PadRead give the same game: run twice from one snapshot,
rand's state, the vertical blanks, the player's place, the calls of PadRead and
the object, creature, effect and player tables agree frame for frame (the
numbers are in TOOLS.md, "A playthrough"). What differs between two runs is the
sound library's voice tables around 0x8009e800, which follow the emulator's
SPU thread and nothing reads back into the game.

So a session is small -- buttons and hashes, 4 MB an hour, and a keyframe of 1.7
MB every five minutes -- and everything else comes from a replay, when it is
asked for. The replay holds itself to the session: each frame's record is set
beside the one written while it was played, so a replay that has wandered off
says on which frame and in which table.
"""
import gzip
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "out", "run")
EMU = os.path.join(ROOT, "emu")
APP = os.path.join(EMU, "squashfs-root", "AppRun")
BIOS = os.path.join(EMU, "squashfs-root", "usr", "share", "pcsx-redux", "resources", "openbios.bin")
CUE = os.path.join(EMU, "kf2.cue")
FRAME = struct.Struct("<4I3i2H4B6I")
NAMES = ("frame", "calls", "vblank", "seed", "x", "y", "z", "facing", "hp", "level", "pstate",
         "spare0", "spare1", "objects", "actors", "effects", "player", "state", "grid")
REGIONS = (("objects", 396 * 68), ("actors", 200 * 0x88), ("effects", 128 * 0x4C),
           ("player", 0x67 * 4), ("state", 0x1451 * 4), ("grid", 64000))
SPEED = 20                   # game frames a second the emulator is good for, with no window
MARK = os.path.join(RUNS, "mark.txt")


def sessions():
    if not os.path.isdir(RUNS):
        return []
    return sorted(d for d in os.listdir(RUNS) if os.path.exists(os.path.join(RUNS, d, "frames.bin")))


def session(name=None):
    all_ = sessions()
    if not all_:
        raise SystemExit("no sessions in out/run: ./emu/run.sh debug bp29.lua, and play")
    if name is None:
        return all_[-1]
    hits = [s for s in all_ if s.endswith(name)]
    if len(hits) != 1:
        raise SystemExit(f"{name}: {len(hits)} sessions")
    return hits[0]


def frames(s):
    with open(os.path.join(RUNS, s, "frames.bin"), "rb") as f:
        raw = f.read()
    n = len(raw) // FRAME.size
    return [dict(zip(NAMES, FRAME.unpack_from(raw, i * FRAME.size))) for i in range(n)]


def keys(s):
    with open(os.path.join(RUNS, s, "keys.txt")) as f:
        return [tuple(int(v) for v in line.split()) for line in f if line.strip()]


def notes(s):
    out = []
    p = os.path.join(RUNS, s, "notes.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                n, frame, calls, text = line.rstrip("\n").split("\t", 3)
                out.append((int(n), int(frame), int(calls), text))
    return out


def show_list():
    all_ = sessions()
    if not all_:
        print("no sessions in out/run: ./emu/run.sh debug bp29.lua, and play")
    for s in all_:
        d = os.path.join(RUNS, s)
        n = os.path.getsize(os.path.join(d, "frames.bin")) // FRAME.size
        size = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)
                   if os.path.isfile(os.path.join(d, f)))
        print(f"{s}: {n} frames, {n / 15 / 60:.1f} minutes of game, {len(keys(s))} keyframes, "
              f"{len(notes(s))} notes, {size / 1e6:.1f} MB")


def sandbox(s, key):
    """The session's replay/: a copy of the emulator's settings, without its
    servers, and the keyframe's cards and state. The cards are copies because a
    game saved in the replay writes them."""
    d = os.path.join(RUNS, s, "replay")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(EMU, "pcsx.json")) as f:
        c = json.load(f)
    c["emulator"]["Debug"]["WebServer"] = False
    c["emulator"]["Debug"]["GdbServer"] = False
    c["emulator"]["Mcd1"], c["emulator"]["Mcd2"] = "memcard1.mcd", "memcard2.mcd"
    with open(os.path.join(d, "pcsx.json"), "w") as f:
        json.dump(c, f)
    base = os.path.join(RUNS, s, f"key-{key:04d}")
    shutil.copy(base + ".mc1", os.path.join(d, "memcard1.mcd"))
    shutil.copy(base + ".mc2", os.path.join(d, "memcard2.mcd"))
    state = os.path.join(d, "key.state")
    if os.path.exists(base + ".state.gz"):
        with gzip.open(base + ".state.gz", "rb") as f, open(state, "wb") as g:
            shutil.copyfileobj(f, g)
    else:
        shutil.copy(base + ".state", state)
    return d, state


def replay(s, key=0, until=0, dump=None, events=None):
    """The emulator over session s from keyframe `key`: the report, as text."""
    d, state = sandbox(s, key)
    k = next(t for t in keys(s) if t[0] == key)
    report = os.path.join(d, "report.txt")
    if os.path.exists(report):
        os.remove(report)
    env = dict(os.environ, KF_RUN=os.path.join(RUNS, s), KF_STATE=state, KF_FROM=f"{k[1]} {k[2]}",
               KF_UNTIL=str(until), KF_REPORT=report, KF_DUMP=dump or "",
               KF_EVENTS=events or "")
    n = (until or len(frames(s))) - k[1]
    stuck = ""
    with open(os.path.join(d, "emulator.log"), "w") as log:
        try:
            subprocess.run([APP, "-no-ui", "-stdout", "-bios", BIOS, "-iso", CUE, "-run",
                            "-interpreter", "-lua_stdout", "-dofile",
                            os.path.join(EMU, "replay.lua")], cwd=d, env=env, stdout=log,
                           stderr=subprocess.STDOUT, timeout=120 + 3 * n / SPEED)
        except subprocess.TimeoutExpired:
            stuck = "the emulator did not finish in time\n"
    if not os.path.exists(report):
        raise SystemExit(f"no report: see {os.path.join(d, 'emulator.log')}")
    with open(report) as f:
        return stuck + f.read()


def rd(ram, a, n=1, signed=False):
    return int.from_bytes(ram[a & 0x1FFFFF:(a & 0x1FFFFF) + n], "little", signed=signed)


def s12(v):
    v &= 0xFFF
    return v - 0x1000 if v & 0x800 else v


def look(ram, reach=0x6000):
    """What is about the player in a RAM image: the place, then the objects and
    the creatures within `reach`, nearest first."""
    import movement
    px, py, pz = (rd(ram, 0x801B25F0 + 4 * i, 4, True) for i in range(3))
    facing = rd(ram, 0x801B2612, 2)
    level = rd(ram, 0x8018FAD9)
    out = [f"level {level}, cell ({px >> 11}, {pz >> 11}), at ({px}, {py}, {pz}), facing {facing:#x}"]
    near = []
    for k in range(396):
        r = 0x80191A5C + 68 * k
        t = rd(ram, r + 6, 2)
        if t == 0xFF:
            continue
        x, y, z = (rd(ram, r + 0x14 + 4 * i, 4, True) for i in range(3))
        dx, dz = x - px, z - pz
        d = math.hypot(dx, dz)
        if d <= reach:
            ang = s12(movement.vec_angle(dx, dz) - facing)
            near.append((d, f"object {k:3d} type {t:3d} opcode {rd(ram, r + 4):#04x} state "
                            f"{rd(ram, r + 8, 2)} cell ({x >> 11}, {z >> 11}) y {y}, "
                            f"{d / 0x800:.1f} cells, {ang * 360 / 4096:+.0f} deg"))
    for k in range(200):
        a = 0x80185DA8 + 0x88 * k
        if rd(ram, a) == 0xFF:
            continue
        x, y, z = (rd(ram, a + 0x2C + 4 * i, 4, True) for i in range(3))
        dx, dz = x - px, z - pz
        d = math.hypot(dx, dz)
        if d <= reach:
            ang = s12(movement.vec_angle(dx, dz) - facing)
            near.append((d, f"creature {k:3d} category {rd(ram, a)} kind {rd(ram, a + 2)} model "
                            f"{rd(ram, a + 1)} state {rd(ram, a + 9)} hp {rd(ram, a + 0x1A, 2)} "
                            f"cell ({x >> 11}, {z >> 11}) y {y}, "
                            f"{d / 0x800:.1f} cells, {ang * 360 / 4096:+.0f} deg"))
    return out + [t for _d, t in sorted(near)]


def picture(s, n):
    """note-NNN.shot as a PNG beside it."""
    from PIL import Image
    base = os.path.join(RUNS, s, f"note-{n:03d}")
    if not os.path.exists(base + ".txt"):
        return None
    with open(base + ".txt") as f:
        w, h, bpp = (int(v) for v in f.read().split())
    with open(base + ".shot", "rb") as f:
        raw = f.read()
    if bpp == 0:                  # 16 bits, 5 to a colour, red lowest
        img = Image.new("RGB", (w, h))
        px = []
        for i in range(w * h):
            v = raw[2 * i] | (raw[2 * i + 1] << 8)
            px.append(((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3))
        img.putdata(px)
    else:
        img = Image.frombytes("RGB", (w, h), raw)
    img.save(base + ".png")
    return base + ".png"


def main():
    a = sys.argv[1:]
    if not a:
        show_list()
        return 0
    cmd, rest = a[0], a[1:]
    if cmd == "mark":
        with open(MARK + ".tmp", "w", encoding="utf-8") as f:
            f.write(" ".join(rest))
        os.replace(MARK + ".tmp", MARK)
        print("left for bp29.lua, which takes it within a second of play")
        return 0
    if cmd == "replay":
        key = int(rest[rest.index("--key") + 1]) if "--key" in rest else 0
        until = int(rest[rest.index("--until") + 1]) if "--until" in rest else 0
        names = [v for i, v in enumerate(rest) if not v.startswith("--")
                 and (i == 0 or not rest[i - 1].startswith("--"))]
        s = session(names[0] if names else None)
        t0 = time.time()
        text = replay(s, key, until)
        print(f"{s}, keyframe {key}, {time.time() - t0:.0f} s:")
        print(text.rstrip())
        m = re.search(r"^frames (\d+) same (\d+)", text, re.M)
        return 0 if m and m[1] == m[2] and int(m[1]) > 0 else 1
    if cmd == "dump":
        s = session(rest[0] if len(rest) > 2 else None)
        first, last = int(rest[-2]), int(rest[-1])
        k = max((t for t in keys(s) if t[1] < first), key=lambda t: t[1])
        out = os.path.join(RUNS, s, f"tables-{first}-{last}.zst")
        print(replay(s, k[0], last, f"{first} {last} {out}").rstrip())
        print(out, os.path.getsize(out))
        return 0
    if cmd == "events":
        s = session(rest[0] if rest else None)
        out = os.path.join(RUNS, s, "events.txt")
        if not os.path.exists(out):
            print(replay(s, 0, 0, None, out).splitlines()[-1])
        with open(out) as f:
            print(f.read().rstrip())
        return 0
    if cmd == "notes":
        s = session(rest[0] if rest else None)
        fr = frames(s)
        for n, frame, _calls, text in notes(s):
            f = fr[min(frame, len(fr)) - 1] if fr else None
            where = f"level {f['level']} cell ({f['x'] >> 11}, {f['z'] >> 11})" if f else ""
            print(f"{n}: frame {frame}, {where}: {text}")
        return 0
    if cmd == "note":
        s = session(rest[0] if len(rest) > 1 else None)
        n = int(rest[-1])
        with open(os.path.join(RUNS, s, f"note-{n:03d}.ram"), "rb") as f:
            ram = f.read()
        for line in look(ram):
            print(line)
        p = picture(s, n)
        if p:
            print(p)
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())

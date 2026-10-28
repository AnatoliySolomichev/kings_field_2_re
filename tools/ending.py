#!/usr/bin/env python3
"""The ending: END.EXE, read whole for what it does, against its own code.

    python3 tools/ending.py              its movies, their lengths and rectangles
    python3 tools/ending.py --check      the model against END.EXE's own code
    python3 tools/ending.py video        transcode the three movies for the port

`game_main` stops when the word at `$gp+0x1e4` goes non-zero, and 3 and 4
both hand the machine to **END.EXE** with `overlay_arg` (`0x800102f8`) 2 and
3 (FORMATS.md, "What a frame is"). END.EXE is a movie player and nothing
else. Its entry (`0x80011d04`) sets `$gp` to `0x80037498` and jumps to
**`end_main`** (`0x800119b8`), which sets the machine up -- the heap at
`0x80100000`, `CdInit`, the two display environments 320 by 240 one above the
other (`end_graphics`, `0x80011ae0`) -- and then:

```
overlay_arg 2   end_play_movie(0)   \\OP\\M4.S   3380 frames, letterboxed
                end_play_movie(1)   \\OP\\M5.S    942 frames
                VSync(0) sixty times -- a second of the last frame held
anything else   end_play_movie(2)   \\OP\\M6.S   1841 frames
then            next_exe and overlay_arg 0, an eight-instruction stop
                (0x8001c08c), CdControl(8) -- CdlStop -- and a loop on
                itself, forever
```

So the ending does not go back to the title: the machine stops on the last
frame of M6, and only a reset leaves it. The two bytes it zeroes are for a
shell that is never returned to.

**`end_play_movie(i)`** (`0x80011d14`) copies its three counts (`0x80011000`)
and three 20-byte names (`0x8001100c`) to the stack, finds the file
(`0x800175b4`; not found, it returns at once), sets the sound, the movie's
rectangle (`end_movie_rect`) and the decoder, and decodes a frame at a time
until the frame counter at `$gp+8` -- which the decoding's callbacks run up --
passes the movie's count, or the loop has gone round more times than it;
then `CdControl(9)`, CdlPause. **No button is read**: the ending's movies
cannot be skipped, as the opening's can.

**`end_movie_rect(i)`** (`0x80011f64`) lays out the decoder's buffers and the
picture: for movie 0 two rectangles 320 by 176 at y 32 and 272 (the
displays' 240 apart) and slices of 16 by 176 from y 32 -- a letterbox; for
the others 320 by 240 at y 0 and 240, slices of 16 by 240.

**How it is held to the game.** `main_check` runs END.EXE's own entry over a
blank RAM with the image laid in at `0x80011000`, every `overlay_arg` from
0 to 5 and a few at random, what main calls stood in for and logged, until
it reaches its loop on itself: the calls in order, the two bytes and the
loop reached. `rect_check` runs `end_movie_rect` for each index and others,
the 48 bytes it lays out against the model's. `play_check` runs
`end_play_movie` for each movie, the file found or not, the decoding stood
in for and the frame counter run up by 1, 2 or 3 a frame: the number of
frames it decodes, the name it asks for, the rectangle and the calls.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ENTRY, MAIN = 0x80011D04, 0x800119B8
PLAY, RECT, GRAPHICS = 0x80011D14, 0x80011F64, 0x80011AE0
SPIN = 0x80011AB8                    # main's last instruction: a jump to itself
GP = 0x80037498
COUNTS, NAMES, NAME_SIZE = 0x80011000, 0x8001100C, 20
NEXT_EXE, OVERLAY_ARG = 0x800102F0, 0x800102F8
FRAME_COUNTER = GP + 8
RECT_AT, RECT_SIZE = 0x8009B0DC, 0x30
HELD = 60                            # VSync(0) between M5 and M6: s0 from 0x3b to -1
VSYNC, CD_CONTROL, STOP = 0x8001C208, 0x80018198, 0x8001C08C
CDL_STOP, CDL_PAUSE = 8, 9
MAIN_STUBS = {0x80011CFC: "init", 0x8001B5A8: "init", 0x800126A8: "heap_init",
              0x80017318: "CdInit", 0x8001BFFC: "init", 0x80012A18: "init",
              0x80011C24: "init", GRAPHICS: "graphics", 0x8001449C: "PutDrawEnv",
              0x80014598: "PutDispEnv"}
FIND = 0x800175B4                    # the file's search: 0 not found
PLAY_STUBS = (0x8001C550, 0x8001C5A0, 0x8001208C, 0x80012220, 0x80011C60, 0x80012AFC,
              0x80013EC4, 0x80012B78, 0x80012348, 0x80017430)
FRAME_DONE = 0x80011CB0              # the loop's last call: here the counter runs up


def exe():
    import mips
    return mips.load("end")


def table(e=None):
    """[(name, frames)] -- the three movies, off END.EXE."""
    e = e or exe()
    counts = struct.unpack("<3i", e.bytes(COUNTS, 12))
    names = [e.bytes(NAMES + NAME_SIZE * i, NAME_SIZE).split(b"\0")[0].decode() for i in range(3)]
    return list(zip(names, counts))


def main_calls(arg):
    """end_main (0x800119b8) after the set-up: [the calls] for overlay_arg
    `arg` -- it ends on its loop with next_exe and overlay_arg 0."""
    out = []
    if arg & 0xFF == 2:
        out += [("movie", 0), ("movie", 1)] + [("vsync", 0)] * HELD
    out += [("movie", 2), ("stop",), ("cd", CDL_STOP, 0, 0)]
    return out


def movie_rect(i):
    """end_movie_rect (0x80011f64): {address: (bytes, value)} it lays out."""
    full = i != 0
    y, h = (0, 0xF0) if full else (0x20, 0xB0)
    out = {0x8009B0DC: (4, 0x800374DC), 0x8009B0E0: (4, 0x8005F4DC), 0x8009B0E4: (4, 0),
           0x8009B0E8: (4, 0x800874DC), 0x8009B0FC: (4, 0), 0x8009B108: (4, 0)}
    for a, v in ((0x8009B0EC, 0), (0x8009B0EE, y), (0x8009B0F0, 0x140), (0x8009B0F2, h),
                 (0x8009B0F4, 0), (0x8009B0F6, 0xF0 + y), (0x8009B0F8, 0x140), (0x8009B0FA, h),
                 (0x8009B100, 0), (0x8009B102, y), (0x8009B104, 0x10), (0x8009B106, h)):
        out[a] = (2, v)
    return out


def frames_decoded(count, step):
    """end_play_movie's loop: frames until the counter, run up by `step` a
    frame, passes `count` or the loop has gone round more than `count`."""
    counter = done = 0
    while True:
        counter += step
        done += 1
        if count < counter:
            return done
        if count < done:
            return done


# --- against END.EXE's own --------------------------------------------------------

class Spun(Exception):
    """main reached its loop on itself."""


def _cpu(e):
    import mipsrun
    ram = bytearray(0x200000)
    o = e.base & 0x1FFFFF
    ram[o:o + e.size] = e.bytes(e.base, e.size)
    return mipsrun.CPU(ram)


def main_check(out=sys.stdout, seed=89):
    rng = random.Random(seed)
    e = exe()
    ok = n = 0
    first = None
    for arg in list(range(6)) + [rng.randrange(0x100) for _ in range(6)]:
        cpu = _cpu(e)
        cpu.wr(OVERLAY_ARG, 1, arg)
        cpu.wr(NEXT_EXE, 1, rng.choice((1, 2)))
        got = []
        for a in MAIN_STUBS:
            cpu.hooks[a] = lambda c: 0
        cpu.hooks[VSYNC] = lambda c: got.append(("vsync", c.r[4]))
        cpu.hooks[PLAY] = lambda c: got.append(("movie", c.r[4]))
        cpu.hooks[STOP] = lambda c: got.append(("stop",))
        cpu.hooks[CD_CONTROL] = lambda c: got.append(("cd", c.r[4], c.r[5], c.r[6]))

        def spin(c):
            raise Spun()
        cpu.watch[SPIN] = spin
        spun = False
        try:
            cpu.call(ENTRY, limit=200000)
        except Spun:
            spun = True
        good = (spun and got == main_calls(arg) and cpu.rd(NEXT_EXE, 1) == 0
                and cpu.rd(OVERLAY_ARG, 1) == 0 and cpu.r[28] == GP)
        n += 1
        ok += good
        if not good and first is None:
            first = f"arg {arg}: spun {spun}, game {got[:6]}..., model {main_calls(arg)[:6]}..."
    print(f"  end_main, the game's own from its entry: {ok} of {n} overlay_args -- the calls "
          f"in order, next_exe and overlay_arg 0, $gp, and the loop on itself reached", file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return ok == n


def rect_check(out=sys.stdout):
    e = exe()
    ok = n = 0
    for i in (0, 1, 2, 3, 0xFF, 0x80000000):
        cpu = _cpu(e)
        for k in range(RECT_SIZE):
            cpu.wr(RECT_AT + k, 1, 0xA5)
        cpu.call(RECT, i)
        want = bytearray([0xA5] * RECT_SIZE)
        for a, (size, v) in movie_rect(i).items():
            want[a - RECT_AT:a - RECT_AT + size] = (v & ((1 << (8 * size)) - 1)).to_bytes(size, "little")
        got = bytes(cpu.ram[(RECT_AT & 0x1FFFFF):(RECT_AT & 0x1FFFFF) + RECT_SIZE])
        n += 1
        ok += got == bytes(want)
    print(f"  end_movie_rect, the game's own: {ok} of {n} indices, the {RECT_SIZE} bytes it "
          f"lays out", file=out)
    return ok == n


def play_check(out=sys.stdout, seed=97):
    rng = random.Random(seed)
    e = exe()
    tab = table(e)
    ok = n = 0
    first = None
    for i in range(3):
        for found in (1, 1, 0):
            step = rng.choice((1, 2, 3))
            cpu = _cpu(e)
            cpu.r[28] = GP
            asked = []
            frames = [0]

            def find(c):
                o = c.r[5] & 0x1FFFFF
                asked.append(bytes(c.ram[o:o + NAME_SIZE]).split(b"\0")[0].decode())
                return found
            cpu.hooks[FIND] = find
            for a in PLAY_STUBS:
                cpu.hooks[a] = lambda c: 0

            def frame(c, step=step):
                frames[0] += 1
                c.wr(FRAME_COUNTER, 4, c.rd(FRAME_COUNTER, 4) + step)
            cpu.hooks[FRAME_DONE] = frame
            pause = []
            cpu.hooks[0x8001841C] = lambda c: pause.append((c.r[4], c.r[5], c.r[6]))
            cpu.call(PLAY, i, limit=50_000_000)
            name, count = tab[i]
            want_frames = frames_decoded(count, step) if found else 0
            rect = {a: cpu.rd(a, size) for a, (size, _v) in movie_rect(i).items()}
            good = (asked == [name] and frames[0] == want_frames
                    and pause == ([(CDL_PAUSE, 0, 0)] if found else [])
                    and (not found or rect == {a: v for a, (_s, v) in movie_rect(i).items()}))
            n += 1
            ok += good
            if not good and first is None:
                first = (f"movie {i} found {found} step {step}: asked {asked}, frames "
                         f"{frames[0]} (model {want_frames}), pause {pause}")
    print(f"  end_play_movie, the game's own: {ok} of {n} runs -- the name it asks for, the "
          f"frames it decodes until the counter passes the count, the rectangle and the pause",
          file=out)
    if first:
        print(f"  first difference: {first}", file=out)
    return ok == n


def check(out=sys.stdout):
    a = main_check(out)
    b = rect_check(out)
    c = play_check(out)
    print(f"END.EXE, against its own code: {'all agree' if a and b and c else 'NOT ALL AGREE'}",
          file=out)
    return a and b and c


def video(out="out/godot/opening"):
    """The three movies as Ogg Theora, ending0..2.ogv, as tools/opening.py
    transcodes the opening's."""
    import subprocess
    import tempfile
    import opening
    import psxiso
    os.makedirs(out, exist_ok=True)
    disc = psxiso.Disc(opening.IMG)
    for i, (name, _count) in enumerate(table()):
        path = name.replace("\\", "/").split(";")[0]
        dst = f"{out}/ending{i}.ogv"
        with tempfile.NamedTemporaryFile(suffix=".str", delete=False) as tf:
            tmp = tf.name
        try:
            opening.raw_stream(disc, path, tmp)
            r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", tmp,
                                "-c:v", "libtheora", "-q:v", "7", "-c:a", "libvorbis", "-q:a", "4",
                                dst], capture_output=True, text=True)
            if r.returncode:
                print(f"  ending{i}: ffmpeg failed -- {r.stderr.strip()[:120]}")
                continue
            print(f"  ending{i}.ogv  {path}  {os.path.getsize(dst) / 1e6:.1f} MB")
        finally:
            os.unlink(tmp)


def export(out_dir):
    """ending.json for the port: the three movies' names and counts."""
    import json
    rows = [{"name": n, "frames": c, "letterbox": i == 0} for i, (n, c) in enumerate(table())]
    rng = random.Random(101)
    check = {"plans": [[arg, [list(c) for c in main_calls(arg) if c[0] in ("movie", "vsync")]]
                       for arg in list(range(6)) + [rng.randrange(0x100) for _ in range(4)]],
             "rects": [[i, movie_rect(i)[0x8009B0EE][1], movie_rect(i)[0x8009B0F2][1]]
                       for i in range(3)],
             "frames": [[c, s, frames_decoded(c, s)] for c in (0, 1, 2, 942, 1841, 3380)
                        for s in (1, 2, 3)]}
    path = os.path.join(out_dir, "ending.json")
    with open(path, "w") as fh:
        json.dump({"_note": "END.EXE 0x80011000 and 0x8001100c (tools/ending.py wrote it)",
                   "movies": rows, "held": HELD, "check": check}, fh)
    return path


def main():
    a = sys.argv[1:]
    if "--check" in a:
        sys.exit(0 if check() else 1)
    if "video" in a:
        video()
        return
    print(__doc__.split("**How it is held")[0])
    for i, (name, count) in enumerate(table()):
        print(f"  movie {i}: {name:12s} {count:5d} frames, {count / 15:6.1f} s at 15 a second, "
              f"{'320x176 at y 32' if i == 0 else '320x240'}")


if __name__ == "__main__":
    main()

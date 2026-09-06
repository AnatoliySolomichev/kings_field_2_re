#!/usr/bin/env python3
"""The opening's assets, out of the disc and into the port.

`OPEN.EXE` draws its title screen out of one file and its logos out of six
movies, and this extracts all of them plus a manifest saying which is which,
so `godot/opening.gd` can run the same sequence over the same pictures.

    python3 tools/opening.py                 into out/godot/opening/
    python3 tools/opening.py video           transcode the movies so they play
    python3 tools/opening.py title           compose the title screen
    python3 tools/opening.py out/op          somewhere else

What it writes:

* `opd0..opd4.png` -- the five TIMs inside `OP.D`, at the VRAM coordinates the
  title screen's `GetTPage` calls name: the artwork, the two halves of the
  logo, the menu text and the loading screen;
* one frame out of each movie `play_movie` can be asked for, decoded with
  `tools/str.py`, so the logos in the port are the game's own;
* `opening.json`, the sequence itself -- which movie each index is, and what
  the title screen is made of.

The movies are streamed off the disc a sector at a time by the real thing and
are 180 MB in total, so the port shows a still of each rather than playing
them. That is a deliberate limit, not a decode failure: `tools/str.py png`
writes any frame of any of them.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, "tools")
import psxiso  # noqa: E402
import str as strmod  # noqa: E402  (the movie reader, not the builtin)
import tim  # noqa: E402

IMG = "emu/kf2.img"

# play_movie's own table, from OPEN.EXE 0x80011028: five 20-byte slots. The
# names on the right are what each one turned out to be once decoded.
MOVIES = [
    (0, "/OP/M0.S", 900, "the attract movie, played after the ASCII logo"),
    (1, "/OP/M1.S", 900, "the second attract movie, alternating with M0"),
    (2, "/OP/M3.S", 200, "the opening story, played only when a new game starts"),
    (3, "/OP/L0.S", 120, "the ASCII Entertainment logo, first thing on the disc"),
    (4, "/OP/L1.S", 60, "the FromSoftware logo, at the top of each attract cycle"),
]
# Not in that table: OPEN.EXE 0x8001273c streams this one on its own behind the
# title screen. Its video track is 16x16, so what it carries is the music.
TITLE_STREAM = ("/OP/M2.S", "the title screen's streamed music")

TIMS = [
    ("the title artwork", "8 bit, VRAM (640,0)"),
    ("KING'S", "8 bit, VRAM (640,256)"),
    ("FIELD II", "8 bit, VRAM (640,384)"),
    ("the menu text: NEW, CONTINUE and the two copyright lines",
     "4 bit with three CLUTs, VRAM (896,0) -- the CLUT picks which entry is lit"),
    ("Program Loading", "4 bit, VRAM (960,0)"),
]


def opd(disc, out):
    """Every TIM in OP.D, as PNG, with where it goes in video memory."""
    lba, size = strmod.find(disc, "/OP/OP.D")
    d = disc.read(lba, size)
    got = []
    for n, (pos, r) in enumerate(tim.scan(d)):
        w, h, px, _nxt, (dx, dy), cluts = r
        tim.write_png(f"{out}/opd{n}.png", w, h, px)
        what = TIMS[n] if n < len(TIMS) else ("?", "?")
        got.append({"file": f"opd{n}.png", "w": w, "h": h, "vram": [dx, dy],
                    "cluts": len(cluts), "what": what[0], "where": what[1]})
        print(f"  opd{n}.png  {w}x{h} at VRAM ({dx},{dy})  {what[0]}")
    # The VAB after the last TIM is the title screen's sounds; the cursor is
    # 0x5a and the confirm is 0x3a, from the menu handler's own calls.
    tail = d[_nxt:] if got else b""
    if tail[:4] == b"pBAV":
        open(f"{out}/opening.vab", "wb").write(tail)
        print(f"  opening.vab  {len(tail)} bytes, the menu's sound bank")
    return got


def stills(disc, out):
    got = []
    for idx, path, frame, what in MOVIES:
        lba, size = strmod.find(disc, path)
        name = f"movie{idx}.png"
        for num, w, h, data in strmod.frames(disc, lba, size):
            if num < frame:
                continue
            img, used, decl, left = strmod.decode(data, w, h)
            if img is None:
                print(f"  {path}: frame {num} did not decode")
                break
            strmod.write_png(f"{out}/{name}", w, h, img)
            print(f"  {name}  {path} frame {num}  {w}x{h}  "
                  f"{left} bits of padding left")
            got.append({"index": idx, "file": name, "path": path, "frame": num,
                        "w": w, "h": h, "what": what})
            break
    return got


# The title screen, at the coordinates the three layer routines write into
# their primitives. Everything here was read out of OPEN.EXE: layer_a
# (0x8001279c) stretches the artwork over the whole 640x240 screen and puts the
# two halves of the logo at these rectangles, layer_b (0x80012b0c) draws the
# copyright lines and layer_c (0x80012ea0) the two menu entries, each a 96x8
# strip of the same image.
TITLE_LAYOUT = [
    (0, (0, 0, 640, 240), None, "the artwork, stretched over the screen"),
    (1, (64, 44, 256, 89), None, "KING'S"),
    (2, (320, 128, 256, 89), None, "FIELD II"),
    (3, (124, 154, 255, 12), (0, 0, 255, 12), "(c) 1996 FROM Software Inc."),
    (3, (124, 172, 255, 12), (0, 24, 255, 12), "(c) 1996 ASCII Entertainment"),
    (3, (272, 190, 96, 8), (0, 16, 96, 8), "NEW"),
    (3, (272, 202, 96, 8), (96, 16, 96, 8), "CONTINUE"),
]


def title(disc, path="out/op/title.png"):
    """Compose the title screen the way OPEN.EXE draws it, and write it out.

    This is what makes the rectangles checkable: they came off the POLY_FT4s in
    the code, and if any of them were misread the picture would say so.
    """
    lba, size = strmod.find(disc, "/OP/OP.D")
    d = disc.read(lba, size)
    imgs = []
    for _pos, r in tim.scan(d):
        w, h, px, _nxt, _vram, _cluts = r
        imgs.append((w, h, px))
    out = [(0, 0, 0, 255)] * (640 * 240)
    for idx, (dx, dy, dw, dh), src, _what in TITLE_LAYOUT:
        w, h, px = imgs[idx]
        sx, sy, sw, sh = src if src else (0, 0, w, h)
        for y in range(dh):
            for x in range(dw):
                p = px[(sy + y * sh // dh) * w + sx + x * sw // dw]
                if p[3] == 0:
                    continue
                out[(dy + y) * 640 + dx + x] = p
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tim.write_png(path, 640, 240, out)
    print(f"title screen -> {path}  640x240, the game's own screen size")


def raw_stream(disc, path, dest):
    """A movie's sectors, byte for byte, into a file ffmpeg's demuxer reads.

    `psxstr` wants whole 2352-byte sectors -- subheaders and all -- because the
    video and the XA audio are interleaved by subheader and there is no other
    way to tell them apart.
    """
    lba, size = strmod.find(disc, path)
    with open(dest, "wb") as f:
        for i in range((size + 2047) // 2048):
            f.write(disc.raw(lba + i))
    return dest


def video(out="out/godot/opening", only=None):
    """Transcode the opening's movies so the port can play them.

    `tools/str.py` is this project's own reading of the format and is what
    checked it. This is not that: ffmpeg carries a `psxstr` demuxer and an
    `mdec` decoder, so it turns the sectors straight into Ogg Theora with the
    XA audio attached, and Godot plays that. Two facts come back out of it that
    are worth having on their own -- the movies run at **15 frames a second**
    and the audio is 37800 Hz stereo, both read off the stream rather than
    guessed.
    """
    os.makedirs(out, exist_ok=True)
    disc = psxiso.Disc(IMG)
    jobs = [(f"movie{i}", p) for i, p, _f, _w in MOVIES]
    jobs.append(("title_music", TITLE_STREAM[0]))
    for name, path in jobs:
        if only and name != only:
            continue
        dst = f"{out}/{name}.ogv"
        with tempfile.NamedTemporaryFile(suffix=".str", delete=False) as tf:
            tmp = tf.name
        try:
            raw_stream(disc, path, tmp)
            # The title stream's video track is 16x16 filler, so only its audio
            # is worth keeping.
            args = (["-vn", "-c:a", "libvorbis", "-q:a", "4"]
                    if name == "title_music"
                    else ["-c:v", "libtheora", "-q:v", "7",
                          "-c:a", "libvorbis", "-q:a", "4"])
            if name == "title_music":
                dst = f"{out}/{name}.ogg"
            r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel",
                                "error", "-i", tmp] + args + [dst],
                               capture_output=True, text=True)
            if r.returncode:
                print(f"  {name}: ffmpeg failed -- {r.stderr.strip()[:120]}")
                continue
            mb = os.path.getsize(dst) / 1e6
            print(f"  {os.path.basename(dst)}  {path}  {mb:.1f} MB")
        finally:
            os.unlink(tmp)


def main(out="out/godot/opening"):
    os.makedirs(out, exist_ok=True)
    disc = psxiso.Disc(IMG)
    print(f"opening assets into {out}/")
    tims = opd(disc, out)
    movies = stills(disc, out)
    manifest = {
        "_note": "The opening sequence, as OPEN.EXE runs it. See BOOT.md.",
        "tims": tims,
        "movies": movies,
        "title_stream": {"path": TITLE_STREAM[0], "what": TITLE_STREAM[1]},
        "menu": {"entries": ["NEW", "CONTINUE"],
                 "timeout_frames": 376,
                 "note": "376 is the 0x178 open_main counts to before giving up "
                         "on the player and going back to the attract movies"},
    }
    json.dump(manifest, open(f"{out}/opening.json", "w"), indent=1)
    print(f"  opening.json  {len(tims)} images, {len(movies)} movie stills")
    # The stills are the fallback; what the port would rather have is the
    # movies themselves. Transcoding is minutes of ffmpeg, so it only runs for
    # the ones that are not there yet.
    missing = [f"movie{i}" for i, _p, _f, _w in MOVIES
               if not os.path.exists(f"{out}/movie{i}.ogv")]
    if not os.path.exists(f"{out}/title_music.ogg"):
        missing.append("title_music")
    if not missing:
        return
    if not shutil.which("ffmpeg"):
        print("  ffmpeg not found, so the movies stay as stills")
        return
    for name in missing:
        video(out, only=name)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "title":
        title(psxiso.Disc(IMG),
              sys.argv[2] if len(sys.argv) > 2 else "out/op/title.png")
    elif len(sys.argv) > 1 and sys.argv[1] == "video":
        video(only=sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "out/godot/opening")

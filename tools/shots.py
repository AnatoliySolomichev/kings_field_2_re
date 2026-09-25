#!/usr/bin/env python3
"""The port, seen from where each snapshot's screenshot was taken, beside it.

    python3 tools/shots.py            every snapshot with a level and a .png
    python3 tools/shots.py b chest1   just those

Every snapshot `tools/snap.py` took carries the game's own screenshot and, in
its RAM, the camera: `player_pos` (0x801b25f0), the facing (0x801b2612) and the
pitch (0x801b2610). This puts the port's camera at the same place, renders one
frame, and writes `out/shots/<name>.png` -- the game's 320x240 on the left,
doubled, and the port's 640x480 on the right. It is the check nobody could make
by reading: a door drawn inside its wall, a bottle standing in front of a chest,
a sea that was not there -- this session found all three that way.

It needs a display, because Godot renders nothing headless, and it opens a
window for a second or two. And it writes its frames inside the project first:
Godot installed as a snap may not write anywhere else, so the frames go to
`res://` and are moved out afterwards.

The comparison is by eye. The port has no HUD and no creatures' animation, and
the game's screenshot has both, so nothing here scores the pair.
"""
import glob
import os
import shutil
import struct
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tim                                                            # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GODOT = os.path.join(ROOT, "out", "godot")
OUT = os.path.join(ROOT, "out", "shots")

SCRIPT = '''extends SceneTree
# Written by tools/shots.py and deleted after it runs.
var world: Node
var n := 0
var k := 0
var poses := %s
func _init() -> void:
	world = load("res://world.tscn").instantiate()
	root.add_child(world)
	for name in ["Cutscene", "UI"]:
		var c = world.get_node_or_null(name)
		if c:
			c.queue_free()
func _process(_dt: float) -> bool:
	n += 1
	var p = world.get_node("Player")
	p.set_process(false)
	var q = poses[k]
	p.gx = q[1]; p.gy = q[2]; p.gz = q[3]
	p._to_godot()
	p.rotation.y = float(q[4]) * TAU / 4096.0
	p.get_node("Camera").rotation.x = -float(q[5]) * TAU / 4096.0
	if n %% 20 == 0:
		root.get_viewport().get_texture().get_image().save_png("res://zz_shot_%%s.png" %% q[0])
		k += 1
		if k >= poses.size():
			return true
	return false
'''


def read_png(path):
    """(width, height, rows of RGB bytes) for an 8-bit RGB or RGBA PNG."""
    b = open(path, "rb").read()
    p, idat, w, h, ct = 8, b"", 0, 0, 2
    while p < len(b):
        n = struct.unpack(">I", b[p:p + 4])[0]
        t = b[p + 4:p + 8]
        if t == b"IHDR":
            w, h, _bd, ct = struct.unpack(">IIBB", b[p + 8:p + 18])
        elif t == b"IDAT":
            idat += b[p + 8:p + 8 + n]
        p += 12 + n
    bpp = 4 if ct == 6 else 3
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            c = prev[i - bpp] if i >= bpp else 0
            up = prev[i]
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + up) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + up) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(up - c), abs(a - c), abs(a + up - 2 * c)
                pr = a if pa <= pb and pa <= pc else (up if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        prev = line
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)])
    return w, h, rows


def poses(only=()):
    out = []
    for ram_path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        name = os.path.basename(ram_path)[:-4]
        if only and name not in only:
            continue
        if not os.path.exists(ram_path[:-4] + ".png"):
            continue
        r = open(ram_path, "rb").read()
        if r[0x191A5C + 6] == 0:                  # no level ever loaded
            continue
        x, y, z = struct.unpack_from("<3i", r, 0x1B25F0)
        facing = struct.unpack_from("<h", r, 0x1B2612)[0] & 0xFFF
        pitch = struct.unpack_from("<h", r, 0x1B2610)[0]
        out.append((name, x, y, z, facing, pitch, r[0x18FAD9]))
    return out


def main():
    only = tuple(sys.argv[1:])
    godot = shutil.which("godot-4") or shutil.which("godot")
    if not godot:
        print("godot not found")
        return
    lv = int(open(os.path.join(GODOT, "project.godot")).read()
             .split("level ")[1].split('"')[0])
    todo = [p for p in poses(only) if p[6] == lv]
    if not todo:
        print(f"no snapshot with a screenshot on level {lv}, the level out/godot holds")
        return
    script = os.path.join(GODOT, "zz_shots.gd")
    with open(script, "w") as f:
        f.write(SCRIPT % repr([list(p[:6]) for p in todo]).replace("(", "[").replace(")", "]"))
    try:
        subprocess.run([godot, "--path", GODOT, "--resolution", "640x480",
                        "--position", "40,40", "-s", "res://zz_shots.gd"],
                       capture_output=True, timeout=300)
    finally:
        for leftover in (script, script + ".uid"):
            if os.path.exists(leftover):
                os.remove(leftover)
    os.makedirs(OUT, exist_ok=True)
    for name, *_rest in todo:
        frame = os.path.join(GODOT, f"zz_shot_{name}.png")
        if not os.path.exists(frame):
            print(f"{name}: no frame came out")
            continue
        _w, _h, port = read_png(frame)
        _gw, _gh, game = read_png(os.path.join(ROOT, "out", "snap", name + ".png"))
        os.remove(frame)
        if os.path.exists(frame + ".import"):
            os.remove(frame + ".import")
        px = []
        for y in range(480):
            left = [game[y // 2][x // 2] + (255,) for x in range(640)]
            right = [c + (255,) for c in port[y]]
            px += left + [(0, 0, 0, 255)] * 8 + right
        path = os.path.join(OUT, f"{name}.png")
        tim.write_png(path, 640 + 8 + 640, 480, px)
        print(f"{name}: the game on the left, the port on the right -> "
              f"{os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()

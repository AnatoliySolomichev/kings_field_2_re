#!/usr/bin/env python3
"""A frame's GPU primitives, read back out of a RAM snapshot.

    python3 tools/gpuframe.py inv1              both buffers' primitives, by kind
    python3 tools/gpuframe.py inv1 sprites      every sprite, in drawing order
    python3 tools/gpuframe.py inv1 all          every primitive

The game builds each frame as packets linked into an ordering table and hands
the table to the GPU. `frame_begin` (`0x80026fe4`, the menus') and
`frame_begin_3d` (`0x80035630`, the world's) flip between two buffers: the
slot record at `0x80199158 + 12 * i` and the ordering table at
`0x80199174 + 0x8000 * i`, cleared with ClearOTagR, so each entry links to the
one before it and the GPU starts from the last. A snapshot catches one buffer
being filled and the other as it was sent -- a whole frame, every sprite and
quad with its place, UV, CLUT and texture page. That is the game's own answer
to "what is on the screen", to hold a port's screens to.

A packet is a tag word -- the next packet's address in the low 24 bits, the
length in words in the high 8 -- and that many words of GP0 commands.
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OT_BASE, OT_SPAN, OT_LEN = 0x80199174, 0x8000, 0x2000
END = 0xFFFFFF


def u32(ram, a):
    return struct.unpack_from("<I", ram, a & 0x1FFFFF)[0]


def walk(ram, base, n=OT_LEN, limit=200000):
    """[(depth, address, words)] of every packet linked from the ordering
    table at `base`, in the order the GPU draws them (from the last entry)."""
    out = []
    seen = set()
    # ClearOTagR: entry k links to entry k-1; the GPU starts at entry n-1.
    a = base + 4 * (n - 1)
    depth_of = {base + 4 * k: k for k in range(n)}
    depth = n - 1
    for _ in range(limit):
        if a in seen:
            break
        seen.add(a)
        tag = u32(ram, a)
        ln = tag >> 24
        if a in depth_of:
            depth = depth_of[a]
        elif ln:
            out.append((depth, a, [u32(ram, a + 4 + 4 * i) for i in range(ln)]))
        nxt = tag & 0xFFFFFF
        if nxt == END:
            break
        a = 0x80000000 | nxt
    return out


def decode(words):
    """One packet's GP0 commands as dicts -- the kinds the game's screens use."""
    out = []
    i = 0
    while i < len(words):
        w = words[i]
        cmd = w >> 24
        if cmd == 0xE1:                              # DR_TPAGE (draw mode)
            out.append({"kind": "tpage", "tpage": w & 0x7FF,
                        "abr": (w >> 5) & 3, "depth": (w >> 7) & 3})
            i += 1
        elif 0x64 <= cmd <= 0x67 or cmd in (0x6C, 0x6D, 0x6E, 0x6F, 0x74, 0x75,
                                             0x76, 0x77, 0x7C, 0x7D, 0x7E, 0x7F):
            rgb = w & 0xFFFFFF
            xy = words[i + 1]
            uvc = words[i + 2]
            x, y = struct.unpack("<hh", struct.pack("<I", xy))
            u, v, clut = uvc & 0xFF, (uvc >> 8) & 0xFF, uvc >> 16
            if cmd & 0xFC == 0x64:
                wh = words[i + 3]
                wdt, hgt = wh & 0xFFFF, wh >> 16
                n = 4
            else:
                wdt = hgt = {0x6C: 1, 0x74: 8, 0x7C: 16}[cmd & 0xFC]
                n = 3
            out.append({"kind": "sprite", "x": x, "y": y, "w": wdt, "h": hgt,
                        "u": u, "v": v, "clut": clut, "rgb": rgb,
                        "semi": bool(cmd & 2), "raw": bool(cmd & 1)})
            i += n
        elif cmd & 0xFC == 0x2C:                     # POLY_FT4
            rgb = w & 0xFFFFFF
            pts, uvs = [], []
            clut = tpage = 0
            for k in range(4):
                xy = words[i + 1 + 2 * k]
                uv = words[i + 2 + 2 * k]
                pts.append(struct.unpack("<hh", struct.pack("<I", xy)))
                uvs.append((uv & 0xFF, (uv >> 8) & 0xFF))
                if k == 0:
                    clut = uv >> 16
                if k == 1:
                    tpage = uv >> 16
            out.append({"kind": "quad", "pts": pts, "uvs": uvs, "clut": clut,
                        "tpage": tpage, "rgb": rgb, "semi": bool(cmd & 2)})
            i += 9
        elif cmd & 0xFC in (0x34, 0x3C, 0x24):       # POLY_GT3, POLY_GT4, POLY_FT3
            n = {0x34: 3, 0x3C: 4, 0x24: 3}[cmd & 0xFC]
            shaded = cmd & 0xFC != 0x24
            step = 3 if shaded else 2
            pts, uvs = [], []
            clut = tpage = 0
            for k in range(n):
                # FT3: colour, then (xy, uv) per corner; GT3/GT4: colour, xy,
                # uv for the first corner and (colour, xy, uv) for the rest
                xy = words[i + 1 + step * k] if not shaded or k == 0 else words[i + step * k]
                uv = words[i + 2 + step * k] if not shaded or k == 0 else words[i + 1 + step * k]
                pts.append(struct.unpack("<hh", struct.pack("<I", xy)))
                uvs.append((uv & 0xFF, (uv >> 8) & 0xFF))
                if k == 0:
                    clut = uv >> 16
                if k == 1:
                    tpage = uv >> 16
            out.append({"kind": {0x34: "gt3", 0x3C: "gt4", 0x24: "ft3"}[cmd & 0xFC],
                        "pts": pts, "uvs": uvs, "clut": clut, "tpage": tpage,
                        "semi": bool(cmd & 2)})
            i += 1 + (3 * n - 1 if shaded else 2 * n)
        elif cmd == 0x00:                            # a NOP word
            i += 1
        elif cmd & 0xFC == 0x28:                     # POLY_F4
            pts = [struct.unpack("<hh", struct.pack("<I", words[i + 1 + k]))
                   for k in range(4)]
            out.append({"kind": "flat4", "pts": pts, "rgb": w & 0xFFFFFF,
                        "semi": bool(cmd & 2)})
            i += 5
        elif cmd & 0xFC == 0x20:                     # POLY_F3
            pts = [struct.unpack("<hh", struct.pack("<I", words[i + 1 + k]))
                   for k in range(3)]
            out.append({"kind": "flat3", "pts": pts, "rgb": w & 0xFFFFFF,
                        "semi": bool(cmd & 2)})
            i += 4
        elif cmd & 0xFC == 0x60:                     # TILE
            x, y = struct.unpack("<hh", struct.pack("<I", words[i + 1]))
            wh = words[i + 2]
            out.append({"kind": "tile", "x": x, "y": y, "w": wh & 0xFFFF,
                        "h": wh >> 16, "rgb": w & 0xFFFFFF, "semi": bool(cmd & 2)})
            i += 3
        else:
            out.append({"kind": f"cmd {cmd:#04x}", "words": words[i:]})
            break
    return out


def frame(ram, buf):
    """[(depth, primitive)] of buffer `buf` (0 or 1), in drawing order, each
    primitive with the texture page last set before it."""
    out = []
    tpage = abr = None
    for depth, _a, words in walk(ram, OT_BASE + OT_SPAN * buf):
        for p in decode(words):
            if p["kind"] == "tpage":
                tpage, abr = p["tpage"], p["abr"]
                continue
            if p["kind"] == "sprite":
                p["tpage"], p["abr"] = tpage, abr
            out.append((depth, p))
    return out


def load(name):
    path = name if os.path.exists(name) else os.path.join(ROOT, "out", "snap", name + ".ram")
    return open(path, "rb").read()


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    ram = load(a[0])
    what = a[1] if len(a) > 1 else "summary"
    for buf in (0, 1):
        prims = frame(ram, buf)
        kinds = {}
        for _d, p in prims:
            kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
        print(f"buffer {buf}: {len(prims)} primitives -- " +
              ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
        if what == "summary":
            continue
        for d, p in prims:
            if what == "sprites" and p["kind"] != "sprite":
                continue
            q = {k: v for k, v in p.items() if k != "words"}
            print(f"  depth {d:4d}  {q}")


if __name__ == "__main__":
    main()

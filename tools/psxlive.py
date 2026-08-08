#!/usr/bin/env python3
"""Live access to a running PCSX-Redux instance over its HTTP API.

Unlike the GDB stub (which pauses emulation on connect and would not resume),
these endpoints snapshot RAM and VRAM while the game keeps running.
"""
import sys
import urllib.request

sys.path.insert(0, "tools")
import tim  # noqa: E402

BASE = "http://127.0.0.1:8080/api/v1"
RAM_BASE = 0x80000000


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.read()


def running():
    import json
    return json.loads(_get("/execution-flow"))


def ram():
    return _get("/cpu/ram/raw")


def vram():
    return _get("/gpu/vram/raw")


def at(buf, addr, n):
    """Slice RAM by PlayStation address (KUSEG/KSEG0/KSEG1 all alias)."""
    return buf[(addr & 0x1FFFFF):(addr & 0x1FFFFF) + n]


def vram_png(path, buf=None, x=0, y=0, w=1024, h=512):
    """Dump VRAM (or a window of it) as a 16bpp RGB image."""
    buf = buf or vram()
    px = []
    for row in range(y, y + h):
        base = row * 1024 * 2
        for col in range(x, x + w):
            v = buf[base + col * 2] | (buf[base + col * 2 + 1] << 8)
            r = (v & 31) << 3
            g = ((v >> 5) & 31) << 3
            b = ((v >> 10) & 31) << 3
            px.append((r | r >> 5, g | g >> 5, b | b >> 5, 255))
    tim.write_png(path, w, h, px)
    return path


if __name__ == "__main__":
    print("state:", running())
    r = ram()
    print("RAM size:", len(r))
    for name, addr in (("boot", 0x80010000), ("exe", 0x80011000)):
        print(f"{name} @{addr:08x}:", at(r, addr, 32).hex())
    for f in ("GAME.EXE", "OPEN.EXE", "END.EXE"):
        ref = open(f"extract/{f}", "rb").read()[0x800:0x800 + 64]
        print(f"{f:9s} loaded at 0x80011000:", at(r, 0x80011000, 64) == ref)
    out = sys.argv[1] if len(sys.argv) > 1 else "out/vram.png"
    print("vram ->", vram_png(out))

#!/usr/bin/env python3
"""The player's stat block in RAM.

The starting addresses came from the GameShark code list for SLUS-00255 on
gamehacking.org, which is the one published source that targets this exact
disc. Every one of them was then checked here rather than taken on trust: each
is referenced by code in GAME.EXE, and the values track the HUD across the
snapshots in out/snap.

Two things the code list gets wrong, or at least leaves ambiguous:

  * HP and MP are stored **maximum first, current second**. The "Infinite HP"
    code writes both, so it never had to distinguish them. Snapshot chest1
    shows HP 022 on screen with 50 at +0x1a and 22 at +0x1c; snapshot door1
    shows HP 050 / MP 030 with 57 and 34 in the maxima.
  * the eight offensive and nine defensive figures are one array each, 9 wide,
    laid out slash, blow, stab, dark, holy, fire, earth, wind, water. The code
    list has no "dark" entry on the offensive side, so its magic labels there
    are all one slot off. Untested: no character we have snapshotted carries
    any magic attack at all. (unverified)

Usage:
    python3 tools/player.py                 # read a running emulator
    python3 tools/player.py chest1          # read out/snap/chest1.ram
"""
import struct
import sys

sys.path.insert(0, "tools")

RAM_BASE = 0x80000000
BASE = 0x801B24E0
INVENTORY = 0x800C85E8       # one byte per item id, 32 pieces of code touch it

# Offsets from BASE. u32 unless the name says otherwise.
FIELDS = [
    (0x00, "u32", "unknown_00"),        # 1 in every snapshot
    (0x04, "u32", "exp"),               # 0x8002b484 in the level-up routine
    (0x08, "u32", "exp_next"),          # 50 at level 1, 110 at level 2
    (0x0c, "u32", "unknown_0c"),        # 0xffffffff at level 1, 11 at level 2
    (0x10, "u32", "level"),             # 0x8002b4bc writes it
    (0x14, "u32", "unknown_14"),        # 0x100, constant so far
    (0x18, "u16", "unknown_18"),        # 0x1000, constant so far
    (0x1a, "u16", "hp_max"),
    (0x1c, "u16", "hp"),
    (0x1e, "u16", "mp_max"),
    (0x20, "u16", "mp"),
    (0x22, "u16", "weapon_meter"),      # 5000 full; the swing recharge
    (0x24, "u16", "unknown_24"),        # 5000
    (0x26, "u16", "magic_meter"),       # 5000 full
    (0x28, "u16", "unknown_28"),        # grows as the character does
    (0x36, "u16", "unknown_36"),        # 20 at level 1, 21 at level 2
    (0x40, "u16", "unknown_40"),        # 10 -> 11
    (0x44, "u16", "unknown_44"),        # 20 -> 21
    (0x4e, "u16", "unknown_4e"),        # 10 -> 11
    (0x54, "u32", "gold"),              # 0x8002b518 writes it
]
DAMAGE = ["slash", "blow", "stab", "dark", "holy", "fire", "earth", "wind", "water"]
OFFENSE = 0x58               # 9 x u16
DEFENSE = 0x6A               # 9 x u16

# The player position is kept in four copies that the game holds in step;
# writing one alone is undone within a frame. 0x801B25F0 is the one the object
# spawner reads when it places something in front of the player.
POS_COPIES = [0x801B0A10, 0x801B25F0, 0x801AEC4C, 0x801FFF98]


def read(buf):
    """Decode the block out of a 2 MB RAM image."""
    b = BASE - RAM_BASE
    out = {}
    for off, kind, name in FIELDS:
        fmt = "<I" if kind == "u32" else "<H"
        out[name] = struct.unpack_from(fmt, buf, b + off)[0]
    for arr, at in (("offense", OFFENSE), ("defense", DEFENSE)):
        out[arr] = {n: struct.unpack_from("<H", buf, b + at + i * 2)[0]
                    for i, n in enumerate(DAMAGE)}
    out["pos"] = list(struct.unpack_from("<iii", buf, POS_COPIES[2] - RAM_BASE))
    return out


def inventory(buf, limit=256):
    """Item id -> count, for whatever the player is carrying.

    Where the array ends is not established. Past roughly index 300 the bytes
    stop behaving like counts -- they hold the same values in every snapshot,
    including ones taken before and after a pickup -- so that is another table
    butted against this one, and the scan stops well short of it.
    """
    b = INVENTORY - RAM_BASE
    return {i: buf[b + i] for i in range(limit) if buf[b + i]}


def summary(p):
    return (f"level {p['level']}  HP {p['hp']}/{p['hp_max']}  "
            f"MP {p['mp']}/{p['mp_max']}  {p['gold']} gold  "
            f"exp {p['exp']}/{p['exp_next']}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        buf = open(f"out/snap/{sys.argv[1]}.ram", "rb").read()
    else:
        import psxlive
        buf = psxlive.ram()
    p = read(buf)
    print(summary(p))
    print("position", p["pos"])
    for arr in ("offense", "defense"):
        print(f"{arr:8s}", "  ".join(f"{k} {v}" for k, v in p[arr].items() if v))
    print("unknown ", "  ".join(f"{k[-2:]}={v}" for k, v in p.items()
                                if k.startswith("unknown")))
    inv = inventory(buf)
    print("carrying", inv if inv else "nothing")

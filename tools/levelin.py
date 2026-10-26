#!/usr/bin/env python3
"""What a level does as it comes in: every level's entry 5, against the overlays' own.

    python3 tools/levelin.py            what each level's entry 5 reads and writes
    python3 tools/levelin.py --check    the model against the overlays' own code
    python3 tools/levelin.py --export D levelincheck.json for the self-test

**Entry 5** (`level_hooks + 0x14`) is what `level_load` (`0x800188f0`) and
`enter_current_level` (`0x80017a88`) call once a level is in, after its
record (`apply_level_state`) and `0x80061918`: the level's own code putting
the world the story has made back where it was -- which creature appears
(an actor's category, `+0`: 8 held, never woken, 1 up), which door is
unlocked (`+0x38` 0xc8 to 0xff), which object is there at all (`+6`, the
type, 0xff gone; `+0`, the view byte, 0 not drawn and 2 drawn), which cells
a stamp_rect lays, and a few story flags. Every one ends by writing its own
number into story flag `0x85` (`0x801baa0d`), which level 10's reads: the
level last come into.

The code is a list of stores at fixed addresses under conditions on the
story flags, the pack and a handful of the objects' own bytes, so the model
is written that way -- `m.rd(address)`, `m.wr(address, value)` over the
game's own addresses -- and so is the port's copy (`godot/levelin.gd`),
which loot.gd maps to and from the port's fields.

Calls it makes that are not stores: `stamp_rect` (levels 1, 10, 14, 16, 17,
20), `has_item`, `key_test_all` (`0x800466e8`: key_test with one key on all
396 objects; levels 9 and 26), `object_signal` (26), find_free_slot and
init_object_record (17), and the level's own routines that change its look
(levels 4, 6 and 26: `0x801e83a4`, `0x801e83a8`, `0x801e8390` with tables of
the overlay and of `0x8008xxxx`), which are logged.

**Against what the game had in memory.** Section 17 of FORMATS.md had one
difference left between the disc's actor table and every snapshot: the two
men by level 0's house are category 1 on the disc and 8 in memory, and in
the level-4 snapshots slot 26 (model 22, at (46,61)) the same -- no store in
GAME.EXE writes a literal 8. The levels' own entry 5 does: level 0's while
story flag 0x1e is 0, level 4's while flag 0x19 is. `snapshot_check()` runs it over each snapshot's own flags
and pack on the disc's table: every snapshot with a level in it holds the
categories that makes, slot for slot.

**How it is held to the game.** `check()` runs each level's own entry 5 out
of its overlay with `tools/mipsrun.py`, over the level as its own
load_object_placement leaves it, with the story flags, the pack, the
figures, the player's level, `drop_count_gold` and the bytes of the objects
it asks drawn at random, `stamp_rect` and the look's routines stood in for
and logged: the model must make the same calls and leave the same RAM, all
of it but the stack.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import useitem                                                       # noqa: E402

MASK = 0x1FFFFF
ACTORS, ASTRIDE = 0x80185DA8, 0x88
OBJECTS, OSTRIDE, COUNT = 0x80191A5C, 0x44, 0x18C
FLAGS = 0x801BA988
INV_A, INV_B = 0x800C85E8, 0x800C867E
STAT36, SKILLS, PLAYER_LEVEL = 0x801B2516, 0x801B2518, 0x801B24F0
DROP_COUNT = 0x8019839A
LAST_LEVEL = 0x85                  # story flag 0x85, 0x801baa0d: the level last come into
STAMP_RECT = 0x800445B8
KEY_TEST_ALL = 0x800466E8
ENTRY = 5                          # level_hooks + 0x14
# the levels' own routines that change the look, by level: logged
LOOKS = {4: (0x801E83A4,), 6: (0x801E83A8,), 26: (0x801E8390,)}


def A(k, off=0):
    """An actor's byte."""
    return ACTORS + ASTRIDE * k + off


def O(k, off=0):
    """An object's byte."""
    return OBJECTS + OSTRIDE * k + off


def F(k):
    """A story flag."""
    return FLAGS + k


class Mem:
    """RAM as the model reads and writes it, and the calls it makes."""

    def __init__(self, ram):
        self.ram = bytearray(ram)
        self.calls = []
        self.read = {}                 # address: the byte as it was, first read before a write
        self.written = set()

    def rd(self, a, n=1):
        o = a & MASK
        for i in range(n):
            if (a + i) not in self.written and (a + i) not in self.read:
                self.read[a + i] = self.ram[o + i]
        return int.from_bytes(self.ram[o:o + n], "little")

    def wr(self, a, v, n=1):
        o = a & MASK
        self.ram[o:o + n] = (v & ((1 << (8 * n)) - 1)).to_bytes(n, "little")
        self.written.update(a + i for i in range(n))

    def has(self, item):
        """has_item (0x8005d7bc): both arrays' counts."""
        return self.rd(INV_A + item) + self.rd(INV_B + item)

    def stamp(self, *args):
        self.calls.append(("stamp",) + args)

    def look(self, at, *args):
        self.calls.append(("look", at) + args)


def key_test_all(m, key):
    """0x800466e8: key_test (0x80046608) with `key` on every object."""
    import chests
    if key & 0xFF == 0xFF:
        return
    for k in range(COUNT):
        r = O(k)
        _got, lock = chests.key_test(m.rd(r + 4), m.rd(r + 8, 2), m.rd(r + 0x38), key & 0xFF)
        m.wr(r + 0x38, lock)


def object_signal(m, sig):
    """object_signal (0x800463bc) over the RAM: tools/useitem.py's, on the
    records' bytes."""
    w = {"objects": []}
    for k in range(COUNT):
        r = O(k)
        w["objects"].append({"op": m.rd(r + 4), "state": m.rd(r + 8, 2), "b38": m.rd(r + 0x38),
                             "b39": m.rd(r + 0x39), "h3a": m.rd(r + 0x3A, 2),
                             "b3d": m.rd(r + 0x3D), "b3f": m.rd(r + 0x3F)})
    useitem.object_signal(w, sig)
    for k, o in enumerate(w["objects"]):
        r = O(k)
        m.wr(r + 8, o["state"], 2)
        m.wr(r + 0x38, o["b38"])
        m.wr(r + 0x39, o["b39"])
        m.wr(r + 0x3F, o["b3f"])


def free_slot(m, start, count, counter):
    """find_free_slot (0x80046034) over the RAM: the slot, or None."""
    chosen, age = None, 0
    for k in range(start, start + count):
        if m.rd(O(k, 6), 2) == 0xFF:
            return k
        if counter == -1:
            continue
        d = counter - m.rd(O(k, 0x3C), 2)
        if d < 0:
            d += 0x10000
        if age < d:
            chosen, age = k, d
    return chosen


def init_record(m, k):
    """init_object_record (0x800448b8)."""
    r = O(k)
    m.wr(r + 1, 0x80)
    for off in (0x30, 0x2E, 0x2C):
        m.wr(r + off, 0x1000, 2)
    for off in (0xA, 0x28, 0x24, 0x26, 0xE, 0x10):
        m.wr(r + off, 0, 2)
    m.wr(r + 2, 0)
    m.wr(r + 0, 0)
    m.wr(r + 4, 0xFF)
    m.wr(r + 5, 0xFF)


def lock_lift(m, k, want):
    """The pattern most levels use: an object's lock, if it is `want`, 0xff."""
    if m.rd(O(k, 0x38)) == want:
        m.wr(O(k, 0x38), 0xFF)


def cats(m, pairs):
    for k, v in pairs:
        m.wr(A(k), v)


def entry5(lv, m):
    """Level `lv`'s entry 5 over the RAM `m`."""
    f = lambda k: m.rd(F(k))                                     # noqa: E731
    if lv == 0:
        if f(0x16):
            for k in (70, 33, 116):
                lock_lift(m, k, 0xC8)
        # the three men by the house, and the two that stand for them
        if f(0x1E) == 0:
            men, d, e, x = (1, 8, 8), 0, 0, None
        elif f(0x2) == 0:
            men, d, e, x = (8, 1, 8), 0, 0, None
        elif f(0x6) == 0:
            men, d, e, x = (8, 8, 1), 0, 0, None
        elif f(0x7) == 0:
            men, d, e, x = (8, 8, 8), 2, 0xFF, 2
        else:
            men, d, e, x = (8, 8, 8), 0, 0, 0xFF
        cats(m, zip((0, 1, 2), men))
        if x is None:
            m.wr(O(214), 0)
            m.wr(O(214, 0x3C), 0)
            m.wr(O(177, 0x3E), 0)
            m.wr(O(111), 0)
            m.wr(O(111, 0x3C), 0)
            m.wr(O(182, 0x3E), 0)
            for k in (62, 195, 172):
                m.wr(O(k), 0)
                m.wr(O(k, 0x38), 0)
        elif x == 2:                    # flag 7 clear
            m.wr(O(214), 2)
            m.wr(O(214, 0x3C), 0xFF)
            m.wr(O(177, 0x3E), 0xFF)
            m.wr(O(111), 0)
            m.wr(O(111, 0x3C), 0)
            m.wr(O(182, 0x3E), 0)
            for k in (62, 195, 172):
                m.wr(O(k), 2)
                m.wr(O(k, 0x38), 0xFF)
        else:                           # every flag set
            m.wr(O(214), 0)
            m.wr(O(214, 0x3C), 0)
            m.wr(O(177, 0x3E), 0)
            m.wr(O(111), 2)
            m.wr(O(111, 0x3C), 0xFF)
            m.wr(O(182, 0x3E), 0xFF)
            for k in (62, 195, 172):
                m.wr(O(k), 0)
                m.wr(O(k, 0x38), 0)
        m.wr(F(3), 1 if all(m.has(t) > 0 for t in (2, 0x82, 0x83, 0x84)) else 0)
        if f(0x8) and m.rd(O(344, 0x38)) == 0xF1:
            m.wr(O(344, 0x38), 0xFF)
        if m.rd(O(158, 5)) == 0xFF:
            m.wr(O(158, 5), 0x3F)
            m.wr(O(158, 2), 7)
            m.wr(O(158, 0x10), 0x800, 2)
        m.wr(F(LAST_LEVEL), 0)
    elif lv == 1:
        if f(0xA):
            cats(m, ((20, 8), (10, 1), (25, 8), (23, 1), (24, 1), (40, 8)))
            lock_lift(m, 71, 0xC8)
            cats(m, ((22, 8), (39, 1)))
        else:
            cats(m, ((20, 1), (10, 8), (25, 1), (23, 8), (24, 1), (40, 8), (22, 1), (39, 8)))
        if f(0x20):
            cats(m, ((24, 8), (40, 1)))
        else:
            cats(m, ((24, 1), (40, 8)))
        sx = 0x4E if f(0xC) == 0 and f(0xD) else 0x4F       # flag 0xd: the strip open
        m.stamp(2, sx, 0, 0x1B, 0x11, 1, 7, 0, 0x2F)
        v = f(0x38)
        if v == 1:
            m.wr(F(0x38), 2)
            m.wr(A(42), 8)
            m.wr(O(276, 0x38), 0x90)
        elif v == 2:
            m.wr(A(42), 8)
        m.wr(F(LAST_LEVEL), 1)
    elif lv == 2:
        if f(0x7D):
            m.wr(O(70, 6), 0xFF, 2)
            m.wr(O(91, 6), 0xFF, 2)
            m.wr(F(0x12), 1)
        if f(0x12):
            m.wr(A(4), 8)
            m.wr(O(44, 0x38), 0xFF)
        elif m.rd(O(44, 0x38)) != 0x9A:
            m.wr(O(44, 0x38), 0x9A)
        if f(0x15):
            m.wr(O(82, 8), 1, 2)
            m.wr(O(82, 0x38), 3)
        if f(0x14) < 2:
            m.wr(F(0x14), f(0x14) + 1)
        m.wr(F(LAST_LEVEL), 2)
    elif lv == 3:
        m.wr(F(0x75), 1)
        m.wr(F(LAST_LEVEL), 3)
    elif lv == 4:
        if f(0x19):
            m.wr(A(7), 8)
            m.wr(A(26), 1)
            m.wr(O(141, 6), 0xFF, 2)
            m.wr(O(159, 6), 0xFF, 2)
            if m.rd(O(74, 0x38)) < 0xFD:
                m.wr(O(74, 0x38), 0xFF)
            m.look(0x801E83A4, 0x801E8E74, 0x801E8EA4, 0x8008255C, 0x1000)
        else:
            m.wr(A(7), 1)
            m.wr(A(26), 8)
            m.look(0x801E83A4, 0x801E8E74, 0x801E8EA4, 0x8008255C, 0)
        if f(0x7B):
            m.wr(O(55, 6), 0xFF, 2)
            m.wr(O(148, 6), 0xFF, 2)
        m.wr(F(LAST_LEVEL), 4)
    elif lv == 5:
        if f(0x1C) == 0:
            m.wr(F(0x1C), 1)
        if f(0xA):
            m.wr(F(0x20), 1)
        if f(0x1E):
            for k in range(COUNT):
                if m.rd(O(k, 4)) == 0x56:
                    m.wr(O(k, 0x30), 0, 2)
                    m.wr(O(k, 0x2E), 0, 2)
                    m.wr(O(k, 0x2C), 0, 2)
                    m.wr(O(k, 0x38), 0)
                    m.wr(O(k), 0)
                    m.wr(O(k, 4), 0xFF)
        m.wr(F(LAST_LEVEL), 5)
    elif lv == 6:
        if m.rd(STAT36, 2) >= 0x32 and all(m.rd(SKILLS + 2 * k, 2) >= 0x32 for k in range(5)):
            m.wr(F(0x26), 1)

        def look6(n):
            for t, tab in ((0x801E8CE8, 0x8008246C), (0x801E8D18, 0x8008249C),
                           (0x801E8D48, 0x800824CC)):
                m.look(0x801E83A8, t, 0x801E8D78, tab, 0x100 * n)
        if f(0x23) == 0:
            look6(0)
            for a in (O(121), O(121, 0x3C), O(173, 0x3E)):
                m.wr(a, 0)
            cats(m, ((3, 8), (0, 1), (1, 8)))
            for k in range(0x47):
                m.wr(A(4 + k), 1)
        elif f(0x32) == 0:
            m.wr(F(0x25), 1)
            look6(0x10)
            for a in (O(121), O(121, 0x3C), O(173, 0x3E), O(91)):
                m.wr(a, 0)
            cats(m, ((3, 1), (0, 8), (1, 1)))
            for k in range(0x47):
                m.wr(A(4 + k), 8)
        else:
            look6(0)
            m.wr(O(121), 2)
            m.wr(O(121, 0x3C), 0xFF)
            m.wr(O(173, 0x3E), 0xFF)
            m.wr(O(91), 0)
            cats(m, ((3, 8), (0, 8), (1, 1)))
            for k in range(0x47):
                m.wr(A(4 + k), 1)
        if f(0x28) == 0:
            m.wr(A(58), 8)
        else:
            m.wr(O(83), 0)
        m.wr(F(LAST_LEVEL), 6)
    elif lv == 7:
        m.wr(F(LAST_LEVEL), 7)
    elif lv == 8:
        m.wr(A(1), 8 if f(0x2C) == 0 or f(0x2E) else 1)
        m.wr(F(0x2F), 1 if m.has(0x85) > 0 else 0)
        if m.has(0x10) > 0:
            m.wr(F(0x30), 1)
        if m.has(0x7D) > 0:
            m.wr(F(0x31), 1)
        m.wr(F(LAST_LEVEL), 8)
    elif lv == 9:
        if f(0x24) and f(0x27):
            m.wr(F(0x32), 1)
        if f(0x34) == 0:
            m.wr(A(2), 1)
            for a in (O(249), O(249, 0x3C), O(262, 0x3E)):
                m.wr(a, 0)
        else:
            m.wr(A(2), 8)
            m.wr(O(249), 2)
            m.wr(O(249, 0x3C), 0xFF)
            m.wr(O(262, 0x3E), 0xFF)
        if f(0x35):
            m.wr(O(58, 6), 0xFF, 2)
            m.wr(O(58, 4), 0xFF)
            m.wr(O(58), 0)
            m.wr(F(0x35), 2)
        if f(0x36) == 0 and (m.has(0x7D) > 0 or m.rd(PLAYER_LEVEL) >= 0x28):
            m.wr(F(0x36), 1)
            key_test_all(m, 0xF1)
        m.wr(F(LAST_LEVEL), 9)
    elif lv == 10:
        _level10(m, f)
    elif lv == 11:
        if f(0x3C) == 0:
            m.wr(O(20), 2)
            m.wr(O(20, 0x3C), 0xFF)
            m.wr(O(33, 0x3E), 0xFF)
        else:
            m.wr(O(20), 0)
            k = m.rd(O(20, 0x3A), 2)
            m.wr(O(20, 0x3C), 0)
            if k != 0xFFFF and m.rd(O(k, 6), 2) != 0xFF:
                m.wr(O(k), 2)
                m.wr(O(k, 0x38), 0xFF)
                m.wr(O(20, 0x3A), 0xFFFF, 2)
            m.wr(O(33, 0x3E), 0)
        m.wr(F(LAST_LEVEL), 11)
    elif lv == 12:
        for flag, k, want in ((0x3E, 241, 0x64), (0x3F, 242, 0x65), (0x40, 243, 0x66)):
            if f(flag) == 1:
                lock_lift(m, k, want)
        m.wr(F(LAST_LEVEL), 12)
    elif lv == 13:
        m.wr(F(0x47), 1)
        if f(0x7C):
            m.wr(O(15, 6), 0xFF, 2)
            m.wr(O(86, 6), 0xFF, 2)
        if f(0x42) == 0:
            m.wr(F(0x43), 1)
        else:
            m.wr(O(20, 6), 0xFF, 2)
            m.wr(A(30), 8)
            m.wr(A(30, 9), 3)
        m.wr(F(LAST_LEVEL), 13)
    elif lv == 14:
        if f(0x14) >= 2:
            m.wr(O(7, 6), 0xFF, 2)
            m.wr(O(49, 6), 0xFF, 2)
            m.stamp(2, 0x4E, 0, 0x21, 2, 2, 3, 0, 0x2F)
            m.stamp(2, 0x4E, 3, 0xC, 0x48, 2, 3, 0, 0x2F)
            v = 8
        else:
            m.stamp(2, 0x4C, 0, 0x21, 2, 2, 3, 0, 0x2F)
            m.stamp(2, 0x4C, 3, 0xC, 0x48, 2, 3, 0, 0x2F)
            v = 1
        cats(m, ((66, v), (70, v), (24, v), (43, v)))
        m.wr(F(LAST_LEVEL), 14)
    elif lv == 15:
        if f(0x49):
            for k in range(4, 6):
                m.wr(A(k), 8)
            m.wr(O(115, 6), 0xFF, 2)
            m.wr(O(116, 6), 0xFF, 2)
        if f(0x4A):
            for k in range(10, 12):
                m.wr(A(k), 8)
            m.wr(O(117, 6), 0xFF, 2)
            m.wr(O(118, 6), 0xFF, 2)
        m.wr(F(LAST_LEVEL), 15)
    elif lv == 16:
        m.stamp(2, 0x14 if f(0x52) else 0x13, 0, 0xC, 1, 1, 3, 0, 0x2F)
        m.wr(F(LAST_LEVEL), 16)
    elif lv == 17:
        _level17(m, f)
    elif lv == 18:
        m.wr(F(LAST_LEVEL), 18)
    elif lv == 19:
        m.wr(A(17), 1 if f(0x59) == 0 else 8)
        if f(0x55):
            m.wr(O(85, 0x3F), 0xFF)
            m.wr(O(85), 2)
        else:
            m.wr(O(85, 0x3F), 0)
            m.wr(O(85), 0)
        m.wr(F(LAST_LEVEL), 19)
    elif lv == 20:
        m.wr(F(0x57), 1)
        m.stamp(2, 0x4D if f(0x56) else 0x4A, 0, 0x26, 0xC, 3, 5, 0, 0x2F)
        m.wr(F(0x58), 0 if m.has(0x7D) > 0 else 1)
        m.wr(F(LAST_LEVEL), 20)
    elif lv == 21:
        m.wr(F(LAST_LEVEL), 21)
    elif lv == 22:
        if f(0x5C) == 0:
            m.wr(A(25), 1)
            for a in (O(28), O(28, 0x3C), O(95, 0x3E)):
                m.wr(a, 0)
        else:
            m.wr(A(25), 8)
            m.wr(O(28), 2)
            m.wr(O(28, 0x3C), 0xFF)
            m.wr(O(95, 0x3E), 0xFF)
        m.wr(F(LAST_LEVEL), 22)
    elif lv == 23:
        m.wr(F(LAST_LEVEL), 23)
    elif lv == 24:
        if f(0x65) == 0:
            m.wr(F(0x5D), 0)
        m.wr(F(LAST_LEVEL), 24)
    elif lv == 25:
        m.wr(F(LAST_LEVEL), 25)
    elif lv == 26:
        if f(0x60):
            object_signal(m, 0xF2)
        if f(0x7E):
            m.wr(O(6, 6), 0xFF, 2)
            m.wr(O(87, 6), 0xFF, 2)
        if f(0x64):
            key_test_all(m, 0xF1)
        bits, n = f(0x62) | (f(0x63) << 8), 0
        for i in range(12):
            if bits & 1:
                m.wr(0x8018296A + 0x18 * i, 2)
                n += 1
            else:
                m.wr(0x8018296A + 0x18 * i, 0)
            bits >>= 1
        m.look(0x801E8390, 0x801E8BB8, 0x801E8BE8, 0x8008243C, 0x140 * n)
        m.wr(F(LAST_LEVEL), 26)
    elif lv == 27:
        m.wr(F(LAST_LEVEL), 27)


def _level10(m, f):
    if f(0x38) == 0:
        m.wr(F(0x38), 1)

    def first():
        # flag 0x39 clear, or the level come into from itself: the way in
        m.wr(A(29), 1)
        m.wr(O(253), 0)
        m.wr(O(253, 0x38), 0)
        m.stamp(2, 0x48, 5, 0x41, 0x31, 1, 1, 0, 0x2F)
        m.wr(O(90), 0)
        m.wr(O(90, 0x3E), 0)
        cats(m, ((k, 1) for k in range(15)))
        cats(m, ((k, 8) for k in range(15, 29)))

    def after():
        m.stamp(2, 0x47, 5, 0x41, 0x31, 1, 1, 0, 0x2F)
        m.wr(O(90), 2)
        m.wr(O(90, 0x3E), 0xFF)
        cats(m, ((k, 8) for k in range(15)))
    if f(0x39) == 0:
        first()
    elif f(LAST_LEVEL) != 0xA:
        after()
        if f(0x3A) == 0:
            m.wr(F(0x3A), 1)
            cats(m, ((k, 1) for k in range(15, 29)))
    elif f(0x3A) == 0:
        first()
    else:
        after()
    if f(0x3A):
        if f(0x3A) == 1:
            m.wr(O(253), 2)
            m.wr(O(253, 0x38), 0xFF)
            m.wr(F(0x3A), 2)
        m.wr(A(29), 8)
    m.wr(F(LAST_LEVEL), 0xA)


def _level17(m, f):
    def held(k, n):
        # 0x801e8924: n slots from k held
        cats(m, ((k + i, 8) for i in range(n)))

    def mark(k, how):
        # 0x801e8958: an object's +0x3f 0 or 1, and +8 1
        if how in (0, 1):
            m.wr(O(k, 0x3F), how)
            m.wr(O(k, 8), 1, 2)
    for flag, k, obj in ((0x4E, 0x10, 0x50), (0x4F, 0x37, 0x51), (0x50, 0x2E, 5)):
        if f(flag):
            held(k, 1)
            mark(obj, 1)
        else:
            mark(obj, 0)
    m.wr(A(15), 8)
    if f(0x52):
        m.wr(O(63), 2)
        m.wr(O(63, 0x3F), 0xFF)
    else:
        m.wr(O(63), 0)
        m.wr(O(63, 0x3F), 0)
    v = f(0x53)
    if v == 0:
        m.wr(O(50), 2)
        for k in range(52, 62):
            m.wr(O(k), 0)
        m.stamp(2, 0x38, 0x4C, 0x47, 0x30, 3, 4, 0, 0x2F)
        m.wr(A(56), 8)
        m.wr(A(56, 3), 0)
        m.wr(O(11), 2)
    else:
        m.wr(O(50), 0)
        for k in range(52, 62):
            m.wr(O(k), 2)
        m.stamp(2, 0x3B, 0x4C, 0x47, 0x30, 3, 4, 0, 0x2F)
        m.wr(A(56), 1 if v == 1 else 8)
        m.wr(A(56, 3), 0)
        m.wr(O(11), 2 if v == 1 else 0)
        if v == 1:
            # a thing of type 0x8f made in the gold ring where the portrait is
            count = m.rd(DROP_COUNT, 2)
            k = free_slot(m, 0x15E, 10, count)
            if k is None:
                raise ValueError("no slot in the ring older than now")
            init_record(m, k)
            m.wr(DROP_COUNT, count + 1, 2)
            m.wr(O(k, 0xE), -0x64, 2)
            m.wr(O(k, 6), 0x8F, 2)
            m.wr(O(k, 0x3C), count, 2)
            m.wr(O(k), 2)
            m.wr(O(k, 4), 0xFF)
            m.wr(O(k, 0x28), 0, 2)
            m.wr(O(k, 0x24), 0, 2)
            m.wr(O(k, 0x38), 0)
            m.wr(O(k, 0x26), m.rd(O(11, 0x26), 2), 2)
            m.wr(O(k, 0x14), m.rd(O(11, 0x14), 4), 4)
            m.wr(O(k, 0x18), m.rd(O(11, 0x18), 4) - 0x32, 4)
            m.wr(O(k, 0x1C), m.rd(O(11, 0x1C), 4), 4)
    m.wr(F(0x54), 1)
    m.wr(F(LAST_LEVEL), 0x11)


# --- against the overlays' own ---------------------------------------------------

def _stack(c, n):
    return tuple(c.rd(c.r[29] + 0x10 + 4 * i, 4) for i in range(n))


def game_run(cpu, lv):
    """The overlay's own entry 5 over the machine's RAM: [the calls it made
    that the model logs, in order]."""
    calls = []
    hooks = struct.unpack_from("<I", cpu.ram, useitem.LEVEL_HOOKS & MASK)[0]
    entry = lambda n: struct.unpack_from("<I", cpu.ram, (hooks + 4 * n) & MASK)[0]   # noqa: E731
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks[STAMP_RECT] = lambda c: calls.append(("stamp",) + tuple(c.r[4:8]) + _stack(c, 5))
    for at in LOOKS.get(lv, ()):
        cpu.hooks[at] = lambda c, at=at: calls.append(("look", at) + tuple(c.r[4:8]))
    cpu.call(entry(ENTRY))
    return calls


READS = {0: (70, 33, 116, 344, 158), 1: (71,), 2: (44,), 4: (74,), 11: (20,),
         12: (241, 242, 243), 17: (11,)}
LOCKS = (0xC8, 0xC8, 0xFF, 0x9A, 0xF1, 0x64, 0x65, 0x66, 0xFC, 0xFD, 0xFE, 0x23)
HELD = (2, 0x82, 0x83, 0x84, 0x85, 0x10, 0x7D)


def cases(lv, n, rng, snap="a1"):
    """`n` runs of level `lv`'s entry 5: [the machine], laid out at random."""
    import mipsrun
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        for k in range(0x100):
            put(cpu, F(k), 1, rng.choice((0, 0, 0, 1, 1, 2, 3, 0xA, rng.randrange(0x100))))
        for t in HELD:
            put(cpu, INV_A + t, 1, rng.choice((0, 0, 1, 2)))
            put(cpu, INV_B + t, 1, rng.choice((0, 0, 0, 1)))
        put(cpu, STAT36, 2, rng.choice((0x31, 0x32, 0x33, rng.randrange(1000))))
        for k in range(5):
            put(cpu, SKILLS + 2 * k, 2, rng.choice((0x31, 0x32, 0x40, 0x40, rng.randrange(1000))))
        put(cpu, PLAYER_LEVEL, 1, rng.choice((0x27, 0x28, rng.randrange(0x100))))
        put(cpu, DROP_COUNT, 2, rng.randrange(0x10000))
        for k in READS.get(lv, ()):
            put(cpu, O(k, 0x38), 1, rng.choice(LOCKS))
            put(cpu, O(k, 5), 1, rng.choice((0xFF, 0xFF, 0x32, 0)))
        if lv == 11:
            k = rng.choice((0xFFFF, rng.randrange(COUNT), rng.randrange(COUNT)))
            put(cpu, O(20, 0x3A), 2, k)
        if lv == 17:
            for i in range(10):
                if rng.random() < 0.5:
                    put(cpu, O(0x15E + i, 6), 2, rng.choice((0x60, 0x77, 0x88)))
                    put(cpu, O(0x15E + i, 0x3C), 2, rng.randrange(0x10000))
        for k in range(COUNT):
            if rng.random() < 0.05:
                put(cpu, O(k, 0x38), 1, rng.choice(LOCKS + (0xF1, 0xF2, 0xF3)))
            if lv == 5 and rng.random() < 0.05:
                put(cpu, O(k, 4), 1, 0x56)
        out.append(cpu)
    return out


STACK_LO, STACK_HI = 0x1F0000, 0x200000       # the stack mipsrun runs on, below 0x801fc000


def compare(cpu, lv):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    ram = bytes(cpu.ram)
    m = Mem(ram)
    entry5(lv, m)
    got = game_run(cpu, lv)
    what = (lv, hash((tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written)))))
    if m.calls != got:
        return what, f"calls: model {m.calls}, game {got}"
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, STACK_LO), (STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, f"{0x80000000 | i:#x}: model {a[i]:#x}, game {b[i]:#x}" \
                        f" ({_where(0x80000000 | i)})"
    return what, None


def _where(a):
    if ACTORS <= a < ACTORS + ASTRIDE * 200:
        k, o = divmod(a - ACTORS, ASTRIDE)
        return f"actor {k} +{o:#x}"
    if OBJECTS <= a < OBJECTS + OSTRIDE * COUNT:
        k, o = divmod(a - OBJECTS, OSTRIDE)
        return f"object {k} +{o:#x}"
    if FLAGS <= a < FLAGS + 0x100:
        return f"flag {a - FLAGS:#x}"
    return "elsewhere"


def check(out=sys.stdout, per_level=40, seed=31, verbose=False):
    """The model against every level's own entry 5."""
    rng = random.Random(seed)
    ok = n = 0
    seen = {}
    told = False
    for lv in range(28):
        try:
            runs = cases(lv, per_level, rng)
        except Exception as e:                                     # noqa: BLE001
            print(f"  level {lv}: no machine ({e})", file=out)
            continue
        for cpu in runs:
            n += 1
            what, why = compare(cpu, lv)
            if why is None:
                ok += 1
                seen[what] = seen.get(what, 0) + 1
            elif not told or verbose:
                told = True
                print(f"  level {lv}: {why}", file=out)
    for lv in range(28):
        ways = [w for w in seen if w[0] == lv]
        if ways:
            print(f"  level {lv:2d}: {sum(seen[w] for w in ways):4d} runs, {len(ways)} different "
                  f"outcomes", file=out)
    print(f"entry 5, against the overlays' own over 28 levels: {ok} of {n} runs agree -- "
          f"the calls and all of RAM but the stack", file=out)
    return ok == n


def snapshot_check(out=sys.stdout):
    """Against what the game had in memory: every RAM snapshot with a level
    in it, the disc's actor table (tools/actors.py) with the level's entry 5
    run over the snapshot's own flags and pack -- the categories must be the
    snapshot's, slot for slot. (`probe` holds no actor table.)"""
    import glob
    import actors
    ok = n = slots = 0
    for path in sorted(glob.glob(os.path.join(useitem.ROOT, "out", "snap", "*.ram"))):
        ram = open(path, "rb").read()
        lv = ram[0x8018FADD & MASK]                 # level_loaded
        if lv >= 28 or not any(ram[A(k, 2) & MASK] for k in range(200)):
            continue
        m = Mem(ram)
        disc = {a["slot"]: a["cat"] for a in actors.table(lv) if a}
        for k, c in disc.items():
            m.wr(A(k), c)
        entry5(lv, m)
        bad = [k for k in disc if m.ram[A(k) & MASK] != ram[A(k) & MASK]]
        before = sum(1 for k, c in disc.items() if ram[A(k) & MASK] != c)
        n += 1
        slots += len(disc)
        if bad:
            print(f"  {os.path.basename(path)} (level {lv}): slots {bad} differ", file=out)
        else:
            ok += 1
            if before:
                print(f"  {os.path.basename(path)} (level {lv}): the {before} the disc gets wrong "
                      f"put right", file=out)
    print(f"entry 5, against the snapshots: {ok} of {n} snapshots hold the categories the disc "
          f"and the level's entry 5 make, {slots} slots", file=out)
    return ok == n


def export(out_dir, per_level=6, seed=37):
    """levelincheck.json: runs of the model over every level -- the bytes it
    read, the calls and the bytes it wrote -- which godot/selftest.gd holds
    godot/levelin.gd to."""
    import json
    rng = random.Random(seed)
    rows = []
    for lv in range(28):
        try:
            runs = cases(lv, per_level, rng)
        except Exception:                                          # noqa: BLE001
            continue
        for cpu in runs:
            m = Mem(bytes(cpu.ram))
            entry5(lv, m)
            rows.append({"level": lv, "read": [[a, v] for a, v in sorted(m.read.items())],
                         "calls": [list(c) for c in m.calls],
                         "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)]})
    path = os.path.join(out_dir, "levelincheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": rows}, fh, separators=(",", ":"))
    return path


def main():
    a = sys.argv[1:]
    if "--export" in a:
        print(export(a[a.index("--export") + 1] if len(a) > a.index("--export") + 1
                     else os.path.join(useitem.ROOT, "out", "godot")))
        return
    if "--check" in a:
        good = check(verbose="-v" in a)
        good = snapshot_check() and good
        sys.exit(0 if good else 1)
    print(__doc__.split("**How it is held")[0])


if __name__ == "__main__":
    main()

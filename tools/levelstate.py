#!/usr/bin/env python3
"""What a level remembers, and the byte stream it remembers it in.

    python3 tools/levelstate.py            the streams that were recorded
    python3 tools/levelstate.py --check    the model against them, and against
                                           the game's own two routines
    python3 tools/levelstate.py --godot    levelstate.json, for the self-test

`level_state_write` (`0x8005efd4`) builds the whole record from scratch every
time something changes, on its own stack, and `apply_level_state`
(`0x8005f444`) reads it back at level load. Between them the format is three
sections:

**One: the actors that are gone.** Walk all 200 of `actor_table`'s slots,
0x88 apart. For each whose byte 0 is **1** -- category 1, and no other
category -- write the slot index and then `3` if the actor's `+9` is `3`,
otherwise `0`. Terminate with `0xff`. The reader puts the second byte into the
slot's `+9`. (This said the walk *stopped* at the first byte 0 of 0xff. It
skips such a slot and goes on; the game's own routine, run below, settles it.)

**Two: how far each conversation has got.** Walk the 40 entity records,
stopping at the first whose byte 0 is 0xff; for each whose `+0x38` is not null
and whose block begins `0x70`, write the entity index, the program counter at
`+0x10` and the retry flag at `+0x13`. Terminate with `0xff`. The reader puts
the two back through `+0x38` without asking whether it is null.

**Three: one opcode per object slot**, 396 of them, in lockstep -- the reader
steps its own pointer by `0x44` once per record and stops at 396, so there is
no terminator. What is written is chosen by the object's class,
`object_type_table[type]` byte 0, through a 233-arm table at `0x80013298`
that this reads off the executable:

    0xff        the slot is empty: its type is 0xff
    0xfe        nothing about the slot is kept -- 200 classes, and any class
                past the table
    0xfd s      the state byte at +0x38 -- 25 classes, the doors, gates, lifts,
                lids, chests and the hidden walls among them
    0xf4 s n    the state and the byte after it -- 5, the pedestal 0x18 among
                them
    0xf5 n      the byte at +0x39 -- class 0x56
    (nothing)   class 0x53 with its state below 2: the writer puts no byte at
                all, so the reader takes the next slot's for this one and is a
                slot out from there on. It is the game's, and it is kept.
    class 0x40, a thing, by its kind byte at +4:
    0xf0 t x x z z y y a   0x60, gold: the type, x >> 2 in two bytes, z the
                           same, y in two, the angle at +0x26 >> 4
    0xf1 t x x z z y y     0x61: the same without the angle
    0xf2 t x x z z y y r   0x62: and +0x3a >> 2
    0xf3 t s               0x70, a key on a pedestal: the type and the state
    0xfd s                 any other kind

The reader, slot by slot: `0xff` puts 0xff in the type; `0xfd`, `0xf5` and
`0xf4` put their bytes back into +0x38, +0x39 or both; `0xf0`..`0xf3` build the
slot afresh through `init_object_record` -- the kind, the type, the position
(x and z shifted back up by 2, y sign-extended), +8 = 0x63, +0x38 = 0xff, and
byte +0 the layer `select_cell_layer` finds there, 2 for the upper and 1 for
the lower; `0xf0` adds the angle << 4 and +0x28 = 0x400, `0xf2` adds +0x3a =
(r << 2) + (rand() >> 13), and +0x24 = 0x400 for type 0x79; `0xf3` takes only
the type and puts its state byte in +0x38. Any other byte from 0xf0 up, and
anything below 0xf0, does nothing and is one byte long.

**Withdrawn: the lengths of `0xf2` and `0xf3` were 8 and 8 here.** They are 9
and 3. The writer's arm for kind 0x62 adds `+0x3a >> 2` after the position, and
its arm for 0x70 writes only the type and the state. Neither opcode was in
either recorded stream, which is how "3 of 3" held with the wrong numbers.

**Checked.** `emu/bp23.lua` logged both ends while the game was played: the
543-byte stream written on level 0 is byte for byte the one read back when
the player returned, and it decodes to 34 actors with three gone, six
conversations -- entity 9 stopped at pc 7 with the retry flag set, which is
where an earlier recording left it -- and **396 object records ending exactly
on the last byte**. And the game's own two routines, run by tools/mipsrun.py:
`level_state_write` over every snapshot of GAME.EXE, and over copies of them
whose actors, conversations and objects were scrambled from a fixed seed so
that every arm is taken, builds the stream `encode` builds from the same RAM,
byte for byte; `apply_level_state`, handed those streams and the ones the
memory card's saves hold over a fresh load of their level
(`mipsrun.level_cpu`), changes RAM exactly as `apply` does. `--check` prints
the counts.
"""
import json
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SLOTS = 396                    # the reader's own bound
END = 0xFF
MASK = 0x1FFFFF

ACTOR_TABLE, ACTOR_STRIDE, ACTORS = 0x80185DA8, 0x88, 200
ENTITY_TABLE, ENTITY_STRIDE, ENTITIES = 0x8018C7E8, 0x78, 40
OBJECT_TABLE, OBJECT_STRIDE = 0x80191A5C, 0x44
OBJECT_TYPES, TYPE_STRIDE = 0x8018FB3C, 24
LEVEL_STATE, LEVEL_STATE_INDEX = 0x801BAA88, 0x801BFA88
LEVEL_GRID = 0x801D4464
CURRENT_LEVEL = 0x8018FAD9
CLASS_TABLE, CLASSES = 0x80013298, 233
WRITE, APPLY = 0x8005EFD4, 0x8005F444
BUILT = 0x8005F3A4             # level_state_write's call to level_state_unpack: the stream is whole
RAND = 0x800796C0              # the BIOS's rand, A0:2F

# level_state_write's arms, by where the class table sends a class: read off
# its listing (tools/rdis.py game 0x8005efd4).
ARMS = {0x8005F150: "thing", 0x8005F32C: "unless_low", 0x8005F340: "state",
        0x8005F354: "pair", 0x8005F374: "aux", 0x8005F388: "nothing"}

# How long each opcode is; anything else is one byte.
OPS = {0xF0: 9, 0xF1: 8, 0xF2: 9, 0xF3: 3, 0xF4: 3, 0xF5: 2, 0xFD: 2}
# The kind byte each creating opcode stamps at +4, and back.
KINDS = {0xF0: 0x60, 0xF1: 0x61, 0xF2: 0x62, 0xF3: 0x70}
CREATES = {v: k for k, v in KINDS.items()}

# What emu/bp23.lua recorded on 2026-09-24: the stream level_state_write
# built, twice, and the one apply_level_state was handed on the way back.
RECORDED = [
    {"kind": "state", "level": None, "hex": "0000050306030700080009000a000b000c000e0010001100120013001400150016001700180019001a001b031c001d001e00200021002400250026002700280029002f00ff0600000700000800000907010a00000b0000fffefefefefefefd00fefdfffd89fefefefefefefefdfffefdfffdfffefefefefdfefefefefefefefefdc8fefffefefefefefefefefefefd00fefefefefdfffefefefefefdfffd00fefefefd00fefefefefefefefdc8fefefd00fdfffefefefefefefefd00fefefefdfffdfffefd00fefefefefefefefefefefefdfffefefefefefefefefefefdfffdfffdfffefdc8fefefefefefefdfffdfffefdfffdfffefefdfffefd00fefefefefdfffefefefefefefefefefd00fefefefefefefefd00fffefefefefefefdfffefefefefdfffefefefd00fefefefefefefefefefefdfffefefefefefefefefdfffefffd00fefefdfffd00fefd00fd8afefd87fd00fefefd00fdfffdfffdfffdfffefefdfffefd00fefefefefefefffefdfffefefefefefefefefefefefefefefefefefffefefd00fd00fefefefefefd00fefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefffffefefefefefefefefefefefefefefefefefefefd3cfefefefefefefefefefefefefefefefefefefefefdf1fefefefefeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"},
    {"kind": "state", "level": None, "hex": "0000010002000300040005000600070008000a000b000c000d000e000f001000110012001300150016001700180019001b001c001d001f0020002200230024002500260027002800ff0900000a0000fffdfffefffefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefd00fefefefefefefefefefefefefefefefefefdfcfefefefefefefdfffdfffdfffd00fef4fffffefefd00fefdfffefefd00fdfffefdf0fdfcfefefefefefefefefefef4fffffefefefd00fdfcfdfcfefefefdfffdfffefefefefefefefefefef4ff00fef4fffffefefdfffefdfcf4fffffdfffef4fffffdfcfefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefdfffefefd00fd00fd00fdfffdfffefdfffefefefefefefefdfffdfffdfffdfffefdfffefdfffd00fdfffdfffdfffefefd00fefef4fffffffffefd00fffffffffffffffffffffffffffffffffffffffffefffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffefefefefeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"},
    {"kind": "apply", "level": 0, "hex": "0000050306030700080009000a000b000c000e0010001100120013001400150016001700180019001a001b031c001d001e00200021002400250026002700280029002f00ff0600000700000800000907010a00000b0000fffefefefefefefd00fefdfffd89fefefefefefefefdfffefdfffdfffefefefefdfefefefefefefefefdc8fefffefefefefefefefefefefd00fefefefefdfffefefefefefdfffd00fefefefd00fefefefefefefefdc8fefefd00fdfffefefefefefefefd00fefefefdfffdfffefd00fefefefefefefefefefefefdfffefefefefefefefefefefdfffdfffdfffefdc8fefefefefefefdfffdfffefdfffdfffefefdfffefd00fefefefe"}
]


_arms = None


def class_arms():
    """{class: arm} for the 233 classes the table at 0x80013298 has, off the
    executable."""
    global _arms
    if _arms is None:
        import mips
        exe = mips.load("game")
        _arms = {c: ARMS[exe.word(CLASS_TABLE + 4 * c)] for c in range(CLASSES)}
    return _arms


def _u8(m, a):
    return m[a & MASK]


def _u16(m, a):
    return struct.unpack_from("<H", m, a & MASK)[0]


def _u32(m, a):
    return struct.unpack_from("<I", m, a & MASK)[0]


def _w16(m, a, v):
    struct.pack_into("<H", m, a & MASK, v & 0xFFFF)


def _w32(m, a, v):
    struct.pack_into("<I", m, a & MASK, v & 0xFFFFFFFF)


# --- writing --------------------------------------------------------------

def encode(m):
    """level_state_write's stream, from RAM `m`: the level's actors,
    conversations and object slots as they stand."""
    arms = class_arms()
    out = bytearray()
    for k in range(ACTORS):
        a = ACTOR_TABLE + ACTOR_STRIDE * k
        if _u8(m, a) != 1:                       # 0xff skipped, as any other category
            continue
        out += bytes([k, 3 if _u8(m, a + 9) == 3 else 0])
    out.append(END)
    for k in range(ENTITIES):
        e = ENTITY_TABLE + ENTITY_STRIDE * k
        if _u8(m, e) == 0xFF:
            break
        p = _u32(m, e + 0x38)
        if p == 0 or _u8(m, p) != 0x70:
            continue
        out += bytes([k, _u8(m, p + 0x10), _u8(m, p + 0x13)])
    out.append(END)
    for s in range(SLOTS):
        r = OBJECT_TABLE + OBJECT_STRIDE * s
        typ = _u16(m, r + 6)
        if typ == 0xFF:
            out.append(0xFF)
            continue
        cls = _u8(m, OBJECT_TYPES + TYPE_STRIDE * typ)
        arm = arms[cls] if cls < CLASSES else "nothing"
        st, aux = _u8(m, r + 0x38), _u8(m, r + 0x39)
        if arm == "state":
            out += bytes([0xFD, st])
        elif arm == "unless_low":
            if st >= 2:
                out += bytes([0xFD, st])
        elif arm == "pair":
            out += bytes([0xF4, st, aux])
        elif arm == "aux":
            out += bytes([0xF5, aux])
        elif arm == "thing":
            kind = _u8(m, r + 4)
            op = CREATES.get(kind)
            if op is None:
                out += bytes([0xFD, st])
            elif op == 0xF3:
                out += bytes([0xF3, typ & 0xFF, st])
            else:
                x, y, z = _u32(m, r + 0x14), _u32(m, r + 0x18), _u32(m, r + 0x1C)
                out += bytes([op, typ & 0xFF, (x >> 2) & 0xFF, (x >> 10) & 0xFF,
                              (z >> 2) & 0xFF, (z >> 10) & 0xFF, y & 0xFF, (y >> 8) & 0xFF])
                if op == 0xF0:
                    out.append((_u16(m, r + 0x26) >> 4) & 0xFF)
                elif op == 0xF2:
                    out.append((_u16(m, r + 0x3A) >> 2) & 0xFF)
        else:
            out.append(0xFE)
    return bytes(out)


# --- reading --------------------------------------------------------------

def decode(b):
    """(actors, conversations, [(opcode, operands)], bytes consumed)."""
    i, actors = 0, []
    while i + 1 < len(b) and b[i] != END:
        actors.append((b[i], b[i + 1]))
        i += 2
    i += 1
    talks = []
    while i + 2 < len(b) and b[i] != END:
        talks.append((b[i], b[i + 1], b[i + 2]))
        i += 3
    i += 1
    objs = []
    for _n in range(SLOTS):
        if i >= len(b):
            break
        op = b[i]
        n = OPS.get(op, 1)
        objs.append((op, tuple(b[i + 1:i + n])))
        i += n
    return actors, talks, objs, i


def init_object_record(m, r):
    """0x800448b8, its fourteen stores."""
    m[(r + 1) & MASK] = 0x80
    for o in (0x30, 0x2E, 0x2C):
        _w16(m, r + o, 0x1000)
    for o in (0xA, 0x28, 0x24, 0x26, 0xE, 0x10):
        _w16(m, r + o, 0)
    m[(r + 2) & MASK] = m[r & MASK] = 0
    m[(r + 4) & MASK] = m[(r + 5) & MASK] = 0xFF


def layer(m, x, y, z):
    """select_cell_layer's answer, 0 or 5, out of the grid in RAM."""
    import collision
    if x > 0x27FFF or z > 0x27FFF:
        return 0
    c = (LEVEL_GRID + 800 * (z >> 11) + 10 * (x >> 11)) & MASK
    return collision.layer_of(m[c:c + 10], y)


def apply(m, b, rand):
    """apply_level_state's writes into RAM `m`, handed stream `b`; `rand` is
    the game's rand(). The bytes it read."""
    i = 0
    while b[i] != END:
        m[(ACTOR_TABLE + ACTOR_STRIDE * b[i] + 9) & MASK] = b[i + 1]
        i += 2
    i += 1
    while b[i] != END:
        p = _u32(m, ENTITY_TABLE + ENTITY_STRIDE * b[i] + 0x38)
        m[(p + 0x10) & MASK] = b[i + 1]
        m[(p + 0x13) & MASK] = b[i + 2]
        i += 3
    i += 1
    for s in range(SLOTS):
        r = OBJECT_TABLE + OBJECT_STRIDE * s
        op = b[i]
        i += 1
        if op == 0xFF:
            _w16(m, r + 6, 0xFF)
        elif op == 0xF4:
            m[(r + 0x38) & MASK], m[(r + 0x39) & MASK] = b[i], b[i + 1]
            i += 2
        elif op == 0xF5:
            m[(r + 0x39) & MASK] = b[i]
            i += 1
        elif op == 0xFD:
            m[(r + 0x38) & MASK] = b[i]
            i += 1
        elif op in KINDS:
            n = OPS[op]
            t = made(bytes([op]) + bytes(b[i:i + n - 1]), rand)
            i += n - 1
            init_object_record(m, r)
            m[(r + 4) & MASK] = t["kind"]
            _w16(m, r + 6, t["type"])
            if op == 0xF3:
                m[(r + 0x38) & MASK] = t["lock"]
                continue
            x, y, z = t["pos"]
            ax, ay, az = t["angles"]
            if op == 0xF0:
                _w16(m, r + 0x28, az)
                _w16(m, r + 0x26, ay)
            elif op == 0xF2:
                _w16(m, r + 0x3A, t["rest"])
                if ax:
                    _w16(m, r + 0x24, ax)
            _w32(m, r + 0x14, x)
            _w32(m, r + 0x1C, z)
            _w32(m, r + 0x18, y)
            _w16(m, r + 8, t["state"])
            m[r & MASK] = 2 if layer(m, x, y, z) else 1
            m[(r + 0x38) & MASK] = t["lock"]
    return i


def made(row, rand):
    """A creating opcode's thing, as the reader builds it: kind, type, place,
    the three angles (+0x24, +0x26, +0x28), +8, +0x38 and +0x3a ("rest"). The
    same fields godot/levelstate.gd made() gives."""
    op = row[0]
    t = {"kind": KINDS[op], "type": row[1], "angles": [0, 0, 0], "state": 0x63,
         "lock": 0xFF, "rest": 0}
    if op == 0xF3:
        t["lock"] = row[2]
        return t
    y = row[6] | row[7] << 8
    y -= 0x10000 if y & 0x8000 else 0
    t["pos"] = [(row[2] | row[3] << 8) << 2, y, (row[4] | row[5] << 8) << 2]
    if op == 0xF0:
        t["angles"] = [0, row[8] << 4, 0x400]
    elif op == 0xF2:
        t["rest"] = (row[8] << 2) + (rand() >> 13)
        if row[1] == 0x79:
            t["angles"] = [0x400, 0, 0]
    return t


def stream_of(area, index, lv):
    """The stream level `lv` keeps in a level_state area and its index, or
    None: index[lv] is its offset into the area, 0xffff for none."""
    off = struct.unpack_from("<H", index, 2 * lv)[0]
    return None if off == 0xFFFF else bytes(area[off:])


class Lcg:
    """The BIOS's rand: next = next * 0x41c64e6d + 0x3039, (next >> 16) & 0x7fff."""

    def __init__(self, seed=1):
        self.next = seed

    def __call__(self):
        self.next = (self.next * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
        return (self.next >> 16) & 0x7FFF


# --- the game's own two, run --------------------------------------------------

class _Built(Exception):
    pass


def game_encode(ram, lv):
    """level_state_write(lv), the game's, over `ram`: the stream it builds."""
    import mipsrun
    cpu = mipsrun.CPU(ram)
    got = []

    def built(c):
        sp = c.r[29]
        start = (sp + 0x90) & MASK
        got.append(bytes(c.ram[start:c.r[16] & MASK]))
        raise _Built()
    cpu.watch[BUILT] = built
    try:
        cpu.call(WRITE, lv)
    except _Built:
        pass
    return got[0] if got else None


def scramble(ram, rng):
    """A copy of `ram` with the actors' categories and +9, the conversations'
    pcs and the objects' states, kinds, types and places drawn afresh, so that
    every arm of the writer and the reader is taken."""
    m = bytearray(ram)
    for k in range(ACTORS):
        a = ACTOR_TABLE + ACTOR_STRIDE * k
        if _u8(m, a) != 0xFF and rng.randrange(3) == 0:
            m[a & MASK] = rng.choice((1, 1, 2, 0xFF))
            m[(a + 9) & MASK] = rng.choice((0, 3, 3, rng.randrange(256)))
    for k in range(ENTITIES):
        e = ENTITY_TABLE + ENTITY_STRIDE * k
        if _u8(m, e) == 0xFF:
            break
        p = _u32(m, e + 0x38)
        if p and _u8(m, p) == 0x70:
            m[(p + 0x10) & MASK] = rng.randrange(256)
            m[(p + 0x13) & MASK] = rng.randrange(2)
    types = [t for t in range(0x14C) if _u8(m, OBJECT_TYPES + TYPE_STRIDE * t) == 0x40]
    # the level's own 32 rows given classes of every arm, the rare ones (0x53,
    # 0x56, the pairs) and past the table among them
    own = list(range(300, 332))
    for t in own:
        m[(OBJECT_TYPES + TYPE_STRIDE * t) & MASK] = rng.choice(
            (0x53, 0x53, 0x56, 0x56, 0x0F, 0x11, 0x18, 0x1A, 0xA7, 0x51, 0x02, 0xE8,
             rng.randrange(256)))
    for s in range(SLOTS):
        r = OBJECT_TABLE + OBJECT_STRIDE * s
        if _u16(m, r + 6) == 0xFF:
            continue
        m[(r + 0x38) & MASK] = rng.choice((0, 1, 2, 0xFE, 0xFF, rng.randrange(256)))
        m[(r + 0x39) & MASK] = rng.randrange(256)
        if rng.randrange(6) == 0:
            _w16(m, r + 6, rng.choice(own))
        elif types and rng.randrange(4) == 0:
            _w16(m, r + 6, rng.choice(types))
            m[(r + 4) & MASK] = rng.choice((0x60, 0x61, 0x62, 0x70, 0x40, 0x06))
            _w32(m, r + 0x14, rng.randrange(0, 0x28000))
            _w32(m, r + 0x1C, rng.randrange(0, 0x28000))
            _w32(m, r + 0x18, rng.randrange(-0x6000, 0x1000))
            _w16(m, r + 0x26, rng.randrange(0x1000))
            _w16(m, r + 0x3A, rng.randrange(0x400))
        elif rng.randrange(40) == 0:
            _w16(m, r + 6, 0x79 if rng.randrange(2) else 0xFF)
    return bytes(m)


def _game_snapshots():
    import memcard
    return memcard._snapshots()


def game_check(out=sys.stdout, scrambles=3):
    """The writer and the reader against the game's own, run."""
    import mipsrun
    import memcard
    ok = True
    rng = random.Random(0x1E5A7E)
    streams = []                     # (label, level, stream)
    n = same = nbytes = sbytes = 0
    for path in _game_snapshots():
        ram = open(path, "rb").read()
        lv = ram[CURRENT_LEVEL & MASK]
        name = os.path.basename(path)[:-4]
        for k in range(scrambles + 1):
            m = ram if k == 0 else scramble(ram, rng)
            game = game_encode(m, lv)
            mine = encode(m)
            n += 1
            nbytes += max(len(game), len(mine))
            if game == mine:
                same += 1
                sbytes += len(game)
            else:
                d = next((i for i in range(min(len(game), len(mine))) if game[i] != mine[i]),
                         min(len(game), len(mine)))
                print(f"  {name}{' scrambled' if k else ''}: the game's stream and this one "
                      f"part at byte {d} of {len(game)}", file=out)
                ok = False
            streams.append((name + (f" scrambled {k}" if k else ""), lv, game or mine))
    print(f"  level_state_write, the game's, over {n} snapshot states ({n // (scrambles + 1)} "
          f"as taken, the rest scrambled): {same} of {n} streams, {sbytes} of {nbytes} "
          f"bytes, as encode builds them", file=out)

    for path, slot, f in memcard.saves():
        buf = f[memcard.DATA_AT:]
        area, index = buf[0x108:0x5108], buf[0x5108:0x5148]
        for lv in range(32):
            st = stream_of(area, index, lv)
            if st is not None:
                streams.append((f"slot {slot} level {lv}", lv, st))
    for r in RECORDED:
        if r["kind"] == "state" and len(r["hex"]) > 800:
            streams.append(("bp23", 0, bytes.fromhex(r["hex"])))

    fresh = {}
    n = same = changed = 0
    for label, lv, st in streams:
        if lv not in fresh:
            fresh[lv] = bytes(mipsrun.level_cpu(lv).ram)
        base = fresh[lv]
        cpu = mipsrun.CPU(base)
        lcg = Lcg()
        cpu.hooks[RAND] = lambda c, lcg=lcg: lcg()
        a = LEVEL_STATE & MASK
        cpu.ram[a:a + len(st)] = st
        idx = bytearray(b"\xff" * 64)
        struct.pack_into("<H", idx, 2 * lv, 0)
        cpu.ram[LEVEL_STATE_INDEX & MASK:(LEVEL_STATE_INDEX & MASK) + 64] = idx
        before = bytes(cpu.ram)
        cpu.call(APPLY, lv)
        mine = bytearray(before)
        apply(mine, before[a:], Lcg())          # the area as RAM holds it: a stream
        #                                        a slot short reads on past its end
        lo, hi = (mipsrun.STACK - 0x400) & MASK, mipsrun.STACK & MASK
        skip = set(range(lo, hi)) | {x & MASK for a0 in (0x801E6464, 0x801E646E, 0x801E6470)
                                     for x in range(a0, a0 + 4)}
        game = cpu.ram
        diff = [i for i in range(len(before)) if (game[i] != mine[i]) and i not in skip]
        moved = sum(1 for i in range(len(before)) if game[i] != before[i] and i not in skip)
        n += 1
        changed += moved
        if not diff:
            same += 1
        else:
            ok = False
            print(f"  {label}: {len(diff)} bytes differ from the game's apply, the first at "
                  f"{0x80000000 | diff[0]:#x}", file=out)
    print(f"  apply_level_state, the game's, handed {n} streams over a fresh load of their "
          f"level: {same} of {n} leave RAM as apply does ({changed} bytes changed, every one "
          f"the same)", file=out)
    return ok


def check(out=sys.stdout):
    ok = bad = 0
    for r in RECORDED:
        b = bytes.fromhex(r["hex"])
        actors, talks, objs, used = decode(b)
        gone = [s for s, v in actors if v]
        tag = f"{r['kind']}" + (f" level {r['level']}" if r["level"] is not None else "")
        if r["kind"] == "apply" and len(b) < 400:
            # the breakpoint dumps a fixed 256 bytes, so the tail is not there
            print(f"  {tag}: {len(actors)} actors, {len(talks)} conversations "
                  f"(the dump is truncated at {len(b)} bytes, so the object "
                  f"section is not counted)", file=out)
            ok += 1
            continue
        good = len(objs) == SLOTS and used == len(b)
        print(f"  {tag}: {len(actors)} actors, {len(gone)} of them gone, "
              f"{len(talks)} conversations, {len(objs)} object records ending "
              f"at byte {used} of {len(b)}", file=out)
        if good:
            ok += 1
        else:
            bad += 1
    print(f"  {ok} of {ok + bad} recorded streams decode exactly", file=out)
    return bad == 0


def check_streams():
    """(label, level, stream) for the self-test: the saves' and the snapshots'
    streams, the game's own writer's, scrambled as game_check scrambles them."""
    import memcard
    out = []
    rng = random.Random(0x1E5A7E)
    for path in _game_snapshots():
        ram = open(path, "rb").read()
        lv = ram[CURRENT_LEVEL & MASK]
        name = os.path.basename(path)[:-4]
        for k in range(2):
            m = ram if k == 0 else scramble(ram, rng)
            out.append((name + (" scrambled" if k else ""), lv, encode(m)))
    for _path, slot, f in memcard.saves():
        buf = f[memcard.DATA_AT:]
        area, index = buf[0x108:0x5108], buf[0x5108:0x5148]
        for lv in range(32):
            st = stream_of(area, index, lv)
            if st is not None:
                out.append((f"slot {slot} level {lv}", lv, st[:0x1000]))
    return out


# What level_state_write reads of a slot, in the order godot/levelstate.gd's
# table keeps it: type, class, kind (+4), x, y, z, +0x26, +0x38, +0x39, +0x3a.
TABLE = ("type", "cls", "op", "x", "y", "z", "a26", "lock", "aux", "w3a")


def table_of(m):
    """The 396 slots of RAM `m` as that table: a row for each, or None for an
    empty one (type 0xff)."""
    out = []
    for s in range(SLOTS):
        r = OBJECT_TABLE + OBJECT_STRIDE * s
        typ = _u16(m, r + 6)
        if typ == 0xFF:
            out.append(None)
            continue
        out.append([typ, _u8(m, OBJECT_TYPES + TYPE_STRIDE * typ), _u8(m, r + 4),
                    struct.unpack_from("<i", m, (r + 0x14) & MASK)[0],
                    struct.unpack_from("<i", m, (r + 0x18) & MASK)[0],
                    struct.unpack_from("<i", m, (r + 0x1C) & MASK)[0],
                    _u16(m, r + 0x26), _u8(m, r + 0x38), _u8(m, r + 0x39), _u16(m, r + 0x3A)])
    return out


def actors_of(m):
    """[slot, category, +9] of every actor slot that is not 0xff."""
    return [[k, _u8(m, ACTOR_TABLE + ACTOR_STRIDE * k), _u8(m, ACTOR_TABLE + ACTOR_STRIDE * k + 9)]
            for k in range(ACTORS) if _u8(m, ACTOR_TABLE + ACTOR_STRIDE * k) != 0xFF]


def talks_of(m):
    """[entity, pc, retry] of each conversation the writer lists."""
    out = []
    for k in range(ENTITIES):
        e = ENTITY_TABLE + ENTITY_STRIDE * k
        if _u8(m, e) == 0xFF:
            break
        p = _u32(m, e + 0x38)
        if p and _u8(m, p) == 0x70:
            out.append([k, _u8(m, p + 0x10), _u8(m, p + 0x13)])
    return out


def export_check(out_dir):
    """levelstatecheck.json: streams and what this reads in them, for
    godot/selftest.gd to read again with godot/levelstate.gd -- past a short
    stream's end both read zeros -- and what each creating opcode makes, the
    game's rand standing in as an Lcg from 1."""
    rows = []
    for label, lv, st in check_streams():
        a, t, objs, _used = decode(st + bytes(0x1000))
        lcg = Lcg()
        mk = {}
        for s, (op, opr) in enumerate(objs):
            if op in KINDS:
                mk[str(s)] = made(bytes([op]) + bytes(opr), lcg)
        rows.append({"label": label, "level": lv, "hex": st.hex(),
                     "actors": [list(x) for x in a], "talks": [list(x) for x in t],
                     "slots": [[op] + list(opr) for op, opr in objs], "made": mk})
    # the writer over each state a snapshot (or a scrambled copy) holds, as
    # the port's table, actors and conversations would hold it
    writes = []
    rng = random.Random(0x1E5A7E)
    for path in _game_snapshots():
        ram = open(path, "rb").read()
        name = os.path.basename(path)[:-4]
        for k in range(2):
            m = ram if k == 0 else scramble(ram, rng)
            writes.append({"label": name + (" scrambled" if k else ""), "table": table_of(m),
                           "actors": actors_of(m), "talks": talks_of(m), "want": encode(m).hex()})
    # the reader over a fresh load of each stream's level, as the table: what
    # it was and what it becomes; and the objects' section written again
    import mipsrun
    fresh, reads = {}, []
    for label, lv, st in check_streams():
        if lv not in fresh:
            fresh[lv] = bytes(mipsrun.level_cpu(lv).ram)
        m = bytearray(fresh[lv])
        apply(m, st + bytes(0x1000), Lcg())
        again = encode(m)
        i = 0                            # past the first two sections' ends
        while again[i] != END:
            i += 2
        i += 1
        while again[i] != END:
            i += 3
        i += 1
        reads.append({"label": label, "level": lv, "before": table_of(fresh[lv]),
                      "after": table_of(m), "again": again[i:].hex(),
                      "classes": [_u8(fresh[lv], OBJECT_TYPES + TYPE_STRIDE * t)
                                  for t in range(332)]})
    path = os.path.join(out_dir, "levelstatecheck.json")
    with open(path, "w") as fh:
        json.dump({"streams": rows, "writes": writes, "reads": reads}, fh,
                  separators=(",", ":"))
    return path


def export(out_dir):
    path = os.path.join(out_dir, "levelstate.json")
    arms = class_arms()
    with open(path, "w") as fh:
        json.dump({"_note": "level_state_write's byte stream: the actors that "
                            "are gone, each conversation's pc and retry flag, "
                            "then one opcode per object slot, 396 in lockstep; "
                            "and the writer's arm for each of the 233 classes, "
                            "off the table at 0x80013298",
                   "slots": SLOTS, "ops": {str(k): v for k, v in OPS.items()},
                   "arms": [arms[c] for c in range(CLASSES)],
                   "recorded": RECORDED}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else None
    if a == "--check":
        good = check()
        good = game_check() and good
        sys.exit(0 if good else 1)
    elif a == "--godot":
        print(export(os.path.join(ROOT, "godot")))
    else:
        print(__doc__)
        check()
        print()
        for r in RECORDED:
            b = bytes.fromhex(r["hex"])
            actors, talks, objs, _u = decode(b)
            if r["kind"] != "state":
                continue
            print(f"stream of {len(b)} bytes:")
            print(f"  gone: {[s for s, v in actors if v]}")
            print(f"  conversations: {talks}")
            import collections
            c = collections.Counter(op for op, _o in objs)
            print(f"  objects: " + ", ".join(f"{k:#04x} x{v}" for k, v in sorted(c.items())))
            print()

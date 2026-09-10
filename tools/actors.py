#!/usr/bin/env python3
"""The creatures of a level: where the disc puts them, and when they appear.

    python3 tools/actors.py 0              level 0's actor table, off the disc
    python3 tools/actors.py 0 --check      the same, against the RAM snapshot
    python3 tools/actors.py 0 --at 62 8    what arriving in cell (62,8) wakes
    python3 tools/actors.py --all          every level: how many, under which rule

Everything here is read out of GAME.EXE; FORMATS.md section 17 is the long form.

Where they come from
--------------------
`level_load` (0x80018358) reads FDAT entry 3n+1 and walks it as a chain of
length-prefixed blocks -- the chain `tools/placement.py` takes the objects from:

    link 0   the entity records, block_copy'd into entity_table (0xcb0 words)
    link 1   the actors: 200 records of 16 bytes, handed to 0x800530f8
    link 3   the objects, handed to load_object_placement

0x800530f8 turns each record into a 0x88-byte slot of the table at 0x80185da8:

    disc  slot    what
    +0    +0      category -- which rule below; 0xff is an empty slot
    +1    +2      kind: the 120-byte entity record that says what it is
    +2    +5      flags; bit 0 keeps the placed yaw, clear gives a random one
    +3    +7      home cell z
    +4    +8      home cell x
    +5    +0x0a   the chance of appearing
    +6    +0x0b   copied, and read by nothing here
    +7    +6      which of the cell's two floors it stands on: 2 the upper
    +8    +0x20   yaw, stored negated
    +10   +0x22   fine z in the cell -- a follower's leader slot instead
    +12   +0x24   fine x
    +14   +0x26   height above the floor

and 0x8004b560 stands it at home: x and z from the cell and the fine offsets,
y from `collide_at_cell` (0x80033b8c) on the chosen floor, plus the height.
Against a RAM snapshot of level 0 that reproduces all 58 slots, positions and
heights to the unit, and every field but one: the two men by the house are
category 1 on the disc and 8 in memory, changed after loading by something not
yet found.

When they appear
----------------
`actor_tick_driver` (0x80052e5c) runs `0x8004c1f0` on slot k in the frames
where frame & 3 == k & 3 -- once every four frames, staggered -- and on every
slot while 0x801b24f2 is set, which a level load does for exactly one pass.
The byte at +9 is the state, and `render_walk` draws a creature only in 1:

    0 dormant  within (entity+0x0a + 1) cells of the player? then by category:
                 0    held (2) if nearer than entity+0x0a cells -- so it only
                      ever appears at the rim of that ring -- else a roll of
                      rand()>>7 against +0x0a: above it held, else spawn
                 1    the same ring, no roll: spawn
                 2    no ring; a roll of rand()>>4 against +0x0a (0xff always
                      passes): above it try again next time, else spawn
                 3, 4 spawn when the leader is up
                 5, 8 and the rest: held
               "spawn" first asks 0x8004d644 whether another creature that is
               up stands on the spot; if one does, held instead.
    1 up       beyond entity+0x0b cells: back to 0, at home
    2 held     beyond entity+0x0b cells: back to 0 -- leaving is the only release
    3 gone     nothing changes it again

A cell is 2048 units. Every kind on level 0 wakes inside 17 cells, is held
inside 16, and sleeps beyond 17.

What a death does is decided by the category too, in `actor_tick` at
0x80052b7c: 1 goes to 3, gone; 2 straight back to 0; 5 frees the slot; the
rest, 0 among them, to 2 -- and so return the next time the player leaves and
comes back, if the roll allows. When the level is left, 0x8005efd4 writes the
state of every category-1 slot into level_state, 3 or 0, so a dead one is still
dead on the next visit and in the save. Category 0 is not written, and the
next visit rebuilds it from the disc.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tarc import TArc                                                # noqa: E402
from placement import chain, FDAT                                    # noqa: E402
import collision                                                     # noqa: E402
from movement import game_isqrt                                      # noqa: E402

SLOTS = 200
REC = 16
ENTITY = 120
ENTITIES = 40            # entity_table_init walks 0x28 of them
MODEL_TAG = 0x400        # entity[+0] is 0x400 | model
CELL = 11                # a cell is 1 << 11 units
NO_Y = 0xFFFF            # 0x80016ec8's "leave the height out of it"
FREE = 0xFF
SNAP_RAM = "out/snap/b.ram"
ACTOR_TABLE, ACTOR_STRIDE = 0x80185DA8, 0x88

DORMANT, ACTIVE, HELD, GONE = 0, 1, 2, 3
FOLLOWER = 0x10          # entity+0x34: stands on another actor
ON_BASE = 0x400          # entity+0x34: stands at the floor's base height


def links(lv, path=FDAT):
    raw = TArc(path).raw(lv * 3 + 1)
    return raw, chain(raw)


def entities(raw, ch):
    """The fields of an entity record the machine reads."""
    off, _n = ch[0]
    out = []
    for k in range(ENTITIES):
        e = raw[off + k * ENTITY:off + (k + 1) * ENTITY]
        if len(e) < ENTITY:
            break
        out.append({"model": struct.unpack_from("<H", e, 0)[0] - MODEL_TAG,
                    "act": e[0x0A], "deact": e[0x0B],
                    "radius": struct.unpack_from("<H", e, 0x12)[0],
                    "height": struct.unpack_from("<H", e, 0x14)[0],
                    "e1a": struct.unpack_from("<h", e, 0x1A)[0],
                    "e1c": struct.unpack_from("<h", e, 0x1C)[0],
                    "flags": struct.unpack_from("<I", e, 0x34)[0]})
    return out


def floor_y(lvl, layer, x, z, radius, height):
    """collide_at_cell (0x80033b8c): the floor under (x, z), and that floor's base.

    Its first argument picks the floor: 2 is the cell's upper layer, whose height
    is cell[+6], anything else the lower one, cell[+1]. The query is made at the
    layer's own base height and the nearest surface comes back; 0x8004b560 keeps
    it only when it is negative -- up is negative -- and writes 0 otherwise.
    """
    c = lvl.cell(x >> CELL, z >> CELL)
    lay = 5 if layer == 2 else 0
    base = -128 * c[lay + 1]
    _m, cur = collision.collide(lvl, x, base, z, radius, arg5=height,
                                layer=lay, nearest=True)
    return (cur if cur < 0 else 0), base


def table(lv, grid=None):
    """The 200 slots as 0x800530f8 and 0x8004b560 leave them; None where empty."""
    raw, ch = links(lv)
    ents = entities(raw, ch)
    if grid is None:
        import level3d
        grid = level3d.grid_of(lv)
    lvl = collision.Level(lv, grid)
    off, n = ch[1]
    out = [None] * SLOTS
    for k in range(min(SLOTS, n // REC)):
        r = raw[off + k * REC:off + (k + 1) * REC]
        if r[0] == FREE or r[1] >= len(ents):
            continue
        e = ents[r[1]]
        fz, fx, h = struct.unpack_from("<3h", r, 10)
        cat = r[0]
        if e["flags"] & FOLLOWER:          # 0x80053218
            if cat == 3:
                fx = e["e1a"] if fx == -1 else fx
                h = e["e1c"] if h == -1 else h
            else:
                cat, h = 4, 0
        x, z = (r[4] << CELL) + fx, (r[3] << CELL) + fz
        y, base = floor_y(lvl, r[7], x, z, e["radius"], e["height"])
        if e["flags"] & ON_BASE:
            y = base
        if not e["flags"] & FOLLOWER:
            y += h
        out[k] = {"slot": k, "cat": cat, "disc_cat": r[0], "kind": r[1],
                  "model": e["model"], "flags": r[2], "layer": r[7],
                  "cx": r[4], "cz": r[3], "fx": fx, "fz": fz, "h": h,
                  "x": x, "y": y, "z": z,
                  "yaw": (-struct.unpack_from("<H", r, 8)[0]) & 0xFFF,
                  "chance": r[5], "b6": r[6],
                  "act": e["act"], "deact": e["deact"],
                  "radius": e["radius"], "height": e["height"],
                  "eflags": e["flags"],
                  "leader": fz if e["flags"] & FOLLOWER else -1}
    return out


def in_range(ax, ay, az, x, y, z, r, top=0, own=0):
    """0x80016ec8: how far (x, z) is from the actor at (ax, az), or -1 beyond r.

    A box first, then the game's own square root of coordinates shifted down by
    three -- so every distance is a multiple of 8, and a perfect square comes
    out one short. With y other than 0xffff the two bodies must overlap in
    height as well: `top` is the actor's height, `own` the asker's.
    """
    dx = ax - x
    if dx < -r or r < dx:
        return -1
    dz = az - z
    if dz < -r or r < dz:
        return -1
    if y != NO_Y:
        if ay < y:
            if ay < y - own:
                return -1
        elif y < ay - top:
            return -1
    d = game_isqrt((dx >> 3) ** 2 + (dz >> 3) ** 2) << 3
    return -1 if r < d else d


class Machine:
    """0x8004c1f0 and the loop that calls it, over one level's slots.

    What an awake creature *does* -- its AI, in actor_tick -- is not here, so an
    actor stays where it woke. What is here is which ones are drawn.
    """

    def __init__(self, slots, seed=1):
        self.a = [dict(s, st=DORMANT, px=s["x"], py=s["y"], pz=s["z"],
                       ry=s["yaw"]) if s else None for s in slots]
        self.frame = 0
        self.spawn_anywhere = True         # 0x801b24f2, set by the level load
        self.seed = seed
        self.log = []

    def rand(self):
        """BIOS A0:2F, which is all `rand` at 0x800796c0 is. The seed here is
        not the game's: every other caller of rand moves the same sequence."""
        self.seed = (self.seed * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
        return (self.seed >> 16) & 0x7FFF

    def tick(self, px, pz):
        """One pass of actor_tick_driver with the player at (px, pz)."""
        for k, a in enumerate(self.a):
            if a is None or a["cat"] == FREE:
                continue
            if (self.frame & 3) == (k & 3) or self.spawn_anywhere:
                self.activate(k, px, pz)
        self.frame += 1
        self.spawn_anywhere = False        # game_main, 0x80014f58

    def _set(self, k, st, why):
        a = self.a[k]
        if a["st"] != st:
            self.log.append((self.frame, k, a["st"], st, why))
            a["st"] = st

    @staticmethod
    def _home(a):                          # 0x8004b560
        a["px"], a["py"], a["pz"] = a["x"], a["y"], a["z"]

    def _dist(self, a, px, pz, r):
        return in_range(a["px"], a["py"], a["pz"], px, NO_Y, pz, r)

    def _leader(self, a):
        j = a["leader"]
        return self.a[j] if 0 <= j < SLOTS else None

    def _block(self, k, why):              # 0x8004c418: 2 waits, the rest held
        if self.a[k]["cat"] != 2:
            self._set(k, HELD, why)

    def _taken(self, k):
        """0x8004d644 at the spawner's own place: the first other creature that
        is up and overlaps it, radius on radius and height on height, or -1."""
        me = self.a[k]
        for j, o in enumerate(self.a):
            if o is None or j == k or o["st"] != ACTIVE:
                continue
            if in_range(o["px"], o["py"], o["pz"], me["px"], me["py"],
                        me["pz"], o["radius"] + me["radius"], o["height"],
                        me["height"]) != -1:
                return j
        return -1

    def _spawn(self, k):                   # 0x8004b868, then 0x8004b698
        a = self.a[k]
        a["ry"] = a["yaw"]
        self._home(a)
        self._set(k, ACTIVE, "spawn")
        if not a["flags"] & 1:
            a["ry"] = self.rand() >> 3

    def _try(self, k):                     # 0x8004c380
        if self._taken(k) != -1:
            return self._block(k, "spot taken")
        self._spawn(k)

    def activate(self, k, px, pz):
        a = self.a[k]
        st, cat = a["st"], a["cat"]
        if st == ACTIVE:
            if self._dist(a, px, pz, a["deact"] << CELL) == -1:
                self._set(k, DORMANT, "left behind")
                self._home(a)
            return
        if st == HELD:
            if cat in (3, 4):
                lead = self._leader(a)
                if lead is not None and lead["st"] == ACTIVE:
                    return
                self._set(k, DORMANT, "leader gone")
                self._home(a)
                return
            if self._dist(a, px, pz, a["deact"] << CELL) == -1:
                self._set(k, DORMANT, "released")
                self._home(a)
            return
        if st != DORMANT:
            return
        d = self._dist(a, px, pz, (a["act"] + 1) << CELL)
        if d == -1:
            return
        if cat in (3, 4):
            lead = self._leader(a)
            if lead is not None and lead["st"] == ACTIVE:
                self._spawn(k)
            return
        if cat == 2:
            if a["chance"] != FREE and a["chance"] < (self.rand() >> 4):
                return
            return self._try(k)
        if d < (a["act"] << CELL) and not self.spawn_anywhere:
            return self._block(k, "too near")
        if cat == 1:
            return self._try(k)
        if cat != 0 or a["chance"] == 0 or a["chance"] < (self.rand() >> 7):
            return self._block(k, "lost the roll" if cat == 0 else "category")
        self._try(k)

    def kill(self, k):
        """The death branch of actor_tick, 0x80052b7c."""
        a = self.a[k]
        if a["cat"] == 1:                  # 0x8004b770
            self._set(k, GONE, "killed")
            self._home(a)
        elif a["cat"] == 2:
            self._set(k, DORMANT, "killed")
            self._home(a)
        elif a["cat"] == 5:
            a["cat"] = FREE
            self._set(k, DORMANT, "killed, slot freed")
        else:
            self._set(k, HELD, "killed")
            self._home(a)

    def saved(self):
        """What 0x8005efd4 writes into level_state: (slot, 3 or 0) for every
        category-1 slot, and nothing for any other category."""
        return [(k, GONE if a["st"] == GONE else DORMANT)
                for k, a in enumerate(self.a) if a and a["cat"] == 1]


def check(lv=0, path=SNAP_RAM):
    """The disc's table against a RAM snapshot's, field by field."""
    ram = open(path, "rb").read()
    fields = [("cat", 0, 1, False), ("kind", 2, 1, False),
              ("flags", 5, 1, False), ("layer", 6, 1, False),
              ("cz", 7, 1, False), ("cx", 8, 1, False),
              ("chance", 0x0A, 1, False), ("b6", 0x0B, 1, False),
              ("yaw", 0x20, 2, False), ("fz", 0x22, 2, True),
              ("fx", 0x24, 2, True), ("h", 0x26, 2, True)]
    bad = collections.Counter()
    seen = homes = 0
    for a in table(lv):
        if a is None:
            continue
        o = (ACTOR_TABLE + a["slot"] * ACTOR_STRIDE) & 0x1FFFFF
        s = ram[o:o + ACTOR_STRIDE]
        seen += 1
        for name, off, size, signed in fields:
            v = int.from_bytes(s[off:off + size], "little", signed=signed)
            if v != a[name]:
                bad[name] += 1
                print(f"  slot {a['slot']:3d} {name}: disc {a[name]}, RAM {v}")
        if s[9] != ACTIVE:                 # one that is up may have walked off
            homes += 1
            if struct.unpack_from("<3i", s, 0x2C) != (a["x"], a["y"], a["z"]):
                bad["home"] += 1
                print(f"  slot {a['slot']:3d} home: disc "
                      f"{(a['x'], a['y'], a['z'])}, RAM "
                      f"{struct.unpack_from('<3i', s, 0x2C)}")
    print(f"level {lv}: {seen} slots, {homes} of them at home; "
          f"differences: {dict(bad) or 'none'}")
    return bad


def arrive(lv, cx, cz):
    """What one pass with the load flag set does for a player in cell (cx, cz)."""
    m = Machine(table(lv))
    m.tick((cx << CELL) + 1024, (cz << CELL) + 1024)
    for _f, k, old, new, why in m.log:
        a = m.a[k]
        print(f"  slot {k:3d} model {a['model']:3d} category {a['cat']} at "
              f"({a['cx']},{a['cz']})  {old} -> {new}  {why}")
    return m


def main():
    args = sys.argv[1:]
    if "--all" in args:
        lv = 0
        while True:
            try:
                slots = table(lv)
            except Exception:
                break
            live = [a for a in slots if a]
            cats = collections.Counter(a["cat"] for a in live)
            print(f"level {lv:2d}: {len(live):3d} actors, by category "
                  f"{dict(sorted(cats.items()))}")
            lv += 1
        return
    lv = int(args[0]) if args and args[0].isdigit() else 0
    if "--check" in args:
        check(lv)
        return
    if "--at" in args:
        i = args.index("--at")
        arrive(lv, int(args[i + 1]), int(args[i + 2]))
        return
    for a in table(lv):
        if a:
            print(f"slot {a['slot']:3d}  category {a['cat']}  kind {a['kind']:2d}"
                  f"  model {a['model']:3d}  cell ({a['cx']:2d},{a['cz']:2d})"
                  f"  yaw {a['yaw']:4d}{' random' if not a['flags'] & 1 else ''}"
                  f"  chance {a['chance']:3d}  floor {a['layer']}")


if __name__ == "__main__":
    main()

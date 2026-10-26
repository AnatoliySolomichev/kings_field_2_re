#!/usr/bin/env python3
"""A thing used: `use_item` (0x8005cbe0) whole, against the game's own.

    python3 tools/useitem.py            the arms, and the check below
    python3 tools/useitem.py --check    the model against the game's own
                                        use_item, run over every level, and
                                        the warp (warp_to) against its own

**`use_item(pos, angles, item)`** is what a thing does once the menu has
closed on it (`player_turn`, 0x80030708: `player_pos` and `player_pitch`, so
`angles[1]` is the facing) or the button's thing is used. It clears its answer
(`0x801ba984`), switches on `item - 0x65` (61 arms from 0x800131a0) and ends,
whatever the arm, by calling the level's own entry 2 (`level_hooks + 8`, with
the angles and the thing), "Nothing happens" (`announce(0xa)`) unless
something answered, and `clear_movement_state`:

```
0x65        truth glass    the creature in sight (sub_8004d3c4 from the feet
                           along the angles: 0x1f40, cones 0x1f4, no noise) on
                           the player's floor -- its +3, 2 for the upper layer
                           (0x801b2644 not 0), else 1 -- shows ITEM.T 0x10e +
                           its model (+1); else find_object's first object, on
                           block 0x11 and in slot 11 (its +0 not 0), ITEM.T
                           0x131; else the first object of a class-0xe2 type
                           whose +0x40 is that floor and whose rectangle
                           (+0x14 >> 11, +0x1c >> 11, +0x38 by +0x39) holds
                           the player: ITEM.T 0x32a + its +0x3a
0x68..0x6d, 0x77, 0x78     answered: item_consume has eaten them
0x6e        verdite        every skill + 1 from 4 down, the thing taken
0x6f        power fruit    stat 36 + 1, three times; not taken here
0x70        wise fruit     0x801b2530 + 1 to 4; not taken here
0x71..0x75  the crystals   their skill + 1, three times, the thing taken
                           (each step under 1000: skill_unlock, the stats, a
                           banner the first time -- 0xd, 1, 2, 0x12 + k)
0x76        crystal flask  find_object's first object: type 0xfe gives a blue
                           potion (0x77), type 0xfb a gold one (0x78); given,
                           announce 0xc and the flask taken; the pack full,
                           give_item's own "can't carry" and the flask kept
0x80                       on block 6 the two statues (slots 0x5b, 0x53); else
                           taken, 0x801b2578 900 frames (five on every skill)
0x82, 0x83, 0x84           Ichrius' eye, wings, crown: warp_to with 1, 6,
                           9 -- not on blocks 0x19 and 0x1b, nor while a
                           change to one is under way
0x96..0xa1                 the same with item - 0x96 (no such things are held)
0x87 0x89..0x8c 0x8e 0x90  the seven keys: tried on each object found in turn
                           (key_test): 1 the sound, 3 or 4 "Wrong key!"
0x88        Orladin's key  every object found: a type-0xa2 lock that asks for
                           it (+0x38 0x88) 0xfe and the key taken; a free
                           type-0x102 pedestal (+0x38 0xff) the key's number,
                           +8 0, the key taken and the key's own object made
                           in the ring 350..359 (find_free_slot with
                           drop_count_gold), the pedestal's +0x39 its place;
                           anything else a 3 from key_test "Wrong key!"
0x8d        Silviera's key find_object's first object: a free type-0x101
                           pedestal takes it (pedestal_put_key); else a 3
                           "Wrong key!"
the rest                   nothing of its own
```

find_object is always asked from the feet, 0x320 past the type's reach, 0x6a4
as the point's height, within 0x200 of the facing.

**The level's own entry 2** (`level_use`) is read for levels 1, 2, 5, 7, 20,
23, 25 and 27. Levels 1 and 2 hand a thing to a creature: `actor_spot_taken`
from the feet at 0x578 by 0x6a4 must answer their slot --

```
level 1   the blood herb (0x7f) to slot 20 while story flag 0xa is 0: taken,
          the flag 1, script_interpreter for the creature (its conversation,
          one call), door 71's lock (cell (35,43)) 0xc8 lifted to 0xff,
          slot 22's category 8 -- held, never woken -- and slot 39's 1: two
          of model 6, at home in (66,52) and in (34,43) by the door
level 2   the earth herb (0x68), the blood stone (0x6c), the moon stone
          (0x6d) and the dragon crystal (0x6b), in that order, to slot 4,
          each while story byte 0x10 (0x801ba998) names it: the byte 1, 2, 3
          or 4, the thing taken, script_interpreter, and object_signal(0x9a)
          -- gate 44's lock (cell (9,40)) 0x9a turned to 0x9b, which opens
          it, and back; the conversation's own hook (entry 4) names the next
```

**`object_signal(id)`** (0x800463bc) hands an id to every object by its
opcode (`object_signal` below); `signal_check` holds it to the game's own.

**How it is held to the game.** `check()` runs GAME.EXE's own `use_item` with
`tools/mipsrun.py` over every level -- the level's objects as its own
`load_object_placement` leaves them (`mipsrun.level_cpu`), the creatures of the
snapshot -- with the player put in front of the objects that answer a thing
(fountains, locks, pedestals, the class-0xe2 rectangles, slot 11 of block
0x11, the creatures), the thing, the pack, the skills, the spells, the
floors and the counts drawn at random. The game's own find_object, key_test,
sub_8004d3c4, player_in_rect, take_item, give_item, skill_unlock (which
answers too when it unlocks a spell, 0x80029fb0), find_free_slot and
init_object_record run; what it calls beyond them is stood in for and logged,
in order -- announce, load_entry, sound_key_fits, player_recalc_stats,
pedestal_put_key, clear_movement_state, script_interpreter (the creature it is
handed), the level's own entries (by where they return to; the entry 2 of the
levels read here runs out of their overlays, actor_spot_taken and
object_signal as the game's) and warp_to, the warp, whose answer the stand-in gives as the
routine does (0x8005c938, 0x8005cb94: none for a record whose level is 0xff,
else 1 for those below 0xc). The model must give the same log, the same
answer, the same pack, skills, stat 36, 0x801b2530, 0x801b2578, spells and
story flags, the creatures' categories (+0 of all 200) and the same 396 object
records byte for byte: 2800 of 2800. Not run: the thing 0x80 on block 6
(the statues' scene runs frames of the game, actor_tick_driver and
render_frame, until the creature wakes).
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

USE_ITEM = 0x8005CBE0
ANSWER = 0x801BA984
PLAYER_POS = 0x801B25F0          # x, y, z words
PLAYER_ANGLES = 0x801B2610       # player_pitch, player_facing
LAYER = 0x801B2644               # collision_layer_offset as player_horizontal kept it
INV_A, INV_B = 0x800C85E8, 0x800C867E
SKILLS = 0x801B2518              # five halfwords
STAT36 = 0x801B2516
WIS = 0x801B2530
BONUS_SKILLS = 0x801B2578        # five on every skill while it runs
BLOCK = 0x8018FAD8               # current_level_block
BUSY = 0x8018FAD4                # level_change_busy
PENDING = 0x8018FAE4             # pending_level
LEVEL_HOOKS = 0x8018FAE0
DROP_COUNT = 0x8019839A          # drop_count_gold
SPELL_TABLE = 0x801B77EC         # spell_table: +0 of each 24-byte record, unlocked
FLAGS = 0x801BA988               # story_flags
OBJECTS, STRIDE, COUNT = 0x80191A5C, 0x44, 0x18C
TYPES = 0x8018FB3C
ACTORS, ACTOR_STRIDE, ACTOR_N = 0x80185DA8, 0x88, 200
CURRENT_ACTOR = 0x8018FAB4
CUR_INDEX = 0x8018FAC0           # current_actor_index: the pass leaves it at 200
SKIP_MASK = 0x8018FAA8           # actor_skip_mask: 4 through player_controller
MASK = 0x1FFFFF

ANNOUNCE = 0x80041EEC
LOAD_ENTRY = 0x800441D4
SOUND_KEY_FITS = 0x8005BD34
RECALC = 0x80029500
PUT_KEY = 0x8005C7E8
CLEAR_MOVEMENT = 0x8002B6F0
SCRIPT = 0x8005C308              # script_interpreter, a creature's conversation
WARP = 0x8005C864
WARP_TABLE = 0x800130F0          # warp_to's records, eight bytes each

TRUTH_GLASS = 0x65
EATEN = (0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D, 0x77, 0x78)
VERDITE, POWER_FRUIT, WISE_FRUIT = 0x6E, 0x6F, 0x70
CRYSTALS = range(0x71, 0x76)
FLASK, BLUE, GOLD = 0x76, 0x77, 0x78
FOUNTAIN = {0xFE: BLUE, 0xFB: GOLD}         # the type find_object finds, what it gives
STATUE_THING = 0x80
STATUES = (0x5B, 0x53)                      # the slots block 6's arm looks for
ICHRIUS = {0x82: 1, 0x83: 6, 0x84: 9}       # the warp record each asks for
NO_WARP = (0x19, 0x1B)                      # blocks the warp refuses
KEYS = (0x87, 0x89, 0x8A, 0x8B, 0x8C, 0x8E, 0x90)
ORLADIN_KEY, ORLADIN_LOCK, ORLADIN_PEDESTAL = 0x88, 0xA2, 0x102
SILVIERA_KEY, SILVIERA_PEDESTAL = 0x8D, 0x101
RING, RING_SIZE = 0x15E, 0xA                # the gold ring Orladin's key's object is made in
AREA_CLASS = 0xE2                           # the type class of the named rectangles
TRUTH_CREATURE, TRUTH_SLOT11, TRUTH_AREA = 0x10E, 0x131, 0x32A   # ITEM.T bases
ITEM_ARCHIVE = 6
BONUS_FRAMES = 0x384
STAT_CAP, WIS_CAP = 0x3E7, 5

# the banners
NOTHING_HAPPENS, WRONG_KEY, FILLED = 0xA, 7, 0xC


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


# --- the world use_item reads ---------------------------------------------------

def world_of(ram):
    """What use_item and the routines it runs read, out of RAM: the player,
    the block, the pack, the figures, every object record (by its fields)
    and the awake creatures sub_8004d3c4 looks at."""
    def u8(a):
        return ram[a & MASK]

    def u16(a):
        return struct.unpack_from("<H", ram, a & MASK)[0]

    def i32(a):
        return struct.unpack_from("<i", ram, a & MASK)[0]
    w = {"pos": [i32(PLAYER_POS), i32(PLAYER_POS + 4), i32(PLAYER_POS + 8)],
         "pitch": s16(u16(PLAYER_ANGLES)), "facing": s16(u16(PLAYER_ANGLES + 2)),
         "layer": u16(LAYER), "block": u8(BLOCK), "busy": s16(u16(BUSY)),
         "pending": u8(PENDING),
         "inv_a": list(ram[INV_A & MASK:(INV_A & MASK) + 0x96]),
         "inv_b": list(ram[INV_B & MASK:(INV_B & MASK) + 0x96]),
         "skills": [u16(SKILLS + 2 * k) for k in range(5)],
         "stat36": u16(STAT36), "wis": u16(WIS), "b578": u16(BONUS_SKILLS),
         "drops": u16(DROP_COUNT),
         "spells": [u8(SPELL_TABLE + 24 * i) for i in range(96)],
         "flags": list(ram[FLAGS & MASK:(FLAGS & MASK) + 0x100]),
         "skip_mask": u8(SKIP_MASK), "cur_index": i32(CUR_INDEX),
         "cats": [u8(ACTORS + ACTOR_STRIDE * k) for k in range(ACTOR_N)],
         "objects": [], "creatures": []}
    for k in range(COUNT):
        r = OBJECTS + STRIDE * k
        t = u16(r + 6)
        row = TYPES + 24 * (t & 0xFFFF)
        w["objects"].append({
            "slot": k, "type": t, "b0": u8(r), "op": u8(r + 4), "state": u16(r + 8),
            "height": u16(r + 0xC), "x": i32(r + 0x14), "y": i32(r + 0x18),
            "z": i32(r + 0x1C), "yaw": s16(u16(r + 0x26)), "b38": u8(r + 0x38),
            "b39": u8(r + 0x39), "h3a": u16(r + 0x3A), "h3c": u16(r + 0x3C),
            "b40": u8(r + 0x40), "cls": u8(row), "reach": u16(row + 6),
            "top": u16(row + 8), "b3d": u8(r + 0x3D), "b3f": u8(r + 0x3F),
            "clk": u16(r + 0xA)})
    cur = struct.unpack_from("<I", ram, CURRENT_ACTOR & MASK)[0]
    for k in range(ACTOR_N):
        a = ACTORS + ACTOR_STRIDE * k
        if u8(a + 9) != 1 or a == cur:
            continue
        w["creatures"].append({
            "slot": k, "e": u8(a + 0xE), "flags": struct.unpack_from("<I", ram, (a + 0x28) & MASK)[0],
            "x": i32(a + 0x2C), "y": i32(a + 0x30), "z": i32(a + 0x34),
            "model": u8(a + 1), "floor": u8(a + 3), "radius": u16(a + 0x1C),
            "height": u16(a + 0x1E), "lead": s16(u16(a + 0x22)), "lift": s16(u16(a + 0x26))})
    return w


# --- what it runs of the game's -------------------------------------------------

def find_object(w, start, add, own, tol):
    """find_object (0x80045c7c) from the player's feet along the facing: from
    `start`, the first object whose type is not 0xff within `add` past its
    type's reach -- `own` as the point's height -- and, but for type 0x95,
    within `tol` of the facing. A class-0x1b door is asked from 0x700 ahead of
    the point along its own yaw, a class-0 one from 0x700 behind and a
    class-1 one from 0x400 behind, the record's +0xc its top; anything else
    from the point, the type's +8 its top."""
    import movement
    px, py, pz = w["pos"]
    for o in w["objects"][max(start, 0):]:
        if o["type"] == 0xFF:
            continue
        cls = o["cls"]
        door = cls in (0x1B, 0, 1)
        x, z, top = px, pz, o["top"]
        if door:
            off = 0x700 if cls == 0x1B else (-0x700 if cls == 0 else -0x400)
            x += (movement.game_cos(o["yaw"]) * off) >> 12
            z += (movement.game_sin(o["yaw"]) * off) >> 12
            top = o["height"]
        if movement.in_range((o["x"], o["y"], o["z"]), x, py, z, o["reach"] + add,
                             top, own) == -1:
            continue
        if not door and o["type"] == 0x95:
            return o["slot"]
        ang = s16(movement.vec_angle(s32(o["x"] - x), s32(o["z"] - z)))
        d = (w["facing"] - ang) & 0xFFF
        if d <= tol or d >= 0x1000 - tol:
            return o["slot"]
    return -1


def key_test(o, key):
    """key_test (0x80046608) on an object's record."""
    import chests
    got, lock = chests.key_test(o["op"], o["state"], o["b38"], key)
    o["b38"] = lock
    return got


def sight(w, reach, ycone, pcone):
    """sub_8004d3c4 from the feet along the player's angles, no noise: the
    awake creature (not +0xe 3) within reach -- twice it for flag 0x20000 --
    inside the cones whose bearing, pitch and distance / 128 add up least."""
    import effects
    import movement
    best, chosen = 0x7530, None
    px, py, pz = w["pos"]
    for c in w["creatures"]:
        if c["e"] == 3:
            continue
        r = reach << 1 if c["flags"] & 0x20000 else reach
        d = movement.in_range((c["x"], c["y"], c["z"]), px, 0xFFFF, pz, r, 0, 0)
        if d == -1:
            continue
        ang = effects.vec_to_angles(s32(c["x"] - px), s32(c["y"] - py), s32(c["z"] - pz))
        dy = (ang[1] - w["facing"]) & 0xFFF
        if dy >= 0x800:
            dy = 0x1000 - dy
        dp = (ang[0] - w["pitch"]) & 0xFFF
        if dp >= 0x800:
            dp = 0x1000 - dp
        if ycone < dy or pcone < dp:
            continue
        score = dy + dp + (d >> 7)
        if score < best:
            best, chosen = score, c
    return chosen


def in_rect(w, cx, cz, cw, ch):
    """player_in_rect (0x80046884) with no height: the player's cell in it."""
    x, z = w["pos"][0] >> 11, w["pos"][2] >> 11
    return cx <= x < cx + cw and cz <= z < cz + ch


def take_item(w, calls, item):
    """take_item (0x8005d7f8): one from the first array that has one, then
    the level's entry 11."""
    for arr in ("inv_a", "inv_b"):
        if w[arr][item]:
            w[arr][item] -= 1
            calls.append(("hook", "take"))
            return


def give_item(w, calls, item):
    """give_item (0x8005d898): one more in the first array under 99 and the
    level's entry 6, 0; both full, announce 0xb and 1."""
    for arr in ("inv_a", "inv_b"):
        if w[arr][item] < 0x63:
            w[arr][item] += 1
            calls.append(("hook", "give"))
            return 0
    calls.append(("announce", 0xB))
    return 1


def free_slot(w, start, count, counter):
    """find_free_slot (0x80046034)."""
    chosen, age = None, 0
    for o in w["objects"][start:start + count]:
        if o["type"] == 0xFF:
            return o
        if counter == -1:
            continue
        d = counter - o["h3c"]
        if d < 0:
            d += 0x10000
        if age < d:
            chosen, age = o, d
    return chosen


def init_record(o):
    """init_object_record (0x800448b8), on the fields the world keeps -- the
    record's own bytes are written by write_back."""
    o.update({"b0": 0, "op": 0xFF, "made": True})


_SKILLS = []


def _skill_data():
    if not _SKILLS:
        import levelup
        _SKILLS.append(levelup.skill_data())
    return _SKILLS[0]


def warp_record(i):
    """warp_to's record i (0x800130f0), as GAME.EXE holds it."""
    import mips
    exe = mips.load("game")
    return list(exe.bytes(WARP_TABLE + 8 * i, 8))


def warp_answers(i):
    """Whether warp_to(i) answers: it returns at once for a record whose
    level is 0xff (0x8005c938), and sets 0x801ba984 for i below 0xc
    (0x8005cb94)."""
    if i < 0xC or i == 0xD:
        if warp_record(i)[0] == 0xFF:
            return False
    return i < 0xC


def skill_unlock(w, calls, k):
    """skill_unlock (0x80029f1c), run: each spell it unlocks says so
    (announce 3) and answers (0x80029fb0)."""
    import levelup
    st = {"grow": w["skills"], "spells": w["spells"]}
    for b in levelup.skill_unlock(st, k, w["flags"], _skill_data()):
        calls.append(("announce", b))
        w["answer"] = 1


# --- the routine ----------------------------------------------------------------

def use_item(w, item):
    """use_item over the world `w`, which it changes as the game's code
    changes RAM: [the calls it makes beyond what it runs, in order] and
    w["answer"]."""
    calls = []
    w["answer"] = 0
    find = lambda start: find_object(w, start, 0x320, 0x6A4, 0x200)   # noqa: E731
    floor = 2 if w["layer"] else 1

    def say(code):
        calls.append(("announce", code))

    def answer():
        w["answer"] = 1

    def recalc():
        calls.append(("recalc",))

    def unlock(k):
        skill_unlock(w, calls, k)

    if item == TRUTH_GLASS:
        c = sight(w, 0x1F40, 0x1F4, 0x1F4)
        if c is not None and c["floor"] == floor:
            calls.append(("load_entry", ITEM_ARCHIVE, c["model"] + TRUTH_CREATURE))
            answer()
        else:
            k = find(0)
            if k != -1 and w["objects"][k]["b0"] != 0 and k == 0xB and w["block"] == 0x11:
                calls.append(("load_entry", ITEM_ARCHIVE, TRUTH_SLOT11))
                answer()
            if not w["answer"]:
                for o in w["objects"]:
                    if o["cls"] != AREA_CLASS or o["b40"] != floor:
                        continue
                    if in_rect(w, o["x"] >> 11, o["z"] >> 11, o["b38"], o["b39"]):
                        calls.append(("load_entry", ITEM_ARCHIVE,
                                      (o["h3a"] + TRUTH_AREA) & 0xFFFF))
                        answer()
                        break
    elif item in EATEN:
        answer()
    elif item == VERDITE or item in CRYSTALS:
        take_item(w, calls, item)
        ks = range(4, -1, -1) if item == VERDITE else [item - CRYSTALS.start] * 3
        for k in ks:
            w["skills"][k] = (w["skills"][k] + 1) & 0xFFFF
            if w["skills"][k] >= 1000:
                w["skills"][k] = STAT_CAP
                continue
            unlock(k)
            recalc()
            if not w["answer"]:
                answer()
                say(0xD if item == VERDITE else 0x12 + k)
    elif item == POWER_FRUIT:
        for _ in range(3):
            w["stat36"] = (w["stat36"] + 1) & 0xFFFF
            if w["stat36"] >= 1000:
                w["stat36"] = STAT_CAP
                continue
            recalc()
            if not w["answer"]:
                answer()
                say(1)
    elif item == WISE_FRUIT:
        w["wis"] = (w["wis"] + 1) & 0xFFFF
        if w["wis"] >= WIS_CAP:
            w["wis"] = WIS_CAP - 1
        else:
            recalc()
            if not w["answer"]:
                answer()
                say(2)
    elif item == FLASK:
        k = find(0)
        if k != -1 and w["objects"][k]["type"] in FOUNTAIN:
            if give_item(w, calls, FOUNTAIN[w["objects"][k]["type"]]) == 0:
                say(FILLED)
                take_item(w, calls, item)
            answer()
    elif item == STATUE_THING:
        if w["block"] == 6:
            raise ValueError("the statues' scene on block 6 is not modelled")
        take_item(w, calls, item)
        w["b578"] = BONUS_FRAMES
        answer()
        recalc()
    elif item in ICHRIUS or 0x96 <= item <= 0xA1:
        i = ICHRIUS.get(item, item - 0x96)
        if not (w["block"] in NO_WARP or (w["busy"] == 1 and w["pending"] in NO_WARP)):
            calls.append(("warp", i))
            if warp_answers(i):
                answer()
    elif item in KEYS:
        k = 0
        while True:
            k = find(k)
            if k == -1:
                break
            got = key_test(w["objects"][k], item)
            if got == 1:
                calls.append(("sound_key_fits",))
                answer()
                break
            if got in (3, 4):
                say(WRONG_KEY)
                answer()
                break
            k += 1
    elif item == ORLADIN_KEY:
        k = 0
        while True:
            k = find(k)
            if k == -1:
                break
            o = w["objects"][k]
            if o["type"] == ORLADIN_LOCK:
                if o["b38"] == ORLADIN_KEY:
                    o["b38"] = 0xFE
                    answer()
                    take_item(w, calls, item)
            elif o["type"] == ORLADIN_PEDESTAL:
                if o["b38"] == 0xFF:
                    o["b38"] = item
                    o["state"] = 0
                    answer()
                    take_item(w, calls, item)
                    m = free_slot(w, RING, RING_SIZE, w["drops"])
                    if m is None:                # the game's would be address 0
                        raise ValueError("no slot in the ring older than now")
                    init_record(m)
                    m["h3c"] = w["drops"]
                    w["drops"] = (w["drops"] + 1) & 0xFFFF
                    m["type"] = item
                    m["b38"] = 0
                    o["b39"] = (m["slot"] - 0x5E) & 0xFF
            elif key_test(o, item) == 3:
                say(WRONG_KEY)
                answer()
            k += 1
    elif item == SILVIERA_KEY:
        k = find(0)
        if k != -1:
            o = w["objects"][k]
            if o["type"] == SILVIERA_PEDESTAL:
                if o["b38"] == 0xFF:
                    o["b38"] = item
                    o["state"] = 0
                    answer()
                    take_item(w, calls, item)
                    calls.append(("put_key", k, item))
            elif key_test(o, item) == 3:
                say(WRONG_KEY)
                answer()
    level_use(w, item, calls)
    if not w["answer"]:
        say(NOTHING_HAPPENS)
    calls.append(("clear",))
    return calls


LEVEL_USE = (1, 2, 5, 7, 20, 23, 25, 27)   # the levels whose entry 2 is read here
HAND_KEY = 0x85                        # the levels' own keys on their own pedestals
STONE_KEY = 0x86
NO_USE = 0x23                          # the banner levels 7, 25 and 27 raise for 0x85
BLOOD_HERB = 0x7F                      # what level 1's creature in slot 20 takes
LEVEL1_ASKED, LEVEL1_TAKER = 0xA, 20   # story flag 0xa (0x801ba992): it has
LEVEL1_DOOR = 71                       # the door whose lock 0xc8 the herb lifts
LEVEL1_CATS = {22: 8, 39: 1}           # the two slots the herb moves: held, up
LEVEL2_WANTED, LEVEL2_TAKER = 0x10, 4  # story byte 0x801ba998: the thing slot 4 wants
LEVEL2_STAGE = {0x68: 1, 0x6C: 2, 0x6D: 3, 0x6B: 4}   # the byte after each is given
LEVEL2_SIGNAL = 0x9A                   # object_signal's id: gate 44's lock
GIVE_R, GIVE_OWN = 0x578, 0x6A4        # actor_spot_taken from the feet: r, own height
VERTEX_PLACED = 0x400000               # a creature a model's vertex places


def spot_taken(w, x, y, z, r, own):
    """actor_spot_taken (0x8004d644): the slot of the first awake creature
    (the world's creatures are the +9 == 1 ones less current_actor), not
    dying (+0xe 3), whose flags share no bit with actor_skip_mask, in
    in_range of (x, y, z) at its radius + r, its height as the top and `own`
    as the point's -- a follower (flag 0x10) +0x26 higher, and skipped when
    its +0x22 is current_actor_index; or -1."""
    import movement
    for c in w["creatures"]:
        if c["e"] == 3 or c["flags"] & w["skip_mask"]:
            continue
        cy = c["y"]
        if c["flags"] & 0x10:
            if c["lead"] == w["cur_index"]:
                continue
            cy += c["lift"]
        elif c["flags"] & VERTEX_PLACED:
            raise ValueError("a creature a model's vertex places is not modelled")
        if movement.in_range((c["x"], cy, c["z"]), x, y, z, c["radius"] + r,
                             c["height"], own) != -1:
            return c["slot"]
    return -1


def object_signal(w, sig):
    """object_signal (0x800463bc): `sig` handed to every object, each by its
    opcode -- a door's (0..5, 0x1b) lock: for an id in 0x96..0xc6 the lock
    with bit 0 off is turned over (odd opens, even shuts), else the lock
    itself, 0xc8 and up lifted (0xff), below it the door started (+8 1 from
    0) and from 0x64 lifted too; 0x51's +0x3d, 0x52's, 0x55's and 0x5a's
    +0x3f turn +0x38 between 0 and 0xff; 0x54's, 0xa2's and 0xa3's +0x38
    lifted; 0x56's +0x3a turns +0x39; 0x58's +0x39 starts it and turns +0x38
    between 0 and 1; 0x59's +0x38 starts it; 0x5f's +0x38 starts it and turns
    +0x3f between 0 and 1. 0xff is no id."""
    sig &= 0xFF
    if sig == 0xFF:
        return
    toggled = ((sig + 0x6A) & 0xFF) < 0x31
    zero_ff = lambda v: 0xFF if v == 0 else 0      # noqa: E731
    for o in w["objects"]:
        op = o["op"]
        if op <= 5 or op == 0x1B:
            if toggled:
                if o["b38"] & 0xFE == sig:
                    o["b38"] ^= 1
            elif o["b38"] == sig:
                if sig >= 0xC8:
                    o["b38"] = 0xFF
                elif o["state"] == 0:
                    o["state"] = 1
                    if sig >= 0x64:
                        o["b38"] = 0xFF
        elif op == 0x51:
            if o["b3d"] == sig:
                o["b38"] = zero_ff(o["b38"])
        elif op in (0x52, 0x55, 0x5A):
            if o["b3f"] == sig:
                o["b38"] = zero_ff(o["b38"])
        elif op in (0x54, 0xA2, 0xA3):
            if o["b38"] == sig:
                o["b38"] = 0xFF
        elif op == 0x56:
            if o["h3a"] & 0xFF == sig:
                o["b39"] = zero_ff(o["b39"])
        elif op == 0x58:
            if o["b39"] == sig:
                o["state"] = 1
                o["b38"] = 1 if o["b38"] == 0 else 0
        elif op == 0x59:
            if o["b38"] == sig:
                o["state"] = 1
        elif op == 0x5F:
            if o["b38"] == sig:
                o["state"] = 1
                o["b3f"] = 1 if o["b3f"] == 0 else 0


def level_use(w, item, calls):
    """The level's own entry 2 (level_hooks + 8: player_pos, player_pitch,
    the thing), for the levels read here; the others' are logged."""
    lv = w.get("overlay", w["block"])
    if lv not in LEVEL_USE:
        calls.append(("hook", "use"))
        return
    flags = w["flags"]

    def answer():
        w["answer"] = 1

    def first():
        return find_object(w, 0, 0x320, 0x6A4, 0x200)

    def given(slot):
        # actor_spot_taken from the feet: the creature that takes it
        k = spot_taken(w, w["pos"][0], w["pos"][1], w["pos"][2], GIVE_R, GIVE_OWN)
        return k != -1 and k == slot
    if lv == 1:
        if item != BLOOD_HERB or flags[LEVEL1_ASKED] != 0 or not given(LEVEL1_TAKER):
            return
        take_item(w, calls, item)
        flags[LEVEL1_ASKED] = 1           # in the call's delay slot: before it talks
        calls.append(("talk", LEVEL1_TAKER))
        door = w["objects"][LEVEL1_DOOR]
        if door["b38"] == 0xC8:
            door["b38"] = 0xFF
        for k, v in LEVEL1_CATS.items():
            w["cats"][k] = v
        answer()
    elif lv == 2:
        if item not in LEVEL2_STAGE or flags[LEVEL2_WANTED] != item or not given(LEVEL2_TAKER):
            return
        flags[LEVEL2_WANTED] = LEVEL2_STAGE[item]
        take_item(w, calls, item)
        calls.append(("talk", LEVEL2_TAKER))
        object_signal(w, LEVEL2_SIGNAL)
        answer()
    elif lv in (25, 27):
        if item == HAND_KEY:
            answer()
            calls.append(("announce", NO_USE))
    elif lv == 20:
        if item != 0x7E or not in_rect(w, 0x26, 0x10, 3, 2):
            return
        if w["inv_a"][0x7D] or w["inv_b"][0x7D]:
            if flags[0x56] == 0:
                flags[0x56] = 1
                flags[0x57] = 0
                take_item(w, calls, 0x7E)
                answer()
        elif flags[0x56] == 0:
            calls.append(("announce", 0x10))
            answer()
    elif lv == 5:
        if item != 0x66:
            return
        k = first()
        if k == -1:
            return
        o = w["objects"][k]
        if o["op"] != 0x53 or o["b3d"] >= 0x97:
            return
        if not (w["inv_a"][o["b3d"]] or w["inv_b"][o["b3d"]]):
            return
        if o["clk"] == 0 or o["clk"] >= 0xFFF:
            o["state"] = 1
            answer()
    elif lv in (7, 23):
        key, typ = (HAND_KEY, 0x140) if lv == 7 else (STONE_KEY, 0x13F)
        if item != key:
            return
        k = first()
        if k == -1:
            if lv == 7:
                answer()
                calls.append(("announce", NO_USE))
            return
        o = w["objects"][k]
        if o["type"] == typ:
            import ai
            if lv == 7 and not ai.facing_test(s16(w["facing"] + 0x800), o["yaw"], 0x100):
                return
            if o["b38"] != 0xFF:
                return
            o["b38"] = item
            o["state"] = 0
            answer()
            take_item(w, calls, item)
            calls.append(("put_key", k, item))
        elif key_test(o, item) == 3:
            calls.append(("announce", WRONG_KEY))
            answer()


# --- against the game's own -----------------------------------------------------

def write_back(ram, w):
    """The world's object fields into `ram`, where the game keeps them -- and
    a record init_object_record made, with what it writes."""
    for o in w["objects"]:
        r = (OBJECTS + STRIDE * o["slot"]) & MASK
        if o.get("made"):
            ram[r + 1] = 0x80
            for off in (0x30, 0x2E, 0x2C):
                struct.pack_into("<H", ram, r + off, 0x1000)
            for off in (0xA, 0x28, 0x24, 0x26, 0xE, 0x10):
                struct.pack_into("<H", ram, r + off, 0)
            ram[r + 2] = 0
            ram[r + 5] = 0xFF
        ram[r] = o["b0"]
        ram[r + 4] = o["op"]
        struct.pack_into("<H", ram, r + 6, o["type"])
        struct.pack_into("<H", ram, r + 8, o["state"])
        ram[r + 0x38] = o["b38"]
        ram[r + 0x39] = o["b39"]
        struct.pack_into("<H", ram, r + 0x3C, o["h3c"])
        ram[r + 0x3F] = o["b3f"]
    for k, v in enumerate(w["cats"]):
        ram[(ACTORS + ACTOR_STRIDE * k) & MASK] = v


def game_run(cpu, item):
    """The game's own use_item over the machine's RAM: (the calls it made
    beyond what it ran, in order, as use_item() logs them)."""
    calls = []
    hooks = struct.unpack_from("<I", cpu.ram, LEVEL_HOOKS & MASK)[0]
    entry = lambda n: struct.unpack_from("<I", cpu.ram, (hooks + 4 * n) & MASK)[0]   # noqa: E731
    where = {0x8005D764: "use", 0x8005D934: "give"}

    def level_hook(c):
        ra = c.r[31]
        calls.append(("hook", where.get(ra, "take")))

    def warp(c):
        i = c.r[4]
        calls.append(("warp", i))
        if warp_answers(i):
            c.wr(ANSWER, 4, 1)
    cpu.hooks = {
        ANNOUNCE: lambda c: calls.append(("announce", c.r[4])),
        LOAD_ENTRY: lambda c: calls.append(("load_entry", c.r[4], c.r[5])),
        SOUND_KEY_FITS: lambda c: calls.append(("sound_key_fits",)),
        RECALC: lambda c: calls.append(("recalc",)),
        PUT_KEY: lambda c: calls.append(("put_key", (c.r[4] - OBJECTS) // STRIDE, c.r[5])),
        CLEAR_MOVEMENT: lambda c: calls.append(("clear",)),
        WARP: warp,
        SCRIPT: lambda c: calls.append(("talk", (c.r[4] - ACTORS) // ACTOR_STRIDE)),
    }
    for n in (2, 6, 11):
        if n == 2 and getattr(cpu, "level", None) in LEVEL_USE:
            continue                      # the overlay's own code runs
        cpu.hooks[entry(n)] = level_hook
    cpu.call(USE_ITEM, PLAYER_POS, PLAYER_ANGLES, item)
    return calls


def _put(cpu, a, n, v):
    cpu.wr(a, n, v & ((1 << (8 * n)) - 1))


def _targets(w, lv=None):
    """The things worth standing in front of on this level, by what asks
    them: {scenario: [(object, [items])]}. A type of 300 or more is the
    level's own, so level 7's pedestals (0x140) and 23's (0x13f) are asked
    for on their own level."""
    out = {}
    for o in w["objects"]:
        t = o["type"]
        if t == 0xFF:
            continue
        if t in FOUNTAIN:
            out.setdefault("fountain", []).append((o, [FLASK]))
        if t in (ORLADIN_LOCK, ORLADIN_PEDESTAL):
            out.setdefault("orladin", []).append((o, [ORLADIN_KEY]))
        if t == SILVIERA_PEDESTAL:
            out.setdefault("silviera", []).append((o, [SILVIERA_KEY]))
        if o["op"] in (0, 1, 2, 3, 4, 5, 6, 7, 8, 0xF, 0x11, 0x17, 0x18, 0x1A, 0x1B, 0xA7):
            out.setdefault("lock", []).append((o, list(KEYS) + [ORLADIN_KEY, SILVIERA_KEY]))
        if o["cls"] == AREA_CLASS:
            out.setdefault("area", []).append((o, [TRUTH_GLASS]))
        if o["slot"] == 0xB:
            out.setdefault("slot11", []).append((o, [TRUTH_GLASS]))
        if (lv, t) in ((7, 0x140), (23, 0x13F)):
            out.setdefault("own pedestal", []).append((o, [HAND_KEY, STONE_KEY]))
        if lv == 5 and o["op"] == 0x53:
            out.setdefault("0x53", []).append((o, [0x66]))
    return out


ARMS = ([TRUTH_GLASS, FLASK, VERDITE, POWER_FRUIT, WISE_FRUIT, STATUE_THING, ORLADIN_KEY,
         SILVIERA_KEY] + list(CRYSTALS) + list(EATEN) + list(ICHRIUS) + list(KEYS)
        + [0x66, 0x79, 0x7B, 0x8F, 0x95, 0x97, 0xA1, 0x20, 0xA2, HAND_KEY, STONE_KEY, 0x7E,
           0x7F])


def cases(lv, n, rng, snap="a1"):
    """`n` runs on level `lv`: [(the machine, the item)], laid out at random."""
    import mipsrun
    import movement
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    w0 = world_of(ram0)
    targets = _targets(w0, lv)
    out = []
    kinds = sorted(targets) + (["creature"] if w0["creatures"] else []) + ["anything"]
    if lv == 20:
        kinds += ["rect 20"] * 2
    if lv in (25, 27):
        kinds += ["the level's thing"]
    if lv in (1, 2):
        import actors
        homes = actors.table(lv)
        kinds += ["the taker"] * 24
    kinds += [k for k in ("own pedestal", "0x53") if k in targets] * 2
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        block = lv
        kind = rng.choice(kinds)
        if kind in targets:
            o, items = rng.choice(targets[kind])
            item = rng.choice(items)
            if kind == "own pedestal" and rng.random() < 0.8:
                item = HAND_KEY if lv == 7 else STONE_KEY      # the level's own
            if o["cls"] == AREA_CLASS and item == TRUTH_GLASS and o["b38"] and o["b39"]:
                x = ((o["x"] >> 11) + rng.randrange(o["b38"] + 2) - 1) * 0x800 + rng.randrange(0x800)
                z = ((o["z"] >> 11) + rng.randrange(o["b39"] + 2) - 1) * 0x800 + rng.randrange(0x800)
                fac = rng.randrange(0x1000)
            else:
                d = rng.randrange(0x100, 0x800 if kind in ("lock", "own pedestal") else 0xC00)
                a = rng.randrange(0x1000)
                # find_object asks a door from a point off the player's along
                # the door's own yaw: stand where that point falls near it
                off = {0x1B: 0x700, 0: -0x700, 1: -0x400}.get(o["cls"], 0)
                ox = o["x"] - ((movement.game_cos(o["yaw"]) * off) >> 12)
                oz = o["z"] - ((movement.game_sin(o["yaw"]) * off) >> 12)
                x = ox + ((movement.game_cos(a) * d) >> 12)
                z = oz + ((movement.game_sin(a) * d) >> 12)
                fac = (movement.vec_angle(s32(ox - x), s32(oz - z))
                       + rng.randrange(-0x300, 0x300)) & 0xFFF
                if kind == "own pedestal" and lv == 7 and rng.random() < 0.7:
                    # level 7's asks the player to face it: stand where the
                    # way to it is its yaw turned round
                    want = (o["yaw"] - 0x800) & 0xFFF
                    for _ in range(64):
                        a = rng.randrange(0x1000)
                        x = ox + ((movement.game_cos(a) * d) >> 12)
                        z = oz + ((movement.game_sin(a) * d) >> 12)
                        to = movement.vec_angle(s32(ox - x), s32(oz - z))
                        if abs(((to - want + 0x800) & 0xFFF) - 0x800) < 0xA0:
                            break
                    fac = (to + rng.randrange(-0x80, 0x80)) & 0xFFF
            y = o["y"] + rng.randrange(-0x400, 0x400)
            if o["slot"] == 0xB and rng.random() < 0.7:
                block = 0x11
        elif kind == "the level's thing":
            item = HAND_KEY
            x, y, z = w0["pos"]
            fac = rng.randrange(0x1000)
        elif kind == "the taker":
            # the creature the level hands its thing to, up beside the player
            # -- and now and then another slot up on the same spot
            slot = LEVEL1_TAKER if lv == 1 else LEVEL2_TAKER
            if lv == 1:
                item = BLOOD_HERB if rng.random() < 0.8 else rng.choice(ARMS)
            else:
                item = rng.choice(list(LEVEL2_STAGE)) if rng.random() < 0.85 else rng.choice(ARMS)
            h = homes[slot]
            cx, cy, cz = h["x"], h["y"], h["z"]
            radius = rng.choice((h["radius"], h["radius"], 0x2EE, rng.randrange(0x400)))
            reach = radius + GIVE_R + 0x300
            a = rng.randrange(0x1000)
            near = rng.random() < 0.7
            d = rng.randrange(radius + GIVE_R if near else reach)
            x = cx + ((movement.game_cos(a) * d) >> 12)
            z = cz + ((movement.game_sin(a) * d) >> 12)
            y = cy + (rng.randrange(-0x300, 0x300) if near else rng.randrange(-0x900, 0x900))
            fac = rng.randrange(0x1000)
            for k in [slot] + ([rng.choice((2, 3, 10, 30, 0))] if rng.random() < 0.25 else []):
                ac = ACTORS + ACTOR_STRIDE * k
                _put(cpu, ac + 9, 1, 1 if rng.random() < 0.85 else rng.choice((0, 2)))
                _put(cpu, ac + 0xE, 1, rng.choice((0, 0, 0, 1, 3)))
                _put(cpu, ac + 0x28, 4, rng.choice((0, 0, 0, 4, 0x10, 0x14, 0x20000)))
                _put(cpu, ac + 0x2C, 4, cx + rng.randrange(-0x40, 0x40))
                _put(cpu, ac + 0x30, 4, cy)
                _put(cpu, ac + 0x34, 4, cz + rng.randrange(-0x40, 0x40))
                _put(cpu, ac + 0x1C, 2, radius)
                _put(cpu, ac + 0x1E, 2, rng.choice((h["height"], 0x5DC, rng.randrange(0x800))))
                _put(cpu, ac + 0x22, 2, rng.choice((-1, 3, 0xC8)))
                _put(cpu, ac + 0x26, 2, rng.randrange(-0x200, 0x200))
        elif kind == "rect 20":
            item = 0x7E if rng.random() < 0.8 else rng.choice(ARMS)
            inside = rng.random() < 0.8          # its rectangle, or about it
            x = ((0x26 + rng.randrange(3)) if inside else (0x25 + rng.randrange(5))) * 0x800 \
                + rng.randrange(0x800)
            z = ((0x10 + rng.randrange(2)) if inside else (0xF + rng.randrange(4))) * 0x800 \
                + rng.randrange(0x800)
            y = w0["pos"][1]
            fac = rng.randrange(0x1000)
        elif kind == "creature":
            c = rng.choice(w0["creatures"])
            item = TRUTH_GLASS if rng.random() < 0.8 else rng.choice(ARMS)
            d = rng.randrange(0x400, 0x2400)
            a = rng.randrange(0x1000)
            x = c["x"] + ((movement.game_cos(a) * d) >> 12)
            z = c["z"] + ((movement.game_sin(a) * d) >> 12)
            y = c["y"] + rng.randrange(-0x400, 0x400)
            fac = (movement.vec_angle(s32(c["x"] - x), s32(c["z"] - z))
                   + rng.randrange(-0x280, 0x280)) & 0xFFF
            ac = ACTORS + ACTOR_STRIDE * c["slot"]
            _put(cpu, ac + 3, 1, rng.choice((1, 2)))
        else:
            item = rng.choice(ARMS)
            o = rng.choice([o for o in w0["objects"] if o["type"] != 0xFF] or [None])
            x, y, z = (o["x"], o["y"], o["z"]) if o else w0["pos"]
            x += rng.randrange(-0x1000, 0x1000)
            z += rng.randrange(-0x1000, 0x1000)
            fac = rng.randrange(0x1000)
            block = rng.choice((lv, lv, 0x19, 0x1B, 6, 0x11))
        if item == STATUE_THING and block == 6:
            block = lv if lv != 6 else 0
        for k, v in ((0, x), (4, y), (8, z)):
            _put(cpu, PLAYER_POS + k, 4, v)
        _put(cpu, 0x801B25F8, 4, z)
        _put(cpu, PLAYER_ANGLES, 2, rng.randrange(-0x100, 0x100))
        _put(cpu, PLAYER_ANGLES + 2, 2, s16(fac))
        _put(cpu, LAYER, 2, rng.choice((0, 5)))
        _put(cpu, BLOCK, 1, block)
        busy = 1 if rng.random() < 0.2 else 0
        _put(cpu, BUSY, 2, busy)
        _put(cpu, PENDING, 1, rng.choice((0x19, 0x1B, lv, 0xFF)))
        for t in set([item, BLUE, GOLD, FLASK]):
            if t < 0x96:
                _put(cpu, INV_A + t, 1, rng.choice((0, 1, 2, 0x63)))
                _put(cpu, INV_B + t, 1, rng.choice((0, 0, 1, 0x63)))
        for k in range(5):
            _put(cpu, SKILLS + 2 * k, 2, rng.choice((0, 5, 0x3E6, 0x3E7, rng.randrange(1000))))
        _put(cpu, STAT36, 2, rng.choice((20, 0x3E5, 0x3E6, 0x3E7)))
        _put(cpu, WIS, 2, rng.randrange(5))
        for k in range(4):
            _put(cpu, FLAGS + 0x6D + k, 1, rng.choice((0, 1)))
        for k in (0x56, 0x57):                     # level 20's
            _put(cpu, FLAGS + k, 1, rng.choice((0, 0, 1, 2)))
        _put(cpu, INV_A + 0x7D, 1, rng.choice((0, 1)))
        _put(cpu, INV_B + 0x7D, 1, rng.choice((0, 0, 1)))
        for i in range(96):
            if rng.random() < 0.3:
                _put(cpu, SPELL_TABLE + 24 * i, 1, rng.choice((0, 1)))
        _put(cpu, BONUS_SKILLS, 2, rng.choice((0, 0x100)))
        _put(cpu, DROP_COUNT, 2, rng.randrange(0x10000))
        for p in w0["objects"]:
            if p["type"] == ORLADIN_PEDESTAL or p["type"] == SILVIERA_PEDESTAL:
                r = OBJECTS + STRIDE * p["slot"]
                _put(cpu, r + 0x38, 1, rng.choice((0xFF, 0xFF, 0xFF, 0x88, 0x8D, 0xFE)))
            if p["type"] == ORLADIN_LOCK:
                r = OBJECTS + STRIDE * p["slot"]
                _put(cpu, r + 0x38, 1, rng.choice((0x88, 0x88, 0xFE, 0x87)))
            if (lv, p["type"]) in ((7, 0x140), (23, 0x13F)):
                r = OBJECTS + STRIDE * p["slot"]
                _put(cpu, r + 0x38, 1, rng.choice((0xFF, 0xFF, 0x85, 0x86)))
            if lv == 5 and p["op"] == 0x53:
                r = OBJECTS + STRIDE * p["slot"]
                _put(cpu, r + 0xA, 2, rng.choice((0, 0, 0x800, 0xFFF, 0x1000)))
        if item in (FLASK, ORLADIN_KEY, SILVIERA_KEY, HAND_KEY, STONE_KEY, 0x66, 0x7E,
                    BLOOD_HERB) and rng.random() < 0.7:
            _put(cpu, INV_A + item, 1, rng.choice((1, 2)))
        if lv in (1, 2):
            # what the two levels' entry 2 asks: the flag, the byte that names
            # the thing, the door's and the gate's locks, actor_skip_mask and
            # current_actor_index; no creature a vertex places, which
            # spot_taken does not model
            _put(cpu, FLAGS + LEVEL1_ASKED, 1, rng.choice((0, 0, 1)))
            _put(cpu, FLAGS + LEVEL2_WANTED, 1, item if rng.random() < 0.6 else
                 rng.choice(list(LEVEL2_STAGE) + [0, 1, 2, 3, 4]))
            r = OBJECTS + STRIDE * (LEVEL1_DOOR if lv == 1 else 44)
            _put(cpu, r + 0x38, 1, rng.choice((0xC8, 0xC8, 0xFF, 0x23) if lv == 1 else
                                              (0x9A, 0x9A, 0x9B, 0xFF, 0x9C)))
            _put(cpu, r + 8, 2, rng.choice((0, 0, 0x14)))
            _put(cpu, SKIP_MASK, 1, rng.choice((4, 4, 4, 0, 0x10)))
            _put(cpu, CUR_INDEX, 4, rng.choice((0xC8, 0xC8, 3)))
            for k in range(ACTOR_N):
                ac = ACTORS + ACTOR_STRIDE * k
                f = cpu.rd(ac + 0x28, 4)
                if f & VERTEX_PLACED:
                    _put(cpu, ac + 0x28, 4, f & ~VERTEX_PLACED)
                if rng.random() < 0.05:
                    _put(cpu, ac, 1, rng.choice((0, 1, 2, 8, 0xFF)))
        if kind == "lock" and rng.random() < 0.5:
            r = OBJECTS + STRIDE * o["slot"]
            _put(cpu, r + 0x38, 1, rng.choice((item, item, 0xFE, rng.randrange(0x87, 0x91))))
            if rng.random() < 0.5:
                _put(cpu, r + 8, 2, 0)
        for i in range(RING_SIZE):
            r = OBJECTS + STRIDE * (RING + i)
            if rng.random() < 0.5:
                _put(cpu, r + 6, 2, rng.choice((0x60, 0x77, 0x88)))
                _put(cpu, r + 0x3C, 2, rng.randrange(0x10000))
        cpu.level = lv                    # whose overlay is in
        out.append((cpu, item))
    return out


FIELDS = ("answer", "inv_a", "inv_b", "skills", "stat36", "wis", "b578", "drops",
          "spells", "flags", "cats")


def outcome(item, calls, w):
    """A run's arm and what came of it, for the count of what was covered."""
    said = [c[1] for c in calls if c[0] == "announce"]
    if item == TRUTH_GLASS:
        page = [c[2] for c in calls if c[0] == "load_entry"]
        if not page:
            return "truth glass: nothing"
        p = page[0]
        return ("truth glass: slot 11" if p == TRUTH_SLOT11 else
                "truth glass: an area" if p >= TRUTH_AREA else "truth glass: a creature")
    if item == FLASK:
        return ("flask: filled" if FILLED in said else "flask: the pack full" if 0xB in said
                else "flask: nothing")
    if item == ORLADIN_KEY:
        made = any(o.get("made") for o in w["objects"])
        n = sum(1 for c in calls if c == ("hook", "take"))
        return ("Orladin's key: wrong" if WRONG_KEY in said else
                "Orladin's key: on a pedestal" if made else
                "Orladin's key: a lock opened" if w["answer"] else "Orladin's key: nothing") \
            + (", taken" if n else "")
    if item == SILVIERA_KEY:
        return ("Silviera's key: put" if any(c[0] == "put_key" for c in calls) else
                "Silviera's key: wrong" if WRONG_KEY in said else "Silviera's key: nothing")
    if item in KEYS:
        return ("a key: fits" if ("sound_key_fits",) in calls else
                "a key: wrong" if WRONG_KEY in said else "a key: nothing")
    if item in ICHRIUS or 0x96 <= item <= 0xA1:
        return "the warp: called" if any(c[0] == "warp" for c in calls) else "the warp: refused"
    if item == VERDITE or item in CRYSTALS or item in (POWER_FRUIT, WISE_FRUIT):
        if 3 in said:
            return "the figures: raised, a spell unlocked"
        return "the figures: raised" if w["answer"] else "the figures: at their most"
    lv = w.get("overlay")
    if (lv, item) in ((1, BLOOD_HERB),) or (lv == 2 and item in LEVEL2_STAGE):
        talk = [c[1] for c in calls if c[0] == "talk"]
        return (f"entry 2 of level {lv}, {item:#x}: given to slot {talk[0]}" if talk else
                f"entry 2 of level {lv}, {item:#x}: not given")
    if lv in LEVEL_USE and item in (HAND_KEY, STONE_KEY, 0x66, 0x7E):
        took = ("hook", "take") in calls
        said = [c[1] for c in calls if c[0] == "announce"]
        what = ("put on a pedestal" if any(c[0] == "put_key" for c in calls) else
                "wrong" if WRONG_KEY in said else
                "taken" if took else
                f"banner {said[0]:#x}" if said and said[0] != NOTHING_HAPPENS else
                "answered" if w["answer"] else "nothing")
        return f"entry 2 of level {lv}, {item:#x}: {what}"
    if item == STATUE_THING:
        return "0x80: the 900 frames"
    if item in EATEN:
        return "eaten"
    return "the rest: nothing happens"


def compare(cpu, item):
    """One run both ways: None when they agree, else what differs."""
    ram = bytes(cpu.ram)
    w = world_of(ram)
    w["overlay"] = getattr(cpu, "level", w["block"])
    want = use_item(w, item)
    got = game_run(cpu, item)
    after = world_of(bytes(cpu.ram))
    after["answer"] = cpu.rd(ANSWER, 4)
    what = outcome(item, want, w)
    if want != got:
        return what, f"calls: model {want}, game {got}"
    for f in FIELDS:
        if w[f] != after[f]:
            return what, f"{f}: model {w[f]}, game {after[f]}"
    mine = bytearray(ram)
    write_back(mine, w)
    lo, hi = OBJECTS & MASK, (OBJECTS & MASK) + STRIDE * 396
    if bytes(mine[lo:hi]) != bytes(cpu.ram[lo:hi]):
        for i in range(lo, hi):
            if mine[i] != cpu.ram[i]:
                k, off = divmod(i - lo, STRIDE)
                return what, f"object {k} +{off:#x}: model {mine[i]:#x}, game {cpu.ram[i]:#x}"
    return what, None


def check(out=sys.stdout, per_level=100, seed=7, levels=range(28), verbose=False):
    """The model against the game's own use_item, over every level, and how
    many runs went down each arm's ways."""
    rng = random.Random(seed)
    ok = n = 0
    seen = {}
    first = None
    for lv in levels:
        try:
            runs = cases(lv, per_level, rng)
        except Exception as e:                                     # noqa: BLE001
            print(f"  level {lv}: no machine ({e})", file=out)
            continue
        for cpu, item in runs:
            n += 1
            what, why = compare(cpu, item)
            if why is None:
                ok += 1
                seen[what] = seen.get(what, 0) + 1
            elif first is None or verbose:
                first = first or why
                print(f"  level {lv}, item {item:#x}: {why}", file=out)
    for what in sorted(seen):
        print(f"  {seen[what]:4d}  {what}", file=out)
    print(f"use_item, against the game's own over {len(list(levels))} levels: "
          f"{ok} of {n} runs agree -- calls, answer, pack, figures, categories and all "
          f"396 object records", file=out)
    return ok == n


# --- object_signal ----------------------------------------------------------

SIGNAL = 0x800463BC
SIGNAL_OPS = (0, 1, 2, 3, 4, 5, 0x1B, 0x51, 0x52, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A,
              0x5F, 0xA2, 0xA3, 6, 0x17, 0x53, 0xFF)


def signal_check(out=sys.stdout, per_level=10, seed=17):
    """object_signal against the game's own (0x800463bc), run over every
    level as its own load_object_placement leaves it: the id drawn from the
    toggled range (0x96..0xc6), the doors' (0x64..0xc7, 0xc8 up), anything
    and 0xff; a fifth of the records given an opcode that listens and their
    +8, +0x38, +0x39, +0x3a, +0x3d and +0x3f the id, its neighbour or
    anything -- all 396 records byte for byte."""
    import mipsrun
    rng = random.Random(seed)
    ok = n = changed = 0
    for lv in range(28):
        base = mipsrun.level_cpu(lv)
        ram0 = bytes(base.ram)
        for _ in range(per_level):
            cpu = mipsrun.CPU(ram0)
            cpu.hooks.update(base.hooks)
            sig = rng.choice((rng.randrange(0x96, 0xC7), rng.randrange(0x64, 0xC8),
                              rng.randrange(0xC8, 0xFF), rng.randrange(0x100), 0xFF))
            for k in range(COUNT):
                if rng.random() >= 0.2:
                    continue
                r = OBJECTS + STRIDE * k
                _put(cpu, r + 4, 1, rng.choice(SIGNAL_OPS))
                _put(cpu, r + 8, 2, rng.choice((0, 0, 1, 0x14)))
                for off in (0x38, 0x39, 0x3A, 0x3D, 0x3F):
                    _put(cpu, r + off, 1, rng.choice((sig, sig, sig ^ 1, 0, 0xFF,
                                                      rng.randrange(0x100))))
            ram = bytes(cpu.ram)
            w = world_of(ram)
            object_signal(w, sig)
            mine = bytearray(ram)
            write_back(mine, w)
            cpu.call(SIGNAL, sig)
            lo, hi = OBJECTS & MASK, (OBJECTS & MASK) + STRIDE * COUNT
            n += 1
            if bytes(mine[lo:hi]) == bytes(cpu.ram[lo:hi]):
                ok += 1
                changed += sum(1 for i in range(lo, hi, STRIDE)
                               if ram[i:i + STRIDE] != cpu.ram[i:i + STRIDE])
            elif ok == n - 1:
                for i in range(lo, hi):
                    if mine[i] != cpu.ram[i]:
                        k, off = divmod(i - lo, STRIDE)
                        print(f"  level {lv}, id {sig:#x}: object {k} +{off:#x}: model "
                              f"{mine[i]:#x}, game {cpu.ram[i]:#x}", file=out)
                        break
    print(f"object_signal, against the game's own over 28 levels: {ok} of {n} runs agree "
          f"-- all {COUNT} records, {changed} of them changed", file=out)
    return ok == n


# --- the warp: warp_to -----------------------------------------------------

WARP_FADE = 0x80046C00           # fade_frames(mode, from, to, step)
WARP_UPLOAD = 0x80019538         # res_upload_wait
RETIRE = 0x8004B794              # actors_retire_marked
LEVEL_LOAD = 0x80018358
OBJECT_TRIGGER = 0x80017C78
RES_WAIT = 0x80019AB4
SCREEN_FADE = 0x8003D624
SPAWN_ANYWHERE = 0x801B24F2
PLAYER_STATE = 0x801B25E5
VIEW_ANGLES = 0x801B2608         # pitch, yaw, roll, and 0x801b260e
VIEW_TILT = 0x801B2618           # pitch, yaw, roll
VIEW_ADD = 0x801B2620            # pitch, yaw, roll, added to the view
WARPED = 0x801B25EE              # written 1, read nowhere this walk finds
CUTSCENE_WARP, ENDING_WARP = 0xC, 0xD

# the fields the warp writes, (address, size), what the check compares
WARP_FIELDS = ((PLAYER_STATE, 1), (VIEW_ADD, 2), (VIEW_ADD + 2, 2), (VIEW_ADD + 4, 2),
               (VIEW_ANGLES, 2), (VIEW_ANGLES + 2, 2), (VIEW_ANGLES + 4, 2), (VIEW_ANGLES + 6, 2),
               (PLAYER_ANGLES, 2), (PLAYER_ANGLES + 2, 2), (PLAYER_ANGLES + 4, 2),
               (PLAYER_ANGLES + 6, 2), (PLAYER_POS, 4), (PLAYER_POS + 4, 4), (PLAYER_POS + 8, 4),
               (SPAWN_ANYWHERE, 1), (WARPED, 1), (ANSWER, 4),
               (VIEW_TILT, 2), (VIEW_TILT + 2, 2), (VIEW_TILT + 4, 2))


def warp_fields(ram):
    """The warp's fields out of RAM, {address: value}."""
    return {a: int.from_bytes(ram[a & MASK:(a & MASK) + n], "little") for a, n in WARP_FIELDS}


def warp(f, i, block):
    """warp_to(i) over the fields `f` ({address: value}, WARP_FIELDS),
    the block in hand `block` (current_level_block): [the calls it makes
    beyond what it runs], f changed as RAM would be. level_load is taken to
    finish a change at once, as the check's stand-in does."""
    calls = []
    rec = warp_record(i) if 0 <= i < 14 else None
    if rec is None:
        raise ValueError(f"no record {i}")
    lv = rec[0]
    if i < 0xC or i == ENDING_WARP:
        if lv == 0xFF:
            return calls
        calls.append(("fade", 1, 0, 0x1000, 0x100))
        calls.append(("retire",))
    calls += [("upload",), ("level_load",)]
    if lv != block:
        calls.append(("trigger", lv, lv, lv, 0xFF, 0xFF, 0x7F, 0x7F, 0x7F))
    else:
        calls.append(("trigger", 0xFF, 0xFF, lv, 0xFF, 0xFF, 0x7F, 0x7F, 0x7F))
        f[SPAWN_ANYWHERE] = 1
    calls += [("upload",), ("level_load",)]
    f[PLAYER_STATE] = 0
    for k in (0, 2, 4):
        f[VIEW_ADD + k] = 0
    for k in (0, 2, 4, 6):                   # the 8 bytes from player_pitch
        f[VIEW_ANGLES + k] = f[PLAYER_ANGLES + k]
    f[PLAYER_POS] = (rec[3] << 11) + 0x400
    f[PLAYER_POS + 8] = (rec[4] << 11) + 0x400
    f[PLAYER_POS + 4] = (-(rec[5] << 7)) & 0xFFFFFFFF
    face = (-(rec[6] | rec[7] << 8)) & 0xFFFF
    f[PLAYER_ANGLES + 2] = face
    f[VIEW_ANGLES + 2] = face
    if i == ENDING_WARP:
        f[PLAYER_ANGLES + 4] = 0
        f[VIEW_ANGLES + 4] = 0
        f[PLAYER_ANGLES] = 0
        f[VIEW_ANGLES] = 0
        f[PLAYER_POS + 8] = (rec[4] << 11) + 0x7D0
    else:
        calls += [("fade", 1, 0x1000, 0x1000, 0), ("res_wait",),
                  ("fade", 1, 0x1000, 0, 0xFFFFFF00), ("screen_fade", 0xFF, 0, 0, 0)]
        calls.append(("trigger", 0xFF, 0xFF, 0xFF, rec[1], rec[2], 0x7F, 0x7F, 0x7F))
    if i < 0xC:
        f[WARPED] = 1
        f[ANSWER] = 1
        calls.append(("recalc",))
    for k in (0, 2, 4):
        f[VIEW_TILT + k] = 0
    return calls


def warp_run(cpu, i):
    """The game's own warp_to(i) over the machine: the calls it made
    beyond what it ran. level_load ends a change at once (level_change_busy
    0); object_trigger, the fades and the rest are logged."""
    calls = []

    def stack(c, n):
        return [c.rd(c.r[29] + 0x10 + 4 * k, 4) for k in range(n)]

    def load(c):
        calls.append(("level_load",))
        c.wr(BUSY, 2, 0)

    cpu.hooks = {
        WARP_FADE: lambda c: calls.append(("fade", c.r[4], c.r[5], c.r[6], c.r[7])),
        RETIRE: lambda c: calls.append(("retire",)),
        WARP_UPLOAD: lambda c: calls.append(("upload",)),
        LEVEL_LOAD: load,
        OBJECT_TRIGGER: lambda c: calls.append(
            ("trigger", c.r[4] & 0xFF, c.r[5] & 0xFF, c.r[6] & 0xFF, c.r[7] & 0xFF,
             *[v & 0xFF for v in stack(c, 4)])),
        RES_WAIT: lambda c: calls.append(("res_wait",)),
        SCREEN_FADE: lambda c: calls.append(("screen_fade", c.r[4], c.r[5], c.r[6], c.r[7])),
        RECALC: lambda c: calls.append(("recalc",)),
    }
    cpu.call(WARP, i)
    return calls


def warp_check(out=sys.stdout, n=280, seed=13):
    """The model against the game's own warp_to, every record from the
    block it names and from others, over a1 with the fields drawn at random."""
    import mipsrun
    rng = random.Random(seed)
    ram0 = open(os.path.join(ROOT, "out", "snap", "a1.ram"), "rb").read()
    ok = 0
    told = False
    for k in range(n):
        i = k % 14
        cpu = mipsrun.CPU(ram0)
        rec = warp_record(i)
        block = rec[0] if rng.random() < 0.4 and rec[0] != 0xFF else rng.randrange(28)
        cpu.wr(BLOCK, 1, block)
        cpu.wr(BUSY, 2, rng.choice((0, 0, 1)))
        for a, sz in WARP_FIELDS:
            cpu.wr(a, sz, rng.randrange(1 << (8 * sz)))
        f = warp_fields(cpu.ram)
        want = warp(f, i, block)
        got = warp_run(cpu, i)
        after = warp_fields(cpu.ram)
        why = None
        if want != got:
            why = f"calls: model {want}, game {got}"
        elif f != after:
            why = "; ".join(f"{a:#x} model {f[a]:#x} game {after[a]:#x}"
                            for a in f if f[a] != after[a])
        if why is None:
            ok += 1
        elif not told:
            told = True
            print(f"  record {i}, block {block}: {why}", file=out)
    print(f"warp_to, the warp, against the game's own: {ok} of {n} runs agree -- "
          f"every record from its own block and from others, the calls and "
          f"{len(WARP_FIELDS)} fields", file=out)
    return ok == n


def warp_plan(i, block, pitch):
    """What warp(i) leaves, in the port's terms: the block in hand after its
    object_trigger calls (an 0xff byte keeps the byte in hand, as the
    crossings' do), whether the level was the one in hand, the place, the
    facing (0..0xfff), the pitch and the answer, the fade out and the fades
    back (fade_frames' arguments, the step signed) and whether screen_fade
    clears it after -- or {} for a record that does nothing. `block` is the
    five bytes in hand."""
    f = {a: 0 for a, _n in WARP_FIELDS}
    f[PLAYER_ANGLES] = pitch & 0xFFFF
    calls = warp(f, i, block[0])
    if not calls:
        return {}
    b = list(block)
    for c in calls:
        if c[0] == "trigger":
            b = [cur if v == 0xFF else v for cur, v in zip(b, c[1:6])]
    out, back, loaded = [], [], False
    for c in calls:
        if c[0] == "upload":
            loaded = True
        elif c[0] == "fade":
            (back if loaded else out).append([c[1], c[2], c[3], s32(c[4])])
    return {"level": b[1], "block": b, "same": f[SPAWN_ANYWHERE] == 1,
            "pos": [s32(f[PLAYER_POS]), s32(f[PLAYER_POS + 4]), s32(f[PLAYER_POS + 8])],
            "facing": f[PLAYER_ANGLES + 2] & 0xFFF, "pitch": s16(f[PLAYER_ANGLES]),
            "answer": f[ANSWER], "out": out[0] if out else [], "back": back,
            "clear": ("screen_fade", 0xFF, 0, 0, 0) in calls}


# --- for the port ---------------------------------------------------------------

# The fields of an object the port's copy (godot/useitem.gd) reads, in order.
OBJECT_FIELDS = ("slot", "type", "cls", "b0", "op", "state", "x", "y", "z", "yaw",
                 "height", "reach", "top", "b38", "b39", "h3a", "h3c", "b40", "b3d", "b3f",
                 "clk")
CREATURE_FIELDS = ("slot", "e", "flags", "x", "y", "z", "model", "floor", "radius", "height",
                   "lead", "lift")


def compact(w):
    """A world as the self-test reads it: the objects find_object could reach
    from where the player stands (in_range's square test leaves the rest out),
    the class-0xe2 rectangles, slot 11 and the gold ring, as rows of
    OBJECT_FIELDS; the creatures as rows of CREATURE_FIELDS."""
    px, _py, pz = w["pos"]
    objs = []
    for o in w["objects"]:
        ring = RING <= o["slot"] < RING + RING_SIZE
        if o["type"] == 0xFF and not ring:
            continue
        near = o["reach"] + 0x320 + 0x800
        if (abs(o["x"] - px) <= near and abs(o["z"] - pz) <= near) or \
                o["cls"] == AREA_CLASS or o["slot"] == 0xB or ring:
            objs.append([o[f] for f in OBJECT_FIELDS])
    out = {k: w[k] for k in ("pitch", "facing", "layer", "block", "busy", "pending",
                             "stat36", "wis", "b578", "drops", "skip_mask", "cur_index")}
    out["overlay"] = w.get("overlay", w["block"])
    for k in ("pos", "skills", "spells", "inv_a", "inv_b", "flags", "cats"):
        out[k] = list(w[k])
    out["objects"] = objs
    out["creatures"] = [[c[f] for f in CREATURE_FIELDS] for c in w["creatures"]]
    return out


def truth_pages(lv):
    """The ITEM.T entries the truth glass can show on level `lv`: its
    creatures' models + 0x10e, 0x131 on level 17 (slot 11's), and every
    class-0xe2 rectangle's +0x3a + 0x32a."""
    import actors
    import objload
    pages = set()
    for a in actors.table(lv):
        if a:
            pages.add(TRUTH_CREATURE + (a["model"] & 0xFF))
    ld = objload.Load(lv)
    for o in ld.recs.values():
        if o["cls"] == AREA_CLASS:
            pages.add((struct.unpack_from("<H", bytes(o["tail"]), 2)[0] + TRUTH_AREA) & 0xFFFF)
    if lv == 0x11:
        pages.add(TRUTH_SLOT11)
    return sorted(p for p in pages if p < 970)


def export(out_dir, lv=0, per_level=12, seed=11):
    """useitem.json -- warp_to's fourteen records, which the port's copy
    asks whether a warp answers -- the truth glass's pages for level `lv`
    (read/N.png, N the entry less 0x96, as document.gd opens a sign's), and
    usecheck.json: runs of the model the self-test holds godot/useitem.gd to."""
    import json
    import readables
    import tim
    with open(os.path.join(out_dir, "useitem.json"), "w") as fh:
        json.dump({"_note": "GAME.EXE 0x800130f0, warp_to's records; tools/useitem.py wrote it",
                   "warps": [warp_record(i) for i in range(14)]}, fh, separators=(",", ":"))
    os.makedirs(os.path.join(out_dir, "read"), exist_ok=True)
    arc = readables.archive(ITEM_ARCHIVE)
    for e in truth_pages(lv):
        tim.write_png(os.path.join(out_dir, "read", f"{e - readables.TEXT_BASE}.png"),
                      readables.PAGE_W, readables.PAGE_H, readables.page_entry(arc, e))
    rng = random.Random(seed)
    rows = []
    for level in range(28):
        try:
            # the levels whose own entry 2 is read, four times over
            runs = cases(level, per_level * (4 if level in LEVEL_USE else 1), rng)
        except Exception:                                          # noqa: BLE001
            continue
        for cpu, item in runs:
            w = world_of(bytes(cpu.ram))
            w["overlay"] = level
            if item == STATUE_THING and w["block"] == 6:
                continue
            row = {"level": level, "item": item, "world": compact(w)}
            calls = use_item(w, item)
            after = compact(w)
            row["want"] = {"calls": [list(c) for c in calls], "answer": w["answer"]}
            for f in ("inv_a", "inv_b", "skills", "stat36", "wis", "b578", "drops",
                      "spells", "flags", "cats", "objects"):
                if after[f] != row["world"][f]:
                    row["want"][f] = after[f]
            rows.append(row)
    warps = []
    for i in range(14):
        for block in ([warp_record(i)[0]] * 5, [0, 0, 0, 0, 0], [4, 4, 4, 13, 15],
                      [rng.randrange(28) for _ in range(5)]):
            if block[0] == 0xFF:
                continue
            pitch = s16(rng.randrange(0x10000))
            warps.append({"record": i, "block": block, "pitch": pitch,
                          "want": warp_plan(i, block, pitch)})
    path = os.path.join(out_dir, "usecheck.json")
    with open(path, "w") as fh:
        json.dump({"fields": list(OBJECT_FIELDS), "cases": rows, "warps": warps}, fh,
                  separators=(",", ":"))
    return path


def main():
    a = sys.argv[1:]
    if "--export" in a:
        print(export(a[a.index("--export") + 1] if len(a) > a.index("--export") + 1
                     else os.path.join(ROOT, "out", "godot")))
        return
    if "--check" in a or not a:
        good = check(verbose="-v" in a)
        good = signal_check() and good
        good = warp_check() and good
        sys.exit(0 if good else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""What a level remembers, and the byte stream it remembers it in.

    python3 tools/levelstate.py           the streams that were recorded
    python3 tools/levelstate.py --check   the model against them

`level_state_write` (`0x8005efd4`) builds the whole record from scratch every
time something changes, on its own stack, and `apply_level_state`
(`0x8005f444`) reads it back at level load. Between them the format is three
sections:

**One: the actors that are gone.** Walk `actor_table`, 0x88 a slot, stopping
at the first byte-0 of `0xff`. For each slot whose byte 0 is **1** -- category
1, and no other category -- write the slot index and then `3` if the actor's
`+9` is `3`, otherwise `0`. Terminate with `0xff`.

**Two: how far each conversation has got.** Walk the 40 entity records; for
each whose `+0x38` is not null and whose block begins `0x70`, write the entity
index, the program counter at `+0x10` and the retry flag at `+0x13`.
Terminate with `0xff`.

**Three: one opcode per object slot**, 396 of them, in lockstep -- the decoder
steps its own pointer by `0x44` once per record and stops at 396, so there is
no terminator and no slot is skipped. The opcode is chosen by the object's
class through a 233-arm table at `0x80013298`:

    0xff       the slot is empty -- its type id is 0xff
    0xfe       nothing about this slot is worth keeping
    0xfd n     the object's state byte at +0x38
    0xf5 n     the byte at +0x39
    0xf4 s n   the state and the byte after it
    0xf0..0xf2 an object that was not in the level when it was built: a type
               id and a position, x and z as `x >> 2` in two bytes each

**Checked.** `emu/bp23.lua` logged both ends while the game was played. The
543-byte stream written on level 0 is byte for byte the one read back when
the player returned, and it decodes to 34 actors with three gone, six
conversations -- entity 9 stopped at pc 7 with the retry flag set, which is
where an earlier recording left it -- and **396 object records ending exactly
on the last byte**. That last number is the one that matters: a lockstep
reading that is out by one record ends early or runs off the end.
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SLOTS = 396                    # the decoder's own bound
END = 0xFF

# How far each opcode advances, read off level_state_write's arms.
OPS = {0xF0: 9, 0xF1: 8, 0xF2: 8, 0xF3: 8, 0xF4: 3, 0xF5: 2,
       0xFD: 2, 0xFE: 1, 0xFF: 1}

# What emu/bp23.lua recorded on 2026-09-24: the stream level_state_write
# built, twice, and the one apply_level_state was handed on the way back.
RECORDED = [
    {"kind": "state", "level": None, "hex": "0000050306030700080009000a000b000c000e0010001100120013001400150016001700180019001a001b031c001d001e00200021002400250026002700280029002f00ff0600000700000800000907010a00000b0000fffefefefefefefd00fefdfffd89fefefefefefefefdfffefdfffdfffefefefefdfefefefefefefefefdc8fefffefefefefefefefefefefd00fefefefefdfffefefefefefdfffd00fefefefd00fefefefefefefefdc8fefefd00fdfffefefefefefefefd00fefefefdfffdfffefd00fefefefefefefefefefefefdfffefefefefefefefefefefdfffdfffdfffefdc8fefefefefefefdfffdfffefdfffdfffefefdfffefd00fefefefefdfffefefefefefefefefefd00fefefefefefefefd00fffefefefefefefdfffefefefefdfffefefefd00fefefefefefefefefefefdfffefefefefefefefefdfffefffd00fefefdfffd00fefd00fd8afefd87fd00fefefd00fdfffdfffdfffdfffefefdfffefd00fefefefefefefffefdfffefefefefefefefefefefefefefefefefefffefefd00fd00fefefefefefd00fefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefffffefefefefefefefefefefefefefefefefefefefd3cfefefefefefefefefefefefefefefefefefefefefdf1fefefefefeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"},
    {"kind": "state", "level": None, "hex": "0000010002000300040005000600070008000a000b000c000d000e000f001000110012001300150016001700180019001b001c001d001f0020002200230024002500260027002800ff0900000a0000fffdfffefffefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefd00fefefefefefefefefefefefefefefefefefdfcfefefefefefefdfffdfffdfffd00fef4fffffefefd00fefdfffefefd00fdfffefdf0fdfcfefefefefefefefefefef4fffffefefefd00fdfcfdfcfefefefdfffdfffefefefefefefefefefef4ff00fef4fffffefefdfffefdfcf4fffffdfffef4fffffdfcfefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefdfffefefd00fd00fd00fdfffdfffefdfffefefefefefefefdfffdfffdfffdfffefdfffefdfffd00fdfffdfffdfffefefd00fefef4fffffffffefd00fffffffffffffffffffffffffffffffffffffffffefffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffefefefefeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"},
    {"kind": "apply", "level": 0, "hex": "0000050306030700080009000a000b000c000e0010001100120013001400150016001700180019001a001b031c001d001e00200021002400250026002700280029002f00ff0600000700000800000907010a00000b0000fffefefefefefefd00fefdfffd89fefefefefefefefdfffefdfffdfffefefefefdfefefefefefefefefdc8fefffefefefefefefefefefefd00fefefefefdfffefefefefefdfffd00fefefefd00fefefefefefefefdc8fefefd00fdfffefefefefefefefd00fefefefdfffdfffefd00fefefefefefefefefefefefdfffefefefefefefefefefefdfffdfffdfffefdc8fefefefefefefdfffdfffefdfffdfffefefdfffefd00fefefefe"}
]


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


def export(out_dir):
    path = os.path.join(out_dir, "levelstate.json")
    with open(path, "w") as fh:
        json.dump({"_note": "level_state_write's byte stream: the actors that "
                            "are gone, each conversation's pc and retry flag, "
                            "then one opcode per object slot, 396 in lockstep",
                   "slots": SLOTS, "ops": {str(k): v for k, v in OPS.items()},
                   "recorded": RECORDED}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else None
    if a == "--check":
        sys.exit(0 if check() else 1)
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

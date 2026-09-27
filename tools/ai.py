#!/usr/bin/env python3
"""What a creature does: its kind's behaviours, and the machine that runs them.

    python3 tools/ai.py 0            a level's kinds and their behaviours
    python3 tools/ai.py --check      the tables against every snapshot's RAM

## Where the behaviours are

`FDAT.T` entry `3n + 1`, link 0, is `block_copy`'d to `entity_table`
(`0x8018c7e8`): forty 120-byte records -- a creature's **kind** -- and after
them, at `entity_scripts` (`0x8018daa8`), the kinds' behaviour records. A kind
lists up to sixteen behaviours at +0x38, as offsets into that area on the disc
with 0xffffffff for none; `entity_table_init` (`0x80053084`) walks the kinds in
order to the first whose +0 is 0xff and turns each offset into an address and
each 0xffffffff into 0. Kinds past that one keep their raw words.

A behaviour record opens with its **opcode** -- which arm of `actor_tick`
(`0x800500a8`) runs it -- then the animation it starts (+1), a base score
(+2), a sound (+4), the rate its animation clock runs at (+8) and the
opcode's own parameters. Level 0's two monster kinds, models 50 and 51, list
the same seven: 6, 0, 5, 1, 4, 2, 3.

## How one is chosen

An awake actor (+9 == 1) carries the running behaviour at +0x60, its opcode at
+0xe and a phase at +0xf: 0 just switched in, 0xf0 running, 0xff finished.
`actor_tick_driver` runs `actor_choose` (`0x8004c01c`) on the frames where
`frame & 3 == slot & 3`, and `actor_tick` runs it again when a behaviour ends
(`0x8004c104`). It measures the distance to the player and hands it to
`actor_pick` (`0x8004bf1c`), which -- unless the phase is 0xf0 or 0 -- scores
every behaviour of the kind with `actor_behaviour` (`0x8004b984`, a 133-arm
switch on the opcode), keeps the best above -2, and switches to it with
`actor_switch` (`0x8004b94c`) if it is another one, or the running one has
finished: +0x10 = the old opcode, +0x60 = the record, +0xe = its opcode,
+0xf = 0.

The animation clock is +0x18, 0 to 0xfff: `actor_clock` (`0x8004db3c`) adds
the record's rate (+8) and keeps its size at +0x66, and `actor_clock_passed`
(`0x8004db98`) asks whether a given time was crossed in this frame's step.
`actor_start_anim` (`0x8004c130`) puts the animation at +0xc and the clock
at 0.
"""
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ENTITY_TABLE = 0x8018C7E8
ENTITY_SCRIPTS = 0x8018DAA8
ENTITY, KINDS, SLOTS_PER_KIND = 120, 40, 16
LISTS = 0x38
ACTOR_TABLE, ACTOR_STRIDE, ACTORS = 0x80185DA8, 0x88, 200


def entity_blob(lv):
    """link 0 of the level, as entity_table_init leaves it in RAM."""
    import actors
    raw, ch = actors.links(lv)
    off, n = ch[0]
    blob = bytearray(raw[off:off + n])
    for k in range(KINDS):
        if blob[k * ENTITY] == 0xFF:
            break
        for i in range(SLOTS_PER_KIND):
            o = k * ENTITY + LISTS + 4 * i
            v = struct.unpack_from("<I", blob, o)[0]
            struct.pack_into("<I", blob, o, 0 if v == 0xFFFFFFFF else ENTITY_SCRIPTS + v)
    return blob


def kinds(lv, blob=None):
    """[kind] -- each {'kind', 'model', 'behaviours': [record]} for the used kinds.

    A record is {'addr', 'op', 'anim', 'score', 'raw'}: its bytes run to the next
    record the level holds.
    """
    blob = blob or entity_blob(lv)
    addrs = set()
    out = []
    for k in range(KINDS):
        e = blob[k * ENTITY:(k + 1) * ENTITY]
        if e[0] == 0xFF:
            break
        ptrs = [p for p in struct.unpack_from("<16I", e, LISTS) if p]
        addrs.update(ptrs)
        out.append({"kind": k, "model": struct.unpack_from("<H", e, 0)[0] - 0x400,
                    "ptrs": ptrs})
    order = sorted(addrs) + [ENTITY_TABLE + len(blob)]
    nxt = {a: b for a, b in zip(order, order[1:])}
    for kd in out:
        kd["behaviours"] = []
        for p in kd["ptrs"]:
            o = p - ENTITY_TABLE
            raw = bytes(blob[o:nxt[p] - ENTITY_TABLE])
            kd["behaviours"].append({"addr": p, "op": raw[0], "anim": raw[1],
                                     "score": raw[2], "raw": raw})
    return out


def check(out=sys.stdout):
    """The relocated table byte for byte, and every awake actor's behaviour."""
    same = total = awake = ok = snaps = 0
    blobs = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        r = open(path, "rb").read()
        lv = r[0x18FAD9]
        if struct.unpack_from("<I", r, (ENTITY_TABLE & 0x1FFFFF) + LISTS)[0] == 0:
            continue                             # no level ever loaded
        snaps += 1
        if lv not in blobs:
            blobs[lv] = entity_blob(lv)
        blob = blobs[lv]
        base = ENTITY_TABLE & 0x1FFFFF
        live = r[base:base + len(blob)]
        # the kinds' own records and the behaviour area: the table as loaded
        same += sum(a == b for a, b in zip(blob, live))
        total += len(blob)
        ks = {kd["kind"]: kd for kd in kinds(lv, blob)}
        for s in range(ACTORS):
            a = r[(ACTOR_TABLE & 0x1FFFFF) + s * ACTOR_STRIDE:][:ACTOR_STRIDE]
            if a[0] == 0xFF or a[9] != 1:
                continue
            awake += 1
            p60 = struct.unpack_from("<I", a, 0x60)[0]
            kd = ks.get(a[2])
            recs = {b["addr"]: b for b in kd["behaviours"]} if kd else {}
            if p60 in recs and recs[p60]["op"] == a[0xE]:
                ok += 1
            else:
                print(f"  {os.path.basename(path)} actor {s}: +0x60 {p60:#x} "
                      f"op {a[0xE]:#x}", file=out)
    print(f"  {same} of {total} bytes of the kinds and their behaviours as "
          f"entity_table_init leaves them, over {snaps} snapshots; {ok} of "
          f"{awake} awake actors run one of their kind's behaviours, its "
          f"opcode at +0xe", file=out)
    return ok == awake and snaps > 0


def main():
    a = sys.argv[1] if len(sys.argv) > 1 else "0"
    if a == "--check":
        sys.exit(0 if check() else 1)
    lv = int(a)
    for kd in kinds(lv):
        print(f"kind {kd['kind']:2d} model {kd['model']:3d}: " + ", ".join(
            f"{b['op']:#x}" for b in kd["behaviours"]))
    check()


if __name__ == "__main__":
    main()

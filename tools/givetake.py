#!/usr/bin/env python3
"""A thing into the pack and out of it: give_item and take_item whole, with every level's entries 6 and 11.

    python3 tools/givetake.py            what each level's entry 6 does
    python3 tools/givetake.py --check    the model against the game's own
                                         give_item and take_item, and the
                                         overlays' own entries 6 and 11
    python3 tools/givetake.py --export D givetakecheck.json for the self-test

**`give_item(id)`** (`0x8005d898`) puts one more of `id` into the first of
the two arrays (`inventory_a`, `inventory_b`) that holds fewer than 99 and
then calls the level's own **entry 6** (`level_hooks + 0x18`), answering 0;
with both at 99 it says banner `0xb` and answers 1, and no hook runs.
**`take_item(id)`** (`0x8005d7f8`) takes one from the first that has one and
calls the level's **entry 11** (`level_hooks + 0x2c`), answering 0; with
none, 1. So whatever puts a thing in the pack -- a chest's lid, a thing
handed over in a conversation, the flask filled, the excellector grown --
runs the level's entry 6 after.

Entry 11 is `jr $ra` on all 28 levels. Entry 6 is too, but on three:

```
level 0   the excellector as found (0), Ichrius' key (0x85) and Leon's note
          (0x64) all held: story flag 7 = 1 -- the last of the three men by
          the house (entry 5's chain 0x1e, 2, 6, 7: all held, the objects
          that stand for them gone; entry 3's clock waits on it being 0)
level 2   the aquarian boots (0x4b) held: story flag 0x11 = 1
level 6   Ichrius' wings (0x83) held: story flag 0x24 = 1 -- which the
          conversation's arm 3 also sets as it hands the wings over, and
          level 9's entry 5 reads (0x24 and 0x27 make 0x32)
```

Whatever the thing given was: the hook asks the pack, not the id. So on
level 0 the flag is set by the last of the three to arrive, or by anything
given after, and never once the excellector has grown past its first form
(0 is taken for 1, `excellector_grow`).

**How it is held to the game.** `check()` runs GAME.EXE's own give_item and
take_item with `tools/mipsrun.py` over every level as its own loader leaves
it -- the level's overlay in, so the jalr reaches its own entries 6 and 11,
and those call the game's has_item -- with the thing, both arrays' counts of
it and of the five things the hooks ask (0, 99 and between), and the three
flags drawn at random, announce logged: the model must answer the same, make
the same calls and leave the same RAM, all of it but the stack.
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levelin                                                       # noqa: E402
from levelin import F, INV_A, INV_B, MASK, Mem                       # noqa: E402

GIVE_ITEM, TAKE_ITEM = 0x8005D898, 0x8005D7F8
ANNOUNCE = 0x80041EEC
CAP = 0x63                         # 99 in either array
GIVE, TAKE = 6, 11                 # level_hooks + 0x18, + 0x2c
FULL = 0xB                         # give_item's banner, both arrays at 99
# what the levels' entry 6 asks of the pack, and the flags it sets
ASKED = (0, 0x85, 0x64, 0x4B, 0x83)
SET = (7, 0x11, 0x24)


def entry6(lv, m):
    """Level `lv`'s entry 6 over the RAM `m`: a story flag by what is held."""
    if lv == 0:
        # the excellector as found, Ichrius' key, Leon's note
        if m.has(0) > 0 and m.has(0x85) > 0 and m.has(0x64) > 0:
            m.wr(F(7), 1)
    elif lv == 2:
        if m.has(0x4B) > 0:                    # the aquarian boots
            m.wr(F(0x11), 1)
    elif lv == 6:
        if m.has(0x83) > 0:                    # Ichrius' wings
            m.wr(F(0x24), 1)


def entry11(lv, m):
    """Level `lv`'s entry 11: `jr $ra` on every level."""


def give_item(lv, m, item):
    """give_item (0x8005d898): one more in the first array under 99 and the
    level's entry 6, 0; both full, banner 0xb and 1."""
    for base in (INV_A, INV_B):
        if m.rd(base + item) < CAP:
            m.wr(base + item, m.rd(base + item) + 1)
            entry6(lv, m)
            return 0
    m.calls.append(("announce", FULL))
    return 1


def take_item(lv, m, item):
    """take_item (0x8005d7f8): one from the first array that has one and the
    level's entry 11, 0; none, 1."""
    for base in (INV_A, INV_B):
        if m.rd(base + item):
            m.wr(base + item, m.rd(base + item) - 1)
            entry11(lv, m)
            return 0
    return 1


# --- against the game's own ---------------------------------------------------

def game_run(cpu, op, item):
    """GAME.EXE's own give_item or take_item over the machine's RAM, the
    level's entries out of its overlay: (its answer, [the calls it made that
    the model logs])."""
    calls = []
    cpu.hooks = dict(cpu.hooks)
    cpu.hooks[ANNOUNCE] = lambda c: calls.append(("announce", c.r[4]))
    v = cpu.call(GIVE_ITEM if op == "give" else TAKE_ITEM, item)
    return v, calls


def cases(lv, n, rng, snap="a1"):
    """`n` runs on level `lv`: [(the machine, "give" | "take", the thing)]."""
    import mipsrun
    import useitem
    base = mipsrun.level_cpu(lv, snap)
    ram0 = bytes(base.ram)
    put = useitem._put
    count = lambda: rng.choice((0, 0, 1, 2, CAP - 1, CAP, CAP, rng.randrange(0x100)))   # noqa: E731
    out = []
    for _ in range(n):
        cpu = mipsrun.CPU(ram0)
        cpu.hooks.update(base.hooks)
        item = rng.choice(ASKED + (1, 2, rng.randrange(0x96)))
        for t in set(ASKED + (item,)):
            put(cpu, INV_A + t, 1, count())
            put(cpu, INV_B + t, 1, count())
        for k in SET:
            put(cpu, F(k), 1, rng.choice((0, 0, 1, 2, rng.randrange(0x100))))
        out.append((cpu, rng.choice(("give", "take")), item))
    return out


STACK_LO, STACK_HI = levelin.STACK_LO, levelin.STACK_HI


def compare(cpu, lv, op, item):
    """One run both ways: (what it did, None) when they agree, else what differs."""
    m = Mem(bytes(cpu.ram))
    want = (give_item if op == "give" else take_item)(lv, m, item)
    v, got = game_run(cpu, op, item)
    what = (lv, op, want, tuple(m.calls), tuple(sorted((a, m.ram[a & MASK]) for a in m.written)))
    if (want, m.calls) != (v, got):
        return what, f"{op} {item:#x}: model {want} {m.calls}, game {v} {got}"
    a, b = m.ram, cpu.ram
    for lo, hi in ((0, STACK_LO), (STACK_HI, len(a))):
        if a[lo:hi] != b[lo:hi]:
            for i in range(lo, hi):
                if a[i] != b[i]:
                    return what, f"{op} {item:#x}: {0x80000000 | i:#x}: model {a[i]:#x}, " \
                        f"game {b[i]:#x} ({levelin._where(0x80000000 | i)})"
    return what, None


def check(out=sys.stdout, per_level=60, seed=53, verbose=False):
    """The model against the game's own give_item and take_item on every level."""
    rng = random.Random(seed)
    ok = n = 0
    seen = {}
    flagged = {}
    told = False
    for lv in range(28):
        try:
            runs = cases(lv, per_level, rng)
        except Exception as e:                                     # noqa: BLE001
            print(f"  level {lv}: no machine ({e})", file=out)
            continue
        for cpu, op, item in runs:
            n += 1
            what, why = compare(cpu, lv, op, item)
            if why is None:
                ok += 1
                seen[what] = seen.get(what, 0) + 1
                for a, _v in what[4]:
                    if levelin.FLAGS <= a < levelin.FLAGS + 0x100:
                        flagged[lv] = flagged.get(lv, 0) + 1
            elif not told or verbose:
                told = True
                print(f"  level {lv}: {why}", file=out)
    gave = sum(c for w, c in seen.items() if w[1] == "give" and w[2] == 0)
    full = sum(c for w, c in seen.items() if w[1] == "give" and w[2] == 1)
    took = sum(c for w, c in seen.items() if w[1] == "take" and w[2] == 0)
    none = sum(c for w, c in seen.items() if w[1] == "take" and w[2] == 1)
    print(f"  {gave} given, {full} refused (both at 99), {took} taken, {none} with none to take; "
          f"entry 6 set a flag in {', '.join(f'level {k} {v}' for k, v in sorted(flagged.items()))}",
          file=out)
    print(f"give_item and take_item, against the game's own with every level's entries 6 and 11: "
          f"{ok} of {n} runs agree -- the answer, the calls and all of RAM but the stack", file=out)
    return ok == n


def export(out_dir, per_level=8, seed=59):
    """givetakecheck.json: runs of the model over every level -- the bytes it
    read, the call, the answer and the bytes it wrote -- which godot/selftest.gd
    holds KFItems' give_item and take_item, with the level's entry 6, to."""
    import json
    rng = random.Random(seed)
    rows = []
    for lv in range(28):
        try:
            runs = cases(lv, per_level, rng)
        except Exception:                                          # noqa: BLE001
            continue
        for cpu, op, item in runs:
            m = Mem(bytes(cpu.ram))
            v = (give_item if op == "give" else take_item)(lv, m, item)
            rows.append({"level": lv, "op": op, "item": item, "answer": v,
                         "read": [[a, b] for a, b in sorted(m.read.items())],
                         "calls": [list(c) for c in m.calls],
                         "wrote": [[a, m.ram[a & MASK]] for a in sorted(m.written)]})
    path = os.path.join(out_dir, "givetakecheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": rows}, fh, separators=(",", ":"))
    return path


def table(out=sys.stdout):
    """Each level's entries 6 and 11: how many instructions, off the overlays."""
    import overlay
    for lv in range(28):
        _h, ptrs = overlay.hooks(lv)
        raw = overlay.TArc(overlay.FDAT).raw(lv * 3 + 2)
        sizes = []
        for e in (GIVE, TAKE):
            o, k = ptrs[e] - overlay.BASE, 0
            while struct.unpack_from("<I", raw, o + 4 * k)[0] != 0x03E00008:    # jr $ra
                k += 1
            sizes.append(k + 2)
        print(f"  level {lv:2d}: entry 6 at {ptrs[GIVE]:#x}, {sizes[0]:2d} instructions; "
              f"entry 11 at {ptrs[TAKE]:#x}, {sizes[1]}", file=out)


def main():
    a = sys.argv[1:]
    if "--export" in a:
        print(export(a[a.index("--export") + 1] if len(a) > a.index("--export") + 1
                     else os.path.join(levelin.useitem.ROOT, "out", "godot")))
        return
    if "--check" in a:
        sys.exit(0 if check(verbose="-v" in a) else 1)
    print(__doc__.split("**How it is held")[0])
    table()


if __name__ == "__main__":
    main()

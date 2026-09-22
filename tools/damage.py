#!/usr/bin/env python3
"""What a hit takes off, and the log that settles it.

    python3 tools/damage.py              the model, checked against out/lua_bp20.log
    python3 tools/damage.py 0 40 30      one attack, by type
    python3 tools/damage.py --sites      who calls it, and with what

`player_take_hit` (`0x8002ab18`) is 383 instructions and it was read but never
checked, because nothing had ever recorded a creature hitting the player. A
session with `emu/bp20.lua` armed did, and the formula comes out exactly.

**Nine attack values, one per damage type** -- slash, blow, stab, dark, holy,
fire, earth, wind, water, the same nine `tools/player.py` reads out of the
player's block -- arrive as `a0`..`a3` and `arg4`..`arg8`. Each goes through
`damage_of_type` (`0x8002a5f8`) against the matching defence rating:

```
A = attack * 16                                    the attack, in sixteenths
D = ((stat_2524 * 0x801b24f8) >> 8) + defence * 16  what stands against it
                                                    -- 0x801b24f8 is 0x1000
if A == 0:  0                                      a type not in the attack
if D == 0:  D = 0x10                               nothing is ever divided by 0
d = ( max(0, A - D) + (A * A) / (2 * D) ) / 5
```

so a hit gets through in two ways at once: the part that beats the defence
outright, and a quadratic term that never quite vanishes. **The floor is the
point** -- an attack always does *something*, and a strong enough one grows
faster than the defence can hold it.

Then the nine are summed and scaled twice:

```
base = sum of the nine
s1   = (arg9 * base + 0x8000) >> 16      arg9 = 0x1000, so base / 16, rounded
dmg  = (arg10 * s1) / 10                 arg10 = 10, so unchanged
player_hp -= dmg                          0x8002a6f4
```

Both scales were read off a call site (`0x8004d358`), not guessed: `0x1000`
into `sp+0x24` and `0xa` into `sp+0x28`, with `sp+0x10` through `sp+0x20` --
the other five damage types -- all zero.

**Checked against the game.** In the recorded session a creature hit a fresh
character with `(slash 0, blow 40, stab 30)` three separate times and the log
shows 50 -> 36 -> 22 -> 8, fourteen each time. The model gives 222 for the sum
and 14 for the damage, from that character's own defence ratings out of
`out/snap/b.ram`: slash 13, blow 6, stab 4.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import player                                                        # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LOG = os.path.join(ROOT, "out", "lua_bp20.log")
SNAP = os.path.join(ROOT, "out", "snap", "b.ram")

SCALE_ADDR = 0x801B24F8      # a halfword, 0x1000 in every snapshot
STAT_ADDR = 0x801B2524       # the effective copy of the stat at +0x36
ARG9 = 0x1000                # 0x8004d358
ARG10 = 0xA                  # 0x8004d35c


def of_type(attack, defence, stat, k=0x1000):
    """`damage_of_type` (0x8002a5f8), one damage type."""
    a = attack * 16
    if a == 0:
        return 0
    d = ((stat * k) >> 8) + defence * 16
    over = max(0, a - d)
    if d == 0:
        d = 0x10
    return (over + (a * a) // (2 * d)) // 5


def hit(attacks, defence, stat, k=0x1000, arg9=ARG9, arg10=ARG10):
    """The whole of `player_take_hit`'s arithmetic. Returns `(sum, damage)`."""
    base = sum(of_type(attacks[i], defence[i], stat, k)
               for i in range(len(attacks)))
    s1 = (arg9 * base + 0x8000) >> 16
    return base, (arg10 * s1) // 10


def from_snapshot(path=SNAP):
    """`(defence, stat, k)` out of a RAM snapshot."""
    p = player.read(open(path, "rb").read())
    return ([p["defense"][n] for n in player.DAMAGE],
            p["unknown_44"], p["unknown_18"])


IN = re.compile(r"HURT in\s+a0=(-?\d+) a1=(-?\d+) a2=(-?\d+) a3=(-?\d+) "
                r"hp=(\d+)")
OUT = re.compile(r"HURT out hp=(\d+)")


def pairs(path=LOG):
    """`[(attacks, hp_before, hp_after)]` out of a bp20 log."""
    out, pend = [], None
    for line in open(path):
        m = IN.search(line)
        if m:
            pend = ([int(m.group(i)) for i in (1, 2, 3, 4)] + [0] * 5,
                    int(m.group(5)))
            continue
        m = OUT.search(line)
        if m and pend is not None:
            out.append((pend[0], pend[1], int(m.group(1))))
            pend = None
    return out


def check(out=sys.stdout):
    if not os.path.exists(LOG):
        print("no out/lua_bp20.log -- run ./emu/run.sh debug bp20.lua and play",
              file=out)
        return 0, 0
    defence, stat, k = from_snapshot()
    got = pairs()
    ok = seen = 0
    for attacks, before, after in got:
        if before == 0:
            continue          # already dead: there is nothing to take off
        if after == 0:
            continue          # the kill: the damage is clamped, so it only
                              # says "at least this much" -- reported below
        base, dmg = hit(attacks, defence, stat, k)
        seen += 1
        if before - after == dmg:
            ok += 1
        else:
            print(f"  {attacks[:4]}: {before} -> {after} is {before - after}, "
                  f"the model says {dmg} (sum {base})", file=out)
    print(f"{ok} of {seen} recorded hits reproduced exactly", file=out)
    killed = [(a, b) for a, b, c in got if c == 0 and b > 0]
    for attacks, before in killed:
        base, dmg = hit(attacks, defence, stat, k)
        print(f"  and the kill: {attacks[:4]} on {before} HP, "
              f"the model says {dmg}" + ("  (enough)" if dmg >= before
                                         else "  -- NOT enough"), file=out)
    return ok, seen


def export(out_dir):
    """The recorded hits, for the port to reproduce."""
    import json
    if not os.path.exists(LOG):
        return None
    defence, stat, k = from_snapshot()
    rows = []
    for attacks, before, after in pairs():
        base, dmg = hit(attacks, defence, stat, k)
        rows.append({"attacks": attacks, "before": before, "after": after,
                     "sum": base, "damage": dmg})
    path = os.path.join(out_dir, "damagecheck.json")
    with open(path, "w") as fh:
        json.dump({"_note": "hits recorded by emu/bp20.lua, with what "
                            "tools/damage.py makes of each; defence and stat "
                            "are the fresh character's, out of out/snap/b.ram",
                   "defence": defence, "stat": stat, "k": k,
                   "hits": rows}, fh, separators=(",", ":"))
    return path


def sites(out=sys.stdout):
    import json
    db = json.load(open(os.path.join(ROOT, "out", "rdis", "game.json")))
    for k, f in db["functions"].items():
        for c in f["calls"]:
            if c["to"] == 0x8002AB18:
                print(f"  {f['name']:26s} at {c['at']:#010x}", file=out)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--sites":
        sites()
    elif a:
        defence, stat, k = from_snapshot()
        attacks = [int(x) for x in a] + [0] * (9 - len(a))
        base, dmg = hit(attacks, defence, stat, k)
        for i, n in enumerate(player.DAMAGE):
            if attacks[i]:
                print(f"  {n:6s} {attacks[i]:4d} against {defence[i]:3d} "
                      f"-> {of_type(attacks[i], defence[i], stat, k)}")
        print(f"  sum {base}, damage {dmg}")
    else:
        defence, stat, k = from_snapshot()
        print(f"a fresh character: defence {defence[:4]}..., "
              f"stat {stat}, k {k:#x}")
        check()

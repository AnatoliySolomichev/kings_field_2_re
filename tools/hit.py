#!/usr/bin/env python3
"""A creature takes a hit: actor_take_hit whole, and actor_attack_player.

    python3 tools/hit.py --check     the model against the game's own
                                     actor_take_hit over every snapshot's
                                     creatures, every flag path

**`actor_take_hit`** (`0x8004c668`) -- (slot, the striker's stat, eight
attacks, strength, flags, the striker's spell record, the point it came
from). tools/weapon.py had its blow's path (flags 0x50); this is all of it,
on the actor's own bytes:

```
the things that take nothing: model (+1) 0x6e, 1, 2, 0x1d, 0x16
a part (+0 3) passes the hit to the actor its +0x22 names
dying (op 3) with its clock (+0x18) at 0x60c or past, op 0x1a: nothing
op 0x15: +0x70 to 2 if it was 0, and nothing more; op 6: the same, and on
flags & 0xc0 0x80 (a creature's) against +0x28 bit 0x100000: nothing
the damage: creature_type_damage eight times against the kind's +0x20..,
  summed to 0x68db7 at most, * strength / 5000, + 0x80, >> 4; the level's
  hook (level_hooks + 0x48) may change it; 0 takes nothing
with HP left and flags 0x40 (the player's): 0x20 practises the spell
  (skill_practice), 0x10 at strength 2500 or more counts a strong blow
a blow (0x10) on op 0x13 with +0x70 0x10: no HP lost
a spell (0x20): +0x28 bit 0x40000 is immune; a kind with a behaviour 0x16
  facing the point within 0x200 switches to it instead
the player's blow with weapon 0x1f rolls 0x80030c4c(rand * 9 >> 15 + 1);
  weapon 0x20 against models 0x3b, 0x3c, 0x3d, 0x3f, 0x42, 0x43, 0x4f,
  0x58, 0x59, 0x5b takes all its HP
HP left <= 0: the player's (flags & 0xc0 == 0x40) award_exp(kind +0x1e)
  if it had any; a model under 0x2b sets kill_flag and counts kill_count;
  opcode 3; HP 0
else the first of its sixteen behaviours of op 2 whose +0xc the damage
  reaches and whose chance (+2, 0xff always, else rand >> 7 under it) comes
  up -- one it does not reach sets +0x28 bit 0x200000 and +0x84 0 -- and
  HP less the damage
then the push (tools/weapon.py knock) from the point unless the kind's
  weight (+2; a follower's leader's) is 0xf0 or more, a follower's handed
  to its leader (opcode 2 unless it is dying), and +0xd 0x10
```

**`actor_attack_player`** (`0x800533e8`), what an effect's hit hands on:
code 0x80 is the player (`player_take_hit` with the record's attacks and
effect, the strength as its scale); 0x10 the creature `collide_query` left
at `0x801e648c` -- if the point is behind it by its kind's `+0x18` arc it
takes nothing (`facing_test`), else `actor_take_hit` with flags `+0 & 0xc0`
and 0x20 (0x10 for code bit 0x20000), and code bit 0x10000 sets its `+0x28`
bit 0x800.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movement                                                      # noqa: E402
import weapon                                                        # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MASK = 0x1FFFFF
ACTORS, STRIDE, N = 0x80185DA8, 0x88, 200
ENTITY = 0x8018C7E8
TAKE_HIT = 0x8004C668
ATTACK = 0x800533E8
SKILL_PRACTICE, STRONG_BLOW, AWARD_EXP = 0x8002A10C, 0x8002A074, 0x8002A310
SPECIAL = 0x80030C4C
PLAYER_TAKE_HIT = 0x8002AB18
LEVEL_HOOKS = 0x8018FAE0
WEAPON = 0x801B25AF
KILL_FLAG, KILL_COUNT = 0x801BAA01, 0x801BAA02
COLLIDE_ACTOR = 0x801E648C
RAND = 0x800796C0
UNHIT = (0x6E, 1, 2, 0x1D, 0x16)
SLAIN_BY_0X20 = (0x3B, 0x3C, 0x3D, 0x3F, 0x42, 0x43, 0x4F, 0x58, 0x59, 0x5B)


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def _s32(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


class Ram:
    def __init__(self, m):
        self.m = m

    def u8(self, a):
        return self.m[a & MASK]

    def u16(self, a):
        return struct.unpack_from("<H", self.m, a & MASK)[0]

    def s16(self, a):
        return struct.unpack_from("<h", self.m, a & MASK)[0]

    def u32(self, a):
        return struct.unpack_from("<I", self.m, a & MASK)[0]

    def s32(self, a):
        return struct.unpack_from("<i", self.m, a & MASK)[0]

    def w8(self, a, v):
        self.m[a & MASK] = v & 0xFF

    def w16(self, a, v):
        struct.pack_into("<H", self.m, a & MASK, v & 0xFFFF)

    def w32(self, a, v):
        struct.pack_into("<I", self.m, a & MASK, v & 0xFFFFFFFF)

    def with_op(self, kind, op):
        """kind_behaviour_with_op (0x8004c068): the first of sixteen."""
        for i in range(16):
            p = self.u32(kind + 0x38 + 4 * i)
            if p == 0:
                return 0
            if self.u8(p) == op:
                return p
        return 0

    def switch(self, a, rec):
        """actor_switch (0x8004b94c)."""
        self.w8(a + 0x10, self.u8(a + 0xE))
        if rec:
            self.w32(a + 0x60, rec)
            self.w8(a + 0xF, 0)
            self.w8(a + 0xE, self.u8(rec))
        else:
            self.w32(a + 0x60, 0)
            self.w8(a + 0xE, 0xFF)
            self.w8(a + 0xF, 0xFF)

    def switch_op(self, a, op):
        """actor_switch_op (0x8004c0b0)."""
        self.switch(a, self.with_op(ENTITY + 120 * self.u8(a + 2), op))


def actor_take_hit(r, slot, stat, att, strength, flags, record, point, rand, calls, hook):
    """actor_take_hit on RAM `r` (a Ram). `point` the address of the point
    or 0; `hook(actor, dmg)` the level's, answering the damage; `calls`
    collects skill_practice, strong_blow, award_exp and the 0x1f special."""
    a = ACTORS + STRIDE * (slot & 0xFFFF)
    if r.u8(a + 1) in UNHIT:
        return
    if r.u8(a) == 3:
        a = ACTORS + STRIDE * r.s16(a + 0x22)
    kind = ENTITY + 120 * r.u8(a + 2)
    op = r.u8(a + 0xE)
    if op == 3 and r.u16(a + 0x18) >= 0x60C:
        return
    if op == 0x15:
        if r.s16(a + 0x70) == 0:
            r.w16(a + 0x70, 2)
        return
    if op == 6 and r.s16(a + 0x70) == 0:
        r.w16(a + 0x70, 2)
    if r.u8(a + 0xE) == 0x1A:
        return
    s7, s1 = flags & 0xC0, flags & 0x30
    if s7 == 0x80 and r.u32(a + 0x28) & 0x100000:
        return
    total = sum(weapon.type_damage(stat & 0xFFFF, att[i] & 0xFFFF, r.u16(kind + 0x20 + 2 * i))
                for i in range(8))
    total = min(_s32(total), 0x68DB7)
    dmg = (weapon._div5000(total * (strength & 0xFFFF)) + 0x80) >> 4
    dmg = hook(a, dmg)
    if dmg == 0:
        return
    hp = r.u16(a + 0x1A)
    if hp != 0 and s7 & 0x40:
        if s1 & 0x20:
            calls.append(("practice", record))
        elif s1 & 0x10 and (strength & 0xFFFF) >= 0x9C4:
            calls.append(("strong",))
    skip_hp = False
    if s1 & 0x10:
        if r.u8(a + 0xE) == 0x13 and r.s16(a + 0x70) == 0x10:
            skip_hp = True
    elif s1 & 0x20:
        if r.u32(a + 0x28) & 0x40000:
            skip_hp = True
        else:
            rec = r.with_op(kind, 0x16)
            if rec:
                ang = movement.vec_angle(_s32(r.s32(a + 0x2C) - r.s32(point)),
                                         _s32(r.s32(a + 0x34) - r.s32(point + 8)))
                if weapon._facing(r.s16(a + 0x42), _s16(ang), 0x200):
                    r.switch(a, rec)
                    skip_hp = True
    if not skip_hp:
        if s7 & 0x40 and s1 & 0x10:
            w = r.u8(WEAPON)
            if w == 0x1F:
                calls.append(("special", ((rand() * 9) >> 15) + 1))
            elif w == 0x20 and r.u8(a + 1) in SLAIN_BY_0X20 and hp:
                dmg = hp
        left = hp - dmg
        if left <= 0:
            if hp != 0 and s7 == 0x40:
                calls.append(("exp", r.s16(kind + 0x1E)))
            if r.u8(a + 1) < 0x2B:
                if r.u8(KILL_FLAG) == 0:
                    r.w8(KILL_FLAG, 1)
                r.w8(KILL_COUNT, r.u8(KILL_COUNT) + 1)
            r.switch_op(a, 3)
            r.w16(a + 0x1A, 0)
        else:
            for i in range(16):
                rec = r.u32(kind + 0x38 + 4 * i)
                if rec == 0:
                    break
                if r.u8(rec) != 2:
                    continue
                if _s32(dmg) < r.u16(rec + 0xC):
                    r.w32(a + 0x28, r.u32(a + 0x28) | 0x200000)
                    r.w8(a + 0x84, 0)
                    continue
                ch = r.u8(rec + 2)
                if ch == 0xFF or (rand() >> 7) < ch:
                    r.switch(a, rec)
                    break
            r.w16(a + 0x1A, left)
    # the push (0x8004cca0)
    leader = None
    if r.u32(a + 0x28) & 0x10:
        leader = ACTORS + STRIDE * r.s16(a + 0x22)
        weight = r.u8(ENTITY + 120 * r.u8(leader + 2) + 2)
    else:
        weight = r.u8(kind + 2)
    if point and weight < 0xF0:
        v = weapon.knock(dmg, weight, (r.s32(point), r.s32(point + 4), r.s32(point + 8)),
                         (r.s32(a + 0x2C), r.s32(a + 0x30), r.s32(a + 0x34)), r.u16(a + 0x1E))
        r.w16(a + 0x50, v[0])
        r.w16(a + 0x54, v[2])
        r.w16(a + 0x52, v[1])
        if leader is not None:
            for o in (0x50, 0x52, 0x54):
                r.w16(leader + o, r.u16(a + o))
            if r.u8(leader + 0xE) != 3:
                r.switch_op(leader, 2)
    r.w8(a + 0xD, 0x10)


def actor_attack_player(r, code, flags, record, strength, stat, pct, point, rand, calls, hook):
    """actor_attack_player (0x800533e8) as an effect's hit calls it: code
    0x80 the player (player_take_hit, recorded), 0x10 the creature at
    0x801e648c -- nothing if the point is outside its back arc, else
    actor_take_hit with flags +0 & 0xc0 and 0x20 (0x10 for code bit
    0x20000) -- and code bit 0x10000 its +0x28 bit 0x800. A code with other
    bits (a creature and a wall at once) does nothing."""
    rec = record
    att = [r.u16(rec + o) for o in (6, 8, 0xA, 0xC, 0xE, 0x10, 0x12, 0x14)]
    hi = code & 0xF0000
    lo = code & 0xFFF0FFFF
    if lo == 0x80:
        calls.append(("player", att, r.u16(rec + 4), strength & 0xFFFF, pct))
        return
    if lo != 0x10:
        return
    a = ACTORS + STRIDE * r.u32(COLLIDE_ACTOR)
    kind = ENTITY + 120 * r.u8(a + 2)
    if point:
        ang = movement.vec_angle(_s32(r.s32(a + 0x2C) - r.s32(point)),
                                 _s32(r.s32(a + 0x34) - r.s32(point + 8))) + 0x800
        if not weapon._facing(r.s16(a + 0x42), _s16(ang), r.s16(kind + 0x18)):
            return
    f = (flags & 0xC0) | (0x10 if hi & 0x20000 else 0x20)
    actor_take_hit(r, r.u16(COLLIDE_ACTOR), stat, att, strength, f, record, point, rand,
                   calls, hook)
    if hi & 0x10000:
        r.w32(a + 0x28, r.u32(a + 0x28) | 0x800)


# --- against the game ---------------------------------------------------------

SCRATCH = 0x801FF100


def _level_hook(ram):
    return struct.unpack_from("<I", ram, (struct.unpack_from("<I", ram, LEVEL_HOOKS & MASK)[0]
                                          + 0x48) & MASK)[0]


def _cases(ram, rng, n):
    awake = [k for k in range(N) if ram[(ACTORS + STRIDE * k + 9) & MASK] == 1]
    out = []
    for _ in range(n):
        slot = rng.choice(awake) if awake and rng.randrange(4) else rng.randrange(N)
        a = ACTORS + STRIDE * slot
        x, y, z = struct.unpack_from("<3i", ram, (a + 0x2C) & MASK)
        out.append({
            "slot": slot, "stat": rng.randrange(0, 120),
            "att": [rng.choice((0, 0, rng.randrange(1, 80))) for _ in range(8)],
            "strength": rng.choice((0x1388, 0x9C4, 0x9C3, rng.randrange(0, 0x1389))),
            "flags": rng.choice((0x50, 0x60, 0x60, 0x20, 0x10, 0x90, 0xA0, 0x40)),
            "point": None if rng.randrange(5) == 0 else (
                x + rng.randrange(-0x800, 0x800), y - rng.randrange(0, 0x800),
                z + rng.randrange(-0x800, 0x800)),
            "weapon": rng.choice((0, 0, 0x1F, 0x20)),
            "hp": rng.choice((None, 1, 5, 40)),
            "seed": rng.randrange(1 << 30)})
    return out


def check(out=sys.stdout, per=60):
    import random
    import memcard
    import mipsrun
    import levelstate
    rng = random.Random(0xAC7)
    ok = n = 0
    tally = {}
    first = None
    for path in memcard._snapshots():
        base = bytearray(open(path, "rb").read())
        hook_at = _level_hook(base)
        for c in _cases(base, rng, per):
            ram = bytearray(base)
            ram[WEAPON & MASK] = c["weapon"]
            a = ACTORS + STRIDE * c["slot"]
            if c["hp"] is not None:
                struct.pack_into("<H", ram, (a + 0x1A) & MASK, c["hp"])
            pt = 0
            if c["point"]:
                pt = SCRATCH
                struct.pack_into("<3i", ram, pt & MASK, *c["point"])
            record = 0x801B77EC + 24 * rng.randrange(0, 31)
            if c["flags"] & 0x20 and rng.randrange(3) == 0:
                # a behaviour 0x16, which no snapshot's kinds have: laid in
                # scratch and put at the end of the kind's list
                kind = ENTITY + 120 * ram[(a + 2) & MASK]
                beh = SCRATCH + 0x40
                ram[beh & MASK:(beh & MASK) + 0x20] = bytes([0x16, 0, 0xFF]) + bytes(0x1D)
                for i in range(16):
                    q = (kind + 0x38 + 4 * i) & MASK
                    if struct.unpack_from("<I", ram, q)[0] == 0:
                        struct.pack_into("<I", ram, q, beh)
                        break
                if rng.randrange(2) and c["point"]:
                    yaw = movement.vec_angle(struct.unpack_from("<i", ram, (a + 0x2C) & MASK)[0] - c["point"][0],
                                             struct.unpack_from("<i", ram, (a + 0x34) & MASK)[0] - c["point"][2])
                    struct.pack_into("<h", ram, (a + 0x42) & MASK, _s16(yaw + rng.randrange(-0x300, 0x300)))
                tally["0x16"] = tally.get("0x16", 0) + 1
            g_calls = []
            cpu = mipsrun.CPU(ram)
            lcg = levelstate.Lcg(c["seed"])
            cpu.hooks[RAND] = lambda c_: lcg()
            cpu.hooks[SKILL_PRACTICE] = lambda c_: g_calls.append(("practice", c_.r[4]))
            cpu.hooks[STRONG_BLOW] = lambda c_: g_calls.append(("strong",))
            cpu.hooks[AWARD_EXP] = lambda c_: g_calls.append(("exp", _s16(c_.r[4])))
            cpu.hooks[SPECIAL] = lambda c_: g_calls.append(("special", c_.r[4]))
            cpu.hooks[hook_at] = lambda c_: None
            at = c["att"]
            cpu.call(TAKE_HIT, c["slot"], c["stat"], at[0], at[1], at[2], at[3], at[4], at[5],
                     at[6], at[7], c["strength"], c["flags"], record, pt)
            m = bytearray(ram)
            r = Ram(m)
            m_calls = []
            lcg2 = levelstate.Lcg(c["seed"])
            actor_take_hit(r, c["slot"], c["stat"], at, c["strength"], c["flags"], record, pt,
                           lcg2, m_calls, lambda actor, d: d)
            o = ACTORS & MASK
            same = (bytes(cpu.ram[o:o + STRIDE * N]) == bytes(m[o:o + STRIDE * N])
                    and g_calls == m_calls
                    and cpu.ram[KILL_FLAG & MASK:(KILL_FLAG & MASK) + 2] == m[KILL_FLAG & MASK:(KILL_FLAG & MASK) + 2])
            n += 1
            ok += same
            g = Ram(cpu.ram)
            a2 = ACTORS + STRIDE * c["slot"]
            if g.u16(a2 + 0x1A) == 0 and r.u16(a2 + 0x1A) == 0 and ram[(a2 + 0x1A) & MASK] | ram[(a2 + 0x1B) & MASK]:
                tally["killed"] = tally.get("killed", 0) + 1
            if g.u8(a2 + 0xE) != ram[(a2 + 0xE) & MASK]:
                tally["switched"] = tally.get("switched", 0) + 1
            for k in g_calls:
                tally[k[0]] = tally.get(k[0], 0) + 1
            if not same and first is None:
                diff = [i for i in range(STRIDE * N) if cpu.ram[o + i] != m[o + i]]
                first = (f"{os.path.basename(path)} {c}: bytes {[(d // STRIDE, hex(d % STRIDE), cpu.ram[o + d], m[o + d]) for d in diff[:6]]} "
                         f"calls {g_calls} / {m_calls}")
    print(f"actor_take_hit, against the game's own: {ok} of {n} hits on the snapshots' "
          f"creatures, all 200 actors' bytes and every call out alike -- "
          + ", ".join(f"{v} {k}" for k, v in sorted(tally.items())), file=out)
    if first:
        print("  first difference: " + first[:1500], file=out)
    return ok == n


def _actor_dict(r, a, kind_list):
    rec = r.u32(a + 0x60)
    return {"model": r.u8(a + 1), "hp": r.u16(a + 0x1A), "op": r.u8(a + 0xE),
            "sub": r.s16(a + 0x70), "clock": r.u16(a + 0x18), "ry": r.s16(a + 0x42),
            "eflags": r.u32(a + 0x28), "px": r.s32(a + 0x2C), "py": r.s32(a + 0x30),
            "pz": r.s32(a + 0x34), "height": r.u16(a + 0x1E), "vx": r.s16(a + 0x50),
            "vy": r.s16(a + 0x52), "vz": r.s16(a + 0x54), "vst": r.u8(a + 0xD),
            "prev": r.u8(a + 0x10), "phase": r.u8(a + 0xF),
            "rec": kind_list.index(rec) if rec in kind_list else -1}


def export(out_dir, n=400):
    """hitcheck.json: actor_take_hit's cases in godot/actors.gd's form -- the
    creature's fields, its kind's defence, experience, weight and behaviours,
    the hit, rand's seed -- and what the model leaves, for the self-test.
    Parts and followers, which the port does not pass on, are left out."""
    import json
    import random
    import memcard
    import levelstate
    rng = random.Random(0x417)
    out = []
    paths = memcard._snapshots()
    while len(out) < n:
        base = bytearray(open(paths[len(out) % len(paths)], "rb").read())
        c = _cases(base, rng, 1)[0]
        c["weapon"] = 0
        ram = bytearray(base)
        a = ACTORS + STRIDE * c["slot"]
        r = Ram(ram)
        if r.u8(a) == 3 or r.u32(a + 0x28) & 0x10 or r.u8(a + 9) != 1:
            continue
        if c["flags"] & 0x20 and not c["point"]:
            continue                    # a spell always has its point; with none the game reads address 0
        if c["hp"] is not None:
            r.w16(a + 0x1A, c["hp"])
        kind = ENTITY + 120 * r.u8(a + 2)
        klist = []
        for i in range(16):
            q = r.u32(kind + 0x38 + 4 * i)
            if q == 0:
                break
            klist.append(q)
        if c["flags"] & 0x20 and rng.randrange(3) == 0:
            beh = SCRATCH + 0x40
            ram[beh & MASK:(beh & MASK) + 0x20] = bytes([0x16, 0, 0xFF]) + bytes(0x1D)
            if len(klist) < 16:
                r.w32(kind + 0x38 + 4 * len(klist), beh)
                klist.append(beh)
        pt = 0
        if c["point"]:
            pt = SCRATCH
            struct.pack_into("<3i", ram, pt & MASK, *c["point"])
        kdict = {"defence": [r.u16(kind + 0x20 + 2 * i) for i in range(8)],
                 "exp": r.s16(kind + 0x1E), "weight": r.u8(kind + 2),
                 "arc_back": r.s16(kind + 0x18),
                 "behaviours": [list(ram[q & MASK:(q & MASK) + 0x20]) for q in klist]}
        before = _actor_dict(r, a, klist)
        kills = [r.u8(KILL_FLAG), r.u8(KILL_COUNT)]
        calls = []
        lcg = levelstate.Lcg(c["seed"])
        actor_take_hit(r, c["slot"], c["stat"], c["att"], c["strength"], c["flags"], 0, pt,
                       lcg, calls, lambda actor, d: d)
        out.append({"actor": before, "kind": kdict, "stat": c["stat"], "att": c["att"],
                    "strength": c["strength"], "flags": c["flags"], "point": c["point"],
                    "seed": c["seed"], "kills": kills,
                    "after": _actor_dict(r, a, klist), "kills_after": [r.u8(KILL_FLAG), r.u8(KILL_COUNT)],
                    "calls": sorted({k[0] for k in calls})})
    path = os.path.join(out_dir, "hitcheck.json")
    with open(path, "w") as fh:
        json.dump({"_note": "actor_take_hit as tools/hit.py has it (whose model the game's "
                            "own holds)", "cases": out}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    print(__doc__)

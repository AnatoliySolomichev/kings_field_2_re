#!/usr/bin/env python3
"""A creature's animation: vertex poses, picked by its animation clock.

    python3 tools/anim.py 50           model 50's animations, segment by segment
    python3 tools/anim.py --check      against every snapshot's actor caches

The creatures do not have skeletons. `draw_model_plain` (`0x8003e34c`) hands
`0x800431e8` the creature's model, its animation (+0xc, animated only under
0x80), its clock (+0x18, 0..0xfff) and the vertex count of the model's first
TMD object, and gets back that object's vertices for this frame.

## The model entry (MO.T)

    +4   the number of animations (0: a still model)
    +8   the TMD, from the entry's start (tools/tmd.py reads it)
    +0xc the pose table: an offset per pose
    +0x10 the animation table: an offset per animation

An **animation** is `u16 n, u16 pad` and n offsets to its **segments**:

    +0  u16  1: run it backwards (the factor is 0x1000 - t)
    +2  u16  its length, in clock units
    +4  u16  the pose it blends towards
    +6  u16  how many poses make the start (0: the model's own vertices)
    +8  u16  ... those poses

`0x80042cac` walks the segments adding up their lengths until the clock falls
inside one, and the factor is `((clock - start) << 12) / length` (unsigned);
past the end, the last segment at 0x1000. Model 50's first animation is six
segments of 0x2aa, one cycle of the clock.

A **pose** is `s16 n` and n entries: either an absolute vertex `(x, y, z)` for
the next vertex, or `0x8000, k` -- the next k vertices left as they are. The
start is the model's vertices with the first start pose written over them
(`0x80042d70`) and the others on top (`0x80042e34`); the actor's cache keeps it
with the segment it was built for (`+4` the animation, `+6` the segment, `+8`
the target pose, `+0xc` the vertices). Then `0x80042eb0` blends towards the
target: every vertex the target pose names moves by `((target - v) * t) >> 12`
(through `ScaleMatrix`, three vertices at a time), the rest stay.

## Checked

Against the snapshots: every awake creature's cache (the handle at actor
+0x5c) holds the segment, the target and the start vertices this reading
builds from its animation and clock.
"""
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SKIP = -0x8000


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


class Model:
    """An MO.T entry as 0x800431e8 reads it."""

    def __init__(self, raw):
        self.raw = raw
        self.nanim, self.tmd, self.poses, self.anims = struct.unpack_from(
            "<4I", raw, 4)
        t = self.tmd
        vtop, nv = struct.unpack_from("<2I", raw, t + 12)
        self.nvert = nv
        v0 = t + 12 + vtop
        self.base = [struct.unpack_from("<3h", raw, v0 + 8 * i)
                     for i in range(nv)]

    def anim(self, k):
        """[segment] of animation k: (reverse, length, target, [start poses])."""
        a = struct.unpack_from("<I", self.raw, self.anims + 4 * k)[0]
        n = u16(self.raw, a)
        out = []
        for i in range(n):
            o = struct.unpack_from("<I", self.raw, a + 4 + 4 * i)[0]
            rev, ln, tgt, cnt = struct.unpack_from("<4H", self.raw, o)
            starts = [u16(self.raw, o + 8 + 2 * j) for j in range(cnt)]
            out.append((rev, ln, tgt, starts))
        return out

    def pose(self, p):
        """[(x, y, z) or ('skip', k)] of pose p."""
        o = struct.unpack_from("<I", self.raw, self.poses + 4 * p)[0]
        n = struct.unpack_from("<h", self.raw, o)[0]
        o += 2
        out = []
        for _ in range(n):
            h = struct.unpack_from("<h", self.raw, o)[0]
            if h == SKIP:
                out.append(("skip", struct.unpack_from("<h", self.raw, o + 2)[0]))
                o += 4
            else:
                out.append(struct.unpack_from("<3h", self.raw, o))
                o += 6
        return out


def load(m):
    import tmd
    from tarc import TArc
    arch, entry = ("MO", m) if m < tmd.MO_COUNT else ("MOF", m - tmd.MO_COUNT)
    return Model(TArc(os.path.join(ROOT, tmd.ARCHIVES[arch])).raw(entry))


WEAPON_ENTRY = 0x62        # FDAT.T entry 0x62 + the weapon (sub_8002bdc0)
WEAPON_KEY = 0x10000       # where the export files a weapon's model
BANK_KEY = 0x20000         # and a resident model, model_table[index]
BANK_ANIMATED = (0x51,)    # the resident models an effect takes a vertex of: flame's


def load_bank(index):
    """model_table[index] of the resident bank (tools/modelbank.py) in the
    same wrapper as MO.T's: flame's head (0x51) has one animation, which
    sub_8004352c runs by the effect's +0x14."""
    import modelbank
    raw, at, _n = modelbank.block(modelbank.FDAT, modelbank.BLOCK if index >= modelbank.FIRST
                                  else 9)
    for i, off, size in modelbank.models(modelbank.FDAT, modelbank.BLOCK if index >= modelbank.FIRST
                                         else 9):
        if i == index:
            return Model(raw[at + off:at + off + size])
    raise ValueError(f"model {index} is not in the bank")


def load_weapon(w):
    """The model in the player's hand while they swing weapon w: FDAT.T
    (archive 4) entry 0x62 + w, which sub_8002bdc0 reads into 0x801b2598 and
    installs as model_table[0x20] -- the same wrapper as MO.T's creatures, a
    hand and the weapon, animated by the swing clock (draw_held_item)."""
    from tarc import TArc
    return Model(TArc(os.path.join(ROOT, "extract", "CD", "COM", "FDAT.T"))
                 .raw(WEAPON_ENTRY + w))


def pick(segs, clock):
    """0x80042cac: (segment index, factor)."""
    end = start = 0
    for i, (rev, ln, _tgt, _st) in enumerate(segs):
        end += ln
        if clock < end:
            t = ((clock - start) << 12) // ln
            return i, (0x1000 - t if rev else t)
        start = end
    return len(segs) - 1, 0x1000


def overlay(verts, pose):
    """0x80042e34 (and 0x80042d70 over a copy of the base): the pose's
    vertices written over, its runs skipped."""
    i = 0
    for e in pose:
        if e[0] == "skip":
            i += e[1]
        else:
            verts[i] = e
            i += 1
    return verts


def start(model, seg):
    """The segment's start: the model's own vertices, or its poses on them."""
    v = list(model.base)
    for p in seg[3]:
        overlay(v, model.pose(p))
    return v


def blend(verts, pose, t):
    """0x80042eb0: every vertex the pose names moves by ((target - v) * t) >> 12."""
    v = list(verts)
    i = 0
    for e in pose:
        if e[0] == "skip":
            i += e[1]
            continue
        v[i] = tuple(s16(c + ((s16(tc - c) * t) >> 12)) for c, tc in zip(v[i], e))
        i += 1
    return v


def vertices(model, anim, clock):
    """The first object's vertices for this animation and clock."""
    if anim >= 0x80 or model.nanim == 0:
        return list(model.base)
    segs = model.anim(anim)
    i, t = pick(segs, clock)
    return blend(start(model, segs[i]), model.pose(segs[i][2]), t)


def check(out=sys.stdout):
    """Every awake creature's cache against what this builds."""
    ok = n = frames = 0
    seen = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        d = open(f, "rb").read()
        for k in range(200):
            a = 0x185DA8 + 0x88 * k
            if d[a + 9] != 1:
                continue
            anim, clock = d[a + 0xC], u16(d, a + 0x18)   # +0xd is the vertical state
            h = struct.unpack_from("<I", d, a + 0x5C)[0]
            if anim >= 0x80 or not 0x80000000 <= h < 0x80200000:
                continue
            c = h & 0x1FFFFF
            if u16(d, c + 4) != anim:
                continue                    # not drawn since it changed
            mdl = d[a + 1]          # model_table[+1 + 0x80] is MO.T[+1]
            if mdl not in seen:
                try:
                    seen[mdl] = load(mdl)
                except Exception:
                    seen[mdl] = None
            model = seen[mdl]
            if model is None or model.nanim == 0:
                continue
            segs = model.anim(anim)
            i, _t = pick(segs, clock)
            n += 1
            frames += u16(d, c + 6) == i
            vp = struct.unpack_from("<I", d, c + 0xC)[0] & 0x1FFFFF
            got = [struct.unpack_from("<3h", d, vp + 8 * j)
                   for j in range(model.nvert)]
            ok += got == start(model, segs[i]) and u16(d, c + 6) == i
    print(f"  {ok} of {n} awake creatures' caches hold the segment ({frames}) "
          f"and the start vertices this builds from their animation and clock",
          file=out)
    # the blend: 0x801acb98 holds the last creature drawn -- the highest slot
    # with a cache -- at its clock, or one step (+0x66) before when the
    # snapshot fell between actor_tick and the draw
    bok = bn = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        d = open(f, "rb").read()
        last = None
        for k in range(200):
            a = 0x185DA8 + 0x88 * k
            h = struct.unpack_from("<I", d, a + 0x5C)[0]
            if d[a + 9] == 1 and 0x80000000 <= h < 0x80200000 and d[a + 0xC] < 0x80:
                last = a
        if last is None:
            continue
        model = seen.get(d[last + 1])
        if model is None or model.nanim == 0:
            continue
        sc = [struct.unpack_from("<3h", d, 0x1ACB98 + 8 * j)
              for j in range(model.nvert)]
        clock, step = u16(d, last + 0x18), u16(d, last + 0x66)
        if sc not in (vertices(model, d[last + 0xC], clock),
                      vertices(model, d[last + 0xC], (clock - step) & 0xFFF)):
            continue                        # something else drawn after it
        bok += 1
    print(f"  {bok} snapshots' last drawn creature is the blend at its clock or "
          f"a step before", file=out)
    return ok == n


def export(out_dir, lv=0):
    """animNN.json for godot/anim.gd: each animated model the level's creatures
    and lift doors use, and the weapon's -- its vertices, animations and poses
    -- and cases for selftest.gd."""
    import json
    import actors
    doc = {"_note": "MO.T entries as 0x800431e8 reads them; tools/anim.py",
           "models": {}, "cases": []}
    wanted = [(m, None) for m in sorted({a["model"] for a in actors.table(lv) if a})]
    # every weapon: the equipment screen can put any in hand (equip_weapon)
    wanted += [(WEAPON_KEY + w, w) for w in range(0x22)]
    # the resident models an effect takes a vertex of (flame's head)
    wanted += [(BANK_KEY + i, None) for i in BANK_ANIMATED]
    # and the lift doors' and the big chests' models, which draw_model_plain
    # animates by the object's counter (tools/doors.py, tools/chests.py)
    try:
        import objload
        import doors
        import level3d
        ld = objload.Load(lv)
        for m in sorted({level3d.lift_model(r["type"], lv) for r in ld.recs.values()
                         if r["op"] in doors.LIFT_OPS + doors.GATE_OPS + doors.WALL_OPS
                         or r["op"] == 7}):
            if (m, None) not in wanted:
                wanted.append((m, None))
    except Exception:
        pass
    for m, w in wanted:
        try:
            mo = (load_bank(m - BANK_KEY) if m >= BANK_KEY else
                  load(m) if w is None else load_weapon(w))
        except Exception:
            continue
        if mo.nanim == 0:
            continue
        segs = [mo.anim(k) for k in range(mo.nanim)]
        npose = max(max([s[2]] + s[3]) for sg in segs for s in sg) + 1
        poses = []
        for p in range(npose):
            flat = []
            for e in mo.pose(p):
                flat.append([SKIP, e[1]] if e[0] == "skip" else list(e))
            poses.append(flat)
        doc["models"][str(m)] = {"base": [list(v) for v in mo.base],
                                 "anims": [[[r, ln, tg, st] for r, ln, tg, st in sg]
                                           for sg in segs],
                                 "poses": poses}
        for k in range(mo.nanim):
            for clock in (0, 0x155, 0x2AA, 0x7FF, 0xAB0, 0xFFF):
                v = vertices(mo, k, clock)
                doc["cases"].append([m, k, clock, sum(c * (i + 1) for i, t in
                                                      enumerate(v) for c in t),
                                     list(v[len(v) // 2])])
    path = os.path.join(out_dir, f"anim{lv:02d}.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--check":
        sys.exit(0 if check() else 1)
    m = load(int(a[0]) if a else 50)
    print(f"model: {m.nanim} animations, {m.nvert} vertices")
    for k in range(m.nanim):
        print(f"  animation {k}: " + ", ".join(
            f"{'<' if r else '>'}{ln:#x} to {tg} from {st}"
            for r, ln, tg, st in m.anim(k)))

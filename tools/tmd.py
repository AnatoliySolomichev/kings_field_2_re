#!/usr/bin/env python3
"""TMD, the PlayStation model format, as this game uses it.

    python3 tools/tmd.py RTMD 0             what level 0's tile models contain
    python3 tools/tmd.py RTMD 0 174         one object, primitive by primitive
    python3 tools/tmd.py RTMD 0 174 obj     write out/tmd/RTMD_0_174.obj

`RTMD.T[level]` is one TMD of 240 objects and `cell[+5]` picks one per cell, so
these are the tiles the world is built from (FORMATS.md section 4). `ITEM.T`,
`MO.T` and `MOF.T` hold TMDs too.

    header      u32 id = 0x41, u32 flags, u32 nobj                 12 bytes
    object      vert_top n_vert normal_top n_normal                28 bytes
                prim_top n_prim scale
    vertex      s16 x, y, z, pad
    normal      s16 x, y, z, pad                                   0x1000 = 1.0
    primitive   u8 olen, u8 ilen, u8 flag, u8 mode, then ilen words

Offsets run from the **end of the header**, not the start of the file, when bit
0 of `flags` is clear — which it is here.

The `mode` byte says how to read the rest: bit 3 picks quad over triangle, bit 2
texture, bit 4 gouraud. Every layout below is checked rather than trusted: each
vertex index must land inside the object's own vertex block, and
`python3 tools/tmd.py RTMD 0` reports how many fail. On level 0 none do.

**The archives disagree about what a vertex reference is.** `RTMD.T` stores byte
offsets, eight to a vertex; `MO.T` stores plain indices. Nothing in the file
says which, so each object is scored both ways and the reading that yields more
*usable* faces wins — in range and not collapsed. Counting only out-of-range
references is not enough to tell them apart: read MO.T's small indices as byte
offsets and every one divides to zero, which is in range and draws nothing.
All 271 MO.T models come out as indices, all 240 RTMD tiles as offsets.

`MO.T` also puts its TMD behind a wrapper, and **the wrapper's third word says
where it is**. Scanning for the id instead only worked for the models that keep
it near the front: 53 of level 0's objects — the chests, the statues — put it
thousands of bytes in and came out as "holds no TMD". With the offset read
properly, all 347 objects on level 0 have a model.
"""
import os
import struct
import sys

sys.path.insert(0, "tools")
from tarc import TArc  # noqa: E402

ARCHIVES = {"RTMD": "extract/CD/COM/RTMD.T", "ITEM": "extract/CD/COM/ITEM.T",
            "MO": "extract/CD/COM/MO.T", "MOF": "extract/CD/COM/MOF.T"}
HDR = 12


class Prim:
    """One primitive: what it draws and what it draws it with."""

    def __init__(self, olen, ilen, flag, mode, body):
        self.olen, self.ilen, self.flag, self.mode = olen, ilen, flag, mode
        self.body = body
        self.quad = bool(mode & 0x08)
        self.tex = bool(mode & 0x04)
        self.iip = bool(mode & 0x10)
        self.lit = not (flag & 0x01)
        self.verts, self.norms, self.uvs = [], [], []
        self.vrefs, self.nrefs = [], []
        self.tpage, self.clut, self.rgb = None, None, []
        self._decode()

    def _hw(self, i):
        return struct.unpack_from("<H", self.body, i * 2)[0]

    def _decode(self):
        n = 4 if self.quad else 3
        p = 0                                        # in halfwords
        if self.tex:
            for k in range(n):
                u, v = self.body[p * 2], self.body[p * 2 + 1]
                self.uvs.append((u, v))
                extra = self._hw(p + 1)
                if k == 0:
                    self.clut = extra
                elif k == 1:
                    self.tpage = extra
                p += 2
        # Colour words come before the references, but **a textured primitive
        # carries them only when it is unlit**. Reading one for every gouraud
        # primitive, textured or not, shifted the references by a word on mode
        # 0x34 -- which is 58 000 of the game's object primitives.
        # **One colour word, never n of them.** The renderer's own handlers say
        # so: for mode 0x30 -- an untextured gouraud triangle, four words long --
        # 0x80035ab4 multiplies halfwords 2 to 7 by eight, so only halfwords 0
        # and 1 are colour and the other six are references. Same for 0x38, the
        # quad. Reading one colour word per vertex left two halfwords where six
        # references belonged, and type 309's 704 primitives came out at nothing
        # usable.
        if not self.tex or not self.lit:
            ncol = 1
            for _ in range(ncol):
                if p * 2 + 4 > len(self.body):
                    break
                self.rgb.append(tuple(self.body[p * 2:p * 2 + 3]))
                p += 2
        # What remains references vertices and normals. **As byte offsets, not
        # indices** -- the first quad of object 174 reads 8, 0, 16, 24, which at
        # eight bytes a vertex is 1, 0, 2, 3. Reading them as indices puts ten
        # thousand of them past the end of their own object.
        rest = [self._hw(i) for i in range(p, len(self.body) // 2)]
        if self.lit and self.iip:
            # **Gouraud interleaves them**: n0 v0 n1 v1 n2 v2, one normal beside
            # its own vertex -- not all the normals and then all the vertices.
            # Reading them in blocks took n0, v0, n1 as the normals and v1, n2,
            # v2 as the vertices, which is geometry from three different corners
            # of the model. It is what a player saw as objects "badly distorted".
            self.nrefs = rest[0:2 * n:2]
            self.vrefs = rest[1:2 * n:2]
        else:
            if self.lit:
                self.nrefs = rest[:1]
                rest = rest[1:] if len(rest) >= 1 + n else rest
            self.vrefs = rest[:n]
        self.scale_refs(1)

    def scale_refs(self, div):
        self.verts = [v // div for v in self.vrefs]
        self.norms = [v // div for v in self.nrefs]

    def __str__(self):
        kind = ("quad" if self.quad else "tri") + (" tex" if self.tex else "") + \
               (" gouraud" if self.iip else "") + ("" if self.lit else " unlit")
        s = f"mode {self.mode:#04x} flag {self.flag:#04x}  {kind:20s} v={self.verts}"
        if self.tex:
            s += f" uv={self.uvs} tpage={self.tpage:#06x} clut={self.clut:#06x}"
        if self.rgb:
            s += f" rgb={self.rgb}"
        return s


class Obj:
    def __init__(self, data, rec):
        (vt, self.nv, nt, self.nn, pt, self.npr, self.scale) = rec
        self.verts = [struct.unpack_from("<3h", data, HDR + vt + 8 * i)
                      for i in range(self.nv)]
        self.normals = [struct.unpack_from("<3h", data, HDR + nt + 8 * i)
                        for i in range(self.nn)]
        self.prims, p = [], HDR + pt
        for _ in range(self.npr):
            if p + 4 > len(data):
                break
            olen, ilen, flag, mode = data[p], data[p + 1], data[p + 2], data[p + 3]
            body = data[p + 4:p + 4 + ilen * 4]
            self.prims.append(Prim(olen, ilen, flag, mode, body))
            p += 4 + ilen * 4
        # **The two archives disagree about what a vertex reference is.**
        # `MO.T` stores plain indices; `RTMD.T` stores byte offsets, eight to a
        # vertex. Neither says which, so pick whichever lands inside the object
        # -- reading MO.T as offsets silently collapses every face to vertex 0.
        # Score each reading by how many faces come out *usable*: inside the
        # object and not collapsed. Counting only out-of-range references misses
        # the real failure -- read MO.T's small indices as byte offsets and they
        # all divide to zero, which is in range and draws nothing.
        def usable(div):
            n = 0
            for pr in self.prims:
                v = [r // div for r in pr.vrefs]
                if len(v) >= 3 and max(v) < self.nv and len(set(v)) >= 3:
                    n += 1
            return n
        self.div = 1 if usable(1) >= usable(8) else 8
        for pr in self.prims:
            pr.scale_refs(self.div)

    def bad_indices(self):
        return sum(1 for pr in self.prims for v in pr.verts if v >= self.nv)


def _is_tmd(data, off):
    if not 0 <= off <= len(data) - 12:
        return False
    idv, _flags, nobj = struct.unpack_from("<3I", data, off)
    return idv == 0x41 and 0 < nobj < 4096


def find_tmd(data):
    """Where the TMD starts.

    `RTMD.T` puts it at 0. `MO.T` puts it behind a wrapper, and **the wrapper's
    third word is the offset** — that is the whole of it:

        +0  total size          +0x0c  ?
        +4  a count, 1 to 3     +0x10  0x14, the first of a table of offsets
        +8  where the TMD is

    Scanning for the id instead, which is what this did, only looked at the first
    256 bytes, and 53 of level 0's objects keep their TMD further in than that —
    at 3448 for the statue, 13964 for the chest. They came out as "holds no TMD"
    and simply did not appear in the port. A player looked at the two side by
    side and said a statue was missing and a chest was distorted; the chest was
    the wrapper being read as geometry.
    """
    if len(data) >= 12:
        off = struct.unpack_from("<I", data, 8)[0]
        if _is_tmd(data, off):
            return off
    for off in range(0, max(0, len(data) - 12), 4):
        if _is_tmd(data, off):
            return off
    return None


MO_COUNT = 428          # MO.T's entries; MOF.T continues the numbering
MODEL_BIAS = 128
# From this type up, the model number carries the level in it: model_of_type
# (0x80040568) adds `32 * current_level_block`, so MOF.T is banked 32 to a
# level and level n uses bank n + 4.
LEVEL_BANKED = 300
BANK = 32        # an object of type N uses model N + 128


def model_of(type_id, level=0):
    """Which archive and entry an object type's model is, as (name, entry).

    Below type 300 it is **`MO.T[type + 128]`**, and the 128 was measured
    before it was read: a player stood in the game beside the port and named
    four pairs — a helmet at type 34 is model 162, healing grass at 104 is 232,
    a save point at 227 is 355, a bull's head at 253 is 381 — all differing by
    exactly that. The sizes agree too: the grass comes out 384 x 211 x 416
    under the rule where the old assumption `MO.T[type]` gave it
    4176 x 4096 x 3808, which is what the player saw as "a big white thing
    where the grass should be".

    **From type 300 up the level decides the model**, which is now read off
    `model_of_type` (`0x80040568`) rather than guessed:

        type <  300   model = type + 0x100
        type >= 300   model = type + 0x100 + 32 * level

    and past `MO.T`'s 428 entries the numbering continues into `MOF.T`. So
    `MOF.T` is **banked, 32 models to a level**, and the arithmetic says
    level *n* uses bank *n + 4*. Over all 1424 placed objects of type 300 and
    above in the game, across 25 levels, the bank comes out as `level + 4`
    **every time** -- 992 entries is 31 banks, and the first four are not any
    level's.

    The old rule ignored the level, which is right only on level 0 and picks a
    model 32 banks wrong on level 1 and so on. 1423 of the 1424 land on an
    entry that holds a model; 1410 did before.
    """
    n = type_id + MODEL_BIAS
    if type_id >= LEVEL_BANKED:
        n += BANK * level
    return ("MO", n) if n < MO_COUNT else ("MOF", n - MO_COUNT)


def load(name, entry, path=None):
    data = TArc(path or ARCHIVES[name]).raw(entry)
    off = find_tmd(data)
    if off is None:
        raise ValueError(f"{name}[{entry}] holds no TMD")
    data = data[off:]
    idv, flags, nobj = struct.unpack_from("<3I", data, 0)
    if idv != 0x41:
        raise ValueError(f"{name}[{entry}] is not a TMD (id {idv:#x})")
    objs = [Obj(data, struct.unpack_from("<7i", data, HDR + 28 * i))
            for i in range(nobj)]
    return flags, objs


def render(objs, path, size=256, yaw=0.6, pitch=0.35, only=None):
    """Draw a model to a PNG so it can be looked at without an engine.

    Orthographic, painter's algorithm, flat shaded off the face normal. It
    exists because "which model is this" is a question no amount of reading the
    data answers, and the alternative -- building the Godot gallery and asking
    a person -- costs a round trip every time. Colours are the primitive's own
    when it carries them and grey when it does not; textures are ignored.

        python3 tools/tmd.py MO 282 png            the whole entry
        python3 tools/tmd.py MO 305 png 1          just its second object
    """
    import math
    tris = []
    for k, o in enumerate(objs):
        if only is not None and k != only:
            continue
        tint = [(1.0, 1.0, 1.0), (1.0, 0.55, 0.55), (0.55, 0.75, 1.0),
                (0.6, 1.0, 0.6)][k % 4]
        for pr in o.prims:
            v = [o.verts[i] for i in pr.verts if i < len(o.verts)]
            if len(v) < 3:
                continue
            faces = [v[:3]] + ([[v[0], v[2], v[3]]] if len(v) >= 4 else [])
            base = pr.rgb[0] if pr.rgb else (140, 140, 140)
            for f in faces:
                tris.append((f, base, tint))
    if not tris:
        return None
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    def project(v):
        x, y, z = v
        x, z = x * cy + z * sy, -x * sy + z * cy
        y, z = y * cp - z * sp, y * sp + z * cp
        return x, y, z

    pts = [project(v) for f, _c, _t in tris for v in f]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    lo = min(min(xs), min(ys))
    hi = max(max(xs), max(ys))
    span = max(hi - lo, 1)
    m = size * 0.08

    def to_px(p):
        return ((p[0] - lo) / span * (size - 2 * m) + m,
                (p[1] - lo) / span * (size - 2 * m) + m)

    px = [(24, 24, 28, 255)] * (size * size)
    order = []
    for f, base, tint in tris:
        pr3 = [project(v) for v in f]
        order.append((sum(q[2] for q in pr3) / 3.0, pr3, base, tint))
    order.sort(key=lambda r: -r[0])                 # far first
    for _z, pr3, base, tint in order:
        a, b, c = (to_px(q) for q in pr3)
        # a normal in screen space, for a little shading
        ux, uy = b[0] - a[0], b[1] - a[1]
        vx, vy = c[0] - a[0], c[1] - a[1]
        area = ux * vy - uy * vx
        if abs(area) < 0.5:
            continue
        shade = 0.55 + 0.45 * min(1.0, abs(area) / (size * size * 0.02))
        col = tuple(min(255, int(base[i] * tint[i] * shade)) for i in range(3))
        xmin = max(0, int(min(a[0], b[0], c[0])))
        xmax = min(size - 1, int(max(a[0], b[0], c[0])) + 1)
        ymin = max(0, int(min(a[1], b[1], c[1])))
        ymax = min(size - 1, int(max(a[1], b[1], c[1])) + 1)
        for yy in range(ymin, ymax + 1):
            for xx in range(xmin, xmax + 1):
                w0 = (b[0] - a[0]) * (yy - a[1]) - (b[1] - a[1]) * (xx - a[0])
                w1 = (c[0] - b[0]) * (yy - b[1]) - (c[1] - b[1]) * (xx - b[0])
                w2 = (a[0] - c[0]) * (yy - c[1]) - (a[1] - c[1]) * (xx - c[0])
                if (w0 >= 0 and w1 >= 0 and w2 >= 0) or \
                   (w0 <= 0 and w1 <= 0 and w2 <= 0):
                    px[yy * size + xx] = col + (255,)
    import tim
    tim.write_png(path, size, size, px)
    return path


def write_obj(path, obj, scale=1 / 256):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for x, y, z in obj.verts:
            f.write(f"v {x * scale:.5f} {-y * scale:.5f} {z * scale:.5f}\n")
        for pr in obj.prims:
            if len(pr.verts) >= 3 and max(pr.verts) < len(obj.verts):
                idx = " ".join(str(v + 1) for v in pr.verts)
                f.write(f"f {idx}\n")
    return path


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "RTMD"
    entry = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    flags, objs = load(name, entry)
    if len(sys.argv) > 3 and sys.argv[3] == "png":
        only = int(sys.argv[4]) if len(sys.argv) > 4 else None
        os.makedirs("out/tmd", exist_ok=True)
        tag = f"{name}_{entry}" + ("" if only is None else f"_{only}")
        print("wrote", render(objs, f"out/tmd/{tag}.png", only=only),
              f"-- {len(objs)} object(s)")
        sys.exit(0)
    if len(sys.argv) > 3:
        i = int(sys.argv[3])
        o = objs[i]
        print(f"{name}[{entry}] object {i}: {o.nv} vertices, {o.nn} normals, "
              f"{o.npr} primitives, scale {o.scale}")
        for pr in o.prims:
            print("   ", pr)
        if len(sys.argv) > 4:
            print("wrote", write_obj(f"out/tmd/{name}_{entry}_{i}.obj", o))
        sys.exit(0)

    import collections
    modes = collections.Counter()
    bad = tv = tp = 0
    for o in objs:
        bad += o.bad_indices()
        tv += o.nv
        tp += len(o.prims)
        for pr in o.prims:
            modes[(pr.mode, pr.flag)] += 1
    print(f"{name}[{entry}]: flags {flags:#x}, {len(objs)} objects, "
          f"{tv} vertices, {tp} primitives")
    print(f"vertex indices out of range: {bad}\n")
    print(f"{'mode':>6s} {'flag':>6s} {'count':>7s}  what")
    for (m, fl), n in sorted(modes.items(), key=lambda kv: -kv[1]):
        kind = ("quad" if m & 8 else "tri") + (" tex" if m & 4 else "") + \
               (" gouraud" if m & 0x10 else "") + ("" if not (fl & 1) else " unlit")
        print(f"  {m:#04x} {fl:#04x}   {n:7d}  {kind}")

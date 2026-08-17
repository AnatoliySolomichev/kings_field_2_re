#!/usr/bin/env python3
"""Build a whole level as geometry a modern engine can open.

    python3 tools/level3d.py 0                 out/godot/ -- obj, mtl, textures, project
    python3 tools/level3d.py 0 --cells 20      a 20x20 corner of it, for a quick look

Everything this needs is decoded (FORMATS.md section 4):

    model      RTMD.T[level], object cell[+5]      tools/tmd.py
    texture    the page and CLUT its primitives name, out of RTIM.T
    place at   cx * 2048 + 1024,  -128 * cell[+6],  cz * 2048 + 1024
    turned by  cell[+7] & 3, which is Ry(rot * 90 degrees)

**The rotation had to be recovered rather than read.** The four matrices at
`0x801aeb8c` are not clean quarter turns: the camera is already multiplied into
them and they are rebuilt every frame. What survives is the relation between
them -- `M1 = M0 . Ry(90)` holds row for row on all four -- so the tile's own
part is a quarter turn about Y, which in PlayStation axes sends `(x, y, z)` to
`(z, y, -x)`.

Axes: the PlayStation has Y pointing down and Z pointing away from the viewer;
an engine has Y up and -Z away. **Both** are negated, which is a half turn about
X and leaves handedness alone. Negating Y by itself was the first attempt, and
it is a mirror -- the level came out reflected left to right, which is obvious
once seen in the game and invisible in any map or top-down view, since those
are symmetric under exactly that flip.

Face winding is not assumed at all: each triangle is turned to agree with the
model's own normal, so the axis convention can change without breaking it.

One cell becomes 2.048 metres, which puts the player's eye at about 1.5.
"""
import math
import os
import struct
import sys

sys.path.insert(0, "tools")
import collision as coll                                             # noqa: E402
import gltf                                                           # noqa: E402
import placement                                                      # noqa: E402
import rtim                                                           # noqa: E402
import tim                                                            # noqa: E402
import tmd                                                            # noqa: E402

W, CELLB = 80, 10
CELL = 0x800
# Object types the game places but does not draw. See build_objects_gltf.
NOT_DRAWN = {299}
UNIT = 1000.0            # world units per metre
VOID = 0xF0              # cell[+5] at or above this is solid rock


def spin(v, rot):
    """Ry(rot * 90 degrees) in PlayStation axes."""
    x, y, z = v
    for _ in range(rot & 3):
        x, z = z, -x
    return x, y, z


def light_class(look, cls, rot):
    """The GTE lighting a cell's class applies: (direction, colour, background).

    A record is four 20-byte light-direction matrices, one per orientation, then
    the light-colour matrix at +0x50 and the background at +0x64. Each 20-byte
    block is five words of packed halfwords, which is the GTE's own matrix
    layout: R11R12, R13R21, R22R23, R31R32, R33.
    """
    base = cls * 108

    def mat(off):
        hw = struct.unpack_from("<10h", look, base + off)
        return (hw[0:3], hw[3:6], hw[6:9])
    return (mat(rot * 20), mat(0x50),
            [look[base + 0x64 + k] * 16 for k in range(3)])


def shade(normal, llm, lcm, bk):
    """One face's colour, as the GTE computes it. Never reaches black: the
    background term is added after the light, which is why nothing in the real
    game is unlit and why an engine light on top of this would be wrong."""
    ir = [max(0, min(0x7FFF, (llm[r][0] * normal[0] + llm[r][1] * normal[1]
                              + llm[r][2] * normal[2]) >> 12)) for r in range(3)]
    out = []
    for r in range(3):
        v = (bk[r] * 4096 + lcm[r][0] * ir[0] + lcm[r][1] * ir[1]
             + lcm[r][2] * ir[2]) >> 12
        out.append(max(0.0, min(1.0, v / 4096.0)))
    return out


def grid_of(lv):
    live = "out/grid_live_lv0.bin"
    if lv == 0 and os.path.exists(live):
        return open(live, "rb").read()          # level state included
    from maps import levels
    return dict(levels())[lv]


def build(lv, limit=None):
    grid = grid_of(lv)
    _flags, objs = tmd.load("RTMD", lv)
    vram = rtim.vram(lv)

    mats = {}                                    # (tpage, clut) -> name
    verts, uvs, norms, faces = [], [], [], {}
    n = 0
    span = range(min(limit, W)) if limit else range(W)
    for cz in span:
        for cx in span:
            c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
            sid = c[5]
            if sid >= VOID or sid >= len(objs):
                continue
            obj = objs[sid]
            if not obj.prims:
                continue
            n += 1
            rot = c[7] & 3
            ox, oy, oz = cx * CELL + CELL // 2, -128 * c[6], cz * CELL + CELL // 2
            base, nbase = len(verts), len(norms)
            for v in obj.verts:
                x, y, z = spin(v, rot)
                # a half turn about X: Y down becomes Y up, +Z away becomes -Z
                verts.append(((ox + x) / UNIT, -(oy + y) / UNIT, -(oz + z) / UNIT))
            for nv in obj.normals:
                x, y, z = spin(nv, rot)
                norms.append((x / 4096.0, -y / 4096.0, -z / 4096.0))
            for pr in obj.prims:
                if not pr.tex or len(pr.verts) < 3 or max(pr.verts) >= obj.nv:
                    continue
                key = (pr.tpage, pr.clut)
                mats.setdefault(key, f"tex_{pr.tpage:04x}_{pr.clut:04x}")
                uv0 = len(uvs)
                for u, v in pr.uvs:
                    uvs.append((u / 256.0, 1.0 - v / 256.0))
                idx = [base + i + 1 for i in pr.verts]
                t = [uv0 + i + 1 for i in range(len(pr.uvs))]
                nrm = [nbase + i + 1 for i in pr.norms if i < obj.nn] or [0]
                tri = ([(0, 1, 2), (1, 3, 2)] if pr.quad else [(0, 1, 2)])
                for a, b, cc in tri:
                    # Wind each triangle to agree with the model's own normal
                    # rather than with an assumption about TMD's convention --
                    # which is what let the axis fix above land without also
                    # having to reason about which way the faces then pointed.
                    order = (a, b, cc)
                    ni = nrm[0] - 1 - nbase
                    if 0 <= ni < len(obj.normals):
                        f = [verts[idx[i] - 1] for i in order]
                        gx = ((f[1][1] - f[0][1]) * (f[2][2] - f[0][2])
                              - (f[1][2] - f[0][2]) * (f[2][1] - f[0][1]))
                        gy = ((f[1][2] - f[0][2]) * (f[2][0] - f[0][0])
                              - (f[1][0] - f[0][0]) * (f[2][2] - f[0][2]))
                        gz = ((f[1][0] - f[0][0]) * (f[2][1] - f[0][1])
                              - (f[1][1] - f[0][1]) * (f[2][0] - f[0][0]))
                        nn = norms[nbase + ni]
                        if gx * nn[0] + gy * nn[1] + gz * nn[2] < 0:
                            order = (cc, b, a)
                    faces.setdefault(key, []).append(
                        tuple((idx[i], t[i], nrm[0]) for i in order))
    return verts, uvs, norms, faces, mats, vram, n


def build_gltf(lv, out="out/godot", limit=None):
    """The level as glTF: baked lighting, nearest sampling, no engine lights."""
    grid = grid_of(lv)
    _flags, objs = tmd.load("RTMD", lv)
    vram = rtim.vram(lv)
    look = open("out/tile_look.bin", "rb").read()
    g = gltf.Gltf()
    groups = {}
    span = range(min(limit, W)) if limit else range(W)
    ncell = 0
    for cz in span:
        for cx in span:
            c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
            sid = c[5]
            if sid >= VOID or sid >= len(objs) or not objs[sid].prims:
                continue
            obj = objs[sid]
            ncell += 1
            rot = c[7] & 3
            llm, lcm, bk = light_class(look, c[9] & 0x3F, rot)
            ox, oy, oz = cx * CELL + CELL // 2, -128 * c[6], cz * CELL + CELL // 2

            def place(v):
                x, y, z = spin(v, rot)
                return ((ox + x) / UNIT, -(oy + y) / UNIT, -(oz + z) / UNIT)

            for pr in obj.prims:
                if not pr.tex or len(pr.verts) < 3 or max(pr.verts) >= obj.nv:
                    continue
                ni = pr.norms[0] if pr.norms and pr.norms[0] < obj.nn else None
                raw = obj.normals[ni] if ni is not None else (0, -4096, 0)
                rgb = shade(raw, llm, lcm, bk)
                nx, ny, nz = spin(raw, rot)
                nrm = (nx / 4096.0, -ny / 4096.0, -nz / 4096.0)
                pts = [place(obj.verts[i]) for i in pr.verts]
                key = (pr.tpage, pr.clut)
                bag = groups.setdefault(key, ([], [], [], []))
                for a, b, cc in ([(0, 1, 2), (1, 3, 2)] if pr.quad
                                 else [(0, 1, 2)]):
                    order = (a, b, cc)
                    f = [pts[i] for i in order]
                    gx = ((f[1][1] - f[0][1]) * (f[2][2] - f[0][2])
                          - (f[1][2] - f[0][2]) * (f[2][1] - f[0][1]))
                    gy = ((f[1][2] - f[0][2]) * (f[2][0] - f[0][0])
                          - (f[1][0] - f[0][0]) * (f[2][2] - f[0][2]))
                    gz = ((f[1][0] - f[0][0]) * (f[2][1] - f[0][1])
                          - (f[1][1] - f[0][1]) * (f[2][0] - f[0][0]))
                    if gx * nrm[0] + gy * nrm[1] + gz * nrm[2] < 0:
                        order = (cc, b, a)
                    for i in order:
                        bag[0].append(pts[i])
                        bag[1].append(nrm)
                        u, v = pr.uvs[i]
                        bag[2].append((u / 256.0, v / 256.0))
                        bag[3].append((rgb[0], rgb[1], rgb[2], 1.0))

    os.makedirs(f"{out}/tex", exist_ok=True)
    prims, ntri = [], 0
    for (tpage, clut), (pos, nrm, uv, col) in groups.items():
        name = f"tex_{tpage:04x}_{clut:04x}"
        if not (tpage >> 7) & 3:
            tim.write_png(f"{out}/tex/{name}.png", 256, 256,
                          rtim.page4(vram, tpage, clut))
        m = g.material(name, f"tex/{name}.png")
        p = g.primitive(pos, nrm, uv, col)
        p["material"] = m
        prims.append(p)
        ntri += len(pos) // 3
    # No `-col` suffix: the level is not handed to a physics engine at all.
    # Movement runs the game's own collision (godot/collision.gd), which is the
    # only way ramps, stairs, steppable walls and drowning come out right.
    path, nbytes = g.write(f"{out}/level{lv:02d}.gltf", prims, f"level{lv}")
    print(f"level {lv}: {ncell} cells, {ntri} triangles, {len(prims)} materials, "
          f"{nbytes // 1024} KB of buffer -> {path}")
    return path


def write(lv, out="out/godot", limit=None):
    verts, uvs, norms, faces, mats, vram, ncell = build(lv, limit)
    os.makedirs(f"{out}/tex", exist_ok=True)
    for (tpage, clut), name in mats.items():
        if (tpage >> 7) & 3:                     # 8-bit or 15-bit page
            print(f"  note: {name} is not a 4-bit page, skipping its texture")
            continue
        tim.write_png(f"{out}/tex/{name}.png", 256, 256,
                      rtim.page4(vram, tpage, clut))

    with open(f"{out}/level{lv:02d}.mtl", "w") as f:
        for name in mats.values():
            f.write(f"newmtl {name}\nKd 1 1 1\nKa 1 1 1\nd 1\nillum 1\n"
                    f"map_Kd tex/{name}.png\n\n")

    obj = f"{out}/level{lv:02d}.obj"
    ntri = 0
    with open(obj, "w") as f:
        f.write(f"# King's Field II, level {lv}: {ncell} cells\n")
        f.write(f"mtllib level{lv:02d}.mtl\n")
        for x, y, z in verts:
            f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
        for u, v in uvs:
            f.write(f"vt {u:.5f} {v:.5f}\n")
        for x, y, z in norms:
            f.write(f"vn {x:.4f} {y:.4f} {z:.4f}\n")
        for key, tris in faces.items():
            f.write(f"usemtl {mats[key]}\no {mats[key]}\n")
            for tri in tris:
                f.write("f " + " ".join(f"{a}/{b}/{c}" for a, b, c in tri) + "\n")
                ntri += 1
    print(f"level {lv}: {ncell} cells, {len(verts)} vertices, {ntri} triangles, "
          f"{len(mats)} textures -> {obj}")
    return obj, ncell, ntri


# `importer_defaults` matters more than it looks. Left alone, Godot sees the
# textures used in 3D and re-imports them mipmapped and VRAM-compressed, which
# on sixteen-colour pixel art is ruinous -- block compression has nothing to
# work with and the brickwork turns to mush.
def build_collision_gltf(lv, out="out/godot"):
    """The game's own collision, drawn as translucent quads.

    Not for walking on -- the level mesh does that -- but for *looking at*. This
    is where `tools/collision.py` says the game blocks you, and the interesting
    places are where it disagrees with what is drawn: a wall you can see through,
    a room the geometry reaches and the collision seals off.
    """
    lvl = coll.Level(lv)
    g = gltf.Gltf()
    pos, nrm, uv, col = [], [], [], []
    n = 0
    for cx, cz, face, off, lo, hi in coll.walls(lv, lvl):
        n += 1
        x0, z0 = cx * CELL, cz * CELL
        if face in (0, 2):
            x = x0 + (off if face == 0 else CELL - off)
            quad = [(x, lo, z0), (x, lo, z0 + CELL),
                    (x, hi, z0 + CELL), (x, hi, z0)]
            nv = (1.0, 0.0, 0.0)
        else:
            z = z0 + (off if face == 3 else CELL - off)
            quad = [(x0, lo, z), (x0 + CELL, lo, z),
                    (x0 + CELL, hi, z), (x0, hi, z)]
            nv = (0.0, 0.0, 1.0)
        p = [(x / UNIT, -y / UNIT, -z / UNIT) for x, y, z in quad]
        for a, b, c in ((0, 1, 2), (0, 2, 3)):
            for i in (a, b, c):
                pos.append(p[i])
                nrm.append(nv)
                uv.append((0.0, 0.0))
                col.append((1.0, 1.0, 1.0, 1.0))
    prim = g.primitive(pos, nrm, uv, col)
    prim["material"] = g.plain("collision", (1.0, 0.25, 0.2, 0.35))
    path, nbytes = g.write(f"{out}/collision{lv:02d}.gltf", [prim],
                           f"collision{lv}")
    print(f"collision overlay: {n} wall planes, {len(pos) // 3} triangles, "
          f"{nbytes // 1024} KB -> {path}")
    return path


SNAP_VRAM = "out/snap/b.vram"
SNAP_RAM = "out/snap/b.ram"
OBJECT_TABLE, OBJECT_STRIDE, OBJECT_SLOTS = 0x80191A5C, 0x44, 396


def live_scales(lv):
    """Each placed object's scale, out of the live table in a RAM snapshot.

    The scale is **per object, not per type**, and it is not in the disc record:
    `+0x2c` of the live record at `object_table` carries it, `0x1000` being 1.0.
    Across level 0 it reads x1.00 on 271 objects, **x0.00 on 59**, x1.99 on 34
    and a scatter of values between on the graves — so a good part of what the
    port drew at the wrong size was drawn at the wrong size, and 59 things it
    drew are not drawn by the game at all.

    Like the object textures, this is taken from a snapshot because the code
    that fills it has not been found. It is the game's own state, obtained by
    looking rather than by understanding, and it only applies to level 0.
    """
    if lv != 0 or not os.path.exists(SNAP_RAM):
        return {}
    ram = open(SNAP_RAM, "rb").read()
    out = {}
    for k in range(OBJECT_SLOTS):
        off = (OBJECT_TABLE + k * OBJECT_STRIDE) & 0x1FFFFF
        tid = struct.unpack_from("<H", ram, off + 6)[0]
        if tid in (0xFFFF, 0xFFFE):
            continue
        out[k] = struct.unpack_from("<h", ram, off + 0x2C)[0]
    return out


def object_vram(lv):
    """VRAM for the objects, which is not all in `RTIM.T[lv]`.

    The placed objects want texture pages `0x0b` to `0x0f` — VRAM from x=704
    across — for 57 119 of their primitives, and `RTIM.T[lv]` leaves that whole
    region empty. In the running game it is full, so something else loads it and
    **we have not found what**: the bytes are not a verbatim run in any of the
    nine archives.

    Until that is found, those pages are taken from a RAM snapshot. This is not
    a reading and it is not fitted either — it is the game's own VRAM, obtained
    by looking rather than by understanding — and it is why objects that came
    out white now have their textures. Anything built without `out/snap/b.vram`
    still gets the white, which is the honest failure rather than a silent one.
    """
    v = bytearray(rtim.vram(lv))
    if not os.path.exists(SNAP_VRAM):
        return bytes(v)
    snap = open(SNAP_VRAM, "rb").read()
    filled = 0
    for page in range(32):
        x0, y0 = (page & 0xF) * 64, ((page >> 4) & 1) * 256
        here = any(v[(r * 1024 + c) * 2:(r * 1024 + c) * 2 + 2] != b"\0\0"
                   for r in range(y0, y0 + 256, 8)
                   for c in range(x0, x0 + 64, 4))
        if here:
            continue
        for r in range(y0, y0 + 256):
            a = (r * 1024 + x0) * 2
            v[a:a + 128] = snap[a:a + 128]
        filled += 1
    if filled:
        print(f"object textures: {filled} pages RTIM leaves empty, taken from "
              f"{SNAP_VRAM} — the archive that loads them is not found yet")
    return bytes(v)


def emit_object(objs, place, colour, groups, normal_of=None):
    """Append one model's triangles into `groups`, keyed by (tpage, clut).

    **Shared deliberately.** The world build and the catalogue each had their own
    copy of this loop and the copies drifted: the catalogue never turned a
    triangle to agree with the model's own normal, so about half of every model
    faced away from the camera and was culled. A player looking at the same
    helmet in both said it was whole in the world and torn into layers in the
    catalogue, with "some polygons transparent" -- which is exactly what a
    back-facing triangle looks like against a single-sided material.

    The other copy also had `if i >= len(pts): continue` inside the vertex loop,
    which can emit two vertices for a triangle and shift every triangle after it
    in that group. One skipped vertex corrupted the rest of the model.

    `place` maps a model vertex to world space, `colour` gives a primitive its
    rgb, and `normal_of` maps a model normal the same way `place` maps a vertex.
    """
    for obj in objs:
        for pr in obj.prims:
            if not pr.tex or len(pr.verts) < 3 or max(pr.verts) >= obj.nv:
                continue
            if len(set(pr.verts)) < 3:
                continue
            ni = pr.norms[0] if pr.norms and pr.norms[0] < obj.nn else None
            raw = obj.normals[ni] if ni is not None else (0, -4096, 0)
            nrm = normal_of(raw) if normal_of else (raw[0] / 4096.0,
                                                    -raw[1] / 4096.0,
                                                    -raw[2] / 4096.0)
            rgb = colour(raw)
            pts = [place(obj.verts[i]) for i in pr.verts]
            if len(pts) < (4 if pr.quad else 3):
                continue
            bag = groups.setdefault((pr.tpage, pr.clut), ([], [], [], []))
            # No winding correction: the materials are double-sided, because the
            # PlayStation does not cull and these models rely on it. Turning
            # each triangle to agree with its own normal was tried and made
            # things visibly worse -- the per-face normal is not a reliable
            # guide here.
            for a, b, c in ([(0, 1, 2), (1, 3, 2)] if pr.quad else [(0, 1, 2)]):
                for i in (a, b, c):
                    bag[0].append(pts[i])
                    bag[1].append(nrm)
                    u, v = pr.uvs[i]
                    bag[2].append((u / 256.0, v / 256.0))
                    bag[3].append((rgb[0], rgb[1], rgb[2], 1.0))


def build_objects_gltf(lv, out="out/godot"):
    """Everything standing on the level: doors, chests, trees, save points.

    These are not tiles. The 24-byte placement records in `FDAT.T` entry
    `3n + 1` name a type id, a cell, a fine offset inside it and a rotation, and
    the model is **`MO.T[type + 128]`**, continuing into `MOF.T` past its 428
    entries. The 128 was measured, not reasoned: a player named four pairs from
    the gallery and all four differed by exactly that. `MO.T[type]`, which this
    used before and which nothing had ever checked, put a two-cell model where
    the healing grass should be and armour where the doors are.

    Height is not in the record: an object stands on the terrain, at
    `-128 * cell[+6]`, the same rule as everything else here.

    **Type 299 is not drawn.** `MO.T[299]` is a box two cells across and two
    cells tall carrying fourteen primitives — a hundred times coarser than the
    next coarsest model in the game — and every one of its **76 instances across
    all 28 levels carries a text index**, which is exactly the number of readable
    things `tools/readables.py` finds. It is the volume that says "an inscription
    can be read here", and it stands on the same cell as the object that is
    actually there: type 253 at level 0 (47,12), type 301 at (49,19), the *Broken
    Cart*. Drawing it put a stone column over both of them, which is how this was
    caught — a player looked at the port beside the emulator and said the bull's
    head and the cart had turned into pillars.
    """
    grid = grid_of(lv)
    vram = object_vram(lv)
    look = open("out/tile_look.bin", "rb").read()
    g = gltf.Gltf()
    groups = {}
    placed = missing = 0
    scales = live_scales(lv)
    hidden = 0
    for o in placement.objects(lv):
        if o["type"] in NOT_DRAWN:
            continue
        # x0.00 means the game does not draw it. 59 of level 0's objects.
        sc = scales.get(o["slot"], 0x1000)
        if sc == 0:
            hidden += 1
            continue
        try:
            _flags, objs = tmd.load(*tmd.model_of(o["type"]))
        except Exception:
            missing += 1
            continue
        cx, cz = o["cx"], o["cz"]
        if not (0 <= cx < W and 0 <= cz < W):
            continue
        c = grid[(cz * W + cx) * CELLB:(cz * W + cx) * CELLB + CELLB]
        oy = -128 * c[6]
        llm, lcm, bk = light_class(look, c[9] & 0x3F, c[7] & 3)
        # The record stores the rotation the way the loader will *negate* it:
        # `load_object_placement` does `negu` then masks to 0xfff before writing
        # the live record, so the disc value is the negative of the angle the
        # object actually stands at.
        ang = (-o["rot"] % 4096) / 4096.0 * 2.0 * math.pi
        ca, sa = math.cos(ang), math.sin(ang)
        placed += 1

        f = sc / 4096.0

        def place(v, f=f):
            x, y, z = (c * f for c in v)
            rx = x * ca + z * sa
            rz = -x * sa + z * ca
            return ((o["x"] + rx) / UNIT, -(oy + y) / UNIT, -(o["z"] + rz) / UNIT)

        def spin_normal(n):
            nx, ny, nz = n
            return ((nx * ca + nz * sa) / 4096.0, -ny / 4096.0,
                    -(-nx * sa + nz * ca) / 4096.0)

        emit_object(objs, place, lambda raw: shade(raw, llm, lcm, bk), groups,
                    spin_normal)

    os.makedirs(f"{out}/tex", exist_ok=True)
    prims, ntri = [], 0
    for (tpage, clut), (pos, nrm, uv, col) in groups.items():
        name = f"tex_{tpage:04x}_{clut:04x}"
        path = f"{out}/tex/{name}.png"
        if not (tpage >> 7) & 3 and not os.path.exists(path):
            tim.write_png(path, 256, 256, rtim.page4(vram, tpage, clut))
        m = (g.material(name, f"tex/{name}.png", double=True)
             if os.path.exists(path)
             else g.plain(name + "_flat", (0.8, 0.75, 0.7, 1.0)))
        p = g.primitive(pos, nrm, uv, col)
        p["material"] = m
        prims.append(p)
        ntri += len(pos) // 3
    if not prims:
        print("no objects placed")
        return None
    path, nbytes = g.write(f"{out}/objects{lv:02d}.gltf", prims, f"objects{lv}")
    print(f"objects: {placed} placed, {missing} without a model, {ntri} triangles, "
          f"{len(prims)} materials -> {path}")
    return path


PROJECT = """config_version=5

[application]
config/name="King's Field II - level {lv}"
run/main_scene="res://world.tscn"
config/features=PackedStringArray("4.2", "GL Compatibility")

[rendering]
renderer/rendering_method="gl_compatibility"
textures/canvas_textures/default_texture_filter=0

[importer_defaults]

texture={{
"compress/mode": 0,
"detect_3d/compress_to": 0,
"mipmaps/generate": false,
"process/fix_alpha_border": false
}}
"""

# A .gltf imports as a scene, so it is instanced rather than assigned to a mesh.
# There are **no lights**: the materials are unlit and carry the game's own
# lighting in their vertex colours. Adding a light here would shade the level a
# second time, over shading it already has.
SCENE = """[gd_scene load_steps={load_steps} format=3]

[ext_resource type="PackedScene" path="res://level{lv:02d}.gltf" id="1"]
[ext_resource type="Script" path="res://player.gd" id="2"]
[ext_resource type="PackedScene" path="res://collision{lv:02d}.gltf" id="3"]
[ext_resource type="PackedScene" path="res://objects{lv:02d}.gltf" id="4"]
[ext_resource type="Script" path="res://ghost.gd" id="5"]
[ext_resource type="Script" path="res://labels.gd" id="6"]
{gallery_res}

[sub_resource type="Environment" id="Env"]
background_mode = 1
background_color = Color(0.02, 0.02, 0.03, 1)
ambient_light_source = 0

[node name="World" type="Node3D"]

[node name="Level" parent="." instance=ExtResource("1")]

[node name="Objects" parent="." instance=ExtResource("4")]

[node name="CollisionView" parent="." instance=ExtResource("3")]
visible = false

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Env")

[node name="Player" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {px:.2f}, {py:.2f}, {pz:.2f})
script = ExtResource("2")

[node name="Camera" type="Camera3D" parent="Player"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1.6, 0)
current = true
far = 400.0

[node name="Ghost" type="Node3D" parent="."]
script = ExtResource("5")

[node name="Gallery" type="Node3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 400, 0)
visible = false
{gallery_nodes}

[node name="Labels" type="Node3D" parent="."]
script = ExtResource("6")

[node name="UI" type="CanvasLayer" parent="."]

[node name="Hud" type="Label" parent="UI"]
offset_left = 12.0
offset_top = 8.0
text = "F  walk / fly    N  object labels    K  the model gallery"

[node name="Compare" type="Label" parent="UI"]
offset_left = 12.0
offset_top = 96.0
text = "C  compare with the emulator"
"""

PLAYER = '''extends CharacterBody3D
# Two ways round the level, because both are needed.
#
#   WALK  collides with the level mesh, has gravity and a step up
#   FLY   passes through everything -- which is the point: this level has
#         rooms the game never lets you reach, and the only way to look at
#         them is to go through the wall
#
#   F   walk / fly          G   show the game\'s own collision
#   Space  jump             Shift  faster        Escape  release the mouse
#
# The readout gives the cell you are standing in, in the game\'s own numbering,
# so anything found here can be pointed at in the data.

const WALK := 4.5
const FLY := 9.0
const GRAVITY := 18.0
const JUMP := 6.0
const CELL := 2.048

var flying := true
var pitch := 0.0

func _ready() -> void:
    Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
    _ensure_collision(get_node_or_null("../Level"))
    _refresh()

func _ensure_collision(n: Node) -> void:
    # The `-col` suffix on the glTF node should have built this at import time.
    # Doing it again here takes a moment and removes the dependence on an import
    # hint quietly not applying, which would leave the level with no floor at all.
    if n == null:
        return
    if n is MeshInstance3D and n.get_child_count() == 0:
        n.create_trimesh_collision()
    for c in n.get_children():
        _ensure_collision(c)

func _refresh() -> void:
    $Shape.disabled = flying
    var hud := get_node_or_null("../UI/Hud")
    if hud:
        var cx := int(floor(position.x / CELL))
        var cz := int(floor(-position.z / CELL))
        hud.text = "%s   cell (%d, %d)   height %.2f\\nF walk/fly   G collision   Esc mouse" % [
            "FLY" if flying else "WALK", cx, cz, position.y]

func _unhandled_input(e: InputEvent) -> void:
    if e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
        rotate_y(-e.relative.x * 0.003)
        pitch = clamp(pitch - e.relative.y * 0.003, -1.4, 1.4)
        $Camera.rotation.x = pitch
    elif e is InputEventKey and e.pressed and not e.echo:
        match e.keycode:
            KEY_F:
                flying = not flying
                velocity = Vector3.ZERO
                _refresh()
            KEY_G:
                var v := get_node_or_null("../CollisionView")
                if v:
                    v.visible = not v.visible
            KEY_ESCAPE:
                Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
            KEY_TAB:
                Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _physics_process(dt: float) -> void:
    var dir := Vector3.ZERO
    if Input.is_key_pressed(KEY_W): dir -= transform.basis.z
    if Input.is_key_pressed(KEY_S): dir += transform.basis.z
    if Input.is_key_pressed(KEY_A): dir -= transform.basis.x
    if Input.is_key_pressed(KEY_D): dir += transform.basis.x
    var fast := 3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0

    if flying:
        if Input.is_key_pressed(KEY_Q): dir -= Vector3.UP
        if Input.is_key_pressed(KEY_E): dir += Vector3.UP
        # moved directly, so nothing is asked of the physics engine and
        # nothing stops us
        position += dir.normalized() * FLY * fast * dt
    else:
        var flat := Vector3(dir.x, 0, dir.z).normalized()
        velocity.x = flat.x * WALK * fast
        velocity.z = flat.z * WALK * fast
        velocity.y -= GRAVITY * dt
        if is_on_floor() and Input.is_key_pressed(KEY_SPACE):
            velocity.y = JUMP
        move_and_slide()
    _refresh()
'''


def project(lv, out="out/godot", start=(57, 4)):
    """Write the Godot side: the scene, the scripts, and the collision data.

    The scripts live in `godot/` rather than in string literals here, so they
    can be edited as code.
    """
    import shutil
    import gdcoll
    grid = grid_of(lv)
    cx, cz = start
    h = grid[(cz * W + cx) * CELLB + 6]
    px = (cx * CELL + CELL // 2) / UNIT
    pz = -(cz * CELL + CELL // 2) / UNIT
    py = 128 * h / UNIT                          # the feet; the camera sits 1.6 up
    os.makedirs(out, exist_ok=True)
    open(f"{out}/project.godot", "w").write(PROJECT.format(lv=lv))
    # The gallery decides how many pieces there are -- Godot takes at most 256
    # surfaces in a mesh -- so it is built before the scene that names them.
    import gallery
    import glob
    gallery.build(out=out)
    gallery.world_labels(lv, out)
    pieces = sorted(glob.glob(f"{out}/gallery*.gltf"))
    res = "\n".join(f'[ext_resource type="PackedScene" '
                    f'path="res://{os.path.basename(q)}" id="{7 + i}"]'
                    for i, q in enumerate(pieces))
    nodes = "\n".join(f'\n[node name="g{i}" parent="Gallery" '
                       f'instance=ExtResource("{7 + i}")]'
                       for i in range(len(pieces)))
    open(f"{out}/world.tscn", "w").write(
        SCENE.format(lv=lv, px=px, py=py, pz=pz, gallery_res=res,
                     gallery_nodes=nodes, load_steps=8 + len(pieces)))
    for name in ("player.gd", "collision.gd", "selftest.gd", "ghost.gd",
                 "labels.gd"):
        shutil.copyfile(f"godot/{name}", f"{out}/{name}")
    gdcoll.export(lv, out)
    print(f"godot project in {out}/ — player starts in cell ({cx},{cz})")


def verify(out="out/godot"):
    """Load the project headless and report anything Godot complains about.

    Worth the seconds it costs: `out/godot` is generated, but it is also a live
    Godot project, and the editor writes into it. A stray keystroke into the
    script editor once left eighteen Cyrillic characters in the middle of
    `collision.gd`, which no amount of reading the source would have found --
    the source was clean and only the copy was broken.
    """
    import shutil
    import subprocess
    godot = shutil.which("godot-4") or shutil.which("godot")
    if not godot:
        print("godot not found; skipping the load check")
        return True
    bad = []
    # --import first, always. Godot only refreshes `.godot/imported/` when the
    # editor runs, so a rebuilt mesh beside a stale cache is shown as the old
    # one, silently. See gallery.reimport.
    for args in (["--import"], ["--quit-after", "60"]):
        r = subprocess.run([godot, "--headless", "--path", out] + args,
                           capture_output=True, text=True, timeout=900)
        for line in (r.stdout + r.stderr).splitlines():
            if "SCRIPT ERROR" in line or line.startswith("ERROR:"):
                bad.append(line.strip())
    if bad:
        print(f"godot reported {len(bad)} problems:")
        for line in bad[:8]:
            print("   " + line)
        return False
    # And then make it answer a question, because loading cleanly only says the
    # syntax is intact. `selftest.gd` replays the frames `tools/movement.py`
    # produced and prints how many of them the GDScript copy reproduced.
    r = subprocess.run([godot, "--headless", "--path", out,
                        "--script", "res://selftest.gd"],
                       capture_output=True, text=True, timeout=900)
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith(("loaded:", "movement:", "FAIL", "  first")):
            print("   " + line.strip())
    if r.returncode != 0:
        print("the port and the Python model disagree")
        return False
    print("godot loads the project cleanly")
    return True


if __name__ == "__main__":
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    limit = None
    if "--cells" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--cells") + 1])
    if "--obj" in sys.argv:
        write(lv, limit=limit)            # the flat, unlit OBJ, kept for viewers
    else:
        build_gltf(lv, limit=limit)
        build_objects_gltf(lv)
        build_collision_gltf(lv)
    project(lv)
    if "--no-check" not in sys.argv:
        verify()

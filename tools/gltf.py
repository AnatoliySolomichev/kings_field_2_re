#!/usr/bin/env python3
"""A very small glTF 2.0 writer: triangle soup with textures and vertex colour.

Written because OBJ cannot carry the one thing this project needs most. The
game's lighting is per cell and per face — `cell[+9] & 0x3f` picks a class whose
matrices the GTE applies to each face normal — and once that is computed there
is nowhere to put it in an OBJ. Godot ignores the vertex-colour extension.

So: glTF, with

  * `COLOR_0` carrying the baked light, so the picture does not depend on any
    light placed in the scene;
  * `KHR_materials_unlit`, for the same reason — the shading is already in the
    colours and an engine light on top of it would be wrong twice;
  * `NEAREST` sampling, because these are sixteen-colour textures and smoothing
    them is what makes a PlayStation level look like a phone game.

Vertices are not shared. Faces are flat-shaded with a colour of their own, so
sharing them would mean averaging colours across a corner, which is exactly the
softening this is trying to avoid.
"""
import json
import os
import struct

NEAREST = 9728
FLOAT, UINT = 5126, 5125
ARRAY_BUFFER, ELEMENT_BUFFER = 34962, 34963


class Gltf:
    def __init__(self):
        self.buf = bytearray()
        self.views, self.accessors = [], []
        self.meshes, self.materials, self.textures = [], [], []
        self.images, self.samplers = [], [{"magFilter": NEAREST,
                                           "minFilter": NEAREST}]

    def _view(self, data, target):
        while len(self.buf) % 4:
            self.buf.append(0)
        off = len(self.buf)
        self.buf += data
        self.views.append({"buffer": 0, "byteOffset": off,
                           "byteLength": len(data), "target": target})
        return len(self.views) - 1

    def _acc(self, data, kind, comp, count, target, mn=None, mx=None):
        a = {"bufferView": self._view(data, target), "componentType": comp,
             "count": count, "type": kind}
        if mn is not None:
            a["min"], a["max"] = mn, mx
        self.accessors.append(a)
        return len(self.accessors) - 1

    def material(self, name, png, double=False):
        """`double` draws both faces.

        The PlayStation has **no backface culling in hardware** -- what a game
        skips, it skips in software with the GTE -- and the object models rely
        on that: walk round a figure in the game and it is solid from every
        side. Culled here, about half of every model vanished and the rest read
        as loose plates, which a player described as a boy who "splits into
        layers" from some angles and has "transparent polygons".

        Trying to fix that by turning each triangle to face the way its own
        normal does made it *worse*, because the per-face normal is not a
        reliable guide for these models. Not culling at all is both simpler and
        what the console does. It costs nothing here: the port's materials are
        unlit and carry baked vertex colour, so which way a face points has no
        effect on what it looks like.
        """
        self.images.append({"uri": png})
        self.textures.append({"sampler": 0, "source": len(self.images) - 1})
        self.materials.append({
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": len(self.textures) - 1},
                "metallicFactor": 0.0, "roughnessFactor": 1.0},
            "alphaMode": "MASK", "alphaCutoff": 0.5,
            "doubleSided": bool(double),
            "extensions": {"KHR_materials_unlit": {}}})
        return len(self.materials) - 1

    def plain(self, name, rgba):
        """An untextured material -- for the collision overlay, which is not a
        surface anyone textured but a fact about where the game lets you walk."""
        self.materials.append({
            "name": name,
            "pbrMetallicRoughness": {"baseColorFactor": list(rgba),
                                     "metallicFactor": 0.0,
                                     "roughnessFactor": 1.0},
            "alphaMode": "BLEND", "doubleSided": True,
            "extensions": {"KHR_materials_unlit": {}}})
        return len(self.materials) - 1

    def primitive(self, pos, nrm, uv, col):
        """Each list is one entry per vertex, three vertices to a triangle."""
        n = len(pos)
        xs = [p[0] for p in pos]
        ys = [p[1] for p in pos]
        zs = [p[2] for p in pos]
        pa = self._acc(struct.pack(f"<{n * 3}f", *[c for p in pos for c in p]),
                       "VEC3", FLOAT, n, ARRAY_BUFFER,
                       [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
        na = self._acc(struct.pack(f"<{n * 3}f", *[c for p in nrm for c in p]),
                       "VEC3", FLOAT, n, ARRAY_BUFFER)
        ta = self._acc(struct.pack(f"<{n * 2}f", *[c for p in uv for c in p]),
                       "VEC2", FLOAT, n, ARRAY_BUFFER)
        ca = self._acc(struct.pack(f"<{n * 4}f", *[c for p in col for c in p]),
                       "VEC4", FLOAT, n, ARRAY_BUFFER)
        ia = self._acc(struct.pack(f"<{n}I", *range(n)), "SCALAR", UINT, n,
                       ELEMENT_BUFFER)
        return {"attributes": {"POSITION": pa, "NORMAL": na,
                               "TEXCOORD_0": ta, "COLOR_0": ca},
                "indices": ia}

    def write(self, path, prims, name="level", node=None):
        """`node` may differ from the mesh name: Godot reads import hints off
        the node, and a name ending in `-col` is what gives the level a
        collision body without a line of scene setup."""
        self.meshes.append({"name": name, "primitives": prims})
        return self._dump(path, [{"mesh": len(self.meshes) - 1,
                                  "name": node or name}])

    def write_nodes(self, path, items):
        """Many nodes, each with its own mesh and its own place.

        `items` is [(name, primitives, translation, rotation)], the rotation a
        quaternion (x, y, z, w). Godot imports each as a child it can find by
        name, which is what lets a script show and hide creatures one at a time.
        """
        nodes = []
        for name, prims, tr, rot in items:
            self.meshes.append({"name": name, "primitives": prims})
            nodes.append({"mesh": len(self.meshes) - 1, "name": name,
                          "translation": list(tr), "rotation": list(rot)})
        return self._dump(path, nodes)

    def _dump(self, path, nodes):
        base = os.path.basename(path).rsplit(".", 1)[0] + ".bin"
        doc = {
            "asset": {"version": "2.0",
                      "generator": "kings_field_2 tools/gltf.py"},
            "extensionsUsed": ["KHR_materials_unlit"],
            "scene": 0,
            "scenes": [{"nodes": list(range(len(nodes)))}],
            "nodes": nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "textures": self.textures,
            "images": self.images,
            "samplers": self.samplers,
            "accessors": self.accessors,
            "bufferViews": self.views,
            "buffers": [{"uri": base, "byteLength": len(self.buf)}],
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(doc, f, separators=(",", ":"))
        with open(os.path.join(os.path.dirname(path), base), "wb") as f:
            f.write(self.buf)
        return path, len(self.buf)

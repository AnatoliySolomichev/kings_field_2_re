class_name KFAnim
# A creature's animation: vertex poses picked by its animation clock.
# tools/anim.py is the same in Python, with the reading; FORMATS.md "A
# creature's animation".
#
# draw_model_plain hands 0x800431e8 the model, the animation (+0xc, animated
# only under 0x80) and the clock (+0x18). The animation's segments add up
# their lengths until the clock falls in one; its start is the model's
# vertices with the segment's start poses written over them, and every vertex
# the target pose names moves towards it by ((target - v) * t) >> 12.
#
# @exe game

const SKIP := -0x8000

static var models := {}          # model -> {base, anims, poses}


# @port data -- reads animNN.json: each model's base vertices, animations and poses, as tools/anim.py takes them
static func load_from(path: String) -> bool:
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	for key in d["models"]:
		var md: Dictionary = d["models"][key]
		var base := []
		for v in md["base"]:
			base.append(Vector3i(int(v[0]), int(v[1]), int(v[2])))
		var poses := []
		for p in md["poses"]:
			var entries := []
			for e in p:
				if int(e[0]) == SKIP:
					entries.append(-int(e[1]) - 1)            # a run: -k - 1
				else:
					entries.append(Vector3i(int(e[0]), int(e[1]), int(e[2])))
			poses.append(entries)
		models[int(key)] = {"base": base, "anims": md["anims"], "poses": poses}
	return true


# @port helper -- a halfword, sign-extended: the game's vertices are s16
static func _s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v >= 0x8000 else v


# 0x80042cac: [segment, factor].
# @orig game:0x80042cac anim_segment  status:verified -- the segment of 11 of 11 creatures' caches in the snapshots, tools/anim.py
static func pick(segs: Array, clock: int) -> Array:
	var end := 0
	var start := 0
	for i in segs.size():
		var sg: Array = segs[i]
		var ln := int(sg[1])
		end += ln
		if clock < end:
			var t := ((clock - start) << 12) / ln
			return [i, 0x1000 - t if int(sg[0]) else t]
		start = end
	return [segs.size() - 1, 0x1000]


# 0x80042d70 and 0x80042e34: a pose's vertices written over, its runs skipped.
# @orig game:0x80042d70 pose_start  status:verified -- with the copy of the base vertices() makes first
# @orig game:0x80042e34 pose_overlay  status:verified -- the start vertices of 11 of 11 creatures' caches
static func overlay(verts: Array, pose: Array) -> void:
	var i := 0
	for e in pose:
		if e is int:
			i += -int(e) - 1
		else:
			verts[i] = e
			i += 1


# 0x80042eb0: every vertex the pose names moves by ((target - v) * t) >> 12.
# @orig game:0x80042eb0 pose_blend  status:verified -- 3 snapshots' last drawn creature, tools/anim.py
static func blend(verts: Array, pose: Array, t: int) -> void:
	var i := 0
	for e in pose:
		if e is int:
			i += -int(e) - 1
			continue
		var v: Vector3i = verts[i]
		var g: Vector3i = e
		verts[i] = Vector3i(_s16(v.x + ((_s16(g.x - v.x) * t) >> 12)),
			_s16(v.y + ((_s16(g.y - v.y) * t) >> 12)),
			_s16(v.z + ((_s16(g.z - v.z) * t) >> 12)))
		i += 1


# The model's first-object vertices for this animation and clock (0x800431e8).
# @orig game:0x800431e8 model_animate  status:verified -- tools/anim.py against the snapshots
static func vertices(model: int, anim: int, clock: int) -> Array:
	var md: Dictionary = models[model]
	var v: Array = (md["base"] as Array).duplicate()
	if anim >= 0x80 or anim >= (md["anims"] as Array).size():
		return v
	var segs: Array = md["anims"][anim]
	var pt := pick(segs, clock)
	var sg: Array = segs[int(pt[0])]
	for p in sg[3]:
		overlay(v, md["poses"][int(p)])
	blend(v, md["poses"][int(sg[2])], int(pt[1]))
	return v


# A node's meshes made so their vertices can be moved: each imported vertex is
# matched back to the model vertex it came from by its position -- the
# creatures' first objects have no two vertices in the same place but for one
# pair in model 32 -- and the surfaces copied into meshes of the node's own.
# {} when the model has no animation.
# @port engine -- makes a node's meshes movable, each vertex matched to the model's
static func skin(node: Node3D, model: int) -> Dictionary:
	if not models.has(model):
		return {}
	var base: Array = models[model]["base"]
	var where := {}
	for i in base.size():
		if not where.has(base[i]):
			where[base[i]] = i
	var parts := []
	var found: Array = node.find_children("*", "MeshInstance3D", true, false)
	if node is MeshInstance3D:
		found.push_front(node)          # the glTF node is the mesh itself
	for mi in found:
		var mesh: Mesh = (mi as MeshInstance3D).mesh
		if mesh == null:
			continue
		var own := ArrayMesh.new()
		var surfaces := []
		for s in mesh.get_surface_count():
			var arrays := mesh.surface_get_arrays(s)
			var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var idx := PackedInt32Array()
			idx.resize(verts.size())
			for i in verts.size():
				var v := verts[i]
				var key := Vector3i(roundi(v.x * 1000.0), roundi(-v.y * 1000.0),
					roundi(-v.z * 1000.0))
				idx[i] = where.get(key, -1)
			# the active material: scroll.gd may have put its shader over the
			# imported one, and a new mesh on the node drops the override
			surfaces.append({"arrays": arrays, "idx": idx,
				"material": (mi as MeshInstance3D).get_active_material(s)})
		(mi as MeshInstance3D).mesh = own
		parts.append({"mesh": own, "surfaces": surfaces})
	return {"model": model, "parts": parts, "anim": -1, "clock": -1}


# A skin at this animation and clock: the vertices moved, the surfaces made
# again, when either has changed.
# @port engine -- moves a skin's vertices to vertices() and rebuilds its surfaces
static func animate(sk: Dictionary, anim: int, clock: int) -> void:
	if anim == int(sk["anim"]) and clock == int(sk["clock"]):
		return
	sk["anim"] = anim
	sk["clock"] = clock
	var v := vertices(int(sk["model"]), anim, clock)
	for part in sk["parts"]:
		var own: ArrayMesh = part["mesh"]
		own.clear_surfaces()
		for sf in part["surfaces"]:
			var arrays: Array = sf["arrays"]
			var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var idx: PackedInt32Array = sf["idx"]
			for i in verts.size():
				var j := idx[i]
				if j >= 0:
					var p: Vector3i = v[j]
					verts[i] = Vector3(p.x, -p.y, -p.z) / 1000.0
			arrays[Mesh.ARRAY_VERTEX] = verts
			own.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
			own.surface_set_material(own.get_surface_count() - 1, sf["material"])

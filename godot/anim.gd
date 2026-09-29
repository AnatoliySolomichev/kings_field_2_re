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

const SKIP := -0x8000

static var models := {}          # model -> {base, anims, poses}


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


static func _s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v >= 0x8000 else v


# 0x80042cac: [segment, factor].
# @orig game:0x80042cac  status:verified -- the segment of 11 of 11 creatures' caches in the snapshots, tools/anim.py
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
# @orig game:0x80042e34  status:verified -- the start vertices of 11 of 11 creatures' caches
static func overlay(verts: Array, pose: Array) -> void:
	var i := 0
	for e in pose:
		if e is int:
			i += -int(e) - 1
		else:
			verts[i] = e
			i += 1


# 0x80042eb0: every vertex the pose names moves by ((target - v) * t) >> 12.
# @orig game:0x80042eb0  status:verified -- 3 snapshots' last drawn creature, tools/anim.py
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
# @orig game:0x800431e8  status:verified -- tools/anim.py against the snapshots
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

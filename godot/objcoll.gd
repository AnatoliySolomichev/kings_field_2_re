class_name KFObjectCollision
# What makes an object solid.
#
# `collide_query`'s mask bit 0x20 means "test the objects", and that branch is
# `object_collide` (0x80045ac8). It walks all 396 slots -- skipping a type of
# 0xff, a byte +0 of zero and whichever slot is `current_object` -- and tests
# what is left two ways:
#
#   radius = object_type_table[type] + 4                  a u16
#   if the row's byte +3 has bit 0x10:
#       radius = radius * object[+0x38] / 128             the object's scale
#
#   radius  > 0                     a circle of that radius (in_range)
#   radius == 0, row +3 has bit 4   an oriented rectangle, half-extents from
#                                   the row's +0xe and +0x10, turned by the
#                                   angle at object[+0x26] (in_oriented_rect)
#   otherwise                       the object does not stop you
#
# The shape is a property of the **type**: an object's own byte +3 is a copy
# of the row's, which `load_object_placement` makes and `object_set_present`
# then sets bit 0x80 in. Only the scale that stretches a circle and the angle
# that turns a rectangle come from the object itself.
#
# `emu/bp23.lua` recorded 401 touches while the player walked into things and
# this reproduces all 401, over 13 distinct shapes.
# @orig game:0x80045ac8 object_collide  status:verified -- the shape and the radius

const SCALE_BIT := 0x10        # in the type row's byte +3
const RECT_BIT := 0x04         # the same byte, and the object's copy of it
const SCALE_ONE := 128         # the object's +0x38 is over this

var shapes: Dictionary = {}    # level -> { type -> {kind, a, b} }


func load_shapes(path := "res://objcoll.json") -> bool:
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	for lv in d.get("levels", {}):
		var by_type := {}
		for row in d["levels"][lv]:
			by_type[int(row["type"])] = {"kind": row["kind"],
				"a": int(row["a"]), "b": int(row["b"])}
		shapes[int(lv)] = by_type
	return true


# @orig game:0x80045ac8 object_collide  status:verified
static func radius_of(row_flags: int, row_radius: int, obj_scale: int) -> int:
	if row_flags & SCALE_BIT:
		return (row_radius * obj_scale) / SCALE_ONE
	return row_radius


# The shape a type gives, at the object's own scale.
# @orig game:0x80045ac8 object_collide  status:verified
static func shape_of(row_flags: int, row_radius: int, rect_a: int, rect_b: int,
		obj_scale := SCALE_ONE) -> Dictionary:
	var r := radius_of(row_flags, row_radius, obj_scale)
	if r > 0:
		return {"kind": "circle", "a": r, "b": 0}
	if row_flags & RECT_BIT:
		return {"kind": "rect", "a": rect_a, "b": rect_b}
	return {"kind": "none", "a": 0, "b": 0}


# Does the query point stand inside this object?
#
# The circle is `in_range`: |dx| and |dz| within r first, then the true
# distance. The rectangle is `in_oriented_rect` -- the offset turned into the
# object's frame by its angle, then compared against the two half-extents.
# @orig game:0x80016d3c in_oriented_rect  status:transcribed
func hits(s: Dictionary, dx: int, dz: int, angle: int, coll) -> bool:
	if s["kind"] == "circle":
		var r: int = int(s["a"])
		if absi(dx) > r or absi(dz) > r:
			return false
		return dx * dx + dz * dz <= r * r
	if s["kind"] == "rect":
		var c: int = coll.game_cos(angle)
		var sn: int = coll.game_sin(angle)
		var lx: int = (dx * c + dz * sn) >> 12
		var lz: int = (dz * c - dx * sn) >> 12
		return absi(lx) <= int(s["a"]) and absi(lz) <= int(s["b"])
	return false

class_name KFCollision
extends RefCounted
# The game's own collision, transcribed from `tools/collision.py`, which was
# transcribed from `tile_collision` at 0x8003260c and checked against the
# game's own answers on every logged call — 4264 of them, all exact.
#
# Handing a physics engine the drawn mesh instead gets four things wrong, and
# each is a property of this model rather than of the geometry:
#
#   * ramps and bridges     the floor opcodes return a height that varies
#                           across the cell, so you rise as you cross it
#   * stepping over a low wall
#                           the blocking branch writes the wall's top into the
#                           same "nearest surface" it uses for floors, so a wall
#                           you cannot pass through is a floor you can stand on
#   * stairs                the same mechanism, one step at a time
#   * falling into water     nothing is solid unless a shape says so
#
# Which is also why the original needs no jump: you never jump, you are lifted.
#
# All arithmetic here is the PlayStation's: integers, world units, Y increasing
# downward. The caller converts.

const W := 80
const CELL := 0x800
const NO_SURFACE := 100000

const WALL_BIT := 5
const FLOOR_BIT := 4
const CEIL_BIT := 8
const DIAG_BIT := 6
const BLOCKING := WALL_BIT | DIAG_BIT      # bits 0 and 1: something lateral

var cells := PackedInt32Array()
var shapes := {}
var radius := 800
var body := 1700
var isqrt_table := PackedInt32Array()
var sin_table := PackedInt32Array()


func load_from(path: String) -> bool:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_error("collision data not found: " + path)
		return false
	var d = JSON.parse_string(f.get_as_text())
	if typeof(d) != TYPE_DICTIONARY:
		push_error("collision data is not JSON: " + path)
		return false
	cells = PackedInt32Array(d["cells"])
	shapes = d["shapes"]
	radius = int(d["radius"])
	body = int(d["body"])
	if d.has("isqrt"):
		isqrt_table = PackedInt32Array(d["isqrt"])
	if d.has("sin"):
		sin_table = PackedInt32Array(d["sin"])
	return true


# 0x80076cc4 and 0x80076da0, over the game's own quarter wave: 0x1000 to the
# turn, 4096 to the unit. Not Godot's sin() -- these are the values the
# PlayStation actually multiplied by.
# @orig game:0x80076cc4 game_sin  status:transcribed
func game_sin(a: int) -> int:
	if sin_table.is_empty():
		return 0
	if a < 0:
		return -game_sin(-a)
	a &= 0xFFF
	if a < 0x401:
		return sin_table[a]
	if a < 0x801:
		return sin_table[0x800 - a]
	if a < 0xC01:
		return -sin_table[a - 0x800]
	return -sin_table[0x1000 - a]


# @orig game:0x80076da0 game_cos  status:transcribed
func game_cos(a: int) -> int:
	if sin_table.is_empty():
		return 0
	a = absi(a) & 0xFFF
	if a < 0x401:
		return sin_table[0x400 - a]
	if a < 0x801:
		return -sin_table[a - 0x400]
	if a < 0xC01:
		return -sin_table[0xC00 - a]
	return sin_table[a - 0xC00]


# A pair of angles to a unit direction, the way the GTE does it.
#
# `rot_matrix_x` (0x80016598) writes [0x1000,0,0; 0,cos,-sin; 0,sin,cos] and
# `rot_matrix_y` (0x8001660c) writes [cos,0,-sin; 0,0x1000,0; sin,0,cos].
# `ApplyMatrixLV` (0x80074840) loads a matrix into the GTE rotation registers
# and runs MVMVA with no translation, storing MAC1..3 -- the 32-bit results,
# not the saturated IR ones.
#
# `direction_from_angles` (0x800167cc) rotates (0, 0, 0x1000) by the
# **negated** first angle about the first axis and then by the second about
# the second. **Between the two stages the game copies the three 32-bit
# results into a 16-bit SVECTOR**, so that truncation is part of the answer.
# Eleven pieces of actor, object and effect code ask which way something
# points, and this is what they ask.
# @orig game:0x80016598 rot_matrix_x  status:verified
func rot_matrix_x(a: int) -> PackedInt32Array:
	var s := game_sin(a)
	var c := game_cos(a)
	return PackedInt32Array([0x1000, 0, 0, 0, c, -s, 0, s, c])


# @orig game:0x8001660c rot_matrix_y  status:verified
func rot_matrix_y(a: int) -> PackedInt32Array:
	var s := game_sin(a)
	var c := game_cos(a)
	return PackedInt32Array([c, 0, -s, 0, 0x1000, 0, s, 0, c])


# @orig game:0x80074840 ApplyMatrixLV  status:verified
func apply_matrix(m: PackedInt32Array, v: PackedInt32Array) -> PackedInt32Array:
	var out := PackedInt32Array([0, 0, 0])
	for r in range(3):
		var acc := m[3 * r] * v[0] + m[3 * r + 1] * v[1] + m[3 * r + 2] * v[2]
		out[r] = acc >> 12
	return out


func _s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v >= 0x8000 else v


# @orig game:0x800167cc direction_from_angles  status:verified
func direction_from_angles(pitch: int, yaw: int) -> PackedInt32Array:
	var v := apply_matrix(rot_matrix_x(-pitch), PackedInt32Array([0, 0, 0x1000]))
	for i in range(3):
		v[i] = _s16(v[i])
	var w := apply_matrix(rot_matrix_y(yaw), v)
	for i in range(3):
		w[i] = _s16(w[i])
	return w


# The game's own arctangent: vec_angle (0x80016ab8) with arctan_unit
# (0x800742ac) under it. Twelve CORDIC iterations over a table of atan(2**-i)
# in the game's 0x1000-to-the-turn units -- 511, 302, 159, 81, 41, 20, 10, 5,
# 3, 1, 0, 0, against 512.00, 302.25, 159.70, 81.07 ... computed. The table's
# own rounding is why this disagrees with a real atan2 by up to 4.37 units of
# 4096: that is the game's answer, not an error in the copy.
#
# Nineteen routines in GAME.EXE call it, all of them things that turn towards
# something.
const CORDIC := [511, 302, 159, 81, 41, 20, 10, 5, 3, 1, 0, 0]


# @orig game:0x800742ac arctan_unit  status:transcribed
func arctan_unit(ratio: int) -> int:
	var x := 0x1000
	var y := ratio
	var z := 0
	for i in range(12):
		var nx: int
		var ny: int
		if y >= 0:
			nx = x + (y >> i)
			ny = y - (x >> i)
			z += CORDIC[i]
		else:
			nx = x - (y >> i)
			ny = y + (x >> i)
			z -= CORDIC[i]
		x = nx
		y = ny
	return z


# MIPS `div` truncates towards zero; GDScript's integer / does too, but the
# shift has to happen first and stay exact, so both are written out.
func _idiv(a: int, b: int) -> int:
	var q := absi(a) / absi(b)
	return -q if (a < 0) != (b < 0) else q


# @orig game:0x80016ab8 vec_angle  status:transcribed -- within 4.37 of 4096 of atan2
func vec_angle(u: int, v: int) -> int:
	if absi(v) >= absi(u):
		if v > 0:
			return (-arctan_unit(_idiv(u << 12, v))) & 0xFFF
		if v < 0:
			return 0x800 - arctan_unit(_idiv(u << 12, v))
		return 0
	if u < 0:
		return arctan_unit(_idiv(v << 12, u)) + 0x400
	return arctan_unit(_idiv(v << 12, u)) + 0xC00


# 0x80074508: the game's integer square root, through the GTE leading-zero count
# and a 192-entry table. NOT floor(sqrt(x)) -- a perfect square comes back one
# short, isqrt(40000) = 199, and the walking step depends on that unit.
# @orig game:0x80074508 game_isqrt  status:transcribed
func isqrt(x: int) -> int:
	if x <= 0 or isqrt_table.is_empty():
		return 0
	var lzc := 32
	var v := x
	while v > 0:
		v >>= 1
		lzc -= 1
	if lzc == 0x20:
		return 0
	var t2 := lzc & ~1
	var t1 := (0x1F - t2) >> 1
	var t3 := t2 - 0x18
	var t4 := (x << t3) & 0xFFFFFFFF if t3 >= 0 else x >> (0x18 - t2)
	var idx := t4 - 0x40
	if idx < 0 or idx >= isqrt_table.size():
		return 0
	return ((isqrt_table[idx] << t1) & 0xFFFFFFFF) >> 12


func _plane(f: int, tx: int, tz: int, op0: int, a3: int, t6: int) -> bool:
	match f:
		0: return tx <= op0 + a3
		1: return tz >= t6 - op0
		2: return tx >= t6 - op0
		_: return tz <= op0 + a3


# Handler 0x24: a wall of limited length, op0..op1 from its own face.
func _slab(f: int, tx: int, tz: int, a3: int, a: Array) -> bool:
	var u := tx
	match f:
		1: u = CELL - tz
		2: u = CELL - tx
		3: u = tz
	return int(a[0]) - a3 <= u and u <= int(a[1]) + a3


# Handler 0x23: a wall at 45 degrees. This is what the tx +- tz values the
# routine precomputes in its prologue are for.
func _diag_wall(f: int, tx: int, tz: int, a3: int, a: Array) -> bool:
	var d := tx - tz
	var adj := -CELL
	match f:
		1:
			d = -tx - tz
			adj = -0x1000
		2:
			d = tz - tx
		3:
			d = tx + tz
			adj = 0
	return d <= int(a[0]) + a3 + adj


# Handler 0x30: a sloping floor. Returns NO_SURFACE when outside its extent.
func _ramp(f: int, tx: int, tz: int, a3: int, t6: int, a: Array) -> int:
	var op1 := int(a[1])
	var op2 := int(a[2])
	var op5 := int(a[5])
	if op5 == 0:
		return NO_SURFACE
	var q := 0
	var inside := false
	match f:
		0:
			inside = op1 - a3 <= tx and tx <= op2 + a3
			q = tz
		1:
			inside = t6 - op2 <= tz and tz <= a3 + CELL - op1
			q = tx
		2:
			inside = t6 - op2 <= tx and tx <= a3 + CELL - op1
			q = CELL - tz
		_:
			inside = op1 - a3 <= tz and tz <= op2 + a3
			q = CELL - tx
	if not inside:
		return NO_SURFACE
	return int(a[0]) - (q / op5 + 1) * int(a[4])


# Handler 0x32: a floor sloping along a diagonal, clamped into op1..op2.
func _diag_ramp(f: int, tx: int, tz: int, a: Array) -> int:
	var a2 := CELL + tz - tx
	match f:
		1: a2 = tx + tz
		2: a2 = CELL + tx - tz
		3: a2 = 0x1000 - tx - tz
	var op1 := int(a[1])
	var op5 := int(a[5])
	if a2 < op1 or op5 == 0:
		return NO_SURFACE
	a2 = min(a2, int(a[2]))
	return int(a[0]) - ((a2 - op1) / op5) * int(a[4])


# Handlers 0x33 and 0x34: a corner slope, following the nearer axis or the
# farther one. The diagonal is in plan; the pitch is usually very gentle.
func _corner(f: int, tx: int, tz: int, a: Array, outer: bool) -> int:
	var p := tx
	var q := tz
	match f:
		1:
			p = tx
			q = CELL - tz
		2:
			p = CELL - tx
			q = CELL - tz
		3:
			p = CELL - tx
			q = tz
	var v: int = max(p, q) if outer else min(p, q)
	var div := int(a[3])
	if div == 0:
		return NO_SURFACE
	return int(a[0]) - (v / div + 1) * int(a[2])


# Which of a cell's two layers a query at `ymid` belongs to. This is
# `0x800324f0`, the routine the wrapper calls before the collision proper: the
# heights count upward in units of 128, so the query's own height is
# -(ymid >> 7), and the rule is "stand on the layer whose floor is not above
# you", falling back to the other when the nearer one is absent.
#
# Exporting only layer 5 and skipping this put the lower room's floor under a
# player standing on the bridge above it.
# @orig game:0x800324f0 select_cell_layer  status:transcribed
func _layer(i: int, ymid: int) -> int:
	var ha := cells[i + 2]          # layer 0's height
	var hb := cells[i + 5]          # layer 5's height
	var hu := (-(ymid >> 7)) & 0xFFFF
	if hb < ha:
		return 3 if (hu < ha and hb != 0) else 0
	return 0 if (hu < hb and ha != 0) else 3


# The answer: which kinds of surface this position is against, and the nearest
# one, which is what you stand on. `y` is the feet; the body height above them
# is what the wall test uses, and its middle is what picks the layer.
#
# `ymid` overrides that last part, because the game has two wrappers and they
# disagree: 0x80033d38 halves the body height, 0x80033b44 passes a flat y-0x500.
# `surface()` below is the second one, which is what the walking code asks.
# @orig game:0x8003260c tile_collision  status:verified -- every logged call reproduced, tools/collision.py
# What opcodes 0x17, 0x18 and 0x19 left behind on the last query, by opcode.
# The game keeps them at 0x801e6484, 0x801e647c and 0x801e6480 and nothing but
# sync_player_pos reads them.
var surfaces := {}


func query(x: int, y: int, z: int, ymid := 0x7FFFFFFF) -> Dictionary:
	if ymid == 0x7FFFFFFF:
		ymid = y - (body >> 1)
	var out := {"mask": 0, "floor": NO_SURFACE}
	var cx := x >> 11
	var cz := z >> 11
	if cx < 0 or cx >= W or cz < 0 or cz >= W:
		return out
	var i := (cz * W + cx) * 6 + _layer((cz * W + cx) * 6, ymid)
	var sid := cells[i]
	var key := str(sid)
	if sid == 255 or not shapes.has(key):
		return out
	var sh: Dictionary = shapes[key]
	var rot := cells[i + 1]
	var base := -128 * cells[i + 2]
	var a3 := (radius * int(sh["scale"])) >> 12
	var t6 := CELL - a3
	var tx := x & 0x7FF
	var tz := z & 0x7FF
	var s3 := y - body
	var cur := NO_SURFACE
	var mask := 0
	surfaces.clear()

	for ins in sh["ins"]:
		var op := int(ins[0])
		var a: Array = ins[1]
		if op == 0x10 and a.size() >= 1:
			var h := int(a[0]) + base
			cur = int(min(cur, h))
			if cur < y:
				mask |= FLOOR_BIT
		elif op == 0x11 and a.size() >= 2:
			# a ceiling: overhead when the head is inside it, a surface if not
			var top := int(a[0]) + base
			if s3 < top:
				var bot := int(a[1]) + base
				if bot < s3:
					mask |= CEIL_BIT
				else:
					cur = int(min(cur, bot))
		elif op == 0x30 and a.size() >= 6:
			var d := _ramp((int(a[3]) + rot) & 3, tx, tz, a3, t6, a)
			if d != NO_SURFACE and d + base < cur:
				cur = d + base
				if cur < y:
					mask |= FLOOR_BIT
		elif op == 0x32 and a.size() >= 6:
			var d2 := _diag_ramp((int(a[3]) + rot) & 3, tx, tz, a)
			if d2 != NO_SURFACE and d2 + base < cur:
				cur = d2 + base
				if cur < y:
					mask |= FLOOR_BIT
		elif (op == 0x33 or op == 0x34) and a.size() >= 4:
			var d3 := _corner((int(a[1]) + rot) & 3, tx, tz, a, op == 0x34)
			if d3 != NO_SURFACE and d3 + base < cur:
				cur = d3 + base
				if cur < y:
					mask |= FLOOR_BIT
		elif op == 0x23 and a.size() >= 4:
			if _diag_wall((int(a[3]) + rot) & 3, tx, tz, a3, a):
				var lo := int(a[1]) + base
				var hi := int(a[2]) + base
				if s3 < lo and hi < cur:
					cur = hi
					if y > hi:
						mask |= DIAG_BIT
		elif op == 0x24 and a.size() >= 5:
			if _slab((int(a[4]) + rot) & 3, tx, tz, a3, a):
				var lo2 := int(a[2]) + base
				var hi2 := int(a[3]) + base
				if s3 < lo2 and hi2 < cur:
					cur = hi2
					if y > hi2:
						mask |= WALL_BIT
		elif op == 0x25 and a.size() >= 7:
			# A wall whose footprint is an L, not a rectangle: 207 uses across
			# the 28 levels and nothing here handled it until the switch table
			# at 0x80011b0c was read. tools/collision.py has the derivation.
			if _notch((int(a[6]) + rot) & 3, tx, tz, a3, a):
				var lo4 := int(a[4]) + base
				var hi4 := int(a[5]) + base
				if s3 < lo4 and hi4 < cur:
					cur = hi4
					if y > hi4:
						mask |= WALL_BIT
		elif (op == 0x17 or op == 0x18 or op == 0x19) and a.size() >= 1:
			# The three planes that do something to you when you are under
			# them. The game publishes each into its own slot and compares it
			# with the eye in sync_player_pos (0x80028d54); 0x18 also takes
			# part in the mask, but only when the caller sets the top bits of
			# its fifth argument, which nothing in this port does yet.
			surfaces[op] = int(a[0]) + base
		elif (op == 0x20 or op == 0x21 or op == 0x22) and a.size() >= 4:
			var f := (int(a[3]) + rot) & 3
			var op0 := int(a[0])
			var hit := _plane(f, tx, tz, op0, a3, t6)
			if op != 0x20:
				var other := _plane((f + 1) & 3, tx, tz, op0, a3, t6)
				hit = (hit or other) if op == 0x21 else (hit and other)
			if hit:
				var lo3 := int(a[1]) + base
				var hi3 := int(a[2]) + base
				if s3 < lo3 and hi3 < cur:
					cur = hi3
					if y > hi3:
						mask |= WALL_BIT

	out["mask"] = mask
	out["floor"] = cur
	return out


# Handler 0x25, transcribed from 0x80032d3c. In the face's own frame -- `u`
# along it and `v` across, the same rotation the other lateral handlers use --
# the region is a quadrant with a bite out of its far corner:
#
#     u >= op0 - a3  and  v <= op3 + a3  and  not (u > op1 + a3 and v < op2 - a3)
#
# The code says it in exactly that shape: a pair of tests that only reject
# together, then two that reject on their own.
# @orig game:0x80032d3c  status:transcribed -- a label inside tile_collision, opcode 0x25
func _notch(f: int, tx: int, tz: int, a3: int, a: Array) -> bool:
	var u := tx if f == 0 else (CELL - tz if f == 1 else
		(CELL - tx if f == 2 else tz))
	var v := tz if f == 0 else (tx if f == 1 else
		(CELL - tz if f == 2 else CELL - tx))
	if int(a[1]) + a3 < u and v < int(a[2]) - a3:
		return false
	return not (u < int(a[0]) - a3 or int(a[3]) + a3 < v)


func blocked(x: int, y: int, z: int) -> bool:
	return (query(x, y, z)["mask"] & BLOCKING) != 0


# 0x80033b10: the nearest surface alone, the way player_vertical asks for it.
# @orig game:0x80033b10 collide_surface  status:transcribed
func surface(x: int, y: int, z: int) -> int:
	return int(query(x, y, z, y - 0x500)["floor"])

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
#
# @exe game

const W := 80
const CELL := 0x800
const NO_SURFACE := 100000

const WALL_BIT := 5
const FLOOR_BIT := 4
const CEIL_BIT := 8
const DIAG_BIT := 6
const BLOCKING := WALL_BIT | DIAG_BIT      # bits 0 and 1: something lateral

# collision_ceiling (0x801e6478) starts 40000 above the base, and the handlers
# overwrite it: 0x11, a wall whose bottom is not below the head (a beam), 0x31
# and 0x35. A ramp whose run op5 is under 0x40 leaves a push of (op4 << 7) /
# op5 along face << 10 (0x801e6498, 0x801e649c) -- tools/collision.py.
const CEIL_START := -40000
const NO_CEILING := -100000
const STEEP := 0x40

var cells := PackedInt32Array()
# Per cell, the layers whose byte +4 carries 0x40: bit 0 layer 0, bit 1 the
# other. collide_query's flag 2 (0x80033f94) makes them walls to the creatures,
# whose flags are 0x93, and not to the player's 0x31.
var fence := PackedByteArray()
var shapes := {}
var radius := 800
var body := 1700
var isqrt_table := PackedInt32Array()
var isqrt_below := PackedInt32Array()   # the 192 halfwords 640 bytes before it
var sin_table := PackedInt32Array()
var ratan_table := PackedInt32Array()
var occ := PackedInt32Array()        # each cell's occupancy count, byte +2 >> 2
var objects := []                    # [slot, 0 circle / 1 rect, a, b, byte +3,
                                     #  x, y, z, top, angle, push radius]


# @port data -- reads collNN.json: the grid's collision fields and the tile shapes, as tools/gdcoll.py writes them
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
	if d.has("fence"):
		fence = PackedByteArray(d["fence"])
	shapes = d["shapes"]
	radius = int(d["radius"])
	body = int(d["body"])
	if d.has("isqrt"):
		isqrt_table = PackedInt32Array(d["isqrt"])
	if d.has("isqrt_below"):
		isqrt_below = PackedInt32Array(d["isqrt_below"])
	if d.has("sin"):
		sin_table = PackedInt32Array(d["sin"])
	if d.has("ratan"):
		ratan_table = PackedInt32Array(d["ratan"])
	if d.has("occ"):
		occ = PackedInt32Array(d["occ"])
	if d.has("objects"):
		objects = d["objects"]
	return true


# 0x80076cc4 and 0x80076da0, over the game's own quarter wave: 0x1000 to the
# turn, 4096 to the unit. Not Godot's sin() -- these are the values the
# PlayStation actually multiplied by.
# @orig game:0x80076cc4 game_sin  status:verified -- 4396 of 4396 calls of the game's own, every angle and some past the circle (tools/routines.py)
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


# @orig game:0x80076da0 game_cos  status:verified -- 4396 of 4396 calls of the game's own (tools/routines.py)
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


# @port helper -- a halfword, sign-extended
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


# @orig game:0x800742ac arctan_unit  status:verified -- 557 of 557 calls of the game's own (tools/routines.py)
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
# @port helper -- the MIPS div, truncating towards zero
func _idiv(a: int, b: int) -> int:
	var q := absi(a) / absi(b)
	return -q if (a < 0) != (b < 0) else q


# @orig game:0x80016ab8 vec_angle  status:verified -- 601 of 601 calls of the game's own, the axes and diagonals among them (tools/routines.py)
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
# The input is a 32-bit word: the GTE's LZCR counts the leading ones of a
# negative one, and the shift keeps it negative, so such an input reads the
# 192 halfwords 640 bytes before the table (isqrt_below) -- the fire ball's
# (dx ^ 2) hands it some.
# @orig game:0x80074508 game_isqrt  status:verified -- 607 of 607 calls of the game's own, through its GTE leading-zero count (tools/routines.py); and 5010 of 5010 32-bit inputs, the negative ones among them (tools/movement.py)
func isqrt(x: int) -> int:
	x &= 0xFFFFFFFF
	if isqrt_table.is_empty():
		return 0
	var sign := (x >> 31) & 1
	var lzc := 0
	var bit := 31
	while bit >= 0 and ((x >> bit) & 1) == sign:
		lzc += 1
		bit -= 1
	if lzc == 0x20:
		return 0
	var t2 := lzc & ~1
	var t1 := (0x1F - t2) >> 1
	var t3 := t2 - 0x18
	var t4: int
	if t3 >= 0:
		t4 = (x << t3) & 0xFFFFFFFF
		if t4 & 0x80000000:
			t4 -= 0x100000000
	else:
		t4 = (x - 0x100000000 if sign else x) >> (0x18 - t2)
	var idx := t4 - 0x40
	var v := 0
	if idx >= 0 and idx < isqrt_table.size():
		v = isqrt_table[idx]
	elif idx >= -320 and idx < -128 and isqrt_below.size() == 192:
		v = isqrt_below[idx + 320]
	else:
		return 0
	return ((v << t1) & 0xFFFFFFFF) >> 12


# @orig game:0x800328c0 tile_op_20_wall  status:verified -- opcode 0x20's face test, which 0x21 and 0x22 make on two faces; 1427 of 1430, 83 of 83 and 143 of 143 logged calls on cells carrying them
func _plane(f: int, tx: int, tz: int, op0: int, a3: int, t6: int) -> bool:
	match f:
		0: return tx <= op0 + a3
		1: return tz >= t6 - op0
		2: return tx >= t6 - op0
		_: return tz <= op0 + a3


# Handler 0x24: a wall of limited length, op0..op1 from its own face.
# @orig game:0x80032c3c tile_collision+0x630  status:verified -- opcode 0x24; 4 of 4 logged calls on cells carrying it
func _slab(f: int, tx: int, tz: int, a3: int, a: Array) -> bool:
	var u := tx
	match f:
		1: u = CELL - tz
		2: u = CELL - tx
		3: u = tz
	return int(a[0]) - a3 <= u and u <= int(a[1]) + a3


# Handler 0x23: a wall at 45 degrees. This is what the tx +- tz values the
# routine precomputes in its prologue are for.
# @orig game:0x80032b90 tile_collision+0x584  status:verified -- opcode 0x23; 82 of 82 logged calls on cells carrying it
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
# @orig game:0x80032f78 tile_op_30_ramp  status:verified -- opcode 0x30; 3558 of 3558 logged calls on cells carrying it
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
# @orig game:0x80033460 tile_collision+0xe54  status:verified -- opcode 0x32; 166 of 166 logged calls on cells carrying it
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
# @orig game:0x800331b0 tile_collision+0xba4  status:verified -- opcode 0x33, the nearer axis; 193 of 193 logged calls on cells carrying it
# @orig game:0x80033308 tile_collision+0xcfc  status:verified -- opcode 0x34, the farther; 413 of 413
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
#
# What opcodes 0x17, 0x18 and 0x19 left behind on the last query, by opcode.
# The game keeps them at 0x801e6484, 0x801e647c and 0x801e6480 and nothing but
# sync_player_pos reads them.
var surfaces := {}
var flags := 0                       # the fifth argument's top nibble, which only 0x18 reads


# @orig game:0x8003260c tile_collision  status:verified -- 8075 of 8078 logged calls, through tools/collision.py
func query(x: int, y: int, z: int, ymid := 0x7FFFFFFF) -> Dictionary:
	if ymid == 0x7FFFFFFF:
		ymid = y - (body >> 1)
	var out := {"mask": 0, "floor": NO_SURFACE, "ceil": CEIL_START, "push": 0,
		"push_angle": 0, "at": -1}
	var cx := x >> 11
	var cz := z >> 11
	if cx < 0 or cx >= W or cz < 0 or cz >= W:
		return out
	var i := (cz * W + cx) * 6 + _layer((cz * W + cx) * 6, ymid)
	var sid := cells[i]
	var key := str(sid)
	var base := -128 * cells[i + 2]
	out["ceil"] = base + CEIL_START
	out["at"] = i                    # the cell and layer, what 0x801e6468 holds
	if not shapes.has(key):             # 255 is a shape too: the void (tools/collision.py Level.shape)
		return out
	var sh: Dictionary = shapes[key]
	var rot := cells[i + 1]
	var a3 := (radius * int(sh["scale"])) >> 12
	var t6 := CELL - a3
	var tx := x & 0x7FF
	var tz := z & 0x7FF
	var s3 := y - body
	var cur := NO_SURFACE
	var mask := 0
	var ceil := base + CEIL_START
	var push := 0
	var push_angle := 0
	var locked := false              # [sp+0x10]: 0x18 sets it, 0x10 obeys it
	surfaces.clear()

	for ins in sh["ins"]:
		var op := int(ins[0])
		var a: Array = ins[1]
		if op == 0x10 and a.size() >= 1 and not locked:
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
					ceil = top
				else:
					cur = int(min(cur, bot))
					ceil = NO_CEILING
			else:
				ceil = top
		elif (op == 0x30 or op == 0x35) and a.size() >= 6:
			# 0x35 is 0x30 with a top: a head below it makes it the ceiling
			# (0x80033604); either leaves its push when steep (0x80033710)
			var face := (int(a[3]) + rot) & 3
			var d := _ramp(face, tx, tz, a3, t6, a)
			if d != NO_SURFACE:
				var rtop := int(a[0]) + base
				if op == 0x35 and not (s3 < rtop):
					ceil = rtop
				else:
					if d + base < cur:
						cur = d + base
						if cur < y:
							mask |= FLOOR_BIT
					if int(a[5]) < STEEP:
						push = _idiv(int(a[4]) << 7, int(a[5]))
						push_angle = face << 10
		elif op == 0x31 and a.size() >= 5:
			# a gap in a wall, armed by a wall before it: tools/collision.py
			if (mask & 1) and _opening((int(a[4]) + rot) & 3, tx, tz, a3, a):
				cur = int(a[2]) + base
				ceil = int(a[3]) + base
				if s3 < ceil:
					mask |= CEIL_BIT
				if not (cur < y):
					mask &= ~0x205
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
				if not (s3 < lo):
					ceil = lo
				elif hi < cur:
					cur = hi
					if y > hi:
						mask |= DIAG_BIT
		elif op == 0x24 and a.size() >= 5:
			if _slab((int(a[4]) + rot) & 3, tx, tz, a3, a):
				var lo2 := int(a[2]) + base
				var hi2 := int(a[3]) + base
				if not (s3 < lo2):
					ceil = lo2
				elif hi2 < cur:
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
				if not (s3 < lo4):
					ceil = lo4
				elif hi4 < cur:
					cur = hi4
					if y > hi4:
						mask |= WALL_BIT
		elif (op == 0x17 or op == 0x18 or op == 0x19) and a.size() >= 1:
			# The three planes that do something to you when you are under
			# them. The game publishes each into its own slot and compares it
			# with the eye in sync_player_pos (0x80028d54); 0x18, the water,
			# also takes part in the mask when the caller sets the top bits of
			# its fifth argument (`flags`): 0x80000000 makes it the floor --
			# set, not lowered, and 0x10 no longer heard -- 0x40000000 the
			# ceiling (0x80033a30). A fire ball bursts on water so.
			var h := int(a[0]) + base
			surfaces[op] = h
			if op == 0x18:
				if flags & 0x80000000:
					cur = h
					if h < y:
						mask |= FLOOR_BIT
						locked = true
				if flags & 0x40000000:
					ceil = h
					if not (h < s3):
						mask |= CEIL_BIT
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
				if not (s3 < lo3):
					ceil = lo3
				elif hi3 < cur:
					cur = hi3
					if y > hi3:
						mask |= WALL_BIT

	out["mask"] = mask
	out["floor"] = cur
	out["ceil"] = ceil
	out["push"] = push
	out["push_angle"] = push_angle
	return out


# Handler 0x31, from 0x800338c4: within op0 + r .. op1 - r across the face.
# @orig game:0x800338c4 tile_collision+0x12b8  status:transcribed -- a label inside tile_collision, opcode 0x31
func _opening(f: int, tx: int, tz: int, a3: int, a: Array) -> bool:
	var u := tz if f == 0 else (tx if f == 1 else (CELL - tz if f == 2 else CELL - tx))
	return int(a[0]) + a3 <= u and u <= int(a[1]) - a3


# Handler 0x25, transcribed from 0x80032d3c. In the face's own frame -- `u`
# along it and `v` across, the same rotation the other lateral handlers use --
# the region is a quadrant with a bite out of its far corner:
#
#     u >= op0 - a3  and  v <= op3 + a3  and  not (u > op1 + a3 and v < op2 - a3)
#
# The code says it in exactly that shape: a pair of tests that only reject
# together, then two that reject on their own.
# @orig game:0x80032d3c tile_collision+0x730  status:transcribed -- a label inside tile_collision, opcode 0x25
func _notch(f: int, tx: int, tz: int, a3: int, a: Array) -> bool:
	var u := tx if f == 0 else (CELL - tz if f == 1 else
		(CELL - tx if f == 2 else tz))
	var v := tz if f == 0 else (tx if f == 1 else
		(CELL - tz if f == 2 else CELL - tx))
	if int(a[1]) + a3 < u and v < int(a[2]) - a3:
		return false
	return not (u < int(a[0]) - a3 or int(a[3]) + a3 < v)


# -- the objects: what the player's 0x31 asks after the tiles ----------------
#
# collide_query (0x80033f38) goes on to the things in the level only where the
# cell under the query has an occupancy count, which load_object_placement
# gives every cell within an object's radius + 0x800. Then object_collide
# (0x80045ac8) walks the slots in order and answers with the first one hit, and
# the mask gains bit 0x20. The list is movement.solids' -- present objects whose
# type row gives them a shape -- as tools/gdcoll.py writes it.
const OBJECT_BIT := 0x20


# 0x80074380, the library's ratan2 over its 1025-entry table.
# @orig game:0x80074380 ratan2  status:verified -- 601 of 601 calls of the game's own (tools/routines.py)
func ratan2(y: int, x: int) -> int:
	var negx := x < 0
	var negy := y < 0
	x = absi(x)
	y = absi(y)
	if x == 0 and y == 0:
		return 0
	var v := 0
	if y < x:
		var t := y / (x >> 10) if (y & 0x7FE00000) != 0 else (y << 10) / x
		v = ratan_table[t]
	else:
		var t := x / (y >> 10) if (x & 0x7FE00000) != 0 else (x << 10) / y
		v = 0x400 - ratan_table[t]
	if negx:
		v = 0x800 - v
	return -v if negy else v


# 0x80016ec8 and the height test it shares with in_oriented_rect: a thing at
# py whose top is `top` above its feet against one at y whose top is `own`
# above; Y grows downward.
# @orig game:0x80016f28 in_range+0x60  status:verified -- the height overlap, skipped for y 0xffff; through in_range and in_oriented_rect, the game's own answers (tools/routines.py)
func _heights(py: int, y: int, top: int, own: int) -> bool:
	if y == 0xFFFF:
		return true
	if py < y:
		return not (py < y - own)
	return not (y < py - top)


# @orig game:0x80016ec8 in_range  status:verified -- 600 of 600 calls of the game's own, the skipped height among them (tools/routines.py)
func in_range(px: int, py: int, pz: int, x: int, y: int, z: int, r: int,
		top: int, own: int) -> int:
	var dx := px - x
	if dx < -r or dx > r:
		return -1
	var dz := pz - z
	if dz < -r or dz > r:
		return -1
	if not _heights(py, y, top, own):
		return -1
	var d := isqrt((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3)) << 3
	return -1 if d > r else d


# 0x80016fb4: a box of the radius + own about the point, then the length to
# the target's middle (height / 2 up from its feet) through the game's root,
# less own -- 0 within own (0x80017090), FAR (0xff676981) beyond.
const FAR := -0x98967F
# @orig game:0x80016fb4 in_range_3d  status:verified -- 600 of 600 calls of the game's own (tools/routines.py); through effect_hurt_player, 118 strikes of bp26; through 0x8004ceac, tools/effects.py spell_hit_check against the game's own
func in_range_3d(p: Vector3i, radius: int, t: Vector3i, own: int, height: int) -> int:
	var r := radius + own
	var dx := t.x - p.x
	if dx < -r or r < dx:
		return FAR
	var dz := t.z - p.z
	if dz < -r or r < dz:
		return FAR
	var dy := t.y - p.y - (height >> 1)
	if dy < -r or r < dy:
		return FAR
	var ln := isqrt((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3) + (dy >> 3) * (dy >> 3)) << 3
	if r < ln:
		return FAR
	return ln - own if own < ln else 0


# 0x80016d3c: the offset to polar and back out along the rectangle's own axes.
# @orig game:0x80016d3c in_oriented_rect  status:verified -- 600 of 600 calls of the game's own (tools/routines.py)
func in_oriented_rect(ang: int, px: int, py: int, pz: int, x: int, y: int,
		z: int, a: int, b: int, top: int, own: int) -> int:
	var ddx := (px - x) >> 3
	var ddz := (pz - z) >> 3
	var d := isqrt(ddx * ddx + ddz * ddz) << 3
	var rel := (vec_angle(x - px, z - pz) & 0xFFFF) - _s16(ang) + 0x400
	var lx := (game_cos(rel) * d) >> 12
	var lz := (game_sin(rel) * d) >> 12
	if lx < -a or lx > a or lz < -b or lz > b:
		return -1
	return d if _heights(py, y, top, own) else -1


# 0x80045ac8: the index in `objects` of the first one (x, y, z) runs into.
# @orig game:0x80045ac8 object_collide  status:transcribed
func object_collide(x: int, y: int, z: int) -> int:
	for i in objects.size():
		var o: Array = objects[i]
		var hit := -1
		if int(o[1]) == 0:
			hit = in_range(o[5], o[6], o[7], x, y, z, int(o[2]) + radius, o[8], body)
		else:
			hit = in_oriented_rect(o[9], o[5], o[6], o[7], x, y, z,
				int(o[2]) + radius, int(o[3]) + radius, o[8], body)
		if hit != -1:
			return i
	return -1


# collide_query with the player's 0x31, the objects included: the tile answer
# with "object" the index hit or -1.
# @orig game:0x80033f38 collide_query  status:partial -- tiles and objects; not the creatures (0x10)
func query_all(x: int, y: int, z: int) -> Dictionary:
	var q := query(x, y, z)
	q["object"] = -1
	var cx := x >> 11
	var cz := z >> 11
	if cx < 0 or cx >= W or cz < 0 or cz >= W or occ.is_empty() \
			or occ[cz * W + cx] == 0:
		return q
	var i := object_collide(x, y, z)
	if i != -1:
		q["mask"] = int(q["mask"]) | OBJECT_BIT
		q["object"] = i
	return q


# collide_query's flag 2 on the answer of query(): the layer it looked at
# ("at", what 0x801e6468 holds) is fenced -- a wall, with the surface written
# over as 0xfffe7960.
# @orig game:0x80033f94 collide_query+0x5c  status:verified -- a label inside collide_query; 5006 of 5006 logged creature positions stand clear of a fence, tools/ai.py
func fenced(q: Dictionary) -> bool:
	var at := int(q["at"])
	if at < 0 or fence.is_empty():
		return false
	return (fence[at / 6] & (1 if at % 6 == 0 else 2)) != 0


const FENCED_SURFACE := -100000


# @port helper -- the lateral bits of query()'s mask; nothing calls it now
func blocked(x: int, y: int, z: int) -> bool:
	return (query(x, y, z)["mask"] & BLOCKING) != 0


# 0x80033b10: the nearest surface alone, the way player_vertical asks for it.
# @orig game:0x80033b10 collide_surface  status:transcribed
func surface(x: int, y: int, z: int) -> int:
	return int(query(x, y, z, y - 0x500)["floor"])

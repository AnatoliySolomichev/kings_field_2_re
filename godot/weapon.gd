class_name KFWeapon
# The player's weapon: the swing, the probe, and the damage a blow does to a
# creature. tools/weapon.py is the same in Python, and its docstring the long
# form; FORMATS.md "The player's blow" the reading.
#
# A swing is a clock (0x801b25a4, -1 between swings) that the record's +0x1c
# drives a frame; the blow falls on the frame it crosses +0x1e, with the
# strength of the meter the swing began with. Between swings the meter refills
# at 2 * min((stat << 6) / (+1 + 1) + 1, 5000) a frame, after a pause of 10.
# The blow looks for a creature four times along a quarter of (0, 0, +0x1a)
# turned by the view; actors.gd strikes what it finds.

const FULL := 5000
const PAUSE := 10
const NEVER := 5000
const PROBE_UP := 0x320
const PROBE_R := 0x190
const PROBE_H := 0x258
const STRONG := 0x9C4
const SUM_CAP := 0x68DB7
const PUSH_CAP := 0x200
const EYE_DROP := 0x3E8

static var records: Array = []     # the 48 weapon records, 68 bytes each
static var guard := {}             # level -> the actor slot its hook protects


static func load_from(path := "res://weapon.json") -> bool:
	if not records.is_empty():
		return true
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	for r in d["records"]:
		var raw := PackedByteArray()
		for v in r:
			raw.append(int(v))
		records.append(raw)
	for k in d.get("guard", {}):
		if d["guard"][k] != null:
			guard[int(k)] = int(d["guard"][k])
	return true


static func u16(raw: PackedByteArray, o: int) -> int:
	return raw[o] | (raw[o + 1] << 8)


static func s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v >= 0x8000 else v


static func _trunc(a: int, b: int) -> int:
	var q := absi(a) / absi(b)
	return -q if (a < 0) != (b < 0) else q


# @orig game:0x80029390  status:transcribed -- the meter's refill before it is doubled
static func gain(stat: int, rate: int) -> int:
	return mini(_trunc(stat << 6, rate + 1) + 1, FULL)


# held_item_tick's idle frame (0x8002dde8): nothing while attack is held, the
# pause first, then the refill -- the ring at 0x801b25d7 is not worn in the port.
# @orig game:0x8002dde8  status:transcribed -- a label inside held_item_tick
static func refill(w: Dictionary, rec: PackedByteArray, stat: int, held: bool) -> void:
	if held:
		return
	if int(w["pause"]) > 0:
		w["pause"] = int(w["pause"]) - 1
		return
	w["meter"] = mini((int(w["meter"]) + 2 * gain(stat, rec[1])) & 0xFFFF, FULL)


# 0x8002c040 with phase 0: the clock at 0, the times off the record, the meter
# kept as the strength and emptied.
# @orig game:0x8002c040  status:transcribed -- phase 0; the special phase 1 is not here
static func start(w: Dictionary, rec: PackedByteArray) -> bool:
	if int(w["clock"]) != -1:
		return false
	w["clock"] = 0
	w["hit"] = u16(rec, 0x1E)
	w["sound"] = u16(rec, 0x2C)
	w["strength"] = int(w["meter"])
	w["meter"] = 0
	return true


# One frame of a phase-0 swing (held_item_tick 0x8002d7bc). Returns
# {sound: bool, hit: strength or -1, push: whether the blow pushes}.
# @orig game:0x8002d2a0 held_item_tick  status:transcribed -- the melee swing, phase 0; not the bows, the spells or phase 1
static func swing(w: Dictionary, rec: PackedByteArray) -> Dictionary:
	var ev := {"sound": false, "hit": -1, "push": false}
	if int(w["clock"]) == -1:
		return ev
	var rate := u16(rec, 0x1C)
	var end := u16(rec, 0x1E)
	var last := u16(rec, 0x2C)
	w["clock"] = s16(int(w["clock"]) + rate)
	var c: int = w["clock"]
	var t: int = w["sound"]
	if t <= c and c < t + rate:
		ev["sound"] = rec[0] != 0xFF
		w["sound"] = t if t < last else NEVER
	var h: int = w["hit"]
	if h <= c and c < h + rate:
		if c >= end:
			w["hit"] = NEVER
			w["pause"] = PAUSE
			w["meter"] = 0
			ev["hit"] = int(w["strength"])
			ev["push"] = true
		else:
			ev["hit"] = int(w["strength"]) >> 2
	if int(w["clock"]) >= 0x1000:
		w["clock"] = -1
	return ev


static func _mul(a: Array, b: Array) -> Array:
	var m := []
	for i in 3:
		for j in 3:
			m.append((int(a[3 * i]) * int(b[j]) + int(a[3 * i + 1]) * int(b[3 + j])
				+ int(a[3 * i + 2]) * int(b[6 + j])) >> 12)
	return m


# vec_rotate (0x800168a8): Ry(a1) Rx(a0) Rz(a2), each product through the GTE's
# >> 12, and the vector through ApplyMatrixLV.
# @orig game:0x800168a8 vec_rotate  status:transcribed
static func vec_rotate(c: KFCollision, ax: int, ay: int, az: int, v: Array) -> Array:
	var sz := c.game_sin(az)
	var cz := c.game_cos(az)
	var rz := [cz, -sz, 0, sz, cz, 0, 0, 0, 0x1000]
	var m := _mul(Array(c.rot_matrix_x(ax)), rz)
	m = _mul(Array(c.rot_matrix_y(ay)), m)
	var out := []
	for r in 3:
		out.append((int(m[3 * r]) * int(v[0]) + int(m[3 * r + 1]) * int(v[1])
			+ int(m[3 * r + 2]) * int(v[2])) >> 12)
	return out


# The quarter step the probe walks (0x8002dbd8): the reach turned by the view,
# its Y scaled by (0xe10 - reach) / 1800.
# @orig game:0x8002dbd8  status:transcribed -- a label inside held_item_tick
static func probe(c: KFCollision, pitch: int, facing: int, reach: int) -> Array:
	var v := vec_rotate(c, s16(-pitch), facing, 0, [0, 0, reach])
	var y := _trunc((0xE10 - reach) * int(v[1]), 1800)
	return [_trunc(int(v[0]), 4), _trunc(y, 4), _trunc(int(v[2]), 4)]


# 0x8004c5ec: one type of the player's blow against a creature's defence.
# @orig game:0x8004c5ec  status:transcribed
static func type_damage(stat: int, attack: int, defence: int) -> int:
	var a := attack * 16
	if a == 0:
		return 0
	a += stat * 16
	var d := defence * 16
	var over := maxi(a - d, 0)
	if d == 0:
		d = 0x10
	return over + _trunc(a * a, 2 * d)


# actor_take_hit's damage, before the level's hook: the eight summed and held
# to 0x68db7, times the strength over 5000, rounded to sixteenths.
# @orig game:0x8004c668 actor_take_hit  status:transcribed -- the damage; the reaction is actors.gd's strike
static func creature_damage(stat: int, attacks: Array, defence: Array, strength: int) -> int:
	var s := 0
	for i in 8:
		s += type_damage(stat, int(attacks[i]), int(defence[i]))
	s = mini(s, SUM_CAP)
	return (_trunc(s * strength, 5000) + 0x80) >> 4


# The push a hit gives a creature (0x8004cc10), from the player's point to its
# middle: isqrt(isqrt(dmg << 11)) << 10, over the weight, << 5, over the weight
# again, at most 0x200; X and Z >> 3, Y >> 6. Empty for a weight of 0xf0 or more.
# @orig game:0x8004cc10  status:transcribed -- a label inside actor_take_hit
static func knock(c: KFCollision, dmg: int, weight: int, point: Vector3i,
		pos: Vector3i, height: int) -> Array:
	if weight >= 0xF0:
		return []
	var dx := pos.x - point.x
	var dy := (pos.y - (height >> 1)) - point.y
	var dz := pos.z - point.z
	var yaw := c.vec_angle(dx, dz)
	var ln := c.isqrt((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3)) << 3
	var pitch := (-c.vec_angle(dy, ln)) & 0xFFF
	var d := c.direction_from_angles(pitch, yaw)
	var m := c.isqrt(c.isqrt(dmg << 11)) << 10
	m = mini(_trunc(_trunc(m, weight) << 5, weight), PUSH_CAP)
	return [s16((int(d[0]) * m) >> 12) >> 3, s16((int(d[1]) * m) >> 12) >> 6,
		s16((int(d[2]) * m) >> 12) >> 3]

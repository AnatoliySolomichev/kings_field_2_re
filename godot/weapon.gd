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
#
# @exe game

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


# @port data -- reads weapon.json: the 48 records and each level's guarded slot, as tools/weapon.py takes them
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


# @port helper -- a little-endian halfword out of a record
static func u16(raw: PackedByteArray, o: int) -> int:
	return raw[o] | (raw[o + 1] << 8)


# @port helper -- a halfword, sign-extended
static func s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v >= 0x8000 else v


# @port helper -- the MIPS div: the quotient truncated towards zero
static func _trunc(a: int, b: int) -> int:
	var q := absi(a) / absi(b)
	return -q if (a < 0) != (b < 0) else q


# @orig game:0x80029390 meter_gain  status:transcribed -- the meter's refill before it is doubled
static func gain(stat: int, rate: int) -> int:
	return mini(_trunc(stat << 6, rate + 1) + 1, FULL)


# held_item_tick's idle frame (0x8002dde8): nothing while attack is held, the
# pause first, then the refill -- the ring at 0x801b25d7 is not worn in the port.
# @orig game:0x8002dde8 held_item_tick+0xb48  status:transcribed -- a label inside held_item_tick
static func refill(w: Dictionary, rec: PackedByteArray, stat: int, held: bool) -> void:
	if held:
		return
	if int(w["pause"]) > 0:
		w["pause"] = int(w["pause"]) - 1
		return
	w["meter"] = mini((int(w["meter"]) + 2 * gain(stat, rec[1])) & 0xFFFF, FULL)


# swing_start (phase): the clock at 0, the hit and sound times off the record
# (+0x1e and +0x2c, or the combination's phase 1 +0x26 and +0x2e), the meter
# kept as the strength and emptied; begun on both meters full (0x801b25b3),
# the swing carries the record's +5 shots of its spell (0x801b25b2).
# @orig game:0x8002c040 swing_start  status:verified -- tools/weapon.py start, 200 of 200 as the game's own, both phases (magic_check); not 0x801b2568, which stops it and the port has not
static func start(w: Dictionary, rec: PackedByteArray, magic := FULL, phase := 0) -> bool:
	if int(w["clock"]) != -1:
		return false
	w["phase"] = phase
	w["clock"] = 0
	w["hit"] = u16(rec, 0x26 if phase != 0 else 0x1E)
	w["sound"] = u16(rec, 0x2E if phase != 0 else 0x2C)
	w["strength"] = int(w["meter"])
	w["charged"] = int(w["meter"]) == FULL and magic == FULL
	if bool(w["charged"]):
		w["shots"] = int(rec[5])
	w["meter"] = 0
	return true


# weapon_may_cast(which): may the weapon in hand cast its spell -- +3 for which
# 0, the swing's, +4 for which 1. The spell, if the record names one, must be
# unlocked; then excellector (2) and weapons 0xd..0x11 may, and every other
# only with the effective stat and the least of the five working skills
# both 50 or more.
# @orig game:0x8002cfe0 weapon_may_cast  status:verified -- tools/weapon.py may_cast, 200 of 200 as the game's own (magic_check)
static func may_cast(weapon: int, rec: PackedByteArray, which: int, unlocked: Array, stat: int,
		skills: Array) -> int:
	if weapon != 0xFF:
		var sp := int(rec[3 + which])
		if sp != 0xFF and (sp >= unlocked.size() or int(unlocked[sp]) == 0):
			return 0
	if weapon == 2 or (weapon >= 0xD and weapon < 0x12):
		return 1
	var least := 0x3E7
	for v in skills:
		if int(v) < least:
			least = int(v)
	return 1 if stat >= 0x32 and least >= 0x32 else 0


# held_item_tick's phase-0 stretch: after the clock moves, with the record's
# spell +3, the swing begun on both meters full, the weapon allowed and
# ACTION held, a frame inside the window +0x20..+0x22 spends a shot and a
# frame outside it loses them all. [spell, commit, n] for the shot, or [].
# @orig game:0x8002d81c held_item_tick+0x57c  status:verified -- tools/weapon.py magic_window, 200 of 200 frames of the game's own held_item_tick (magic_check)
static func magic_window(w: Dictionary, rec: PackedByteArray, action_held: bool, may: int) -> Array:
	if int(w.get("phase", 0)) != 0 or int(rec[3]) == 0xFF or not bool(w.get("charged", false)) \
			or may == 0 or not action_held:
		return []
	var c := int(w["clock"])
	if c < u16(rec, 0x20) or u16(rec, 0x22) < c:
		w["shots"] = 0
		return []
	var shots := int(w.get("shots", 0))
	if shots == 0:
		return []
	w["shots"] = (shots - 1) & 0xFF
	return [int(rec[3]), shots == int(rec[5]), shots]


# The swing's times by phase (held_item_tick 0x8002d7e4, .L21): the rate,
# the last blow's time, the time between blows, the last sound's time and the
# time between sounds; phase 0 has one blow and one sound (-1: none)
const FIELDS := [[0x1C, 0x1E, -1, 0x2C, -1], [0x24, 0x28, 0x2A, 0x30, 0x32]]
const FLAME_ROD := 0x21
const SEATHS_SWORD := 0xD


# One frame of a swing (held_item_tick 0x8002d7bc). Returns {sound: bool,
# hit: strength or -1, push: whether the blow pushes, shot: the weapon's
# spell cast, [spell, commit, n] or [] -- phase 0's charged window, or phase
# 1's every blow, +4, paid on the last -- fire: the flame rod's fire ball on a
# full magic meter}. Seath's sword in phase 1 meets its blow with ACTION held
# as a guard: w.guard (0x801b25b4) set, the clock held back, the blow waiting.
# At the end the clock -1 and the shots gone (.L41).
# @orig game:0x8002d7bc held_item_tick+0x51c  status:verified -- tools/weapon.py swing, both phases, the guard and the flame rod: 400 of 400 frames of the game's own (magic_check), the bp25 recording 817 of 817; not the bows
static func swing(w: Dictionary, rec: PackedByteArray, action_held := false, may := 0,
		weapon := -1, magic := 0) -> Dictionary:
	var ev := {"sound": false, "hit": -1, "push": false, "shot": [], "fire": false, "guard": false}
	if int(w["clock"]) == -1:
		return ev
	var phase := int(w.get("phase", 0))
	var f: Array = FIELDS[1 if phase != 0 else 0]
	var rate := u16(rec, f[0])
	var end := u16(rec, f[1])
	var last := u16(rec, f[3])
	var step := u16(rec, f[2]) if int(f[2]) >= 0 else 0
	var sstep := u16(rec, f[4]) if int(f[4]) >= 0 else 0
	w["clock"] = s16(int(w["clock"]) + rate)
	ev["shot"] = magic_window(w, rec, action_held, may)
	var c: int = w["clock"]
	var t: int = w["sound"]
	if t <= c and c < t + rate:
		ev["sound"] = rec[0] != 0xFF
		w["sound"] = s16(t + sstep) if t < last else NEVER
	var h: int = w["hit"]
	if h <= c and c < h + rate:
		ev["fire"] = weapon == FLAME_ROD and magic == FULL
		w["guard"] = 0
		if phase == 1:
			if weapon == SEATHS_SWORD and action_held:
				w["guard"] = 1
				w["clock"] = s16(c - rate)
				ev["guard"] = true
				return ev
			ev["shot"] = [int(rec[4]), c >= end, (c - u16(rec, 0x26)) / step if step != 0 else 0]
		if c >= end:
			w["hit"] = NEVER
			w["pause"] = PAUSE
			w["meter"] = 0
			ev["hit"] = int(w["strength"])
			ev["push"] = true
		else:
			w["hit"] = s16(h + step)
			ev["hit"] = int(w["strength"]) >> 2
	if int(w["clock"]) >= 0x1000:
		w["clock"] = -1
		w["shots"] = 0
	return ev


# player_turn's tail (0x80030298 on), once the USE stretch has let the frame
# through: the combination and the swing it starts. `c` holds 0x801b25aa as
# time and the pointer 0x801b258c as next, an index into the table player_turn
# writes at gp+0x1b8: the use, attack and action buttons and 0xffff (the
# halves after it read 0). `press` is the button word on a frame that newly
# presses one of the three, else 0. 1 starts the combination's swing, 0 the
# ordinary one (the attack button's edge, no pause, no combination under way),
# -1 neither.
# @orig game:0x80030298 player_turn+0x47c  status:verified -- tools/weapon.py turn_combo, 400 of 400 frames of the game's own player_turn (magic_check)
static func combo(c: Dictionary, rec: PackedByteArray, press: int, attack_edge: bool, binds: Array,
		may: int, full: bool, swing_pause: int) -> int:
	var table := [int(binds[0]), int(binds[1]), int(binds[2]), 0xFFFF]
	if int(c["time"]) != 0:
		c["time"] = (int(c["time"]) - 1) & 0xFF
	else:
		c["next"] = 0
	if press != 0 and u16(rec, 0x24) != 0:
		var k := int(c["next"])
		var want: int = table[k] if k < 4 else 0
		if may != 0 and int(rec[4]) != 0xFF and (press & want) != 0 and (k != 0 or full):
			c["next"] = k + 1
			if k + 1 < 4 and int(table[k + 1]) == 0xFFFF:
				return 1
			c["time"] = 20
		else:
			c["time"] = 0
	if swing_pause != 0 or int(c["time"]) != 0:
		return -1
	return 0 if attack_edge else -1


# @port helper -- a 3x3 product through the GTE's >> 12, for vec_rotate
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
# @orig game:0x8002dbd8 held_item_tick+0x938  status:transcribed -- a label inside held_item_tick
static func probe(c: KFCollision, pitch: int, facing: int, reach: int) -> Array:
	var v := vec_rotate(c, s16(-pitch), facing, 0, [0, 0, reach])
	var y := _trunc((0xE10 - reach) * int(v[1]), 1800)
	return [_trunc(int(v[0]), 4), _trunc(y, 4), _trunc(int(v[2]), 4)]


# 0x8004c5ec: one type of the player's blow against a creature's defence.
# @orig game:0x8004c5ec creature_type_damage  status:transcribed
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
# @orig game:0x8004cc10 actor_take_hit+0x5a8  status:transcribed -- a label inside actor_take_hit
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

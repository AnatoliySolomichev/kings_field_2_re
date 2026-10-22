class_name KFCreatureAI
extends RefCounted
# What an awake creature does each frame: tools/ai.py, line for line, which is
# actor_tick (0x800500a8) and its helpers read off GAME.EXE. FORMATS.md,
# "What an awake creature does", has the long form.
#
# A creature is actors.gd's dictionary with these added:
#
#   vx vz vy vst  the velocity +0x50/+0x54/+0x52 and the vertical state +0xd
#   turn          the turn rate +0x58          ry is the yaw +0x42
#   rec op phase  the running behaviour +0x60 (a record's bytes), its opcode
#                 +0xe and phase +0xf: 0 new, 0xf0 running, 0xff done
#   prev          the opcode before, +0x10     anim clock step  +0xc +0x18 +0x66
#   aim sub n72   +0x64, a behaviour's own state +0x70, +0x72
#   flee cut      opcode 5's +0x70 and +0x71
#
# and a kind is {accel, turn_accel, fall, radius, height, behaviours}.
#
# @exe game

const HOLD := 0x800                # +0x28: bortecth's hold, set by actor_attack_player's code bit 0x10000

var coll: KFCollision
var rand: Callable                 # the BIOS rand, 0..0x7fff


# @port helper -- a halfword, sign-extended
static func s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v >= 0x8000 else v


# @port helper -- a little-endian halfword out of a record's bytes
static func u16f(raw: Array, off: int) -> int:
	if off + 1 >= raw.size():
		return 0
	return int(raw[off]) | (int(raw[off + 1]) << 8)


# @port helper -- the same, sign-extended
static func s16f(raw: Array, off: int) -> int:
	return s16(u16f(raw, off))


# @orig game:0x800170c0 rand_score  status:transcribed
func rand_score(x: int) -> int:
	# 0x800170c0: ((rand() + rand()) * x) >> 15, 0 to 2x
	var r1: int = rand.call()
	var r2: int = rand.call()
	return ((r1 + r2) * x) >> 15


# @orig game:0x80016a2c facing_test  status:verified -- 300 of 300 calls of the game's own (tools/routines.py)
static func facing_test(a: int, b: int, tol: int) -> bool:
	var d := (a - b) & 0xFFF
	return d <= tol or d >= 0x1000 - tol


# @orig game:0x80017158 fixed_madd  status:verified -- 300 of 300 calls of the game's own (tools/routines.py)
static func lerp_fixed(a: int, b: int, t: int) -> int:
	# fixed_madd (0x80017158): a + ((b - a) * t >> 12)
	return a + (((b - a) * t) >> 12)


# -- the clock ------------------------------------------------------------------

# @orig game:0x8004db3c actor_clock  status:transcribed
static func clock(a: Dictionary, rate: int) -> void:
	# actor_clock (0x8004db3c)
	rate = s16(rate)
	a["step"] = absi(rate)
	var t := s16(int(a["clock"]) + rate)
	a["clock"] = 0xFFF if t >= 0x1000 else (0 if t < 0 else t)


# @orig game:0x8004db08 sub_8004db08  status:transcribed -- actor_clock that wraps instead of stopping
static func clock_loop(a: Dictionary, rate: int) -> void:
	# 0x8004db08
	rate = s16(rate)
	a["step"] = absi(rate)
	a["clock"] = (int(a["clock"]) + rate) & 0xFFF


# @orig game:0x8004db98 actor_clock_passed  status:transcribed
static func clock_passed(a: Dictionary, t: int) -> bool:
	# actor_clock_passed (0x8004db98)
	return t < int(a["clock"]) and not t < int(a["clock"]) - int(a["step"])


# @orig game:0x8004c130 actor_start_anim  status:partial -- not the +2 it adds while 0x80199150 is set for the actor at 0x80199148
static func start_anim(a: Dictionary, anim: int) -> void:
	if anim != 0xFF:
		a["anim"] = anim
		a["clock"] = 0


# @orig game:0x8004b94c actor_switch  status:transcribed
static func switch_to(a: Dictionary, rec) -> void:
	# actor_switch (0x8004b94c)
	a["prev"] = a["op"]
	if rec == null:
		a["rec"] = null
		a["op"] = 0xFF
		a["phase"] = 0xFF
	else:
		a["rec"] = rec
		a["op"] = int(rec[0])
		a["phase"] = 0


# @orig game:0x8004c3bc actor_activate+0x1cc  status:transcribed -- asks for 0x15, then 6, then 0x1a
# @orig game:0x8004c068 kind_behaviour_with_op  status:transcribed
static func entrance(kind: Dictionary):
	# 0x8004c068 as actor_activate asks it: 0x15, else 6, else 0x1a
	for op in [0x15, 6, 0x1A]:
		for rec in kind["behaviours"]:
			if int(rec[0]) == op:
				return rec
	return null


# -- choosing -------------------------------------------------------------------

# @orig game:0x8004b984 actor_behaviour  status:partial -- the opcodes level 0's kinds use
func score(a: Dictionary, rec: Array, dist: int, player: Vector3i) -> int:
	# actor_behaviour (0x8004b984), the opcodes level 0's kinds use
	var op := int(rec[0])
	var cur: bool = is_same(rec, a["rec"])
	var base := int(rec[3]) if cur else int(rec[2])
	match op:
		0:
			return rand_score(base) if u16f(rec, 0xC) < dist else 0
		1:
			if not u16f(rec, 0x10) < dist or u16f(rec, 0x12) < dist:
				return 0
			return rand_score(base)
		5:
			if cur:
				return 0 if u16f(rec, 0x12) < dist else rand_score(int(rec[3]))
			var sc := 0 if u16f(rec, 0x10) < dist else rand_score(int(rec[2]))
			if int(a["op"]) in [4, 0x12, 0x17, 0x18, 0x84]:
				sc <<= 1
			return sc
		4:
			if int(a["eflags"]) & 0x100 or u16f(rec, 0x1A) < dist:
				return 0
			var y: int = a["py"]
			if y - int(a["height"]) > player.y + 0xC8 or player.y + 0xC8 - 0x834 > y:
				return 0
			var brg := s16(coll.vec_angle(player.x - int(a["px"]), player.z - int(a["pz"])))
			if not facing_test(s16(a["ry"]), brg, int(rec[0x10]) << 4):
				return 0
			if cur:
				return rand_score(int(rec[3]))
			var sc4 := int(rec[2])
			var near := int(rec[0xE]) << 6
			if not dist < (near + u16f(rec, 0x1A)) >> 1:
				sc4 -= sc4 / 3
			elif not dist < near:
				sc4 -= sc4 / 6
			return rand_score(sc4)
		0x19:
			# 0x8004bcdc: at range and facing; flag 0x100 holds it back, and a
			# record whose +0xc is 0x27 lifts that
			if int(a["eflags"]) & 0x100:
				if int(rec[0xC]) == 0x27:
					a["eflags"] = int(a["eflags"]) & ~0x100
				return 0
			if u16f(rec, 0x16) < dist or dist < u16f(rec, 0x14):
				return 0
			var b19 := s16(coll.vec_angle(player.x - int(a["px"]), player.z - int(a["pz"])))
			if not facing_test(s16(a["ry"]), b19, int(rec[0xD]) << 4):
				return 0
			return rand_score(base)
		2, 3:
			return 0
		0x70:
			return -1
	if op < 0x80:
		return rand_score(base)
	return -2


# @orig game:0x8004c01c actor_choose  status:transcribed -- the distance, through dist_to
# @orig game:0x8004bf1c actor_pick  status:transcribed
func pick(a: Dictionary, kind: Dictionary, player: Vector3i) -> void:
	# actor_pick (0x8004bf1c)
	if int(a["phase"]) == 0xF0 or int(a["phase"]) == 0:
		return
	var dist := dist_to(a, player)
	var best := -2
	var best_rec = null
	for rec in kind["behaviours"]:
		var sc := score(a, rec, dist, player)
		if best < sc:
			best = sc
			best_rec = rec
	if best_rec != null and (not is_same(best_rec, a["rec"]) or int(a["phase"]) == 0xFF):
		switch_to(a, best_rec)


# @orig game:0x8004c104 actor_finish  status:transcribed
func finish(a: Dictionary, kind: Dictionary, player: Vector3i) -> void:
	# actor_finish (0x8004c104)
	a["phase"] = 0xFF
	pick(a, kind, player)


# @orig game:0x80016c08 vec_length_2d  status:transcribed -- of the actor to the player, as actor_choose takes it
func dist_to(a: Dictionary, player: Vector3i) -> int:
	# vec_length_2d (0x80016c08)
	var dx: int = (player.x - int(a["px"])) >> 3
	var dz: int = (player.z - int(a["pz"])) >> 3
	return coll.isqrt(dx * dx + dz * dz) << 3


# -- moving ---------------------------------------------------------------------

# @orig game:0x80015fdc approach  status:verified -- 300 of 300 calls of the game's own (tools/routines.py)
static func approach(cur: int, target: int, step: int) -> int:
	# 0x80015fdc
	if step > 0:
		if cur < target:
			return mini(cur + step, target)
		if target < cur:
			return maxi(cur - step, target)
		return cur
	if target < cur:
		return maxi(cur + step, target)
	if cur < target:
		return mini(cur - step, target)
	return cur


# @orig game:0x8004e928 actor_turn  status:transcribed
func turn(a: Dictionary, target: int, most: int, accel: int) -> void:
	# 0x8004e928
	target = s16(target)
	var yaw := s16(a["ry"])
	if ((yaw - target) & 0xFFF) == 0:
		a["turn"] = 0
		return
	if ((target - yaw) & 0xFFF) < 0x801:
		var r := s16(int(a["turn"]) + accel)
		a["turn"] = s16(most) if s16(most) < r else r
	else:
		var r := s16(int(a["turn"]) - accel)
		a["turn"] = -s16(most) if r < -s16(most) else r
	var old := yaw
	a["ry"] = s16(old + int(a["turn"]))
	if int(a["turn"]) > 0:
		if _gt(target, old) and not _gt(target, int(a["ry"])):
			a["ry"] = target
	else:
		if _gt(old, target) and not _gt(int(a["ry"]), target):
			a["ry"] = target


# @orig game:0x80016a78 sub_80016a78  status:transcribed -- the angle difference; its callers' > 0 folded in
static func _gt(p: int, q: int) -> bool:
	# 0x80016a78
	return s16(((p + 0x800) & 0xFFF) - ((q + 0x800) & 0xFFF)) > 0


# @orig game:0x8004e824 actor_drive  status:transcribed
func drive(a: Dictionary, yaw: int, speed: int, accel: int, flags: int,
		others: Array, player: Vector3i) -> int:
	# 0x8004e824
	var dx := -coll.game_sin(s16(yaw))
	var dz := coll.game_cos(s16(yaw))
	var tx := (s16(speed) * dx) >> 11
	var tz := (s16(speed) * dz) >> 11
	var ax := (s16(accel) * dx) >> 11
	var az := (s16(accel) * dz) >> 11
	a["vx"] = s16(approach(int(a["vx"]), tx, ax))
	a["vz"] = s16(approach(int(a["vz"]), tz, az))
	return move_horizontal(a, flags, others, player)


# @orig game:0x8004ea7c actor_walk_to  status:transcribed
func walk_to(a: Dictionary, angle: int, speed: int, most: int, accel: int,
		turn_accel: int, flags: int, others: Array, player: Vector3i) -> int:
	# 0x8004ea7c
	turn(a, angle, most, turn_accel)
	return drive(a, int(a["ry"]), speed, accel, flags, others, player)


# @orig game:0x8004e6f8 actor_brake  status:transcribed
func brake(a: Dictionary, decel: int, flags: int, others: Array, player: Vector3i) -> int:
	# 0x8004e6f8
	if int(a["vst"]) != 0:
		return move_horizontal(a, flags, others, player)
	var vx: int = a["vx"]
	var vz: int = a["vz"]
	var n := coll.isqrt(vx * vx + vz * vz)
	if n == 0:
		return 0
	a["vx"] = s16(approach(vx, 0, coll._idiv((vx * decel) << 1, n)))
	a["vz"] = s16(approach(vz, 0, coll._idiv((vz * decel) << 1, n)))
	return move_horizontal(a, flags, others, player)


# collide_query for a creature: its own radius and height on the tiles, then
# the other awake creatures (0x10) and the player (0x80).
# @orig game:0x80033f38 collide_query  status:partial -- a creature's 0x93: the tiles, the fence (2), the other creatures (0x10) and the player (0x80)
func _query(a: Dictionary, x: int, z: int, others: Array, player: Vector3i) -> Dictionary:
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = int(a["radius"])
	coll.body = int(a["height"])
	var q := coll.query(x, int(a["py"]), z)
	coll.radius = keep_r
	coll.body = keep_b
	if coll.fenced(q):                  # 0x80033f94: flag 2 of the creatures' 0x93
		q["mask"] = int(q["mask"]) | 1
		q["floor"] = KFCollision.FENCED_SURFACE
	q["thing"] = null
	for o in others:
		if o == a:
			continue
		if coll.in_range(o["px"], o["py"], o["pz"], x, int(a["py"]), z,
				int(o["radius"]) + int(a["radius"]), o["height"], a["height"]) != -1:
			q["mask"] = int(q["mask"]) | 0x10
			q["thing"] = Vector2i(o["px"], o["pz"])
			return q
	if coll.in_range(player.x, player.y, player.z, x, int(a["py"]), z,
			0x320 + int(a["radius"]), 0x6A4, a["height"]) != -1:
		q["mask"] = int(q["mask"]) | 0x80
		q["thing"] = Vector2i(player.x, player.z)
	return q


# @orig game:0x80033f38 collide_query  status:partial -- the floor alone, at a creature's size, for actor_move_horizontal's probes
func _floor_at(a: Dictionary, x: int, z: int) -> int:
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = int(a["radius"])
	coll.body = int(a["height"])
	var f := int(coll.query(x, int(a["py"]), z)["floor"])
	coll.radius = keep_r
	coll.body = keep_b
	return f


# actor_move_horizontal (0x8004dbc8): tools/ai.py move_horizontal.
# @orig game:0x8004dbc8 actor_move_horizontal  status:transcribed
func move_horizontal(a: Dictionary, flags: int, others: Array, player: Vector3i) -> int:
	var sx := s16(a["vx"])
	var sz := s16(a["vz"])
	if sx == 0 and sz == 0:
		return 0
	var s7 := sx
	var s6 := sz
	var seen := 0
	var things := 0
	var diag := false
	var second := false
	for _i in 16:
		var tx: int = int(a["px"]) + sx
		var tz: int = int(a["pz"]) + sz
		var q := _query(a, tx, tz, others, player)
		var mask: int = q["mask"]
		var cur: int = q["floor"]
		var take := mask == 0
		var slide := false
		if not take:
			seen |= mask
			if flags & 3 == 0:
				break
			if mask & 0xB0:
				things += 1
				if things == 2:
					break
				var th: Vector2i = q["thing"]
				var b := coll.vec_angle(th.x - int(a["px"]), th.y - int(a["pz"]))
				var step_dir := s16(coll.vec_angle(sx, sz))
				var side := (b + 0x400) if ((step_dir - s16(b)) & 0xFFF) < 0x801 else (b - 0x400)
				side &= 0xFFF
				var n := coll.isqrt(sx * sx + sz * sz)
				sx = (-coll.game_sin(side) * n) >> 13
				sz = (coll.game_cos(side) * n) >> 13
				continue
			if not (flags & 0x10):
				if int(a["eflags"]) & 0x4000:
					slide = true
				elif mask & ~0x205 == 0:
					if cur + 0x320 < int(a["py"]):
						slide = true
					else:
						take = true
			if not take and not slide:
				if mask & 1:
					slide = true
				elif mask & 2:
					if diag:
						slide = true
					else:
						var rot := 0
						var cx := tx >> 11
						var cz := tz >> 11
						if cx >= 0 and cx < 80 and cz >= 0 and cz < 80:
							rot = coll.cells[(cz * 80 + cx) * 6 + 1] & 3
						if rot == 0 or rot == 2:
							sx = (s7 + s6) >> 1
							sz = sx
						else:
							sx = (s7 - s6) >> 1
							sz = -sx
						diag = true
						continue
				else:
					break
		if take:
			if int(a["vst"]) == 0 and flags & 0x24:
				var lowest := cur
				var ax := 0
				var az := 0
				if sx != 0:
					ax = (int(a["radius"]) << 1) * (1 if sx > 0 else -1)
				if sz != 0:
					az = (int(a["radius"]) << 1) * (1 if sz > 0 else -1)
				lowest = maxi(lowest, _floor_at(a, int(a["px"]), int(a["pz"]) + az))
				lowest = maxi(lowest, _floor_at(a, int(a["px"]) + ax, int(a["pz"])))
				if int(a["py"]) < lowest - 0x44C:
					seen |= 0x100
					if flags & 4:
						slide = true
						take = false
			if take:
				a["px"] = tx
				a["pz"] = tz
				break
		if slide:
			if second:
				sx = 0
				sz = 0
				break
			if sx != 0:
				sx = 0
				if flags & 1:
					var n1 := coll.isqrt(s7 * s7 + s6 * s6)
					sz = n1 if s6 > 0 else -n1
				else:
					sz = s6
				continue
			if sz != 0:
				sz = 0
				if flags & 1:
					var n2 := coll.isqrt(s7 * s7 + s6 * s6)
					sx = n2 if s7 > 0 else -n2
				else:
					sz = s6
				second = true
				continue
			break
	if flags & 8:
		a["vx"] = s16(sx)
		a["vz"] = s16(sz)
	return seen


# actor_move_vertical (0x8004e330), states 0, 0x10 and 0x20. Each frame
# the floor it stands on (+3) is the layer collide_surface asked -- 2 the
# upper, else 1 (0x8004e3b4) -- and again the one a free fall's step was
# asked on (0x8004e680).
# @orig game:0x8004e330 actor_move_vertical  status:partial -- not the ballistic 0x30, nor the blow a fall onto the player deals
func move_vertical(a: Dictionary, kind: Dictionary) -> void:
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = int(a["radius"])
	coll.body = int(a["height"])
	var sq := coll.query(int(a["px"]), int(a["py"]), int(a["pz"]), int(a["py"]) - 0x500)
	var surf := int(sq["floor"])
	if int(sq["at"]) >= 0:
		a["floor"] = 2 if int(sq["at"]) % 6 == 3 else 1
	match int(a["vst"]):
		0:
			var d := surf - int(a["py"])
			if d < 0:
				a["vst"] = 0x20
				a["vy"] = -0x64
			elif d > 0:
				a["vst"] = 0x10
				a["vy"] = 0
		0x20:
			a["py"] = int(a["py"]) + int(a["vy"])
			a["vy"] = s16(int(a["vy"]) + 5)
			if not (surf < int(a["py"]) and int(a["vy"]) < 0):
				a["py"] = surf
				a["vst"] = 0
		0x10:
			var ny: int = int(a["py"]) + int(a["vy"])
			var q := coll.query(int(a["px"]), ny, int(a["pz"]))
			if coll.fenced(q):          # 0x8004e488 asks collide_query too
				q["mask"] = int(q["mask"]) | 1
				q["floor"] = KFCollision.FENCED_SURFACE
			if int(q["mask"]) == 0:
				a["py"] = ny
				a["vy"] = s16(int(a["vy"]) + int(kind["fall"]))
				if int(q["at"]) >= 0:
					a["floor"] = 2 if int(q["at"]) % 6 == 3 else 1
			elif int(q["mask"]) & 4:
				a["py"] = int(q["floor"])
				a["vy"] = 0
				a["vst"] = 0
			else:
				a["vst"] = 0
	coll.radius = keep_r
	coll.body = keep_b


# -- one frame --------------------------------------------------------------------

# Returns a blow opcode 4 struck this frame -- {reach, lift, arc, rec} -- or {}.
# A flinch (op 2) held (+0x28 bit 0x800) past its first half runs no clock,
# so waits; a death (op 3) held with its clock at 0x400 or past does nothing
# but the tail -- no clock, no drop, no brake -- until the hold is let go.
# @orig game:0x800500a8 actor_tick  status:partial -- the arms of opcodes 0 to 6 and 0x19: 8 of the 30 its switch has besides the one 209 opcodes share; the hold in 2 and 3 against the game's own, tools/ai.py hold_check, 1680 of 1680
func tick(a: Dictionary, kind: Dictionary, player: Vector3i, others: Array) -> Dictionary:
	var blow := {}
	if a["rec"] == null:
		return blow
	var raw: Array = a["rec"]
	var dist := dist_to(a, player)
	match int(a["op"]):
		0:
			if int(a["phase"]) == 0:
				a["phase"] = 0xF0
				start_anim(a, int(raw[1]))
			clock(a, s16f(raw, 8))
			brake(a, int(kind["accel"]), 0xA, others, player)
			_done(a, kind, player)
		1:
			if int(a["phase"]) == 0:
				a["phase"] = 0xF0
				start_anim(a, int(raw[1]))
				a["aim"] = int(rand.call()) >> 3
			else:
				var hit := walk_to(a, s16(a["aim"]), u16f(raw, 0xC), u16f(raw, 0xE),
					int(kind["accel"]), int(kind["turn_accel"]), 5, others, player)
				if hit != 0 or (int(rand.call()) >> 5) < int(raw[0x14]):
					a["aim"] = int(rand.call()) >> 3
			clock(a, s16f(raw, 8))
			_done(a, kind, player)
		5:
			if int(a["phase"]) == 0:
				a["phase"] = 0xF0
				start_anim(a, int(raw[1]))
				a["flee"] = 1 if int(a["prev"]) in [4, 0x12, 0x17, 0x18] else 0
				a["cut"] = 0
			if int(rand.call()) < 0x1770:
				if not dist < u16f(raw, 0x16):
					a["flee"] = 0
				elif not u16f(raw, 0x14) < dist:
					a["flee"] = 1
			var brg := s16(coll.vec_angle(player.x - int(a["px"]), player.z - int(a["pz"])))
			a["aim"] = brg
			var fl := 0x21 if int(a["cut"]) else 5
			var got := 0
			if int(a["flee"]) == 0:
				got = walk_to(a, brg, u16f(raw, 0xC), u16f(raw, 0xE), int(kind["accel"]),
					int(kind["turn_accel"]), fl, others, player)
			else:
				got = drive(a, s16(brg + 0x800), u16f(raw, 0xC), int(kind["accel"]), fl,
					others, player)
			var toggle := false
			if got & 0x100:
				if int(a["cut"]) == 0:
					if int(rand.call()) < u16f(raw, 0x18):
						a["cut"] = 1
					else:
						toggle = true
			else:
				a["cut"] = 0
				toggle = got != 0
			if toggle:
				a["flee"] = 0 if int(a["flee"]) else 1
			clock(a, s16f(raw, 8))
			_done(a, kind, player)
		4:
			if int(a["phase"]) == 0:
				a["phase"] = 0xF0
				start_anim(a, int(raw[1]))
			clock(a, s16f(raw, 8))
			if clock_passed(a, u16f(raw, 0x18)):
				blow = {"reach": int(raw[0xE]) << 6, "lift": int(raw[0xF]) << 5,
					"arc": int(raw[0x10]) << 4, "rec": raw}
			if int(a["clock"]) >= 0xFFF:
				finish(a, kind, player)
			brake(a, int(raw[0xD]), 0xA, others, player)
		6:
			_burrowed(a, kind, raw, player, others, dist)
		0x19:                           # 0x800523f0, a volley
			if int(a["phase"]) == 0:
				a["phase"] = 0xF0
				start_anim(a, int(raw[1]))
				a["sub"] = u16f(raw, 0xE)
				a["n72"] = 0
				if int(raw[7]) == 1:
					a["vst"] = 0x10
			clock(a, s16f(raw, 8))
			if clock_passed(a, int(a["sub"])):
				a["sub"] = (int(a["sub"]) + u16f(raw, 0x12)) & 0xFFFF
				if u16f(raw, 0x10) < s16(int(a["sub"])):
					a["sub"] = 0
				a["fired"] = volley(raw, a)     # actors.gd launches them
			if int(a["clock"]) >= 0xFFF:
				finish(a, kind, player)
			brake(a, int(kind["accel"]), 0xA, others, player)
		2:                              # 0x80050400, a flinch
			if int(a["phase"]) == 0:
				a["phase"] = 0xF0
				a["sub"] = 0
				start_anim(a, int(raw[1]))
			var s2: int = int(a["sub"])
			if s16(s2) < 2 or (int(a.get("eflags", 0)) & HOLD) == 0:   # 0x80050424: held,
				clock(a, s16f(raw, 8))                                  # the second half waits
			if s2 == 0:
				a["sub"] = 1
			elif s2 == 1 and int(a["clock"]) >= 0x7FF:
				a["sub"] = 2
			elif s2 == 2 and int(a["clock"]) >= 0xFFF:
				a["sub"] = 3
			elif s2 == 3:
				finish(a, kind, player)
			brake(a, int(kind["accel"]) << 1, 0xA, others, player)   # 0x80052bd0
		3:                              # 0x800505a4, dying
			if int(a["phase"]) == 0:
				a["phase"] = 0xF0
				a["sub"] = 0
				start_anim(a, int(raw[1]))
			var s3: int = int(a["sub"])
			if s3 == 0 and int(a["clock"]) >= 0x400 and (int(a.get("eflags", 0)) & HOLD) != 0:
				move_vertical(a, kind)      # 0x8005063c: held, nothing but the tail (0x80052c14)
				return blow
			if s3 == 0:
				clock(a, s16f(raw, 8))
				if clock_passed(a, 0x800):  # 0x800506c0: what it leaves
					a["drop"] = drops(a, kind, raw)
				if int(a["clock"]) >= 0xFFF or s16f(raw, 8) == 0:
					a["sub"] = 0xF
			else:
				a["sub"] = s3 + 1
				if s3 >= 0x26:          # 0x80050868: gone, by its category
					a["retire"] = true
					return blow
			brake(a, int(kind["accel"]) << 1, 0xA, others, player)
	move_vertical(a, kind)
	return blow


# What a dying creature leaves when its clock crosses 0x800: the gold -- its
# kind's +0x30 and the spread, two rolls made whatever the gold -- when it
# comes to more than 0, and a thing: for categories 0 and 4 the dying
# behaviour's +0xc if not 0xff and rand() >> 7 is under its +0xd, for
# category 1 the one it was placed with (+0xb). tools/ai.py drops.
# @orig game:0x800506c0 actor_tick+0x618  status:transcribed -- the gold (random_spread, spawn_gold) and the thing (spawn_thing), as drops for loot.gd to make; checked as tools/ai.py's, whose replay keeps 336 of 336 dying frames with the rolls in
func drops(a: Dictionary, kind: Dictionary, raw: Array) -> Array:
	var out := []
	var g := int(kind.get("gold", 0))
	var r := int(rand.call()) + int(rand.call()) - 0x8000
	var amount := (g + ((r * g) >> 15)) & 0xFFFF
	if amount != 0:
		var ang := (int(rand.call()) >> 3) & 0xFFFF
		out.append({"type": 0x95, "amount": amount, "ring": 0x15E,
			"pos": [int(a["px"]) + ((600 * coll.game_sin(ang)) >> 12),
				int(a["py"]) - (int(a["height"]) >> 1),
				int(a["pz"]) + ((600 * coll.game_cos(ang)) >> 12)],
			"yaw": (int(rand.call()) >> 3) & 0xFFFF})
	var cat := int(a.get("cat", 0))
	var thing := -1
	var ring := 0x172                 # what a category-1 creature carried: 370 up
	if cat == 0 or cat == 4:
		if int(raw[0xC]) != 0xFF and (int(rand.call()) >> 7) < int(raw[0xD]):
			thing = int(raw[0xC])
			ring = 0x168              # a dying behaviour's: 360 up
	elif cat == 1 and int(a.get("b6", 0xFF)) != 0xFF:
		thing = int(a["b6"])
	if thing >= 0:
		out.append({"type": thing, "amount": 0, "ring": ring,
			"pos": [int(a["px"]), int(a["py"]) - (int(a["height"]) >> 1), int(a["pz"])],
			"yaw": (int(rand.call()) >> 3) & 0xFFFF})
	return out


# @orig game:0x80051cf8 actor_tick+0x1c50  status:transcribed -- the tail the arms share: clock at 0xfff, actor_finish
func _done(a: Dictionary, kind: Dictionary, player: Vector3i) -> void:
	if int(a["clock"]) >= 0xFFF:
		finish(a, kind, player)


# @orig game:0x8005205c actor_tick+0x1fb4  status:transcribed -- opcode 6's arm
func _burrowed(a: Dictionary, kind: Dictionary, raw: Array, player: Vector3i,
		others: Array, dist: int) -> void:
	if int(a["phase"]) == 0:
		a["phase"] = 0xF0
		a["sub"] = 0
		start_anim(a, int(raw[1]))
		a["radius"] = u16f(raw, 0x16)
		a["height"] = u16f(raw, 0x18)
		if u16f(raw, 0xE) != 0:
			a["aim"] = int(rand.call()) >> 3
	match int(a["sub"]):
		0:
			clock_loop(a, s16f(raw, 8))
			if dist < u16f(raw, 0xC) and not int(a["clock"]) < 0xFFF - u16f(raw, 8):
				a["sub"] = 2
				a["clock"] = 0
				start_anim(a, int(raw[0x1A]))
			var hit := walk_to(a, s16(a["aim"]), u16f(raw, 0xE), u16f(raw, 0x10),
				int(kind["accel"]), int(kind["turn_accel"]), 5, others, player)
			if hit != 0 or (int(rand.call()) >> 5) < int(raw[0x1C]):
				a["aim"] = int(rand.call()) >> 3
		2:
			clock(a, s16f(raw, 8))
			a["radius"] = lerp_fixed(u16f(raw, 0x16), int(kind["radius"]), int(a["clock"]))
			a["height"] = lerp_fixed(u16f(raw, 0x18), int(kind["height"]), int(a["clock"]))
			if not int(a["clock"]) < 0xFFF:
				a["radius"] = kind["radius"]
				a["height"] = kind["height"]
				a["sub"] = 3
				a["n72"] = u16f(raw, 0x12)
		3:
			# 0x80052284: walk_to the aim, most 0 and turn accel 0 -- a rate it
			# has still turns it while the aim is behind
			walk_to(a, s16(int(a["aim"])), u16f(raw, 0xE), 0, 0xFF, 0, 5, others, player)
			a["n72"] = s16(int(a["n72"]) - 1)
			if int(a["n72"]) == -1:
				finish(a, kind, player)
			clock(a, int(raw[0x1B]))


# @port helper -- a halfword of a volley's list, 0 past the record's end
static func _word(raw: Array, k: int) -> int:
	return u16f(raw, 0x1A + 2 * k) if 0x1A + 2 * k + 1 < raw.size() else 0


# The list at a volley record's +0x1a from +0x72 (0x80052484): the entries to
# fire -- a vertex of the creature's model each, for level 0's records; 0x8000
# goes back to the start, 0x8001 n sets how many, 0x8003 n skips n, and the
# three-argument 0x8002 and 0x8004 are passed on as [code, a, b, c]. Each
# carries last the word further down the list that the arms 0x55 and 0x76
# read through the pointer actor_animation_effects is handed: a plain
# entry's at the entry + the entries left less one, two on; an 0x8002's two
# after its three (0x8004's is the stack's, 0 here).
# @orig game:0x80052484 actor_tick+0x23dc  status:transcribed -- a label inside actor_tick; tools/effects.py volley
static func volley(raw: Array, a: Dictionary) -> Array:
	var fired := []
	var left := 1
	var i := int(a.get("n72", 0))
	var guard := 0
	while left > 0 and guard < 64:
		guard += 1
		var e := u16f(raw, 0x1A + 2 * i)
		i += 1
		if e == 0x8000:
			i = 0
		elif e == 0x8001:
			left = u16f(raw, 0x1A + 2 * i)
			i += 1
		elif e == 0x8003:
			i += 1 + u16f(raw, 0x1A + 2 * i)
		elif e == 0x8002 or e == 0x8004:
			fired.append([e, s16f(raw, 0x1A + 2 * i), s16f(raw, 0x1C + 2 * i), s16f(raw, 0x1E + 2 * i),
				_word(raw, i + 5) if e == 0x8002 else 0])
			i += 3
			left -= 1
		else:
			fired.append([e, _word(raw, i + left + 1)])
			left -= 1
	a["n72"] = i
	return fired


# What actor_wake leaves, with the entrance behaviour switched in.
# @orig game:0x8004b698 actor_wake  status:partial -- the AI bytes cleared; its random yaw is actors.gd _spawn's, the cells it marks are not here
# @orig game:0x8004c3f8 actor_activate+0x208  status:transcribed -- the entrance behaviour switched in
static func wake(a: Dictionary, kind: Dictionary) -> void:
	for k in ["vx", "vz", "vy", "vst", "turn", "op", "prev", "anim", "clock",
			"step", "aim", "sub", "n72", "flee", "cut"]:
		a[k] = 0
	a["rec"] = null
	a["phase"] = 0xFF
	a["radius"] = kind["radius"]
	a["height"] = kind["height"]
	var rec = entrance(kind)
	if rec != null:
		switch_to(a, rec)

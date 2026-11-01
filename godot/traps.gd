class_name KFTraps
# The traps: opcode 0x51, which swings or runs by its clock, and 0x52, which
# comes up out of the floor for one run when the player steps into its
# rectangle. A model that moves by its clock +0xa and one or two of its
# vertices, each asked of collide_query every frame; what stands there is
# struck once a meeting. Opcode 0x55 rolls between two cells and strikes every
# frame it touches; 0x5a, a gate, shuts behind whoever walked in; 0x32 strikes
# nothing and only moves by a clock, its own or a creature's. tools/traps.py
# has it in prose.
#
# Over dictionaries, not the game's bytes: forty-four of them run every frame
# of levels 12, 15 and 18 from the moment the level comes in, and the port does
# not make the level's bytes for that. `d` is the object as loot.gd keeps it,
# `row` what the arms read of its type, `w` the world as Callables -- rect,
# vertex, query, attack, sound, present. tools/traps.py is the same in Python,
# held to the game's own arms; the self-test holds this to it.
#
# @exe game

const SWING_OP := 0x51
const POP_OP := 0x52
const ROLL_OP := 0x55
const GATE_OP := 0x5A
const FOLLOW_OP := 0x32
const OPS := [SWING_OP, POP_OP, ROLL_OP, GATE_OP, FOLLOW_OP]
const QUERY := 0x90                    # the creatures and the player
const NEVER := 0xFE
const FREE := 0xFF
const THE_END := 0xFFF
const REST_STEP := 0x40
const SOUND := 0x1E
const BIG_STEP_TYPE := 0xDE            # steps in sixteens, not fours; no 0x51 has it
const NEAR := 0xA000                   # twenty cells: nearer, a trap's mesh is posed
const WAY_BACK := 1                    # 0x55's +0x42
const WAY_ACROSS := 2
const ROLL_LOWER := 0x800              # the strike's question, this far below the vertex
const GATE_RADIUS := 0x1130
const GATE_HEIGHT := 0xC80
const GATE_FLAGS := 0xC0
const GATE_MASK := 0x2D                # shape, tile, rotation, fence
const GATE_DONE := 9

static var posed_cache := {}


# The strike, once a meeting: +0x40 clear, it is set and actor_attack_player
# called with the mask whole.
# @orig game:0x80049a7c object_interpreter+0x2a6c  status:verified -- .L200; tools/traps.py, 3600 of 3600 frames of the game's own arms, actor_attack_player logged, the self-test this to it
static func _hit(d: Dictionary, row: Dictionary, w: Dictionary, p: Array, mask: int) -> void:
	if int(d["b40"]) != 0:
		return
	d["b40"] = 1
	w["attack"].call(mask, int(d["b39"]), row["att"], p)


# @port helper -- each vertex asked in turn, the first met struck, +0x40 cleared when none is
static func _strike(d: Dictionary, row: Dictionary, w: Dictionary, verts: Array) -> void:
	for v in verts:
		var p: Array = w["vertex"].call(d, v)
		var mask: int = w["query"].call(p, int(row["radius"]), int(row["height"]), QUERY)
		if mask != 0:
			_hit(d, row, w, p, mask)
			return
	d["b40"] = 0


# @port helper -- state 2's start, +0x38 0
static func _rest(d: Dictionary) -> void:
	d["state"] = 2
	d["b1"] = 1
	d["ha"] = 0


# @port helper -- state 2's clock; its end, with +0x38 0xff, state 3
static func _end_rest(d: Dictionary) -> void:
	d["ha"] = (int(d["ha"]) + REST_STEP) & 0xFFFF
	if int(d["ha"]) >= THE_END:
		d["ha"] = THE_END
		if int(d["lock"]) == 0xFF:
			d["state"] = 3
			d["b1"] = 1


# @port helper -- state 3's clock; under 0, 0 and state 0
static func _back(d: Dictionary) -> void:
	d["ha"] = (int(d["ha"]) - REST_STEP) & 0xFFFF
	if int(d["ha"]) & 0x8000:
		d["state"] = 0
		d["ha"] = 0


# Opcode 0x51's arm; tools/traps.py swing.
# @orig game:0x80049188 object_interpreter+0x2178  status:verified -- opcode 0x51's arm; tools/traps.py, 3600 of 3600 frames of the game's own arms over all 94 traps, the calls in order and all of RAM but the stack, the self-test this to it; the sounds not played
static func swing(d: Dictionary, row: Dictionary, w: Dictionary) -> void:
	var st := int(d["state"])
	var step := int(d["b3a"]) << (4 if int(d["type"]) == BIG_STEP_TYPE else 2)
	var verts := [int(row["v0"]), int(row["v1"])]
	var sound := int(row["sound"])
	var tone := SOUND if sound == 0xFF else sound + 0x1F0
	if st == 0:
		if int(d["lock"]) == 0:
			_rest(d)
			return
		var a := int(d["b3b"])
		if a == NEVER:
			return
		if a != FREE and not w["rect"].call(int(d["x"]) >> 11, int(d["z"]) >> 11, a,
				int(d["b3c"]), int(d["y"])):
			return
		d["state"] = 1
		d["b1"] = 0
		d["ha"] = 0
		d["b40"] = 0
		w["sound"].call(tone)
	elif st == 1:
		var free := int(d["b3b"]) == FREE
		if not free and int(d["ha"]) == 0:
			w["present"].call(d, 1, int(row["tile"]))
			w["sound"].call(SOUND)
		if int(d["lock"]) == 0 and int(d["ha"]) >= 0x1000 - step:
			_rest(d)
			return
		d["ha"] = (int(d["ha"]) + step) & 0xFFFF
		if int(d["ha"]) >= THE_END:
			if not free:
				d["ha"] = 0
				d["state"] = 0
				w["present"].call(d, 0, int(row["tile"]))
				return
			w["sound"].call(tone)
			d["ha"] = int(d["ha"]) & 0xFFF
		if int(d["ha"]) >= 0x800 and int(d["ha"]) < step + 0x800 and free and sound != 0xFF:
			w["sound"].call(sound + 0x1F0)
		_strike(d, row, w, verts)
	elif st == 2:
		_end_rest(d)
		_strike(d, row, w, verts)
	elif st == 3:
		_back(d)
		_strike(d, row, w, verts)


# Opcode 0x52's arm; tools/traps.py pop.
# @orig game:0x80049888 object_interpreter+0x2878  status:verified -- opcode 0x52's arm; tools/traps.py, among the 3600 frames, the self-test this to it; the sounds not played
static func pop(d: Dictionary, row: Dictionary, w: Dictionary) -> void:
	var st := int(d["state"])
	var step := int(d["b3a"]) << 2
	var sound := int(row["sound"])
	if st == 0:
		if int(d["lock"]) == 0:
			_rest(d)
			return
		var a := int(d["b3b"])
		if a == NEVER:
			return
		if a != FREE and not w["rect"].call(a, int(d["b3c"]), int(d["b3d"]), int(d["b3e"]),
				int(d["y"])):
			return
		d["state"] = 1
		d["b1"] = 0
		d["ha"] = 0
		d["b40"] = 0
		w["sound"].call(sound)
	elif st == 1:
		var comes := int(d["b3d"]) != FREE
		if comes:
			if int(d["ha"]) == 0:
				w["present"].call(d, 1, int(row["tile"]))
				w["sound"].call(sound)
			elif int(d["ha"]) >= 0x5DC and int(d["ha"]) < step + 0x5DC:
				w["sound"].call(SOUND)
		if int(d["lock"]) == 0 and int(d["ha"]) >= 0x1000 - step:
			_rest(d)
			return
		d["ha"] = (int(d["ha"]) + step) & 0xFFFF
		if int(d["ha"]) >= THE_END:
			if comes:
				d["ha"] = 0
				d["state"] = 0
				w["present"].call(d, 0, int(row["tile"]))
				return
			w["sound"].call(sound)
			d["ha"] = int(d["ha"]) & 0xFFF
		_strike(d, row, w, [int(row["v16"])])
	elif st == 2:
		_end_rest(d)
	elif st == 3:
		_back(d)


# @port helper -- 0x55's .L207: out of the world where it stands
static func _gone(d: Dictionary) -> void:
	d["state"] = 2
	d["scale"] = 0
	d["ha"] = 0


# What 0x55 adds to its place this frame: the speed, but for the cell it
# left, gathering it from the centre with +0x43 still 1, and the cell it is
# making for, losing it to the centre, where +0x42's bit 0 turns over.
# @port helper -- .L211's stretch of opcode 0x55's arm, split out of roll
static func _roll_speed(d: Dictionary, row: Dictionary) -> int:
	var fast := int(row["tile"]) << 4
	var back := int(d["b42"]) & WAY_BACK != 0
	var way := -1 if back else 1
	var a := Vector2i(int(d["b3b"]), int(d["b3c"]))
	var b := Vector2i(int(d["b3d"]), int(d["b3e"]))
	var left := b if back else a
	var making := a if back else b
	var x := int(d["x"]) - 0x400
	var z := int(d["z"]) - 0x400
	var cell := Vector2i(int(d["x"]) >> 11, int(d["z"]) >> 11)
	if int(d["b43"]) != 0:
		if cell == left:
			var past := way * ((x - (left.x << 11)) + (z - (left.y << 11)))
			return way * (((fast * past) >> 10) + 8)
		d["b43"] = 0
		return way * fast
	if cell != making:
		return way * fast
	var dx := way * ((making.x << 11) - x)
	var dz := way * ((making.y << 11) - z)
	if dx <= 0 and dz <= 0:
		d["b42"] = int(d["b42"]) + (-1 if back else 1)
		d["b43"] = 1
	return way * (((fast * (dx + dz)) >> 10) + 4)


# Opcode 0x55's arm; tools/traps.py roll. +0x40 is cleared here and never set:
# it strikes every frame it touches.
# @orig game:0x80049b40 object_interpreter+0x2b30  status:verified -- opcode 0x55's arm; tools/traps.py, the game's own over both of level 18's, the calls in order and all of RAM but the stack, the self-test this to it; the sounds not played
static func roll(d: Dictionary, row: Dictionary, w: Dictionary) -> void:
	var st := int(d["state"])
	var step := int(d["b3a"]) << 3
	var tone := int(row["sound"]) + 0x1F0
	if st == 0:
		if int(d["lock"]) == 0:
			_gone(d)
			return
		d["state"] = 1
		d["scale"] = 0x1000
		d["ha"] = 0
		d["b40"] = 0
		w["sound"].call(tone)
	elif st == 1:
		if int(d["lock"]) == 0 and int(d["ha"]) >= 0x1000 - step:
			_gone(d)
			return
		d["ha"] = (int(d["ha"]) + step) & 0xFFFF
		if int(d["ha"]) >= THE_END:
			w["sound"].call(tone)
			d["ha"] = int(d["ha"]) & 0xFFF
		var p: Array = w["vertex"].call(d, int(row["v16"]))
		var mask: int = w["query"].call([p[0], int(p[1]) + ROLL_LOWER, p[2]], int(row["radius"]),
			int(row["height"]), QUERY)
		if mask == 0:
			d["b40"] = 0
		elif int(d["b40"]) == 0:
			w["attack"].call(mask, int(d["b39"]), row["att"], p)
		var v := _roll_speed(d, row)
		var axis := "x" if int(d["b42"]) & WAY_ACROSS else "z"
		d[axis] = int(d[axis]) + v
	elif st == 2:
		d["ha"] = (int(d["ha"]) + REST_STEP) & 0xFFFF
		if int(d["ha"]) >= THE_END:
			d["ha"] = THE_END
			if int(d["lock"]) == 0xFF:
				d["state"] = 3
				d["scale"] = 0
	elif st == 3:
		_back(d)


# Opcode 0x5a's arm; tools/traps.py gate.
# @orig game:0x800496b8 object_interpreter+0x26a8  status:verified -- opcode 0x5a's arm; tools/traps.py, the game's own over both of level 18's gates, the calls in order and all of RAM but the stack, the self-test this to it; the sounds not played; a yaw other than a quarter turn reads the stack in the game and is 0x800's here, and no gate has one
static func gate(d: Dictionary, row: Dictionary, w: Dictionary) -> void:
	var st := int(d["state"])
	if st == 0:
		if int(d["lock"]) == 0:
			d["state"] = 1
			d["ha"] = 0
			return
		var wide := int(d["b3d"])
		var deep := int(d["b3e"])
		if int(d["yaw"]) == 0x400 or int(d["yaw"]) == 0xC00:
			wide = int(d["b3e"])
			deep = int(d["b3d"])
		if not w["rect"].call(int(d["b39"]), int(d["b3a"]), wide, deep, int(d["y"])):
			return
		d["lock"] = 0
		d["state"] = 1
		d["ha"] = 0
		w["sound"].call(int(row["tone"]))
	elif st == 1:
		if int(w["query"].call([int(d["x"]), int(d["y"]), int(d["z"])], GATE_RADIUS, GATE_HEIGHT,
				GATE_FLAGS)) != 0:
			return
		d["state"] = 2
		w["stamp"].call(int(d["b0"]), int(d["b3b"]), int(d["b3c"]), int(d["b39"]), int(d["b3a"]),
			int(d["b3d"]), int(d["b3e"]), KFTicks.s16(int(d["yaw"])) & 0xFFFFFFFF, GATE_MASK)
		w["sound"].call(int(row["tone"]))
	elif st == 2:
		if int(d["ha"]) < 0x800:
			d["ha"] = int(d["ha"]) + 0x100
		elif int(d["ha"]) < THE_END:
			d["ha"] = int(d["ha"]) + REST_STEP
		else:
			d["ha"] = THE_END
			d["state"] = GATE_DONE


# Opcode 0x32's arm; tools/traps.py follow: the clock a creature's +0x18 and
# the u16 at +0x3c, or with the u16 at +0x3a 0xffff its own on by the u16 at
# +0x38.
# @orig game:0x8004b168 object_interpreter+0x4158  status:verified -- opcode 0x32's arm; tools/traps.py, the game's own over both, the calls in order and all of RAM but the stack, the self-test this to it
static func follow(d: Dictionary, w: Dictionary) -> void:
	if int(d["state"]) != 0:
		return
	var who := int(d["b3a"]) | (int(d["b3b"]) << 8)
	if who != 0xFFFF:
		d["ha"] = (int(w["actor_clock"].call(who)) + (int(d["b3c"]) | (int(d["b3d"]) << 8))) & THE_END
	else:
		d["ha"] = (int(d["ha"]) + (int(d["lock"]) | (int(d["b39"]) << 8))) & THE_END


# @port helper -- the arm by the object's opcode
static func step(d: Dictionary, row: Dictionary, w: Dictionary) -> void:
	match int(d["op"]):
		SWING_OP:
			swing(d, row, w)
		POP_OP:
			pop(d, row, w)
		ROLL_OP:
			roll(d, row, w)
		GATE_OP:
			gate(d, row, w)
		FOLLOW_OP:
			follow(d, w)


# The model's vertices at an animation and a clock. A frame of level 18 asks
# for sixty-odd, and traps of one type and step share their clocks.
# @orig game:0x8004352c model_vertex  status:partial -- through KFAnim.vertices, an animation under 0x80: tools/traps.py, the game's own over every trap's model at every clock the arms reach, its answers in collide_query's arguments; not an animation of 0x80 and up, another object's own vertices, which no trap asks
static func posed(model: int, anim: int, clock: int) -> Array:
	var key := (model << 20) | (anim << 16) | clock
	if not posed_cache.has(key):
		posed_cache[key] = KFAnim.vertices(model, anim, clock)
	return posed_cache[key]


# A vertex of the object's model where it is in the world: at +1 and the
# clock, each axis by the scale, turned by the angles with the yaw a half turn
# on, from the object's place.
# @orig game:0x80046760 object_vertex_point  status:verified -- tools/traps.py point, the game's own run for every strike of the 3600 frames, the self-test this to it
static func point(c: KFCollision, d: Dictionary, model: int, vertex: int) -> Array:
	var vs := posed(model, int(d["b1"]), int(d["ha"]))
	var v := [0, 0, 0]
	if vertex < vs.size():
		var w: Vector3i = vs[vertex]
		var sc := KFTicks.s16(int(d["scale"]))
		v = [KFTicks.s16((w.x * sc) >> 12), KFTicks.s16((w.y * sc) >> 12),
			KFTicks.s16((w.z * sc) >> 12)]
	var r := KFWeapon.vec_rotate(c, KFTicks.s16(int(d["ax"])),
		KFTicks.s16(int(d["yaw"]) + 0x800), KFTicks.s16(int(d["az"])), v)
	return [KFTicks.s32(int(r[0]) + int(d["x"])), KFTicks.s32(int(r[1]) + int(d["y"])),
		KFTicks.s32(int(r[2]) + int(d["z"]))]

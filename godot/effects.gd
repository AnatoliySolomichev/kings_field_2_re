extends Node
# The effects: what a creature's volley throws, and what that leaves behind.
#
# An effect is one of 128 slots of 0x4c bytes at effect_slots (0x801b80ec),
# and this keeps them as the game does, a byte at a time, so that every arm
# below reads and writes the offsets the game's does. tools/effects.py is the
# same machine in Python, held to the game's own effect_spawn and
# effect_driver run over the snapshots -- every slot, every frame, byte for
# byte -- and the self-test holds this to it (fxcheck.json).
#
#   +0    bits: 1 strikes the player, 2 the creatures; & 7 effect_collide's
#         flags      +1  the kind: the arm, and its spell_table record
#   +2 +3 the model is model_table[+3 + 0x28]   +4  0x80   +6 the percentage
#   +8    how it is drawn: & 3 0 not at all, & 0xc the matrix
#   +0xa  the layer it last met     +0xb a grace count    +0xd the half-step
#   +0xe  render_walk hands it to the draw (0x1f800084)    +0x10 life
#   +0x18 x y z (s32)   +0x28 angles   +0x30 scale x y z   +0x38 velocity
#   +0x44, +0x46 the kind's own
#
# effect_driver (0x8005bc50) runs each live slot once a game frame, after the
# creatures: its life counts down, at -1 it is freed, else effect_tick runs
# its kind's arm. The arms here:
#
#   0x23, 0x24  a creature's bolt (level 4's model-53 creatures): strikes the
#               player within its scale / 8 each frame, flies until it meets
#               the tiles, an object or the player, and leaves a puff (0x6f)
#               where it is, with two fifths of its velocity. Not drawn.
#   0x1f        a bolt that bobs up and down as it flies (model 0x4a)
#   0x22        a dart (model 0x49; level 4's model-67 creatures, level 12's)
#               -- both strike within their scale / 16 and meet the tiles alone
#   0x26        a spore (level 0's and 4's model-57 creatures)
#   0x6f        a puff: drifts, rises by +0x46, its scale grows by +0x44
#
# A slot spawned during the walk lands in the first free one from the top, so
# one below the slot that made it waits for the next frame and one above runs
# in this one -- the machine keeps that order because it keeps the slots.
#
# @exe game

const TICK_HZ := 15.0
const COUNT := 128
const STRIDE := 0x4C
const FAST := 0xC5C10              # a speed squared past it gets the half-step test
const TRAIL := 0x6F
const FIRE_BALL := 0x00
const SPLASH := 0x70
const TRAIL_ARGS := [0xE10, -0x80, 5, 0x16, 0, 1, 3]   # 0x80058f50's, after the velocity
const QUERY := {1: 0xA1, 2: 0x31, 3: 0xB1, 4: 0x01}    # effect_collide: +0 & 7 -> flags
const GROW := 0x96
const RISE := 0x28
const SINK := 0x55
const TURN := 0x21
const OWN := 0x320
const BODY := 0x6A4
const EDGE := 0x400
const MODEL_BASE := 0x28           # model_table[+3 + 0x28]: the resident bank
const LOOT := preload("res://loot.gd")   # game_basis, the game's turn in Godot's axes

var m := PackedByteArray()         # effect_slots, as the game keeps them
var current := -1                  # 0x801ba6f0: the slot being run, an offset into m
var records := {}                  # kind -> its spell_table record (24 bytes)
var layer_offset := 0              # collision_layer_offset after the last tile query
var world = null                   # what the effects ask of the game; this node, or a stand-in
var pulse := []                     # this frame's lighting from an effect: [near, far, k, rgb]
var collide_actor := -1             # 0x801e648c: the creature the last query met
var surface18 := 100000             # 0x801e647c: the water the last query found
var acc := 0.0
var player: Node3D
var coll: KFCollision
var templates := {}                # model_table index -> its node in effectsNN.gltf
var nodes := {}                    # slot -> the node drawing it, and its model


# @port data -- the kinds' spell_table records (fxrecords.json, tools/effects.py), the player, its collision and the models in effectsNN.gltf
func _ready() -> void:
	clear()
	world = self
	player = get_node_or_null("../Player")
	if player and player.get("coll") is KFCollision:
		coll = player.get("coll")
	load_records()
	var models := get_node_or_null("../EffectModels")
	if models:
		for n in models.get_children():
			if n is Node3D and str(n.name).begins_with("m"):
				templates[str(n.name).substr(1).to_int()] = n
				(n as Node3D).visible = false


# @port data -- fxrecords.json: spell_table's records, by kind
func load_records(path := "res://fxrecords.json") -> void:
	if not FileAccess.file_exists(path):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return
	for k in d.get("records", {}):
		records[int(k)] = PackedByteArray((d["records"][k] as Array).map(func(v): return int(v)))


# @port helper -- every slot free, as init leaves them
func clear() -> void:
	m.resize(COUNT * STRIDE)
	m.fill(0)
	for k in COUNT:
		m[k * STRIDE] = 0xFF


# @port engine -- runs effect_driver at the game's 15 frames a second
func _process(dt: float) -> void:
	if KFGame.modal:                  # object_give's frames: they stand still
		return
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		driver()
	_draw_all()


# --- bytes ----------------------------------------------------------------

# @port helper -- a byte of the slots
func u8(o: int) -> int:
	return m[o]


# @port helper -- an unsigned halfword of the slots
func u16(o: int) -> int:
	return m.decode_u16(o)


# @port helper -- a signed halfword of the slots
func s16(o: int) -> int:
	return m.decode_s16(o)


# @port helper -- a signed word of the slots
func s32(o: int) -> int:
	return m.decode_s32(o)


# @port helper -- stores, the way sb, sh and sw truncate
func w8(o: int, v: int) -> void:
	m[o] = v & 0xFF


# @port helper -- a halfword store
func w16(o: int, v: int) -> void:
	m.encode_u16(o, v & 0xFFFF)


# @port helper -- a word store
func w32(o: int, v: int) -> void:
	m.encode_u32(o, v & 0xFFFFFFFF)


# @port helper -- bytes copied in, as the lwl/lwr and swl/swr pairs copy them
func put(o: int, data: PackedByteArray) -> void:
	for i in data.size():
		m[o + i] = data[i]


# @port helper -- two's complement of a 32-bit sum
static func s32v(v: int) -> int:
	v &= 0xFFFFFFFF
	return v - 0x100000000 if v & 0x80000000 else v


# x / 5 as the compiler builds it: 0x66666667, a shift, the sign -- toward 0.
# @port helper -- the division by five 0x80058fa8 does with a multiply
static func div5(x: int) -> int:
	x = s32v(x)
	var q := (x * 0x66666667) >> 32
	return (q >> 1) + (1 if x < 0 else 0)


# --- making one -----------------------------------------------------------

# effect_alloc (0x80053b64): the first slot from the top whose +0 is 0xff.
# @orig game:0x80053b64 effect_alloc  status:verified -- through effect_spawn, 189 of 189 runs of the game's own (tools/effects.py)
func alloc() -> int:
	for k in COUNT:
		if m[k * STRIDE] == 0xFF:
			return k * STRIDE
	return -1


# effect_spawn(a0, a1, kind, point, ...): `point` the 16 bytes a3 points at
# (or empty), `args` the stack arguments from the fifth on -- a pointer as the
# bytes it points at. The slot's offset, or -1 when none is free.
# @orig game:0x80053c84 effect_spawn  status:partial -- the common setting up and the arms of kinds 0x1f, 0x22, 0x23, 0x24, 0x26 and 0x6f; 189 of 189 runs of the game's own as tools/effects.py, which the self-test holds this to; the other 124 arms are not here
func spawn(a0: int, a1: int, kind: int, point: PackedByteArray, args: Array) -> int:
	var s := alloc()
	if s < 0:
		return -1
	w8(s, a1)
	w8(s + 1, kind)
	if point.size() >= 16:
		put(s + 0x18, point.slice(0, 16))
	w8(s + 0xA, 3)
	var vel = args[0] if not args.is_empty() else null
	if vel is PackedByteArray:
		put(s + 0x38, (vel as PackedByteArray).slice(0, 8))
	else:
		for o in [0x3C, 0x3A, 0x38]:
			w16(s + o, 0)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, 0x1000)
	var f0 := u8(s)
	w8(s + 7, 0)
	w8(s + 6, a0)
	for o in [0x2C, 0x2A, 0x28, 0x14]:
		w16(s + o, 0)
	w8(s + 5, 0)
	w8(s + 8, 1)
	var pstate := int(player.get("pstate")) if player and player.get("pstate") != null else 0
	w8(s + 0xB, 8 if (f0 & 0x40) != 0 and pstate == 1 else 1)
	var vx := s16(s + 0x38)
	var vy := s16(s + 0x3A)
	var vz := s16(s + 0x3C)
	w16(s + 0x12, 0)
	w8(s + 9, 0)
	w8(s + 0xC, 0xFF)
	w16(s + 0x10, -1)
	w8(s + 0xD, 1 if FAST < s32v(vx * vx + vy * vy + vz * vz) else 0)
	w16(s + 0xE, 0)
	if kind >= 0x82:
		w8(s, 0xFF)
		return s
	match kind:
		0x1F:                               # 0x80054d50, a bolt that bobs
			_aimed(s, 0x22)
			w8(s + 9, 0)
			w16(s + 0x3A, 0)
			w16(s + 0x44, 1)
			w16(s + 0x46, 0)
		0x22:                               # 0x80054b5c
			_aimed(s, 0x21)
			w8(s + 9, 5)
		0x23:                               # 0x80054be4
			w8(s + 8, 0)
			w16(s + 0x10, 0x14)
			put(s + 0x28, (args[1] as PackedByteArray).slice(0, 8))
			w16(s + 0xE, 0xC0)
			w8(s + 0xD, 1)
		0x24:                               # 0x80054c2c
			w8(s + 8, 0)
			w16(s + 0x10, 0x3C)
			put(s + 0x28, (args[1] as PackedByteArray).slice(0, 8))
			w16(s + 0xE, 0xC0)
		0x26:                               # 0x80054338
			setup(s, 0x24, 0x400, 5)
			w16(s + 0xE, 0x40)
			w16(s + 0x10, 0x32)
			w8(s + 0xD, 1)
			w16(s + 0x44, 0x14)
			w32(s + 0x1C, s32(s + 0x1C) - 0xC8)
		SPLASH:                             # 0x800557dc
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 2, 0x2A)
			w8(s + 3, 0x2A)
			w16(s + 0x32, 0)
			w16(s + 0x34, int(args[1]))
			w16(s + 0x30, int(args[1]))
			w16(s + 0x44, int(args[2]))      # and its sound, every 30 blanks at most: not here
		FIRE_BALL:                          # 0x80053e98
			particle(s, 9, 0x1000, 5)
			w16(s + 0xE, 0x40)
			w16(s + 0x10, 0x32)             # sub_800532d4's sound between, not here
			w8(s + 0xD, 1)
		0x1A:                               # 0x8005585c, fire resist's mark
			var i := int(args[1]) if args.size() > 1 and args[1] != null else 0
			orbit(s, 0x18, i << 11, 14 * i - 7)
			w16(s + 0xE, 0xC0)
		0x1B:                               # 0x8005588c, refusal's
			orbit(s, 0x2F, 0, 0)
			w16(s + 0xE, 0x80)
		0x1C:                               # 0x800558a8, missile shield's
			var i := int(args[1]) if args.size() > 1 and args[1] != null else 0
			orbit(s, 0x18, i << 11, 14 * i - 7)
			w16(s + 0xE, 0x80)
		0x17:                               # 0x800558d4, earth heal
			w8(s + 8, 0)
			w16(s + 0x10, 8)
		0x19:                               # 0x800558f4, antidote
			w8(s + 8, 0)
			w16(s + 0x10, 0x10)
			w16(s + 0xE, 0x80)
		0x1E:                               # 0x80055918, blessings
			w8(s + 8, 0)
			w16(s + 0x10, 0x10)
			w16(s + 0xE, 0x40)
		TRAIL:                              # 0x80055738
			particle(s, int(args[4]), int(args[1]), int(args[6]) | 4)
			w16(s + 0x44, int(args[2]))
			w16(s + 0x10, int(args[3]))
			w16(s + 0x46, int(args[5]))
			w16(s + 0xE, (int(args[7]) & 0xFFFF) << 6)
		_:
			w8(s, 0xFF)                     # an arm not here: no effect at all
			KFInfo.note("effect: kind 0x%x is not in the port" % kind)
	return s


# What 0x1f's and 0x22's arms share (0x80054cf4, 0x80054d68): +8 1, +4 0x80,
# +2 and +3 the model, a life of 0x46, the scale 0x1800, and the angles off the
# velocity -- the pitch ratan2(vy, vec_length_2d(vx, vz)), the yaw
# ratan2(vz, vx) less a quarter.
# @orig game:0x80054cf4 effect_spawn+0x1070  status:verified -- the arms of 0x1f and 0x22 through tools/effects.py, 189 of 189 runs of the game's own
func _aimed(s: int, model: int) -> void:
	var vx := s16(s + 0x38)
	var vz := s16(s + 0x3C)
	w8(s + 8, 1)
	w8(s + 4, 0x80)
	w8(s + 2, model)
	w8(s + 3, model)
	w16(s + 0x10, 0x46)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, 0x1800)
	var ln := coll.isqrt(s32v((vx >> 3) * (vx >> 3) + (vz >> 3) * (vz >> 3)) & 0xFFFFFFFF) << 3
	w16(s + 0x28, coll.ratan2(s16(s + 0x3A), ln))
	w16(s + 0x2C, 0)
	w16(s + 0x2A, coll.ratan2(s16(s + 0x3C), s16(s + 0x38)) - 0x400)


# What the three protecting spells' marks share: drawn by mode 0xe, in front
# of the eye, at (0xa0, y + 0x78, 0), scale 0x100, turned by `angle`.
# @orig game:0x80053c20 sub_80053c20  status:verified -- through the arms of 0x1a, 0x1b and 0x1c, tools/effects.py magic_check, 126 of 126 runs of the game's own
func orbit(s: int, model: int, angle: int, y: int) -> void:
	w8(s + 8, 0xE)
	w8(s + 4, 0x80)
	w8(s + 9, 5)
	w8(s + 0xC, 0x34)
	w16(s + 0x12, 0x1000)
	for o in [0x32, 0x34, 0x30]:
		w16(s + o, 0x100)
	w8(s + 2, model)
	w8(s + 3, model)
	w32(s + 0x18, 0xA0)
	w32(s + 0x1C, y + 0x78)
	w32(s + 0x20, 0)
	w16(s + 0x28, angle)
	w16(s + 0x2C, 0)
	w16(s + 0x2A, 0)


# @orig game:0x80053ba8 effect_setup  status:verified -- through the spore's arm, the same 189 runs
func setup(s: int, a: int, scale: int, b: int) -> void:
	w8(s + 8, 1)
	w8(s + 4, 0x80)
	w8(s + 0xC, 0x34)
	w8(s + 2, a)
	w8(s + 3, a)
	w8(s + 9, b)
	w16(s + 0x12, 0x1000)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, scale)


# @orig game:0x80053be4 sub_80053be4  status:verified -- through the puff's arm, the same 189 runs
func particle(s: int, a: int, scale: int, b: int) -> void:
	w8(s + 8, 5)
	w8(s + 4, 0x80)
	w8(s + 0xC, 0x33)
	w8(s + 2, a)
	w8(s + 3, a)
	w8(s + 9, b)
	w16(s + 0x12, 0x1000)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, scale)


# --- running them ---------------------------------------------------------

# effect_driver: each live slot in turn, its life counted down, freed at -1,
# else its kind's arm.
# @orig game:0x8005bc50 effect_driver  status:verified -- 4702 of 4702 frames, all 128 slots, of the game's own (tools/effects.py), which the self-test holds this to
func driver() -> void:
	pulse = []
	for k in COUNT:
		var s := k * STRIDE
		if m[s] == 0xFF:
			continue
		current = s
		var life := (u16(s + 0x10) - 1) & 0xFFFF
		w16(s + 0x10, life)
		if life == 0xFFFF:
			m[s] = 0xFF
		else:
			tick(s)
	if world == self:
		var sc := get_node_or_null("../Scroll")
		if sc and sc.has_method("set_pulse"):
			sc.call("set_pulse", pulse)


# effect_tick's switch on the kind (0x80056908), with the arms the port has.
# @orig game:0x800568bc effect_tick  status:partial -- the switch, and the arms of kinds 0x1f, 0x22, 0x23, 0x24, 0x26 and 0x6f; the other 124 do nothing here
func tick(s: int) -> void:
	match u8(s + 1):
		0x1F:
			_tick_bob(s)
		0x22:
			_tick_dart(s)
		0x23, 0x24:
			_tick_bolt(s)
		0x26:
			_tick_spore(s)
		TRAIL:
			_tick_puff(s)
		FIRE_BALL:
			_tick_fire(s)
		SPLASH:
			_tick_splash(s)
		0x1A:
			_mark(s, "b56a", 0x40)
		0x1B:
			_mark(s, "b56c", -0x100)
		0x1C:
			_mark(s, "b56e", -0x40)
		0x17:
			_tick_earth_heal(s)
		0x19:
			_tick_antidote(s)
		0x1E:
			_tick_blessings(s)


# The fire ball (0x80056910): in flight (+7 0) effect_move at radius 0xb4 and
# the height's top bit, turning 0x12c a frame; a hit splashes on water within
# 0x1f4 under its surface, steps it back, half its velocity when
# game_isqrt((x - the player's x) ^ 2), the compiler's xor, is under 0x400,
# all of it otherwise, and hands what it hit to actor_attack_player from 8
# velocities back with 0x1388 and the caster's strength; then it grows by
# 0x800 two frames, +4 0x80 + the phase, and is gone at phase 3.
# @orig game:0x80056910 effect_tick+0x54  status:verified -- tools/effects.py fire_world_check, 210 of 210 runs of the game's own with its own collide_query, 34 hits on a creature and the splash among them; fire_check with the world stood in for; the self-test this to it
func _tick_fire(s: int) -> void:
	var ph := u8(s + 7)
	if ph == 0:
		var hit := move(0xB4, 0x80000000, -0x12C)
		if hit == 0:
			return
		_splash(s + 0x18, 3, 0x190, 0x2000, 0x2000, 0x400)
		var dx := (s32(s + 0x18) - int(world.field("px"))) & 0xFFFFFFFF
		if coll.isqrt(dx ^ 2) < 0x400:
			for i in 3:
				var h := s16(s + 0x38 + 2 * i)
				w32(s + 0x18 + 4 * i, s32(s + 0x18 + 4 * i) - (-((-h) >> 1) if h < 0 else h >> 1))
		else:
			undo(s)
		var back := []
		for i in 3:
			back.append(s32(s + 0x18 + 4 * i) - (s16(s + 0x38 + 2 * i) << 3))
		world.attack_hit(hit, u8(s), u8(s + 1), 0x1388, magic_strength(s), u8(s + 6), back)
		w8(s + 7, 1)
	elif ph >= 3:
		w8(s, 0xFF)
		return
	w8(s + 4, (ph - 0x80) & 0xFF)
	var sc := (u16(s + 0x30) + 0x800) & 0xFFFF
	for o in [0x30, 0x32, 0x34]:
		w16(s + o, sc)
	w8(s + 7, u8(s + 7) + 1)


# sub_80056580: splashes on the water, when the point is within 0x1f4 under
# the surface the last query found (surface_plane_18): n of kind 0x70 on the
# surface, the first at the point and the rest within `spread` of it, each
# sized by random_spread(wobble) + 0x1000 -- `size` across, `bob` its rise.
# Their velocity is the stack's leftover in the game, nothing here.
# @orig game:0x80056580 sub_80056580  status:verified -- through the fire ball, tools/effects.py fire_world_check and fire_check
func _splash(point: int, n: int, spread: int, size: int, bob: int, wobble: int) -> int:
	var y := s32(point + 4)
	var surf := int(world.field("s18"))
	if y < surf or surf + 0x1F4 < y:
		return 0
	var dx := 0
	var dz := 0
	for i in n:
		var pt := PackedByteArray()
		pt.resize(16)
		pt.encode_s32(0, s32(point) + dx)
		pt.encode_s32(4, surf)
		pt.encode_s32(8, s32(point + 8) + dz)
		var r := ((int(world.rand()) + int(world.rand()) - 0x8000) * wobble) >> 15
		var v := r + 0x1000
		var vel := PackedByteArray()
		vel.resize(8)
		spawn(0xA, 0, SPLASH, pt, [vel, s32v(size * v) >> 12, s32v(bob * v) >> 12])
		dx = ((int(world.rand()) * spread) >> 14) - spread
		dz = ((int(world.rand()) * spread) >> 14) - spread
	return 1


# A splash (0x8005b598): eight frames, its height scale sin(phase << 8) times
# +0x44, then gone.
# @orig game:0x8005b598 effect_tick+0x4cdc  status:verified -- through the fire ball's splashes, the same runs
func _tick_splash(s: int) -> void:
	var ph := (u8(s + 7) + 1) & 0xFF
	w8(s + 7, ph)
	w16(s + 0x32, s32v(coll.game_sin(ph << 8) * s16(s + 0x44)) >> 12)
	if ph >= 8:
		w8(s, 0xFF)


# sub_80053624: a player's effect (+0 0x40) strikes with the mean of the
# working skills whose bit its spell's group (+5) has; any other with 5.
# @orig game:0x80053624 sub_80053624  status:verified -- through the fire ball's hits, the same 168 runs
func magic_strength(s: int) -> int:
	if (u8(s) & 0x40) == 0:
		return 5
	var rec: PackedByteArray = records.get(u8(s + 1), PackedByteArray())
	var group := int(rec[5]) if rec.size() > 5 else 0
	var n := 0
	var total := 0
	for k in range(4, -1, -1):
		if group & (1 << k):
			n += 1
			total += int(world.field("w%d" % k))
	return ((total & 0xFFFF) / n) & 0xFFFF if n > 0 else total & 0xFFFF


# What an effect's hit hands actor_attack_player (0x800533e8): code 0x80
# the player -- player_take_hit with the record's attacks and effect, the
# strength its scale -- 0x10 the creature collide_query met (actors.gd
# take_spell), whose practice and experience go to the player. A code with
# other bits does nothing.
# @orig game:0x800533e8 actor_attack_player  status:verified -- tools/effects.py fire_hit_check, 84 of 84 runs of the game's own end to end; the player's half through player_take_hit
func attack_hit(code: int, flags: int, kind: int, strength: int, stat: int, pct: int, back: Array) -> void:
	var rec: PackedByteArray = records.get(kind, PackedByteArray())
	if rec.size() < 0x16:
		return
	var att := []
	for o in [6, 8, 0xA, 0xC, 0xE, 0x10, 0x12, 0x14]:
		att.append(rec.decode_u16(o))
	var lo := code & 0xFFF0FFFF
	var point := Vector3i(int(back[0]), int(back[1]), int(back[2]))
	if lo == 0x80:
		if player and player.has_method("take_effect"):
			player.call("take_effect", att, int(rec[4]), strength & 0xFFFF, pct, point)
		return
	if lo != 0x10 or collide_actor < 0:
		return
	var an := get_node_or_null("../Actors")
	if an == null or not an.has_method("take_spell"):
		return
	var out: Dictionary = an.call("take_spell", collide_actor, stat, att, strength, flags,
		point, code & 0xF0000)
	if not out.is_empty() and player and player.has_method("spell_struck"):
		player.call("spell_struck", out, kind)


# The protecting spells' marks (0x8005b5e4, 0x8005b610, 0x8005b63c): gone
# when their timer is, else turned by 0x40, -0x100 or -0x40 a frame.
# @orig game:0x8005b5e4 effect_tick+0x4d28  status:verified -- kinds 0x1a, 0x1b, 0x1c; tools/effects.py magic_check, 126 of 126 runs of the game's own, which the self-test holds this to
func _mark(s: int, timer: String, turn: int) -> void:
	if KFWeapon.s16(int(world.field(timer))) == 0:
		w8(s, 0xFF)
	w16(s + 0x2A, u16(s + 0x2A) + turn)


# earth heal (0x8005b668): 0x50 HP, to the most, four frames before its end;
# every frame the lighting pulsed toward (0xe6, 0xc8, 0xa0), near 0, far
# 0x59d8 by sin(life << 8).
# @orig game:0x8005b668 effect_tick+0x4dac  status:verified -- the same runs
func _tick_earth_heal(s: int) -> void:
	if s16(s + 0x10) == 4:
		_heal(0x50)
	var k := coll.game_sin((s16(s + 0x10) << 8) & 0xFFFFFFFF)
	world.lighting([0xE6, 0xC8, 0xA0], 0, 0x59D8, s16v(k))


# antidote (0x8005b6d4): the poison gone twelve frames before its end; a
# sparkle every frame; the lighting toward (0xa0, 0xb4, 0xdc), far 0x4650.
# @orig game:0x8005b6d4 effect_tick+0x4e18  status:verified -- the same runs
func _tick_antidote(s: int) -> void:
	if s16(s + 0x10) == 0xC:
		world.set_field("poison", 0)
	_sparkle(1, 2)
	var k := coll.game_sin((s16(s + 0x10) << 7) & 0xFFFFFFFF)
	world.lighting([0xA0, 0xB4, 0xDC], 0, 0x4650, s16v(k))


# blessings (0x8005b7a4): 0xc8 HP and the cure of the curse, the darkness,
# the poison, the slowing and the paralysis (sub_8002aa54(7)) twelve frames
# before its end; three sparkles a frame; the lighting toward (0xf0, 0xf0,
# 0xa0), far 0x4650.
# @orig game:0x8005b7a4 effect_tick+0x4ee8  status:verified -- the same runs
func _tick_blessings(s: int) -> void:
	if s16(s + 0x10) == 0xC:
		_heal(0xC8)
		cure(world, 7)
	for i in 3:
		_sparkle(1, 1)
	var k := coll.game_sin((s16(s + 0x10) << 7) & 0xFFFFFFFF)
	world.lighting([0xF0, 0xF0, 0xA0], 0, 0x4650, s16v(k))


# @port helper -- HP up by n, to its most, as both healing arms do it
func _heal(n: int) -> void:
	var hp := (int(world.field("hp")) + n) & 0xFFFF
	if int(world.field("hp_max")) < hp:
		hp = int(world.field("hp_max"))
	world.set_field("hp", hp)


# A sparkle in front of the eye: a puff (0x6f) at (rand >> 5 - 0x200,
# rand >> 8 + 0xc8, 0x400), drawn by mode 0xe, its +0xa 1.
# @orig game:0x8005b6ec effect_tick+0x4e30  status:verified -- the same runs
func _sparkle(b: int, e: int) -> void:
	var x := (int(world.rand()) >> 5) - 0x200
	var y := (int(world.rand()) >> 8) + 0xC8
	var pt := PackedByteArray()
	pt.resize(16)
	pt.encode_s32(0, x)
	pt.encode_s32(4, y)
	pt.encode_s32(8, 0x400)
	var vel := PackedByteArray()
	vel.resize(8)
	var t := spawn(0xA, 0, TRAIL, pt, [vel, 0x2BC, -0x1E, 0xA, 0x26, -0xA, b, e])
	if t >= 0:
		w8(t + 0xA, 1)
		w8(t + 8, 0xE)


# sub_8002aa54 on `w`'s fields: bit 1 the curse and 2 the darkness -- the
# level cut to 0x40, the timer 0, so it ramps out -- either the poison, 1 or
# 4 the slowing cut to 0x40, 4 the paralysis.
# @orig game:0x8002aa54 sub_8002aa54  status:verified -- through blessings, the same runs
static func cure(w, mask: int) -> void:
	for p in [[1, "curse_lv", "curse_t"], [2, "dark_lv", "dark_t"]]:
		if mask & int(p[0]):
			if KFWeapon.s16(int(w.field(p[1]))) >= 0x41:
				w.set_field(p[1], 0x40)
			w.set_field(p[2], 0)
	if mask & 3:
		w.set_field("poison", 0)
	if mask & 5 and KFWeapon.s16(int(w.field("slow"))) >= 0x41:
		w.set_field("slow", 0x40)
	if mask & 4:
		w.set_field("paralysis", 0)


# The player's fields the effects read and write, by tools/effects.py's
# names, when this node is its own world.
# @port helper -- a player field by name
func field(name: String) -> int:
	if player == null:
		return 0
	match name:
		"hp": return int(player.get("hp"))
		"hp_max": return int(player.get("hp_max"))
		"poison": return int(player.get("poison"))
		"curse_lv": return int(player.get("curse")[0])
		"curse_t": return int(player.get("curse")[1])
		"dark_lv": return int(player.get("dark")[0])
		"dark_t": return int(player.get("dark")[1])
		"slow": return int(player.get("caps")["slow"])
		"paralysis": return int(player.get("caps")["paralysis"])
		"b56a": return int(player.get("bonus")[0])
		"b56c": return int(player.get("shielded"))
		"b56e": return int(player.get("bonus")[1])
		"px": return int(player.get("gx"))
		"s18": return surface18
		"w0", "w1", "w2", "w3", "w4":
			return int(player.get("working")[int(name.substr(1))])
	return 0


# @port helper -- and written
func set_field(name: String, v: int) -> void:
	if player == null:
		return
	match name:
		"hp": player.set("hp", v)
		"poison": player.set("poison", v)
		"curse_lv": player.get("curse")[0] = v
		"curse_t": player.get("curse")[1] = v
		"dark_lv": player.get("dark")[0] = v
		"dark_t": player.get("dark")[1] = v
		"slow": player.get("caps")["slow"] = v
		"paralysis": player.get("caps")["paralysis"] = v


# @port helper -- the BIOS's rand, for the sparkles
func rand() -> int:
	return randi() & 0x7FFF


# sub_8003456c from an effect: kept for the world's shader, which blends the
# near and far by it after the frame's darkness and light -- the last one of
# the frame, the driver hands it on.
# @port helper -- an effect's lighting, for scroll.gd
func lighting(rgb: Array, near: int, far: int, k: int) -> void:
	pulse = [near, far, k, rgb]


# A bolt (0x80058f3c, kinds 0x23 and 0x24): its strike within a scale of
# 0x200, its flight -- taken back and the slot freed when it meets the tiles,
# an object or the player -- and the puff it leaves.
# @orig game:0x80058f3c effect_tick+0x2680  status:verified -- kinds 0x23 and 0x24; through tools/effects.py, 189 of 189 runs of the game's own
func _tick_bolt(s: int) -> void:
	w8(s, 0x81)
	strike(s + 0x18, 0, s16(s + 0x30) >> 3, 0x8000, 0x400, 0x1000)
	w8(s, 0x81)
	if move(0x64, 0xC8, 0) != 0:
		undo(s)
		w8(s, 0xFF)
	_puff(s, 1, 3)


# A bolt that bobs (0x80058a2c, kind 0x1f): its height speed +0x46 runs by 10
# a frame up or down as +0x44 says, turning at -0x45 and 0x46; it strikes
# within a scale of 0x180, meets the tiles alone -- and is freed there where it
# stands -- and leaves a puff.
# @orig game:0x80058a2c effect_tick+0x2170  status:verified -- kind 0x1f; through tools/effects.py, 189 of 189 runs of the game's own
func _tick_bob(s: int) -> void:
	w8(s, 0x81)
	w16(s + 0x46, u16(s + 0x46) + (0xA if s16(s + 0x44) != 0 else -0xA))
	w32(s + 0x1C, s32(s + 0x1C) + s16(s + 0x46))
	if s16(s + 0x46) < -0x45 and s16(s + 0x44) == 0:
		w16(s + 0x44, 1)
	if s16(s + 0x46) >= 0x46 and s16(s + 0x44) == 1:
		w16(s + 0x44, 0)
	strike(s + 0x18, 0, s16(s + 0x30) >> 4, 0x8000, 0x400, 0x1000)
	w8(s, 0x84)
	if move(0x64, 0xC8, 0) != 0:
		w8(s, 0xFF)
	_puff(s, 2, 5)


# A dart (0x80058bb4, kind 0x22): its strike within a scale of 0x180, its
# flight against the tiles alone -- taken back and freed when it meets them --
# and a puff.
# @orig game:0x80058bb4 effect_tick+0x22f8  status:verified -- kind 0x22; through tools/effects.py, 189 of 189 runs of the game's own
func _tick_dart(s: int) -> void:
	w8(s, 0x81)
	strike(s + 0x18, 0, s16(s + 0x30) >> 4, 0x8000, 0x400, 0x1000)
	w8(s, 0x84)
	if move(0x64, 0xC8, 0) != 0:
		undo(s)
		w8(s, 0xFF)
	_puff(s, 1, 4)


# The puff a bolt leaves at its point (kind 0x6f): two fifths of its velocity
# and effect_spawn(10, 0, 0x6f, point, v, 0xe10, -0x80, 5, 0x16, 0, b, e) --
# +9 is b | 4 and +0xe e << 6. The velocity's fourth halfword is the stack's
# leftover in the game; here it is 0.
# @port helper -- the trail's spawn the bolts' arms share, with their two last arguments
func _puff(s: int, b: int, e: int) -> void:
	var v := PackedByteArray()
	v.resize(8)
	for i in 3:
		v.encode_s16(2 * i, div5(2 * s16(s + 0x38 + 2 * i)))
	spawn(10, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v] + TRAIL_ARGS.slice(0, 5) + [b, e])


# A spore (0x80056de8): it swells for +0x44 frames, rises and then sinks,
# strikes with its whole x scale, and goes when it meets the tiles.
# @orig game:0x80056de8 effect_tick+0x52c  status:verified -- tools/effects.py: 118 of 118 frames of the recorded spores, and the game's own over the snapshots
func _tick_spore(s: int) -> void:
	if s16(s + 0x44) != 0:
		w16(s + 0x44, u16(s + 0x44) - 1)
		w16(s + 0x30, u16(s + 0x30) + GROW)
		w16(s + 0x34, u16(s + 0x34) + GROW)
	if s16(s + 0x32) < 0x1000:
		w16(s + 0x32, s16(s + 0x32) + GROW)
	w32(s + 0x1C, s32(s + 0x1C) + (-RISE if s16(s + 0x10) >= TURN else SINK))
	w8(s, 0x81)
	strike(s + 0x18, 0, s16(s + 0x30), 0x8000, 0x400, 0x1000)
	w8(s, 0x84)
	if move(0x64, 0xC8, 0) != 0:
		w8(s, 0xFF)


# A puff (0x8005b45c): the vertical speed by +0x46, the place by the speed,
# the three scales by +0x44.
# @orig game:0x8005b45c effect_tick+0x4ba0  status:verified -- kind 0x6f; through tools/effects.py, 189 of 189 runs of the game's own
func _tick_puff(s: int) -> void:
	var vy := (u16(s + 0x3A) + u16(s + 0x46)) & 0xFFFF
	w32(s + 0x18, s32(s + 0x18) + s16(s + 0x38))
	w16(s + 0x3A, vy)
	w32(s + 0x20, s32(s + 0x20) + s16(s + 0x3C))
	var sc := u16(s + 0x30) + u16(s + 0x44)
	for o in [0x30, 0x34, 0x32]:
		w16(s + o, sc)
	w32(s + 0x1C, s32(s + 0x1C) + s16(s + 0x3A))


# @orig game:0x80056800 sub_80056800  status:verified -- the move taken back; the same runs
func undo(s: int) -> void:
	for i in 3:
		w32(s + 0x18 + 4 * i, s32(s + 0x18 + 4 * i) - s16(s + 0x38 + 2 * i))


# effect_strike: bit 1 of +0 strikes the player through effect_hurt_player
# with the kind's spell_table record -- three attacks, the effect byte, five
# more; bit 2 the creatures, which no arm here sets.
# @orig game:0x80053850 effect_strike  status:partial -- the player's half; 3964 of 3964 calls handed what the game hands them (tools/effects.py); the creatures' (0x8004ceac) not here
func strike(point: int, a1: int, radius: int, mode: int, edge: int, scale: int) -> void:
	var s := current
	if (u8(s) & 1) == 0:
		return
	var rec: PackedByteArray = records.get(u8(s + 1), PackedByteArray())
	var r := func(o: int) -> int: return rec.decode_u16(o) if rec.size() >= o + 2 else 0
	world.hurt_player(Vector3i(s32(point), s32(point + 4), s32(point + 8)), a1, radius,
		mode, edge & 0xFFFF, [r.call(6), r.call(8), r.call(0xA)],
		int(rec[4]) if rec.size() > 4 else 0,
		[r.call(0xC), r.call(0xE), r.call(0x10), r.call(0x12), r.call(0x14)],
		scale & 0xFFFF, u8(s + 6))


# effect_collide: a grace count first; then collide_query at the point, its y
# plus half the height, with the flags +0 & 7 chooses -- 0 answers 1 and
# 5..7 answer 4 without asking.
# @orig game:0x80053310 effect_collide  status:verified -- through effect_move, the same 189 runs
func collide(p: Vector3i, radius: int, height: int) -> int:
	var s := current
	var g := u8(s + 0xB)
	if g != 0:
		w8(s + 0xB, g - 1)
		return 0
	var f := u8(s) & 7
	if not QUERY.has(f):
		return 1 if f == 0 else 4
	return world.collide_query(p.x, p.y + ((height & 0xFFF) >> 1), p.z, radius, height, QUERY[f])


# effect_move: the velocity added, effect_collide there and, with +0xd, half a
# step back too; +0xa the layer the tiles were asked in, +0x2c turned by spin.
# @orig game:0x800566d4 effect_move  status:verified -- the same 189 runs
func move(radius: int, height: int, spin: int) -> int:
	var s := current
	for i in 3:
		w32(s + 0x18 + 4 * i, s32(s + 0x18 + 4 * i) + s16(s + 0x38 + 2 * i))
	var p := Vector3i(s32(s + 0x18), s32(s + 0x1C), s32(s + 0x20))
	var hit := collide(p, radius, height)
	if u8(s + 0xD) != 0 and hit == 0:
		hit = collide(Vector3i(p.x - (s16(s + 0x38) >> 1), p.y - (s16(s + 0x3A) >> 1),
			p.z - (s16(s + 0x3C) >> 1)), radius, height)
	w8(s + 0xA, 2 if world.layer_offset != 0 else 1)
	w16(s + 0x2C, (u16(s + 0x2C) - spin) & 0xFFF)
	return hit


# --- the world the effects meet -------------------------------------------

# collide_query for an effect: the tiles (the radius and the height the
# effect asks with), and where the cell is marked occupied, the objects and
# the player. The occupancy here is the objects' marks (coll.occ) and the
# player's own: player_controller unmarks and marks again every frame through
# grid_mark (0x80033c4c) every cell from (x - 0x320) >> 11 to (x + 0x320) >> 11,
# and z the same. A creature's marks are not kept, so a cell only a creature
# marked does not let an effect there ask after the player or the objects.
# @orig game:0x80033f38 collide_query  status:partial -- the tiles, the objects and the player, for an effect's 0xa1 and 1; the creatures (0x10, 0x40), their marks and the fence not asked
func collide_query(x: int, y: int, z: int, r: int, h: int, flags: int) -> int:
	if coll == null:
		return 0
	var mask := 0
	var inside := x >= 0 and x <= 0x27FFF and z >= 0 and z <= 0x27FFF
	if flags & 1:
		var keep_r := coll.radius
		var keep_b := coll.body
		coll.radius = r
		coll.body = h & 0x0FFFFFFF          # tile_collision's mask: the top bits are flags
		coll.flags = h & 0xF0000000
		var q := coll.query(x, y, z)
		coll.flags = 0
		coll.radius = keep_r
		coll.body = keep_b
		surface18 = int(coll.surfaces.get(0x18, 100000))   # seeded 100000 (0x8003265c)
		mask = int(q["mask"])
		var at := int(q["at"])
		layer_offset = 5 if at >= 0 and at % 6 != 0 else 0
	if not inside:
		return mask
	var cx := x >> 11
	var cz := z >> 11
	var c := cz * KFCollision.W + cx
	var marked := false
	if player:
		var px := int(player.get("gx"))
		var pz := int(player.get("gz"))
		marked = cx >= (px - 0x320) >> 11 and cx <= (px + 0x320) >> 11 \
			and cz >= (pz - 0x320) >> 11 and cz <= (pz + 0x320) >> 11
	var an := get_node_or_null("../Actors")
	if not marked and an and an.has_method("marks_cell"):
		marked = bool(an.call("marks_cell", cx, cz))
	collide_actor = -1
	if (coll.occ.is_empty() or coll.occ[c] == 0) and not marked:
		return mask
	if flags & 0x10 and an and an.has_method("spot_taken"):
		collide_actor = int(an.call("spot_taken", x, y, z, r, h & 0x0FFFFFFF))
		if collide_actor != -1:
			mask |= 0x10
	if flags & 0x20:
		var keep_r := coll.radius
		var keep_b := coll.body
		coll.radius = r
		coll.body = h & 0x0FFFFFFF
		var o := coll.object_collide(x, y, z)
		coll.radius = keep_r
		coll.body = keep_b
		if o != -1:
			mask |= 0x20
	if flags & 0x80 and player:
		if coll.in_range(int(player.get("gx")), int(player.get("gy")), int(player.get("gz")),
				x, y, z, r + 0x320, 0x6A4, h & 0x0FFFFFFF) != -1:
			mask |= 0x80
	return mask


# effect_hurt_player with mode 0x8000, the effects' own: in_range_3d -- a box
# of the radius + 0x320, then the length to the player's middle (0x6a4 / 2 up)
# through the game's root, less 0x320 -- must be 0 or more, and the scale
# falls from `scale` to `edge` at the rim; then player_take_hit.
# @orig game:0x8002b114 effect_hurt_player  status:verified -- 118 of 118 strikes of bp26, scale and all; the bolts' through the same arithmetic
func hurt_player(p: Vector3i, _a1: int, radius: int, _mode: int, edge: int, attacks: Array,
		effect: int, more: Array, scale: int, pct: int) -> void:
	if player == null or not player.has_method("take_effect"):
		return
	var t := Vector3i(int(player.get("gx")), int(player.get("gy")), int(player.get("gz")))
	var hit := strike_scale(p, radius, t, edge, scale)
	if hit < 0:
		return
	player.call("take_effect", attacks + more, effect, hit, pct, p)


# @orig game:0x80016fb4 in_range_3d  status:verified -- through effect_hurt_player, 118 strikes of bp26
func strike_scale(p: Vector3i, radius: int, t: Vector3i, edge := EDGE, scale := 0x1000) -> int:
	var r := radius + OWN
	var dx := t.x - p.x
	var dz := t.z - p.z
	var dy := t.y - p.y - (BODY >> 1)
	if dx < -r or r < dx or dz < -r or r < dz or dy < -r or r < dy:
		return -1
	var ln := coll.isqrt((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3) + (dy >> 3) * (dy >> 3)) << 3
	if r < ln:
		return -1
	var d := ln - OWN
	if d < 0:
		return -1
	if edge == 0x1000:
		return scale
	var q := absi(d << 12) / radius
	var f := (0x1000 - (((q & 0xFFFF) * (0x1000 - edge)) >> 12)) & 0xFFFF
	return (scale * f) >> 12


# --- what a volley throws -------------------------------------------------

# effect_aim with one pass, no lead: the bearing from the point to the
# target's eye (0x640 above its feet), its yaw pulled towards the creature's
# facing (+0x42) the further off it is -- wholly past `spread` -- and its
# pitch by its own distance from the creature's (+0x40); a velocity of
# `speed` along it. [velocity x, y, z, the yaw].
# @orig game:0x8004f1d0 effect_aim  status:verified -- 600 of 600 random cases of the game's own as tools/effects.py aim, which the self-test holds this to
func aim(apitch: int, ayaw: int, target: Vector3i, speed: int, point: Vector3i,
		spread := 0x400) -> Array:
	var ang := vec_to_angles(target.x - point.x, target.y - (point.y + 0x640),
		target.z - point.z)
	var d: int = (int(ang[1]) - ayaw) & 0xFFF
	if d >= 0x800:
		d = 0x1000 - d
	var t: int = (d << 12) / spread
	if t > 0x1000:
		t = 0x1000
	ang[1] = s16v(angle_lerp(int(ang[1]), ayaw, t))
	d = (int(ang[0]) - apitch) & 0xFFF
	if d >= 0x800:
		d = 0x1000 - d
	ang[0] = s16v(angle_lerp(int(ang[0]), apitch, d))
	var v := coll.direction_from_angles(int(ang[0]), int(ang[1]))
	var sp := s16v(speed)
	return [s16v((v[0] * sp) >> 12), s16v((v[1] * sp) >> 12), s16v((v[2] * sp) >> 12), ang[1]]


# @orig game:0x80016c90 vec_to_angles  status:verified -- through effect_aim, the 600
func vec_to_angles(dx: int, dy: int, dz: int) -> Array:
	var yaw := s16v(coll.vec_angle(dx, dz))
	var ln := coll.isqrt(s32v((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3)) & 0xFFFFFFFF) << 3
	var pitch := (-coll.vec_angle(dy, ln)) & 0xFFF
	return [pitch, yaw, 0]


# @orig game:0x80017170 angle_lerp  status:verified -- through effect_aim, the 600
static func angle_lerp(a: int, b: int, t: int) -> int:
	var d := (s16v(b) - s16v(a)) & 0xFFF
	if d > 0x800:
		d -= 0x1000
	return (a + ((d * t) >> 12)) & 0xFFF


# @port helper -- sign-extended halfword
static func s16v(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v & 0x8000 else v


# A volley's bolt (actor_animation_effects' arm for 0x1f..0x25, 0x8004fc18):
# effect_aim from the point at the player with a speed of 0x12c, the spread
# 0x400 and one pass, then effect_spawn(pct, 0x83, kind, the point, that
# velocity, the creature's angles).
# @orig game:0x8004fc18 actor_animation_effects+0x804  status:transcribed -- the arm for 0x1f to 0x25; of those kinds effect_spawn here has 0x1f, 0x22, 0x23 and 0x24
func volley_bolt(kind: int, pct: int, point: Vector3i, apitch: int, ayaw: int) -> void:
	if player == null or coll == null:
		return
	var t := Vector3i(int(player.get("gx")), int(player.get("gy")), int(player.get("gz")))
	var a := aim(apitch, ayaw, t, 0x12C, point)
	var v := PackedByteArray()
	v.resize(8)
	for i in 3:
		v.encode_s16(2 * i, int(a[i]))
	var ang := PackedByteArray()
	ang.resize(8)
	ang.encode_s16(0, apitch)
	ang.encode_s16(2, ayaw)
	var p := PackedByteArray()
	p.resize(16)
	p.encode_s32(0, point.x)
	p.encode_s32(4, point.y)
	p.encode_s32(8, point.z)
	spawn(pct, 0x83, kind, p, [v, ang])


# effect_spawn's spore, as actor_animation_effects arm 0x26 asks for it: the
# point the creature's vertex gives, effect_aim's velocity at a speed of 0,
# +6 the percentage -- and then the grace count +0xb set to 0 (0x8004f720),
# so a spore meets the tiles from its first frame.
# @orig game:0x8004f6c4 actor_animation_effects+0x2b0  status:verified -- arm 0x26; tools/effects.py against bp26
func spawn_spore(point: Vector3i, pct: int) -> void:
	var p := PackedByteArray()
	p.resize(16)
	p.encode_s32(0, point.x)
	p.encode_s32(4, point.y)
	p.encode_s32(8, point.z)
	var s := spawn(pct, 0x81, 0x26, p, [null])
	if s >= 0:
		w8(s + 0xB, 0)


# --- drawing --------------------------------------------------------------

# render_walk's third loop: a slot whose +8 & 3 is not 0 is drawn by
# draw_model_plain, model_table[+3 + 0x28] at +0x18, turned by +0x28.. with
# 0x800 on the yaw, through the scale +0x30..+0x34.
# @orig game:0x8004165c render_walk+0xb78  status:partial -- the model, the place, the turn and the scale of +8 & 0xc 0, the world's; not the view test (+8 & 3, view_bits_at), the other matrices +8 & 0xc chooses -- 4 (the particles) drawn as the world's, 0xc (the marks and sparkles in front of the eye) not at all, nor +0xe and the light
func _draw_all() -> void:
	var live := {}
	for k in COUNT:
		var s := k * STRIDE
		if m[s] == 0xFF or (m[s + 8] & 3) == 0 or (m[s + 8] & 0xC) == 0xC:
			continue
		var model := u8(s + 3) + MODEL_BASE
		var n = nodes.get(k)
		if n == null or int(n[1]) != model:
			if n != null and n[0] != null:
				(n[0] as Node).queue_free()
			var tn: Node3D = templates.get(model)
			var made: Node3D = (tn.duplicate() as Node3D) if tn else null
			if made:
				made.visible = true
				add_child(made)
			n = [made, model]
			nodes[k] = n
		live[k] = true
		var node: Node3D = n[0]
		if node == null:
			continue
		node.position = Vector3(float(s32(s + 0x18)) / 1000.0, float(-s32(s + 0x1C)) / 1000.0,
			float(-s32(s + 0x20)) / 1000.0)
		node.basis = LOOT.game_basis(u16(s + 0x28) & 0xFFF, (u16(s + 0x2A) + 0x800) & 0xFFF,
			u16(s + 0x2C) & 0xFFF).scaled_local(Vector3(float(s16(s + 0x30)),
			float(s16(s + 0x32)), float(s16(s + 0x34))) / 4096.0)
	for k in nodes.keys():
		if not live.has(k):
			var n = nodes[k]
			if n[0] != null:
				(n[0] as Node).queue_free()
			nodes.erase(k)

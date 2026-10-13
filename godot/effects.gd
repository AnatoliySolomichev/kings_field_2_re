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
const STONE := 0x06
const WIND_CUTTER := 0x0D
const HAZE := 0x0B
const SHUDOM := 0x09
const WALWIND := 0x11
const RING := 0x5E                 # shudom's
const WAVE := 0x59                 # walwind's
const EARTH_WAVE := 0x07           # and 0x16, the same arms
const BORTECTH := 0x0C
const HOLD := 0x65                 # bortecth's
const METEOR := 0x5F
const BLAST := 0x5A                # meteor's
const ORLADIN := 0x15
const BURST := 0x58                # orladin's
const RAY := 0x5B                  # orladin's
const TORNADO := 0x0F
const FIRE_WALL := 0x01
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
var tick_frame := PackedByteArray()  # effect_tick's stack frame (0x2b8): what one arm leaves the next
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
	tick_frame.resize(0x2B8)
	tick_frame.fill(0)


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
# @orig game:0x80053c84 effect_spawn  status:partial -- the common setting up and the arms of 32 kinds: 0 (fire ball), 1 (fire wall), 6 (stone), 7 and 0x16 (earth wave), 9 (shudom), 0xb (haze), 0xc (bortecth), 0xd (wind cutter), 0xf (tornado), 0x11 (walwind), 0x15 (orladin), 0x17, 0x19, 0x1a, 0x1b, 0x1c, 0x1e (the healing and protecting), 0x1f, 0x22, 0x23, 0x24, 0x26 (the creatures'), 0x58, 0x59, 0x5a, 0x5b, 0x5e, 0x5f, 0x65 (the spells' children), 0x6f (puff) and 0x70 (splash); tools/effects.py's, which the game's own holds (machine_check, magic_check, spell_hit_check) and the self-test holds this to. 35 kinds have the empty arm, which frees the slot, as here; the other 63 arms are not here
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
		STONE:                              # 0x800541f4
			w16(s + 0xE, 0x40)
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 2, 0xF)
			w8(s + 3, 0xF)
			w8(s + 0x44, 0)
			w16(s + 0x10, 0x46)             # and its sound (0x32), not here
		WIND_CUTTER:                        # 0x800544b8
			setup(s, 0xD, 0x1400, 5)        # after its sound (0x2b)
			w16(s + 0x10, 0x2D)
			w8(s + 0x44, 0)
			w8(s + 0xD, 1)
			w16(s + 0x2A, int(world.field("vy")))   # the view's angles; pitch and roll 0
			w16(s + 0x2E, 0)
			w16(s + 0x30, 0x1800)
			w16(s + 0x32, 0x1000)
			w16(s + 0x28, 0)
			w16(s + 0x2C, 0)
			w16(s + 0x34, 0x2000)
		HAZE:                               # 0x80054b08
			particle(s, 0x16, 0x1000, 5)
			w16(s + 0x10, 0x46)
			w16(s + 0xE, 0xC0)              # its sound (0x94) with a cast's third, not here
		SHUDOM:                             # 0x80054e54
			_flat(s, 0x33, 0x4B0)
			w16(s + 0xE, 0)
			w16(s + 0x46, int(world.field("vy")))   # and its sound (0x92), not here
		WALWIND:                            # 0x80054804
			_flat(s, 0x32, 0xBB8)           # and its sound (0x98), not here
		RING:                               # 0x80054b7c
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 2, 0x1E)
			w8(s + 3, 0x1E)
			w16(s + 0x10, 0x1E)
			w16(s + 0x32, 0x1000)
			w8(s + 9, 0)
			w16(s + 0x30, 0xA)
			w16(s + 0x34, 0xA)
			w16(s + 0x28, 0x400)
			w16(s + 0x2C, 0)
			w16(s + 0xE, 0)
			w16(s + 0x2A, int(args[1]))     # and its sound (0x26), not here
		WAVE:                               # 0x80054894
			w8(s + 8, 1)
			w8(s + 2, 0x1F)
			w8(s + 3, 0x1F)
			w8(s + 0xC, 0x34)
			w16(s + 0x12, 0x1000)
			w16(s + 0x32, 0x7D0)
			w8(s + 4, 0)
			w8(s + 9, 5)
			w16(s + 0x30, 0x28)
			w16(s + 0x34, 0x28)
			w16(s + 0x10, 0x50)
			w16(s + 0x44, 0)
			w8(s + 0xB, 5)
		EARTH_WAVE, 0x16:                   # 0x80054ef4
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 2, 0xE)
			w8(s + 3, 0xE)
			w8(s + 0xC, 0x34)
			w16(s + 0x12, 0x1000)
			w16(s + 0x34, 0)
			w16(s + 0x30, 0)
			w16(s + 0x44, int(args[1]))     # how far it goes
			w16(s + 0x46, int(args[2]))     # how fast
			w16(s + 0x48, int(args[3]))     # the strike's scale
			w16(s + 0xE, (int(args[4]) & 0xFFFF) << 6)   # and its sound (0x23), not here
		BORTECTH:                           # 0x80054a84
			setup(s, 0x1F, 0xAF0, 5)
			w16(s + 0x10, 0x3C)
			w16(s + 0x32, 0x1400)
			for o in [0x4A, 0x48, 0x46, 0x44]:
				w16(s + o, 0)
			w16(s + 0xE, 0x80)              # and its sound (0x95), not here
		HOLD:                               # 0x80054ac8
			setup(s, 0x20, 0x1B58, 5)
			w16(s + 0x10, 0x3C)
			for o in [0x4A, 0x48, 0x44]:
				w16(s + o, 0)
			w16(s + 0x32, 0)
			w16(s + 0xE, 0x40)
			w16(s + 0x46, int(args[1]))     # the creature held, or -1
		METEOR:                             # 0x8005593c
			_spawn_meteor(s)
		FIRE_WALL:                          # 0x80053fa8
			w8(s + 9, 5)
			w8(s + 2, 0x28)
			w8(s + 3, 0x28)
			w8(s + 0xC, 0x34)
			w16(s + 0x12, 0x1000)
			w8(s + 8, 1)
			w8(s + 4, 0)
			w16(s + 0x30, 0x7D0)
			w16(s + 0x32, 0xA)
			w16(s + 0x34, 0x7D0)
			put(s + 0x28, (args[1] as PackedByteArray).slice(0, 8))   # the view's angles
			w16(s + 0x28, 0)
			w16(s + 0x2C, 0)
			w16(s + 0x3A, 0)
			w16(s + 0x44, 0)
			w16(s + 0x10, 0x78)
			w16(s + 0xE, 0)
			w8(s + 0xD, 1)                  # and its sound (0x31), not here
		TORNADO:                            # 0x80054294
			var i := int(args[2])           # the first of the two 0, the second 1
			w8(s + 4, 0x80)
			w8(s + 2, 8)
			w8(s + 3, 8)
			w8(s + 9, 5)
			w16(s + 0x10, 0x32)
			w16(s + 0x32, 0xC80)
			w8(s + 8, 1)
			w8(s + 0x44, 0)
			w8(s + 0xD, 1)
			w16(s + 0xE, 0x40)
			w16(s + 0x30, 2000 * i + 0xC80)
			w16(s + 0x34, 2000 * i + 0xC80)
			w16(s + 0x2A, i << 11)          # and the first, its sound (0x96), not here
		ORLADIN:                            # 0x800543e8
			particle(s, 0x37, 0x1800, 5)
			w16(s + 0x10, 0x78)
			w8(s + 0xD, 1)
			w16(s + 0x44, 0)
			w16(s + 0xE, 0x40)              # and its sound (0x9a), not here
		BURST:                              # 0x800548ec
			setup(s, 0x15, 0, 5)
			for o in [0x30, 0x32, 0x34]:
				w16(s + o, int(args[1]))
			w16(s + 0x10, 0x2D)
			for o in [0x28, 0x2A, 0x2C]:
				w16(s + o, 0)
			w16(s + 0xE, (int(args[2]) & 0xFFFF) << 6)
		RAY:                                # 0x80055788
			w8(s + 4, 0x80)
			w8(s + 2, 0xB)
			w8(s + 3, 0xB)
			w8(s + 8, 5)
			w8(s + 9, 5)
			w8(s + 0xC, 0x33)
			w16(s + 0x32, 0xC00)
			w16(s + 0x10, 0x14)
			w16(s + 0x12, 0x1000)
			w16(s + 0x30, 0x1000)
			w16(s + 0x34, 0x1000)
			w16(s + 0xE, 0x40)
		BLAST:                              # 0x800553a8
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 2, 0x1E)
			w8(s + 3, 0x1E)
			w8(s + 0xC, 0x34)
			w16(s + 0x12, 0x1000)
			w16(s + 0x30, 0xA)
			w16(s + 0x34, 0xA)
			w16(s + 0x44, int(args[1]))     # how far it goes
			w16(s + 0x46, int(args[2]))     # how fast
			w16(s + 0xE, 0)
			w16(s + 0x48, int(args[3]))     # the strike's scale; and its sound (0x23), not here
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


# What shudom's and walwind's arms share (0x80054e54, 0x80054804): model
# `model`, mode 5 (+9), the yaw of the angles args[1] points at -- the view's,
# its fourth halfword 0 -- level (+0x3a 0), a life of 0x96.
# @orig game:0x80054e54 effect_spawn+0x11d0  status:verified -- shudom's arm, walwind's (0x80054804) the same but the model and scale; through spell_hit_check
func _flat(s: int, model: int, scale: int) -> void:
	w8(s + 8, 1)
	w8(s + 9, 5)
	w8(s + 2, model)
	w8(s + 3, model)
	w8(s + 0xC, 0x34)
	w16(s + 0x12, 0x1000)
	w8(s + 4, 0)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, scale)
	w16(s + 0x2A, int(world.field("vy")))
	w16(s + 0x2E, 0)
	w16(s + 0x28, 0)
	w16(s + 0x2C, 0)
	w16(s + 0x3A, 0)
	w16(s + 0x10, 0x96)
	w16(s + 0x44, 0)


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
# @orig game:0x800568bc effect_tick  status:partial -- the switch, and the arms of the same 32 kinds as effect_spawn's; the other 63 do nothing here
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
		STONE:
			_tick_stone(s)
		WIND_CUTTER:
			_tick_wind(s)
		HAZE:
			_tick_haze(s)
		SHUDOM:
			_tick_shudom(s)
		WALWIND:
			_tick_walwind(s)
		RING:
			_tick_ring(s)
		WAVE:
			_tick_wave(s)
		EARTH_WAVE, 0x16:
			_tick_earth_wave(s)
		BORTECTH:
			_tick_bortecth(s)
		HOLD:
			_tick_hold(s)
		METEOR:
			_tick_meteor(s)
		TORNADO:
			_tick_tornado(s)
		FIRE_WALL:
			_tick_fire_wall(s)
		ORLADIN:
			_tick_orladin(s)
		BURST:
			_tick_burst(s)
		RAY:
			_tick_ray(s)
		BLAST:
			_tick_blast(s)
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
		_attack(s, hit)
		w8(s + 7, 1)
	elif ph >= 3:
		w8(s, 0xFF)
		return
	w8(s + 4, (ph - 0x80) & 0xFF)
	var sc := (u16(s + 0x30) + 0x800) & 0xFFFF
	for o in [0x30, 0x32, 0x34]:
		w16(s + o, sc)
	w8(s + 7, u8(s + 7) + 1)


# Stone (0x800569e4): flying (+0x44 0) it spins its pitch 0xc8 a frame; its
# first hit strikes, steps it back and drops it from -0x64, falling by 0xd a
# frame (+0x44 1); the next hit strikes again and it lies (+0x44 2), +9 5,
# +0xc 0x32, fading +0x12 by 0x100 a frame from 0x400 to 0x1000. A splash a
# frame while it is in the water.
# @orig game:0x800569e4 effect_tick+0x128  status:verified -- tools/effects.py spell_hit_check, 63 of 63 runs of the game's own end to end, all 200 creatures; the self-test this to it
func _tick_stone(s: int) -> void:
	var b44 := u8(s + 0x44)
	if b44 == 2:
		var v := (u16(s + 0x12) + 0x100) & 0xFFFF
		w16(s + 0x12, v)
		if s16v(v) >= 0x1000:
			w8(s, 0xFF)
		return
	if b44 == 1:
		w16(s + 0x3A, u16(s + 0x3A) + 0xD)
	w16(s + 0x28, u16(s + 0x28) + 0xC8)
	var hit := move(0x1F4, 0x1F4, 0xFA)
	if hit != 0:
		_attack(s, hit)
		if u8(s + 0x44) == 1:
			w8(s + 0x44, 2)
			w8(s + 9, 5)
			w8(s + 0xC, 0x32)
			w16(s + 0x12, 0x400)
			return
		undo(s)
		w8(s + 0x44, 1)
		w16(s + 0x3C, 0)
		w16(s + 0x38, 0)
		w16(s + 0x3A, -0x64)
	_splash_one(s + 0x18, 0x4000, 0x4000, 0x1F4)


# Wind cutter (0x800574b4): flat, its yaw the view's turning 0x2bc a frame;
# each thing it passes it strikes once (+0x44 the latch, cleared on a clear
# frame), and the tiles (any of the low four bits) end it.
# @orig game:0x800574b4 effect_tick+0xbf8  status:verified -- tools/effects.py spell_hit_check, 63 of 63 runs of the game's own end to end; the self-test this to it
func _tick_wind(s: int) -> void:
	var hit := move(0xB4, 0x80000000, 0)
	if hit != 0:
		if hit & 0xF:
			w8(s, 0xFF)
		if u8(s + 0x44) == 0:
			w8(s + 0x44, 1)
			_attack(s, hit)
	else:
		w8(s + 0x44, 0)
	_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
	w16(s + 0x2A, u16(s + 0x2A) + 0x2BC)


# Haze (0x80058164): each thing it meets it strikes once (+0x44 the latch,
# cleared on a clear frame), and the tiles end it -- the wind cutter's way,
# with nothing turned and no splash.
# @orig game:0x80058164 effect_tick+0x18a8  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_haze(s: int) -> void:
	var hit := move(0xB4, 0, 0)
	if hit != 0:
		if hit & 0xF:
			w8(s, 0xFF)
		if u8(s + 0x44) == 0:
			_attack(s, hit)
			w8(s + 0x44, 1)
	else:
		w8(s + 0x44, 0)


# Shudom (0x800581b8): level through anything, the tiles ending it; at counts
# 12, 18, 24 ... (11 or more, a multiple of 6) a ring (0x5e) where it is,
# turned as the view was when it was cast (+0x46).
# @orig game:0x800581b8 effect_tick+0x18fc  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_shudom(s: int) -> void:
	if move(0xFA, 0x80000000, 0) & 0xF:
		w8(s, 0xFF)
	var n := s16(s + 0x44)
	if n >= 0xB and n % 6 == 0:
		spawn(0xA, 0x42, RING, m.slice(s + 0x18, s + 0x28), [null, s16(s + 0x46)])
	_spin(s)


# Walwind (0x80058248): level, striking whatever it meets every frame, the
# tiles ending it; at counts 20, 30, 40 ... (16 or more, a multiple of 10) a
# wave (0x59) falling from where it is.
# @orig game:0x80058248 effect_tick+0x198c  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_walwind(s: int) -> void:
	var hit := move(0xFA, 0x80000000, 0)
	if hit != 0:
		if hit & 0xF:
			w8(s, 0xFF)
		_attack(s, hit)
	var n := s16(s + 0x44)
	if n >= 0x10 and n % 10 == 0:
		var v := PackedByteArray()
		v.resize(8)
		v.encode_s16(2, 0x54)
		spawn(0xA, 0x42, WAVE, m.slice(s + 0x18, s + 0x28), [v])
	_spin(s)


# What shudom's and walwind's arms end with (0x800582f4): +0x44 counted,
# +0x14 turned 0x80.
# @orig game:0x800582f4 effect_tick+0x1a38  status:verified -- through shudom and walwind
func _spin(s: int) -> void:
	w16(s + 0x44, u16(s + 0x44) + 1)
	w16(s + 0x14, (u16(s + 0x14) + 0x80) & 0xFFF)


# Shudom's ring (0x80059adc): growing 0xc0 a frame; from 0x300 it strikes the
# creatures between 15/16 and 9/8 of it from its middle, 0x3e8 under it,
# mode 0x8002 from the yaw it was given; past 0xc80 gone.
# @orig game:0x80059adc effect_tick+0x3220  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, the creatures it strikes among them; the self-test this to it
func _tick_ring(s: int) -> void:
	w16(s + 0x34, u16(s + 0x34) + 0xC0)
	w16(s + 0x30, u16(s + 0x30) + 0xC0)
	var sc := s16(s + 0x30)
	if sc >= 0x300:
		strike([s32(s + 0x18), s32v(s32(s + 0x1C) + 0x3E8), s32(s + 0x20), s16(s + 0x2A)],
			(15 * sc) >> 4, (9 * sc) >> 3, 0x8002, 0x400, 0x1000)
	if s16(s + 0x30) >= 0xC81:
		w8(s, 0xFF)


# Walwind's wave (0x80058314): turning 0x140 a frame. Falling until the tiles
# stop it (+0x44 0; its sound, 0x27, then); up 0xa0 once (1); then growing
# 0x280 a frame (2), from 0x300 striking the creatures between 29/32 and
# 35/32 of it, mode 0x800 -- and gone past 0x36b0, striking once more as +0
# 0xff: the player too, and the creatures as nobody's spell, no experience.
# @orig game:0x80058314 effect_tick+0x1a58  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, the creatures it strikes among them; the self-test this to it
func _tick_wave(s: int) -> void:
	w16(s + 0x2A, u16(s + 0x2A) + 0x140)
	var n := s16(s + 0x44)
	if n == 0:
		if move(0xB4, 0x80000000, 0) & 0xF:
			w16(s + 0x44, u16(s + 0x44) + 1)
	elif n == 1:
		w16(s + 0x44, u16(s + 0x44) + 1)
		w32(s + 0x1C, s32(s + 0x1C) - 0xA0)
	elif n == 2:
		w16(s + 0x30, u16(s + 0x30) + 0x280)
		w16(s + 0x34, u16(s + 0x34) + 0x280)
		var sc := s16(s + 0x30)
		if sc >= 0x36B1:
			w8(s, 0xFF)
		if sc >= 0x300:
			strike([s32(s + 0x18), s32v(s32(s + 0x1C) + 0x3E8), s32(s + 0x20), 0],
				(29 * sc) >> 5, (35 * sc) >> 5, 0x800, 0x400, 0x1000)


# sub_800537e8: what was hit, handed to actor_attack_player from 8
# velocities back, with 0x1388 and the caster's strength.
# @orig game:0x800537e8 sub_800537e8  status:verified -- through the fire ball, stone and wind cutter, spell_hit_check
func _attack(s: int, hit: int) -> void:
	var back := []
	for i in 3:
		back.append(s32(s + 0x18 + 4 * i) - (s16(s + 0x38 + 2 * i) << 3))
	_hand(s, hit, 0x1388, back)


# sub_800536f8: actor_attack_player(code, +0, the record, strength, the
# caster's strength, +6, the point -- null for none).
# @orig game:0x800536f8 sub_800536f8  status:verified -- through every spell's hit and bortecth's, spell_hit_check
func _hand(s: int, code: int, strength: int, point) -> void:
	world.attack_hit(code, u8(s), u8(s + 1), strength, magic_strength(s), u8(s + 6), point)


# Earth wave (0x80057c34, kinds 7 and 0x16): a ring growing +0x46 a frame;
# from 0x300 it strikes between four times its last size and four times its
# size less one, 0x3e8 under its point, mode 0x7d0, at +0x48 throughout;
# gone past +0x44. Cast with +0 0x43, it strikes the player too -- who stands
# at its middle, nearer than it reaches.
# @orig game:0x80057c34 effect_tick+0x1378  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_earth_wave(s: int) -> void:
	var v := u16(s + 0x30) + u16(s + 0x46)
	w16(s + 0x30, v)
	w16(s + 0x34, v)
	var sc := s16(s + 0x30)
	if sc >= 0x300:
		strike([s32(s + 0x18), s32v(s32(s + 0x1C) + 0x3E8), s32(s + 0x20), 0],
			(sc - s16(s + 0x46)) << 2, (sc << 2) - 1, 0x7D0, 0x1000, s16(s + 0x48))
	if s16(s + 0x44) < s16(s + 0x30):
		w8(s, 0xFF)


# Bortecth (0x80057cd0): its first frame asks collide_query for the creatures
# and objects within 0x400 of its point, its height its scale; a creature
# alone (the mask 0x10 exactly) is handed actor_attack_player with code
# 0x10010 -- the hit, and its +0x28 bit 0x800, the hold -- 0x1388 and no
# point. Then its child 0x65 with the creature's slot, or -1. It turns 0x1a4
# a frame.
# @orig game:0x80057cd0 effect_tick+0x1414  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, the hold and its end among it; the self-test this to it
func _tick_bortecth(s: int) -> void:
	if s16(s + 0x44) == 0:
		var mask: int = world.collide_query(s32(s + 0x18), s32(s + 0x1C), s32(s + 0x20), 0x400,
			s16(s + 0x30), 0x30)
		if mask == 0x10:
			_hand(s, 0x10010, 0x1388, null)
		w16(s + 0x44, u16(s + 0x44) + 1)
		spawn(0xA, 0, HOLD, m.slice(s + 0x18, s + 0x28), [null, int(world.collide_actor)])
		w16(s + 0x48, 0)
		w16(s + 0x4A, 0)
	w16(s + 0x2A, u16(s + 0x2A) + 0x1A4)


# Bortecth's hold (0x80057d74, kind 0x65): rising 0x1b8 a frame for 12
# frames; from count 48 sinking again and letting the creature go (its +0x28
# bit 0x800); from 12 to 47 a puff (0x6f) a frame, its velocity three rands
# over 0x7fff. It turns -0x190 a frame.
# @orig game:0x80057d74 effect_tick+0x14b8  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_hold(s: int) -> void:
	var n := s16(s + 0x44)
	if n < 0xC:
		w16(s + 0x32, u16(s + 0x32) + 0x1B8)
	if n >= 0x30:
		w16(s + 0x32, u16(s + 0x32) - 0x1B8)
		var c := s16(s + 0x46)
		if c != -1:
			world.release(c)
	if ((u16(s + 0x44) - 0xC) & 0xFFFFFFFF) < 0x24:
		var v := PackedByteArray()
		v.resize(8)
		v.encode_s16(0, _div7fff(int(world.rand()) << 9) - 0x100)
		v.encode_s16(2, _div7fff(-(int(world.rand()) << 8)))
		v.encode_s16(4, _div7fff(int(world.rand()) << 9) - 0x100)
		spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v, 0x1000, -0x80, 5, 0xC, 0, 1, 0])
	w16(s + 0x44, u16(s + 0x44) + 1)
	w16(s + 0x2A, u16(s + 0x2A) - 0x190)


# Meteor's arm of effect_spawn (0x8005593c): put down where it is to land --
# +0x48 that y -- then moved to a point within 0x514 of it each way by two
# rands, unless collide_wrapper_actor finds that point blocked; from there
# 0x9d8 back in x and z and 0x4000 up, falling (0x64, 0x28a, 0x64).
# @orig game:0x8005593c effect_spawn+0x1cb8  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, the blocked point among them; the self-test this to it
func _spawn_meteor(s: int) -> void:
	var y := s32(s + 0x1C)
	w8(s + 8, 1)
	w8(s + 4, 0x80)
	w8(s + 2, 0xF)
	w8(s + 3, 0xF)
	w16(s + 0x10, 0x2D)
	w32(s + 0x48, y)
	var x := s32v(s32(s + 0x18) - 0x514 + ((int(world.rand()) * 2600) >> 15))
	var z := s32v(s32(s + 0x20) - 0x514 + ((int(world.rand()) * 2600) >> 15))
	if int(world.collide_wrapper(x, y, z, 0xA, 0xA)) != 0:
		x = s32(s + 0x18)
		z = s32(s + 0x20)
	w32(s + 0x18, x - 0x9D8)
	w16(s + 0x38, 0x64)
	w16(s + 0x3C, 0x64)
	w32(s + 0x1C, y - 0x4000)
	w16(s + 0x3A, 0x28A)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, 0x1000)
	w16(s + 0xE, 0x80)
	w32(s + 0x20, z - 0x9D8)                # and its sound (0x2d), not here


# Meteor (0x8005b8f8): falling, turning 0x100 a frame, asking collide_query
# for the creatures, objects and player within 0xa; meeting none, the floor
# under it at +0x48 (collide_surface): above it, six puffs a frame behind it
# (its velocity / 8 times 6 down to 1, scales 0xb86 down by 0x15e); at or
# past it, set on it. Then the impact: what it met struck (sub_800537e8), a
# blast (0x5a) with its own +0 -- 0x640 at 0x64 a frame, scale 0x800 -- four
# puffs about it, and gone.
# @orig game:0x8005b8f8 effect_tick+0x503c  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, on the floor and on a creature; the self-test this to it
func _tick_meteor(s: int) -> void:
	for i in 3:
		w32(s + 0x18 + 4 * i, s32(s + 0x18 + 4 * i) + s16(s + 0x38 + 2 * i))
	w16(s + 0x2A, u16(s + 0x2A) + 0x100)
	var x := s32(s + 0x18)
	var z := s32(s + 0x20)
	var mask: int = world.collide_query(x, s32(s + 0x1C), z, 0xA, 0xA, 0xB0)
	if mask == 0:
		var surf: int = world.surface(x, s32(s + 0x48), z, 0, 0)
		if s32(s + 0x1C) < surf:
			var scale := 0xB86
			for k in range(5, -1, -1):
				var v := m.slice(s + 0x38, s + 0x40)
				for i in 3:
					v.encode_s16(2 * i, s16v((s16(s + 0x38 + 2 * i) >> 3) * (k + 1)))
				spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28),
					[v, scale, -0x80, 5, 0x1C, 0, 1, 2])
				scale -= 0x15E
			return
		w32(s + 0x1C, surf)
	var point := m.slice(s + 0x18, s + 0x28)
	_attack(s, mask)
	var v0 := PackedByteArray()
	v0.resize(8)
	v0.encode_s16(2, -0x20)
	spawn(0xA, u8(s), BLAST, point, [v0, 0x640, 0x64, 0x800])
	for _k in 4:
		var pt := m.slice(s + 0x18, s + 0x28)
		pt.encode_s32(0, s32v(pt.decode_s32(0) - 0x1F4 + ((int(world.rand()) * 1000) >> 15)))
		pt.encode_s32(8, s32v(pt.decode_s32(8) - 0x1F4 + ((int(world.rand()) * 1000) >> 15)))
		var v := PackedByteArray()
		v.resize(8)
		v.encode_s16(2, -0x168)
		spawn(0xA, 0, TRAIL, pt, [v, 0x4000, -0x80, 5, 0x1D, 0, 1, 2])
	w8(s, 0xFF)


# Meteor's blast (0x80059a28): earth wave's ring, its two sizes kept apart,
# turning 0x200 a frame. With meteor's +0 (0x43) it strikes the player too.
# @orig game:0x80059a28 effect_tick+0x316c  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_blast(s: int) -> void:
	w16(s + 0x30, u16(s + 0x30) + u16(s + 0x46))
	w16(s + 0x34, u16(s + 0x34) + u16(s + 0x46))
	var sc := s16(s + 0x30)
	if sc >= 0x300:
		strike([s32(s + 0x18), s32v(s32(s + 0x1C) + 0x3E8), s32(s + 0x20), 0],
			(sc - s16(s + 0x46)) << 2, (sc << 2) - 1, 0x7D0, 0x1000, s16(s + 0x48))
	if s16(s + 0x44) < s16(s + 0x30):
		w8(s, 0xFF)
	w16(s + 0x2A, u16(s + 0x2A) + 0x200)


# Tornado (0x80056ac4): effect_move at 0xb4 with no height and no turn; the
# tiles (the hit's low two bits) take the move back and free it, and what it
# meets it strikes once (sub_800537e8, +0x44 the latch a clear frame lifts).
# Then a strike about its point -- radius its scale x / 8, mode its height /
# 2, 0x640: in_range's asker's height -- with +0 as it stands, so a tornado
# that has just met a wall, its +0 0xff, strikes the player too. The point is
# offset by the three halfwords at effect_tick's sp+0x50, which the arm
# writes only after, with its puff's velocity: within a frame the tornado
# before it; the first of a frame reads what the rest of the game's frame
# left there, which the port does not have -- it keeps the last tornado's.
# A puff (0x6f) a frame, velocity three rands over 0x7fff; a splash in the
# water; it turns 0x15e a frame.
# @orig game:0x80056ac4 effect_tick+0x208  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, 126 of 126 runs; the self-test this to it. The leftover a frame's first tornado reads is the last tornado's here, the game's other routines' there
func _tick_tornado(s: int) -> void:
	var hit := move(0xB4, 0, 0)
	if hit != 0:
		if hit & 3:
			undo(s)
			w8(s, 0xFF)
		if u8(s + 0x44) == 0:
			w8(s + 0x44, 1)
			_attack(s, hit)
	else:
		w8(s + 0x44, 0)
	strike(_off_point(s, 0x50), 0, s16(s + 0x30) >> 3, s16(s + 0x32) >> 1, 0x400, 0x1000)
	tick_frame.encode_s16(0x50, s16v(_div7fff(int(world.rand()) << 9) - 0x100))
	tick_frame.encode_s16(0x52, s16v(_div7fff(-(int(world.rand()) << 8))))
	tick_frame.encode_s16(0x54, s16v(_div7fff(int(world.rand()) << 9) - 0x100))
	spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x50, 0x58), 0x270F,
		-0x80, 5, 0x16, 0, 1, 1])
	w16(s + 0x2A, u16(s + 0x2A) + 0x15E)
	_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)


# The slot's point offset by the three halfwords at effect_tick's sp+`at`:
# what an arm that writes its puff's velocity there left, read before this
# arm writes its own.
# @port helper -- a strike point off a stack leftover, tornado's and fire wall's
func _off_point(s: int, at: int) -> Array:
	return [s32v(s32(s + 0x18) + tick_frame.decode_s16(at)),
		s32v(s32(s + 0x1C) + tick_frame.decode_s16(at + 2)),
		s32v(s32(s + 0x20) + tick_frame.decode_s16(at + 4)), 0]


# Fire wall (0x8005a070): effect_move at 0xb4 and the height's top bit --
# walls do not stop it -- a creature it meets struck every frame
# (sub_800537e8). Then a strike about its point, radius its scale x / 4, mode
# its height, the point offset by the halfwords at effect_tick's sp+0x170,
# which flash, fire storm and this arm write their puffs' velocities to --
# this one only after. Rising (+0x44 0) 0x1f4 a frame and 0x230 wider to
# 0x1069, standing three frames (1), sinking (2), gone under 0x64; turning
# 0x1f4 a frame. A puff (0x6f) a frame, rising 0x64 to 0xc8.
# @orig game:0x8005a070 effect_tick+0x37b4  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, 126 of 126 runs; the self-test this to it. The leftover a frame's first reader takes is the port's last writer's, the game's other routines' there
func _tick_fire_wall(s: int) -> void:
	var hit := move(0xB4, 0x80000000, 0)
	if hit & 0x10:
		_attack(s, hit)
	strike(_off_point(s, 0x170), 0, s16(s + 0x30) >> 2, s16(s + 0x32), 0x400, 0x1000)
	match s16(s + 0x44):
		0:
			w16(s + 0x30, u16(s + 0x30) + 0x230)
			w16(s + 0x32, u16(s + 0x32) + 0x1F4)
			w16(s + 0x34, u16(s + 0x34) + 0x230)
			w16(s + 0x2A, u16(s + 0x2A) + 0x1F4)
			if s16(s + 0x32) >= 0x1069:
				w16(s + 0x46, 0)
				w16(s + 0x44, u16(s + 0x44) + 1)
		1:
			w16(s + 0x46, u16(s + 0x46) + 1)
			w16(s + 0x2A, u16(s + 0x2A) + 0x1F4)
			if s16(s + 0x46) >= 3:
				w16(s + 0x44, u16(s + 0x44) + 1)
		2:
			w16(s + 0x32, u16(s + 0x32) - 0x1F4)
			w16(s + 0x34, u16(s + 0x34) - 0x230)
			w16(s + 0x30, u16(s + 0x30) - 0x230)
			w16(s + 0x2A, u16(s + 0x2A) + 0x1F4)
			if s16(s + 0x32) < 0x64:
				w8(s, 0xFF)
	tick_frame.encode_s16(0x170, 0)
	tick_frame.encode_s16(0x172, s16v(-((100 * int(world.rand())) >> 15) - 0x64))
	tick_frame.encode_s16(0x174, 0)
	spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x170, 0x178), 0x1000, 0,
		8, 0x1C, 2, 1, 2])


# Orladin (0x80057fc0): a puff a frame where it was (its velocity three
# rands, +-0x10), then effect_move at 0xb4 with no height and no turn; the
# tiles end it. Meeting a creature (bit 0x10) -- and it goes on through, so a
# creature it is still inside is met again -- two bursts (0x58) where it is,
# with +0 0x43, sized 0 and 0x80, and sixteen rays (0x5b) 0x4b0 above,
# flying out at 360 a frame.
# @orig game:0x80057fc0 effect_tick+0x1704  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, 126 of 126 runs; the self-test this to it
func _tick_orladin(s: int) -> void:
	var v := PackedByteArray()
	v.resize(8)
	for i in 3:
		v.encode_s16(2 * i, ((int(world.rand()) << 5) >> 15) - 0x10)
	spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v, 0x1A90, -0x3E8, 4, 0x25, 0, 1, 1])
	var hit := move(0xB4, 0, 0)
	if hit == 0:
		return
	if hit & 0xF:
		w8(s, 0xFF)
	if hit & 0x10 == 0:
		return
	var point := m.slice(s + 0x18, s + 0x28)
	spawn(0xA, 0x43, BURST, point, [null, 0, 1])
	spawn(0xA, 0x43, BURST, point, [null, 0x80, 1])     # and its sound (0x25), not here
	var x := s32(s + 0x18)
	var y := s32v(s32(s + 0x1C) + 0x4B0)
	var z := s32(s + 0x20)
	for a in range(0, 0x1000, 0x100):
		var pt := PackedByteArray()
		pt.resize(16)
		pt.encode_s32(0, x)
		pt.encode_s32(4, y)
		pt.encode_s32(8, z)
		var vr := PackedByteArray()
		vr.resize(8)
		vr.encode_s16(0, s16v((45 * coll.game_sin(a)) >> 9))
		vr.encode_s16(4, s16v((45 * coll.game_cos(a)) >> 9))
		spawn(0xA, 0, RAY, pt, [vr])


# Orladin's burst (0x80059b84, kind 0x58): growing 0x80 a frame from its
# size, striking a shell four times it -- the player too, its +0 is 0x43 --
# gone at 0x600; then fire resist's mark's tail (0x8005b5fc), turning 0x40.
# @orig game:0x80059b84 effect_tick+0x32c8  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
# @orig game:0x8005b5fc effect_tick+0x4d40  status:verified -- the turn of the tail it shares with fire resist's mark
func _tick_burst(s: int) -> void:
	grow(0x4000, 0x600, 0x80, 0x400, 0x8000)
	w16(s + 0x2A, u16(s + 0x2A) + 0x40)


# sub_80056134: a sphere growing `step` a frame, its three scales alike; it
# strikes between mult times its last size and mult times its size less
# one, `mode` and `edge`, at 0x1000; gone at `limit`.
# @orig game:0x80056134 sub_80056134  status:verified -- through orladin's burst, tools/effects.py spell_hit_check against the game's own
func grow(mult: int, limit: int, step: int, edge: int, mode: int) -> void:
	var s := current
	var v := (u16(s + 0x30) + step) & 0xFFFF
	for o in [0x30, 0x34, 0x32]:
		w16(s + o, v)
	var r := s32v(mult * s16(s + 0x30)) >> 12
	strike(point_at(s + 0x18), r - (s32v(mult * step) >> 12), r - 1, mode, edge, 0x1000)
	if s16(s + 0x30) >= limit:
		w8(s, 0xFF)


# Orladin's ray (0x8005b4b8, kind 0x5b): out by its velocity while its life
# is 10 or more, back by it and 0x200 taller after, flickering (+4 0x80 and
# 0x81). It strikes from a step ahead within its scale, mode 0x8000 -- but
# its +0 is 0, so it strikes nothing.
# @orig game:0x8005b4b8 effect_tick+0x4bfc  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_ray(s: int) -> void:
	var sign := 1 if s16(s + 0x10) >= 0xA else -1
	w32(s + 0x18, s32(s + 0x18) + sign * s16(s + 0x38))
	w32(s + 0x20, s32(s + 0x20) + sign * s16(s + 0x3C))
	if sign < 0:
		w16(s + 0x32, u16(s + 0x32) + 0x200)
	w8(s + 4, (u8(s + 0x10) & 1) - 0x80)
	strike([s32v(s32(s + 0x18) + s16(s + 0x38)), s32v(s32(s + 0x1C) + s16(s + 0x3A)),
		s32v(s32(s + 0x20) + s16(s + 0x3C)), 0], 0, s16(s + 0x30), 0x8000, 0x400, 0x1000)


# collide_wrapper_actor for an effect: the tiles alone at the radius and
# height asked, the mask.
# @orig game:0x80033d08 collide_wrapper_actor  status:verified -- through meteor's landing point, tools/effects.py spell_hit_check against the game's own (movement.query its model)
func collide_wrapper(x: int, y: int, z: int, r: int, h: int) -> int:
	if coll == null:
		return 0
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = r
	coll.body = h & 0x0FFFFFFF
	coll.flags = h & 0xF0000000
	var q := coll.query(x, y, z)
	coll.flags = 0
	coll.radius = keep_r
	coll.body = keep_b
	surface18 = int(coll.surfaces.get(0x18, 100000))
	return int(q["mask"])


# collide_surface for an effect: the nearest surface under the point, its
# layer from a flat y - 0x500 (collision.gd surface).
# @port helper -- collision.gd surface at the radius and height an effect asks with
func surface(x: int, y: int, z: int, r: int, h: int) -> int:
	if coll == null:
		return 100000
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = r
	coll.body = h
	var f := coll.surface(x, y, z)
	coll.radius = keep_r
	coll.body = keep_b
	return f


# x / 0x7fff as the compiler builds it, toward 0.
# @port helper -- the division by 0x7fff (0x80010003 and a shift of 14) as plain integer division
static func _div7fff(x: int) -> int:
	var q := absi(x) / 0x7FFF
	return -q if x < 0 else q


# The creature a hold lets go: its +0x28 bit 0x800 cleared (0x80057dd0).
# @port helper -- 0x80057dd0's write, handed to actors.gd
func release(c: int) -> void:
	var an := get_node_or_null("../Actors")
	if an and an.has_method("release"):
		an.call("release", c)


# sub_80056268: one splash on the surface the last query found, when the
# point is within `depth` under it.
# @orig game:0x80056268 sub_80056268  status:verified -- through stone and wind cutter
func _splash_one(point: int, size: int, bob: int, depth: int) -> void:
	var y := s32(point + 4)
	var surf := int(world.field("s18"))
	if y < surf or surf + depth < y:
		return
	var pt := PackedByteArray()
	pt.resize(16)
	pt.encode_s32(0, s32(point))
	pt.encode_s32(4, surf)
	pt.encode_s32(8, s32(point + 8))
	var vel := PackedByteArray()
	vel.resize(8)
	spawn(0xA, 0, SPLASH, pt, [vel, size, bob])


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
func attack_hit(code: int, flags: int, kind: int, strength: int, stat: int, pct: int, back) -> void:
	var rec: PackedByteArray = records.get(kind, PackedByteArray())
	if rec.size() < 0x16:
		return
	var att := []
	for o in [6, 8, 0xA, 0xC, 0xE, 0x10, 0x12, 0x14]:
		att.append(rec.decode_u16(o))
	var lo := code & 0xFFF0FFFF
	var point = null if back == null else Vector3i(int(back[0]), int(back[1]), int(back[2]))
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
		"vy": return (int(player.get("facing")) + int(player.get("tilt")[1])) & 0xFFFF
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
	strike(point_at(s + 0x18), 0, s16(s + 0x30) >> 3, 0x8000, 0x400, 0x1000)
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
	strike(point_at(s + 0x18), 0, s16(s + 0x30) >> 4, 0x8000, 0x400, 0x1000)
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
	strike(point_at(s + 0x18), 0, s16(s + 0x30) >> 4, 0x8000, 0x400, 0x1000)
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
	strike(point_at(s + 0x18), 0, s16(s + 0x30), 0x8000, 0x400, 0x1000)
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
# more; bit 2 the creatures (0x8004ceac, strike_creatures) with all eight, the
# caster's strength and the flags +0 & 0xc0 and 0x20. `p` the point's four
# words, the fourth the bearing mode 0x8002 turns from.
# @orig game:0x80053850 effect_strike  status:verified -- the player's half 3964 of 3964 calls handed what the game hands them; the creatures' through tools/effects.py spell_hit_check, shudom's and walwind's against the game's own
func strike(p: Array, a1: int, radius: int, mode: int, edge: int, scale: int) -> void:
	var s := current
	var rec: PackedByteArray = records.get(u8(s + 1), PackedByteArray())
	var r := func(o: int) -> int: return rec.decode_u16(o) if rec.size() >= o + 2 else 0
	if u8(s) & 1:
		world.hurt_player(Vector3i(int(p[0]), int(p[1]), int(p[2])), a1, radius,
			mode, edge & 0xFFFF, [r.call(6), r.call(8), r.call(0xA)],
			int(rec[4]) if rec.size() > 4 else 0,
			[r.call(0xC), r.call(0xE), r.call(0x10), r.call(0x12), r.call(0x14)],
			scale & 0xFFFF, u8(s + 6))
	if u8(s) & 2:
		var att := []
		for o in [6, 8, 0xA, 0xC, 0xE, 0x10, 0x12, 0x14]:
			att.append(r.call(o))
		world.strike_creatures(p, a1, radius, mode, edge & 0xFFFF, magic_strength(s) & 0xFFFF,
			att, scale & 0xFFFF, (u8(s) & 0xC0) | 0x20, u8(s + 1))


# @port helper -- a slot's point, its four words, as effect_strike is handed it
func point_at(o: int) -> Array:
	return [s32(o), s32(o + 4), s32(o + 8), s32(o + 12)]


# effect_strike's creature half handed to the creatures (actors.gd
# strike_area, 0x8004ceac); each hit's practice -- with the effect's own
# record, `kind` -- and experience to the player.
# @port helper -- the creatures' strike, from the effect to actors.gd and its leavings to the player
func strike_creatures(p: Array, near: int, radius: int, mode: int, edge: int, stat: int,
		att: Array, scale: int, flags: int, kind: int) -> void:
	var an := get_node_or_null("../Actors")
	if an == null or not an.has_method("strike_area"):
		return
	var outs: Array = an.call("strike_area", p, near, radius, mode, edge, stat, att, scale, flags)
	if player and player.has_method("spell_struck"):
		for out in outs:
			player.call("spell_struck", out, kind)


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


# effect_hurt_player: the player within the radius of the point, not nearer
# than a1, and the scale falling from `scale` to `edge` at the rim; then
# player_take_hit.
# @orig game:0x8002b114 effect_hurt_player  status:verified -- 118 of 118 strikes of bp26, scale and all; the bolts' through the same arithmetic; walwind's wave's mode 0x800 through tools/effects.py spell_hit_check
func hurt_player(p: Vector3i, a1: int, radius: int, mode: int, edge: int, attacks: Array,
		effect: int, more: Array, scale: int, pct: int) -> void:
	if player == null or not player.has_method("take_effect"):
		return
	var t := Vector3i(int(player.get("gx")), int(player.get("gy")), int(player.get("gz")))
	var hit := strike_scale(p, radius, t, edge, scale, a1, mode)
	if hit < 0:
		return
	player.call("take_effect", attacks + more, effect, hit, pct, p)


# How far the player is for effect_hurt_player, by the mode: 0x8000
# in_range_3d to the player's middle (0x6a4 / 2 up, radius 0x320); 0x8001 the
# same, a point above the player's top missing; any other in_range
# (0x8002b8d8) with the player's height and the mode as the asker's. Then the
# falloff: -1 a miss, else the scale handed on.
# @orig game:0x8002b1a4 effect_hurt_player+0x90  status:verified -- the distance by the mode; 118 strikes of bp26 (0x8000), walwind's wave (0x800) through tools/effects.py spell_hit_check
# @orig game:0x8002b8d8 sub_8002b8d8  status:verified -- in_range from the player, its height 0x6a4; through spell_hit_check
func strike_scale(p: Vector3i, radius: int, t: Vector3i, edge := EDGE, scale := 0x1000,
		near := 0, mode := 0x8000) -> int:
	var d: int
	if mode == 0x8001 and p.y < t.y - BODY:
		d = KFCollision.FAR
	elif mode == 0x8000 or mode == 0x8001:
		d = coll.in_range_3d(p, radius, t, OWN, BODY)
	else:
		d = coll.in_range(t.x, t.y, t.z, p.x, p.y, p.z, radius, BODY, mode)
		if d == -1:
			d = KFCollision.FAR
	return KFDamage.falloff(d, near, radius, edge, scale)


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

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
const FIRE_STORM := 0x02
const FLAME := 0x04
const BREATH := 0x6E               # flame's: the empty arm
# The weapons' spells whose arms are here: ryu-ga's is wind cutter's two arms,
# anorium sword's the fire ball's with its own particle
const RYU_GA := 0x38
const CAPRICORN := 0x3A
const ANORIUM := 0x3E
const VACULACIA := 0x40
const SEATHS := 0x42
const MORGULINE := 0x4C
# and the rest: the excellector's two (one tick), 0x3c (no weapon's), triple
# fang's two (the second flash's arms), 0x4b (the second moonlight sword's
# second), the moonlight swords' marks with their pillars and bursts, dark
# slayer's two with their spheres, and 0x4b's sparks
const EXCEL1 := 0x36
const EXCEL2 := 0x37
const FALLER := 0x3C
const FANG := 0x46
const FLASH := 0x47                # and 0x14, flash itself, and 0x12
const MOON := 0x4B
const MARK := 0x78
const MARK2 := 0x7A
const PILLAR := 0x5C
const PILLAR2 := 0x5D
const MOON_BURST := 0x48
const SLAYER2 := 0x7C
const SLAYER := 0x7B
const SPHERE2 := 0x44
const SPHERE := 0x45
const SPARK := 0x03
const LIGHTNING := 0x71            # the creatures' 0x7d and 0x81; bolts 0x72, 0x7e, 0x80; spheres 0x13, 0x29, 0x2d
const BANK_KEY := 0x20000          # KFAnim's key for model_table[index] of the resident bank
const EMPTY := [0x08, 0x0A, 0x0E, 0x18, 0x1D, 0x2B, 0x39, 0x3B, 0x3D, 0x3F, 0x41, 0x43, 0x49,
	0x4A, 0x4D, 0x4E, 0x4F, 0x54, 0x57, 0x60, 0x61, 0x62, 0x63, 0x68, 0x69, 0x6A, 0x6B, 0x6D,
	0x6E, 0x73, 0x75, 0x76, 0x77, 0x79, 0x7F]   # effect_spawn's arm 0x80055b18: set up, freed
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
var collide_mask := 0               # 0x801e6488: what the last query answered
var tick_frame := PackedByteArray()  # effect_tick's stack frame (0x2b8): what one arm leaves the next
var surface18 := 100000             # 0x801e647c: the water the last query found
var collision_surface := 100000     # 0x801e6474: the nearest surface the last tile query found
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

# The stack arguments a call effect_tick makes leaves in its frame from
# sp+0x10: the next call that hands fewer and reads more takes them -- flash's
# second burst (0x80059c90) takes five. A pointer is laid as 0: no reader
# takes one. In the game the rest of its frame -- the code that runs between
# two passes of effect_driver -- can write there too; here only the effects do.
# @port helper -- the outgoing words of effect_tick's frame, kept in tick_frame
func out_words(words: Array) -> void:
	for i in words.size():
		tick_frame.encode_u32(0x10 + 4 * i, int(words[i]) & 0xFFFFFFFF)


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
# `direct`: called by effect_tick itself, which leaves the stack words in its
# frame (out_words).
# @orig game:0x80053c84 effect_spawn  status:partial -- the common setting up and the arms of 58 kinds: 0 (fire ball), 1 (fire wall), 2 (fire storm), 3 (a spark), 4 (flame), 6 (stone), 7 and 0x16 (earth wave), 9 (shudom), 0xb (haze), 0xc (bortecth), 0xd (wind cutter), 0xf (tornado), 0x11 (walwind), 0x12 and 0x14 (flash), 0x15 (orladin), 0x17, 0x19, 0x1a, 0x1b, 0x1c, 0x1e (the healing and protecting), 0x1f, 0x22, 0x23, 0x24, 0x26 (the creatures'), 0x44, 0x45, 0x48, 0x58, 0x59, 0x5a, 0x5b, 0x5c, 0x5d, 0x5e, 0x5f, 0x65 (the spells' children), 0x6f (puff), 0x70 (splash), and 0x36, 0x37, 0x38, 0x3a, 0x3c, 0x3e, 0x40, 0x42, 0x46, 0x47, 0x4b, 0x4c, 0x78, 0x7a, 0x7b and 0x7c (the weapons' spells); tools/effects.py's, which the game's own holds (machine_check, magic_check, fire_check, spell_hit_check) and the self-test holds this to. 35 kinds have the empty arm, which frees the slot, as here; the other 37 arms are not here
func spawn(a0: int, a1: int, kind: int, point: PackedByteArray, args: Array,
		direct := false) -> int:
	if direct:
		var words := []
		for v in args:
			words.append(int(v) if typeof(v) == TYPE_INT else 0)
		out_words(words)
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
	if kind >= 0x82 or kind in EMPTY:
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
		WIND_CUTTER, RYU_GA:                # 0x800544b8
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
		FLAME:                              # 0x80054dd4
			w8(s + 8, 1)
			w8(s + 9, 5)
			w8(s + 2, 0x29)
			w8(s + 3, 0x29)
			w8(s + 0xC, 0x34)
			w16(s + 0x12, 0x1000)
			w8(s + 4, 0)
			for o in [0x34, 0x32, 0x30]:
				w16(s + o, 0xBB8)
			put(s + 0x28, (args[1] as PackedByteArray).slice(0, 8))   # the view's angles, pitch too
			w16(s + 0x10, 0x96)
			w8(s + 0x45, 0)
			w16(s + 0xE, 0x80)              # and its sound (0x90), not here
		FIRE_STORM:                         # 0x800540b8
			particle(s, 9, 0x1B58, 5)
			for o in [0x38, 0x3A, 0x3C]:
				w16(s + o, u16(s + o) - 0x40 + (int(world.rand()) >> 8))
			w16(s + 0x10, 0x50)
			w8(s + 0xB, 3)
			w16(s + 0xE, 0x40)
			w8(s + 0x44, int(args[1]))      # its creature: the slot, 0xfe the player, 0xff none
			# and the last of a cast's three (args[2] 2), its sound (0x2d), not here
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
		FIRE_BALL, ANORIUM:                 # 0x80053e98, anorium's 0x80053e8c
			particle(s, 9 if kind == FIRE_BALL else 0x3B, 0x1000, 5)
			w16(s + 0xE, 0x40)
			w16(s + 0x10, 0x32)             # sub_800532d4's sound between, not here
			w8(s + 0xD, 1)
		CAPRICORN:                          # 0x800543b4
			particle(s, 0xA, 0xC00, 5)
			w16(s + 0x10, 0x32)
			w8(s + 0xD, 1)
			w16(s + 0xE, 0x40)              # with its sound (0x64), not here
		SEATHS:                             # 0x80054940
			_spawn_seaths(s)
		MORGULINE:                          # 0x8005422c
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 2, 0xF)
			w8(s + 3, 0xF)
			w16(s + 0x10, 0x50)
			w16(s + 0xE, 0x80)              # with its sound (0x36), not here
		VACULACIA:                          # 0x8005474c
			particle(s, 0x43, 0x1400, 5)
			w16(s + 0x10, 0x46)
			w8(s + 0x44, 0)
			w8(s + 0xD, 0)
			w16(s + 0xE, 0)                 # with its sound (0x67), not here
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
		EXCEL1:                             # 0x80054538, its size by its place in the cast
			setup(s, 0x3D, 0x1000, 5)
			var n := int(args[1])
			w16(s + 0x30, (n << 10) + 0x1800)
			w16(s + 0x34, (n << 10) + 0x1800)
			w16(s + 0x10, 0x28)
			w8(s + 0x44, 0)
			w8(s + 0xD, 0)
			w16(s + 0x32, (n << 10) + 0xC00)
			put(s + 0x28, _view())
			w16(s + 0xE, 0x40)
		EXCEL2:                             # 0x800545c4
			setup(s, 0x39, 0x1B58, 5)
			w16(s + 0x10, 0x30)
			w8(s + 0x44, 0)
			w8(s + 0xD, 0)
			w16(s + 0xE, 0x40)
			_face(s)
			w16(s + 0x2C, 0)                # with its sound (0x63), not here
		FALLER:                             # 0x8005477c
			setup(s, 0x1E, 0x64, 0)
			w16(s + 0x32, 0x800)
			w16(s + 0x30, 0x64)
			w16(s + 0x34, 0x64)
			w16(s + 0x10, 0x2D)
			put(s + 0x28, _view())
			w16(s + 0x3A, -0x1E)
			w16(s + 0x28, 0)
			w16(s + 0x2C, 0)
			w8(s + 0xB, 5)
			w16(s + 0xE, 0)
			w16(s + 0x44, 0)
			w32(s + 0x1C, s32(s + 0x1C) - 0xC8)
		FANG:                               # 0x80054690
			setup(s, 0x3F, 0x800, 5)
			w16(s + 0x34, 0xC00)
			w16(s + 0x10, 0x3C)
			w8(s + 0xD, 1)
			w8(s + 0xB, 3)
			put(s + 0x28, _view())
			w16(s + 0x44, 0)
			w16(s + 0xE, 0x100)
			w16(s + 0x46, int(args[1]))     # with its sound (0x2d), not here
		FLASH, 0x14, 0x12:                  # 0x80055424; 0x12 at 0x80055414
			_spawn_flash(s, kind, args)
		MOON:                               # 0x80054188
			setup(s, 0x44, 0x1400, 5)
			put(s + 0x28, _view())
			w8(s + 0xD, 1)
			w16(s + 0x10, 0x64)
			w8(s + 0xB, 5)
			w8(s + 0x44, 0)
			w16(s + 0xE, 0)                 # with its sound (0x66), not here
		SPARK:                              # 0x8005415c
			particle(s, 0x45, 0x1000, 5)
			w16(s + 0x10, 0xC)
			w16(s + 0x32, 0)
			w16(s + 0xE, 0x40)
		MARK, MARK2:                        # 0x80055524
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 9, 5)
			w8(s + 2, 0x3A)
			w8(s + 3, 0x3A)
			w8(s + 0xC, 0x34)
			w16(s + 0x12, 0x1000)
			w16(s + 0x10, 0x2D)
			put(s + 0x28, (args[1] as PackedByteArray).slice(0, 8))
			w16(s + 0x30, 0x1800)
			w16(s + 0x32, 0xA00)
			w16(s + 0x34, 0xC00)
			w16(s + 0xE, 0)                 # with its sound (0x66), not here
		PILLAR, PILLAR2:                    # 0x800555b4, 0x800555e8
			particle(s, 0xB, 0x1800, 5)
			w16(s + 0x32, 0)
			w8(s + 0x44, 0)
			w16(s + 0x3A, 0)
			w16(s + 0xE, 0x40 if kind == PILLAR else 0)
			w8(s + 0x45, int(args[1]))      # the mark's slot
		MOON_BURST:                         # 0x800554d0
			_from_nothing(s, 0x40)
			w8(s + 0x44, int(args[1]))      # the frames it waits
		SPHERE2, SPHERE:                    # 0x80055618
			_from_nothing(s, 0xC0)
			w16(s + 0x44, int(args[1]))     # how large it grows
		SLAYER2:                            # 0x8005566c
			w8(s + 8, 1)
			w8(s + 4, 0x80)
			w8(s + 9, 5)
			w8(s + 2, 0x20)
			w8(s + 3, 0x20)
			w8(s + 0xC, 0x34)
			w16(s + 0x12, 0x1000)
			w16(s + 0x10, 0x32)
			put(s + 0x28, _view())
			w16(s + 0x32, 0x2000)
			w16(s + 0x30, 0x15E)
			w16(s + 0x34, 0x15E)
			w16(s + 0x28, 0)
			w16(s + 0x2C, 0)
			w16(s + 0x3A, 0)
			w16(s + 0xE, 0x40)
			w32(s + 0x1C, s32(s + 0x1C) + 0x960)   # with its sound (0x65), not here
		SLAYER:                             # 0x80055718: not drawn
			w8(s + 8, 0)
			w16(s + 0x10, 0x14)             # with its sound (0x65), not here
		LIGHTNING, 0x7D, 0x81:              # 0x80055290, 0x80055258, 0x80055274
			particle(s, 0xA, 0x800 if kind == LIGHTNING else 0x1000, 5)
			w16(s + 0xE, 0x40 if kind == LIGHTNING else (0 if kind == 0x7D else 0xC0))
			w16(s + 0x10, 0x64)
			w16(s + 0x44, int(args[1]))     # the frames it flies level; its sound (0x2e), not here
		0x72, 0x7E, 0x80:                   # 0x800552d0, a bolt
			particle(s, 0xB, 0x1000, 5)
			w16(s + 0xE, 0x40)
			w16(s + 0x10, 0xC)
			w16(s + 0x32, int(args[1]))     # as high as the lightning fell
		0x13, 0x29, 0x2D:                   # 0x80055328, 0x80055300, 0x80055314: a bolt's sphere
			w8(s + 2, 0x15)
			w8(s + 3, 0x15)
			w16(s + 0xE, 0x40 if kind == 0x13 else (0xC0 if kind == 0x29 else 0))
			_from_nothing(s, u16(s + 0xE))
			for o in [0x2C, 0x2A, 0x28]:
				w16(s + o, 0)
			w16(s + 0x44, _trunc(int(args[1]), 4))   # and its sound (0x26), not here
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


# Seath's sword's spell (0x80054940): after its sound (0x62 with +0 & 0x40,
# else 0x2c, not here) set up as model 0x2d, scale 0x1000 and +0x34 0x1400, a
# life of 0x32, and the angles off the velocity as _aimed has them.
# @orig game:0x80054940 effect_spawn+0xcbc  status:verified -- tools/effects.py spell_hit_check and fire_check, 126 of 126 and 168 of 168 runs of the game's own; the self-test this to it
func _spawn_seaths(s: int) -> void:
	setup(s, 0x2D, 0x1000, 5)
	var vx := s16(s + 0x38)
	var vz := s16(s + 0x3C)
	w16(s + 0x34, 0x1400)
	w16(s + 0x10, 0x32)
	w8(s + 0x44, 0)
	w8(s + 0xD, 1)
	var ln := coll.isqrt(s32v((vx >> 3) * (vx >> 3) + (vz >> 3) * (vz >> 3)) & 0xFFFFFFFF) << 3
	w16(s + 0x28, coll.ratan2(s16(s + 0x3A), ln))
	w16(s + 0x2C, 0)
	w16(s + 0x2A, coll.ratan2(s16(s + 0x3C), s16(s + 0x38)) - 0x400)
	w16(s + 0xE, 0x40)


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
# @orig game:0x800568bc effect_tick  status:partial -- the switch, and the arms of the same 58 kinds as effect_spawn's, and 0x31's (the excellector's); the other 36 do nothing here
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
		FIRE_BALL, ANORIUM:
			_tick_fire(s)
		CAPRICORN:
			_tick_capricorn(s)
		SEATHS:
			_tick_seaths(s)
		MORGULINE:
			_tick_morguline(s)
		VACULACIA:
			_tick_vaculacia(s)
		SPLASH:
			_tick_splash(s)
		STONE:
			_tick_stone(s)
		WIND_CUTTER, RYU_GA:
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
		FIRE_STORM:
			_tick_fire_storm(s)
		FLAME:
			_tick_flame(s)
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
		EXCEL1, EXCEL2, 0x31:
			_tick_excellector(s)
		FALLER:
			_tick_faller(s)
		FANG:
			_tick_fang(s)
		FLASH, 0x14, 0x12:
			_tick_flash(s)
		MOON:
			_tick_moon(s)
		SPARK:
			_tick_spark(s)
		MARK:
			_tick_mark(s)
		MARK2:
			_tick_mark2(s)
		PILLAR, PILLAR2:
			_tick_pillar(s)
		MOON_BURST:
			_tick_moon_burst(s)
		SPHERE2, SPHERE:
			_tick_sphere(s)
		SLAYER2:
			_tick_slayer2(s)
		SLAYER:
			_tick_slayer(s)
		LIGHTNING, 0x7D, 0x81:
			_tick_lightning(s)
		0x72, 0x7E, 0x80:
			_tick_bolt_of(s)
		0x13, 0x29, 0x2D:
			_tick_bolt_sphere(s)


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


# Capricorn's spell (0x80057f78): +0xe flips 0x40 every frame; effect_move at
# radius 0xb4, no height, turning 0x258 a frame; what it meets it strikes and
# is gone (freed first when the tiles stopped it).
# @orig game:0x80057f78 effect_tick+0x16bc  status:verified -- tools/effects.py spell_hit_check, 126 of 126 runs of the game's own end to end; the self-test this to it
func _tick_capricorn(s: int) -> void:
	w16(s + 0xE, (u16(s + 0xE) + 0x40) & 0x40)
	var hit := move(0xB4, 0, -0x258)
	if hit == 0:
		return
	if hit & 0xF:
		w8(s, 0xFF)
	_attack(s, hit)
	w8(s, 0xFF)


# Seath's sword's spell (0x80058a00): effect_move at radius 0x64, height 0xc8;
# in flight a splash on water just under it, and what it meets it strikes and
# is gone.
# @orig game:0x80058a00 effect_tick+0x2144  status:verified -- tools/effects.py spell_hit_check and fire_check (the splash, the world stood in for), 126 of 126 and 168 of 168 runs of the game's own; the self-test this to it
func _tick_seaths(s: int) -> void:
	var hit := move(0x64, 0xC8, 0)
	if hit == 0:
		_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
		return
	_attack(s, hit)
	w8(s, 0xFF)


# Morguline axe's spell (0x8005758c): turning 0xc8 a frame on two axes,
# falling 5 a frame faster, a still puff at its point (0xc00, -0x100, 8,
# 0x1c, 0, 1, 2), then effect_move at radius 0xb4, the height's top bit: what
# it meets it strikes and is gone.
# @orig game:0x8005758c effect_tick+0xcd0  status:verified -- tools/effects.py spell_hit_check, 126 of 126 runs of the game's own end to end (none reached a creature); the self-test this to it
func _tick_morguline(s: int) -> void:
	w16(s + 0x2A, u16(s + 0x2A) + 0xC8)
	w16(s + 0x3A, u16(s + 0x3A) + 5)
	w16(s + 0x28, u16(s + 0x28) + 0xC8)
	var v := PackedByteArray()
	v.resize(8)
	spawn(10, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v, 0xC00, -0x100, 8, 0x1C, 0, 1, 2], true)
	var hit := move(0xB4, 0x80000000, 0)
	if hit != 0:
		w8(s, 0xFF)
		_attack(s, hit)


# Vaculacia sword's spell (0x8005763c): effect_move at radius 0xb4, the
# height's top bit, turning 0x1f4 a frame; what it meets it strikes and is
# gone in sixteen puffs flung from its point, each axis rand() * 500 >> 15
# less 0xfa (0x1400, -0x18, 0xa, 0x26, 0, 1, 2).
# @orig game:0x8005763c effect_tick+0xd80  status:verified -- tools/effects.py spell_hit_check, 126 of 126 runs of the game's own end to end; the self-test this to it
func _tick_vaculacia(s: int) -> void:
	var hit := move(0xB4, 0x80000000, -0x1F4)
	if hit == 0:
		return
	w8(s, 0xFF)
	_attack(s, hit)
	for k in 16:
		var v := PackedByteArray()
		v.resize(8)
		for i in 3:
			v.encode_s16(2 * i, ((500 * int(world.rand())) >> 15) - 0xFA)
		spawn(10, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v, 0x1400, -0x18, 0xA, 0x26, 0, 1, 2], true)


# --- the weapons' other spells ----------------------------------------------

# The view's angles as an arm copies them (view_angles, 8 bytes): the pitch,
# the yaw, the roll 0.
# @port helper -- view_angles from the world's fields
func _view() -> PackedByteArray:
	var b := PackedByteArray()
	b.resize(8)
	b.encode_s16(0, int(world.field("vp")))
	b.encode_s16(2, int(world.field("vy")))
	return b


# +0x28 the pitch and +0x2a the yaw of the velocity, the yaw a quarter back --
# ratan2(vy, vec_length_2d(vx, vz)), ratan2(vz, vx) - 0x400.
# @port helper -- the aim along the velocity, as _aimed and _spawn_seaths have it, for the arms below
func _face(s: int) -> void:
	var vx := s16(s + 0x38)
	var vz := s16(s + 0x3C)
	var ln := coll.isqrt(s32v((vx >> 3) * (vx >> 3) + (vz >> 3) * (vz >> 3)) & 0xFFFFFFFF) << 3
	w16(s + 0x28, coll.ratan2(s16(s + 0x3A), ln))
	w16(s + 0x2A, coll.ratan2(vz, vx) - 0x400)


# What the arms of 0x48 and 0x44/0x45 share (0x800554d0, 0x80055618): model
# 0x15 from nothing, mode 0x34; +0xe `e`.
# @orig game:0x800554d0 effect_spawn+0x184c  status:verified -- 0x48's arm; 0x44's and 0x45's (0x80055618) the same but +0xe 0xc0 and +0x44 a halfword; tools/effects.py spell_hit_check, the moonlight swords' and dark slayer's against the game's own; the self-test this to it
func _from_nothing(s: int, e: int) -> void:
	w8(s + 8, 1)
	w8(s + 4, 0x80)
	w8(s + 9, 5)
	w8(s + 2, 0x15)
	w8(s + 3, 0x15)
	w8(s + 0xC, 0x34)
	w16(s + 0x12, 0x1000)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, 0)
	w16(s + 0xE, e)


# Flash's arm (0x80055424; 0x12's at 0x80055414): model 0x23, mode 0x39, the
# angles args[1] points at; the homing's four numbers out of args[2..5] -- the
# most, the pull, the turn, the pull up close -- and the life out of args[6].
# 0x12 has three frames' grace and +0xe 0x140.
# @orig game:0x80055414 effect_spawn+0x1790  status:verified -- 0x12's head, then the arm of 0x14 and 0x47 (0x80055424); tools/effects.py spell_hit_check, flash's and triple fang's second against the game's own; the self-test this to it
func _spawn_flash(s: int, kind: int, args: Array) -> void:
	if kind == 0x12:
		w8(s + 0xB, 3)
		w16(s + 0xE, 0x140)
	else:
		w16(s + 0xE, 0x100)
	w8(s + 8, 1)
	w8(s + 9, 5)
	w8(s + 4, 0x80)
	w8(s + 2, 0x23)
	w8(s + 3, 0x23)
	w8(s + 0xC, 0x39)
	w16(s + 0x12, 0x1000)
	put(s + 0x28, (args[1] as PackedByteArray).slice(0, 8))
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, 0x1000)
	var at := [0x44, 0x46, 0x48, 0x4A, 0x10]
	for i in 5:
		w16(s + int(at[i]), int(args[2 + i]) if args.size() > 2 + i else 0)


# Both of the excellector's spells (0x80057aa8, and 0x31): effect_move at
# radius 0xb4, the height's top bit; the tiles end it. Each thing it meets it
# strikes once (+0x44 the latch, cleared on a clear frame), in seven puffs
# flung from its point, each axis rand() * 240 >> 15 less 0x78 (0x1400, 0, 7,
# 0xc, 0, 1, 1). A splash a frame on water just under it.
# @orig game:0x80057aa8 effect_tick+0x11ec  status:verified -- tools/effects.py spell_hit_check, the excellector's two against the game's own end to end; the self-test this to it
func _tick_excellector(s: int) -> void:
	var hit := move(0xB4, 0x80000000, 0)
	if hit == 0:
		w8(s + 0x44, 0)
	else:
		if hit & 0xF:
			w8(s, 0xFF)
		if u8(s + 0x44) == 0:
			w8(s + 0x44, 1)
			_attack(s, hit)
			for _k in 7:
				for i in 3:
					tick_frame.encode_s16(0xA0 + 2 * i, ((240 * int(world.rand())) >> 15) - 0x78)
				spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0xA0, 0xA8),
					0x1400, 0, 7, 0xC, 0, 1, 1], true)
	_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)


# 0x3c, no weapon's (0x80057ba8): falling 5 a frame faster until effect_move
# (0xb4, the height's top bit) meets something; then spreading 0x100 a frame
# across, gone past 0x1000. It strikes nothing.
# @orig game:0x80057ba8 effect_tick+0x12ec  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_faller(s: int) -> void:
	var n := s16(s + 0x44)
	if n == 0:
		if move(0xB4, 0x80000000, 0) != 0:
			w16(s + 0x44, u16(s + 0x44) + 1)
		w16(s + 0x3A, u16(s + 0x3A) + 5)
	elif n == 1:
		w16(s + 0x30, u16(s + 0x30) + 0x100)
		w16(s + 0x34, u16(s + 0x34) + 0x100)
		if s16(s + 0x30) >= 0x1001:
			w8(s, 0xFF)


# Triple fang's first (0x8005773c): rolling 0x190 a frame, aimed along its
# velocity. At a life of 0x2d -- fifteen frames out -- the cast's (+0x46 0)
# splits: two more (+0x46 1) at its point, the velocity turned an eighth either
# way. Then effect_move (0xb4, the height's top bit): what it meets it strikes,
# and it becomes a burst (0x58, 0x28 frames from nothing) with another beside
# it (+0 3, 0x80 across, the player struck too); else a puff behind it.
# @orig game:0x8005773c effect_tick+0xe80  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, the splits and the bursts among it; the self-test this to it
func _tick_fang(s: int) -> void:
	w16(s + 0x2C, u16(s + 0x2C) + 0x190)
	_face(s)
	if s16(s + 0x10) == 0x2D and s16(s + 0x46) == 0:
		var vx := s16(s + 0x38)
		var vy := s16(s + 0x3A)
		var vz := s16(s + 0x3C)
		for xz in [[(vx - vz + vx) >> 1, (vx + vz + vz) >> 1], [(vz + vx + vx) >> 1, (vz - vx + vz) >> 1]]:
			tick_frame.encode_s16(0xD8, s16v(int(xz[0])))
			tick_frame.encode_s16(0xDA, vy)
			tick_frame.encode_s16(0xDC, s16v(int(xz[1])))
			spawn(0xA, 0x43, FANG, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0xD8, 0xE0), 1], true)
	var hit := move(0xB4, 0x80000000, 0)
	if hit != 0:
		_attack(s, hit)
		w8(s + 1, BURST)
		w8(s + 8, 1)
		w8(s + 9, 5)
		w8(s + 2, 0x15)
		w8(s + 3, 0x15)
		w8(s + 0xC, 0x34)
		w16(s + 0x12, 0x1000)
		w16(s + 0x10, 0x28)
		w8(s + 4, 0)
		for o in [0x30, 0x32, 0x34, 0x28, 0x2A, 0x2C]:
			w16(s + o, 0)
		w16(s + 0xE, 0x40)                  # and the sound (0x28), not here
		spawn(0xA, 3, BURST, m.slice(s + 0x18, s + 0x28), [null, 0x80, 1], true)
		return
	for i in 3:
		tick_frame.encode_s16(0xD8 + 2 * i, ((20 * int(world.rand())) >> 15) - 0xA)
	spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0xD8, 0xE0), 0x1000,
		-0x280, 5, 0xC, 0, 1, 0], true)


# Flash, triple fang's second and 0x12 (0x80059ba8), by +7. Under 0x64 it
# homes (seek), counting up -- in flight a splash on water under it, rolling
# 0x80 a frame and a still puff behind it. Meeting something, or at 0x64,
# another of its kind where it is -- +0 | 3, handed its angles and the stack's
# last five words for the rest, +7 0x65, so it would burst two frames on --
# and it bursts: model 0x15, +7 0x6e, +0 | 3 (the player struck too), growing
# from nothing 0x46 a frame. The second one's life is the stack's word at
# sp+0x28, which the puff in flight leaves 1: it is freed before it bursts.
# @orig game:0x80059ba8 effect_tick+0x32ec  status:partial -- tools/effects.py spell_hit_check against the game's own end to end, flash and triple fang's second; the second one's numbers are effect_tick's stack leftovers, which here only the effects write (out_words); the sounds not here
func _tick_flash(s: int) -> void:
	var kind := u8(s + 1)
	var ph := u8(s + 7)
	if ph == 0x65:
		w8(s + 7, 0x66)
		return
	if ph == 0x6E:
		_flash_grow(s, kind)
		return
	if ph != 0x66:
		if ph != 0x64:
			if ph == 0:
				out_words([0x7148, 0])      # its sound's (0x2c) two words
			w8(s + 7, ph + 1)
			var r := seek(s16(s + 0x44), s16(s + 0x46), s16(s + 0x48), 0xA0, 0, 0x1770,
				s16(s + 0x4A), 0x800)
			if r != -1:
				_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
				w16(s + 0x2C, u16(s + 0x2C) + 0x80)
				for i in 3:
					tick_frame.encode_s16(0x170 + 2 * i, 0)
				spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x170, 0x178),
					0xE10, -0x80, 3, 0x25, 0, 1, 0 if kind == 0x12 else 1], true)
				return
		var args := [null, m.slice(s + 0x28, s + 0x30)]
		for i in 5:
			args.append(tick_frame.decode_u32(0x18 + 4 * i))
		var c := spawn(0xA, u8(s) | 3, kind, m.slice(s + 0x18, s + 0x28), args, true)
		if c >= 0:
			w8(c + 7, 0x65)                 # the game's writes address 7 when no slot was free
	w8(s + 3, 0x15)
	w8(s + 7, 0x6E)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, 0)
	w16(s + 0xE, 0x40)
	w8(s, u8(s) | 3)                        # and the sound (0x28), not here
	_flash_grow(s, kind)


# Flash's burst (0x80059be0): 0x12 drawn plain (+0xe 0); effect_grow(0x2000,
# 0x31f, 0x46, 0xc00, 0x8000), then the mark's tail, a turn of 0x40.
# @orig game:0x80059be0 effect_tick+0x3324  status:verified -- through flash, the same runs
func _flash_grow(s: int, kind: int) -> void:
	if kind == 0x12:
		w16(s + 0xE, 0)
	out_words([0x8000])
	grow(0x2000, 0x31F, 0x46, 0xC00, 0x8000)
	w16(s + 0x2A, u16(s + 0x2A) + 0x40)


# effect_seek: a player's effect (+0 & 0x40) turns its angles towards the
# creature sub_8004d3c4 finds along them (0x5dc0, the cones, no noise) -- its
# middle -- by `turn` each (angle_approach), and is steered along them
# (effect_steer: `accel`, `near_accel` once the creature is within `near`; at
# most `most`). -1 when the move met something.
# @orig game:0x80055db0 effect_seek  status:partial -- the player's effects', through flash and the second moonlight sword's, tools/effects.py spell_hit_check against the game's own; the others' (sub_8002b80c, the player in sight) not read: they seek nothing here
func seek(most: int, accel: int, turn: int, radius: int, height: int, near: int,
		near_accel: int, cone: int) -> int:
	var s := current
	out_words([height, near, near_accel, cone])
	var dist := -1
	if u8(s) & 0x40:
		var p := [s32(s + 0x18), s32(s + 0x1C), s32(s + 0x20)]
		var r: Array = world.sight(p, s16(s + 0x2A), s16(s + 0x28), 0x5DC0, cone, cone, 0)
		dist = int(r[1])
		if int(r[0]) != -1:
			var t: Array = world.actor_mid(int(r[0]))
			var ang := vec_to_angles(s32v(int(t[0]) - int(p[0])), s32v(int(t[1]) - int(p[1])),
				s32v(int(t[2]) - int(p[2])))
			turn = s16v(turn)
			w16(s + 0x28, LOOT.approach_angle(s16(s + 0x28), s16v(int(ang[0])), turn))
			w16(s + 0x2A, LOOT.approach_angle(s16(s + 0x2A), s16v(int(ang[1])), turn))
	var d := coll.direction_from_angles(s16(s + 0x28), s16(s + 0x2A))
	if dist >= 0 and not near < dist:
		accel = near_accel
	return steer(accel, most, radius, height, [s16v(d[0]), s16v(d[1]), s16v(d[2])])


# The second moonlight sword's second (0x80056c7c): aimed along its velocity,
# rolling 0xc8 a frame; effect_move at 0xb4, no height. Meeting something: a
# creature or an object (no tile bit) struck; gone in three bursts (0x58, +0
# 3, 0, 0x40 and 0x80 across). Every frame a splash on water under it, and on
# every third of its life a spark (3) where it is.
# @orig game:0x80056c7c effect_tick+0x3c0  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_moon(s: int) -> void:
	_face(s)
	w16(s + 0x2C, u16(s + 0x2C) + 0xC8)
	var hit := move(0xB4, 0, 0)
	if hit != 0:
		if hit & 0xF == 0:
			_attack(s, hit)
		w8(s, 0xFF)                         # and the sound (0x27), not here
		for size in [0, 0x40, 0x80]:
			spawn(0xA, 3, BURST, m.slice(s + 0x18, s + 0x28), [null, size, 2], true)
	_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)
	for i in 3:
		tick_frame.encode_s16(0x68 + 2 * i, 0)
	var life := s16(s + 0x10)
	if (life - 3 * (life / 3)) & 0xFFFF == 0:
		spawn(0xA, 0, SPARK, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x68, 0x70)], true)


# A spark (0x8005699c): 0x4b0 taller a frame, flickering -- +4 0x80 or 0x81
# and +0xe 0 or 0x40 by its life's last bit (the remainder's sign kept).
# @orig game:0x8005699c effect_tick+0xe0  status:verified -- through the second moonlight sword's second, tools/effects.py spell_hit_check
func _tick_spark(s: int) -> void:
	w16(s + 0x32, u16(s + 0x32) + 0x4B0)
	var life := s16(s + 0x10)
	w8(s + 4, (u8(s + 0x10) & 1) - 0x80)
	w16(s + 0xE, (life - 2 * (life / 2)) << 6)


# A moonlight sword's end: three bursts (0x48) where it is, +0 | 3, a frame
# apart; gone.
# @orig game:0x800585a8 effect_tick+0x1cec  status:verified -- the first sword's, the second's (0x80058500) the same after the move taken back; through spell_hit_check
func _moon_burst(s: int) -> void:
	for i in 3:
		spawn(0xA, u8(s) | 3, MOON_BURST, m.slice(s + 0x18, s + 0x28), [null, i], true)
	w8(s, 0xFF)                             # with the sound (0x27), not here


# The first moonlight sword's mark (0x8005857c): effect_move at 0xb4, 0x168
# high; meeting something, or with a frame left, three bursts; else a splash
# on water under it.
# @orig game:0x8005857c effect_tick+0x1cc0  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, its pillars among it; the self-test this to it
func _tick_mark(s: int) -> void:
	if move(0xB4, 0x168, 0) != 0 or s16(s + 0x10) < 2:
		_moon_burst(s)
		return
	_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)


# The second moonlight sword's mark (0x800584a4): homing (seek: 0x258 at most,
# pulled 0x28 -- 0x104 within 0x1000 -- turning 0x24, radius 0xb4, 0x168 high,
# cones 0x800); meeting something, or with a frame left, the move taken back
# and three bursts; else a splash on water under it.
# @orig game:0x800584a4 effect_tick+0x1be8  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_mark2(s: int) -> void:
	var r := seek(0x258, 0x28, 0x24, 0xB4, 0x168, 0x1000, 0x104, 0x800)
	if r == -1 or s16(s + 0x10) < 2:
		undo(s)
		_moon_burst(s)
		return
	_splash_one(s + 0x18, 0x2000, 0x2000, 0x1F4)


# A mark's pillar (0x80058624, 0x5c and 0x5d): following on the ground under
# its mark, across by its velocity. While the mark lives (+0x44 0) it strikes
# what stands in it (no tiles: radius 0xa, its height), stands on the floor
# under the mark's height (collide_surface) and is half as high as the room
# there, 0x4000 at most; once the mark is gone (+0x44 1) it shrinks from that
# height to nothing in eight frames (fixed_madd, 0x200 a frame), then goes.
# @orig game:0x80058624 effect_tick+0x1d68  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, both phases; the self-test this to it
func _tick_pillar(s: int) -> void:
	w32(s + 0x18, s32(s + 0x18) + s16(s + 0x38))
	w32(s + 0x20, s32(s + 0x20) + s16(s + 0x3C))
	var k := u8(s + 0x45)
	var parent := STRIDE * (k - 0x100 if k >= 0x80 else k)
	var ph := u8(s + 0x44)
	if ph == 0:
		var x := s32(s + 0x18)
		var z := s32(s + 0x20)
		out_words([s16(s + 0x32), 0x30])
		var mask: int = world.collide_query(x, s32(s + 0x1C), z, 0xA, s16(s + 0x32), 0x30)
		_attack(s, mask)
		out_words([0])
		var sc: Array = world.surface_ceiling(x, s32(parent + 0x1C) if parent >= 0 else 0, z, 0, 0)
		w32(s + 0x1C, int(sc[0]))
		var d := s32v(int(sc[0]) - int(sc[1]))
		w16(s + 0x32, 0x4000 if 0x7FFF < d else d >> 1)
		if parent < 0 or u8(parent) == 0xFF:
			w8(s + 0x44, 1)
			w16(s + 0x46, 0)
			w16(s + 0x36, u16(s + 0x32))
	elif ph == 1:
		w16(s + 0x32, KFCreatureAI.lerp_fixed(s16(s + 0x36), 0, s16(s + 0x46)))
		w16(s + 0x46, u16(s + 0x46) + 0x200)
		if s16(s + 0x46) >= 0x1000:
			w8(s, 0xFF)


# A mark's burst (0x80058464): waiting +0x44 frames, then growing 0x46 a frame
# to 0x1f8, striking a shell 3.5 times it (effect_grow 0x3800, 0x800, 0x8000).
# @orig game:0x80058464 effect_tick+0x1ba8  status:verified -- through the moonlight swords, tools/effects.py spell_hit_check
func _tick_moon_burst(s: int) -> void:
	var n := u8(s + 0x44)
	if n != 0:
		w8(s + 0x44, n - 1)
		return
	out_words([0x8000])
	grow(0x3800, 0x1F8, 0x46, 0x800, 0x8000)


# Dark slayer's spheres (0x8005876c, 0x44 and 0x45): growing 0x46 a frame to
# +0x44, striking a shell four times it (effect_grow 0x4000, 0x800, 0x8000).
# @orig game:0x8005876c effect_tick+0x1eb0  status:verified -- through dark slayer's two, tools/effects.py spell_hit_check
func _tick_sphere(s: int) -> void:
	out_words([0x8000])
	grow(0x4000, s16(s + 0x44), 0x46, 0x800, 0x8000)


# Dark slayer's second (0x80058898): turning 0x190 a frame, on by its velocity
# through anything. A column 0x2710 high about its point, 0x1388 under it: the
# first creature standing in it (actor_spot_taken, 0x64) gets a sphere (0x44,
# growing to 0x4ec) where it stands; with none, the player alone in it
# (collide_query 0xb0 answering 0x80) gets one at the feet. Every frame it
# does. A splash on water within 0x2710 under the column's foot.
# @orig game:0x80058898 effect_tick+0x1fdc  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, at the creatures and back at the player; the self-test this to it
func _tick_slayer2(s: int) -> void:
	w16(s + 0x2A, u16(s + 0x2A) + 0x190)
	for i in 3:
		w32(s + 0x18 + 4 * i, s32(s + 0x18 + 4 * i) + s16(s + 0x38 + 2 * i))
	var x := s32(s + 0x18)
	var y := s32v(s32(s + 0x1C) + 0x1388)
	var z := s32(s + 0x20)
	out_words([0x2710])
	var a: int = world.spot_taken(x, y, z, 0x64, 0x2710)
	if a != -1:                             # the sound (0x27), not here
		spawn(0xA, u8(s), SPHERE2, world.actor_point(a), [null, 0x4EC], true)
	else:
		out_words([0x2710, 0xB0])
		world.collide_query(x, y, z, 0x64, 0x2710, 0xB0)
		if int(world.collide_mask) == 0x80:     # the sound (0x27), not here
			spawn(u8(s + 6), u8(s), SPHERE2, world.player_point(), [null, 0x4EC], true)
	_splash_one_at([x, y, z], 0x2000, 0x7FFF, 0x2710)


# Dark slayer's first (0x80058790): not drawn; on by its velocity, the tiles
# asked half a step back and where it is (collide_wrapper_actor, 5, 0xa) --
# either met, it is freed -- and a sphere (0x45, growing to 0x1a4) where it
# is every frame regardless, +0 its own (0xff once freed, so the sphere's slot
# stays free).
# @orig game:0x80058790 effect_tick+0x1ed4  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_slayer(s: int) -> void:
	var half := []
	for i in 3:
		half.append(s32v(s32(s + 0x18 + 4 * i) + (s16(s + 0x38 + 2 * i) >> 1)))
	for i in 3:
		w32(s + 0x18 + 4 * i, s32(s + 0x18 + 4 * i) + s16(s + 0x38 + 2 * i))
	out_words([0xA])
	if world.collide_wrapper(int(half[0]), int(half[1]), int(half[2]), 5, 0xA) != 0:
		w8(s, 0xFF)
	elif world.collide_wrapper(s32(s + 0x18), s32(s + 0x1C), s32(s + 0x20), 5, 0xA) != 0:
		w8(s, 0xFF)
	var f := u8(s)
	spawn(0xA if f & 0x40 else u8(s + 6), f, SPHERE, m.slice(s + 0x18, s + 0x28), [null, 0x1A4],
		true)


# --- lightning ------------------------------------------------------------

# Lightning (0x8005917c; the creatures' 0x7d and 0x81 the same), by +7. 0:
# level, effect_move at 0x32 (the height's top bit, turning 0x12c a frame),
# counting +0x44 down; the tiles stop it -- the move taken back, the level
# speed zeroed -- and it falls (+7 1). 1: falling 0x46 a frame faster, the
# level speed to 0xbb8/0x1000 each frame; with the floor under it -- the
# nearer of the surface and the water the last query found -- 0x1b58 or more
# below, over a drop, or once the tiles stop it (the move taken back,
# collide_surface asked), it strikes: +7 2, a bolt (0x72; 0x7e, 0x80) standing on the floor as high
# as it fell, and an earth wave (0x16) there, half that far at a sixteenth a
# frame -- their velocity the last puff's. 2: shrinking 0x80 a frame, gone at
# nothing. While 0 or 1, four puffs a frame where it is.
# @orig game:0x8005917c effect_tick+0x28c0  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, the player's and the creatures' kinds; the self-test this to it; the sounds not here
func _tick_lightning(s: int) -> void:
	var kind := u8(s + 1)
	var ph := u8(s + 7)
	if ph == 2:
		var v := (u16(s + 0x30) - 0x80) & 0xFFFF
		w16(s + 0x30, v)
		w16(s + 0x32, v)
		if s16v(v) <= 0:
			w8(s, 0xFF)
		return
	var hit := move(0x32, 0x80000000, -0x12C)
	var drop := 0
	var strike := false
	if hit != 0:
		if hit & 0xF:
			undo(s)
			if ph == 0:
				w16(s + 0x3C, 0)
				w16(s + 0x38, 0)
			else:
				out_words([0])
				world.surface(s32(s + 0x18), s32(s + 0x1C), s32(s + 0x20), 0x32, 0)
				drop = _floor_under(s)
				strike = true
		if not strike:
			w8(s + 7, 1)
	if not strike:
		if ph == 1:
			w16(s + 0x3A, u16(s + 0x3A) - 0x46)
			w16(s + 0x38, KFCreatureAI.lerp_fixed(0, s16(s + 0x38), 0xBB8))
			w16(s + 0x3C, KFCreatureAI.lerp_fixed(0, s16(s + 0x3C), 0xBB8))
			drop = _floor_under(s)
			strike = drop >= 0x1B58
		elif ph == 0:
			var c := u16(s + 0x44)
			w16(s + 0x44, c - 1)
			if s16v(c) <= 0:
				w8(s + 7, 1)
	if strike:
		w8(s + 7, 2)
		var point := PackedByteArray()
		point.resize(16)
		point.encode_s32(0, s32(s + 0x18))
		point.encode_s32(4, s32v(drop + s32(s + 0x1C)))
		point.encode_s32(8, s32(s + 0x20))
		point.encode_s32(12, tick_frame.decode_s32(0x15C))
		for i in 16:
			tick_frame[0x150 + i] = point[i]
		var vel := tick_frame.slice(0x160, 0x168)
		var bolt := 0x72
		var last := 1
		if kind == 0x7D:
			bolt = 0x7E
			last = 3
		elif kind == 0x81:
			bolt = 0x80
			last = 0
		spawn(0xA, u8(s) | 3, bolt, point, [vel, drop], true)
		spawn(0xA, u8(s), 0x16, point, [vel, drop >> 1, drop >> 4, 0x800, last], true)   # and the sound (0x27), not here
	for _k in 4:
		for i in 3:
			tick_frame.encode_s16(0x160 + 2 * i, (int(world.rand()) >> 7) - 0x80)
		spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x160, 0x168), 0x800,
			-0x80, 5, 0xC, 0, 1, 1], true)


# The nearer (higher) of collision_surface and surface_plane_18, as the last
# query left them, less the point's height (0x80059210).
# @orig game:0x80059210 effect_tick+0x2954  status:verified -- through lightning; the water's side of the choice never met in the check's runs
func _floor_under(s: int) -> int:
	var surf := int(world.field("cs"))
	var water := int(world.field("s18"))
	var f := surf if surf < water else water
	tick_frame.encode_s32(0x154, f)
	return s32v(f - s32(s + 0x1C))


# A lightning's bolt (0x80059518; 0x7e, 0x80): its first three frames (+7 0..2)
# a sphere (0x13; 0x29, 0x2d; +0 | 3) where it stands, as large as the cube of
# its height under two roots, an eighth (game_sqrt12 twice) -- its velocity the
# stack's. Flickering, and while +7 is under 9 a flash of light (0xc8, 0xb4,
# 0xa0) out to 0x7d00 when the player is nearer than that: (sin(+7 << 8) / 2
# + 0x400) times how much nearer, over 0x7d00. +7 counts.
# @orig game:0x80059518 effect_tick+0x2c5c  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
func _tick_bolt_of(s: int) -> void:
	var kind := u8(s + 1)
	var ph := u8(s + 7)
	if ph < 3:
		var h := s16(s + 0x32)
		var a := s32v(h * (s32v(h * h) >> 12))
		var r := s32v(coll.sqrt12(coll.sqrt12(a))) >> 3
		var child := 0x13 if kind == 0x72 else (0x29 if kind == 0x7E else 0x2D)
		spawn(0xA, u8(s) | 3, child, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x168, 0x170), r],
			true)
	w8(s + 4, (ph & 1) - 0x80)
	if u8(s + 7) < 9:
		var d := vec_length_3d(s32v(int(world.field("px")) - s32(s + 0x18)),
			s32v(int(world.field("py")) - s32(s + 0x1C)), s32v(int(world.field("pz")) - s32(s + 0x20)))
		if d < 0x7D01:
			var v := s32v(((coll.game_sin(u8(s + 7) << 8) >> 1) + 0x400) * (0x7D00 - d))
			var k := s16v(_trunc(v, 0x7D00))
			out_words([0x7D00, k])
			world.lighting([0xC8, 0xB4, 0xA0], 0, 0x7D00, k)
	w8(s + 7, u8(s + 7) + 1)


# A bolt's sphere (0x80059688; 0x29, 0x2d): growing 0x80 a frame to +0x44,
# striking a shell 3.5 times it (effect_grow 0x3800, 0x400, 0x8000); a puff
# rising from it, each axis rand >> 6 less 0x100 across, -(rand >> 7) - 0x80
# up (0x2000, -0x80, 0xf, 0xc, 0xa, 1, 1); turning 0x40 a frame.
# @orig game:0x80059688 effect_tick+0x2dcc  status:verified -- through lightning, tools/effects.py spell_hit_check
func _tick_bolt_sphere(s: int) -> void:
	out_words([0x8000])
	grow(0x3800, s16(s + 0x44), 0x80, 0x400, 0x8000)
	tick_frame.encode_s16(0x168, (int(world.rand()) >> 6) - 0x100)
	tick_frame.encode_s16(0x16C, (int(world.rand()) >> 6) - 0x100)
	tick_frame.encode_s16(0x16A, -(int(world.rand()) >> 7) - 0x80)
	spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x168, 0x170), 0x2000,
		-0x80, 0xF, 0xC, 0xA, 1, 1], true)
	w16(s + 0x2A, u16(s + 0x2A) + 0x40)


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
		spawn(0xA, 0x42, RING, m.slice(s + 0x18, s + 0x28), [null, s16(s + 0x46)], true)
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
		spawn(0xA, 0x42, WAVE, m.slice(s + 0x18, s + 0x28), [v], true)
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
		spawn(0xA, 0, HOLD, m.slice(s + 0x18, s + 0x28), [null, int(world.collide_actor)], true)
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
		spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v, 0x1000, -0x80, 5, 0xC, 0, 1, 0], true)
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
					[v, scale, -0x80, 5, 0x1C, 0, 1, 2], true)
				scale -= 0x15E
			return
		w32(s + 0x1C, surf)
	var point := m.slice(s + 0x18, s + 0x28)
	_attack(s, mask)
	var v0 := PackedByteArray()
	v0.resize(8)
	v0.encode_s16(2, -0x20)
	spawn(0xA, u8(s), BLAST, point, [v0, 0x640, 0x64, 0x800], true)
	for _k in 4:
		var pt := m.slice(s + 0x18, s + 0x28)
		pt.encode_s32(0, s32v(pt.decode_s32(0) - 0x1F4 + ((int(world.rand()) * 1000) >> 15)))
		pt.encode_s32(8, s32v(pt.decode_s32(8) - 0x1F4 + ((int(world.rand()) * 1000) >> 15)))
		var v := PackedByteArray()
		v.resize(8)
		v.encode_s16(2, -0x168)
		spawn(0xA, 0, TRAIL, pt, [v, 0x4000, -0x80, 5, 0x1D, 0, 1, 2], true)
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
		-0x80, 5, 0x16, 0, 1, 1], true)
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
		8, 0x1C, 2, 1, 2], true)


# Fire storm (0x80059db8): at a creature (+0x44 its slot) it homes on its
# middle, effect_home at most 0x1c2 a frame, slowing within 0x64; at the
# player (0xfe) on the eye, 0x1f4, within 0xbb8; with none (0xff) it falls,
# 0xa a frame more, through effect_move. Meeting anything: what collide_query
# last answered (collide_mask) struck, six puffs about it, splashes in the
# water, gone. Else, from its seventh frame, a puff a frame behind.
# @orig game:0x80059db8 effect_tick+0x34fc  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, 126 of 126 runs, at a creature, the player and none; the self-test this to it
func _tick_fire_storm(s: int) -> void:
	var t := u8(s + 0x44)
	var met := false
	if t == 0xFF:
		w16(s + 0x3A, u16(s + 0x3A) + 0xA)
		met = move(0xA, 0x80000000, 0) != 0
	else:
		var target: Array
		var most := 0x1C2
		var near := 0x64
		if t == 0xFE:
			target = [int(world.field("px")), s32v(int(world.field("py")) - 0x640),
				int(world.field("pz"))]
			most = 0x1F4
			near = 0xBB8
		else:
			target = world.actor_mid(t)
		out_words([0, 0xA, 0x80000000])
		met = home(target, most, 0x3C, near, 0, 0xA, 0x80000000) == -1
	if met:
		_attack(s, int(world.collide_mask))
		for _k in 6:
			tick_frame.encode_s16(0x170, ((400 * int(world.rand())) >> 15) - 0xC8)
			tick_frame.encode_s16(0x174, ((400 * int(world.rand())) >> 15) - 0xC8)
			tick_frame.encode_s16(0x172, ((400 * int(world.rand())) >> 15) - 0xC8)
			spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x170, 0x178),
				0x1D4C, -0x2EE, 8, 0x16, 0xA, 1, 2], true)
		_splash(s + 0x18, 5, 0x400, 0x2000, 0x4000, 0x1000)
		w8(s, 0xFF)
		return
	if s16(s + 0x10) < 0x4A:
		for at in [0x170, 0x172, 0x174]:
			tick_frame.encode_s16(at, ((60 * int(world.rand())) >> 15) - 0x1E)
		spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [tick_frame.slice(0x170, 0x178),
			0x1000, -0x100, 0xD, 0x1C, 0xA, 1, 2], true)


# effect_home: from the point to the target, vec_length_3d; -2 when not past
# `reach`; within `near` the velocity to three quarters (fixed_madd(0, v,
# 0xc00)); then effect_steer along the direction, each axis << 12 over the
# length.
# @orig game:0x80055f74 effect_home  status:verified -- through fire storm, tools/effects.py spell_hit_check against the game's own
func home(target: Array, most: int, accel: int, near: int, reach: int, radius: int,
		height: int) -> int:
	var s := current
	var d := []
	for i in 3:
		d.append(s32v(int(target[i]) - s32(s + 0x18 + 4 * i)))
	var ln := vec_length_3d(d[0], d[1], d[2])
	if not reach < ln:
		return -2
	if not near < ln:
		for o in [0x38, 0x3A, 0x3C]:
			w16(s + o, (s16(s + o) * 0xC00) >> 12)
	var dirv := []
	for i in 3:
		dirv.append(s16v(_trunc(s32v(int(d[i]) << 12), ln)))
	return steer(accel, most, radius, height, dirv)


# effect_steer: the velocity += vec_scale(accel, dir), cut to `most` when
# longer, the point moved; then effect_collide there -- -1 met, 0 not;
# nothing asked with a height of -1.
# @orig game:0x80055bd8 effect_steer  status:verified -- through fire storm, tools/effects.py spell_hit_check against the game's own
func steer(accel: int, most: int, radius: int, height: int, dirv: Array) -> int:
	var s := current
	accel = s16v(accel)
	for i in 3:
		var o := s + 0x38 + 2 * i
		w16(o, u16(o) + ((int(dirv[i]) * accel) >> 12))
	var v := [s16(s + 0x38), s16(s + 0x3A), s16(s + 0x3C)]
	var ln := vec_length_3d(v[0], v[1], v[2])
	if most < ln:
		for i in 3:
			w16(s + 0x38 + 2 * i, _trunc(int(v[i]) * most, ln))
	for i in 3:
		w32(s + 0x18 + 4 * i, s32(s + 0x18 + 4 * i) + s16(s + 0x38 + 2 * i))
	if height == -1:
		return 0
	return -1 if collide(Vector3i(s32(s + 0x18), s32(s + 0x1C), s32(s + 0x20)), radius,
		height) != 0 else 0


# vec_length_3d: each >> 3, the squares summed in a word, the game's root, << 3.
# @orig game:0x80016c44 vec_length_3d  status:verified -- through fire storm's homing, tools/effects.py spell_hit_check against the game's own
func vec_length_3d(x: int, y: int, z: int) -> int:
	return coll.isqrt(((x >> 3) * (x >> 3) + (y >> 3) * (y >> 3) + (z >> 3) * (z >> 3))
		& 0xFFFFFFFF) << 3


# MIPS div, toward 0.
# @port helper -- division as the R3000 does it
static func _trunc(a: int, b: int) -> int:
	var q := absi(a) / absi(b)
	return -q if (a < 0) != (b < 0) else q


# The middle of creature `t`, as fire storm aims at it: its place, half its
# height (+0x1e) up.
# @port helper -- an actor's middle from actors.gd, the world's answer to fire storm
func actor_mid(t: int) -> Array:
	var an := get_node_or_null("../Actors")
	if an == null or an.get("actors") == null:
		return [0, 0, 0]
	var list: Array = an.get("actors")
	if t >= list.size() or list[t] == null:
		return [0, 0, 0]
	var a = list[t]
	return [int(a["px"]), s32v(int(a["py"]) - (int(a["height"]) >> 1)), int(a["pz"])]


# Flame (0x8005a39c), by +7. 0, flying: effect_move at 0xfa and the height's
# top bit, the head's clock (+0x14) 0x80 a frame; with a creature marked
# (+0x45 shots left of five) a fire ball from the head's vertex 0 at its
# middle, 0x320 a frame; else one time in sixteen a look for one within
# 0x61a8 (sub_8004d3c4, cones 0x320, noise 0x200), and one in thirty-two,
# within 0x7530, two breaths (0x6e, the empty arm) from vertices 0x2f and
# 0x32. Meeting anything or at the end of its life: splashes, a second flame
# (+0 | 3) set at +7 2 to burst three frames on, and it bursts -- +7 1,
# model 0x15, +0 | 3, effect_grow(0x4000, 0x800, 0x4b, 0x400, 0x8000) and a
# turn of 0x40 a frame, the player struck too. 2..4 count to 5, which bursts.
# @orig game:0x8005a39c effect_tick+0x3ae0  status:verified -- tools/effects.py spell_hit_check against the game's own end to end, 126 of 126 runs; the self-test this to it
func _tick_flame(s: int) -> void:
	var ph := u8(s + 7)
	if ph == 0:
		var hit := move(0xFA, 0x80000000, 0)
		if hit != 0 or s16(s + 0x10) < 2:
			_splash(s + 0x18, 8, 0x190, 0x2000, 0x8000, 0x400)
			var c := spawn(0xA, u8(s) | 3, FLAME, m.slice(s + 0x18, s + 0x28),
				[null, m.slice(s + 0x28, s + 0x30)], true)
			if c >= 0:
				w8(c + 7, 2)                # and its sound (0x27), not here
			_flame_burst(s)
			return
		w16(s + 0x14, (u16(s + 0x14) + 0x80) & 0xFFF)
		if u8(s + 0x45) != 0:
			var p := head(s, 0)
			for i in 3:
				tick_frame.encode_s32(0x1D0 + 4 * i, int(p[i]))
			var t: Array = world.actor_mid(u8(s + 0x44))
			for i in 3:
				tick_frame.encode_s32(0x1C0 + 4 * i, int(t[i]))
			var v := vec_toward(p, t, 0x320)
			for i in 3:
				tick_frame.encode_s16(0x1B8 + 2 * i, int(v[i]))
			spawn(0xA, u8(s), FIRE_BALL, tick_frame.slice(0x1D0, 0x1E0),
				[tick_frame.slice(0x1B8, 0x1C0)], true)
			w8(s + 0x45, u8(s + 0x45) - 1)
		elif int(world.rand()) < 0x800:
			var k := _look(s, 0x61A8)
			if k >= 0:
				w8(s + 0x44, k)
				w8(s + 0x45, 5)
		if int(world.rand()) < 0x400 and _look(s, 0x7530) >= 0:
			breath(s, 0x2F)
			breath(s, 0x32)
		return
	if ph == 1:
		_flame_grow(s)
	elif ph == 5:
		_flame_burst(s)
	else:
		w8(s + 7, ph + 1)


# Flame's burst (0x8005a458): +7 1, model 0x15, its scale 0, a life that
# does not run out, +0 | 3; then its growth.
# @orig game:0x8005a458 effect_tick+0x3b9c  status:verified -- through flame, the same runs
func _flame_burst(s: int) -> void:
	w8(s + 7, 1)
	w8(s + 3, 0x15)
	w8(s + 0xC, 0x34)
	for o in [0x34, 0x32, 0x30]:
		w16(s + o, 0)
	w16(s + 0x10, -1)
	w8(s, u8(s) | 3)
	_flame_grow(s)


# Flame's growth (0x8005a628): effect_grow(0x4000, 0x800, 0x4b, 0x400,
# 0x8000), then the mark's tail, a turn of 0x40.
# @orig game:0x8005a628 effect_tick+0x3d6c  status:verified -- through flame, the same runs
func _flame_grow(s: int) -> void:
	grow(0x4000, 0x800, 0x4B, 0x400, 0x8000)
	w16(s + 0x2A, u16(s + 0x2A) + 0x40)


# sub_8004d3c4 from the effect's point along its angles, cones 0x320, noise
# 0x200; the distance left at effect_tick's sp+0x1e0. The slot, or -1.
# @port helper -- flame's look for a creature, through the world
func _look(s: int, reach: int) -> int:
	out_words([0x320, 0x320, 0x801FBE00, 0x200])     # the last: effect_tick's sp+0x1e0, as the check runs it
	var r: Array = world.sight([s32(s + 0x18), s32(s + 0x1C), s32(s + 0x20)], s16(s + 0x2A),
		s16(s + 0x28), reach, 0x320, 0x320, 0x200)
	tick_frame.encode_s32(0x1E0, int(r[1]))
	return int(r[0])


# sub_8004d3c4 for an effect: the player's list of the awake creatures,
# a rand for each one in the cones. [slot or -1, distance].
# @port helper -- the creature in sight from an effect, from player.gd's sight
func sight(point: Array, yaw: int, pitch: int, reach: int, ycone: int, pcone: int,
		noise: int) -> Array:
	if player == null or not player.has_method("sight_list"):
		return [-1, -1]
	var r: Array = player.sight(coll, player.call("sight_list"), point, yaw, pitch, reach, ycone,
		pcone, noise, rand)
	return [int(r[0][0]) if r[0] != null else -1, int(r[1])]


# sub_80053af4 (through 0x80053a0c and sub_8004352c): vertex `vertex` of the
# effect's animated model -- model_table[+3 + 0x28], animation +4, clock
# +0x14 -- each axis by its scale, turned by its angles with the yaw a half
# turn on (vec_rotate), from its point.
# @orig game:0x80053af4 sub_80053af4  status:verified -- through flame's fire balls, tools/effects.py spell_hit_check against the game's own
# @orig game:0x80053a0c sub_80053a0c  status:verified -- the same
func head(s: int, vertex: int) -> Array:
	var key := BANK_KEY + u8(s + 3) + 0x28
	if not KFAnim.models.has(key):
		KFAnim.load_from("res://anim%02d.json" % (int(player.call("_level")) if player and
			player.has_method("_level") else 0))
	var vs := KFAnim.vertices(key, u8(s + 4), u16(s + 0x14)) if KFAnim.models.has(key) else []
	var v := [0, 0, 0]
	if vertex < vs.size():
		var w: Vector3i = vs[vertex]
		v = [s16v((w.x * s16(s + 0x30)) >> 12), s16v((w.y * s16(s + 0x32)) >> 12),
			s16v((w.z * s16(s + 0x34)) >> 12)]
	var r := KFWeapon.vec_rotate(coll, s16(s + 0x28), s16v(u16(s + 0x2A) + 0x800), s16(s + 0x2C), v)
	return [s32v(int(r[0]) + s32(s + 0x18)), s32v(int(r[1]) + s32(s + 0x1C)),
		s32v(int(r[2]) + s32(s + 0x20))]


# sub_800561d8: from vertex `vertex` of the head, the yaw jittered by
# (rand >> 7) - 0x80, effect_spawn(10, +0, 0x6e, ...) with a velocity of 0 --
# the empty arm, so the slot is set up and freed -- and +7 2 written in it.
# @orig game:0x800561d8 sub_800561d8  status:verified -- through flame, the same runs
func breath(s: int, vertex: int) -> void:
	var p := head(s, vertex)
	var pt := PackedByteArray()
	pt.resize(16)
	for i in 3:
		pt.encode_s32(4 * i, int(p[i]))
	var _jitter := int(world.rand())        # the yaw's, for angles the empty arm never reads
	var zero := PackedByteArray()
	zero.resize(8)
	var c := spawn(0xA, u8(s), BREATH, pt, [zero, zero])
	if c >= 0:
		w8(c + 7, 2)


# 0x80016044: from a to b, `speed` long -- each axis times the speed over
# vec_length_3d, toward 0.
# @orig game:0x80016044 sub_80016044  status:verified -- through flame's fire balls, tools/effects.py spell_hit_check against the game's own
func vec_toward(a: Array, b: Array, speed: int) -> Array:
	var d := []
	for i in 3:
		d.append(s32v(int(b[i]) - int(a[i])))
	var ln := vec_length_3d(d[0], d[1], d[2])
	var out := []
	for i in 3:
		out.append(s16v(_trunc(s32v(int(d[i]) * speed), ln)))
	return out


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
	spawn(0xA, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v, 0x1A90, -0x3E8, 4, 0x25, 0, 1, 1], true)
	var hit := move(0xB4, 0, 0)
	if hit == 0:
		return
	if hit & 0xF:
		w8(s, 0xFF)
	if hit & 0x10 == 0:
		return
	var point := m.slice(s + 0x18, s + 0x28)
	spawn(0xA, 0x43, BURST, point, [null, 0, 1], true)
	spawn(0xA, 0x43, BURST, point, [null, 0x80, 1], true)     # and its sound (0x25), not here
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
		spawn(0xA, 0, RAY, pt, [vr], true)


# Orladin's burst (0x80059b84, kind 0x58): growing 0x80 a frame from its
# size, striking a shell four times it -- the player too, its +0 is 0x43 --
# gone at 0x600; then fire resist's mark's tail (0x8005b5fc), turning 0x40.
# @orig game:0x80059b84 effect_tick+0x32c8  status:verified -- tools/effects.py spell_hit_check against the game's own end to end; the self-test this to it
# @orig game:0x8005b5fc effect_tick+0x4d40  status:verified -- the turn of the tail it shares with fire resist's mark
func _tick_burst(s: int) -> void:
	grow(0x4000, 0x600, 0x80, 0x400, 0x8000)
	w16(s + 0x2A, u16(s + 0x2A) + 0x40)


# effect_grow: a sphere growing `step` a frame, its three scales alike; it
# strikes between mult times its last size and mult times its size less
# one, `mode` and `edge`, at 0x1000; gone at `limit`.
# @orig game:0x80056134 effect_grow  status:verified -- through orladin's burst, tools/effects.py spell_hit_check against the game's own
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
	coll.surfaces.clear()
	var q := coll.query(x, y, z)
	coll.flags = 0
	coll.radius = keep_r
	coll.body = keep_b
	surface18 = int(coll.surfaces.get(0x18, 100000))
	collision_surface = int(q["floor"])
	return int(q["mask"])


# collide_surface for an effect: the nearest surface under the point, its
# layer from a flat y - 0x500 (collision.gd surface).
# @port helper -- collision.gd surface at the radius and height an effect asks with
func surface(x: int, y: int, z: int, r: int, h: int) -> int:
	return int(surface_ceiling(x, y, z, r, h)[0])


# collide_surface, and the ceiling tile_collision leaves beside the surface
# (collision_ceiling, 0x801e6478), as a mark's pillar reads them; the water's
# plane it finds kept, as tile_collision keeps it (0x801e647c).
# @port helper -- collision.gd query from a flat y - 0x500, [surface, ceiling]
func surface_ceiling(x: int, y: int, z: int, r: int, h: int) -> Array:
	if coll == null:
		return [100000, -40000]
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = r
	coll.body = h
	coll.surfaces.clear()
	var q := coll.query(x, y, z, y - 0x500)
	coll.radius = keep_r
	coll.body = keep_b
	surface18 = int(coll.surfaces.get(0x18, 100000))
	collision_surface = int(q["floor"])
	return [int(q["floor"]), int(q["ceil"])]


# actor_spot_taken for an effect, from actors.gd.
# @port helper -- the creature standing in a column, the world's answer to dark slayer's second
func spot_taken(x: int, y: int, z: int, r: int, own: int) -> int:
	var an := get_node_or_null("../Actors")
	if an == null or not an.has_method("spot_taken"):
		return -1
	return int(an.call("spot_taken", x, y, z, r, own))


# Creature t's place as an arm copies it, the 16 bytes from its +0x2c (+0x38
# is 0 on every awake creature of the snapshots).
# @port helper -- an actor's place from actors.gd, 16 bytes
func actor_point(t: int) -> PackedByteArray:
	var b := PackedByteArray()
	b.resize(16)
	var an := get_node_or_null("../Actors")
	if an == null or an.get("actors") == null:
		return b
	var list: Array = an.get("actors")
	if t < 0 or t >= list.size() or list[t] == null:
		return b
	b.encode_s32(0, int(list[t]["px"]))
	b.encode_s32(4, int(list[t]["py"]))
	b.encode_s32(8, int(list[t]["pz"]))
	return b


# player_pos as an arm copies it, 16 bytes; the fourth word (0x801b25fc,
# which only save_restore writes) the field "pw".
# @port helper -- the player's place, 16 bytes
func player_point() -> PackedByteArray:
	var b := PackedByteArray()
	b.resize(16)
	b.encode_s32(0, int(world.field("px")))
	b.encode_s32(4, int(world.field("py")))
	b.encode_s32(8, int(world.field("pz")))
	b.encode_s32(12, int(world.field("pw")))
	return b


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


# @port helper -- _splash_one_at at a point in the slots
func _splash_one(point: int, size: int, bob: int, depth: int) -> void:
	_splash_one_at([s32(point), s32(point + 4), s32(point + 8)], size, bob, depth)


# sub_80056268: one splash on the surface the last query found, when the
# point is within `depth` under it.
# @orig game:0x80056268 sub_80056268  status:verified -- through stone and wind cutter, and dark slayer's second at its column's foot
func _splash_one_at(p: Array, size: int, bob: int, depth: int) -> void:
	var y := int(p[1])
	var surf := int(world.field("s18"))
	if y < surf or surf + depth < y:
		return
	var pt := PackedByteArray()
	pt.resize(16)
	pt.encode_s32(0, int(p[0]))
	pt.encode_s32(4, surf)
	pt.encode_s32(8, int(p[2]))
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
	var t := spawn(0xA, 0, TRAIL, pt, [vel, 0x2BC, -0x1E, 0xA, 0x26, -0xA, b, e], true)
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
		"py": return int(player.get("gy"))
		"pz": return int(player.get("gz"))
		"s18": return surface18
		"cs": return collision_surface
		"vp": return int(player.call("view_pitch_now")) if player.has_method("view_pitch_now") else 0
		"pw": return 0                  # 0x801b25fc: not kept by the port
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
	spawn(10, 0, TRAIL, m.slice(s + 0x18, s + 0x28), [v] + TRAIL_ARGS.slice(0, 5) + [b, e], true)


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
		coll.surfaces.clear()
		var q := coll.query(x, y, z)
		coll.flags = 0
		coll.radius = keep_r
		coll.body = keep_b
		surface18 = int(coll.surfaces.get(0x18, 100000))   # seeded 100000 (0x8003265c)
		collision_surface = int(q["floor"])
		mask = int(q["mask"])
		var at := int(q["at"])
		layer_offset = 5 if at >= 0 and at % 6 != 0 else 0
	if not inside:
		return _kept(mask)
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
		return _kept(mask)
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
	return _kept(mask)


# collide_query's end: the answer kept at collide_mask before it is returned.
# @orig game:0x80034144 collide_query+0x20c  status:verified -- through fire storm's burst, which strikes with it; tools/effects.py spell_hit_check against the game's own
func _kept(mask: int) -> int:
	collide_mask = mask
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

class_name KFLevers
# The levers, opcode 0x53, and two of the things they move: level 5's trees,
# opcode 0x56, which grow and shrink by pairs, and level 13's slabs, opcode
# 0x58. tools/levers.py has it in prose.
#
# Written as it is there, over the game's own addresses: `m` is KFLevelIn's
# {"mem", "calls"}, which godot/loot.gd fills from the port's fields and puts
# back. tools/levers.py is the same in Python, held to the game's own arms and
# object_signal; the self-test holds this to it.
#
# @exe game

const LEVER_OP := 0x53
const TREE_OP := 0x56
const SLAB_OP := 0x58
const OPS := [LEVER_OP, TREE_OP, SLAB_OP]
const OBJECT_TYPES := 0x8018FB3C       # object_type_table: 24 bytes a type
const CURRENT_LEVEL := 0x8018FAD8
const SCALE := 0x2C                    # +0x2c, +0x2e, +0x30
const ONE := 0x1000
const DONE := 0x63
const PLAIN := 0xF                     # a type's +0xf that sounds in passing
const MASK_STAMP := 0x2D               # tile, rotation, shape, fence
const SLAB_SOUND := 0x14
const LEVEL_13 := 0xD
const LEVEL_13_SOUNDS := 0x1F0


# The end of a swing: +0x3c not 1, the signal; +0x38 1, the sound and state
# 4; 0 state 0x63; 2 and 3 state 0.
# @orig game:0x80048dc8 object_interpreter+0x1db8  status:verified -- with lever
static func _lever_end(m: Dictionary, r: int, tone: int) -> void:
	if KFLevelIn.rd(m, r + 0x3C) != 1:
		KFLevelIn.signal_all(m, KFLevelIn.rd(m, r + 0x39))
	var b := KFLevelIn.rd(m, r + 0x38)
	if b == 1:
		m["calls"].append(["sound", r, tone])
		KFLevelIn.wr(m, r + 8, 4, 2)
	elif b == 0:
		KFLevelIn.wr(m, r + 8, DONE, 2)
	elif b < 4:
		KFLevelIn.wr(m, r + 8, 0, 2)


# Opcode 0x53's arm for the record in slot k; tools/levers.py lever.
# @orig game:0x80048c7c object_interpreter+0x1c6c  status:verified -- opcode 0x53's arm; tools/levers.py, 7200 of 7200 frames of the game's own arms and object_signal over six levels, the calls in order and all of RAM but the stack, the self-test this to it; the sounds not played
static func lever(m: Dictionary, k: int) -> void:
	var r := KFLevelIn.O(k)
	var tone := KFLevelIn.rd(m, OBJECT_TYPES + 24 * KFLevelIn.rd(m, r + 6, 2) + 0xF)
	if KFLevelIn.rd(m, CURRENT_LEVEL) == LEVEL_13:
		tone += LEVEL_13_SOUNDS
	var step := KFLevelIn.rd(m, r + 0x3A, 2)
	if step == 0xFFFF:
		step = 0x100
	var st := KFLevelIn.rd(m, r + 8, 2)
	if st == 1:
		if tone != PLAIN:
			m["calls"].append(["sound", r, tone])
		if KFLevelIn.rd(m, r + 0x3C) == 1:
			KFLevelIn.signal_all(m, KFLevelIn.rd(m, r + 0x39))
		var b := KFLevelIn.rd(m, r + 0x38)
		if b == 2:
			KFLevelIn.wr(m, r + 8, 2, 2)
			KFLevelIn.wr(m, r + 0x38, 3)
		elif b == 3:
			KFLevelIn.wr(m, r + 8, 3, 2)
			KFLevelIn.wr(m, r + 0x38, 2)
		elif b < 2:
			KFLevelIn.wr(m, r + 8, 2, 2)
	elif st == 2:
		var c := (KFLevelIn.rd(m, r + 0xA, 2) + step) & 0xFFFF
		KFLevelIn.wr(m, r + 0xA, c, 2)
		if tone == PLAIN and c > 0x400 and c <= step + 0x400:
			m["calls"].append(["sound", r, PLAIN])
		if c >= ONE:
			KFLevelIn.wr(m, r + 0xA, 0xFFF, 2)
			_lever_end(m, r, tone)
	elif st == 3:
		var c := KFLevelIn.rd(m, r + 0xA, 2)
		if tone == PLAIN and c > 0xC00 and c <= step + 0xC00:
			m["calls"].append(["sound", r, PLAIN])
		c = (c - step) & 0xFFFF
		KFLevelIn.wr(m, r + 0xA, c, 2)
		if KFTicks.s16(c) <= 0:
			KFLevelIn.wr(m, r + 0xA, 0, 2)
			_lever_end(m, r, tone)
	elif st == 4:
		var c := (KFLevelIn.rd(m, r + 0xA, 2) - step) & 0xFFFF
		KFLevelIn.wr(m, r + 0xA, c, 2)
		if KFTicks.s16(c) <= 0:
			KFLevelIn.wr(m, r + 8, DONE, 2)
	elif st == 9:
		if KFLevelIn.rd(m, r + 0x38) == 3:
			KFLevelIn.wr(m, r + 0xA, 0xFFF, 2)
		KFLevelIn.wr(m, r + 8, 0, 2)


# @port helper -- the three halves of the scale
static func _scale(m: Dictionary, r: int, v: int) -> void:
	for i in 3:
		KFLevelIn.wr(m, r + SCALE + 2 * i, v, 2)


# Opcode 0x56's arm for the record in slot k; tools/levers.py tree.
# @orig game:0x80049fcc object_interpreter+0x2fbc  status:verified -- opcode 0x56's arm; tools/levers.py, among the 7200 frames, the self-test this to it
static func tree(m: Dictionary, k: int) -> void:
	var r := KFLevelIn.O(k)
	var st := KFLevelIn.rd(m, r + 8, 2)
	if st == 0:
		if KFLevelIn.rd(m, r + 0x39) == 0:
			KFLevelIn.wr(m, r + 8, 2, 2)
			_scale(m, r, 0)
			KFLevelIn.wr(m, r + 0x38, 0)
			KFLevelIn.wr(m, r, 0)
		else:
			_scale(m, r, ONE)
			KFLevelIn.wr(m, r + 0x38, 0x80)
			KFLevelIn.wr(m, r + 8, 1, 2)
			KFLevelIn.wr(m, r, 2)
	elif st == 1:
		if KFLevelIn.rd(m, r + 0x39) == 0:
			KFLevelIn.wr(m, r + 8, 2, 2)
	elif st == 2:
		for i in 3:
			KFLevelIn.wr(m, r + SCALE + 2 * i, KFLevelIn.rd(m, r + SCALE + 2 * i, 2) - 0x80, 2)
		if KFTicks.s16(KFLevelIn.rd(m, r + SCALE, 2)) <= 0:
			_scale(m, r, 0)
			KFLevelIn.wr(m, r + 0x38, 0)
			KFLevelIn.wr(m, r, 0)
			if KFLevelIn.rd(m, r + 0x39) == 0xFF:
				KFLevelIn.wr(m, r + 8, 3, 2)
	elif st == 3:
		KFLevelIn.wr(m, r, 2)
		for i in 3:
			KFLevelIn.wr(m, r + SCALE + 2 * i, KFLevelIn.rd(m, r + SCALE + 2 * i, 2) + 0x100, 2)
		if KFTicks.s16(KFLevelIn.rd(m, r + SCALE, 2)) >= ONE:
			_scale(m, r, ONE)
			KFLevelIn.wr(m, r + 8, 0, 2)
			KFLevelIn.wr(m, r + 0x38, 0x80)


# @port helper -- stamp_rect's call, the template at `sx` laid at the record's +0x3a, +0x3b
static func _stamp(m: Dictionary, r: int, sx: int) -> void:
	m["calls"].append(["stamp", KFLevelIn.rd(m, r), sx, KFLevelIn.rd(m, r + 0x3D),
		KFLevelIn.rd(m, r + 0x3A), KFLevelIn.rd(m, r + 0x3B), KFLevelIn.rd(m, r + 0x3E),
		KFLevelIn.rd(m, r + 0x3F), KFTicks.s16(KFLevelIn.rd(m, r + 0x26, 2)) & 0xFFFFFFFF,
		MASK_STAMP])


# Opcode 0x58's arm for the record in slot k; tools/levers.py slab.
# @orig game:0x8004ab40 object_interpreter+0x3b30  status:verified -- opcode 0x58's arm; tools/levers.py, among the 7200 frames, the self-test this to it
static func slab(m: Dictionary, k: int) -> void:
	var r := KFLevelIn.O(k)
	var st := KFLevelIn.rd(m, r + 8, 2)
	if st == 1:
		var b := KFLevelIn.rd(m, r + 0x38)
		if b == 0:
			KFLevelIn.wr(m, r + 8, 2, 2)
			m["calls"].append(["sound", r, SLAB_SOUND])
		elif b == 1:
			KFLevelIn.wr(m, r + 8, 3, 2)
			m["calls"].append(["sound", r, SLAB_SOUND])
		_stamp(m, r, KFLevelIn.rd(m, r + 0x3C) + KFLevelIn.rd(m, r + 0x3E))
	elif st == 2:
		var c := (KFLevelIn.rd(m, r + 0xA, 2) - 0x40) & 0xFFFF
		KFLevelIn.wr(m, r + 0xA, c, 2)
		if KFTicks.s16(c) <= 0:
			KFLevelIn.wr(m, r + 8, DONE, 2)
			KFLevelIn.wr(m, r + 0xA, 0, 2)
			_stamp(m, r, KFLevelIn.rd(m, r + 0x3C))
	elif st == 3:
		var c := (KFLevelIn.rd(m, r + 0xA, 2) + 0x40) & 0xFFFF
		KFLevelIn.wr(m, r + 0xA, c, 2)
		if c >= ONE:
			KFLevelIn.wr(m, r + 0xA, 0xFFF, 2)
			KFLevelIn.wr(m, r + 8, DONE, 2)


# @port helper -- the arm by the record's opcode
static func arm(m: Dictionary, k: int) -> void:
	match KFLevelIn.rd(m, KFLevelIn.O(k, 4)):
		LEVER_OP:
			lever(m, k)
		TREE_OP:
			tree(m, k)
		SLAB_OP:
			slab(m, k)


# Would this record's arm change anything this frame? A tree gone stays in
# state 2 for good, writing its noughts every frame. tools/levers.py busy,
# which the game's own hold: a frame it calls idle leaves all of RAM alone.
# @port helper -- what spares loot.gd making the level's bytes every frame
static func busy(op: int, state: int, b39: int, scale: int) -> bool:
	if op == LEVER_OP:
		return state in [1, 2, 3, 4, 9]
	if op == TREE_OP:
		if state == 2:
			return scale != 0 or b39 == 0xFF
		return state == 0 or state == 3 or (state == 1 and b39 == 0)
	return state in [1, 2, 3]

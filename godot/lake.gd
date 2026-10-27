class_name KFLake
# Level 2's lake: opcode 0x5f's stamp switches, and the switch over them --
# object 82, opcode 0xa6, whose arm is the level's own entry 9 (the escape
# object_interpreter takes for the opcodes with no arm of their own).
#
# Opcode 0x5f lays one of two templates of cells into the level by its +0x3f
# (0 the one at +0x3b, 1 the one +0x3d further on) when something puts it in
# state 1 -- object_signal, the level's entry 1 by the aquarian boots, or the
# switch; the switch, from state 1 or 4, picks a position of six from its
# lock and gives each of level 2's seventeen stones its +0x3f for it, from
# seventeen words of the overlay (lake.json). tools/lake.py has it in prose.
#
# Written as it is there, over the game's own addresses: `m` is KFLevelIn's
# {"mem", "calls"}, which godot/loot.gd fills from the port's fields and puts
# back. tools/lake.py is the same in Python, held to the game's own arms and
# level 2's own entry 9; the self-test holds this to it.
#
# @exe game

const OP_STAMP := 0x5F
const OP_SWITCH := 0xA6
const OBJECT_TYPES := 0x8018FB3C       # object_type_table: 24 bytes a type
const CURRENT_OBJECT := 0x80198394
const CURRENT_TYPE := 0x80198390
const MASK_STAMP := 0x2D               # tile, rotation, shape, fence
const SWITCH := 82
const STONES := 100                    # 100..116
const COUNT := 17
const PATTERNS := 0x801E8F80           # level 2's overlay: a word a stone, a bit a position
const POSITIONS := 6
const DONE := 0x63


# @port helper -- stamp_rect's call, the record's template at `sx` laid at its +0x39, +0x3a
static func _stamp(m: Dictionary, r: int, sx: int) -> void:
	m["calls"].append(["stamp", 2, sx, KFLevelIn.rd(m, r + 0x3C), KFLevelIn.rd(m, r + 0x39),
		KFLevelIn.rd(m, r + 0x3A), KFLevelIn.rd(m, r + 0x3D), KFLevelIn.rd(m, r + 0x3E),
		KFTicks.s16(KFLevelIn.rd(m, r + 0x26, 2)) & 0xFFFFFFFF, MASK_STAMP])


# Opcode 0x5f's arm for record k: state 1 lays the template +0x3f does not
# leave (+0x3b + +0x3d) and goes to 2 (+0x3f 0), 3 (1) or stays; 2 lays the
# one at +0x3b and ends; 3 ends.
# @orig game:0x800490b8 object_interpreter+0x20a8  status:verified -- opcode 0x5f's arm; tools/lake.py, the game's own arm over every one of the twenty on levels 2 and 17 from every state (672 of 672 runs with the switch, all of RAM but the stack), the self-test this to it
static func arm5f(m: Dictionary, k: int) -> void:
	var r := KFLevelIn.O(k)
	var st := KFLevelIn.rd(m, r + 8, 2)
	if st == 1:
		var b := KFLevelIn.rd(m, r + 0x3F)
		if b == 0:
			KFLevelIn.wr(m, r + 8, 2, 2)
		elif b == 1:
			KFLevelIn.wr(m, r + 8, 3, 2)
		_stamp(m, r, KFLevelIn.rd(m, r + 0x3B) + KFLevelIn.rd(m, r + 0x3D))
	elif st == 2:
		KFLevelIn.wr(m, r + 8, DONE, 2)
		_stamp(m, r, KFLevelIn.rd(m, r + 0x3B))
	elif st == 3:
		KFLevelIn.wr(m, r + 8, DONE, 2)


# @port helper -- the switch's +1 from its lock: the lock less 1, or 5 for 0
static func _position(m: Dictionary, r: int) -> void:
	var lock := KFLevelIn.rd(m, r + 0x38)
	KFLevelIn.wr(m, r + 1, (lock - 1) & 0xFF if lock else 5)


# The level's entry 9 with record k the current object: level 2's switch
# (opcode 0xa6) -- state 1 its sound and its position, then a ramp of +0xa to
# 0xfff (state 2), then the pattern for (+1 + 1) mod 6 laid on the
# seventeen (state 3), and back to 0; state 4 the position and the pattern
# at once. Every other level's, and level 2's for any other opcode, nothing.
# @orig game:0x8004b4b4 object_interpreter+0x44a4  status:verified -- the escape into the level's entry 9 (level_hooks + 0x24); level 2's own out of its overlay, written out here as tools/lake.py, which the game's own arm and overlay hold (672 of 672 runs), the self-test this to it; level 7's (the pedestal, opcode 0xa7, object_use_state) not yet
static func entry9(lv: int, m: Dictionary, k: int) -> void:
	var r := KFLevelIn.O(k)
	if lv != 2 or KFLevelIn.rd(m, r + 4) != OP_SWITCH:
		return
	var st := KFLevelIn.rd(m, r + 8, 2)
	if st == 1:
		var row := OBJECT_TYPES + 24 * KFLevelIn.rd(m, r + 6, 2)
		m["calls"].append(["sound", r, KFLevelIn.rd(m, row + 0xF)])
		_position(m, r)
		KFLevelIn.wr(m, r + 8, 2, 2)
		KFLevelIn.wr(m, r + 0xA, 0, 2)
	elif st == 2:
		var v := (KFLevelIn.rd(m, r + 0xA, 2) + 0x80) & 0xFFFF
		KFLevelIn.wr(m, r + 0xA, v, 2)
		if v >= 0x1000:
			KFLevelIn.wr(m, r + 0xA, 0xFFF, 2)
			KFLevelIn.wr(m, r + 8, 3, 2)
	elif st == 3:
		var bit := 1 << ((KFLevelIn.rd(m, r + 1) + 1) % POSITIONS)
		for i in COUNT:
			var s := KFLevelIn.O(STONES + i)
			if KFLevelIn.rd(m, PATTERNS + 4 * i, 4) & bit:
				if KFLevelIn.rd(m, s + 0x38) == 0xC8 + i and KFLevelIn.rd(m, s + 0x3F) != 0:
					KFLevelIn.wr(m, s + 0x3F, 0)
					KFLevelIn.wr(m, s + 8, 1, 2)
			elif KFLevelIn.rd(m, s + 0x3F) != 1:
				KFLevelIn.wr(m, s + 0x3F, 1)
				KFLevelIn.wr(m, s + 8, 1, 2)
		KFLevelIn.wr(m, r + 0x40, 0xFF)
		KFLevelIn.wr(m, r + 8, 0, 2)
	elif st == 4:
		_position(m, r)
		KFLevelIn.wr(m, r + 8, 3, 2)


# Record k's turn in object_interpreter: the loop publishing it, then
# opcode 0x5f's arm or the escape into the level's entry 9.
# @port helper -- object_interpreter's dispatch for these two, as tools/lake.py arm
static func arm(lv: int, m: Dictionary, k: int) -> void:
	KFLevelIn.wr(m, CURRENT_OBJECT, KFLevelIn.O(k), 4)
	KFLevelIn.wr(m, CURRENT_TYPE, OBJECT_TYPES + 24 * KFLevelIn.rd(m, KFLevelIn.O(k, 6), 2), 4)
	if KFLevelIn.rd(m, KFLevelIn.O(k, 4)) == OP_STAMP:
		arm5f(m, k)
	else:
		entry9(lv, m, k)

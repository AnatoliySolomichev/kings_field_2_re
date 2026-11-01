class_name KFWarps
# What carries the player. Opcode 0xeb, the pads: A flat square on the floor of one
# cell whose record is a warp_to record but for the facing's size: +0x38 the
# level, +0x39 and +0x3a the block's last two bytes, +0x3b, +0x3c the cell,
# +0x3d the height in 128s, +0x3e the facing negated in 16ths. +0x3f 0 holds it
# off, which the levels' own code does till a creature dies. Over the
# dictionaries of godot/traps.gd; `w` is the world, loot.gd's -- rect, carry,
# level, slide -- and the warp itself crossing.gd's, which warp_to's plan drives.
# Opcode 0xea, the strips at the edges of levels 25's and 27's plain, walks the
# whole world back 24 cells, so that the plain has no end. tools/warps.py is
# the same in Python, held to the game's own arms; the self-test holds this to it.
#
# @exe game

const OP := 0xEB
const WRAP_OP := 0xEA
const NO_LEVEL := 0xFF
const TURNING_LEVEL := 24              # the only one that turns them
const TURNS := {0x144: 0x80, 0x145: 0x100}


# The warp as KFCrossing.warp takes it: warp_to's plan, from this record, with
# no answer, no screen_fade and the tilt at 0x801b2618 left alone.
# @orig game:0x8004a36c object_interpreter+0x335c  status:verified -- the arm's warp: the place, the facing, the block and the fades' arguments, tools/warps.py over 960 runs of the game's own, the self-test this to it; not actors_retire_marked, which warp_to's copy has not either
static func plan(d: Dictionary, block: Array, pitch: int) -> Dictionary:
	var lv := int(d["lock"])
	var same := lv == int(block[0])
	var first := [NO_LEVEL, NO_LEVEL, lv, NO_LEVEL, NO_LEVEL] if same \
		else [lv, lv, lv, NO_LEVEL, NO_LEVEL]
	var b := block.duplicate()
	for t in [first, [NO_LEVEL, NO_LEVEL, NO_LEVEL, int(d["b39"]), int(d["b3a"])]]:
		for k in 5:
			if int(t[k]) != NO_LEVEL:
				b[k] = int(t[k])
	return {"level": int(b[1]), "block": b, "same": same,
		"pos": [(int(d["b3b"]) << 11) + 0x400, -(int(d["b3d"]) << 7),
			(int(d["b3c"]) << 11) + 0x400],
		"facing": (-(int(d["b3e"]) << 4)) & 0xFFF, "pitch": pitch, "answer": 0,
		"out": [1, 0, 0x1000, 0x100], "back": [[1, 0x1000, 0x1000, 0], [1, 0x1000, 0, -0x100]],
		"clear": false, "tilt": false}


# Opcode 0xea's arm; tools/warps.py wrap_step. slide is world_slide. The arm's
# loop over the records of 0xe7 is not here: no level places one.
# @orig game:0x8004a5b8 object_interpreter+0x35a8  status:verified -- opcode 0xea's arm; tools/warps.py wrap_check, 320 of 320 runs of the game's own over the 8, the calls in order and all of RAM but the stack, the self-test this to it; grid_mark not called, the port's marks being worked out from where things stand
static func wrap(d: Dictionary, w: Dictionary) -> void:
	if not w["rect"].call(int(d["lock"]), int(d["b39"]), int(d["b3a"]), int(d["b3b"]), int(d["y"])):
		d["b40"] = 0
	elif int(d["b40"]) == 0:
		w["slide"].call(_cells(int(d["b3c"])), _cells(int(d["b3d"])))


# @port helper -- an s8 of cells, as the arm's lb and sll make it
static func _cells(v: int) -> int:
	return (v - 0x100 if v & 0x80 else v) << 11


# Opcode 0xeb's arm; tools/warps.py step. carry is the rest of it: every
# pad's +0x40 1 and the warp.
# @orig game:0x8004a2e0 object_interpreter+0x32d0  status:verified -- opcode 0xeb's arm; tools/warps.py, 960 of 960 runs of the game's own over the 16, the calls in order and all of RAM but the stack, the self-test this to it
static func step(d: Dictionary, w: Dictionary) -> void:
	if int(d["b3f"]) == 0:
		return
	if int(d["lock"]) != NO_LEVEL:
		if not w["rect"].call(int(d["x"]) >> 11, int(d["z"]) >> 11, 1, 1, int(d["y"])):
			d["b40"] = 0
		elif int(d["b40"]) == 0:
			w["carry"].call(d)
	if int(w["level"].call()) == TURNING_LEVEL:
		d["yaw"] = (int(d["yaw"]) + int(TURNS.get(int(d["type"]), 0))) & 0xFFFF

class_name KFTeleports
# Level 7's teleports: opcode 0xe8's arm, a rectangle of cells given outright
# (+0x38, +0x39, +0x3a by +0x3b, the height +0x18) and a place -- the cell
# +0x3c, +0x3d, the layer +0x3e (1 the lower, else the upper), the facing
# -(+0x3f << 4) -- and the pedestal that wakes them (slot 12, opcode 0xa7,
# the level's entry 9): Ichrius' key brought to rest on it clears every
# teleport's +0x40, which the loader leaves 0xff.
#
# Written as it is there, over the game's own addresses: `m` is KFLevelIn's
# {"mem", "calls"}, which godot/loot.gd fills from the port's fields and puts
# back. tools/teleports.py is the same in Python, with what each part does in
# prose, held to the game's own code; the self-test holds this to it.
#
# @exe game

const OP := 0xE8
const PEDESTAL_OP := 0xA7
const LAYER := 0x801B2644              # 0 the lower, 5 the upper
const FACING := 0x801B2612
const VIEW_YAW := 0x801B260A
const YAW_OFFSETS := [0x801B261A, 0x801B2622, 0x801B262A]   # the tilt's, the scene's, the nod's
const KEY_START := [0, -1600, 1024]    # overlay 7's 0x801e8908, where the key is set down
const KEY_END := [0, -1600, 256]       # 0x801e8910, where it comes to rest


# Opcode 0xe8's arm for the record in slot k. The player in its rectangle and
# its +0x40 0: every teleport's +0x40 1, the player at the place, the layer
# and the facing, and the calls the caller acts -- ["capture", 1] and
# ["capture", -1] around it (screen_capture, the frame kept), ["grid_mark",
# x, z, 0x320, -1] (the player's cells cleared), ["place"]
# (place_player_on_terrain) -- the view's yaw the facing with its three
# offsets on. Out of it, +0x40 other than 0xff back to 0. +0xa 0x40 on.
# @orig game:0x8004a66c object_interpreter+0x365c  status:verified -- opcode 0xe8's arm: tools/teleports.py, 480 of 480 runs of the game's own over level 7's twelve, the calls in order and all of RAM but the stack; the self-test this to it
static func arm(m: Dictionary, k: int) -> void:
	var r := KFLevelIn.O(k)
	var cx := KFLevelIn.rd(m, r + 0x38)
	var cz := KFLevelIn.rd(m, r + 0x39)
	var w := KFLevelIn.rd(m, r + 0x3A)
	var h := KFLevelIn.rd(m, r + 0x3B)
	var y := KFTicks.s32(KFLevelIn.rd(m, r + 0x18, 4))
	var px := KFTicks.s32(KFLevelIn.rd(m, KFTriggers.PLAYER_POS, 4))
	var py := KFTicks.s32(KFLevelIn.rd(m, KFTriggers.PLAYER_POS + 4, 4))
	var pz := KFTicks.s32(KFLevelIn.rd(m, KFTriggers.PLAYER_POS + 8, 4))
	if KFObjects.player_in_rect(px, pz, cx, cz, w, h, py, y):
		if KFLevelIn.rd(m, r + 0x40) == 0:
			m["calls"].append(["capture", 1])
			for j in KFLevelIn.COUNT:
				if KFLevelIn.rd(m, KFLevelIn.O(j, 4)) == OP:
					KFLevelIn.wr(m, KFLevelIn.O(j, 0x40), 1)
			m["calls"].append(["grid_mark", px & 0xFFFFFFFF, pz & 0xFFFFFFFF, 0x320, 0xFFFFFFFF])
			KFLevelIn.wr(m, KFTriggers.PLAYER_POS, (KFLevelIn.rd(m, r + 0x3C) << 11) + 0x400, 4)
			KFLevelIn.wr(m, KFTriggers.PLAYER_POS + 8, (KFLevelIn.rd(m, r + 0x3D) << 11) + 0x400, 4)
			KFLevelIn.wr(m, LAYER, 0 if KFLevelIn.rd(m, r + 0x3E) == 1 else 5, 2)
			KFLevelIn.wr(m, FACING, -(KFLevelIn.rd(m, r + 0x3F) << 4), 2)
			m["calls"].append(["place"])
			var yaw := KFLevelIn.rd(m, FACING, 2)
			for a in YAW_OFFSETS:
				yaw += KFLevelIn.rd(m, a, 2)
			KFLevelIn.wr(m, VIEW_YAW, yaw, 2)
			m["calls"].append(["capture", 0xFFFFFFFF])
	elif KFLevelIn.rd(m, r + 0x40) != 0xFF:
		KFLevelIn.wr(m, r + 0x40, 0)
	KFLevelIn.wr(m, r + 0xA, (KFLevelIn.rd(m, r + 0xA, 2) + 0x40) & 0xFFF, 2)

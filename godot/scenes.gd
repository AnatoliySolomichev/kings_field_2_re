class_name KFScenes
# The scenes: cutscene_step (0x80061940), the machine game_main runs every
# frame and player_controller's state 8 again; opcode 0xe4's arm, the
# rectangles that start one; and every level's entry 10, which the machine
# calls before the movie. A scene is a record of 52 bytes at seq_data
# (0x801e7edc + 52 * n): +0 the movie, +1 the mark that retires it, then
# the place the player is walked to (+0xc, +0x10, +0x14 and the view's three
# angles +4, +6, +8), the fade (+0xa, +0x22) and the place back (+0x24,
# +0x28, +0x2c, +0x1c, +0x1e, +0x20) -- player.gd walks them (states 7, 8, 9).
#
# Written as it is there, over the game's own addresses: `m` is KFLevelIn's
# {"mem", "calls"}, which godot/loot.gd fills from the port's fields and puts
# back. tools/scenes.py is the same in Python, with what each part does in
# prose, held to the game's own code; the self-test holds this to it.
#
# @exe game

const SEQ_DATA := 0x801E7EDC
const STRIDE := 52
const CUT_NUMBER := 0x801E8260
const CUT_RECORD := 0x801E825C
const CUT_PENDING := 0x801E824E
const CUT_PHASE := 0x801E824C
const FLAG_WARP := 0x5D                # level 24's entry 10: warp_to(0xc) after the movie
const PLAYER_STATE := 0x801B25E5
const SCENE_ARG := 0x801B266C          # the state's scene (named player_velocity)
const WALK := 0x801B266D               # the walk's count
const VIEW := 0x801B2610               # pitch, facing, roll, and the halfword after
const SAVED := 0x801B266E              # the same eight bytes, kept as a walk starts
const RESET_HALVES := [0x2648, 0x2646, 0x261C, 0x261A, 0x2618, 0x2624, 0x2622, 0x2620,
	0x262C, 0x262A, 0x2628]            # player_state_reset's, under 0x801b0000
const DRAW_BUFFER := 0x801AEAE8
const DRAW_ENV := 0x801A91BC
const DISP_ENV := 0x801A9274
const SCENE_OP := 0xE4
const ENTRY_SCENE := 10
const ENTRY_AFTER := 7
const LEVELS := [2, 4, 13, 17, 20, 24, 26]   # the levels whose entry 10 is not jr $ra

# The machine's own four (cutscene_number, cutscene_phase, cutscene_pending,
# cutscene_record), kept across frames and levels as the game's RAM keeps them
static var number := 0xFF
static var phase := 0
static var pending := 0
static var record := 0


# @port helper -- a halfword as the s16 lh reads
static func s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v & 0x8000 else v


# The three helpers that put the player into a scene's state with its
# number; 7 and 9 also zero the walk's count and keep the view's eight bytes.
# @orig game:0x80030810 player_to_scene  status:verified -- state 7, through tools/scenes.py step_check (the game's own run)
# @orig game:0x80030864 player_from_scene  status:verified -- state 9, through step_check
# @orig game:0x800307f4 player_in_scene  status:transcribed -- state 8, the state and the scene
static func player_state(m: Dictionary, st: int, n: int) -> void:
	KFLevelIn.wr(m, PLAYER_STATE, st)
	KFLevelIn.wr(m, SCENE_ARG, n)
	if st == 8:
		return
	KFLevelIn.wr(m, WALK, 0)
	for i in 8:
		KFLevelIn.wr(m, SAVED + i, KFLevelIn.rd(m, VIEW + i))


# player_state_reset over the bytes: state 0, the speeds, the view offsets.
# @port helper -- player_state_reset (player.gd _knock_end carries its marker) as the bytes step_check holds
static func state_reset(m: Dictionary) -> void:
	KFLevelIn.wr(m, PLAYER_STATE, 0)
	for lo in RESET_HALVES:
		KFLevelIn.wr(m, 0x801B0000 + int(lo), 0, 2)


# cutscene_step over `m`; `entry` is the level's entry n with k, called as
# entry.call(n, k). tools/scenes.py has the phases in prose.
# @orig game:0x80061940 cutscene_step  status:verified -- tools/scenes.py step_check, 960 of 960 runs of the game's own over six levels (the calls in order and all of RAM but the stack), its sub_80030810, sub_80030864 and player_state_reset run; the self-test this to it
static func step(m: Dictionary, entry: Callable) -> void:
	var n := KFLevelIn.rd(m, CUT_NUMBER)
	if n == 0xFF:
		return
	var rec := SEQ_DATA + STRIDE * n
	KFLevelIn.wr(m, CUT_RECORD, rec, 4)
	var ph := KFLevelIn.rd(m, CUT_PHASE, 2)
	if ph >= 0x11:
		return
	match ph:
		1:
			var b := KFLevelIn.rd(m, rec + 1)
			var v := 2
			if b != 0xFF:
				if b & 0x80:
					v = 2 if KFLevelIn.f(m, b & 0x7F) else 0x10
				else:
					v = 0x10 if KFLevelIn.f(m, b) else 2
			KFLevelIn.wr(m, CUT_PHASE, v, 2)
			if v == 2:
				player_state(m, 7, n)
		2:
			if s16(KFLevelIn.rd(m, CUT_PENDING, 2)) == 1:
				KFLevelIn.wr(m, CUT_PHASE, 4, 2)
			KFLevelIn.wr(m, CUT_PENDING, 0, 2)
		4:
			entry.call(ENTRY_SCENE, n)
			m["calls"].append(["str_play"])
			if KFLevelIn.f(m, FLAG_WARP) == 1:
				KFLevelIn.wr(m, KFLevelIn.F(FLAG_WARP), 2)
				KFLevelIn.wr(m, CUT_PENDING, 1, 2)
				KFLevelIn.wr(m, CUT_PHASE, 0, 2)
				KFLevelIn.wr(m, CUT_NUMBER, 0xFF)
				state_reset(m)
				var i := KFLevelIn.rd(m, DRAW_BUFFER)
				m["calls"].append(["move_image", (DISP_ENV + 20 * i) & 0xFFFFFFFF,
					s16(KFLevelIn.rd(m, DRAW_ENV + 92 * i, 2)) & 0xFFFFFFFF,
					s16(KFLevelIn.rd(m, DRAW_ENV + 2 + 92 * i, 2)) & 0xFFFFFFFF])
				m["calls"].append(["draw_sync", 0])
				m["calls"].append(["warp_to", 0xC])
			KFLevelIn.wr(m, CUT_PHASE, 8, 2)
			player_state(m, 9, n)
		8:
			if s16(KFLevelIn.rd(m, CUT_PENDING, 2)) == 1:
				KFLevelIn.wr(m, CUT_PHASE, 0, 2)
				entry.call(ENTRY_AFTER, n)
			KFLevelIn.wr(m, CUT_PENDING, 0, 2)
		16:
			KFLevelIn.wr(m, CUT_PHASE, 1, 2)


# Opcode 0xe4 for the record in slot k: a rectangle of cells (+0x14 >> 11,
# +0x1c >> 11, +0x38 by +0x39) naming scene +0x3a. No scene under way and the
# player in it: phase 1 and the number; its own scene, the player out and the
# phase 0 or 0x10: no scene.
# @orig game:0x8004a9a8 object_interpreter+0x3998  status:verified -- opcode 0xe4's arm: tools/scenes.py arm_check, 540 of 540 runs of the game's own arm over its nine rectangles, all of RAM but the stack; the self-test this to it
static func arm(m: Dictionary, k: int) -> void:
	var px := KFTicks.s32(KFLevelIn.rd(m, KFTriggers.PLAYER_POS, 4))
	var pz := KFTicks.s32(KFLevelIn.rd(m, KFTriggers.PLAYER_POS + 8, 4))
	var r := KFLevelIn.O(k)
	var cx := KFTicks.s32(KFLevelIn.rd(m, r + 0x14, 4)) >> 11
	var cz := KFTicks.s32(KFLevelIn.rd(m, r + 0x1C, 4)) >> 11
	var w := KFLevelIn.rd(m, r + 0x38)
	var h := KFLevelIn.rd(m, r + 0x39)
	var n := KFLevelIn.rd(m, CUT_NUMBER)
	if n == 0xFF:
		if KFObjects.player_in_rect(px, pz, cx, cz, w, h):
			KFLevelIn.wr(m, CUT_PHASE, 1, 2)
			KFLevelIn.wr(m, CUT_NUMBER, KFLevelIn.rd(m, r + 0x3A))
	elif n == KFLevelIn.rd(m, r + 0x3A):
		if not KFObjects.player_in_rect(px, pz, cx, cz, w, h):
			var ph := s16(KFLevelIn.rd(m, CUT_PHASE, 2))
			if ph == 0 or ph == 0x10:
				KFLevelIn.wr(m, CUT_NUMBER, 0xFF)


# @port helper -- stamp_rect's call as the levels' code makes it, for loot.gd to act
static func _stamp(m: Dictionary, args: Array) -> void:
	m["calls"].append(["stamp"] + args)


# The level's entry 10 with scene n, before its movie. tools/scenes.py has
# each level's in prose: the marks, level 13's creature 30 and object 20,
# level 17's objects and stamp, level 20's stamp and the sword (0x7d for
# 0x10), level 24's flag 0x5d.
# @orig game:0x80061a74 cutscene_step+0x134  status:verified -- the call of the level's entry 10 (level_hooks + 0x28) with the scene; every level's own out of its overlay, written out here as tools/scenes.py, which the overlays' own code holds (1680 of 1680 runs, the calls and all of RAM but the stack), the self-test this to it
static func entry10(lv: int, m: Dictionary, n: int) -> void:
	n &= 0xFF
	match lv:
		2:
			if n == 0xF:
				KFLevelIn.wr(m, KFLevelIn.F(0x6F), 1)
		4:
			if n == 0xC:
				KFLevelIn.wr(m, KFLevelIn.F(0x6D), 1)
		13:
			if n == 4 and KFLevelIn.f(m, 0x42):
				KFLevelIn.wr(m, KFLevelIn.O(20, 6), 0xFF, 2)
				KFLevelIn.wr(m, KFLevelIn.A(30), 8)
				KFLevelIn.wr(m, KFLevelIn.A(30, 9), 3)
			if n == 0xD:
				KFLevelIn.wr(m, KFLevelIn.F(0x6E), 1)
		17:
			if n == 9:
				KFLevelIn.wr(m, KFLevelIn.O(50), 0)
				for k in range(52, 62):
					KFLevelIn.wr(m, KFLevelIn.O(k), 2)
				_stamp(m, [2, 0x3B, 0x4C, 0x47, 0x30, 3, 4, 0, 0x2F])
				KFLevelIn.wr(m, KFLevelIn.A(56, 9), 0)
				KFLevelIn.wr(m, KFLevelIn.A(56), 2)
		20:
			if n == 5:
				_stamp(m, [2, 0x4D, 0, 0x26, 0xC, 3, 5, 0, 0x2F])
			if n == 0xA and KFLevelIn.has_item(m, 0x7D) > 0:
				KFDeaths.take_item(m, 0x7D)
				KFDeaths.give_item(lv, m, 0x10)
				KFLevelIn.wr(m, KFLevelIn.F(0x59), 1)
		24:
			KFLevelIn.wr(m, KFLevelIn.F(FLAG_WARP), 1)
		26:
			if n == 0xE:
				KFLevelIn.wr(m, KFLevelIn.F(0x70), 1)

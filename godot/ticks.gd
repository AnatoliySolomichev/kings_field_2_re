class_name KFTicks
# What a level does every frame: every level's own entry 1 (level_hooks + 4),
# which level_overlay_tick (0x8005eb20) calls first thing, once a frame of
# the game. Six levels have one -- level 0's flicker and the three men by the
# house, level 1's son gone home, level 2's lake and the aquarian boots,
# levels 8's and 17's creature that appears when the player looks away,
# level 26's flag by skill 3 -- the rest are `jr $ra`. And what the routine
# does after it, on any level: story flag 0x65 at 1 -- level 27's
# creature-death hook sets it (deaths.gd) -- becomes 2, and with flag 0x66
# the warp on to level 24 and scene 7, without it scene 8 and game_exit 4,
# the short ending (finale).
#
# Written as it is there, over the game's own addresses: `m` is KFLevelIn's
# {"mem", "calls"}, which godot/loot.gd fills from the port's fields and puts
# back. tools/ticks.py is the same in Python, held to the overlays' own code;
# the self-test holds this to it.
#
# @exe game

const PLAYER_POS := 0x801B25F0         # x, y, z
const VIEW_YAW := 0x801B260A           # view_angles + 2, s16
const FEET := 0x801B25D8               # equip_armour's slot 3
const SKILL_3 := 0x801B251E
const FLICKER := 0x8009C21C            # level 0's word: +1 or -1, 16 a step
const FAR := 0x191                     # 401: 20 cells, squared
const BOOTS := 0x4B                    # the aquarian boots
const SWITCH := 82                     # level 2's switch, opcode 0xa6
const STONES := 100                    # and its seventeen, opcode 0x5f, 100..116
const LEVELS := [0, 1, 2, 8, 17, 26]   # the levels whose entry 1 is not jr $ra
const FLAG_DONE := 0x65                # level 27's boss dead (deaths.gd)
const FLAG_ON := 0x66                  # and thing 0x10 was in the pack
const MUSIC_VOLUME := 0x801B25DC       # OPTION 1's music volume, a byte
const MUSIC_ON := 0x801B0A04
const MUSIC := 0x801B0A08              # the music's handle, s16
const MUSIC_STOP := [0x800677E8, 0x80071F9C, 0x80072CE8]   # the first also sets its volume
const LEVEL_CHANGE_BUSY := 0x8018FAD4
const DRAW_BUFFER := 0x801AEAE8
const DRAW_ENV := 0x801A91BC           # 92 bytes a buffer
const DISP_ENV := 0x801A9274           # 20 bytes a buffer
const CUT_NUMBER := 0x801E8260
const CUT_RECORD := 0x801E825C
const CUT_PENDING := 0x801E824E
const CUT_PHASE := 0x801E824C
const SCENES := {7: 0x801E8048, 8: 0x801E807C}   # seq_data + 52 * n; the record's first byte is n
const GAME_EXIT := 0x8009C3F8
const WARP_ON := 0xD                   # warp_to's record: level 24


# @port helper -- a word as the signed 32 bits the game keeps it in
static func s32(v: int) -> int:
	v &= 0xFFFFFFFF
	return v - 0x100000000 if v & 0x80000000 else v


# @port helper -- a halfword as the s16 lh reads
static func s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v & 0x8000 else v


# (a - b) / 2048 as C divides, toward 0: the cells from b to a.
# @port helper -- the division by 0x800 the levels' code does, toward 0
static func cells(a: int, b: int) -> int:
	var d := s32(a - b)
	return (d + 0x7FF if d < 0 else d) >> 11


# Levels 8's and 17's: creature k not in state 1, and the view (0x801b260a)
# not within 0x258 of the way to it -- state 0 and category 2, it appears.
# @port helper -- the two levels' one test, vec_angle and facing_test as the game's
static func _appear(m: Dictionary, k: int, angle: Callable) -> void:
	if KFLevelIn.rd(m, KFLevelIn.A(k, 9)) == 1:
		return
	var dx := s32(KFLevelIn.rd(m, KFLevelIn.A(k, 0x2C), 4) - KFLevelIn.rd(m, PLAYER_POS, 4))
	var dz := s32(KFLevelIn.rd(m, KFLevelIn.A(k, 0x34), 4) - KFLevelIn.rd(m, PLAYER_POS + 8, 4))
	var b := s16(int(angle.call(dx, dz)))
	if not KFCreatureAI.facing_test(s16(KFLevelIn.rd(m, VIEW_YAW, 2)), b, 0x258):
		KFLevelIn.wr(m, KFLevelIn.A(k, 9), 0)
		KFLevelIn.wr(m, KFLevelIn.A(k), 2)


# The level's entry 1 over `m`; `rand` answers as the game's rand, `angle`
# is vec_angle (collision.gd's). tools/ticks.py has what each level does in
# prose. Level 0's distance is the source's `dx ^ 2 + dz ^ 2`, which C reads
# as dx ^ (dz + 2) ^ 2 -- an exclusive or, kept here as the game runs it.
# @orig game:0x8005eb38 level_overlay_tick+0x18  status:verified -- the call of the level's entry 1 (level_hooks + 4) first thing in the frame's seventh call; every level's own out of its overlay, written out here as tools/ticks.py, which the overlays' own code holds (1680 of 1680 runs, all of RAM but the stack), the self-test this to it
static func entry1(lv: int, m: Dictionary, rand: Callable, angle: Callable) -> void:
	match lv:
		0:
			if int(rand.call()) < 0x2000:
				var a := KFLevelIn.O(158, 0x10)
				KFLevelIn.wr(m, a, KFLevelIn.rd(m, a, 2) + (KFLevelIn.rd(m, FLICKER, 4) << 4), 2)
			var v := KFLevelIn.rd(m, KFLevelIn.O(158, 0x10), 2)
			if v > 0x800:
				KFLevelIn.wr(m, FLICKER, -s32(KFLevelIn.rd(m, FLICKER, 4)), 4)
				if v >= 0x1000:
					KFLevelIn.wr(m, KFLevelIn.O(158, 0x10), 0, 2)
			if KFLevelIn.f(m, 1) and KFLevelIn.f(m, 2) and not KFLevelIn.f(m, 7):
				var dx := cells(KFLevelIn.rd(m, KFLevelIn.A(1, 0x2C), 4), KFLevelIn.rd(m, PLAYER_POS, 4))
				var dz := cells(KFLevelIn.rd(m, KFLevelIn.A(1, 0x34), 4), KFLevelIn.rd(m, PLAYER_POS + 8, 4))
				if s32(dx ^ (dz + 2) ^ 2) >= FAR:
					KFLevelIn.cats(m, [[0, 8], [1, 8], [2, 1]])
		1:
			if KFLevelIn.f(m, 0xA) and not KFLevelIn.f(m, 0xB):
				var dx := cells(KFLevelIn.rd(m, KFLevelIn.A(20, 0x2C), 4), KFLevelIn.rd(m, PLAYER_POS, 4))
				var dz := cells(KFLevelIn.rd(m, KFLevelIn.A(20, 0x34), 4), KFLevelIn.rd(m, PLAYER_POS + 8, 4))
				if s32(dx * dx + dz * dz) >= FAR:
					KFLevelIn.wr(m, KFLevelIn.F(0xB), 1)
					KFLevelIn.cats(m, [[20, 8], [10, 1], [25, 8], [23, 1], [24, 1], [40, 8]])
		2:
			var sw := KFLevelIn.O(SWITCH)
			if KFLevelIn.rd(m, FEET) != BOOTS:
				if KFLevelIn.rd(m, sw + 0x40) != 1:
					for k in range(STONES, STONES + 17):
						if KFLevelIn.rd(m, KFLevelIn.O(k, 0x3F)) != 1:
							KFLevelIn.wr(m, KFLevelIn.O(k, 0x3F), 1)
							KFLevelIn.wr(m, KFLevelIn.O(k, 8), 1, 2)
				KFLevelIn.wr(m, sw + 0x40, 1)
			else:
				if KFLevelIn.rd(m, sw + 8, 2) == 0 and KFLevelIn.rd(m, sw + 0x40):
					KFLevelIn.wr(m, sw + 8, 4, 2)
				KFLevelIn.wr(m, sw + 0x40, 0)
		8:
			# flags 0x2c and 0x2e: the word at 0x2c masked 0xff00ff
			if KFLevelIn.rd(m, KFLevelIn.F(0x2C), 4) & 0xFF00FF == 1:
				_appear(m, 1, angle)
		17:
			if KFLevelIn.f(m, 0x51) == 1:
				_appear(m, 15, angle)
			KFLevelIn.wr(m, KFLevelIn.A(56, 3), 0)
		26:
			if KFLevelIn.rd(m, SKILL_3, 2) and not KFLevelIn.f(m, 0x5F):
				KFLevelIn.wr(m, KFLevelIn.F(0x5F), 1)


# The music down by 2 a VSync from OPTION 1's volume, (v >> 1) VSyncs, on
# the handle at 0x801b0a08: the loop both branches below have (0x8005eb94,
# 0x8005ed2c).
# @port helper -- level_overlay_tick's two copies of one loop, written once
static func _music_down(m: Dictionary) -> void:
	var v := KFLevelIn.rd(m, MUSIC_VOLUME)
	for i in v >> 1:
		v -= 2
		var h := s16(KFLevelIn.rd(m, MUSIC, 2)) & 0xFFFFFFFF
		var a := v if v >= 0 else 0
		m["calls"].append(["music", MUSIC_STOP[0], h, a, a])
		m["calls"].append(["draw_sync", 0])
		m["calls"].append(["vsync", 0])


# cutscene_number n, its record, str_play (0x80061bc4), and the machine left
# at rest: cutscene_pending -1, the phase 0, the number 0xff.
# @port helper -- the two branches' scene, written once
static func _scene(m: Dictionary, n: int) -> void:
	KFLevelIn.wr(m, CUT_NUMBER, n)
	KFLevelIn.wr(m, CUT_RECORD, int(SCENES[n]), 4)
	m["calls"].append(["str_play"])
	KFLevelIn.wr(m, CUT_PENDING, 0xFFFF, 2)
	KFLevelIn.wr(m, CUT_PHASE, 0, 2)
	KFLevelIn.wr(m, CUT_NUMBER, 0xFF)


# @port helper -- the scene a record pointer names, -1 for none
static func scene_of(record: int) -> int:
	for n in SCENES:
		if int(SCENES[n]) == record:
			return int(n)
	return -1


# level_overlay_tick after the level's entry 1: flag 0x65 at 1 becomes 2;
# with flag 0x66, warp_to(0xd), the music down, the level loaded (res_wait,
# then res_upload_wait and a step of level_load while level_change_busy is
# 1 -- `level_load` is that step over `m`), scene 7, player_state_reset, the
# master volume up, object_trigger(0xff, 0xff, 0xff, 9, 0xb, 0x7f, 0x7f,
# 0x7f), the displayed buffer moved onto the one drawn, fade_frames(1, 0, 0,
# 0); without it, the music down and stopped, fade_frames(1, 0, 0x1000,
# 0x100), scene 8 and game_exit 4. tools/ticks.py has it in prose.
# @orig game:0x8005eb48 level_overlay_tick+0x28  status:verified -- the flag 0x65 branch, both ways: tools/ticks.py whole_check, 1120 of 1120 runs of GAME.EXE's own over every level (the calls in order and all of RAM but the stack), the self-test this to it
static func finale(m: Dictionary, level_load: Callable) -> void:
	if KFLevelIn.f(m, FLAG_DONE) != 1:
		return
	KFLevelIn.wr(m, KFLevelIn.F(FLAG_DONE), 2)
	if KFLevelIn.f(m, FLAG_ON):
		m["calls"].append(["warp_to", WARP_ON])
		_music_down(m)
		m["calls"].append(["res_wait"])
		while true:
			m["calls"].append(["res_upload_wait"])
			m["calls"].append(["level_load"])
			level_load.call(m)
			if s16(KFLevelIn.rd(m, LEVEL_CHANGE_BUSY, 2)) != 1:
				break
		_scene(m, 7)
		m["calls"].append(["player_state_reset"])
		m["calls"].append(["volume", 0x7F, 0x7F])
		m["calls"].append(["object_trigger", 0xFF, 0xFF, 0xFF, 9, 0xB, 0x7F, 0x7F, 0x7F])
		var i := KFLevelIn.rd(m, DRAW_BUFFER)
		m["calls"].append(["move_image", (DISP_ENV + 20 * i) & 0xFFFFFFFF,
			s16(KFLevelIn.rd(m, DRAW_ENV + 92 * i, 2)) & 0xFFFFFFFF,
			s16(KFLevelIn.rd(m, DRAW_ENV + 2 + 92 * i, 2)) & 0xFFFFFFFF])
		m["calls"].append(["draw_sync", 0])
		m["calls"].append(["fade_frames", 1, 0, 0, 0])
		m["calls"].append(["res_wait"])
	else:
		_music_down(m)
		m["calls"].append(["volume", 0, 0])
		if KFLevelIn.rd(m, MUSIC_ON, 4) == 1:
			var h := s16(KFLevelIn.rd(m, MUSIC, 2)) & 0xFFFFFFFF
			m["calls"].append(["music", MUSIC_STOP[0], h, 0, 0])
			m["calls"].append(["music", MUSIC_STOP[1], h])
			m["calls"].append(["music", MUSIC_STOP[2], h])
			KFLevelIn.wr(m, MUSIC_ON, 0, 4)
		m["calls"].append(["fade_frames", 1, 0, 0x1000, 0x100])
		_scene(m, 8)
		KFLevelIn.wr(m, GAME_EXIT, 4, 4)


# level_overlay_tick whole, seventh in game_main's frame: the level's own
# entry 1, then the finale.
# @orig game:0x8005eb20 level_overlay_tick  status:verified -- tools/ticks.py whole_check, 1120 of 1120 runs of GAME.EXE's own over every level, the level's entry 1 out of its overlay through the jalr (the rolls, the calls in order and all of RAM but the stack), the self-test this to it
static func overlay_tick(lv: int, m: Dictionary, rand: Callable, angle: Callable,
		level_load: Callable) -> void:
	entry1(lv, m, rand, angle)
	finale(m, level_load)

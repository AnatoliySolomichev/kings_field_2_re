class_name KFTicks
# What a level does every frame: every level's own entry 1 (level_hooks + 4),
# which level_overlay_tick (0x8005eb20) calls first thing, once a frame of
# the game. Six levels have one -- level 0's flicker and the three men by the
# house, level 1's son gone home, level 2's lake and the aquarian boots,
# levels 8's and 17's creature that appears when the player looks away,
# level 26's flag by skill 3 -- the rest are `jr $ra`.
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

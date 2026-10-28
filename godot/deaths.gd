class_name KFDeaths
# What a level does when one of its creatures dies: every level's own entry
# 19 (level_hooks + 0x4c), which actor_tick (0x80050868) calls with the
# creature once its body is gone and before it goes by its category (+0) --
# actors.gd _kill -- so a level that writes the dying creature's own +0
# changes how it goes. Thirteen levels have one: story flags, creatures
# held, locks lifted and objects started, level 12's object_signal, level
# 13's thirteen bits, level 15's two objects dissolved, and the two that end
# the game -- level 25's (the word at $gp+0x1e4 3: END.EXE, all three
# movies) and level 27's (flag 0x65, which level_overlay_tick turns into the
# short ending, or with thing 0x10 in the pack flag 0x66 and on).
#
# Written as it is there, over the game's own addresses: `m` is KFLevelIn's
# {"mem", "calls"}, which godot/loot.gd fills from the port's fields and puts
# back. tools/deaths.py is the same in Python, with what each level does in
# prose, held to the overlays' own code; the self-test holds this to it.
#
# @exe game

const EXIT := 0x8009C3F8               # $gp + 0x1e4: game_main stops on it
const SWING_CLOCK := 0x801B25A4        # s16
const PLAYER_STATE := 0x801B25E5
const IN_HAND := 0x801B25AF            # equipped_weapon
const MUSIC_ON := 0x801B0A04           # the music's word
const MUSIC := 0x801B0A08              # and its handle, s16
const MUSIC_STOP := [0x800677E8, 0x80071F9C, 0x80072CE8]   # on the handle, in turn
const LEVELS := [0, 1, 2, 6, 8, 11, 12, 13, 15, 17, 19, 25, 27]   # the rest are jr $ra


# @port helper -- a halfword as the s16 lh reads
static func s16(v: int) -> int:
	v &= 0xFFFF
	return v - 0x10000 if v & 0x8000 else v


# Level 15's 0x801e86d8 and level 17's 0x801e8924: n creatures from slot k
# category 8 -- held.
# @port helper -- the two overlays' one loop, written out
static func _held(m: Dictionary, k: int, n: int) -> void:
	for i in n:
		KFLevelIn.wr(m, KFLevelIn.A(k + i), 8)


# Level 15's 0x801e85b8: objects a and b +5 0x32 and +2 5, then sixteen
# frames of the game's own -- res_wait, res_upload_spu, res_upload_vram,
# camera_pose, render_frame -- with +0x10 up by 0x100 a frame (a halfword,
# so it turns over) and held to 0xfff, and both freed (+6 0xff).
# @port helper -- level 15's dissolve, written out; its frames are calls here
static func _dissolve(m: Dictionary, a: int, b: int) -> void:
	for k in [a, b]:
		KFLevelIn.wr(m, KFLevelIn.O(k, 5), 0x32)
	for k in [a, b]:
		KFLevelIn.wr(m, KFLevelIn.O(k, 2), 5)
	for i in 16:
		for k in [a, b]:
			KFLevelIn.wr(m, KFLevelIn.O(k, 0x10), KFLevelIn.rd(m, KFLevelIn.O(k, 0x10), 2) + 0x100, 2)
		for k in [a, b]:
			if KFLevelIn.rd(m, KFLevelIn.O(k, 0x10), 2) >= 0xFFF:
				KFLevelIn.wr(m, KFLevelIn.O(k, 0x10), 0xFFF, 2)
		for c in ["res_wait", "res_upload_spu", "res_upload_vram", "camera_pose", "render_frame"]:
			m["calls"].append([c])
	for k in [a, b]:
		KFLevelIn.wr(m, KFLevelIn.O(k, 6), 0xFF, 2)


# take_item over the bytes, as KFItems' (items.gd carries its marker): one
# from the first array that has one; the level's entry 11 is jr $ra.
# @port helper -- take_item over the pack as the game's bytes
static func take_item(m: Dictionary, item: int) -> void:
	for base in [KFLevelIn.INV_A, KFLevelIn.INV_B]:
		if KFLevelIn.rd(m, base + item):
			KFLevelIn.wr(m, base + item, KFLevelIn.rd(m, base + item) - 1)
			return


# give_item over the bytes, as KFItems': one more in the first array under
# 99 and the level's entry 6; both full, the banner.
# @port helper -- give_item over the pack as the game's bytes
static func give_item(lv: int, m: Dictionary, item: int) -> void:
	for base in [KFLevelIn.INV_A, KFLevelIn.INV_B]:
		if KFLevelIn.rd(m, base + item) < KFItems.CAP:
			KFLevelIn.wr(m, base + item, KFLevelIn.rd(m, base + item) + 1)
			KFLevelIn.entry6(lv, m)
			return
	m["calls"].append(["announce", KFItems.FULL_MESSAGE])


# The level's entry 19 over `m` for the creature in slot `k`.
# tools/deaths.py has what each level does in prose.
# @orig game:0x80050868 actor_tick+0x7c0  status:verified -- the call of the level's entry 19 (level_hooks + 0x4c) with the dying creature, before it goes by its category; every level's own out of its overlay, written out here as tools/deaths.py, which the overlays' own code holds (1680 of 1680 runs: the calls in order and all of RAM but the stack), the self-test this to it
static func entry19(lv: int, m: Dictionary, k: int) -> void:
	match lv:
		0:
			if k == 0x20 and not KFLevelIn.f(m, 8):
				KFLevelIn.wr(m, KFLevelIn.F(8), 1)
				KFLevelIn.lock_lift(m, 344, 0xF1)
		1:
			if (k == 0x18 or k == 0x28) and not KFLevelIn.f(m, 0xC):
				KFLevelIn.wr(m, KFLevelIn.F(0xC), 1)
		2:
			if k == 4:                                 # the lake's caretaker
				KFLevelIn.wr(m, KFLevelIn.F(0x15), 1)
				KFLevelIn.wr(m, KFLevelIn.O(82, 8), 1, 2)
				KFLevelIn.wr(m, KFLevelIn.O(82, 0x38), 3)
		6:
			if k == 3:
				KFLevelIn.wr(m, KFLevelIn.A(k), 1)
		8:
			if k == 1 and KFLevelIn.f(m, 0x2C) == 1:
				KFLevelIn.wr(m, KFLevelIn.F(0x2C), 2)
				KFLevelIn.wr(m, KFLevelIn.A(1), 8)
		11:
			if k == 3:
				KFLevelIn.wr(m, KFLevelIn.F(0x3C), 1)
				KFLevelIn.wr(m, KFLevelIn.O(20), 0)
				var link := KFLevelIn.rd(m, KFLevelIn.O(20, 0x3A), 2)
				KFLevelIn.wr(m, KFLevelIn.O(20, 0x3C), 0)
				if link != 0xFFFF and KFLevelIn.rd(m, KFLevelIn.O(link, 6), 2) != 0xFF:
					KFLevelIn.wr(m, KFLevelIn.O(link), 2)
					KFLevelIn.wr(m, KFLevelIn.O(link, 0x38), 0xFF)
				KFLevelIn.wr(m, KFLevelIn.O(33, 0x3E), 0)
		12:
			if k >= 0x32 and k <= 0x34 and not KFLevelIn.f(m, 0x3E + k - 0x32):
				KFLevelIn.wr(m, KFLevelIn.F(0x3E + k - 0x32), 1)
				KFLevelIn.signal_all(m, 0x64 + k - 0x32)
		13:
			if k < 13:
				var bit := 1 << k
				KFLevelIn.wr(m, KFLevelIn.F(0x44), KFLevelIn.f(m, 0x44) | bit)
				KFLevelIn.wr(m, KFLevelIn.F(0x45), KFLevelIn.f(m, 0x45) | (bit >> 8))
			if KFLevelIn.rd(m, KFLevelIn.F(0x44), 2) == 0x1FFF:
				KFLevelIn.wr(m, KFLevelIn.F(0x46), 1)
		15:
			if k == 3 and not KFLevelIn.f(m, 0x49):
				KFLevelIn.wr(m, KFLevelIn.F(0x49), 1)
				_held(m, 4, 2)
				_dissolve(m, 0x73, 0x74)
			elif k == 0x28 and not KFLevelIn.f(m, 0x4A):
				KFLevelIn.wr(m, KFLevelIn.F(0x4A), 1)
				_held(m, 0xA, 2)
				_dissolve(m, 0x75, 0x76)
		17:
			# slot: [flag, the creature held, the object started]
			var arms := {0xB: [0x4E, 0x10, 0x50], 0xC: [0x4F, 0x37, 0x51], 0xD: [0x50, 0x2E, 5]}
			if arms.has(k):
				var arm: Array = arms[k]
				if not KFLevelIn.f(m, int(arm[0])):
					KFLevelIn.wr(m, KFLevelIn.F(int(arm[0])), 1)
					_held(m, int(arm[1]), 1)
					# 0x801e8958 with 1: +0x3f 1 and state 1
					KFLevelIn.wr(m, KFLevelIn.O(int(arm[2]), 0x3F), 1)
					KFLevelIn.wr(m, KFLevelIn.O(int(arm[2]), 8), 1, 2)
			elif k == 0xF:
				if KFLevelIn.f(m, 0x51) == 1:
					KFLevelIn.wr(m, KFLevelIn.F(0x51), 2)
					KFLevelIn.wr(m, KFLevelIn.A(15), 8)
			elif k == 0x38:
				KFLevelIn.wr(m, KFLevelIn.A(56), 1)
				KFLevelIn.wr(m, KFLevelIn.A(56, 3), 0)
		19:
			if k == 0x14:
				KFLevelIn.wr(m, KFLevelIn.F(0x55), 1)
				KFLevelIn.wr(m, KFLevelIn.O(85, 0x3F), 0xFF)
				KFLevelIn.wr(m, KFLevelIn.O(85), 2)
		25:
			if k == 0 and not KFLevelIn.f(m, 0x67):
				KFLevelIn.wr(m, KFLevelIn.F(0x67), 1)
				KFLevelIn.wr(m, SWING_CLOCK, 0xFFFF, 2)
				for c in ["light_table_reset", "render_flags_reset", "light_table_step", "status"]:
					m["calls"].append([c])
				var v := 0x7D
				for i in 64:                           # the master volume down, a frame each
					var a := v if v >= 0 else 0
					m["calls"].append(["volume", a, a])
					m["calls"].append(["draw_sync", 0])
					m["calls"].append(["vsync", 0])
					v -= 2
				m["calls"].append(["volume", 0, 0])
				if KFLevelIn.rd(m, MUSIC_ON, 4) == 1:
					var h := s16(KFLevelIn.rd(m, MUSIC, 2)) & 0xFFFFFFFF
					m["calls"].append(["music", MUSIC_STOP[0], h, 0, 0])
					m["calls"].append(["music", MUSIC_STOP[1], h])
					m["calls"].append(["music", MUSIC_STOP[2], h])
					KFLevelIn.wr(m, MUSIC_ON, 0, 4)
				KFLevelIn.wr(m, EXIT, 3, 4)
				m["calls"].append(["fade_frames", 0x82, 0, 0x1000, 0x40])
		27:
			if k == 0 and KFLevelIn.rd(m, PLAYER_STATE) != 0x11:
				KFLevelIn.wr(m, KFLevelIn.F(0x65), 1)
				if KFLevelIn.has_item(m, 0x10) > 0:
					KFLevelIn.wr(m, KFLevelIn.F(0x66), 1)
					take_item(m, 0x10)
					give_item(lv, m, 0x11)
					if KFLevelIn.rd(m, IN_HAND) == 0x10:
						m["calls"].append(["equip_weapon", 0x11])

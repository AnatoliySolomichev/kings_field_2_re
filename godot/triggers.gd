class_name KFTriggers
# The rectangles that do something while the player is in them: opcode
# 0xe1's arm (0x8004a868) and every level's own entry 3 (level_hooks + 0xc),
# which the arm hands the record.
#
# Written as tools/triggers.py has them, over the game's own addresses (`m`
# is KFLevelIn's {"mem", "calls"}): godot/loot.gd fills it from the port's
# fields and puts back what changed, and acts out the calls -- ["stamp",
# ...] (stamp_rect), ["hit", slash, blow, stab, effect, m1..m5, scale, pct,
# point] (player_take_hit), ["hurt", point, near, radius, mode, edge, slash,
# blow, stab, effect, m1..m5, scale, pct] (effect_hurt_player), ["sound_at",
# ...], ["light", ...] (0x8005d948), ["equip_armour", id, slot], ["recalc"],
# ["frame"] (a frame of the game, render_frame), ["hook", "give" | "take"],
# ["announce", code]. The self-test holds this to tools/triggers.py, which
# the game's own arm and the overlays' own entry 3 hold.
#
# @exe game

const OP := 0xE1                      # the trigger rectangle's opcode
const WARPED := 0x801B25EE            # warp_to's own byte: the player came by a warp
const PLAYER_POS := 0x801B25F0
const PLAYER_STATE := 0x801B25E5
const IN_HAND := 0x801B25D8           # equip_armour slot 3's byte, the feet
const SLOT_4 := 0x801B25D6            # equip_armour slot 4's, the shield
const FLAG_BASE := 0xA7               # mode 2's story flags
# the warp's arrival on each level (selector 10): the rectangle, the template
# the three cells come from in it (having warped) and out of it, and the rest
# of stamp_rect's arguments: [sz, dx, dz, w, h]
const ARRIVALS := {
	0: [[9, 0x37, 3, 3], 0x4A, 0x4D, [0, 9, 0x37, 3, 1]],
	1: [[0x1C, 6, 9, 0xB], 0x48, 0x4B, [0, 0x1F, 0x10, 3, 1]],
	2: [[0x38, 0x23, 3, 3], 0x4A, 0x4D, [0, 0x38, 0x25, 3, 1]],
	3: [[6, 0x1E, 3, 4], 0x4A, 0x4D, [0, 6, 0x21, 3, 1]],
	4: [[0x37, 0xC, 3, 3], 0x4A, 0x4D, [0, 0x37, 0xC, 3, 1]],
	5: [[0x1C, 0x1E, 3, 4], 0x4A, 0x4D, [0, 0x1C, 0x21, 3, 1]],
	6: [[0x1F, 0x41, 7, 0xC], 0x4A, 0x4D, [4, 0x21, 0x41, 3, 1]],
	7: [[0x12, 0x1C, 3, 3], 0x15, 0x18, [0x4F, 0x12, 0x1E, 3, 1]],
	9: [[0x24, 0x36, 7, 0xC], 0x2A, 0x2D, [0x4F, 0x26, 0x36, 3, 1]],
	10: [[0x24, 0x32, 3, 3], 0x4A, 0x4D, [5, 0x24, 0x32, 3, 1]],
	11: [[0x39, 0x21, 3, 3], 0x4A, 0x4D, [0, 0x39, 0x23, 3, 1]],
}


# @port helper -- a signed word out of the bytes
static func s32(v: int) -> int:
	v &= 0xFFFFFFFF
	return v - 0x100000000 if v >= 0x80000000 else v


# player_in_rect (0x80046884) over the bytes: the player's own cell in the
# rectangle, and unless `y` is 0x8000 the height near it.
# @orig game:0x80046884 player_in_rect  status:verified -- through opcode 0xe1 and the levels' entry 3, tools/triggers.py against the game's own
static func in_rect(m: Dictionary, cx: int, cz: int, w: int, h: int, y := 0x8000) -> bool:
	var px := s32(KFLevelIn.rd(m, PLAYER_POS, 4)) >> 11
	var pz := s32(KFLevelIn.rd(m, PLAYER_POS + 8, 4)) >> 11
	if not (px >= cx and px < cx + w and pz >= cz and pz < cz + h):
		return false
	if y == 0x8000:
		return true
	var py := s32(KFLevelIn.rd(m, PLAYER_POS + 4, 4))
	return not (y + 0x800 < py) and not (py < y - 0xC80)


# Opcode 0xe1's arm for record `k`: in its rectangle (+0x14, +0x1c in
# cells, +0x38 by +0x39, +0x18 the height) and not yet fired (+0x40) -- +0x3a
# bit 7 clear sets +0x40 first -- by +0x3a & 0xf the level's entry 3, the
# signal +0x3b, or story flag 0xa7 + +0x3b set to +0x3c; out of it +0x40
# cleared.
# @orig game:0x8004a868 object_interpreter+0x3858  status:verified -- opcode 0xe1's arm, tools/triggers.py against the game's own over every level's records, the self-test this to it
static func arm(lv: int, m: Dictionary, k: int) -> void:
	var O := KFLevelIn.O(k)
	var x := s32(KFLevelIn.rd(m, O + 0x14, 4)) >> 11
	var z := s32(KFLevelIn.rd(m, O + 0x1C, 4)) >> 11
	if not in_rect(m, x, z, KFLevelIn.rd(m, O + 0x38), KFLevelIn.rd(m, O + 0x39),
			s32(KFLevelIn.rd(m, O + 0x18, 4))):
		KFLevelIn.wr(m, O + 0x40, 0)
		return
	if KFLevelIn.rd(m, O + 0x40):
		return
	var mode := KFLevelIn.rd(m, O + 0x3A)
	if not (mode & 0x80):
		KFLevelIn.wr(m, O + 0x40, 1)
	match mode & 0xF:
		0:
			entry3(lv, m, k)
		1:
			KFLevelIn.signal_all(m, KFLevelIn.rd(m, O + 0x3B))
		2:
			KFLevelIn.wr(m, KFLevelIn.F(FLAG_BASE + KFLevelIn.rd(m, O + 0x3B)), KFLevelIn.rd(m, O + 0x3C))


# The warp's arrival (selector 10): in the level's rectangle having warped,
# the three cells from the one template; out of it, from the other, and the
# warp's byte cleared.
# @port helper -- the arrival stretch the levels' entry 3 share, split out
static func arrival(lv: int, m: Dictionary) -> void:
	var a: Array = ARRIVALS[lv]
	var rect: Array = a[0]
	var sx := 0
	if in_rect(m, rect[0], rect[1], rect[2], rect[3]):
		if KFLevelIn.rd(m, WARPED) == 0:
			return
		sx = int(a[1])
	else:
		sx = int(a[2])
		KFLevelIn.wr(m, WARPED, 0)
	var rest: Array = a[3]
	m["calls"].append(["stamp", 2, sx, rest[0], rest[1], rest[2], rest[3], rest[4], 0, 0x2F])


# take_item (0x8005d7f8) over the bytes: one from the first array that has
# one, and the level's entry 11.
# @port helper -- KFItems.take_item, which is the game's, over the bytes
static func take(m: Dictionary, item: int) -> void:
	for base in [KFLevelIn.INV_A, KFLevelIn.INV_B]:
		if KFLevelIn.rd(m, base + item):
			KFLevelIn.wr(m, base + item, KFLevelIn.rd(m, base + item) - 1)
			m["calls"].append(["hook", "take"])
			return


# give_item (0x8005d898) over the bytes: one more in the first array under
# 99 and the level's entry 6; both full, announce 0xb.
# @port helper -- KFItems.give_item, which is the game's, over the bytes
static func give(m: Dictionary, item: int) -> void:
	for base in [KFLevelIn.INV_A, KFLevelIn.INV_B]:
		if KFLevelIn.rd(m, base + item) < 0x63:
			KFLevelIn.wr(m, base + item, KFLevelIn.rd(m, base + item) + 1)
			m["calls"].append(["hook", "give"])
			return
	m["calls"].append(["announce", 0xB])


# The level's entry 3 with record `k`, by the record's +0x3b (tools/triggers.py
# has what each level does in prose).
# @orig game:0x8004a8f8 object_interpreter+0x38e8  status:verified -- the call of the level's entry 3 (level_hooks + 0xc) with the record; every level's own entry 3 out of its overlay, written out here as tools/triggers.py, which the overlays' own code holds, the self-test this to it
static func entry3(lv: int, m: Dictionary, k: int) -> void:
	var O := KFLevelIn.O(k)
	var sel := KFLevelIn.rd(m, O + 0x3B)
	var calls: Array = m["calls"]
	match lv:
		0:
			if sel != 0 and sel != 10:
				return
			if sel == 0 and KFLevelIn.f(m, 6) == 1 and KFLevelIn.f(m, 7) == 0:
				for i in 3:
					KFLevelIn.wr(m, KFLevelIn.A(i), 8)
				KFLevelIn.wr(m, KFLevelIn.O(214), 2)
				KFLevelIn.wr(m, KFLevelIn.O(214, 0x3C), 0xFF)
				KFLevelIn.wr(m, KFLevelIn.O(177, 0x3E), 0xFF)
				KFLevelIn.wr(m, KFLevelIn.O(111), 0)
				KFLevelIn.wr(m, KFLevelIn.O(111, 0x3C), 0)
				KFLevelIn.wr(m, KFLevelIn.O(182, 0x3E), 0)
				for i in [62, 195, 172]:
					KFLevelIn.wr(m, KFLevelIn.O(i), 2)
					KFLevelIn.wr(m, KFLevelIn.O(i, 0x38), 0xFF)
			arrival(lv, m)
		1, 3, 5, 7, 10, 11:
			if sel == 10:
				arrival(lv, m)
		2:
			if sel == 0:
				if KFLevelIn.f(m, 0x12) == 0 and KFLevelIn.rd(m, KFLevelIn.O(44, 0x38)) != 0x9A:
					KFLevelIn.wr(m, KFLevelIn.O(44, 0x38), 0x9A)
			elif sel == 1:
				if KFLevelIn.rd(m, KFLevelIn.O(44, 0x38)) == 0x9A:
					KFLevelIn.wr(m, KFLevelIn.O(44, 0x38), 0xFF)
			elif sel == 10:
				arrival(lv, m)
		4:
			if sel == 0:
				if KFLevelIn.f(m, 0x19) == 0:
					KFLevelIn.wr(m, KFLevelIn.O(115, 0x14), s32(KFLevelIn.rd(m, O + 0x14, 4)) - 0x400, 4)
			elif sel == 1:
				KFLevelIn.wr(m, KFLevelIn.O(115, 0x14), s32(KFLevelIn.rd(m, O + 0x14, 4)) + 0x3FF, 4)
			elif sel == 10:
				arrival(lv, m)
		6:
			if sel == 0:
				var sx := 0x4A if KFLevelIn.rd(m, IN_HAND) == 0x4B else 0x44
				calls.append(["stamp", 2, sx, 5, 0x3A, 0x35, 6, 2, 0, 0x2F])
			elif sel == 10:
				arrival(lv, m)
		9:
			_level9(m, sel)
		14:
			if sel == 0x62:
				var x := s32(KFLevelIn.rd(m, O + 0x14, 4)) >> 11
				var z := s32(KFLevelIn.rd(m, O + 0x1C, 4)) >> 11
				if not in_rect(m, x, z, KFLevelIn.rd(m, O + 0x38), KFLevelIn.rd(m, O + 0x39),
						s32(KFLevelIn.rd(m, O + 0x18, 4)) + 0xC80):
					return
			if sel == 0x62 or sel == 0x63:
				calls.append(["hit", 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0])
		17:
			_level17(m, sel)
		26:
			if sel == 0:
				if KFLevelIn.f(m, 0x5E) != 1:
					KFLevelIn.wr(m, KFLevelIn.F(0x5E), 1)
			elif sel == 1:
				if KFLevelIn.f(m, 0x61) != 1:
					KFLevelIn.wr(m, KFLevelIn.F(0x61), 1)
					calls.append(["recalc"])
			elif sel == 2:
				if KFLevelIn.f(m, 0x61) != 0:
					KFLevelIn.wr(m, KFLevelIn.F(0x61), 0)
					calls.append(["recalc"])


# Level 9's: the bridge and slot 2 by flag 0x34 (0), object 58 lifted over
# sixteen frames of the game by flags 0x7b..0x7e and 0x35 (1), the arrival (10).
# @port helper -- level 9's entry 3, split out of entry3
static func _level9(m: Dictionary, sel: int) -> void:
	var calls: Array = m["calls"]
	if sel == 0:
		if KFLevelIn.f(m, 0x34) == 1 and not in_rect(m, 0x36, 0xF, 0xA, 4):
			KFLevelIn.wr(m, KFLevelIn.A(2), 8)
			KFLevelIn.wr(m, KFLevelIn.O(249), 2)
			KFLevelIn.wr(m, KFLevelIn.O(249, 0x3C), 0xFF)
			KFLevelIn.wr(m, KFLevelIn.O(262, 0x3E), 0xFF)
	elif sel == 1:
		var v := KFLevelIn.f(m, 0x35)
		if v == 0:
			var all4 := true
			for i in [0x7B, 0x7C, 0x7D, 0x7E]:
				all4 = all4 and KFLevelIn.f(m, i) != 0
			if all4:
				KFLevelIn.wr(m, KFLevelIn.F(0x35), 1)
			KFLevelIn.wr(m, KFLevelIn.O(58), 2)
			var at := KFLevelIn.O(58, 0x14)
			if KFLevelIn.rd(m, PLAYER_STATE) == 0x10:
				calls.append(["sound_at", 0x28, at, 0x78, 0])
			calls.append(["hurt", at, 0, 0x1000, 0x8000, 0x1000, 0x40, 0x40, 0x40, 0x40, 0x40,
				0x40, 0x40, 0x40, 0x40, 0x400, 0xA])
		elif v == 1:
			KFLevelIn.wr(m, KFLevelIn.O(58), 2)
			KFLevelIn.wr(m, KFLevelIn.O(58, 5), 0x32)
			KFLevelIn.wr(m, KFLevelIn.O(58, 2), 5)
			KFLevelIn.wr(m, KFLevelIn.O(58, 0x10), 0, 2)
			for _i in 16:
				KFLevelIn.wr(m, KFLevelIn.O(58, 0x10), KFLevelIn.rd(m, KFLevelIn.O(58, 0x10), 2) + 0x100, 2)
				if KFLevelIn.rd(m, KFLevelIn.O(58, 0x10), 2) >= 0xFFF:
					KFLevelIn.wr(m, KFLevelIn.O(58, 0x10), 0xFFF, 2)
				calls.append(["frame"])
			KFLevelIn.wr(m, KFLevelIn.O(58, 6), 0xFF, 2)
			KFLevelIn.wr(m, KFLevelIn.O(58, 4), 0xFF)
			KFLevelIn.wr(m, KFLevelIn.O(58), 0)
			KFLevelIn.wr(m, KFLevelIn.F(0x35), 2)
		else:
			KFLevelIn.wr(m, KFLevelIn.O(58, 6), 0xFF, 2)
			KFLevelIn.wr(m, KFLevelIn.O(58, 4), 0xFF)
			KFLevelIn.wr(m, KFLevelIn.O(58), 0)
	elif sel == 10:
		arrival(9, m)


# Level 17's: flag 0x51 (0), the armour 0x39 for 0x38 in the light (1), the
# seals' burns while flags 0x4e..0x50 are clear (0x61), a burn at the player
# (0x63).
# @port helper -- level 17's entry 3, split out of entry3
static func _level17(m: Dictionary, sel: int) -> void:
	var calls: Array = m["calls"]
	match sel:
		0:
			if KFLevelIn.f(m, 0x51) == 0:
				KFLevelIn.wr(m, KFLevelIn.F(0x51), 1)
		1:
			if KFLevelIn.has_item(m, 0x38) > 0:
				calls.append(["light", 0x200, 0, 0, 0, 0x64, 0x64, 0x64])
				if KFLevelIn.rd(m, SLOT_4) == 0x38:
					calls.append(["equip_armour", 0x39, 4])
				take(m, 0x38)
				give(m, 0x39)
				calls.append(["light", 0x200, 0x64, 0x64, 0x64, 0, 0, 0])
		0x61:
			for i in [0x4E, 0x4F, 0x50]:
				if KFLevelIn.f(m, i) == 0:
					calls.append(["hit", 0, 0, 0, 0x40, 0, 0x63, 0, 0, 0, 0, 0, 0])
		0x63:
			calls.append(["hit", 0, 0, 0, 0x43, 0, 0, 0, 0, 0, 0, 0, PLAYER_POS])

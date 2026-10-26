class_name KFLevelIn
# What a level does as it comes in: every level's own entry 5
# (level_hooks + 0x14), which level_load (0x800188f0) and enter_current_level
# (0x80017a88) call once the level and its record are in.
#
# The levels' code is stores at fixed addresses under conditions on the
# story flags, the pack and a few of the objects' own bytes -- which creature
# appears (an actor's +0, its category: 8 held, 1 up), which door is unlocked,
# which object is there (+6 0xff gone, +0 the view byte), which cells a
# stamp_rect lays -- and every level ends by writing its number into story
# flag 0x85. So it is written here as it is there, over the game's own
# addresses: `m` is {"mem": {address: byte}, "calls": []}, rd and wr read and
# write it, and godot/loot.gd fills it from the port's fields and puts back
# what changed. tools/levelin.py is the same in Python, held to the
# overlays' own code; the self-test holds this to it.
#
# @exe game

const ACTORS := 0x80185DA8
const ASTRIDE := 0x88
const OBJECTS := 0x80191A5C
const OSTRIDE := 0x44
const COUNT := 0x18C
const FLAGS := 0x801BA988
const INV_A := 0x800C85E8
const INV_B := 0x800C867E
const STAT36 := 0x801B2516
const SKILLS := 0x801B2518
const PLAYER_LEVEL := 0x801B24F0
const DROP_COUNT := 0x8019839A
const LAST_LEVEL := 0x85               # story flag 0x85, 0x801baa0d: the level last come into
const LOOT := preload("res://loot.gd")


# @port helper -- an actor's byte's address
static func A(k: int, off := 0) -> int:
	return ACTORS + ASTRIDE * k + off


# @port helper -- an object's byte's address
static func O(k: int, off := 0) -> int:
	return OBJECTS + OSTRIDE * k + off


# @port helper -- a story flag's address
static func F(k: int) -> int:
	return FLAGS + k


# @port helper -- n bytes at a, little-endian; what the caller did not fill reads 0
static func rd(m: Dictionary, a: int, n := 1) -> int:
	var mem: Dictionary = m["mem"]
	var v := 0
	for i in n:
		v |= int(mem.get(a + i, 0)) << (8 * i)
	return v


# @port helper -- v into n bytes at a
static func wr(m: Dictionary, a: int, v: int, n := 1) -> void:
	var mem: Dictionary = m["mem"]
	for i in n:
		mem[a + i] = (v >> (8 * i)) & 0xFF


# @port helper -- a story flag
static func f(m: Dictionary, k: int) -> int:
	return rd(m, F(k))


# has_item (0x8005d7bc): both arrays' counts.
# @orig game:0x8005d7bc has_item  status:transcribed
static func has_item(m: Dictionary, item: int) -> int:
	return rd(m, INV_A + item) + rd(m, INV_B + item)


# @port helper -- categories, [slot, value] pairs
static func cats(m: Dictionary, pairs: Array) -> void:
	for p in pairs:
		wr(m, A(int(p[0])), int(p[1]))


# @port helper -- an object's lock, if it is `want`, lifted
static func lock_lift(m: Dictionary, k: int, want: int) -> void:
	if rd(m, O(k, 0x38)) == want:
		wr(m, O(k, 0x38), 0xFF)


# 0x800466e8: key_test (0x80046608) with `key` on every object.
# @orig game:0x800466e8 key_test_all  status:verified -- through levels 9's and 26's entry 5, tools/levelin.py against the overlays' own code; the self-test this to it
static func key_test_all(m: Dictionary, key: int) -> void:
	if key & 0xFF == 0xFF:
		return
	for k in COUNT:
		var r := {"op": rd(m, O(k, 4)), "state": rd(m, O(k, 8), 2), "lock": rd(m, O(k, 0x38))}
		LOOT.key_test(r, "lock", key & 0xFF)
		wr(m, O(k, 0x38), int(r["lock"]))


# object_signal (0x800463bc) over the records' bytes: KFUseItem's.
# @port helper -- KFUseItem.object_signal over the records as bytes
static func signal_all(m: Dictionary, sig: int) -> void:
	var objs := []
	for k in COUNT:
		objs.append({"op": rd(m, O(k, 4)), "state": rd(m, O(k, 8), 2), "lock": rd(m, O(k, 0x38)),
			"b39": rd(m, O(k, 0x39)), "h3a": rd(m, O(k, 0x3A), 2), "b3d": rd(m, O(k, 0x3D)),
			"b3f": rd(m, O(k, 0x3F))})
	KFUseItem.object_signal({"objects": objs}, sig)
	for k in COUNT:
		var o: Dictionary = objs[k]
		wr(m, O(k, 8), int(o["state"]), 2)
		wr(m, O(k, 0x38), int(o["lock"]))
		wr(m, O(k, 0x39), int(o["b39"]))
		wr(m, O(k, 0x3F), int(o["b3f"]))


# find_free_slot (0x80046034) over the records' bytes: the slot, or -1.
# @orig game:0x80046034 find_free_slot  status:verified -- through level 17's entry 5, tools/levelin.py against the overlay's own code
static func free_slot(m: Dictionary, start: int, count: int, counter: int) -> int:
	var chosen := -1
	var age := 0
	for k in range(start, start + count):
		if rd(m, O(k, 6), 2) == 0xFF:
			return k
		var d := counter - rd(m, O(k, 0x3C), 2)
		if d < 0:
			d += 0x10000
		if age < d:
			chosen = k
			age = d
	return chosen


# init_object_record (0x800448b8).
# @orig game:0x800448b8 init_object_record  status:verified -- through level 17's entry 5, tools/levelin.py against the overlay's own code
static func init_record(m: Dictionary, k: int) -> void:
	wr(m, O(k, 1), 0x80)
	for off in [0x30, 0x2E, 0x2C]:
		wr(m, O(k, off), 0x1000, 2)
	for off in [0xA, 0x28, 0x24, 0x26, 0xE, 0x10]:
		wr(m, O(k, off), 0, 2)
	wr(m, O(k, 2), 0)
	wr(m, O(k), 0)
	wr(m, O(k, 4), 0xFF)
	wr(m, O(k, 5), 0xFF)


# The level's entry 5 over `m`. tools/levelin.py has what each level does in
# prose; the calls it makes that are not stores are ["stamp", b0, sx, sz,
# dx, dz, w, h, angle, mask] (stamp_rect) and ["look", routine, a0..a3] (the
# level's own routines that change its look, levels 4, 6 and 26).
# @orig game:0x80017a74 enter_current_level+0x108  status:verified -- the same call as a game starts or a save comes in
# @orig game:0x800188d4 level_load+0x57c  status:verified -- the call of the level's entry 5 (level_hooks + 0x14) as a level comes in; every level's own entry 5 out of its overlay, written out here as tools/levelin.py, which the overlays' own code holds (N of N runs, all of RAM but the stack), the self-test this to it
static func entry5(lv: int, m: Dictionary) -> void:
	var calls: Array = m["calls"]
	match lv:
		0:
			if f(m, 0x16):
				for k in [70, 33, 116]:
					lock_lift(m, k, 0xC8)
			var men := [8, 8, 8]
			var x := 0               # 0 the five off, 2 the first three on, 0xff the second
			if f(m, 0x1E) == 0:
				men = [1, 8, 8]
			elif f(m, 0x2) == 0:
				men = [8, 1, 8]
			elif f(m, 0x6) == 0:
				men = [8, 8, 1]
			elif f(m, 0x7) == 0:
				x = 2
			else:
				x = 0xFF
			cats(m, [[0, men[0]], [1, men[1]], [2, men[2]]])
			var on := 2 if x == 2 else 0
			var fl := 0xFF if x == 2 else 0
			wr(m, O(214), on)
			wr(m, O(214, 0x3C), fl)
			wr(m, O(177, 0x3E), fl)
			wr(m, O(111), 2 if x == 0xFF else 0)
			wr(m, O(111, 0x3C), 0xFF if x == 0xFF else 0)
			wr(m, O(182, 0x3E), 0xFF if x == 0xFF else 0)
			for k in [62, 195, 172]:
				wr(m, O(k), on)
				wr(m, O(k, 0x38), fl)
			var all4 := has_item(m, 2) > 0 and has_item(m, 0x82) > 0 and has_item(m, 0x83) > 0 and has_item(m, 0x84) > 0
			wr(m, F(3), 1 if all4 else 0)
			if f(m, 0x8) and rd(m, O(344, 0x38)) == 0xF1:
				wr(m, O(344, 0x38), 0xFF)
			if rd(m, O(158, 5)) == 0xFF:
				wr(m, O(158, 5), 0x3F)
				wr(m, O(158, 2), 7)
				wr(m, O(158, 0x10), 0x800, 2)
			wr(m, F(LAST_LEVEL), 0)
		1:
			if f(m, 0xA):
				cats(m, [[20, 8], [10, 1], [25, 8], [23, 1], [24, 1], [40, 8]])
				lock_lift(m, 71, 0xC8)
				cats(m, [[22, 8], [39, 1]])
			else:
				cats(m, [[20, 1], [10, 8], [25, 1], [23, 8], [24, 1], [40, 8], [22, 1], [39, 8]])
			if f(m, 0x20):
				cats(m, [[24, 8], [40, 1]])
			else:
				cats(m, [[24, 1], [40, 8]])
			var sx := 0x4E if f(m, 0xC) == 0 and f(m, 0xD) != 0 else 0x4F
			calls.append(["stamp", 2, sx, 0, 0x1B, 0x11, 1, 7, 0, 0x2F])
			var v := f(m, 0x38)
			if v == 1:
				wr(m, F(0x38), 2)
				wr(m, A(42), 8)
				wr(m, O(276, 0x38), 0x90)
			elif v == 2:
				wr(m, A(42), 8)
			wr(m, F(LAST_LEVEL), 1)
		2:
			if f(m, 0x7D):
				wr(m, O(70, 6), 0xFF, 2)
				wr(m, O(91, 6), 0xFF, 2)
				wr(m, F(0x12), 1)
			if f(m, 0x12):
				wr(m, A(4), 8)
				wr(m, O(44, 0x38), 0xFF)
			elif rd(m, O(44, 0x38)) != 0x9A:
				wr(m, O(44, 0x38), 0x9A)
			if f(m, 0x15):
				wr(m, O(82, 8), 1, 2)
				wr(m, O(82, 0x38), 3)
			if f(m, 0x14) < 2:
				wr(m, F(0x14), f(m, 0x14) + 1)
			wr(m, F(LAST_LEVEL), 2)
		3:
			wr(m, F(0x75), 1)
			wr(m, F(LAST_LEVEL), 3)
		4:
			if f(m, 0x19):
				cats(m, [[7, 8], [26, 1]])
				wr(m, O(141, 6), 0xFF, 2)
				wr(m, O(159, 6), 0xFF, 2)
				if rd(m, O(74, 0x38)) < 0xFD:
					wr(m, O(74, 0x38), 0xFF)
				calls.append(["look", 0x801E83A4, 0x801E8E74, 0x801E8EA4, 0x8008255C, 0x1000])
			else:
				cats(m, [[7, 1], [26, 8]])
				calls.append(["look", 0x801E83A4, 0x801E8E74, 0x801E8EA4, 0x8008255C, 0])
			if f(m, 0x7B):
				wr(m, O(55, 6), 0xFF, 2)
				wr(m, O(148, 6), 0xFF, 2)
			wr(m, F(LAST_LEVEL), 4)
		5:
			if f(m, 0x1C) == 0:
				wr(m, F(0x1C), 1)
			if f(m, 0xA):
				wr(m, F(0x20), 1)
			if f(m, 0x1E):
				for k in COUNT:
					if rd(m, O(k, 4)) == 0x56:
						for off in [0x30, 0x2E, 0x2C]:
							wr(m, O(k, off), 0, 2)
						wr(m, O(k, 0x38), 0)
						wr(m, O(k), 0)
						wr(m, O(k, 4), 0xFF)
			wr(m, F(LAST_LEVEL), 5)
		6:
			var strong := rd(m, STAT36, 2) >= 0x32
			for k in 5:
				strong = strong and rd(m, SKILLS + 2 * k, 2) >= 0x32
			if strong:
				wr(m, F(0x26), 1)
			var n := 0
			var v3 := 8
			var v0 := 1
			var v1 := 8
			var rest := 1
			var on := 0
			var off91 := -1
			if f(m, 0x23) == 0:
				pass
			elif f(m, 0x32) == 0:
				wr(m, F(0x25), 1)
				n = 0x10
				v3 = 1
				v0 = 8
				v1 = 1
				rest = 8
				off91 = 0
			else:
				v0 = 8
				v1 = 1
				on = 2
				off91 = 0
			for t in [[0x801E8CE8, 0x8008246C], [0x801E8D18, 0x8008249C], [0x801E8D48, 0x800824CC]]:
				calls.append(["look", 0x801E83A8, t[0], 0x801E8D78, t[1], 0x100 * n])
			wr(m, O(121), on)
			wr(m, O(121, 0x3C), 0xFF if on else 0)
			wr(m, O(173, 0x3E), 0xFF if on else 0)
			if off91 == 0:
				wr(m, O(91), 0)
			cats(m, [[3, v3], [0, v0], [1, v1]])
			for k in 0x47:
				wr(m, A(4 + k), rest)
			if f(m, 0x28) == 0:
				wr(m, A(58), 8)
			else:
				wr(m, O(83), 0)
			wr(m, F(LAST_LEVEL), 6)
		7:
			wr(m, F(LAST_LEVEL), 7)
		8:
			wr(m, A(1), 8 if f(m, 0x2C) == 0 or f(m, 0x2E) != 0 else 1)
			wr(m, F(0x2F), 1 if has_item(m, 0x85) > 0 else 0)
			if has_item(m, 0x10) > 0:
				wr(m, F(0x30), 1)
			if has_item(m, 0x7D) > 0:
				wr(m, F(0x31), 1)
			wr(m, F(LAST_LEVEL), 8)
		9:
			if f(m, 0x24) and f(m, 0x27):
				wr(m, F(0x32), 1)
			if f(m, 0x34) == 0:
				wr(m, A(2), 1)
				wr(m, O(249), 0)
				wr(m, O(249, 0x3C), 0)
				wr(m, O(262, 0x3E), 0)
			else:
				wr(m, A(2), 8)
				wr(m, O(249), 2)
				wr(m, O(249, 0x3C), 0xFF)
				wr(m, O(262, 0x3E), 0xFF)
			if f(m, 0x35):
				wr(m, O(58, 6), 0xFF, 2)
				wr(m, O(58, 4), 0xFF)
				wr(m, O(58), 0)
				wr(m, F(0x35), 2)
			if f(m, 0x36) == 0 and (has_item(m, 0x7D) > 0 or rd(m, PLAYER_LEVEL) >= 0x28):
				wr(m, F(0x36), 1)
				key_test_all(m, 0xF1)
			wr(m, F(LAST_LEVEL), 9)
		10:
			_level10(m)
		11:
			if f(m, 0x3C) == 0:
				wr(m, O(20), 2)
				wr(m, O(20, 0x3C), 0xFF)
				wr(m, O(33, 0x3E), 0xFF)
			else:
				wr(m, O(20), 0)
				var k := rd(m, O(20, 0x3A), 2)
				wr(m, O(20, 0x3C), 0)
				if k != 0xFFFF and rd(m, O(k, 6), 2) != 0xFF:
					wr(m, O(k), 2)
					wr(m, O(k, 0x38), 0xFF)
					wr(m, O(20, 0x3A), 0xFFFF, 2)
				wr(m, O(33, 0x3E), 0)
			wr(m, F(LAST_LEVEL), 11)
		12:
			for t in [[0x3E, 241, 0x64], [0x3F, 242, 0x65], [0x40, 243, 0x66]]:
				if f(m, t[0]) == 1:
					lock_lift(m, t[1], t[2])
			wr(m, F(LAST_LEVEL), 12)
		13:
			wr(m, F(0x47), 1)
			if f(m, 0x7C):
				wr(m, O(15, 6), 0xFF, 2)
				wr(m, O(86, 6), 0xFF, 2)
			if f(m, 0x42) == 0:
				wr(m, F(0x43), 1)
			else:
				wr(m, O(20, 6), 0xFF, 2)
				wr(m, A(30), 8)
				wr(m, A(30, 9), 3)
			wr(m, F(LAST_LEVEL), 13)
		14:
			var v := 1
			var sx := 0x4C
			if f(m, 0x14) >= 2:
				wr(m, O(7, 6), 0xFF, 2)
				wr(m, O(49, 6), 0xFF, 2)
				v = 8
				sx = 0x4E
			calls.append(["stamp", 2, sx, 0, 0x21, 2, 2, 3, 0, 0x2F])
			calls.append(["stamp", 2, sx, 3, 0xC, 0x48, 2, 3, 0, 0x2F])
			cats(m, [[66, v], [70, v], [24, v], [43, v]])
			wr(m, F(LAST_LEVEL), 14)
		15:
			if f(m, 0x49):
				cats(m, [[4, 8], [5, 8]])
				wr(m, O(115, 6), 0xFF, 2)
				wr(m, O(116, 6), 0xFF, 2)
			if f(m, 0x4A):
				cats(m, [[10, 8], [11, 8]])
				wr(m, O(117, 6), 0xFF, 2)
				wr(m, O(118, 6), 0xFF, 2)
			wr(m, F(LAST_LEVEL), 15)
		16:
			calls.append(["stamp", 2, 0x14 if f(m, 0x52) else 0x13, 0, 0xC, 1, 1, 3, 0, 0x2F])
			wr(m, F(LAST_LEVEL), 16)
		17:
			_level17(m)
		19:
			wr(m, A(17), 1 if f(m, 0x59) == 0 else 8)
			wr(m, O(85, 0x3F), 0xFF if f(m, 0x55) else 0)
			wr(m, O(85), 2 if f(m, 0x55) else 0)
			wr(m, F(LAST_LEVEL), 19)
		20:
			wr(m, F(0x57), 1)
			calls.append(["stamp", 2, 0x4D if f(m, 0x56) else 0x4A, 0, 0x26, 0xC, 3, 5, 0, 0x2F])
			wr(m, F(0x58), 0 if has_item(m, 0x7D) > 0 else 1)
			wr(m, F(LAST_LEVEL), 20)
		22:
			var on := f(m, 0x5C) != 0
			wr(m, A(25), 8 if on else 1)
			wr(m, O(28), 2 if on else 0)
			wr(m, O(28, 0x3C), 0xFF if on else 0)
			wr(m, O(95, 0x3E), 0xFF if on else 0)
			wr(m, F(LAST_LEVEL), 22)
		24:
			if f(m, 0x65) == 0:
				wr(m, F(0x5D), 0)
			wr(m, F(LAST_LEVEL), 24)
		26:
			if f(m, 0x60):
				signal_all(m, 0xF2)
			if f(m, 0x7E):
				wr(m, O(6, 6), 0xFF, 2)
				wr(m, O(87, 6), 0xFF, 2)
			if f(m, 0x64):
				key_test_all(m, 0xF1)
			var bits := f(m, 0x62) | (f(m, 0x63) << 8)
			var n := 0
			for i in 12:
				wr(m, 0x8018296A + 0x18 * i, 2 if bits & 1 else 0)
				if bits & 1:
					n += 1
				bits >>= 1
			calls.append(["look", 0x801E8390, 0x801E8BB8, 0x801E8BE8, 0x8008243C, 0x140 * n])
			wr(m, F(LAST_LEVEL), 26)
		18, 21, 23, 25, 27:
			wr(m, F(LAST_LEVEL), lv)


# Level 10's: the way in by flags 0x39 and 0x3a and the level last come
# into, a stamp_rect either way, and fifteen and fourteen creatures' categories.
# @port helper -- level 10's entry 5, split out of entry5
static func _level10(m: Dictionary) -> void:
	if f(m, 0x38) == 0:
		wr(m, F(0x38), 1)
	var first := false
	var after := false
	if f(m, 0x39) == 0:
		first = true
	elif f(m, LAST_LEVEL) != 0xA:
		after = true
	elif f(m, 0x3A) == 0:
		first = true
	else:
		after = true
	if first:
		wr(m, A(29), 1)
		wr(m, O(253), 0)
		wr(m, O(253, 0x38), 0)
		m["calls"].append(["stamp", 2, 0x48, 5, 0x41, 0x31, 1, 1, 0, 0x2F])
		wr(m, O(90), 0)
		wr(m, O(90, 0x3E), 0)
		for k in 15:
			wr(m, A(k), 1)
		for k in range(15, 29):
			wr(m, A(k), 8)
	else:
		m["calls"].append(["stamp", 2, 0x47, 5, 0x41, 0x31, 1, 1, 0, 0x2F])
		wr(m, O(90), 2)
		wr(m, O(90, 0x3E), 0xFF)
		for k in 15:
			wr(m, A(k), 8)
		if f(m, LAST_LEVEL) != 0xA and f(m, 0x3A) == 0:
			wr(m, F(0x3A), 1)
			for k in range(15, 29):
				wr(m, A(k), 1)
	if f(m, 0x3A):
		if f(m, 0x3A) == 1:
			wr(m, O(253), 2)
			wr(m, O(253, 0x38), 0xFF)
			wr(m, F(0x3A), 2)
		wr(m, A(29), 8)
	wr(m, F(LAST_LEVEL), 0xA)


# Level 17's: three slots held and three objects marked by flags 0x4e..0x50,
# Orladin's portrait and the seals' gate by 0x52 and 0x53, and on 0x53 1 a
# thing of type 0x8f made in the gold ring at the portrait.
# @port helper -- level 17's entry 5, split out of entry5
static func _level17(m: Dictionary) -> void:
	for t in [[0x4E, 0x10, 0x50], [0x4F, 0x37, 0x51], [0x50, 0x2E, 5]]:
		var how := 1 if f(m, t[0]) else 0
		if how:
			wr(m, A(t[1]), 8)
		wr(m, O(t[2], 0x3F), how)
		wr(m, O(t[2], 8), 1, 2)
	wr(m, A(15), 8)
	wr(m, O(63), 2 if f(m, 0x52) else 0)
	wr(m, O(63, 0x3F), 0xFF if f(m, 0x52) else 0)
	var v := f(m, 0x53)
	wr(m, O(50), 2 if v == 0 else 0)
	for k in range(52, 62):
		wr(m, O(k), 0 if v == 0 else 2)
	m["calls"].append(["stamp", 2, 0x38 if v == 0 else 0x3B, 0x4C, 0x47, 0x30, 3, 4, 0, 0x2F])
	wr(m, A(56), 1 if v == 1 else 8)
	wr(m, A(56, 3), 0)
	wr(m, O(11), 0 if v >= 2 else 2)
	if v == 1:
		var count := rd(m, DROP_COUNT, 2)
		var k := free_slot(m, 0x15E, 10, count)
		if k >= 0:
			init_record(m, k)
			wr(m, DROP_COUNT, count + 1, 2)
			wr(m, O(k, 0xE), -0x64, 2)
			wr(m, O(k, 6), 0x8F, 2)
			wr(m, O(k, 0x3C), count, 2)
			wr(m, O(k), 2)
			wr(m, O(k, 4), 0xFF)
			wr(m, O(k, 0x28), 0, 2)
			wr(m, O(k, 0x24), 0, 2)
			wr(m, O(k, 0x38), 0)
			wr(m, O(k, 0x26), rd(m, O(11, 0x26), 2), 2)
			wr(m, O(k, 0x14), rd(m, O(11, 0x14), 4), 4)
			wr(m, O(k, 0x18), rd(m, O(11, 0x18), 4) - 0x32, 4)
			wr(m, O(k, 0x1C), rd(m, O(11, 0x1C), 4), 4)
	wr(m, F(0x54), 1)
	wr(m, F(LAST_LEVEL), 0x11)

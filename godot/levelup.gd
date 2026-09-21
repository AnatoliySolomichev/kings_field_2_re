class_name KFLevels
# Experience, and what a level gives you.
#
# The whole of it is `award_exp` at 0x8002a310, and it is short: add the
# experience, cap it at 999999, and while it reaches the next threshold, take a
# level. What a level *gives* is not computed -- it is read out of a table of
# 99 records of twelve bytes which is not in GAME.EXE at all. It lives at
# 0x8009f114, past the end of the image, and it comes off the disc: FDAT.T
# entry 97 at offset 12592, the same shared blob that carries the cutscene list
# and the creature animation frames. tools/levelup.py writes it out beside the
# level geometry as levels.json, so this file holds no copy of it.
#
#   +0  u16  HP maximum at this level       50 at level 1, 999 by level 97
#   +2  u16  MP maximum                     30 ... 999
#   +4  u16  added to the stat at +0x36     20 once, then 0, 1 or 2
#   +8  u32  experience for the next level  50, 110, 187, ... 999999
#
# Checked: every RAM snapshot in out/snap -- 13 of 13 -- has the HP maximum,
# the MP maximum and the next threshold its level's record says.
#
# Five more stats grow by a coin toss instead, the halfwords at 0x801b2518 to
# 0x801b2520: for each one that is not already zero, rand() < 0x6665 adds one,
# about four times in five. It is the only place levelling uses rand, and it is
# why two characters at the same level are not the same character.

const EXP_CAP := 0xF423F             # 0x8002a35c
const STAT_CAP := 0x3E7              # 0x8002a52c and the three beside it
const GROW_ODDS := 0x6665            # 0x8002a420
const LEVEL_CAP := 0xFF              # 0x8002a3a8
const TABLE_LEVELS := 0x63           # above 99 the routine extrapolates

static var levels: Array = []


static func load_from(path := "res://levels.json") -> bool:
	if not levels.is_empty():
		return true
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	levels = d.get("levels", [])
	return not levels.is_empty()


# The game's own rand is BIOS A0:2F behind 0x800796c0, and its seed is not
# reproduced here -- so a levelling run in the port will not roll the same
# stats as the same run in the game. The rule is the game's; the sequence is
# not, and that is said here rather than left to be discovered.
static func _roll() -> int:
	return randi() & 0x7FFF


# @orig game:0x8002a310  status:transcribed -- award_exp; checked against 13 of 13 snapshots
static func award(state: Dictionary, delta: int) -> Dictionary:
	if not load_from():
		return state
	var s := state.duplicate(true)
	s["exp"] = mini(int(s["exp"]) + delta, EXP_CAP)
	while int(s["exp"]) >= int(s["exp_next"]) and int(s["level"]) < LEVEL_CAP:
		var lv := int(s["level"])
		s["level"] = lv + 1
		if (lv & 0xFF) < TABLE_LEVELS:
			var r: Dictionary = levels[lv]
			s["hp_max"] = int(r["hp"])
			s["mp_max"] = int(r["mp"])
			s["stat36"] = int(s["stat36"]) + int(r["gain"])
			s["exp_next"] = int(r["next"])
		else:
			# 0x8002a45c: past the table, each step repeats the last one.
			var last: Dictionary = levels[levels.size() - 1]
			var prev: Dictionary = levels[levels.size() - 2]
			s["hp_max"] = int(s["hp_max"]) + int(last["hp"]) - int(prev["hp"])
			s["mp_max"] = int(s["mp_max"]) + int(last["mp"]) - int(prev["mp"])
			s["stat36"] = int(s["stat36"]) + int(last["gain"])
			s["exp_next"] = (int(s["exp_next"])
				+ int(last["next"]) - int(prev["next"]))
		var grow: Array = s["grow"]
		for k in range(5):
			# A stat already at zero never grows: the routine tests it before
			# it rolls (0x8002a410).
			if int(grow[k]) != 0 and _roll() < GROW_ODDS:
				grow[k] = int(grow[k]) + 1
		s["hp_max"] = mini(int(s["hp_max"]), STAT_CAP)
		s["mp_max"] = mini(int(s["mp_max"]), STAT_CAP)
		s["stat36"] = mini(int(s["stat36"]), STAT_CAP)
		for k in range(grow.size()):
			grow[k] = mini(int(grow[k]), STAT_CAP)
		s["grow"] = grow
	return s


# What a fresh character is, out of the table's first record rather than out of
# a constant: 0x8002b468 seeds the block at level 1 the same way.
static func fresh() -> Dictionary:
	load_from()
	var r: Dictionary = levels[0] if not levels.is_empty() else {}
	return {"exp": 0, "exp_next": int(r.get("next", 50)), "level": 1,
		"hp_max": int(r.get("hp", 50)), "mp_max": int(r.get("mp", 30)),
		"stat36": int(r.get("gain", 20)), "grow": [10, 10, 10, 10, 10]}

class_name KFLevels
# Experience, and what a level gives you.
#
# The whole of it is `award_exp` at 0x8002a310, and it is short: add the
# experience, cap it at 999999, and while it reaches the next threshold, take a
# level. What a level *gives* is not computed -- it is read out of a table of
# 99 records of twelve bytes which is not in GAME.EXE at all. It lives at
# 0x8009f114, past the end of the image, and it comes off the disc: FDAT.T
# entry 97 at offset 12592, the same shared blob that carries the cutscene list
# the object type table and the spell table. tools/levelup.py writes it beside the
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
#
# @exe game

const EXP_CAP := 0xF423F             # 0x8002a35c
const STAT_CAP := 0x3E7              # 0x8002a52c and the three beside it
const GROW_ODDS := 0x6665            # 0x8002a420
const LEVEL_CAP := 0xFF              # 0x8002a3a8
const TABLE_LEVELS := 0x63           # above 99 the routine extrapolates

# skill_unlock's data, GAME.EXE's: five skills' thresholds (s16, a 0 ends them,
# 0x80081884) and the spells each unlocks in turn (0xff ends them, 0x800818c0)
const SKILL_FLAG := 0x6D             # story_flags + 0x6d + k (0x801ba9f5): skills 0..3 unlock only once set
const SKILL_UNLOCKED := 0x7B         # story_flags + 0x7b + k (0x801baa03): set when one of k's spells is
const SPELLS := 96
const FIRST_SPELL := 29              # light: new_character sets its flag by hand (0x801b7aa4)
const LEVEL_UP := 0                  # the banners
const NEW_SPELL := 3
const GROWN := 4                     # the excellector's, 0x8002a2e0
const EXCEL_STEP := 0x32C8           # 13000 past the mark and it grows, 0x8002a254

static var levels: Array = []
static var skills := {}
static var beyond := {}              # record 99, the twelve bytes after the table: zeros


# @port data -- reads levels.json, the 99 records tools/levelup.py takes off FDAT entry 97
static func load_from(path := "res://levels.json") -> bool:
	if not levels.is_empty():
		return true
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	levels = d.get("levels", [])
	skills = d.get("skills", {})
	beyond = d.get("beyond", {"hp": 0, "mp": 0, "gain": 0, "next": 0})
	return not levels.is_empty()


# The game's own rand is BIOS A0:2F behind 0x800796c0, and its seed is not
# reproduced here -- so a levelling run in the port will not roll the same
# stats as the same run in the game. The rule is the game's; the sequence is
# not, and that is said here rather than left to be discovered. `rolls`, when
# given, answers in its place, in turn (the self-test's, the game's rand as
# tools/levelup.py drew it), and s["rolls"] counts what was drawn.
# @port helper -- Godot's randi in the place of the game's rand; not its sequence
static func _roll(s: Dictionary, rolls: Array) -> int:
	var n := int(s.get("rolls", 0))
	s["rolls"] = n + 1
	if n < rolls.size():
		return int(rolls[n])
	return randi() & 0x7FFF


# @port helper -- a word as the signed 32 bits the game keeps it in
static func _s32(v: int) -> int:
	v &= 0xFFFFFFFF
	return v - 0x100000000 if v & 0x80000000 else v


# award_exp: the experience (the award as the s16 it is taken as), the
# excellector's growth (excellector, before the cap), and while it reaches
# the next threshold a level -- HP max, MP max, stat 36 and the next
# threshold from the level's record; past the table's 99 by the difference
# between the twelve zero bytes after it (record 99, "beyond") and record
# 98, which takes 999 off both maxima -- the five skills from the fifth down
# each one more on a roll under 0x6665, "level up", the clamps to 999 and
# skill_unlock for each from 4 down. The banners land in "banners" in the
# game's order (the excellector's first), the weapon equip_weapon is to be
# given in "equip" (-1 none), for the caller to act; player_recalc_stats is
# the caller's too, and so is use_answer, which skill_unlock sets.
# @orig game:0x8002a310 award_exp  status:verified -- tools/levelup.py --game, 840 of 840 runs of the game's own over every level, excellector_grow, skill_unlock, has_item, take_item, give_item and the levels' entries 6 and 11 run as the game's (the calls, the rolls drawn, all of RAM but the stack); 20 of 20 snapshots hold the table; the self-test this to it, the rolls given
static func award(state: Dictionary, delta: int, flags: Array = [], inv: KFItems = null,
		weapon := 0xFF, rolls: Array = []) -> Dictionary:
	if not load_from():
		return state
	var s := state.duplicate(true)
	s["banners"] = []
	s["equip"] = -1
	s["rolls"] = 0
	var d := delta & 0xFFFF
	s["exp"] = _s32(int(s["exp"]) + (d - 0x10000 if d & 0x8000 else d))
	if inv != null:
		excellector(s, inv, weapon)
	s["exp"] = mini(int(s["exp"]), EXP_CAP)
	while int(s["exp"]) >= int(s["exp_next"]) and int(s["level"]) < LEVEL_CAP:
		var lv := int(s["level"])
		s["level"] = lv + 1
		if (lv & 0xFF) < TABLE_LEVELS:
			var r: Dictionary = levels[lv]
			s["hp_max"] = int(r["hp"])
			s["mp_max"] = int(r["mp"])
			s["stat36"] = (int(s["stat36"]) + int(r["gain"])) & 0xFFFF
			_grow(s, rolls)
			s["exp_next"] = int(r["next"])
		else:
			# 0x8002a45c: record 99, the twelve bytes after the table, less
			# record 98
			var last: Dictionary = beyond
			var prev: Dictionary = levels[levels.size() - 1]
			s["hp_max"] = (int(s["hp_max"]) + int(last["hp"]) - int(prev["hp"])) & 0xFFFF
			s["mp_max"] = (int(s["mp_max"]) + int(last["mp"]) - int(prev["mp"])) & 0xFFFF
			s["stat36"] = (int(s["stat36"]) + int(last["gain"])) & 0xFFFF
			_grow(s, rolls)
			s["exp_next"] = _s32(int(s["exp_next"]) + int(last["next"]) - int(prev["next"]))
		s["banners"].append(LEVEL_UP)
		for k in ["hp_max", "mp_max", "stat36"]:
			if int(s[k]) > STAT_CAP:
				s[k] = STAT_CAP
		# 0x8002a574: skill_unlock for each, from 4 down, and its clamp
		var grow: Array = s["grow"]
		for k in range(4, -1, -1):
			if s.has("spells"):
				s["banners"] += skill_unlock(s, k, flags)
			if int(grow[k]) > STAT_CAP:
				grow[k] = STAT_CAP
	return s


# The five skills from the fifth (0x801b2520) down: one not at zero -- the
# routine tests it before it rolls (0x8002a410) -- grows by one when the roll
# is under 0x6665.
# @port helper -- award_exp's two loops of rolls, one function
static func _grow(s: Dictionary, rolls: Array) -> void:
	var grow: Array = s["grow"]
	for k in range(4, -1, -1):
		if int(grow[k]) != 0 and _roll(s, rolls) < GROW_ODDS:
			grow[k] = (int(grow[k]) + 1) & 0xFFFF


# excellector_grow, which award_exp calls with the experience added and not yet
# capped: the excellector growing. Held in its first or second form (items 0
# and 1), s["excel"] (0x801b24ec) is the experience it counts from: -1,
# new_character's, takes the experience now; once the experience is more
# than 13000 past it, the excellector in hand (weapon 0 or 1) is to be
# exchanged for the next form (s["equip"]), the second form in the pack for
# the third and the first for the second (take_item, give_item -- the
# level's entry 6 after; with no room for it, give_item's banner), banner 4,
# and the word -1 again. Holding neither, -1.
# @orig game:0x8002a210 excellector_grow  status:verified -- through award_exp, tools/levelup.py --game, 840 of 840 runs of the game's own (376 growths); the snapshots past the first kill hold the experience it took (11 in 8 of 8, -1 in the 13 before); the self-test this to it
static func excellector(s: Dictionary, inv: KFItems, weapon: int) -> void:
	if not (inv.has_item(0) or inv.has_item(1)):
		s["excel"] = -1
		return
	var mark := int(s.get("excel", -1))
	if mark == -1:
		s["excel"] = int(s["exp"])
		return
	if not _s32(mark + EXCEL_STEP) < int(s["exp"]):
		return
	if (weapon & 0xFF) < 2:
		s["equip"] = ((weapon & 0xFF) + 1) & 0xFF
	if inv.has_item(1):
		inv.take_item(1)
		if not inv.give_item(2):
			s["banners"].append(inv.last_message)
	if inv.has_item(0):
		inv.take_item(0)
		if not inv.give_item(1):
			s["banners"].append(inv.last_message)
	s["banners"].append(GROWN)
	s["excel"] = -1


# For each threshold of skill k the skill has reached, the first spell not yet
# unlocked among the first (index + 1) of the skill's list is, with a "new
# spell" banner and story flag 0x7b + k. Skills 0..3 do nothing until story
# flag 0x6d + k is set. `s["spells"]` and `flags` change in place.
# @orig game:0x80029f1c skill_unlock  status:verified -- 13 of 13 snapshots hold the spells it leaves a new character with their skills (tools/levelup.py); the banners returned, not raised
static func skill_unlock(s: Dictionary, k: int, flags: Array) -> Array:
	var out := []
	if k >= 5 or skills.is_empty():
		return out
	while flags.size() < KFTalk.FLAG_COUNT:       # the story flags, all clear
		flags.append(0)
	if k != 4 and int(flags[SKILL_FLAG + k]) == 0:
		return out
	var th: Array = skills["thresholds"][k]
	var lst: Array = skills["unlock"][k]
	var skill := int(s["grow"][k])
	var spells: Array = s["spells"]
	for i in th.size():
		var t := int(th[i])
		if skill < t or t == 0:
			break
		for j in range(i + 1):
			var sp := int(lst[j])
			if sp == 0xFF:
				return out
			if int(spells[sp]) == 0:
				spells[sp] = 1
				out.append(NEW_SPELL)
				flags[SKILL_UNLOCKED + k] = 1
				break
	return out


# new_character's spell flags (0x8002b618): all clear, then light's set.
# @port helper -- the spells' +0 flags of a new character
static func new_spells() -> Array:
	var sp := []
	sp.resize(SPELLS)
	sp.fill(0)
	sp[FIRST_SPELL] = 1
	return sp


# What a fresh character is, out of the table's first record rather than out of
# a constant: 0x8002b468 seeds the block at level 1 the same way.
# @orig game:0x8002b468 new_character  status:partial -- the level, the experience, the excellector's mark (0x801b24ec), HP and MP, stat 36, the five that grow, 0x801b2530 and the spells' flags; the equipment is player.gd's (worn, weapon_id); not the gold or the place
static func fresh() -> Dictionary:
	load_from()
	var r: Dictionary = levels[0] if not levels.is_empty() else {}
	return {"exp": 0, "exp_next": int(r.get("next", 50)), "level": 1,
		"hp_max": int(r.get("hp", 50)), "mp_max": int(r.get("mp", 30)),
		# new_character (0x8002b468): the five from the table's +6, which is
		# zero, and 10 more on the fifth -- [0, 0, 0, 0, 10] in every snapshot
		"stat36": int(r.get("gain", 20)), "grow": [0, 0, 0, 0, 10],
		# 0x801b2530 zeroed, and the spells' flags: light only
		"wis": 0, "spells": new_spells(),
		# 0x8002b49c: the excellector's mark, none yet
		"excel": -1}

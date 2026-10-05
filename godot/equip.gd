class_name KFEquip
# What the player is carrying, and the sixteen ratings it comes to.
#
# `player_recalc_stats` (0x80029500) is called from twelve places -- award_exp,
# player_take_hit, player_action, equipping something -- so the ratings are
# never stored anywhere, only ever recomputed from what is worn.
#
#   1. zero the eight offense ratings (0x801b2538) and the eight defense
#      ratings (0x801b254a), and copy the five skills down into a working set;
#   2. the equipped **weapon** (id at 0x801b25af, 0xff for none) is a 68-byte
#      record at `weapon_table + 68 * id`, and its eight u16 from +6 go one
#      per offense rating;
#   3. each of the seven worn **pieces** (0x801b25d4..0x801b25da) is a 32-byte
#      record at `armour_table + 32 * (id - 34)`, and its eight u16 at
#      +2, +4, +6, +0xa, +0xc, +0xe, +0x10, +0x12 go one per defense rating.
#      `0x800293e4` is that step, and the -34 is visible in it as a base of
#      0x801e6078 where the table itself is at 0x801e64b8;
#   4. the flat bonuses: +0x32 to defense 4, +0x1e to defense 0, 1 and 2,
#      +5 to every working skill, each behind its own timer;
#   5. what thirteen worn things add by id -- to a working skill, the
#      effective stat or the offense (SPECIALS, RINGS below) -- and a story
#      byte's +0x32 on level 0x1a;
#   6. under zero is 0, and the stat and the skills stop at 999.
#
# All of it is recalc(); tools/equip.py --check holds the same reading against
# every snapshot: 483 of 483 values over 21 of them. And the armour helper adds
# a ninth value, the record's +8, to 0x801b255a: the resistance to poison.
#
# Both tables come off the disc -- FDAT entry 97 blocks 1 and 2 -- and
# `tools/equip.py` writes them here as `equip.json`. Checked against a RAM
# snapshot of a running game: 3264 of 3264 weapon bytes, 2112 of 2112 armour
# bytes, and 16 of 16 ratings.
#
# @exe game

const RATINGS := 8
const NONE := 0xFF
const ARMOUR_FIRST := 34    # 0x801e64b8 - 0x801e6078, over 32 bytes a record
const BONUS_DEFENSE_AT := 4          # 0x801b2552, behind 0x801b256a
const BONUS_DEFENSE_4 := 0x32
const BONUS_DEFENSE := 0x1E          # defense 0..2, behind 0x801b256e
const BONUS_SKILLS := 5              # every working skill, behind 0x801b2578
const CAP := 0x3E7
const STORY_LEVEL := 0x1A            # with 0x801ba9e9 at 1: +0x32 to skill 3
# (slot, id, [what, amount]...) as tools/equip.py SPECIALS: the slot -1 for
# the weapon, else 0..6 for 0x801b25d4..0x801b25da
const SPECIALS := [
	[-1, 0x20, ["w2", 0x14]], [-1, 0x21, ["w0", 0x14]],
	[0, 0x26, ["stat", 0x14]], [0, 0x29, ["w4", 0x14]],
	[1, 0x31, ["w1", 0x14]],
	[2, 0x39, ["w4", 0x1E]], [2, 0x3C, ["w2", 0x14]],
	[3, 0x43, ["o4", 0x14]], [3, 0x44, ["o*", 0xA]], [3, 0x46, ["w0", 0x14]],
	[4, 0x4F, ["w3", 0x14]],
	[5, 0x51, ["stat", 5]], [6, 0x51, ["stat", 5]],
]
# the two ring slots (5 and 6) asked together
const RINGS := [
	[0x52, ["w*", 8, "stat", -0x1E]],
	[0x55, ["o4", 0xC, "o5", 0xC, "o6", 0xC, "o7", 0xC]],
	[0x59, ["w3", 0x14]], [0x5A, ["w1", 0x14]], [0x5B, ["w4", 0x14]],
]

var weapons: Array = []     # id -> its eight offense values
var armour: Array = []      # (id - 34) -> its eight defense values
var resists: Array = []     # (id - 34) -> its +8, the ninth defense half


# @port data -- reads equip.json, the two tables tools/equip.py cuts out of FDAT entry 97
func load_tables(path := "res://equip.json") -> bool:
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	weapons = d.get("weapons", [])
	armour = d.get("armour", [])
	resists = d.get("resist", [])
	return true


# @orig game:0x800293e4 add_armour_ratings  status:verified
func add_armour(id: int, defense: Array) -> void:
	if id == NONE:
		return
	var i := id - ARMOUR_FIRST
	if i < 0 or i >= armour.size():
		return
	for k in range(RATINGS):
		defense[k] = int(defense[k]) + int(armour[i][k])


# player_recalc_stats whole: `st` holds what it reads -- "stat36", "skills"
# (five), "curse" (0x801b255e), "b56a", "b56e", "b578" (the flat bonuses'
# timers), "weapon", "worn" (seven), "story" (0x801ba9e9), "level" -- and the
# answer is what it writes: "offense", "defense", "working", "stat".
# @orig game:0x80029500 player_recalc_stats  status:verified -- 483 of 483 values over 21 snapshots, one with nothing worn or wielded (tools/equip.py); not the word it copies from 0x801b2584 to 0x801c12f0
func recalc(st: Dictionary) -> Dictionary:
	var off := []
	var dfn := []
	off.resize(RATINGS)
	off.fill(0)
	dfn.resize(RATINGS)
	dfn.fill(0)
	var stat: int = int(st["stat36"]) & 0xFFFF
	var work := []
	for v in st["skills"]:
		work.append(int(v) & 0xFFFF)
	if int(st.get("curse", 0)) != 0:
		stat >>= 1
		for k in range(5):
			work[k] = int(work[k]) >> 1
	var weapon := int(st["weapon"])
	if weapon != NONE and weapon >= 0 and weapon < weapons.size():
		for k in range(RATINGS):
			off[k] = (int(off[k]) + int(weapons[weapon][k])) & 0xFFFF
	var worn: Array = st["worn"]
	var resist := 0
	for id in worn:
		add_armour(int(id), dfn)
		# add_armour_ratings' last add: the record's +8 to 0x801b255a
		var i := int(id) - ARMOUR_FIRST
		if int(id) != NONE and i >= 0 and i < resists.size():
			resist = (resist + int(resists[i])) & 0xFFFF
	if int(st.get("b56a", 0)) != 0:
		dfn[BONUS_DEFENSE_AT] = int(dfn[BONUS_DEFENSE_AT]) + BONUS_DEFENSE_4
	if int(st.get("b56e", 0)) != 0:
		for k in range(3):
			dfn[k] = int(dfn[k]) + BONUS_DEFENSE
	if int(st.get("b578", 0)) != 0:
		for k in range(5):
			work[k] = (int(work[k]) + BONUS_SKILLS) & 0xFFFF
	var r := {"offense": off, "defense": dfn, "working": work, "stat": stat,
		"resist": resist}
	for sp in SPECIALS:
		var have: int = weapon if int(sp[0]) < 0 else int(worn[int(sp[0])])
		if have == int(sp[1]):
			_give(r, sp[2])
	for ring in RINGS:
		if int(worn[5]) == int(ring[0]) or int(worn[6]) == int(ring[0]):
			_give(r, ring[1])
	if int(st.get("story", 0)) == 1 and int(st.get("level", 0)) == STORY_LEVEL:
		work[3] = (int(work[3]) + 0x32) & 0xFFFF
	# under zero, as a u16 over 0x7fff, is 0; the stat and the skills stop at 999
	var s: int = int(r["stat"]) & 0xFFFF
	r["stat"] = 0 if s > 0x7FFF else mini(s, CAP)
	for k in range(5):
		var w: int = int(work[k]) & 0xFFFF
		work[k] = 0 if w > 0x7FFF else mini(w, CAP)
	for k in range(RATINGS):
		var o: int = int(off[k]) & 0xFFFF
		off[k] = 0 if o > 0x7FFF else o
		var d: int = int(dfn[k]) & 0xFFFF
		dfn[k] = 0 if d > 0x7FFF else d
	r["resist"] = 0 if resist > 0x7FFF else resist
	return r


# @port helper -- one of SPECIALS' or RINGS' lists of what a worn thing adds
func _give(r: Dictionary, what: Array) -> void:
	for i in range(0, what.size(), 2):
		var key := str(what[i])
		var n := int(what[i + 1])
		if key == "stat":
			r["stat"] = (int(r["stat"]) + n) & 0xFFFF
		elif key == "w*":
			for k in range(5):
				r["working"][k] = (int(r["working"][k]) + n) & 0xFFFF
		elif key.begins_with("w"):
			var k := int(key.substr(1))
			r["working"][k] = (int(r["working"][k]) + n) & 0xFFFF
		elif key == "o*":
			for k in range(RATINGS):
				r["offense"][k] = (int(r["offense"][k]) + n) & 0xFFFF
		else:
			var k := int(key.substr(1))
			r["offense"][k] = (int(r["offense"][k]) + n) & 0xFFFF


# The ratings alone, as the snapshots and bp23 recorded them.
# @port check -- recalc() with nothing but the equipment
func ratings(weapon: int, worn: Array,
		bonus_offense := false, bonus_defense := false) -> Dictionary:
	var off: Array = []
	var dfn: Array = []
	off.resize(RATINGS)
	off.fill(0)
	dfn.resize(RATINGS)
	dfn.fill(0)
	if weapon != NONE and weapon >= 0 and weapon < weapons.size():
		for k in range(RATINGS):
			off[k] = int(weapons[weapon][k])
	for id in worn:
		add_armour(int(id), dfn)
	if bonus_offense:
		dfn[BONUS_DEFENSE_AT] += BONUS_DEFENSE_4
	if bonus_defense:
		for k in range(3):
			dfn[k] += BONUS_DEFENSE
	return {"offense": off, "defense": dfn}

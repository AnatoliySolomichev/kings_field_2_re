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
#   4. the flat bonuses: +0x32 to offense 5, +0x1e to defense 0, 1 and 2,
#      +5 to every working skill, each behind its own flag.
#
# Both tables come off the disc -- FDAT entry 97 blocks 1 and 2 -- and
# `tools/equip.py` writes them here as `equip.json`. Checked against a RAM
# snapshot of a running game: 3264 of 3264 weapon bytes, 2112 of 2112 armour
# bytes, and 16 of 16 ratings.
# @orig game:0x80029500 player_recalc_stats  status:partial -- the equipment

const RATINGS := 8
const NONE := 0xFF
const ARMOUR_FIRST := 34    # 0x801e64b8 - 0x801e6078, over 32 bytes a record
const BONUS_OFFENSE_AT := 5
const BONUS_OFFENSE := 0x32
const BONUS_DEFENSE := 0x1E

var weapons: Array = []     # id -> its eight offense values
var armour: Array = []      # (id - 34) -> its eight defense values


func load_tables(path := "res://equip.json") -> bool:
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	weapons = d.get("weapons", [])
	armour = d.get("armour", [])
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


# @orig game:0x80029500 player_recalc_stats  status:partial
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
		off[BONUS_OFFENSE_AT] += BONUS_OFFENSE
	if bonus_defense:
		for k in range(3):
			dfn[k] += BONUS_DEFENSE
	return {"offense": off, "defense": dfn}

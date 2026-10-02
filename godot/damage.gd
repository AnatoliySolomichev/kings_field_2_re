class_name KFDamage
# What a hit takes off.
#
# `player_take_hit` (0x8002ab18) is given **eight attack values, one per damage
# type** -- slash, blow and stab in a0..a2, the five magic types in arg4..arg8
# -- and in a3 an effect, not an attack: its low nibble picks one of seven
# (poison and its kin), and apply_damage reads its 0x40 (a heavier push) and
# 0x80 (a stun) bits. Each attack goes through `damage_of_type` (0x8002a5f8)
# against the matching one of the eight defence halves at 0x801b254a:
#
#     A = attack * 16
#     D = ((stat * 0x1000) >> 8) + defence * 16
#     if A == 0:  0
#     if D == 0:  D = 0x10
#     d = ( max(0, A - D) + (A * A) / (2 * D) ) / 5
#
# so a hit gets through two ways at once: the part that beats the defence
# outright, and a quadratic term that never quite vanishes. **An attack always
# does something**, and a strong enough one grows faster than a defence can
# hold it.
#
# The eight are then summed and scaled twice, and both scales come off the call
# site at 0x8004d358 rather than from a guess: 0x1000 into sp+0x24 and 0xa into
# sp+0x28.
#
#     base = sum of the eight
#     s1   = (0x1000 * base + 0x8000) >> 16      = base / 16, rounded
#     dmg  = (0xa * s1) / 10                     = s1
#
# Checked against the game: in a recorded session a creature hit a fresh
# character with (slash 0, blow 40, stab 30) three times and the log shows
# 50 -> 36 -> 22 -> 8, fourteen each time. The model gives 222 for the sum and
# 14 for the damage. **6 of 6 recorded hits**. The seventh, the one that
# killed the player, logged (10, 10, 70) with effect 0x40: 30 from those
# against 33 HP, so the magic five that log did not carry were not all zero.
#
# @exe game

const TYPES := 8                     # slash blow stab, then the five magic
const NAMES := ["slash", "blow", "stab", "magic 1", "magic 2", "magic 3",
	"magic 4", "magic 5"]
const K := 0x1000                    # 0x801b24f8, 0x1000 in every snapshot
const ARG9 := 0x1000                 # 0x8004d358
const ARG10 := 0xA                   # 0x8004d35c


# @orig game:0x8002a5f8 damage_of_type  status:verified -- through hit(), 6 of 6
static func of_type(attack: int, defence: int, stat: int, k := K) -> int:
	var a := attack * 16
	if a == 0:
		return 0
	var d := ((stat * k) >> 8) + defence * 16
	var over := maxi(0, a - d)
	if d == 0:
		d = 0x10
	return (over + (a * a) / (2 * d)) / 5


# The whole of player_take_hit's arithmetic. `attacks` and `defence` are eight
# long; anything shorter is taken as zero, which is what the call site does
# with the five types it never sets, and anything past the eighth -- the effect
# damagecheck.json carries ninth -- is not an attack.
# @orig game:0x8002ab18 player_take_hit  status:partial -- the arithmetic, 6 of 6 hits in out/lua_bp20.log; what the hit then does is player.gd's
static func hit(attacks: Array, defence: Array, stat: int,
		k := K, arg9 := ARG9, arg10 := ARG10) -> Dictionary:
	var base := 0
	for i in range(TYPES):
		var at: int = int(attacks[i]) if i < attacks.size() else 0
		var df: int = int(defence[i]) if i < defence.size() else 0
		base += of_type(at, df, stat, k)
	var s1 := (arg9 * base + 0x8000) >> 16
	return {"sum": base, "damage": (arg10 * s1) / 10}

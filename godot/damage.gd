class_name KFDamage
# What a hit takes off.
#
# `player_take_hit` (0x8002ab18) is given **nine attack values, one per damage
# type** -- slash, blow, stab, dark, holy, fire, earth, wind, water, the same
# nine the player's block carries as ratings. Each goes through
# `damage_of_type` (0x8002a5f8) against the matching defence:
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
# The nine are then summed and scaled twice, and both scales come off the call
# site at 0x8004d358 rather than from a guess: 0x1000 into sp+0x24 and 0xa into
# sp+0x28.
#
#     base = sum of the nine
#     s1   = (0x1000 * base + 0x8000) >> 16      = base / 16, rounded
#     dmg  = (0xa * s1) / 10                     = s1
#
# Checked against the game: in a recorded session a creature hit a fresh
# character with (slash 0, blow 40, stab 30) three times and the log shows
# 50 -> 36 -> 22 -> 8, fourteen each time. The model gives 222 for the sum and
# 14 for the damage. **6 of 6 recorded hits**, and the seventh -- the one that
# killed the player -- comes out at 59 against 33 HP.
# @orig game:0x8002ab18 player_take_hit  status:verified -- 6 of 6 hits in out/lua_bp20.log

const TYPES := 9                     # slash blow stab dark holy fire earth wind water
const NAMES := ["slash", "blow", "stab", "dark", "holy", "fire", "earth",
	"wind", "water"]
const K := 0x1000                    # 0x801b24f8, 0x1000 in every snapshot
const ARG9 := 0x1000                 # 0x8004d358
const ARG10 := 0xA                   # 0x8004d35c


# @orig game:0x8002a5f8 damage_of_type  status:verified
static func of_type(attack: int, defence: int, stat: int, k := K) -> int:
	var a := attack * 16
	if a == 0:
		return 0
	var d := ((stat * k) >> 8) + defence * 16
	var over := maxi(0, a - d)
	if d == 0:
		d = 0x10
	return (over + (a * a) / (2 * d)) / 5


# The whole of player_take_hit's arithmetic. `attacks` and `defence` are nine
# long; anything shorter is taken as zero, which is what the call site does
# with the five types it never sets.
# @orig game:0x8002ab18 player_take_hit  status:verified
static func hit(attacks: Array, defence: Array, stat: int,
		k := K, arg9 := ARG9, arg10 := ARG10) -> Dictionary:
	var base := 0
	for i in range(TYPES):
		var at: int = int(attacks[i]) if i < attacks.size() else 0
		var df: int = int(defence[i]) if i < defence.size() else 0
		base += of_type(at, df, stat, k)
	var s1 := (arg9 * base + 0x8000) >> 16
	return {"sum": base, "damage": (arg10 * s1) / 10}

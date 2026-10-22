class_name KFUseItem
# A thing used: use_item (0x8005cbe0), whole.
#
# What a thing does once the menu has closed on it, or the button's thing is
# used: the answer (0x801ba984) cleared, a switch on item - 0x65 (61 arms from
# 0x800131a0), and whatever the arm, the level's own entry 2, "Nothing
# happens" (announce 0xa) unless something answered, and clear_movement_state.
# FORMATS.md, "A thing used", has the arms; tools/useitem.py is the same in
# Python, held to the game's own use_item run over every level, and the
# self-test holds this to it.
#
# The world `w` is the game's state as the routine reads it, and it changes
# as RAM would:
#
#   pos [x, y, z], pitch, facing     player_pos, player_pitch, player_facing
#   layer                            0x801b2644, the floor the player stands on
#   block, busy, pending             current_level_block, level_change_busy,
#                                    pending_level
#   inv                              the pack (KFItems)
#   skills, stat36, wis, b578        0x801b2518.., 0x801b2516, 0x801b2530,
#                                    0x801b2578
#   drops                            drop_count_gold
#   spells, flags                    spell_table's +0 flags, story_flags
#   objects                          396 slots: null, or the record's fields
#                                    (OBJECT_FIELDS, the lock +0x38 as "lock")
#   creatures                        the awake ones: [slot, +0xe, +0x28, x, y,
#                                    z, model (+1), floor (+3)]
#
# run() returns the calls it makes beyond what it runs, in order, for the
# caller to act out: ["announce", code], ["load_entry", 6, entry],
# ["sound_key_fits"], ["recalc"], ["put_key", slot, item], ["hook", "use" |
# "give" | "take"] (the level's entries 2, 6 and 11), ["warp", record],
# ["clear"].
#
# @exe game

const PLAYER := preload("res://player.gd")
const LOOT := preload("res://loot.gd")

const TRUTH_GLASS := 0x65
const EATEN := [0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D, 0x77, 0x78]   # item_consume's
const VERDITE := 0x6E
const POWER_FRUIT := 0x6F
const WISE_FRUIT := 0x70
const FIRST_CRYSTAL := 0x71
const FLASK := 0x76
const FOUNTAINS := {0xFE: 0x77, 0xFB: 0x78}   # the type found, the potion it gives
const STATUE_THING := 0x80
const ICHRIUS := {0x82: 1, 0x83: 6, 0x84: 9}  # Ichrius' eye, wings, crown: the warp records
const NO_WARP := [0x19, 0x1B]                 # blocks the warp refuses
const KEYS := [0x87, 0x89, 0x8A, 0x8B, 0x8C, 0x8E, 0x90]
const ORLADIN_KEY := 0x88
const ORLADIN_LOCK := 0xA2
const ORLADIN_PEDESTAL := 0x102
const SILVIERA_KEY := 0x8D
const SILVIERA_PEDESTAL := 0x101
const RING := 0x15E                           # the gold ring, ten slots, drop_count_gold's
const RING_SIZE := 0xA
const AREA_CLASS := 0xE2                      # the class of the named rectangles
const TRUTH_CREATURE := 0x10E                 # ITEM.T: + a creature's model
const TRUTH_SLOT11 := 0x131                   # ITEM.T: slot 11 of block 0x11
const TRUTH_AREA := 0x32A                     # ITEM.T: + a rectangle's +0x3a
const ITEM_ARCHIVE := 6
const BONUS_FRAMES := 0x384                   # 0x801b2578: five on every skill
const STAT_CAP := 0x3E7
const WIS_CAP := 5
const FIND_ADD := 0x320                       # find_object: past the type's reach
const FIND_OWN := 0x6A4                       # the point's height
const FIND_TOL := 0x200                       # of the facing
const NOTHING_HAPPENS := 0xA
const WRONG_KEY := 7
const FILLED := 0xC
const FULL := 0xB                             # give_item's own "can't carry"
const NEW_SPELL := 3

const OBJECT_FIELDS := ["slot", "type", "cls", "b0", "op", "state", "x", "y", "z", "yaw",
	"height", "reach", "top", "lock", "b39", "h3a", "h3c", "b40"]

static var warps: Array = []                  # sub_8005c864's fourteen records


# @port data -- reads useitem.json, sub_8005c864's records as tools/useitem.py wrote them
static func load_from(path := "res://useitem.json") -> bool:
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	warps = d["warps"]
	return true


# The routine: the arm, then the level's entry 2, the banner, the stop.
# @orig game:0x8005cbe0 use_item  status:partial -- every arm but block 6's two statues (their scene runs frames of the game until the creature wakes; here the thing goes on as when none is found); tools/useitem.py 2800 of 2800 runs of the game's own over every level, the self-test this to it; the level's own entries 2, 6 and 11 are logged, not run
# @orig game:0x8005d60c use_item+0xa2c  status:verified -- the eaten things' arm: answered, item_consume has eaten them
# @orig game:0x8005d748 use_item+0xb68  status:verified -- the tail: the level's entry 2, "Nothing happens", clear_movement_state
static func run(w: Dictionary, item: int, c: KFCollision) -> Array:
	var calls := []
	w["answer"] = 0
	if item == TRUTH_GLASS:
		_truth(w, c, calls)
	elif item in EATEN:
		w["answer"] = 1
	elif item == VERDITE or item == POWER_FRUIT or item == WISE_FRUIT \
			or (item >= FIRST_CRYSTAL and item < FIRST_CRYSTAL + 5):
		_figures(w, item, calls)
	elif item == FLASK:
		_flask(w, c, calls)
	elif item == STATUE_THING:
		_statues(w, item, calls)
	elif ICHRIUS.has(item) or (item >= 0x96 and item <= 0xA1):
		_warp(w, item, calls)
	elif item in KEYS:
		_keys(w, item, c, calls)
	elif item == ORLADIN_KEY:
		_orladin(w, item, c, calls)
	elif item == SILVIERA_KEY:
		_silviera(w, item, c, calls)
	calls.append(["hook", "use"])
	if int(w["answer"]) == 0:
		calls.append(["announce", NOTHING_HAPPENS])
	calls.append(["clear"])
	return calls


# The truth glass: the creature in sight on the player's floor -- its page
# ITEM.T 0x10e + its model; else find_object's first object, slot 11 on
# block 0x11 (its +0 not 0), ITEM.T 0x131; else the first class-0xe2
# rectangle on that floor holding the player's cell, ITEM.T 0x32a + its
# +0x3a. The floor: 2 when 0x801b2644 is not 0, else 1 -- a creature's +3 and
# a rectangle's +0x40 say it the same way.
# @orig game:0x8005d584 use_item+0x9a4  status:verified -- tools/useitem.py, the creature, slot 11 and the areas among 2800 runs of the game's own
static func _truth(w: Dictionary, c: KFCollision, calls: Array) -> void:
	var fl := 2 if int(w["layer"]) != 0 else 1
	var pos: Array = w["pos"]
	var seen: Array = PLAYER.sight(c, w["creatures"], pos, int(w["facing"]), int(w["pitch"]),
		0x1F40, 0x1F4, 0x1F4, -1)
	var who = seen[0]
	if who != null and int(who[7]) == fl:
		calls.append(["load_entry", ITEM_ARCHIVE, int(who[6]) + TRUTH_CREATURE])
		w["answer"] = 1
		return
	var k := find_object(w, 0, c)
	if k != -1 and int(w["objects"][k]["b0"]) != 0 and k == 0xB and int(w["block"]) == 0x11:
		calls.append(["load_entry", ITEM_ARCHIVE, TRUTH_SLOT11])
		w["answer"] = 1
		return
	for o in w["objects"]:
		if o == null or int(o["cls"]) != AREA_CLASS or int(o["b40"]) != fl:
			continue
		if KFObjects.player_in_rect(int(pos[0]), int(pos[2]), int(o["x"]) >> 11,
				int(o["z"]) >> 11, int(o["lock"]), int(o["b39"])):
			calls.append(["load_entry", ITEM_ARCHIVE, (int(o["h3a"]) + TRUTH_AREA) & 0xFFFF])
			w["answer"] = 1
			return


# The things that raise a figure: verdite every skill once from 4 down, a
# crystal its own skill three times -- each taken -- the power fruit stat 36
# three times, the wise fruit 0x801b2530 once to 4 (those two item_consume
# has taken). Each step under 1000: skill_unlock (run: a spell it unlocks says
# so, announce 3, and answers), the stats, and a banner the first time --
# 0xd, 0x12 + k, 1, 2. At 1000 the figure is 999 and the step says nothing.
# @orig game:0x8005cc4c use_item+0x6c  status:verified -- the crystals' arm; tools/useitem.py, among 2800 runs of the game's own, skill_unlock run
# @orig game:0x8005cd04 use_item+0x124  status:verified -- verdite's arm
# @orig game:0x8005cd90 use_item+0x1b0  status:verified -- the power fruit's arm
# @orig game:0x8005ce10 use_item+0x230  status:verified -- the wise fruit's arm
static func _figures(w: Dictionary, item: int, calls: Array) -> void:
	var sk: Array = w["skills"]
	if item == WISE_FRUIT:
		w["wis"] = (int(w["wis"]) + 1) & 0xFFFF
		if int(w["wis"]) >= WIS_CAP:
			w["wis"] = WIS_CAP - 1
			return
		calls.append(["recalc"])
		if int(w["answer"]) == 0:
			w["answer"] = 1
			calls.append(["announce", 2])
		return
	if item == POWER_FRUIT:
		for _i in 3:
			w["stat36"] = (int(w["stat36"]) + 1) & 0xFFFF
			if int(w["stat36"]) >= 1000:
				w["stat36"] = STAT_CAP
				continue
			calls.append(["recalc"])
			if int(w["answer"]) == 0:
				w["answer"] = 1
				calls.append(["announce", 1])
		return
	_take(w, item, calls)
	var ks := [4, 3, 2, 1, 0]
	if item != VERDITE:
		var k0 := item - FIRST_CRYSTAL
		ks = [k0, k0, k0]
	for k in ks:
		sk[k] = (int(sk[k]) + 1) & 0xFFFF
		if int(sk[k]) >= 1000:
			sk[k] = STAT_CAP
			continue
		var st := {"grow": sk, "spells": w["spells"]}
		for b in KFLevels.skill_unlock(st, k, w["flags"]):
			calls.append(["announce", int(b)])
			w["answer"] = 1
		calls.append(["recalc"])
		if int(w["answer"]) == 0:
			w["answer"] = 1
			calls.append(["announce", 0xD if item == VERDITE else 0x12 + k])


# The crystal flask: find_object's first object, a fountain of type 0xfe
# fills it with a blue potion, one of 0xfb with a gold one -- given, announce
# 0xc and the flask taken; the pack full, give_item's own banner (0xb) and
# the flask kept. Either way it answers.
# @orig game:0x8005d450 use_item+0x870  status:verified -- tools/useitem.py: filled, and the pack full, among 2800 runs of the game's own
static func _flask(w: Dictionary, c: KFCollision, calls: Array) -> void:
	var k := find_object(w, 0, c)
	if k == -1 or not FOUNTAINS.has(int(w["objects"][k]["type"])):
		return
	var inv: KFItems = w["inv"]
	if inv.give_item(int(FOUNTAINS[int(w["objects"][k]["type"])])):
		calls.append(["hook", "give"])
		calls.append(["announce", FILLED])
		_take(w, FLASK, calls)
	else:
		calls.append(["announce", FULL])
	w["answer"] = 1


# The thing 0x80: off block 6, taken and 0x801b2578 900 frames -- five on
# every skill, as player_recalc_stats reads it -- and the stats.
# @orig game:0x8005ce7c use_item+0x29c  status:partial -- off block 6; on it, the two statues (slots 0x5b and 0x53: their creatures' scenes, story bytes 0x801ba9ab and 0x801ba9b0) are not run, and the thing goes on as when none is found
static func _statues(w: Dictionary, item: int, calls: Array) -> void:
	_take(w, item, calls)
	w["b578"] = BONUS_FRAMES
	w["answer"] = 1
	calls.append(["recalc"])


# Ichrius' eye, wings and crown, and the ids 0x96..0xa1 nothing holds:
# sub_8005c864 with record 1, 6 or 9 (item - 0x96 for the rest) -- not on
# blocks 0x19 and 0x1b, nor while a change to one is under way. It answers
# itself, unless its record's level is 0xff (record 8).
# @orig game:0x8005d500 use_item+0x920  status:verified -- tools/useitem.py, the warp's call and its refusal among 2800 runs of the game's own; the warp itself stood in for
static func _warp(w: Dictionary, item: int, calls: Array) -> void:
	var i: int = int(ICHRIUS.get(item, item - 0x96))
	if int(w["block"]) in NO_WARP or (int(w["busy"]) == 1 and int(w["pending"]) in NO_WARP):
		return
	calls.append(["warp", i])
	if warp_answers(i):
		w["answer"] = 1


# Whether sub_8005c864(i) answers: it returns at once for a record whose
# level is 0xff (0x8005c938), and sets 0x801ba984 below record 0xc
# (0x8005cb94).
# @port helper -- what sub_8005c864 answers, read off it; the warp itself is the caller's
static func warp_answers(i: int) -> bool:
	if (i < 0xC or i == 0xD) and i < warps.size() and int(warps[i][0]) == 0xFF:
		return false
	return i < 0xC


# The seven keys of the shared arm: each object find_object finds in turn has
# the key tried on it (key_test): 1 it fitted -- the lock 0xff, open to USE
# -- and the sound; 3 or 4 "Wrong key!"; anything else the next object. The
# key is kept.
# @orig game:0x8005d188 use_item+0x5a8  status:verified -- tools/useitem.py, fits and wrong among 2800 runs of the game's own; not the sound when one fits (sound_key_fits), which is logged
static func _keys(w: Dictionary, item: int, c: KFCollision, calls: Array) -> void:
	var k := 0
	while true:
		k = find_object(w, k, c)
		if k == -1:
			return
		var got := LOOT.key_test(w["objects"][k], "lock", item)
		if got == 1:
			calls.append(["sound_key_fits"])
			w["answer"] = 1
			return
		if got == 3 or got == 4:
			calls.append(["announce", WRONG_KEY])
			w["answer"] = 1
			return
		k += 1


# Orladin's key: every object find_object finds. A type-0xa2 lock that asks
# for it (+0x38 0x88) is 0xfe after, and the key taken; a free type-0x102
# pedestal (+0x38 0xff) holds the key's number, its state 0, the key taken
# and the key's own object made in the gold ring -- find_free_slot with
# drop_count_gold, init_object_record, its type the key's and its +0x3c the
# count -- the pedestal's +0x39 its place; anything else a 3 from key_test
# "Wrong key!".
# @orig game:0x8005d300 use_item+0x720  status:verified -- tools/useitem.py, the locks, the pedestals and wrong among 2800 runs of the game's own; in the port nothing yet acts on what it leaves (opcodes 0x17 and 0x1a are not in)
static func _orladin(w: Dictionary, item: int, c: KFCollision, calls: Array) -> void:
	var k := 0
	while true:
		k = find_object(w, k, c)
		if k == -1:
			return
		var o: Dictionary = w["objects"][k]
		if int(o["type"]) == ORLADIN_LOCK:
			if int(o["lock"]) == ORLADIN_KEY:
				o["lock"] = 0xFE
				w["answer"] = 1
				_take(w, item, calls)
		elif int(o["type"]) == ORLADIN_PEDESTAL:
			if int(o["lock"]) == 0xFF:
				o["lock"] = item
				o["state"] = 0
				w["answer"] = 1
				_take(w, item, calls)
				var m := free_slot(w, RING, RING_SIZE, int(w["drops"]))
				if m < 0:                     # every one as new as now: the game's is address 0
					k += 1
					continue
				var made := {}
				if w["objects"][m] != null:
					made = (w["objects"][m] as Dictionary).duplicate()
				else:
					for f in OBJECT_FIELDS:
						made[f] = 0
					made["slot"] = m
					made["lock"] = 0xFF
					made["b39"] = 0xFF
				made["b0"] = 0                # init_object_record (0x800448b8)
				made["op"] = 0xFF
				made["made"] = true
				made["h3c"] = int(w["drops"])
				w["drops"] = (int(w["drops"]) + 1) & 0xFFFF
				made["type"] = item
				made["lock"] = 0
				w["objects"][m] = made
				o["b39"] = (m - 0x5E) & 0xFF
		elif LOOT.key_test(o, "lock", item) == 3:
			calls.append(["announce", WRONG_KEY])
			w["answer"] = 1
		k += 1


# Silviera's key: find_object's first object, and that one only. A free
# type-0x101 pedestal (+0x38 0xff) takes it -- the lock the key's number, the
# state 0, the key out of the pack -- and pedestal_put_key stands it there;
# anything else has the key tried on it, and a 3 is "Wrong key!". A key that
# fits says nothing.
# @orig game:0x8005d244 use_item+0x664  status:verified -- tools/useitem.py, put and wrong among 2800 runs of the game's own; held to silv1 and silv2 through tools/chests.py check_pedestal
static func _silviera(w: Dictionary, item: int, c: KFCollision, calls: Array) -> void:
	var k := find_object(w, 0, c)
	if k == -1:
		return
	var o: Dictionary = w["objects"][k]
	if int(o["type"]) == SILVIERA_PEDESTAL:
		if int(o["lock"]) != 0xFF:
			return
		o["lock"] = item
		o["state"] = 0
		w["answer"] = 1
		_take(w, item, calls)
		calls.append(["put_key", k, item])
	elif LOOT.key_test(o, "lock", item) == 3:
		calls.append(["announce", WRONG_KEY])
		w["answer"] = 1


# take_item on the pack, and the level's entry 11 when one was taken.
# @port helper -- KFItems.take_item, which is the game's, and the hook it calls logged
static func _take(w: Dictionary, item: int, calls: Array) -> void:
	var inv: KFItems = w["inv"]
	if inv.take_item(item):
		calls.append(["hook", "take"])


# find_object (0x80045c7c) from the player's feet along the facing, as
# use_item asks it -- 0x320 past the type's reach, 0x6a4 as the point's
# height, within 0x200: from slot `start` on, the first object whose type is
# not 0xff in range and, but for type 0x95, faced. A class-0x1b door is asked
# from 0x700 ahead of the point along its own yaw, a class-0 one from 0x700
# behind and a class-1 one from 0x400 behind, the record's +0xc its top;
# anything else from the point, the type's +8 its top.
# @orig game:0x80045c7c find_object  status:verified -- through use_item, tools/useitem.py: 2800 of 2800 runs of the game's own over every level, the doors among them
static func find_object(w: Dictionary, start: int, c: KFCollision) -> int:
	var pos: Array = w["pos"]
	var objs: Array = w["objects"]
	for k in range(maxi(start, 0), objs.size()):
		var o = objs[k]
		if o == null or int(o["type"]) == 0xFF:
			continue
		var cls := int(o["cls"])
		var door := cls == 0x1B or cls == 0 or cls == 1
		var x := int(pos[0])
		var z := int(pos[2])
		var top := int(o["top"])
		if door:
			var off := 0x700 if cls == 0x1B else (-0x700 if cls == 0 else -0x400)
			x += (c.game_cos(int(o["yaw"])) * off) >> 12
			z += (c.game_sin(int(o["yaw"])) * off) >> 12
			top = int(o["height"])
		if c.in_range(int(o["x"]), int(o["y"]), int(o["z"]), x, int(pos[1]), z,
				int(o["reach"]) + FIND_ADD, top, FIND_OWN) < 0:
			continue
		if not door and int(o["type"]) == 0x95:
			return k
		var ang := KFWeapon.s16(c.vec_angle(PLAYER._s32(int(o["x"]) - x), PLAYER._s32(int(o["z"]) - z)))
		var d := (int(w["facing"]) - ang) & 0xFFF
		if d <= FIND_TOL or d >= 0x1000 - FIND_TOL:
			return k
	return -1


# find_free_slot (0x80046034) over the world: of `count` slots from `start`,
# the first whose type is 0xff, else the oldest by `counter` minus its +0x3c,
# mod 0x10000; -1 when none is older than now, where the game's answer is 0.
# @orig game:0x80046034 find_free_slot  status:verified -- through use_item's Orladin arm, tools/useitem.py among 2800 runs of the game's own
static func free_slot(w: Dictionary, start: int, count: int, counter: int) -> int:
	var chosen := -1
	var age := 0
	for k in range(start, start + count):
		var o = w["objects"][k]
		if o == null or int(o["type"]) == 0xFF:
			return k
		if counter == -1:
			continue
		var d := counter - int(o["h3c"])
		if d < 0:
			d += 0x10000
		if age < d:
			chosen = k
			age = d
	return chosen

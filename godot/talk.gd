class_name KFTalk
# A conversation as the player meets it: one call of script_interpreter
# (0x8005c308) for every USE on the talker. tools/talk.py is the same in
# Python, and holds it to bp21's recording.
#
# The state lives in the conversation's block between calls -- the pc at
# +0x10, the retry flag at +0x13 -- and in the global script_speaker
# (0x801baa2e), the actor[+1] of whoever talked last. A call:
#
#   a zero pc       the speaker becomes this actor
#   script_prescan  the pc a guard picks, or past the 0xfe (escript.gd)
#   the speaker not this actor and the retry flag set: on to past the next
#                   0xf0 and its operand, the flag clear
#   then op by op until a line -- TALK.T[+0xc + op], shown by load_entry
#   (document.gd) -- after which the call goes on only if a step is left:
#   the press that closed the line had USE in it and +0x12 is 0xff, or 0xf5
#   gave some; 0xf4 calls the level's hook, entry 4; 0xf7 sets a story flag;
#   0xf3 spends a step, 0xff ends it
#   the end         +0x12's service, the speaker this actor, the end animation
#
# So on level 0, where the men by the house have no service, each USE that
# closes a line brings the next; the last line of a section (0xf0) comes back
# for as long as USE closes it, and anything else stops the call.
#
# @exe game

const NO_SERVICE := 0xFF
const SPELLS_6 := [0x38, 0x3A, 0x3C, 0x3E, 0x40, 0x4C]   # level 6's lesson unlocks these
const SPELLS_8 := [0x36, 0x37, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B]   # and level 8's these
const LINE_OPS := [0xF1, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE]
const FLAG_COUNT := 0x100

static var flags := []             # story_flags, 0x801ba988
static var speaker := -1           # script_speaker, 0x801baa2e
static var states := {}            # "level/entity" -> {pc, retry}: each block's +0x10, +0x13
static var scripts := {}           # level -> {entity: escript.json's script}


# @port data -- escript.json's conversations for the level, keyed by entity
static func load_level(level: int) -> void:
	if flags.size() != FLAG_COUNT:
		flags.resize(FLAG_COUNT)
		flags.fill(0)
	if scripts.has(level) or not FileAccess.file_exists("res://escript.json"):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://escript.json"))
	var out := {}
	if typeof(d) == TYPE_DICTIONARY:
		for sc in d["scripts"]:
			if int(sc["level"]) == level:
				out[int(sc["entity"])] = sc
	scripts[level] = out


# @port helper -- the conversation for an actor's kind (its +2, the entity), or {}
static func script_for(level: int, entity: int) -> Dictionary:
	load_level(level)
	return (scripts[level] as Dictionary).get(entity, {})


# @port helper -- below 0xf0, and 0xf1, 0xfa..0xfe
static func is_line(op: int) -> bool:
	return op < 0xF0 or op in LINE_OPS


# The start of a call: the speaker, script_prescan and the retry scan.
# @orig game:0x8005c308 script_interpreter  status:verified -- the entry: 21 of 21 calls bp21 caught start at the game's pc (tools/talk.py); not the talking animation (+1, +8 and +0x11, +0xe), the voice (seq_lookup) or the services of +0x12
static func begin(level: int, entity: int, sc: Dictionary, model: int) -> Dictionary:
	var key := "%d/%d" % [level, entity]
	if not states.has(key):
		states[key] = {"pc": 0, "retry": 0}
	var st: Dictionary = states[key]
	var code := PackedByteArray(sc["code"])
	if int(st["pc"]) == 0:
		speaker = model
	var pc := KFScript.start_pc(code, flags, int(st["pc"]))
	if speaker != model and int(st["retry"]) == 1:
		var i := pc
		if int(code[i]) == 0xF0:
			i += 1
		else:
			i += 1
			while true:
				var v := int(code[i])
				i += 1
				if v == 0xF0:
					break
		pc = i + 1
		st["retry"] = 0
	return {"sc": sc, "code": code, "st": st, "pc": pc, "s3": 0, "model": model,
		"done": false, "why": "", "hooks": []}


# Ops until a line -- its TALK.T entry -- or the end of the call (-1).
# @orig game:0x8005c3f8 script_interpreter+0xf0  status:verified -- the ops and the lines: 21 of 21 calls bp21 caught, op for op (tools/talk.py), and the self-test
static func advance(c: Dictionary, hook: Callable = Callable()) -> int:
	if bool(c["done"]):
		return -1
	var code: PackedByteArray = c["code"]
	var st: Dictionary = c["st"]
	var h: Dictionary = c["sc"]["header"]
	for _i in 1000:
		var pc := int(c["pc"])
		if pc < 0 or pc >= code.size():
			return _end(c, "off")
		var op := int(code[pc])
		if is_line(op):
			return int(h["talk"]) + op
		match op:
			0xF0, 0xF8:
				if op == 0xF0:
					st["retry"] = 1
				c["pc"] = pc - int(code[pc + 1])
			0xF9:
				if int(flags[int(code[pc + 1])]) == int(code[pc + 2]):
					var t := KFScript.find_label(code, int(code[pc + 3]))
					c["pc"] = t if t >= 0 else pc + 4
				else:
					c["pc"] = pc + 4
			0xF2:
				c["pc"] = pc + 2
			0xF6:
				speaker = int(c["model"])
				st["retry"] = 0
				c["pc"] = pc + 1
			0xF4:
				(c["hooks"] as Array).append(int(code[pc + 1]))
				if hook.is_valid():
					hook.call(int(code[pc + 1]))
				c["pc"] = pc + 1
				if not _step(c):
					return -1
			0xF5:
				c["s3"] = int(code[pc + 1])
				c["pc"] = pc + 1
				if not _step(c):
					return -1
			0xF7:
				flags[int(code[pc + 1])] = int(code[pc + 2])
				c["pc"] = pc + 2
				if not _step(c):
					return -1
			0xF3:
				c["pc"] = pc + 1
				if int(c["s3"]) == 0:
					return _end(c, "spent")
				c["s3"] = int(c["s3"]) - 1
			_:
				return _end(c, "end")
	return _end(c, "limit")


# After a line: one more step when USE closed it and +0x12 is 0xff, then the
# step test.
# @orig game:0x8005c604 script_interpreter+0x2fc  status:verified -- the line's tail, the USE test and .L18's step: where the 21 calls bp21 caught end and go on
static func closed(c: Dictionary, use: bool) -> void:
	if use and int(c["sc"]["header"]["service"]) == NO_SERVICE:
		c["s3"] = int(c["s3"]) + 1
	_step(c)


# .L18: pc on one; a step left is spent and the call goes on, else it ends.
# @port helper -- false when the call has ended
static func _step(c: Dictionary) -> bool:
	c["pc"] = int(c["pc"]) + 1
	if int(c["s3"]) == 0:
		_end(c, "wait")
		return false
	c["s3"] = int(c["s3"]) - 1
	return true


# The end of a call: the pc kept, the speaker this actor.
# @orig game:0x8005c654 script_interpreter+0x34c  status:partial -- the pc and the speaker; not +0x12's services (the inn, the shop, the scenes) nor the end animation
static func _end(c: Dictionary, why: String) -> int:
	c["done"] = true
	c["why"] = why
	(c["st"] as Dictionary)["pc"] = int(c["pc"])
	speaker = int(c["model"])
	return -1


# The level's own entry 7 (level_hooks + 0x1c), which cutscene_step's phase
# 8 calls with the scene after the movie -- a night's dream at the inn:
# level 0's, for scene 0 alone, the HP to its most and the MP 30 on, held to
# its most; level 1's the HP to its most, for any scene. [hp, mp].
# @orig game:0x80061b8c cutscene_step+0x24c  status:verified -- the call of the level's entry 7; level 0's (overlay 0x801e89d8) and level 1's (overlay 0x801e88cc) written out here, tools/ui.py night_heal, each 12 of 12 against the overlay's own code run over menu1 (inn_check)
static func night(level: int, scene: int, hp: int, hp_max: int, mp: int, mp_max: int) -> Array:
	if level == 0 and scene & 0xFF == 0:
		mp = (mp + 0x1E) & 0xFFFF
		hp = hp_max
		if mp_max < mp:
			mp = mp_max
	elif level == 1:
		hp = hp_max
	return [hp, mp]


# What 0xf4 calls: the level's own entry 4 (level_hooks + 0x10), which lives
# in the level's overlay -- every level's arms, as tools/hooks.py reads them
# and holds them to the overlays' own code. `w` is the world as the arm reads
# it -- flags (story_flags), inv (KFItems), cats and floors (the creatures'
# +0 and +3), objects (the views use_item takes, by slot), skills, spells,
# answer, weapon (equipped_weapon), minutes (play_minutes), exp (player_exp),
# chosen (the pack chooser's answer), buttons and bind_use -- and changes as
# RAM would; the calls are what the arm makes beyond what it runs, for the
# caller to act out: ["give", type] (object_give), ["stamp", b0, sx, sz, dx,
# dz, w, h, angle, mask] (stamp_rect), ["equip_weapon", id], ["equip_armour",
# id, slot], ["light", ...] (0x8005d948), ["da10", ...], ["bare"]
# (render_frame_bare), ["choose"] (0x80021d94), ["sound_key_fits"],
# ["recalc"], ["announce", code], ["hook", "take"].
# @orig game:0x8005c4c0 script_interpreter+0x1b8  status:verified -- 0xf4's call into the level's entry 4; the fifteen levels' 45 arms out of their overlays, written out here as tools/hooks.py, which the overlays' own code holds (2400 of 2400 runs), the self-test this to it
static func hook(level: int, a: int, w: Dictionary) -> Array:
	var calls := []
	var f: Array = w["flags"]
	var inv: KFItems = w["inv"]
	var exp32 := int(w["exp"]) & 0xFFFFFFFF          # player_exp, a signed word
	if exp32 >= 0x80000000:
		exp32 -= 0x100000000
	match level:
		0:
			var pieces := inv.has_item(0x82) and inv.has_item(0x83) and inv.has_item(0x84)
			match a:
				0:
					f[3] = 1 if pieces and inv.has_item(2) else 0
				1:
					if pieces and inv.has_item(2):
						f[1] = 1
						w["answer"] = 1
						for id in [0x82, 0x83, 0x84, 2]:
							_take(inv, id, calls)
						if int(w["weapon"]) == 2:
							calls.append(["equip_weapon", 0xFF])
				2:
					w["cats"][1] = 8
					w["cats"][2] = 1
					f[2] = 1
					f[4] = posmod(int(w["minutes"]), 60) & 0xFF
					f[5] = (exp32 % 10000) / 100 & 0xFF
				4:
					var mins := posmod(int(w["minutes"]), 60)
					if mins < int(f[4]) or mins >= int(f[4]) + 10:
						f[6] = 1
					var e := (exp32 % 10000) / 100
					if e < int(f[5]) or e >= int(f[5]) + 10:
						f[6] = 1
				5:
					f[1] = 1 if pieces else 0
		1:
			match a:
				0:
					if int(f[0xD]) == 0:
						f[0xD] = 1
						calls.append(["stamp", 2, 0x4E, 0, 0x1B, 0x11, 1, 7, 0, 0x2F])
				1:
					calls.append(["give", 0x74])
				2:
					calls.append(["give", 0x72])
		2:
			if a >= 0 and a < 4:
				f[0x10] = [0x68, 0x6C, 0x6D, 0x6B][a]
			elif a == 4:
				calls.append(["give", 0x56])
			elif a == 5:
				calls.append(["give", 0x52])
		3:
			match a:
				0:
					f[0x77] = 1 if inv.has_item(0x7C) else 0
				1:
					calls.append(["bare"])
					calls.append(["choose"])
					var got := int(w["chosen"])
					w["buttons"] = ~int(w["bind_use"]) & 0xFFFF
					if got < 0:
						f[0x74] = 0
						f[0x72] = 0x68
					else:
						f[0x75] = 0
						f[0x74] = 1
						f[0x72] = got & 0xFF
				2:
					calls.append(["give", int(f[0x72])])
		4:
			match a:
				0, 1:
					var k := 0x17 if a == 0 else 0x18
					if int(f[k]) != 1:
						f[k] = 1
						calls.append(["give", 0x7B if a == 0 else 0x5F])
				2:
					if inv.has_item(0x84):
						f[0x1A] = 1
				3:
					w["cats"][8] = 8
				4:
					f[0x16] = 1
		5:
			match a:
				0:
					for o in w["objects"]:
						if o != null and int(o["op"]) == 0x56:
							o["scale"] = 0
							o["lock"] = 0
							o["b0"] = 0
							o["op"] = 0xFF
					if inv.has_item(0x66):
						_take(inv, 0x66, calls)
					calls.append(["give", 0x82])
					f[0x1E] = 1
				1:
					if int(f[0x1D]) == 0:
						calls.append(["give", 0x60])
						f[0x1D] = 1
				2:
					calls.append(["give", 0x66])
		6:
			match a:
				0:
					f[0x22] = 1
				1:
					calls.append(["give", 0x80])
				2:
					f[0x21] = 1
				3:
					calls.append(["give", 0x83])
					f[0x24] = 1
				4:
					calls.append(["light", 0x200, 0, 0, 0, 0x80, 0xC8, 0x80])
					calls.append(["light", 0x200, 0x80, 0xC8, 0x80, 0, 0, 0])
					calls.append(["da10", 0, 0, 0, 0, 1])
					f[0x27] = 1
					for s in SPELLS_6:
						w["spells"][s] = 1
				5:
					calls.append(["give", 0xA])
		7:
			if a == 0:
				f[0x2A] = 1
		8:
			match a:
				0:
					calls.append(["light", 0x200, 0, 0, 0, 0x80, 0xC8, 0x80])
					calls.append(["light", 0x200, 0x80, 0xC8, 0x80, 0, 0, 0])
					f[0x2D] = 1
					for s in SPELLS_8:
						w["spells"][s] = 1
				1:
					f[0x2E] = 1
					w["cats"][1] = 8
		9:
			if a == 0 or a == 1:
				f[0x33 + a] = 1
		10:
			if a == 0:
				calls.append(["give", 0x90])
			elif a == 1 and int(f[0x39]) == 0:
				f[0x39] = 1
		13:
			if a == 0 and int(f[0x42]) == 0:
				f[0x42] = 1
				f[0x43] = 0
		17:
			if a == 0 and int(f[0x52]) != 1:
				f[0x52] = 1
				var things := [0x29, 0x31, 0x46, 0x4F, 0x3C]
				for slot in things.size():
					calls.append(["give", things[slot]])
					calls.append(["equip_armour", things[slot], slot])
				var o = w["objects"][63]
				if o != null:
					o["b0"] = 2
					o["b3f"] = 0xFF
			elif a == 1 and int(f[0x53]) == 1:
				f[0x53] = 2
				calls.append(["light", 0x200, 0, 0, 0, 0xC8, 0xC8, 0xC8])
				calls.append(["light", 0x200, 0xC8, 0xC8, 0xC8, 0, 0, 0])
				w["skills"][4] = (int(w["skills"][4]) + 0x1E) & 0xFFFF
				var st := {"grow": w["skills"], "spells": w["spells"]}
				for b in KFLevels.skill_unlock(st, 4, f):     # run: each spell it unlocks says so and answers
					calls.append(["announce", int(b)])
					w["answer"] = 1
				calls.append(["recalc"])
				w["cats"][56] = 8
				w["floors"][56] = 0
		22:
			if a == 0 or a == 1:
				f[0x5B + a] = 1
		26:
			if a == 0 and int(f[0x60]) == 0:
				f[0x60] = 1
				KFUseItem.object_signal(w, 0xF2)
				calls.append(["sound_key_fits"])
	return calls


# take_item on the pack, and the level's entry 11 when one was taken.
# @port helper -- KFItems.take_item, which is the game's, and the hook it calls logged
static func _take(inv: KFItems, item: int, calls: Array) -> void:
	if inv.take_item(item):
		calls.append(["hook", "take"])

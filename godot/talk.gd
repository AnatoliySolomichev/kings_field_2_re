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
# @orig game:0x8005c308 script_interpreter  status:transcribed -- the entry; not the talking animation (+1, +8 and +0x11, +0xe), the voice (seq_lookup) or the services of +0x12
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
# @orig game:0x8005c3f8 script_interpreter+0xf0  status:transcribed -- the ops and the lines; tools/talk.py against bp21, and the self-test
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
# @orig game:0x8005c604 script_interpreter+0x2fc  status:transcribed -- the line's tail: the USE test and .L18's step
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


# What 0xf4 calls: the level's own entry 4 (level_hooks + 0x10), which lives
# in the level's overlay. Level 0's arms 0, 1 and 5, as tools/quest.py reads
# them -- whether the player holds the three pieces of Ichrius (130, 131, 132)
# and the sword (2), and the trade.
# @orig game:0x8005c4c0 script_interpreter+0x1b8  status:partial -- 0xf4's call into the level's entry 4; level 0's overlay arms 0, 1 and 5 written out here (tools/quest.py); arms 2 and 4 read the play clock (0x801b2588, 0x801b24e4) and are not, nor arm 1's unequipping
static func hook(level: int, a: int, inv: KFItems) -> void:
	if level != 0 or inv == null:
		return
	var pieces := inv.has_item(130) and inv.has_item(131) and inv.has_item(132)
	match a:
		0:
			flags[3] = 1 if pieces and inv.has_item(2) else 0
		1:
			if pieces and inv.has_item(2):
				flags[1] = 1
				for id in [130, 131, 132, 2]:
					inv.take_item(id)
		5:
			flags[1] = 1 if pieces else 0

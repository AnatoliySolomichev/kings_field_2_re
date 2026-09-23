class_name KFScript
# A conversation, stepped the way the game steps it.
#
# `script_interpreter` (0x8005c308) takes an entity's 120-byte record out of
# `entity_table` at `120 * actor[+2]`, and the conversation from that record's
# **`+0x38`** -- the first of sixteen block pointers `entity_table_init`
# relocates, and the only one any code in GAME.EXE reads. It has to begin
# 0x70; 43 entities in the game have one. The block is a 20-byte header --
# the TALK.T base at `+0x0c`, the program counter at `+0x10`, what happens
# when the talking stops at `+0x12`, the retry flag at `+0x13` -- and then
# code, with `pc` counting from `+0x14`.
#
# **Starting.** `script_prescan` (0x8005c1e8) reads the code from pc 0, where
# a chain of four-byte guards sits:
#
#   0xf1 flag value label   start at `label` when story_flags[flag] == value
#
# The first guard that holds wins, and only if its label is further on than
# the pc already stored. The chain ends with a lone 0xfe, and a fresh
# conversation starts just past it -- pc 1 when there are no guards.
#
# A byte below 0xf0 -- and 0xf1, 0xfa..0xfe, which share the same arm -- is a
# **line**: the interpreter drives the animation, loads `TALK.T[base + byte]`,
# draws a frame, and then **waits for the use button**. Everything else
# dispatches through a 16-arm table at 0x80013160:
#
#   0xf0 n    pc -= n, and set the retry flag -- a section break, see `visits`
#   0xf2 n    a label; a two-byte no-op when it is executed
#   0xf3      spend one of the run-on count
#   0xf4 a n  call the level's own code with a, then take n as a run-on count
#   0xf5 n    run the next n lines without waiting
#   0xf6      script_speaker = actor[+1], and clear the retry flag
#   0xf7 i v  story_flags[i] = v
#   0xf8 n    pc -= n
#   0xf9 i v t   if story_flags[i] == v, jump to **label** t
#   0xff      stop
#
# `0xf9` and the guards name a label, not an offset. `0x8005c18c` resolves
# one by scanning the code from pc 0 for an `0xf2` byte and comparing what
# follows; it scans bytes rather than instructions and gives up at the first
# 0xff, and `find_label` below reproduces both.
#
# **What this reproduces is the order of execution and the flags.** The
# waiting is not reproduced: every line is taken at once, and a line yields
# its byte for the caller to turn into text and animation.
#
# Held to `tools/escript.py`, which is in turn held to what `emu/bp21.lua`
# recorded in play. An earlier version of this file agreed with an earlier
# version of that one on 1086 scripts; they were not scripts, and the
# agreement meant nothing. See tools/entities.py.
# @orig game:0x8005c308 script_interpreter  status:partial -- flow and flags

const FLAG_COUNT := 0x80
const END := 0xFF
const HEADER := 0x14        # the code starts here, and pc counts from here
const CONVERSATION := 0x70  # the block kind the interpreter will run

# The bytes that are lines rather than opcodes, above 0xf0.
const LINE_OPS := [0xF1, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE]
# opcode -> how far the pointer moves when nothing else decides.
const SIZE := {0xF0: 2, 0xF2: 2, 0xF3: 1, 0xF4: 3, 0xF5: 2, 0xF6: 1,
	0xF7: 3, 0xF8: 2, 0xF9: 4, 0xFF: 1}


static func is_line(op: int) -> bool:
	return op < 0xF0 or op in LINE_OPS


# @orig game:0x8005c18c script_find_label  status:verified
static func find_label(code: PackedByteArray, want: int) -> int:
	var i := 0
	while i < code.size():
		var b := int(code[i])
		i += 1
		if b == 0xF2:
			if i < code.size() and int(code[i]) == want:
				return i + 1
			i += 1
		elif b == END:
			return -1
	return -1


# @orig game:0x8005c1e8 script_prescan  status:verified
static func start_pc(code: PackedByteArray, flags: Array = [], pc := 0) -> int:
	var f: Array = flags.duplicate() if flags.size() == FLAG_COUNT else _zeros()
	var i := 0
	while i + 3 < code.size() and int(code[i]) == 0xF1:
		var flag := int(code[i + 1])
		if flag < f.size() and int(f[flag]) == int(code[i + 2]):
			var t := find_label(code, int(code[i + 3]))
			return t if t > pc else pc
		i += 4
	if i < code.size() and int(code[i]) == 0xFE and pc == 0:
		return i + 1
	return pc


# @orig game:0x8005c308 script_interpreter  status:partial
static func run(code: PackedByteArray, flags: Array = [],
		limit := 400, stop_on_loop := true) -> Dictionary:
	var f: Array = flags.duplicate() if flags.size() == FLAG_COUNT \
		else _zeros()
	var pc := start_pc(code, f)
	var run_on := 0
	var trace: Array = []
	var said: Array = []
	var seen := {}
	for _step in range(limit):
		if pc < 0 or pc >= code.size():
			return _done(trace, said, f, "off")
		var op := int(code[pc])
		var key := pc * 256 + op
		if stop_on_loop and op == 0xF0 and seen.has(key):
			trace.append([pc, op])
			return _done(trace, said, f, "loop")
		seen[key] = true
		trace.append([pc, op])
		if is_line(op):
			said.append(op)
			pc += 1
			run_on = maxi(run_on - 1, 0)
			continue
		if op == END:
			return _done(trace, said, f, "end")
		match op:
			0xF0, 0xF8:
				pc -= int(code[pc + 1]) if pc + 1 < code.size() else 0
			0xF7:
				var i := int(code[pc + 1])
				if i < f.size():
					f[i] = int(code[pc + 2])
				pc += 3
				run_on = maxi(run_on - 1, 0)
			0xF9:
				var fi := int(code[pc + 1])
				if fi < f.size() and int(f[fi]) == int(code[pc + 2]):
					var t := find_label(code, int(code[pc + 3]))
					pc = t if t >= 0 else pc + 4
				else:
					pc += 4
			0xF5:
				run_on = int(code[pc + 1])
				pc += 2
			0xF4:
				run_on = int(code[pc + 2]) if pc + 2 < code.size() else 0
				pc += 3
			0xF3:
				pc += 1
				if run_on > 0:
					run_on -= 1
			0xF6:
				pc += 1
			_:
				pc += int(SIZE.get(op, 1))
	return _done(trace, said, f, "limit")


# What the entity says on the first visit, the second, and so on.
#
# `0xf0` is a section break: it jumps back onto the line before it and sets
# the retry flag, so pressing the button again repeats that last line for
# ever. What moves the conversation on is talking to somebody *else* --
# `script_interpreter` compares the global `script_speaker` (0x801baa2e,
# the previous talker's `actor[+1]`) against this one's, and when they differ
# and the retry flag is set it scans forward from the stored pc to the next
# `0xf0` and resumes just past it. `0xf8` jumps back without setting the
# flag, so a section ending on one repeats for ever: the entity is out of
# things to say.
# @orig game:0x8005c308 script_interpreter  status:verified -- .L1..L3 and .L6
static func visits(code: PackedByteArray, flags: Array = [],
		count := 16, limit := 400) -> Array:
	var f: Array = flags.duplicate() if flags.size() == FLAG_COUNT else _zeros()
	var pc := 0
	var retry := false
	var out: Array = []
	for _visit in range(count):
		var p := start_pc(code, f, pc)
		if retry:
			var i := p
			while i < code.size() and int(code[i]) != 0xF0:
				i += 1
			p = mini(i + 2, code.size())
			retry = false
		var said: Array = []
		var why := "off"
		for _step in range(limit):
			if p < 0 or p >= code.size():
				why = "off"
				break
			var op := int(code[p])
			if is_line(op):
				said.append(op)
				p += 1
				continue
			if op == END:
				why = "end"
				break
			if op == 0xF0:
				retry = true
				why = "break"
				break
			if op == 0xF8:
				why = "repeat"
				break
			if op == 0xF9:
				var fi := int(code[p + 1])
				var t := -1
				if fi < f.size() and int(f[fi]) == int(code[p + 2]):
					t = find_label(code, int(code[p + 3]))
				p = t if t >= 0 else p + 4
				continue
			if op == 0xF7 and p + 2 < code.size() and int(code[p + 1]) < f.size():
				f[int(code[p + 1])] = int(code[p + 2])
			p += int(SIZE.get(op, 1))
		out.append(said)
		pc = p
		if why == "end" or why == "repeat" or why == "off":
			break
	return out


static func _done(trace: Array, said: Array, f: Array, why: String) -> Dictionary:
	return {"trace": trace, "said": said, "flags": f, "why": why}


static func _zeros() -> Array:
	var f: Array = []
	f.resize(FLAG_COUNT)
	f.fill(0)
	return f

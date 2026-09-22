class_name KFScript
# The entity script language, stepped the way the game steps it.
#
# `script_interpreter` (0x8005c308) takes an entity's 120-byte record out of
# `entity_table` at `120 * record[+2]`, and its running state from that
# record's `+0x38` -- which has to begin 0x70. The state carries the program
# counter at `+0x10`, the retry flag at `+0x13`, the wait state at `+0x12` and
# the TALK.T base at `+0x0c`.
#
# A byte below 0xf0 -- and 0xf1, 0xfa..0xfe, which share the same arm -- is a
# **line**: the interpreter drives the animation, loads `TALK.T[base + byte]`
# when the entity's kind is 0x2b, draws a frame, and then **waits for the use
# button**. Everything else dispatches through a 16-arm table at 0x80013160:
#
#   0xf0 n    jump back n, and set the retry flag
#   0xf3      spend one of the no-wait count
#   0xf4 a n  call the level's own code with a, and set the no-wait count to n
#   0xf5 n    set the no-wait count
#   0xf6      script_speaker = record[+1], and clear the retry flag
#   0xf7 i v  story_flags[i] = v
#   0xf8 n    jump back n
#   0xf9 i v t   if story_flags[i] == v, go to t
#   0xff      end
#
# **What this reproduces is the control flow and the flags** -- the part that
# is the same every time. The waiting is not reproduced: every line is taken at
# once, and the no-wait count is tracked so the two copies can still be
# compared on it. The text and the animation are not here either; a line yields
# its byte and the caller decides what to do with it.
#
# Checked against tools/escript.py on every script in the game.
# @orig game:0x8005c308 script_interpreter  status:partial -- the control flow and the flags

const FLAG_COUNT := 0x80
const END := 0xFF

# The bytes that are lines rather than opcodes, above 0xf0.
const LINE_OPS := [0xF1, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE]
# opcode -> how far the pointer moves when nothing else decides.
const SIZE := {0xF0: 2, 0xF2: 2, 0xF3: 1, 0xF4: 3, 0xF5: 2, 0xF6: 1,
	0xF7: 3, 0xF8: 2, 0xF9: 4, 0xFF: 1}


static func is_line(op: int) -> bool:
	return op < 0xF0 or op in LINE_OPS


# @orig game:0x8005c308 script_interpreter  status:partial
static func run(code: PackedByteArray, flags: Array = [],
		limit := 2000) -> Dictionary:
	var f: Array = flags.duplicate() if flags.size() == FLAG_COUNT \
		else _zeros()
	var pc := 0
	var no_wait := 0
	var trace: Array = []
	for _step in range(limit):
		if pc < 0 or pc >= code.size():
			return {"trace": trace, "flags": f, "why": "off"}
		var op := int(code[pc])
		trace.append([pc, op])
		if is_line(op):
			pc += 1
			no_wait = maxi(no_wait - 1, 0)
			continue
		if op == END:
			return {"trace": trace, "flags": f, "why": "end"}
		match op:
			0xF0, 0xF8:
				pc -= int(code[pc + 1]) if pc + 1 < code.size() else 0
			0xF7:
				var i := int(code[pc + 1])
				if i < f.size():
					f[i] = int(code[pc + 2])
				pc += 3
				no_wait = maxi(no_wait - 1, 0)
			0xF9:
				var fi := int(code[pc + 1])
				if fi < f.size() and int(f[fi]) == int(code[pc + 2]):
					pc = int(code[pc + 3])      # 0x8005c18c resolves the label
				else:
					pc += 4
			0xF5:
				no_wait = int(code[pc + 1])
				pc += 2
			0xF4:
				no_wait = int(code[pc + 2]) if pc + 2 < code.size() else 0
				pc += 3
			0xF3:
				pc += 1
				if no_wait > 0:
					no_wait -= 1
			0xF6:
				pc += 1
			_:
				pc += int(SIZE.get(op, 1))
	return {"trace": trace, "flags": f, "why": "limit"}


static func _zeros() -> Array:
	var f: Array = []
	f.resize(FLAG_COUNT)
	f.fill(0)
	return f

class_name KFLevelState
extends RefCounted
# What each level remembers between visits, in the game's own form.
#
# level_state (0x801baa88) is 0x5000 bytes of records and level_state_index
# (0x801bfa88) 32 halfwords, each a level's offset into it -- 0xffff for a
# level not yet left. level_state_write (0x8005efd4) builds a level's byte
# stream when the player leaves it, and apply_level_state (0x8005f444) reads
# it back when the level loads, in three sections:
#
#   (slot, value) pairs to 0xff     a category-1 actor's +9: 3 gone, 0 not
#   (entity, pc, retry) to 0xff     where each conversation has got
#   one opcode per object slot, 396 in lockstep, chosen by the object's class
#   (object_type_table[type] byte 0) through the table at 0x80013298:
#     0xff          the slot empty: its type 0xff
#     0xfe          nothing kept (200 classes, and any past the table)
#     0xfd s        +0x38 -- the lock of a door, a gate, a lift, a chest
#     0xf5 n        +0x39 (class 0x56)
#     0xf4 s n      both -- a pedestal's lock (the key's number) and its key's
#                   place in the ring
#     (nothing)     class 0x53 below state 2: the reader takes the next
#                   slot's byte for this one, and is a slot out from there on
#     0xf0 t xx zz yy a   a thing made since the level was built -- gold (kind
#     0xf1 t xx zz yy     0x60), 0x61, 0x62 -- with its type and place, x and
#     0xf2 t xx zz yy r   z >> 2, the angle >> 4 and +0x3a >> 2
#     0xf3 t s      a key on a pedestal (kind 0x70): the type and +0x38
#
# The port keeps the same: `streams`, one per level the player has left or a
# save carried; and for the level in hand a table of what the writer reads of
# each slot -- type, class, kind (+4), place, +0x26, +0x38, +0x39, +0x3a --
# made from the placement (lootNN.json's find rows), the stream applied over
# it, and the port's objects written into it as the level is left. A table
# left is written into its stream when the level is next asked for, by which
# time everything in the old scene has left: actors.gd, loot.gd and doors.gd
# each leave in their own order.
#
# tools/levelstate.py is the same, held to the game's own writer and reader
# (84 of 84 streams, 90 of 90 applied); the self-test holds this to it
# (levelstatecheck.json).
#
# @exe game

const SLOTS := 396                 # OBJECT_COUNT, both routines' bound
const ACTORS := 200
const END := 0xFF
const NONE := 0xFFFF
const LEVELS := 32
const CLASSES := 233               # the writer's table at 0x80013298
# How long each opcode is; any other byte is one (tools/levelstate.py OPS).
const OPS := {0xF0: 9, 0xF1: 8, 0xF2: 9, 0xF3: 3, 0xF4: 3, 0xF5: 2, 0xFD: 2}
# The kind byte (+4) each creating opcode stamps (0x8005f580..0x8005f754).
const KINDS := {0xF0: 0x60, 0xF1: 0x61, 0xF2: 0x62, 0xF3: 0x70}
const CREATES := {0x60: 0xF0, 0x61: 0xF1, 0x62: 0xF2, 0x70: 0xF3}

static var arms := []              # the writer's arm for each class, levelstate.json
static var streams := {}           # level -> its stream
static var tables := {}            # level -> the table of the level in hand, or of one left
static var left := {}              # level -> true: its table is final, to be written
static var actor_parts := {}       # level -> [[slot, +9]] of its category-1 actors, as left
# Goes up when a save is put back or the levels are cleared; what a scene
# made before that is not written into anything.
static var epoch := 0


# @port data -- levelstate.json's arms: the writer's table at 0x80013298, by class, as tools/levelstate.py reads it off the executable
static func load_arms() -> void:
	if not arms.is_empty() or not FileAccess.file_exists("res://levelstate.json"):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://levelstate.json"))
	if typeof(d) == TYPE_DICTIONARY:
		arms = d.get("arms", [])


# A save's two blocks: save_restore copies the area and the index whole; each
# level's stream is the bytes its offset points at, as far as the reader goes.
# @port engine -- the save's area and index made into the streams this keeps, and what came before dropped
static func put(area: PackedByteArray, idx: PackedByteArray) -> void:
	clear()
	for lv in LEVELS:
		var off := idx.decode_u16(2 * lv) if idx.size() >= 2 * lv + 2 else NONE
		if off != NONE and off < area.size():
			var b := area.slice(off)
			streams[lv] = b.slice(0, int(decode(b)["used"]))


# reset_story_flags (0x8005ea64), at a new character: the flags and the whole
# of level_state and its index cleared -- every level forgets.
# @orig game:0x8005ea64 reset_story_flags  status:partial -- the levels' records forgotten; the flags are KFTalk's, the things in the pack items.gd's
static func clear() -> void:
	streams.clear()
	tables.clear()
	left.clear()
	actor_parts.clear()
	epoch += 1


# level_state_unpack (0x8005ee58) turns each of the 32 offsets into a pointer,
# or null for 0xffff, and apply_level_state takes the level's. A level whose
# table was left is written first.
# @orig game:0x8005ee58 level_state_unpack  status:partial -- one level's stream, or none; the area's packing is not kept, the streams are
static func stream(lv: int) -> PackedByteArray:
	if left.has(lv):
		write(lv)
	return streams.get(lv, PackedByteArray())


# What apply_level_state does with a stream, as data: {"actors": [[slot, +9]],
# "talks": [[entity, pc, retry]], "slots": one [opcode, operands...] for each
# of the 396 slots, "used": the bytes read}, or {} for no stream. A stream
# that ends early reads on into zeros.
# @orig game:0x8005f444 apply_level_state  status:verified -- the reading; tools/levelstate.py's, which 90 of 90 runs of the game's own hold, is this on every stream the self-test has (levelstatecheck.json); what each slot's object does with it is actors.gd's, loot.gd's and doors.gd's
static func decode(b: PackedByteArray) -> Dictionary:
	if b.is_empty():
		return {}
	var i := 0
	var actors := []
	while _at(b, i) != END:
		actors.append([_at(b, i), _at(b, i + 1)])
		i += 2
	i += 1
	var talks := []
	while _at(b, i) != END:
		talks.append([_at(b, i), _at(b, i + 1), _at(b, i + 2)])
		i += 3
	i += 1
	var slots := []
	for _s in SLOTS:
		var op := _at(b, i)
		var n: int = OPS.get(op, 1)
		var row := [op]
		for k in range(1, n):
			row.append(_at(b, i + k))
		slots.append(row)
		i += n
	return {"actors": actors, "talks": talks, "slots": slots, "used": i}


# A level's stream, read: decode(stream(lv)).
# @port helper -- the two together
static func decoded(lv: int) -> Dictionary:
	return decode(stream(lv))


# A created thing's fields, as the reader builds them (0x8005f580 for 0xf0,
# 0x8005f654 for 0xf1, 0x8005f6bc for 0xf2): x and z shifted back up by 2, y
# sign-extended; 0xf0's angle << 4 at +0x26 and 0x400 at +0x28, 0xf2's +0x3a
# (r << 2) plus rand() >> 13, and 0x400 at +0x24 for type 0x79. The record is
# init_object_record's first (0x800448b8): +0x24..+0x28 zero, +1 0x80; then
# +8 0x63 -- at rest -- and +0x38 0xff, free to take; 0xf3's +0x38 its own.
# @orig game:0x8005f580 apply_level_state+0x13c  status:verified -- the three arms that make a thing, as tools/levelstate.py apply makes them (90 of 90 against the game's); the layer (+0) is the caller's, which has the collision
static func made(row: Array, rand: Callable) -> Dictionary:
	var op := int(row[0])
	var t := {"kind": KINDS[op], "type": int(row[1]), "angles": [0, 0, 0],
		"state": 0x63, "lock": 0xFF, "rest": 0}
	if op == 0xF3:
		t["lock"] = int(row[2])
		return t
	var y := int(row[6]) | (int(row[7]) << 8)
	if y & 0x8000:
		y -= 0x10000
	t["pos"] = Vector3i((int(row[2]) | (int(row[3]) << 8)) << 2, y,
		(int(row[4]) | (int(row[5]) << 8)) << 2)
	if op == 0xF0:
		t["angles"] = [0, int(row[8]) << 4, 0x400]
	elif op == 0xF2:
		t["rest"] = (int(row[8]) << 2) + (int(rand.call()) >> 13)
		if int(row[1]) == 0x79:
			t["angles"] = [0x400, 0, 0]
	return t


# The table a fresh load of the level leaves, out of its placement: for each
# slot a row of what the writer reads -- type, class, kind (+4), x, y, z,
# +0x26, +0x38, +0x39 and +0x3a -- or null where nothing is placed. `finds`
# is lootNN.json's find rows by slot (tools/level3d.py find_rows), which
# tools/objload.py takes off the disc as load_object_placement does (4836 of
# 4838 records of the game's own).
# @port data -- the find rows, as the writer's table
static func fresh_table(finds: Dictionary) -> Array:
	var t := []
	t.resize(SLOTS)
	for s in finds:
		var f: Array = finds[s]
		if int(s) < SLOTS and f.size() >= 14:
			t[int(s)] = [int(f[2]), int(f[1]), int(f[10]), int(f[3]), int(f[4]), int(f[5]),
				int(f[6]) & 0xFFFF, int(f[11]), int(f[12]), int(f[13])]
	return t


# The object section of a stream over a table, as the reader writes the
# record: 0xff empties the slot, 0xfd, 0xf5 and 0xf4 put +0x38 and +0x39 back,
# 0xf0..0xf3 make a thing there -- its class looked up in `classes`, the
# level's type rows' byte 0 -- with the place, the angle and +0x3a made()
# gives it, each also left in d["made"] by slot. init_object_record leaves
# +0x39 and +0x3a alone, so a key (0xf3) keeps what the slot had; a slot the
# stream makes from nothing has 0 there.
# @orig game:0x8005f520 apply_level_state+0xdc  status:verified -- the object section over the writer's fields; 46 of 46 streams leave the table as tools/levelstate.py apply leaves the game's RAM (levelstatecheck.json)
static func apply_table(table: Array, d: Dictionary, classes: Array, rand: Callable) -> void:
	if d.is_empty():
		return
	var made_here := {}
	d["made"] = made_here               # each thing made, by slot, for the objects to take up
	var ops: Array = d["slots"]
	for s in mini(ops.size(), SLOTS):
		var row: Array = ops[s]
		var op := int(row[0])
		var e = table[s]
		if op == 0xFF:
			if e != null:
				e[0] = 0xFF
				table[s] = null
		elif op == 0xFD:
			if e != null:
				e[7] = int(row[1])
		elif op == 0xF5:
			if e != null:
				e[8] = int(row[1])
		elif op == 0xF4:
			if e != null:
				e[7] = int(row[1])
				e[8] = int(row[2])
		elif KINDS.has(op):
			var m := made(row, rand)
			made_here[s] = m
			var typ := int(m["type"])
			var old: Array = e if e != null else [0xFF, 0, 0, 0, 0, 0, 0, 0, 0, 0]
			var cls: int = int(classes[typ]) if typ < classes.size() else 0
			var p: Vector3i = m.get("pos", Vector3i(old[3], old[4], old[5]))
			var a26: int = int(m["angles"][1]) if op != 0xF3 else 0
			var w3a: int = int(m["rest"]) if op == 0xF2 else int(old[9])
			table[s] = [typ, cls, int(m["kind"]), p.x, p.y, p.z, a26, int(m["lock"]),
				int(old[8]), w3a]


# level_state_write's stream for a level: its category-1 actors' slots, 3 for
# one gone and 0 for one not; its conversations' places; and for each of the
# 396 slots what its class's arm writes. `pairs` is [[slot, +9]] in slot
# order, `talks` [[entity, pc, retry]], `table` fresh_table's form.
# @orig game:0x8005efd4 level_state_write  status:verified -- the stream, as tools/levelstate.py encode builds it (84 of 84 against the game's own writer) from the same state, over every snapshot and scrambled copies (levelstatecheck.json); not the area's packing (0x8001939c), which the port does not keep
static func encode(pairs: Array, talks: Array, table: Array) -> PackedByteArray:
	load_arms()
	var out := PackedByteArray()
	for p in pairs:
		out.append(int(p[0]))
		out.append(3 if int(p[1]) == 3 else 0)
	out.append(END)
	for t in talks:
		out.append(int(t[0]))
		out.append(int(t[1]) & 0xFF)
		out.append(int(t[2]) & 0xFF)
	out.append(END)
	for s in SLOTS:
		var e = table[s] if s < table.size() else null
		if e == null or int(e[0]) == 0xFF:
			out.append(0xFF)
			continue
		var cls := int(e[1])
		var arm: String = str(arms[cls]) if cls < CLASSES and cls < arms.size() else "nothing"
		var st := int(e[7]) & 0xFF
		match arm:
			"state":
				out.append_array([0xFD, st])
			"unless_low":
				if st >= 2:
					out.append_array([0xFD, st])
			"pair":
				out.append_array([0xF4, st, int(e[8]) & 0xFF])
			"aux":
				out.append_array([0xF5, int(e[8]) & 0xFF])
			"thing":
				var kind := int(e[2])
				if not CREATES.has(kind):
					out.append_array([0xFD, st])
				elif kind == 0x70:
					out.append_array([0xF3, int(e[0]) & 0xFF, st])
				else:
					var x := int(e[3])
					var y := int(e[4])
					var z := int(e[5])
					out.append_array([CREATES[kind], int(e[0]) & 0xFF, (x >> 2) & 0xFF,
						(x >> 10) & 0xFF, (z >> 2) & 0xFF, (z >> 10) & 0xFF, y & 0xFF,
						(y >> 8) & 0xFF])
					if kind == 0x60:
						out.append((int(e[6]) >> 4) & 0xFF)
					elif kind == 0x62:
						out.append((int(e[9]) >> 2) & 0xFF)
			_:
				out.append(0xFE)
	return out


# The conversations a level's stream lists: every entity whose block 0 begins
# 0x70 -- escript.json's for the level -- with where KFTalk has it.
# @port helper -- level_state_write's second section, out of KFTalk
static func talks_of(lv: int) -> Array:
	KFTalk.load_level(lv)
	var ents: Array = (KFTalk.scripts.get(lv, {}) as Dictionary).keys()
	ents.sort()
	var out := []
	for k in ents:
		var st: Dictionary = KFTalk.states.get("%d/%d" % [lv, int(k)], {"pc": 0, "retry": 0})
		out.append([int(k), int(st["pc"]), int(st["retry"])])
	return out


# A table left, written: its stream made as level_state_write makes it, and
# the table and the actors' part done with.
# @port helper -- encode over what the scene left
static func write(lv: int) -> void:
	streams[lv] = encode(actor_parts.get(lv, []), talks_of(lv), tables.get(lv, []))
	left.erase(lv)
	tables.erase(lv)
	actor_parts.erase(lv)


# @port helper -- a byte of the stream, 0 past its end
static func _at(b: PackedByteArray, i: int) -> int:
	return int(b[i]) if i < b.size() else 0

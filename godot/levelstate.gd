class_name KFLevelState
extends RefCounted
# What each level remembers between visits. level_state (0x801baa88) is 0x5000
# bytes of records and level_state_index (0x801bfa88) 32 halfwords, each a
# level's offset into it -- 0xffff for a level not yet left. A save carries
# both whole (KFCard), and when a level loads apply_level_state (0x8005f444)
# reads its byte stream in three sections:
#
#   (slot, value) pairs to 0xff     a category-1 actor's +9: 3 gone, 0 not
#   (entity, pc, retry) to 0xff     where each conversation has got
#   one opcode per object slot, 396 in lockstep:
#     0xff          the slot empty: its type 0xff
#     0xfd s        +0x38 -- the lock of a door, a gate, a lift, a chest
#     0xf5 n        +0x39
#     0xf4 s n      both -- a pedestal's lock (the key's number) and its key's
#                   place in the ring
#     0xf0 t xx zz yy a   a thing made since the level was built -- gold (kind
#     0xf1 t xx zz yy     0x60), 0x61, 0x62 -- with its type and place, x and
#     0xf2 t xx zz yy r   z >> 2, the angle >> 4 and +0x3a >> 2
#     0xf3 t s      a key on a pedestal (kind 0x70): the type and +0x38
#     anything else nothing, one byte
#
# tools/levelstate.py is the same, held to the game's own writer and reader:
# 84 of 84 streams level_state_write builds over snapshots and scrambled
# copies of them, 90 of 90 applied by apply_level_state as the model applies
# them. The self-test holds this reading to that one (levelstate.json).
#
# The port keeps its own record of a level it has left (actors.gd, loot.gd and
# doors.gd, each `saved`); a stream from a save stands for a level until the
# port has been there itself. `epoch` goes up with every save loaded, and each
# of them drops what it kept before when it sees it change.
#
# @exe game

const SLOTS := 396                 # apply_level_state's bound, OBJECT_COUNT
const END := 0xFF
const NONE := 0xFFFF
const LEVELS := 32
const AREA := 0x5000
# How long each opcode is; any other byte is one (tools/levelstate.py OPS).
const OPS := {0xF0: 9, 0xF1: 8, 0xF2: 9, 0xF3: 3, 0xF4: 3, 0xF5: 2, 0xFD: 2}
# The kind byte (+4) each creating opcode stamps (0x8005f580..0x8005f754).
const KINDS := {0xF0: 0x60, 0xF1: 0x61, 0xF2: 0x62, 0xF3: 0x70}

static var area := PackedByteArray()
static var index := PackedInt32Array()
static var epoch := 0


# A save's two blocks, put back: save_restore copies the area and the index
# whole (tools/memcard.py, +0x108 and +0x5108 of the buffer).
# @port engine -- the two blocks kept for the levels still to be loaded, and the epoch that tells the keepers
static func put(a: PackedByteArray, idx: PackedByteArray) -> void:
	area = a.duplicate()
	index = PackedInt32Array()
	for lv in LEVELS:
		index.append(idx.decode_u16(2 * lv) if idx.size() >= 2 * lv + 2 else NONE)
	epoch += 1


# level_state_unpack (0x8005ee58) turns each of the 32 offsets into a pointer
# into the area, or null for 0xffff; apply_level_state takes the level's.
# @orig game:0x8005ee58 level_state_unpack  status:transcribed -- one level's offset into the area, 0xffff for none; the bytes from there on, as the reader walks them
static func stream(lv: int) -> PackedByteArray:
	if lv < 0 or lv >= index.size() or int(index[lv]) == NONE:
		return PackedByteArray()
	return area.slice(int(index[lv]))


# What apply_level_state does with a stream, as data: {"actors": [[slot, +9]],
# "talks": [[entity, pc, retry]], "slots": one [opcode, operands...] for each
# of the 396 slots}, or {} for an empty stream. A stream that ends early --
# the writer puts nothing for a class-0x53 object below state 2 -- reads on
# into whatever follows, here as in the game; past the area's end it reads 0.
# @orig game:0x8005f444 apply_level_state  status:verified -- the reading; tools/levelstate.py's, which 90 of 90 runs of the game's own hold, is this on every stream the self-test has (levelstate.json); what each slot's object does with it is actors.gd's, loot.gd's and doors.gd's
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
# +8 0x63 -- at rest -- and +0x38 0xff, free to take.
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


# @port helper -- a byte of the stream, 0 past its end
static func _at(b: PackedByteArray, i: int) -> int:
	return int(b[i]) if i < b.size() else 0

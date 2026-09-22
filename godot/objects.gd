class_name KFObjects
extends Node
# What an object does, once a frame.
#
# `object_interpreter` (0x80047010) is the third call in every frame and the
# largest routine in the game. It walks all 396 slots of `object_table` and,
# for each one that is in use:
#
#     if record[+4] == 0xff:  skip
#     current_object      = record                    0x80198394
#     current_object_type = type_row(record[+6])      0x80198390
#     if record[+4] < 236:  switch on it              0x8001209c, 236 arms
#
# So **byte +4 is the object's behaviour opcode**, and it is a copy of byte +0
# of its type's row -- the same class `render_walk` draws on. Doors, chests,
# levers, signs and the things that hurt you are one machine.
#
# 236 opcodes through 44 arms, 191 of them sharing the tail. What each arm
# touches is in OBJECTS.md, read off the code by tools/objops.py, and the
# groups below are that reading:
#
#   0x00-0x05, 0x1b     write player_pos and player_speed -- doors that shove
#   0x06-0x08, 0x17,    write the position *and* the facing, and call
#   0x57, 0xe7, 0xe8    place_player_on_terrain -- teleports
#   0xeb                calls level_load -- the stairs between levels
#   0x51, 0x52, 0x55    call object_set_present -- things that come and go
#   0x60-0x62           call collide_surface -- things that follow the floor
#   0xe0                calls object_trigger
#   0x09, 0x12, 0x16,   a handful of instructions each
#   0x31, 0x56
#
# **Only the machine is here, not the handlers.** Every one of them needs a
# recording to check against and there is none: nothing in this repository has
# ever logged a call into the interpreter. So this walks the slots, finds the
# opcode and reports what it would dispatch to, and each group says plainly
# that nothing runs. `tools/objops.py 0x1f` prints the arm to write next.
#
# The class bytes are **borrowed**: object_type_table is built at load time out
# of at least two sources and only 32 of its 819 rows were found on the disc,
# so tools/objops.py takes them from a RAM snapshot of level 0 and writes
# objclass.json. The same arrangement the object scales and textures already
# have, for the same reason.
# @orig game:0x80047010 object_interpreter  status:partial -- the walk and the dispatch, none of the arms

const SLOTS := 396                   # OBJECT_COUNT, 0x18c
const OPCODES := 236                 # OBJECT_OPCODES, 0xec -- the sltiu bound
const SKIP := 0xFF                   # record[+4] == 0xff: the slot is not in use

# The groups OBJECTS.md names, by the opcodes that reach each arm.
const GROUPS := {
	"push_player": [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x1b],
	"teleport": [0x06, 0x07, 0x08, 0x17, 0x57, 0xe7, 0xe8],
	"change_level": [0xeb],
	"appear": [0x51, 0x52, 0x55],
	"follow_floor": [0x60, 0x61, 0x62],
	"trigger": [0xe0],
}

var klass := {}                      # type id -> its class byte


func load_classes(path := "res://objclass.json") -> bool:
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	klass.clear()
	for k in d.get("class", {}).keys():
		klass[int(k)] = int(d["class"][k])
	return not klass.is_empty()


func group_of(op: int) -> String:
	for name in GROUPS:
		if op in GROUPS[name]:
			return name
	return "shared tail" if op < OPCODES else "out of range"


# The trigger test every door, teleport and switch uses: is the player's own
# cell inside this rectangle? Read off player_in_rect (0x80046884), which
# takes the cells as `player_pos >> 11` and `0x801b25f8 >> 11` -- so the
# rectangle is in cells, not in world units.
# @orig game:0x80046884 player_in_rect  status:transcribed
static func player_in_rect(px: int, pz: int, cx: int, cz: int,
		w: int, h: int) -> bool:
	var pcx := px >> 11
	var pcz := pz >> 11
	return pcx >= cx and pcx < cx + w and pcz >= cz and pcz < cz + h


# One frame of the interpreter over whatever the port has placed. It finds each
# object's opcode and its group and returns the tally; it runs no handler,
# because no handler has been checked against the game.
# @orig game:0x80047010 object_interpreter  status:partial
func tick(objects: Array) -> Dictionary:
	var seen := {}
	var n := 0
	for o in objects:
		if n >= SLOTS:
			break
		n += 1
		var op: int = klass.get(int(o.get("type", -1)), SKIP)
		if op == SKIP or op >= OPCODES:
			continue
		var g := group_of(op)
		seen[g] = int(seen.get(g, 0)) + 1
	return seen


func summary(objects: Array) -> String:
	if klass.is_empty() and not load_classes():
		return "objects: no class table (objclass.json is not there)"
	var t := tick(objects)
	var parts: Array[String] = []
	for k in t:
		parts.append("%s %d" % [k, t[k]])
	parts.sort()
	return "objects: " + (", ".join(parts) if parts else "none with an opcode")

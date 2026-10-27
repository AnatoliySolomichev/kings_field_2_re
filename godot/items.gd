class_name KFItems
# The inventory, which is two arrays and three routines.
#
# `inventory_a` (0x800c85e8) and `inventory_b` (0x800c867e) are each **150
# bytes, one count per item id**, and every routine that touches them tries the
# first and falls back to the second. Why there are two is not established;
# what is established is that all three primitives treat them as a pair.
#
#   has_item(id)    0x8005d7bc   a[id] != 0 or b[id] != 0
#   take_item(id)   0x8005d7f8   decrement a[id] if it is not zero, else b[id]
#   give_item(id)   0x8005d898   increment a[id] while it is below 99, else
#                                b[id] while it is below 99, else announce(0xb)
#
# 99 is 0x63 and it is the cap in both arrays, so a stack is 99 and a full pack
# says so rather than losing the item quietly.
#
# Item `n`'s description is `ITEM.T[390 + n]`, a picture, and its **name is
# plain text in the executable**: a 24-byte row at 0x8007f620 where `a` is 0,
# `z` is 25, 0x7f is a space and 0xff ends it. All 150 decode without a single
# unknown code, so nothing here needs the OCR that read item 0 as "Excel
# Iecor" -- it is `excellector`. tools/itemtext.py writes them out.
#
# @exe game

const COUNT := 150                   # ids 0..149
const CAP := 0x63                    # 99, the per-slot cap in both arrays
const FULL_MESSAGE := 0xB            # what give_item announces when both are full

var a: PackedByteArray = _empty()
var b: PackedByteArray = _empty()
# The banner give_item raises when there is nowhere to put the item. The caller
# decides what to do with it; the game calls announce(0xb).
var last_message := -1
# The level whose own code give_item and take_item call after (level_hooks,
# which level_load points at the level's overlay): loot.gd sets it as the
# scene comes in. -1, none -- the self-test's packs.
static var level := -1


# reset_story_flags' tail (0x8005eacc), at a new game and at a death with no
# crystal: both arrays cleared and a new character's things put in -- the
# excellector (0), the leather plate (42), two earth herbs (104) and an antidote
# (105). Every snapshot of a new character carries those, and what it wears
# and wields is among them: an equipped thing still counts.
# @orig game:0x8005eacc reset_story_flags+0x68  status:verified -- the four counts every snapshot of a new character holds
func start() -> void:
	a = _empty()
	b = _empty()
	a[0] = 1
	a[42] = 1
	a[104] = 2
	a[105] = 1


# @port helper -- 150 zero counts
static func _empty() -> PackedByteArray:
	var p := PackedByteArray()
	p.resize(COUNT)
	p.fill(0)
	return p


# @orig game:0x8005d7bc has_item  status:transcribed
func has_item(id: int) -> bool:
	if id < 0 or id >= COUNT:
		return false
	return a[id] != 0 or b[id] != 0


# take_item: true where the game answers 0. The level's entry 11, which it
# calls after (level_hooks + 0x2c), is `jr $ra` on all 28 levels.
# @orig game:0x8005d7f8 take_item  status:verified -- tools/givetake.py, 1680 of 1680 runs of the game's own give_item and take_item with every level's entries 6 and 11 out of its overlay (the answer, the calls, all of RAM but the stack), the self-test this to it
func take_item(id: int) -> bool:
	if id < 0 or id >= COUNT:
		return false
	if a[id] != 0:
		a[id] = a[id] - 1
		return true
	if b[id] != 0:
		b[id] = b[id] - 1
		return true
	return false


# give_item: true where the game answers 0, and the level's entry 6 run
# (_entry6); both arrays at 99, false and the banner, and no hook.
# @orig game:0x8005d898 give_item  status:verified -- tools/givetake.py, 1680 of 1680 runs of the game's own give_item and take_item with every level's entries 6 and 11 out of its overlay (the answer, the calls, all of RAM but the stack), the self-test this to it
func give_item(id: int) -> bool:
	if id < 0 or id >= COUNT:
		return false
	if a[id] < CAP:
		a[id] = a[id] + 1
		_entry6()
		return true
	if b[id] < CAP:
		b[id] = b[id] + 1
		_entry6()
		return true
	last_message = FULL_MESSAGE
	return false


# give_item's call of the level's entry 6 (KFLevelIn.entry6) over the pack as
# the game's bytes, and the story flags it set put back.
# @port engine -- the pack as the game's bytes for the level's entry 6, its flags back into KFTalk's
func _entry6() -> void:
	if level < 0:
		return
	KFTalk.load_level(level)               # the story flags, sized
	var m := {"mem": {}, "calls": []}
	for i in COUNT:
		KFLevelIn.wr(m, KFLevelIn.INV_A + i, a[i])
		KFLevelIn.wr(m, KFLevelIn.INV_B + i, b[i])
	KFLevelIn.entry6(level, m)
	var mem: Dictionary = m["mem"]
	for k in KFTalk.FLAG_COUNT:
		if mem.has(KFLevelIn.F(k)):
			KFTalk.flags[k] = int(mem[KFLevelIn.F(k)])


# @port helper -- both arrays' count of one id, for the readouts
func count(id: int) -> int:
	if id < 0 or id >= COUNT:
		return 0
	return int(a[id]) + int(b[id])


var item_names := {}


# @port data -- reads itemnames.json: tools/itemtext.py decodes the 24-byte rows at 0x8007f620
func load_names(path := "res://itemnames.json") -> bool:
	if not FileAccess.file_exists(path):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	item_names.clear()
	for k in d.get("names", {}).keys():
		item_names[int(k)] = str(d["names"][k])
	return not item_names.is_empty()


# @port data -- one name out of that table
func name_of(id: int) -> String:
	if item_names.is_empty():
		load_names()
	return item_names.get(id, "item %d" % id)


# @port check -- the readout's line
func summary() -> String:
	var held := 0
	for i in range(COUNT):
		if a[i] != 0 or b[i] != 0:
			held += 1
	return "inventory: %d distinct items" % held

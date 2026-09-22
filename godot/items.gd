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
# Item `n` is `ITEM.T[390 + n]` and ids stop at 149 -- tools/itemtext.py.

const COUNT := 150                   # ids 0..149
const CAP := 0x63                    # 99, the per-slot cap in both arrays
const FULL_MESSAGE := 0xB            # what give_item announces when both are full

var a: PackedByteArray = _empty()
var b: PackedByteArray = _empty()
# The banner give_item raises when there is nowhere to put the item. The caller
# decides what to do with it; the game calls announce(0xb).
var last_message := -1


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


# @orig game:0x8005d7f8 take_item  status:transcribed
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


# @orig game:0x8005d898 give_item  status:transcribed
func give_item(id: int) -> bool:
	if id < 0 or id >= COUNT:
		return false
	if a[id] < CAP:
		a[id] = a[id] + 1
		return true
	if b[id] < CAP:
		b[id] = b[id] + 1
		return true
	last_message = FULL_MESSAGE
	return false


func count(id: int) -> int:
	if id < 0 or id >= COUNT:
		return 0
	return int(a[id]) + int(b[id])


func summary() -> String:
	var held := 0
	for i in range(COUNT):
		if a[i] != 0 or b[i] != 0:
			held += 1
	return "inventory: %d distinct items" % held

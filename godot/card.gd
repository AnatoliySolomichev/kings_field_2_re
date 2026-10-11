class_name KFCard
extends RefCounted
# The memory card, and the saves King's Field II keeps on it.
#
# save_load_slot (0x8002860c) -- what the list of saves calls with the slot
# picked -- opens bu00:BASLUS-00255 and the slot's digit, reads 0x6000 bytes,
# three of the card's 8 KB blocks, and believes them only if save_checksum
# (0x80028c74), the sum of the 0x5c00 bytes from +0x400, is the word at
# +0x200. Then save_restore (0x8005ffd0) puts back, from +0x400, 57 fields one
# at a time and ten blocks whole. tools/memcard.py is the same in Python, held
# to the game's own save_restore (534 566 of 534 566 bytes) and save_serialise
# (494 592 of 494 592); FORMATS.md §15, "On the card", has the file.
#
# The card is the console's: sixteen 8 KB blocks, the first a directory of
# 128-byte frames, each naming a file's first block (state 0x51, then 0x52
# and 0x53 down the chain, the next block at +8, the name at +0xa). The BIOS
# reads it for the game; this reads the emulator's card files, which
# tools/level3d.py names in cards.json.
#
# @exe game

const CARD_SIZE := 0x20000
const BLOCK := 0x2000
const FRAME := 0x80
const FIRST := 0x51
const NAME := "BASLUS-00255"       # 0x80081818, then the slot's digit
const FILE_SIZE := 0x6000          # what save_load_slot reads
const SUM_AT := 0x200
const DATA_AT := 0x400             # what save_restore is handed
const SUMMED := 0x5C00             # save_checksum's count

# save_restore, a field at a time: [buffer offset, bytes, address, name] --
# tools/memcard.py FIELDS, run of halves and bytes into consecutive addresses
# one entry.
const FIELDS := [
	[0x0000, 5, 0x8018FAD8, "block"],
	[0x5694, 4, 0x801B25F0, "x"],
	[0x5698, 4, 0x801B25F4, "y"],
	[0x569C, 4, 0x801B25F8, "z"],
	[0x56A0, 4, 0x801B25FC, "pos_w"],
	[0x56A4, 4, 0x801B2610, "pitch_facing"],
	[0x56A8, 4, 0x801B2614, "b2614"],
	[0x56AC, 4, 0x801B2588, "minutes"],
	[0x56B0, 4, 0x801B24E4, "exp"],
	[0x56B4, 4, 0x801B24E8, "exp_next"],
	[0x56B8, 4, 0x801B2534, "gold"],
	[0x56BC, 4, 0x801B24EC, "b24ec"],
	[0x56C0, 2, 0x801B2644, "b2644"],
	[0x56C2, 2, 0x801B24FA, "hp_max"],
	[0x56C4, 2, 0x801B24FC, "hp"],
	[0x56C6, 2, 0x801B24FE, "mp_max"],
	[0x56C8, 2, 0x801B2500, "mp"],
	[0x56CA, 2, 0x801B2516, "stat36"],
	[0x56CC, 10, 0x801B2518, "skills"],
	[0x56D6, 2, 0x801B2522, "b2522"],
	[0x56D8, 2, 0x801B2530, "wis"],
	[0x56DA, 2, 0x801B2508, "strong"],
	[0x56DC, 10, 0x801B250A, "b250a"],
	[0x56E6, 2, 0x801B2514, "b2514"],
	[0x56E8, 2, 0x801B255C, "poison"],
	[0x56EA, 28, 0x801B255E, "timers"],
	[0x5706, 1, 0x801B24F0, "level"],
	[0x5707, 1, 0x801B24F1, "b24f1"],
	[0x5708, 7, 0x801B25D4, "worn"],
	[0x570F, 3, 0x801B25AB, "in_hand"],
	[0x5712, 1, 0x801B25AF, "weapon"],
	[0x5713, 10, 0x801B25DB, "panel"],
]
# ...and the blocks it copies whole: [offset, bytes, address, stride, name].
const BLOCKS := [
	[0x0008, 0x100, 0x801BA988, 1, "flags"],
	[0x0108, 0x5000, 0x801BAA88, 1, "area"],
	[0x5108, 0x40, 0x801BFA88, 1, "index"],
	[0x5148, 0x3C0, 0x80198588, 1, "seq_state"],
	[0x5508, 0x12C, 0x800C85E8, 1, "inventory"],
	[0x5634, 0x60, 0x801B77EC, 24, "spells"],
	[0x571E, 0x280, 0x801B56CC, 1, "map_seen"],
	[0x599E, 0x96, 0x80081780, 1, "items_80081780"],
	[0x5A34, 0x96, 0x80080718, 1, "items_80080718"],
	[0x5ACA, 4, 0x8009C22C, 1, "c22c"],
]

# A save read and not yet taken: what save_restore put back, for the player
# to take up in its _ready (player.gd).
static var loaded = null


# @port data -- cards.json: the emulator's card files, as tools/level3d.py found them
static func card_paths() -> Array:
	var p := "res://cards.json"
	if not FileAccess.file_exists(p):
		return []
	var d = JSON.parse_string(FileAccess.get_file_as_string(p))
	return d.get("cards", []) if typeof(d) == TYPE_DICTIONARY else []


# The card's files: {name: bytes}, each followed down its chain of blocks.
# @port engine -- the BIOS's file system (firstfile, nextfile, read), over the emulator's card file
static func files(card: PackedByteArray) -> Dictionary:
	var out := {}
	if card.size() != CARD_SIZE or card[0] != 0x4D or card[1] != 0x43:     # "MC"
		return out
	for i in range(1, 16):
		var f := i * FRAME
		if card.decode_u32(f) != FIRST:
			continue
		var size := card.decode_u32(f + 4)
		var name := card.slice(f + 0xA, f + 0xA + 21).get_string_from_ascii()
		var data := PackedByteArray()
		var b := i - 1
		var seen := {}
		while not seen.has(b) and b >= 0 and b < 15:
			seen[b] = true
			data.append_array(card.slice((b + 1) * BLOCK, (b + 2) * BLOCK))
			b = card.decode_u16((b + 1) * FRAME + 8)
		out[name] = data.slice(0, size)
	return out


# card_list_saves (open:0x80014264) counts the files whose first twelve
# characters are BASLUS-00255 and files each at its digit; the slot is that
# digit. [{path, slot, data, title, valid}], by slot.
# @orig open:0x80014264 card_list_saves  status:transcribed -- the names, by their twelve characters, each at its digit; reading the directory is the BIOS's (files)
static func saves(paths := []) -> Array:
	var out := []
	for path in (paths if not paths.is_empty() else card_paths()):
		var card := FileAccess.get_file_as_bytes(str(path))
		var fs := files(card)
		for name in fs:
			var tail: String = str(name).substr(NAME.length())
			if not str(name).begins_with(NAME) or tail.length() != 1 or not tail.is_valid_int():
				continue
			var data: PackedByteArray = fs[name]
			out.append({"path": str(path), "slot": int(tail), "data": data,
				"title": title(data), "valid": valid(data)})
	out.sort_custom(func(a, b): return int(a["slot"]) < int(b["slot"]))
	return out


# @orig game:0x80028c74 save_checksum  status:verified -- all three saves on the emulator's card carry it (tools/memcard.py)
static func checksum(f: PackedByteArray) -> int:
	var s := 0
	for i in range(DATA_AT, mini(DATA_AT + SUMMED, f.size())):
		s += f[i]
	return s & 0xFFFFFFFF


# The file is believed when the sum is the word at +0x200.
# @orig game:0x8002860c save_load_slot  status:transcribed -- the 0x6000 bytes and the sum; the name and the BIOS's open and read are files' and saves'
static func valid(f: PackedByteArray) -> bool:
	return f.size() >= FILE_SIZE and checksum(f) == f.decode_u32(SUM_AT)


# The header's title -- KING'S FIELD 2-3 EXP 11 LV 1 -- the Shift-JIS of
# 0x80081828 and 0x80028b70's numbers turned into plain text: the full-width
# forms are the ASCII ones 0xfee0 up, the full-width space 0x8140.
# @port helper -- Shift-JIS's full-width letters, digits and signs as ASCII
static func title(f: PackedByteArray) -> String:
	var s := ""
	var i := 4
	while i + 1 < mini(0x44, f.size()):
		var hi := int(f[i])
		var lo := int(f[i + 1])
		if hi == 0:
			break
		if hi < 0x80:
			s += char(hi)
			i += 1
			continue
		var code := (hi << 8) | lo
		if code == 0x8140:
			s += " "
		elif code >= 0x824F and code <= 0x8258:
			s += char(0x30 + code - 0x824F)          # 0..9
		elif code >= 0x8260 and code <= 0x8279:
			s += char(0x41 + code - 0x8260)          # A..Z
		elif code >= 0x8281 and code <= 0x829A:
			s += char(0x61 + code - 0x8281)          # a..z
		elif code == 0x8166:
			s += "'"
		elif code == 0x817C or code == 0x815D:
			s += "-"
		else:
			s += "?"
		i += 2
	return " ".join(s.split(" ", false))


# save_restore's fields, by name: each the bytes it puts back, and the blocks
# whole (the spells one byte a record).
# @orig game:0x8005ffd0 save_restore  status:verified -- the table tools/memcard.py holds, which the game's own save_restore writes byte for byte (534 566 of 534 566); the self-test holds this to it field by field (savecheck.json)
static func restore(buf: PackedByteArray) -> Dictionary:
	var out := {}
	for f in FIELDS:
		out[f[3]] = buf.slice(int(f[0]), int(f[0]) + int(f[1]))
	for b in BLOCKS:
		out[b[4]] = buf.slice(int(b[0]), int(b[0]) + int(b[1]))
	return out


# A slot read off the card: save_load_slot's checks and save_restore's
# fields, or {} when it is not there or the sum is wrong -- the game tries
# twice and then says so.
# @port helper -- saves, valid and restore in the order save_load_slot runs them
static func read_slot(slot: int, paths := []) -> Dictionary:
	for s in saves(paths):
		if int(s["slot"]) == slot and bool(s["valid"]):
			return restore((s["data"] as PackedByteArray).slice(DATA_AT))
	return {}


# @port helper -- a little-endian number out of one of restore's fields
static func num(f: Dictionary, name: String, signed := false) -> int:
	var b: PackedByteArray = f[name]
	var v := 0
	for i in range(b.size() - 1, -1, -1):
		v = (v << 8) | int(b[i])
	if signed and b.size() < 8 and v & (1 << (8 * b.size() - 1)):
		v -= 1 << (8 * b.size())
	return v


# @port helper -- a run of halves out of one of restore's fields
static func halves(f: Dictionary, name: String) -> Array:
	var b: PackedByteArray = f[name]
	var out := []
	for i in range(0, b.size() - 1, 2):
		out.append(b.decode_u16(i))
	return out


# What save_restore's blocks are to the port: the level block and the level
# (its first byte, which save_restore copies to current_level and 0x8018fada),
# the story flags, every level's stream (KFLevelState) and from them each
# conversation's place (KFTalk); the player's own fields wait in `loaded`.
# @orig game:0x8005ffd0 save_restore  status:partial -- into the port's own state: the block and the level, the flags, the level states and the conversations; the player's fields are player.gd's (take_save); not seq_state, map_seen, the two 150-byte tables or 0x8009c22c, which nothing in the port reads
static func put(f: Dictionary) -> void:
	var blk: PackedByteArray = f["block"]
	KFGame.block = [int(blk[0]), int(blk[0]), int(blk[0]), int(blk[3]), int(blk[4])]
	KFGame.level = int(blk[0])
	var flags: PackedByteArray = f["flags"]
	KFTalk.flags = []
	for v in flags:
		KFTalk.flags.append(int(v))
	KFLevelState.put(f["area"], f["index"])
	KFTalk.states = {}
	for lv in KFLevelState.LEVELS:
		var d := KFLevelState.decoded(lv)
		for t in d.get("talks", []):
			KFTalk.states["%d/%d" % [lv, int(t[0])]] = {"pc": int(t[1]), "retry": int(t[2])}
	loaded = f

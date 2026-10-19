class_name KFMenu
extends Control
# The menu: pause_menu (0x8001a774) on the menu button, its six lines, and the
# "use item" screen with its prompt -- drawn the way the game draws them,
# primitive for primitive (tools/ui.py, FORMATS.md "The menus, as they are
# drawn"), out of the pages ui.json and ui/ hold.
#
# Every screen files sprites and quads into an ordering table: a deeper one is
# drawn first, and within a depth the one filed last first. Here a screen is a
# Dictionary depth -> [primitive], and _draw walks it in that order.
#
#   ui_draw_label   each glyph twice: at (x - 1, y - 1) in the text colour at
#                   depth 2, at (x, y) in the shadow's at depth 3, 7 apart
#   ui_frame        33-square corners and 28-long edges at depth 50 -- a frame
#                   lower than 66 has a middle row of negative height, flipped
#   ui_panel        a list: the rows, the mode's numbers, the frame, the
#                   chosen row's pulsing bar, the button legend
#
# The world stands still while it is up (KFGame.modal). Not here yet: the
# chosen thing's model turning in the "use item" screen (0x80025be8), the
# guide pages (0x80024f88), and "system"'s LOAD.
#
# @exe game

const SCREEN_W := 320.0
const SCREEN_H := 240.0
const FRAME_HZ := 60.0              # the menu's own frames: frame_begin/frame_end, no frame_limit
const LABEL_STYLE := "0x8007e570"
const NUMBER_STYLE := "0x8007e564"
const SMALL_STYLE := "0x8007e57c"
const RECORDS := 0x8007E588
const UP := 0x1000
const DOWN := 0x4000
const LEFT := 0x8000
const RIGHT := 0x2000
const USE_WORD := [0x14, 0x12, 0x04, 0xFF]                    # "use"
const STORE_WORD := [0x12, 0x13, 0x0E, 0x11, 0x04, 0xFF]      # "store", ui_prompt's kind 1
const MOVE_WORD := [0x0C, 0x0E, 0x15, 0x04, 0xFF]             # "move", its kind 0xa
const QTY_WORD := [0x10, 0x13, 0x18, 0xFF]                    # "qty"
const STORE_LAST := 0x95                                      # the storage's lists run 0..0x95
const CANCEL_WORD := [0x02, 0x00, 0x0D, 0x02, 0x04, 0x0B, 0xFF]   # "cancel"
const FIRST_THING := 0x5F
const LAST_THING := 0x95
const NOTHING_HAPPENS := 0xA
# The keys use_item's arm at 0x8005d188 takes: royal, copper, silver,
# magician's, jail, dwarves', Lyn's.
const KEYS := [135, 137, 138, 139, 140, 142, 144]
const SILVIERA_KEY := 141          # an arm of its own (0x8005d244): the pedestals
# ui_panel's modes with no count column
const NO_COUNTS := [2, 3, 4, 8, 9, 0x10]
# ui_ratings_page's lines, as its sb's leave the label record for each: two
# spaces, and SLASH, BLOW, STAB, then HOLY, FIRE, EARTH, WIND, WATER MAGIC
# on the offense side; POISON and DARK MAGIC in their places on the defense
const SP2 := [0x7F, 0x7F]
const MAGIC := [0x7F, 0x0C, 0x00, 0x06, 0x08, 0x02]
const R_SLASH := [0x12, 0x0B, 0x00, 0x12, 0x07]
const R_BLOW := [0x01, 0x0B, 0x0E, 0x16]
const R_STAB := [0x12, 0x13, 0x00, 0x01]
const R_HOLY := [0x07, 0x0E, 0x0B, 0x18]
const R_FIRE := [0x05, 0x08, 0x11, 0x04]
const R_EARTH := [0x04, 0x00, 0x11, 0x13, 0x07]
const R_WIND := [0x16, 0x08, 0x0D, 0x03]
const R_WATER := [0x16, 0x00, 0x13, 0x04, 0x11]
const R_POISON := [0x0F, 0x0E, 0x08, 0x12, 0x0E, 0x0D]
const R_DARK := [0x03, 0x00, 0x11, 0x0A]
# ui_equip_page's lines: the range of things each lists, and the slot of
# equip_armour it hands the choice to (line 0 is equip_weapon's)
const EQUIP_RANGES := {0: [0x00, 0x21], 2: [0x33, 0x3E], 3: [0x22, 0x29], 4: [0x2A, 0x32],
	5: [0x3F, 0x47], 6: [0x48, 0x50], 7: [0x51, 0x5E], 8: [0x51, 0x5E]}
const ARMOUR_SLOT := {2: 4, 3: 0, 4: 1, 5: 2, 6: 3, 7: 5, 8: 6}
# ui_status_page's five icons: (working skill, u, CLUT) in the order drawn --
# light, fire, earth, wind, water -- 14 square at v 0xc0 of page 0x1d, depth 0x1e
const SKILL_ICONS := [[4, 0x00, 0x7D04], [0, 0x10, 0x7D44], [1, 0x20, 0x7D84],
	[3, 0x30, 0x7DC4], [2, 0x40, 0x7E04]]
const ICON_PAGE := 0x1D
const ICON_V := 0xC0
const ICON_SIZE := 0xE
const ICON_DEPTH := 0x1E

static var data := {}
var tex := {}                       # "tpage_clut" -> [solid, semi]
var ot := {}                        # the screen being drawn: depth -> [prim]
var look := {"box": 0x78, "text": 0x80, "shadow": 0x30, "pulse": 0,
	"confirm": 3, "cancel": 1, "semi": 1, "bright": 0x80, "pulse2": 0}
var state := ""                     # "", "main", "use_item", "prompt", "use_magic", "use_magic_prompt", "equip", ...
var main_sel := 0
var list := {}                      # the use-item screen's list
var spells := {}                    # the use-magic screen's list
var magic_cursor := 0               # gp+0x19: where the use-magic screen's cursor was left
var storage_sel := 0                # item_menu's line: store, take out
var stash := {}                     # the storage's list while it is up
var stash_cursor := [0, 0]          # gp+0x1a, gp+0x1b: where each of its lists was left
var system_sel := 0                 # menu_system's line
var config := {}                    # BUTTON CONFIG's schemes and row while it is up
var display := {}                   # OPTION 2's five values and row while it is up
var sound := {}                     # OPTION 1's three sliders and row while it is up
var quit_sel := 1                   # QUIT GAME's answer lit
var prompt_sel := 0
var equip_sel := 0                  # the equipment screen's line
var records_sel := 0                # status/records' line: offense/defense, conversation
var chooser := {}                   # ui_equip_page's list while it is up
var player: Node
var acc := 0.0
var frames := 0                     # the pad is read every second frame
var latch := 0                      # the buttons newly down since it was
var moved := false                  # gp+0x54: the choice moved this frame


# @port data -- ui.json and the pages under ui/, tools/ui.py export
static func load_data() -> bool:
	if not data.is_empty():
		return true
	if not FileAccess.file_exists("res://ui.json"):
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://ui.json"))
	if typeof(d) != TYPE_DICTIONARY:
		return false
	data = d
	return true


# @port engine -- the pages, and the player for the inventory
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	player = get_node_or_null("../../Player")
	if not load_data():
		return
	for key in data["pages"]:
		var pair := []
		for part in ["_solid", "_semi"]:
			var path := "res://ui/%s%s.png" % [key, part]
			pair.append(load(path) if ResourceLoader.exists(path) else null)
		tex[key] = pair
	visible = false


# -- the drawing, as tools/ui.py has it ---------------------------------------

# @port helper -- a descriptor of 0x8007e588 and its neighbours: tpage, clut, u, v, w, h
static func rec(addr) -> Array:
	var key: String = addr if addr is String else "0x%x" % int(addr)
	return data["records"][key]


# @port helper -- grey: the colour byte in all three channels
static func grey(v: int) -> int:
	return v | (v << 8) | (v << 16)


# @port helper -- AddPrim: at the head of the depth's list
static func add(o: Dictionary, depth: int, p: Dictionary) -> void:
	if not o.has(depth):
		o[depth] = []
	(o[depth] as Array).append(p)


# ui_set_tpage (0x80027610): the page, filed one deeper than what uses it.
# @orig game:0x80027610 ui_set_tpage  status:transcribed
static func set_tpage(o: Dictionary, depth: int, tpage: int) -> void:
	add(o, depth + 1, {"kind": "tpage", "tpage": tpage})


# @port helper -- SetSprt's fields as tools/gpuframe.py reads them back
static func sprite(x: int, y: int, w: int, h: int, u: int, v: int, clut: int, col: int) -> Dictionary:
	return {"kind": "sprite", "x": x, "y": y, "w": w, "h": h, "u": u & 0xFF,
		"v": v & 0xFF, "clut": clut, "rgb": col}


# ui_prim_quad (0x80027494): (x, y) (x+w, y) (x, y+h) (x+w, y+h), a height
# below 0 flipping it.
# @orig game:0x80027494 ui_prim_quad  status:verified -- tools/ui.py, 116 of 116 primitives of inv1 and inv2
static func quad(x: int, y: int, w: int, h: int, u: int, v: int, uw: int, vh: int,
		tpage: int, clut: int, col: int, semi: int) -> Dictionary:
	return {"kind": "quad", "pts": [[x, y], [x + w, y], [x, y + h], [x + w, y + h]],
		"uvs": [[u & 0xFF, v & 0xFF], [(u + uw) & 0xFF, v & 0xFF],
			[u & 0xFF, (v + vh) & 0xFF], [(u + uw) & 0xFF, (v + vh) & 0xFF]],
		"tpage": tpage, "clut": clut, "rgb": col, "semi": semi != 0}


# @orig game:0x800261dc ui_draw_label  status:verified -- tools/ui.py against inv1 and inv2
static func draw_label(o: Dictionary, lk: Dictionary, style: Array, x: int, y: int,
		glyphs: Array, text := -1) -> void:
	set_tpage(o, 3, int(style[0]))
	var col := grey(int(lk["text"])) if text < 0 else text
	var i := 0
	for g in glyphs:
		if int(g) == 0xFF:
			break
		var u := (int(g) & 0xF) << 3
		var v := (int(g) >> 4) * 15
		add(o, 2, sprite(x + 7 * i - 1, y - 1, int(style[4]), int(style[5]), u, v, int(style[1]), col))
		add(o, 3, sprite(x + 7 * i, y, int(style[4]), int(style[5]), u, v, int(style[1]), grey(int(lk["shadow"]))))
		i += 1


# @orig game:0x8002636c ui_draw_number  status:verified -- tools/ui.py against inv1 and inv2
static func draw_number(o: Dictionary, lk: Dictionary, style: Array, x: int, y: int, chars: Array) -> void:
	set_tpage(o, 3, int(style[0]))
	var i := 0
	for c in chars:
		if int(c) == 0xFF:
			break
		var u := int(style[2]) if int(c) < 0xB else int(style[2]) + 7
		var v := int(c) * 15 if int(c) < 0xB else (int(c) - 0xB) * 15
		add(o, 2, sprite(x + 7 * i - 1, y - 1, int(style[4]), int(style[5]), u, v, int(style[1]), grey(int(lk["text"]))))
		add(o, 3, sprite(x + 7 * i, y, int(style[4]), int(style[5]), u, v, int(style[1]), grey(int(lk["shadow"]))))
		i += 1


# @orig game:0x800277c0 number_digits  status:transcribed
static func number_digits(value: int, n: int, fill: int, mode: int) -> Array:
	var ln := n + int({1: 1, 2: 1, 3: 2, 5: 2, 4: 3}.get(mode, 0))
	var out := []
	for _i in ln:
		out.append(0xA if fill == 0 else 0)
	out.append(0xFF)
	var last := ln - 1
	match mode:
		1:
			out[0] = 0x13
		2:
			out[ln - 1] = 0xD
			last = ln - 2
		3:
			out[0] = 0xF
			out[1] = 0x10
		4:
			out[0] = 0xC
			out[1] = 0x12
			out[2] = 0x10
		5:
			out[0] = 0xE
			out[1] = 0x11
	var i := last
	while i >= 0:
		out[i] = value % 10
		value /= 10
		if value == 0:
			break
		i -= 1
	return out


# @orig game:0x80025f38 ui_label_plate  status:verified -- tools/ui.py against inv1 and inv2
static func label_plate(o: Dictionary, lk: Dictionary, r: Array, x: int, y: int) -> void:
	add(o, 50, quad(x - 6, y - 6, int(r[4]), int(r[5]), int(r[2]), int(r[3]), int(r[4]), int(r[5]),
		int(r[0]), int(r[1]), grey(int(lk["box"])), int(lk["semi"])))


# @port helper -- ui_panel's pulse: the chosen row's colours from gp+0x4c
static func bar_colour(lk: Dictionary) -> Array:
	var a := int(lk["pulse"])
	var b := int(lk["box"])
	if a < 0x30:
		return [a + b, (a >> 1) + b]
	return [b + 0x5F - a, b + 0x2F - (a >> 1)]


# sub_80026020 (rec, label, pulse): a plate in the pulsing colour -- of the
# selection's pulse (gp+0x4c) for every caller but ui_display_values, which hands
# it the second (gp+0x50, lk["pulse2"]).
# @orig game:0x80026020 sub_80026020  status:transcribed
static func lit_plate(o: Dictionary, lk: Dictionary, r: Array, x: int, y: int, pulse := -1) -> void:
	var c: Array = bar_colour(lk)
	if pulse >= 0:
		c = bar_colour({"pulse": pulse, "box": lk["box"]})
	add(o, 50, quad(x - 6, y - 6, int(r[4]), int(r[5]), int(r[2]), int(r[3]), int(r[4]), int(r[5]),
		int(r[0]), int(r[1]), int(c[0]) | (int(c[0]) << 8) | (int(c[1]) << 16), int(lk["semi"])))


# @orig game:0x80026158 sub_80026158  status:transcribed
static func dim_label(o: Dictionary, lk: Dictionary, style: Array, x: int, y: int, glyphs: Array) -> void:
	var col := 0x57 | (0x57 << 8) | (int(lk["text"]) << 16)
	if int(lk["semi"]) == 0:
		col = 0x47 | (0x47 << 8) | (0x57 << 16)
	draw_label(o, lk, style, x, y, glyphs, col)


# @orig game:0x80026acc ui_frame  status:verified -- tools/ui.py, the list's 30 pieces in inv1 and inv2
static func frame(o: Dictionary, lk: Dictionary, x: int, y: int, w: int, h: int) -> void:
	var col := grey(int(lk["box"]))
	var semi := int(lk["semi"])
	var s5 := x
	var s6 := y
	var t0 := h - 0x42
	var k := 9
	for s4 in 6:
		if s4 == 3:
			s5 = x
			k += 3
			s6 = s6 + 0x21 + (t0 if t0 >= 0 else 0)
		var r: Array = rec(RECORDS + 12 * k)
		var s3: int
		var fv: int
		if s4 >= 3 and t0 < 0:
			s3 = h - 0x21
			fv = int(r[3]) + 0x42 - h
		else:
			s3 = int(r[5])
			fv = int(r[3])
		var s0 := int(r[4])
		var s2 := w - 0x42
		while true:
			add(o, 50, quad(s5, s6, s0, s3, int(r[2]), fv, s0, s3, int(r[0]), int(r[1]), col, semi))
			s5 += s0
			if s4 != 1 and s4 != 4:
				break
			s2 -= s0
			if s2 == 0:
				break
			if s2 < s0:
				s0 = s2
		k += 1
	var left := t0
	s6 = y + 0x21
	while true:
		var s3 := 0
		for kk in [12, 13, 14]:
			var r: Array = rec(RECORDS + 12 * kk)
			s3 = int(r[5]) if not left < int(r[5]) else left
			var s0 := int(r[4])
			var s2 := w - 0x42
			if kk == 12:
				s5 = x
			while true:
				add(o, 50, quad(s5, s6, s0, s3, int(r[2]), int(r[3]), s0, s3, int(r[0]), int(r[1]), col, semi))
				s5 += s0
				if kk != 13:
					break
				s2 -= s0
				if s2 == 0:
					break
				if s2 < s0:
					s0 = s2
		s6 += 0x1C
		left -= s3
		if left == 0:
			break


# @orig game:0x800269c0 ui_button  status:verified -- tools/ui.py against inv1 and inv2
static func button(o: Dictionary, lk: Dictionary, x: int, y: int, b: int) -> void:
	var r: Array = rec(RECORDS + 12 * 3)
	set_tpage(o, 6, int(r[0]))
	var s0 := (int(lk["bright"]) - 0x80) >> 1 if int(lk["bright"]) > 0x80 else 0
	add(o, 6, sprite(x, y, int(r[4]), int(r[5]), int(r[2]) + (b << 4), int(r[3]), int(r[1]), grey(s0 + 0x70)))


# ui_small_text (x, y, ascii, shadow, row): lower-case ASCII in 8 x 8
# letters, at depth 5 -- or, shadowed, in the text colour a pixel up and left
# at depth 5 over the shadow's at depth 6; row 1 takes the letters 16 lower.
# @orig game:0x80026570 ui_small_text  status:verified -- tools/ui.py against inv1 and inv2; the shadowed form through options_check, 112 of 112 frames of the game's own options_screen
static func small_text(o: Dictionary, lk: Dictionary, x: int, y: int, text: Array,
		shadow := 0, row := 0) -> void:
	var r: Array = rec(SMALL_STYLE)
	set_tpage(o, 6, int(r[0]))
	var s0 := ((int(lk["bright"]) - 0x80) >> 1 if int(lk["bright"]) > 0x80 else 0) + 0x70
	var s6 := 16 if row > 0 else 0
	var i := 0
	for ch in text:
		var u := int(r[2]) + (int(ch) - 0x61) * int(r[4])
		if shadow == 0:
			add(o, 5, sprite(x + 8 * i, y, int(r[4]), int(r[5]), u, int(r[3]) + s6, int(r[1]), grey(s0)))
		else:
			add(o, 5, sprite(x + 8 * i - 1, y - 1, int(r[4]), int(r[5]), u, int(r[3]) + s6,
				int(r[1]), grey(int(lk["text"]))))
			add(o, 6, sprite(x + 8 * i, y, int(r[4]), int(r[5]), u, int(r[3]) + s6,
				int(r[1]), grey(int(lk["shadow"]))))
		i += 1


# The legend under a list (ui_panel's tail, 0x80025a2c).
# @orig game:0x80025a2c ui_panel+0x5c4  status:verified -- the three-button legend of inv1 and inv2; the two-button one transcribed
static func legend(o: Dictionary, lk: Dictionary, two: bool) -> void:
	var words: Dictionary = data["words"]
	if two:
		button(o, lk, 0x5F, 0xD6, int(lk["confirm"]))
		small_text(o, lk, 0x69, 0xD6, words["select"])
		button(o, lk, 0xA0, 0xD6, int(lk["cancel"]))
		small_text(o, lk, 0xAA, 0xD6, words["return"])
		return
	button(o, lk, 0x42, 0xD6, int(lk["confirm"]))
	small_text(o, lk, 0x4C, 0xD6, words["select"])
	button(o, lk, 0x83, 0xD6, 0)
	small_text(o, lk, 0x8D, 0xD6, words["guide"])
	button(o, lk, 0xBC, 0xD6, int(lk["cancel"]))
	small_text(o, lk, 0xC6, 0xD6, words["return"])


# ui_panel (0x80025468): the title, the rows, the frame, the chosen row's bar
# and the legend. Mode 3 puts a second name 0x54 to the right of each row's
# (the equipment screen's), modes 1 and 5 the count "x N" at x + 0xe9; the
# legend is two buttons for modes 3, 8, 9 and 12 and with flag 0x8000; modes
# 2 and 4 the cost behind the MP sign, one arm (.L8) for both.
# @orig game:0x80025468 ui_panel  status:partial -- modes 1, 2, 3, 4, 5, 7 and 0x10 and the 0x8000 flag; tools/ui.py, 116 of 116 primitives of inv1 and inv2, and modes 4, 0x10, 2 and 7 160 of 160 frames of the game's own (panel_check); the number columns of modes 8, 9, 0xa..0xf not here
static func panel(o: Dictionary, lk: Dictionary, s: Dictionary, mode: int) -> void:
	var style: Array = rec(LABEL_STYLE)
	var m := mode & 0xFFF
	if not (s["title"] as Array).is_empty():
		label_plate(o, lk, rec(RECORDS + 12 * 2), int(s["tx"]), int(s["ty"]))
		draw_label(o, lk, style, int(s["tx"]), int(s["ty"]), s["title"])
	for row in int(s["rows"]):
		if row >= int(s["count"]):
			break
		var k := int(s["first"]) + row
		var x := int(s["x"]) + 0xD
		var y := int(s["y"]) + 8 + (row << 4)
		draw_label(o, lk, style, x, y, (s["names"][k] as Array).slice(0, int(s["length"])))
		if m == 3:
			draw_label(o, lk, style, x + 0x54, y,
				(s["names2"][k] as Array).slice(0, 0x18) + [0xFF])
		if (m == 2 or m == 4) and int(s["costs"][k]) != -1:
			# .L8, for modes 2 and 4 alike: the u32 column (+0x30), three
			# digits behind the MP sign
			x += 0xCE
			draw_number(o, lk, rec(NUMBER_STYLE), x, y,
				number_digits(int(s["costs"][k]), 3, 0, 3))
		if m == 0x10:
			# .L14: the thing's count, then a spell's cost, each moving the
			# place on from where the last left it
			if int(s["counts"][k]) != 0xFF:
				x += 0xDC
				draw_number(o, lk, rec(NUMBER_STYLE), x, y,
					number_digits(int(s["counts"][k]), 2, 0, 1))
			if int(s["costs"][k]) != -1:
				x += 0xCE
				draw_number(o, lk, rec(NUMBER_STYLE), x, y,
					number_digits(int(s["costs"][k]), 3, 0, 3))
		if not (m in NO_COUNTS) and int(s["counts"][k]) != 0xFF:
			draw_number(o, lk, rec(NUMBER_STYLE), int(s["x"]) + 0xE9, y,
				number_digits(int(s["counts"][k]), 2, 0, 1))
	frame(o, lk, int(s["x"]), int(s["y"]), 0x10A, (int(s["rows"]) << 4) | 0xC)
	for row in int(s["rows"]):
		if row != int(s["sel_row"]):
			continue
		var c: Array = bar_colour(lk)
		var r: Array = rec(RECORDS + 12 * 8)
		add(o, 49, quad(int(s["x"]) + 6, int(s["y"]) + (row << 4) + 5, int(r[4]), int(r[5]),
			int(r[2]), int(r[3]), int(r[4]), int(r[5]), int(r[0]), int(r[1]),
			int(c[0]) | (int(c[0]) << 8) | (int(c[1]) << 16), 1))
	if m == 7:
		quantity(o, lk, int(s.get("qty", 1)))
	legend(o, lk, m in [3, 8, 9, 0xC] or (mode & 0x8000) != 0)


# ui_quantity(0) (0x80025db8), ui_panel's for mode 7 after the bar: a plate at (0xb7,
# 0x2e) with "QTY" on it, and the quantity (gp+0x48) in two digits 0x54 to
# the right. Its 1 -- the shops' modes, at y 0x4a after the gold
# (sub_80025e80) -- is not here.
# @orig game:0x80025db8 ui_quantity  status:partial -- its 0, mode 7's; drawn as tools/ui.py draws it, which the game's own ui_panel holds (panel_check, 40 of 40 frames); not its 1
static func quantity(o: Dictionary, lk: Dictionary, qty: int) -> void:
	label_plate(o, lk, rec(RECORDS + 12 * 2), 0xB7, 0x2E)
	draw_label(o, lk, rec(LABEL_STYLE), 0xB7, 0x2E, QTY_WORD)
	draw_number(o, lk, rec(NUMBER_STYLE), 0xB7 + 0x54, 0x2E, number_digits(qty, 2, 0, 1))


# item_list (0x8001aea4): the things first..last carried in inventory_a --
# 95..149 for "use item", a line's range for the equipment.
# @orig game:0x8001aea4 item_list  status:transcribed
static func item_list(inv: PackedByteArray, first := FIRST_THING, last := LAST_THING) -> Dictionary:
	var names := []
	var counts := []
	var ids := []
	for i in range(first, last + 1):
		if int(inv[i]) != 0:
			names.append(data["names"][i])
			counts.append(int(inv[i]))
			ids.append(i)
	counts.append(0xFF)
	return {"names": names, "counts": counts, "ids": ids}


# ui_menu_label(0, 0) and sub_80027728: the list under "use item" -- x 27,
# y 147, three rows -- its selection held to it, the first row and the bar.
# @orig game:0x80027688 ui_menu_label  status:verified -- the list's place in inv1 and inv2
# @orig game:0x80027728 list_place  status:transcribed
static func use_item_list(inv: PackedByteArray, selected: int) -> Dictionary:
	var l := item_list(inv)
	var title: Array = data["labels"][0][0][2]
	var s := {"tx": 0x1F, "ty": 0x20, "title": title, "x": 0x1B, "y": 0x93, "rows": 3,
		"length": 0x18, "count": (l["ids"] as Array).size(), "names": l["names"],
		"counts": l["counts"], "ids": l["ids"], "sel": 0, "first": 0, "sel_row": 0}
	place(s, selected)
	return s


# @port helper -- sub_80027728's arithmetic: the selection, the first row shown, the bar's row
static func place(s: Dictionary, selected: int) -> void:
	var n := int(s["count"])
	var sel := mini(selected, n - 1) if n > 0 else 0
	s["sel"] = sel
	if n - sel < int(s["rows"]):
		if n < int(s["rows"]):
			s["first"] = 0
			s["sel_row"] = sel
		else:
			s["first"] = n - int(s["rows"])
			s["sel_row"] = sel - int(s["first"])
	else:
		s["first"] = sel
		s["sel_row"] = 0


# ui_menu_chrome's up and down (0x800223a4..0x800224d0): the selection
# moves one, the bar with it until it reaches the edge of the rows shown and
# then the rows under it; past either end it goes round -- to the last, the
# rows showing the end of the list, or to the first.
# @orig game:0x800223a4 ui_menu_chrome+0xa8  status:verified -- the up and down: the rows shown after them as inv3 holds them, and through chrome_pad 200 of 200 runs of the storage as the game's own (storage_check); the sound (0xc) not here
static func chrome_move(s: Dictionary, press: int) -> bool:
	var n := int(s["count"])
	var rows := int(s["rows"])
	if n == 0:
		return false
	if press & UP:
		if int(s["sel"]) != 0:
			s["sel"] = int(s["sel"]) - 1
			if int(s["sel_row"]) != 0:
				s["sel_row"] = int(s["sel_row"]) - 1
			else:
				s["first"] = int(s["first"]) - 1
		else:
			s["sel"] = n - 1
			if n < rows:
				s["first"] = 0
				s["sel_row"] = n - 1
			else:
				s["first"] = n - rows
				s["sel_row"] = rows - 1
		return true
	if press & DOWN:
		if int(s["sel"]) < n - 1:
			s["sel"] = int(s["sel"]) + 1
			if int(s["sel_row"]) == rows - 1:
				s["first"] = int(s["first"]) + 1
			else:
				s["sel_row"] = int(s["sel_row"]) + 1
		else:
			s["sel"] = 0
			s["first"] = 0
			s["sel_row"] = 0
		return true
	return false


# equip_names (0x8001c9c0): the equipment screen's ten names -- the weapon,
# magic A, the shield, head, body, arms, feet, the two items, and the
# button's spell or, with none, its thing; a spell's name for magic A and a
# spell on the button, a thing's otherwise, 0xff for nothing.
# @orig game:0x8001c9c0 equip_names  status:transcribed
static func equip_names(st: Dictionary) -> Array:
	var out := []
	var ids := equip_ids(st)
	for i in ids.size():
		var ident := int(ids[i])
		if ident == 0xFF:
			out.append([0xFF])
		elif i == 1 or (i == 9 and int(st["spell_b"]) != 0xFF):
			out.append(data["equip"]["spells"][ident])
		else:
			out.append(data["names"][ident])
	return out


# @port helper -- equip_names' ten bytes, out of the player's slots
static func equip_ids(st: Dictionary) -> Array:
	var w: Array = st["worn"]
	var last := int(st["spell_b"]) if int(st["spell_b"]) != 0xFF else int(st["item_b"])
	return [int(st["weapon"]), int(st["spell_a"]), int(w[2]), int(w[0]), int(w[1]),
		int(w[3]), int(w[4]), int(w[5]), int(w[6]), last]


# menu_equipment (0x8001c7a8): ui_menu_label's list with no title, ten rows
# from x 0x1b, y 0x23 -- the headings and, in mode 3, the names beside them.
# @orig game:0x8001c7a8 menu_equipment  status:partial -- the ten lines, drawn as the game draws them (equip1, equip4: 4 of 4 buffers), and their choosing; magic (1) and the button (9) open nothing yet (0x8001d0c4, 0x8001d3a0)
static func equipment_list(st: Dictionary, sel: int) -> Dictionary:
	return {"tx": 0, "ty": 0x20, "title": [], "x": 0x1B, "y": 0x23, "rows": 10,
		"length": 0x18, "count": 10, "sel": sel, "first": 0, "sel_row": sel,
		"names": data["equip"]["headings"], "names2": equip_names(st),
		"counts": [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]}


# ui_equip_page's list (0x8001cbb8) for a line: what is carried in its range
# and "TAKE OFF", the other item line's thing counted one less, the
# selection on what is worn now -- under ui_menu_label's title "EQUIPMENT".
# @orig game:0x8001cbb8 ui_equip_page  status:partial -- the list, its choosing, the prompt and the equipping, the list and prompt drawn as the game draws them (equip2, equip3: 4 of 4 buffers); not the thing's model turning (0x80025be8) or the guide (0x80024f88)
static func equip_list(inv: PackedByteArray, line: int, st: Dictionary) -> Dictionary:
	var counted := inv.duplicate()
	if line == 7 or line == 8:
		var other := int(st["worn"][6 if line == 7 else 5])
		if other != 0xFF:
			counted[other] = int(counted[other]) - 1
	var range_: Array = EQUIP_RANGES[line]
	var l := item_list(counted, int(range_[0]), int(range_[1]))
	var names: Array = l["names"]
	var ids: Array = l["ids"]
	var counts: Array = l["counts"]
	counts.pop_back()
	names.append(data["equip"]["take_off"])
	counts.append(0xFF)
	ids.append(0xFF)
	var now := int(equip_ids(st)[line])
	var sel := 0
	for i in ids.size() - 1:
		if int(ids[i]) == now:
			sel = i
			break
	var s := {"tx": 0x1F, "ty": 0x20, "title": data["labels"][0][2][2], "x": 0x1B,
		"y": 0x93, "rows": 3, "length": 0x18, "count": ids.size(), "names": names,
		"counts": counts, "ids": ids, "sel": 0, "first": 0, "sel_row": 0, "line": line}
	place(s, sel)
	return s


# sub_8001c6c0: the names, MP costs and ids of the spells first..last whose
# record's +0 is 1 -- `table` the 96 records' bytes.
# @orig game:0x8001c6c0 sub_8001c6c0  status:verified -- through panel_check's lists, 80 of 80 frames of the game's own ui_panel
static func spell_rows(table: PackedByteArray, first: int, last: int) -> Dictionary:
	var names := []
	var costs := []
	var ids := []
	for k in range(first, last + 1):
		if int(table[24 * k]) == 1:
			names.append(data["equip"]["spells"][k])
			costs.append(int(table[24 * k + 0x16]) | (int(table[24 * k + 0x17]) << 8))
			ids.append(k)
	return {"names": names, "costs": costs, "ids": ids}


# menu_use_magic's list (0x8001c48c): the healing and protecting spells
# 0x17..0x1e unlocked, their MP beside them in mode 2, under ui_menu_label(0,
# 1)'s title "USE MAGIC" -- four rows from y 0x83, no "TAKE OFF" -- the
# selection where gp+0x19 left it (list_place).
# @orig game:0x8001c48c menu_use_magic  status:partial -- the list up to list_place, verified 40 of 40 as the game's own builds it over menu1 (tools/ui.py panel_check); the self-test this to it
static func use_magic_list(table: PackedByteArray, cursor: int) -> Dictionary:
	var r := spell_rows(table, 0x17, 0x1E)
	var ids: Array = r["ids"]
	var s := {"tx": 0x1F, "ty": 0x20, "title": data["labels"][0][1][2], "x": 0x1B,
		"y": 0x83, "rows": 4, "length": 0x18, "count": ids.size(), "names": r["names"],
		"costs": r["costs"], "counts": [], "ids": ids, "sel": 0, "first": 0, "sel_row": 0}
	place(s, cursor)
	return s


# item_list_unheld (0x8001af88): item_list's names, counts and ids, but a thing worn or held
# -- the weapon (0x801b25af), the seven worn bytes 0x801b25d4..da, the
# button's thing (0x801b25ad) -- counted one less, two less when both item
# slots (d9, da) hold it, and left out when that leaves none.
# @orig game:0x8001af88 item_list_unheld  status:verified -- through storage_check, 200 of 200 lists as the game's own builds them over menu1
static func store_rows(inv: PackedByteArray, st: Dictionary) -> Dictionary:
	var w: Array = st["worn"]
	var held := [int(st["weapon"]), int(st["item_b"])]
	for b in w:
		held.append(int(b))
	var names := []
	var counts := []
	var ids := []
	for i in STORE_LAST + 1:
		var c := int(inv[i])
		if c == 0:
			continue
		if i in held:
			c = (c - 2 if i == int(w[5]) and i == int(w[6]) else c - 1) & 0xFF
		if c == 0:
			continue
		names.append(data["names"][i])
		counts.append(c)
		ids.append(i)
	return {"names": names, "counts": counts, "ids": ids}


# item_menu's two lists, under ui_menu_label(2, which): "STORE" (0,
# menu_store) the things carried as item_list_unheld counts them, "TAKE OUT"
# (1, menu_take_out) the things in storage, inventory_b, as item_list does;
# three rows from y 0x93, the selection where gp+0x1a or gp+0x1b left it, the
# quantity 1 as ui_menu_label leaves it.
# @orig game:0x8001dee4 menu_store  status:partial -- "store": verified, the list 200 of 200 as the game's own builds it, and runs of pad words through storage_press as the game's own runs them, over menu1 (tools/ui.py storage_check); not the thing's turning model or the guide
# @orig game:0x8001e1b4 menu_take_out  status:partial -- "take out", verified by the same check; not the model or the guide
static func storage_list(which: int, inv: PackedByteArray, st: Dictionary, cursor: int) -> Dictionary:
	var l := store_rows(inv, st) if which == 0 else item_list(inv, 0, STORE_LAST)
	var counts: Array = l["counts"]
	if which == 1:
		counts.pop_back()
	var n := (l["ids"] as Array).size()
	var costs := []
	for k in n:
		costs.append(-1)
	var s := {"tx": 0x1F, "ty": 0x20, "title": data["labels"][2][which][2], "x": 0x1B,
		"y": 0x93, "rows": 3, "length": 0x18, "count": n, "names": l["names"],
		"counts": counts, "costs": costs, "ids": l["ids"], "which": which, "qty": 1,
		"mode": 0, "prompt": 0, "sel": 0, "first": 0, "sel_row": 0}
	place(s, cursor)
	return s


# One pad word on the storage's list: while the list is up (s["mode"] 0)
# its ui_menu_chrome with kind 2 -- the confirm refused, back to the list,
# when the chosen row's count is under the quantity or the other side would
# reach 100 -- and while ui_prompt(s, 1 or 0xa, 7) asks (mode 1, s["prompt"]
# the answer lit) "STORE" or "MOVE", and "CANCEL" back to the list. The first
# answer moves the quantity across. -0x63 while the screen is up, -1 when it
# goes, or the id of the thing moved.
# @orig game:0x8001dfcc menu_store+0xe8  status:partial -- its loop, tools/ui.py storage_press: verified, storage_check 200 of 200 runs of both screens as the game's own, the self-test this to it; not the guide, the model or the sounds
# @orig game:0x8001e29c menu_take_out+0xe8  status:partial -- the same loop, take out's, verified with it; not the guide, the model or the sounds
static func storage_press(s: Dictionary, press: int, inv_a: PackedByteArray,
		inv_b: PackedByteArray, confirm: int, cancel: int) -> int:
	if int(s["mode"]) == 1:
		var r := prompt_press(int(s["prompt"]), press, confirm, cancel)
		s["prompt"] = int(r[0])
		if r[1] == null:
			return -0x63
		if int(r[1]) == 0:
			var i := int(s["ids"][int(s["sel"])])
			var q := int(s["qty"])
			if int(s["which"]) == 0:
				inv_a[i] = (int(inv_a[i]) - q) & 0xFF
				inv_b[i] = (int(inv_b[i]) + q) & 0xFF
			else:
				inv_a[i] = (int(inv_a[i]) + q) & 0xFF
				inv_b[i] = (int(inv_b[i]) - q) & 0xFF
			return i
		s["mode"] = 0
		return -0x63
	var c := chrome_pad(s, press, 2, confirm, cancel)
	if int(c[1]) == -1:
		return -1
	if int(c[0]) == 1:
		var k := int(s["sel"])
		var other := inv_b if int(s["which"]) == 0 else inv_a
		if not (int(s["counts"][k]) < int(s["qty"]) \
				or int(other[int(s["ids"][k])]) + int(s["qty"]) >= 0x64):
			s["mode"] = 1
			s["prompt"] = 0
	return -0x63


# ui_menu_chrome's pad: one word read, one thing done, in this order -- an
# empty list goes at any button; UP and DOWN move the selection
# (chrome_move); with kind 2 (the storage) RIGHT raises the quantity
# (s["qty"], gp+0x48) while the chosen row's count holds one more, and with
# any kind LEFT lowers it to no less than 1; the confirm asks (mode 1), the
# cancel leaves (-1). [mode, result -0x63 or -1]. Kind 1, the shops' gold
# check, is not here.
# @orig game:0x80022374 ui_menu_chrome+0x78  status:partial -- the pad's arms, verified through storage_check (200 of 200 runs as the game's own): the up, the down, the quantity, the confirm and the cancel; not kind 1 (the shops' gold), the model's turning or the sounds
static func chrome_pad(s: Dictionary, press: int, kind: int, confirm: int, cancel: int) -> Array:
	if int(s["count"]) == 0:
		return [0, -1 if press != 0 else -0x63]
	if press & (UP | DOWN):
		chrome_move(s, press)
	elif press & RIGHT:
		if kind == 2 and int(s["counts"][int(s["sel"])]) >= int(s["qty"]) + 1:
			s["qty"] = int(s["qty"]) + 1
	elif press & LEFT:
		if kind != 0 and int(s["qty"]) >= 2:
			s["qty"] = int(s["qty"]) - 1
	elif press & confirm:
		return [1, -0x63]
	elif press & cancel:
		return [0, -1]
	return [0, -0x63]


# One word of ui_prompt's loop: UP or DOWN turns between its two answers,
# the confirm answers -- 0 for the first, -1 for the second -- and the
# cancel answers -1. [sel, the answer or null].
# @orig game:0x80024e84 ui_prompt+0x214  status:partial -- the answer, verified through storage_check, 200 of 200 runs as the game's own; its drawing is the callers' (panel, options); not the model or the sounds
static func prompt_press(sel: int, press: int, confirm: int, cancel: int) -> Array:
	if press & (UP | DOWN):
		return [1 - sel, null]
	if press & confirm:
		return [sel, -sel]
	if press & cancel:
		return [sel, -1]
	return [sel, null]


# options_screen's two switches, read with their delay slots: for each
# action scheme the word beside each of the four buttons, and for each
# movement scheme the action beside each of the six after them
const OPTION_ACTIONS := [[0, 1, 2, 3], [2, 1, 0, 3], [0, 3, 2, 1], [2, 3, 0, 1]]
const OPTION_MOVES := [[0, 1, 2, 3, 4, 5], [1, 3, 0, 2, 4, 5], [0, 2, 1, 3, 4, 5],
	[7, 1, 8, 3, 4, 6], [1, 3, 7, 8, 4, 6], [7, 8, 1, 3, 4, 6], [3, 0, 1, 2, 4, 5]]


# options_screen, BUTTON CONFIG's page: buttons 0..3 at x 0x89 from y 0x31,
# 14 apart, each with its word for the action scheme beside it at x 0x9b;
# buttons 4..9 from y 0x6f with their actions for the movement scheme;
# "action" and the action scheme's name, "move" and the movement scheme's --
# all shadowed; the pulsing bar 0x35 x 0xf at x 0x37 on the row chosen; the
# frame 0x102 x 0xb0 at (0x1f, 0x20); its own legend, button 9 "select" and
# the cancel's "return".
# @orig game:0x80023fd4 options_screen  status:verified -- tools/ui.py options_page, 112 of 112 frames of the game's own over menu1 (every scheme, both rows, two pulses; options_check); the self-test this to it
static func options_page(o: Dictionary, lk: Dictionary, action: int, move: int, row: int) -> void:
	var w: Dictionary = data["options"]
	for i in 4:
		button(o, lk, 0x89, 0x31 + 14 * i, i)
		small_text(o, lk, 0x9B, 0x32 + 14 * i, w["buttons"][int(OPTION_ACTIONS[action][i])], 1, 0)
	for i in 6:
		button(o, lk, 0x89, 0x6F + 14 * i, 4 + i)
		small_text(o, lk, 0x9B, 0x70 + 14 * i, w["actions"][int(OPTION_MOVES[move][i])], 1, 0)
	small_text(o, lk, 0x32, 0x32, w["action"], 1, 0)
	small_text(o, lk, 0x3A, 0x40, w["schemes"][action], 1, 0)
	small_text(o, lk, 0x32, 0x70, w["move"], 1, 0)
	small_text(o, lk, 0x3A, 0x7E, w["schemes"][move], 1, 0)
	var c: Array = bar_colour(lk)
	var r: Array = rec(RECORDS + 12 * 8)
	add(o, 49, quad(0x37, 0x7A if row != 0 else 0x3C, 0x35, 0xF, int(r[2]), int(r[3]),
		int(r[4]), int(r[5]), int(r[0]), int(r[1]),
		int(c[0]) | (int(c[0]) << 8) | (int(c[1]) << 16), 1))
	frame(o, lk, 0x1F, 0x20, 0x102, 0xB0)
	button(o, lk, 0x5B, 0xD6, 9)
	small_text(o, lk, 0x69, 0xD6, data["words"]["select"])
	button(o, lk, 0xA0, 0xD6, int(lk["cancel"]))
	small_text(o, lk, 0xAA, 0xD6, data["words"]["return"])


# One pad word on BUTTON CONFIG: the cancel leaves; UP or DOWN turns between
# the rows, the action scheme (0) and the movement scheme (1); LEFT lowers
# the row's scheme and RIGHT raises it, held to 0..3 and 0..6. `st` holds
# "action", "move", "row"; true when it leaves, the caller then storing the
# two (0x801b25e2, e3) and running apply_control_scheme.
# @orig game:0x8001f31c menu_button_config  status:partial -- the pad, verified: tools/ui.py button_config_press, 120 of 120 runs as the game's own runs them whole (options_check); the self-test this to it; not the sounds
static func button_config_press(st: Dictionary, press: int, cancel: int) -> bool:
	if press & cancel:
		return true
	if press & (UP | DOWN):
		st["row"] = 1 if int(st["row"]) == 0 else 0
	elif press & LEFT:
		var k := "move" if int(st["row"]) != 0 else "action"
		if int(st[k]) != 0:
			st[k] = int(st[k]) - 1
	elif press & RIGHT:
		var k := "move" if int(st["row"]) != 0 else "action"
		st[k] = mini(int(st[k]) + 1, 6 if int(st["row"]) != 0 else 3)
	return false


# ui_display_values's words, immediates in its code: the three plates' letters,
# and "on"/"off" -- "clear"/"solid" on the last row
const STYLE_LETTERS := [[0x00, 0xFF], [0x01, 0xFF], [0x02, 0xFF]]
const WORD_ON := [0x7F, 0x7F, 0x0E, 0x0D, 0xFF]
const WORD_OFF := [0x7F, 0x7F, 0x0E, 0x05, 0x05, 0xFF]
const WORD_CLEAR := [0x02, 0x0B, 0x04, 0x00, 0x11, 0xFF]
const WORD_SOLID := [0x12, 0x0E, 0x0B, 0x08, 0x03, 0xFF]


# ui_display_values (0x800246bc), OPTION 2's five values beside its lines: the two styles, rows
# at y 0x3a and 0x54, three plates (record 5) at x 0xab, 0xc7 and 0xe3
# lettered A, B, C -- A lit for 2, B for 1, C for 0 -- each letter 4 right of
# its plate's place; the three switches, from y 0x6e 26 apart, two smaller
# plates (record 1) at 0xab and 0xe5, "on" and "off" ("clear" and "solid" on
# the last), the first lit for 1. The lit plates pulse with gp+0x50.
# @orig game:0x800246bc ui_display_values  status:verified -- tools/ui.py display_values, 72 of 72 frames of the game's own over menu1, half with the panel solid (display_check); the self-test this to it
static func display_values(o: Dictionary, lk: Dictionary, values: Array) -> void:
	var style: Array = rec(LABEL_STYLE)
	var big: Array = rec(RECORDS + 12 * 5)
	var small: Array = rec(RECORDS + 12 * 1)
	var y := 0x3A
	for row in 2:
		var v := int(values[row])
		var lit := 0 if v == 2 else (1 if v == 1 else 2)
		var i := 0
		for x in [0xAB, 0xC7, 0xE3]:
			if i == lit:
				lit_plate(o, lk, big, x, y, int(lk["pulse2"]))
				draw_label(o, lk, style, x + 4, y, STYLE_LETTERS[i])
			else:
				label_plate(o, lk, big, x, y)
				dim_label(o, lk, style, x + 4, y, STYLE_LETTERS[i])
			i += 1
		y += 0x1A
	for row in 3:
		var one: Array = WORD_CLEAR if row == 2 else WORD_ON
		var two: Array = WORD_SOLID if row == 2 else WORD_OFF
		if int(values[2 + row]) == 1:
			lit_plate(o, lk, small, 0xAB, y, int(lk["pulse2"]))
			draw_label(o, lk, style, 0xAB, y, one)
			label_plate(o, lk, small, 0xE5, y)
			dim_label(o, lk, style, 0xE5, y, two)
		else:
			label_plate(o, lk, small, 0xAB, y)
			dim_label(o, lk, style, 0xAB, y, one)
			lit_plate(o, lk, small, 0xE5, y, int(lk["pulse2"]))
			draw_label(o, lk, style, 0xE5, y, two)
		y += 0x1A


# OPTION 2's frame: sub_800252f4(5, 5, row, 1) -- page 5's five lines, the
# row chosen lit, button 9's legend -- and the values beside them.
# @port helper -- the two calls of OPTION 2's frame (0x8001f1e0)
static func display_page(o: Dictionary, lk: Dictionary, values: Array, row: int) -> void:
	menu_page(o, lk, 5, 5, row, 1)
	display_values(o, lk, values)


# One pad word on OPTION 2: UP and DOWN move round the five rows; the
# confirm, RIGHT or LEFT change the row's value -- the two styles stepping 2,
# 1, 0, 2 on the confirm and RIGHT and the other way on LEFT, the three
# switches turned over by any of them -- and the cancel leaves. `st` holds
# "values" (five) and "row"; true when it leaves, the caller then storing the
# five and running panel_colours.
# @orig game:0x8001f004 menu_display  status:partial -- the pad, verified: tools/ui.py display_press, 120 of 120 runs as the game's own runs them whole (display_check); the self-test this to it; not the sounds
static func display_press(st: Dictionary, press: int, confirm: int, cancel: int) -> bool:
	var v: Array = st["values"]
	var r := int(st["row"])
	if press & UP:
		st["row"] = 4 if r == 0 else r - 1
	elif press & DOWN:
		st["row"] = 0 if r == 4 else r + 1
	elif press & (confirm | RIGHT | LEFT):
		if r >= 2:
			v[r] = 1 if int(v[r]) < 1 else 0
		elif press & (confirm | RIGHT):
			v[r] = 2 if int(v[r]) == 0 else int(v[r]) - 1
		else:
			v[r] = 0 if int(v[r]) == 2 else int(v[r]) + 1
	elif press & cancel:
		return true
	return false


# panel_colours (0x8001f274): the menus' colours for the panel's switch (0x801b25e4) and the
# brightness (0x801b25e1) -- clear (1): boxes 0x78, the shadow 0x30, the text
# 0x80 plus half what the brightness is over 0x80; solid (0): boxes 0x57, the
# shadow 0x80, the text 0x30 less that half. The halving rounds toward zero.
# @orig game:0x8001f274 panel_colours  status:verified -- tools/ui.py panel_look, 20 of 20 colour sets as the game's own leaves gp+0x58..0x68 (display_check); the self-test this to it
static func panel_look(semi: int, bright: int) -> Dictionary:
	var d := bright - 0x80
	var half := -((-d) >> 1) if d < 0 else d >> 1
	if semi == 0:
		return {"box": 0x57, "text": 0x30 - half if bright >= 0x81 else 0x30, "shadow": 0x80}
	return {"box": 0x78, "text": half + 0x80, "shadow": 0x30}


# sub_80024a78: OPTION 1's three sliders -- the track (record 7) at (0xa5,
# 0x34) at depth 0x32, the knob (record 6, its u 16 on with the panel clear)
# at x 0xac + 96 * v / 128, y 0x3c, depth 0x31 -- 26 apart, in the boxes' grey.
# @orig game:0x80024a78 sub_80024a78  status:verified -- tools/ui.py sound_sliders, 48 of 48 frames of the game's own over menu1, half with the panel solid (sound_check); the self-test this to it
static func sound_sliders(o: Dictionary, lk: Dictionary, values: Array) -> void:
	var tr: Array = rec(RECORDS + 12 * 7)
	var kn: Array = rec(RECORDS + 12 * 6)
	set_tpage(o, 0x32, int(tr[0]))
	for i in 3:
		add(o, 0x32, sprite(0xA5, 0x34 + 0x1A * i, int(tr[4]), int(tr[5]), int(tr[2]),
			int(tr[3]), int(tr[1]), grey(int(lk["box"]))))
		add(o, 0x31, sprite(0xAC + ((96 * int(values[i])) >> 7), 0x3C + 0x1A * i, int(kn[4]),
			int(kn[5]), int(kn[2]) + (int(lk["semi"]) << 4), int(kn[3]), int(kn[1]),
			grey(int(lk["box"]))))


# @port helper -- the two calls of OPTION 1's frame (0x8001eefc): page 4's three lines and the sliders
static func sound_page(o: Dictionary, lk: Dictionary, values: Array, row: int) -> void:
	menu_page(o, lk, 4, 3, row, 1)
	sound_sliders(o, lk, values)


# One pad word on OPTION 1: UP and DOWN round the three rows; RIGHT moves the
# row's slider 3 on, to 0x80 at most; LEFT 3 back, to 0; the cancel leaves.
# The sound it plays and the music's volume it sets as they move are not here.
# @orig game:0x8001ec84 menu_sound  status:partial -- the pad, the sliders and the bytes stored, verified: tools/ui.py sound_press, 160 of 160 runs as the game's own runs them whole (sound_check); not the sounds or the music's volume
static func sound_press(st: Dictionary, press: int, cancel: int) -> bool:
	var v: Array = st["values"]
	var r := int(st["row"])
	if press & UP:
		st["row"] = 2 if r == 0 else r - 1
	elif press & DOWN:
		st["row"] = 0 if r == 2 else r + 1
	elif press & RIGHT:
		v[r] = mini((int(v[r]) + 3) & 0xFF, 0x80)
	elif press & LEFT:
		v[r] = int(v[r]) - 3 if int(v[r]) >= 3 else 0
	elif press & cancel:
		return true
	return false


# The MAGIC line's list (0x8001d0c4): the attacking spells 0..0x16 unlocked,
# their MP beside them in mode 4, and "TAKE OFF"; four rows from y 0x83, the
# selection on magic A.
# @orig game:0x8001d0c4 sub_8001d0c4  status:partial -- the list, its selection, the prompt and set_spell_a; not the guide (0x80024f88) or set_spell_a's sound bank
static func magic_list(table: PackedByteArray, st: Dictionary) -> Dictionary:
	var r := spell_rows(table, 0, 0x16)
	var names: Array = r["names"]
	var costs: Array = r["costs"]
	var ids: Array = r["ids"]
	names.append((data["equip"]["take_off"] as Array) + [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
	costs.append(-1)
	ids.append(0xFF)
	var out := {"tx": 0x1F, "ty": 0x20, "title": data["labels"][0][2][2], "x": 0x1B,
		"y": 0x83, "rows": 4, "length": 0x18, "count": ids.size(), "names": names,
		"costs": costs, "counts": [], "ids": ids, "sel": 0, "first": 0, "sel_row": 0}
	var sel := 0
	for i in ids.size() - 1:
		if int(ids[i]) == int(st["spell_a"]):
			sel = i
			break
	place(out, sel)
	return out


# The BUTTON line's list (0x8001d3a0): the things 0x65..0x92 carried, not
# 0x85, with their counts, then every spell unlocked with its MP, mode 0x10,
# then "TAKE OFF"; the selection on the button's spell or, with none, its
# thing.
# @orig game:0x8001d3a0 sub_8001d3a0  status:partial -- the list, its selection, the prompt, set_spell_b and set_button_item; not the thing's model (0x80025be8), the guide, or the sound banks
static func button_list(inv: PackedByteArray, table: PackedByteArray, st: Dictionary) -> Dictionary:
	var counted := inv.duplicate()
	counted[0x85] = 0
	var l := item_list(counted, 0x65, 0x92)
	var names: Array = l["names"]
	var counts: Array = l["counts"]
	counts.pop_back()
	var items: Array = l["ids"]
	var spells := []
	var costs := []
	for i in items.size():
		spells.append(0xFF)
		costs.append(-1)
	var r := spell_rows(table, 0, 0x1E)
	for i in (r["ids"] as Array).size():
		names.append(r["names"][i])
		counts.append(0xFF)
		costs.append(int(r["costs"][i]))
		spells.append(int(r["ids"][i]))
		items.append(0xFF)
	names.append((data["equip"]["take_off"] as Array) + [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
	counts.append(0xFF)
	costs.append(-1)
	spells.append(0xFF)
	items.append(0xFF)
	var out := {"tx": 0x1F, "ty": 0x20, "title": data["labels"][0][2][2], "x": 0x1B,
		"y": 0x93, "rows": 3, "length": 0x18, "count": items.size(), "names": names,
		"counts": counts, "costs": costs, "items": items, "spells": spells,
		"sel": 0, "first": 0, "sel_row": 0}
	var sel := 0
	if not (int(st["spell_b"]) == 0xFF and int(st["item_b"]) == 0xFF):
		for i in items.size():
			var hit: bool = (int(items[i]) == int(st["item_b"])) if int(st["spell_b"]) == 0xFF \
				else (int(spells[i]) == int(st["spell_b"]))
			if hit:
				sel = i
				break
	place(out, sel)
	return out


# The "use item" screen's 2D part, as tools/ui.py draws it.
# @orig game:0x8001aa84 menu_use_item  status:partial -- the list, its pad and the prompt; not the thing's model (0x80025be8), the maps and notes (95..100) or the guide
static func use_item_screen(lk: Dictionary, s: Dictionary) -> Dictionary:
	var o := {}
	panel(o, lk, s, 1)
	return o


# The prompt's two answers at the places ui_prompt keeps (0x8007e778,
# 0x8007e794), the kind's word and "cancel".
# @port helper -- ui_prompt's two labels handed to sub_80025b24
static func options(o: Dictionary, lk: Dictionary, sel: int, word: Array = USE_WORD) -> void:
	var one: Array = rec("0x8007e778")
	var two: Array = rec("0x8007e794")
	answers(o, lk, [int(one[0]), int(one[1]), word], [int(two[0]), int(two[1]), CANCEL_WORD], sel)


# sub_80025b24 (one, two, sel): two answers [x, y, glyphs] on plates
# (record 1), the chosen one lit.
# @orig game:0x80025b24 sub_80025b24  status:verified -- through tools/ui.py, the prompts' frames, and QUIT GAME's 8 of 8 of the game's own (quit_check)
static func answers(o: Dictionary, lk: Dictionary, one: Array, two: Array, sel: int) -> void:
	var r: Array = rec(RECORDS + 12 * 1)
	var style: Array = rec(LABEL_STYLE)
	if sel == 0:
		lit_plate(o, lk, r, int(one[0]), int(one[1]))
		label_plate(o, lk, r, int(two[0]), int(two[1]))
		draw_label(o, lk, style, int(one[0]), int(one[1]), one[2])
		dim_label(o, lk, style, int(two[0]), int(two[1]), two[2])
	else:
		label_plate(o, lk, r, int(one[0]), int(one[1]))
		lit_plate(o, lk, r, int(two[0]), int(two[1]))
		dim_label(o, lk, style, int(one[0]), int(one[1]), one[2])
		draw_label(o, lk, style, int(two[0]), int(two[1]), two[2])


# QUIT GAME's answers, immediates in its code
const QUIT_YES := [0xAB, 0xA2, [0x18, 0x04, 0x12, 0xFF]]
const QUIT_NO := [0xE5, 0xA2, [0x0D, 0x0E, 0xFF]]


# @port helper -- QUIT GAME's frame (0x8001fa0c): the system page, its last line lit, and the two answers
static func quit_page(o: Dictionary, lk: Dictionary, sel: int) -> void:
	menu_page(o, lk, 3, 5, 4, 0)
	answers(o, lk, QUIT_YES, QUIT_NO, sel)


# One pad word on QUIT GAME: any of the four directions turns between the
# answers; the confirm answers 0 on "yes" (and sets overlay_arg to 1), -1 on
# "no"; the cancel -1. [sel, the answer or null]; it starts on "no", 1.
# @orig game:0x8001f8b4 menu_quit  status:verified -- tools/ui.py quit_press, 100 of 100 runs as the game's own runs it whole (quit_check); the self-test this to it; not the sounds
static func quit_press(sel: int, press: int, confirm: int, cancel: int) -> Array:
	if press & (UP | DOWN | LEFT | RIGHT):
		return [1 - sel, null]
	if press & confirm:
		return [sel, 0 if sel == 0 else -1]
	if press & cancel:
		return [sel, -1]
	return [sel, null]


# sub_800252f4: a page of the menu's lines on their plates, the chosen one lit,
# and the two-button legend. Page 0 is the menu itself, with no title.
# The legend by the fourth argument (0x800253c4): 0 the confirm button at
# 0x5f, 1 button 9 at 0x5b (OPTION 1 and 2), anything else none (no caller
# passes one); "select", then the cancel button and "return", each time.
# @orig game:0x800252f4 sub_800252f4  status:transcribed
static func menu_page(o: Dictionary, lk: Dictionary, page: int, n: int, sel: int,
		legend_mode := 0) -> void:
	var style: Array = rec(LABEL_STYLE)
	var plate: Array = rec(RECORDS + 12 * 2)
	var title: Array = data["page_minus"] if page == 0 else data["labels"][page - 1][8]
	if page != 0 and int(title[0]) != 0:
		label_plate(o, lk, plate, int(title[0]), int(title[1]))
		draw_label(o, lk, style, int(title[0]), int(title[1]), title[2])
	for i in n:
		var line: Array = data["labels"][page][i]
		var x := int(line[0])
		var y := int(line[1])
		if i == sel:
			lit_plate(o, lk, plate, x, y)
			draw_label(o, lk, style, x, y, line[2])
		else:
			label_plate(o, lk, plate, x, y)
			dim_label(o, lk, style, x, y, line[2])
	if legend_mode == 0:
		legend(o, lk, true)
		return
	if legend_mode == 1:
		button(o, lk, 0x5B, 0xD6, 9)
	small_text(o, lk, 0x69, 0xD6, data["words"]["select"])
	button(o, lk, 0xA0, 0xD6, int(lk["cancel"]))
	small_text(o, lk, 0xAA, 0xD6, data["words"]["return"])


# ui_status_page (0x800227ec), behind the main page every frame: experience,
# level, HP and MP over their maxima, the effective stat and 0x801b2530 + 1,
# the five working skills under their icons -- light, fire, earth, wind,
# water -- the condition and the gold, in a frame. Two records on the stack
# carry it, a label's (x, y, glyphs) and a number's, each moved and
# overwritten in place as the routine goes; `ps` holds the values.
# @orig game:0x800227ec ui_status_page  status:verified -- as tools/ui.py draws it, which is the game's frame: 2 of 2 buffers of menu1, 428 primitives each
static func status_page(o: Dictionary, lk: Dictionary, ps: Dictionary) -> void:
	var style: Array = rec(LABEL_STYLE)
	var nstyle: Array = rec(NUMBER_STYLE)
	var words: Dictionary = data["status"]["labels"]
	var lx := 0xA3
	var ly := 0x24
	var lg: Array = (words["experience"] as Array).duplicate()
	draw_label(o, lk, style, lx, ly, lg)
	var nx := lx + 0x4D
	var ny := ly
	draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps["exp"]), 7, 0, 0))
	ly += 0x11
	_put(lg, words["level"])
	draw_label(o, lk, style, lx, ly, lg)
	ny += 0x11
	draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps["level"]), 7, 0, 0))
	for which in ["hp", "mp"]:
		if which == "hp":
			_put(lg, [0x07, 0x0F, 0xFF])                 # "HP"
		else:
			lg[0] = 0x0C                                # and "MP" off it
		ly += 0x11
		draw_label(o, lk, style, lx, ly, lg)
		nx = lx + 0x3F
		ny += 0x11
		draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps[which]), 4, 0, 0))
		nx += 0x1C
		draw_number(o, lk, nstyle, nx, ny, [0x14, 0xFF])            # the stroke
		nx += 7
		draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps[which + "_max"]), 4, 0, 0))
	_put(lg, [0x0F, 0x16, 0x11, 0x3B, 0x16, 0x08, 0x12, 0xFF])
	ly += 0x11
	draw_label(o, lk, style, lx, ly, lg)
	nx = lx + 0x46
	ny = ly
	draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps["stat"]), 5, 0, 0))
	nx = lx + 0x62
	draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps["wis"]) + 1, 4, 0, 0))
	_put(lg, [0x3B, 0xFF])
	lx += 0x69
	draw_label(o, lk, style, lx, ly, lg)
	lx = 0xA3
	_put(lg, [0x0C, 0x00, 0x06, 0xFF])
	ly += 0x11
	draw_label(o, lk, style, lx, ly, lg)
	lx += 0x23
	for i in SKILL_ICONS.size():
		var ic: Array = SKILL_ICONS[i]
		if i == 2 or i == 4:
			lx = 0xC6
			ly += 0xF
		elif i > 0:
			lx += 0x31
		add(o, ICON_DEPTH, quad(lx, ly - 1, ICON_SIZE, ICON_SIZE, int(ic[1]), ICON_V,
			ICON_SIZE, ICON_SIZE, ICON_PAGE, int(ic[2]), grey(0x80), 0))
		nx = lx
		ny = ly
		draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps["working"][int(ic[0])]), 6, 0, 0))
	lx = 0xA3
	ly += 0x11
	_put(lg, words["condition"])
	draw_label(o, lk, style, lx, ly, lg)
	nx = lx + 0x38
	ny += 0x11
	var text: Array = []
	for c in data["status"]["conditions"]:
		if str(c[0]) == "" or int(ps.get(str(c[0]), 0)) != 0:
			text = c[1]
			break
	draw_label(o, lk, style, nx, ny, text)
	ly += 0x11
	_put(lg, words["gold"])
	draw_label(o, lk, style, lx, ly, lg)
	nx = lx + 0x4D
	ny += 0x11
	draw_number(o, lk, nstyle, nx, ny, number_digits(int(ps["gold"]), 7, 0, 0))
	frame(o, lk, 0x9B, 0x1A, 0x8D, 0xB4)


# ui_ratings_page (0x80023300), under status/records' first line: OFFENSE at
# (30, 34) and its eight ratings below it 16 apart, DEFENSE at (164, 34) and
# its nine halves 17 apart -- the ninth, the poison resistance (0x801b255a),
# fourth -- each number in six digits 0x4d right of its label; the frame
# (20, 26, 276, 180) round them, and "return" under it. tools/mipsrun.py runs
# the routine itself over a snapshot's RAM for the self-test's cases.
# @orig game:0x80023300 ui_ratings_page  status:verified -- the game's own code run over menu1's RAM draws what this draws, four sets of ratings (tools/mipsrun.py)
static func ratings_page(o: Dictionary, lk: Dictionary, off: Array, dfn: Array) -> void:
	var style: Array = rec(LABEL_STYLE)
	var nstyle: Array = rec(NUMBER_STYLE)
	var words: Dictionary = data["ratings"]
	var sides := [
		[30, 34, 16, 50, words["offense"], [
			[R_SLASH, 0], [R_BLOW, 1], [R_STAB, 2], [R_HOLY + MAGIC, 3],
			[R_FIRE + MAGIC, 4], [R_EARTH + MAGIC, 5], [R_WIND + MAGIC, 6],
			[R_WATER + MAGIC, 7]], off],
		[164, 34, 17, 51, words["defense"], [
			[R_SLASH, 0], [R_BLOW, 1], [R_STAB, 2], [R_POISON, 8],
			[R_DARK + MAGIC, 3], [R_FIRE + MAGIC, 4], [R_EARTH + MAGIC, 5],
			[R_WIND + MAGIC, 6], [R_WATER + MAGIC, 7]], dfn],
	]
	for side in sides:
		var x := int(side[0])
		draw_label(o, lk, style, x, int(side[1]), side[4])
		var y := int(side[3])
		for line in side[5]:
			draw_label(o, lk, style, x, y, SP2 + line[0] + [0xFF])
			var v: Array = side[6]
			var k := int(line[1])
			draw_number(o, lk, nstyle, x + 0x4D, y,
				number_digits(int(v[k]) if k < v.size() else 0, 6, 0, 0))
			y += int(side[2])
	frame(o, lk, 20, 26, 276, 180)
	button(o, lk, 128, 214, int(lk["cancel"]))
	small_text(o, lk, 138, 214, data["words"]["return"])


# @port helper -- bytes copied over the front of a record on the stack, as lwl/lwr and sb do
static func _put(dst: Array, src: Array) -> void:
	for i in src.size():
		dst[i] = int(src[i])


# @port helper -- the ordering table in the order the GPU draws it, each sprite with its page
static func order(o: Dictionary) -> Array:
	var depths := o.keys()
	depths.sort()
	depths.reverse()
	var out := []
	var tp = null
	for d in depths:
		var lst: Array = o[d]
		for i in range(lst.size() - 1, -1, -1):
			var p: Dictionary = lst[i]
			if p["kind"] == "tpage":
				tp = p["tpage"]
				continue
			var q := p.duplicate()
			if q["kind"] == "sprite":
				q["tpage"] = tp
			out.append([d, q])
	return out


# -- the menu's flow ----------------------------------------------------------

# @port engine -- the menu button opens it; its own frames at 15 a second while it is up
func _process(dt: float) -> void:
	if data.is_empty() or player == null:
		return
	if state == "":
		if KFPad.hit(KFPad.MENU_SLOT) and not KFGame.modal and _may_open():
			_open()
		return
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / FRAME_HZ and state != "":
		acc -= 1.0 / FRAME_HZ
		pulse_step()
		frames += 1
		if frames & 1 == 0:
			_step(latch)
			latch = 0
	latch |= KFPad.now & ~KFPad.prev
	_build()
	queue_redraw()


# frame_begin (0x80026fe4): the chosen row's pulse goes round 0..0x5f, one a
# frame, and starts again from 0x30 when the choice has just moved (gp+0x54);
# the second (gp+0x50) goes round beside it and is never put back.
# @orig game:0x80027090 frame_begin+0xac  status:transcribed
func pulse_step() -> void:
	look["pulse"] = (int(look["pulse"]) + 1) % 0x60
	look["pulse2"] = (int(look["pulse2"]) + 1) % 0x60
	if moved:
		look["pulse"] = 0x30
		moved = false


# sub_800305d8: the menu button, newly down, with no swing under way and the
# player not dying.
# @orig game:0x80030640 sub_800305d8+0x68  status:transcribed
func _may_open() -> bool:
	return int(player.wstate["clock"]) == -1 and int(player.pstate) != 0x11


# pause_menu's start (0x80027198 and its first frames): the world held, the
# main page up.
# @orig game:0x8001a774 pause_menu  status:partial -- the six lines, the status page behind them, "use item", "use magic", "equipment", "status/records", "storage" and "system" (all of its five but LOAD)
func _open() -> void:
	KFGame.modal = true
	state = "main"
	visible = true
	acc = 0.0
	KFInfo.note("menu: open")


# QUIT GAME answered "yes": overlay_arg 1, menu_system's -2, pause_menu's,
# sub_800305d8's game state 2, and game_main's arm for it -- next_exe 0, back
# to the shell, which runs OPEN.EXE; open_main, seeing overlay_arg 1, goes
# straight to the title. The "please wait" and the music's fade between
# (menu_system's tail, sub_8001eb3c) are not here.
# @orig game:0x80015034 game_main+0x460  status:transcribed -- state 2: next_exe 0, and back to the shell
func _quit() -> void:
	KFInfo.note("menu: quit game")
	_close()
	var shell = load("res://boot.gd")
	shell.next_exe = shell.OPEN
	shell.overlay_arg = 1
	get_tree().change_scene_to_file("res://boot.tscn")


# @port helper -- the menu closed, the world going again
func _close() -> void:
	state = ""
	visible = false
	KFGame.modal = false
	player.clear_movement()
	KFInfo.note("menu: closed")


# One frame of whichever screen is up, on the buttons newly down.
# @orig game:0x800221e8 sub_800221e8  status:transcribed -- the main page's choice: up and down round the six, the confirm and the cancel
# @orig game:0x800222fc ui_menu_chrome  status:partial -- the list's up and down, the confirm and the cancel, for the lists _step runs itself (the storage's go through chrome_pad, which has the quantity); not the model's turning
# @orig game:0x80024c70 ui_prompt  status:partial -- kind 0, "use" and "cancel"
# @orig game:0x8001d784 menu_records  status:partial -- status/records' two lines; CONVERSATION (text_pager) not here
# @orig game:0x8001d8a4 menu_ratings  status:transcribed -- the ratings page until a button is pressed
# @orig game:0x8001c540 menu_use_magic+0xb4  status:transcribed -- its loop: the chrome, the cursor into gp+0x19, ui_prompt(s, 0, 2, 0xff) and the spell handed back; not the guide (TRIANGLE, 0x80024f88) or the sounds
# @orig game:0x8001dd94 item_menu  status:transcribed -- the storage's page: sub_800221e8 over page 2's two lines, a list for each, the cancel back to the main page
# @orig game:0x8001e484 menu_system  status:partial -- the page: sub_800221e8 over page 3's five lines, OPTION 1, OPTION 2, BUTTON CONFIG and QUIT GAME, the cancel back to the main page; not LOAD (sub_8001e710), or QUIT GAME's "please wait" (0x8001e620)
func _step(press: int) -> void:
	var confirm := 0x40 if int(look["confirm"]) == 3 else 0x20
	var cancel := 0x20 if int(look["confirm"]) == 3 else 0x40
	match state:
		"main":
			if press & UP:
				main_sel = 5 if main_sel == 0 else main_sel - 1
				moved = true
			elif press & DOWN:
				main_sel = 0 if main_sel == 5 else main_sel + 1
				moved = true
			elif press & confirm:
				if main_sel == 0:
					list = use_item_list(player.inventory.a, int(list.get("sel", 0)))
					state = "use_item"
				elif main_sel == 1:
					spells = use_magic_list(_spell_table(), magic_cursor)
					state = "use_magic"
				elif main_sel == 2:
					equip_sel = 0                       # ui_menu_label's 0
					state = "equip"
				elif main_sel == 3:
					records_sel = 0
					state = "records"
				elif main_sel == 4:
					storage_sel = 0
					state = "storage"
				elif main_sel == 5:
					system_sel = 0
					state = "system"
				else:
					KFInfo.note("menu: line %d is not ported yet" % main_sel)
			elif press & cancel:
				_close()
		"use_item":
			var n := int(list["count"])
			if n == 0:
				if press != 0:                  # ui_menu_chrome: an empty list goes at any button
					state = "main"
			elif press & (UP | DOWN):
				chrome_move(list, press)
			elif press & confirm and n > 0:
				prompt_sel = 0
				state = "prompt"
			elif press & cancel:
				state = "main"
		"prompt":
			if press & (UP | DOWN):
				prompt_sel = 1 - prompt_sel
				moved = true
			elif press & confirm:
				if prompt_sel == 0:
					_use(int(list["ids"][int(list["sel"])]))
				else:
					state = "use_item"
			elif press & cancel:
				state = "use_item"
		"use_magic":
			# menu_use_magic's loop: ui_menu_chrome on the list -- an empty one
			# goes at any button -- the cursor back into gp+0x19 after it
			var n := int(spells["count"])
			if n == 0:
				if press != 0:
					state = "main"
			elif press & (UP | DOWN):
				chrome_move(spells, press)
				magic_cursor = int(spells["sel"])
			elif press & confirm:
				prompt_sel = 0
				state = "use_magic_prompt"
			elif press & cancel:
				state = "main"
		"use_magic_prompt":
			# ui_prompt(s, 0, 2, 0xff): "USE" hands the spell back to pause_menu,
			# which closes the menu and casts it; "CANCEL" goes back to the list
			if press & (UP | DOWN):
				prompt_sel = 1 - prompt_sel
				moved = true
			elif press & confirm and prompt_sel == 0:
				var spell := int(spells["ids"][int(spells["sel"])])
				KFInfo.note("menu: use magic %d" % spell)
				player.cast_from_menu(spell)
				_close()
			elif press & (confirm | cancel):
				state = "use_magic"
		"records":
			# sub_8001d784: sub_800221e8 over page 1's two lines
			if press & UP:
				records_sel = 1 if records_sel == 0 else records_sel - 1
				moved = true
			elif press & DOWN:
				records_sel = 0 if records_sel == 1 else records_sel + 1
				moved = true
			elif press & confirm:
				if records_sel == 0:
					state = "ratings"
				else:
					KFInfo.note("menu: the conversations' record is not ported yet")
			elif press & cancel:
				state = "main"
		"storage":
			# item_menu: sub_800221e8 over page 2's two lines
			if press & UP:
				storage_sel = 1 if storage_sel == 0 else storage_sel - 1
				moved = true
			elif press & DOWN:
				storage_sel = 0 if storage_sel == 1 else storage_sel + 1
				moved = true
			elif press & confirm:
				var inv: KFItems = player.inventory
				stash = storage_list(storage_sel, inv.b if storage_sel == 1 else inv.a,
					_equip_state(), int(stash_cursor[storage_sel]))
				state = "storage_list"
			elif press & cancel:
				state = "main"
		"storage_list":
			var inv: KFItems = player.inventory
			var was := int(stash["prompt"])
			var end := storage_press(stash, press, inv.a, inv.b, confirm, cancel)
			if int(stash["mode"]) == 1 and int(stash["prompt"]) != was:
				moved = true
			stash_cursor[storage_sel] = int(stash["sel"])        # gp+0x1a, gp+0x1b
			if end == -1:
				state = "storage"
			elif end != -0x63:
				KFInfo.note("menu: %d of %d %s" % [int(stash["qty"]), end,
					"stored" if storage_sel == 0 else "taken out"])
				state = "storage"
		"system":
			# menu_system: sub_800221e8 over page 3's five lines
			if press & UP:
				system_sel = 4 if system_sel == 0 else system_sel - 1
				moved = true
			elif press & DOWN:
				system_sel = 0 if system_sel == 4 else system_sel + 1
				moved = true
			elif press & confirm:
				if system_sel == 3:
					config = {"action": KFPad.action_type, "move": KFPad.move_type, "row": 0}
					state = "button_config"
				elif system_sel == 2:
					display = {"values": KFGame.display.duplicate(), "row": 0}
					state = "display"
				elif system_sel == 4:
					quit_sel = 1
					state = "quit"
				elif system_sel == 1:
					# menu_sound's start: the music's byte one on unless 0, the
					# brightness's 0xc0 on
					var b: Array = KFGame.sound
					sound = {"values": [int(b[0]), 0 if int(b[1]) == 0 else int(b[1]) + 1,
						(int(b[2]) + 0xC0) & 0xFF], "row": 0}
					state = "sound"
				else:
					KFInfo.note("menu: the system's line %d is not ported yet" % system_sel)
			elif press & cancel:
				state = "main"
		"display":
			var was := int(display["row"])
			if display_press(display, press, confirm, cancel):
				# menu_display's end: the five stored, and panel_colours
				KFGame.display = (display["values"] as Array).duplicate()
				var semi := int(KFGame.display[4])
				look.merge(panel_look(semi, int(look["bright"])), true)
				look["semi"] = semi
				KFInfo.note("menu: display %s" % str(KFGame.display))
				state = "system"
			elif int(display["row"]) != was:
				moved = true
		"sound":
			var was := int(sound["row"])
			if sound_press(sound, press, cancel):
				# menu_sound's end: the three stored, and with the panel clear
				# the text from the brightness
				var v: Array = sound["values"]
				KFGame.sound = [int(v[0]), 0 if int(v[1]) == 0 else int(v[1]) - 1,
					(int(v[2]) + 0x40) & 0xFF]
				look["bright"] = int(KFGame.sound[2])
				if int(look["semi"]) == 1:
					look["text"] = int(panel_look(1, int(look["bright"]))["text"])
				KFInfo.note("menu: sound %s" % str(KFGame.sound))
				state = "system"
			elif int(sound["row"]) != was:
				moved = true
		"quit":
			var q := quit_press(quit_sel, press, confirm, cancel)
			if int(q[0]) != quit_sel:
				moved = true
			quit_sel = int(q[0])
			if q[1] != null:
				if int(q[1]) == 0:
					_quit()
				else:
					state = "system"
		"button_config":
			if button_config_press(config, press, cancel):
				KFPad.apply(int(config["move"]), int(config["action"]))
				KFInfo.note("menu: control type %d, movement type %d" % [int(config["action"]),
					int(config["move"])])
				state = "system"
		"ratings":
			# sub_8001d8a4: the page until any button is pressed
			if press != 0:
				state = "records"
		"equip":
			var s := equipment_list(_equip_state(), equip_sel)
			if press & (UP | DOWN):
				chrome_move(s, press)
				equip_sel = int(s["sel"])
			elif press & confirm:
				if EQUIP_RANGES.has(equip_sel):
					chooser = equip_list(player.inventory.a, equip_sel, _equip_state())
					state = "equip_list"
				elif equip_sel == 1:
					chooser = magic_list(_spell_table(), _equip_state())
					state = "magic_list"
				elif equip_sel == 9:
					chooser = button_list(player.inventory.a, _spell_table(), _equip_state())
					state = "button_list"
				else:
					KFInfo.note("menu: the equipment's line %d is not ported yet" % equip_sel)
			elif press & cancel:
				state = "main"
		"equip_list":
			if press & (UP | DOWN):
				chrome_move(chooser, press)
			elif press & confirm:
				prompt_sel = 0
				state = "equip_prompt"
			elif press & cancel:
				state = "equip"
		"magic_list", "button_list":
			if press & (UP | DOWN):
				chrome_move(chooser, press)
			elif press & confirm:
				prompt_sel = 0
				state = "magic_prompt" if state == "magic_list" else "button_prompt"
			elif press & cancel:
				state = "equip"
		"magic_prompt", "button_prompt":
			# ui_prompt(s, 5, 4 or 0x10, ...): "USE" puts the choice in its slot and
			# closes the page; "CANCEL" goes back to the list
			var back := "magic_list" if state == "magic_prompt" else "button_list"
			if press & (UP | DOWN):
				prompt_sel = 1 - prompt_sel
				moved = true
			elif press & confirm and prompt_sel == 0:
				var k := int(chooser["sel"])
				if state == "magic_prompt":
					player.spell_a = int(chooser["ids"][k])            # set_spell_a
				else:
					_set_button(int(chooser["spells"][k]), int(chooser["items"][k]))
				state = "equip"
			elif press & (confirm | cancel):
				state = back
		"equip_prompt":
			# ui_prompt(s, 5, 5, id): "USE" or "CANCEL"; either way back to the list
			# unless it was used
			if press & (UP | DOWN):
				prompt_sel = 1 - prompt_sel
				moved = true
			elif press & confirm and prompt_sel == 0:
				_equip(int(chooser["line"]), int(chooser["ids"][int(chooser["sel"])]))
				state = "equip"
			elif press & (confirm | cancel):
				state = "equip_list"


# The thing chosen: 104..120 are eaten (item_consume), then the menu closes
# and use_item runs, whose last word is the level's entry 2 and, if nothing
# has answered, "Nothing Happens".
# @orig game:0x8001b254 item_consume  status:transcribed
# @orig game:0x8005d748 use_item+0xb68  status:partial -- the tail: the level's entry 2 not called (level 0's is empty, 0x801e8704; level 4's answers item 0x7b alone); the eaten things, the keys (loot.gd try_key, put_key) and the arms that raise a figure (levelup.gd use_arm) answer, the rest say "Nothing Happens"
func _use(id: int) -> void:
	var inv: KFItems = player.inventory
	var eaten := false
	if id >= 0x68 and id <= 0x78 and not (id == 0x6E or (id >= 0x71 and id <= 0x76)) \
			and int(inv.a[id]) != 0:
		eaten = true
		match id:
			0x68:
				player.hp += 0x32
			0x69:
				player.poison = 0
				player.hp += 0xF
			0x6A:
				player.hp = player.hp_max
			0x6B:
				player.hp = player.hp_max
				player.mp = int(player.character.get("mp_max", player.mp))
			0x6C:                                       # the blood stone (0x8001b350)
				if int(player.caps["paralysis"]) > 0:
					player.caps["paralysis"] = 0
				if int(player.caps["slow"]) >= 0x41:
					player.caps["slow"] = 0x40
			0x6D:
				player.mp += 0x28
				player.mp = mini(player.mp, int(player.character.get("mp_max", player.mp)))
			0x77:
				player.hp += 0x64
			0x78:
				player.hp += 0xC8
				player.mp = mini(player.mp + 0x64, int(player.character.get("mp_max", player.mp + 0x64)))
		player.hp = mini(player.hp, player.hp_max)
		inv.a[id] = int(inv.a[id]) - 1
		if id == 0x77 or id == 0x78:
			inv.a[0x76] = int(inv.a[0x76]) + 1       # the crystal flask back
	KFInfo.note("use: item %d%s" % [id, " eaten" if eaten else ""])
	_close()
	var answered := eaten
	if id >= KFLevels.VERDITE and id < KFLevels.FIRST_CRYSTAL + 5:
		# use_item's arms that raise a figure, then player_recalc_stats
		var r := KFLevels.use_arm(id, player.character, KFTalk.flags)
		if bool(r["took"]):
			inv.take_item(id)
		for b in r["banners"]:
			KFMessages.announce(int(b))
		player.recalc_stats()
		answered = bool(r["answered"])
		KFInfo.note("use: item %d -- skills %s, stat 36 %d, 0x801b2530 %d" % [id,
			str(player.character["grow"]), int(player.character["stat36"]),
			int(player.character.get("wis", 0))])
	if id in KEYS:
		var lt := get_node_or_null("../../Loot")
		if lt and int(lt.try_key(id)) != 0:
			answered = true
	elif id == SILVIERA_KEY:
		var lt := get_node_or_null("../../Loot")
		if lt and int(lt.put_key(id)) != 0:
			answered = true
	if not answered:
		KFMessages.announce(NOTHING_HAPPENS)


# The BUTTON page's end (0x8001d734): set_spell_b with the row's spell, then
# set_button_item with its thing -- either clears the other when it puts
# one, so a spell's row leaves no thing and a thing's no spell.
# @orig game:0x8002ba38 set_spell_b  status:partial -- the slot and the thing cleared; not the spell's sound bank
# @orig game:0x8002bb5c set_button_item  status:transcribed -- the slot, and the spell cleared with one
func _set_button(spell: int, item: int) -> void:
	player.spell_b = spell
	if spell != 0xFF:
		player.item_b = 0xFF
	player.item_b = item
	if item != 0xFF:
		player.spell_b = 0xFF


# @port helper -- spell_table's 96 records as the lists read them: +0 the unlocked flag off the character
func _spell_table() -> PackedByteArray:
	var t := PackedByteArray()
	t.resize(96 * 24)
	var fx := get_node_or_null("../../Effects")
	var recs: Dictionary = fx.get("records") if fx and fx.get("records") != null else {}
	var unlocked: Array = player.character.get("spells", [])
	for k in 96:
		var r: PackedByteArray = recs.get(k, PackedByteArray())
		for i in mini(r.size(), 24):
			t[24 * k + i] = r[i]
		t[24 * k] = int(unlocked[k]) if k < unlocked.size() else 0
	return t


# @port helper -- the slots equip_names reads, out of the player
func _equip_state() -> Dictionary:
	return {"weapon": player.weapon_id, "spell_a": player.spell_a,
		"spell_b": player.spell_b, "item_b": player.item_b, "worn": player.worn}


# ui_equip_page's end (0x8001cfa0): the line's slot gets the choice --
# equip_weapon for the weapon, equip_armour for the rest; "TAKE OFF" is 0xff.
# @orig game:0x8001cfa0 ui_equip_page+0x3e8  status:transcribed
func _equip(line: int, id: int) -> void:
	if line == 0:
		player.equip_weapon(id)
	elif ARMOUR_SLOT.has(line):
		player.equip_armour(id, int(ARMOUR_SLOT[line]))


# @port helper -- what ui_status_page reads, out of the player: the paralysis, the curse, the slowing and the dark are not in the port
func _status() -> Dictionary:
	var ch: Dictionary = player.character
	return {"exp": int(ch.get("exp", 0)), "level": int(ch.get("level", 1)),
		"hp": player.hp, "hp_max": player.hp_max, "mp": player.mp,
		"mp_max": int(ch.get("mp_max", player.mp)), "stat": player.stat,
		"wis": int(ch.get("wis", 0)), "working": player.working,
		"poison": player.poison, "gold": player.gold}


# @port engine -- the screen up now, as primitives
func _build() -> void:
	ot = {}
	match state:
		"main":
			status_page(ot, look, _status())
			menu_page(ot, look, 0, 6, main_sel)
		"use_item":
			panel(ot, look, list, 1)
		"prompt":
			panel(ot, look, list, 1 | 0x8000)
			options(ot, look, prompt_sel)
		"use_magic":
			panel(ot, look, spells, 2)
		"use_magic_prompt":
			panel(ot, look, spells, 2 | 0x8000)
			options(ot, look, prompt_sel)
		"records":
			menu_page(ot, look, 1, 2, records_sel)
		"storage":
			menu_page(ot, look, 2, 2, storage_sel)
		"system":
			menu_page(ot, look, 3, 5, system_sel)
		"button_config":
			options_page(ot, look, int(config["action"]), int(config["move"]), int(config["row"]))
		"display":
			display_page(ot, look, display["values"], int(display["row"]))
		"sound":
			sound_page(ot, look, sound["values"], int(sound["row"]))
		"quit":
			quit_page(ot, look, quit_sel)
		"storage_list":
			if int(stash["mode"]) == 1:
				panel(ot, look, stash, 7 | 0x8000)
				options(ot, look, int(stash["prompt"]), MOVE_WORD if storage_sel == 1 else STORE_WORD)
			else:
				panel(ot, look, stash, 7)
		"ratings":
			ratings_page(ot, look, player.offense, player.defence + [player.resist])
		"equip":
			panel(ot, look, equipment_list(_equip_state(), equip_sel), 3)
		"equip_list":
			panel(ot, look, chooser, 5)
		"equip_prompt":
			panel(ot, look, chooser, 5 | 0x8000)
			options(ot, look, prompt_sel)
		"magic_list":
			panel(ot, look, chooser, 4)
		"magic_prompt":
			panel(ot, look, chooser, 4 | 0x8000)
			options(ot, look, prompt_sel)
		"button_list":
			panel(ot, look, chooser, 0x10)
		"button_prompt":
			panel(ot, look, chooser, 0x10 | 0x8000)
			options(ot, look, prompt_sel)


# The primitives, in the order the GPU draws them: sprites and quads out of the
# pages, coloured as the GPU colours a texel (x / 0x80), a semi-transparent
# quad's STP texels half and half with what is under them.
# @port engine -- the GPU's drawing of SPRT and POLY_FT4, on a 320 x 240 screen centred in the window
func _draw() -> void:
	if state == "":
		return
	var vs := get_viewport_rect().size
	var k := vs.y / SCREEN_H
	var left := (vs.x - SCREEN_W * k) * 0.5
	for e in order(ot):
		var p: Dictionary = e[1]
		var key := "%d_%04x" % [int(p.get("tpage", 0)) & 0x7FF, int(p["clut"])]
		if not tex.has(key):
			continue
		var c := int(p["rgb"])
		var col := Color(float(c & 0xFF) / 128.0, float((c >> 8) & 0xFF) / 128.0,
			float((c >> 16) & 0xFF) / 128.0, 1.0)
		var pair: Array = tex[key]
		if p["kind"] == "sprite":
			var dst := Rect2(left + int(p["x"]) * k, int(p["y"]) * k, int(p["w"]) * k, int(p["h"]) * k)
			var src := Rect2(int(p["u"]), int(p["v"]), int(p["w"]), int(p["h"]))
			for t in pair:
				if t:
					draw_texture_rect_region(t, dst, src, col)
		else:
			var pts := PackedVector2Array()
			var uvs := PackedVector2Array()
			if int(p["pts"][0][1]) == int(p["pts"][2][1]) or int(p["pts"][0][0]) == int(p["pts"][1][0]):
				continue                                # no area: the GPU draws nothing either
			for i in [0, 1, 3, 2]:
				pts.append(Vector2(left + int(p["pts"][i][0]) * k, int(p["pts"][i][1]) * k))
				uvs.append(Vector2(int(p["uvs"][i][0]), int(p["uvs"][i][1])) / 256.0)
			if pair[0]:
				draw_polygon(pts, PackedColorArray([col, col, col, col]), uvs, pair[0])
			if pair[1]:
				var c2 := col
				if bool(p["semi"]):
					c2.a = 0.5
				draw_polygon(pts, PackedColorArray([c2, c2, c2, c2]), uvs, pair[1])

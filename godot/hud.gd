extends Control
# The panel in the top-left corner: HP and MP, and the weapon and magic meters.
#
# Thirty sprites in GAME.EXE's table at 0x800819b4 (tools/hud.py reads it into
# hud.json): each a rectangle of the 4-bit page at (896, 256) under a CLUT, put
# at a place on the 320x240 screen by sub_80041ad4 as a semi-transparent SPRT.
# render_frame switches records 15-29 on for style 2 -- the default a new
# character gets -- and writes the numbers into them every frame:
#
#   records 17-19, 22-24   u = 12 * digit + 128, HP and MP each % 1000
#   records 25, 26         w = meter * 64 / 5000, the weapon and magic meters
#
# The draw order is the ordering table's: the larger depth first (40, the
# panel's back, then 32, then 24), and within one depth the later record first,
# because each goes in at the head of its entry's list. A semi-transparent
# SPRT blends only the texels whose colour has STP set -- at the page rate the
# record's +1 picks, 0 mixing half and half and 3 adding a quarter -- and draws
# the rest solid, so each sprite is two rectangles here: its solid texels, and
# its STP texels with the blend. The colour is the brightness byte, 0x80, which
# leaves the texels as they are.
# @orig game:0x80041ad4  status:transcribed -- one panel sprite: SPRT, DR_TPAGE, the record's place in the ordering table
# @orig game:0x80041e68  status:transcribed -- the walk over hud_sprites

const SCREEN_H := 240.0
const PANEL_BOTTOM := 62.0        # the lowest row the style-2 sprites cover, 12 + 48 + 2
const BLEND := [CanvasItemMaterial.BLEND_MODE_MIX, CanvasItemMaterial.BLEND_MODE_ADD,
	CanvasItemMaterial.BLEND_MODE_SUB, CanvasItemMaterial.BLEND_MODE_ADD]

var style := 2                    # 0x801b25dd
var player: Node
var sprites := {}                 # index -> the record
var rects := {}                   # index -> [solid TextureRect, semi TextureRect]
var shown_scale := -1.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	player = get_node_or_null("../../Player")
	var path := "res://hud.json"
	if not FileAccess.file_exists(path):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return
	var on := {}
	for k in (d["style2"] if style == 2 else d["style1"]):
		on[int(k)] = true
	var order := []
	for s in d["sprites"]:
		if on.has(int(s["index"])):
			order.append(s)
	order.sort_custom(func(a, b):
		if int(a["depth"]) != int(b["depth"]):
			return int(a["depth"]) > int(b["depth"])
		return int(a["index"]) > int(b["index"]))
	for s in order:
		var k := int(s["index"])
		sprites[k] = s
		var rate: int = (int(s["abr"]) & 3) if int(s["abr"]) != 0xFF else 0
		var pair := []
		for part in ["_solid", "_semi"]:
			var tex = load("res://%s%s.png" % [s["png"], part])
			if tex == null:
				continue
			var r := TextureRect.new()
			var at := AtlasTexture.new()
			at.atlas = tex
			r.texture = at
			r.stretch_mode = TextureRect.STRETCH_SCALE
			r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			r.mouse_filter = Control.MOUSE_FILTER_IGNORE
			if part == "_semi":
				var m := CanvasItemMaterial.new()
				m.blend_mode = BLEND[rate]
				r.material = m
			add_child(r)
			pair.append(r)
		rects[k] = pair
	_update()


func _process(_dt: float) -> void:
	_update()


# render_frame's style-2 arithmetic (0x80042668): three digits of HP and MP,
# and the meters over 5000 -- tools/hud.py, held to 520 of 520 fields of the
# live table in the snapshots.
func _update() -> void:
	if sprites.is_empty():
		return
	var hp: int = int(player.get("hp")) if player and player.get("hp") != null else 50
	var mp: int = int(player.get("mp")) if player and player.get("mp") != null else 30
	var wm: int = int(player.get("weapon_meter")) if player and player.get("weapon_meter") != null else 5000
	var mm: int = int(player.get("magic_meter")) if player and player.get("magic_meter") != null else 5000
	var u := {}
	var w := {}
	for pair in [[17, hp], [22, mp]]:
		var v: int = int(pair[1]) % 1000
		var digits := [v / 100, v % 100 / 10, v % 10]
		for i in 3:
			u[int(pair[0]) + i] = (12 * int(digits[i]) - 0x80) & 0xFF
	w[25] = ((wm * 64 * 0x68DB8BAD) >> 32) >> 11
	w[26] = ((mm * 64 * 0x68DB8BAD) >> 32) >> 11
	var k_scale := get_viewport_rect().size.y / SCREEN_H
	# The port's own text goes under the panel, which the game's screen has to
	# itself up there.
	if k_scale != shown_scale:
		shown_scale = k_scale
		var top := PANEL_BOTTOM * k_scale + 8.0
		for n in ["../Hud", "../Compare"]:
			var lab := get_node_or_null(n) as Control
			if lab:
				var h := lab.offset_bottom - lab.offset_top
				lab.offset_top = top
				lab.offset_bottom = top + h
				top += 88.0
	for k in sprites:
		var s: Dictionary = sprites[k]
		var su: int = u.get(k, int(s["u"]))
		var sw: int = w.get(k, int(s["w"])) & 0xFF
		var region := Rect2(su, int(s["v"]), sw, int(s["h"]))
		for r in rects[k]:
			(r.texture as AtlasTexture).region = region
			r.position = Vector2(int(s["x"]), int(s["y"])) * k_scale
			r.size = Vector2(sw, int(s["h"])) * k_scale
			r.visible = sw > 0

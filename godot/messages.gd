class_name KFMessages
extends Control
# The banners along the bottom of the screen: "Locked", "Empty", "Can't Carry
# Any More", and so on.
#
# `announce` (0x80041eec) puts a code under 0xf0 into a ring of eight bytes at
# 0x801aeaed, at 0x801aeaf6, unless that place is still taken; for 0x19, the
# gold, the amount goes beside it at 0x801aead8. `message_tick` (0x80041f9c),
# which `render_frame` calls every frame -- object_give's own frames too --
# shows them one at a time, a state at 0x801aeaf7:
#
#   0  the next code (0x801aeaf5) is not 0xff: state 1, 15 frames to hold, the
#      brightness 0; its picture into sprite 0 -- u = 128 * (code / 18),
#      v = 14 * (code % 18), a 127 x 14 piece of the page at (640, 256) -- or,
#      for the gold, the word "Gold" into sprite 1 and the amount, four digits
#      right-aligned and blank-filled, into sprites 2 to 5
#   1  the brightness (0x801aeaf9) up by 0x14 until it reaches 0x64
#   2  the hold down by 1 to 0
#   3  the brightness down by 0x14 to 0; then the code is cleared, and the next
#      too while it is the same one -- except the gold -- and state 0
#
# `message_draw` (0x80041d9c) draws the six sprites at 0x80081928 that are on: bit 1 of a
# record's +0 as an additive SPRT, bit 2 as a subtractive one, both coloured
# by the brightness. Every texel of the page has STP set, so both blend, and
# the subtraction goes in second -- drawn first, the ordering table being a
# stack: what is left is the brighter of the scene and the text.
#
# tools/hud.py writes the page (msgpage.png) and the six records
# (messages.json) out of GAME.EXE.
#
# @exe game

const RING := 8
const EMPTY := 0xFF
const GOLD := 0x19
const HOLD := 0xF
const FADE := 0x14
const FULL := 0x64
const PER_COLUMN := 18
const LINE := 14
const DIGIT_ROW := 238             # the digits' strip, v
const BLANK := 0xA                 # the digit number_digits fills with
const SCREEN_W := 320.0
const SCREEN_H := 240.0
const TICK_HZ := 15.0

static var ring := PackedInt32Array([EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY])
static var amounts := PackedInt32Array([0, 0, 0, 0, 0, 0, 0, 0])
static var put := 0                # 0x801aeaf6
static var take := 0               # 0x801aeaf5
static var state := 0              # 0x801aeaf7
static var hold := 0               # 0x801aeaf8
static var bright := 0             # 0x801aeaf9
static var on := PackedInt32Array([0, 0, 0, 0, 0, 0])   # each sprite's +0
static var uv := [Vector2i(), Vector2i(), Vector2i(), Vector2i(), Vector2i(), Vector2i()]

var sprites := []                  # messages.json: the six records
var rects := []                    # per sprite: [subtract, add] TextureRects
var page: Texture2D
var acc := 0.0


# @orig game:0x80041eec announce  status:transcribed
static func announce(code: int, value := 0) -> void:
	if code >= 0xF0 or ring[put] != EMPTY:
		return
	ring[put] = code
	if code == GOLD:
		amounts[put] = value
	put = (put + 1) & 7


# number_digits(value, 4, 0, 0): four digits, right-aligned, the rest 0xa.
# @orig game:0x800277c0 number_digits  status:partial -- the plain form, mode 0, that the gold's banner asks for; not the prefixes of modes 1 to 5
static func digits(value: int, n := 4) -> Array:
	var out := []
	out.resize(n)
	out.fill(BLANK)
	var i := n - 1
	while i >= 0:
		out[i] = value % 10
		value /= 10
		if value == 0:
			break
		i -= 1
	return out


# @orig game:0x80041f9c message_tick  status:transcribed
static func tick() -> void:
	match state:
		0:
			var code := ring[take]
			if code == EMPTY:
				return
			state = 1
			hold = HOLD
			bright = 0
			if code == GOLD:
				on = PackedInt32Array([0, 3, 3, 3, 3, 3])
				uv[1] = Vector2i(0x80, 0x62)
				var d := digits(amounts[take])
				for k in 4:                # sprite 2 the ones, 5 the thousands
					uv[2 + k] = Vector2i(int(d[3 - k]) << 3, DIGIT_ROW)
			else:
				on = PackedInt32Array([3, 0, 0, 0, 0, 0])
				uv[0] = Vector2i((code / PER_COLUMN) << 7, (code % PER_COLUMN) * LINE)
		1:
			bright = (bright + FADE) & 0xFF
			if bright >= FULL:
				state = 2
		2:
			hold = (hold - 1) & 0xFF
			if hold == 0:
				state = 3
		3:
			bright = (bright - FADE) & 0xFF
			if bright != 0:
				return
			var code := ring[take]
			on = PackedInt32Array([code, code, code, code, code, code])
			while true:
				ring[take] = EMPTY
				take = (take + 1) & 7
				if ring[take] != code or code == GOLD:
					break
			state = 0


# @port data -- the page and the six records, and a pair of rects for each
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	if not FileAccess.file_exists("res://messages.json"):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://messages.json"))
	if typeof(d) != TYPE_DICTIONARY:
		return
	page = load("res://" + str(d["png"]))
	if page == null:
		return
	sprites = d["sprites"]
	for _s in sprites:
		var pair := []
		for mode in [CanvasItemMaterial.BLEND_MODE_SUB, CanvasItemMaterial.BLEND_MODE_ADD]:
			var r := TextureRect.new()
			var at := AtlasTexture.new()
			at.atlas = page
			r.texture = at
			r.stretch_mode = TextureRect.STRETCH_SCALE
			r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			r.mouse_filter = Control.MOUSE_FILTER_IGNORE
			var m := CanvasItemMaterial.new()
			m.blend_mode = mode
			r.material = m
			r.visible = false
			add_child(r)
			pair.append(r)
		rects.append(pair)


# @port engine -- message_tick at the game's 15 frames a second, whatever else is stopped
func _process(dt: float) -> void:
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		tick()
	_show()


# What message_draw draws: each sprite that is on, its two blends coloured by
# the brightness (0x80 leaves a texel as it is). The game's 320 x 240 screen
# is centred in the port's window, scaled to its height.
# @orig game:0x80041d9c message_draw  status:partial -- bits 1 and 2 of +0; bit 4, a subtraction at a quarter, only ever comes with the brightness at 0
func _show() -> void:
	if rects.is_empty():
		return
	var vs := get_viewport_rect().size
	var k := vs.y / SCREEN_H
	var left := (vs.x - SCREEN_W * k) * 0.5
	var c := float(bright) / 128.0
	for i in rects.size():
		var s: Dictionary = sprites[i]
		var shown := bright != 0 and (on[i] & 3) != 0
		var region := Rect2(uv[i].x, uv[i].y, int(s["w"]), int(s["h"]))
		for j in 2:
			var r: TextureRect = rects[i][j]
			r.visible = shown and (on[i] & (2 if j == 0 else 1)) != 0
			if not r.visible:
				continue
			(r.texture as AtlasTexture).region = region
			r.position = Vector2(left + int(s["x"]) * k, int(s["y"]) * k)
			r.size = Vector2(int(s["w"]), int(s["h"])) * k
			r.modulate = Color(c, c, c, 1.0)

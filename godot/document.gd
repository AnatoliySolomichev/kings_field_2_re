class_name KFDocument
extends Control
# What the player reads: an inscription, a plaque, a gravestone.
#
# object_interact's .L38 (classes 0x0d and 0x14) calls load_entry (0x800441d4)
# with ITEM.T entry 0x96 + the object's u16 at +0x38. That loads the entry's
# TIMs into a cleared 4-bit page at VRAM (960, 256) -- the words sit where each
# TIM says -- keeps the screen as it is, and runs load_wait_screen
# (0x80043bb8), its own frames:
#
#   each frame   the kept screen, darkened to 0x80 - s2 / 2; over it the page's
#                256 x 208 at (32, 32), twice: subtracted one texel down and to
#                the right, then added, both at s2 -- the words and a shadow
#   s2           0 up by 0xc a frame while it is 1..0x77: ten frames to 0x6c.
#                The pad is read after each: up first, then a press ends it
#   then         if no press came: wait for one, the pad up first, drawing
#                nothing; and fade out from 0x50, or from where the press
#                caught it, by 0xc a frame: seven frames from 0x50
#
# The world stands still meanwhile (KFGame.modal); godot/loot.gd starts it.
# tools/readables.py is the same in Python, and writes the pages, read/N.png.
#
# @exe game

const FADE := 0xC
const OUT_FROM := 0x50
const AT := Vector2(32, 32)
const SCREEN_W := 320.0
const SCREEN_H := 240.0
const TICK_HZ := 15.0

var phase := 0                     # 0 shut, 1 fading in, 2 waiting, 3 fading out
var s2 := 0
var armed := -1                    # load_wait_screen's local: -1, then -2 once the pad is up
var shown := -1                    # the s2 of the frame on screen
# The press that ended it: load_entry ORs its USE bit into `buttons`
# (0x801b265c), or clears it, and script_interpreter asks it whether the next
# line follows.
var closed_by := 0
var page: Texture2D
var dim: ColorRect
var words := []                    # [subtract, add]
var acc := 0.0


# @port engine -- the darkening and the two passes of the page, as nodes
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	dim = ColorRect.new()
	dim.color = Color(0, 0, 0, 0)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	dim.visible = false
	add_child(dim)
	for mode in [CanvasItemMaterial.BLEND_MODE_SUB, CanvasItemMaterial.BLEND_MODE_ADD]:
		var r := TextureRect.new()
		r.stretch_mode = TextureRect.STRETCH_SCALE
		r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		r.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var m := CanvasItemMaterial.new()
		m.blend_mode = mode
		r.material = m
		r.visible = false
		add_child(r)
		words.append(r)


# load_entry's start: the page, and load_wait_screen(0, 0xc). A sign's page is
# ITEM.T 0x96 + n, read/N.png; a conversation's line TALK.T n, talk/N.png.
# @orig game:0x800441d4 load_entry  status:partial -- the page and the frames; the page comes ready-made from tools/readables.py rather than through VRAM
func open(n: int) -> bool:
	return open_path("res://read/%d.png" % n)


# @port helper -- load_entry on a page tools/readables.py or tools/talk.py wrote
func open_path(path: String) -> bool:
	if not ResourceLoader.exists(path):
		return false
	page = load(path)
	for r in words:
		(r as TextureRect).texture = page
	phase = 1
	s2 = 0
	armed = -1
	shown = -1
	closed_by = 0
	return true


# @port helper -- still up
func is_open() -> bool:
	return phase != 0


# One step of load_entry: a frame of load_wait_screen, drawn and then the pad
# looked at, or a look of the wait between them. `pad` is the pad's word; true
# when it was looked at.
# @orig game:0x80043bb8 load_wait_screen  status:transcribed -- the fade and the pad; tools/readables.py, selftest
# @orig game:0x800442c8 load_entry+0xf4  status:transcribed -- the wait between the fades
func step(pad: int) -> bool:
	match phase:
		1, 3:
			shown = s2
			s2 += FADE if phase == 1 else -FADE
			if s2 - 1 < 0 or s2 - 1 >= 0x77:
				phase = 0 if phase == 3 else 2
				return false
			if armed == -1:
				if pad == 0:
					armed = -2
			elif pad != 0:
				closed_by = pad
				if phase == 1:          # a press while it fades in: out from here
					phase = 3
					armed = -1
				else:
					phase = 0
			return true
		2:
			if armed == -1:
				if pad == 0:
					armed = -2
			elif pad != 0:
				closed_by = pad
				s2 = OUT_FROM
				phase = 3
				armed = -1
			return true
	return false


# @port engine -- load_wait_screen's frames at 15 a second; the wait reads the pad every rendered frame
func _process(dt: float) -> void:
	if phase == 0:
		_show()
		return
	if phase == 2:
		step(KFPad.now)
	else:
		acc = minf(acc + dt, 0.25)
		while acc >= 1.0 / TICK_HZ and (phase == 1 or phase == 3):
			acc -= 1.0 / TICK_HZ
			step(KFPad.now)
	_show()


# What one frame of load_wait_screen puts on the screen at s2: the scene at
# 0x80 - s2 / 2, the shadow and the words at s2.
# @orig game:0x80043bb8 load_wait_screen  status:transcribed -- the four primitives: two of the kept screen, the page subtracted at (33, 33) and added at (32, 32)
func _show() -> void:
	var up := phase != 0 and shown >= 0
	dim.visible = up
	for r in words:
		(r as TextureRect).visible = up
	if not up:
		return
	var vs := get_viewport_rect().size
	var k := vs.y / SCREEN_H
	var left := (vs.x - SCREEN_W * k) * 0.5
	dim.position = Vector2.ZERO
	dim.size = vs
	var s4 := 0x80 - (shown >> 1)
	dim.color = Color(0, 0, 0, 1.0 - float(s4) / 128.0)
	var c := float(shown) / 128.0
	for i in 2:
		var r: TextureRect = words[i]
		var at := AT + (Vector2.ONE if i == 0 else Vector2.ZERO)
		r.position = Vector2(left, 0) + at * k
		r.size = Vector2(page.get_width(), page.get_height()) * k
		r.modulate = Color(c, c, c, 1.0)

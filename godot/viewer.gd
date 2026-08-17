extends Node3D
# One model at a time, by number.
#
#   Left / Right      the model before, the model after
#   Page Up / Down    ten at a time
#   type digits, Enter   go to that number
#   Home              back to 0
#   E                 only models that draw anything
#   drag the mouse    turn it       wheel  closer or further
#
# The numbering is the one an object type reaches a model by: `MO.T` is 0 to 427
# and `MOF.T` carries on from 428, so the number here is the world label's type
# plus 128. That offset was measured, not reasoned — four pairs a player named
# off the grid, all differing by exactly 128 — and this exists because hunting
# for a number on a field of five hundred models is no way to name a fifth.
#
# Models sit two hundred metres apart, so the camera being at one of them means
# nothing else is in the frame.

var index := 0
var models: Array = []
var bias := 128
var spacing := 200.0
var per_row := 20
var yaw := 0.6
var pitch := 0.5
var dist := 3.0
var typed := ""
var only_drawn := false
var uses := {}
var cam: Camera3D
var hud: Label


func _ready() -> void:
	cam = get_node_or_null("Camera")
	hud = get_node_or_null("UI/Hud")
	var f := FileAccess.open("res://gallery.json", FileAccess.READ)
	if f:
		var doc = JSON.parse_string(f.get_as_text())
		models = doc["labels"]
		bias = int(doc.get("bias", 128))
		spacing = float(doc["spacing"])
		per_row = int(doc["per_row"])
	var g := FileAccess.open("res://objlabels00.json", FileAccess.READ)
	if g:
		for row in JSON.parse_string(g.get_as_text()):
			var n := int(row["type"]) + bias
			uses[n] = int(uses.get(n, 0)) + 1
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	_go(0)


func _model(i: int) -> Dictionary:
	if i < 0 or i >= models.size():
		return {}
	return models[i]


func _go(i: int) -> void:
	if models.is_empty():
		return
	index = clampi(i, 0, models.size() - 1)
	if only_drawn:
		var step := 1 if i >= index else -1
		while index > 0 and index < models.size() - 1 and models[index]["empty"]:
			index += step
	var m := _model(index)
	# Frame the model: a bigger thing wants the camera further back.
	var ext = m.get("ext")
	var size := 1.0
	if ext != null:
		size = maxf(0.5, float(max(max(float(ext[0]), float(ext[1])),
			float(ext[2]))) / 1000.0)
	dist = size * 2.2
	_place()
	_hud()


func _place() -> void:
	var m := _model(index)
	if m.is_empty() or cam == null:
		return
	var centre := Vector3(float(m["x"]), 0.0, float(m["z"]))
	var ext = m.get("ext")
	if ext != null:
		centre.y = float(ext[1]) / 2000.0
	var dir := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch))
	cam.position = centre + dir * dist
	cam.look_at(centre, Vector3.UP)


func _hud() -> void:
	if hud == null:
		return
	var m := _model(index)
	if m.is_empty():
		hud.text = "no models"
		return
	var ext = m.get("ext")
	var size := "-"
	if ext != null:
		size = "%d x %d x %d" % [int(ext[0]), int(ext[1]), int(ext[2])]
	var used: String = "used by %d object(s) on level 0" % int(uses.get(index, 0))
	if not uses.has(index):
		used = "no object on level 0 uses it"
	hud.text = ("model %d      %s.T entry %d\n" +
		"type %d  (model number less %d)\n" +
		"%d primitives   %s units%s\n%s\n\n" +
		"left/right  step    page up/down  ten    digits+enter  go to\n" +
		"E  %s    drag  turn    wheel  zoom") % [
		index, str(m.get("archive", "?")), int(m.get("entry", -1)),
		index - bias, bias,
		int(m.get("prims", 0)), size,
		"     EMPTY" if m["empty"] else "",
		used,
		"skipping the empty ones" if only_drawn else "showing every number"]


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseMotion and (e.button_mask & MOUSE_BUTTON_MASK_LEFT):
		yaw -= e.relative.x * 0.01
		pitch = clampf(pitch + e.relative.y * 0.01, -1.3, 1.3)
		_place()
	elif e is InputEventMouseButton and e.pressed:
		if e.button_index == MOUSE_BUTTON_WHEEL_UP:
			dist = maxf(0.3, dist * 0.85)
			_place()
		elif e.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			dist = minf(400.0, dist * 1.18)
			_place()
	elif e is InputEventKey and e.pressed and not e.echo:
		match e.keycode:
			KEY_LEFT: _go(index - 1)
			KEY_RIGHT: _go(index + 1)
			KEY_PAGEUP: _go(index - 10)
			KEY_PAGEDOWN: _go(index + 10)
			KEY_HOME: _go(0)
			KEY_END: _go(models.size() - 1)
			KEY_E:
				only_drawn = not only_drawn
				_hud()
			KEY_ENTER, KEY_KP_ENTER:
				if typed != "":
					_go(int(typed))
					typed = ""
			KEY_BACKSPACE:
				typed = typed.substr(0, typed.length() - 1)
				_typing()
			_:
				var ch := char(e.unicode)
				if ch.length() == 1 and ch >= "0" and ch <= "9":
					typed += ch
					_typing()


func _typing() -> void:
	if hud:
		_hud()
		hud.text = "go to: " + typed + "\n\n" + hud.text

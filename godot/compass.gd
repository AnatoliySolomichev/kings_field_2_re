extends Control
# The compass: the ball with the N in the top-right corner.
#
# render_frame keeps the ball's yaw on a damped spring behind the view's
# (0x80042448), and draw_model_cell_lit (0x8003c35c) draws model_table[0] --
# FDAT.T entry 97 block 9, 26 vertices and 32 faces -- without perspective:
# the library's RotMatrix (0x80076168) of (view pitch, ball yaw, 0), scaled by
# the record's 0x55 over 4096, put through MVMVA alone, so x and y of R v plus
# (290, 32) are the screen position and z sorts the faces. model_prims drops a
# face whose NCLIP is not positive. The light is class 0x30's, its direction
# matrix turned by the same R so it stays put on the screen; every face is
# semi-transparent, the STP texels mixing half and half. tools/compass.py has
# it all, and compass.json carries the model, the light and RotMatrix's own
# sine table, which is not the one game_sin reads.
# @orig game:0x8003c35c draw_model_cell_lit  status:transcribed -- the compass: orthographic, class light turned by R, NCLIP
# @orig game:0x80076168  status:transcribed -- the library's RotMatrix, with its own table

const SCREEN_W := 320.0
const SCREEN_H := 240.0
const TICK_HZ := 15.0

var doc := {}
var rec := {}
var trig := PackedInt32Array()
var tex := {}                      # png -> Texture2D
var yaw := 0                       # the record's +0x1a
var vel := 0                       # $gp+0xd8
var acc := 0.0
var player: Node


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	player = get_node_or_null("../../Player")
	var path := "res://compass.json"
	if not FileAccess.file_exists(path):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return
	doc = d
	trig = PackedInt32Array(d["trig"])
	# compass_style 2, which a new character has: the second record
	for r in d["records"]:
		if int(r["index"]) == 1:
			rec = r
	for f in d["faces"]:
		if not tex.has(f["png"]):
			tex[f["png"]] = load("res://" + str(f["png"]))


func _process(dt: float) -> void:
	if rec.is_empty() or player == null:
		return
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		_swing(int(player.get("facing")) & 0xFFF)
	queue_redraw()


# render_frame, 0x80042448: the spring the ball's yaw rides on.
func _swing(view_yaw: int) -> void:
	var d := (view_yaw - yaw) & 0xFFF
	if d >= 0x801:
		d -= 0x1000
	vel += d
	if vel > 0:
		vel -= (vel + 7) >> 3
	elif vel < 0:
		vel -= (vel - 7) >> 3
	yaw = (yaw + (vel >> 6)) & 0xFFFF


func _sc(a: int) -> Vector2i:
	a &= 0xFFFF
	if a >= 0x8000:
		a -= 0x10000
	if a < 0:
		var i := (-a) & 0xFFF
		return Vector2i(-trig[2 * i], trig[2 * i + 1])
	var j := a & 0xFFF
	return Vector2i(trig[2 * j], trig[2 * j + 1])


# 0x80076168: Rx(ax) Ry(ay) Rz(az), carrying -sin y as the routine does.
func _rot(ax: int, ay: int, az: int) -> Array:
	var x := _sc(ax)
	var y := _sc(ay)
	var z := _sc(az)
	var sx := x.x; var cx := x.y
	var sy := y.x; var cy := y.y
	var sz := z.x; var cz := z.y
	var ny := -sy
	return [[(cz * cy) >> 12, (-(sz * cy)) >> 12, sy],
		[((sz * cx) >> 12) - ((((cz * ny) >> 12) * sx) >> 12),
			((cz * cx) >> 12) + ((((sz * ny) >> 12) * sx) >> 12),
			(-(cy * sx)) >> 12],
		[((sz * sx) >> 12) + ((((cz * ny) >> 12) * cx) >> 12),
			((cz * sx) >> 12) - ((((sz * ny) >> 12) * cx) >> 12),
			(cy * cx) >> 12]]


# The GTE's lit colour for one normal: tools/level3d.py's shade().
func _shade(n: Array, l: Array) -> Color:
	var ir := [0, 0, 0]
	for r in 3:
		var v: int = (int(l[r][0]) * int(n[0]) + int(l[r][1]) * int(n[1])
			+ int(l[r][2]) * int(n[2])) >> 12
		ir[r] = clampi(v, 0, 0x7FFF)
	var lcm: Array = doc["colour"]
	var bk: Array = doc["back"]
	var c := [0.0, 0.0, 0.0]
	for r in 3:
		var v: int = (int(bk[r]) * 4096 + int(lcm[r][0]) * ir[0]
			+ int(lcm[r][1]) * ir[1] + int(lcm[r][2]) * ir[2]) >> 12
		c[r] = clampf(float(v) / 4096.0, 0.0, 1.0)
	return Color(c[0], c[1], c[2], 1.0)


func _draw() -> void:
	if rec.is_empty():
		return
	var pitch := int(player.get("pitch")) if player else 0
	var m := _rot(pitch, yaw, 0)
	var light: Array = doc["light"]
	var lp := []
	for i in 3:
		var row := []
		for j in 3:
			row.append((int(light[i][0]) * int(m[0][j]) + int(light[i][1]) * int(m[1][j])
				+ int(light[i][2]) * int(m[2][j])) >> 12)
		lp.append(row)
	var s: Array = rec["scale"]
	var place: Array = rec["place"]
	var ms := []
	for i in 3:
		ms.append([(int(m[i][0]) * int(s[0])) >> 12, (int(m[i][1]) * int(s[1])) >> 12,
			(int(m[i][2]) * int(s[2])) >> 12])
	var scr := []
	for v in doc["verts"]:
		var p := Vector3i()
		for i in 3:
			p[i] = ((int(ms[i][0]) * int(v[0]) + int(ms[i][1]) * int(v[1])
				+ int(ms[i][2]) * int(v[2])) >> 12) + int(place[i])
		scr.append(p)
	var faces := []
	for f in doc["faces"]:
		var vs: Array = f["v"]
		var a: Vector3i = scr[int(vs[0])]
		var b: Vector3i = scr[int(vs[1])]
		var c: Vector3i = scr[int(vs[2])]
		var nclip := a.x * b.y + b.x * c.y + c.x * a.y - a.x * c.y - b.x * a.y - c.x * b.y
		if nclip <= 0:
			continue
		var zsum := 0
		for k in vs:
			zsum += scr[int(k)].z
		faces.append([float(zsum) / vs.size(), f])
	faces.sort_custom(func(p, q): return p[0] > q[0])
	var k_scale := get_viewport_rect().size.y / SCREEN_H
	var right := get_viewport_rect().size.x
	for pair in faces:
		var f: Dictionary = pair[1]
		var vs: Array = f["v"]
		var order := [0, 1, 3, 2] if f["quad"] else [0, 1, 2]
		var pts := PackedVector2Array()
		var cols := PackedColorArray()
		var uvs := PackedVector2Array()
		for i in order:
			var p: Vector3i = scr[int(vs[i])]
			pts.append(Vector2(right - (SCREEN_W - p.x) * k_scale, p.y * k_scale))
			var n: Array = doc["normals"][int(f["n"][i])]
			cols.append(_shade(n, lp))
			uvs.append(Vector2(float(f["uv"][i][0]) + 0.5, float(f["uv"][i][1]) + 0.5) / 256.0)
		draw_polygon(pts, cols, uvs, tex[f["png"]])

extends Node3D
# Names on things, so the two windows can be compared by number instead of by
# memory.
#
#   N  the objects in the world, each with its slot and its type id
#   K  the gallery: every model in MO.T on a grid, each with its number
#
# The port assumes an object of type N uses model `MO.T[N]`, and that assumption
# has never been checked against the game. A player looking at the two side by
# side reports armour where doors should be. The placement is not the reason —
# the disc records and the live table agree on the type id for 347 of 347 slots
# — so it is the lookup, and the way to settle it is to make both sides visible
# and readable at once: stand somewhere in the game, read the type off the world
# label here, then find the shape you can actually see in the gallery and read
# its number. Each such pair is one fact, and a handful of them name the rule.

const GALLERY_Y := 400.0        # far above the level, so flying there is separate

var world_labels: Node3D
var gallery_labels: Node3D
var gallery: Node3D
var player: Node3D
var back_at := Vector3.ZERO
var in_gallery := false


func _ready() -> void:
	player = get_node_or_null("../Player")
	gallery = get_node_or_null("../Gallery")
	if gallery:
		gallery.visible = false
	world_labels = _make("WorldLabels", "res://objlabels00.json", false)
	gallery_labels = _make("GalleryLabels", "res://gallery.json", true)
	if world_labels:
		world_labels.visible = false


func _label(text: String, pos: Vector3, colour: Color, size: float) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.position = pos
	l.font_size = 48
	l.pixel_size = size
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = false
	l.modulate = colour
	l.outline_size = 12
	l.outline_modulate = Color(0, 0, 0, 0.9)
	return l


func _read(path: String):
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return null
	return JSON.parse_string(f.get_as_text())


func _make(name: String, path: String, is_gallery: bool) -> Node3D:
	var doc = _read(path)
	if doc == null:
		return null
	var holder := Node3D.new()
	holder.name = name
	add_child(holder)
	if is_gallery:
		for row in doc["labels"]:
			var n := int(row["n"])
			var col := Color(0.6, 0.9, 0.6) if not row["empty"] else Color(0.6, 0.4, 0.4)
			holder.add_child(_label("%d" % n,
				Vector3(float(row["x"]), GALLERY_Y + 2.6, float(row["z"])),
				col, 0.006))
	else:
		var at := {}
		for row in doc:
			var s: int = int(row["scale"])
			var extra := ""
			if s != 0x1000:
				extra = "  x%.2f" % (float(s) / 4096.0)
			# Two objects often share a cell -- a readable marker stands on the
			# same square as the thing it describes -- and their labels landed on
			# top of each other, unreadable. Stack them instead.
			var key := Vector2i(int(row["x"] * 4.0), int(row["z"] * 4.0))
			var n: int = at.get(key, 0)
			at[key] = n + 1
			holder.add_child(_label("%d / t%d%s" % [int(row["slot"]),
				int(row["type"]), extra],
				Vector3(float(row["x"]), float(row["y"]) + 2.2 + 0.7 * float(n),
					float(row["z"])),
				Color(1.0, 0.9, 0.5), 0.004))
	return holder


func _unhandled_input(e: InputEvent) -> void:
	if not (e is InputEventKey and e.pressed and not e.echo):
		return
	if e.keycode == KEY_N and world_labels:
		world_labels.visible = not world_labels.visible
	elif e.keycode == KEY_K:
		_toggle_gallery()


func _toggle_gallery() -> void:
	if gallery == null or player == null:
		return
	in_gallery = not in_gallery
	gallery.visible = in_gallery
	if gallery_labels:
		gallery_labels.visible = in_gallery
	if in_gallery:
		back_at = Vector3(float(player.gx), float(player.gy), float(player.gz))
		player.flying = true
		player.gx = 0
		player.gy = int(-GALLERY_Y * 1000.0) - 4000
		player.gz = 0
	else:
		player.gx = int(back_at.x)
		player.gy = int(back_at.y)
		player.gz = int(back_at.z)

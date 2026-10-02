extends Node3D
# The sky: render_walk's own path for an object of class 0xf0 (0x80040fac).
#
# While sky_on (0x801aeaea) is set and object_in_view passes, render_walk hands
# model_table[type - 0xdd] to draw_model_at_eye (0x800400ac), which builds a
# matrix from the record's angles, turns it by the view, and sets the
# translation to (0, 0x64, 0) **in view space** -- so the model sits on the eye,
# 100 below it, wherever the player is -- then lights it with the class at
# +0x3b and files every face in the 8-entry side ordering table, which
# frame_end_3d links into the main one at 0x1ffe: behind everything the world
# draws. Levels 0-7 and 9-11 place one, type 265, model 44 of the resident
# bank: a textured dome 1000 across and 1250 high.
# tools/level3d.py writes it as skyNN.gltf with the class's lighting baked in.
#
# The port gets "under everything" the other way round: the dome follows the
# camera, and its shader pushes each vertex out along its own direction to just
# inside the camera's far plane and writes no depth, so it shows only where
# nothing nearer was drawn -- which is what the back of the ordering table
# means. The direction is all a projection keeps, so the dome looks the size
# it does in the game.
#
# Class 0xe3 objects switch it. Every frame the interpreter (0x8004a954) asks
# player_in_rect of each one's cell rectangle -- the record's cell, +0x38 by
# +0x39 cells -- and one that holds the player writes its +0x3b to sky_on, so
# the last in slot order wins and the value stays when none does. game_main
# starts it at 1 (0x80035610). On level 0 every zone says 1.
#
# @exe game

const LIFT := 0.1                  # 0x64 game units below the eye, in metres
const REACH := 390.0               # just inside the camera's far plane of 400

const CODE := """
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never;
uniform sampler2D page : source_color, filter_nearest;
uniform float lift = 0.1;
uniform float reach = 390.0;
void vertex() {
	vec3 v = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v.y -= lift;
	POSITION = PROJECTION_MATRIX * vec4(normalize(v) * reach, 1.0);
}
void fragment() {
	vec4 c = texture(page, UV);
	if (c.a < 0.5) { discard; }
	ALBEDO = c.rgb * COLOR.rgb;
}
"""

var zones := []
var on := true                     # sky_on, 0x801aeaea
var player: Node3D
var dome: Node3D


# @port data -- reads skyNN.json (the 0xe3 zones) and skyNN.gltf, which tools/level3d.py writes
func _ready() -> void:
	player = get_node_or_null("../Player")
	var lv: int = player._level() if player else 0
	var path := "res://sky%02d.json" % lv
	if not FileAccess.file_exists(path):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_DICTIONARY:
		return
	zones = d.get("zones", [])
	var scene_path := "res://sky%02d.gltf" % lv
	if not d.get("sky", false) or not ResourceLoader.exists(scene_path):
		return
	dome = (load(scene_path) as PackedScene).instantiate()
	add_child(dome)
	var sh := Shader.new()
	sh.code = CODE
	_swap(dome, sh)


# @port engine -- puts the dome's textures on the shader in CODE
func _swap(n: Node, sh: Shader) -> void:
	if n is MeshInstance3D and n.mesh:
		n.extra_cull_margin = 16384.0
		for i in n.mesh.get_surface_count():
			var m = n.get_active_material(i)
			if not (m is BaseMaterial3D) or m.albedo_texture == null:
				continue
			var s := ShaderMaterial.new()
			s.shader = sh
			s.set_shader_parameter("page", m.albedo_texture)
			s.set_shader_parameter("lift", LIFT)
			s.set_shader_parameter("reach", REACH)
			n.set_surface_override_material(i, s)
	for c in n.get_children():
		_swap(c, sh)


# @orig game:0x8004a954 object_interpreter+0x3944  status:transcribed -- class 0xe3's arm: the zone that holds the player writes sky_on
# @orig game:0x80040fac render_walk+0x4c8  status:transcribed -- class 0xf0: drawn only while sky_on
# @orig game:0x800400ac draw_model_at_eye  status:transcribed -- the dome on the eye; the shader in CODE is its view-space (0, 0x64, 0) and the far ordering table
func _process(_dt: float) -> void:
	if dome == null:
		return
	if player:
		var cx: int = int(player.gx) >> 11
		var cz: int = int(player.gz) >> 11
		for z in zones:
			if cx >= int(z[0]) and cx < int(z[0]) + int(z[2]) \
					and cz >= int(z[1]) and cz < int(z[1]) + int(z[3]):
				on = int(z[5]) != 0
	dome.visible = on
	var cam := get_viewport().get_camera_3d()
	if cam:
		global_transform = Transform3D(Basis(), cam.global_position)

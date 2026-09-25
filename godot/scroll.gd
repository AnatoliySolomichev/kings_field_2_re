extends Node
# The water moves: one row of its texture a frame.
#
# game_main registers one scroll at start, texture_scroll_add(&{1016, 96, 32,
# 32}, 0, 1, 1) -- the rect is GAME.EXE data at 0x8009c214 -- which copies that
# 32x32 square of VRAM to a stash 32 halfwords to its left. Then every frame
# texture_scroll_step (0x800351fc), with a delay of 0 and a step of 1, adds one
# to the offset, wraps it at 32, and rebuilds the square from the stash with
# two MoveImages, so that row r shows stash row (r - offset) mod 32. Checked
# against eleven snapshots: each one's VRAM is the stash turned by the offset
# its RAM holds, or by the next one -- the VRAM was fetched a frame later.
#
# The square is page 0x0f, pixels 224..255 across and 96..127 down, and level
# 0's water is drawn from it. Rather than rewrite the texture every frame, this
# gives every material on page 0x0f a shader that samples the page the same way
# the scroll leaves it: inside the square, v moves by the offset; outside it,
# nothing changes. The offset is the game's own frame count at 15 a second
# (frame_limit), so it goes round in 32 frames, a little over two seconds.
#
# The same walk over the materials settles what a glTF cannot say about
# semi-transparency. tools/level3d.py gives a semi-transparent primitive a
# blended material whose texture alpha is how much each texel covers; the page's
# rate 0 mixes, which the glTF says itself, but rates 1 and 3 add and rate 2
# subtracts, and those materials carry "_add" or "_sub" in their names for this
# to act on. The water is rate 0.
# @orig game:0x800351fc texture_scroll_step  status:transcribed

const PAGE := "tex_000f_"            # the page the square is on
const X0 := 224.0                    # (1016 - 960) * 4 pixels
const Y0 := 96.0
const SIZE := 32.0
const STEP := 1.0                    # rows a frame
const FRAME_HZ := 15.0               # see player.gd

const CODE := """
shader_type spatial;
render_mode unshaded, %s, %s;
uniform sampler2D page : source_color, filter_nearest;
uniform float offset = 0.0;
void fragment() {
	vec2 px = UV * 256.0;
	if (px.x >= %.1f && px.y >= %.1f && px.y < %.1f) {
		px.y = %.1f + mod(px.y - %.1f - offset, %.1f);
	}
	vec4 c = texture(page, px / 256.0);
	ALBEDO = c.rgb * COLOR.rgb;
	%s
}
"""
const CUT := "ALPHA = c.a;\n\tALPHA_SCISSOR_THRESHOLD = 0.5;"
const MIXED := "if (c.a < 0.01) { discard; }\n\tALPHA = c.a;"

var mats: Array[ShaderMaterial] = []
var clock := 0.0


func _ready() -> void:
	var shaders := {}
	for root_name in ["../Level", "../Objects", "../Creatures", "../Gallery"]:
		var root := get_node_or_null(root_name)
		if root:
			_swap(root, shaders)


func _swap(n: Node, shaders: Dictionary) -> void:
	if n is MeshInstance3D and n.mesh:
		for i in n.mesh.get_surface_count():
			var m = n.get_active_material(i)
			if not (m is BaseMaterial3D) or m.albedo_texture == null:
				continue
			if m.resource_name.ends_with("_add"):
				m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
			elif m.resource_name.ends_with("_sub"):
				m.blend_mode = BaseMaterial3D.BLEND_MODE_SUB
			if not PAGE in m.albedo_texture.resource_path:
				continue
			var cull: String = "cull_disabled" \
				if m.cull_mode == BaseMaterial3D.CULL_DISABLED else "cull_back"
			# By the name tools/level3d.py gives it: an imported blended material
			# need not come in as TRANSPARENCY_ALPHA, and cut at a half the water's
			# half-covering texels would all come out solid.
			var semi: bool = "_semi" in m.resource_name
			var blend: String = ["blend_mix", "blend_add", "blend_sub", "blend_mul"][m.blend_mode]
			var key := "%s %s %s" % [cull, blend, semi]
			if not shaders.has(key):
				var sh := Shader.new()
				sh.code = CODE % [cull, blend, X0, Y0, Y0 + SIZE, Y0, Y0, SIZE,
					MIXED if semi else CUT]
				shaders[key] = sh
			var s := ShaderMaterial.new()
			s.shader = shaders[key]
			s.set_shader_parameter("page", m.albedo_texture)
			n.set_surface_override_material(i, s)
			mats.append(s)
	for c in n.get_children():
		_swap(c, shaders)


func _process(dt: float) -> void:
	if mats.is_empty():
		return
	clock += dt
	var offset := fmod(floor(clock * FRAME_HZ) * STEP, SIZE)
	for s in mats:
		s.set_shader_parameter("offset", offset)

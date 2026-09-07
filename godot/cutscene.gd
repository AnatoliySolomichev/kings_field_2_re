extends CanvasLayer
# The opening cutscene, where the sword is handed over.
#
# `game_main` plays it at 0x80014e74, in its own init block a few instructions
# after `place_player_on_terrain`, and the call is guarded by `bne $s1, 1` --
# `$s1` being the new-game flag, set when `read_overlay_arg2` answers -1. So it
# runs when a new game starts and not when a save is loaded, which is the
# condition reproduced below.
#
# What it plays is `\STR\S03.S`. That took a while to establish: the sword, the
# painting of the two knights and the three men in the room are all ordinary
# level 0 objects and actors, so the scene looked as though the engine drew it.
# It does not -- decoding frame 60 of S03.S shows that room and the subtitle a
# player quoted. The reason four separate breakpoints stayed silent through the
# whole scene is simply that nothing interactive runs during a movie, and the
# sword was already in the inventory: `reset_story_flags` puts item 0, item 42,
# two of item 104 and one of item 105 there before the first frame is drawn.
#
# The routine behind it is 0x80060d20; `build_str_name` is a label inside it,
# which is why nothing appeared to call it. It reads the scene number through
# the pointer at 0x801f825c and splits it into the two digits of
# `\STR\SXX.S;1`.

const SCENE := 3                  # \STR\S03.S

var video: VideoStreamPlayer
var started := false


func _ready() -> void:
	# The shell's own byte: 0 is NEW, which is what open_main leaves in
	# overlay_arg2 when the title menu's first entry was chosen. Without a
	# shell above us -- world.tscn opened on its own -- the default is 0, and a
	# new game is the right assumption.
	var shell := get_node_or_null("/root/Shell")
	var newgame := true
	if shell != null:
		newgame = shell.overlay_arg2 == 0
	var path := "res://opening/cutscene%02d.ogv" % SCENE
	if not newgame or not ResourceLoader.exists(path):
		queue_free()
		return
	layer = 10
	var back := ColorRect.new()
	back.color = Color.BLACK
	back.anchor_right = 1.0
	back.anchor_bottom = 1.0
	add_child(back)
	video = VideoStreamPlayer.new()
	video.stream = load(path)
	video.expand = true
	video.anchor_right = 1.0
	video.anchor_bottom = 1.0
	add_child(video)
	var hint := Label.new()
	hint.text = "  \\STR\\S03.S — START or a face button skips it"
	hint.anchor_top = 1.0
	hint.anchor_bottom = 1.0
	hint.offset_top = -22
	add_child(hint)
	video.play()
	started = true
	# The world runs on behind the movie in the game too, but the player should
	# not be walking about during it.
	var p := get_node_or_null("/root/World/Player")
	if p:
		p.set_process(false)


func _process(_dt: float) -> void:
	if not started:
		return
	KFPad.poll()
	# play_movie's own rules: START ends it, and so does any of the four face
	# buttons. Escape is this port's, for a keyboard with no pad.
	var skip := KFPad.hit_mask(KFPad.START | KFPad.TRIANGLE | KFPad.SQUARE
		| KFPad.CIRCLE | KFPad.CROSS) or Input.is_key_pressed(KEY_ESCAPE)
	if skip or not video.is_playing():
		var p := get_node_or_null("/root/World/Player")
		if p:
			p.set_process(true)
		queue_free()

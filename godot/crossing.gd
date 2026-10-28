class_name KFCrossing
extends Node
# Walking from one level into the next: object_interpreter's arm for opcode
# 0xe0 (0x8004a7f8), object_trigger (0x80017c78) and the shift level_load
# makes (world_shift, 0x80017aa4). tools/crossing.py is the same reading in
# Python, held to the two crossings bp16 recorded.
#
# A crossing object names a rectangle of cells; while the player's cell is in
# it -- and their height within the object's -- the arm asks object_trigger
# for the object's level block. Nothing starts while a change is under way,
# nor when the block is the one in hand (0xff bytes in it meaning "as it is").
# Otherwise the change starts, and once level_load has the new grid the world
# shifts by the object's cells -- target minus own, which
# load_object_placement read off the placement record (crossNN.json has them)
# -- so the player walks on where the new level puts the same ground.
#
# The game reads the disc for nine frames between the trigger and the shift,
# and another hundred before the level is current; the port loads the other
# level's world at once, on the trigger's frame, and puts the player down
# shifted, carrying what they had (player.gd, carried and arrive).
#
# @exe game

const NO_LEVEL := 0xFF
const TICK_HZ := 15.0

var player: Node
var trig: Array = []
var acc := 0.0
var refused := {}                   # level -> true: not built, said once
# warp_to's fades while they run (fade_frames): the screen's bytes still to
# show, one a frame at 15 a second with the world held, then what follows --
# "jump" (the plan carried out), "clear" (screen_fade(0xff)), "leave" (the
# shell) or "none"; "" while nothing runs
var fades: Array = []
var fade_then := ""
var fade_plan := {}
var fade_acc := 0.0
# what a warp to another level leaves for the next scene's crossing to run:
# the fades back and whether the screen is cleared after them
static var fades_back: Array = []
static var clear_back := false
# and the scene it plays first, -1 for none: level_overlay_tick's scene 7
# after its warp on to level 24 (KFTicks.finale), then fade_frames(1, 0, 0, 0)
static var scene_back := -1
# a scene's movie while it plays (str_play), the world held, and what follows
var movie: VideoStreamPlayer
var movie_layer: CanvasLayer
var movie_then := ""


# @port data -- crossNN.json: this level's crossing objects, tools/crossing.py export
func _ready() -> void:
	player = get_node_or_null("../Player")
	if player == null:
		return
	var lv: int = player._level()
	var path := "res://cross%02d.json" % lv
	if FileAccess.file_exists(path):
		var d = JSON.parse_string(FileAccess.get_file_as_string(path))
		if typeof(d) == TYPE_ARRAY:
			trig = d
	if KFGame.block.is_empty() or int(KFGame.block[1]) != lv:
		KFGame.block = own_block(lv, trig)
	if scene_back >= 0:
		var n := scene_back
		scene_back = -1
		fades_back = [[1, 0, 0, 0]]
		clear_back = false
		_movie(n, "back")
		return
	if not fades_back.is_empty() or clear_back:
		_fade(fades_back, "clear" if clear_back else "")
		fades_back = []
		clear_back = false


# The block a level is in hand as: what its own crossings that keep it ask
# for -- level 0's [0, 0, 0, 0, 0], level 4's [4, 4, 4, 13, 15], as the
# snapshots hold them at 0x8018fad8 -- or the level in all five.
# @port helper -- a level's own block, off its crossings
static func own_block(lv: int, ts: Array) -> Array:
	for t in ts:
		var b: Array = t["block"]
		if int(b[1]) == lv and not (NO_LEVEL in b):
			return b.map(func(v): return int(v))
	return [lv, lv, lv, lv, lv]


# @port engine -- the arm at the game's 15 frames a second, while nothing else holds the world
func _process(dt: float) -> void:
	if movie != null:
		_movie_tick()
		return
	if not fades.is_empty() or fade_then != "":
		_fading(dt)
		return
	if player == null or trig.is_empty() or KFGame.modal or KFGame.follow:
		return
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		var hit := fire(trig, Vector3i(player.gx, player.gy, player.gz), KFGame.block)
		if not hit.is_empty():
			_cross(hit)
			return


# The arm over the level's crossings, in slot order: the first the player
# stands in whose block is not the one in hand -- {trigger, block} -- or {}.
# @orig game:0x8004a7f8 object_interpreter+0x37e8  status:verified -- opcode 0xe0's arm, through object_trigger_args; tools/crossing.py fires on the two frames bp16 crossed on and nowhere else
# @orig game:0x80017c78 object_trigger  status:partial -- a change starts when nothing is under way and the block is not the one in hand; not the level_state written for the level left, the story flag, or the map's marks
static func fire(ts: Array, p: Vector3i, current: Array) -> Dictionary:
	for t in ts:
		if not KFObjects.player_in_rect(p.x, p.z, int(t["cx"]), int(t["cz"]),
				int(t["w"]), int(t["h"]), p.y, int(t["y"])):
			continue
		var want := []
		for i in 5:
			var b := int(t["block"][i])
			want.append(int(current[i]) if b == NO_LEVEL else b)
		if want != current:
			return {"trigger": t, "block": want}
	return {}


# world_shift's three, whole cells across and along and 128s of height the
# other way, when the crossing has them.
# @orig game:0x80017aa4 world_shift  status:transcribed -- the player's part; the new level brings its own objects and creatures
static func shifted(p: Vector3i, shift) -> Vector3i:
	if shift == null:
		return p
	return Vector3i(p.x + (int(shift[0]) << 11), p.y - (int(shift[2]) << 7),
		p.z + (int(shift[1]) << 11))


# @port engine -- the other level's world loaded, the player carried over and shifted
func _cross(hit: Dictionary) -> void:
	var want: Array = hit["block"]
	var lv := int(want[1])
	var scene := "res://world%02d.tscn" % lv
	if not ResourceLoader.exists(scene):
		if not refused.has(lv):
			refused[lv] = true
			KFInfo.note("crossing: level %d is not built (python3 tools/level3d.py %d)" % [lv, lv])
		return
	var t: Dictionary = hit["trigger"]
	var p := shifted(Vector3i(player.gx, player.gy, player.gz), t["shift"])
	KFInfo.note("crossing: level %d's slot %d into level %d, block %s, shift %s" % [
		player._level(), int(t["slot"]), lv, str(want), str(t["shift"])])
	player.carry_over(p)
	KFGame.block = want
	KFGame.level = lv
	get_tree().change_scene_to_file(scene)


# warp_to's level change, the plan KFUseItem.warp_plan made of it: first its
# fade out (fade_frames(1, 0, 0x1000, 0x100): seventeen frames adding white
# until the screen is white), the world held; then on the level in hand the
# player is put down where the record says and the creatures may wake
# anywhere (spawn_anywhere); from another, that level's world loaded and the
# player carried over to the place, as a crossing carries them. Either way
# the facing and the pitch are the record's, the player's state 0 and the
# view's tilt gone; and then the fades back -- one frame white on the new
# place, seventeen back to clear -- and screen_fade(0xff).
# @port engine -- warp_to's fades, then its change of place or level, as _cross makes one
func warp(plan: Dictionary) -> void:
	if plan.is_empty() or player == null:
		return
	var lv := int(plan["level"])
	if not bool(plan["same"]):
		var scene := "res://world%02d.tscn" % lv
		if not ResourceLoader.exists(scene):
			KFInfo.note("warp: level %d is not built (python3 tools/level3d.py %d)" % [lv, lv])
			return
	var out: Array = plan.get("out", [])
	if out.is_empty():
		_jump(plan)
		return
	fade_plan = plan
	_fade([out], "jump")


# The game ended by a level's own code (KFDeaths, level 25's entry 19): the
# frames it runs of its own -- the master volume down a VSync at a time, the
# screen as render_flags_reset left it, four VSyncs to a frame of the game's
# -- and its fade_frames, the world held; then game_main's test of the word
# (KFGame.leave). The sound is not here.
# level_overlay_tick's short ending plays scene 8 between its fade and the
# shell (`scene`).
# @port engine -- a level's last frames, then the shell
func leave(word: int, vsyncs: int, runs: Array, scene := -1) -> void:
	_fade(runs, "leave")
	var hold := []
	for i in vsyncs / 4:
		hold.append([0xFF, 0, 0, 0])
	fades = hold + fades
	fade_plan = {"word": word, "scene": scene}


# A scene's movie, as str_play (0x80060d20) plays it out of \STR\SXX.S --
# the record's first byte is the number, here the scene's own (7 and 8) --
# over the world, which stands; then `then`: "exit" game_main's test of the
# word (KFGame.leave), "back" the fades back the warp left. START or a face
# button ends it, as the opening's and the dreams' do -- the port's; what
# str_play's own loop reads is not read.
# @port engine -- the scene's movie over the held world, then what follows
func _movie(n: int, then: String) -> void:
	var path := "res://opening/cutscene%02d.ogv" % n
	movie_then = then
	KFGame.modal = true
	KFInfo.note("scene %d: \\STR\\S%02d.S" % [n, n])
	if not ResourceLoader.exists(path):
		KFInfo.note("scene %d is not transcoded (python3 tools/opening.py video)" % n)
		_movie_done()
		return
	movie_layer = CanvasLayer.new()
	movie_layer.layer = 10
	var back := ColorRect.new()
	back.color = Color.BLACK
	back.anchor_right = 1.0
	back.anchor_bottom = 1.0
	movie_layer.add_child(back)
	movie = VideoStreamPlayer.new()
	movie.stream = load(path)
	movie.expand = true
	movie.anchor_right = 1.0
	movie.anchor_bottom = 1.0
	movie_layer.add_child(movie)
	add_child(movie_layer)
	movie.play()


# @port engine -- the movie to its end, or skipped
func _movie_tick() -> void:
	KFPad.poll()
	var skip := KFPad.hit_mask(KFPad.START | KFPad.TRIANGLE | KFPad.SQUARE
		| KFPad.CIRCLE | KFPad.CROSS) or Input.is_key_pressed(KEY_ESCAPE)
	if skip or not movie.is_playing():
		_movie_done()


# @port engine -- the movie gone, and what was to follow it
func _movie_done() -> void:
	if movie_layer != null:
		movie_layer.queue_free()
	movie = null
	movie_layer = null
	KFGame.modal = false
	var then := movie_then
	movie_then = ""
	match then:
		"exit":
			KFGame.leave(get_tree(), int(fade_plan.get("word", 0)))
		"back":
			_fade(fades_back, "")
			fades_back = []


# The fades' runs, fade_frames' bytes a frame each, the world held, and then
# `then`.
# @port engine -- warp_to's fades started: the frames to show and what follows
func _fade(runs: Array, then: String) -> void:
	fades = []
	for r in runs:
		fades += KFGame.fade_frames(int(r[0]), int(r[1]), int(r[2]), int(r[3]))
	fade_then = then if then != "" else "none"   # so _process runs it to the end and lets go
	fade_acc = 0.0
	KFGame.modal = true


# @port engine -- a fade's frames at 15 a second, and what follows them
func _fading(dt: float) -> void:
	fade_acc = minf(fade_acc + dt, 0.25)
	while fade_acc >= 1.0 / TICK_HZ:
		fade_acc -= 1.0 / TICK_HZ
		if not fades.is_empty():
			var f: Array = fades.pop_front()
			KFGame.screen_fade(int(f[0]), int(f[1]), int(f[2]), int(f[3]))
			continue
		var then := fade_then
		fade_then = ""
		KFGame.modal = false
		match then:
			"jump":
				_jump(fade_plan)
			"leave":
				if int(fade_plan.get("scene", -1)) >= 0:
					_movie(int(fade_plan["scene"]), "exit")
				else:
					KFGame.leave(get_tree(), int(fade_plan.get("word", 0)))
			"clear":
				KFGame.screen_fade(0xFF, 0, 0, 0)
		return


# @port engine -- the player put down where warp_to's plan says, and its fades back
func _jump(plan: Dictionary) -> void:
	var lv := int(plan["level"])
	var p: Array = plan["pos"]
	var at := Vector3i(int(p[0]), int(p[1]), int(p[2]))
	var back: Array = plan.get("back", [])
	var clear := bool(plan.get("clear", false))
	player.facing = int(plan["facing"])
	player.pitch = int(plan["pitch"])
	player.pstate = 0
	if int(plan.get("answer", 0)):
		player.warped = 1                # 0x801b25ee, below record 0xc
	player.tilt = [0, 0, 0]
	player.tilt_vel = [0, 0, 0]
	KFGame.block = (plan["block"] as Array).map(func(v): return int(v))
	KFInfo.note("warp: level %d, cell (%d, %d), facing 0x%x, block %s" % [lv, at.x >> 11,
		at.z >> 11, int(plan["facing"]), str(KFGame.block)])
	if bool(plan["same"]):
		player.gx = at.x
		player.gy = at.y
		player.gz = at.z
		player.rotation.y = float(player.facing) * TAU / 4096.0
		player._to_godot()
		var an := get_node_or_null("../Actors")
		if an:
			an.spawn_anywhere = true
		if scene_back >= 0:              # level_overlay_tick's scene, on the level in hand
			var n := scene_back
			scene_back = -1
			fades_back = back + [[1, 0, 0, 0]]
			_movie(n, "back")
			return
		if not back.is_empty() or clear:
			_fade(back, "clear" if clear else "")
		return
	player.carry_over(at)
	KFGame.level = lv
	if not back.is_empty() or clear:
		fades_back = back
		clear_back = clear
		KFGame.modal = true
	get_tree().change_scene_to_file("res://world%02d.tscn" % lv)

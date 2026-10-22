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


# warp_to's level change, the plan KFUseItem.warp_plan made of it: on the
# level in hand the player is put down where the record says and the
# creatures may wake anywhere (spawn_anywhere); from another, that level's
# world loaded and the player carried over to the place, as a crossing
# carries them. Either way the facing and the pitch are the record's, the
# player's state 0 and the view's tilt gone. The game fades to black and
# back around it (fade_frames); the port does not.
# @port engine -- warp_to's change of place or level, as _cross makes one
func warp(plan: Dictionary) -> void:
	if plan.is_empty() or player == null:
		return
	var lv := int(plan["level"])
	var p: Array = plan["pos"]
	var at := Vector3i(int(p[0]), int(p[1]), int(p[2]))
	if not bool(plan["same"]):
		var scene := "res://world%02d.tscn" % lv
		if not ResourceLoader.exists(scene):
			KFInfo.note("warp: level %d is not built (python3 tools/level3d.py %d)" % [lv, lv])
			return
	player.facing = int(plan["facing"])
	player.pitch = int(plan["pitch"])
	player.pstate = 0
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
		return
	player.carry_over(at)
	KFGame.level = lv
	get_tree().change_scene_to_file("res://world%02d.tscn" % lv)

extends Node
# The effects: what a creature's volley throws. tools/effects.py is the same
# in Python, and its docstring the reading; so far, the spores (effect 0x26)
# of level 0's kind-3 creatures.
#
# effect_driver (0x8005bc50) runs once a game frame after the creatures: each
# live slot's life counts down, it goes past 0, and otherwise effect_tick runs
# its kind's arm. A spore swells, rises and then sinks, strikes the player
# within its x scale -- poison, through player.gd take_effect -- and goes
# when it meets the tiles.
#
# @exe game

const TICK_HZ := 15.0
const SPORE := 0x26
const GROW := 0x96
const RISE := 0x28
const SINK := 0x55
const TURN := 0x21
const OWN := 0x320
const BODY := 0x6A4
const EDGE := 0x400
const FAR := -0x98967F

var slots: Array = []            # the live effects, as tools/effects.py's dicts
var acc := 0.0
var player: Node3D
var coll: KFCollision
var template: Node3D             # model 0x40, out of effectsNN.gltf


# @port engine -- finds the player, its collision and model 0x40's node
func _ready() -> void:
	player = get_node_or_null("../Player")
	if player and player.get("coll") is KFCollision:
		coll = player.get("coll")
	var models := get_node_or_null("../EffectModels")
	if models:
		template = models.find_child("m064", true, false) as Node3D


# @port engine -- runs _pass at the game's 15 frames a second
func _process(dt: float) -> void:
	if KFGame.modal:                  # object_give's frames: they stand still
		return
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		_pass()


# effect_spawn's arm 0x26 (0x80054338): the scale 0x400, model 0x40, a life of
# 0x32, the half-step test, 0x14 frames of growth, 200 higher; the grace count
# 0 as actor_animation_effects leaves it, and +6 the percentage.
# @orig game:0x80054338 effect_spawn+0x6b4  status:verified -- a label inside effect_spawn; tools/effects.py against bp26
func spawn_spore(point: Vector3i, pct: int) -> void:
	if slots.size() >= 128:
		return                          # effect_alloc: none free
	var e := {"f0": 0x81, "kind": SPORE, "pct": pct, "grace": 0, "half": 1,
		"life": 0x32, "x": point.x, "y": point.y - 0xC8, "z": point.z,
		"scale": [0x400, 0x400, 0x400], "vel": [0, 0, 0], "count": 0x14,
		"node": null}
	if template:
		var n := template.duplicate() as Node3D
		n.visible = true
		add_child(n)
		e["node"] = n
	slots.append(e)
	_draw(e)


# @orig game:0x8005bc50 effect_driver  status:partial -- the walk over the live slots; the count is _tick's, the 128 a cap in spawn_spore
func _pass() -> void:
	if coll == null:
		return
	var keep := []
	var t := Vector3i.ZERO
	if player:
		t = Vector3i(int(player.get("gx")), int(player.get("gy")), int(player.get("gz")))
	for e in slots:
		if _tick(e, t):
			keep.append(e)
		elif e["node"]:
			(e["node"] as Node3D).queue_free()
	slots = keep


# effect_driver's count and effect_tick's arm 0x26 (0x80056de8). False when
# the slot goes.
# @orig game:0x8005bcc0 effect_driver+0x70  status:verified -- the life, counted down; -1 retires the slot
# @orig game:0x80056de8 effect_tick+0x52c  status:verified -- tools/effects.py: 118 of 118 frames of the recorded spores, 118 of 118 strikes
func _tick(e: Dictionary, t: Vector3i) -> bool:
	e["life"] = int(e["life"]) - 1
	if int(e["life"]) == -1:
		return false
	var sc: Array = e["scale"]
	if int(e["count"]) > 0:
		sc[0] = int(sc[0]) + GROW
		sc[2] = int(sc[2]) + GROW
		e["count"] = int(e["count"]) - 1
	if int(sc[1]) < 0x1000:
		sc[1] = int(sc[1]) + GROW
	e["y"] = int(e["y"]) + (SINK if int(e["life"]) < TURN else -RISE)
	var p := Vector3i(int(e["x"]), int(e["y"]), int(e["z"]))
	var hit := _strike_scale(p, int(sc[0]), t)
	e["hit"] = hit
	if hit >= 0 and player and player.has_method("take_effect"):
		# record 0x26 of spell_table: no attack, the effect 3 -- poison
		player.call("take_effect", [0, 0, 0, 0, 0, 0, 0, 0], 3, hit, int(e["pct"]), p)
	var v: Array = e["vel"]
	e["x"] = int(e["x"]) + int(v[0])
	e["y"] = int(e["y"]) + int(v[1])
	e["z"] = int(e["z"]) + int(v[2])
	if _collides(e):
		return false
	_draw(e)
	return true


# effect_hurt_player (0x8002b114) with mode 0x8000: in_range_3d (0x80016fb4) --
# a box of radius + 0x320, then the length to the player's middle through the
# game's root, less 0x320, must be 0 or more -- and the scale falling to 0x400
# at the rim. -1 for a miss.
# @orig game:0x8002b114 effect_hurt_player  status:verified -- 118 of 118 strikes of bp26, scale and all
# @orig game:0x80016fb4 in_range_3d  status:verified -- through effect_hurt_player, the same 118
func _strike_scale(p: Vector3i, radius: int, t: Vector3i) -> int:
	var r := radius + OWN
	var dx := t.x - p.x
	var dz := t.z - p.z
	var dy := t.y - p.y - (BODY >> 1)
	if dx < -r or r < dx or dz < -r or r < dz or dy < -r or r < dy:
		return -1
	var ln := coll.isqrt((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3) + (dy >> 3) * (dy >> 3)) << 3
	if r < ln:
		return -1
	var d := ln - OWN
	if d < 0:
		return -1
	var q := absi(d << 12) / radius
	var f := (0x1000 - (((q & 0xFFFF) * (0x1000 - EDGE)) >> 12)) & 0xFFFF
	return (0x1000 * f) >> 12


# effect_move's collision (0x80053310): the tiles, at the point's y plus half
# the height -- the point is the middle -- and, with +0xd, half a step back.
# @orig game:0x80053310 effect_collide  status:verified -- a spore freed on the floor, bp26
func _collides(e: Dictionary) -> bool:
	if int(e["grace"]) > 0:
		e["grace"] = int(e["grace"]) - 1
		return false
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = 0x64
	coll.body = 0xC8
	var v: Array = e["vel"]
	var m := int(coll.query(int(e["x"]), int(e["y"]) + 0x64, int(e["z"]))["mask"])
	if m == 0 and int(e["half"]) != 0:
		m = int(coll.query(int(e["x"]) - (int(v[0]) >> 1),
			int(e["y"]) - (int(v[1]) >> 1) + 0x64,
			int(e["z"]) - (int(v[2]) >> 1))["mask"])
	coll.radius = keep_r
	coll.body = keep_b
	return m != 0


# render_walk's third loop draws a slot's model +0xe at its point, turned by
# +0x28.. with 0x800 on the yaw, through the scale +0x30..+0x34.
# @orig game:0x8004165c render_walk+0xb78  status:partial -- the place, the turn and the scale; not the view test (+8 & 3, view_bits_at) nor the light
func _draw(e: Dictionary) -> void:
	var n = e["node"]
	if n == null:
		return
	var sc: Array = e["scale"]
	(n as Node3D).position = Vector3(float(e["x"]) / 1000.0, float(-int(e["y"])) / 1000.0,
		float(-int(e["z"])) / 1000.0)
	(n as Node3D).basis = Basis(Vector3.UP, PI).scaled_local(
		Vector3(float(sc[0]), float(sc[1]), float(sc[2])) / 4096.0)

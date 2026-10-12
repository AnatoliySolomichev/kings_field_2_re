extends Node
# The game's creature activation machine, run over the level's actors.
#
# Transcribed from GAME.EXE, not tuned: `0x8004c1f0` and the loop in
# `actor_tick_driver` (0x80052e5c) that calls it. tools/actors.py is the same
# machine in Python and FORMATS.md section 17 the long form; read one of them
# before changing a line here.
#
# Every actor has a state, the game's byte +9, and render_walk draws a creature
# only while it is 1. So what the player sees is not all 58 creatures of level 0
# but the few this machine has woken:
#
#   0 dormant  waits for the player to come within (act + 1) cells, and then by
#              category: 0 must also be beyond act cells -- it appears at the
#              rim of the ring, never in front of you -- and win rand()>>7
#              against its chance byte; 1 needs the ring only; 2 no ring, and
#              rolls rand()>>4 every time it is looked at
#   1 up       drawn; beyond deact cells it goes back to 0, at home
#   2 held     not drawn; walking out past deact cells is the only release
#   3 gone     never again, and kept across visits (0x8005efd4)
#
# Slot k is looked at in the frames where frame & 3 == k & 3, and every slot in
# the first pass after a level loads: the load sets 0x801b24f2 and game_main
# clears it after one pass.
#
# What an awake creature then does -- actor_tick's behaviours -- is ai.gd, run
# from _pass. F10 kills the nearest awake one, to try the rules on -- not X,
# which is the emulator's CROSS and the port's too.
#
# @exe game

const TICK_HZ := 15.0          # the game's frame, four blanks: see player.gd
const SLOTS := 200
const DORMANT := 0
const ACTIVE := 1
const HELD := 2
const GONE := 3
const NO_Y := 0xFFFF
const FREE := 0xFF

# What 0x8005efd4 writes for a level when the player leaves it -- slot and 3-or-0
# for every category-1 actor -- and apply_level_state puts back on the next
# load: KFLevelState keeps it, in the level's stream. The epoch this scene was
# made in, so that one made before a save was put back writes nothing.
var made_epoch := -1

var level := 0
var actors := []               # a Dictionary per slot, null where empty
var nodes := {}                # slot -> its node in the Creatures scene
var frame := 0
var spawn_anywhere := true     # 0x801b24f2
var rand_next := 1             # not `seed`, which is a global function
var show_all := false
var acc := 0.0
var changes := 0
var shown := -1
var last := PackedStringArray()
var player: Node3D
var coll: KFCollision          # for the game's square root
var ai: KFCreatureAI           # what an awake creature does (ai.gd)
var kinds := {}                # kind -> its fields and behaviours, aiNN.json
var skins := {}                # slot -> its animated mesh (KFAnim), see _skin


# @orig game:0x8005f444 apply_level_state  status:partial -- the first section: the category-1 states put back from the level's stream (KFLevelState); reading actorsNN.json, aiNN.json and animNN.json and finding the nodes is the port's
func _ready() -> void:
	player = get_node_or_null("../Player")
	# the level in hand: the scene sets nothing here, and a level other than 0
	# took level 0's creatures until this was read off KFGame
	level = KFGame.current_level()
	actors.resize(SLOTS)
	var f := FileAccess.open("res://actors%02d.json" % level, FileAccess.READ)
	if f == null:
		push_warning("actors: res://actors%02d.json is missing" % level)
		return
	var d = JSON.parse_string(f.get_as_text())
	if typeof(d) != TYPE_ARRAY:
		push_warning("actors: res://actors%02d.json is not a list" % level)
		return
	for row in d:
		var a := {}
		for key in row:
			var v = row[key]
			a[key] = int(v) if typeof(v) == TYPE_FLOAT else v
		a["st"] = DORMANT
		a["ry"] = a["yaw"]
		_home(a)
		actors[a["slot"]] = a
	var root := get_node_or_null("../Creatures")
	if root:
		for k in SLOTS:
			if actors[k] != null:
				var n := root.find_child("a%03d" % k, true, false)
				if n is Node3D:
					nodes[k] = n
	if player and player.get("coll") is KFCollision:
		coll = player.get("coll")
	else:
		coll = KFCollision.new()
		coll.load_from("res://coll%02d.json" % level)
	ai = KFCreatureAI.new()
	ai.coll = coll
	ai.rand = Callable(self, "_rand")
	var af := FileAccess.open("res://ai%02d.json" % level, FileAccess.READ)
	if af:
		var ad = JSON.parse_string(af.get_as_text())
		if typeof(ad) == TYPE_DICTIONARY:
			for key in ad["kinds"]:
				var kd: Dictionary = ad["kinds"][key]
				var recs := []
				for r in kd["behaviours"]:
					var raw := []
					for v in r:
						raw.append(int(v))
					recs.append(raw)
				kd["behaviours"] = recs
				for field in ["accel", "turn_accel", "fall", "radius", "height",
						"weight", "arc_face", "arc_back", "hp", "exp", "gold", "scale"]:
					kd[field] = int(kd.get(field, 0x1000 if field == "scale" else 0))
				var dfn := []
				for v in kd.get("defence", []):
					dfn.append(int(v))
				kd["defence"] = dfn
				kinds[int(key)] = kd
	if KFAnim.load_from("res://anim%02d.json" % level):
		for k in nodes:
			_skin(k)
	made_epoch = KFLevelState.epoch
	var st := KFLevelState.decoded(level)     # the level's stream, if it was left or saved
	for pair in st.get("actors", []):
		if int(pair[0]) < SLOTS and actors[int(pair[0])] != null:
			actors[int(pair[0])]["st"] = int(pair[1])
	refresh()


# level_state_write's first section: the slot and +9 of each category-1
# actor, which KFLevelState.encode writes as 3 or 0.
# @orig game:0x8005f00c level_state_write+0x38  status:transcribed -- the walk over the 200 slots for category 1; the stream is KFLevelState's
func _exit_tree() -> void:
	if made_epoch != KFLevelState.epoch:
		return
	var keep := []
	for k in SLOTS:
		var a = actors[k]
		if a != null and int(a["cat"]) == 1:
			keep.append([k, int(a["st"])])
	KFLevelState.actor_parts[level] = keep


# @port engine -- runs _pass at the game's 15 frames a second
func _process(dt: float) -> void:
	if player == null or nodes.is_empty():
		return
	if KFGame.modal:                  # object_give's frames: they stand still
		return
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		if not KFGame.follow:         # following the emulator, they are the game's
			_pass(int(player.get("gx")), int(player.get("gz")))
	if changes != shown:
		refresh()


# @port check -- F10 kills the nearest awake creature
func _unhandled_input(e: InputEvent) -> void:
	# X, because K is the pad's cross in pad.gd and N the labels
	if e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_F10:
		if player == null:
			return
		var k := _nearest(int(player.get("gx")), int(player.get("gz")), 3 << 11)
		if k >= 0:
			_kill(k)
			refresh()


# actor_tick_driver: one game frame. Each slot is looked at for waking on its
# own frame in four; then an awake one chooses on the frames where the count of
# awake ones ticked so far this frame agrees with the frame in its low two bits
# (0x8018fac8 against 0x8018facc), and is ticked (ai.gd) -- the player has
# already moved, since game_main runs player_controller first.
# @orig game:0x80052e5c actor_tick_driver  status:transcribed -- the loop over the 199 slots, activation, choosing and the tick
func _pass(px: int, pz: int) -> void:
	var p := Vector3i(px, int(player.get("gy")), pz) if player else Vector3i(px, 0, pz)
	var awake := []
	for k in SLOTS:
		var a = actors[k]
		if a != null and a["st"] == ACTIVE:
			awake.append(a)
	var n := 0
	for k in SLOTS:
		var a = actors[k]
		if a == null or a["cat"] == FREE:
			continue
		if (frame & 3) == (k & 3) or spawn_anywhere:
			_activate(k, px, pz)
			if a["st"] == ACTIVE and not awake.has(a):
				awake.append(a)
		if a["st"] != ACTIVE or not kinds.has(int(a["kind"])) or not a.has("phase"):
			continue
		var kind: Dictionary = kinds[int(a["kind"])]
		if (frame & 3) == (n & 3):
			ai.pick(a, kind, p)
		var blow := ai.tick(a, kind, p, awake)
		if a.has("fired"):
			_launch(a, kind, a["fired"])
			a.erase("fired")
		if a.has("drop"):
			var lt := get_node_or_null("../Loot")
			if lt:
				for d in a["drop"]:
					lt.spawn(d)
			a.erase("drop")
		if a.get("retire", false):
			a.erase("retire")
			_kill(k)
			refresh()
			continue
		if not blow.is_empty():
			_blow(a, blow)
		n += 1
		_place(k)
	frame += 1
	spawn_anywhere = false


# The game's creatures, while the port follows the emulator (ghost.gd, C):
# every slot in use with its +9, place, yaw, animation, clock and HP as bp16
# sends them. A slot it does not send is free in the game (+0 is 0xff): gone.
# @port check -- the game's actors laid over the port's, for the comparison
func follow(entries: Array) -> void:
	var seen := {}
	for e in entries:
		var k := int(e[0])
		if k < 0 or k >= SLOTS or actors[k] == null:
			continue
		seen[k] = true
		var a: Dictionary = actors[k]
		if int(a["st"]) != int(e[1]):
			a["st"] = int(e[1])
			changes += 1
		a["px"] = int(e[2])
		a["py"] = int(e[3])
		a["pz"] = int(e[4])
		a["ry"] = int(e[5]) & 0xFFF
		a["anim"] = int(e[6])
		a["clock"] = int(e[7])
		a["hp"] = int(e[8])
		_place(k)
	for k in SLOTS:
		var a = actors[k]
		if a != null and not seen.has(k) and int(a["st"]) != GONE:
			a["st"] = GONE
			changes += 1


# Where the creature's node stands and faces: its position and its yaw +0x42.
# @port engine -- the node where the actor stands; the turn is _draw_basis's
func _place(k: int) -> void:
	if not nodes.has(k):
		return
	var a: Dictionary = actors[k]
	var nd: Node3D = nodes[k]
	nd.position = Vector3(float(a["px"]) / 1000.0, float(-int(a["py"])) / 1000.0,
		float(-int(a["pz"])) / 1000.0)
	nd.basis = _draw_basis(a)
	_animate(k)


# An animated creature's mesh, made so its vertices can be moved (KFAnim.skin).
# @port engine -- an animated creature's mesh, made movable
func _skin(k: int) -> void:
	var sk := KFAnim.skin(nodes[k], int(actors[k]["model"]))
	if not sk.is_empty():
		skins[k] = sk


# The frame 0x800431e8 would draw: the animation +0xc and the clock +0x18.
# @port engine -- hands the skin +0xc and +0x18; the frame is anim.gd's model_animate
func _animate(k: int) -> void:
	if not skins.has(k):
		return
	var a: Dictionary = actors[k]
	KFAnim.animate(skins[k], int(a.get("anim", 0x80)) & 0xFF, int(a.get("clock", 0)))


# A volley's fire (actor_animation_effects, 0x8004f414, keyed by the record's
# +0xc): a plain entry is a vertex of the creature's animated model -- scaled
# by +0x48 and turned by the yaw + 0x800 (actor_vertex_point, 0x8004ede0) --
# and an 0x8002 entry carries an offset of its own, turned by the creature's
# angles as they are (vec_rotate, 0x8004f48c); the arm throws from there: 0x26 a spore, with +0x18's low byte as its
# percentage (tools/effects.py puts slot 40's spore at the point bp26 logged,
# to the unit); 0x1f..0x25 a bolt, aimed at the player and flown by the effect
# machine (effects.gd volley_bolt). Of those, effects.gd has 0x1f, 0x22, 0x23
# and 0x24 -- level 4's model-53 and model-67 creatures', and level 12's.
# @orig game:0x8004f414 actor_animation_effects  status:partial -- the point -- off the creature's vertex, or an 0x8002 entry's offset turned by its angles -- and the switch, for arms 0x26 and 0x1f..0x25; the 0x8004 entry (a point along a limb, 0x8004f49c) and the other arms are not here
# @orig game:0x8004f6c4 actor_animation_effects+0x2b0  status:verified -- arm 0x26, the spores
func _launch(a: Dictionary, kind: Dictionary, fired: Array) -> void:
	var raw: Array = a["rec"]
	if raw == null:
		return
	var arm := int(raw[0xC])
	if arm != 0x26 and (arm < 0x1F or arm > 0x25):
		return
	var fx := get_node_or_null("../Effects")
	if fx == null or not fx.has_method("spawn"):
		return
	var pct := KFCreatureAI.u16f(raw, 0x18) & 0xFF
	var m := int(a["model"])
	for f in fired:
		var w: Array
		if f.size() == 4 and int(f[0]) == 0x8002:
			# a2 = -1: the offset the entry carries, turned by the creature's
			# own angles (+0x40, no half turn) through vec_rotate
			w = KFWeapon.vec_rotate(coll, 0, int(a["ry"]) & 0xFFF, 0,
				[int(f[1]), int(f[2]), int(f[3])])
		elif f.size() == 1:
			var v := Vector3i(0, -(int(a["height"]) >> 1), -int(a["radius"]))
			if KFAnim.models.has(m):
				var vs := KFAnim.vertices(m, int(a.get("anim", 0x80)) & 0xFF, int(a["clock"]))
				if int(f[0]) < vs.size():
					v = vs[int(f[0])]
			var sc := int(kind.get("scale", 0x1000))
			w = KFWeapon.vec_rotate(coll, 0, (int(a["ry"]) + 0x800) & 0xFFF, 0,
				[(v.x * sc) >> 12, (v.y * sc) >> 12, (v.z * sc) >> 12])
		else:
			continue                          # 0x8004, along a limb: not here
		var point := Vector3i(int(a["px"]) + int(w[0]), int(a["py"]) + int(w[1]),
			int(a["pz"]) + int(w[2]))
		if arm == 0x26:
			fx.spawn_spore(point, pct)
		else:
			fx.volley_bolt(arm, pct, point, 0, int(a["ry"]))


# How render_walk (0x80040c94) turns a creature to draw it: its angles +0x40,
# +0x42 + 0x800, +0x44 into draw_model_plain, which builds Ry Rx Rz with the
# game's own rot_matrix_y (cos, -sin / sin, cos) at 0x800166f4 -- so a model's
# front is its -z, and the half turn faces it the way it walks. Flip Y and Z
# into Godot's axes and that is a turn of yaw + 0x800 about up. A kind with
# flag 0x20 (+0x28) is drawn with no turn at all (0x80040c34).
# @orig game:0x80040c94 render_walk+0x1b0  status:transcribed -- a label inside render_walk
func _draw_basis(a: Dictionary) -> Basis:
	# the kind's +0x32, at the actor's +0x48..+0x4c: draw_model_plain's
	# ScaleMatrix -- 0x1400 for level 0's commonest monsters, a quarter larger
	var s := float(kinds[int(a["kind"])].get("scale", 0x1000)) / 4096.0 \
		if kinds.has(int(a["kind"])) else 1.0
	if int(a.get("eflags", 0)) & 0x20:
		return Basis().scaled_local(Vector3(s, s, s))
	return Basis(Vector3.UP, float((int(a["ry"]) + 0x800) & 0xFFF) * TAU / 4096.0) \
		.scaled_local(Vector3(s, s, s))


# A blow opcode 4 struck: the player within its reach of the creature raised by
# its lift, not nearer than 0, and inside its arc of the yaw (0x8004d254). What
# it does to the player is damage.gd's and player.gd's.
# @orig game:0x8004d254 actor_blow  status:transcribed -- the reach and the arc; the damage is the caller's
func _blow(a: Dictionary, blow: Dictionary) -> void:
	if player == null:
		return
	var gx: int = player.get("gx")
	var gy: int = player.get("gy")
	var gz: int = player.get("gz")
	var d := _in_range(int(a["px"]), int(a["py"]) - int(blow["lift"]), int(a["pz"]),
		gx, gy, gz, int(blow["reach"]), 0, 0x6A4)
	if d == -1:
		return
	var brg := coll.vec_angle(gx - int(a["px"]), gz - int(a["pz"]))
	if not KFCreatureAI.facing_test(KFCreatureAI.s16(a["ry"]), KFCreatureAI.s16(brg), int(blow["arc"])):
		return
	if player.has_method("take_blow"):
		player.call("take_blow", a, blow["rec"])


# The player's blow (held_item_tick, 0x8002dcd8): a quarter of the reach
# walked four times from the player's point 0x320 above the feet, each point
# asked of actor_spot_taken at radius 0x190 and height 0x258 with nothing let
# through; the first creature met is struck if the view's yaw is within its
# kind's +0x16 of the bearing to it and its own yaw within +0x18 of the bearing
# back. Returns {slot, damage, hp, exp, strong} or {}.
# @orig game:0x8002dcd8 held_item_tick+0xa38  status:transcribed -- a label inside held_item_tick; weapons 0x1f and 0x20's specials are not here
func strike(p: Vector3i, step: Array, view_yaw: int, stat: int,
		attacks: Array, strength: int, push: bool) -> Dictionary:
	var q := Vector3i(p.x, p.y - KFWeapon.PROBE_UP, p.z)
	for _i in 4:
		q += Vector3i(int(step[0]), int(step[1]), int(step[2]))
		var k := _spot(q)
		if k == -1:
			continue
		var a: Dictionary = actors[k]
		var kind: Dictionary = kinds[int(a["kind"])]
		var b := coll.vec_angle(int(a["px"]) - p.x, int(a["pz"]) - p.z)
		if not KFCreatureAI.facing_test(view_yaw, KFCreatureAI.s16(b), int(kind["arc_face"])):
			continue
		if not KFCreatureAI.facing_test(int(a["ry"]), KFCreatureAI.s16(b + 0x800), int(kind["arc_back"])):
			continue
		var dmg := KFWeapon.creature_damage(stat, attacks, kind["defence"], strength)
		var point := Vector3i(p.x, p.y - KFWeapon.EYE_DROP, p.z)
		var out := _take_hit(k, dmg, strength, point if push else null)
		out["slot"] = k
		return out
	return {}


# actor_spot_taken (0x8004d644) as the blow asks it: mask 0, the dying skipped.
# @orig game:0x8004d644 actor_spot_taken  status:transcribed -- as the blow asks it: mask 0, the dying skipped
func _spot(q: Vector3i) -> int:
	for j in SLOTS:
		var o = actors[j]
		if o == null or o["st"] != ACTIVE or int(o.get("op", 0)) == 3:
			continue
		if not kinds.has(int(o["kind"])):
			continue
		if _in_range(o["px"], o["py"], o["pz"], q.x, q.y, q.z,
				int(o["radius"]) + KFWeapon.PROBE_R, o["height"], KFWeapon.PROBE_H) != -1:
			return j
	return -1


# actor_take_hit (0x8004c668) after the damage, for the player's blow (flags
# 0x50): the level's hook (level 0's spares slot 0x20 any blow that would not
# kill it), the HP at +0x1a, and at 0 the experience and the kind's opcode 3
# (dying); short of that the first opcode-2 behaviour the damage reaches and
# the roll allows (a flinch). Then the push from the player's point, and the
# vertical state 0x10 either way. tools/weapon.py take_hit.
# @orig game:0x8004c668 actor_take_hit  status:transcribed -- the player's blow; the special weapons 0x1f and 0x20 and the followers' leader are not here
func _take_hit(k: int, dmg: int, strength: int, point) -> Dictionary:
	var a: Dictionary = actors[k]
	var kind: Dictionary = kinds[int(a["kind"])]
	var out := {"damage": 0, "exp": 0, "strong": false, "hp": int(a.get("hp", 0))}
	var op := int(a.get("op", 0))
	if op == 0x1A or (op == 3 and int(a["clock"]) >= 0x60C):
		return out
	if op == 0x15:
		if int(a["sub"]) == 0:
			a["sub"] = 2
		return out
	if op == 6 and int(a["sub"]) == 0:
		a["sub"] = 2
	KFWeapon.load_from()
	if KFWeapon.guard.get(level, -1) == k and dmg < int(a["hp"]):
		dmg = 0
	if dmg == 0:
		return out
	out["damage"] = dmg
	out["strong"] = int(a["hp"]) != 0 and strength >= KFWeapon.STRONG
	if not (op == 0x13 and int(a["sub"]) == 0x10):
		var left := int(a["hp"]) - dmg
		if left <= 0:
			if int(a["hp"]) != 0:
				out["exp"] = int(kind["exp"])
			KFCreatureAI.switch_to(a, _with_op(kind, 3))
			a["hp"] = 0
		else:
			for rec in kind["behaviours"]:
				if int(rec[0]) != 2 or dmg < KFCreatureAI.u16f(rec, 0xC):
					continue
				if int(rec[2]) == 0xFF or (_rand() >> 7) < int(rec[2]):
					KFCreatureAI.switch_to(a, rec)
					break
			a["hp"] = left
	if point != null:
		var v := KFWeapon.knock(coll, dmg, int(kind["weight"]), point,
			Vector3i(int(a["px"]), int(a["py"]), int(a["pz"])), int(a["height"]))
		if not v.is_empty():
			a["vx"] = v[0]
			a["vy"] = v[1]
			a["vz"] = v[2]
	a["vst"] = 0x10
	out["hp"] = int(a["hp"])
	KFInfo.note("actors: f%d  slot %d  model %d  struck for %d, %d HP left%s" % [
		frame, k, a["model"], dmg, int(a["hp"]), "  -- dying" if int(a["hp"]) == 0 else ""])
	return out


# kind_behaviour_with_op for the creature in a slot, as a spell's aim asks
# it (0x8002c274): its kind's first behaviour with the opcode, or null.
# @port helper -- _with_op by a creature's slot
func behaviour_of(slot: int, op: int):
	var a = actors[slot] if slot < actors.size() else null
	if a == null or not kinds.has(int(a["kind"])):
		return null
	return _with_op(kinds[int(a["kind"])], op)


# 0x8004c068: the kind's first behaviour with that opcode.
# @orig game:0x8004c068 kind_behaviour_with_op  status:transcribed
func _with_op(kind: Dictionary, op: int):
	for rec in kind["behaviours"]:
		if int(rec[0]) == op:
			return rec
	return null


# 0x8004c1f0
# @orig game:0x8004c1f0 actor_activate  status:transcribed -- the rule for when a creature appears
func _activate(k: int, px: int, pz: int) -> void:
	var a: Dictionary = actors[k]
	var st: int = a["st"]
	var cat: int = a["cat"]
	if st == ACTIVE:
		if _dist(a, px, pz, a["deact"] << 11) == -1:
			_state(k, DORMANT, "left behind")
			_home(a)
		return
	if st == HELD:
		if cat == 3 or cat == 4:
			var lead = _leader(a)
			if lead != null and lead["st"] == ACTIVE:
				return
			_state(k, DORMANT, "its leader is gone")
			_home(a)
			return
		if _dist(a, px, pz, a["deact"] << 11) == -1:
			_state(k, DORMANT, "released")
			_home(a)
		return
	if st != DORMANT:
		return
	var d := _dist(a, px, pz, (a["act"] + 1) << 11)
	if d == -1:
		return
	if cat == 3 or cat == 4:
		var lead = _leader(a)
		if lead != null and lead["st"] == ACTIVE:
			_spawn(k)
		return
	if cat == 2:
		if a["chance"] != FREE and a["chance"] < (_rand() >> 4):
			return
		_try(k)
		return
	if d < (a["act"] << 11) and not spawn_anywhere:
		_block(k, "too near")
		return
	if cat == 1:
		_try(k)
		return
	if cat != 0 or a["chance"] == 0 or a["chance"] < (_rand() >> 7):
		_block(k, "lost the roll" if cat == 0 else "not woken by distance")
		return
	_try(k)


# 0x8004c380: spawn, unless 0x8004d644 finds the spot taken
# @orig game:0x8004c380 actor_activate+0x190  status:transcribed -- a label inside actor_activate
func _try(k: int) -> void:
	if _taken(k) != -1:
		_block(k, "spot taken")
		return
	_spawn(k)


# 0x8004c418: category 2 just waits; any other is held
# @orig game:0x8004c418 actor_activate+0x228  status:transcribed -- a label inside actor_activate
func _block(k: int, why: String) -> void:
	if actors[k]["cat"] != 2:
		_state(k, HELD, why)


# 0x8004b868 and 0x8004b698
# @orig game:0x8004b868 actor_spawn  status:transcribed
func _spawn(k: int) -> void:
	var a: Dictionary = actors[k]
	a["ry"] = a["yaw"]
	_home(a)
	_state(k, ACTIVE, "woken")
	if (a["flags"] & 1) == 0:
		a["ry"] = _rand() >> 3
	# actor_wake's AI bytes, and actor_activate's entrance (ai.gd)
	if kinds.has(int(a["kind"])):
		KFCreatureAI.wake(a, kinds[int(a["kind"])])
		a["hp"] = int(kinds[int(a["kind"])]["hp"])   # actor_copy_kind, +0x1a
	_place(k)


# actor_spot_taken as collide_query's bit 0x10 asks it for an effect: the
# first awake creature, not dying (+0xe 3), whose place -- +0x26 higher for a
# follower -- is within the asker's radius and its own, heights its own and
# the asker's. actor_skip_mask is 0 while the effects run (player_controller
# clears it at 0x80032104) and no creature is the one acting. The slot, or -1.
# @orig game:0x8004d644 actor_spot_taken  status:verified -- as collide_query asks it for the effects: tools/effects.py fire_world_check, 210 of 210 runs of the game's own, 34 hits on a creature; not the creatures a model's vertex places (flag 0x400000)
func spot_taken(x: int, y: int, z: int, r: int, own: int) -> int:
	for j in SLOTS:
		var o = actors[j]
		if o == null or o["st"] != ACTIVE or int(o.get("op", 0)) == 3:
			continue
		var ay := int(o["py"])
		if int(o.get("eflags", 0)) & 0x10:
			ay += int(o.get("lift", 0))
		if _in_range(o["px"], ay, o["pz"], x, y, z, int(o["radius"]) + r, o["height"],
				own) != -1:
			return j
	return -1


# Whether an awake creature has the cell marked: grid_mark (0x80033c4c) from
# actor_wake, actor_activate and actor_tick marks every cell within its
# radius + 0x800 of where it stands, which is what lets collide_query ask
# there after the creatures and the objects.
# @port helper -- a creature's grid_mark marks, asked by a cell
func marks_cell(cx: int, cz: int) -> bool:
	for o in actors:
		if o == null or o["st"] != ACTIVE:
			continue
		var reach := int(o["radius"]) + 0x800
		if cx >= (int(o["px"]) - reach) >> 11 and cx <= (int(o["px"]) + reach) >> 11 \
				and cz >= (int(o["pz"]) - reach) >> 11 and cz <= (int(o["pz"]) + reach) >> 11:
			return true
	return false


# 0x8004d644: another creature that is up and overlaps this one's place
# @orig game:0x8004d644 actor_spot_taken  status:transcribed
func _taken(k: int) -> int:
	var me: Dictionary = actors[k]
	for j in SLOTS:
		var o = actors[j]
		if o == null or j == k or o["st"] != ACTIVE:
			continue
		if _in_range(o["px"], o["py"], o["pz"], me["px"], me["py"], me["pz"],
				o["radius"] + me["radius"], o["height"], me["height"]) != -1:
			return j
	return -1


# the death branch of actor_tick, 0x80052b7c
# @orig game:0x80052b7c actor_tick+0x2ad4  status:transcribed -- the death branch, a label inside actor_tick
func _kill(k: int) -> void:
	var a: Dictionary = actors[k]
	match int(a["cat"]):
		1:
			_state(k, GONE, "killed: category 1 never comes back")
			_home(a)
		2:
			_state(k, DORMANT, "killed: category 2 may return at once")
			_home(a)
		5:
			a["cat"] = FREE
			_state(k, DORMANT, "killed: slot freed")
		_:
			_state(k, HELD, "killed: back after you leave, if the roll allows")
			_home(a)


# 0x80016ec8: the distance from (x, z) to the actor, or -1 beyond r. With y
# other than 0xffff the bodies must also overlap in height. KFCollision's,
# which tools/routines.py holds to the game's own answers.
# @port helper -- in_range through KFCollision
func _in_range(ax: int, ay: int, az: int, x: int, y: int, z: int, r: int,
		top := 0, own := 0) -> int:
	return coll.in_range(ax, ay, az, x, y, z, r, top, own)


# actor_in_range (0x8004d838), collide_query's flag 0x40: the first awake
# creature, dying or not, in_range of the point at its radius + r, with its
# height as the top and `own` the point's; -1 for none. It skips model 0x6e --
# actor +1 is the model, 696 of 696 in the level-0 snapshots, and 110 is kind
# 15 there -- and whatever actor_skip_mask names, which is 0 outside
# player_controller. An actor carrying entity flag 0x10 or 0x400000 is asked
# at another point; none on level 0 does.
# @orig game:0x8004d838 actor_in_range  status:transcribed -- the plain creature; flags 0x10 and 0x400000 not here
func in_range_of(x: int, y: int, z: int, r: int, own: int) -> int:
	for k in SLOTS:
		var a = actors[k]
		if a == null or a["st"] != ACTIVE or int(a["model"]) == 0x6E:
			continue
		if _in_range(a["px"], a["py"], a["pz"], x, y, z, int(a["radius"]) + r,
				a["height"], own) != -1:
			return k
	return -1


# actor_spot_taken (0x8004d644) as object_interact asks it before anything
# else: the first awake creature, in slot order, in range of the point -- the
# player's, 0x1f4 up -- at its radius + 0x578, its height as the top and 0xc80
# as the point's, whose flags have nothing in common with 4: object_interact
# runs inside player_controller, while actor_skip_mask is 4. The actor, or {}.
# @orig game:0x8004d644 actor_spot_taken  status:transcribed -- with r 0x578, own 0xc80 and the mask at 4
func talker(x: int, y: int, z: int) -> Dictionary:
	for k in SLOTS:
		var a = actors[k]
		if a == null or a["st"] != ACTIVE:
			continue
		if int(a["eflags"]) & 4:
			continue
		if _in_range(a["px"], a["py"], a["pz"], x, y, z, int(a["radius"]) + 0x578,
				a["height"], 0xC80) != -1:
			return a
	return {}


# The creatures the player can run into: every awake one (the game's +9 is 1),
# in slot order, as [x, y, z, radius, height, flags] -- flags the entity's
# +0x34, which the actor carries at +0x28. player.gd asks them as
# actor_spot_taken does.
# @port helper -- the awake creatures' shapes, which player.gd asks as actor_spot_taken does
func solid() -> Array:
	var out := []
	for k in SLOTS:
		var a = actors[k]
		if a != null and a["st"] == ACTIVE and int(a.get("op", 0)) != 3:
			out.append([a["px"], a["py"], a["pz"], a["radius"], a["height"],
				a["eflags"]])
	return out


# @port helper -- in_range with the height skipped (y 0xffff), the ring test actor_activate makes
func _dist(a: Dictionary, px: int, pz: int, r: int) -> int:
	return _in_range(a["px"], a["py"], a["pz"], px, NO_Y, pz, r)


# @port helper -- the actor in the slot its leader byte names
func _leader(a: Dictionary):
	var j: int = a["leader"]
	if j < 0 or j >= SLOTS:
		return null
	return actors[j]


# @port helper -- back to its placement, where actor_spawn puts it when it wakes
func _home(a: Dictionary) -> void:
	a["px"] = a["x"]
	a["py"] = a["y"]
	a["pz"] = a["z"]


# BIOS A0:2F, which is what rand at 0x800796c0 calls. The seed is not the
# game's: every other caller of rand moves the same sequence along.
# @orig game:0x800796c0 rand  status:transcribed -- BIOS A0:2F behind it; the seed is not the game's
func _rand() -> int:
	rand_next = (rand_next * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
	return (rand_next >> 16) & 0x7FFF


# @port helper -- writes the state, the game's +9, and logs the change
func _state(k: int, st: int, why: String) -> void:
	var a: Dictionary = actors[k]
	if a["st"] == st:
		return
	var line := "f%d  slot %d  model %d  category %d  %d -> %d  %s" % [
		frame, k, a["model"], a["cat"], a["st"], st, why]
	a["st"] = st
	changes += 1
	last.append(line)
	if last.size() > 5:
		last.remove_at(0)
	KFInfo.note("actors: " + line)


# @port check -- the nearest awake creature, for F10
func _nearest(px: int, pz: int, r: int) -> int:
	var best := -1
	var bd := r + 1
	for k in SLOTS:
		var a = actors[k]
		if a == null or a["st"] != ACTIVE:
			continue
		var d := _in_range(a["px"], a["py"], a["pz"], px, NO_Y, pz, r)
		if d != -1 and d < bd:
			best = k
			bd = d
	return best


# @orig game:0x80040b9c render_walk+0xb8  status:transcribed -- a creature is drawn while its +9 is 1; show_all is the port's
func refresh() -> void:
	for k in nodes:
		var a: Dictionary = actors[k]
		var n: Node3D = nodes[k]
		n.visible = show_all or (a["st"] == ACTIVE and a["cat"] != FREE)
		n.basis = _draw_basis(a)
	shown = changes
	var g := get_node_or_null("../Ghost")
	if g and not g.get("compare"):
		g.call("_hud", "")


# @port check -- the readout's lines
func summary() -> String:
	var n := [0, 0, 0, 0]
	for a in actors:
		if a != null and a["cat"] != FREE and a["st"] >= 0 and a["st"] < 4:
			n[a["st"]] += 1
	var s := "%d drawn, %d dormant, %d held, %d gone   F10 kills the nearest" % [
		n[ACTIVE], n[DORMANT], n[HELD], n[GONE]]
	if not last.is_empty():
		s += "\n" + "\n".join(last)
	return s

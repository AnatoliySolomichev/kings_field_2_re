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
# Not here: what an awake creature *does* -- the AI in actor_tick -- so an
# actor stands at home. X kills the nearest awake one, to try the rules on.

const TICK_HZ := 30.0          # player.gd's guess, so the same clock
const SLOTS := 200
const DORMANT := 0
const ACTIVE := 1
const HELD := 2
const GONE := 3
const NO_Y := 0xFFFF
const FREE := 0xFF

# What 0x8005efd4 writes for a level when the player leaves it -- slot and 3-or-0
# for every category-1 actor -- and apply_level_state puts back on the next
# load. Static, so it outlives world.tscn being loaded again.
static var saved := {}

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


func _ready() -> void:
	player = get_node_or_null("../Player")
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
	if saved.has(level):
		for pair in saved[level]:
			if actors[pair[0]] != null:
				actors[pair[0]]["st"] = pair[1]
	refresh()


func _exit_tree() -> void:
	var keep := []
	for k in SLOTS:
		var a = actors[k]
		if a != null and a["cat"] == 1:
			keep.append([k, GONE if a["st"] == GONE else DORMANT])
	saved[level] = keep


func _process(dt: float) -> void:
	if player == null or nodes.is_empty():
		return
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		_pass(int(player.get("gx")), int(player.get("gz")))
	if changes != shown:
		refresh()


func _unhandled_input(e: InputEvent) -> void:
	# X, because K is the pad's cross in pad.gd and N the labels
	if e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_X:
		if player == null:
			return
		var k := _nearest(int(player.get("gx")), int(player.get("gz")), 3 << 11)
		if k >= 0:
			_kill(k)
			refresh()


# actor_tick_driver: one game frame
# @orig game:0x80052e5c actor_tick_driver  status:transcribed -- the loop over the 199 slots
func _pass(px: int, pz: int) -> void:
	for k in SLOTS:
		var a = actors[k]
		if a == null or a["cat"] == FREE:
			continue
		if (frame & 3) == (k & 3) or spawn_anywhere:
			_activate(k, px, pz)
	frame += 1
	spawn_anywhere = false


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
# @orig game:0x8004c380  status:transcribed -- a label inside actor_activate
func _try(k: int) -> void:
	if _taken(k) != -1:
		_block(k, "spot taken")
		return
	_spawn(k)


# 0x8004c418: category 2 just waits; any other is held
# @orig game:0x8004c418  status:transcribed -- a label inside actor_activate
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
# @orig game:0x80052b7c  status:transcribed -- the death branch, a label inside actor_tick
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
# other than 0xffff the bodies must also overlap in height.
# @orig game:0x80016ec8 in_range  status:transcribed
func _in_range(ax: int, ay: int, az: int, x: int, y: int, z: int, r: int,
		top := 0, own := 0) -> int:
	var dx := ax - x
	if dx < -r or r < dx:
		return -1
	var dz := az - z
	if dz < -r or r < dz:
		return -1
	if y != NO_Y:
		if ay < y:
			if ay < y - own:
				return -1
		elif y < ay - top:
			return -1
	var sx := dx >> 3
	var sz := dz >> 3
	var dist := coll.isqrt(sx * sx + sz * sz) << 3
	return -1 if r < dist else dist


func _dist(a: Dictionary, px: int, pz: int, r: int) -> int:
	return _in_range(a["px"], a["py"], a["pz"], px, NO_Y, pz, r)


func _leader(a: Dictionary):
	var j: int = a["leader"]
	if j < 0 or j >= SLOTS:
		return null
	return actors[j]


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
	print("actors: " + line)


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


func refresh() -> void:
	for k in nodes:
		var a: Dictionary = actors[k]
		var n: Node3D = nodes[k]
		n.visible = show_all or (a["st"] == ACTIVE and a["cat"] != FREE)
		n.basis = Basis(Vector3.UP, -float(a["ry"]) * TAU / 4096.0)
	shown = changes
	var g := get_node_or_null("../Ghost")
	if g and not g.get("compare"):
		g.call("_hud", "")


func summary() -> String:
	var n := [0, 0, 0, 0]
	for a in actors:
		if a != null and a["cat"] != FREE and a["st"] >= 0 and a["st"] < 4:
			n[a["st"]] += 1
	var s := "%d drawn, %d dormant, %d held, %d gone   X kills the nearest" % [
		n[ACTIVE], n[DORMANT], n[HELD], n[GONE]]
	if not last.is_empty():
		s += "\n" + "\n".join(last)
	return s

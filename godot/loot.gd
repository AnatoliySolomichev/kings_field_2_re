extends Node
# Chests, and what the player takes out of them and off the floor.
#
# A small chest is three objects in one cell: the body (type 155), a lid of
# class 6 0x280 above it, and a class-0x40 thing inside that the lid hides on
# its first frame (object_mode 0); a big chest is one object of class 7. The
# arms that move them -- object_interpreter's for opcodes 6 (0x80048790) and 7
# (0x80048960) -- and object_give (0x8005db30), which hands a thing over, are
# tools/chests.py in Python, and FORMATS.md "Chests, and picking things up"
# has the reading. In short:
#
#   lid        USE -- object_interact, the lid within 0x155 of facing the
#              player and its lock 0xff -- writes 0xfe into the lock; the arm
#              then kicks its X angle by -0x10 and springs it to 0xa00
#              (spring_to, 8 and 4), showing what is inside, which can be
#              taken once the angle is under 0xc00: 82 frames from USE to
#              rest, and seven lids in the snapshots, one still moving, lie
#              on that path
#   big chest  the same lock; then a counter up by 0x80 a frame is its
#              model's animation clock, and at 0xfff what is inside is free
#   a thing    object_give, for a class-0x40 object whose +0x38 is 0xff.
#              Gold is counted at once, with a banner; anything else flies to
#              the eye while the view levels, spins until a button goes down,
#              and is taken on USE -- if give_item has room -- or put back
#
# Locks other than 0xff say why not (KFMessages): 0xf1 "Sealed", 0xf0 "Spell
# is Cast", an opened chest with nothing in it "Empty", and the rest --
# keys, in the main -- "Locked". The keys themselves are use_item's: try_key
# tries one on what is in front, and put_key stands Silviera's on a pedestal.
#
# A pedestal (opcode 0x18, level 4's type 0x101) holds a gate's bits: the key
# put on it is an object of its own in the ring of slots 380..395, which
# object_use_state moves down onto it over twenty frames; then the pedestal ORs
# its mask into its gate's lock (doors.gd), and USE opens the gate. Taken back
# -- object_give, while the gate is at rest -- the key leaves, and the mask
# with it.
#
# @exe game

const TICK_HZ := 15.0
const LID_OPEN := 0xA00
const LID_KICK := -0x10
const LID_ACCEL := 8
const LID_FRICTION := 4
const LID_FREE := 0xC00
const BIG_RATE := 0x80
const OPENED := 0xFE
const FREE := 0xFF
const GONE := 0xFF                 # the type of a thing taken
const NOTHING := 0xFFFF            # +0x3a when a chest holds nothing
const GOLD_KIND := 0x20            # the type row's +1 for gold
const NO_FACING := 0x95            # the one type find_object asks no facing of
const USE_UP := 0x1F4
const USE_REACH := 0x320
const USE_OWN := 0x9C4
const USE_FACING := 0x200
const LID_FACING := 0x155
const TALK_FACING := 0x12C         # object_interact's facing test for a talker
const EYE := 0x640
const FLIGHT := 0x200
const SPIN := 0x40
const TURN_BACK := 0x100
const TURN_TOL := 0x80
const ARROWS := 0x93
const LIGHT_ARROWS := 0x94

const KEY_RING := 380              # pedestal_put_key's find_free_slot(0x17c, 0x10, -1)
const KEY_RING_SIZE := 16
const KEY_START := [0, -0x600, 0x190]   # 0x8009c318: where the key is set down, turned by the pedestal
const KEY_END := [0, -0x500, 0]         # 0x8009c320: where it comes to rest
const KEY_FRAMES := 20             # the arm's last argument to object_use_state
const KEY_OP := 0x70               # the key on a pedestal: level_hooks+0x24, which on level 4 does nothing
const AT_REST := 0x63
const PEDESTAL := 0x101            # the pedestals Silviera's key is for
const PEDESTAL_KEYS := [0x86, 0x8D, 0x88]   # object_give's types that stand on a pedestal
const WRONG_KEY := 7

const SEALED := 5                  # the banners object_interact raises
const LOCKED := 6
const SPELL := 0x17
const EMPTY := 0x1A
const GOLD := 0x19

var after_service := false         # a service a conversation ended in is up
var player: Node3D
var rows := {}                     # slot -> row, lootNN.json and the state
var slots := []                    # in slot order, as object_interact asks
var acc := 0.0
var give := {}                     # object_give while it runs
var press := 0                     # a press latched for its next frame
var reading = null                 # the document up, load_entry's frames
var resume := 0                    # where object_interact goes on after it
var talking := {}                  # script_interpreter's call while it runs (KFTalk)
# What was opened, taken, dropped and set down goes where the game keeps it,
# the level's stream (KFLevelState): out of it when the level loads, into the
# level's table when it is left. The epoch this scene was made in, so that one
# made before a save was put back writes nothing; and the level's type rows'
# classes (lootNN.json's), which a thing made again is looked up in.
var made_epoch := -1
var classes: Array = []
# The level this scene is of. A crossing names the next one in KFGame before
# the scene goes, so leaving asks this, not KFGame.
var level := -1
# What a creature can leave when it dies (lootNN.json's "spawn"): type ->
# {the type row's fields, the hidden tNNN node a drop is copied from}.
var templates := {}
# The three rings of ten slots drops go to, and the count each keeps:
# 0x8019839a for the gold (350..359), 0x8019839c for a dying behaviour's thing
# (360..369), 0x8019839e for what a category-1 creature carried (370..379).
var counters := {0x15E: 0, 0x168: 0, 0x172: 0}
# The pedestals (lootNN.json's "pedestals"), each with its state, lock, ring
# place (+0x39) and count (+0x40); the keys one can hold (type -> {the type
# row's fields, the hidden qNNN node}); and find_object's view of every
# object the level places ("find").
var pedestals: Array = []
var key_templates := {}
var finds := {}
var held_locks := {}               # slot -> {op, state, lock}: an object a pedestal or a key asks of


# @port data -- reads lootNN.json, tools/level3d.py build_loot's rows, and finds their nodes
func _ready() -> void:
	player = get_node_or_null("../Player")
	if player == null:
		return
	var path := "res://loot%02d.json" % player._level()
	if not FileAccess.file_exists(path):
		return
	var doc = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(doc) != TYPE_DICTIONARY:
		return
	var objs := get_node_or_null("../Objects")
	for key in doc.get("spawn", {}):
		var t: Dictionary = doc["spawn"][key]
		var tn: Node3D = objs.find_child("t%03d" % int(key), true, false) if objs else null
		if tn:
			tn.visible = false
		templates[int(key)] = {"row": t, "node": tn}
	for key in doc.get("keys", {}):
		var tn: Node3D = objs.find_child("q%03d" % int(key), true, false) if objs else null
		if tn:
			tn.visible = false
		key_templates[int(key)] = {"row": doc["keys"][key], "node": tn}
	for row in doc.get("pedestals", []):
		var pd := {}
		for key in row:
			var v = row[key]
			pd[key] = int(v) if typeof(v) == TYPE_FLOAT else v
		pd["angles"] = (pd["angles"] as Array).map(func(v): return int(v))
		pd["tail"] = (pd["tail"] as Array).map(func(v): return int(v))
		pd["lock"] = int(pd["tail"][0])
		pd["ring"] = int(pd["tail"][1])
		pd["state"] = 0
		pd["n"] = 0
		pedestals.append(pd)
	for f in doc.get("find", []):
		finds[int(f[0])] = (f as Array).map(func(v): return int(v))
	for row in doc["rows"]:
		var r := {}
		for key in row:
			var v = row[key]
			r[key] = int(v) if typeof(v) == TYPE_FLOAT else v
		var ang := []
		for v in r["angles"]:
			ang.append(int(v))
		r["angles"] = ang
		r["node"] = objs.find_child("k%03d" % int(r["slot"]), true, false) if objs else null
		r["state"] = 0
		r["vel"] = 0
		r["counter"] = 0
		r["skin"] = {}
		r["pos"] = Vector3i(int(r["x"]), int(r["y"]), int(r["z"]))
		rows[int(r["slot"])] = r
	slots = rows.keys()
	slots.sort()
	classes = (doc.get("classes", []) as Array).map(func(v): return int(v))
	# the level's stream -- a table left last time written into it first --
	# over a fresh table of the placement, kept as the level in hand's
	made_epoch = KFLevelState.epoch
	var lv: int = player._level()
	level = lv
	var d := KFLevelState.decoded(lv)
	var table := KFLevelState.fresh_table(finds)
	KFLevelState.apply_table(table, d, classes, _rand_fn())
	KFLevelState.tables[lv] = table
	take_stream(d)


# The game's rand, for the reader's 0xf2: actors.gd's, which is the game's
# generator, when there is one.
# @port helper -- a Callable for rand()
func _rand_fn() -> Callable:
	var act := get_node_or_null("../Actors")
	if act and act.has_method("_rand"):
		return Callable(act, "_rand")
	return func() -> int: return 0


# The object section of a level's stream (KFLevelState.decode), over what this
# file keeps: an emptied slot's thing gone (its type 0xff), a lock put back
# (0xfd) -- a lid opened is 0xfe -- a pedestal's lock and its key's place in
# the ring (0xf4), and a thing made since the level was built made again
# (0xf0..0xf3), as apply_table made it. A slot of a class this file does not
# keep is doors.gd's, or only the table's.
# @orig game:0x8005f520 apply_level_state+0xdc  status:partial -- the object section over the chests, the things, the pedestals and the keys; 0xf5 (class 0x56) and the classes the port does not run are only in the table
func take_stream(d: Dictionary) -> void:
	if d.is_empty():
		return
	var made: Dictionary = d.get("made", {})
	var ops: Array = d["slots"]
	for s in ops.size():
		var row: Array = ops[s]
		var op := int(row[0])
		if op == 0xFF:
			if rows.has(s):
				rows[s]["type"] = GONE
		elif op == 0xFD:
			if rows.has(s):
				rows[s]["lock"] = int(row[1])
		elif op == 0xF4:
			for pd in pedestals:
				if int(pd["slot"]) == s:
					pd["lock"] = int(row[1])
					pd["ring"] = int(row[2])
		elif KFLevelState.KINDS.has(op):
			_made(s, made[s] if made.has(s) else KFLevelState.made(row, _rand_fn()))


# A thing the stream makes, in slot `s` (KFLevelState.made): its model off the
# template a drop or a key is copied from; at rest (+8 0x63) and free to take
# (+0x38 0xff), but for a key, whose +0x38 is the stream's and whose place
# object_use_state gives it. +0 is the layer select_cell_layer finds -- 2 the
# upper, 1 the lower -- and a key's 0, init_object_record's. What the game
# leaves at +0x3a -- a heap of gold's amount -- is whatever the slot held
# before, which a fresh level does not say; here it is 0.
# @orig game:0x8005f5fc apply_level_state+0x1b8  status:partial -- the made thing's place, +8, the layer and +0x38, as the reader writes them; +0x3a of gold (not in the stream) is 0 here
func _made(s: int, t: Dictionary) -> void:
	if rows.has(s):
		var old = rows[s].get("node")
		if old:
			(old as Node).queue_free()
		slots.erase(s)
	var typ := int(t["type"])
	var tp: Dictionary = templates.get(typ, key_templates.get(typ, {}))
	var tr: Dictionary = tp.get("row", {})
	var pos: Vector3i = t.get("pos", Vector3i.ZERO)
	var b0 := 0
	if t.has("pos"):
		b0 = 1
		var cx := pos.x >> 11
		var cz := pos.z >> 11
		var c: KFCollision = player.coll
		if cx >= 0 and cx < KFCollision.W and cz >= 0 and cz < KFCollision.W \
				and c._layer((cz * KFCollision.W + cx) * 6, pos.y) != 0:
			b0 = 2
	var r := {"slot": s, "cls": 0x40, "type": typ, "kind": int(tr.get("kind", 0)),
		"count": 0, "reach": int(tr.get("reach", 0)), "top": int(tr.get("top", 0)),
		"c": int(tr.get("c", 0)), "e": int(tr.get("e", 0)), "lock": int(t["lock"]),
		"b0": b0, "b1": 0x80, "inside": 0, "op": int(t["kind"]), "state": int(t["state"]),
		"vel": 0, "rest": int(t["rest"]), "angles": t["angles"], "skin": {}, "model": 0,
		"link": 0, "pos": pos, "node": null}
	var tn = tp.get("node")
	if tn:
		var nd := (tn as Node3D).duplicate() as Node3D
		nd.name = "k%03d" % s
		(tn as Node3D).get_parent().add_child(nd)
		r["node"] = nd
	rows[s] = r
	slots.append(s)
	slots.sort()
	KFInfo.note("save: type %d made again in slot %d" % [typ, s])


# What the chests, the things and the pedestals are as the level is left, into
# its table: a thing taken is an empty slot, the rest their type, kind, place,
# yaw and lock -- and +0x3a for kind 0x62, the angle it comes to rest at -- and
# a pedestal its lock and its key's place; then the table is final, and
# KFLevelState writes it into the level's stream when the level is next asked
# for (level_state_write, which object_trigger and player_controller call as
# the level is left).
# @port engine -- the port's objects into the writer's table
func _exit_tree() -> void:
	if player == null or made_epoch != KFLevelState.epoch:
		return
	var lv := level
	var table: Array = KFLevelState.tables.get(lv, [])
	if table.is_empty():
		return
	for k in rows:
		var r: Dictionary = rows[k]
		var typ := int(r["type"])
		if typ == GONE:
			table[k] = null
			continue
		var e = table[k]
		var old: Array = e if e != null else [GONE, 0x40, 0, 0, 0, 0, 0, FREE, 0, 0]
		var op := int(r.get("op", old[2]))
		var p: Vector3i = r["pos"]
		table[k] = [typ, int(classes[typ]) if typ < classes.size() else int(old[1]), op,
			p.x, p.y, p.z, int(r["angles"][1]) & 0xFFFF, int(r["lock"]), int(old[8]),
			int(r["rest"]) if op == 0x62 else int(old[9])]
	for pd in pedestals:
		var e = table[int(pd["slot"])]
		if e != null:
			e[7] = int(pd["lock"])
			e[8] = int(pd["ring"])
	KFLevelState.left[lv] = true


# @port engine -- USE into _interact, the arms at 15 a second, and object_give's own frames while it runs
func _process(dt: float) -> void:
	if rows.is_empty():
		return
	if after_service:
		# the shop the conversation's end opened, until it closes
		var menu = get_node_or_null("../UI/Menu")
		if menu != null and str(menu.state) != "":
			return
		after_service = false
		KFGame.modal = false
		player.clear_movement()
		_interact(0, true)
		return
	if not talking.is_empty():
		var doc = get_node_or_null("../UI/Document")
		if doc == null or not doc.is_open():
			var use := 0
			if doc != null and not KFPad.binding.is_empty():
				use = int(doc.closed_by) & KFPad.binding[KFPad.USE]
			KFTalk.closed(talking, use != 0)
			_talk_next()
		return
	if reading != null:
		if not reading.is_open():
			reading = null
			KFGame.modal = false
			player.clear_movement()
			_interact(resume, true)
		return
	if not give.is_empty():
		# object_give reads the pad itself: a press is a word that is not 0
		# after one that was
		if KFPad.prev == 0 and KFPad.now != 0 and press == 0:
			press = KFPad.now
		acc = minf(acc + dt, 0.25)
		while acc >= 1.0 / TICK_HZ and not give.is_empty():
			acc -= 1.0 / TICK_HZ
			var p := press
			press = 0
			if not give_step(give, p & KFPad.binding[KFPad.USE] if not KFPad.binding.is_empty() else 0, p != 0):
				_give_done()
		_draw()
		return
	if KFPad.hit(KFPad.USE) and not KFGame.modal:
		_interact(0)
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		if KFGame.modal:
			continue
		for k in slots:
			var r: Dictionary = rows[k]
			var op := int(r["op"])
			if op == 6:
				lid_step(r, func(m: int, v: int) -> void: _mode(r, m, v))
			elif op == 7:
				big_step(r, func(m: int, v: int) -> void: _mode(r, m, v))
			elif op >= 0x60 and op <= 0x62 and int(r["state"]) != 0x63:
				var p: Vector3i = r["pos"]
				fall_step(r, player.coll.surface(p.x, p.y, p.z))
		for pd in pedestals:
			_pedestal(pd)
	_draw()


# spawn_gold (0x80046294) and spawn_thing (0x800460bc), for a drop tools/ai.py's way --
# ai.gd's drops: an object in the next slot from 350, the type's model copied
# from its template, +0x38 0xff so it can be taken as it falls, and the fall
# its type row's +1 picks; the gold falls by 0x62 from a velocity of -0x78.
# @orig game:0x80046294 spawn_gold  status:transcribed -- the object in the ring from 350
# @orig game:0x800460bc spawn_thing  status:transcribed -- the thing a creature leaves: the fall by the type row's +1, the angle 0x62 brings it to, the doubled scale (in the template)
func spawn(d: Dictionary) -> void:
	var typ := int(d["type"])
	if not templates.has(typ):
		return
	var t: Dictionary = templates[typ]["row"]
	var ring := int(d.get("ring", 0x15E))
	var made := free_slot(ring, int(counters[ring]))
	if made < 0:
		return
	counters[ring] = (int(counters[ring]) + 1) & 0xFFFF
	if rows.has(made):                  # a thing taken, or the oldest: gone now
		var old = rows[made].get("node")
		if old:
			(old as Node).queue_free()
		slots.erase(made)
	var r := {"slot": made, "cls": 0x40, "type": typ, "kind": int(t["kind"]),
		"count": int(counters[ring]),
		"reach": int(t["reach"]), "top": int(t["top"]), "c": int(t["c"]),
		"e": int(t["e"]), "lock": FREE, "b0": 2, "b1": 0x80,
		"inside": int(d["amount"]), "op": int(t["op"]), "state": 0,
		"vel": -0x78 if typ == 0x95 else 0, "rest": int(t["rest"]),
		"angles": [0, int(d["yaw"]), 0], "skin": {}, "model": 0,
		"pos": Vector3i(int(d["pos"][0]), int(d["pos"][1]), int(d["pos"][2]))}
	var tn: Node3D = templates[typ]["node"]
	if tn:
		var nd := tn.duplicate() as Node3D
		nd.name = "k%03d" % made
		tn.get_parent().add_child(nd)
		r["node"] = nd
	else:
		r["node"] = null
	rows[made] = r
	slots.append(made)
	slots.sort()
	KFInfo.note("drop: type %d%s in slot %d" % [typ,
		(" (%d gold)" % int(d["amount"])) if typ == 0x95 else "", made])


# find_free_slot (0x80046034): of the ten slots from `start`, the first whose
# type is 0xff -- never used, or taken -- else the oldest by the count at its
# +0x3c, `count` minus it, mod 0x10000. -1 when every one is as new as now.
# @orig game:0x80046034 find_free_slot  status:transcribed
func free_slot(start: int, count: int) -> int:
	var oldest := -1
	var age := 0
	for i in 10:
		var k := start + i
		if not rows.has(k) or int(rows[k]["type"]) == GONE:
			return k
		var dv := count - int(rows[k].get("count", 0))
		if dv < 0:
			dv += 0x10000
		if age < dv:
			age = dv
			oldest = k
	return oldest


# Opcodes 0x60, 0x61 and 0x62 (0x8004b228, 0x8004b300, 0x8004b388): a thing
# made where a creature died, falling to `floor` -- collide_surface under it.
#   0x60  y += velocity, velocity += 0x14; at the floor a velocity of 0x10 for
#         the X angle, += 0x10 a frame, to 0x400: lying flat
#   0x61  y += 0x14 and the yaw += 0x100 a frame, to the floor
#   0x62  y += velocity, the X angle 0xa0 one way or the other, velocity +=
#         0x1e; at the floor under 0x50 it lies, else it bounces with half the
#         velocity and the turn reversed; lying, its X angle goes to the rest
#         by 0xa0 a frame (0x80015f18)
# State 0x63 is at rest. tools/chests.py fall_step; three things lying in the
# snapshots rest with the velocity it gives.
# @orig game:0x8004b228 object_interpreter+0x4218  status:transcribed -- opcode 0x60
# @orig game:0x8004b300 object_interpreter+0x42f0  status:transcribed -- opcode 0x61
# @orig game:0x8004b388 object_interpreter+0x4378  status:transcribed -- opcode 0x62; not the splash where it crosses the water (sub_80056268), nor the layer it writes to +0
static func fall_step(o: Dictionary, floor_y: int) -> void:
	var op := int(o["op"])
	var st := int(o["state"])
	var p: Vector3i = o["pos"]
	var ang: Array = o["angles"]
	if op == 0x60:
		if st == 0:
			p.y += int(o["vel"])
			o["vel"] = KFWeapon.s16(int(o["vel"]) + 0x14)
			if p.y >= floor_y:
				p.y = floor_y
				o["vel"] = 0x10
				o["state"] = 1
		elif st == 1:
			ang[0] = (int(ang[0]) + int(o["vel"])) & 0xFFFF
			o["vel"] = KFWeapon.s16(int(o["vel"]) + 0x10)
			if KFWeapon.s16(int(ang[0])) >= 0x400:
				ang[0] = 0x400
				o["state"] = 0x63
	elif op == 0x61:
		if st == 0:
			p.y += 0x14
			ang[1] = (int(ang[1]) + 0x100) & 0xFFF
			if p.y >= floor_y:
				p.y = floor_y
				o["state"] = 0x63
	elif op == 0x62:
		if st < 2:
			p.y += int(o["vel"])
			ang[0] = (int(ang[0]) + (0xA0 if st == 0 else -0xA0)) & 0xFFF
			var v := KFWeapon.s16(int(o["vel"]) + 0x1E)
			o["vel"] = v
			if v >= 0 and p.y >= floor_y:
				if v < 0x50:
					p.y = floor_y
					o["state"] = 2
				else:
					o["vel"] = -(v >> 1)
					o["state"] = 1 if st == 0 else 0
		elif st == 2:
			ang[0] = approach_angle(int(ang[0]), int(o["rest"]), 0xA0) & 0xFFFF
			if KFWeapon.s16(int(ang[0])) == KFWeapon.s16(int(o["rest"])):
				o["state"] = 0x63
	o["pos"] = p


# 0x80015f18: a towards b by step the short way round, onto b when the step
# would pass it. tools/chests.py approach_angle.
# @orig game:0x80015f18 angle_approach  status:transcribed
static func approach_angle(a: int, b: int, step: int) -> int:
	a &= 0xFFF
	b &= 0xFFF
	if a == b:
		return b
	if a < b:
		if b - a < 0x801:
			var n := KFWeapon.s16(a + step)
			return b if b < n else n
		var n2 := (a - step) & 0xFFF
		if n2 < 0x800:
			return n2
		return n2 if b < n2 else b
	if a - b < 0x801:
		var n3 := KFWeapon.s16(a - step)
		return b if n3 < b else n3
	var n4 := (a + step) & 0xFFF
	if n4 >= 0x801:
		return n4
	return n4 if n4 < b else b


# object_mode (0x80044900) on what a chest holds: 0 takes it away, its +0
# and +0x38 zeroed; 1 puts its +0 back; 2 makes its +0x38 0xff, so it can be
# taken. Modes 3 and the big chest's 0xc8 write +0xe, which only the drawing
# reads (the model's light), and the port leaves.
# @orig game:0x80044900 object_mode  status:partial -- modes 0 to 2 for class 0x40; +0xe (mode 3) not carried
func _mode(chest: Dictionary, mode: int, value: int) -> void:
	var r = rows.get(int(chest["inside"]))
	if r == null:
		return
	match mode:
		0:
			r["b0"] = 0
			r["lock"] = 0
		1:
			r["b0"] = value
		2:
			r["lock"] = FREE


# One frame of opcode 6's arm on d (state, angles, vel, lock); `mode` is
# object_mode on what is inside. tools/chests.py lid_step.
# @orig game:0x80048790 object_interpreter+0x1780  status:verified -- opcode 6's arm: 8 of 8 opened lids in the snapshots on its path, one of them moving (tools/chests.py); not the trap, +0x3c
static func lid_step(d: Dictionary, mode: Callable) -> void:
	var st := int(d["state"])
	var ang: Array = d["angles"]
	if st == 0:
		if int(d["lock"]) == OPENED:
			ang[0] = LID_OPEN
			d["state"] = 3
		else:
			mode.call(0, 0)
			mode.call(3, 0)
			d["state"] = 1
	elif st == 1:
		if int(d["lock"]) == OPENED:
			d["vel"] = LID_KICK
			d["state"] = 2
			mode.call(1, 2)
	elif st == 2:
		var v := _spring_to(LID_OPEN, int(ang[0]), int(d["vel"]))
		d["vel"] = v
		ang[0] = (int(ang[0]) + v) & 0xFFF
		if int(ang[0]) < LID_FREE:
			mode.call(2, 0)
		if v == 0 and int(ang[0]) == LID_OPEN:
			d["state"] = 3


# One frame of opcode 7's arm on d (state, counter, lock). tools/chests.py big_step.
# @orig game:0x80048960 object_interpreter+0x1950  status:transcribed -- opcode 7's arm; not recorded, no snapshot holds one opened
static func big_step(d: Dictionary, mode: Callable) -> void:
	var st := int(d["state"])
	if st == 0:
		mode.call(4, 0xC8)
		if int(d["lock"]) == OPENED:
			d["counter"] = 0xFFF
			d["state"] = 3
		else:
			mode.call(0, 0)
			mode.call(3, 0)
			d["state"] = 1
	elif st == 1:
		if int(d["lock"]) == OPENED:
			d["state"] = 2
			mode.call(1, 2)
	elif st == 2:
		d["counter"] = (int(d["counter"]) + BIG_RATE) & 0xFFFF
		if int(d["counter"]) >= 0xFFF:
			mode.call(2, 0)
			d["counter"] = 0xFFF
			d["state"] = 3


# spring_to (0x80016168), as player.gd has it.
# @orig game:0x80016168 spring_to  status:transcribed
static func _spring_to(target: int, cur: int, vel: int) -> int:
	var d := (target - cur) & 0xFFF
	var tol := LID_ACCEL >> 1
	if (d <= tol or d >= 0x1000 - tol) and vel >= -LID_ACCEL and vel <= LID_ACCEL:
		return target - cur
	if cur != target:
		vel += -LID_ACCEL if ((cur - target) & 0xFFF) < 0x801 else LID_ACCEL
	if vel > 0:
		return vel - LID_FRICTION
	if vel < 0:
		return vel + LID_FRICTION
	return vel


# object_interact (0x8005e2d0) for the chests and the things: every object
# find_object offers in front -- in_range of the player's point 0x1f4 up at the
# type's +6 plus 0x320, the type's +8 as its top and 0x9c4 as the point's, and
# within 0x200 of the facing -- in slot order from `from`. A lid must also face
# the player within 0x155. After a thing is taken the walk stops.
# @orig game:0x8005e2d0 object_interact  status:partial -- the talker first, then classes 6, 7, 0x40, 0x0d and 0x14 (.L13, .L26, .L28, .L38); doors.gd has the doors, and no save point is here
# @orig game:0x80045c7c find_object  status:partial -- the plain test, for a class past 2
func _interact(from: int, talked := false) -> void:
	var c: KFCollision = player.coll
	var px: int = player.gx
	var py: int = player.gy + USE_UP
	var pz: int = player.gz
	if from == 0 and not talked:
		# the creature in front, within 0x12c of the facing: script_interpreter
		var an := get_node_or_null("../Actors")
		if an and an.has_method("talker"):
			var a: Dictionary = an.talker(px, py, pz)
			if not a.is_empty() and _facing(player.facing,
					c.vec_angle(int(a["px"]) - px, int(a["pz"]) - pz), TALK_FACING):
				if _talk(a):
					return
	for i in range(from, slots.size()):
		var r: Dictionary = rows[slots[i]]
		if int(r["type"]) == GONE:
			continue
		var p: Vector3i = r["pos"]
		if c.in_range(p.x, p.y, p.z, px, py, pz, int(r["reach"]) + USE_REACH,
				int(r["top"]), USE_OWN) < 0:
			continue
		if int(r["type"]) != NO_FACING and not _facing(player.facing,
				c.vec_angle(p.x - px, p.z - pz), USE_FACING):
			continue
		match int(r["cls"]):
			6:
				if _facing(player.facing, (int(r["angles"][1]) + 0x800) & 0xFFF, LID_FACING):
					_lock(r)
			7:
				_lock(r)
			0x40:
				if _give(r, i):
					return
			0x0D, 0x14:
				if _read(r, i):
					return


# object_interact's .L38: something to read, while its +0x3e is not 0 --
# facing it within 0x155 unless its +0x3d says not to ask -- shows ITEM.T
# entry 0x96 + its u16 at +0x38 (load_entry, godot/document.gd). True when the
# walk is to wait for it.
# @orig game:0x8005e7c4 object_interact+0x4f4  status:transcribed
func _read(r: Dictionary, at: int) -> bool:
	if int(r["on"]) == 0:
		return false
	if int(r["facing"]) == 0 and not _facing(player.facing,
			(int(r["angles"][1]) + 0x800) & 0xFFF, LID_FACING):
		return false
	var d = get_node_or_null("../UI/Document")
	if d == null or not d.open(int(r["text"])):
		return false
	reading = d
	resume = at + 1
	KFGame.modal = true
	KFInfo.note("read: slot %d, ITEM.T %d" % [int(r["slot"]), 0x96 + int(r["text"])])
	return true


# script_interpreter for the talker: its conversation (escript.json, by the
# actor's kind, the entity), one call (KFTalk). False when it has none, and
# object_interact goes straight on to the objects.
# @orig game:0x8005e3a4 object_interact+0xd4  status:transcribed -- the call of script_interpreter, after the talker test
func _talk(a: Dictionary) -> bool:
	var lv: int = player._level()
	var sc := KFTalk.script_for(lv, int(a["kind"]))
	if sc.is_empty():
		return false
	talking = KFTalk.begin(lv, int(a["kind"]), sc, int(a["model"]))
	KFGame.modal = true
	_talk_next()
	return true


# The call's next line through load_entry (TALK.T, talk/N.png), or its end:
# then the object walk from the first object, as object_interact goes on.
# @port engine -- the lines of a call shown one after another through document.gd
func _talk_next() -> void:
	var lv: int = player._level()
	var doc = get_node_or_null("../UI/Document")
	while true:
		var entry := KFTalk.advance(talking,
			func(x: int) -> void: KFTalk.hook(lv, x, player.inventory))
		if entry < 0:
			break
		if doc != null and doc.open_path("res://talk/%d.png" % entry):
			KFInfo.note("talk: TALK.T %d, pc %d" % [entry, int(talking["pc"])])
			return
		KFTalk.closed(talking, false)       # no page: as if closed without USE
	# .L19, the end of the call: the service of the header's +0x12
	var svc := int(talking["sc"]["header"]["service"])
	talking = {}
	if svc != KFTalk.NO_SERVICE and svc & 0xF0 == 0x00:
		var menu = get_node_or_null("../UI/Menu")
		if menu != null:
			menu.open_shop(svc & 0xF)
			after_service = true
			return
	KFGame.modal = false
	player.clear_movement()
	_interact(0, true)


# use_item's arm for the keys (0x8005d188): royal, copper, silver, magician's,
# jail, dwarves' and Lyn's. find_object offers each object in front of the
# player -- from the player's own place this time, 0x320 more than the type's
# reach, 0x6a4 as the point's height, within 0x200 of the facing -- and the key
# is tried on it (0x80046608): 1 it fitted and the lock is 0xff now, open to
# USE; 3 or 4 "Wrong key!"; anything else the next object. The key is kept.
# The chests and pedestals here and the doors and gates in doors.gd are
# offered in slot order.
# @orig game:0x8005d188 use_item+0x5a8  status:transcribed -- the keys' arm; not the sound when one fits (sound_key_fits)
func try_key(key: int) -> int:
	var c: KFCollision = player.coll
	var offered := []
	for k in slots:
		offered.append([int(k), rows[k], "lock"])
	var dn := get_node_or_null("../Doors")
	if dn:
		for d in dn.doors:
			offered.append([int(d["slot"]), d, "door"])
		for d in dn.lifts:
			offered.append([int(d["slot"]), d, "lift"])
		for d in dn.gates:
			offered.append([int(d["slot"]), d, "lock"])
	for pd in pedestals:
		offered.append([int(pd["slot"]), pd, "lock"])
	offered.sort_custom(func(a, b): return int(a[0]) < int(b[0]))
	for o in offered:
		var r: Dictionary = o[1]
		if int(r.get("type", 0)) == GONE:
			continue
		var p: Vector3i = r["pos"] if r.has("pos") else Vector3i(int(r["x"]), int(r["y"]), int(r["z"]))
		var px: int = player.gx
		var pz: int = player.gz
		var top := int(r.get("top", r.get("height", 0)))
		if str(o[2]) == "door":
			# find_object's point for a class-1 door: 0x400 back along its yaw
			var yaw := int(r["yaw"])
			px += (c.game_cos(yaw) * -0x400) >> 12
			pz += (c.game_sin(yaw) * -0x400) >> 12
			top = int(r["height"])
		if c.in_range(p.x, p.y, p.z, px, player.gy, pz, int(r["reach"]) + 0x320, top, 0x6A4) < 0:
			continue
		if int(r.get("type", 0)) != NO_FACING and not _facing(player.facing,
				c.vec_angle(p.x - px, p.z - pz), 0x200):
			continue
		var got := key_test(r, str(o[2]), key)
		if got == 1:
			KFInfo.note("key: item %d opens the lock of slot %d" % [key, int(o[0])])
			return 1
		if got == 3 or got == 4:
			KFMessages.announce(7)                     # "Wrong key!"
			KFInfo.note("key: item %d does not fit slot %d" % [key, int(o[0])])
			return got
	return 0


# 0x80046608: a key tried on an object, by its opcode -- the doors 0..5 and
# 0x1b while they stand still, the chests 6..8 and 0x17, 0x18, 0x1a ask their
# lock: 0xfe or 0xff already open (2), the key's own number opens it (1, the
# lock 0xff), anything else wrong (3); 0xf, 0x11 and 0xa7 are wrong whatever
# the key (4); the rest are not for keys (0).
# @orig game:0x80046608 key_test  status:transcribed
static func key_test(r: Dictionary, kind: String, key: int) -> int:
	var op := int(r["op"])
	if op == 0x11 or op == 0xF or op == 0xA7:
		return 4
	var asks := op in [6, 7, 8, 0x17, 0x18, 0x1A]
	if op <= 5 or op == 0x1B:
		if int(r.get("state", 0)) != 0:
			return 0
		asks = true
	if not asks:
		return 0
	var lock := int(r["tail"][0]) if kind != "lock" else int(r["lock"])
	if lock >= 0xFE:
		return 2
	if lock != key:
		return 3
	if kind != "lock":
		r["tail"][0] = 0xFF
	else:
		r["lock"] = 0xFF
	return 1


# use_item's arm for Silviera's key (0x8005d244): find_object's first object
# in front of the player -- from their own place, 0x320 past its reach, 0x6a4
# as the point's height, within 0x200 of the facing -- and that one only. A
# type-0x101 pedestal whose lock is 0xff takes the key: the lock the key's
# number, the state 0, the key out of the pack, and pedestal_put_key stands
# it there (1). Anything else has the key tried on it, and a 3 is "Wrong
# key!" (1); the rest is 0, "Nothing happens" -- a key that fits too, which
# the shared arm would have answered with its sound.
# @orig game:0x8005d244 use_item+0x664  status:transcribed -- held to silv1 and silv2 through tools/chests.py check_pedestal
func put_key(item: int) -> int:
	var k := find_object(0, Vector3i(player.gx, player.gy, player.gz), 0x320, 0x6A4,
		int(player.facing), 0x200)
	if k < 0:
		return 0
	for pd in pedestals:
		if int(pd["slot"]) != k or int(pd["type"]) != PEDESTAL:
			continue
		if int(pd["lock"]) != FREE:
			return 0
		pd["lock"] = item
		pd["state"] = 0
		player.inventory.take_item(item)
		_put_key(pd, item)
		KFInfo.note("key: item %d put on the pedestal in slot %d" % [item, k])
		return 1
	var o := _lockable(k)
	if not o.is_empty() and key_test(o[0], str(o[1]), item) == 3:
		KFMessages.announce(WRONG_KEY)
		KFInfo.note("key: item %d does not fit slot %d" % [item, k])
		return 1
	return 0


# pedestal_put_key (0x8005c7e8): the first free slot of the ring 380..395 --
# find_free_slot with no count, so never the oldest -- gets the key's type
# and +0x38 0, and the pedestal's +0x39 its place in the ring. The object is
# a copy of the key's hidden qNNN node; object_use_state places it.
# @orig game:0x8005c7e8 pedestal_put_key  status:verified -- silv1 to silv2 (tools/chests.py): the ring's first slot, free before, holds the key's type after, and the pedestal's +0x39 names it
func _put_key(pd: Dictionary, item: int) -> void:
	var made := -1
	for i in KEY_RING_SIZE:
		if not rows.has(KEY_RING + i) or int(rows[KEY_RING + i]["type"]) == GONE:
			made = KEY_RING + i
			break
	if made < 0:
		return
	if rows.has(made):
		var old = rows[made].get("node")
		if old:
			(old as Node).queue_free()
		slots.erase(made)
	pd["ring"] = made - KEY_RING
	var tp: Dictionary = key_templates.get(item, {})
	var t: Dictionary = tp.get("row", {})
	var r := {"slot": made, "cls": 0x40, "type": item, "kind": int(t.get("kind", 0)),
		"reach": int(t.get("reach", 0)), "top": int(t.get("top", 0)),
		"c": int(t.get("c", 0)), "e": int(t.get("e", 0)), "lock": 0, "b0": 0,
		"b1": 0x80, "inside": 0, "op": 0xFF, "state": 0, "vel": 0, "rest": 0,
		"angles": [0, 0, 0], "skin": {}, "model": 0, "link": 0, "pos": Vector3i.ZERO,
		"node": null}
	var tn = tp.get("node")
	if tn:
		var nd := (tn as Node3D).duplicate() as Node3D
		nd.name = "k%03d" % made
		(tn as Node3D).get_parent().add_child(nd)
		r["node"] = nd
	rows[made] = r
	slots.append(made)
	slots.sort()


# One frame of opcode 0x18's arm (0x8004aeb8) on a pedestal `p` with its key
# (the object in slot 380 + its +0x39, or null) and the object its tail[3]
# names, `gate`. A pedestal not at state 0 whose key is gone -- taken, its
# type 0xff -- goes back to state 0 with the lock 0xff, and the gate loses
# its mask (tail[5], or tail[2] when that is 0xff); then object_use_state,
# and on the frame the key comes to rest the gate's lock takes tail[2]. True
# on that frame. tools/chests.py pedestal_step.
# @orig game:0x8004aeb8 object_interpreter+0x3ea8  status:verified -- 72 of 72 frames of the game's own arm, run over silv1 by tools/mipsrun.py (three pedestals, to rest and the key taken), as tools/chests.py pedestal_step, whose end silv2 holds; not the type-0x86 key's view on level 23 (gp+0x10e)
static func pedestal_step(p: Dictionary, key, gate: Dictionary, c: KFCollision) -> bool:
	var t: Array = p["tail"]
	if int(p["state"]) != 0 and key != null and int(key["type"]) == GONE:
		p["lock"] = FREE
		p["state"] = 0
		var mask := int(t[5]) if int(t[5]) != 0xFF else int(t[2])
		gate["lock"] = int(gate["lock"]) & ~mask & 0xFF
	if key == null or not use_state(p, key, c):
		return false
	gate["lock"] = int(gate["lock"]) | int(t[2])
	return true


# object_use_state (0x80046914) as the pedestal's arm calls it, with
# (0x8009c318, 0x8009c320, 0, 20). At state 0 with a lock other than 0xff the
# key is set up -- init_object_record, opcode 0x70, the pedestal's +0, +1
# 0x80, the pedestal's slot at its +0x40 and its yaw -- the count 19 if the
# key's +0x38 is not 0, else 0, and state 1; and in the same call, as at
# state 1, the count goes up and the key stands at the pedestal plus
# fixed_madd from KEY_START to KEY_END, both turned by the pedestal's angles,
# count / 20 of the way. At 20 the key's +0x38 is 0xff, free to take, the
# state 0x63, and the answer true.
# @orig game:0x80046914 object_use_state  status:verified -- with the pedestal's arguments: the same 72 frames of the game's own code, and silv2's end; not the sound (0x12)
static func use_state(p: Dictionary, key: Dictionary, c: KFCollision) -> bool:
	if int(p["state"]) == 0:
		if int(p["lock"]) == FREE:
			return false
		p["n"] = KEY_FRAMES - 1 if int(key["lock"]) != 0 else 0
		p["state"] = 1
		key["op"] = KEY_OP
		key["b0"] = int(p["b0"])
		key["b1"] = 0x80
		key["link"] = int(p["slot"])
		key["angles"] = [0, int(p["angles"][1]), 0]
	if int(p["state"]) != 1:
		return false
	p["n"] = (int(p["n"]) + 1) & 0xFF
	var t: int = (int(p["n"]) << 12) / KEY_FRAMES
	var ang: Array = p["angles"]
	var a: Array = KFWeapon.vec_rotate(c, int(ang[0]), int(ang[1]), int(ang[2]), KEY_START)
	var b: Array = KFWeapon.vec_rotate(c, int(ang[0]), int(ang[1]), int(ang[2]), KEY_END)
	key["pos"] = Vector3i(lerp_i(int(a[0]), int(b[0]), t) + int(p["x"]),
		lerp_i(int(a[1]), int(b[1]), t) + int(p["y"]),
		lerp_i(int(a[2]), int(b[2]), t) + int(p["z"]))
	if int(p["n"]) < KEY_FRAMES:
		return false
	key["lock"] = FREE
	p["state"] = AT_REST
	return true


# @port helper -- a pedestal's frame: its key out of the rows, its gate out of doors.gd
func _pedestal(p: Dictionary) -> void:
	var ring := int(p["ring"])
	var key = rows.get(KEY_RING + ring) if ring < KEY_RING_SIZE else null
	var gate := _gate_of(int(p["tail"][3]))
	var was := int(p["state"])
	if pedestal_step(p, key, gate, player.coll):
		KFInfo.note("pedestal: the key stands on slot %d, and the lock of slot %d is %d" % [
			int(p["slot"]), int(p["tail"][3]), int(gate["lock"])])
	elif was != 0 and int(p["state"]) == 0:
		KFInfo.note("pedestal: the key is gone from slot %d, and the lock of slot %d is %d" % [
			int(p["slot"]), int(p["tail"][3]), int(gate["lock"])])


# @port helper -- the slot a pedestal's tail[3] names, from the pedestal's slot (a key's +0x40)
func _pedestal_target(slot: int) -> int:
	for pd in pedestals:
		if int(pd["slot"]) == slot:
			return int(pd["tail"][3])
	return -1


# The object in `slot` as the dictionary that holds its lock: a gate of
# doors.gd's, or one kept here for anything else a pedestal names.
# @port helper -- the object a pedestal serves, by slot
func _gate_of(slot: int) -> Dictionary:
	var dn := get_node_or_null("../Doors")
	if dn:
		for d in dn.gates:
			if int(d["slot"]) == slot:
				return d
	if not held_locks.has(slot):
		var f: Array = finds.get(slot, [])
		held_locks[slot] = {"op": int(f[10]) if f.size() > 11 else 0xFF, "state": 0,
			"lock": int(f[11]) if f.size() > 11 else 0xFF}
	return held_locks[slot]


# What key_test is to ask of the object in `slot`: [its dictionary, the kind]
# -- a chest's or a pedestal's lock, a door's or a lift's tail, a gate's lock
# -- or, for an object the port does not move, its opcode and lock as placed.
# @port helper -- the object find_object found, for key_test
func _lockable(slot: int) -> Array:
	if rows.has(slot):
		return [rows[slot], "lock"]
	for pd in pedestals:
		if int(pd["slot"]) == slot:
			return [pd, "lock"]
	var dn := get_node_or_null("../Doors")
	if dn:
		for d in dn.doors:
			if int(d["slot"]) == slot:
				return [d, "door"]
		for d in dn.lifts:
			if int(d["slot"]) == slot:
				return [d, "lift"]
	if finds.has(slot):
		return [_gate_of(slot), "lock"]
	return []


# find_object (0x80045c7c): from slot `start` on, the first object whose type
# is not 0xff within `add` past its type's reach (+6) of the point `pt` --
# `own` as the point's height -- and, but for type 0x95, within `tol` of
# `facing`. A class-0 door is asked from 0x700 behind the point along its own
# yaw, a class-0x1b one from 0x700 ahead and a class-1 door from 0x400
# behind, the record's +0xc as its top; anything else from the point itself,
# the type's +8 its top. Over the objects as they are now: lootNN.json's find
# rows, with what loot.gd has made and taken and a swinging door's yaw.
# @orig game:0x80045c7c find_object  status:transcribed -- the plain test and the three doors' points, over every object
func find_object(start: int, pt: Vector3i, add: int, own: int, facing: int, tol: int) -> int:
	var c: KFCollision = player.coll
	var yaws := {}
	var dn := get_node_or_null("../Doors")
	if dn:
		for d in dn.doors:
			yaws[int(d["slot"])] = int(d["yaw"])
	var order: Array = finds.keys()
	for k in rows:
		if not finds.has(int(k)):
			order.append(int(k))
	order.sort()
	for k in order:
		if int(k) < start:
			continue
		var cls := 0x40
		var typ := GONE
		var o := Vector3i.ZERO
		var yaw := 0
		var height := 0
		var reach := 0
		var top := 0
		if finds.has(k):
			var f: Array = finds[k]
			cls = int(f[1])
			typ = int(f[2])
			o = Vector3i(int(f[3]), int(f[4]), int(f[5]))
			yaw = int(f[6])
			height = int(f[7])
			reach = int(f[8])
			top = int(f[9])
		if rows.has(k):
			var r: Dictionary = rows[k]
			typ = int(r["type"])
			o = r["pos"]
			if not finds.has(k):
				cls = int(r["cls"])
				reach = int(r["reach"])
				top = int(r["top"])
		if typ == GONE:
			continue
		yaw = int(yaws.get(k, yaw))
		var px := pt.x
		var pz := pt.z
		var door := cls == 0 or cls == 1 or cls == 0x1B
		if door:
			var off := 0x700 if cls == 0x1B else (-0x700 if cls == 0 else -0x400)
			px += (c.game_cos(yaw) * off) >> 12
			pz += (c.game_sin(yaw) * off) >> 12
			top = height
		if c.in_range(o.x, o.y, o.z, px, pt.y, pz, reach + add, top, own) < 0:
			continue
		if not door and typ == NO_FACING:
			return int(k)
		if _facing(facing, c.vec_angle(o.x - px, o.z - pz), tol):
			return int(k)
	return -1


# object_interact's .L28: what a chest's lock says to USE.
# @orig game:0x8005e704 object_interact+0x434  status:transcribed
func _lock(r: Dictionary) -> void:
	var lock := int(r["lock"])
	if lock == 0xF1:
		KFMessages.announce(SEALED)
	elif lock == 0xF0:
		KFMessages.announce(SPELL)
	elif lock == OPENED:
		var inside = rows.get(int(r["inside"]))
		if int(r["inside"]) == NOTHING or (inside != null and int(inside["type"]) == GONE):
			KFMessages.announce(EMPTY)
	elif lock == FREE:
		r["lock"] = OPENED
		KFInfo.note("chest: slot %d opens" % int(r["slot"]))
	else:
		KFMessages.announce(LOCKED)
		KFInfo.note("chest: slot %d is locked, lock byte %d" % [int(r["slot"]), lock])


# object_give (0x8005db30) up to its own frames: not a thing whose +0x38 is
# not 0xff; gold counted at once; anything else starts the flight. True when
# the walk is to wait for it.
# @orig game:0x8005db30 object_give  status:partial -- the gold, the start of the flight, and a key on a pedestal kept while its gate moves (.L3); not type 0x85 on level 7, nor +0xe
func _give(r: Dictionary, at: int) -> bool:
	if int(r["lock"]) != FREE:
		return false
	# a key standing on a pedestal (opcode 0x70) stays while the object the
	# pedestal serves is a gate on the move
	if int(r["op"]) == KEY_OP and int(r["type"]) in PEDESTAL_KEYS:
		var g := _gate_of(_pedestal_target(int(r.get("link", 0))))
		if int(g.get("op", 0)) == 2 and int(g.get("state", 0)) != 0:
			return false
	if int(r["kind"]) == GOLD_KIND:
		KFMessages.announce(GOLD, int(r["inside"]))
		r["type"] = GONE
		player.gold += int(r["inside"])
		KFInfo.note("gold: %d from slot %d, %d in all" % [int(r["inside"]), int(r["slot"]), player.gold])
		return false
	var view: int = player.view_pitch_now()
	give = give_start(r, Vector3i(player.gx, player.gy, player.gz), view,
		int(player.facing), player.coll)
	give["resume"] = at + 1
	give["items"] = player.inventory
	KFInfo.note("take: item %d from slot %d flies to the eye -- USE takes it" % [
		int(r["type"]), int(r["slot"])])
	press = 0
	KFGame.modal = true
	return true


# object_give's frames, a step at a time: give_start sets them up, and every
# call of give_step draws one -- the flight in (t = 0, 0x200 .. 0x1000), the
# spin, and on a press the turn back and the flight back, or on USE the flight
# away to the side. tools/chests.py give_frames is the same.
# @orig game:0x8005be28 object_give_point  status:transcribed -- the point ahead of the eye, and the one to the side
static func eye_point(c: KFCollision, player: Vector3i, pitch: int, facing: int,
		v: Array, dy: int) -> Vector3i:
	var r := KFWeapon.vec_rotate(c, KFWeapon.s16(-pitch), facing, 0, v)
	return Vector3i(int(r[0]) + player.x, int(r[1]) - EYE + dy + player.y,
		int(r[2]) + player.z)


# @port helper -- object_give's set-up: where it flies from and to, and the view's pitch
static func give_start(r: Dictionary, player: Vector3i, view_pitch: int, facing: int,
		c: KFCollision) -> Dictionary:
	var s7 := view_pitch & 0xFFF
	var s3 := 0
	if s7 >= 0x800:
		s3 = 0xFFF
	var a0: Array = (r["angles"] as Array).duplicate()
	return {"row": r, "c": c, "player": player, "facing": facing, "s7": s7, "s3": s3,
		"level": s3,
		"start": r["pos"], "a0": a0,
		"front": eye_point(c, player, s3, facing, [0, 0x1F4 + int(r["c"]),
			0x5DC + int(r["e"])], int(r["c"])),
		"a1": [0, (facing + 0x800) & 0xFFF, 0],
		"phase": 0, "t": 0, "pitch": s7, "taken": false}


# fixed_madd (0x80017158).
# @orig game:0x80017158 fixed_madd  status:transcribed
static func lerp_i(a: int, b: int, t: int) -> int:
	return a + (((b - a) * t) >> 12)


# 0x80017170: from a towards b the short way round, by t / 0x1000.
# @orig game:0x80017170 angle_lerp  status:transcribed
static func angle_lerp(a: int, b: int, t: int) -> int:
	var d := (KFWeapon.s16(b) - KFWeapon.s16(a)) & 0xFFF
	if d >= 0x801:
		d -= 0x1000
	return (a + ((d * t) >> 12)) & 0xFFF


# One frame of object_give. `pressed` says a button went down since the last
# frame, `use` that USE did. False when it has drawn its last frame.
# @orig game:0x8005dda4 object_give+0x274  status:transcribed -- the frames: the flight, the spin, give_item, the turn back and the flight out (tools/chests.py give_frames)
static func give_step(g: Dictionary, use: int, pressed: bool) -> bool:
	var r: Dictionary = g["row"]
	while true:
		match int(g["phase"]):
			0, 1:                       # the flight in, then the spin
				if pressed:
					pressed = false
					_decide(g, use != 0)
					continue
				if int(g["phase"]) == 0:
					var t := int(g["t"])
					var s: Vector3i = g["start"]
					var f: Vector3i = g["front"]
					r["pos"] = Vector3i(lerp_i(s.x, f.x, t), lerp_i(s.y, f.y, t), lerp_i(s.z, f.z, t))
					var a0: Array = g["a0"]
					var a1: Array = g["a1"]
					r["angles"] = [angle_lerp(int(a0[0]), int(a1[0]), t),
						angle_lerp(int(a0[1]), int(a1[1]), t), angle_lerp(int(a0[2]), int(a1[2]), t)]
					g["pitch"] = angle_lerp(int(g["s7"]), int(g["s3"]), t)
					g["t"] = t + FLIGHT
					if t + FLIGHT > 0x1000:
						g["phase"] = 1
				else:
					var ang: Array = r["angles"]
					ang[1] = (int(ang[1]) + SPIN) & 0xFFFF
				return true
			2:                          # turning back to face the player
				var ang: Array = r["angles"]
				var want := (int(g["facing"]) + 0x800) & 0xFFF
				if _facing(int(ang[1]), want, TURN_TOL):
					ang[1] = want
					_out(g, g["start"], g["a0"])
					continue
				ang[1] = (int(ang[1]) + TURN_BACK) & 0xFFF
				return true
			3:                          # the flight out
				var t := int(g["t"])
				if t < 0:
					return false
				var s: Vector3i = g["from"]
				var f: Vector3i = g["to"]
				r["pos"] = Vector3i(lerp_i(s.x, f.x, t), lerp_i(s.y, f.y, t), lerp_i(s.z, f.z, t))
				var a0: Array = g["a_from"]
				var a1: Array = g["a_to"]
				r["angles"] = [angle_lerp(int(a0[0]), int(a1[0]), t),
					angle_lerp(int(a0[1]), int(a1[1]), t), angle_lerp(int(a0[2]), int(a1[2]), t)]
				g["pitch"] = angle_lerp(int(g["s7"]), int(g["s3"]), t)
				g["t"] = t - FLIGHT
				return true
	return false


# object_give's .L14: USE takes it if give_item has room -- arrows bring
# 4 to 9 more, light arrows 4 -- else, or for any other button, it goes back.
# @orig game:0x8005dff0 object_give+0x4c0  status:transcribed -- the decision and give_item; the arrows' extra by the port's random, not rand(); not the level's hook give_item calls
static func _decide(g: Dictionary, use: bool) -> void:
	var r: Dictionary = g["row"]
	var take := false
	if use and g.has("items"):
		var items: KFItems = g["items"]
		take = items.give_item(int(r["type"]))
		if not take:
			KFMessages.announce(KFItems.FULL_MESSAGE)
		elif int(r["type"]) == ARROWS:
			var more := ((6 * (randi() & 0x7FFF)) >> 15) + 4
			var n := int(items.a[ARROWS])
			items.a[ARROWS] = n + more if n < KFItems.CAP - more else KFItems.CAP
		elif int(r["type"]) == LIGHT_ARROWS:
			var n := int(items.a[LIGHT_ARROWS])
			items.a[LIGHT_ARROWS] = n + 4 if n < 0x5F else KFItems.CAP
	elif use and g.has("take"):
		take = bool(g["take"])             # the self-test says what give_item says
	if take:
		g["taken"] = true
		var pocket := eye_point(g["c"], g["player"], int(g["level"]), int(g["facing"]),
			[-0x1F4, 0x1F4, 0], 0)
		g["s3"] = int(g["pitch"])          # .L27 reads the view's pitch again
		_out(g, pocket, (r["angles"] as Array).duplicate())
	else:
		g["s3"] = int(g["pitch"])
		g["phase"] = 2


# @port helper -- the flight out, from `frm` (t = 0) to where it is (t = 0x1000)
static func _out(g: Dictionary, frm: Vector3i, a_from: Array) -> void:
	var r: Dictionary = g["row"]
	g["from"] = frm
	g["to"] = r["pos"]
	g["a_from"] = a_from.duplicate()
	g["a_to"] = (r["angles"] as Array).duplicate()
	g["t"] = 0x1000
	g["phase"] = 3


# object_give's end: a thing taken is gone (type 0xff); then
# clear_movement_state, and object_interact goes on with the next object
# unless a thing was taken.
# @orig game:0x8005e284 object_give+0x754  status:transcribed
func _give_done() -> void:
	var r: Dictionary = give["row"]
	var taken := bool(give["taken"])
	var resume := int(give["resume"])
	KFInfo.note("take: slot %d %s" % [int(r["slot"]), "taken" if taken else "put back"])
	if taken:
		r["type"] = GONE
	give = {}
	KFGame.modal = false
	player.view_pitch = -1
	player._view()
	player.clear_movement()
	if not taken:
		_interact(resume, true)


# @port engine -- the nodes: a lid turned by its angles, a big chest posed by its counter, a thing shown while it is there
func _draw() -> void:
	for k in slots:
		var r: Dictionary = rows[k]
		var nd: Node3D = r["node"]
		if nd == null:
			continue
		nd.visible = int(r["b0"]) != 0 and int(r["type"]) != GONE
		if not nd.visible:
			continue
		var p: Vector3i = r["pos"]
		var a: Array = r["angles"]
		nd.transform = Transform3D(game_basis(int(a[0]), (int(a[1]) + 0x800) & 0xFFF, int(a[2])),
			Vector3(p.x, -p.y, -p.z) / 1000.0)
		if int(r["op"]) == 7:
			if (r["skin"] as Dictionary).is_empty():
				if not KFAnim.models.has(int(r["model"])):
					KFAnim.load_from("res://anim%02d.json" % player._level())
				r["skin"] = KFAnim.skin(nd, int(r["model"]))
			if not (r["skin"] as Dictionary).is_empty():
				KFAnim.animate(r["skin"], int(r["b1"]), int(r["counter"]))
	if not give.is_empty():
		player.view_pitch = int(give["pitch"])
		player._view()


# The game's turn (0x800166f4: Ry . Rx . Rz) in Godot's axes, x kept and y
# and z flipped: F M F with F = diag(1, -1, -1).
# @port helper -- the matrix tools/level3d.py's _rot3 and quaternion make, at run time
static func game_basis(rx: int, ry: int, rz: int) -> Basis:
	var k := TAU / 4096.0
	var cx := cos(rx * k)
	var sx := sin(rx * k)
	var cy := cos(ry * k)
	var sy := sin(ry * k)
	var cz := cos(rz * k)
	var sz := sin(rz * k)
	# Rx . Rz, then Ry on the left
	var m := [
		[cz, -sz, 0.0],
		[cx * sz, cx * cz, -sx],
		[sx * sz, sx * cz, cx]]
	var g := [
		[cy * m[0][0] - sy * m[2][0], cy * m[0][1] - sy * m[2][1], cy * m[0][2] - sy * m[2][2]],
		m[1],
		[sy * m[0][0] + cy * m[2][0], sy * m[0][1] + cy * m[2][1], sy * m[0][2] + cy * m[2][2]]]
	var f := [1.0, -1.0, -1.0]
	var col := func(j: int) -> Vector3:
		return Vector3(f[0] * f[j] * g[0][j], f[1] * f[j] * g[1][j], f[2] * f[j] * g[2][j])
	return Basis(col.call(0), col.call(1), col.call(2))


# facing_test (0x80016a2c).
# @orig game:0x80016a2c facing_test  status:transcribed
static func _facing(a: int, b: int, tol: int) -> bool:
	var d := (a - b) & 0xFFF
	return d <= tol or d >= 0x1000 - tol

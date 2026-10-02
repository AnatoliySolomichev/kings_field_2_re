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
# keys, in the main -- "Locked". The keys themselves are use_item's, and not
# here.
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

const SEALED := 5                  # the banners object_interact raises
const LOCKED := 6
const SPELL := 0x17
const EMPTY := 0x1A
const GOLD := 0x19

var player: Node3D
var rows := {}                     # slot -> row, lootNN.json and the state
var slots := []                    # in slot order, as object_interact asks
var acc := 0.0
var give := {}                     # object_give while it runs
var press := 0                     # a press latched for its next frame
var reading = null                 # the document up, load_entry's frames
var resume := 0                    # where object_interact goes on after it
var talking := {}                  # script_interpreter's call while it runs (KFTalk)
# What was opened and taken, by level, across the reload a revive makes:
# {level: {slot: [type, lock, +0]}} -- the game keeps it in level_state.
static var saved := {}


# @port data -- reads lootNN.json, tools/level3d.py build_loot's rows, and finds their nodes
func _ready() -> void:
	player = get_node_or_null("../Player")
	if player == null:
		return
	var path := "res://loot%02d.json" % player._level()
	if not FileAccess.file_exists(path):
		return
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(d) != TYPE_ARRAY:
		return
	var objs := get_node_or_null("../Objects")
	for row in d:
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
	var kept: Dictionary = saved.get(player._level(), {})
	for k in kept:
		if rows.has(k):
			rows[k]["type"] = int(kept[k][0])
			rows[k]["lock"] = int(kept[k][1])
			rows[k]["b0"] = int(kept[k][2])


# @port data -- what was opened and taken, kept for the next load of the level
func _exit_tree() -> void:
	if player == null or rows.is_empty():
		return
	var kept := {}
	for k in rows:
		var r: Dictionary = rows[k]
		kept[k] = [int(r["type"]), int(r["lock"]), int(r["b0"])]
	saved[player._level()] = kept


# @port engine -- USE into _interact, the arms at 15 a second, and object_give's own frames while it runs
func _process(dt: float) -> void:
	if rows.is_empty():
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
			if int(r["op"]) == 6:
				lid_step(r, func(m: int, v: int) -> void: _mode(r, m, v))
			elif int(r["op"]) == 7:
				big_step(r, func(m: int, v: int) -> void: _mode(r, m, v))
	_draw()


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
# @orig game:0x80048790 object_interpreter+0x1780  status:verified -- opcode 6's arm: 7 of 7 opened lids in the snapshots on its path, one of them moving (tools/chests.py); not the trap, +0x3c
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
			return
		KFTalk.closed(talking, false)       # no page: as if closed without USE
	talking = {}
	KFGame.modal = false
	player.clear_movement()
	_interact(0, true)


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
	else:
		KFMessages.announce(LOCKED)


# object_give (0x8005db30) up to its own frames: not a thing whose +0x38 is
# not 0xff; gold counted at once; anything else starts the flight. True when
# the walk is to wait for it.
# @orig game:0x8005db30 object_give  status:partial -- the gold and the start of the flight; not the special cases of types 0x86, 0x88, 0x8d with opcode 0x70 or 0x85 on level 7, nor +0xe
func _give(r: Dictionary, at: int) -> bool:
	if int(r["lock"]) != FREE:
		return false
	if int(r["kind"]) == GOLD_KIND:
		KFMessages.announce(GOLD, int(r["inside"]))
		r["type"] = GONE
		player.gold += int(r["inside"])
		return false
	var view: int = player.view_pitch_now()
	give = give_start(r, Vector3i(player.gx, player.gy, player.gz), view,
		int(player.facing), player.coll)
	give["resume"] = at + 1
	give["items"] = player.inventory
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

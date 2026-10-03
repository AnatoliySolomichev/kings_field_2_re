extends Node
# The doors that swing: object_interpreter's arm for opcode 1 (0x8004814c).
#
# load_object_placement gives each such door (class 0x01) opcode 1 and stamps
# its closed state into the grid: stamp_rect copies a w x h block of cells from
# a template the level keeps out of sight -- source (p[+0x13] + 1, p[+0x14]),
# destination (p[+0x11], p[+0x12]) -- so the doorway's collision shape is a wall.
# It also stores its yaw twice, at +0x26 and +0x42, and leaves +8, the state, 0.
#
# Pressing USE -- X, in the scheme the port starts with -- runs object_interact
# (0x8005e2d0), which asks find_object for
# the object in front and, for a door whose state is 0 and whose lock byte (+0x38)
# is 0xff -- or 0xfd or 0xfe, unless the type is 0xae -- sets the state to 1. Any
# other lock byte is a key or a message, and nothing here opens those.
#
# Then, once a frame, the arm (listing at 0x8004814c):
#
#   state 1:         state 2, counter 0, remember which way the player faces
#   counter < 0x20:  yaw += 0x20 -- a quarter turn in 32 frames; while the
#                    counter is under 0x15 and the player is in the swing, shove
#                    them 0x4c along the door's facing and set their speeds
#     counter 0x18:  stamp the open state, from the template one cell to the
#                    left of the closed one
#     counter 0x1f:  jump the counter to 0x118 -- twenty frames of standing open
#   counter 0x12c:   if anything stands in the doorway, stay here; otherwise stamp
#                    the closed state again (template two cells to the right of
#                    the open one) and start back
#   counter < 0x14c: yaw -= 0x20
#   after:           state 0, done
#
# Two snapshots bear it out: door1 holds the door of slot 114 closed after a full
# cycle -- state 0, counter 0x14d, the doorway's shape 46 -- and door2 the same
# door open -- state 2, counter 0x121, yaw a quarter turn on, shape 64 in both
# cells of the doorway. And a recording follows it frame by frame: emu/bp24.lua
# caught two full cycles of that door, once waiting at 0x12c while the player
# stood in the doorway, and tools/doors.py -- the same arm in Python -- steps
# 226 of 226 of its frames to the game's state, counter, yaw and doorway.
#
# "Anything stands in the doorway" is collide_query(point, door y, 0x5dc, the
# door's height, 0xc0): the cell's occupancy count must be non-zero -- the door
# marked its own cells at load, so for a door it always is -- and then 0x40 asks
# every awake creature and 0x80 asks player_in_range (0x80028e48), which is
# in_range(player, point, 0x5dc + 0x320, 0x6a4, the door's height). Only the
# player is asked here: the port's creatures stand at home. And a stamp here
# changes the collision, not the drawn tile.
#
# @exe game

const TICK_HZ := 15.0              # frame_limit; see player.gd
const OPENING := 0x20
const SHOVE_UNTIL := 0x15
const STAMP_OPEN := 0x18
const LAST_SWING := 0x1f
const WAIT_FROM := 0x118
const CLOSE_AT := 0x12c
const DONE_AT := 0x14c
const SWING := 0x20                # yaw a frame
const SHOVE := -0x4c
const MASK := 0x2d                 # stamp_rect: tile, rotation, shape, a bit of +9
const CLEAR := 0x5dc               # the radius collide_query is asked about
const PLAYER_R := 0x320            # player_in_range adds it
const PLAYER_BODY := 0x6a4         # and passes it as the player's top

# The doors that lift: opcodes 3, 4 and 5, one arm written three times
# (0x800470c4, 0x80047290, 0x80047444) with its own pair of stamp_table tables.
# Shut, such a door is a piece of wall the grid draws: the loader stamped the
# wall tile into its two cells and a solid shape under them, and its model has
# a scale of 0. USE sets its state to 1 -- object_interact, through
# find_object's plain test for any class past 2: in_range of the player's point
# 0x1f4 up at the type's +6 plus 0x320, the type's +8 as the door's top and
# 0x9c4 as the point's, and the door within 0x200 of the facing; then state 0
# and a lock byte of 0xff. Then, a frame at a time (tools/doors.py):
#
#   state 1        at counter 0 the tile table open -- 0xfc, which draw_terrain
#                  does not draw -- and the scale 0x1000, so the model shows;
#                  counter += 0x48; at 0xc18 the shape table open; from
#                  0x1000 on, counter 0xfff and state 2
#   state 2..0x13  state += 1: eighteen frames standing open
#   state 0x14     wait until collide_query(the door, 0x700, 0xc80, 0xc0) is
#                  clear, then the shape table shut and state 0x15
#   state 0x15     counter -= 0x48; at 0 or under, the tile table shut, and
#                  counter, state and scale 0
#
# The model is drawn by draw_model_plain animated -- the animation the
# record's +1 names, 0, at the clock of the counter -- so it rises as the
# counter does: model 299's one animation lifts the slab 0xf80 over 0x1000.
const LIFT_OPS := [3, 4, 5]
const LIFT_RATE := 0x48
const LIFT_PASSABLE := 0xC18
const LIFT_OPEN := 0xFFF
const LIFT_WAIT := 0x14
const LIFT_CLEAR := 0x700          # collide_query's radius for the doorway
const LIFT_OWN := 0xC80            # and its height
const USE_UP := 0x1F4              # object_interact's point, above the feet
const USE_REACH := 0x320           # find_object's $a2, added to the type's +6
const USE_OWN := 0x9C4             # find_object's $a3, the point's height
const USE_FACING := 0x200
const DRAWN := 0xF0                # draw_terrain skips a tile at or above this (0x8003c1b8)

var doors: Array = []
var lifts: Array = []
var player: Node3D
var acc := 0.0


# @port data -- reads doorsNN.json, the doors tools/level3d.py finds in the placement, and finds their nodes
func _ready() -> void:
	player = get_node_or_null("../Player")
	if player == null:
		return
	var path := "res://doors%02d.json" % player._level()
	if not FileAccess.file_exists(path):
		return
	var rows = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(rows) != TYPE_ARRAY:
		return
	var objs := get_node_or_null("../Objects")
	var level := get_node_or_null("../Level")
	for row in rows:
		var d: Dictionary = row
		if int(d["op"]) in LIFT_OPS:
			d["node"] = objs.find_child("l%03d" % int(d["slot"]), true, false) if objs else null
			d["tiles"] = level.find_child("t%03d" % int(d["slot"]), true, false) if level else null
			d["state"] = 0
			d["counter"] = 0
			d["scale"] = 0
			d["skin"] = {}
			# the drawn tile of each cell of the tile table, as the loader left it
			var hi := int(d["hi"])
			var drawn := []
			for e in d["stamps"][1]:
				drawn.append(int(e[2][2 if hi == 3 else 3]))
			d["drawn"] = drawn
			if d["node"]:
				d["node"].visible = false
			lifts.append(d)
			continue
		d["node"] = objs.find_child("d%03d" % int(d["slot"]), true, false) if objs else null
		d["yaw0"] = int(d["yaw"])
		d["state"] = 0
		d["counter"] = 0x3e7
		d["push"] = 0
		doors.append(d)


# @port engine -- USE into _interact, the arms at 15 a second, the nodes turned to the yaw
func _process(dt: float) -> void:
	if doors.is_empty() and lifts.is_empty():
		return
	if KFGame.modal:                  # object_give's frames: they stand still
		return
	if KFPad.hit(KFPad.USE):
		_interact()
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		for d in doors:
			if int(d["state"]) != 0:
				_step(d)
		for d in lifts:
			if int(d["state"]) != 0:
				_lift(d)
	for d in doors:
		if d["node"]:
			# rot_matrix_y is cos, -sin / sin, cos, so with y and z flipped the
			# game's Ry(t) is a turn of +t about Godot's up axis.
			d["node"].rotation.y = float(int(d["yaw"]) - int(d["yaw0"])) * TAU / 4096.0
	for d in lifts:
		_draw_lift(d)


# object_interact for the doors: find_object's point for class 1 is the player,
# 0x1f4 up, moved 0x400 back along the door's own yaw; it must be within the
# type's reach plus 0x320 of the door, and the door within 0x200 of the facing.
# @orig game:0x8005e2d0 object_interact  status:partial -- classes 1 and 3 to 5: state 0 and the lock
# @orig game:0x80045c7c find_object  status:partial -- its point and tests for class 1 and for a class past 2 (0x80045f30)
func _interact() -> void:
	var c: KFCollision = player.coll
	# find_object's test for a class past 2 (0x80045f30) and object_interact's
	# arm for classes 3 to 5 (0x8005e2d0, .L17): state 0 and the lock 0xff
	for d in lifts:
		if int(d["state"]) != 0 or int(d["tail"][0]) != 0xFF:
			continue
		var py: int = player.gy + USE_UP
		if _in_range(int(d["x"]), int(d["y"]), int(d["z"]), player.gx, py, player.gz,
				int(d["reach"]) + USE_REACH, int(d["top"]), USE_OWN) < 0:
			continue
		if not _facing(player.facing,
				c.vec_angle(int(d["x"]) - player.gx, int(d["z"]) - player.gz), USE_FACING):
			continue
		d["state"] = 1
		KFInfo.note("door: the lift door in slot %d opens" % int(d["slot"]))
	for d in doors:
		if int(d["state"]) != 0:
			continue
		var lock := int(d["tail"][0])
		if not (lock == 0xFF or ((lock == 0xFD or lock == 0xFE) and int(d["type"]) != 0xAE)):
			continue
		var yaw := int(d["yaw"])
		# Ry(yaw) . (-0x400, 0, 0) = (cos * -0x400, 0, sin * -0x400)
		var px: int = player.gx + ((c.game_cos(yaw) * -0x400) >> 12)
		var pz: int = player.gz + ((c.game_sin(yaw) * -0x400) >> 12)
		if _in_range(int(d["x"]), int(d["y"]), int(d["z"]), px, player.gy + 0x1f4, pz,
				int(d["reach"]) + 0x320, int(d["height"]), 0x9c4) < 0:
			continue
		var ang := c.vec_angle(int(d["x"]) - px, int(d["z"]) - pz)
		if not _facing(player.facing, ang, 0x200):
			continue
		d["state"] = 1
		KFInfo.note("door: the door in slot %d swings" % int(d["slot"]))


# @orig game:0x8004814c object_interpreter+0x113c  status:verified -- opcode 1's arm: the swing, the shove, the stamps and the wait; 226 of 226 recorded steps (emu/bp24.lua, tools/doors.py)
func _step(d: Dictionary) -> void:
	var c: KFCollision = player.coll
	if int(d["state"]) == 1:
		d["state"] = 2
		d["counter"] = 0
		d["push"] = player.facing
	var n := int(d["counter"])
	d["counter"] = n + 1
	if n < OPENING:
		if n < SHOVE_UNTIL and _facing((int(d["push"]) + 0x800) & 0xFFF, int(d["yaw0"]), 0x384) \
				and _facing(int(d["push"]),
					c.vec_angle(int(d["x"]) - player.gx, int(d["z"]) - player.gz), 0x400):
			# Ry(a) . (0, 0, -0x4c) = (-sin * -0x4c, 0, cos * -0x4c)
			var a := (int(d["yaw0"]) + 0x800) & 0xFFF
			player.gx += (-c.game_sin(a) * SHOVE) >> 12
			player.gz += (c.game_cos(a) * SHOVE) >> 12
			player.stf_speed = 0
			player.fwd_speed = SHOVE
		d["yaw"] = int(d["yaw"]) + SWING
		if n == STAMP_OPEN:
			_stamp(d, 0)
		elif n == LAST_SWING:
			d["counter"] = WAIT_FROM
		return
	if n < CLOSE_AT:
		return
	if n < DONE_AT:
		if n == CLOSE_AT:
			var a := int(d["yaw0"])
			var qx: int = int(d["x"]) + ((c.game_cos(a) * 0x400) >> 12)
			var qz: int = int(d["z"]) + ((c.game_sin(a) * 0x400) >> 12)
			# @orig game:0x80028e48 player_in_range  status:transcribed
			if _in_range(player.gx, player.gy, player.gz, qx, int(d["y"]), qz,
					CLEAR + PLAYER_R, PLAYER_BODY, int(d["height"])) >= 0:
				d["counter"] = CLOSE_AT
				return
			_stamp(d, 2)
		d["yaw"] = int(d["yaw"]) - SWING
		return
	d["state"] = 0


# @port helper -- hands lift_step the doorway test and the stamps
func _lift(d: Dictionary) -> void:
	lift_step(d, func() -> bool: return _lift_clear(d),
		func(t: int, sel: int) -> void: _stamp_table(d, t, sel))


# One frame of the lift arm (0x800470c4) on d's state, counter and scale;
# `clear` answers collide_query about the doorway and `stamp(t, sel)` lays
# table t down. tools/doors.py lift_step, which selftest.gd holds this to.
# @orig game:0x800470c4 object_interpreter+0xb4  status:verified -- opcode 3's arm: the lift, the stamps and the wait; 2016 of 2016 recorded steps of doors 51 and 123 (emu/bp27.lua, tools/doors.py), with the game's own answer for the creatures
# @orig game:0x80047290 object_interpreter+0x280  status:transcribed -- opcode 4's, the same arm with its own tables
# @orig game:0x80047444 object_interpreter+0x434  status:transcribed -- opcode 5's
static func lift_step(d: Dictionary, clear: Callable, stamp: Callable) -> void:
	var st := int(d["state"])
	if st == 0:
		return
	if st == 1:
		if int(d["counter"]) == 0:
			stamp.call(1, 1)
			d["scale"] = 0x1000
		d["counter"] = (int(d["counter"]) + LIFT_RATE) & 0xFFFF
		if int(d["counter"]) == LIFT_PASSABLE:
			stamp.call(0, 1)
		if int(d["counter"]) >= 0x1000:
			d["counter"] = LIFT_OPEN
			d["state"] = 2
	elif st == LIFT_WAIT:
		if clear.call():
			stamp.call(0, 0)
			d["state"] = 0x15
	elif st == 0x15:
		d["counter"] = (int(d["counter"]) - LIFT_RATE) & 0xFFFF
		if int(d["counter"]) != 0 and int(d["counter"]) < 0x8000:
			return
		stamp.call(1, 0)
		d["counter"] = 0
		d["state"] = 0
		d["scale"] = 0
	else:
		d["state"] = (st + 1) & 0xFFFF


# collide_query(x, y, z, 0x700, 0xc80, 0xc0) is 0: no awake creature within
# its radius + 0x700 of the door (actor_in_range) and the player not within
# 0x700 + 0x320 (player_in_range). The cell's occupancy count, asked first,
# follows from either: each marks every cell within its radius + 0x800.
# @orig game:0x80033f38 collide_query  status:partial -- the doorway test the lift arm asks: the player (0x80) 621 of 621 against the game's answers in bp27; the creatures (0x40) not yet, the game hiding which it found
func _lift_clear(d: Dictionary) -> bool:
	var x := int(d["x"])
	var y := int(d["y"])
	var z := int(d["z"])
	var an := get_node_or_null("../Actors")
	if an and an.has_method("in_range_of") and an.in_range_of(x, y, z, LIFT_CLEAR, LIFT_OWN) != -1:
		return false
	# @orig game:0x80028e48 player_in_range  status:transcribed
	return _in_range(player.gx, player.gy, player.gz, x, y, z, LIFT_CLEAR + PLAYER_R,
		PLAYER_BODY, LIFT_OWN) < 0


# stamp_table (0x800443c8) with the cells worked out at export: table 0 is the
# shape, 1 the tile; `sel` picks an entry's first four bytes or its last. 0xfc
# leaves a shape and 0xff a tile as it is. The shapes go into the port's
# collision cells -- the upper layer is `hi`, 3 unless b0 is 1 -- and the
# tiles of the drawn layer are kept to show or hide the door's tNNN cells.
# @orig game:0x800443c8 stamp_table  status:transcribed -- the flag byte (0xff here) not carried
func _stamp_table(d: Dictionary, t: int, sel: int) -> void:
	var hi := int(d["hi"])
	var lo := 3 - hi
	var cells: PackedInt32Array = player.coll.cells
	var entries: Array = d["stamps"][t]
	for i in entries.size():
		var e: Array = entries[i]
		var cx := int(e[0])
		var cz := int(e[1])
		if cx < 0 or cx >= 80 or cz < 0 or cz >= 80:
			continue
		var q: Array = e[2]
		var b := sel * 4
		var o := (cz * 80 + cx) * 6
		if int(q[b]) != 0xFC:
			cells[o + hi] = int(q[b])
		if int(q[b + 1]) != 0xFC:
			cells[o + lo] = int(q[b + 1])
		var tile := int(q[b + (2 if hi == 3 else 3)])
		if t == 1 and tile != 0xFF:
			d["drawn"][i] = tile
	player.coll.cells = cells


# What render_walk and draw_terrain make of it: the model while the scale is not
# 0, at the counter's frame of its animation, and the door's cells while their
# tile is one draw_terrain draws.
# @orig game:0x8003e34c draw_model_plain  status:partial -- the model while the scale is not 0, at the counter's frame
# @orig game:0x8003c1b8 draw_terrain+0x1e8  status:transcribed -- a cell is drawn while its tile is under 0xf0: draw_terrain's test, not draw_tile's
func _draw_lift(d: Dictionary) -> void:
	var nd: Node3D = d["node"]
	if d["tiles"]:
		var shown := false
		for tile in d["drawn"]:
			shown = shown or int(tile) < DRAWN
		(d["tiles"] as Node3D).visible = shown
	if nd == null:
		return
	nd.visible = int(d["scale"]) != 0
	if not nd.visible:
		return
	if (d["skin"] as Dictionary).is_empty():
		if not KFAnim.models.has(int(d["model"])):
			KFAnim.load_from("res://anim%02d.json" % player._level())
		d["skin"] = KFAnim.skin(nd, int(d["model"]))
	if not (d["skin"] as Dictionary).is_empty():
		KFAnim.animate(d["skin"], int(d["anim"]), int(d["counter"]))


# stamp_rect (0x800445b8) over the port's collision cells, with the mask the
# door uses: layer 1's rotation (added to by the turn) and its shape. `shift` is
# where the template sits relative to p[+0x13]: 0 open, 1 closed, 2 closed again.
# @orig game:0x800445b8 stamp_rect  status:transcribed
func _stamp(d: Dictionary, shift: int) -> void:
	var t: Array = d["tail"]
	var b0 := int(d["b0"])
	if not (b0 & 2):
		return
	var sx := int(t[3]) + shift
	var sz := int(t[4])
	var dx := int(t[1])
	var dz := int(t[2])
	var w := int(d["w"])
	var h := int(d["h"])
	if sx == 0xFF or dx == 0xFF or w == 0xFF:
		return
	var rot := (-(int(d["yaw0"]) >> 10)) & 3
	var step := 1
	var row := 80
	if rot == 1:
		step = -80
		row = 1
		dz += w - 1
	elif rot == 2:
		step = -1
		row = -80
		dx += w - 1
		dz += h - 1
	elif rot == 3:
		step = 80
		row = -1
		dx += h - 1
	var cells: PackedInt32Array = player.coll.cells
	var src := sz * 80 + sx
	var dst := dz * 80 + dx
	for _r in h:
		var s := src
		var o := dst
		for _c in w:
			if MASK & 4:
				cells[o * 6 + 4] = (cells[s * 6 + 4] + rot) & 3
			if MASK & 8:
				cells[o * 6 + 3] = cells[s * 6 + 3]
			s += 1
			o += step
		src += 80
		dst += row
	player.coll.cells = cells


# facing_test (0x80016a2c): is `b` within `tol` of `a`, either way round.
# @orig game:0x80016a2c facing_test  status:transcribed
static func _facing(a: int, b: int, tol: int) -> bool:
	var d := (a - b) & 0xFFF
	return d <= tol or d >= 0x1000 - tol


# in_range (0x80016ec8), as godot/actors.gd has it.
# @orig game:0x80016ec8 in_range  status:transcribed
func _in_range(ax: int, ay: int, az: int, x: int, y: int, z: int, r: int,
		top := 0, own := 0) -> int:
	var dx := ax - x
	if dx < -r or r < dx:
		return -1
	var dz := az - z
	if dz < -r or r < dz:
		return -1
	if ay < y:
		if ay < y - own:
			return -1
	elif y < ay - top:
		return -1
	var sx := dx >> 3
	var sz := dz >> 3
	var dist: int = player.coll.isqrt(sx * sx + sz * sz) << 3
	return -1 if r < dist else dist

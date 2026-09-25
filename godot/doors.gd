extends Node
# The doors that swing: object_interpreter's arm for opcode 1 (0x8004814c).
#
# load_object_placement gives each such door (class 0x01) opcode 1 and stamps
# its closed state into the grid: stamp_rect copies a w x h block of cells from
# a template the level keeps out of sight -- source (p[+0x13] + 1, p[+0x14]),
# destination (p[+0x11], p[+0x12]) -- so the doorway's collision shape is a wall.
# It also stores its yaw twice, at +0x26 and +0x42, and leaves +8, the state, 0.
#
# Pressing USE runs object_interact (0x8005e2d0), which asks find_object for
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
# cells of the doorway. No recording has followed a door frame by frame yet;
# emu/bp24.lua is the one to run.
#
# "Anything stands in the doorway" is collide_query(point, door y, 0x5dc, the
# door's height, 0xc0): the cell's occupancy count must be non-zero -- the door
# marked its own cells at load, so for a door it always is -- and then 0x40 asks
# every awake creature and 0x80 asks player_in_range (0x80028e48), which is
# in_range(player, point, 0x5dc + 0x320, 0x6a4, the door's height). Only the
# player is asked here: the port's creatures stand at home. And a stamp here
# changes the collision, not the drawn tile.
# @orig game:0x80047010 object_interpreter  status:partial -- opcode 1's arm at 0x8004814c: the swing, the stamps and the wait, against two snapshots' end states

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

var doors: Array = []
var player: Node3D
var acc := 0.0


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
	for row in rows:
		var d: Dictionary = row
		d["node"] = objs.find_child("d%03d" % int(d["slot"]), true, false) if objs else null
		d["yaw0"] = int(d["yaw"])
		d["state"] = 0
		d["counter"] = 0x3e7
		d["push"] = 0
		doors.append(d)


func _process(dt: float) -> void:
	if doors.is_empty():
		return
	if KFPad.hit(KFPad.USE):
		_interact()
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		for d in doors:
			if int(d["state"]) != 0:
				_step(d)
	for d in doors:
		if d["node"]:
			# The game's Ry(t) is a turn of -t about Godot's up axis.
			d["node"].rotation.y = -float(int(d["yaw"]) - int(d["yaw0"])) * TAU / 4096.0


# object_interact for the doors: find_object's point for class 1 is the player,
# 0x1f4 up, moved 0x400 back along the door's own yaw; it must be within the
# type's reach plus 0x320 of the door, and the door within 0x200 of the facing.
# @orig game:0x8005e2d0 object_interact  status:partial -- the swinging doors only
func _interact() -> void:
	var c: KFCollision = player.coll
	for d in doors:
		if int(d["state"]) != 0:
			continue
		var lock := int(d["tail"][0])
		if not (lock == 0xFF or ((lock == 0xFD or lock == 0xFE) and int(d["type"]) != 0xAE)):
			continue
		var yaw := int(d["yaw"])
		var px: int = player.gx + ((c.game_cos(yaw) * -0x400) >> 12)
		var pz: int = player.gz + ((-c.game_sin(yaw) * -0x400) >> 12)
		if _in_range(int(d["x"]), int(d["y"]), int(d["z"]), px, player.gy + 0x1f4, pz,
				int(d["reach"]) + 0x320, int(d["height"]), 0x9c4) < 0:
			continue
		var ang := c.vec_angle(int(d["x"]) - px, int(d["z"]) - pz)
		if not _facing(player.facing, ang, 0x200):
			continue
		d["state"] = 1


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
			var a := (int(d["yaw0"]) + 0x800) & 0xFFF
			player.gx += (c.game_sin(a) * SHOVE) >> 12
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
			var qz: int = int(d["z"]) + ((-c.game_sin(a) * 0x400) >> 12)
			# @orig game:0x80028e48 player_in_range  status:transcribed
			if _in_range(player.gx, player.gy, player.gz, qx, int(d["y"]), qz,
					CLEAR + PLAYER_R, PLAYER_BODY, int(d["height"])) >= 0:
				d["counter"] = CLOSE_AT
				return
			_stamp(d, 2)
		d["yaw"] = int(d["yaw"]) - SWING
		return
	d["state"] = 0


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

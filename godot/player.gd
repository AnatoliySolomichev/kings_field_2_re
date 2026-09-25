extends Node3D
# Movement, transcribed from the game's own player_vertical at 0x8002ed60.
#
#   F1  walk / fly      G  the collision, drawn      Esc  release the mouse
#   the game's buttons on the emulator's keys (godot/pad.gd): arrows, Q/R, Z, X...
#   Shift  faster       PgUp/PgDn  up / down, flying
#
# This was a guess -- "take the floor from the position you tried to reach and
# snap to it" -- and then briefly a different mistake: `player_move` at
# 0x8002f320, read carefully out of the MIPS and wrong about which routine
# matters. A recording settled it: that one ran 69 times in a whole session,
# every time in the knockback after dying, while the player walked about for
# eight hundred frames without it.
#
# What walking actually does is not a physics model. Each frame the height moves
# toward the surface by a limited amount, and inside 0x80 it is *placed* on the
# surface exactly:
#
#   d = surface - y            (Y is down, so d < 0 means the ground is higher)
#   |d| < 0x80      y = surface        placed, not eased
#   |d| < 0x100     y += 0x80  toward it
#   |d| < 0x200     y += 0x100
#   |d| < 0x400     y += 0x200 rising only
#   d < -0x400      state 0x20: launched upward at -0x96, decaying by 0x0a
#   d >  0x400      state 0x40: a fall from 0x28, gaining 0x28 a frame
#   0x200 < d       state 0x10: a shorter drop, gaining 0x50 -- twice as fast
#
# Descending also asks the collision at y+1 first and stays put if that is
# blocked -- which is what keeps you on a bridge instead of dropping to the
# floor of the room beneath it. State 0x40 is the one that tests the collision
# mask rather than the surface, so it is what carries you off a ledge.
#
# So there is no gravity while walking and no jump: you are carried up steps and
# down them at a fixed rate, and only a gap wider than 0x400 becomes a fall.
#
# Flying moves the position directly and asks the collision nothing, which is
# the point -- this level has rooms the game never lets anyone reach.
#
# Every constant below is read off the code and checked against the game:
# emu/bp15.lua watched the player's own coordinates and named each instruction
# that stores the height, and tools/movement.py picks the same one on 48 of 48.
#
# The horizontal is read now too, and checked the same way: over three minutes of
# ordinary play, tools/replay.py reproduces 6682 of 6682 frames of the height and
# 6186 of 6682 of the ground move -- and every one of the 496 that differ is a
# frame where the step is blocked, which is the wall slide. That is the one piece
# still missing: the game turns a refused step along the wall's own facing, out
# of 0x801e6498 and 0x801e649c, and tools/collision.py does not compute those.
# Walking into a wall therefore stops dead here where the game would slide.

const UNIT := 1000.0
const CELL := 2048.0
const SPEED_MAX := 200               # 0x801b2664 in the recorded session; the
                                     # acceleration is a quarter of it, the decay an eighth
const SPEED_MAX_RUN := 400           # not the game's -- there is no run button, this is
                                     # for getting about the level quickly
const FLY := 9000.0
const STEP_UP := 0x500               # player_horizontal: the most a step may climb
const SHRINK := 0x16                 # and how much shorter each retry is
const AROUND := 0x370                # how far past an object's radius the push-out goes
const STEEP_PUSH := 0x40             # the least push a taken step gains
const RECT_TRIES := [0x400, 0x400, 0x3E8, 0x3E8, 0x418, 0x418]   # the turns back
                                     # along a rectangle's axes, one a try
const PITCH_LIMIT := 0x2bc           # player_look stops the pitch here, either way
const EYE := 1.6
# Read off the code, no longer a guess. The game's clock is the vertical blank:
# vblank_tick (0x80019570), hooked to root counter 3 by 0x8001a438, adds one to
# 0x801c12ec every blank -- and one minute of play to 0x801b2588 every 3600 of
# them, so 60 a second. render_frame ends every pass of game_main's loop with
# frame_limit (0x80019614), which calls VSync(0) until that count reaches 4 and
# then zeroes it: **a frame lasts at least four blanks, so the game runs at 15
# frames a second**, slower only when a frame's own work overruns. This was 30
# for a long time, from two wall-clock measurements an uncapped emulator could
# not give -- which made the port walk and turn twice as fast as the game.
# @orig game:0x80019614 frame_limit  status:transcribed
const TICK_HZ := 15.0

# player_vertical's own constants, at the addresses named
const V_START := 0x28                # 0x8002f254, the seed for either fall
const V_ACCEL_SHORT := 0x50          # 0x8002ee20, state 0x10
const V_ACCEL_LONG := 0x28           # 0x8002ef18, state 0x40 -- the longer fall
const V_ACCEL_RISE := 0xA            # 0x8002eebc, state 0x20
const V_RECOIL := 0x12C              # 0x8002f0ac, state 0x50
const V_LAND_SLACK := 0x64           # 0x8002ee2c
const V_SQUASH := 0x200              # 0x8002efec
const V_LAUNCH := -0x96              # 0x8002f1ac

# The head bob, 0x8002f298. The phase accumulates the walking speed every frame
# and the height follows a *rectified* sine -- two lifts a stride, one a footfall.
# It accumulates whether or not the step was taken, which is why walking into a
# wall still bobs the camera. That is the game's behaviour, so it is the port's.
const BOB_SHIFT := 5                 # 0x8002f2c4
const EYE_UNITS := 1600.0            # 0x640 at 0x80028e10

# The buttons come through the game's own binding table now -- see godot/pad.gd
# and BOOT.md. player_controller (0x80030fcc) reads the pad once a frame, keeps
# the word at 0x801b265c and hands it to player_walk and player_turn, which ask
# the table which button each of their slots holds. With the default scheme
# that is: forward and back on UP and DOWN, strafe on L1 and R1, turn on LEFT
# and RIGHT, and this port's keyboard stands in for those.
# The turn, read off player_look (0x8002f5c0) and the cap the controller sets
# before calling it (0x80031194). It is the same shape as the walk: a rate that
# ramps towards a cap by a quarter of it each frame and decays to zero by the
# same quarter, and the facing is that rate added to 0x801b2612 every frame,
# wrapped to 0xfff.
#
# The cap is not constant, and this is a thing a player can feel: 0x28 standing
# still and 0x20 with forward or back held (0x800311a8 writes 0x28 only when
# neither `bind_forward` nor `bind_back` is down). So you turn about a fifth
# faster when you are not walking. Out of 0x1000 to the circle, 0x20 is 2.81
# degrees a frame and 0x28 is 3.52.
#
# There is a third case not reproduced here: while the counter at 0x801b2566
# is running, 0x80031254 halves the cap every frame and counts it down.
# Dying, out of player_controller. All 128 ai_slots go to 0xff, and then
# either item 107 -- "this crystal gives total recovery to the injured body and
# mind" -- is consumed and the player is put back at a fixed spot, or the
# character is made anew and the story flags are cleared.
#
# -0x3a80 is -128 * 117, and 117 is the height byte of cell (57, 24) on level
# 0, so the spot is a real place with the floor under it.
const REVIVE_ITEM := 107             # 0x6b, at 0x8002a558 in player_controller
const REVIVE_POS := Vector3i(0x1C800, -0x3A80, 0xC000)
const REVIVE_FACING := 0x2D5
const REVIVE_LAYER := 5

const TURN_MAX_STILL := 0x28         # 0x800311a8
const TURN_MAX_MOVING := 0x20        # 0x8003118c

var coll := KFCollision.new()
var have_coll := false
var flying := true
# 0x801b2610, the view pitch, 0x1000 to the turn and positive looking down, and
# 0x801b264e, the rate player_look drives it by.
var pitch := 0
var pitch_rate := 0
var look_acc := 0.0
# the position the game would keep: world units, Y increasing downward
var gx := 0
var gy := 0
var gz := 0
# the vertical state machine: the byte at 0x801b25e8 and the s16 at 0x801b2656
var vstate := 0
var vvel := 0
# 0x801b2648 and 0x801b2646: the two ground speeds the ramp drives
var fwd_speed := 0
var stf_speed := 0
# 0x801b264c, the turn rate the ramp drives, and 0x801b2612, the facing itself
var turn_rate := 0
var facing := 0
# 0x801b2652 and 0x801b2650: the bob's phase and the lift it produces
var bob_phase := 0
var bob := 0
var acc := 0.0
var last_surface := KFCollision.NO_SURFACE


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	have_coll = coll.load_from("res://coll%02d.json" % _level())
	gx = int(position.x * UNIT)
	gy = int(-position.y * UNIT)
	gz = int(-position.z * UNIT)
	facing = int(rotation.y / TAU * 4096.0) & 0xFFF
	_refresh()


# The level out/godot was built for: tools/level3d.py names the project
# "King's Field II - level N". This returned 0 whatever the build, so on any
# other level the port read level 0's collision, doors and sky.
func _level() -> int:
	var name := str(ProjectSettings.get_setting("application/config/name", ""))
	var i := name.rfind("level ")
	return int(name.substr(i + 6)) if i >= 0 else 0


func _to_godot() -> void:
	position = Vector3(float(gx) / UNIT, float(-gy) / UNIT, float(-gz) / UNIT)


func _refresh() -> void:
	var hud := get_node_or_null("../UI/Hud")
	if hud == null:
		return
	if KFPad.binding.is_empty():
		KFPad.apply()
	var cx := int(floor(float(gx) / CELL))
	var cz := int(floor(float(gz) / CELL))
	var note := "FLY" if flying else "WALK"
	if not have_coll:
		note += "  (no collision data)"
	var above := "-"
	if last_surface != KFCollision.NO_SURFACE:
		above = str(last_surface - gy)
	hud.text = ("%s   cell (%d, %d)   height %d\n" +
		"state %d   vy %d   speed %d/%d   %s above the surface\n" +
		"F1 walk/fly   F2 darkening   G collision   Esc mouse   PgUp/PgDn fly up/down\n" +
		"forward %s   strafe %s/%s   turn %s/%s   attack %s   use %s   menu %s   pause %s\n") % [
		note, cx, cz, -gy, vstate, vvel, fwd_speed, stf_speed, above,
		KFPad.slot_key(KFPad.FORWARD), KFPad.slot_key(KFPad.ALT_A),
		KFPad.slot_key(KFPad.ALT_C), KFPad.slot_key(KFPad.LEFT_SLOT),
		KFPad.slot_key(KFPad.RIGHT_SLOT), KFPad.slot_key(KFPad.ATTACK),
		KFPad.slot_key(KFPad.USE), KFPad.slot_key(KFPad.MENU_SLOT),
		KFPad.slot_key(KFPad.PAUSE)]


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		# The mouse moves the game's own facing rather than the node, so that
		# looking about and the turn buttons do not fight over the rotation.
		facing = int(facing - e.relative.x * 2.0) & 0xFFF
		rotation.y = float(facing) * TAU / 4096.0
		# The mouse moves the game's own pitch, held to the same limits.
		var sp := _signed(pitch) + int(e.relative.y * 2.0)
		pitch = clampi(sp, -PITCH_LIMIT, PITCH_LIMIT) & 0xFFF
		_aim()
	elif e is InputEventKey and e.pressed and not e.echo:
		match e.keycode:
			KEY_F1:
				flying = not flying
				vstate = 0
				vvel = 0
				_refresh()
			KEY_G:
				var v := get_node_or_null("../CollisionView")
				if v:
					v.visible = not v.visible
			KEY_ESCAPE:
				Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			KEY_TAB:
				Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


# @orig game:0x80030fcc player_controller  status:partial -- the pad once a frame and the edge detection; the rest of the routine is not here
func _process(dt: float) -> void:
	# player_controller reads the pad once a frame and keeps this frame's word
	# and last frame's. Here that happens once a *rendered* frame rather than
	# once a game tick, which only matters to the edge detection.
	KFPad.poll()
	var dir := Vector3.ZERO
	if KFPad.held(KFPad.FORWARD): dir -= transform.basis.z
	if KFPad.held(KFPad.BACK): dir += transform.basis.z
	if KFPad.held(KFPad.ALT_A): dir -= transform.basis.x
	if KFPad.held(KFPad.ALT_C): dir += transform.basis.x

	# player_look runs every frame the controller does; in flight too, so the
	# view can be tilted with the game's own buttons either way.
	look_acc = minf(look_acc + dt, 0.25)
	while look_acc >= 1.0 / TICK_HZ:
		look_acc -= 1.0 / TICK_HZ
		_look()

	if flying:
		if Input.is_key_pressed(KEY_PAGEDOWN): dir -= Vector3.UP
		if Input.is_key_pressed(KEY_PAGEUP): dir += Vector3.UP
		var fast := 3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0
		var d := dir.normalized() * FLY * fast * dt
		gx += int(d.x)
		gy -= int(d.y)
		gz -= int(d.z)
		acc = 0.0
	elif have_coll:
		# The model is per frame, not per second, so it runs on its own clock and
		# the renderer's frame rate does not change how anything moves.
		acc = minf(acc + dt, 0.25)
		while acc >= 1.0 / TICK_HZ:
			acc -= 1.0 / TICK_HZ
			_tick(dir)
	_to_godot()
	_refresh()


# 0x8002f9bc: accelerate by max/4 while held, decay when not, clamping at zero by
# sign. The forward ramp decays by max/8 (sra 3 at 0x8002fad4) and the strafe by
# max/4 (sra 2 at 0x8002fc38) -- two different rates, and a replay caught each of
# them before either was read.
# @orig game:0x8002f9bc player_walk  status:verified -- tools/replay.py: 6186 of 6682 ground frames, and all 496 that differ are the wall slide
func _ramp(speed: int, pos: bool, neg: bool, cap: int, decay := 3) -> int:
	if pos:
		return mini(speed + (cap >> 2), cap)
	if neg:
		return maxi(speed - (cap >> 2), -cap)
	var step := cap >> decay
	if speed > 0:
		return maxi(speed - step, 0)
	if speed < 0:
		return mini(speed + step, 0)
	return 0


# @orig game:0x8002e3f8 player_horizontal  status:partial -- the step; the slide along a refused wall is missing
func _tick(dir: Vector3) -> void:
	var cap := SPEED_MAX_RUN if Input.is_key_pressed(KEY_SHIFT) else SPEED_MAX
	# The controller's own order, off its call list: player_turn (the button
	# edges), player_look (the turn and the pitch), player_walk (the speeds),
	# then player_vertical or player_move. So the facing for this frame's step
	# is this frame's turn, not last frame's.
	_turn()
	# 0x8002f9bc reads the forward slot at 0x80081868 and the back one at
	# 0x8008186a; the strafe pair is 0x8008187c, which accelerates the speed,
	# and 0x80081878, which decelerates it -- so 0x7c is the positive
	# direction and with the default scheme that makes R1 strafe right.
	fwd_speed = _ramp(fwd_speed, KFPad.held(KFPad.FORWARD),
		KFPad.held(KFPad.BACK), cap)
	stf_speed = _ramp(stf_speed, KFPad.held(KFPad.ALT_C),
		KFPad.held(KFPad.ALT_A), cap, 2)
	# 0x8002fc94: the distances are not the speeds. Each is
	# speed^2 / isqrt(sum of squares), which normalises a diagonal and, because
	# the root is a unit short, makes a straight walk one unit longer.
	var h := coll.isqrt(fwd_speed * fwd_speed + stf_speed * stf_speed)
	var fd := 0
	var sd := 0
	if h != 0:
		fd = (fwd_speed * fwd_speed) / h
		sd = (stf_speed * stf_speed) / h
		if fwd_speed < 0: fd = -fd
		if stf_speed < 0: sd = -sd
	# player_walk steps twice, forward along facing + 0x400 and the strafe along
	# the facing, each through player_horizontal; then the height. Both calls
	# are made even for a step of nothing (0x8002fda0, 0x8002fdb4): that still
	# takes a steep ramp's push, so standing on one slides you down it.
	_horizontal((facing + 0x400) & 0xFFF, fd)
	_horizontal(facing & 0xFFF, sd)
	_move(0, 0)
	_bob(coll.isqrt(fd * fd + sd * sd))


# player_horizontal (0x8002e3f8): a step of `dist` along `angle`, and what the
# game does when collide_query at the player's height says no. Before this the
# port took every step and let player_vertical lift it onto whatever it had
# walked into, so any wall could be climbed; a player noticed. Read off the
# listing, in its order, and the same in tools/movement.py, where the
# recording checks it:
#
#   clear                        take it, but first: a steep ramp's push of
#                                0x40 or more is added once and the step asked
#                                again -- a slide back down
#   nothing outside 0x207, the surface no more than 0x500 above the feet,
#   player state 0, the ceiling more than a body above it
#                                a step up: take it, the same way
#   an object with a rectangle   (its byte +3 has bit 4) slide along one of its
#                                axes: the step turned into its frame, one part
#                                kept, turned back by its angle + 0x400, 0x3e8
#                                or 0x418; six tries
#   anything else in the way     go round it: the target moves to the object's
#                                centre plus its radius plus 0x370, along the
#                                bearing from the centre; a second thing in the
#                                way and the player stays
#   otherwise, a wall            try it 0x16 shorter at a time, once; then
#                                slide, the X part dropped, then only the X
#                                part; a diagonal wall (bit 2) slides along the
#                                diagonal the rotation of the cell the last
#                                query looked at gives; else stay
#
# Not here: the creatures.
# @orig game:0x8002e3f8 player_horizontal  status:partial -- all but the creatures; tools/replay.py: 118 288 of 118 500 ground frames
func _horizontal(angle: int, dist: int) -> void:
	var s4: int = (coll.game_cos(angle) * dist) >> 12
	var s2: int = (coll.game_sin(angle) * dist) >> 12
	var first_x := s4
	var first_z := s2
	var shrunk := false
	var diag := false
	var tries := 0
	var pushes := 0
	var rel := 0
	var slid := false
	var last := -1                    # the cell and layer 0x801e6468 points at
	var x := gx
	var z := gz
	for _i in 64:
		var tx := x + s4
		var tz := z + s2
		var q := coll.query_all(tx, gy, tz)
		last = int(q["at"])
		var mask: int = int(q["mask"])
		var take := mask == 0
		var blocked := false
		if not take and mask & ~0x207 == 0:
			if not (int(q["floor"]) + STEP_UP < gy) \
					and int(q["ceil"]) - int(q["floor"]) < -coll.body:
				take = true
			elif not (mask & 2):
				blocked = true
		if take:
			var push: int = q["push"]
			if push >= STEEP_PUSH and not slid:
				slid = true
				var pa: int = -int(q["push_angle"]) - 0x400
				s4 += (coll.game_cos(pa) * push) >> 12
				s2 += (coll.game_sin(pa) * push) >> 12
				continue
			gx = tx
			gz = tz
			return
		var oi: int = q["object"]
		if oi != -1 and (int(coll.objects[oi][4]) & 4) and tries < RECT_TRIES.size():
			var o: Array = coll.objects[oi]
			tries += 1
			var d := absi(dist)
			if tries == 1:
				rel = coll._s16(coll.ratan2(s2, s4) - 0x400 - (int(o[9]) & 0xFFFF))
			var u: int = (d * coll.game_cos(rel)) >> 12
			var v: int = (d * coll.game_sin(rel)) >> 12
			if tries & 1:
				if v != 0: u = 0
			elif u != 0:
				v = 0
			var turn: int = coll._s16(o[9]) + RECT_TRIES[tries - 1]
			var c := coll.game_cos(turn)
			var sn := coll.game_sin(turn)
			s4 = ((u * c) >> 12) - ((v * sn) >> 12)
			s2 = ((u * sn) >> 12) + ((v * c) >> 12)
			continue
		if mask & 0x30:
			pushes += 1
			if pushes == 2:
				break
			var o: Array = coll.objects[oi]
			var ox: int = o[5]
			var oz: int = o[7]
			var bearing := coll.ratan2(s2 - (oz - z), s4 - (ox - x))
			var r: int = int(o[10]) + AROUND
			s4 = _trunc12(coll.game_cos(bearing) * r) + ox - x
			s2 = _trunc12(coll.game_sin(bearing) * r) + oz - z
			continue
		if not shrunk:
			shrunk = true
			var s0 := dist - SHRINK
			while s0 >= 0:
				var vx: int = coll.game_cos(angle) * s0
				var vz: int = coll.game_sin(angle) * s0
				var nx := x + ((vx + 0xFFF if vx < 0 else vx) >> 12)
				var nz := z + ((vz + 0xFFF if vz < 0 else vz) >> 12)
				s0 -= SHRINK
				var sq := coll.query_all(nx, gy, nz)
				last = int(sq["at"])
				if int(sq["mask"]) == 0:
					x = nx
					z = nz
					break
		if blocked or (mask & 1):
			if s4 != 0:
				s4 = 0
				continue
			if s2 != 0:
				s4 = first_x
				s2 = 0
				continue
		if not (mask & 2):
			break
		if diag:
			if s4 != 0:
				s4 = 0
				continue
			if s2 != 0:
				s4 = first_x
				s2 = 0
				continue
			break
		var rot := 0
		if last >= 0:
			rot = coll.cells[last + 1] & 3
		if rot == 0 or rot == 2:
			s4 = (first_x + first_z) >> 1
			s2 = s4
		else:
			s4 = (first_x - first_z) >> 1
			s2 = -s4
		diag = true
	gx = x
	gz = z


# A product over 4096 rounded towards zero, the way player_horizontal's
# push-out does it (`addiu 0xfff` before the shift when negative).
static func _trunc12(v: int) -> int:
	return (v + 0xFFF if v < 0 else v) >> 12


# The turn rate ramps to the cap and decays back to zero by a quarter of the cap
# a frame -- the same rule player_walk uses for the ground speed, and the reason
# a turn keeps going for a few frames after the button is let go. Then the
# facing takes the rate and wraps: `facing = (facing + rate) & 0xfff`, at
# 0x8002f738.
#
# The rate is kept in the game's own units, 0x1000 to the circle, so it can be
# compared with 0x801b264c directly; the Godot rotation is derived from the
# facing at the end, the way ghost.gd reads the game's own.
# @orig game:0x8002f5c0 player_look  status:transcribed -- the yaw here, the pitch in _look
func _turn() -> void:
	var cap := TURN_MAX_MOVING if (KFPad.held(KFPad.FORWARD)
		or KFPad.held(KFPad.BACK)) else TURN_MAX_STILL
	var step := cap >> 2
	if KFPad.held(KFPad.LEFT_SLOT):                   # 0x8002f5e0
		turn_rate += step
		if turn_rate > cap:
			turn_rate = cap
	elif KFPad.held(KFPad.RIGHT_SLOT):                # 0x8002f648
		turn_rate -= step
		if turn_rate < -cap:
			turn_rate = -cap
	elif turn_rate > 0:                               # 0x8002f6b4, the decay
		turn_rate -= step
		if turn_rate < 0:
			turn_rate = 0
	elif turn_rate < 0:                               # 0x8002f6ec
		turn_rate += step
		if turn_rate > 0:
			turn_rate = 0
	facing = (facing + turn_rate) & 0xFFF             # 0x8002f738
	rotation.y = float(facing) * TAU / 4096.0


# The other half of player_look: the pitch. look_b (R2 in scheme A) adds 3 to
# the rate a frame up to 0x20, look_a (L2) takes 3 away down to -0x20, neither
# lets it decay by 3 to nothing, and both bring the view back to level -- the
# rate steps by 8 towards the pitch that is left, no more than a quarter of it.
# The pitch then takes the rate and stops at 0x2bc either way. Against the
# recording, the rate this predicts is the one the game logged on 118 501 of
# 118 502 frames, 1086 of them with a look button or the rate active.
# @orig game:0x8002f5c0 player_look  status:transcribed -- the pitch half
func _look() -> void:
	var up := KFPad.held(KFPad.ALT_B)                 # bind_look_a
	var down := KFPad.held(KFPad.ALT_D)               # bind_look_b
	if down and up:
		var sp := _signed(pitch)
		if sp >= 0:                                   # at or below level: back up
			pitch_rate -= 8
			if pitch_rate < -(sp >> 2):
				pitch_rate = -(sp >> 2)
				if pitch_rate == 0:
					pitch_rate = -sp
		elif sp < 0:                                  # above level: back down
			pitch_rate += 8
			if (-sp) >> 2 < pitch_rate:
				pitch_rate = (-sp) >> 2
				if pitch_rate == 0:
					pitch_rate = -sp
	elif down:
		pitch_rate = mini(pitch_rate + 3, 0x20)
	elif up:
		pitch_rate = maxi(pitch_rate - 3, -0x20)
	elif pitch_rate > 0:
		pitch_rate = maxi(pitch_rate - 3, 0)
	elif pitch_rate < 0:
		pitch_rate = mini(pitch_rate + 3, 0)
	if pitch_rate > 0:
		pitch = (pitch + pitch_rate) & 0xFFF
		if _signed(pitch) > PITCH_LIMIT:
			pitch = PITCH_LIMIT
	elif pitch_rate < 0:
		pitch = (pitch + pitch_rate) & 0xFFF
		if _signed(pitch) < -PITCH_LIMIT:
			pitch = (-PITCH_LIMIT) & 0xFFF
	_aim()


# The camera follows the pitch the way ghost.gd has it: negated, 0x1000 a turn.
func _aim() -> void:
	var cam := get_node_or_null("Camera")
	if cam:
		cam.rotation.x = -float(_signed(pitch)) * TAU / 4096.0


static func _signed(a: int) -> int:
	a &= 0xFFF
	return a - 0x1000 if a >= 0x800 else a


# 0x8002f298, the tail of player_vertical: the phase walks forward by the
# magnitude of the step and the lift is three quarters of |sin| shifted down by
# five, so it peaks at 96 units and never goes negative. Grounded only.
# @orig game:0x8002f298 player_bob  status:transcribed -- a label inside player_vertical, not a routine of its own
func _bob(mag: int) -> void:
	if vstate != 0:
		bob = 0
		return
	bob_phase = (bob_phase + mag) & 0xFFF
	var v := coll.game_sin(bob_phase) >> BOB_SHIFT
	if v < 0:
		v = -v
	bob = v - (v >> 2)
	var cam := get_node_or_null("Camera")
	if cam:
		cam.position.y = (EYE_UNITS + float(bob)) / UNIT


# player_vertical (0x8002ed60). The horizontal is the caller's; this is the
# height, and the state machine that owns it. Every branch here was matched
# against the instruction the game actually took -- see tools/movement.py bp15.
# @orig game:0x8002ed60 player_vertical  status:verified -- 48 of 48 of the game's own height stores, tools/movement.py bp15
func _move(dx: int, dz: int) -> void:
	gx += dx
	gz += dz

	if vstate == 0x20:                                # 0x8002ee50, rising
		var surf20 := coll.surface(gx, gy, gz)
		last_surface = surf20
		var ry := gy + vvel
		if not (surf20 < ry and vvel < 0):
			if surf20 < gy:
				ry = surf20
			vstate = 0
		gy = ry
		vvel += V_ACCEL_RISE
		return

	if vstate == 0x10:                                # 0x8002edf4, a short drop
		var surf10 := coll.surface(gx, gy, gz)
		last_surface = surf10
		var ny := gy + vvel
		if surf10 + V_LAND_SLACK < ny:
			gy = surf10
			vstate = 0
		else:
			gy = ny
		vvel += V_ACCEL_SHORT
		return

	if vstate == 0x40:                                # 0x8002eec8, a real fall
		var fy := gy + vvel
		var q40 := coll.query(gx, fy, gz)             # the mask, not the surface
		last_surface = int(q40["floor"])
		if int(q40["mask"]) == 0:
			gy = fy
			vvel += V_ACCEL_LONG
			return
		if vvel < 0:
			vvel = 0                                  # into a ceiling: stopped
			return
		gy = last_surface if vvel < V_SQUASH else last_surface - (vvel >> 1)
		vstate = 0x50
		return

	# 0x50 is the landing recoil and owns no height: after its bookkeeping at
	# 0x8002f068 it falls straight through into state 0's code, below.
	if vstate == 0x50:
		vvel -= V_RECOIL
		if vvel <= 0:
			vstate = 0

	var surf := coll.surface(gx, gy, gz)              # 0x8002f120, grounded
	last_surface = surf
	if surf == KFCollision.NO_SURFACE:
		return
	var d := surf - gy
	if d < 0:                                         # the ground is above
		if d < -0x400:
			vstate = 0x20
			vvel = V_LAUNCH
		elif d < -0x200:
			gy -= 0x200
		elif d < -0x100:
			gy -= 0x100
		elif d < -0x80:
			gy -= 0x80
		else:
			gy = surf                                 # placed, not eased
	elif d > 0:                                       # the ground is below
		if int(coll.query(gx, gy + 1, gz)["mask"]) != 0:
			return                                    # 0x8002f1e0: nothing under us
		if d < 0x81:
			gy = surf
		elif d < 0x101:
			gy += 0x80
		elif d < 0x201:
			gy += 0x100
		else:
			vstate = 0x10 if d < 0x401 else 0x40
			vvel = V_START

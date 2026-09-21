extends Node3D
# Movement, transcribed from the game's own player_vertical at 0x8002ed60.
#
#   F   walk / fly      G  the collision, drawn      Esc  release the mouse
#   WASD  move          Shift  faster                Q/E  down / up, flying
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
const EYE := 1.6
const TICK_HZ := 30.0                # STILL A GUESS. Two recordings measured 26 and
                                     # 34 frames a second, but the emulator runs
                                     # uncapped under the interpreter, so wall clock
                                     # says nothing about the console. 30 is the
                                     # PlayStation's usual half-VSync and it sits
                                     # between the two; counting game frames per
                                     # VSync would settle it properly.

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
const TURN_RATE := 24                # A GUESS. player_turn is 0x8002fe1c and
                                     # its rate is not transcribed; nothing in
                                     # a recording has settled it either.

var coll := KFCollision.new()
var have_coll := false
var flying := true
var pitch := 0.0
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
	_refresh()


func _level() -> int:
	return 0


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
		"F walk/fly   G collision   Esc mouse   " +
		"buttons: forward %s, strafe %s/%s, turn %s/%s, menu %s\n" ) % [
		note, cx, cz, -gy, vstate, vvel, fwd_speed, stf_speed, above,
		KFPad.name_of(KFPad.binding[KFPad.FORWARD]),
		KFPad.name_of(KFPad.binding[KFPad.ALT_A]),
		KFPad.name_of(KFPad.binding[KFPad.ALT_C]),
		KFPad.name_of(KFPad.binding[KFPad.LEFT_SLOT]),
		KFPad.name_of(KFPad.binding[KFPad.RIGHT_SLOT]),
		KFPad.name_of(KFPad.binding[KFPad.PAUSE])]


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-e.relative.x * 0.003)
		pitch = clamp(pitch - e.relative.y * 0.003, -1.4, 1.4)
		$Camera.rotation.x = pitch
	elif e is InputEventKey and e.pressed and not e.echo:
		match e.keycode:
			KEY_F:
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

	if flying:
		if Input.is_key_pressed(KEY_Q): dir -= Vector3.UP
		if Input.is_key_pressed(KEY_E): dir += Vector3.UP
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
	# 0x8002f9bc reads the forward slot at 0x80081868 and the back one at
	# 0x8008186a; the strafe pair is 0x8008187c, which accelerates the speed,
	# and 0x80081878, which decelerates it -- so 0x7c is the positive
	# direction and with the default scheme that makes R1 strafe right.
	fwd_speed = _ramp(fwd_speed, KFPad.held(KFPad.FORWARD),
		KFPad.held(KFPad.BACK), cap)
	stf_speed = _ramp(stf_speed, KFPad.held(KFPad.ALT_C),
		KFPad.held(KFPad.ALT_A), cap, 2)
	# The turn, which 0x8002f5c0 takes from the two lateral slots. The rate is
	# this port's guess, not the game's.
	if KFPad.held(KFPad.LEFT_SLOT):
		rotate_y(deg_to_rad(TURN_RATE) / TICK_HZ)
	if KFPad.held(KFPad.RIGHT_SLOT):
		rotate_y(-deg_to_rad(TURN_RATE) / TICK_HZ)
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
	var f := -transform.basis.z
	var r := transform.basis.x
	_move(int(f.x * fd + r.x * sd), int(-(f.z * fd + r.z * sd)))
	_bob(coll.isqrt(fd * fd + sd * sd))


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

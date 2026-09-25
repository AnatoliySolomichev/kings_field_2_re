extends Node3D
# The game and the port, in one world, frame for frame.
#
#   C  compare on / off      L  locked / free      R  resync now
#   B  take the buttons from the emulator
#   V  all the creatures / only the ones the game draws
#
# While comparing, the camera takes both angles from the game: yaw from
# 0x801b2612 and pitch from 0x801b2614.
#   1  height only           2  ground and height  3  from the buttons
#
# `emu/bp16.lua` overwrites `res://live.txt` once per game frame with the
# player's real position, facing, speeds and vertical state. This reads it,
# stands a marker where the game's player is, and runs the port's own model over
# the same input -- so the two can be looked at side by side and, more usefully,
# subtracted.
#
# **B sends the same buttons to both.** The line carries the game's own decoded
# button word, so with B on the port stops reading the keyboard and takes that
# instead: one pair of hands in the emulator window drives the game and the copy
# at once. It only works in that direction. Nothing here can press a button in
# the emulator -- there is no input to inject through, which is why every
# breakpoint script in this repository ends by asking a person to play.
#
# B and C are worth having apart. With C on and locked, the port is reset to the
# game's state every frame and the readout is a per-frame difference. With C off
# and B on, the port walks on its own over the game's input and drifts, which is
# the end-to-end question instead.
#
# **Locked is the default and it is the instrument.** Every frame it takes the
# state the game actually had, runs exactly one frame of the model, compares,
# and then throws the answer away and takes the game's state again. That way
# each disagreement is its own, and the cell it happened in gets a red marker
# you can walk over and look at. Free running is the honest end-to-end test and
# a poor diagnostic: after the first mistake the model is standing somewhere
# else asking about different cells, so everything downstream disagrees for a
# reason that has nothing to do with it.
#
# Resync puts back the **whole** state, not just the position: the vertical
# state byte and its velocity too. Putting back the position alone leaves the
# model mid-fall at the wrong height and it diverges again on the next frame.
#
# While comparing, the port's **facing is the game's**, not the mouse's: yaw
# comes straight from 0x801b2612. Without it the port walks the right distances
# in the wrong direction and every frame disagrees for a reason that has nothing
# to do with the model -- which is exactly what the first look at this showed,
# the copy always facing one way while the game turned. Godot's yaw is the
# game's angle unchanged, rotation.y = ang * TAU / 4096: forward is a quarter
# turn off the facing and Godot's Z is the negative of the game's, and the two
# cancel.
#
# The rungs are the ladder from `tools/replay.py`, released one layer at a time:
# 1 gives the model the game's own ground move and asks only about height;
# 2 gives the facing and the speeds and computes the step; 3 derives the speeds
# from the buttons. The facing is the game's in all three -- the turn rate at
# 0x8002fe1c is not transcribed, and putting an unread layer under a checked one
# would spoil the point of the ladder.

const LIVE := "res://live.txt"
const UNIT := 1000.0
const MARKERS := 64
# **live.txt is only news while something is rewriting it.** Nothing deletes it
# when the emulator stops, so the last session's last frame stays in it -- and
# this used to take that for the game. With the emulator started plainly, which
# loads no script, C jumped the port to where a player had stood two weeks
# earlier and held it there, and nothing on screen said why: the hint about
# starting the emulator with bp16.lua showed only when the file was missing
# altogether. Past this many seconds without a new line the feed counts as
# stopped. The file's time is kept to the second, hence not 1.
const STALE := 3

var player: Node3D
var marker: MeshInstance3D
var flags: MeshInstance3D
var compare := false
var locked := true
var rung := 2

# Disagreements go to a file as well as the screen, so a session can be handed
# to somebody who was not watching it. One line per frame that differs: the
# frame number, the buttons, where the game was, where the port went, and by
# how much.
const LOG := "res://compare.log"
var log_buf := PackedStringArray()
# The creatures are one node each and actors.gd runs the game's activation
# machine over them: `render_walk` draws an actor only while its byte +9 is 1,
# and 0x8004c1f0 decides when that is. V shows every one of them instead, which
# is what this build drew before the machine was read.
var only_drawn := true
var live_input := false
var feed := ""                     # why live.txt cannot be followed, "" if it can
var last_btn := 0
var last_frame := -1
var prev := {}                     # the previous game frame
var worst := 0
var drift := Vector3.ZERO
var bad_cells := {}
var checked := 0
var matched := 0
# The game's own frame rate, off vblank_count: frames over blanks since C, times
# 60. frame_limit holds it to 15 at most; it says how often the console dips.
var vb0 := -1
var f0 := -1
var game_fps := 0.0


func _ready() -> void:
	player = get_node_or_null("../Player")
	marker = MeshInstance3D.new()
	var caps := CapsuleMesh.new()
	caps.radius = 0.4
	caps.height = 1.7
	marker.mesh = caps
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.2, 0.9, 1.0, 0.45)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	marker.material_override = mat
	marker.visible = false
	add_child(marker)

	flags = MeshInstance3D.new()
	flags.mesh = ImmediateMesh.new()
	var fm := StandardMaterial3D.new()
	fm.albedo_color = Color(1.0, 0.25, 0.2, 0.5)
	fm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	fm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	fm.cull_mode = BaseMaterial3D.CULL_DISABLED
	flags.material_override = fm
	add_child(flags)


func _unhandled_input(e: InputEvent) -> void:
	if not (e is InputEventKey and e.pressed and not e.echo):
		return
	match e.keycode:
		KEY_C:
			compare = not compare
			marker.visible = compare
			if compare:
				_reset()
			else:
				_flush()
			# Say so immediately. Without this the readout only changed on the
			# next frame that carried data, so with no live.txt at all -- a
			# breakpoint script that does not write one -- pressing C looked
			# like it did nothing.
			_hud("")
		KEY_L:
			locked = not locked
			_reset()
		KEY_V:
			only_drawn = not only_drawn
			var act = get_node_or_null("../Actors")
			if act:
				act.show_all = not only_drawn
				act.refresh()
			_hud("")
		KEY_B:
			live_input = not live_input
			KFPad.from_emulator = live_input
			if not live_input:
				KFPad.live_word = 0
			_hud("")
		KEY_R:
			if prev.has("p"):
				_resync(prev)
		KEY_1:
			rung = 1
			_reset()
		KEY_2:
			rung = 2
			_reset()
		KEY_3:
			rung = 3
			_reset()


func _reset() -> void:
	worst = 0
	checked = 0
	matched = 0
	drift = Vector3.ZERO
	bad_cells.clear()
	_redraw_flags()
	if prev.has("p"):
		_resync(prev)


func _resync(f: Dictionary) -> void:
	# The whole state, not just where it is standing.
	var fp: Vector3i = f["p"]
	player.gx = fp.x
	player.gy = fp.y
	player.gz = fp.z
	player.vstate = int(f["vst"])
	player.vvel = int(f["vv"])
	player.fwd_speed = int(f["fwd"])
	player.stf_speed = int(f["stf"])


func _read() -> Dictionary:
	var f := FileAccess.open(LIVE, FileAccess.READ)
	if f == null:
		return {}
	var parts := f.get_as_text().strip_edges().split(" ", false)
	if parts.size() < 11:
		return {}
	return {
		"age": int(Time.get_unix_time_from_system()) -
			FileAccess.get_modified_time(LIVE),
		"f": int(parts[0]),
		"p": Vector3i(int(parts[1]), int(parts[2]), int(parts[3])),
		"ang": int(parts[4]), "vst": int(parts[5]), "vv": int(parts[6]),
		"fwd": int(parts[7]), "stf": int(parts[8]),
		"btn": int(parts[9]), "lv": int(parts[10]),
		"pitch": int(parts[11]) if parts.size() > 11 else 0,
		"vb": int(parts[12]) if parts.size() > 12 else -1,
	}


func _process(_dt: float) -> void:
	if player == null or not (compare or live_input):
		return
	var cur := _read()
	var why := _why_not(cur)
	if why != feed:
		_hud("")
	if why != "":
		# Nothing new is coming, so nothing is held: the port must not keep
		# walking on the last buttons of a session that has ended.
		KFPad.live_word = 0
		return
	# The buttons cross over whether or not the comparison is running, so B
	# works on its own.
	if live_input:
		last_btn = int(cur["btn"])
		KFPad.live_word = last_btn
	if not compare:
		return
	if int(cur["f"]) == last_frame:
		return
	last_frame = int(cur["f"])
	if int(cur["vb"]) >= 0:
		if vb0 < 0 or int(cur["vb"]) < vb0:
			vb0 = int(cur["vb"])
			f0 = int(cur["f"])
		elif int(cur["vb"]) > vb0:
			game_fps = 60.0 * float(int(cur["f"]) - f0) / float(int(cur["vb"]) - vb0)

	# Where the game's player is, in Godot's axes.
	var gp: Vector3i = cur["p"]
	marker.position = Vector3(float(gp.x) / UNIT,
		float(-gp.y) / UNIT + 0.85, float(-gp.z) / UNIT)
	# Face where the game faces, and look where it looks. The mouse does not
	# steer while comparing. The pitch is 0x801b2610, signed, the same 0x1000 to
	# the turn as the facing, and it *is* negated. The sign was reasoned out from
	# the resting value near -190 and the reasoning was wrong -- a player looked
	# up and the port looked down. The measurement was right and the inference
	# from it was not, which is the difference between the two kinds of number.
	player.rotation.y = float(int(cur["ang"]) & 0xFFF) * TAU / 4096.0
	var cam := player.get_node_or_null("Camera")
	if cam:
		var pitch := int(cur["pitch"])
		if pitch > 2048:
			pitch -= 4096
		cam.rotation.x = -float(pitch) * TAU / 4096.0

	if int(cur["lv"]) != player._level():
		_hud("the game is on level %d; this build has only level %d" % [
			cur["lv"], player._level()])
		return
	if prev.is_empty() or int(cur["f"]) != int(prev["f"]) + 1:
		prev = cur
		_resync(cur)
		return

	# One frame of the model over the input the game had, then compare.
	_advance(prev, cur)
	var got := Vector3i(player.gx, player.gy, player.gz)
	var want: Vector3i = cur["p"]
	var d := got - want
	checked += 1
	if d == Vector3i.ZERO:
		matched += 1
	else:
		var pp: Vector3i = prev["p"]
		var cell := Vector2i(pp.x >> 11, pp.z >> 11)
		if not bad_cells.has(cell) and bad_cells.size() < MARKERS:
			bad_cells[cell] = true
			_redraw_flags()
	drift = Vector3(d)
	worst = maxi(worst, maxi(absi(d.x), maxi(absi(d.y), absi(d.z))))
	if d != Vector3i.ZERO:
		log_buf.append("f=%d rung=%d %s btn=%s game=%d,%d,%d port=%d,%d,%d diff=%d,%d,%d"
			% [int(cur["f"]), rung, "locked" if locked else "free",
			   KFPad.names_of(int(prev["btn"])),
			   want.x, want.y, want.z, got.x, got.y, got.z, d.x, d.y, d.z])
		if log_buf.size() >= 32:
			_flush()
	if locked:
		_resync(cur)
	prev = cur
	_hud("")


# The rungs. The controller turns and accelerates before it steps, so the facing
# and the speeds a frame used are the ones standing at the *next* frame's start.
func _advance(a: Dictionary, b: Dictionary) -> void:
	player.vstate = int(a["vst"])
	player.vvel = int(a["vv"])
	if rung == 1:
		var bp: Vector3i = b["p"]
		player.gx = bp.x
		player.gz = bp.z
		player._move(0, 0)
		return
	var fwd: int = int(b["fwd"])
	var stf: int = int(b["stf"])
	if rung == 3:
		var btn: int = int(a["btn"])
		fwd = player._ramp(int(a["fwd"]), (btn & 0x1000) != 0,
			(btn & 0x4000) != 0, player.SPEED_MAX)
		stf = player._ramp(int(a["stf"]), (btn & 0x0008) != 0,
			(btn & 0x0004) != 0, player.SPEED_MAX, 2)
	var h: int = player.coll.isqrt(fwd * fwd + stf * stf)
	var fd := 0
	var sd := 0
	if h != 0:
		fd = (fwd * fwd) / h
		sd = (stf * stf) / h
		if fwd < 0: fd = -fd
		if stf < 0: sd = -sd
	# Forward runs a quarter turn off the facing; strafe along it.
	var af: int = (int(b["ang"]) + 0x400) & 0xFFF
	var ax: int = int(b["ang"]) & 0xFFF
	var dx: int = (player.coll.game_cos(af) * fd >> 12) \
		+ (player.coll.game_cos(ax) * sd >> 12)
	var dz: int = (player.coll.game_sin(af) * fd >> 12) \
		+ (player.coll.game_sin(ax) * sd >> 12)
	player._move(dx, dz)
	# The bob rides on the step's magnitude, whether or not the step landed.
	player._bob(player.coll.isqrt(fd * fd + sd * sd))


func _flush() -> void:
	if log_buf.is_empty():
		return
	var f := FileAccess.open(LOG, FileAccess.READ_WRITE)
	if f == null:
		f = FileAccess.open(LOG, FileAccess.WRITE)
	if f == null:
		log_buf.clear()
		return
	f.seek_end()
	for line in log_buf:
		f.store_line(line)
	f.close()
	log_buf.clear()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		_flush()


func _redraw_flags() -> void:
	var m: ImmediateMesh = flags.mesh
	m.clear_surfaces()
	if bad_cells.is_empty():
		return
	m.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for cell in bad_cells:
		var x0 := float(cell.x * 2048) / UNIT
		var z0 := -float(cell.y * 2048) / UNIT
		var x1 := float((cell.x + 1) * 2048) / UNIT
		var z1 := -float((cell.y + 1) * 2048) / UNIT
		var y := float(-player.gy) / UNIT + 0.05
		m.surface_add_vertex(Vector3(x0, y, z0))
		m.surface_add_vertex(Vector3(x1, y, z0))
		m.surface_add_vertex(Vector3(x1, y, z1))
		m.surface_add_vertex(Vector3(x0, y, z0))
		m.surface_add_vertex(Vector3(x1, y, z1))
		m.surface_add_vertex(Vector3(x0, y, z1))
	m.surface_end()


# Why the feed cannot be followed, in words a person can act on; "" when it can.
func _why_not(cur: Dictionary) -> String:
	var what := ""
	if cur.is_empty():
		what = "res://live.txt is not there, so there is nothing to follow."
	elif int(cur["age"]) > STALE:
		what = ("res://live.txt last changed %s ago, at game frame %d:" +
			" nothing is writing it now.") % [_ago(int(cur["age"])), int(cur["f"])]
	else:
		return ""
	return (what + "\n" +
		"Only a breakpoint script writes it, so start the emulator with one:\n" +
		"  ./emu/run.sh stop\n" +
		"  ./emu/run.sh debug bp16.lua      (or bp19.lua)\n" +
		"and get into the game. It is written from the player's movement, so\n" +
		"it also stands still while that is not running -- on the title screen.")


func _ago(s: int) -> String:
	if s < 120:
		return "%d s" % s
	if s < 7200:
		return "%d min" % (s / 60)
	if s < 172800:
		return "%d h" % (s / 3600)
	return "%d days" % (s / 86400)


func _hud(note: String) -> void:
	var hud := get_node_or_null("../UI/Compare")
	if hud == null:
		return
	feed = _why_not(_read()) if (compare or live_input) else ""
	if feed != "":
		hud.text = ("%s is on, but it has nothing to go on.\n%s\n" +
			"C compare: %s   B buttons: %s   V creatures") % [
			"COMPARE" if compare else "B", feed,
			"on" if compare else "off", "on" if live_input else "off"]
		return
	if not compare:
		var who := "all of them"
		var act = get_node_or_null("../Actors")
		if only_drawn:
			who = "as the game decides"
			if act:
				who += " -- " + act.summary()
		hud.text = ("C  compare with the emulator    B  take its buttons: %s\n" +
			"V  creatures: %s\n%s") % [
			"ON — " + KFPad.names_of(last_btn) if live_input else "off",
			who,
			"the emulator is driving this player" if live_input else ""]
		return
	var pct := 0
	if checked > 0:
		pct = matched * 100 / checked
	var gp: Vector3i = prev["p"] if prev.has("p") else Vector3i.ZERO
	hud.text = ("COMPARE  rung %d (%s)  %s   buttons from the emulator: %s\n" +
		"held: %s\n" +
		"game  %8d %8d %8d\nport  %8d %8d %8d\ndiff  %8d %8d %8d" +
		"      worst so far %d\n" +
		"%d of %d frames exact (%d %%)   the game: %s\n%s\n" +
		"C off   B buttons   V creatures   L lock/free   R resync   1/2/3 rung") % [
		rung,
		["", "height only", "ground and height", "from the buttons"][rung],
		"locked" if locked else "FREE RUNNING",
		"on" if live_input else "off",
		KFPad.names_of(last_btn),
		gp.x, gp.y, gp.z,
		player.gx, player.gy, player.gz,
		int(drift.x), int(drift.y), int(drift.z), worst,
		matched, checked, pct,
		("%.1f frames/s" % game_fps) if game_fps > 0.0 else "rate not logged", note]

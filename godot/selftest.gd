extends SceneTree
# Headless check that the port answers inside Godot what it answers in Python.
#   godot-4 --headless --path out/godot --script res://selftest.gd
#
# Two transcriptions sit between the PlayStation and this project:
# `tile_collision` into `tools/collision.py` and `player_vertical` into
# `tools/movement.py`, then both of those into GDScript. The first pair is
# checked against the game's own logged answers. This checks the second:
# `tools/gdcoll.py` writes out the frames the Python model produces, and the
# GDScript copy has to reproduce them exactly. A drift of one unit in a divide
# would otherwise go unnoticed for weeks.
#
# Whether the model matches the *game* is a separate question, answered by
# `python3 tools/movement.py bp15`: 48 of 48 of the height stores the game made
# in a recorded walk are the ones this model reaches for.

const V_START := 0x28
const V_ACCEL_SHORT := 0x50
const V_ACCEL_LONG := 0x28
const V_ACCEL_RISE := 0xA
const V_RECOIL := 0x12C
const V_LAND_SLACK := 0x64
const V_SQUASH := 0x200
const V_LAUNCH := -0x96

var coll: KFCollision


# player_vertical (0x8002ed60), the same transcription player.gd carries.
# Returns [x, y, z, state, velocity].
func _step(p: Array, dx: int, dz: int, state: int, vel: int) -> Array:
	var x: int = p[0] + dx
	var y: int = p[1]
	var z: int = p[2] + dz

	if state == 0x20:
		var s20 := coll.surface(x, y, z)
		var ry := y + vel
		if not (s20 < ry and vel < 0):
			if s20 < y:
				ry = s20
			state = 0
		return [x, ry, z, state, vel + V_ACCEL_RISE]

	if state == 0x10:
		var s10 := coll.surface(x, y, z)
		var ny := y + vel
		if s10 + V_LAND_SLACK < ny:
			return [x, s10, z, 0, vel + V_ACCEL_SHORT]
		return [x, ny, z, state, vel + V_ACCEL_SHORT]

	if state == 0x40:
		var fy := y + vel
		var q40 := coll.query(x, fy, z)
		if int(q40["mask"]) == 0:
			return [x, fy, z, state, vel + V_ACCEL_LONG]
		if vel < 0:
			return [x, y, z, state, 0]
		var f: int = int(q40["floor"])
		return [x, (f if vel < V_SQUASH else f - (vel >> 1)), z, 0x50, vel]

	if state == 0x50:
		vel -= V_RECOIL
		state = 0 if vel <= 0 else 0x50

	var surf := coll.surface(x, y, z)
	if surf == KFCollision.NO_SURFACE:
		return [x, y, z, state, vel]
	var d := surf - y
	if d < 0:
		if d < -0x400:
			return [x, y, z, 0x20, V_LAUNCH]
		if d < -0x200:
			return [x, y - 0x200, z, state, vel]
		if d < -0x100:
			return [x, y - 0x100, z, state, vel]
		if d < -0x80:
			return [x, y - 0x80, z, state, vel]
		return [x, surf, z, state, vel]
	if d == 0:
		return [x, y, z, state, vel]
	if int(coll.query(x, y + 1, z)["mask"]) != 0:
		return [x, y, z, state, vel]
	if d < 0x81:
		return [x, surf, z, state, vel]
	if d < 0x101:
		return [x, y + 0x80, z, state, vel]
	if d < 0x201:
		return [x, y + 0x100, z, state, vel]
	return [x, y, z, (0x10 if d < 0x401 else 0x40), V_START]


func _init() -> void:
	coll = KFCollision.new()
	if not coll.load_from("res://coll00.json"):
		print("FAIL: no collision data")
		quit(1)
		return
	print("loaded: %d cells, %d shapes, radius %d, body %d" % [
		coll.cells.size() / 6, coll.shapes.size(), coll.radius, coll.body])

	var f := FileAccess.open("res://movecheck00.json", FileAccess.READ)
	if f == null:
		print("FAIL: no movement reference (rerun tools/gdcoll.py)")
		quit(1)
		return
	var doc = JSON.parse_string(f.get_as_text())
	var total := 0
	var bad := 0
	var first := ""
	for run in doc["runs"]:
		var p: Array = [int(run["start"][0]), int(run["start"][1]), int(run["start"][2])]
		var state := 0
		var vel := 0
		var dx: int = int(run["d"][0])
		var dz: int = int(run["d"][1])
		for i in range(run["frames"].size()):
			var got := _step(p, dx, dz, state, vel)
			var want: Array = run["frames"][i]
			total += 1
			if got[0] != int(want[0]) or got[1] != int(want[1]) \
					or got[2] != int(want[2]) or got[3] != int(want[3]) \
					or got[4] != int(want[4]):
				bad += 1
				if first == "":
					first = "%s frame %d: godot %s, python %s" % [
						run["name"], i, str(got), str(want)]
			p = [got[0], got[1], got[2]]
			state = got[3]
			vel = got[4]
	print("movement: %d of %d frames match tools/movement.py exactly" % [
		total - bad, total])
	if bad > 0:
		print("  first difference: " + first)
		quit(1)
		return
	if not _levels():
		quit(1)
		return
	if not _angles():
		quit(1)
		return
	if not _scripts():
		quit(1)
		return
	quit(0)


# Every entity script in the game, through both copies of the interpreter. What
# is compared is where each one stopped, why, how many steps it took and which
# flags it left -- the part that does not depend on the text, the animation or
# anyone pressing a button.
func _scripts() -> bool:
	if not FileAccess.file_exists("res://escript.json"):
		print("scripts: no cases to check against")
		return true
	var d = JSON.parse_string(
		FileAccess.get_file_as_string("res://escript.json"))
	if typeof(d) != TYPE_DICTIONARY:
		print("scripts: escript.json is not a dictionary")
		return false
	var rows: Array = d.get("scripts", [])
	var bad_s := 0
	for r in rows:
		var code := PackedByteArray()
		for b in r["code"]:
			code.append(int(b))
		var got := KFScript.run(code)
		var flags: Array = []
		for i in range(got["flags"].size()):
			if int(got["flags"][i]) != 0:
				flags.append(i)
		var last: int = int(got["trace"][-1][0]) if got["trace"].size() else -1
		if got["why"] != r["why"] or got["trace"].size() != int(r["steps"]) \
				or last != int(r["last"]) or flags != Array(r["flags"]):
			bad_s += 1
			if bad_s == 1:
				print("  script level %d entity %d at %d: godot %s/%d/%d, python %s/%d/%d" % [
					int(r["level"]), int(r["entity"]), int(r["at"]),
					got["why"], got["trace"].size(), last,
					r["why"], int(r["steps"]), int(r["last"])])
	print("scripts: %d of %d run the same as tools/escript.py" % [
		rows.size() - bad_s, rows.size()])
	return bad_s == 0


# The game's arctangent, against the same directions tools/movement.py put
# through its copy. Nothing has ever logged a call to vec_angle, so what this
# checks is that the two transcriptions agree exactly -- not that either is
# right. That rests on the CORDIC table being atan(2**-i) and on the answers
# tracking a real atan2 to within the table's own rounding, 4.37 of 4096.
func _angles() -> bool:
	if not FileAccess.file_exists("res://anglecheck.json"):
		print("angles: no cases to check against")
		return true
	var rows = JSON.parse_string(
		FileAccess.get_file_as_string("res://anglecheck.json"))
	if typeof(rows) != TYPE_ARRAY:
		print("angles: anglecheck.json is not a list")
		return false
	var c := KFCollision.new()
	var bad_a := 0
	for r in rows:
		var got := c.vec_angle(int(r[0]), int(r[1]))
		if got != int(r[2]):
			bad_a += 1
			if bad_a == 1:
				print("  angle (%d, %d): godot %d, python %d" % [
					int(r[0]), int(r[1]), got, int(r[2])])
	print("angles: %d of %d directions match tools/movement.py exactly" % [
		rows.size() - bad_a, rows.size()])
	return bad_a == 0


# The levelling, against the cases tools/levelup.py wrote beside the table. The
# rolled stats are held at zero on both sides, because the game's rand is not
# reproduced here -- so what is compared is the part that is the same every
# time, which is everything the table decides.
func _levels() -> bool:
	if not FileAccess.file_exists("res://levelcheck.json"):
		print("levels: no cases to check against")
		return true
	var cases = JSON.parse_string(
		FileAccess.get_file_as_string("res://levelcheck.json"))
	if typeof(cases) != TYPE_ARRAY:
		print("levels: levelcheck.json is not a list")
		return false
	var bad_l := 0
	for c in cases:
		var got := KFLevels.award({
			"exp": int(c["exp"]), "exp_next": int(c["exp_next"]),
			"level": int(c["level"]), "hp_max": int(c["hp_max"]),
			"mp_max": int(c["mp_max"]), "stat36": int(c["stat36"]),
			"grow": [0, 0, 0, 0, 0]}, int(c["award"]))
		for k in ["level", "hp_max", "mp_max", "stat36", "exp", "exp_next"]:
			if int(got[k]) != int(c["want"][k]):
				bad_l += 1
				print("  level case %s: %s is %d, python says %d" % [
					str(c["award"]), k, int(got[k]), int(c["want"][k])])
				break
	print("levels: %d of %d cases match tools/levelup.py exactly" % [
		cases.size() - bad_l, cases.size()])
	return bad_l == 0

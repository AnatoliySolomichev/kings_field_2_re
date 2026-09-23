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
	if not _damage():
		quit(1)
		return
	if not _equip():
		quit(1)
		return
	quit(0)


# The hits emu/bp20.lua recorded, through the port's copy of the formula. What
# is compared is the damage, against what the log's own HP either side says.
func _damage() -> bool:
	if not FileAccess.file_exists("res://damagecheck.json"):
		print("damage: no cases to check against")
		return true
	var d = JSON.parse_string(
		FileAccess.get_file_as_string("res://damagecheck.json"))
	if typeof(d) != TYPE_DICTIONARY:
		print("damage: damagecheck.json is not a dictionary")
		return false
	var defence: Array = d.get("defence", [])
	var stat: int = int(d.get("stat", 0))
	var k: int = int(d.get("k", KFDamage.K))
	var hits: Array = d.get("hits", [])
	var bad_d := 0
	var seen := 0
	for h in hits:
		var before := int(h["before"])
		var after := int(h["after"])
		if before == 0 or after == 0:
			continue                       # already dead, or the kill clamps
		seen += 1
		var got := KFDamage.hit(Array(h["attacks"]), defence, stat, k)
		if int(got["damage"]) != before - after:
			bad_d += 1
			if bad_d == 1:
				print("  hit %s: %d -> %d is %d, godot says %d" % [
					str(h["attacks"].slice(0, 4)), before, after,
					before - after, int(got["damage"])])
	print("damage: %d of %d recorded hits reproduced exactly" % [
		seen - bad_d, seen])
	return bad_d == 0


# Every conversation in the game, through both copies of the interpreter, and
# then the two the emulator recorded in play. What is compared is the order of
# execution -- where it stopped, why, how many steps, which TALK.T entries it
# asked for and what it hands out on each visit -- the part that does not
# depend on the text, the animation or anyone pressing a button.
#
# The recorded pair is the one that counts. Two copies of one reading agreeing
# with each other is what this check used to be, and it agreed 1086 times
# about bytes that were not scripts at all.
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
	var by_key := {}
	var bad_s := 0
	for r in rows:
		var code := PackedByteArray()
		for b in r["code"]:
			code.append(int(b))
		by_key[[int(r["level"]), int(r["entity"])]] = code
		var got := KFScript.run(code)
		var last: int = int(got["trace"][-1][0]) if got["trace"].size() else -1
		var talk: Array = []
		for op in got["said"]:
			talk.append(int(r["header"]["talk"]) + int(op))
		var vis: Array = []
		for v in KFScript.visits(code):
			var one: Array = []
			for op in v:
				one.append(int(r["header"]["talk"]) + int(op))
			vis.append(one)
		var want_talk: Array = []
		for v in r["talk"]:
			want_talk.append(int(v))
		var want_vis: Array = []
		for v in r["visits"]:
			var one: Array = []
			for op in v:
				one.append(int(op))
			want_vis.append(one)
		if got["why"] != r["why"] or got["trace"].size() != int(r["steps"]) \
				or last != int(r["last"]) or talk != want_talk \
				or vis != want_vis:
			bad_s += 1
			if bad_s == 1:
				print("  conversation level %d entity %d: godot %s/%d/%d, python %s/%d/%d" % [
					int(r["level"]), int(r["entity"]),
					got["why"], got["trace"].size(), last,
					r["why"], int(r["steps"]), int(r["last"])])
	print("conversations: %d of %d run the same as tools/escript.py" % [
		rows.size() - bad_s, rows.size()])

	# and against what the game itself did, which is the only claim that is
	# not this project agreeing with itself
	var rec: Array = d.get("recorded", [])
	var ok := 0
	var want := 0
	for r in rec:
		var code: PackedByteArray = by_key.get(
			[int(r["level"]), int(r["entity"])], PackedByteArray())
		var got := KFScript.run(code, [], int(r["trace"].size()), false)
		for n in range(r["trace"].size()):
			want += 1
			if n < got["trace"].size() \
					and int(got["trace"][n][0]) == int(r["trace"][n][0]) \
					and int(got["trace"][n][1]) == int(r["trace"][n][1]):
				ok += 1
	print("conversations: %d of %d steps emu/bp21.lua recorded in play" % [ok, want])
	return bad_s == 0 and ok == want


# What the player is carrying, against what the game had in memory.
func _equip() -> bool:
	var e := KFEquip.new()
	if not e.load_tables():
		print("equipment: no tables to check against")
		return true
	var d = JSON.parse_string(
		FileAccess.get_file_as_string("res://equip.json"))
	var rec: Array = d.get("recorded", [])
	var ok := 0
	var want := 0
	for r in rec:
		var got := e.ratings(int(r["weapon"]), Array(r["worn"]))
		for k in range(KFEquip.RATINGS):
			want += 2
			if int(got["offense"][k]) == int(r["offense"][k]):
				ok += 1
			if int(got["defense"][k]) == int(r["defense"][k]):
				ok += 1
	print("equipment: %d of %d ratings match what the game had in memory" % [ok, want])
	return ok == want


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

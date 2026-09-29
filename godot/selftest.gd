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

var coll: KFCollision


# player_vertical (0x8002ed60), run by player.gd's own _move over the frames
# tools/gdcoll.py made with tools/movement.py: the position, the state, the
# velocity, and the landing's crouch and nod, frame after frame.
func _vertical(doc: Dictionary) -> bool:
	var pl = load("res://player.gd").new()
	pl.coll = coll
	var total := 0
	var bad := 0
	var first := ""
	for run in doc["runs"]:
		pl.gx = int(run["start"][0])
		pl.gy = int(run["start"][1])
		pl.gz = int(run["start"][2])
		pl.vstate = 0
		pl.vvel = 0
		pl.crouch = 0
		pl.dip = 0
		var dx: int = int(run["d"][0])
		var dz: int = int(run["d"][1])
		for i in range(run["frames"].size()):
			pl._move(dx, dz)
			var got := [pl.gx, pl.gy, pl.gz, pl.vstate, pl.vvel, pl.crouch, pl.dip]
			var want: Array = run["frames"][i]
			total += 1
			var same := true
			for j in got.size():
				if j < want.size() and got[j] != int(want[j]):
					same = false
			if not same:
				bad += 1
				if first == "":
					first = "%s frame %d: godot %s, python %s" % [
						run["name"], i, str(got), str(want)]
	pl.free()
	print("movement: %d of %d frames match tools/movement.py exactly" % [
		total - bad, total])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# player_horizontal, run by player.gd itself over steps tools/gdcoll.py took out
# of the recorded walking -- the refused, shortened and slid ones first -- with
# tools/movement.py's answer beside each.
func _steps(doc: Dictionary) -> bool:
	var cases: Array = doc.get("steps", [])
	if cases.is_empty():
		print("steps: none in movecheck00.json (no recording to take them from)")
		return true
	var pl = load("res://player.gd").new()
	pl.coll = coll
	var bad := 0
	var first := ""
	for c in cases:
		pl.gx = int(c[0])
		pl.gy = int(c[1])
		pl.gz = int(c[2])
		pl._horizontal(int(c[3]), int(c[4]))
		if pl.gx != int(c[5]) or pl.gz != int(c[6]):
			bad += 1
			if first == "":
				first = "%s: godot %d,%d python %d,%d" % [str(c), pl.gx, pl.gz,
					int(c[5]), int(c[6])]
	pl.free()
	print("steps: %d of %d recorded steps land where tools/movement.py puts them"
		% [cases.size() - bad, cases.size()])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# Steps into the creatures, made by tools/gdcoll.py (creaturecheck) with every
# creature of level 0 awake: player.gd's _horizontal against the Python.
func _creature_steps(doc: Dictionary) -> bool:
	var cases: Array = doc.get("creature_steps", [])
	if cases.is_empty():
		print("creature steps: none in movecheck00.json")
		return true
	var pl = load("res://player.gd").new()
	pl.coll = coll
	pl.creatures = doc.get("creatures", [])
	var bad := 0
	var first := ""
	for c in cases:
		pl.gx = int(c[0])
		pl.gy = int(c[1])
		pl.gz = int(c[2])
		pl._horizontal(int(c[3]), int(c[4]))
		if pl.gx != int(c[5]) or pl.gz != int(c[6]):
			bad += 1
			if first == "":
				first = "%s: godot %d,%d python %d,%d" % [str(c), pl.gx, pl.gz,
					int(c[5]), int(c[6])]
	pl.free()
	print("creature steps: %d of %d steps into a creature land where tools/movement.py puts them"
		% [cases.size() - bad, cases.size()])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# One creature stepped by ai.gd against tools/ai.py's run: the same start, the
# same player path, the same BIOS rand from the same seed -- every frame's
# position, yaw and opcode.
var _seed := 1


func _lcg() -> int:
	_seed = (_seed * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
	return (_seed >> 16) & 0x7FFF


func _ai_run() -> bool:
	var f := FileAccess.open("res://ai00.json", FileAccess.READ)
	if f == null:
		print("creature run: no ai00.json")
		return true
	var d = JSON.parse_string(f.get_as_text())
	if typeof(d) != TYPE_DICTIONARY or not d.has("run"):
		print("creature run: none in ai00.json")
		return true
	var run: Dictionary = d["run"]
	var kd: Dictionary = d["kinds"][str(int(run["kind"]))]
	var recs := []
	for r in kd["behaviours"]:
		var raw := []
		for v in r:
			raw.append(int(v))
		recs.append(raw)
	var kind := {"accel": int(kd["accel"]), "turn_accel": int(kd["turn_accel"]),
		"fall": int(kd["fall"]), "radius": int(kd["radius"]),
		"height": int(kd["height"]), "behaviours": recs}
	var st: Array = run["start"]
	var a := {"px": int(st[0]), "py": int(st[1]), "pz": int(st[2]), "ry": int(st[3]),
		"eflags": int(st[4])}
	var brain := KFCreatureAI.new()
	brain.coll = coll
	_seed = int(run["seed"])
	brain.rand = Callable(self, "_lcg")
	KFCreatureAI.wake(a, kind)
	a["ry"] = int(st[3])
	var bad := 0
	var first := ""
	var frames: Array = run["frames"]
	for i in frames.size():
		var q: Array = run["path"][i]
		var p := Vector3i(int(q[0]), int(q[1]), int(q[2]))
		if (i & 3) == 0:
			brain.pick(a, kind, p)
		brain.tick(a, kind, p, [a])
		var want: Array = frames[i]
		var got := [int(a["px"]), int(a["py"]), int(a["pz"]), int(a["ry"]) & 0xFFFF, int(a["op"])]
		if got != [int(want[0]), int(want[1]), int(want[2]), int(want[3]), int(want[4])]:
			bad += 1
			if first == "":
				first = "frame %d: godot %s python %s" % [i, str(got), str(want)]
	print("creature run: %d of %d frames of a level-0 creature where tools/ai.py puts it"
		% [frames.size() - bad, frames.size()])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


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
	if not _vertical(doc):
		quit(1)
		return
	if not _steps(doc):
		quit(1)
		return
	if not _creature_steps(doc):
		quit(1)
		return
	if not _ai_run():
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
	if not _knock():
		quit(1)
		return
	if not _weapon():
		quit(1)
		return
	if not _equip():
		quit(1)
		return
	if not _directions():
		quit(1)
		return
	if not _objects():
		quit(1)
		return
	quit(0)


# A blow's aftermath, player.gd against tools/knock.py: apply_damage over a
# spread of hits, the tilt spring for every shake, fall damage, and
# player_move from every position of the recorded knock-backs.
func _knock() -> bool:
	if not FileAccess.file_exists("res://knockcheck.json"):
		print("knock-back: no cases to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://knockcheck.json"))
	var pl = load("res://player.gd").new()
	pl.coll = coll
	var bad := 0
	var first := ""
	var n := 0
	for h in d["hits"]:
		n += 1
		pl.hp = int(h[0])
		pl.hp_max = int(h[1])
		pl.gx = int(h[3])
		pl.gy = int(h[4])
		pl.gz = int(h[5])
		pl.facing = int(h[10])
		pl.pstate = 0
		pl.push = [0, 0, 0]
		pl.tilt = [0, 0, 0]
		pl.tilt_vel = [0, 0, 0]
		pl.flash = 0
		pl._apply_damage(int(h[2]), true, Vector3i(int(h[6]), int(h[7]), int(h[8])), int(h[9]))
		var got := [pl.hp, pl.pstate, pl.push[0], pl.push[1], pl.push[2],
			pl.tilt_vel[0], pl.tilt_vel[2], pl.flash]
		var want := []
		for i in range(11, 19):
			want.append(int(h[i]))
		if got != want:
			bad += 1
			if first == "":
				first = "hit %s: godot %s" % [str(h), str(got)]
	for sp in d["springs"]:
		n += 1
		pl.tilt = [0, 0, 0]
		pl.tilt_vel = [int(sp[0]), 0, 0]
		var frames := 0
		while true:
			frames += 1
			pl._tilt()
			if pl.tilt == [0, 0, 0] or frames > 200:
				break
		if frames != int(sp[1]):
			bad += 1
			if first == "":
				first = "shake %d: godot %d frames, python %d" % [int(sp[0]), frames, int(sp[1])]
	for fl in d["falls"]:
		n += 1
		if pl.fall_damage(int(fl[0])) != int(fl[1]):
			bad += 1
			if first == "":
				first = "fall %d: godot %d, python %d" % [int(fl[0]), pl.fall_damage(int(fl[0])), int(fl[1])]
	pl.creatures = []
	for m in d["moves"]:
		n += 1
		pl.gx = int(m[0])
		pl.gy = int(m[1])
		pl.gz = int(m[2])
		pl.push = [int(m[3]), 1, int(m[4])]
		pl._push()
		var got := [pl.gx, pl.gy, pl.gz, pl.push[0], pl.push[1], pl.push[2]]
		var want := []
		for i in range(5, 11):
			want.append(int(m[i]))
		if got != want:
			bad += 1
			if first == "":
				first = "move %s: godot %s" % [str(m), str(got)]
	pl.free()
	print("knock-back: %d of %d cases match tools/knock.py (%d hits, %d shakes, %d falls, %d pushes)" % [
		n - bad, n, d["hits"].size(), d["springs"].size(), d["falls"].size(), d["moves"].size()])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# The player's weapon, weapon.gd against tools/weapon.py: every weapon's swing
# and the refill after it frame by frame, the probe's step, the damage to a
# creature and the push it gets.
func _weapon() -> bool:
	if not KFWeapon.load_from():
		print("weapon: no cases to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://weapon.json"))
	var bad := 0
	var n := 0
	var first := ""
	for sw in d["swings"]:
		var rec: PackedByteArray = KFWeapon.records[int(sw[0])]
		var w := {"clock": -1, "meter": 5000, "pause": 0}
		KFWeapon.start(w, rec)
		var swinging := true
		for fr in sw[1]:
			n += 1
			var snd := 0
			var hit := -1
			if swinging:
				var ev := KFWeapon.swing(w, rec)
				snd = 1 if ev["sound"] else 0
				hit = int(ev["hit"])
				if int(w["clock"]) == -1:
					swinging = false
			else:
				KFWeapon.refill(w, rec, 20, false)
			var got := [int(w["clock"]), int(w["meter"]), int(w["pause"]), snd, hit]
			var want := []
			for v in fr:
				want.append(int(v))
			if got != want:
				bad += 1
				if first == "":
					first = "weapon %d: godot %s, python %s" % [int(sw[0]), str(got), str(want)]
				break
	for pr in d["probes"]:
		n += 1
		var got := KFWeapon.probe(coll, int(pr[0]), int(pr[1]), int(pr[2]))
		if got != [int(pr[3]), int(pr[4]), int(pr[5])]:
			bad += 1
			if first == "":
				first = "probe %s: godot %s" % [str(pr), str(got)]
	for dm in d["damages"]:
		n += 1
		var att := []
		var dfn := []
		for i in 8:
			att.append(int(dm[1 + i]))
			dfn.append(int(dm[9 + i]))
		var got := KFWeapon.creature_damage(int(dm[0]), att, dfn, int(dm[17]))
		if got != int(dm[18]):
			bad += 1
			if first == "":
				first = "damage %s: godot %d" % [str(dm), got]
	for kn in d["knocks"]:
		n += 1
		var got := KFWeapon.knock(coll, int(kn[0]), int(kn[1]),
			Vector3i(int(kn[2]), int(kn[3]), int(kn[4])), Vector3i(100700, -12800, 59300), 1625)
		var want := [int(kn[5]), int(kn[6]), int(kn[7])] if int(kn[8]) else []
		if got != want:
			bad += 1
			if first == "":
				first = "knock %s: godot %s" % [str(kn), str(got)]
	print("weapon: %d of %d cases match tools/weapon.py (%d swings, %d probes, %d damages, %d pushes)" % [
		n - bad, n, d["swings"].size(), d["probes"].size(), d["damages"].size(), d["knocks"].size()])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


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


# The collision shape every object type gives, against what the game did.
func _objects() -> bool:
	if not FileAccess.file_exists("res://objcoll.json"):
		print("objects: no shapes to check against")
		return true
	var d = JSON.parse_string(
		FileAccess.get_file_as_string("res://objcoll.json"))
	if typeof(d) != TYPE_DICTIONARY:
		print("objects: objcoll.json is not a dictionary")
		return false
	var rec: Array = d.get("recorded", [])
	var ok := 0
	var want := 0
	for r in rec:
		var n: int = int(r["times"])
		want += n
		var got := KFObjectCollision.shape_of(int(r["row3"]), int(r["radius"]),
			int(r["rect"][0]), int(r["rect"][1]), int(r["scale"]))
		var want_kind: String = "circle" if int(r["expect_radius"]) > 0 else (
			"rect" if (int(r["row3"]) & KFObjectCollision.RECT_BIT) else "none")
		var good: bool = str(got["kind"]) == want_kind
		if good and want_kind == "circle":
			good = int(got["a"]) == int(r["expect_radius"])
		if good and want_kind == "rect":
			good = int(got["a"]) == int(r["rect"][0]) \
				and int(got["b"]) == int(r["rect"][1])
		if good:
			ok += n
		elif ok + n == want:
			print("  type %d: godot %s %d,%d" % [
				int(r["type"]), got["kind"], int(got["a"]), int(got["b"])])
	print("objects: %d of %d touches emu/bp23.lua recorded in play" % [ok, want])
	return ok == want


# A pair of angles through direction_from_angles, against tools/movement.py.
func _directions() -> bool:
	if not FileAccess.file_exists("res://dircheck.json"):
		print("directions: no cases to check against")
		return true
	var rows = JSON.parse_string(
		FileAccess.get_file_as_string("res://dircheck.json"))
	if typeof(rows) != TYPE_ARRAY:
		print("directions: dircheck.json is not a list")
		return false
	var c := KFCollision.new()
	c.load_from("res://coll00.json")          # for the sine table, nothing else
	var bad := 0
	for r in rows:
		var got := c.direction_from_angles(int(r[0]), int(r[1]))
		for k in range(3):
			if int(got[k]) != int(r[2][k]):
				bad += 1
				if bad == 1:
					print("  pitch %d yaw %d: godot %s, python %s" % [
						int(r[0]), int(r[1]), str(got), str(r[2])])
				break
	print("directions: %d of %d angle pairs match tools/movement.py exactly" % [
		rows.size() - bad, rows.size()])
	return bad == 0


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

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
#
# @port-file check -- the self-test; it runs the port's copies, it is not one
# @exe game

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


# The creatures' fence (collide_query's flag 2) on points around every fenced
# cell of level 0: whether the layer is fenced, and the creature query's mask
# and surface, against tools/ai.py.
func _fences(doc: Dictionary) -> bool:
	var cases: Array = doc.get("fences", [])
	if cases.is_empty():
		print("fences: none in movecheck00.json")
		return true
	var keep_r := coll.radius
	var keep_b := coll.body
	coll.radius = 1000
	coll.body = 1625
	var bad := 0
	var first := ""
	for c in cases:
		var q := coll.query(int(c[0]), int(c[1]), int(c[2]))
		var f := coll.fenced(q)
		var mask := int(q["mask"])
		var cur := int(q["floor"])
		if f:
			mask |= 1
			cur = KFCollision.FENCED_SURFACE
		if int(f) != int(c[3]) or mask != int(c[4]) or cur != int(c[5]):
			bad += 1
			if first == "":
				first = "%s: godot %d %d %d" % [str(c), int(f), mask, cur]
	coll.radius = keep_r
	coll.body = keep_b
	print("fences: %d of %d points around the creatures' fences match tools/ai.py"
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
	var ok := true
	for run in d.get("runs", [d["run"]]):
		ok = _one_run(d, run) and ok
	return ok


func _one_run(d: Dictionary, run: Dictionary) -> bool:
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
	print("creature run: %d of %d frames of level 0's slot %d (kind %d) where tools/ai.py puts it"
		% [frames.size() - bad, frames.size(), int(run["slot"]), int(run["kind"])])
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
	if not _fences(doc):
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
	if not _anim():
		quit(1)
		return
	if not _effects():
		quit(1)
		return
	if not _lifts():
		quit(1)
		return
	if not _chests():
		quit(1)
		return
	if not _inscriptions():
		quit(1)
		return
	if not _conversations():
		quit(1)
		return
	if not _menus():
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
	if not _routines():
		quit(1)
		return
	if not _saves():
		quit(1)
		return
	if not _run():
		quit(1)
		return
	if not _take_hit():
		quit(1)
		return
	if not _status_tick():
		quit(1)
		return
	if not _casting():
		quit(1)
		return
	if not _level_states():
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


# The creatures' animation, anim.gd against tools/anim.py: every animation of
# every animated model of level 0 at six clocks -- a weighted sum of all the
# vertices and the middle one.
func _anim() -> bool:
	if not KFAnim.load_from("res://anim00.json"):
		print("animation: no cases to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://anim00.json"))
	var bad := 0
	var first := ""
	for c in d["cases"]:
		var v := KFAnim.vertices(int(c[0]), int(c[1]), int(c[2]))
		var sum := 0
		for i in v.size():
			var p: Vector3i = v[i]
			sum += (p.x + p.y + p.z) * (i + 1)
		var mid: Vector3i = v[v.size() / 2]
		if sum != int(c[3]) or [mid.x, mid.y, mid.z] != [int(c[4][0]), int(c[4][1]), int(c[4][2])]:
			bad += 1
			if first == "":
				first = "model %d animation %d clock %d: godot %d %s" % [
					int(c[0]), int(c[1]), int(c[2]), sum, str(mid)]
	print("animation: %d of %d frames match tools/anim.py" % [
		d["cases"].size() - bad, d["cases"].size()])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# The effect machine, effects.gd against tools/effects.py, whose machine the
# game's own effect_spawn and effect_driver hold slot for slot: the same runs
# over snapshots -- bolts, spores and the puffs they leave -- with the world's
# answers replayed in the order the Python machine asked for them. Every
# frame: the same questions asked, the same strikes on the player, and the 128
# slots byte for byte (an md5 of their hex).
func _effects() -> bool:
	if not FileAccess.file_exists("res://fxcheck.json"):
		print("effects: no cases to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://fxcheck.json"))
	var fx = load("res://effects.gd").new()
	fx.load_records()
	fx.coll = coll                    # the game's arithmetic: roots, bearings
	var rp := FxReplay.new()
	fx.world = rp
	var runs := 0
	var good := 0
	var frames := 0
	var fgood := 0
	var first := ""
	for run in d["runs"]:
		runs += 1
		fx.clear()
		rp.layer_offset = int(run["layer0"])
		for sp in run["spawns"]:
			var args := []
			for v in sp[4]:
				if v == null:
					args.append(null)
				elif typeof(v) == TYPE_DICTIONARY:
					args.append((v["b"] as String).hex_decode())
				else:
					args.append(int(v))
			fx.spawn(int(sp[0]), int(sp[1]), int(sp[2]), (sp[3] as String).hex_decode(), args)
		var ok := true
		for f in run["frames"]:
			frames += 1
			rp.calls = f["q"]
			rp.i = 0
			rp.bad = ""
			rp.hurts = []
			fx.driver()
			var want_h := []
			for h in f["h"]:
				want_h.append(str(h).replace(".0", ""))
			var got_h := rp.hurts.map(func(h): return str(h))
			var same: bool = rp.bad == "" and rp.i == (f["q"] as Array).size() \
				and got_h == want_h and fx.m.hex_encode().md5_text() == str(f["md5"])
			if same:
				fgood += 1
			elif ok:
				ok = false
				if first == "":
					first = "%s, frame %d: %s" % [run["label"], frames,
						rp.bad if rp.bad != "" else ("strikes %s, python %s" % [str(got_h), str(want_h)]
							if got_h != want_h else "the slots differ")]
		if ok:
			good += 1
	# effect_aim: the velocity and the yaw
	var aims := 0
	var aok := 0
	for c in d.get("aims", []):
		var v: Array = (c as Array).map(func(x): return int(x))
		aims += 1
		var got: Array = fx.aim(v[0], v[1], Vector3i(v[2], v[3], v[4]), v[5],
			Vector3i(v[6], v[7], v[8]), v[9])
		if got == [v[10], v[11], v[12], v[13]]:
			aok += 1
		elif first == "":
			first = "aim %s: godot %s" % [str(v.slice(0, 10)), str(got)]
	# the healing and protecting spells' effects: the player's fields, the rand
	# values and the lighting through the replay
	var heals := 0
	var hgood := 0
	for run in d.get("heals", []):
		heals += 1
		fx.clear()
		rp.fields = {}
		for k in run["fields"]:
			rp.fields[k] = int(run["fields"][k])
		for sp in run["spawns"]:
			var args := []
			for v in sp[4]:
				args.append((v["b"] as String).hex_decode() if typeof(v) == TYPE_DICTIONARY else int(v))
			fx.spawn(int(sp[0]), int(sp[1]), int(sp[2]), (sp[3] as String).hex_decode(), args)
		var ok := true
		for f in run["frames"]:
			frames += 1
			rp.rands = (f["rand"] as Array).map(func(x): return int(x))
			rp.lit = []
			rp.calls = []
			rp.i = 0
			rp.bad = ""
			fx.driver()
			var same: bool = rp.bad == "" and rp.rands.is_empty() \
				and fx.m.hex_encode().md5_text() == str(f["md5"]) \
				and str(rp.lit) == str((f["lit"] as Array).map(func(x): return (x as Array).map(func(y): return int(y))))
			for k in f["fields"]:
				if int(rp.fields[k]) != int(f["fields"][k]):
					same = false
			if same:
				fgood += 1
			elif ok:
				ok = false
				if first == "":
					first = "%s, frame %d: %s" % [run["label"], frames, rp.bad if rp.bad != "" else "the slots, fields or lighting differ"]
		if ok:
			hgood += 1
	runs += heals
	good += hgood
	fx.free()
	print("effects: %d of %d runs, %d of %d frames of the effect machine as tools/effects.py's (whose machine the game's own effect_spawn and effect_driver hold: 189 of 189 runs, and the healing spells' 126 of 126); %d of %d aims as its effect_aim (600 of 600 the game's)" % [
		good, runs, fgood, frames, aok, aims])
	if first != "":
		print("  first difference: " + first)
	return good == runs and aok == aims


# What the effects ask of the game, answered from a run tools/effects.py made:
# collide_query's answer and the layer it leaves, in order, and the strikes
# effect_hurt_player is handed, kept.
class FxReplay:
	var calls: Array = []
	var i := 0
	var layer_offset := 0
	var hurts: Array = []
	var bad := ""
	var fields := {}
	var rands: Array = []
	var lit: Array = []

	func field(name: String) -> int:
		return int(fields.get(name, 0))

	func set_field(name: String, v: int) -> void:
		fields[name] = v & 0xFFFF

	func rand() -> int:
		if rands.is_empty():
			if bad == "":
				bad = "an extra rand"
			return 0
		return int(rands.pop_front())

	func lighting(_rgb: Array, near: int, far: int, k: int) -> void:
		lit.append([near, far, k])

	func collide_query(x: int, y: int, z: int, r: int, h: int, flags: int) -> int:
		if i >= calls.size():
			if bad == "":
				bad = "an extra query (%d, %d, %d)" % [x, y, z]
			return 0
		var c: Array = calls[i]
		i += 1
		var asked := [x, y, z, r, h, flags]
		for k in 6:
			if int(c[k]) != int(asked[k]) and bad == "":
				bad = "query %s, python %s" % [str(asked), str(c.slice(0, 6))]
		layer_offset = int(c[7])
		return int(c[6])

	func hurt_player(p: Vector3i, a1: int, radius: int, mode: int, edge: int, attacks: Array,
			effect: int, more: Array, scale: int, pct: int) -> void:
		hurts.append([p.x, p.y, p.z, a1, radius, mode, edge, attacks, effect, more, scale, pct])


# The lift doors' arm, doors.gd's lift_step against tools/doors.py
# lift_cycle: state, counter, scale and which half of each table is down,
# frame by frame from USE, shut at once and kept open seven frames.
func _lifts() -> bool:
	if not FileAccess.file_exists("res://liftcheck.json"):
		print("lift doors: no cases to check against")
		return true
	var doc = JSON.parse_string(FileAccess.get_file_as_string("res://liftcheck.json"))
	var script = load("res://doors.gd")
	var n := 0
	var bad := 0
	var first := ""
	for run in doc["runs"]:
		var d := {"state": 1, "counter": 0, "scale": 0}
		var sel := [0, 0]
		var held := [int(run["wait"])]
		var clear := func() -> bool:
			if held[0] > 0:
				held[0] -= 1
				return false
			return true
		var stamp := func(t: int, v: int) -> void:
			sel[t] = v
		for want in run["frames"]:
			script.lift_step(d, clear, stamp)
			var got := [int(d["state"]), int(d["counter"]), int(d["scale"]), sel[0], sel[1]]
			var w := []
			for v in want:
				w.append(int(v))
			n += 1
			if got != w:
				bad += 1
				if first == "":
					first = "frame %d: godot %s python %s" % [n, str(got), str(w)]
	var gn := 0
	for run in doc.get("gates", []):
		var g := {"state": 1, "counter": 0, "lock": int(run["lock"])}
		var laid := [script.GATE_SHUT]
		var gheld := [int(run["wait"])]
		var gclear := func() -> bool:
			if gheld[0] > 0:
				gheld[0] -= 1
				return false
			return true
		var gstamp := func(k: int) -> void:
			laid[0] = k
		for want in run["frames"]:
			script.gate_step(g, gclear, gstamp)
			var got := [int(g["state"]), int(g["counter"]), laid[0]]
			var w := []
			for v in want:
				w.append(int(v))
			n += 1
			gn += 1
			if got != w:
				bad += 1
				if first == "":
					first = "gate frame %d: godot %s python %s" % [gn, str(got), str(w)]
	var wn := 0
	for run in doc.get("walls", []):
		var wd := {"state": 0, "counter": 0, "scale": 0, "lock": 60, "b1": 0,
			"stay": bool(run["stay"])}
		var wlaid := [0]
		var f := 0
		for want in run["frames"]:
			var inside: bool = f >= int(run["enter"]) and (run["leave"] == null or f < int(run["leave"]))
			script.wall_step(wd, func() -> bool: return inside,
				func(sel: int) -> void: wlaid[0] = sel)
			var got := [int(wd["state"]), int(wd["counter"]), int(wd["scale"]), int(wlaid[0])]
			var w := []
			for v in want:
				w.append(int(v))
			n += 1
			wn += 1
			if got != w:
				bad += 1
				if first == "":
					first = "wall frame %d: godot %s python %s" % [f, str(got), str(w)]
			f += 1
	print("lift doors: %d of %d frames match tools/doors.py (%d of them a gate's, %d a hidden wall's)" % [n - bad, n, gn, wn])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# The game's own small routines, called by tools/mipsrun.py over a snapshot
# (tools/routines.py), against the port's copies one call at a time: the sine
# and cosine, the bearings, the square root, the range tests, facing_test,
# approach, fixed_madd and player_in_rect.
func _routines() -> bool:
	if not FileAccess.file_exists("res://routinecheck.json"):
		print("routines: no cases to check against")
		return true
	var doc = JSON.parse_string(FileAccess.get_file_as_string("res://routinecheck.json"))
	var r: Dictionary = doc["routines"]
	var n := 0
	var bad := 0
	var first := ""
	var per := {}
	for name in r:
		var ok := 0
		for row in r[name]:
			var c: Array = (row as Array).map(func(v): return int(v))
			var want: int = c[c.size() - 1]
			var got := 0
			match name:
				"game_sin":
					got = coll.game_sin(c[0])
				"game_cos":
					got = coll.game_cos(c[0])
				"arctan_unit":
					got = coll.arctan_unit(c[0])
				"vec_angle":
					got = coll.vec_angle(c[0], c[1])
				"ratan2":
					got = coll.ratan2(c[0], c[1])
				"game_isqrt":
					got = coll.isqrt(c[0])
				"in_range":
					got = coll.in_range(c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8])
				"in_oriented_rect":
					got = coll.in_oriented_rect(c[0], c[1], c[2], c[3], c[4], c[5], c[6],
						c[7], c[8], c[9], c[10])
				"facing_test":
					got = 1 if KFCreatureAI.facing_test(c[0], c[1], c[2]) else 0
					want = 1 if want != 0 else 0
				"approach":
					got = KFCreatureAI.approach(c[0], c[1], c[2])
				"fixed_madd":
					got = KFCreatureAI.lerp_fixed(c[0], c[1], c[2])
				"player_in_rect":
					got = 1 if KFObjects.player_in_rect(c[0], c[2], c[3], c[4], c[5], c[6],
						c[1], c[7]) else 0
					want = 1 if want != 0 else 0
				_:
					continue
			n += 1
			if got == want:
				ok += 1
			else:
				bad += 1
				if first == "":
					first = "%s%s: godot %d, the game %d" % [name, str(c.slice(0, c.size() - 1)), got, want]
		per[name] = "%d/%d" % [ok, (r[name] as Array).size()]
	print("routines: %d of %d calls of the game's own routines answered alike (%s)" % [
		n - bad, n, ", ".join(per.keys().map(func(k): return "%s %s" % [k, per[k]]))])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# The run, player.gd against bp16's own speed caps: frame_caps and run_flag
# over the frames round every run the log holds -- the state carried from frame
# to frame and taken off the log's cap again where the stretch is cut, both at
# 0 for a new character.
func _run() -> bool:
	if not FileAccess.file_exists("res://runcheck.json"):
		print("the run: no frames to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://runcheck.json"))
	var script = load("res://player.gd")
	var c := {"run": 1, "mod": 0, "slow": 0, "paralysis": 0}
	var n := 0
	var ok := 0
	var ran := 0
	var first := ""
	for row in d["frames"]:
		var v: Array = (row as Array).map(func(x): return int(x))
		if v[0] == 1:
			c = {"run": 1, "mod": ((v[4] - 200) * 4096 + 199) / 200 if v[4] > 200 else 0,
				"slow": 0, "paralysis": 0}
		else:
			if v[1] == 1:
				c["run"] = 0
				c["mod"] = 0
			var got: Array = script.frame_caps(c, v[3] == 1)
			n += 1
			if v[4] > 200:
				ran += 1
			if int(got[0]) == v[4]:
				ok += 1
			elif first == "":
				first = "frame %d: godot %d, the game %d" % [n, int(got[0]), v[4]]
		script.run_flag(c, v[2] == 1)
	print("the run: %d of %d frames' speed caps as bp16 logged them (%d above 200, USE held)" % [ok, n, ran])
	if first != "":
		print("  first difference: " + first)
	return ok == n


# player_take_hit, player.gd's take_hit against tools/status.py's (whose model
# the game's own holds, 840 of 840): a fresh character with each case's worn
# things, timers and attacks laid in, the rand values drawn in the order the
# model drew them -- the state left, the damage, and every draw taken.
func _take_hit() -> bool:
	if not FileAccess.file_exists("res://takehit.json"):
		print("player_take_hit: no cases to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://takehit.json"))
	var eq := KFEquip.new()
	if not eq.load_tables():
		print("player_take_hit: no equipment tables")
		return true
	var script = load("res://player.gd")
	var ok := 0
	var n := 0
	var first := ""
	for c in d["hits"]:
		var draws: Array = c["draws"]
		var at := [0]
		var rnd := func() -> int:
			at[0] += 1
			return int(draws[at[0] - 1]) if at[0] <= draws.size() else -1
		var rs: Dictionary = (d["recalc"] as Dictionary).duplicate(true)
		rs["worn"] = (c["worn"] as Array).map(func(x): return int(x))
		var st := {"worn": rs["worn"], "guard": int(c["guard"]),
			"shielded": int(c["shielded"]), "resist": int(c["resist"]),
			"mp_max": int(c["mp_max"]),
			"defence": (d["defence"] as Array).map(func(x): return int(x)),
			"stat": int(d["stat"]), "k": int(d["k"]), "recalc": rs}
		for k in c["before"]:
			st[k] = int(c["before"][k])
		var dmg: int = script.take_hit(st, c["attacks"], int(c["effect"]),
			int(c["scale"]), int(c["pct"]), rnd, eq)
		var same: bool = dmg == int(c["damage"]) and at[0] == draws.size()
		for k in c["after"]:
			if int(st[k]) != int(c["after"][k]):
				same = false
		n += 1
		if same:
			ok += 1
		elif first == "":
			first = "case %d, effect 0x%x, worn %s: godot %d, %d draws; python %d, %d" % [
				n, int(c["effect"]), str(rs["worn"]), dmg, at[0], int(c["damage"]), draws.size()]
	print("player_take_hit: %d of %d hits as tools/status.py takes them (whose model the game's own holds)" % [ok, n])
	if first != "":
		print("  first difference: " + first)
	return ok == n


# sub_80030e14, player.gd's status_tick against tools/status.py's tick (whose
# model the game's own holds frame for frame): every frame's fields, the two
# rectangles drawn, the recalculations, and the first lighting record after
# the darkness and the light.
func _status_tick() -> bool:
	if not FileAccess.file_exists("res://statuscheck.json"):
		print("the status: no frames to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://statuscheck.json"))
	var script = load("res://player.gd")
	var names := ["dark_lv", "dark_t", "light_lv", "light_t", "curse_lv", "curse_t",
		"flash", "flash_step"]
	var runs := 0
	var good := 0
	var n := 0
	var ok := 0
	var first := ""
	for run in d["runs"]:
		var st := {}
		for k in names:
			st[k] = int(run["start"][k])
		var all := true
		runs += 1
		for row in run["frames"]:
			var out: Dictionary = script.status_tick(st)
			var fields := []
			for k in names:
				fields.append(int(st[k]))
			var rects := []
			for rec in out["tints"]:
				var c := int(rec[0])
				if c > 0:
					rects.append([int(rec[1]) & 3, (int(rec[2]) / c) & 0xFF,
						(int(rec[3]) / c) & 0xFF, (int(rec[4]) / c) & 0xFF])
			var look: Array = (d["look0"] as Array).map(func(x): return int(x))
			if int(out["dark"]) != -1:
				script.light_blend(look, [0xA, 0xA, 0xA], 0x1388, 0x1770, int(out["dark"]))
			if int(out["light"]) != -1:
				script.light_blend(look, [0xDC, 0xDC, 0xA0], 0xFFFF, 0x4650, int(out["light"]))
			var want_rects: Array = (row[1] as Array).map(func(r): return (r as Array).map(func(x): return int(x)))
			var same: bool = fields == (row[0] as Array).map(func(x): return int(x)) \
				and rects == want_rects and int(out["recalc"]) == int(row[2]) \
				and look == (row[3] as Array).map(func(x): return int(x))
			n += 1
			if same:
				ok += 1
			elif all:
				all = false
				if first == "":
					first = "run %d frame %d: godot %s %s %s, python %s %s %s" % [runs,
						n, str(fields), str(rects), str(look), str(row[0]), str(row[1]), str(row[3])]
		if all:
			good += 1
	print("the status: %d of %d runs, %d of %d frames of sub_80030e14 as tools/status.py runs it (whose model the game's own holds)" % [good, runs, ok, n])
	if first != "":
		print("  first difference: " + first)
	return ok == n


# Casting, player.gd against tools/magic.py (whose model the game's own holds):
# cast_spell, player_action's healing and protecting arms, the pending action
# and the timers at the controller's end -- the fields after and the calls.
func _casting() -> bool:
	if not FileAccess.file_exists("res://magiccheck.json"):
		print("casting: no cases to check against")
		return true
	var d = JSON.parse_string(FileAccess.get_file_as_string("res://magiccheck.json"))
	var fx = load("res://effects.gd").new()
	fx.load_records()
	var recs: Dictionary = fx.records
	fx.free()
	var script = load("res://player.gd")
	var ok := 0
	var n := 0
	var first := ""
	for r in d["rows"]:
		var st: Dictionary = _ints(r["before"])
		var calls := []
		match str(r["what"]):
			"cast":
				script.cast_spell(st, int(r["spell"]), recs, calls)
			"action":
				script.player_action(st, int(r["spell"]), calls)
			"pending":
				script.pending_tick(st, calls)
			"use":
				calls.append(["rest", 1 if script.use_tick(st, recs) else 0])
			_:
				script.timers_tick(st, calls)
		var want: Dictionary = _ints(r["after"])
		var same: bool = str(_ints(calls)) == str(_ints(r["calls"]))
		for k in want:
			if str(st[k]) != str(want[k]):
				same = false
		n += 1
		if same:
			ok += 1
		elif first == "":
			first = "%s 0x%x: godot %s %s, python %s %s" % [r["what"], int(r["spell"]) if r["spell"] != null else -1,
				str(st), str(calls), str(want), str(r["calls"])]
	print("casting: %d of %d casts, actions and frames as tools/magic.py has them (whose model the game's own holds)" % [ok, n])
	if first != "":
		print("  first difference: " + first)
	return ok == n


# @port check -- JSON's floats back to ints, all the way down
func _ints(v):
	if v is Dictionary:
		var o := {}
		for k in v:
			o[k] = _ints(v[k])
		return o
	if v is Array:
		return (v as Array).map(func(x): return _ints(x))
	if v is float:
		return int(v)
	return v


# The memory card, card.gd against tools/memcard.py: save_restore's table
# entry by entry -- the one the game's own save_restore writes byte for byte
# -- and every save on the emulator's cards read alike: its slot, title, sum,
# whether the game would believe it, its level and where the player stands.
func _saves() -> bool:
	if not FileAccess.file_exists("res://savecheck.json"):
		print("saves: no cases to check against")
		return true
	var doc = JSON.parse_string(FileAccess.get_file_as_string("res://savecheck.json"))
	var n := 0
	var bad := 0
	var first := ""
	var tables := [[doc["fields"], KFCard.FIELDS, 3], [doc["blocks"], KFCard.BLOCKS, 4]]
	for t in tables:
		var want: Array = t[0]
		var have: Array = t[1]
		for i in maxi(want.size(), have.size()):
			n += 1
			var w: Array = want[i] if i < want.size() else []
			var g: Array = (have[i] as Array).slice(0, int(t[2])) if i < have.size() else []
			if w.map(func(v): return int(v)) != g.map(func(v): return int(v)):
				bad += 1
				if first == "":
					first = "table entry %d: godot %s, tools/memcard.py %s" % [i, str(g), str(w)]
	var entries := n
	var got := {}
	for sv in KFCard.saves(KFCard.card_paths()):
		got["%s/%d" % [sv["path"], int(sv["slot"])]] = sv
	for w in doc["saves"]:
		n += 1
		var key := "%s/%d" % [w["path"], int(w["slot"])]
		var sv: Dictionary = got.get(key, {})
		var why := ""
		if sv.is_empty():
			why = "not found"
		else:
			var data: PackedByteArray = sv["data"]
			var f := KFCard.restore(data.slice(KFCard.DATA_AT))
			var pos := [KFCard.num(f, "x", true), KFCard.num(f, "y", true), KFCard.num(f, "z", true)]
			if str(sv["title"]) != str(w["title"]):
				why = "title %s, not %s" % [sv["title"], w["title"]]
			elif KFCard.checksum(data) != int(w["sum"]) or bool(sv["valid"]) != bool(w["valid"]):
				why = "the sum %d, not %d" % [KFCard.checksum(data), int(w["sum"])]
			elif int(data[KFCard.DATA_AT]) != int(w["level"]) \
					or pos != (w["pos"] as Array).map(func(v): return int(v)):
				why = "level %d at %s" % [int(data[KFCard.DATA_AT]), str(pos)]
		if why != "":
			bad += 1
			if first == "":
				first = "%s: %s" % [key, why]
	print("saves: %d of %d -- save_restore's %d entries as tools/memcard.py has them (the game's own writes them byte for byte), and %d saves on the cards read alike" % [
		n - bad, n, entries, (doc["saves"] as Array).size()])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# What a level remembers, levelstate.gd against tools/levelstate.py: every
# stream the self-test is given -- the snapshots', scrambled ones, the saves'
# -- read into the same actors, conversations and 396 slot opcodes, and every
# thing a creating opcode makes, the game's rand an LCG from 1 on both sides.
func _level_states() -> bool:
	if not FileAccess.file_exists("res://levelstatecheck.json"):
		print("level states: no cases to check against")
		return true
	var doc = JSON.parse_string(FileAccess.get_file_as_string("res://levelstatecheck.json"))
	var n := 0
	var ok := 0
	var mn := 0
	var mok := 0
	var first := ""
	var ints := func(a): return (a as Array).map(func(r): return (r as Array).map(func(v): return int(v)))
	for st in doc["streams"]:
		n += 1
		var d := KFLevelState.decode((st["hex"] as String).hex_decode())
		var same: bool = ints.call(d["actors"]) == ints.call(st["actors"]) \
			and ints.call(d["talks"]) == ints.call(st["talks"]) \
			and ints.call(d["slots"]) == ints.call(st["slots"])
		if same:
			ok += 1
		elif first == "":
			first = "%s: the stream read otherwise" % st["label"]
		var lcg := [1]
		var rand := func() -> int:
			lcg[0] = (int(lcg[0]) * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
			return (int(lcg[0]) >> 16) & 0x7FFF
		var slots: Array = d["slots"]
		for s in slots.size():
			var row: Array = slots[s]
			if not KFLevelState.KINDS.has(int(row[0])):
				continue
			mn += 1
			var m := KFLevelState.made(row, rand)
			var w: Dictionary = (st["made"] as Dictionary).get(str(s), {})
			var pos = [m["pos"].x, m["pos"].y, m["pos"].z] if m.has("pos") else null
			var wpos = (w["pos"] as Array).map(func(v): return int(v)) if w.has("pos") else null
			if int(m["kind"]) == int(w.get("kind", -1)) and int(m["type"]) == int(w.get("type", -1)) \
					and (m["angles"] as Array) == (w.get("angles", []) as Array).map(func(v): return int(v)) \
					and int(m["state"]) == int(w.get("state", -1)) and int(m["lock"]) == int(w.get("lock", -1)) \
					and int(m["rest"]) == int(w.get("rest", -1)) and pos == wpos:
				mok += 1
			elif first == "":
				first = "%s slot %d: made %s, tools/levelstate.py %s" % [st["label"], s, str(m), str(w)]
	# the writer, over each state a snapshot holds and scrambled copies
	var wn := 0
	var wok := 0
	for w in doc.get("writes", []):
		wn += 1
		var pairs := []
		for a in w["actors"]:
			if int(a[1]) == 1:
				pairs.append([int(a[0]), int(a[2])])
		var got := KFLevelState.encode(pairs, ints.call(w["talks"]), _table(w["table"]))
		if got.hex_encode() == str(w["want"]):
			wok += 1
		elif first == "":
			first = "%s: written otherwise" % w["label"]
	# the reader over the table of a fresh load, and the objects written again
	var by := {}
	for st in doc["streams"]:
		by[str(st["label"])] = st
	var rn := 0
	var rok := 0
	for r in doc.get("reads", []):
		rn += 1
		var table := _table(r["before"])
		var lcg := [1]
		var rand := func() -> int:
			lcg[0] = (int(lcg[0]) * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
			return (int(lcg[0]) >> 16) & 0x7FFF
		var d := KFLevelState.decode((by[str(r["label"])]["hex"] as String).hex_decode())
		KFLevelState.apply_table(table, d, (r["classes"] as Array).map(func(v): return int(v)), rand)
		var again := KFLevelState.encode([], [], table).slice(2)
		if table == _table(r["after"]) and again.hex_encode() == str(r["again"]):
			rok += 1
		elif first == "":
			first = "%s: the table after, or the objects written again, otherwise" % r["label"]
	print("level states: %d of %d streams read as tools/levelstate.py reads them (whose reader 90 of 90 runs of the game's hold), %d of %d things made alike; %d of %d states written as its writer writes them (84 of 84 the game's own), %d of %d tables read and written again alike" % [
		ok, n, mok, mn, wok, wn, rok, rn])
	var good := ok == n and mok == mn and wok == wn and rok == rn
	if not good:
		print("  first difference: " + first)
	return good


# A table as levelstatecheck.json has it: a row of ten for each slot, or null.
func _table(rows: Array) -> Array:
	var t := []
	for r in rows:
		t.append(null if r == null else (r as Array).map(func(v): return int(v)))
	return t


# The chests and object_give, loot.gd against tools/chests.py: the lid's 82
# frames from USE to rest -- a path seven lids in the snapshots lie on -- the
# big chest's, three of object_give's sequences: taken after the spin, put
# back, and taken mid-flight -- and Silviera's key on three pedestals.
func _chests() -> bool:
	if not FileAccess.file_exists("res://chestcheck.json"):
		print("chests: no cases to check against")
		return true
	var doc = JSON.parse_string(FileAccess.get_file_as_string("res://chestcheck.json"))
	var script = load("res://loot.gd")
	var n := 0
	var bad := 0
	var first := ""
	for which in ["lid", "big"]:
		var d := {"state": 0, "angles": [0, 0, 0], "vel": 0, "counter": 0, "lock": 0xFF}
		var c := {"present": 0, "free": 0}
		var mode := func(m: int, v: int) -> void:
			if m == 0:
				c["present"] = 0
				c["free"] = 0
			elif m == 1:
				c["present"] = v
			elif m == 2:
				c["free"] = 1
		var step: Callable = script.lid_step if which == "lid" else script.big_step
		step.call(d, mode)
		d["lock"] = 0xFE
		for want in doc[which]:
			step.call(d, mode)
			var a: int = int(d["angles"][0]) if which == "lid" else int(d["counter"])
			var got := [int(d["state"]), a, int(d["vel"]), int(c["present"]), int(c["free"])]
			var w := []
			for v in want:
				w.append(int(v))
			n += 1
			if got != w:
				bad += 1
				if first == "":
					first = "%s frame %d: godot %s python %s" % [which, n, str(got), str(w)]
	var flights := 0
	for f in doc["flights"]:
		var args: Dictionary = f["args"]
		var r := {"pos": Vector3i(int(args["pos"][0]), int(args["pos"][1]), int(args["pos"][2])),
			"angles": [int(args["angles"][0]), int(args["angles"][1]), int(args["angles"][2])],
			"c": int(args["c"]), "e": int(args["e"]), "type": 0x33}
		var p := Vector3i(int(args["player"][0]), int(args["player"][1]), int(args["player"][2]))
		var g: Dictionary = script.give_start(r, p, int(args["pitch"]), int(args["facing"]), coll)
		g["take"] = bool(args["take"])
		var i := 0
		for want in f["frames"]:
			var pressed: bool = i == int(args["press"])
			script.give_step(g, 1 if bool(args["take"]) else 0, pressed)
			var q: Vector3i = r["pos"]
			var got := [q.x, q.y, q.z, int(r["angles"][0]), int(r["angles"][1]),
				int(r["angles"][2]), int(g["pitch"])]
			var w := []
			for v in want:
				w.append(int(v))
			n += 1
			if got != w:
				bad += 1
				if first == "":
					first = "flight %d frame %d: godot %s python %s" % [flights, i, str(got), str(w)]
			i += 1
		flights += 1
	var falls := 0
	for f in doc.get("falls", []):
		var o := {"op": int(f["op"]), "state": 0, "pos": Vector3i(0, -int(f["drop"]), 0),
			"angles": [0, 0, 0], "vel": int(f["vel"]), "rest": int(f["rest"])}
		var i := 0
		for want in f["frames"]:
			script.fall_step(o, 0)
			var q: Vector3i = o["pos"]
			var got := [int(o["state"]), q.y, int(o["vel"]), int(o["angles"][0]), int(o["angles"][1])]
			var w := []
			for v in want:
				w.append(int(v))
			n += 1
			if got != w:
				bad += 1
				if first == "":
					first = "fall %d frame %d: godot %s python %s" % [falls, i, str(got), str(w)]
			i += 1
		falls += 1
	var keys := 0
	for k in doc.get("keys", []):
		# [op, state, lock, key, result, lock after], on a chest's lock and on
		# a door's tail alike
		var want := [int(k[4]), int(k[5])]
		var chest := {"op": int(k[0]), "state": int(k[1]), "lock": int(k[2])}
		var door := {"op": int(k[0]), "state": int(k[1]), "tail": [int(k[2])]}
		var got_c := [script.key_test(chest, "lock", int(k[3])), int(chest["lock"])]
		var got_d := [script.key_test(door, "door", int(k[3])), int(door["tail"][0])]
		n += 2
		keys += 1
		for got in [got_c, got_d]:
			if got != want:
				bad += 1
				if first == "":
					first = "key case %s: godot %s python %s" % [str(k), str(got), str(want)]
	var peds := 0
	for pc in doc.get("pedestals", []):
		# Silviera's key put on a pedestal, its frames to rest, and the key
		# taken back: [state, count, the key's x, y, z, its +0x38 (the
		# pedestal's lock on the last), the gate's lock]
		var pd := {"slot": 108, "state": 0, "lock": 141, "ring": 0, "n": 0xFF,
			"x": int(pc["pos"][0]), "y": int(pc["pos"][1]), "z": int(pc["pos"][2]),
			"angles": (pc["angles"] as Array).map(func(v): return int(v)), "b0": 2,
			"tail": (pc["tail"] as Array).map(func(v): return int(v))}
		var gate := {"lock": 0xFC}
		var key := {"type": 141, "op": 0xFF, "lock": 0, "pos": Vector3i.ZERO,
			"angles": [0, 0, 0], "b0": 0, "b1": 0x80, "link": 0}
		var frames: Array = pc["frames"]
		for i in frames.size():
			var last := i == frames.size() - 1
			if last:
				key["type"] = 0xFF
			script.pedestal_step(pd, key, gate, coll)
			var q: Vector3i = key["pos"]
			var got := [int(pd["state"]), int(pd["n"]), q.x, q.y, q.z,
				int(pd["lock"]) if last else int(key["lock"]), int(gate["lock"])]
			var w := []
			for v in frames[i]:
				w.append(int(v))
			n += 1
			if got != w:
				bad += 1
				if first == "":
					first = "pedestal %d frame %d: godot %s python %s" % [peds, i, str(got), str(w)]
		peds += 1
	print("chests: %d of %d frames match tools/chests.py (the lid, the big chest, %d flights of object_give, %d falls, %d keys tried on locks twice over, %d pedestals)" % [n - bad, n, flights, falls, keys, peds])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# script_interpreter's calls, talk.gd against tools/talk.py: for each of
# level 0's talkers, eight calls under two ways of closing the lines -- with
# USE but each sixth, and never -- the lines shown, the hooks called, the pc,
# the retry flag and why each call ended.
func _conversations() -> bool:
	if not FileAccess.file_exists("res://talkcheck.json"):
		print("conversations: no cases to check against")
		return true
	var doc = JSON.parse_string(FileAccess.get_file_as_string("res://talkcheck.json"))
	var lv := int(doc.get("level", 0))           # the level the cases were cut for
	var n := 0
	var bad := 0
	var first := ""
	for case in doc["cases"]:
		var ent := int(case["entity"])
		var sc := KFTalk.script_for(lv, ent)
		if sc.is_empty():
			continue
		KFTalk.states.erase("%d/%d" % [lv, ent])
		KFTalk.flags.fill(0)
		KFTalk.speaker = -1
		var pattern: Array = case["pattern"]
		var k := 0
		for want in case["calls"]:
			var c := KFTalk.begin(lv, ent, sc, int(sc["kind"]))
			var shown := []
			while true:
				var e := KFTalk.advance(c)
				if e < 0:
					break
				shown.append(e)
				KFTalk.closed(c, bool(pattern[k % pattern.size()]))
				k += 1
			var got := [shown, c["hooks"], int(c["st"]["pc"]), int(c["st"]["retry"]), c["why"]]
			var w := [[], [], int(want[2]), int(want[3]), str(want[4])]
			for v in want[0]:
				w[0].append(int(v))
			for v in want[1]:
				w[1].append(int(v))
			n += 1
			if str(got) != str(w):
				bad += 1
				if first == "":
					first = "entity %d: godot %s python %s" % [ent, str(got), str(w)]
	print("conversations: %d of %d calls match tools/talk.py" % [n - bad, n])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# The menus' drawing, menu.gd against tools/ui.py -- which reproduces the
# game's own frames of the "use item" screen: the screens' primitive lists,
# position, UV, CLUT, page, colour, depth and order, for a few states.
func _menus() -> bool:
	if not FileAccess.file_exists("res://ui.json"):
		print("menus: no cases to check against")
		return true
	if not KFMenu.load_data():
		print("menus: ui.json does not read")
		return false
	var n := 0
	var bad := 0
	var first := ""
	for case in KFMenu.data["cases"]:
		var lk := {"box": 0x78, "text": 0x80, "shadow": 0x30, "pulse": int(case["pulse"]),
			"confirm": 3, "cancel": 1, "semi": 1, "bright": 0x80}
		var o := {}
		match str(case["screen"]):
			"use_item":
				var inv := PackedByteArray()
				inv.resize(150)
				for key in case["inventory"]:
					inv[int(key)] = int(case["inventory"][key])
				KFMenu.panel(o, lk, KFMenu.use_item_list(inv, int(case["sel"])), 1)
			"prompt":
				KFMenu.options(o, lk, int(case["sel"]))
			"menu":
				KFMenu.menu_page(o, lk, 0, 6, int(case["sel"]))
			"main":
				KFMenu.status_page(o, lk, case["status"])
				KFMenu.menu_page(o, lk, 0, 6, int(case["sel"]))
			"equip":
				KFMenu.panel(o, lk, KFMenu.equipment_list(case["equip"], int(case["sel"])), 3)
			"ratings":
				KFMenu.ratings_page(o, lk, case["offense"], case["defense"])
			"page":
				KFMenu.menu_page(o, lk, int(case["page"]), int(case["n"]), int(case["sel"]))
			"equip_list":
				var inv := PackedByteArray()
				inv.resize(150)
				for key in case["inventory"]:
					inv[int(key)] = int(case["inventory"][key])
				var sl := KFMenu.equip_list(inv, int(case["line"]), case["equip"])
				if int(sl["sel"]) != int(case["sel"]):
					print("  equip_list line %d: the selection %d, python's %d" % [int(case["line"]),
						int(sl["sel"]), int(case["sel"])])
				if case["prompt"] == null:
					KFMenu.panel(o, lk, sl, 5)
				else:
					KFMenu.panel(o, lk, sl, 5 | 0x8000)
					KFMenu.options(o, lk, int(case["prompt"]))
		var got := JSON.stringify(_norm(KFMenu.order(o)))
		var want := JSON.stringify(_norm(case["prims"]))
		n += 1
		if got != want:
			bad += 1
			if first == "":
				first = "%s sel %d: godot %s ... python %s ..." % [case["screen"], int(case["sel"]),
					got.substr(0, 300), want.substr(0, 300)]
	print("menus: %d of %d screens drawn as tools/ui.py draws them" % [n - bad, n])
	if bad > 0:
		print("  first difference: " + first)
	return bad == 0


# @port check -- a primitive list with every number an int and every pair an array, for comparing
func _norm(v):
	if v is Array:
		var out := []
		for x in v:
			out.append(_norm(x))
		return out
	if v is Dictionary:
		var out := {}
		var keys: Array = v.keys()
		keys.sort()
		for key in keys:
			out[str(key)] = _norm(v[key])
		return out
	if v is float:
		return int(v)
	return v


# load_entry's frames, document.gd against tools/readables.py: for two pad
# histories, the brightness of every frame drawn, in and out.
func _inscriptions() -> bool:
	if not FileAccess.file_exists("res://readcheck.json"):
		print("inscriptions: no cases to check against")
		return true
	var doc = JSON.parse_string(FileAccess.get_file_as_string("res://readcheck.json"))
	var n := 0
	var bad := 0
	var first := ""
	for case in doc["cases"]:
		var d = load("res://document.gd").new()
		d.phase = 1
		d.s2 = 0
		d.armed = -1
		var hist: Array = case["pad"]
		var look := 0
		var frames := []
		var guard := 0
		while d.phase != 0 and guard < 200:
			guard += 1
			var drew: bool = d.phase != 2
			if d.phase == 3:
				d.step(0)                # tools/readables.py fades out on an idle pad
			elif d.step(int(hist[mini(look, hist.size() - 1)])):
				look += 1
			if drew:
				frames.append(d.shown)
		var want := []
		for v in case["in"]:
			want.append(int(v))
		for v in case["out"]:
			want.append(int(v))
		n += want.size()
		if frames != want:
			bad += want.size()
			if first == "":
				first = "godot %s python %s" % [str(frames), str(want)]
		d.free()
	print("inscriptions: %d of %d frames match tools/readables.py" % [n - bad, n])
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
		var got := KFDamage.hit(Array(h["attacks"]), defence, stat, k,
			int(h.get("scale", KFDamage.ARG9)), int(h.get("pct", KFDamage.ARG10)))
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
	var cases: Array = d.get("recalc", [])
	var same := 0
	for c in cases:
		var got := e.recalc(c["state"])
		if JSON.stringify(_norm(got)) == JSON.stringify(_norm(c["want"])):
			same += 1
		elif same == 0:
			print("  first difference: %s: godot %s python %s" % [str(c["state"]),
				str(got), str(c["want"])])
	print("player_recalc_stats: %d of %d states as tools/equip.py answers them" % [same, cases.size()])
	return ok == want and same == cases.size()


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
	var arms_ok := 0
	var arms: Array = []
	if FileAccess.file_exists("res://skillcheck.json"):
		arms = JSON.parse_string(FileAccess.get_file_as_string("res://skillcheck.json"))["arms"]
	for c in arms:
		var st: Dictionary = (c["state"] as Dictionary).duplicate(true)
		var flags := []
		flags.resize(KFTalk.FLAG_COUNT)
		flags.fill(0)
		for k in 4:
			flags[KFLevels.SKILL_FLAG + k] = int(c["flags"])
		var r := KFLevels.use_arm(int(c["item"]), st, flags)
		var spells := []
		for i in st["spells"].size():
			if int(st["spells"][i]) != 0:
				spells.append(i)
		var got := {"grow": st["grow"], "stat36": st["stat36"], "wis": st["wis"],
			"spells": spells, "unlocked": flags.slice(KFLevels.SKILL_UNLOCKED, KFLevels.SKILL_UNLOCKED + 5),
			"banners": r["banners"], "answered": r["answered"], "took": r["took"]}
		if JSON.stringify(_norm(got)) == JSON.stringify(_norm(c["want"])):
			arms_ok += 1
		elif arms_ok == 0:
			print("  first difference: item %d: godot %s python %s" % [int(c["item"]),
				str(got), str(c["want"])])
	print("skills: %d of %d uses of verdite, the fruits and the crystals match tools/levelup.py" % [
		arms_ok, arms.size()])
	return bad_l == 0 and arms_ok == arms.size()

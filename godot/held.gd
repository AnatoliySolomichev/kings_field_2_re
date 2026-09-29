extends Node3D
# The hand and weapon, while the player swings: draw_held_item (0x8003df50).
#
# It returns at once while the swing clock (0x801b25a4) is -1, so the weapon
# is seen only in a swing. Otherwise it draws model_table[0x20] -- FDAT.T
# entry 0x62 + the weapon, which sub_8002bdc0 installs when it is equipped --
# straight into the camera's space: no view matrix, the weapon record's +0x3c
# as RotMatrix's angles and its +0x34..+0x38 as the translation. The model is
# animated like a creature's (model_animate, anim.gd) by the swing's phase
# (0x801b25ae) and clock.
#
# RotMatrix is Rx Ry Rz with the textbook matrices; with Y and Z flipped into
# Godot's axes that is Rx(a) Ry(-b) Rz(-c), and the translation (x, -y, -z).

const WEAPON_KEY := 0x10000      # tools/anim.py files a weapon's model here

var player: Node
var skins := {}                  # weapon -> KFAnim skin
var nodes := {}                  # weapon -> its node, out of heldNN.gltf


func _ready() -> void:
	player = get_node_or_null("../..")      # Held -> Camera -> Player
	var models := get_node_or_null("HeldModels")
	if models == null:
		return
	for n in models.get_children():
		if n is Node3D and str(n.name).begins_with("w"):
			var w := int(str(n.name).substr(1))
			var nd := n as Node3D
			models.remove_child(nd)
			add_child(nd)
			nd.visible = false
			nodes[w] = nd


# @orig game:0x8003df50 draw_held_item  status:transcribed -- the place, the turn and the animation; lit by the level's class 0, not the player's cell
func _process(_dt: float) -> void:
	if player == null or KFWeapon.records.is_empty():
		return
	var w := int(player.get("weapon_id"))
	var ws: Dictionary = player.get("wstate")
	for k in nodes:
		(nodes[k] as Node3D).visible = false
	if not nodes.has(w) or ws == null or int(ws["clock"]) == -1:
		return
	var nd: Node3D = nodes[w]
	if not skins.has(w):
		var sk := KFAnim.skin(nd, WEAPON_KEY + w)
		if sk.is_empty():
			return
		skins[w] = sk
	var rec: PackedByteArray = KFWeapon.records[w]
	var t := Vector3(KFWeapon.s16(KFWeapon.u16(rec, 0x34)),
		KFWeapon.s16(KFWeapon.u16(rec, 0x36)), KFWeapon.s16(KFWeapon.u16(rec, 0x38)))
	var k := TAU / 4096.0
	var a := float(KFWeapon.u16(rec, 0x3C) & 0xFFF) * k
	var b := float(KFWeapon.u16(rec, 0x3E) & 0xFFF) * k
	var c := float(KFWeapon.u16(rec, 0x40) & 0xFFF) * k
	nd.transform = Transform3D(
		Basis(Vector3.RIGHT, a) * Basis(Vector3.UP, -b) * Basis(Vector3.BACK, -c),
		Vector3(t.x, -t.y, -t.z) / 1000.0)
	KFAnim.animate(skins[w], int(ws.get("phase", 0)), int(ws["clock"]))
	nd.visible = true

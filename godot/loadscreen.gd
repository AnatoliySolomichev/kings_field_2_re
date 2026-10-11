extends Node2D
# GAME.EXE's first screen: read_overlay_arg2 (0x8001fa60), which game_main
# calls once, straight after its block of initialisation, to learn what
# OPEN.EXE's title menu chose. NEW (overlay_arg2 0) answers -1 at once, and
# the game starts afresh. CONTINUE (1) runs the list of saves (0x8001fc5c):
# the player picks one, save_load_slot (0x8002860c) reads it -- the file, the
# sum, save_restore -- and the answer is its slot; backing out answers -1, a
# new game after all. Then game_main: a slot means save_loaded_fixup
# (0x80028f90), and either way enter_current_level loads the level in hand.
#
# The list is the port's own drawing. The game's is ui_panel's mode 8 under
# ui_menu_chrome and ui_prompt's kind 6, none of which tools/ui.py has read;
# what is kept is the choice: the saves by slot, UP and DOWN, a confirm loads
# and a cancel is a new game. The saves are the emulator's card files
# (KFCard), so a save made there is here the next time the title is passed.
#
# @exe game

const TICK_HZ := 15.0
const CONFIRM := KFPad.CIRCLE | KFPad.START
const CANCEL := KFPad.CROSS | KFPad.TRIANGLE

var shell: Node
var saves: Array = []
var sel := 0
var said := ""
var acc := 0.0


# @orig game:0x8001fa60 read_overlay_arg2  status:partial -- NEW answers -1 and CONTINUE runs the list; not the card's checks before it (0x80028034, 0x800280d4) or the screen it draws first
func _ready() -> void:
	var arg2: int = int(shell.overlay_arg2) if shell else 0
	if arg2 != 1:
		_enter(-1)
		return
	saves = KFCard.saves()
	if saves.is_empty():
		_enter(-1)
		return
	set_process(true)


# @port engine -- the list's frames at 15 a second, as the game's menus run
func _process(dt: float) -> void:
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / TICK_HZ:
		acc -= 1.0 / TICK_HZ
		KFPad.poll()
		_step()
	queue_redraw()


# @orig game:0x8001fc5c sub_8001fc5c  status:partial -- the choice: a slot by UP and DOWN, a confirm reads it, a cancel answers -1; not drawn as the game draws it
func _step() -> void:
	if KFPad.hit_mask(KFPad.UP):
		sel = (sel + saves.size() - 1) % saves.size()
	elif KFPad.hit_mask(KFPad.DOWN):
		sel = (sel + 1) % saves.size()
	elif KFPad.hit_mask(CONFIRM):
		var s: Dictionary = saves[sel]
		if not bool(s["valid"]):
			said = "slot %d: the sum is wrong -- the game would not read it" % int(s["slot"])
			return
		_enter(int(s["slot"]))
	elif KFPad.hit_mask(CANCEL):
		_enter(-1)


# game_main after read_overlay_arg2: a slot is read and put back, -1 starts
# afresh; then the level in hand is loaded -- the save's, or 0.
# @orig game:0x80014db4 game_main+0x1e0  status:partial -- the branch on read_overlay_arg2's answer and enter_current_level; the opening cutscene a new game plays is cutscene.gd's
func _enter(slot: int) -> void:
	set_process(false)
	if slot >= 0:
		var f := KFCard.read_slot(slot)
		if f.is_empty():
			said = "slot %d could not be read" % slot
			set_process(true)
			return
		KFCard.put(f)
		KFInfo.note("save: slot %d read off the card, level %d" % [slot, KFGame.level])
		var scene := "res://world%02d.tscn" % KFGame.level
		if not ResourceLoader.exists(scene):
			said = "level %d is not built (python3 tools/level3d.py %d)" % [KFGame.level, KFGame.level]
			KFCard.loaded = null
			set_process(true)
			return
		get_tree().change_scene_to_file(scene)
		return
	get_tree().change_scene_to_file(KFGame.scene_of(KFGame.current_level()))


# @port engine -- the list: each save's slot and title, the one chosen lit
func _draw() -> void:
	draw_rect(Rect2(0, 0, 640, 240), Color.BLACK)
	var font := ThemeDB.fallback_font
	var y := 40.0
	_text(font, Vector2(200, 24), "LOAD DATA", Color(0.8, 0.8, 0.9))
	for i in saves.size():
		var s: Dictionary = saves[i]
		var lit := i == sel
		var col := Color(1, 1, 0.8) if lit else Color(0.55, 0.55, 0.6)
		if not bool(s["valid"]):
			col = Color(0.7, 0.3, 0.3)
		_text(font, Vector2(150, y), ("> " if lit else "  ") + str(s["title"]), col)
		y += 16.0
	_text(font, Vector2(150, 212), "UP/DOWN chooses, CIRCLE loads, CROSS starts a new game",
		Color(0.5, 0.5, 0.55))
	if said != "":
		_text(font, Vector2(150, 226), said, Color(0.9, 0.5, 0.4))


# @port engine -- a line of text on the 640x240 screen, unsquashed
func _text(font: Font, at: Vector2, s: String, col: Color) -> void:
	draw_set_transform(at, 0.0, Vector2(1.0, 0.5))
	draw_string(font, Vector2.ZERO, s, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, col)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)

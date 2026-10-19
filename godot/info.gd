class_name KFInfo
extends Node
# The port's own words, in a window of their own beside the game's: the
# player's cell and state, the buttons, the comparison with the emulator, and
# a log of what happens -- creatures waking and struck, chests, things taken,
# lines said, banners raised. The game's screen keeps only what the game
# draws. F12 shows and hides the window; with no display (the self-test) there
# is none, and the old labels on the screen take the text again.
#
# @port-file engine

const KEEP := 400                   # log lines kept
const SIZE := Vector2i(600, 820)

static var status := ""             # player.gd's lines
static var compare := ""            # ghost.gd's lines
static var lines := PackedStringArray()
static var active := false          # a window is up, so the screen's labels go
static var changed := true
static var started := 0

var win: Window
var force := false                  # build the window even with no display (a test)
var top: Label
var cmp: Label
var log_box: TextEdit


# Something that happened, for the log -- and stdout, as print() was.
static func note(text: String) -> void:
	if started == 0:
		started = Time.get_ticks_msec()
	var t := float(Time.get_ticks_msec() - started) / 1000.0
	print(text)
	lines.append("%7.2f  %s" % [t, text])
	if lines.size() > KEEP:
		lines = lines.slice(lines.size() - KEEP)
	changed = true


func _ready() -> void:
	if DisplayServer.get_name() == "headless" and not force:
		return
	if started == 0:
		started = Time.get_ticks_msec()
	get_viewport().gui_embed_subwindows = false
	win = Window.new()
	win.title = "King's Field II port -- what is going on"
	win.size = SIZE
	win.wrap_controls = false
	win.close_requested.connect(func() -> void: _show(false))
	win.window_input.connect(_forward)
	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 6)
	var bg := ColorRect.new()
	bg.color = Color(0.07, 0.07, 0.09)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	win.add_child(bg)
	win.add_child(root)
	top = _label(root)
	cmp = _label(root)
	var head := Label.new()
	head.text = "log"
	head.add_theme_color_override("font_color", Color(0.6, 0.7, 0.9))
	root.add_child(head)
	log_box = TextEdit.new()
	log_box.editable = false
	log_box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	log_box.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	log_box.add_theme_font_size_override("font_size", 13)
	root.add_child(log_box)
	add_child(win)
	var at := DisplayServer.window_get_position()
	var sz := DisplayServer.window_get_size()
	win.position = Vector2i(at.x + sz.x + 8, at.y)
	_show(true)


# A key pressed while this window has the focus goes on to the game's window.
# The window manager focuses this one when it opens, and the pad reads Input,
# which every window feeds, so the game played on while F1..F12 -- which come
# through the game window's _unhandled_input alone -- went nowhere.
func _forward(e: InputEvent) -> void:
	if e is InputEventKey:
		get_viewport().push_input(e)


func _label(parent: Control) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", 14)
	l.add_theme_color_override("font_color", Color(0.9, 0.9, 0.85))
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(l)
	return l


func _show(on: bool) -> void:
	if win == null:
		return
	win.visible = on
	active = on
	for n in ["../UI/Hud", "../UI/Compare"]:
		var lab := get_node_or_null(n) as CanvasItem
		if lab:
			lab.visible = not on


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_F12:
		_show(win != null and not win.visible)


func _process(_dt: float) -> void:
	if win == null or not win.visible:
		return
	top.text = status + "\nbuttons down: " + KFPad.names_of(KFPad.now) \
		+ "\nF12 this window"
	cmp.text = compare
	if changed:
		changed = false
		log_box.text = "\n".join(lines)
		log_box.scroll_vertical = log_box.get_line_count()

extends Node
# The shell: SLUS_002.55, the four-kilobyte program the console actually boots.
#
# `shell_main` (0x80010038) does five things and then loops forever:
#
#     SetMem(2); CdRemove(); CdInit()
#     for (;;) {
#         while (Load(exe_name_table[next_index], exec_header) != 1) ;
#         CdRemove(); EnterCriticalSection();
#         Exec(exec_header, 0, 0);          <- the overlay runs, and returns
#         next_index = *(u8 *)0x800102f0;   <- what it left behind
#         CdInit();
#     }
#
# `exe_name_table` at 0x8001024c holds three names in this order:
# `cdrom:OPEN.EXE;1`, `cdrom:GAME.EXE;1`, `cdrom:END.EXE;1`. All three load at
# 0x80011000 -- the same address -- which is why an overlay cannot call
# another one and has to return to this instead. The shell sits at 0x80010000
# and so survives, and the three bytes at 0x800102f0, 0x800102f8 and 0x800102fa
# survive with it: the first says which overlay runs next, the other two are
# the only thing one overlay can tell the next.
#
# Those bytes are `next_exe`, `overlay_arg` and `overlay_arg2` below, and the
# port keeps them static for the same reason the shell keeps them out of the
# way of the overlays: a scene change here is an Exec there.

const OPEN := 0
const GAME := 1
const END := 2

static var next_exe := OPEN        # 0x800102f0, zero in the file: OPEN.EXE first
static var overlay_arg := 0        # 0x800102f8: open_main branches on it
static var overlay_arg2 := 0       # 0x800102fa: the title menu's choice

var screen: Node2D


func _ready() -> void:
	KFPad.apply()
	var layer := CanvasLayer.new()
	add_child(layer)
	screen = Node2D.new()
	screen.name = "Screen"
	layer.add_child(screen)
	get_viewport().size_changed.connect(_fit)
	_fit()
	_exec()


# The PlayStation's display is 640x240 here -- init_graphics (0x80012500) hands
# SetDefDrawEnv a width of 0x280 -- shown on a 4:3 screen, so every pixel is
# twice as tall as it is wide. The port keeps the game's own coordinates and
# does the stretching here, which is why every rectangle in opening.gd is the
# number that is in OPEN.EXE.
func _fit() -> void:
	if screen == null:
		return
	var v := Vector2(get_viewport().get_visible_rect().size)
	var s: float = minf(v.x / 640.0, v.y / 480.0)
	screen.scale = Vector2(s, s * 2.0)
	screen.position = Vector2((v.x - 640.0 * s) * 0.5, (v.y - 480.0 * s) * 0.5)


# Exec: run whichever overlay next_exe names.
func _exec() -> void:
	for c in screen.get_children():
		c.queue_free()
	match next_exe:
		OPEN:
			var op := preload("res://opening.gd").new()
			op.shell = self
			screen.add_child(op)
		GAME:
			# GAME.EXE. The port's game is the level the tools build, so this
			# is where the boot chain hands over to what the rest of the
			# project already had.
			get_tree().change_scene_to_file("res://world.tscn")
		END:
			var l := Label.new()
			l.text = "END.EXE is not ported. It plays \\OP\\M4.S, M5.S and M6.S."
			screen.add_child(l)


# What an overlay does when it returns: the shell reads the byte and goes round
# again. `open_main` reaches this by falling off the end of itself.
func overlay_returned() -> void:
	_exec()

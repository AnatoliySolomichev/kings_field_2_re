class_name KFGame
extends Node
# One frame of King's Field II, in the order the game runs it.
#
# `game_main` (0x80014bd4) zeroes twelve tables, loads a level, and then runs
# sixteen calls in a loop until the word at $gp+0x1e4 goes non-zero -- which is
# how the game ends: 2 hands the machine back to OPEN.EXE, 3 and 4 go to
# END.EXE with different arguments.
#
# The loop, read straight off it:
#
#    1  light_table_reset       0x800341e8   the 64 lighting entries, refilled
#    2  render_flags_reset      0x80034180   eleven render flags to defaults
#    3  0x80047010                           the object opcode interpreter
#    4  player_controller       0x80030fcc   pad, then turn, look, walk, height
#    5  actor_tick_driver       0x80052e5c   the 199 creature slots
#    6  effect_driver           0x8005bc50   128 effect slots -> effect_tick
#    7  spawn_anywhere = 0                   0x801b24f2, cleared every frame
#    8  level_overlay_tick      0x8005eb20   the level's own code, and fades
#    9  level_load              0x80018358   acts when a transition is pending
#   10  cutscene_step           0x80061940   the scene running, if one is
#   11  camera_pose             0x8002b330   the eye and the three view angles
#   12  audio_listener_set      0x800156bc   the same pose, for 3D sound
#   13  light_table_step        0x80034300   interpolate the lighting
#   14  res_upload_vram         0x80018cd0   a texture into VRAM, if one waits
#   15  res_upload_spu          0x80015a48   sound into the SPU, if one waits
#   16  render_frame            0x800422b8   everything drawn
#
# and render_frame is seventeen more:
#
#    view_pose_set, texture_scroll_step, message_tick, view_matrix_build,
#    frame_begin_3d, effect_timers_step, draw_held_item, 0x80016a98,
#    draw_model_cell_lit, 0x80041e68, 0x80041d9c, draw_terrain, render_walk,
#    overlay_plane_18, overlay_plane_19, overlay_plane_17, 0x8003d568,
#    0x8003d64c, 0x8003d79c, frame_end_3d, 0x80019614, resource_sweep
#
# **This file is the shape, not the whole.** Each step below either calls the
# port's copy or says which address it stands for and that nothing runs. That
# is on purpose: a frame with named holes is worth more than a frame that
# quietly does fifteen of sixteen things, because the holes are the work list
# and `tools/portmap.py --next` ranks them.
#
# The port's own scene tree still drives the parts that are ported -- player.gd
# has its own _process -- so this node does not take over. It is the map.
#
# @exe game

# What the game does with $gp+0x1e4 when it wants to stop.
enum Exit { RUNNING = 0, TO_OPENING = 2, TO_ENDING_A = 3, TO_ENDING_B = 4 }

# Every step of the loop, in order: the address it stands for, a name, and
# whether the port has it. Read by the frame readout and by nothing else.
# @orig game:0x80014f24 game_main+0x350  status:partial -- the loop's sixteen steps in order, as data; nothing here runs them
# Set while a routine runs frames of its own -- object_give's flight and spin
# (godot/loot.gd) -- in which game_main's loop does not turn: the player, the
# creatures, the doors and the effects stand still, and only render_frame's
# part goes on (the banners, messages.gd).
static var modal := false
# OPTION 2's five bytes (0x801b25dd, de, df, e0, e4): the panel's style and
# the compass's (0..2, a bit each for the two sets of records render_frame
# switches on), the chosen thing's turning model in the menus' lists, the
# walking bob, and the menus' boxes clear (1) or solid (0); a new
# character's, sub_8002b64c
static var display := [2, 2, 1, 1, 1]
# OPTION 1's three bytes (0x801b25db, dc, e1): the sound effects' and the
# music's volumes and the brightness; a new character's, sub_8002b64c
static var sound := [0x80, 0x50, 0x80]
# shop 0's stock (0x80080718, 150 bytes), which buying runs down and selling
# fills -- the save carries it; empty until the menu's data gives the disc's
static var shop0 := PackedByteArray()
# the guide's table (0x80081780, 150 bytes): the wise fruits' count each
# thing's full description wants -- level 1's sage sets a thing's to 4; the
# save carries it; empty until the menu's data gives the disc's
static var guide_require := PackedByteArray()
# While the port follows the emulator (ghost.gd, C, with bp16 writing
# live.txt): the creatures, the doors and the swing are the game's, laid over
# the port's every frame, and their own machines stand still.
static var follow := false
# The level the world scene is of: set by whoever loads one (a crossing, the
# comparison following the game); -1 until then, and the level the project was
# built for stands in -- tools/level3d.py names it "King's Field II - level N".
static var level := -1
# The level block in hand, 0x8018fad8's five bytes: the level second. A
# crossing asks for another (crossing.gd).
static var block: Array = []
# screen_fade's four bytes (0x801aeafa..0x801aeafd): the mode -- 0xff none,
# the low two bits the blend, bit 0x80 over the panel -- and the colour.
# render_flags_reset puts the mode back to 0xff every frame of the game's, so
# whoever fades says so every frame (player.gd's tick, crossing.gd's fades).
static var screen := [0xFF, 0, 0, 0]
# F3, the port's own test switch (player.gd), not the game's: the player
# loses no HP -- the blows, the falls, the poison and the second bow leave it
# as it was, so nothing kills -- and every blow or spell of the player's
# that reaches a creature takes all of its HP, so it dies the game's way:
# its dying behaviour, the gold and the thing actor_tick's drops leave, the
# experience, the level's entry 19. What the game makes nothing hurt (the
# models actors.gd's UNHIT names, a body already falling) stays unhurt.
static var test := false


# game_main's test of the word at $gp+0x1e4, after render_frame, the frame's
# last call: 3 hands the machine to END.EXE with overlay_arg 2 (all three
# movies), 4 with 3 (M6 alone), by the shell's two bytes; 2, OPEN.EXE, is
# QUIT GAME's (menu.gd _quit). sub_80015064 first -- the sound, PadStop,
# ResetGraph(3) -- which is Godot's to do.
# @orig game:0x80014fb0 game_main+0x3dc  status:transcribed -- the test of the word and its switch
# @orig game:0x80014ff4 game_main+0x420  status:transcribed -- the arms of 3 and 4: next_exe 2, overlay_arg 2 or 3; not sub_80015064
static func leave(tree: SceneTree, word: int) -> void:
	if word != Exit.TO_ENDING_A and word != Exit.TO_ENDING_B:
		return
	var shell = load("res://boot.gd")
	shell.next_exe = shell.END
	shell.overlay_arg = 2 if word == Exit.TO_ENDING_A else 3
	KFInfo.note("game: the word at $gp+0x1e4 is %d -- END.EXE, overlay_arg %d" % [word,
		int(shell.overlay_arg)])
	modal = false
	tree.change_scene_to_file("res://boot.tscn")


# @orig game:0x8003d624 screen_fade  status:verified -- through screen_fade_draw, 840 of 840 quads of the game's own over every snapshot (tools/fade.py)
static func screen_fade(mode: int, r: int, g: int, b: int) -> void:
	screen = [mode & 0xFF, r & 0xFF, g & 0xFF, b & 0xFF]


# fade_frames (0x80046c00), the screen's bytes of each of its frames: s from
# `from` by `step` to `to`, both ends in, and v = (s * s) >> 16 held to 0xff
# for all three colours. Its frames are the game's with nothing but the
# drawing going on -- the caller holds the world while they run (KFGame.modal).
# @orig game:0x80046c00 fade_frames  status:partial -- the screen's bytes, 40 of 40 runs of the game's own (tools/fade.py); the frames themselves are the caller's, the world held: not res_upload_spu or res_upload_vram
static func fade_frames(mode: int, from: int, to: int, step: int) -> Array:
	var out := []
	var s := from
	while true:
		var v := mini(0xFF, (s * s) >> 16)
		out.append([mode & 0xFF, v, v, v])
		if s == to or out.size() > 0x200:
			return out
		s += step
	return out


# screen_fade_draw (0x8003d568), render_frame's seventeenth call: nothing for
# a mode of 0xff; else a POLY_FT4 over the screen (prim_ft4_rect) of a white
# texel (CLUT 0x7a8d's first, with the STP bit) under the colour, so (31 * c)
# >> 7 of white held to 31 each channel, put on the screen by the mode's
# blend -- 0 half and half, 1 adding, 2 taking away, 3 adding a quarter --
# at depth 1 with bit 0x80, over the panel, else 0x40, under it.
# {blend, five (the three 5-bit colours), over} or {}.
# @orig game:0x8003d568 screen_fade_draw  status:verified -- 840 of 840 quads of the game's own over every snapshot, and its texture in 19 of 19 snapshots' VRAM (tools/fade.py)
static func fade_quad(scr: Array) -> Dictionary:
	var m := int(scr[0])
	if m == 0xFF:
		return {}
	var five := []
	for i in 3:
		five.append(mini(31, (31 * int(scr[1 + i])) >> 7))
	return {"blend": m & 3, "five": five, "over": (m & 0x80) != 0}


# @port engine -- the level in hand: the one loaded, or the project's own
static func current_level() -> int:
	if level >= 0:
		return level
	var name := str(ProjectSettings.get_setting("application/config/name", ""))
	var i := name.rfind("level ")
	return int(name.substr(i + 6)) if i >= 0 else 0


# @port engine -- the scene of a level: worldNN.tscn, which tools/level3d.py writes for each level it builds
static func scene_of(lv: int) -> String:
	var path := "res://world%02d.tscn" % lv
	return path if ResourceLoader.exists(path) else "res://world.tscn"

const FRAME := [
	[0x800341e8, "light_table_reset", false],
	[0x80034180, "render_flags_reset", false],
	[0x80047010, "object_interpreter", true],    # doors.gd, objects.gd: part
	[0x80030fcc, "player_controller", true],
	[0x80052e5c, "actor_tick_driver", true],
	[0x8005bc50, "effect_driver", true],         # effects.gd: the spores
	[0x00000000, "spawn_anywhere = 0", true],
	[0x8005eb20, "level_overlay_tick", false],
	[0x80018358, "level_load", false],
	[0x80061940, "cutscene_step", false],
	[0x8002b330, "camera_pose", true],
	[0x800156bc, "audio_listener_set", false],
	[0x80034300, "light_table_step", false],
	[0x80018cd0, "res_upload_vram", false],
	[0x80015a48, "res_upload_spu", false],
	[0x800422b8, "render_frame", true],
]


# @port check -- counts the steps marked ported, for the frame readout
static func ported() -> int:
	var n := 0
	for step in FRAME:
		if step[2]:
			n += 1
	return n


# @port check -- the frame readout's line
static func summary() -> String:
	return "frame: %d of %d steps in the port" % [ported(), FRAME.size()]


# The eye, as camera_pose builds it (0x8002b330): the player's X and Z, and
# Y + bob + crouch - EYE_HEIGHT. Y points down, so minus is up.
const EYE_HEIGHT := 0x640            # 0x8002b370; 1600, and sync_player_pos adds it back


# @orig game:0x8002b330 camera_pose  status:partial -- the eye; the three view angles are player.gd's _view
static func camera_pose(px: int, py: int, pz: int, bob: int,
		crouch: int) -> Vector3i:
	return Vector3i(px, (py + bob + crouch) - EYE_HEIGHT, pz)

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

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
#    6  ai_driver               0x8005bc50   128 behaviour slots -> actor_ai
#    7  spawn_anywhere = 0                   0x801b24f2, cleared every frame
#    8  level_overlay_tick      0x8005eb20   the level's own code, and fades
#    9  level_load              0x80018358   acts when a transition is pending
#   10  flag_gate               0x80061940   the story flags
#   11  camera_pose             0x8002b330   the eye and the three view angles
#   12  audio_listener_set      0x800156bc   the same pose, for 3D sound
#   13  light_table_step        0x80034300   interpolate the lighting
#   14  0x80018cd0                           the sound task, type 0x40
#   15  0x80015a48                           the sound task, type 0x30
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
# @orig game:0x80014bd4 game_main  status:partial -- the order, and the six steps that exist

# What the game does with $gp+0x1e4 when it wants to stop.
enum Exit { RUNNING = 0, TO_OPENING = 2, TO_ENDING_A = 3, TO_ENDING_B = 4 }

# Every step of the loop, in order: the address it stands for, a name, and
# whether the port has it. Read by the frame readout and by nothing else.
const FRAME := [
	[0x800341e8, "light_table_reset", false],
	[0x80034180, "render_flags_reset", false],
	[0x80047010, "object_interpreter", false],
	[0x80030fcc, "player_controller", true],
	[0x80052e5c, "actor_tick_driver", true],
	[0x8005bc50, "ai_driver", false],
	[0x00000000, "spawn_anywhere = 0", true],
	[0x8005eb20, "level_overlay_tick", false],
	[0x80018358, "level_load", false],
	[0x80061940, "flag_gate", false],
	[0x8002b330, "camera_pose", true],
	[0x800156bc, "audio_listener_set", false],
	[0x80034300, "light_table_step", false],
	[0x80018cd0, "sound_task_40", false],
	[0x80015a48, "sound_task_30", false],
	[0x800422b8, "render_frame", true],
]


static func ported() -> int:
	var n := 0
	for step in FRAME:
		if step[2]:
			n += 1
	return n


static func summary() -> String:
	return "frame: %d of %d steps in the port" % [ported(), FRAME.size()]


# The eye, as camera_pose builds it (0x8002b330): the player's X and Z, and
# Y + bob + crouch - EYE_HEIGHT. Y points down, so minus is up.
# @orig game:0x8002b330 camera_pose  status:transcribed
const EYE_HEIGHT := 0x640            # 1600, and sync_player_pos adds it back


static func camera_pose(px: int, py: int, pz: int, bob: int,
		crouch: int) -> Vector3i:
	return Vector3i(px, (py + bob + crouch) - EYE_HEIGHT, pz)

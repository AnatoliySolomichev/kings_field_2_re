extends Node3D
# Movement, transcribed from the game's own player_vertical at 0x8002ed60.
#
#   F1  walk / fly      G  the collision, drawn      Esc  release the mouse
#   the game's buttons on the emulator's keys (godot/pad.gd): arrows, Q/R, Z, X...
#   Shift  faster       PgUp/PgDn  up / down, flying
#
# This was a guess -- "take the floor from the position you tried to reach and
# snap to it" -- and then briefly a different mistake: `player_move` at
# 0x8002f320, read carefully out of the MIPS and wrong about which routine
# matters. A recording settled it: that one ran 69 times in a whole session,
# every time in the knockback after dying, while the player walked about for
# eight hundred frames without it.
#
# What walking actually does is not a physics model. Each frame the height moves
# toward the surface by a limited amount, and inside 0x80 it is *placed* on the
# surface exactly:
#
#   d = surface - y            (Y is down, so d < 0 means the ground is higher)
#   |d| < 0x80      y = surface        placed, not eased
#   |d| < 0x100     y += 0x80  toward it
#   |d| < 0x200     y += 0x100
#   |d| < 0x400     y += 0x200 rising only
#   d < -0x400      state 0x20: launched upward at -0x96, decaying by 0x0a
#   d >  0x400      state 0x40: a fall from 0x28, gaining 0x28 a frame
#   0x200 < d       state 0x10: a shorter drop, gaining 0x50 -- twice as fast
#
# Descending also asks the collision at y+1 first and stays put if that is
# blocked -- which is what keeps you on a bridge instead of dropping to the
# floor of the room beneath it. State 0x40 is the one that tests the collision
# mask rather than the surface, so it is what carries you off a ledge.
#
# So there is no gravity while walking and no jump: you are carried up steps and
# down them at a fixed rate, and only a gap wider than 0x400 becomes a fall.
#
# Flying moves the position directly and asks the collision nothing, which is
# the point -- this level has rooms the game never lets anyone reach.
#
# Every constant below is read off the code and checked against the game:
# emu/bp15.lua watched the player's own coordinates and named each instruction
# that stores the height, and tools/movement.py picks the same one on 48 of 48.
#
# The horizontal is read now too, and checked the same way: over three minutes of
# ordinary play, tools/replay.py reproduces 6682 of 6682 frames of the height and
# 6186 of 6682 of the ground move -- and every one of the 496 that differ is a
# frame where the step is blocked, which is the wall slide. That is the one piece
# still missing: the game turns a refused step along the wall's own facing, out
# of 0x801e6498 and 0x801e649c, and tools/collision.py does not compute those.
# Walking into a wall therefore stops dead here where the game would slide.
# *Update:* the refusals and the slides were read since -- _horizontal below,
# 124 891 of 125 116 ground frames of the recording.
#
# @exe game

const UNIT := 1000.0
const CELL := 2048.0
const SPEED_MAX := 200               # 0x801b2664 in the recorded session; the
                                     # acceleration is a quarter of it, the decay an eighth
const SPEED_MAX_RUN := 400           # not the game's -- its run is USE held, to 336
                                     # (frame_caps); Shift is for getting about quickly
const FLY := 9000.0
const STEP_UP := 0x500               # player_horizontal: the most a step may climb
const SHRINK := 0x16                 # and how much shorter each retry is
const AROUND := 0x370                # how far past an object's radius the push-out goes
const STEEP_PUSH := 0x40             # the least push a taken step gains
const CREATURE_BIT := 0x10           # collide_query's mask bit for a creature
const PLAYER_ACTOR_MASK := 4         # 0x8018faa8 while the player moves
const RECT_TRIES := [0x400, 0x400, 0x3E8, 0x3E8, 0x418, 0x418]   # the turns back
                                     # along a rectangle's axes, one a try
const PITCH_LIMIT := 0x2bc           # player_look stops the pitch here, either way
const EYE := 1.6
# Read off the code, no longer a guess. The game's clock is the vertical blank:
# vblank_tick (0x80019570), hooked to root counter 3 by 0x8001a438, adds one to
# 0x801c12ec every blank -- and one minute of play to 0x801b2588 every 3600 of
# them, so 60 a second. render_frame ends every pass of game_main's loop with
# frame_limit (0x80019614), which calls VSync(0) until that count reaches 4 and
# then zeroes it: **a frame lasts at least four blanks, so the game runs at 15
# frames a second**, slower only when a frame's own work overruns. This was 30
# for a long time, from two wall-clock measurements an uncapped emulator could
# not give -- which made the port walk and turn twice as fast as the game.
const TICK_HZ := 15.0

# player_vertical's own constants, at the addresses named
const V_START := 0x28                # 0x8002f254, the seed for either fall
const V_ACCEL_SHORT := 0x50          # 0x8002ee20, state 0x10
const V_ACCEL_LONG := 0x28           # 0x8002ef18, state 0x40 -- the longer fall
const V_ACCEL_RISE := 0xA            # 0x8002eebc, state 0x20
const V_RECOIL := 0x12C              # 0x8002f0ac, state 0x50
const V_LAND_SLACK := 0x64           # 0x8002ee2c
const V_SQUASH := 0x200              # 0x8002efec
const FALL_HURTS := 0x1E0            # 0x8002ef74
const V_LAUNCH := -0x96              # 0x8002f1ac

# The head bob, 0x8002f298. The phase accumulates the walking speed every frame
# and the height follows a *rectified* sine -- two lifts a stride, one a footfall.
# It accumulates whether or not the step was taken, which is why walking into a
# wall still bobs the camera. That is the game's behaviour, so it is the port's.
const BOB_SHIFT := 5                 # 0x8002f2c4
const EYE_UNITS := 1600.0            # 0x640 at 0x80028e10

# The buttons come through the game's own binding table now -- see godot/pad.gd
# and BOOT.md. player_controller (0x80030fcc) reads the pad once a frame, keeps
# the word at 0x801b265c and hands it to player_walk and player_turn, which ask
# the table which button each of their slots holds. With the default scheme
# that is: forward and back on UP and DOWN, strafe on L1 and R1, turn on LEFT
# and RIGHT, and this port's keyboard stands in for those.
# The turn, read off player_look (0x8002f5c0) and the cap the controller sets
# before calling it (0x80031194). It is the same shape as the walk: a rate that
# ramps towards a cap by a quarter of it each frame and decays to zero by the
# same quarter, and the facing is that rate added to 0x801b2612 every frame,
# wrapped to 0xfff.
#
# The cap is not constant, and this is a thing a player can feel: 0x28 standing
# still and 0x20 with forward or back held (0x800311a8 writes 0x28 only when
# neither `bind_forward` nor `bind_back` is down). So you turn about a fifth
# faster when you are not walking. Out of 0x1000 to the circle, 0x20 is 2.81
# degrees a frame and 0x28 is 3.52.
#
# And a third: while turn_slow_timer (0x801b2566, player_take_hit's effect 5)
# is running, 0x80031254 halves the cap every frame and counts it down --
# frame_caps, with the run.
# Dying, out of player_controller. All 128 ai_slots go to 0xff, and then
# either item 107 -- "this crystal gives total recovery to the injured body and
# mind" -- is consumed and the player is put back at a fixed spot, or the
# character is made anew and the story flags are cleared.
#
# -0x3a80 is -128 * 117, and 117 is the height byte of cell (57, 24) on level
# 0, so the spot is a real place with the floor under it.
const REVIVE_ITEM := 107             # 0x6b, at 0x8002a558 in player_controller
const REVIVE_POS := Vector3i(0x1C800, -0x3A80, 0xC000)
const REVIVE_FACING := 0x2D5
const REVIVE_LAYER := 5

const TURN_MAX_STILL := 0x28         # 0x800311a8
const TURN_MAX_MOVING := 0x20        # 0x8003118c

var coll := KFCollision.new()
var have_coll := false
var flying := true
# 0x801b2610, the view pitch, 0x1000 to the turn and positive looking down, and
# 0x801b264e, the rate player_look drives it by.
var pitch := 0
var pitch_rate := 0
var look_acc := 0.0
# the position the game would keep: world units, Y increasing downward
var gx := 0
var gy := 0
var gz := 0
# the vertical state machine: the byte at 0x801b25e8 and the s16 at 0x801b2656
var vstate := 0
var vvel := 0
var step := Vector3i.ZERO          # 0x801b2600: the last step player_horizontal took, x z, and player_vertical's y
# 0x801b2644: the floor the player stands on, as collision_layer_offset was
# when player_horizontal last took a step -- 0 the cell's lower layer, 5 its
# upper; new_character and the crystal's revive put 5 (0x8002b614,
# 0x80031dcc). use_item's truth glass asks it.
var layer := 5
# 0x801b2648 and 0x801b2646: the two ground speeds the ramp drives
var fwd_speed := 0
var stf_speed := 0
# 0x801b264c, the turn rate the ramp drives, and 0x801b2612, the facing itself
var turn_rate := 0
var facing := 0
# 0x801b2652 and 0x801b2650: the bob's phase and the lift it produces
var bob_phase := 0
var bob := 0
var acc := 0.0
var last_surface := KFCollision.NO_SURFACE
# What the panel shows (hud.gd): HP 0x801b24fc, MP 0x801b2500, and the weapon
# and magic meters 0x801b2502 and 0x801b2506, full at 5000. A new character has
# 50 and 30 and every snapshot at rest holds both meters at 5000; nothing in
# the port spends them yet, and while comparing they follow the game's.
var hp := 50
var hp_max := 50
var mp := 30
var weapon_meter := 5000
var magic_meter := 5000
# What a blow leaves behind (tools/knock.py): player_state (0x801b25e5) 0x10
# while knocked back and 0x12 while stunned; the push (player_velocity,
# 0x801b266c); the tilt the view gets (0x801b2618, pitch yaw roll) and its
# velocity (0x801b2674); the landing's crouch (0x801b2654) and the view's nod
# while falling (0x801b2628); the flash's length (0x801b265a).
var pstate := 0
var push := [0, 0, 0]
var tilt := [0, 0, 0]
var tilt_vel := [0, 0, 0]
var crouch := 0
var dip := 0
var flash := 0
# The hit's flash itself, 0x801b2658: 0xdac from apply_damage, 0x960 from the
# poison; sub_80030e14 takes `flash` off it every frame and adds red over the
# screen by it.
var flash_colour := 0
var tints_now := []                  # this frame's two rectangles (status_tick)
# What player_recalc_stats leaves (KFEquip.recalc, recalc_stats below): the
# eight offense ratings a blow carries (0x801b2538), the eight defence ones a
# hit meets (0x801b254a), the effective stat (0x801b2524) both scale by, and
# the five working skills (0x801b2526) the magic meter refills by. A fresh
# character's: the excellector's offense (weapon 0), the leather plate's
# [13, 6, 4] and 20.
var offense: Array = [39, 32, 9, 0, 0, 0, 0, 0]
var defence: Array = [13, 6, 4, 0, 0, 0, 0, 0]
var stat := 20
var working: Array = [0, 0, 0, 0, 10]
# What is worn, 0x801b25d4..0x801b25da, 0xff for nothing: new_character puts
# the leather plate (42) in the second (0x8002bb84(0x2a, 1)).
var worn: Array = [0xFF, 42, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
var equip := KFEquip.new()
# The magic in hand and the button's spell or thing (0x801b25ab, 0x801b25ac,
# 0x801b25ad): new_character clears all three, and every snapshot has them so.
var spell_a := 0xFF
var spell_b := 0xFF
var item_b := 0xFF
# equip_armour's slots 0..6 are the worn bytes 0x801b25d4, d5, d7, d8, d6, d9
# and da -- head, body, arms, feet, shield and the two items
const WORN_OF_SLOT := [0, 1, 3, 4, 2, 5, 6]
const NO_WEAPON := 0xFF
# The weapon in hand (0x801b25af) and its swing (tools/weapon.py): the clock
# 0x801b25a4, the pause 0x801b24f3, the hit and sound times 0x801b25a6 and
# 0x801b25a8, the strength 0x801b2504; the meter is weapon_meter. The
# character's level and experience (award_exp), and 0x801b2508, the strong
# blows counted towards the stat.
var weapon_id := 0
var wstate := {"clock": -1, "meter": 5000, "pause": 0, "hit": 5000,
	"sound": 5000, "strength": 0}
var attack_latch := false
# The combination (player_turn 0x80030298): 0x801b25aa, the frames left for
# the next press, as time, and the pointer 0x801b258c as next; and, like the
# attack latch, the button word of a rendered frame that newly pressed USE,
# ATTACK or ACTION, kept until a tick takes it.
var combo := {"time": 0, "next": 0}
var combo_latch := 0
var character := {}
var strong_hits := 0
# Dying (player state 0x11): the frames counted at 0x801b261e, and the fade
# screen_fade (KFGame) takes the screen down with; the inventory (inventory_a
# and _b, KFItems), whose crystal (item 107) revives, and the gold (player_gold).
var death_frames := 0
var fade := 0
var inventory := KFItems.new()
var gold := 0
# object_give writes the view's pitch (0x801b2608) itself while it runs:
# -1 when camera_pose's own goes, else the angle the view is drawn at.
var view_pitch := -1
# The USE button held (player_turn, 0x8003002c): both meters drain, and
# damage_scale (0x801b24f8), the K the stat's share of the defence is scaled
# by in damage_of_type, falls; the magic meter's pause is 0x801b24f4.
var damage_k := 0x1000
# Poison (0x801b255c): frames left; player_take_hit's effect 3 sets it to
# 0x384 unless the roll against the resistance (0x801b255a, the ninth defence
# half -- 0 for a new character) goes the player's way.
var poison := 0
var resist := 0
# The rest of what a hit can leave (player_take_hit, tools/status.py): the
# curse, the darkness and the light, each a level and a timer the status ramp
# runs (0x801b255e/0x801b2560, 0x801b2562/0x801b2564, 0x801b2570/0x801b2572);
# 0x801b25b4 and 0x801b256c, either of which lets no hit through; and the
# three bonus timers player_recalc_stats reads (0x801b256a, 0x801b256e,
# 0x801b2578). The save holds all of them but 0x801b25b4.
var curse := [0, 0]
var dark := [0, 0]
var light := [0, 0]
var guard := 0
var shielded := 0
var bonus := [0, 0, 0]
# Casting (tools/magic.py): the action pending (0x801b25e9, 0xff none), the
# shots it has left (0x801b25ea), the frames between them (0x801b25eb) and
# to the next (0x801b25ec); the cast's offset from the eye (0x801b2630,
# 0x801b2632, 0x801b2634); the spell being cast (casting_spell, 0x801b2590,
# -1 none); the five practice counts (0x801b250a..0x801b2512); and
# 0x801b2576, which holds MP at its most while it runs.
var pending := 0xFF
var shots := 0
var shot_gap := 0
var shot_delay := 0
var cast_off := [0, 0, 0]
var casting := -1
var practice := [0, 0, 0, 0, 0]
var mp_hold := 0
var magic_pause := 0
var use_prev := false
# What player_controller makes of the frame's caps (0x800311b4..0x800313ec),
# and the run: while USE has been held two frames running, player_turn counts
# 0x801b24f5 down to 0, and the next frame player_controller ramps 0x801b24f6
# by 0x320 to 0xaf0 -- the speed cap 200 grows by 0xaf0 / 0x1000 of itself,
# to 336, and the turn by half that; let go, it sets 0x801b24f5 back to 1 and
# the ramp falls back. turn_slow_timer (0x801b2566) runs it the other way, to
# -0xce4, with the turn halved; and 0x801b2568, the paralysis, stops both.
# A new character and a loaded save start them at 0 (sub_80028e9c).
var caps := {"run": 0, "mod": 0, "slow": 0, "paralysis": 0}
var speed_cap := SPEED_MAX
var turn_cap := TURN_MAX_STILL
# The creatures in the way this frame, as [x, y, z, radius, height, flags]:
# actors.gd's awake ones, taken before the step because the game moves the
# player before actor_tick_driver.
var creatures: Array = []


# @orig game:0x80031d60 checks_item_107  status:partial -- the crystal's spot, where a death with item 107 puts the player; loading the collision and the tables is the port's
func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	have_coll = coll.load_from("res://coll%02d.json" % _level())
	KFWeapon.load_from()
	character = KFLevels.fresh()
	equip.load_tables()
	gx = int(position.x * UNIT)
	gy = int(-position.y * UNIT)
	gz = int(-position.z * UNIT)
	facing = int(rotation.y / TAU * 4096.0) & 0xFFF
	if not (carried is Array):      # a new game, or a death with no crystal
		inventory.start()
	if carried is Array:            # the crystal kept what the player had
		inventory = carried[0]
		gold = int(carried[1])
		character = carried[2]
		weapon_id = int(carried[3])
		worn = carried[4]
		spell_a = int(carried[5][0])
		spell_b = int(carried[5][1])
		item_b = int(carried[5][2])
	carried = null
	recalc_stats()
	if respawn is Array:
		flying = false              # back on foot after a death
		if respawn.size() == 4:     # the crystal's spot (0x80031d60)
			gx = int(respawn[0])
			gy = int(respawn[1])
			gz = int(respawn[2])
			facing = int(respawn[3])
			rotation.y = float(facing) * TAU / 4096.0
			_to_godot()
	respawn = null
	if arrive is Array:             # walked in from another level (crossing.gd)
		flying = false
		gx = int(arrive[0])
		gy = int(arrive[1])
		gz = int(arrive[2])
		facing = int(arrive[3])
		pitch = int(arrive[4])
		vstate = int(arrive[5])
		vvel = int(arrive[6])
		fwd_speed = int(arrive[7])
		stf_speed = int(arrive[8])
		hp = int(arrive[9])
		hp_max = int(arrive[10])
		mp = int(arrive[11])
		weapon_meter = int(arrive[12])
		magic_meter = int(arrive[13])
		poison = int(arrive[14])
		layer = int(arrive[15])
		rotation.y = float(facing) * TAU / 4096.0
		_to_godot()
	arrive = null
	if KFCard.loaded is Dictionary:  # a save off the card, picked in loadscreen.gd
		take_save(KFCard.loaded)
		KFCard.loaded = null
	_refresh()


# What a crossing takes over into the other level's world (crossing.gd): what
# the crystal keeps -- the inventory, the gold, the character, what is worn
# and wielded, the magic -- and where the player stands, shifted, facing,
# looking, falling and walking, with HP, MP, the meters and the poison.
# @port engine -- the player's state, kept across the change of world
func carry_over(p: Vector3i) -> void:
	carried = [inventory, gold, character, weapon_id, worn, [spell_a, spell_b, item_b]]
	arrive = [p.x, p.y, p.z, facing, pitch, vstate, vvel, fwd_speed, stf_speed,
		hp, hp_max, mp, weapon_meter, magic_meter, poison, layer]


# A save, as save_restore put it back (KFCard.restore): where the player
# stands and faces, the character, what is carried, worn and wielded, the
# magic in hand, HP and MP, the poison and the strong blows. Then what
# save_loaded_fixup (0x80028f90) does before the level is entered:
# sub_80028e9c clears the bob, the crouch, the fall and the player's state;
# equip_weapon takes the weapon up again, its meter at 0, and recalculates the
# stats; and the magic meter is game_main's block_zero of the player block,
# which nothing restores.
# @orig game:0x8005ffd0 save_restore  status:partial -- the player's fields the port keeps; the curse and the timers (0x801b255e..0x801b2578), 0x801b24ec, 0x801b2522, 0x801b250a..0x801b2512, 0x801b2514, 0x801b24f1, the panel's bytes and the minutes are read and not used
# @orig game:0x80028f90 save_loaded_fixup  status:partial -- the clearing (sub_80028e9c), equip_weapon and the stats; not equip_armour(0xff, 0xff), the three bonus timers' effects respawned (effect_spawn), set_spell_a/b's resources or the control scheme
func take_save(f: Dictionary) -> void:
	flying = false
	gx = KFCard.num(f, "x", true)
	gy = KFCard.num(f, "y", true)
	gz = KFCard.num(f, "z", true)
	var pf := KFCard.num(f, "pitch_facing")
	pitch = coll._s16(pf & 0xFFFF)
	facing = (pf >> 16) & 0xFFF
	layer = KFCard.num(f, "b2644")
	hp = KFCard.num(f, "hp")
	hp_max = KFCard.num(f, "hp_max")
	mp = KFCard.num(f, "mp")
	gold = KFCard.num(f, "gold")
	poison = KFCard.num(f, "poison")
	strong_hits = KFCard.num(f, "strong")
	var spells := []
	for v in (f["spells"] as PackedByteArray):
		spells.append(int(v))
	character = {"exp": KFCard.num(f, "exp"), "exp_next": KFCard.num(f, "exp_next"),
		"level": KFCard.num(f, "level"), "hp_max": hp_max,
		"mp_max": KFCard.num(f, "mp_max"), "stat36": KFCard.num(f, "stat36"),
		"grow": KFCard.halves(f, "skills"), "wis": KFCard.num(f, "wis"),
		"spells": spells}
	var inv: PackedByteArray = f["inventory"]
	inventory = KFItems.new()
	inventory.a = inv.slice(0, KFItems.COUNT)
	inventory.b = inv.slice(KFItems.COUNT, 2 * KFItems.COUNT)
	worn = []
	for v in (f["worn"] as PackedByteArray):
		worn.append(int(v))
	var hand: PackedByteArray = f["in_hand"]
	spell_a = int(hand[0])
	spell_b = int(hand[1])
	item_b = int(hand[2])
	# sub_80028e9c (0x80028e9c); the player block's block_zero (game_main)
	vstate = 0
	vvel = 0
	pstate = 0
	bob = 0
	bob_phase = 0
	crouch = 0
	fwd_speed = 0
	stf_speed = 0
	magic_meter = 0
	var tm: Array = KFCard.halves(f, "timers")     # 0x801b255e..0x801b2578
	caps = {"run": 0, "mod": 0, "slow": int(tm[4]), "paralysis": int(tm[5])}
	curse = [int(tm[0]), int(tm[1])]
	dark = [int(tm[2]), int(tm[3])]
	light = [int(tm[9]), int(tm[10])]
	shielded = int(tm[7])
	bonus = [int(tm[6]), int(tm[8]), int(tm[13])]
	mp_hold = int(tm[12])
	practice = KFCard.halves(f, "b250a")
	guard = 0
	equip_weapon(KFCard.num(f, "weapon"))       # the meter 0, the pause, the stats
	rotation.y = float(facing) * TAU / 4096.0
	_to_godot()
	KFInfo.note("save: level %d at (%d, %d, %d), facing 0x%x; %d exp, %d gold" % [
		_level(), gx, gy, gz, facing, int(character["exp"]), gold])


# player_recalc_stats is the game's after anything that changes what it reads:
# a level, a strong blow, something put on or eaten, a curse. This gathers what
# it reads -- the character's stat 36 and five skills, the curse's level, the
# three bonus timers, the weapon and the worn things; the story byte
# 0x801ba9e9 is not in the port and reads 0 -- and keeps what it writes.
# @port helper -- what KFEquip.recalc reads, out of the player, and what it writes, back
func recalc_stats() -> void:
	_take_recalc(equip.recalc(_recalc_state()))


# @port helper -- what player_recalc_stats reads, out of the player
func _recalc_state() -> Dictionary:
	return {"stat36": int(character.get("stat36", 20)),
		"skills": character.get("grow", [0, 0, 0, 0, 10]), "curse": int(curse[0]),
		"b56a": int(bonus[0]), "b56e": int(bonus[1]), "b578": int(bonus[2]),
		"weapon": weapon_id, "worn": worn, "story": 0, "level": _level()}


# @port helper -- what player_recalc_stats writes, into the player
func _take_recalc(r: Dictionary) -> void:
	offense = r["offense"]
	defence = r["defense"]
	working = r["working"]
	stat = int(r["stat"])
	resist = int(r["resist"])


# equip_weapon (0x8002bdc0), from the equipment screen: the weapon in the
# slot, its meter emptied and the swing's pause 0xa, its clock -1, and the
# stats again. The model it installs held.gd finds by the id.
# @orig game:0x8002bdc0 equip_weapon  status:partial -- the slot, the meter, the pause, the clock, the swords' spells story flags 39 and 45 unlock, and the stats; not the sound it plays
func equip_weapon(id: int) -> void:
	weapon_id = id
	wstate["pause"] = 0xA
	wstate["meter"] = 0
	wstate["strength"] = 0
	wstate["clock"] = -1
	weapon_meter = 0
	guard = 0                         # 0x8002bf74
	# 0x8002be9c: with story flag 39 the swords' spells of the first group,
	# with flag 45 the second's, unlocked (levels 6's and 8's lessons)
	var sp: Array = character.get("spells", [])
	if sp.size() >= 0x4D and KFTalk.flags.size() > 45:
		if int(KFTalk.flags[39]) != 0:
			for k in [0x38, 0x3A, 0x3C, 0x3E, 0x40, 0x4C]:
				sp[k] = 1
		if int(KFTalk.flags[45]) != 0:
			for k in [0x36, 0x37, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B]:
				sp[k] = 1
	recalc_stats()
	KFInfo.note("player: weapon %d in hand" % id)


# equip_armour (0x8002bb84): a thing worn in one of the seven slots, and the
# stats again.
# @orig game:0x8002bb84 equip_armour  status:partial -- the slot and the stats; not the record pointers it keeps beside them (0x801b25b8..)
func equip_armour(id: int, slot: int) -> void:
	if slot >= 0 and slot < WORN_OF_SLOT.size():
		worn[int(WORN_OF_SLOT[slot])] = id
	recalc_stats()
	KFInfo.note("player: %d worn in slot %d, defence %s" % [id, slot, str(defence)])


# The level out/godot was built for: tools/level3d.py names the project
# "King's Field II - level N". This returned 0 whatever the build, so on any
# other level the port read level 0's collision, doors and sky.
# @port engine -- the level this world is of (KFGame.current_level)
func _level() -> int:
	return KFGame.current_level()


# @port engine -- the game's position into the node's
func _to_godot() -> void:
	position = Vector3(float(gx) / UNIT, float(-gy) / UNIT, float(-gz) / UNIT)


# @port check -- the readout's lines, for the info window (info.gd) or the screen
func _refresh() -> void:
	var hud := get_node_or_null("../UI/Hud")
	if KFPad.binding.is_empty():
		KFPad.apply()
	var cx := int(floor(float(gx) / CELL))
	var cz := int(floor(float(gz) / CELL))
	var note := "FLY" if flying else "WALK"
	if not have_coll:
		note += "  (no collision data)"
	var above := "-"
	if last_surface != KFCollision.NO_SURFACE:
		above = str(last_surface - gy)
	var text := ("%s   cell (%d, %d)   height %d\n" +
		"state %d   vy %d   speed %d/%d   %s above the surface\n" +
		"F1 walk/fly   F2 darkening   G collision   Esc mouse   PgUp/PgDn fly up/down\n" +
		"forward %s   strafe %s/%s   turn %s/%s   attack %s   use %s   menu %s   pause %s\n") % [
		note, cx, cz, -gy, vstate, vvel, fwd_speed, stf_speed, above,
		KFPad.slot_key(KFPad.FORWARD), KFPad.slot_key(KFPad.ALT_A),
		KFPad.slot_key(KFPad.ALT_C), KFPad.slot_key(KFPad.LEFT_SLOT),
		KFPad.slot_key(KFPad.RIGHT_SLOT), KFPad.slot_key(KFPad.ATTACK),
		KFPad.slot_key(KFPad.USE), KFPad.slot_key(KFPad.MENU_SLOT),
		KFPad.slot_key(KFPad.PAUSE)]
	if hud:
		hud.text = text
	KFInfo.status = text + ("position %d %d %d   facing %03x   pitch %03x\n" +
		"HP %d/%d   MP %d   gold %d   weapon meter %d   magic meter %d   poison %d") % [
		gx, gy, gz, facing, pitch, hp, hp_max, mp, gold, weapon_meter,
		magic_meter, poison]


# @port engine -- the mouse turns the facing and the pitch; F1, F11, G, Esc and Tab are the port's keys
func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		# The mouse moves the game's own facing rather than the node, so that
		# looking about and the turn buttons do not fight over the rotation.
		facing = int(facing - e.relative.x * 2.0) & 0xFFF
		rotation.y = float(facing) * TAU / 4096.0
		# The mouse moves the game's own pitch, held to the same limits.
		var sp := _signed(pitch) + int(e.relative.y * 2.0)
		pitch = clampi(sp, -PITCH_LIMIT, PITCH_LIMIT) & 0xFFF
		_aim()
	elif e is InputEventKey and e.pressed and not e.echo:
		match e.keycode:
			KEY_F1:
				flying = not flying
				vstate = 0
				vvel = 0
				_refresh()
			KEY_F11:
				_learn_all()
			KEY_G:
				var v := get_node_or_null("../CollisionView")
				if v:
					v.visible = not v.visible
			KEY_ESCAPE:
				Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			KEY_TAB:
				Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


# F11, the port's own: every spell the game can give learned and the MP
# raised to the cap (0x3e7) and filled -- to try what the game gives late, on
# level 0. The spells then stand in the MAGIC and BUTTON lists of the
# equipment screen and in "use magic". "Every spell" is the 25 in
# skill_unlock's five lists, the only thing that sets the unlocked byte of one
# the menus list (equip_weapon and the hooks of levels 6 and 8 set the
# weapons' records, 0x36..0x4c, past the lists' end): the six with no name
# (3, 10, 14, 0x12, 0x16, 0x18) are in none, have no code, and the game never
# lists them.
# @port check -- F11: every spell the game gives, and MP to spare
func _learn_all() -> void:
	var sp: Array = character.get("spells", KFLevels.new_spells())
	while sp.size() < KFLevels.SPELLS:
		sp.append(0)
	KFLevels.load_from()
	for lst in KFLevels.skills.get("unlock", []):
		for k in lst:
			if int(k) != 0xFF and int(k) < sp.size():
				sp[int(k)] = 1
	character["spells"] = sp
	character["mp_max"] = KFLevels.STAT_CAP
	mp = KFLevels.STAT_CAP
	KFInfo.note("player: F11 -- every spell, MP %d of %d" % [mp, KFLevels.STAT_CAP])


# @orig game:0x80019614 frame_limit  status:transcribed -- the 15 frames a second _tick and _look run at; the pad's poll, flying and the attack latch are the port's
func _process(dt: float) -> void:
	# player_controller reads the pad once a frame and keeps this frame's word
	# and last frame's. Here that happens once a *rendered* frame rather than
	# once a game tick, which only matters to the edge detection.
	KFPad.poll()
	_screen()
	# player_turn reads the attack button's edge once a game frame; the pad is
	# read once a rendered frame here, so the edge is kept until a tick takes it.
	if KFGame.modal:                  # object_give's own frames: nothing moves
		_to_godot()
		return
	if KFPad.hit(KFPad.ATTACK):
		attack_latch = true
	var three := _combo_buttons()
	if (KFPad.now & (three[0] | three[1] | three[2])) != 0 \
			and (KFPad.prev & (three[0] | three[1] | three[2])) == 0:
		combo_latch = KFPad.now
	var dir := Vector3.ZERO
	if KFPad.held(KFPad.FORWARD): dir -= transform.basis.z
	if KFPad.held(KFPad.BACK): dir += transform.basis.z
	if KFPad.held(KFPad.ALT_A): dir -= transform.basis.x
	if KFPad.held(KFPad.ALT_C): dir += transform.basis.x

	# player_look runs every frame the controller does; in flight too, so the
	# view can be tilted with the game's own buttons either way.
	look_acc = minf(look_acc + dt, 0.25)
	while look_acc >= 1.0 / TICK_HZ:
		look_acc -= 1.0 / TICK_HZ
		if pstate != 0x12:                # the stun's arm calls no player_look
			_look()

	if flying:
		if Input.is_key_pressed(KEY_PAGEDOWN): dir -= Vector3.UP
		if Input.is_key_pressed(KEY_PAGEUP): dir += Vector3.UP
		var fast := 3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0
		var d := dir.normalized() * FLY * fast * dt
		gx += int(d.x)
		gy -= int(d.y)
		gz -= int(d.z)
		acc = 0.0
	elif have_coll:
		# The model is per frame, not per second, so it runs on its own clock and
		# the renderer's frame rate does not change how anything moves.
		acc = minf(acc + dt, 0.25)
		while acc >= 1.0 / TICK_HZ:
			acc -= 1.0 / TICK_HZ
			_tick(dir)
	_to_godot()
	_refresh()


# 0x8002f9bc: accelerate by max/4 while held, decay when not, clamping at zero by
# sign. The forward ramp decays by max/8 (sra 3 at 0x8002fad4) and the strafe by
# max/4 (sra 2 at 0x8002fc38) -- two different rates, and a replay caught each of
# them before either was read.
# @orig game:0x8002f9bc player_walk  status:verified -- tools/replay.py: 6186 of 6682 ground frames, and all 496 that differ are the wall slide
func _ramp(speed: int, pos: bool, neg: bool, cap: int, decay := 3) -> int:
	if pos:
		return mini(speed + (cap >> 2), cap)
	if neg:
		return maxi(speed - (cap >> 2), -cap)
	var step := cap >> decay
	if speed > 0:
		return maxi(speed - step, 0)
	if speed < 0:
		return mini(speed + step, 0)
	return 0


# @orig game:0x80030fcc player_controller  status:partial -- one frame: the state's arm (_frame), then the poison at its end (_poison)
func _tick(dir: Vector3) -> void:
	_render_flags()
	_frame(dir)
	_poison()
	_timers()


# The end of player_controller (0x80031e78), whatever the state: the poison
# counts down, and on every multiple of 30 -- 0x384 is one -- the screen
# flashes and one HP goes (hp_add, 0x8002a6a0; at 0 the player is thrown).
# So a spore that keeps striking, setting it back to 0x384 each frame, takes
# one HP a frame: 31 of 32 such frames in bp26, the other a roll resisted.
# @orig game:0x80031e78 player_controller+0xeac  status:verified -- a label inside player_controller; tools/effects.py against bp26
func _poison() -> void:
	if poison == 0:
		return
	if poison % 30 == 0:
		flash_colour = 0x960
		flash = 0x3C
		hp = maxi(hp - 1, 0)
		if hp == 0:
			_throw(null)
	poison -= 1


# --- casting -------------------------------------------------------------------

const CAST_ARMS := {
	0x04: [[0, -0x200, 0x7D0], 1, 1], 0x4C: [[0, 0, 0x258], 1, 1],
	0x01: [[-0x7D0, 0x640, 0x3E8], 5, 3], 0x38: ["y", 3, 1], 0x0D: ["y", 1, 1],
	0x40: [null, 3, 1], 0x42: [null, 1, 1], 0x09: [[0, -0x190, 0x190], 1, 1],
	0x11: [[0, -0x258, 0x258], 1, 1], 0x14: ["x", 5, 2], 0x47: ["x", 5, 2],
	0x02: [null, 3, 1], 0x0B: [null, 0xC, 1], 0x07: [[0, 0, 0], 2, 1],
	0x08: [null, 4, 2],
}
const ONE_SHOT := [0x00, 0x05, 0x06, 0x0C, 0x0F, 0x10, 0x13, 0x15, 0x1D, 0x36, 0x37,
	0x3A, 0x3C, 0x3E, 0x44, 0x45, 0x46, 0x48, 0x49, 0x4B]
const TIMED := {0x1A: ["b56a", 0x708, 2], 0x1C: ["b56e", 0x708, 2], 0x1B: ["b56c", 0xC8, 1]}
# The weapons' five marks' offsets (0x800818e4): x, y, z, 0
const WEAPON_MARKS := [[0, 0, 100, 0], [-1500, 0, 0, 0], [-3000, 0, -2000, 0],
	[1500, 0, 0, 0], [3000, 0, -2000, 0]]


# cast_spell, tools/magic.py's: nothing while an action is pending; the cost
# the record's +0x16, doubled by the groundal crown (head 0x26), halved by
# orladin's mail (body 0x2e), announce 9 when MP is short; nothing with weapon
# 0x1f; the eight healing and protecting spells' conditions (0x80011920) --
# light (0x1d) set there and done, 0x801b2572 = 0x384 -- each with one shot;
# then the magic meter must be full; the healing five practise; the meter
# and the swing's pause 0, MP spent, the spell pending a frame on, the eye
# offset -200, 200, 400 and what the spell's own arm of 0x80011940 makes of
# it and of the shots and their interval. `st` holds tools/magic.py's
# fields; `records` the spell_table records by index; `calls` collects
# ["announce", n], ["unlock", k], ["recalc"].
# @orig game:0x8002deec cast_spell  status:verified -- tools/magic.py: 1260 of 1260 casts as the game's own over 21 snapshots, fields and calls; the self-test this to it
static func cast_spell(st: Dictionary, spell: int, records: Dictionary, calls: Array) -> void:
	if int(st["pending"]) != 0xFF or spell == 0xFF:
		return
	var rec: PackedByteArray = records.get(spell, PackedByteArray())
	if rec.size() < 24:
		return
	var cost := int(rec[0x16]) | (int(rec[0x17]) << 8)
	if int(st["worn"][0]) == 0x26:
		cost <<= 1
	if int(st["worn"][1]) == 0x2E:
		cost >>= 1
	if int(st["mp"]) < cost:
		calls.append(["announce", 9])
		return
	if int(st["weapon"]) == 0x1F:
		return
	var one := false
	var k := spell - 0x17
	if k >= 0 and k < 8:
		match k:
			0:
				if int(st["hp"]) == int(st["hp_max"]):
					return
				one = true
			2:
				if int(st["poison"]) == 0:
					return
				one = true
			3, 4, 5:
				if int(st[["b56a", "b56c", "b56e"][k - 3]]) != 0:
					return
				one = true
			6:
				if int(st["light_t"]) != 0:
					return
				st["light_t"] = 0x384
				st["mp"] = (int(st["mp"]) - cost) & 0xFFFF
				skill_practice(st, rec, calls)
				return
			7:
				if not (int(st["hp"]) != int(st["hp_max"]) or int(st["curse_lv"]) != 0
						or int(st["dark_lv"]) != 0 or int(st["slow"]) != 0
						or int(st["paralysis"]) != 0):
					return
				one = true
	if one:
		st["count"] = 1
		st["interval"] = 1
	if int(st["meter"]) < 0x1388:
		return
	if spell == 0x17 or (spell >= 0x19 and spell <= 0x1C) or spell == 0x1E:
		skill_practice(st, rec, calls)
	st["off_x"] = -0xC8
	st["off_y"] = 0xC8
	st["off_z"] = 0x190
	st["meter"] = 0
	st["swing_pause"] = 0
	st["pending"] = spell
	st["delay"] = 1
	st["mp"] = (int(st["mp"]) - cost) & 0xFFFF
	if spell in ONE_SHOT:
		st["count"] = 1
		st["interval"] = 1
	elif CAST_ARMS.has(spell):
		var arm: Array = CAST_ARMS[spell]
		var offs = arm[0]
		if offs is String:
			if offs == "y":
				st["off_y"] = 0x1F4
			else:
				st["off_x"] = -0xC8
		elif offs != null:
			st["off_x"] = int(offs[0])
			st["off_y"] = int(offs[1])
			st["off_z"] = int(offs[2])
		st["count"] = int(arm[1])
		st["interval"] = int(arm[2])
	st["casting"] = spell


# skill_practice: for each skill k whose bit 1 << k the record's group (+5)
# has, its +3 into the count at 0x801b250a + 2k; at 400 the count is 0 again
# and the skill one higher -- 999 at most, announce 0x12 + k below that --
# then skill_unlock(k) and the stats.
# @orig game:0x8002a10c skill_practice  status:verified -- through cast_spell, the same 1260 casts
static func skill_practice(st: Dictionary, rec: PackedByteArray, calls: Array) -> void:
	var group := int(rec[5])
	for k in range(4, -1, -1):
		if group & (1 << k) == 0:
			continue
		st["practice"][k] = (int(st["practice"][k]) + int(rec[3])) & 0xFFFF
		if int(st["practice"][k]) < 0x190:
			continue
		st["practice"][k] = 0
		st["skills"][k] = (int(st["skills"][k]) + 1) & 0xFFFF
		if int(st["skills"][k]) >= 0x3E8:
			st["skills"][k] = 0x3E7
		else:
			calls.append(["announce", 0x12 + k])
		calls.append(["unlock", k])
		calls.append(["recalc"])


# player_action's arms for the healing and protecting spells: fire resist and
# missile shield two effects of their kind at the player and 0x801b256a /
# 0x801b256e to 0x708, refusal one and 0x801b256c to 0xc8, each then the
# stats; earth heal, antidote and blessings their effect alone.
# ["spawn", a0, a1, kind, point, the second stack word or null].
# @orig game:0x8002cd2c player_action+0xa20  status:verified -- the arms of 0x17, 0x19, 0x1a, 0x1b, 0x1c and 0x1e: tools/magic.py, 1260 of 1260 as the game's own; the attacking arms are not here
static func player_action(st: Dictionary, spell: int, calls: Array) -> void:
	if TIMED.has(spell):
		var t: Array = TIMED[spell]
		var n := int(t[2])
		for i in n:
			calls.append(["spawn", 0xA, 0x40, spell, 0x801B25F0, i if n == 2 else null])
		st[t[0]] = int(t[1])
		calls.append(["recalc"])
	elif spell in [0x17, 0x19, 0x1E]:
		calls.append(["spawn", 0xA, 0x40, spell, 0x801B25F0, null])


# player_turn's pending action, a frame (0x8002ff88): the delay down, and at 0
# player_action and a shot less -- nothing pending after the last, else the
# delay the interval again.
# @orig game:0x8002ff88 player_turn+0x16c  status:verified -- tools/magic.py, 1260 of 1260 frames as the game's own
static func pending_tick(st: Dictionary, calls: Array) -> void:
	if int(st["pending"]) == 0xFF:
		return
	st["delay"] = (int(st["delay"]) - 1) & 0xFF
	if int(st["delay"]) != 0:
		return
	calls.append(["action", int(st["pending"])])
	st["count"] = (int(st["count"]) - 1) & 0xFF
	if int(st["count"]) == 0:
		st["pending"] = 0xFF
	else:
		st["delay"] = int(st["interval"])


# The timers at player_controller's end (0x80031f0c): 0x801b256a, 256c and
# 256e down, the stats when one reaches 0; 0x801b2576 down holding MP at its
# most, announce 0x1b at its end; 0x801b2578 down, the stats and announce 0x1b
# at its end.
# @orig game:0x80031f0c player_controller+0xf40  status:verified -- tools/magic.py, 1260 of 1260 frames as the game's own
static func timers_tick(st: Dictionary, calls: Array) -> void:
	for name in ["b56a", "b56c", "b56e"]:
		if int(st[name]) != 0:
			st[name] = KFWeapon.s16(int(st[name]) - 1)
			if int(st[name]) == 0:
				calls.append(["recalc"])
	if int(st["b576"]) != 0:
		st["b576"] = KFWeapon.s16(int(st["b576"]) - 1)
		st["mp"] = int(st["mp_max"])
		if int(st["b576"]) == 0:
			calls.append(["announce", 0x1B])
	if int(st["b578"]) != 0:
		st["b578"] = KFWeapon.s16(int(st["b578"]) - 1)
		if int(st["b578"]) == 0:
			calls.append(["recalc"])
			calls.append(["announce", 0x1B])


# --- the attacking arms --------------------------------------------------------

const AIM_PLAIN := {
	0x00: [0x384, -1, []], 0x06: [0x1F4, -1, []], 0x37: [0x1F4, -1, []],
	0x40: [0x1B8, -1, []], 0x4C: [0x1C2, -1, []], 0x3C: [0x140, -1, []],
	0x3A: [0x226, -1, []], 0x3E: [0x2EE, -1, []], 0x4B: [0x2D0, -1, []],
	0x46: [0x1F4, -1, [0]], 0x15: [0x104, -1, []],
	0x38: [0x2BC, -1, ["view"]], 0x39: [0x2BC, -1, ["view"]], 0x0D: [0x2BC, -1, ["view"]],
	0x04: [0xFA, -1, ["view"]], 0x09: [0xFA, -1, ["view"]], 0x11: [0xFA, -1, ["view"]],
	0x10: [0xFA, -1, ["view"]], 0x05: [0xFA, -1, ["view"]], 0x42: [0x384, -1, ["view"]],
	0x44: [0x3E8, 0x7C, []], 0x45: [0x3E8, 0x7B, ["view"]],
}


# sub_8004d3c4: the awake creature (not +0xe 3) within `reach` -- twice it for
# flag 0x20000 -- whose bearing and pitch from `point` are nearest `yaw` and
# `pitch`: inside the two cones, or for flag 0x20000 a quarter of the distance
# and 0x200 off each instead; scored by the two differences and the distance
# over 128. `list` is the awake creatures in slot order, [slot, +0xe, +0x28,
# x, y, z, ...]; [its entry or null, the distance or -1].
# @orig game:0x8004d3c4 sub_8004d3c4  status:verified -- through spell_aim; tools/magic.py attack_check, 840 of 840 casts of the game's own player_action; the noise (a rand for each creature in the cones) through flame, tools/effects.py spell_hit_check
static func sight(c: KFCollision, list: Array, point: Array, yaw: int, pitch: int,
		reach: int, ycone: int, pcone: int, noise := 0, rnd: Callable = Callable()) -> Array:
	var best := 0x7530
	var chosen = null
	var dist := -1
	for e in list:
		if int(e[1]) == 3:
			continue
		var flags := int(e[2])
		var r := reach << 1 if flags & 0x20000 else reach
		var d := c.in_range(int(e[3]), int(e[4]), int(e[5]), int(point[0]), 0xFFFF,
			int(point[2]), r, 0, 0)
		if d == -1:
			continue
		var dx := _s32(int(e[3]) - int(point[0]))
		var dy := _s32(int(e[4]) - int(point[1]))
		var dz := _s32(int(e[5]) - int(point[2]))
		var ayaw := KFWeapon.s16(c.vec_angle(dx, dz))
		var ln := c.isqrt(_s32((dx >> 3) * (dx >> 3) + (dz >> 3) * (dz >> 3)) & 0xFFFFFFFF) << 3
		var apitch := (-c.vec_angle(dy, ln)) & 0xFFF
		var by := (ayaw - yaw) & 0xFFF
		if by >= 0x800:
			by = 0x1000 - by
		var bp := (apitch - pitch) & 0xFFF
		if bp >= 0x800:
			bp = 0x1000 - bp
		if flags & 0x20000 and noise >= 0:
			d >>= 2
			by = KFWeapon.s16(by - 0x200)
			bp = KFWeapon.s16(bp - 0x200)
		elif ycone < by or pcone < bp:
			continue
		var score := by + bp + (d >> 7)
		if noise > 0:
			score += _s32(int(rnd.call()) * noise) >> 15
		if score < best:
			best = score
			chosen = e
			dist = d
	return [chosen, dist]


# sub_8002c164: a spell's start -- the cast offset turned by the view's
# angles (the pitch negated) from the eye, 0x640 above the feet -- the
# creature in sight within 0x55f0 and 0x200 either way, woken by its
# behaviour 0x82 unless its +0x28 has 0x100, and the velocity, the view's
# direction times `speed`. [point, velocity, the creature's entry or null,
# its distance].
# @orig game:0x8002c164 sub_8002c164  status:verified -- tools/magic.py attack_check, 840 of 840 casts of the game's own; the self-test this to it
static func spell_aim(st: Dictionary, speed: int, w, c: KFCollision, calls: Array) -> Array:
	var view: Array = st["view"]
	var pos: Array = st["pos"]
	var v := KFWeapon.vec_rotate(c, KFWeapon.s16(-int(view[0])), int(view[1]), int(view[2]),
		[int(st["off_x"]), int(st["off_y"]), int(st["off_z"])])
	var point := [_s32(int(v[0]) + int(pos[0])), _s32(int(v[1]) - 0x640 + int(pos[1])),
		_s32(int(v[2]) + int(pos[2]))]
	var found := sight(c, w.sight_list(), pos, KFWeapon.s16(int(view[1])),
		KFWeapon.s16(int(view[0])), 0x55F0, 0x200, 0x200)
	var t = found[0]
	st["target"] = int(t[0]) if t != null else -1
	if t != null:
		var rec = w.kind_op(int(t[0]), 0x82)
		if rec != null and (int(t[2]) & 0x100) == 0:
			w.actor_switch(int(t[0]), rec)
			calls.append(["switch", int(t[0])])
	var d := c.direction_from_angles(int(view[0]), int(view[1]))
	var vel := []
	for i in 3:
		vel.append(KFWeapon.s16((int(d[i]) * KFWeapon.s16(speed)) >> 12))
	return [point, vel, t, int(found[1])]


# player_action's attacking arms (0x8002c364 on): each aims and spawns its
# effects -- ["spawn", a1, kind, point, [["vel", x, y, z], "view" or a
# number ...]] -- as tools/magic.py attack makes them. Meteor (8) leads its
# creature by its velocity and keeps it where the lead would collide;
# lightning (0x13) sends kind 0x71 with the distance / 600 - 8 (2 least, 10
# with no creature); fire storm (2) its creature's slot; the weapons' 0x48,
# 0x49 and 0x4a a mark and four more round it, from offsets at 0x800818e4.
# `w` answers the world: sight_list, kind_op, actor_switch, collide, spawn
# (the slot, or 0), rand.
# @orig game:0x8002c364 player_action+0x58  status:verified -- the attacking arms; tools/magic.py attack_check, 840 of 840 casts of the game's own, every spawn, the creature woken, the state left; the self-test this to it
static func attack_action(st: Dictionary, action: int, w, c: KFCollision, calls: Array) -> void:
	if AIM_PLAIN.has(action):
		var arm: Array = AIM_PLAIN[action]
		var r := spell_aim(st, int(arm[0]), w, c, calls)
		_spawn(w, calls, 0x42, action if int(arm[1]) < 0 else int(arm[1]), r[0],
			[["vel"] + (r[1] as Array)] + (arm[2] as Array))
		return
	match action:
		0x36:
			for i in 4:
				st["off_z"] = KFWeapon.s16(800 * (3 - i))
				var r := spell_aim(st, 0x1F4, w, c, calls)
				_spawn(w, calls, 0x42, 0x36, r[0], [["vel"] + (r[1] as Array), 3 - i])
		0x0F:
			var r := spell_aim(st, 0x12C, w, c, calls)
			var pt: Array = r[0]
			pt[1] = _s32(int(pt[1]) + 0x540)
			var vel: Array = r[1]
			vel[1] = 0
			_spawn(w, calls, 0x42, 0x0F, pt, [["vel"] + vel, "view", 0])
			_spawn(w, calls, 0x42, 0x0F, pt, [["vel"] + vel, "view", 1])
		0x07:
			_spawn(w, calls, 0x43, 0x07, st["pos"], [0, 0x1000, 0x100, 0x1000, 1])
		0x08, 0x0C:
			var r := spell_aim(st, 0x1B58, w, c, calls)
			var pt: Array = r[0]
			var vel: Array = r[1]
			var t = r[2]
			if t == null:
				pt = [_s32(int(pt[0]) + int(vel[0])), int(st["pos"][1]), _s32(int(pt[2]) + int(vel[2]))]
			elif action == 0x0C:
				pt = [int(t[3]), int(t[4]), int(t[5])]
			else:
				pt = []
				for i in 3:
					var v := _s32(int(t[6 + i]) << 14)
					var q := (v * 0x64D319FF) >> 32
					pt.append(_s32((q >> 8) - (v >> 31) + int(t[3 + i])))
				calls.append(["collide", int(pt[0]), int(pt[1]), int(pt[2])])
				if w.collide(int(pt[0]), int(pt[1]), int(pt[2])):
					pt = [int(t[3]), int(t[4]), int(t[5])]
			_spawn(w, calls, 0x43 if action == 0x08 else 0x42, 0x5F if action == 0x08 else 0x0C,
				pt, [0])
		0x0B:
			var r := spell_aim(st, 0x104, w, c, calls)
			var vel: Array = r[1]
			vel[0] = KFWeapon.s16(int(vel[0]) - 0x10 + (int(w.rand()) >> 10))
			vel[1] = KFWeapon.s16(int(vel[1]) - 0x10 + (int(w.rand()) >> 10))
			_spawn(w, calls, 0x42, 0x0B, r[0], [["vel"] + vel, _s32(0xE - int(st["count"]))])
		0x13:
			var r := spell_aim(st, 0x258, w, c, calls)
			var d := int(r[3])
			if d != -1:
				d = d / 600 - 8
				if d < 2:
					d = 2
			else:
				d = 0xA
			var vel: Array = r[1]
			vel[1] = 0
			_spawn(w, calls, 0x42, 0x71, r[0], [["vel"] + vel, d])
		0x02:
			var r := spell_aim(st, 0x1F4, w, c, calls)
			var t = r[2]
			_spawn(w, calls, 0x42, 0x02, r[0], [["vel"] + (r[1] as Array),
				int(t[0]) if t != null else 0xFF, int(st["count"])])
		0x01:
			var r := spell_aim(st, 0x23A, w, c, calls)
			_spawn(w, calls, 0x42, 0x01, r[0], [["vel"] + (r[1] as Array), "view"])
			st["off_x"] = KFWeapon.s16(int(st["off_x"]) + 0x3E8)
		0x14, 0x47:
			var view: Array = st["view"]
			var yaw := int(view[1])
			st["view"] = [int(view[0]), (yaw - 2 * int(st["off_x"])) & 0xFFFF, int(view[2])]
			var r := spell_aim(st, 0xAA, w, c, calls)
			st["off_x"] = KFWeapon.s16(int(st["off_x"]) + 0x64)
			st["view"] = [int(view[0]), yaw, int(view[2])]
			_spawn(w, calls, 0x42, action, r[0], [["vel"] + (r[1] as Array), "view",
				0x258, 0x3C, 0x80, 0x8C, 0xA0])
		0x48, 0x49, 0x4A:
			var kind := 0x78 if action == 0x48 else 0x7A
			var child := 0x5C if action == 0x48 else 0x5D
			var offs: Array = st["offsets"]
			_set_off(st, offs[0])
			var r := spell_aim(st, 0x258, w, c, calls)
			var got := _spawn(w, calls, 0x42, kind, r[0], [["vel"] + (r[1] as Array), "view"])
			if got != 0:
				for i in range(1, 5):
					_set_off(st, offs[i])
					var r2 := spell_aim(st, 0x258, w, c, calls)
					_spawn(w, calls, 0x42, child, r2[0], [["vel"] + (r2[1] as Array), got - 1])


# @port helper -- an arm's spawn: recorded, and handed to the world; the slot's number + 1, or 0
static func _spawn(w, calls: Array, a1: int, kind: int, point: Array, args: Array) -> int:
	calls.append(["spawn", a1, kind, point.duplicate(), args.duplicate(true)])
	return int(w.spawn(a1, kind, point, args))


# @port helper -- the cast offset off one of the weapons' marks at 0x800818e4
static func _set_off(st: Dictionary, o: Array) -> void:
	st["off_x"] = int(o[0])
	st["off_y"] = int(o[1])
	st["off_z"] = int(o[2])
	st["off_w"] = int(o[3])


# The world the attacking arms ask, when the player casts: the creatures from
# actors.gd, their behaviour 0x82 and the switch to it, the effects' spawn.
# @port helper -- the awake creatures for sight, in slot order
func sight_list() -> Array:
	var out := []
	var an := get_node_or_null("../Actors")
	if an == null or an.get("actors") == null:
		return out
	var list: Array = an.get("actors")
	for k in list.size():
		var a = list[k]
		if a == null or int(a.get("st", 0)) != 1:
			continue
		out.append([k, int(a.get("op", 0)), int(a.get("eflags", 0)), int(a["px"]), int(a["py"]),
			int(a["pz"]), int(a.get("vx", 0)), int(a.get("vy", 0)), int(a.get("vz", 0))])
	return out


# @port helper -- kind_behaviour_with_op for a creature, by its slot
func kind_op(slot: int, op: int):
	var an := get_node_or_null("../Actors")
	if an and an.has_method("behaviour_of"):
		return an.call("behaviour_of", slot, op)
	return null


# @port helper -- actor_switch on a creature, by its slot
func actor_switch(slot: int, rec) -> void:
	var an := get_node_or_null("../Actors")
	if an and an.get("actors") != null and an.get("actors")[slot] != null:
		KFCreatureAI.switch_to(an.get("actors")[slot], rec)


# collide_wrapper_actor for meteor's lead (radius and height 0xa): the
# tiles there, through effects.gd's.
# @port helper -- meteor's lead test, handed to effects.gd collide_wrapper
func collide(x: int, y: int, z: int) -> bool:
	var fx := get_node_or_null("../Effects")
	return fx != null and int(fx.call("collide_wrapper", x, y, z, 0xA, 0xA)) != 0


# @port helper -- an arm's effect into effects.gd; its slot's number + 1, or 0
func spawn(a1: int, kind: int, point: Array, args: Array) -> int:
	var fx := get_node_or_null("../Effects")
	if fx == null:
		return 0
	var pt := PackedByteArray()
	pt.resize(16)
	for i in 3:
		pt.encode_s32(4 * i, int(point[i]))
	var out := []
	for a in args:
		if a is Array:
			var b := PackedByteArray()
			b.resize(8)
			for i in 3:
				b.encode_s16(2 * i, int(a[1 + i]))
			out.append(b)
		elif a is String:
			var b := PackedByteArray()
			b.resize(8)
			b.encode_s16(0, view_pitch_now())
			b.encode_s16(2, facing)
			b.encode_s16(4, 0)
			out.append(b)
		else:
			out.append(int(a))
	var s := int(fx.call("spawn", 0xA, a1, kind, pt, out))
	return s / 0x4C + 1 if s >= 0 else 0


# @port helper -- the BIOS's rand, for haze
func rand() -> int:
	return randi() & 0x7FFF


# @port helper -- the player's casting fields as tools/magic.py's state
func _magic_state() -> Dictionary:
	return {"pending": pending, "count": shots, "interval": shot_gap,
		"delay": shot_delay, "mp": mp, "mp_max": int(character.get("mp_max", 30)),
		"hp": hp, "hp_max": hp_max, "weapon": weapon_id, "poison": poison,
		"curse_lv": curse[0], "dark_lv": dark[0], "slow": caps["slow"],
		"paralysis": caps["paralysis"], "b56a": bonus[0], "b56c": shielded,
		"b56e": bonus[1], "b576": mp_hold, "b578": bonus[2], "light_t": light[1],
		"meter": magic_meter, "swing_pause": int(wstate["pause"]),
		"off_x": cast_off[0], "off_y": cast_off[1], "off_z": cast_off[2],
		"casting": casting, "worn": worn, "practice": practice,
		"skills": character.get("grow", [0, 0, 0, 0, 10])}


# @port helper -- the state back into the player, and what it asked for done
func _magic_put(st: Dictionary, calls: Array) -> void:
	pending = int(st["pending"])
	shots = int(st["count"])
	shot_gap = int(st["interval"])
	shot_delay = int(st["delay"])
	mp = int(st["mp"])
	bonus = [int(st["b56a"]), int(st["b56e"]), int(st["b578"])]
	shielded = int(st["b56c"])
	mp_hold = int(st["b576"])
	light[1] = int(st["light_t"])
	magic_meter = int(st["meter"])
	wstate["pause"] = int(st["swing_pause"])
	cast_off = [int(st["off_x"]), int(st["off_y"]), int(st["off_z"])]
	casting = int(st["casting"])
	for c in calls:
		match str(c[0]):
			"announce":
				KFMessages.announce(int(c[1]))
			"unlock":
				for b in KFLevels.skill_unlock(character, int(c[1]), KFTalk.flags):
					KFMessages.announce(int(b))
			"recalc":
				recalc_stats()
			"spawn":
				var fx := get_node_or_null("../Effects")
				if fx and fx.has_method("spawn"):
					var pt := PackedByteArray()
					pt.resize(16)
					pt.encode_s32(0, gx)
					pt.encode_s32(4, gy)
					pt.encode_s32(8, gz)
					fx.call("spawn", int(c[1]), int(c[2]), int(c[3]), pt,
						[null, c[5]])
			"action":
				var more := []
				player_action(st, int(c[1]), more)
				_magic_put(st, more)
				_attack(int(c[1]))


# player_action's attacking arms on the player: the view, the place, the cast
# offset and the shots as the arms read them, and the offset as they leave it.
# @port helper -- attack_action on the player's fields, the player as its world
func _attack(action: int) -> void:
	if not (AIM_PLAIN.has(action) or action in [0x36, 0x0F, 0x07, 0x08, 0x0C, 0x0B,
			0x13, 0x02, 0x01, 0x14, 0x47, 0x48, 0x49, 0x4A]):
		return
	var st := {"view": [view_pitch_now() & 0xFFFF, facing & 0xFFFF, 0], "pos": [gx, gy, gz],
		"off_x": cast_off[0], "off_y": cast_off[1], "off_z": cast_off[2], "off_w": 0,
		"count": shots, "offsets": WEAPON_MARKS, "target": -1}
	var calls := []
	attack_action(st, action, self, coll, calls)
	cast_off = [int(st["off_x"]), int(st["off_y"]), int(st["off_z"])]


# spell_begin (spell, commit, n): with the MP for its cost, the spell is the
# one cast; on the commit -- a weapon's first shot -- the magic meter and its
# pause go to 0 and the MP pays; the eye's offset for the spell (0x42's turned
# by n << 9, 0x47's 300 n - 300 across, every other 200, 200, 400) and
# player_action at once.
# @orig game:0x8002d130 spell_begin  status:verified -- tools/weapon.py spell_begin, 200 of 200 as the game's own, player_action stood in for (magic_check); not the sound 0x36's commit plays
func spell_begin(spell: int, commit: bool, n: int) -> void:
	var rec: PackedByteArray = _spell_records().get(spell, PackedByteArray())
	if rec.size() < 24:
		return
	var cost := int(rec[0x16]) | (int(rec[0x17]) << 8)
	if mp < cost:
		return
	casting = spell
	if commit:
		magic_meter = 0
		magic_pause = 0
		mp = (mp - cost) & 0xFFFF
	if spell == 0x42:
		var a := (n << 9) & 0xFFFFFFFF
		cast_off = [coll._s16(coll.game_cos(a) >> 3), coll._s16(coll.game_sin(a) >> 3), 0x258]
	elif spell == 0x47:
		cast_off = [0, coll._s16(300 * n - 300), 0x190]
	else:
		cast_off = [0xC8, 0xC8, 0x190]
	KFInfo.note("player: the weapon's spell 0x%x%s" % [spell, ", the MP paid" if commit else ""])
	_attack(spell)


# @port helper -- the three buttons player_turn writes into the combination's table (gp+0x1b8): bind_use, bind_attack, bind_action
func _combo_buttons() -> Array:
	if KFPad.binding.is_empty():
		KFPad.apply()
	return [KFPad.binding[KFPad.USE], KFPad.binding[KFPad.ATTACK], KFPad.binding[KFPad.ACTION]]


# @port helper -- spell_table's records, as the effects hold them (fxrecords.json)
func _spell_records() -> Dictionary:
	var fx := get_node_or_null("../Effects")
	if fx and fx.get("records") != null:
		return fx.get("records")
	return {}


# player_turn's buttons (0x8002fe1c): the action button's edge casts magic A
# unless the weapon's own magic is firing (0x801b25b2, its shots left) or a
# combination is under way (0x801b25aa); the square button's (bind_map) the
# button's spell, or uses its thing (button_calls). Then the pending action.
# @orig game:0x8002fe1c player_turn  status:partial -- the casting buttons, the button's thing and the pending action
func _cast_buttons() -> void:
	var st := _magic_state()
	var calls := []
	var recs := _spell_records()
	if KFPad.hit(KFPad.ACTION) and int(wstate.get("shots", 0)) == 0 and int(combo["time"]) == 0:
		cast_spell(st, spell_a, recs, calls)
	if KFPad.hit(KFPad.MAP):
		var held := int(inventory.a[item_b]) if item_b >= 0 and item_b < inventory.a.size() else 0
		var todo := button_calls(spell_b, item_b, held)
		var thing := false
		for c in todo:
			if str(c[0]) == "cast":
				cast_spell(st, int(c[1]), recs, calls)
			else:
				thing = true
		if thing:
			# the thing acts on the player itself: what the casts left, first
			_magic_put(st, calls)
			calls = []
			for c in todo:
				match str(c[0]):
					"announce":
						KFMessages.announce(int(c[1]))
					"consume":
						item_consume(int(c[1]))
					"use":
						var lt := get_node_or_null("../Loot")
						if lt:
							lt.use_item(int(c[1]))
			st = _magic_state()
	pending_tick(st, calls)
	_magic_put(st, calls)


# The square button's edge (0x8002fef8): the button's spell (0x801b25ac)
# cast, and its thing (0x801b25ad) -- held, eaten first by item_consume when
# eats() says so and then used (use_item from player_pos and player_pitch);
# held none, "Nothing happens" (0xa). The calls in order: ["cast", spell],
# ["announce", 0xa], ["consume", thing], ["use", thing].
# @orig game:0x8002febc player_turn+0xa0  status:verified -- 1260 of 1260 runs of the game's own stretch over the snapshots, the calls in order (tools/magic.py button_check)
static func button_calls(spell: int, thing: int, held: int) -> Array:
	var out := []
	if spell != 0xFF:
		out.append(["cast", spell])
	if thing == 0xFF:
		return out
	if held == 0:
		out.append(["announce", 0xA])
		return out
	if eats(thing):
		out.append(["consume", thing])
	out.append(["use", thing])
	return out


# item_eaten_first (0x8002fddc): whether item_consume eats the thing before
# use_item has it -- the herbs and stones 0x68..0x6d, the two fruits 0x6f and
# 0x70 (whose arms are use_item's) and the potions 0x77 and 0x78, seventeen
# arms from 0x80011a78; verdite and the crystals are use_item's alone.
# @orig game:0x8002fddc item_eaten_first  status:verified -- through player_turn's stretch, 1260 of 1260 runs of the game's own (tools/magic.py)
static func eats(thing: int) -> bool:
	return (thing >= 0x68 and thing <= 0x6D) or thing == 0x6F or thing == 0x70 \
		or thing == 0x77 or thing == 0x78


# item_consume (0x8001b254): one of a thing out of inventory_a and its good --
# the earth herb HP +50, the antidote the poison and HP +15, the herbal liquid
# HP to the full, the dragon crystal HP and MP to the full, the blood stone
# the paralysis off and the slowing held to 0x40, the moon stone MP +40, the
# blue potion HP +100, the gold potion HP +200 and MP +100, each held to its
# most; the fruits only counted down (use_item has their arms), a potion's
# crystal flask back. Verdite, the crystals and a thing not held are left.
# True when it ate.
# @orig game:0x8001b254 item_consume  status:transcribed -- not ui_sound(9)
func item_consume(id: int) -> bool:
	if id == 0x6E or (id >= 0x71 and id <= 0x76) or int(inventory.a[id]) == 0:
		return false
	match id:
		0x68:
			hp += 0x32
		0x69:
			poison = 0
			hp += 0xF
		0x6A:
			hp = hp_max
		0x6B:
			hp = hp_max
			mp = int(character.get("mp_max", mp))
		0x6C:                                       # the blood stone (0x8001b350)
			if int(caps["paralysis"]) > 0:
				caps["paralysis"] = 0
			if int(caps["slow"]) >= 0x41:
				caps["slow"] = 0x40
		0x6D:
			mp += 0x28
			mp = mini(mp, int(character.get("mp_max", mp)))
		0x77:
			hp += 0x64
		0x78:
			hp += 0xC8
			mp = mini(mp + 0x64, int(character.get("mp_max", mp + 0x64)))
	hp = mini(hp, hp_max)
	inventory.a[id] = int(inventory.a[id]) - 1
	if id == 0x77 or id == 0x78:
		inventory.a[0x76] = int(inventory.a[0x76]) + 1       # the crystal flask back
	return true


# pause_menu's end (0x8001a978): what "use magic" handed back, with 0x1000
# set, cast as the menu goes -- after the screen behind it is put back and
# before sub_800305d8's clear_movement_state. It waits as the pending action
# for player_turn, as a button's cast does.
# @orig game:0x8001a978 pause_menu+0x204  status:transcribed
func cast_from_menu(spell: int) -> void:
	var st := _magic_state()
	var calls := []
	cast_spell(st, spell, _spell_records(), calls)
	_magic_put(st, calls)


# @port helper -- timers_tick on the player, at the controller's end
func _timers() -> void:
	var st := _magic_state()
	var calls := []
	timers_tick(st, calls)
	_magic_put(st, calls)


# An effect's strike (effect_strike 0x80053850 -> effect_hurt_player
# 0x8002b114 -> player_take_hit 0x8002ab18): the eight attacks and the effect
# of its spell_table record, the scale its distance gave and its percentage.
# @port helper -- an effect's strike into take_hit, from its point
func take_effect(attacks: Array, effect: int, scale: int, pct: int, point: Vector3i) -> void:
	_hit(attacks, effect, scale, pct, point)


# player_take_hit, tools/status.py's: nothing at all while 0x801b25b4 is set
# or 0x801b256c runs; else the five durations as what is worn leaves them,
# the attacks less what it turns away -- rnd drawn just where the game draws
# rand -- the effect's arm, and the damage of the eight, which apply_damage
# is handed. `st` holds what it reads and writes: "worn", "guard",
# "shielded", "resist", "mp", "mp_max", "poison", "curse_lv", "curse_t",
# "dark_t", "light_t", "paralysis", "slow", "defence", "stat", "k" and
# "recalc", player_recalc_stats's state, which the curse runs with the curse
# on before the damage; it leaves the recalculation in "recalced". The damage,
# or -1 when nothing gets through.
# @orig game:0x8002ab18 player_take_hit  status:verified -- tools/status.py: 840 of 840 hits as the game's own takes them over 21 snapshots, status, damage and rand draws; the self-test this to it
static func take_hit(st: Dictionary, attacks: Array, effect: int, scale: int, pct: int,
		rnd: Callable, eq: KFEquip) -> int:
	if int(st["guard"]) != 0 or int(st["shielded"]) != 0:
		return -1
	var d := hit_durations(st["worn"])
	var a := hit_shield(st["worn"], attacks, rnd)
	match effect & 0xF:
		1:
			st["curse_t"] = int(d[3])
			st["curse_lv"] = 1
			var rs: Dictionary = (st["recalc"] as Dictionary).duplicate()
			rs["curse"] = 1
			var r := eq.recalc(rs)
			st["defence"] = r["defense"]
			st["stat"] = int(r["stat"])
			st["recalced"] = r
		2:
			st["dark_t"] = int(d[2])
			st["light_t"] = 0
		3:
			if int(st["resist"]) < (100 * int(rnd.call())) >> 15:
				st["poison"] = int(d[1])
		4:
			st["paralysis"] = int(d[0])
		5:
			st["slow"] = int(d[4])
		6:
			var cut := int(st["mp_max"]) >> 4
			st["mp"] = int(st["mp"]) - cut if cut < int(st["mp"]) else 0
		7:
			st["poison"] = 0
	var base := 0
	for i in 8:
		base += KFDamage.of_type(int(a[i]), int(st["defence"][i]), int(st["stat"]), int(st["k"]))
	var s1 := _s32(scale * base + 0x8000) >> 16
	return _s32(pct * s1) / 10


# The five durations -- paralysis, poison, darkness, curse, slowing -- from
# 0xc8, 0x384, 0xa8c, 0x546 and 0x1c2 as what is worn cuts them: silver arms
# (0x41), silver boots (0x4a), groundal boots (0x4c), the silver and gold
# rings (0x53, 0x56), the globe amulet (0x58), the luster wing (0x5b),
# ichrius' helm (0x29) and boots (0x4f). `worn` is 0x801b25d4..0x801b25da.
# @orig game:0x8002abb4 player_take_hit+0x9c  status:verified -- through take_hit
static func hit_durations(worn: Array) -> Array:
	var para := 0xC8
	var poi := 0x384
	var dk := 0xA8C
	var cu := 0x546
	var sl := 0x1C2
	var head := int(worn[0])
	var arms := int(worn[3])
	var feet := int(worn[4])
	var items := [int(worn[5]), int(worn[6])]
	if arms == 0x41:
		para = 0x96
	if feet == 0x4A:
		poi = 0x2A3
	if feet == 0x4C:
		para >>= 1
		dk = 0x546
		cu = 0x2A3
		sl = 0xE1
	if 0x53 in items:
		poi >>= 2
	if 0x56 in items:
		para >>= 2
	if 0x58 in items:
		dk >>= 1
		cu >>= 1
		sl >>= 1
	if 0x5B in items:
		dk >>= 2
		cu >>= 2
		sl >>= 2
	if head == 0x29:
		dk >>= 2
		cu >>= 2
		sl >>= 2
	if feet == 0x4F:
		para >>= 2
		poi >>= 2
	return [para, poi, dk, cu, sl]


# The attacks less what is worn turns away: the fire mail (0x2d) the fire;
# slash, blow and stab one time in four for the dragon head (0x27), groundal
# mail (0x30) and ichrius' armor (0x31), always for the five promeus pieces;
# the five magic one in four for the groundal and ichrius' shields (0x3a,
# 0x3c), one in two for the ebony bracelet (0x55). rand is drawn only for a
# piece worn.
# @orig game:0x8002ad08 player_take_hit+0x1f0  status:verified -- through take_hit
static func hit_shield(worn: Array, attacks: Array, rnd: Callable) -> Array:
	var a: Array = []
	for i in 8:
		a.append(int(attacks[i]) if i < attacks.size() else 0)
	var head := int(worn[0])
	var body := int(worn[1])
	var shld := int(worn[2])
	var items := [int(worn[5]), int(worn[6])]
	if body == 0x2D:
		a[4] = 0
	if head == 0x27 and int(rnd.call()) < 0x2000:
		a[0] = 0; a[1] = 0; a[2] = 0
	if head == 0x28 and body == 0x2F and shld == 0x3B and int(worn[3]) == 0x45 \
			and int(worn[4]) == 0x4E:
		a[0] = 0; a[1] = 0; a[2] = 0
	if body == 0x30 and int(rnd.call()) < 0x2000:
		a[0] = 0; a[1] = 0; a[2] = 0
	if body == 0x31 and int(rnd.call()) < 0x2000:
		a[0] = 0; a[1] = 0; a[2] = 0
	if shld == 0x3A and int(rnd.call()) < 0x2000:
		for i in range(3, 8): a[i] = 0
	if shld == 0x3C and int(rnd.call()) < 0x2000:
		for i in range(3, 8): a[i] = 0
	if 0x55 in items and int(rnd.call()) < 0x4000:
		for i in range(3, 8): a[i] = 0
	return a


# @port helper -- a hit: the player's fields into take_hit and back, then apply_damage
func _hit(attacks: Array, effect: int, scale: int, pct: int, at: Vector3i) -> void:
	var st := {"worn": worn, "guard": guard, "shielded": shielded, "resist": resist,
		"mp": mp, "mp_max": int(character.get("mp_max", 30)), "poison": poison,
		"curse_lv": curse[0], "curse_t": curse[1], "dark_t": dark[1],
		"light_t": light[1], "paralysis": caps["paralysis"], "slow": caps["slow"],
		"defence": defence, "stat": stat, "k": damage_k, "recalc": _recalc_state()}
	var dmg := take_hit(st, attacks, effect, scale, pct, _rand, equip)
	if dmg < 0:
		return
	mp = int(st["mp"])
	poison = int(st["poison"])
	curse = [int(st["curse_lv"]), int(st["curse_t"])]
	dark[1] = int(st["dark_t"])
	light[1] = int(st["light_t"])
	caps["paralysis"] = int(st["paralysis"])
	caps["slow"] = int(st["slow"])
	if st.has("recalced"):
		_take_recalc(st["recalced"])
	_apply_damage(dmg, true, at, effect)


# @port helper -- the BIOS's rand, 0..0x7fff
static func _rand() -> int:
	return randi() & 0x7FFF


# @port helper -- two's complement of a 32-bit product, as mflo leaves it
static func _s32(v: int) -> int:
	v &= 0xFFFFFFFF
	return v - 0x100000000 if v & 0x80000000 else v


# @orig game:0x800313fc player_controller+0x430  status:partial -- the switch on the state, for 0, 0x10, 0x11 and 0x12
# @orig game:0x80031364 player_controller+0x398  status:transcribed -- the paralysis's orange flash, every fourth frame, into status_tick's records
# @orig game:0x80031b98 player_controller+0xbcc  status:transcribed -- state 0x10 after the walk: the push, the tilt spring, the end
# @orig game:0x80031c14 player_controller+0xc48  status:transcribed -- state 0x12, the stun
# @orig game:0x80030424 player_turn+0x608  status:transcribed -- a swing begins on the attack edge once the pause is over
# @orig game:0x8002fc94 player_step_distances  status:transcribed -- speed squared over the root of the sum, and the two steps (0x8002fda0, 0x8002fdb4)
func _frame(dir: Vector3) -> void:
	var an := get_node_or_null("../Actors")
	creatures = an.solid() if an and an.has_method("solid") else []
	_status()
	if pstate == 0x11:
		_dying()
		_view()
		return
	# 0x80031c14, state 0x12 -- a stun: the tilt spring and nothing else, no
	# turn, no walk, no height, until the view has settled.
	if pstate == 0x12:
		_tilt()
		if tilt == [0, 0, 0]:
			_knock_end()
		_view()
		attack_latch = false
		combo_latch = 0
		_weapon()
		return
	var held := KFPad.held(KFPad.FORWARD) or KFPad.held(KFPad.BACK)
	var c := frame_caps(caps, held)
	speed_cap = int(c[0])
	turn_cap = int(c[1])
	if int(c[2]):                     # the paralysis halves the speeds
		fwd_speed = coll._s16(fwd_speed) >> 1
		stf_speed = coll._s16(stf_speed) >> 1
		# and every fourth frame flashes orange (0x800313ac), into this
		# frame's records after sub_80030e14's
		if (int(caps["paralysis"]) & 3) == 3:
			_tint(tints_now, 1, [0x3C, 0x1E, 0], 0xC00, true)
			_tints(tints_now)
	# 0x800313b4: Seath's sword's guard (0x801b25b4) halves both caps
	if guard != 0:
		speed_cap >>= 1
		turn_cap >>= 1
	_cast_buttons()
	var rest := _use()
	# player_turn's tail (0x80030298): the combination, then a swing on the
	# attack button's edge when the pause after the last blow is over and no
	# combination is under way -- never while USE is held, when player_turn
	# has returned already. swing_start starts nothing with no weapon in hand
	# or while paralysed (0x801b2568); following the emulator, the swing is
	# the game's (ghost.gd)
	if rest and weapon_id < KFWeapon.records.size() and not KFGame.follow:
		var rec: PackedByteArray = KFWeapon.records[weapon_id]
		var full := int(wstate["meter"]) == KFWeapon.FULL and magic_meter == KFWeapon.FULL
		var may := KFWeapon.may_cast(weapon_id, rec, 1, character.get("spells", []), stat, working)
		var ph := KFWeapon.combo(combo, rec, combo_latch, attack_latch, _combo_buttons(), may, full,
			int(wstate["pause"]))
		if ph >= 0 and int(caps["paralysis"]) == 0:
			KFWeapon.start(wstate, rec, magic_meter, ph)
			if ph == 1:
				KFInfo.note("player: the combination -- the weapon's second swing")
	attack_latch = false
	combo_latch = 0
	var cap := SPEED_MAX_RUN if Input.is_key_pressed(KEY_SHIFT) else speed_cap
	# The controller's own order, off its call list: player_turn (the button
	# edges), player_look (the turn and the pitch), player_walk (the speeds),
	# then player_vertical or player_move. So the facing for this frame's step
	# is this frame's turn, not last frame's.
	_turn()
	# 0x8002f9bc reads the forward slot at 0x80081868 and the back one at
	# 0x8008186a; the strafe pair is 0x8008187c, which accelerates the speed,
	# and 0x80081878, which decelerates it -- so 0x7c is the positive
	# direction and with the default scheme that makes R1 strafe right.
	fwd_speed = _ramp(fwd_speed, KFPad.held(KFPad.FORWARD),
		KFPad.held(KFPad.BACK), cap)
	stf_speed = _ramp(stf_speed, KFPad.held(KFPad.ALT_C),
		KFPad.held(KFPad.ALT_A), cap, 2)
	# 0x8002fc94: the distances are not the speeds. Each is
	# speed^2 / isqrt(sum of squares), which normalises a diagonal and, because
	# the root is a unit short, makes a straight walk one unit longer.
	var h := coll.isqrt(fwd_speed * fwd_speed + stf_speed * stf_speed)
	var fd := 0
	var sd := 0
	if h != 0:
		fd = (fwd_speed * fwd_speed) / h
		sd = (stf_speed * stf_speed) / h
		if fwd_speed < 0: fd = -fd
		if stf_speed < 0: sd = -sd
	# player_walk steps twice, forward along facing + 0x400 and the strafe along
	# the facing, each through player_horizontal; then the height. Both calls
	# are made even for a step of nothing (0x8002fda0, 0x8002fdb4): that still
	# takes a steep ramp's push, so standing on one slides you down it.
	_horizontal((facing + 0x400) & 0xFFF, fd)
	_horizontal(facing & 0xFFF, sd)
	# 0x80031b98, state 0x10 -- knocked back: after the walk, the push with its
	# Y held at 1, the tilt spring, and the end once all three tilts are 0.
	if pstate == 0x10:
		push[1] = 1
		_push()
		_tilt()
		if tilt == [0, 0, 0]:
			_knock_end()
	_move(0, 0)
	_bob(coll.isqrt(fd * fd + sd * sd))
	_view()
	_weapon()


# player_controller's caps for the frame, before player_turn runs (0x80031180
# on): the speed 200 and the turn 0x20 walking or 0x28 standing; then
# 0x801b24f6 -- under turn_slow_timer down by 0x64 to -0xce4 (up again once
# the timer is under 0x40) with the turn halved and the timer counted down,
# else up by 0x320 to 0xaf0 while 0x801b24f5 is 0 and down to 0 while not --
# grows the speed by mod / 0x1000 and the turn by mod / 0x2000 of themselves;
# and the paralysis (0x801b2568) makes both 0, counts down and halves the two
# speeds. [speed cap, turn cap, paralysed].
# @orig game:0x800311b4 player_controller+0x1e8  status:verified -- the run: tools/replay.py, 150129 of 150129 frames of bp16's speed caps, and the self-test this to it; the slowing and the paralysis transcribed (the paralysis's flash and the guard's halving, 0x800313b4, are _frame's)
static func frame_caps(c: Dictionary, walking: bool) -> Array:
	var speed := 0xC8
	var turn := TURN_MAX_MOVING if walking else TURN_MAX_STILL
	var mod := int(c["mod"])
	if int(c["slow"]) != 0:
		if int(c["slow"]) < 0x40:
			mod = KFWeapon.s16(mod + 0x64)
			if mod > 0:
				mod = 0
		else:
			mod = KFWeapon.s16(mod - 0x64)
			if mod < -0xCE4:
				mod = -0xCE4
		turn >>= 1
		c["slow"] = int(c["slow"]) - 1
	elif int(c["run"]) == 0:
		mod = KFWeapon.s16(mod + 0x320)
		if mod > 0xAF0:
			mod = 0xAF0
	else:
		mod = KFWeapon.s16(mod - 0x320)
		if mod < 0:
			mod = 0
	c["mod"] = mod
	speed += (mod * speed) >> 12
	turn += (mod * turn) >> 13
	var para := int(c["paralysis"]) != 0
	if para:
		speed = 0
		turn = 0
		c["paralysis"] = int(c["paralysis"]) - 1
	return [speed, turn, 1 if para else 0]


# player_turn on 0x801b24f5: USE held this frame and the last counts it down to
# 0 -- and with the groundal boots (0x4c) on the feet (0x801b25d8) USE held
# does nothing at all -- else it is 1 again (0x800302a8).
# @orig game:0x8003005c player_turn+0x240  status:verified -- through frame_caps, the same 150129 frames
static func run_flag(c: Dictionary, held: bool) -> void:
	if held:
		if int(c["run"]) != 0:
			c["run"] = int(c["run"]) - 1
	else:
		c["run"] = 1


# player_turn's USE stretch (0x80030010), tools/magic.py's: held this frame
# and the last, and the feet not the groundal boots (0x4c), the run's flag
# counts down (run_flag), 500 goes from each meter -- an empty one pauses 60
# frames, 1 and 0 with the fu-jin or ichrius' boots (0x4d, 0x4f) -- and 0x80
# from damage_scale down to 0x400, and player_turn returns there: no swing
# starts. Otherwise the magic meter's pause runs down or it refills by
# meter_gain(the five working skills' mean, the cast record's +1 -- a quarter
# less with helm 0x25, twice with armour 0x30), to 5000; damage_scale climbs
# by 0x80 to 0x1000; the run's flag is 1; 0x801b25aa counts down, or
# 0x801b258c is 0x8009c3cc. `st` holds tools/magic.py's fields; true when the
# rest of player_turn runs.
# @orig game:0x80030010 player_turn+0x1f4  status:verified -- tools/magic.py, 1260 of 1260 frames as the game's own over 21 snapshots; tools/weapon.py use_held, 817 of 817 of bp25; the self-test this to it
static func use_tick(st: Dictionary, records: Dictionary) -> bool:
	var feet := int(st["worn"][4])
	var held: bool = (int(st["buttons"]) & int(st["use"])) != 0 \
		and (int(st["buttons_prev"]) & int(st["use"])) != 0
	if held and feet != 0x4C:
		run_flag(st, true)
		st["swing_pause"] = 1
		st["weapon_meter"] = (int(st["weapon_meter"]) - 500) & 0xFFFF
		if KFWeapon.s16(int(st["weapon_meter"])) <= 0:
			st["weapon_meter"] = 0
			st["swing_pause"] = 1 if feet == 0x4D or feet == 0x4F else 0x3C
		st["magic_pause"] = 1
		st["meter"] = (int(st["meter"]) - 500) & 0xFFFF
		if KFWeapon.s16(int(st["meter"])) <= 0:
			st["meter"] = 0
			st["magic_pause"] = 0 if feet == 0x4D or feet == 0x4F else 0x3C
		st["damage_scale"] = (int(st["damage_scale"]) - 0x80) & 0xFFFF
		if KFWeapon.s16(int(st["damage_scale"])) < 0x400:
			st["damage_scale"] = 0x400
		return false
	var total := 0
	for v in st["working"]:
		total += int(v)
	var avg := total / 5
	if int(st["magic_pause"]) != 0:
		st["magic_pause"] = int(st["magic_pause"]) - 1
	else:
		var rate := 0
		if int(st["casting"]) >= 0 and records.has(int(st["casting"])):
			rate = int((records[int(st["casting"])] as PackedByteArray)[1])
			if int(st["worn"][0]) == 0x25:
				rate -= rate >> 2
			if int(st["worn"][1]) == 0x30:
				rate <<= 1
		st["meter"] = (int(st["meter"]) + KFWeapon.gain(avg, rate)) & 0xFFFF
	if int(st["meter"]) >= 0x1389:
		st["meter"] = 0x1388
	st["damage_scale"] = (int(st["damage_scale"]) + 0x80) & 0xFFFF
	if KFWeapon.s16(int(st["damage_scale"])) > 0x1000:
		st["damage_scale"] = 0x1000
	run_flag(st, false)
	if int(st["b25aa"]) != 0:
		st["b25aa"] = int(st["b25aa"]) - 1
	else:
		st["b258c"] = 0x8009C3CC
	return true


# @port helper -- use_tick on the player's fields; true when player_turn goes on
func _use() -> bool:
	var now := KFPad.held(KFPad.USE)
	var st := {"buttons": 1 if now else 0, "buttons_prev": 1 if use_prev else 0,
		"use": 1, "worn": worn, "run": caps["run"], "swing_pause": int(wstate["pause"]),
		"weapon_meter": int(wstate["meter"]), "magic_pause": magic_pause,
		"meter": magic_meter, "damage_scale": damage_k, "working": working,
		"casting": casting, "b25aa": 0, "b258c": 0}
	var rest := use_tick(st, _spell_records())
	caps["run"] = int(st["run"])
	wstate["pause"] = int(st["swing_pause"])
	wstate["meter"] = int(st["weapon_meter"])
	weapon_meter = int(st["weapon_meter"])
	magic_pause = int(st["magic_pause"])
	magic_meter = int(st["meter"])
	damage_k = int(st["damage_scale"])
	use_prev = now
	return rest


# held_item_tick (0x8002d2a0), last in the controller (0x80032150): a bow's
# draw (0x1b, 0x1c), or the swing, or between swings the meter's refill; the
# blow is actors.gd's to land.
# @orig game:0x8002d2a0 held_item_tick  status:partial -- which of its three paths runs: the bow, the swing or the refill (weapon.gd)
func _weapon() -> void:
	# held_item_tick's .L47: with no weapon (0xff), nothing at all; and
	# following the emulator the swing and the meter are the game's
	if weapon_id >= KFWeapon.records.size() or KFGame.follow:
		return
	var rec: PackedByteArray = KFWeapon.records[weapon_id]
	if KFWeapon.BOWS.has(weapon_id):
		_bow(rec)
		weapon_meter = int(wstate["meter"])
		return
	if int(wstate["clock"]) == -1:
		KFWeapon.refill(wstate, rec, stat, KFPad.held(KFPad.ATTACK))
	else:
		var may := KFWeapon.may_cast(weapon_id, rec, 0, character.get("spells", []), stat, working)
		var ev := KFWeapon.swing(wstate, rec, KFPad.held(KFPad.ACTION), may, weapon_id, magic_meter)
		if wstate.has("guard"):       # the blow's frame sets or clears 0x801b25b4
			guard = int(wstate["guard"])
			wstate.erase("guard")
		if bool(ev["fire"]):
			# 0x8002d9bc: the flame rod's fire ball, aimed as spell 0 is from
			# (-200, 200, 400), paid for by nothing
			cast_off = [-0xC8, 0xC8, 0x190]
			_attack(0)
		if not (ev["shot"] as Array).is_empty():
			spell_begin(int(ev["shot"][0]), bool(ev["shot"][1]), int(ev["shot"][2]))
		if int(ev["hit"]) >= 0:
			_blow(rec, int(ev["hit"]), bool(ev["push"]))
	weapon_meter = int(wstate["meter"])


# A bow's frame over the player's own: the arrows counted in inventory_a
# alone (0x800c85e8, not take_item's fallback to the second array), the HP
# the second bow costs and the throw when the last of it goes, and the arrow
# on the effects node, put on the hand's model as held.gd draws it -- the
# swing's phase and clock. The sound 0x60 the port has not.
# @port helper -- hands KFWeapon.bow the player, the effects node and the hand's model
func _bow(rec: PackedByteArray) -> void:
	var fx = get_node_or_null("../Effects")
	if fx == null:
		return
	var item: int = KFWeapon.BOWS[weapon_id][1]
	var p := {"pos": [gx, gy, gz, 0], "view": view_angles(), "bob": bob, "crouch": crouch,
		"hp": hp, "arrows": {item: int(inventory.a[item])}, "rand": func() -> int: return rand()}
	var key := KFWeapon.MODEL_KEY + weapon_id
	var verts := func(ph: int, c: int) -> Array:
		return KFAnim.vertices(key, ph, c) if KFAnim.models.has(key) else []
	var ev := KFWeapon.bow(wstate, rec, weapon_id, KFPad.held(KFPad.ATTACK), p, fx, verts)
	var a := inventory.a
	a[item] = int(p["arrows"][item])
	inventory.a = a
	hp = int(p["hp"])
	if ev.has("thrown"):
		_throw(null)


# The view's angles as 0x801b2608 holds them for what reads it: the pitch the
# view draws at, the yaw with the knock-back's tilt, and its roll.
# @port helper -- [pitch, yaw, roll], as _view draws them
func view_angles() -> Array:
	var p := view_pitch if view_pitch >= 0 else view_pitch_now()
	return [_signed(p), _signed((facing + int(tilt[1])) & 0xFFF), _signed(int(tilt[2]) & 0xFFF)]


# The blow: the probe's step off the pitch and facing, the offense ratings --
# the weapon's own eight, which is all player_recalc_stats adds for a fresh
# character -- against the creature, and what comes back: experience through
# award_exp, and a strong blow counted towards the stat (0x8002a074, one in
# a hundred).
# @orig game:0x8002a074 strong_blow  status:transcribed -- a strong blow counted, one in a hundred to stat 36; the strike is actors.gd's, the experience levelup.gd's
func _blow(rec: PackedByteArray, strength: int, push_back: bool) -> void:
	var an := get_node_or_null("../Actors")
	if an == null or not an.has_method("strike"):
		return
	var step := KFWeapon.probe(coll, pitch, facing, KFWeapon.u16(rec, 0x1A))
	# held_item_tick hands actor_take_hit the effective stat and the eight
	# offense ratings (0x8002db64)
	var r: Dictionary = an.strike(Vector3i(gx, gy, gz), step,
		coll._s16(facing + int(tilt[1])), stat, offense, strength, push_back)
	if r.is_empty():
		return
	if bool(r.get("strong", false)):
		strong_hits += 1
		if strong_hits >= 100:           # 0x8002a074
			strong_hits = 0
			character["stat36"] = mini(int(character["stat36"]) + 1, 999)
			recalc_stats()
	_award(int(r.get("exp", 0)))


# What an effect's hit on a creature leaves the player (actor_take_hit's calls
# out): skill_practice with the spell's record when it was the player's spell
# and the creature had HP, the experience when it died.
# @port helper -- a spell's hit's practice and experience, from effects.gd
func spell_struck(out: Dictionary, kind: int) -> void:
	if bool(out.get("practice", false)):
		var recs := _spell_records()
		if recs.has(kind):
			var st := _magic_state()
			var calls := []
			skill_practice(st, recs[kind], calls)
			_magic_put(st, calls)
	_award(int(out.get("exp", 0)))


# award_exp (0x8002a310) through levelup.gd, and its banners and the stats.
# @port helper -- the experience a creature's death gives, with its banners and the stats
func _award(exp: int) -> void:
	if exp > 0:
		var r := {"exp": exp}
		var before := int(character["level"])
		character = KFLevels.award(character, int(r["exp"]), KFTalk.flags)
		hp_max = int(character["hp_max"])
		for b in character.get("banners", []):
			KFMessages.announce(int(b))          # "level up", "new spell"
		character.erase("banners")
		recalc_stats()
		KFInfo.note("player: %d experience, %d of %d, level %d" % [int(r["exp"]),
			int(character["exp"]), int(character["exp_next"]), int(character["level"])])
		if int(character["level"]) != before:
			KFInfo.note("player: level %d, HP max %d" % [int(character["level"]), hp_max])


# 0x8002ef80: a landing at 0x1e0 or faster hurts, t^3 / 118000 with t the
# velocity squared over 0x1000 -- the multiply by 0x8e2e0727 and the shift by
# 16 at 0x8002ef9c are a division by exactly 118000. 0x1e0 costs 1 HP, 0x300 25.
# @orig game:0x8002ef80 player_vertical+0x220  status:transcribed -- read, not yet seen in a recording
static func fall_damage(v: int) -> int:
	var t := (v * v) >> 12
	var c := t * t * t
	c = (c & 0xFFFFFFFF) - (0x100000000 if c & 0x80000000 else 0)
	var hi := (c * (0x8E2E0727 - 0x100000000)) >> 32
	return ((hi + c) >> 16) - (c >> 31)


# A creature's blow, from actors.gd: actor_blow (0x8004d254) found the player in
# reach and arc and hands player_take_hit (0x8002ab18) slash, blow and stab
# from the record's +0x12, +0x14 and +0x16, the five magic attacks 0, the
# effect +0x11, the scales 0x1000 and 10, and its own point raised by +0xf << 5.
# @orig game:0x8004d348 actor_blow+0xf4  status:transcribed -- the call: the record's three attacks and its effect, the rest 0
func take_blow(a: Dictionary, rec: Array) -> void:
	var attacks := [_u16(rec, 0x12), _u16(rec, 0x14), _u16(rec, 0x16), 0, 0, 0, 0, 0]
	var at := Vector3i(int(a["px"]), int(a["py"]) - (int(rec[0xF]) << 5),
		int(a["pz"]))
	_hit(attacks, int(rec[0x11]), KFDamage.ARG9, KFDamage.ARG10, at)


# @port helper -- a little-endian halfword out of a record's bytes
static func _u16(rec: Array, o: int) -> int:
	return int(rec[o]) | (int(rec[o + 1]) << 8)


# apply_damage (0x8002a6f4), tools/knock.py's: the HP; with an attacker, a push
# away from its point raised 0x352 -- the share of the HP the hit took, a
# quarter of (dmg << 12) / hp_max held to 0x3b6, at least 0x50 and at most
# 0x1c2 (x5 up to 0x258 for effect bit 0x40), its Y held to +-0xc8 -- and a
# shake of isqrt(share << 2) held to 0x10..0x2a, one of eight by the bearing
# against the view's yaw, into player_knock; effect bit 0x80 makes it a stun.
# Without an attacker (a fall) the HP and the flash alone.
# @orig game:0x8002a6f4 apply_damage  status:transcribed -- tools/knock.py: 83 of 83 knock-back frames, the push's Y from the creature
func _apply_damage(dmg: int, has_at: bool, at: Vector3i, effect: int) -> void:
	if pstate == 0x11 or dmg == 0:
		return
	var left := maxi(hp - dmg, 0)
	var share := mini(coll._idiv(dmg << 12, hp_max), 0x3B6)
	hp = left
	var s1 := share >> 2
	var pv := [0, 0, 0]
	var yaw := 0
	if has_at:
		var dx := gx - at.x
		var dz := gz - at.z
		yaw = coll.vec_angle(dx, dz)
		var pitch_to := (-coll.vec_angle(gy - (at.y + 0x352), _len2d(dx, dz))) & 0xFFF
		s1 = maxi(s1, 0x50)
		s1 = mini(s1 * 5, 0x258) if effect & 0x40 else mini(s1, 0x1C2)
		var d := coll.direction_from_angles(pitch_to, yaw)
		for i in 3:
			pv[i] = coll._s16((int(d[i]) * s1) >> 12)
		pv[1] = clampi(pv[1], -0xC8, 0xC8)
	flash = maxi((0x514 - (share >> 1)) >> 2, 0x46)
	flash_colour = 0xDAC
	if left == 0:
		_throw(pv)                  # 0x8002a8b0: thrown by the blow that killed
		return
	if not has_at:
		return
	var sh := clampi(coll.isqrt(share << 2), 0x10, 0x2A)
	if effect & 0x40:
		sh <<= 1
	if effect & 0x80:               # player_knock_hard (0x800309c8)
		if pstate == 7 or pstate == 8 or pstate == 9:
			return
		pstate = 0x12
		push = pv
		tilt_vel = [0, 0, -sh if randi() % 0x8000 < 0x4001 else sh]
		return
	var i := (((yaw - coll._s16(facing + int(tilt[1]))) + 0x100) >> 9) & 7
	var way: Array = SHAKES[i]
	if pstate == 7 or pstate == 8 or pstate == 9:
		return
	pstate = 0x10                   # player_knock (0x80030908)
	push = pv
	tilt_vel = [int(way[0]) * sh, 0, int(way[1]) * sh]
	vstate = 0x40
	vvel = int(pv[1])


const SHAKES := [[-1, 0], [-1, 1], [0, 1], [1, 1], [1, 0], [1, -1], [0, -1],
	[-1, -1]]


# vec_length_2d (0x80016c08): the length to eight, through the game's root.
# @orig game:0x80016c08 vec_length_2d  status:transcribed
func _len2d(a: int, b: int) -> int:
	return coll.isqrt((a >> 3) * (a >> 3) + (b >> 3) * (b >> 3)) << 3


# player_move (0x8002f320), only ever run while thrown: the push whole if the
# way is clear; else at the same height, the push 0x20 shorter after; else up a
# step of at most 0x100 if nothing but floor and wall (0x205) is in the way,
# 0x38 shorter; else not at all. A push shorter than what it loses stops.
# @orig game:0x8002f320 player_move  status:transcribed -- tools/knock.py: 83 of 83 frames of the recorded knock-backs
func _push() -> void:
	var nx: int = gx + int(push[0])
	var ny: int = gy + int(push[1])
	var nz: int = gz + int(push[2])
	var q := _query31(nx, ny, nz)
	if int(q["mask"]) != 0:
		ny = gy
		q = _query31(nx, ny, nz)
		var cut := 0x20
		var mask: int = q["mask"]
		if mask == 0:
			push[1] = 1
		elif (mask & ~0x205) != 0 or int(q["floor"]) + 0x100 < gy:
			return
		else:
			ny = int(q["floor"])
			cut = 0x38
		var ln := _len2d(int(push[0]), int(push[2]))
		if not cut < ln:
			push[0] = 0
			push[2] = 0
			return
		push[0] = coll._idiv(int(push[0]) * (ln - cut), ln)
		push[2] = coll._idiv(int(push[2]) * (ln - cut), ln)
	gx = nx
	gy = ny
	gz = nz
	push[1] = coll._s16(int(push[1]) + 0x20)


# collide_query with the player's 0x31: tiles, objects and the creatures.
# @orig game:0x80033f38 collide_query  status:partial -- the player's 0x31: the tiles, the objects and the creatures
func _query31(x: int, y: int, z: int) -> Dictionary:
	var q := coll.query_all(x, y, z)
	if _creature_at(x, y, z) != -1:
		q["mask"] = int(q["mask"]) | CREATURE_BIT
	return q


# 0x8003047c: each tilt driven back to 0 by the spring at 0x80016168 -- within
# 4 of it and no faster than 8, snap; else 8 towards it and 4 of friction.
# @orig game:0x8003047c player_tilt_spring  status:transcribed -- a shake of 0x2a lasts 28 frames, both recorded knock-backs
func _tilt() -> void:
	for i in 3:
		tilt_vel[i] = coll._s16(_spring(coll._s16(int(tilt[i])), int(tilt_vel[i])))
	for i in 3:
		tilt[i] = coll._s16(int(tilt[i]) + int(tilt_vel[i]))


# @port helper -- spring_to as player_tilt_spring calls it: target 0, accel 8, friction 4
static func _spring(cur: int, vel: int) -> int:
	return _spring_to(0, cur, vel, 8, 4)


# spring_to (0x80016168): within accel/2 of the target and no faster than
# accel, the velocity that lands on it; else accel towards it, friction off.
# @orig game:0x80016168 spring_to  status:transcribed
static func _spring_to(target: int, cur: int, vel: int, accel: int, friction: int) -> int:
	var d := (target - cur) & 0xFFF
	var tol := accel >> 1
	if (d <= tol or d >= 0x1000 - tol) and vel >= -accel and vel <= accel:
		return target - cur
	if cur != target:
		vel += -accel if ((cur - target) & 0xFFF) < 0x801 else accel
	if vel > 0:
		return vel - friction
	if vel < 0:
		return vel + friction
	return vel


# player_throw (0x80030a6c): state 0x11, the push that killed as the velocity,
# the view's pitch tilt still, the count from 0.
# @orig game:0x80030a6c player_throw  status:transcribed -- not the sound
func _throw(pv) -> void:
	if pstate == 0x11:
		return
	pstate = 0x11
	if pv != null:
		push = [int(pv[0]), int(pv[1]), int(pv[2])]
	tilt_vel[0] = 0
	tilt_vel[1] = 0
	death_frames = 0


# The controller's arm for state 0x11 (0x80031c54): no turn, no walk, no
# height -- the HP held at 0, the view's pitch springing to -0x400 (8, 4, and
# half again of the velocity each frame), the head bob sinking the eye by 0x1f4
# a frame to 0x5dc, the throw through player_move with its own gravity. From
# frame 0x20 the screen fades out over 0x20 frames (0x8003d624), and at 0x41:
# with item 107 the crystal revives -- a fixed spot on level 0, the item taken,
# HP and MP full (0x8002b3a8) -- else a new character (0x8002b468) and the
# story flags cleared, and level 0 loaded either way (level_state_writer).
# @orig game:0x80031c54 player_controller+0xc88  status:transcribed -- a label inside player_controller; the inventory and the gold kept across the revive's reload are the port's way of keeping them; the level 0 it loads either way (it reloaded the level in hand until this was read)
func _dying() -> void:
	hp = 0
	tilt_vel[0] = coll._s16(_spring_to(-0x400, coll._s16(int(tilt[0])), int(tilt_vel[0]), 8, 4))
	tilt[0] = coll._s16(int(tilt[0]) + ((3 * int(tilt_vel[0])) >> 1))
	if bob < 0x5DC:
		bob += 0x1F4
	_push()
	death_frames += 1
	if death_frames < 0x20:
		return
	if death_frames < 0x41:
		fade = (0xFF * ((death_frames - 0x20) << 7)) >> 12
		KFGame.screen_fade(0x82, fade, fade, fade)
		return
	var revive: bool = inventory.has_item(REVIVE_ITEM)
	if revive:
		# level_state_write for the level left (0x80031df4): the scene's
		# objects write its table as they leave, and KFLevelState its stream
		inventory.take_item(REVIVE_ITEM)
		respawn = [REVIVE_POS.x, REVIVE_POS.y, REVIVE_POS.z, REVIVE_FACING]
		carried = [inventory, gold, character, weapon_id, worn, [spell_a, spell_b, item_b]]
	else:
		# a new character (0x8002b468), where it puts a new game: bp25's session
		# began at (0x1f000, -0x3c00, 0x4000) too; reset_story_flags
		# (0x80031e2c) clears the flags and every level's record, and
		# story_flags + 9 is set again (0x80031e3c)
		respawn = [0x1F000, -0x3C00, 0x4000, 0]
		KFLevelState.clear()
		KFTalk.flags = []
		KFTalk.states = {}
		KFTalk.load_level(0)
		KFTalk.flags[9] = 1
	fade = 0
	# either way level 0 (level_state_writer(0, ...), 0x80031e70)
	KFGame.level = 0
	KFGame.block = [0, 0, 0, 0, 0]
	get_tree().change_scene_to_file(KFGame.scene_of(0))


# Where _ready puts the player after a death reloads the level: the crystal's
# spot, or [] for a new game's start.
static var respawn = null
# Where a crossing puts the player down in the next level's world, and how:
# [x, y, z, facing, pitch, vertical state and velocity, speeds, HP, its
# maximum, MP, the two meters, the poison, the floor (0x801b2644)].
static var arrive = null
# What the player carries across that reload when the crystal revives them:
# [the inventory, the gold, the character, the weapon, what is worn, the
# magic and the button's].
static var carried = null


# sub_80030e14, called by player_controller each frame before the pad
# (0x80031118), tools/status.py's: four ramps of a level and a timer through
# sub_80030b24 -- the level climbs a frame at a time while it is under the
# timer, which is then zeroed, and falls back; the intensity is level * scale
# / 0x40, scale from 0x40 up, -1 once both are 0. The darkness (0x801b2562)
# blends the lighting toward a background of (10, 10, 10), near 0x1388 and far
# 0x1770 and sets a grey (0x80) subtracted by a quarter of it; the light
# (0x801b2570) the background toward (0xdc, 0xdc, 0xa0) and the far toward
# 0x4650; the hit's flash falls by its step and adds red (0x3c) by itself,
# 0x1000 at most; the curse (0x801b255e) adds (0x1e, 0x1e, 0xa), and its
# level back at 0 runs player_recalc_stats. `st` holds the eight fields;
# the answer is the two rectangles' records ([count, mode, r, g, b], mode 1
# adding and 2 subtracting), the two lighting intensities (-1: none) and the
# recalculations.
# @orig game:0x80030e14 sub_80030e14  status:verified -- tools/status.py: 84 of 84 runs, the game's own over the snapshots frame for frame, fields, tints and the 48 lighting records; the self-test this to it
# @orig game:0x80030b24 sub_80030b24  status:verified -- through status_tick
static func status_tick(st: Dictionary) -> Dictionary:
	var tints := [[0, 1, 0, 0, 0], [0, 1, 0, 0, 0]]
	var out := {"tints": tints, "dark": -1, "light": -1, "recalc": 0}
	var r := _ramp_status(st, "dark_lv", "dark_t", 0x40, 0xC00)
	if r != -1:
		out["dark"] = r
		_tint(tints, 2, [0x80, 0x80, 0x80], r >> 2, false)
	r = _ramp_status(st, "light_lv", "light_t", 0x40, 0xE10)
	if r != -1:
		out["light"] = r
	if KFWeapon.s16(int(st["flash"])) != 0:
		var f := (int(st["flash"]) - int(st["flash_step"])) & 0xFFFF
		if KFWeapon.s16(f) < 0:
			f = 0
		st["flash"] = f
		_tint(tints, 1, [0x3C, 0, 0], mini(KFWeapon.s16(f), 0x1000), true)
	r = _ramp_status(st, "curse_lv", "curse_t", 0x40, 0xC00)
	if r != -1:
		if KFWeapon.s16(int(st["curse_lv"])) == 0:
			out["recalc"] = 1
		_tint(tints, 1, [0x1E, 0x1E, 0xA], r, true)
	return out


# @port helper -- sub_80030b24 on two of status_tick's fields, written back unless -1
static func _ramp_status(st: Dictionary, lk: String, tk: String, most: int, scale: int) -> int:
	var lv := int(st[lk]) & 0xFFFF
	var t := int(st[tk]) & 0xFFFF
	if KFWeapon.s16(lv) == 0 and t == 0:
		return -1
	if KFWeapon.s16(lv) < KFWeapon.s16(t):
		lv = (lv + 1) & 0xFFFF
	else:
		t = 0
		lv = (lv - 1) & 0xFFFF
	st[lk] = lv
	st[tk] = t
	var v := KFWeapon.s16(lv)
	if v < most:
		v = _s32(v * scale) / most
	else:
		v = scale
	return KFWeapon.s16(v)


# sub_8003d8ec (adding) and sub_8003da10 (setting) on render_frame's two
# records: the count up, the mode, and each colour times k >> 12.
# @orig game:0x8003d8ec sub_8003d8ec  status:verified -- through status_tick
# @orig game:0x8003da10 sub_8003da10  status:verified -- through status_tick
static func _tint(tints: Array, mode: int, rgb: Array, k: int, add: bool) -> void:
	var rec: Array = tints[mode - 1]
	rec[0] = (int(rec[0]) + 1) & 0xFF
	rec[1] = mode
	for i in 3:
		var d := _s32(int(rgb[i]) * k) >> 12
		rec[2 + i] = KFWeapon.s16((int(rec[2 + i]) if add else 0) + d)


# sub_80034394 on one lighting record [r, g, b, near, far] (the bytes at
# +0x64 and the halves at +0x68, +0x6a): each moved by fixed_madd toward its
# target by k / 0x1000 -- 0xff in the colour or 0xffff for a distance leaves
# it -- and the two kept 0x1000 apart. scroll.gd's shader does the distances
# the same way, vertex by vertex, from the record's near and far.
# @orig game:0x80034394 sub_80034394  status:verified -- through status_tick, the 48 records sub_800344dc blends
static func light_blend(rec: Array, rgb: Array, near: int, far: int, k: int) -> void:
	var colour := int(rgb[0]) & 0xFF != 0xFF and int(rgb[1]) & 0xFF != 0xFF \
		and int(rgb[2]) & 0xFF != 0xFF
	if colour:
		for i in 3:
			rec[i] = (int(rec[i]) + (_s32((int(rgb[i]) - int(rec[i])) * k) >> 12)) & 0xFF
	if near != 0xFFFF:
		rec[3] = (int(rec[3]) + (_s32((near - int(rec[3])) * k) >> 12)) & 0xFFFF
		if int(rec[4]) - 0x1000 < int(rec[3]):
			rec[4] = (int(rec[3]) + 0x1000) & 0xFFFF
	if far != 0xFFFF:
		rec[4] = (int(rec[4]) + (_s32((far - int(rec[4])) * k) >> 12)) & 0xFFFF
		if int(rec[4]) < int(rec[3]) + 0x1000:
			rec[3] = (int(rec[4]) - 0x1000) & 0xFFFF


# @port helper -- status_tick on the player's fields, its rectangles drawn and its lighting handed to the world's shader
func _status() -> void:
	var st := {"dark_lv": dark[0], "dark_t": dark[1], "light_lv": light[0],
		"light_t": light[1], "curse_lv": curse[0], "curse_t": curse[1],
		"flash": flash_colour, "flash_step": flash}
	var out := status_tick(st)
	dark = [int(st["dark_lv"]), int(st["dark_t"])]
	light = [int(st["light_lv"]), int(st["light_t"])]
	curse = [int(st["curse_lv"]), int(st["curse_t"])]
	flash_colour = int(st["flash"])
	if int(out["recalc"]) > 0:
		recalc_stats()
	tints_now = out["tints"]
	_tints(tints_now)
	var sc := get_node_or_null("../Scroll")
	if sc and sc.has_method("set_lights"):
		sc.call("set_lights", int(out["dark"]), int(out["light"]))


# render_frame's two rectangles over the whole screen (sub_8003d64c, adding,
# and sub_8003d79c, subtracting): each record asked for this frame draws its
# colour over its count, a byte a channel, at the rate its mode gives -- under
# the panel, which is drawn nearer.
# @orig game:0x8003d64c sub_8003d64c  status:transcribed -- the colour and the rate; a ColorRect blended as the GPU's B+F
# @orig game:0x8003d79c sub_8003d79c  status:transcribed -- the same, B-F
func _tints(tints: Array) -> void:
	var layer := get_node_or_null("Tints")
	if layer == null:
		layer = CanvasLayer.new()
		layer.name = "Tints"
		layer.layer = 0
		for m in [1, 2]:
			var r := ColorRect.new()
			r.name = "Rate%d" % m
			r.set_anchors_preset(Control.PRESET_FULL_RECT)
			r.mouse_filter = Control.MOUSE_FILTER_IGNORE
			var mat := CanvasItemMaterial.new()
			mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD if m == 1 \
				else CanvasItemMaterial.BLEND_MODE_SUB
			r.material = mat
			r.visible = false
			layer.add_child(r)
		add_child(layer)
	for i in 2:
		var rec: Array = tints[i]
		var r := layer.get_node("Rate%d" % (i + 1)) as ColorRect
		var n := int(rec[0])
		r.visible = n > 0
		if n > 0:
			r.color = Color8((int(rec[2]) / n) & 0xFF, (int(rec[3]) / n) & 0xFF,
				(int(rec[4]) / n) & 0xFF)


# screen_fade_draw's quad (KFGame.fade_quad) as Godot draws it, every
# rendered frame: a rectangle over the view whose blend is the mode's -- mix
# at a half, add, subtract, add a quarter -- under the panel's layer, or over
# it for bit 0x80 (the dying's 0x82, which takes the screen to black; a warp's
# 1, which adds white until it is white).
# @port engine -- the screen's fade, as a layer over the view
func _screen() -> void:
	var q := KFGame.fade_quad(KFGame.screen)
	var layer := get_node_or_null("ScreenFade") as CanvasLayer
	if q.is_empty():
		if layer:
			layer.visible = false
		return
	if layer == null:
		layer = CanvasLayer.new()
		layer.name = "ScreenFade"
		var r := ColorRect.new()
		r.name = "Quad"
		r.set_anchors_preset(Control.PRESET_FULL_RECT)
		r.mouse_filter = Control.MOUSE_FILTER_IGNORE
		r.material = CanvasItemMaterial.new()
		layer.add_child(r)
		add_child(layer)
	layer.visible = true
	layer.layer = 10 if bool(q["over"]) else 0
	var rect := layer.get_node("Quad") as ColorRect
	var mat := rect.material as CanvasItemMaterial
	var five: Array = q["five"]
	var c := Color(int(five[0]) / 31.0, int(five[1]) / 31.0, int(five[2]) / 31.0, 1.0)
	match int(q["blend"]):
		0:
			mat.blend_mode = CanvasItemMaterial.BLEND_MODE_MIX
			c.a = 0.5
		1:
			mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
		2:
			mat.blend_mode = CanvasItemMaterial.BLEND_MODE_SUB
		3:
			mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
			c.a = 0.25
	rect.color = c


# render_flags_reset (0x80034180), second in game_main's frame and so before
# player_controller: of its eleven render flags, the one the port keeps --
# screen_fade's mode back to 0xff, no fade.
# @orig game:0x80034180 render_flags_reset  status:partial -- the fade's mode (0x801aeafa) alone; the other ten flags are not the port's
func _render_flags() -> void:
	KFGame.screen[0] = 0xFF


# 0x8003078c: back to state 0 with both speeds and every view offset at 0.
# @orig game:0x8003078c player_state_reset  status:transcribed
func _knock_end() -> void:
	pstate = 0
	fwd_speed = 0
	stf_speed = 0
	tilt = [0, 0, 0]
	dip = 0


# The view, as camera_pose (0x8002b330) hands it to RotMatrix: the eye bob and
# crouch below 0x640 (Y grows down), pitch + tilt.x + the nod, yaw + tilt.y,
# roll = tilt.z, as Rx(pitch) Ry(yaw) Rz(roll) from the world to the eye. The
# player node carries the facing, so the camera takes what is left of it.
# @orig game:0x8002b330 camera_pose  status:partial -- the eye's bob and crouch, and the three angles with the tilts, as the view takes them
func _view() -> void:
	var cam := get_node_or_null("Camera")
	if cam == null:
		return
	cam.position.y = (EYE_UNITS - float(bob) - float(crouch)) / UNIT
	var k := TAU / 4096.0
	var p := float(_signed(view_pitch if view_pitch >= 0 else view_pitch_now())) * k
	var y := float(_signed(int(tilt[1]))) * k
	var r := float(_signed(int(tilt[2]))) * k
	var f := float(facing) * k
	var world := Basis(Vector3.BACK, r) * Basis(Vector3.UP, f + y) \
		* Basis(Vector3.RIGHT, -p)
	cam.basis = Basis(Vector3.UP, f).inverse() * world


# player_horizontal (0x8002e3f8): a step of `dist` along `angle`, and what the
# game does when collide_query at the player's height says no. Before this the
# port took every step and let player_vertical lift it onto whatever it had
# walked into, so any wall could be climbed; a player noticed. Read off the
# listing, in its order, and the same in tools/movement.py, where the
# recording checks it:
#
#   clear                        take it, but first: a steep ramp's push of
#                                0x40 or more is added once and the step asked
#                                again -- a slide back down
#   nothing outside 0x207, the surface no more than 0x500 above the feet,
#   player state 0 (0x8002e5cc -- none while knocked back), the ceiling more
#   than a body above it
#                                a step up: take it, the same way
#   an object with a rectangle   (its byte +3 has bit 4) slide along one of its
#                                axes: the step turned into its frame, one part
#                                kept, turned back by its angle + 0x400, 0x3e8
#                                or 0x418; six tries
#   anything else in the way     go round it: the target moves to the thing's
#                                centre plus its radius plus 0x370, along the
#                                bearing from the centre -- a creature first,
#                                an object only when no creature was hit; a
#                                second thing in the way and the player stays
#   otherwise, a wall            try it 0x16 shorter at a time, once; then
#                                slide, the X part dropped, then only the X
#                                part; a diagonal wall (bit 2) slides along the
#                                diagonal the rotation of the cell the last
#                                query looked at gives; else stay
#
# The creatures are the awake ones in `creatures`, asked as actor_spot_taken
# asks for the player (_creature_at). Whichever way it ends, the step it ends
# on goes to 0x801b2600 and 0x801b2604 (0x8002ec7c) -- `step`, which a
# creature's lob leads the player by; called twice a frame, the strafe last,
# so that is the strafe's.
# @orig game:0x8002e3f8 player_horizontal  status:transcribed -- tools/replay.py: 124 891 of 125 116 ground frames; the creatures against the Python on made steps; the step it leaves read, not in a recording
func _horizontal(angle: int, dist: int) -> void:
	var s4: int = (coll.game_cos(angle) * dist) >> 12
	var s2: int = (coll.game_sin(angle) * dist) >> 12
	var first_x := s4
	var first_z := s2
	var shrunk := false
	var diag := false
	var tries := 0
	var pushes := 0
	var rel := 0
	var slid := false
	var last := -1                    # the cell and layer 0x801e6468 points at
	var x := gx
	var z := gz
	for _i in 64:
		var tx := x + s4
		var tz := z + s2
		var q := coll.query_all(tx, gy, tz)
		last = int(q["at"])
		var mask: int = int(q["mask"])
		var who := _creature_at(tx, gy, tz)
		if who != -1:
			mask |= CREATURE_BIT
		var take := mask == 0
		var blocked := false
		if not take and mask & ~0x207 == 0:
			if not (int(q["floor"]) + STEP_UP < gy) and pstate == 0 \
					and int(q["ceil"]) - int(q["floor"]) < -coll.body:
				take = true
			elif not (mask & 2):
				blocked = true
		if take:
			var push: int = q["push"]
			if push >= STEEP_PUSH and not slid:
				slid = true
				var pa: int = -int(q["push_angle"]) - 0x400
				s4 += (coll.game_cos(pa) * push) >> 12
				s2 += (coll.game_sin(pa) * push) >> 12
				continue
			gx = tx
			gz = tz
			if int(q["at"]) >= 0:         # 0x8002e590: the layer that step was asked on
				layer = 5 if int(q["at"]) % 6 == 3 else 0
			step.x = s4                   # 0x8002ec7c: whatever it ends on
			step.z = s2
			return
		var oi: int = q["object"]
		if oi != -1 and (int(coll.objects[oi][4]) & 4) and tries < RECT_TRIES.size():
			var o: Array = coll.objects[oi]
			tries += 1
			var d := absi(dist)
			if tries == 1:
				rel = coll._s16(coll.ratan2(s2, s4) - 0x400 - (int(o[9]) & 0xFFFF))
			var u: int = (d * coll.game_cos(rel)) >> 12
			var v: int = (d * coll.game_sin(rel)) >> 12
			if tries & 1:
				if v != 0: u = 0
			elif u != 0:
				v = 0
			var turn: int = coll._s16(o[9]) + RECT_TRIES[tries - 1]
			var c := coll.game_cos(turn)
			var sn := coll.game_sin(turn)
			s4 = ((u * c) >> 12) - ((v * sn) >> 12)
			s2 = ((u * sn) >> 12) + ((v * c) >> 12)
			continue
		if mask & 0x30:
			pushes += 1
			if pushes == 2:
				break
			# collide_target (0x80033d84): the creature when there is one
			var ox := 0
			var oz := 0
			var r := AROUND
			if who != -1:
				var c: Array = creatures[who]
				ox = int(c[0])
				oz = int(c[2])
				r += int(c[3])
			else:
				var o: Array = coll.objects[oi]
				ox = int(o[5])
				oz = int(o[7])
				r += int(o[10])
			var bearing := coll.ratan2(s2 - (oz - z), s4 - (ox - x))
			s4 = _trunc12(coll.game_cos(bearing) * r) + ox - x
			s2 = _trunc12(coll.game_sin(bearing) * r) + oz - z
			continue
		if not shrunk:
			shrunk = true
			var s0 := dist - SHRINK
			while s0 >= 0:
				var vx: int = coll.game_cos(angle) * s0
				var vz: int = coll.game_sin(angle) * s0
				var nx := x + ((vx + 0xFFF if vx < 0 else vx) >> 12)
				var nz := z + ((vz + 0xFFF if vz < 0 else vz) >> 12)
				s0 -= SHRINK
				var sq := coll.query_all(nx, gy, nz)
				last = int(sq["at"])
				if int(sq["mask"]) == 0 and _creature_at(nx, gy, nz) == -1:
					x = nx
					z = nz
					break
		if blocked or (mask & 1):
			if s4 != 0:
				s4 = 0
				continue
			if s2 != 0:
				s4 = first_x
				s2 = 0
				continue
		if not (mask & 2):
			break
		if diag:
			if s4 != 0:
				s4 = 0
				continue
			if s2 != 0:
				s4 = first_x
				s2 = 0
				continue
			break
		var rot := 0
		if last >= 0:
			rot = coll.cells[last + 1] & 3
		if rot == 0 or rot == 2:
			s4 = (first_x + first_z) >> 1
			s2 = s4
		else:
			s4 = (first_x - first_z) >> 1
			s2 = -s4
		diag = true
	gx = x
	gz = z
	step.x = s4
	step.z = s2


# actor_spot_taken (0x8004d644) as the player asks it: the first creature, in
# slot order, that is awake -- the list holds only those -- whose flags have no
# bit in common with 4, the byte player_controller puts at 0x8018faa8 while it
# moves the player (0x80031004), and that in_range puts within its radius plus
# the player's, bodies overlapping in height. Level 0's ten of kind 15, flags
# 0x404, are the ones it lets through.
# @orig game:0x8004d644 actor_spot_taken  status:transcribed -- the player's side; the follower lift is in tools/movement.py
func _creature_at(x: int, y: int, z: int) -> int:
	for i in creatures.size():
		var c: Array = creatures[i]
		if int(c[5]) & PLAYER_ACTOR_MASK:
			continue
		if coll.in_range(int(c[0]), int(c[1]), int(c[2]), x, y, z,
				int(c[3]) + coll.radius, int(c[4]), coll.body) != -1:
			return i
	return -1


# A product over 4096 rounded towards zero, the way player_horizontal's
# push-out does it (`addiu 0xfff` before the shift when negative).
# @port helper -- a product over 4096 rounded towards zero, as player_horizontal's push-out does it
static func _trunc12(v: int) -> int:
	return (v + 0xFFF if v < 0 else v) >> 12


# The turn rate ramps to the cap and decays back to zero by a quarter of the cap
# a frame -- the same rule player_walk uses for the ground speed, and the reason
# a turn keeps going for a few frames after the button is let go. Then the
# facing takes the rate and wraps: `facing = (facing + rate) & 0xfff`, at
# 0x8002f738.
#
# The rate is kept in the game's own units, 0x1000 to the circle, so it can be
# compared with 0x801b264c directly; the Godot rotation is derived from the
# facing at the end, the way ghost.gd reads the game's own.
# @orig game:0x8002f5c0 player_look  status:transcribed -- the yaw here, the pitch in _look
func _turn() -> void:
	var cap := turn_cap                               # 0x801b2668, frame_caps'
	var step := cap >> 2
	if KFPad.held(KFPad.LEFT_SLOT):                   # 0x8002f5e0
		turn_rate += step
		if turn_rate > cap:
			turn_rate = cap
	elif KFPad.held(KFPad.RIGHT_SLOT):                # 0x8002f648
		turn_rate -= step
		if turn_rate < -cap:
			turn_rate = -cap
	elif turn_rate > 0:                               # 0x8002f6b4, the decay
		turn_rate -= step
		if turn_rate < 0:
			turn_rate = 0
	elif turn_rate < 0:                               # 0x8002f6ec
		turn_rate += step
		if turn_rate > 0:
			turn_rate = 0
	facing = (facing + turn_rate) & 0xFFF             # 0x8002f738
	rotation.y = float(facing) * TAU / 4096.0


# The other half of player_look: the pitch. look_b (R2 in scheme A) adds 3 to
# the rate a frame up to 0x20, look_a (L2) takes 3 away down to -0x20, neither
# lets it decay by 3 to nothing, and both bring the view back to level -- the
# rate steps by 8 towards the pitch that is left, no more than a quarter of it.
# The pitch then takes the rate and stops at 0x2bc either way. Against the
# recording, the rate this predicts is the one the game logged on 118 501 of
# 118 502 frames, 1086 of them with a look button or the rate active.
# @orig game:0x8002f5c0 player_look  status:transcribed -- the pitch half
func _look() -> void:
	var up := KFPad.held(KFPad.ALT_B)                 # bind_look_a
	var down := KFPad.held(KFPad.ALT_D)               # bind_look_b
	if down and up:
		var sp := _signed(pitch)
		if sp >= 0:                                   # at or below level: back up
			pitch_rate -= 8
			if pitch_rate < -(sp >> 2):
				pitch_rate = -(sp >> 2)
				if pitch_rate == 0:
					pitch_rate = -sp
		elif sp < 0:                                  # above level: back down
			pitch_rate += 8
			if (-sp) >> 2 < pitch_rate:
				pitch_rate = (-sp) >> 2
				if pitch_rate == 0:
					pitch_rate = -sp
	elif down:
		pitch_rate = mini(pitch_rate + 3, 0x20)
	elif up:
		pitch_rate = maxi(pitch_rate - 3, -0x20)
	elif pitch_rate > 0:
		pitch_rate = maxi(pitch_rate - 3, 0)
	elif pitch_rate < 0:
		pitch_rate = mini(pitch_rate + 3, 0)
	if pitch_rate > 0:
		pitch = (pitch + pitch_rate) & 0xFFF
		if _signed(pitch) > PITCH_LIMIT:
			pitch = PITCH_LIMIT
	elif pitch_rate < 0:
		pitch = (pitch + pitch_rate) & 0xFFF
		if _signed(pitch) < -PITCH_LIMIT:
			pitch = (-PITCH_LIMIT) & 0xFFF
	_aim()


# The camera follows the pitch the way ghost.gd has it: negated, 0x1000 a turn.
# @port engine -- the camera after a change of pitch
func _aim() -> void:
	_view()


# The view's pitch as camera_pose leaves it in 0x801b2608: the player's,
# the knock-back's tilt and the landing's nod.
# @port helper -- the pitch _view draws at, for object_give to start from
func view_pitch_now() -> int:
	return (pitch + int(tilt[0]) + dip) & 0xFFF


# clear_movement_state (0x8002b6f0): the speeds, the turn rate and the pitch
# rate zeroed. Its other half, buttons_now masked down to the attack, action,
# use and map buttons, the port's pad does not need.
# @orig game:0x8002b6f0 clear_movement_state  status:partial -- the five speeds; not the button mask
func clear_movement() -> void:
	fwd_speed = 0
	stf_speed = 0
	turn_rate = 0
	pitch_rate = 0


# @port helper -- an angle, 0x1000 to the turn, as -0x800..0x7ff
static func _signed(a: int) -> int:
	a &= 0xFFF
	return a - 0x1000 if a >= 0x800 else a


# 0x8002f298, the tail of player_vertical: the phase walks forward by the
# magnitude of the step and the lift is three quarters of |sin| shifted down by
# five, so it peaks at 96 units and never goes negative. Grounded only: in the
# air (.L29) every path goes past it and the bob stays as it is -- the port
# had it 0 there, read without the branch, which wiped what _dying adds to it
# while the player is thrown -- and with OPTION 2's walking effect off
# (0x801b25e0) it is 0 (.L31).
# @orig game:0x8002f270 player_vertical+0x510  status:transcribed -- .L29: the state and the walking effect tested before the bob
# @orig game:0x8002f298 player_bob  status:transcribed -- a label inside player_vertical, not a routine of its own
func _bob(mag: int) -> void:
	if vstate != 0:
		return
	if int(KFGame.display[3]) == 0:
		bob = 0
		return
	bob_phase = (bob_phase + mag) & 0xFFF
	var v := coll.game_sin(bob_phase) >> BOB_SHIFT
	if v < 0:
		v = -v
	bob = v - (v >> 2)


# player_vertical (0x8002ed60). The horizontal is the caller's; this is the
# height, and the state machine that owns it. Every branch here was matched
# against the instruction the game actually took -- see tools/movement.py bp15.
# The height's step goes to 0x801b2602 (`step.y`): 0 (0x8002eda0), or the
# velocity before this frame's pull in the rise, the short drop and a clear
# frame of the fall.
# @orig game:0x8002ed60 player_vertical  status:verified -- 48 of 48 of the game's own height stores, tools/movement.py bp15; step.y read, not in a recording
func _move(dx: int, dz: int) -> void:
	gx += dx
	gz += dz
	step.y = 0                                        # 0x8002eda0; the falls' velocity below

	if vstate == 0x20:                                # 0x8002ee50, rising
		var surf20 := coll.surface(gx, gy, gz)
		last_surface = surf20
		var ry := gy + vvel
		if not (surf20 < ry and vvel < 0):
			if surf20 < gy:
				ry = surf20
			vstate = 0
		gy = ry
		step.y = vvel
		vvel += V_ACCEL_RISE
		return

	if vstate == 0x10:                                # 0x8002edf4, a short drop
		var surf10 := coll.surface(gx, gy, gz)
		last_surface = surf10
		var ny := gy + vvel
		if surf10 + V_LAND_SLACK < ny:
			gy = surf10
			vstate = 0
		else:
			gy = ny
		step.y = vvel
		vvel += V_ACCEL_SHORT
		return

	if vstate == 0x40:                                # 0x8002eec8, a real fall
		var fy := gy + vvel
		var q40 := coll.query(gx, fy, gz)             # the mask, not the surface
		last_surface = int(q40["floor"])
		if int(q40["mask"]) == 0:
			gy = fy
			step.y = vvel
			vvel = coll._s16(vvel + V_ACCEL_LONG)
			dip = vvel >> 1                           # 0x8002ef30, the view nods
			return
		if vvel < 0:
			vvel = 0                                  # into a ceiling: stopped
			return
		if vvel >= FALL_HURTS:                        # 0x8002efc0
			_apply_damage(fall_damage(vvel), false, Vector3i.ZERO, 0)
		gy = last_surface if vvel < V_SQUASH else last_surface - (vvel >> 1)
		crouch = 1                                    # 0x8002f058
		vstate = 0x50                                 # and into 0x50 now

	# 0x50 is the landing recoil and owns no height (0x8002f068): the crouch
	# takes a quarter of the velocity while it is positive, the velocity loses
	# 0x12c, the nod gains 0xa while the velocity is positive and loses 0x1e
	# after, and both spent ends it. Then state 0's code, below -- the landing
	# frame too: tools/knock.py, 2 of 2 recorded landings.
	if vstate == 0x50:
		if crouch > 0:
			crouch = coll._s16(crouch + (vvel >> 2))
		vvel = coll._s16(vvel - V_RECOIL)
		if dip > 0:
			dip = coll._s16(dip + (0xA if vvel > 0 else -0x1E))
		if crouch <= 0 and dip <= 0:
			vstate = 0
			vvel = 0
			crouch = 0
			dip = 0

	var surf := coll.surface(gx, gy, gz)              # 0x8002f120, grounded
	last_surface = surf
	if surf == KFCollision.NO_SURFACE:
		return
	var d := surf - gy
	if d < 0:                                         # the ground is above
		if d < -0x400:
			vstate = 0x20
			vvel = V_LAUNCH
		elif d < -0x200:
			gy -= 0x200
		elif d < -0x100:
			gy -= 0x100
		elif d < -0x80:
			gy -= 0x80
		else:
			gy = surf                                 # placed, not eased
	elif d > 0:                                       # the ground is below
		if int(coll.query(gx, gy + 1, gz)["mask"]) != 0:
			return                                    # 0x8002f1e0: nothing under us
		if d < 0x81:
			gy = surf
		elif d < 0x101:
			gy += 0x80
		elif d < 0x201:
			gy += 0x100
		else:
			vstate = 0x10 if d < 0x401 else 0x40
			vvel = V_START

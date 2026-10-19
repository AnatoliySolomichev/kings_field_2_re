class_name KFPad
# The controller, as the game reads it.
#
# `PadRead` is the Sony library's, at 0x800785ac in GAME.EXE and open:0x8001f9f0 in
# OPEN.EXE: it calls the BIOS (B0 0x16) and returns NOT of the buffer the BIOS
# fills, so **a set bit means pressed**. The bits below are the PSY-Q layout --
# the two halves of the hardware's word swapped -- and every one of them is
# used by the game's own binding tables, which is where they were read from.
#
# The game does not test buttons directly. It reads a *slot*, and the options
# screen decides which button each slot holds. The slots live at 0x80081868 to
# 0x80081882 in GAME.EXE and 0x8001f4c0 fills them from the seven movement
# schemes and four action schemes transcribed below, every value read off the
# code. Two slots the options screen never writes: the map is always SELECT and
# the menu is always START, which is what fixes the bit names to real buttons.
#
# The edge detection is the game's too: 0x801b265c is this frame's word and
# 0x801b265e last frame's, and every menu asks for a bit set in the first and
# clear in the second.
#
# @exe game -- OPEN.EXE's addresses say open:

const UP := 0x1000
const RIGHT := 0x2000
const DOWN := 0x4000
const LEFT := 0x8000
const TRIANGLE := 0x0010
const CIRCLE := 0x0020
const CROSS := 0x0040
const SQUARE := 0x0080
const L2 := 0x0001
const R2 := 0x0002
const L1 := 0x0004
const R1 := 0x0008
const SELECT := 0x0100
const START := 0x0800

# The slots, by the address of each in GAME.EXE.
const FORWARD := 0        # 0x80081868, read by player_walk and player_controller
const BACK := 1           # 0x8008186a
const LEFT_SLOT := 2      # 0x8008186c, read by 0x8002f5c0
const RIGHT_SLOT := 3     # 0x8008186e
const ATTACK := 4         # 0x80081870, read by player_turn and the attack code
const MENU_SLOT := 5      # 0x80081872, read by 0x800305d8
const ACTION := 6         # 0x80081874
const USE := 7            # 0x80081876, read by the interpreter and use_item
const ALT_A := 8          # 0x80081878, read by player_walk
const ALT_B := 9          # 0x8008187a
const ALT_C := 10         # 0x8008187c
const ALT_D := 11         # 0x8008187e
const MAP := 12           # 0x80081880, never written by the options screen
const PAUSE := 13         # 0x80081882, never written either

# 0x8001f4c0, the seven movement schemes, in the order the code writes them:
# forward, back, the two lateral slots, then the four shoulder slots.
# Types A, B, C and G turn with the D-pad; D, E and F turn with the shoulders
# and walk sideways with the D-pad.
#
# **The last slot was 0 in six of the seven**, and the four action schemes
# below were wrong in three: both were read without the delay slots, and every
# arm of 0x8001f4c0 stores its last value from the `ori` in the delay slot of
# its jump. Replayed off the listing with the delay slots, scheme A is exactly
# what the game's own slots held in the session emu/bp16.lua logged on
# 2026-09-25 -- forward UP, back DOWN, LEFT/RIGHT, then L1, L2, R1, R2.
const MOVE_PRESETS := [
	[UP, DOWN, LEFT, RIGHT, L1, L2, R1, R2],      # A
	[UP, DOWN, LEFT, RIGHT, R1, L1, R2, L2],      # B
	[UP, DOWN, LEFT, RIGHT, L1, R1, L2, R2],      # C
	[UP, DOWN, L1, R1, LEFT, L2, RIGHT, R2],      # D
	[UP, DOWN, R1, R2, LEFT, L1, RIGHT, L2],      # E
	[UP, DOWN, L1, L2, LEFT, R1, RIGHT, R2],      # F
	[UP, DOWN, LEFT, RIGHT, L2, R1, R2, L1],      # G
]

# The same routine's four action schemes, read with the delay slots: attack,
# the menu (slot 5), action and use. Scheme 3 is the one the logged session
# used -- attack SQUARE, menu CIRCLE, action TRIANGLE, use CROSS -- and all four
# of its slots agree with what the game held.
const ACTION_PRESETS := [
	{ATTACK: TRIANGLE, MENU_SLOT: CROSS, ACTION: SQUARE, USE: CIRCLE},
	{ATTACK: SQUARE, MENU_SLOT: CROSS, ACTION: TRIANGLE, USE: CIRCLE},
	{ATTACK: TRIANGLE, MENU_SLOT: CIRCLE, ACTION: SQUARE, USE: CROSS},
	{ATTACK: SQUARE, MENU_SLOT: CIRCLE, ACTION: TRIANGLE, USE: CROSS},
]

# The schemes the port starts with. The game's own default is A and 0, when a
# save has not chosen; the port is played beside a save that chose A and 3, so
# it starts with those, and the same keys do the same things in both windows.
const START_MOVE := 0
const START_ACTION := 3

static var binding := PackedInt32Array()
static var move_type := START_MOVE      # 0x801b25e3, BUTTON CONFIG's movement scheme
static var action_type := START_ACTION  # 0x801b25e2, its action scheme
# the menus' confirm and cancel, as apply_control_scheme leaves them: the
# masks (gp+0x38, +0x3c) and the buttons' icons (+0x40, +0x44)
static var menu_buttons := [0x40, 0x20, 3, 1]
static var now := 0
static var prev := 0

# The emulator can drive this instead of the keyboard. `emu/bp16.lua` writes the
# game's own decoded button word -- 0x801b265c, the same word player_controller
# reads -- into live.txt once per game frame, and godot/ghost.gd feeds it here.
# Then one pair of hands playing in the emulator window drives both the game and
# the port, which is the only direction that works: nothing here can press a
# button in the emulator.
static var live_word := 0
static var from_emulator := false

# What a keyboard stands in for: **the emulator's own keys**, so the same hands
# play both windows. These are PCSX-Redux's pad 1 keys as emu/pcsx.json has
# them -- Keyboard_PadCross 88 is X, PadSquare 90 Z, PadCircle 68 D,
# PadTriangle 83 S, PadL1 81 Q, PadR1 82 R, PadL2 65 A, PadR2 70 F, Select
# Backspace, Start Enter, the D-pad the arrows. A real gamepad is read as well,
# below. The port's own debugging keys stay off every one of these.
const KEYS := {
	UP: [KEY_UP], DOWN: [KEY_DOWN], LEFT: [KEY_LEFT], RIGHT: [KEY_RIGHT],
	TRIANGLE: [KEY_S], CIRCLE: [KEY_D], CROSS: [KEY_X], SQUARE: [KEY_Z],
	L1: [KEY_Q], R1: [KEY_R], L2: [KEY_A], R2: [KEY_F],
	SELECT: [KEY_BACKSPACE], START: [KEY_ENTER],
}
const PADS := {
	UP: JOY_BUTTON_DPAD_UP, DOWN: JOY_BUTTON_DPAD_DOWN,
	LEFT: JOY_BUTTON_DPAD_LEFT, RIGHT: JOY_BUTTON_DPAD_RIGHT,
	TRIANGLE: JOY_BUTTON_Y, CIRCLE: JOY_BUTTON_B,
	CROSS: JOY_BUTTON_A, SQUARE: JOY_BUTTON_X,
	L1: JOY_BUTTON_LEFT_SHOULDER, R1: JOY_BUTTON_RIGHT_SHOULDER,
	SELECT: JOY_BUTTON_BACK, START: JOY_BUTTON_START,
}


# 0x8001f4c0, the schemes into the slots. See START_MOVE for what the port
# starts with.
# @orig game:0x8001f4c0 apply_control_scheme  status:verified -- 28 of 28 schemes fill the fourteen slots and the menus' four words (gp+0x38..0x44) as the game's own run over menu1 does (the self-test, from tools/ui.py export_cases)
static func apply(move := START_MOVE, action := START_ACTION) -> void:
	move_type = move
	action_type = action
	binding = PackedInt32Array()
	binding.resize(14)
	var m: Array = MOVE_PRESETS[clampi(move_type, 0, MOVE_PRESETS.size() - 1)]
	binding[FORWARD] = m[0]
	binding[BACK] = m[1]
	binding[LEFT_SLOT] = m[2]
	binding[RIGHT_SLOT] = m[3]
	binding[ALT_A] = m[4]
	binding[ALT_B] = m[5]
	binding[ALT_C] = m[6]
	binding[ALT_D] = m[7]
	for slot in ACTION_PRESETS[clampi(action_type, 0, ACTION_PRESETS.size() - 1)]:
		binding[slot] = ACTION_PRESETS[action_type][slot]
	binding[MAP] = SELECT
	binding[PAUSE] = START
	# 0x8001f858: action schemes 0 and 1 confirm with CIRCLE and cancel with
	# CROSS, 2 and 3 the other way round
	menu_buttons = [0x20, 0x40, 1, 3] if action_type < 2 else [0x40, 0x20, 3, 1]


# PadRead: one word, a set bit meaning pressed.
# @port engine -- the keyboard, a joypad or the emulator's word, in PadRead's layout (0x800785ac)
static func read() -> int:
	if from_emulator:
		return live_word
	var w := 0
	for bit in KEYS:
		for k in KEYS[bit]:
			if Input.is_key_pressed(k):
				w |= bit
				break
	for bit in PADS:
		if Input.is_joy_button_pressed(0, PADS[bit]):
			w |= bit
	var ax := Input.get_joy_axis(0, JOY_AXIS_LEFT_X)
	var ay := Input.get_joy_axis(0, JOY_AXIS_LEFT_Y)
	if ax < -0.4: w |= LEFT
	if ax > 0.4: w |= RIGHT
	if ay < -0.4: w |= UP
	if ay > 0.4: w |= DOWN
	return w


# player_controller stores this frame's word at 0x801b265c and, at the end of
# the frame, last frame's at 0x801b265e. Call once a frame, before asking
# anything else.
# @orig game:0x80031120 player_controller+0x154  status:transcribed -- PadRead into buttons (0x801b265c)
# @orig game:0x80031e84 player_controller+0xeb8  status:transcribed -- buttons into buttons_prev (0x801b265e), at the frame's end
static func poll() -> void:
	prev = now
	now = read()


# @port helper -- the test every reader of a slot makes inline: this frame's word & the slot
static func held(slot: int) -> bool:
	if binding.is_empty():
		apply()
	return (now & binding[slot]) != 0


# The shape every menu in the game uses: set now, clear last frame.
# @port helper -- that test, made inline by every menu, on a slot
static func hit(slot: int) -> bool:
	if binding.is_empty():
		apply()
	var m: int = binding[slot]
	return (now & m) != 0 and (prev & m) == 0


# @port helper -- the same test on buttons rather than a slot
static func hit_mask(mask: int) -> bool:
	return (now & mask) != 0 and (prev & mask) == 0


# Every button in a word, named. For a readout that has to be glanced at.
# @port check -- the readout's names
static func names_of(word: int) -> String:
	var out := PackedStringArray()
	for m in [UP, DOWN, LEFT, RIGHT, TRIANGLE, CIRCLE, CROSS, SQUARE,
			L1, L2, R1, R2, SELECT, START]:
		if word & m:
			out.append(name_of(m))
	return " ".join(out) if out.size() else "-"


# A slot's button and the key that presses it, for the HUD: "CROSS [X]".
# @port check -- the readout's key hint
static func slot_key(slot: int) -> String:
	if binding.is_empty():
		apply()
	var m: int = binding[slot]
	var keys: Array = KEYS.get(m, [])
	return "%s [%s]" % [name_of(m), OS.get_keycode_string(keys[0]) if keys else "-"]


# @port check -- one button's name
static func name_of(mask: int) -> String:
	match mask:
		UP: return "UP"
		DOWN: return "DOWN"
		LEFT: return "LEFT"
		RIGHT: return "RIGHT"
		TRIANGLE: return "TRIANGLE"
		CIRCLE: return "CIRCLE"
		CROSS: return "CROSS"
		SQUARE: return "SQUARE"
		L1: return "L1"
		L2: return "L2"
		R1: return "R1"
		R2: return "R2"
		SELECT: return "SELECT"
		START: return "START"
	return "-"

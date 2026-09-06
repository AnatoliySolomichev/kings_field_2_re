class_name KFPad
# The controller, as the game reads it.
#
# `PadRead` is the Sony library's, at 0x800785ac in GAME.EXE and 0x8001f9f0 in
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
# forward, back, the two lateral slots, then the three shoulder slots.
# Types A, B, C and G turn with the D-pad; D, E and F turn with the shoulders
# and walk sideways with the D-pad.
const MOVE_PRESETS := [
	[UP, DOWN, LEFT, RIGHT, L1, L2, R1, 0],       # A
	[UP, DOWN, LEFT, RIGHT, R1, L1, R2, 0],       # B
	[UP, DOWN, LEFT, RIGHT, L1, R1, L2, 0],       # C
	[UP, DOWN, L1, R1, LEFT, L2, RIGHT, 0],       # D
	[UP, DOWN, R1, R2, LEFT, L1, RIGHT, 0],       # E
	[UP, DOWN, L1, L2, LEFT, R1, RIGHT, 0],       # F
	[UP, DOWN, LEFT, RIGHT, L2, R1, R2, L1],      # G
]

# The same routine's four action schemes: attack, action and use. The third
# writes only the attack slot, and the fourth writes the menu slot as well.
const ACTION_PRESETS := [
	{ATTACK: SQUARE, ACTION: SQUARE, USE: CIRCLE},
	{ATTACK: CROSS, ACTION: TRIANGLE, USE: CIRCLE},
	{ATTACK: CROSS},
	{ATTACK: SQUARE, ACTION: TRIANGLE, USE: CROSS, MENU_SLOT: CIRCLE},
]

static var binding := PackedInt32Array()
static var now := 0
static var prev := 0

# What a keyboard stands in for. The port has no PlayStation pad, so each bit
# gets a key; a real gamepad is read as well, below.
const KEYS := {
	UP: [KEY_UP, KEY_W], DOWN: [KEY_DOWN, KEY_S],
	LEFT: [KEY_LEFT], RIGHT: [KEY_RIGHT],
	TRIANGLE: [KEY_I], CIRCLE: [KEY_L], CROSS: [KEY_K], SQUARE: [KEY_J],
	L1: [KEY_A], R1: [KEY_D], L2: [KEY_Q], R2: [KEY_E],
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


# 0x8001f4c0. The defaults are scheme A and scheme 0, which is what the game
# starts with when a save has not chosen otherwise.
static func apply(move_type := 0, action_type := 0) -> void:
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


# PadRead: one word, a set bit meaning pressed.
static func read() -> int:
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
static func poll() -> void:
	prev = now
	now = read()


static func held(slot: int) -> bool:
	if binding.is_empty():
		apply()
	return (now & binding[slot]) != 0


# The shape every menu in the game uses: set now, clear last frame.
static func hit(slot: int) -> bool:
	if binding.is_empty():
		apply()
	var m: int = binding[slot]
	return (now & m) != 0 and (prev & m) == 0


static func hit_mask(mask: int) -> bool:
	return (now & mask) != 0 and (prev & mask) == 0


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

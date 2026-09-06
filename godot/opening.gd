extends Node2D
# OPEN.EXE: the logos, the attract movies, the title screen and its menu.
#
# `open_main` at 0x80011e14 is the whole overlay -- 1464 bytes of one function
# that the entry point jumps to after setting $gp. What it does, in its order:
#
#   heap_init(0x80100000, 0xf8000); CdInit(); PadInit(0); card_init()
#   init_sound(); init_graphics()                    two 640x240 draw buffers
#   if (*overlay_arg != 1) {                         not just back from a game
#       if (play_movie(3) != 1)                      L0.S, the ASCII logo
#           play_movie(seen ? 1 : 0)                 M0.S / M1.S, the attract
#   }
#   load_opening_data()                              OP.D, once
#   card_start(); spu_master_volume(0x7f, 0x7f); play_title_music()   M2.S
#   fade the title in, any button skipping it
#   for (;;) {                                       the title screen
#       layer_a(1); layer_b(1);
#       if (title_menu(&choice, saves) == 1) break;  a confirm button
#       if (++frames >= 0x178) { play_movie(4); go round the attract again; }
#       layer_c(choice);
#   }
#   *overlay_arg2 = choice
#   if (choice == 0) play_movie(2)                   M3.S, the opening story
#   *next_exe = 1                                    GAME.EXE next
#   draw "Program Loading", card_stop(), PadStop(), ResetGraph(1), return
#
# Every rectangle below is the one in OPEN.EXE, on its own 640x240 screen; the
# layout came out of the POLY_FT4s the three layer routines fill in.
#
# The movies really play. `tools/opening.py video` turns each of the five
# `play_movie` names, and the title screen's music stream, into Ogg Theora that
# a VideoStreamPlayer can take -- 15 frames a second and 37800 Hz stereo, both
# off the stream itself. If those files are missing the state machine still
# runs and shows one decoded frame instead, which is what it did before.

var shell: Node

enum {LOGO, ATTRACT, FADEIN, TITLE, CHOSEN, STORY, LOADING, DONE}

const TIMEOUT := 376              # 0x178, what open_main counts the title to
const FADE := 60                  # the port's; the game's fade is layer_a's own
const STILL_FRAMES := 210         # only used when a movie could not be
                                  # transcoded and a still stands in for it

var state := LOGO
var frames := 0
var movie := 3                    # play_movie(3): L0.S, the ASCII logo
var seen_attract := false         # open_main's $s4
var choice := 0                   # the byte that ends up in overlay_arg2
var saves := 0                    # card_list_saves' count; nothing to load here
var art: Texture2D
var kings: Texture2D
var field: Texture2D
var text: Texture2D
var loading: Texture2D
var stills := {}
var hud: Label
var video: VideoStreamPlayer
var music: AudioStreamPlayer
var playing := false


func _ready() -> void:
	art = _tex("opd0")
	kings = _tex("opd1")
	field = _tex("opd2")
	text = _tex("opd3")
	loading = _tex("opd4")
	for i in range(5):
		stills[i] = _tex("movie%d" % i)
	video = VideoStreamPlayer.new()
	video.position = Vector2(0, 0)
	video.size = Vector2(640, 240)
	video.expand = true
	video.visible = false
	add_child(video)
	music = AudioStreamPlayer.new()
	var m := "res://opening/title_music.ogg"
	if ResourceLoader.exists(m):
		music.stream = load(m)
		if music.stream is AudioStreamOggVorbis:
			music.stream.loop = true
	add_child(music)
	hud = Label.new()
	hud.position = Vector2(6, 222)
	hud.scale = Vector2(1, 0.5)                 # the screen is squashed; undo it
	hud.add_theme_font_size_override("font_size", 12)
	add_child(hud)
	# open_main only shows the logos when it was not just handed back the
	# machine by GAME.EXE.
	if _arg() == 1:
		state = FADEIN
		frames = 0
		_start_title_music()
	else:
		_start_movie(3)               # play_movie(3): L0.S, the ASCII logo
	set_process(true)


# The byte at 0x800102f8. GAME.EXE leaves 1 in it when it hands the machine
# back, and open_main takes that as "you have seen the logos".
func _arg() -> int:
	return shell.overlay_arg if shell else 0


func _tex(name: String) -> Texture2D:
	var p := "res://opening/%s.png" % name
	return load(p) if ResourceLoader.exists(p) else null


# One frame of open_main. The game's loop is a frame of its own, so this counts
# them at 60 a second rather than working in seconds.
var acc := 0.0

func _process(dt: float) -> void:
	acc = minf(acc + dt, 0.25)
	while acc >= 1.0 / 60.0:
		acc -= 1.0 / 60.0
		KFPad.poll()
		_tick()
	queue_redraw()


func _tick() -> void:
	frames += 1
	match state:
		LOGO, ATTRACT, STORY:
			_movie_tick()
		FADEIN:
			# The first title loop: the three layers fade in and any button at
			# all cuts it short (0x80011fbc, PadRead then bnez).
			if frames >= FADE or KFPad.now != 0:
				state = TITLE
				frames = 0
		TITLE:
			_title_tick()
		CHOSEN:
			# 0x800123cc: the picked entry blinks while the CD volume fades and
			# CdControl(CdlPause) stops the title music.
			if frames >= 45:
				if choice == 0:
					state = STORY
					_start_movie(2)              # M3.S, the opening story
				else:
					state = LOADING
					frames = 0
		LOADING:
			# open_main sets *next_exe = 1 before drawing this, then returns.
			if frames >= 90:
				state = DONE
				if shell:
					shell.next_exe = shell.GAME
					shell.overlay_arg = 0
					shell.overlay_returned()


# play_movie (0x800136d8): open the file, stream it, and watch the pad.
func _start_movie(idx: int) -> void:
	movie = idx
	frames = 0
	playing = false
	var p := "res://opening/movie%d.ogv" % idx
	if ResourceLoader.exists(p):
		video.stream = load(p)
		video.visible = true
		video.play()
		playing = true
	else:
		video.visible = false


func _start_title_music() -> void:
	# 0x8001273c: CdSearchFile on \OP\M2.S;1 and a seek to it. The file's
	# video track is 16x16 filler; the music is its XA audio.
	if music.stream and not music.playing:
		music.play()


# START returns 1 and skips the whole chain; any of the four face buttons
# returns 2 and skips this movie only.
func _movie_tick() -> void:
	var skipped_all := KFPad.hit_mask(KFPad.START)
	var skipped_one := KFPad.hit_mask(KFPad.TRIANGLE | KFPad.SQUARE
		| KFPad.CIRCLE | KFPad.CROSS)
	var ended := (frames > 8 and playing and not video.is_playing()) \
		or (not playing and frames >= STILL_FRAMES)
	if not (skipped_all or skipped_one or ended):
		return
	video.stop()
	video.visible = false
	playing = false
	frames = 0
	if state == STORY:
		state = LOADING
		return
	if skipped_all:
		state = FADEIN
		seen_attract = true
		_start_title_music()
		return
	if state == LOGO and movie == 3:
		# open_main falls straight from the ASCII logo into an attract movie.
		state = ATTRACT
		_start_movie(1 if seen_attract else 0)
		seen_attract = not seen_attract
		return
	state = FADEIN
	_start_title_music()


# The title screen's own loop, and title_menu (0x800131ac) inside it.
func _title_tick() -> void:
	# Confirm: CIRCLE, CROSS or START, each on the frame it goes down.
	if KFPad.hit_mask(KFPad.CIRCLE | KFPad.CROSS | KFPad.START):
		state = CHOSEN
		frames = 0
		# title_confirm_fade ends with CdControl(CdlPause), which stops the
		# streamed music.
		music.stop()
		if shell:
			shell.overlay_arg2 = choice
		return
	# Move: UP or DOWN, and only when there is a save to move to -- the game
	# passes the number of saves in as the second argument and does nothing
	# with the D-pad when it is zero.
	if saves > 0 and KFPad.hit_mask(KFPad.UP | KFPad.DOWN):
		choice = 0 if choice != 0 else 1
	if frames >= TIMEOUT:
		# 0x178 frames without a decision: play_movie(4), the FromSoftware
		# logo, and then round to the attract movie again.
		state = LOGO
		music.stop()
		_start_movie(4)                          # L1.S, the FromSoftware logo


func _draw() -> void:
	draw_rect(Rect2(0, 0, 640, 240), Color.BLACK)
	match state:
		LOGO, ATTRACT, STORY:
			_draw_still()
		FADEIN, TITLE, CHOSEN:
			_draw_title()
		LOADING:
			_draw_loading()
	hud.text = _caption()


func _draw_still() -> void:
	if playing:
		return                      # the VideoStreamPlayer is drawing it
	var t: Texture2D = stills.get(movie)
	if t:
		# The movies run on a 320-wide screen where the title runs on a
		# 640-wide one, so a movie pixel is two of these.
		draw_texture_rect(t, Rect2(0, (240 - t.get_height()) * 0.5,
			640, t.get_height()), false)


# layer_a (0x8001279c), layer_b (0x80012b0c) and layer_c (0x80012ea0), with the
# rectangles they write into their primitives.
func _draw_title() -> void:
	if art:
		draw_texture_rect(art, Rect2(0, 0, 640, 240), false)          # full screen
	if kings:
		draw_texture_rect(kings, Rect2(64, 44, 256, 89), false)       # x 0x40..0x140
	if field:
		draw_texture_rect(field, Rect2(320, 128, 256, 89), false)     # x ..0x240
	if text == null:
		return
	# Both entries come out of the same 256x56 image: NEW is u 0..96 of the row
	# at v 16, CONTINUE is u 96..192 of the same row, and each lands in a 96x8
	# rectangle at x 0x110..0x170.
	var lit := Color(1, 1, 1)
	var dim := Color(0.45, 0.45, 0.5)
	draw_texture_rect_region(text, Rect2(272, 190, 96, 8), Rect2(0, 16, 96, 8),
		lit if choice == 0 else dim)
	# CONTINUE is drawn darker when there is nothing to continue. That is not
	# decoration: title_menu takes the number of saves as its second argument
	# and does nothing at all with UP or DOWN when it is zero, so with no
	# memory card image the cursor cannot leave NEW -- in the game as here.
	var cont := dim if saves == 0 else (lit if choice == 1 else dim)
	draw_texture_rect_region(text, Rect2(272, 202, 96, 8), Rect2(96, 16, 96, 8),
		cont)
	# The two copyright lines layer_b draws, from the same image.
	draw_texture_rect_region(text, Rect2(124, 154, 255, 12), Rect2(0, 0, 255, 12))
	draw_texture_rect_region(text, Rect2(124, 172, 255, 12), Rect2(0, 24, 255, 12))
	if state == CHOSEN and (frames / 6) % 2 == 0:
		draw_rect(Rect2(268, 188 + choice * 12, 104, 12), Color(1, 1, 1, 0.25))


func _draw_loading() -> void:
	if loading:
		draw_texture_rect(loading, Rect2(240, 48, 160, 144), false)


func _caption() -> String:
	match state:
		LOGO, ATTRACT, STORY:
			var what := {0: "M0.S, the attract movie", 1: "M1.S, the attract movie",
				2: "M3.S, the opening story", 3: "L0.S, the ASCII logo",
				4: "L1.S, the FromSoftware logo"}
			return ("play_movie(%d): %s   —   START skips everything, " +
				"a face button skips this one") % [movie, what.get(movie, "?")]
		FADEIN:
			return "the title fading in — any button cuts it short"
		TITLE:
			var how := ("UP/DOWN chooses, " if saves > 0
				else "no save on the card, so UP/DOWN does nothing — ")
			return (how + "CIRCLE, CROSS or START confirms — %d frames of " +
				"the %d left before the attract movies") \
				% [TIMEOUT - frames, TIMEOUT]
		CHOSEN:
			return "chosen: %s" % ("NEW" if choice == 0 else "CONTINUE")
		LOADING:
			return "next_exe = 1: the shell loads GAME.EXE"
	return ""

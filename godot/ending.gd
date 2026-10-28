extends Node2D
# END.EXE: the ending, which is three movies and nothing else.
#
# GAME.EXE's game_main hands the machine here when the word at $gp+0x1e4 is
# 3 or 4, with overlay_arg 2 or 3. end_main plays \OP\M4.S and \OP\M5.S for
# overlay_arg 2, holds the last frame for sixty VSyncs, and then \OP\M6.S
# for anything -- and then stops the CD and loops on itself: the game does
# not go back to the title, the last frame of M6 stays until a reset. No
# button is read; the ending's movies cannot be skipped.
#
# Each plays until END.EXE's own count of its frames (3380, 942, 1841, at
# 0x80011000) or its stream ends; M4 is letterboxed, 320 by 176 at y 32, the
# others fill the 320 by 240 display. tools/ending.py is the same in Python,
# held to END.EXE's own code; ending.json and the movies come from it.
#
# @exe end

const HELD := 60                   # VSync(0) between M5 and M6: a second at 60 a second
const VSYNC_HZ := 60.0
const MOVIE_HZ := 15.0             # the streams' own rate

var shell                          # boot.gd, as opening.gd has it
var video: VideoStreamPlayer
var movies := []                   # ending.json: [{name, frames, letterbox}]
var steps := []                    # plan(overlay_arg), what is left of it
var clock := 0.0
var limit := 0.0                   # this movie's length by END.EXE's count, or the hold's
var holding := false
var done := false


# end_main's sequence for an overlay_arg: ["movie", i] and ["hold", vsyncs],
# in order; after the last, next_exe and overlay_arg 0 and the machine stops.
# @orig end:0x800119b8 end_main  status:verified -- tools/ending.py main_check, END.EXE's own from its entry, 12 of 12 overlay_args (the calls in order, the two bytes, the loop on itself); its set-up -- the heap, CdInit, end_graphics, the environments put -- is Godot's (the nodes in _ready), CdControl(8) and the stop are the movie left as it is
static func plan(arg: int) -> Array:
	var out := []
	if (arg & 0xFF) == 2:
		out.append(["movie", 0])
		out.append(["movie", 1])
		out.append(["hold", HELD])
	out.append(["movie", 2])
	return out


# end_movie_rect's picture: [y, height] on the 240-line display -- movie 0
# letterboxed, 176 lines from y 32, the others the whole 240.
# @orig end:0x80011f64 end_movie_rect  status:partial -- the picture's rectangle (tools/ending.py rect_check, 6 of 6 of the game's own); not the decoder's buffers and slices, which are Godot's
static func rect(i: int) -> Array:
	return [0, 0xF0] if i != 0 else [0x20, 0xB0]


# end_play_movie's loop: the frames it decodes before the counter, run up by
# `step` a frame, passes `count` or the loop has gone round more than it.
# @port helper -- tools/ending.py frames_decoded, which play_check holds to END.EXE's own loop
static func frames_decoded(count: int, step := 1) -> int:
	var counter := 0
	var n := 0
	while true:
		counter += step
		n += 1
		if count < counter or count < n:
			break
	return n


# end_entry: $gp and the jump to end_main; end_graphics: the display, 320 by
# 240 and cleared black -- here the shell's screen, a black field under the
# movie, and the movie's player.
# @orig end:0x80011d04 end_entry  status:verified -- the jump to end_main, run from in main_check
# @orig end:0x80011ae0 end_graphics  status:partial -- the black 320-by-240 display, in the shell's 640 by 240; not the environments' other fields or the double buffer, which are Godot's
func _ready() -> void:
	var black := ColorRect.new()
	black.color = Color.BLACK
	black.size = Vector2(640, 240)
	add_child(black)
	video = VideoStreamPlayer.new()
	video.expand = true
	video.visible = false
	add_child(video)
	movies = _movies()
	steps = plan(_arg())
	_next()
	set_process(true)


# @port data -- ending.json: the three movies' names, counts and letterboxes, off END.EXE
func _movies() -> Array:
	var p := "res://ending.json"
	if not FileAccess.file_exists(p):
		return []
	var d = JSON.parse_string(FileAccess.get_file_as_string(p))
	return d.get("movies", []) if typeof(d) == TYPE_DICTIONARY else []


# @port engine -- the shell's byte, as opening.gd reads it
func _arg() -> int:
	return int(shell.overlay_arg) if shell else 0


# end_play_movie(i): the movie's file, its rectangle, and its length by
# END.EXE's count -- or the stream's own end, if that comes first.
# @orig end:0x80011d14 end_play_movie  status:partial -- which file, its count of frames and its rectangle (tools/ending.py play_check, 9 of 9 of the game's own); the decoding is Godot's VideoStreamPlayer
func _start(i: int) -> void:
	var p := "res://opening/ending%d.ogv" % i
	var r := rect(i)
	video.position = Vector2(0, int(r[0]))
	video.size = Vector2(640, int(r[1]))
	var count: int = int(movies[i]["frames"]) if i < movies.size() else 0
	limit = float(frames_decoded(count)) / MOVIE_HZ
	clock = 0.0
	holding = false
	if ResourceLoader.exists(p):
		video.stream = load(p)
		video.paused = false
		video.visible = true
		video.play()
	else:
		limit = 0.0                    # no file: end_play_movie returns at once


# @port engine -- the next of end_main's steps, or the stop: next_exe and overlay_arg 0, the last frame left on the screen
func _next() -> void:
	if steps.is_empty():
		done = true
		if shell:
			shell.next_exe = shell.OPEN
			shell.overlay_arg = 0
		video.paused = true
		KFInfo.note("ending: over -- END.EXE stops here until a reset")
		return
	var s: Array = steps.pop_front()
	if str(s[0]) == "movie":
		_start(int(s[1]))
	else:
		holding = true
		clock = 0.0
		limit = float(int(s[1])) / VSYNC_HZ
		video.paused = true            # the last frame of M5, held


# @port engine -- the steps a frame at a time; no button is read
func _process(dt: float) -> void:
	if done:
		return
	clock += dt
	if clock >= limit or (not holding and not video.is_playing() and clock > 0.5):
		_next()

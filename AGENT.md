# Working on this project

You are continuing a reverse-engineering effort that turns King's Field II
(SLUS-00255) into something a modern engine can run. A lot is already decoded.
Your job is to keep going, mostly on your own, without breaking what works.

Read [FORMATS.md](FORMATS.md) for what is known, [BOOT.md](BOOT.md) for the
chain from the entry point through the logos, the title menu and the buttons,
[BACKLOG.md](BACKLOG.md) for what is not known, [TOOLS.md](TOOLS.md) for how to
run things, and `data/symbols.json` for every address that has a name and a
reason.

One thing to have in mind before reading any address: **the disc has four
executables and three of them load at `0x80011000`.** `data/symbols.json` is
`GAME.EXE`'s alone, and `OPEN.EXE`, `END.EXE` and the shell have their own
tables. Every tool takes the executable by nickname — `boot`, `open`, `game`,
`end`.

**Read those before touching anything.** Several hours were once lost to
re-deriving a fact that was already written down, and twice a tool's own
docstring turned out to be more current than the backlog entry describing it.

Four tools do most of the reading now, and reaching for them first saves the
afternoon: **`tools/rdis.py`** walks an executable from its entry point and
prints any routine annotated — names, resolved addresses, switch arms, what
each call is given, and where the port's copy lives; **`tools/consts.py`** says
what a number means and every other place it is used, including the ones the
compiler built out of shifts and adds; **`tools/portmap.py`** says which
function of the port is which code of the game, either way round, and what to
port next; and `out/rdis/game.json` is all of it as data, which
is how the last three findings here were made — by querying it rather than by
reading listings.

---

## What may be committed

**Everything committed here is published on GitHub**, history included. So
nothing that belongs to the game goes in, however it was obtained and however
far it has been transformed:

* the disc image, any of its four executables, or any file from `extract/`;
* anything decoded from them — images, models, sounds, movies, the game's
  text, level data, or any table of the game's bytes, the conversations'
  bytecode among them;
* long stretches of the game's code, whether as a listing, a hex dump or the C
  that `tools/pseudo.py` and `tools/decomp.py` make of it.

What goes in is this project's own work: the tools, the notes, the names and
the evidence for them, the port, and short quotations — a few instructions, a
few bytes, a line of text — where a finding cannot be followed without them.
Everything else the tools regenerate from the reader's own copy of the disc,
into `extract/` and `out/`, which `.gitignore` keeps out. **A tool that writes
anywhere else needs a `.gitignore` line before its output is committed.**
`godot/escript.json` and `godot/quest.json` — every conversation's bytecode and
every quest hook as C — went in unnoticed and had to be cut out of the whole
history before the first push.

Nor anything private: no keys, tokens or passwords, and nothing you would not
put on a public page under your own name.

If you are not sure something may be published, leave it out and ask.

---

## The method that got this far

This is the part worth copying. It is not a style preference; each rule is here
because breaking it produced a confident wrong answer.

**Make the game state the answer.** The wall decode was stuck for a long time
while it was scored against a hand-drawn map. It came apart in an afternoon once
`emu/bp13.lua` started logging the arguments going into `tile_collision` and the
mask coming out, because then a reimplementation either reproduced the game's
own answer or it did not. Prefer a breakpoint that captures *input and output*
over reading a value out of RAM: the struct at `0x801e6470` looks like it holds
the answer and does not, since ten call sites share it and every monster
overwrites it.

**Verify by reimplementation, not by inspection.** Write the model out in
Python, run it against the logged calls, and report the exact count. "Looks
right" is not a result; "4264 of 4264" is.

**A permissive metric will lie to you.** The withdrawn wall decode scored 90.6 %
on a per-edge test and overlapped the real geometry by 12 %. If a score is high
and the recall is poor, believe the recall.

**Write down the evidence, not the conclusion.** Every entry in
`data/symbols.json` carries *why*. Two findings were caught as wrong only
because the earlier note said how they had been established.

**Withdraw loudly.** When something turns out to be wrong, say so in the
document that carried it, and say what the mistake was. FORMATS.md has several
of these and they are the most useful paragraphs in it.

**Say which kind of thing each number is.** There are three, and they must never
be confused in prose or in code comments:

* *read off the code* — transcribed from the MIPS, e.g. the collision opcodes;
* *fitted* — chosen to match observation, e.g. `HOFF` was, until the real
  argument was captured;
* *guessed* — neither, e.g. the tick rate `godot/player.gd` runs the movement
  at, which no recording has settled.

A guess presented as a reading is the worst failure mode available here, and it
has happened.

---

## The port and the game, one to one

**Every function in `godot/` says what it is in the game, and the tools hold
it to that.** It is what lets a question about the port -- "why does the door
wait here?" -- go to the right instructions in one step, and a question about
the game -- "does the port do this?" -- be answered without reading the port.
It is a rule, not a convention: `tools/portmap.py --check` fails without it.

* **A function that reproduces code of the game** says so in the comment block
  directly above it, with no blank line between, one line for each piece of
  the game it reproduces:

  ```gdscript
  # @orig game:0x8004e928 actor_turn  status:transcribed
  # @orig game:0x8005205c actor_tick+0x1fb4  status:transcribed -- opcode 6's arm
  ```

  The executable (`boot`, `open`, `game`, `end`); the address -- a routine's
  first instruction, or where the stretch it reproduces starts inside one; the
  symbol table's name for that address, `routine+0xoff` inside a routine; and
  the status: `verified` with the count, `transcribed`, `partial` with what is
  missing, or `guessed`. A function that folds two routines into one carries
  two lines. Two functions that split one routine each point at their own
  stretch. Something the port does on its own inside such a function is said
  in the note.
* **A function with no counterpart in the game** says that, and which kind of
  the port's own code it is: `# @port engine -- why` (Godot's side: nodes,
  meshes, input, timing), `data` (reads what a tool wrote; the tool is where the
  game was read), `check` (self-test, comparison, debug views) or `helper`
  (arithmetic the CPU did unasked, small utilities). A file that is all of one
  kind -- the self-test, the side-by-side comparison, the viewer -- says it once
  in its header with `# @port-file check`.
* **Every address in a comment names its executable.** The file declares its
  own once in its header, `# @exe game`, and an address from another executable
  is written `open:0x80013a20`. Those plain addresses are citations, and the
  listings print them against the instruction.
* **The name in a marker is the symbol table's.** Rename a symbol and `--check`
  lists every marker still carrying the old name; fix them in the same commit.

To go between the two:

```
python3 tools/portmap.py godot/ai.gd:turn     the port's side: what in the game it is
python3 tools/portmap.py godot/ai.gd:213      the same, by line
python3 tools/portmap.py game:0x8004e928      the game's side: what copies it, and
                                              every line of the port that cites it
python3 tools/rdis.py game 0x8004e928         the listing: `; port:` for the routine,
                                              a line per stretch the port pins, and
                                              the port's citations at the instructions
```

and PORT.md is the whole table, regenerated by `tools/portmap.py --doc`.

**When a function changes, its marker changes with it.** An arm newly ported
is a new line, or a note that no longer says it is missing; a recording that
checks it moves `transcribed` to `verified` with the count. **When the game and
the port turn out to disagree, say so in the marker** -- `partial`, and what
differs -- and in BACKLOG.md, rather than leaving a `transcribed` that is no
longer true. The first full pass found a dozen such, from a dead copy of
`in_oriented_rect` with the wrong arithmetic to a `_tick` claiming a routine it
only called; BACKLOG.md, "The port against the game", has the ones still open.

A marker says the port reproduces that code. It does not say it reproduces it
correctly; that is what the recordings are for.

**How much of the game the port has is counted, every run.** `portmap.py`
(the summary, `--check`, `--doc`, `--progress`) prints a `progress:` line:
the share of each executable's own code -- below the first routine the Sony
library's own messages name (`tools/psyq.py`), the game's objects being linked
first -- that sits in routines whose start a marker claims, verified and
transcribed whole, **partial at half** (a convention: its note says what is
missing, not how much). The last figure is in `data/progress.json`, with a
line of history each time it moves; while the port is ahead of the record the
same commands print `progress changed since the record: ... -> ...`, and
`--doc` (which `build.py` runs) records it. **When a commit moves it, tell
the user the line -- was and now -- in the report** (in Russian), and commit
`data/progress.json` with the change.

---

## What counts as done

A change is finished when all of these hold:

1. The claim is verified against the game, with a number in the output.
2. `python3 tools/build.py --check` still reports every number below.
3. If it touches the Godot build, `python3 tools/level3d.py 0` ends with
   `godot loads the project cleanly`.
4. FORMATS.md, BOOT.md, BACKLOG.md, TOOLS.md and the symbol tables are updated
   to match, including anything now withdrawn.
5. `python3 tools/portmap.py --check` passes: every function in `godot/` is
   placed against the game, every marker names a real address by its real name
   and says how far it went, and every address in a comment has its executable
   ("The port and the game, one to one", above).

Do not report a step as complete without 1, 4 and 5.

### What is standing, as of the last run

```
the collision, against the game's own answers          8075 of 8078
the level table, against the snapshots                 13 of 13
the movement, against the watchpoint                   48 of 48, 15 of 15
the conversations, against what was played             44 of 44
the equipment tables, against a RAM snapshot           3264/3264, 2112/2112, 16/16;
                                                       player_recalc_stats 483 of
                                                       483 values over 21 snapshots
the conversation hooks, two readings of one table      23 of 23
how much of the game the port has (portmap progress)   46.8% of the game's own
                                                       code (game 47.2%, open
                                                       46.7%, end 0%; partial at
                                                       half, the library left out)
the port against the game, function by function        826 of 826 placed: 480
                                                       reproduce the game, 346 the
                                                       port's own; 546 markers and
                                                       1095 cited addresses, every
                                                       one resolving
the object loader, against 13 snapshots                angles 4344/4352, scale and
                                                       position 4352/4352, opcode
                                                       4226/4226, grid exact on 7
the lighting table, against every snapshot             89 856 of 89 856 bytes
the panel's sprite table, against every snapshot       520 of 520 fields
the compass's records, against every snapshot          105 of 105 fields
the swinging door, against the bp24 recording          226 of 226 steps
the lift doors, against the bp27 recording             3528 of 3528 steps; the doorway
                                                       answers, the player 1078 of
                                                       1078, the creatures 457 of 457
the chests' lids, against the snapshots                8 of 8 opened lids on the
                                                       lid's path, one moving
the conversations a USE at a time, bp21                4 of 4 recorded conversations;
                                                       21 of 21 calls op for op
the menus, against their snapshots' frames             16 of 16 frames primitive for
                                                       primitive: use item (scrolled
                                                       too), the main page with the
                                                       status page, the equipment
                                                       screen, its list and prompt
the MAGIC, BUTTON, USE MAGIC and storage lists,       160 of 160 frames; USE
against the game's own ui_panel (modes 4, 0x10, 2      MAGIC's list as the game's
and 7) over menu1                                      own menu_use_magic builds
                                                       it, 40 of 40
the storage, against the game's own menu_store and    200 of 200 runs of scripted
menu_take_out run whole over menu1                     pad words; 200 of 200 lists
BUTTON CONFIG, against the game's own options_screen   112 of 112 frames; 120 of
and menu_button_config over menu1                      120 runs of scripted words
OPTION 2, against the game's own sub_800252f4,         72 of 72 frames; 120 of 120
ui_display_values, menu_display and panel_colours      runs; 20 of 20 colour sets
OPTION 1, against the game's own sub_80024a78 and     48 of 48 frames; 160 of 160
menu_sound over menu1                                  runs
QUIT GAME, against the game's own over menu1           8 of 8 frames; 100 of 100 runs
the message box, against the game's own sub_8001eb3c  4 of 4 boxes
LOAD, against the game's own save_title_numbers and   33 of 33 titles; 40 of 40
ui_panel mode 8                                        frames
the shops, against the game's own ui_panel,            45 of 45 frames; 200 of 200
shop_buy and shop_sell over menu1                      runs, 5 of 5 aimed
the inn, against the game's own and the levels' own   4 of 4 frames; 100 of 100
night hooks run from their overlays                    runs; 24 of 24 heals
the guide, against the game's own sub_80024f88        12 of 12 pages and frames
the spells unlocked, against every snapshot            21 of 21
Silviera's key on a pedestal, silv1 and silv2          7 of 7
the drops, against the snapshots                       5 of 5 lying as the fall leaves
                                                       them (consistent, not a proof)
the creatures' behaviour tables, against snapshots     168 896 of 168 896 bytes,
                                                       69 of 69 awake actors
the creatures' machine, against the bp16 act= log      level 0: 261 of 261 runs,
                                                       12095 of 12098 frames with
                                                       every field logged; level
                                                       4: 221 of 221, 7200 of 7272
                                                       (before: 181 of 181 runs,
                                                       3939 of 3942 frames with
                                                       every field logged)
the spores, against the bp26 recording                 118 of 118 frames,
                                                       118 of 118 strikes
the effect machine, against the game's own             189 of 189 runs, 5144 of
effect_spawn and effect_driver over the snapshots      5144 frames all 128 slots,
                                                       4284 of 4284 strikes;
                                                       effect_aim 600 of 600
the walking, against the recording (replay rung 2)     124 891 of 125 116 frames;
                                                       447 of the 455 that touch
                                                       an object, 76 of 76 a
                                                       creature
the run (USE held), against bp16's speed caps          150 129 of 150 129 frames,
                                                       92 of them above 200
what a hit leaves, against the game's own              player_take_hit 840 of 840
player_take_hit and sub_80030e14 over the snapshots    hits; sub_80030e14 84 of 84
                                                       runs, 13 057 of 13 057
                                                       frames
the healing spells' effects, against the game's own     126 of 126 runs, 2698 of
effect_spawn and effect_driver                         2698 frames, slots, fields
                                                       and lighting
a creature's hit, against the game's own              1260 of 1260 hits, every
actor_take_hit                                         flag path, 200 actors
the fire ball end to end, the game's own collide,      84 of 84 runs, 988
actor_attack_player and actor_take_hit                 frames, 15 struck, 11 dead;
                                                       stone 63 of 63, wind
                                                       cutter 63 of 63; haze,
                                                       shudom, walwind, earth
                                                       wave, bortecth, meteor,
                                                       orladin, tornado, fire
                                                       wall, fire storm, flame,
                                                       flash, lightning (the
                                                       creatures' two too),
                                                       freeze and thedek 126 of
                                                       126 each;
                                                       every weapon's spell, 126
                                                       of 126 each (dark slayer's
                                                       also back at the player
                                                       and into the walls)
what a creature's volley throws, against the game's   2772 of 2772 volleys, every
own actor_animation_effects, and the kinds only        slot and creature; the
creatures throw, end to end                            twenty creatures' kinds,
                                                       the lob and the charge
                                                       among them, 63 of 63 each
the fire ball, against the game's own effect_spawn    168 of 168 runs, 914 of
and effect_driver (its world stood in for)             914 frames, queries, hits;
                                                       Seath's sword's 168 of 168
                                                       with its own collide_query
                                                       210 of 210, 2512 frames,
                                                       34 hits on a creature
the attacking arms, against the game's own             840 of 840 casts, every
player_action (aim, creature in sight, spawns)         spawn and argument
a thing used, against the game's own use_item over     2800 of 2800 runs: calls,
every level (tools/useitem.py)                         answer, pack, figures and
                                                       396 object records; the
                                                       truth glass's three pages,
                                                       the flask, every key; six
                                                       levels' own entry 2 run
the warp, against the game's own warp_to               280 of 280 runs, every
                                                       record, calls and fields
Orladin's seals and pedestals, against the game's      7600 of 7600 frames of the
own arms (tools/seals.py)                              seals, 3240 of 3240 of the
                                                       pedestals, every field
the screen's fade, against the game's own              840 of 840 quads, 40 of 40
screen_fade, screen_fade_draw and fade_frames          runs of fade_frames, the
(tools/fade.py)                                        texture in 19 of 19 VRAMs
casting, against the game's own cast_spell,            1260 of 1260 of each:
player_action, player_turn and the controller's end    casts, actions, pending,
                                                       timers, the USE stretch,
                                                       the square button's thing
the knock-back, against the bp16 recording             171 of 171 frames, 7 of 7
                                                       lengths, 6 of 6 landings
the creatures' HP, against 13 snapshots                69 of 69
the player's weapon, against the bp25 recording        817 of 817 frames,
                                                       11 of 11 blows
the weapons' own spells, against the game's own        200 of 200 of each;
swing_start, weapon_may_cast, spell_begin and          400 of 400 frames of
held_item_tick's window; player_turn's combination     each; the bows'
and held_item_tick's second swing; the bows' draws     draws 1688 of 1688
                                                       frames, all 128 slots
the creatures' fences, against the bp16 act= log       5006 of 5006 positions
the creatures' animation, against the actor caches     11 of 11
the level's record, against the game's own writer     84 of 84 streams, 71 718
and reader (level_state_write, apply_level_state)      bytes; 90 of 90 applied
the saves on the memory card, against the game's own   save_restore 534 566 of
save_restore and save_serialise                        534 566 bytes, 3 saves and
                                                       20 random buffers;
                                                       save_serialise 494 592 of
                                                       494 592 over 21 snapshots
the video memory, against every snapshot               2 994 944 of 2 998 544;
                                                       object pages 779 760 of
                                                       782 320 (the rest: the
                                                       water's scroll offset)
the pseudocode, against the instructions it is read    126 168 of 126 168 block runs
from (tools/pseudo.py --check)                         over the four executables,
                                                       three ways of folding
```

and in the Godot self-test:

```
movement 690 of 690 · steps 750 of 750 · creature steps 384 of 384
creature runs 480 of 480 twice
levels 40 of 40 · angles 400 of 400
conversations 43 of 43, and 25 of 25 steps the emulator recorded
damage 6 of 6 · knock-back 2484 of 2484 · weapon 12020 of 12020
fences 600 of 600 · animation 540 of 540
equipment 16 of 16 · menus 88 of 88, 256 of 256 storage, shop, inn,
BUTTON CONFIG, OPTION and QUIT runs, heals and panel colours, 28 of 28 control schemes as the game's
own apply_control_scheme
directions 400 of 400
routines 15363 of 15363
saves 45 of 45 · level states 46 of 46 streams, 958 of 958 things made,
42 of 42 states written, 46 of 46 tables read and written again
effects 1494 of 1494 runs, 27656 of 27656 frames · aims 300 of 300 · volleys 264 of 264
the run 150129 of 150129 frames
player_take_hit 300 of 300 · the status 40 of 40 runs, 6312 of 6312 frames
casting 1200 of 1200 · the attacking arms 240 of 240 · creature hits 400 of 400
use_item 552 of 552 · warp_to 55 of 55 · seals 975 of 975 · fades 117 of 117
```

**Tell the two kinds apart.** Against a recording or a RAM snapshot — the
conversations, the damage, the equipment, the collision, the movement — the
game is the answer. Between two of this project's own readings — the
directions, the levels, the angles, the 43-of-43 — the number says only that
two copies agree, and they have agreed about the wrong thing before: 1086 of
1086 entity scripts, for months, about bytes that were not scripts.

The exception worth keeping is the hooks: those two readings share nothing,
one scanning a routine's first instructions for a bound and a base and the
other running the whole overlay through the walker's switch resolver.

---

## Where a human is required

Stop and ask when you reach these. Do not simulate them.

**[PLAYTEST.md](PLAYTEST.md) is the list of what is waiting for a person** --
what to look at in the port and which emulator session to record, with the
cells and the buttons. Whenever a finding wants a recording or a look, add it
there (in Russian: it is written for the player-tester) as well as to BACKLOG.md,
and take it out once its number is in "What is standing".

* **Anything needing a controller.** Breakpoint scripts can be loaded into a
  running emulator with `dofile(...)` from its Lua console, but nobody can press
  a button from here. Say exactly where to walk and what to do, in cell
  coordinates — the Godot build shows the cell under the player.
* **Anything needing eyes on the game.** The level was exported mirrored left to
  right for a whole round trip. No map, no top-down render and no automated
  check can see that error: they are all symmetric under exactly that flip. A
  person who remembers the game caught it in one sentence. When a change affects
  how the world looks or moves, ask for a look, and ask a *specific* question —
  "rotated, small, crooked, floating or sunk" beats "does it look right".

---

## The queue

In order. Each has an acceptance test; do not move on without it.

**1. The vertical half of movement — done.** Two premises failed first, both
caught by recordings rather than by reading: `actor_move_horizontal` moves the
*monsters*, and `player_move` (`0x8002f320`) moves the player only when thrown.
Walking is **`player_vertical` (`0x8002ed60`)** for the height and `0x8002e3f8`
for the ground plane, and the height is a rate limiter with four fall states
rather than a physics model — FORMATS.md section 4 has it in full.

Verified: `python3 tools/movement.py bp15` reports **48 of 48** of the game's own
height stores chosen exactly and **15 of 15** falling frames advancing by exactly
the velocity. `godot/player.gd` carries the model and `godot/selftest.gd` proves
the GDScript copy matches the Python one on 690 frames.

The turn is read now too: `player_look` (`0x8002f5c0`) ramps a rate to a cap by
a quarter of it a frame and adds it to the facing, and the cap is `0x20` while
forward or back is held and `0x28` when neither is — you turn faster standing
still. `godot/player.gd` carries it; FORMATS.md, "The turn".

What is left of it, and neither blocks anything: **`0x8002e3f8` is not
transcribed** (the horizontal step is 201 units a frame at speed and ramps up
from a standstill -- *update*: its refusal and slides are in, below). **The frame rate is read**: `frame_limit` (`0x80019614`)
ends every pass of the loop by waiting for the fourth vertical blank, so the
game runs at 15 frames a second, and `godot/player.gd` does now -- it ran at a
guessed 30, twice the game's speed. `emu/bp16.lua` logs `vblank_count` as `vb=`
from now on, and `tools/replay.py` says from it how often a frame overruns.

**2. The collision opcodes never seen in a log — read, and two of the six are
in.** The switch at `0x800327e8` indexes `tile_op_table` at `opcode - 0x10`, so
the whole dispatch is readable without a log: 18 handlers, 31 empty arms, and
**no shape in the game uses an opcode without a handler**.

`0x25` is transcribed and in both copies: an L-shaped wall footprint, 207 uses
on all 28 levels, and level 0 goes from 1304 wall planes to 1345 — the 41 the
old note counted. 622 of 775 probe points inside its 31 cells change their mask.
`0x17`, `0x18` and `0x19` are in too: they are not walls but **planes that
throw the player into state `0x11` when the eye goes under them**, which is why
no recording ever hit one.

`tools/collision.py` still reproduces 8075 of 8078 logged calls, unchanged.

*What is left:* `0x31` (11 uses) and `0x35` (4 uses) are located but not
transcribed, and none of the six has been seen in a log yet — **that still
wants a person walking over one of those cells with `emu/bp13.lua` armed.**
`python3 tools/collision.py walls 0` lists where they are.

**3. Object scale — answered, and then the whole loader.** The triple is also a
size, `p[+0x10] << 5` on flag `0x10`, and `load_object_placement` is transcribed
in `tools/objload.py`: the angles, the scale, the draw rule and the doors in the
grid come off the disc for every level, and the snapshot is no longer consulted
for any of them. What follows is the first answer, kept for how it was reached.

**The first answer, in the negative, which opened something better.**
The triple at `+0x2c` is not a size. `object_set_present` (`0x80044b40`) writes
`0x1000` into all three when an object is present and `0` when it is not, so it
is a **visible / not visible switch**, and it reaches the renderer through
`ScaleMatrix` (`0x80074910`), which by `0x1000` applies exactly nothing. The 59
objects on level 0 at `x0.00` are switched off, not tiny.

So the half-size objects are **not a factor the game applies at draw time**: the
position at `+0x14..+0x1c` goes in unhalved and nothing else scales. What is
left to check is the model's own units and the port's placement.

The same routine writes a byte into the terrain cell as well, and the first
reading of *that* was wrong: it is the layer's `+0`, the tile index the drawing
uses, not the shape at `+3` the collision reads, and the restore byte comes
from the type row rather than from the placement record. **So an object's
collision is still not found** — withdrawn in full in FORMATS.md, "The scale
triple is a switch".

**4. The objects with no model — answered, and mostly on purpose.** Across the
game 707 of 4838 placed objects have no usable model, and `python3
tools/objops.py --types` accounts for 696: **578 are markers** whose type row
is empty past +3 and whose opcode is in the trigger range, 76 are type 299 (the
inscription volume), 42 carry a class that means never drawn, and one is past
the end of the type table. **Ten are left, all type 298.** Type 287, the one
this item named, is a marker with 136 instances across 13 levels.

The model *rule* is read too: `model_of_type`
(`0x80040568`) says it in eleven instructions: below type 300 the model is
`type + 0x100`, and **from 300 up it is `type + 0x100 + 32 * level`**. So
`MOF.T` is banked 32 models to a level, level *n* using bank *n + 4*, which
holds for all 1424 placed objects of type 300 and above across 25 levels.
`tools/tmd.py` ignored the level — right on level 0, wrong by 32 banks on level
1, and level 0 is the only one the port has ever built.

*What is left:* 33 of those 1424 still land on an empty `MOF.T` entry, and the
`MO.T` wrapper problem below type 300 is separate and still open.

**5. Enemies.** The 265 entity records are definitions — stats and kind, no
position. Nothing places them yet. Find what does before drawing anything.

**6. The boot chain — done, and it opened three new ones.** The shell, the
opening, the title menu and the whole input path are read and in
[BOOT.md](BOOT.md), with the port following them in `godot/boot.gd`,
`godot/opening.gd` and `godot/pad.gd`. What it left open is `END.EXE`, the
save-loading path on the `GAME.EXE` side (`0x8001fa60`), and sound.

**7. What to port next, and how to find it.** `python3 tools/portmap.py --next`
ranks every routine with no marker in the port by how many routines call it,
leaving out the Sony library and anything that talks to hardware — Godot is
what those were for. Read the candidate with `python3 tools/pseudo.py game
<address>` before opening the listing; it is usually enough on its own.

The systems still entirely unported, largest first: the creature AI
(`sub_800568bc`, 4584 instructions), the object opcode interpreter
(`sub_80047010`, 3965, with its own 236-arm switch), combat and the damage roll
(`0x8002ab18` and `sub_80029500`), the inventory and the menus (the cluster
around `0x80025468`, which now reads as screens because `ui_prim_begin`,
`ui_prim_quad` and `ui_prim_add` are named), the entity script interpreter
(`0x8005c308`, whose language `tools/escript.py` already decodes), save and
load (`save_serialise`, `save_restore`), and sound.

**None of those has a recording behind it.** The method this project runs on
wants one — so for each, the first move is an `emu/bp*.lua` that logs the
routine's arguments and its answer, and a person at the emulator playing for a
minute. Reading alone gets a transcription; it does not get a number.

**`emu/bp20.lua` is that instrument for five of them at once**, and one
session has already been run through it. `out/lua_bp20.log` is in the
repository's `out/`, which regenerates — so if it is gone, ask for another: the
session is a minute of ordinary play, opening a door, taking things out of
chests, picking up herbs, and dying once.

What that one session settled: **the damage formula**, reproduced on 6 of 6
recorded hits (`tools/damage.py`); **13 of the 44 object arms**, each on
exactly the opcode the table says; the item ids, which name themselves against
`tools/itemtext.py`; **the death branch** and the crystal that stops it; and
two corrections to readings made without it.

**`emu/bp21.lua` has been run, and it earned its keep on the first
conversation.** It logs every opcode `script_interpreter` runs, and what it
logged did not match what this project had read: the game fetched
`04 05 06 07 08 09 f0 01` where `tools/escript.py` had `02 00 ff`. The whole
"1086 scripts" corpus was blocks 1..15 of each entity record, which are not
scripts. There are 43 conversations. The recording is now the anchor — 44 of
44 steps and lines in Python over four conversations, 25 of 25 in the port — and it is the pattern to
repeat: **a check between two of my own readings is worth almost nothing.**

Still unrun on that script: `cast_spell` and `skill_unlock`, a conversation
with an `f1` guard or an `f9` taken, and one whose header `+0x12` is not
`0xff` so the shop or the inn opens.

What would also help, and needs no new script: `bp20.lua` again with the five
damage types it does not print added to the `HURT in` line.

**8. Swinging doors -- in the port, and checked.** `godot/doors.gd` runs
opcode 1's arm (FORMATS.md, "A door that swings"), and `tools/doors.py`, the
same arm in Python, steps 226 of 226 frames of the `emu/bp24.lua` recording --
two cycles of the door at (41,10), one of them waiting on a player in the
doorway -- to the game's state, counter, yaw and doorway shapes. The other
door classes are BACKLOG.md item 5c.

**9. Everything else in BACKLOG.md**, which is ordered roughly by what it
unblocks.

---

## Traps already paid for

Do not rediscover these.

* **Flipping one axis is a mirror.** PlayStation Y points down and +Z away;
  negate **both** and it is a half turn. Negating Y alone reflects the world.
* **`map_d` in an MTL is a transparency map**, not a texture. Pointed at a
  colour image it makes dark surfaces vanish, which reads as missing floors.
* **Vertex references differ between archives.** `RTMD.T` stores byte offsets,
  eight to a vertex; `MO.T` stores plain indices. Counting out-of-range
  references cannot tell them apart, because small indices read as offsets
  divide to zero — in range, and drawing nothing. Score by *usable* faces.
* **A routine that plainly writes the value is not necessarily the one that
  does.** `player_move` writes the player's Y, reads exactly like movement, and
  runs only when you are thrown. Two sessions went into it. When the question is
  "what does X", a **write watchpoint on X** answers it without having to pick a
  routine first; a breakpoint on a routine you chose can only confirm the choice.
  Arm the watchpoint, then read the code it names.
* **Never `return false` from a PCSX-Redux breakpoint callback.** It deletes the
  breakpoint, so it fires once and the silence afterwards means nothing. Arm a
  control breakpoint on something known to happen constantly, in the same run,
  before believing that anything did *not* happen.
* **`out/godot/` is generated and is also a live Godot project.** The editor
  writes into it. Edit scripts in `godot/`, never there — a rebuild overwrites
  it, and a stray keystroke into its script editor once put eighteen Cyrillic
  characters into the middle of `collision.gd` and broke the whole project.
* **A stale Godot import shows the old mesh and says nothing.** Godot keeps
  converted geometry in `.godot/imported/` and only refreshes it when the
  *editor* runs — playing the project does not. So a rebuilt `.gltf` beside an
  old cache renders as it did before, silently. This cost a whole round trip:
  two real bugs were found and fixed, the files were rewritten, and the player
  looked at meshes three quarters of an hour older than the files and reported
  no change. Always run `--import` after writing geometry; `tools/level3d.py`
  and `tools/gallery.py` now do it themselves.
* **Godot needs `--import` before the first run** after the cache is cleared,
  or `class_name` is unregistered and every script fails to parse. Verify
  headless: `godot-4 --headless --path out/godot --import` then `--quit-after 60`.
  There is no display here; headless is the only way you can check your own work,
  and `tools/level3d.py` now runs it for you.
* **An address without an executable is not a fact.** Three of the four
  programs on the disc load at `0x80011000`, so `0x80013a20` names one routine
  in `OPEN.EXE` and a different one in `GAME.EXE`. Say which.
* **The button bits are the PSY-Q layout, not the hardware's.** `PadRead`
  returns the two halves of the hardware word swapped, so `0x1000` is UP and
  not TRIANGLE. An entry in `symbols.json` carried the raw reading for a while
  and named the wrong physical button for every action in the game; BOOT.md
  section 6 has the four independent places that settle it.
* **`tools/rdis.py` resolves `lui` pairs, not `$gp`.** A store like
  `sh $v1, 0x1b8($gp)` carries no address in the listing, so a search for
  `[0x8009c3cc]` finds no writer of a table `player_turn` writes every frame.
  GP is `0x8009c214` in GAME.EXE; search `0x...($gp)` as well before calling
  anything unwritten.
* **capstone does not decode the GTE**, which is most of the renderer. Use
  `tools/fdis.py`, which names the coprocessor registers — `ctc2 $t5, L11L12`
  says "light matrix" where the raw form says nothing.

---

## How to leave the repo

Small, working commits. Tools take arguments and print what they found. Every
docstring says what the tool established and how, because that is the only place
a future reader will look. If you withdraw a claim, delete it from the document
that carried it and say why in its place.

The goal is not a finished game. It is that the next person — or the next
session — can tell exactly what is known, how it is known, and what to do next.

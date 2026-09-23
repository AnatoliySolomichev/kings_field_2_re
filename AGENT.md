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
compiler built out of shifts and adds; **`tools/portmap.py`** says what is
ported and what to do next; and `out/rdis/game.json` is all of it as data, which
is how the last three findings here were made — by querying it rather than by
reading listings.

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

## What counts as done

A change is finished when all of these hold:

1. The claim is verified against the game, with a number in the output.
2. `python3 tools/build.py --check` still reports every number below.
3. If it touches the Godot build, `python3 tools/level3d.py 0` ends with
   `godot loads the project cleanly`.
4. FORMATS.md, BOOT.md, BACKLOG.md, TOOLS.md and the symbol tables are updated
   to match, including anything now withdrawn.

Do not report a step as complete without 1 and 4.

### What is standing, as of the last run

```
the collision, against the game's own answers          8075 of 8078
the level table, against the snapshots                 13 of 13
the movement, against the watchpoint                   48 of 48, 15 of 15
the conversations, against what was played             44 of 44
the equipment tables, against a RAM snapshot           3264/3264, 2112/2112, 16/16
the conversation hooks, two readings of one table      23 of 23
the port's markers                                     56 in 13 files, all resolving
```

and in the Godot self-test:

```
movement 690 of 690 · levels 40 of 40 · angles 400 of 400
conversations 43 of 43, and 25 of 25 steps the emulator recorded
damage 6 of 6 · equipment 16 of 16 · directions 400 of 400
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
from a standstill), and **the frame rate is unknown** — a watchpoint log carries
no clock, so the port's 15 Hz is a guess. A timestamped recording settles it.

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

**3. Object scale — answered, in the negative, and it opened something better.**
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

**8. Everything else in BACKLOG.md**, which is ordered roughly by what it
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

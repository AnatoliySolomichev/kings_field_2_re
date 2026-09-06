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
2. `python3 tools/collision.py` still reports every logged call reproduced.
3. If it touches the Godot build, `python3 tools/level3d.py 0` ends with
   `godot loads the project cleanly`.
4. FORMATS.md, BOOT.md, BACKLOG.md, TOOLS.md and the symbol tables are updated
   to match, including anything now withdrawn.

Do not report a step as complete without 1 and 4.

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

What is left of it, and neither blocks anything: **`0x8002e3f8` is not
transcribed** (the horizontal step is 201 units a frame at speed and ramps up
from a standstill), and **the frame rate is unknown** — a watchpoint log carries
no clock, so the port's 15 Hz is a guess. A timestamped recording settles it.

**2. The three collision opcodes never seen in a log:** `0x25` (41 cells on
level 0), `0x18`, `0x31`. They are silently ignored, which is why some low walls
can be walked through. *Done when:* `tools/collision.py` still reproduces every
logged call and a walk over cells using them is logged and reproduced too.

**3. Object scale.** Placed objects come out about half the size they should be
— a door is 900 units tall where a cell is 2048 and a wall 2560. The models
carry `scale = 0`, and `load_object_placement` writes `0x1000` into the live
record, so the factor is neither of those. Find where it is applied. *Done
when:* the factor is read off the code, not fitted to look right.

**4. The 53 objects with no model**, `MO.T` type 287 among them (28 instances on
level 0). `tools/tmd.py` cannot find a TMD in those entries; their wrapper
differs. Chests (`MO.T` 106) are one of them and are visibly missing.

**5. Enemies.** The 265 entity records are definitions — stats and kind, no
position. Nothing places them yet. Find what does before drawing anything.

**6. The boot chain — done, and it opened three new ones.** The shell, the
opening, the title menu and the whole input path are read and in
[BOOT.md](BOOT.md), with the port following them in `godot/boot.gd`,
`godot/opening.gd` and `godot/pad.gd`. What it left open is `END.EXE`, the
save-loading path on the `GAME.EXE` side (`0x8001fa60`), and sound.

**7. Everything else in BACKLOG.md**, which is ordered roughly by what it
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

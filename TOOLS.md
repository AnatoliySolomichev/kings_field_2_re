# The tools

Everything here runs from the project root, as `python3 tools/<name>.py`. The
findings they produced are in [FORMATS.md](FORMATS.md); what is still open is in
[BACKLOG.md](BACKLOG.md); names for the addresses are in `data/symbols.json`;
how to work on this without repeating its mistakes is in [AGENT.md](AGENT.md).

Two things they need, neither of which is in the repository:

* **`extract/`** — the disc, unpacked. Everything that reads the game's data
  starts there.
* **`out/`** — where derived files go: RAM snapshots, decoded text, rendered
  maps, caches. All of it regenerates.

Anything marked **live** needs the emulator running; everything else works from
the disc alone.

---

## Start here

| Want to | Run |
| --- | --- |
| See what an address is | `tools/syms.py 0x8005d7bc` |
| Read what a sign in the world says | `tools/readables.py` |
| Read a level's entity scripts | `tools/escript.py 0` |
| See who wants which item | `tools/overlay.py` |
| Check an archive is intact | `tools/tsum.py extract/CD/COM/*.T` |
| Watch the game while you play | `emu/run.sh` then `tools/livemap.py` |
| Follow the boot chain from the entry point | `tools/rdis.py open --tree entry -d 3` |
| Read a routine, annotated | `tools/rdis.py game 0x8002ed60` |
| Find out what a number means | `tools/consts.py 0x800` |
| See what the opening plays | `tools/str.py list` |

---

## Naming things

**`syms.py`** — the address book. `data/symbols.json` holds a name, a kind and
*the evidence* for every address we have pinned down, and this reads it.

```
python3 tools/syms.py                  every name we have
python3 tools/syms.py 0x8005d7bc       one address, with why we believe it
python3 tools/syms.py open 0x80011e14  the same, in OPEN.EXE's own table
some_command | python3 tools/syms.py - annotate any output that contains addresses
```

There are four tables, because three of the executables load at `0x80011000`
and an address is meaningless without saying which one: `data/symbols.json` is
`GAME.EXE`'s and is what a bare address means, and `symbols_open.json`,
`symbols_boot.json` and `symbols_end.json` are the others.

It will say `use_item+0x8c8` for an address inside a routine whose size we
recorded, and plain hex otherwise — deliberately, because guessing "nearest
name above" once labelled two unrelated functions as offsets into their
neighbours, and that reads as a fact.

## The disc

**`psxiso.py`** — the ISO. Lists and extracts.

**`tarc.py`** — the `.T` archives: `python3 tools/tarc.py extract/CD/COM/*.T`
prints entry counts and checks each file's offset table adds up.

**`tsum.py`** — the checksum on every entry inside a `.T`. Matters because the
game refuses an entry whose checksum is wrong, which is what makes editing text
freeze it. `stamp()` recomputes the word after an edit.

```
python3 tools/tsum.py extract/CD/COM/*.T
```

**`tim.py`** — PlayStation TIM images, in and out.

## Text

No string in this game is ASCII; it is all pre-rendered images.

**`dump_text.py`**, **`ocr.py`** — the fixed-grid dialogue face. **`propfont.py`**
and **`propocr.py`** — the proportional face used on signs and item names.
**`glyphs.py`**, **`textgrid.py`**, **`align.py`**, **`cluster.py`**, **`round2.py`**
are the steps that built and grew the glyph templates.

The result lands in `out/text.pkl`, which most other tools read to put English
words beside what they find.

**`build_atlas.py`** — every decoded image on one browsable page.

## Levels

**`maps.py`** — the 80×80 grids out of `FDAT.T`, and a renderer for all 28.

**`level_map.py`** — one level in detail.

**`build_levelmap.py`** — a level with its objects as a standalone HTML page.

**`mapcheck.py`** — scores a guess about where the walls are against the game's
*own* map, `ITEM.T` 721, 160×160 for the 80×80 grid.

Use `agreement()`, not `score()`. The per-edge score counts a hit when ink falls
anywhere in the two-pixel band along an edge, which on this map is nearly always
— a wrong wall decode scored 90.6 % that way and overlapped the real ink by 12 %.
`agreement()` rasterises the prediction at the map's own scale and compares pixel
for pixel.

```
python3 tools/mapcheck.py
```

## Objects and entities

**`objects.py`** — the object table out of a RAM snapshot, with each object's
type, cell, class and gold.

```
python3 tools/objects.py b          # out/snap/b.ram
```

**`tiles.py`** — the tile shapes, the little programs that carry a level's
geometry. `tiles.py 0 37` disassembles one. The format is decoded; which
instruction draws a wall is not — the first answer agreed with the game's own
map on 12 % of its ink.

**`allmaps.py`** — every level drawn with its walls and every object on it, into
`out/maps/all/` with an index page.

**`placement.py`** — where every object on every level stands, from the disc.
No emulator: the placement is a block in `FDAT.T` entry `3n + 1`, 350 records of
24 bytes.

```
python3 tools/placement.py          # all 28 levels, counted
python3 tools/placement.py 0        # one level, every object
```

**`actors.py`** — every creature on every level, from the disc, and the game's
rule for when each one is drawn. The table is link 1 of the same `FDAT.T` entry,
200 records of 16 bytes; the rule is `0x8004c1f0` transcribed, with the death
rule beside it. `--check` holds the table against a RAM snapshot (58 of 58 on
level 0) and `--at` shows what arriving somewhere wakes. `godot/actors.gd` is
the same machine in the port.

```
python3 tools/actors.py 0              # one level's table
python3 tools/actors.py 0 --check      # against out/snap/b.ram
python3 tools/actors.py 0 --at 62 8    # arriving in cell (62,8)
python3 tools/actors.py --all          # every level, by category
```

**`readables.py`** — every object you can read, and what it says. This is the
one that turns the world into text: signs, graves, plaques, with their cells.

```
python3 tools/readables.py          # all 76 signs in the game, from the disc
python3 tools/readables.py b        # from a snapshot, showing what has changed
```

**`entities.py`** — the entities placed on a level and how many scripts each
owns.

```
python3 tools/entities.py           # every level, one line each
python3 tools/entities.py 0         # level 0 in full
```

**`escript.py`** — the entity script language, decoded.

```
python3 tools/escript.py            # the opcode table, then a summary
python3 tools/escript.py 0          # level 0, every script
python3 tools/escript.py flags      # which flag is set where and tested where
```

To dump the whole game at once:

```
for lv in $(seq 0 27); do python3 tools/escript.py $lv; done > out/scripts.txt
```

**`items.py`** — where the game decides what an item does: the three inventory
routines, every call site, and the hardcoded use-item pairs.

**`overlay.py`** — the code each level ships with it, in `FDAT.T` entry
`3n + 2`. This is where the quest conditions live: what a level requires, takes
and gives.

```
python3 tools/overlay.py            every level, in one table
python3 tools/overlay.py 17         one level: entry points and calls
python3 tools/overlay.py 17 dis     disassembled
```

**`itemtext.py`** — what each item id *is*: item `n` is `ITEM.T[390 + n]`.

```
python3 tools/itemtext.py            every item
python3 tools/itemtext.py 104        one
python3 tools/itemtext.py 104 png    write the image out to read by eye
```

**`savemap.py`** — what the game persists, field by field: 57 globals and the
offset each occupies in a save, taken from the serialiser and its inverse and
kept only where the two agree.

```
python3 tools/savemap.py             the layout
python3 tools/savemap.py save1       read those fields out of a snapshot
```

**`player.py`** — the player's stat block, from a snapshot or from the emulator.

```
python3 tools/player.py             # live
python3 tools/player.py chest1      # from out/snap/chest1.ram
```

## The world in three dimensions

**`collision.py`** — a software copy of `tile_collision`, and the harness that
proved it. Run it and it re-checks itself against the game's own answers in
`out/lua_bp13.log`; every logged call carrying the fifth argument is reproduced
exactly.

```
python3 tools/collision.py            check it against the game
python3 tools/collision.py walls 0    every wall plane on level 0
```

**`movement.py`** — the player's own movement. `bp15` is the one that matters:
it replays `out/lua_bp15.log`, the write watchpoint on the player's coordinates,
and reports how many of the game's own height stores the model reaches for. 48
of 48, and 15 of 15 falling frames exact.

```
python3 tools/movement.py bp15        check it against the game
python3 tools/movement.py             the same for player_move, from bp14
python3 tools/movement.py model       the constants, with their sources
python3 tools/movement.py fall 0      a drop, frame by frame
```

Two routines, and telling them apart cost two sessions. **`player_vertical`
(`0x8002ed60`)** is walking: a rate limiter towards the surface, not a physics
model. **`player_move` (`0x8002f320`)** runs only when you are thrown. And
`actor_move_horizontal` is neither — it moves the monsters, from the actor table
at `0x80185da8`, and their vertical is `actor_move_vertical` (`0x8004e330`).

**`tmd.py`** — the PlayStation model format. `RTMD.T[level]` is 240 tile models
and `cell[+5]` picks one per cell; `ITEM.T`, `MO.T` and `MOF.T` hold models too.
The summary reports vertex references that fall outside their object, which is
the check that matters — the references are byte offsets, not indices, and
reading them wrongly is silent otherwise.

```
python3 tools/tmd.py RTMD 0           what level 0's tiles contain
python3 tools/tmd.py RTMD 0 174 obj   one tile, written out as .obj
python3 tools/tmd.py MO 286 png       a model as a picture, to look at
python3 tools/tmd.py MO 305 png 1     just its second object
```

`png` is the cheap answer to "which model is this": orthographic, flat shaded,
textures ignored. It is what showed that `MO.T[286]` and `MO.T[287]` are one
treasure chest closed and open, that `MO.T[234]` is a padlock and not the
keyhole plate the notes called it, and that `MO.T[128]` — the thing hanging in
the air where the game hands you a sword — is a sword.

**`rtim.py`** — a level's textures. Not TIM files: blocks to be pushed into
video memory, each headed by its rect written twice.

```
python3 tools/rtim.py 0               the blocks
python3 tools/rtim.py 0 vram          rebuild VRAM (looks like noise, correctly)
python3 tools/rtim.py 0 page 7 0x7a00 one page through a CLUT -- brick and clay
```

**`level3d.py`** — the whole level as glTF, textures and a Godot project.
Level 0 comes out as 4637 cells, 42 788 triangles and 13 textures.

```
python3 tools/level3d.py 0
python3 tools/level3d.py 0 --cells 24    a corner of it, quickly
python3 tools/level3d.py 0 --obj         plain OBJ instead, for other viewers
```

The lighting is the game's own, computed the way the GTE does and baked into
vertex colours, so the scene carries **no lights at all** — adding one would
shade a level that is already shaded. Two things worth knowing, both learned the
hard way:

* **Axes.** The PlayStation has Y down and +Z away; both are negated, which is a
  half turn and not a mirror. Negating Y alone reflects the whole world left to
  right, and **no map or top-down check can see it** — they are symmetric under
  exactly that flip. It took someone who remembers the game to catch it.
* **`map_d` in an MTL is a transparency map.** Pointing it at the colour texture
  made every dark surface fade out, which read as missing floors.

It also writes **two** meshes. `level00.gltf` is the level, its node named
`-col` so Godot builds a collision body from it. `collision00.gltf` is the
game's *own* collision — the 1304 wall planes out of `collision.py`, drawn as
translucent quads and hidden until you press G. Where the two disagree is worth
looking at: a wall you can see through, or a room the geometry reaches and the
collision seals off.

In the project: **F** walks or flies, **G** shows the collision, **Space**
jumps, **Shift** hurries, **Escape** frees the mouse. Flying passes through
everything on purpose — this level has rooms the game never lets you into. The
readout names the cell you are in, in the game's own numbering, so anything
found there can be pointed at in the data.

**`gltf.py`** — the glTF writer behind it. OBJ was abandoned because it cannot
carry vertex colours in a form Godot reads, and the baked lighting is the whole
point.

**`replay.py`** — plays a recorded session back through the model and says where
the two part company, with a number.

```
./emu/run.sh debug bp16.lua      record: play normally for a minute
python3 tools/replay.py          then replay it
```

`emu/bp16.lua` writes one line a frame — the buttons and the whole player state.
The replay runs three **rungs**, each releasing one layer of the model, and each
in two modes. **Locked** resets to the game's own state every frame, so each
disagreement is its own bug and carries the cell to go and look at. **Free**
carries its own position and reports the first drift and the worst — the honest
end-to-end test, and a useless diagnostic on its own, because after the first
mistake every later frame is wrong for a reason that has nothing to do with it.

The rungs: **height only** gives the game's ground move and asks about Y alone;
**ground and height** gives the facing and speed and computes the step;
**from the buttons** derives the speed too. The facing is the game's in all
three — the turn rate is in `0x8002fe1c` and is not transcribed, and putting an
unread layer under a checked one would spoil the point of the ladder.

What it cannot do yet: `player_horizontal` refuses a blocked step where the game
**slides along the wall**, which needs the wall's facing out of `0x801e6498` and
`0x801e649c`; `tools/collision.py` does not compute those. Pressing into a wall
therefore disagrees, and the output counts that separately rather than burying
it.

### Watching the two side by side

`emu/bp16.lua` also overwrites `out/godot/live.txt` once per game frame, and the
Godot build reads it. Start the emulator with it, run the port, press **C**, and
the game's own player stands in the port's world as a marker while the model
runs over the same input.

```
./emu/run.sh debug bp16.lua
godot-4 --path out/godot
```

**C** compares, **B** takes the buttons from the emulator, **L** switches
locked against free running, **R** resyncs, and **1/2/3** pick the rung.

**B is the one to reach for first.** The line `bp16.lua` writes carries the
game's own decoded button word — `0x801b265c`, the same word
`player_controller` reads — so with B on the port stops reading its keyboard
and takes that instead. One pair of hands playing in the emulator window then
drives the game and the port at once, and the readout shows, every frame, which
buttons are down, where the game's player is, where the port's is, and the
difference between them.

It works in that direction only. Nothing here can press a button *in* the
emulator: there is no input to inject through, which is why every breakpoint
script in this repository ends by asking a person to play.

B and C answer different questions and are worth using apart. **C on, locked**
resets the port to the game's whole state every frame, so each line of the
readout is one frame's disagreement and nothing carries over. **C off, B on**
lets the port walk on its own over the game's input, which is the end-to-end
question: it will drift, and where it starts drifting is the answer.

Locked is the default and it is the instrument: it resets to the game's whole state — position, vertical state *and* velocity —
every frame, so each disagreement is its own and the cell it happened in gets a
red patch on the floor you can walk over and look at.

**`gallery.py`** — every model in `MO.T` on a grid with its number on it, and a
label over every placed object in the world with its slot and its type.

```
python3 tools/gallery.py         # level3d.py runs it too
```

In the Godot build: **K** goes to the gallery and back, **N** shows the object
labels in the world. It exists for one question that reading has not answered —
*which model does an object of type N actually use?* The port assumes
`MO.T[type]`, which has never been checked against the game, and a player looking
at the two side by side reports armour standing where doors should be. The
placement is not the reason: the disc records and the live table agree on the
type id for 347 of 347 slots.

So the correspondence is made visible instead. Stand somewhere in the game, read
the type off the world label, then find the shape you can actually see in the
gallery and read its number. Each pair is one fact, and a handful of them will
name the rule.

**`walk.py`** — records where the player goes, for checking any of this against
the running game.

## The boot chain

The disc holds four executables and three of them load at the same address, so
none of these tools work on an address alone: every one takes the executable
with it, by nickname — `boot` for `SLUS_002.55`, then `open`, `game` and `end`.
What they found is in [BOOT.md](BOOT.md).

**`mips.py`** — the four executables and enough MIPS to walk them. A library,
not a command: `mips.load("open")` gives an `Exe` with its base, its entry
point and its text, and `mips.resolve` pairs every `lui` with its `%lo` to say
which absolute address each instruction forms.

**`calltree.py`** — function discovery and the call graph.

```
python3 tools/calltree.py open                what is in it
python3 tools/calltree.py open entry -d 3     the tree from the entry point
python3 tools/calltree.py open 0x80011e14 -f  one routine's skeleton
python3 tools/calltree.py open 0x800136d8 -u  who calls it
python3 tools/calltree.py open 0x80012494 -s  its strings and constants
python3 tools/calltree.py open --tables       pointer tables in the image
```

`-f` is the one to reach for. `open_main` is 366 instructions of which about
sixty say what the opening does, and `-f` prints those sixty: every call with
the constants going into it, every branch, and every absolute address touched.
An argument it cannot trace to a constant prints `?` rather than a guess — an
earlier version carried a stale `a0=3` down four calls that never set it, which
reads as a finding and is not one.

**`psyq.py`** — names the Sony library from the library's own words.

```
python3 tools/psyq.py open              what it can name
python3 tools/psyq.py open --write      put those names in the symbol table
```

The PSY-Q libraries are linked in with their debug messages intact, and each
message is built inside the routine it describes, so whatever forms the address
of `"PutDrawEnv(%08x)..."` **is** `PutDrawEnv`. That names 31 routines in
`OPEN.EXE`, 32 in `GAME.EXE` and 30 in `END.EXE`, and what is left standing is
the game. It refuses to name a routine two messages print from, because that
means the boundary swallowed a neighbour rather than that the routine has two
names.

**`str.py`** — the movies: 28 Sony STR streams under `/OP`, `/STR` and `/DRM`.

```
python3 tools/str.py list                  every movie on the disc
python3 tools/str.py info /OP/L0.S         one, frame by frame
python3 tools/str.py check /OP/L0.S 40     decode 40, and report the count
python3 tools/str.py png /OP/M3.S 200 out/ one frame, as a PNG
```

The MDEC decoder is checked by decoding: every block has to be a valid Huffman
code and the bitstream has to run out within a word of the frame's end. Twenty
frames each of `L0.S`, `M0.S` and `M3.S` pass with at most 42 bits of padding
left. Version 2 and version 3 differ in how the DC coefficient is stored and
the difference is not optional — see BOOT.md section 4.

**`opening.py`** — the opening's assets, into the port.

```
python3 tools/opening.py           into out/godot/opening/: the TIMs, the stills,
                                   and the movies if ffmpeg is about
python3 tools/opening.py video     just the transcodes, ~37 MB of Ogg Theora
python3 tools/opening.py title     compose the title screen at the game's own coordinates
```

The movies play in the port because ffmpeg has a `psxstr` demuxer and an `mdec`
decoder and will hand back Ogg Theora with the XA audio attached. That is not a
substitute for `str.py`: reading the format ourselves is what established it,
and it is what says the version 2 and version 3 frames differ. It is how the
pixels get on screen without a decoder faster than Python.

`title` is the check on the layout: the rectangles came off the primitives the
three layer routines fill in, and if any were misread the picture says so.

## Disassembly

**`rdis.py`** — the whole executable, walked from its entry point. This is the
one to reach for: it finds the routines, decides where each one ends, resolves
the switch tables, and writes an annotated listing of any of them.

```
python3 tools/rdis.py game                what is in it
python3 tools/rdis.py game --build        out/rdis/game.json, the database
python3 tools/rdis.py game 0x8002ed60     one routine, annotated
python3 tools/rdis.py game --listing      every routine, into out/asm/game/
python3 tools/rdis.py game --tree entry -d 4    the call tree
python3 tools/rdis.py game --unnamed      the biggest routines with no name
```

It differs from `calltree.py` in where it starts. That one scans the whole
image for `jal` targets and ends each routine where the next begins, which is
the right first instrument and has two failures that matter: a word inside a
texture that reads as `jal` invents a routine, and a listing runs off the end
of a real one straight into data. Against capstone over GAME.EXE, **3161
instructions inside what that method calls functions are opcodes the R3000A
does not have**, every one of them past `0x80080000`.

`rdis.py` follows control flow instead and decodes only what it reaches: 92175
of 142848 words in GAME.EXE, in 816 routines, and **every instruction belongs to
exactly one of them**. What it would otherwise lose — a routine reached only
through a pointer — is put back by scanning the image for words pointing at a
routine already walked, and for GAME.EXE by seeding it with every address the
twenty-eight level overlays `jal`, since nothing inside the executable calls
those.

Three things it resolves that a linear disassembler cannot:

* **`lui`/`%lo` pairs across basic blocks**, by constant propagation over the
  control flow graph. `mips.resolve` pairs them only inside a straight line.
* **Switch tables** — 40 in GAME.EXE, 2156 arms, every bound read off the
  `sltiu` that guards the index. Tying the guard to the register it tests is
  what settled it: taking the *nearest* `sltiu` read a 236-entry table out of
  an unrelated comparison, and the arms swallowed four routines into one.
* **What a call is given**, where the argument is a constant. Where it is not,
  nothing is printed.

It also found that **24 names in `data/symbols.json` are labels inside routines
rather than routines**: `tile_op_20_wall` and `tile_op_30_ramp` are arms of
`tile_collision`'s 49-way switch, and `player_bob` is inside `player_vertical`.
The listing shows them that way.

**`mipsdis.py`** — the decoder underneath it, and a library rather than a
command. Written here rather than bound from the emulator's capstone for two
reasons: capstone does not decode the GTE at all, and it hands back a string,
which is the one thing an annotating pass cannot work with. It agrees with
capstone on every R3000A instruction in GAME.EXE.

**`consts.py`** — every number in the code, where it appears, and what it is
doing there.

```
python3 tools/consts.py --build      walk all four, write the cross reference
python3 tools/consts.py 0x800        every site of 2048, with its role
python3 tools/consts.py --top        the commonest numbers with no name yet
python3 tools/consts.py --switches   every switch, with the count its guard states
python3 tools/consts.py --fields 0x44   what is read at +0x44 of something
python3 tools/consts.py --doc        regenerate CONSTANTS.md
```

The names live in `data/constants.json` with the evidence for each and which
kind of claim it is — **read**, **derived** or **guessed**. A number may have
several meanings and they are all kept: `0x320` is the player's collision
radius *and* the byte stride of a row of the terrain grid, and a file with one
name per number would have to be wrong about one of them.

The part that is not obvious: **the compiler takes numbers apart.**
`collide_at_cell` indexes the grid at `cz * 800 + cx * 10` and neither 800 nor
10 appears in its code — both are built out of shifts and adds. So the chains
are read back and the multiplier is reported where it is *used*, not where it
is built. That distinction is the whole thing: the routine finishes building
`10 * cx` and then adds the grid's address with the same `addu` it has been
using all along, and reading that as one more step turns 10 into 11 and loses
the only place the number appears.

[CONSTANTS.md](CONSTANTS.md) is the generated index of all of it.

**`portmap.py`** — what in the port corresponds to what in the game.

```
python3 tools/portmap.py              the coverage, in one screen
python3 tools/portmap.py --check      every marker resolves; exit 1 if not
python3 tools/portmap.py --next       what to port next, and why that
python3 tools/portmap.py --doc        regenerate PORT.md
python3 tools/portmap.py 0x8002ed60   what the port does with one routine
```

The two sides drifted apart in the obvious way: `godot/player.gd` opens with
forty lines of prose saying it came from `player_vertical` at `0x8002ed60`,
which is exactly right and which no tool can read. So the correspondence is
written where both sides can carry it — a marker comment in the GDScript:

```gdscript
# @orig game:0x8002ed60 player_vertical  status:verified -- 48 of 48, bp15
func _move(dx: int, dz: int) -> void:
```

and the same pairing comes back the other way, as a `; port:` line at the top
of the listing `tools/rdis.py` prints. The marker names the executable as well
as the address, because three of the four load at `0x80011000`.

**A marker is a claim that the port reproduces that routine, not that it does
so correctly.** `--check` only verifies the address is real. `status` says how
far it went: **verified** (checked against a recording, with a count),
**transcribed** (read off the MIPS), **partial**, or **guessed**.

A marker may point *inside* a routine, and often should: `player_bob` and the
death branch of `actor_tick` are labels, and the port has a function for each.
Those count as parts rather than as the whole routine — counting `player_bob`
as `player_vertical` would claim all 368 of its instructions for twelve lines.

[PORT.md](PORT.md) is the generated index, and its last table is the queue:
every routine with no marker, ordered by how many routines call it.

**`disasm.py`** — MIPS disassembly of `GAME.EXE`, binding the capstone that
ships inside the emulator's AppImage. With no arguments it cross-references the
player position and the inventory; give it addresses to cross-reference those
instead, and the output comes back with names attached.

```
python3 tools/disasm.py 0x801ba988
```

**`fdis.py`** — disassembles a stretch of code **including the GTE**, which
capstone does not decode at all. Name an executable first to read one of the
others: `python3 tools/fdis.py open 0x80011e14 40`. A single `ctc2` ended every attempt to read the
renderer until this existed, and the register names are the point: `ctc2 $t5,
L11L12` says "light matrix" where `ctc2 $t5, $8` says nothing.

```
python3 tools/fdis.py 0x8003bb04 60
```

## The emulator

**`emu/run.sh`** — starts PCSX-Redux with the HTTP API on :8080.

```
./emu/run.sh                    normal
./emu/run.sh debug              plus emu/bp.lua and its breakpoints
./emu/run.sh debug bp7.lua      plus a different script
./emu/run.sh stop
```

**Never `return false` from a breakpoint callback.** PCSX-Redux reads it as
"remove this breakpoint", so the point fires once and is gone — which cost this
project two wrong conclusions drawn from silence. Return nothing. And arm a
control on something known to happen constantly, in the same run, before
believing that anything did *not* happen.

Breakpoints only fire under `debug`: they need the interpreter, and they need
the Lua file to turn the debug switch on at runtime because setting it in
`pcsx.json` does not take. Each `emu/bp*.lua` writes its own log under `out/`.

The three worth knowing: **`bp13.lua`** takes `tile_collision`'s arguments at
entry and its mask at exit, which is what `tools/collision.py` is checked
against; **`bp14.lua`** does the same for `player_move`; and **`bp15.lua`** is a
*write watchpoint on the player's own coordinates*, which is the one that found
the movement after two readings had picked the wrong routine. Prefer that shape
of question: a breakpoint on a routine you chose can only confirm the choice,
while a watchpoint on the value makes whatever writes it name itself. All three
need somebody walking about — that is the whole point of them.

**`bp19.lua`** is the one for the monsters. It puts an execution breakpoint on
each of the 39 instructions in the actor cluster that store the state byte at
`actor+9`, and logs every change as a transition — old value, new value, the
routine that made it, which actor, where it stood, where the player was. It
also logs the die `0x8004c1f0` rolls (`ROLL`), a heartbeat every 600 frames
with the counts of everything that fired, and writes `live.txt` so the port
can compare. Kill something, walk away, come back, and the log is the respawn
rule.

It watches **instructions, not memory**, on purpose. A write watchpoint's
callback runs before the store lands, so reading memory there gives the value
the byte *had*; the first version of this script did that and reported two
`sb $zero` instructions as setting 1 and 2.
There is no way to press a button from here, so anything needing input needs a
person at the window. `POST /api/v1/lua` returns 404, so a script cannot be
injected into a running emulator either — it has to be loaded from the
emulator's own Lua console, or at startup.

**`psxlive.py`** — reads RAM and VRAM over that API without disturbing the game.

**`psxdbg.py`** — the GDB stub on :3333, which is what can *write* memory, and
what resumes the emulator if it ends up paused.

**`snap.py`** — takes a snapshot: RAM, VRAM and a screenshot together, into
`out/snap/`. Everything above that reads a snapshot reads what this writes.

**`diff.py`** — compares two snapshots. Most of what we know about live memory
came from taking one either side of a deliberate action and looking at what
moved.

**`livemap.py`** — follow the player around the level in a browser.

```
python3 tools/livemap.py         # then open http://localhost:8777
python3 tools/livemap.py stop
```

It shows the map, the objects near you, your HP, MP, gold and level, and it
records where one level hands over to another into `data/transitions.json`.
Level detection can drift, so the page can pin a map by hand; object pins come
straight from memory and stay right either way.

**`bpwatch.py`**, **`bptest.py`** — breakpoint experiments driven from Python.

---

## How a finding usually goes

Worth writing down, because nearly everything in FORMATS.md arrived this way.

1. **Snapshot either side of an action.** `snap.py` before, do the thing,
   `snap.py` after, `diff.py` between. That gives an address.
2. **Ask the code about it.** `disasm.py <address>` gives every instruction that
   forms it. What the code does with a value is worth more than what the value
   looks like.
3. **Check it against data.** A reading that holds on one level and fails on the
   other twenty-seven is not a reading. Several claims in FORMATS.md were
   withdrawn exactly here.
4. **Write down the evidence, not just the conclusion** — in `symbols.json` for
   an address, in FORMATS.md for a format. Two findings this session were wrong
   in ways only visible because the earlier note said *how* it had been
   established.

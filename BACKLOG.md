# Backlog

Open threads, roughly in the order they unblock other work. Everything here is
described in more detail in [FORMATS.md](FORMATS.md) and, for the boot chain,
[BOOT.md](BOOT.md); external material we have not verified ourselves is kept
separately in [EXTERNAL.md](EXTERNAL.md).

## 0. What the boot chain left open

The chain from the entry point to the first frame with a controller in it is
read and written up in [BOOT.md](BOOT.md): the shell and its three shared
bytes, `OPEN.EXE`'s logos, attract movies and title menu, the STR decoder, and
the whole input path down to the seven control schemes. Four things it did not
finish, none of them blocking:

* **`END.EXE` is unread.** Only its Sony library is named, by `tools/psyq.py`.
  Its own `play_movie` table names `\OP\M4.S`, `M5.S` and `M6.S`, so it is
  built like `OPEN.EXE` and should read quickly.
* **The save path.** `OPEN.EXE` counts the saves on the card and passes the
  menu's answer in `overlay_arg2`; `0x8001fa60` in `GAME.EXE` is what reads it
  and it has not been read. Until then the port always starts a new game, and
  nothing here can load `tools/savemap.py`'s fields back into a running game.
* **Sound.** `OP.D`'s trailing VAB is extracted and unparsed, the title music
  is a streamed XA track inside `\OP\M2.S` that nothing decodes, and the two
  menu sounds are ids `0x3a` and `0x5a` into that bank.
* **The title screen's frame rate.** It gives up after `0x178` frames, and
  whether that is six seconds or twelve is OPEN.EXE's own loop, not read.
  `GAME.EXE`'s is settled: `frame_limit` holds every frame to four vertical
  blanks, 15 a second (FORMATS.md, "How long a frame lasts"), and the port's
  `TICK_HZ` is that now.

Also worth doing and cheap: the port shows a still where the game plays a
movie. `tools/str.py` decodes any frame correctly but is pure Python, so
playing one back wants either a faster decoder or a pre-rendered sequence.

## 1. Cross-level teleport

The loader is now known: `0x8005f444(level)`, fed from the pending byte at
`0x8018fae4`, indexing a pointer table that `0x8005ee58` builds. What is not
known is how to drive it from outside — writing the pending byte should do
nothing on its own. Next step is to find what normally sets `0x8018fae4` and
then calls the loader, which is the same trigger the placed transition objects
pull. Until then, writing the four position copies only moves the player inside
the level already loaded.

Still open underneath it: the per-level `FDAT.T` triples at `3n` are read by
something we have not found, and a level change touches no archive at all, so
the two may not be the same path.

## 2. The rest of the 24-byte placement record — now the blocker for objects

Five of its twenty-four bytes are decoded (FORMATS.md section 16): flags, cell X
and Z, the type id and the sign text index. The other nineteen carry the height,
the rotation and whatever else an object needs, and correlating them against a
RAM snapshot is straightforward now that the block is located.

**Done, and the backlog was out of date rather than the work undone**: the
record's own reader already had cell, fine offset within the cell, rotation and
type id. `tools/level3d.py` now places 294 of level 0's 347 objects.

**Withdrawn: "height is not in the record at all."** It is, at offset 12, a
signed 16-bit measured from the terrain, and `y = -128 * cell[+6] + h`
reproduces the live table for 345 of level 0's 347 objects. The claim survived
because every object it was checked against happened to have `h = 0`. What it
cost was visible in the port: a chest is three objects in one cell — body, lid
and contents at three different heights — and putting all three on the floor
drew the lid inside the body. FORMATS.md section 16 has it. (The contents were
called a lock plate here; that is withdrawn -- type 106 is the herbal liquid.)

**The 53 without a model are found.** An `MO.T` entry is not a bare TMD: word 0
is the total size, word 1 a count of one to three, and **word 2 is the offset of
the TMD**, with a table of further offsets from `0x14`. `find_tmd` was scanning
the first 256 bytes for the id, which works only for the models that keep it near
the front; the statue keeps its at 3448 and the chest at 13964. Reading the offset
properly gives **347 of 347 objects on level 0 a model**, up from 294, and the
port went from 37 542 triangles of objects to 65 942.

**The scale is per object and it is in the live record**, at `+0x2c` of
`object_table` with `0x1000` for 1.0 — not the constant the queue assumed.
Across level 0 it reads x1.00 on 271 objects, **x0.00 on 59**, x1.99 on 34 and a
scatter between on the graves, so some of what the port drew at the wrong size
was drawn at the wrong size and some of what it drew is not drawn by the game at
all. `tools/level3d.py` takes it from a snapshot for now and skips the zeroes,
the same borrowed-not-understood arrangement as the object textures.

**What fills it is found, and it is not a size.** `object_set_present`
(`0x80044b40`) writes `0x1000` into all three when an object is present and `0`
when it is not, so the triple is a visible/not-visible switch and the 59
objects at `x0.00` are switched off rather than tiny.

**Superseded: it is a size too, and nothing is borrowed for it any more.**
`load_object_placement` is read whole (`tools/objload.py`; FORMATS.md section
16, "read whole"): on flag `0x10` the scale is `p[+0x10] << 5` -- the trees,
which this note called graves -- and it is zero for the door classes, which the
grid draws instead. Of the 59 zeroes, 49 are empty slots. The same reading gives
the three angles and the game's rule for what is drawn, so `tools/level3d.py`
no longer takes the scale, the angles or the render class from a snapshot, and
every level has them. Only the object textures are still borrowed.

The same routine also writes a byte into the terrain cell the object stands in,
and **the first reading of that was wrong and is withdrawn**: it is the layer's
`+0`, the tile index the *drawing* uses, not the shape at `+3` the collision
reads, and the byte it restores comes from the type row rather than from the
placement record. So an object's collision is still not found. FORMATS.md, "The
scale triple is a switch", has it in full.
The old note, which the reading replaces: the disc record's `+8` and `+10` look like the object's own
radius and height instead — `0x320` and `0x6a4` shapes, which is what the
object-collision gap needs.

**And from type 300 up the level is part of it too.** `model_of_type`
(`0x80040568`) adds `32 * current_level_block` for any type at or above 300, so
`MOF.T` is banked 32 models to a level and level *n* uses bank *n + 4*. Over
all 1424 such objects in the game the bank is `level + 4` every time. The old
rule ignored the level, which is right on level 0 and wrong by 32 banks on
level 1 — and level 0 is the only one the port has built.

**Objects drawn as the wrong things — solved, and the answer was 128.** An
object of type N uses `MO.T[N + 128]`, measured off four pairs a player named
from the model gallery, with the sizes agreeing independently. `MO.T[type]` was
an assumption nobody had ever checked. Past `MO.T`'s 428 entries the numbering
continues into `MOF.T`; that part is inferred from the shapes and wants
confirming — type 301 is the *Broken Cart* and lands on `MOF.T[1]`, which is
cart-shaped.

What is left of it: **48 of level 0's objects now have no readable model**, up
from none, because the correct mapping reaches entries the old one never did.
Whether that is the wrapper again, a third archive, or the MOF continuation being
wrong is open.

**The old note, kept because the reasoning still holds:** The placement is not the
reason: the 24-byte disc records and the live table agree on the type id for
**347 of 347** slots. The live record carries no pointer to a model either. The
renderer's object walk is `0x80040ae4` — it steps `object_table` by 0x44, skips
type `0xff` and dispatches on the byte at `+4` — but where it picks the model is
not read, and that is the next thing to find. Reading `MO.T[type]` is an
assumption that has never been checked against the game.

**The chest is only its lock.** Type 106 reaches `MO.T[234]`, and that entry is
140 primitives measuring 110 x 300 x 96 — a keyhole plate and nothing else,
with no second TMD inside the wrapper. A player reported exactly that: a small
keyhole, correctly drawn, hanging where a chest should be. So the body comes
from somewhere else — the class byte `0x16`, which no other object nearby
carries, is the obvious place to look.

**Two primitive-layout bugs, found by looking at the port beside the game.**
A lit gouraud primitive interleaves its references — `n0 v0 n1 v1 n2 v2` — and a
textured primitive carries colour words only when it is unlit. Reading them the
other way scrambled mode `0x34`, which is 58 000 of the object primitives, into
tangles that parsed and placed without complaint. Level 0's objects went from 44
of 82 types above 95 % usable primitives to **81 of 82**. Only type 309 is left,
704 primitives of untextured gouraud with the wrong `ilen`, and nothing draws it
anyway.

**Found: `FDAT.T` entry 96.** The object textures are a `LoadImage` stream in
`RTIM.T`'s format that `init_level_state` sends into VRAM at game start, and
`tools/level3d.py` now builds every level's VRAM from it and the level's own
`RTIM.T` -- no snapshot. FORMATS.md, "Where the object textures are". The water
on page `0x0f` is animated by `texture_scroll_step`, a row a frame, and the port
does the same (`godot/scroll.gd`). The note below is kept for how it was looked
for.

**The object textures are not in `RTIM.T`.** The placed objects want texture
pages `0x0b` to `0x0f` — VRAM from x=704 across — for **57 119 of their
primitives**, and `RTIM.T[0]` leaves that whole region empty, so every one of
them drew white. In the running game those pages are full, so something loads
them and we have not found what: the bytes are not a verbatim run in any of the
nine archives, which rules out a plain copy and points at a packed or
rearranged load. Until it is found, `tools/level3d.py` takes those pages from
`out/snap/b.vram` — the game's own VRAM, obtained by looking rather than by
understanding, and labelled as such in `object_vram`. Building without a
snapshot still draws white, which is the honest failure rather than a silent
one.

**Answered, and it is the sea.** The four materials below sample entry 96's
CLUTs; the flat sheet is level 0's water, drawn with a frame of the animated
water texture at (1016, 96), and the port draws it now. Kept for the record:

**The level's own geometry reaches into those pages too, and draws nothing
there.** Level 0's geometry names four page-and-CLUT pairs whose CLUTs `RTIM.T[0]`
leaves empty — pages `0x0b`, `0x0d` and `0x0f` twice — so in the port they are
transparent throughout and **404 of its triangles are invisible**: 6, 54, 48,
and 296 that make one flat sheet at Y = -12160 spanning cells x 0 to 67 and z 11
to 29. The geometry is still drawn from `RTIM.T` alone, deliberately. With the
snapshot's pages three of the four come out mostly opaque, and turning them on
changes how the level looks, which wants somebody who knows the game to look at
those cells first rather than a reading of what the sheet ought to be.
`page_texture` keeps the two readings in separate files (`tex_` and `obj_`)
for exactly this reason: they disagree on those pages, and while one file
served both, whichever was written first won.

**Not every placed object is drawn.** Type 299 is the readable marker — a coarse
box two cells across, 76 instances across the game and every one of them
carrying a text index, which is exactly the number of readable things in it. It
stands on the same cell as the object actually there and the port was drawing it
on top, which turned a bull's head, the *Broken Cart* and a monument into stone
pillars. It is in `NOT_DRAWN` now. Whether other types belong there is open, and
the way to settle it is the same as everything else here: find what the renderer
walks and what it skips, rather than excluding models that look wrong.

## 3. Finish the proportional font

The item mapping is settled — item `n` is `ITEM.T[390 + n]`, proven at both ends
(FORMATS.md section 13) — and `tools/itemtext.py` reads it. Nine human-read images seeded 78 glyphs,
206 shapes to 284, and the corpus reached 91 % dictionary words; `out/items.txt`
holds all 131 descriptions. What is left is cosmetic: `R` in *Recovery*, an `S`
in a kerned *Sword*, the `t` in *Effect*, and the pair in *Key*. Low priority —
the text is readable as it stands.

## 4. NPC conversations — done, and the corpus was wrong twice

Settled. An entity's **block 0** is its conversation when it begins `0x70`,
and 43 entities in the game have one, saying 594 lines. `tools/escript.py`
decodes them, `tools/story.py` prints them in the order the game tells them,
and `python3 tools/escript.py check` replays what `emu/bp21.lua` recorded in
play — **44 of 44** steps and lines over four conversations.

Both earlier readings were wrong and both are withdrawn in FORMATS.md §9:
"entity scripts are animation sequencers" (they are dialogue; the `0x2b` test
gates a different call) and "1086 scripts" (those were blocks 1..15 of each
record, which are not scripts — the pointer list starts at `+0x38`, not
`+0x3c`).

**What is left here** is the other fifteen blocks. Nothing in `GAME.EXE`
reads them; they are relocated for the level's own overlay and their kind
bytes repeat across entities — every entity on level 0 has a `0x00`, and all
but one end with a `0x02` then a `0x03`. `tools/ovdis.py` now walks the
overlays properly, so whichever routine indexes `record+0x38+4n` is findable.

## 4. The walls — done, bar the tail of the opcode table

`0x20`, `0x21`, `0x22`, `0x23`, `0x24` are walls, `0x10`, `0x30`, `0x32`,
`0x33`, `0x34` are floors and `0x11` is a ceiling — transcribed from the
handlers and reproduced against the game's own answers on **every one of the
4264 logged calls that carries the fifth argument** (FORMATS.md section 4,
`tools/collision.py`). A wall is a plane *inside* the cell with a height band,
which is why every attempt to predict walls as cell edges failed.

Every opcode that has appeared in a log is transcribed and exact. `0x25`,
`0x31`, `0x35`, `0x17`, `0x18`, `0x19` and `0x40` have not appeared yet; each is
one handler at its address in the table at `0x80011b0c`, scored the same way.
Level 0 uses `0x25` in 41 cells and `0x31` in 4, so those two are reachable.

## 4b. What the level looks like — read

**Found.** `RTMD.T[level]` is a TMD of 240 objects and `cell[+5]` picks one per
cell; `cell[+7]` turns it and `cell[+9] & 0x3f` lights it (FORMATS.md section 4).
The renderer is `draw_cell_walk` into `draw_tile`, readable now that
`tools/fdis.py` decodes the GTE that stopped capstone.

Both readers are written and check out:

* **`tools/tmd.py`** reads the models. 240 objects, 3485 primitives, zero vertex
  references outside their own object — which is the test that caught the
  references being byte offsets rather than indices.
* **`tools/rtim.py`** reads the textures. 98 blocks, 231 424 of level 0's
  233 472 bytes, and page 7 under CLUT `0x7a00` comes out as the brick, cobble
  and clay the level is built from.

And it is assembled: `tools/level3d.py` writes level 0 as glTF — 4637 cells,
42 788 triangles, 13 textures — with the game's own lighting baked into vertex
colours and unlit materials, so the picture depends on no light anyone placed.
It opens in Godot and can be walked and flown through.

**The movement policy is read and confirmed.** Two readings failed first, and
both were caught by a recording rather than by more reading:

* that `actor_move_horizontal` is the player's — it is the monsters', and the
  player is not in the actor table at `0x80185da8` at all;
* that `player_move` (`0x8002f320`) is walking — it ran 69 times in a session,
  all in the knockback after dying. That transcription is right about the
  routine and `tools/movement.py` reproduces all 69 frames exactly.

Walking is **`player_vertical` (`0x8002ed60`)** for the height, `0x8002e3f8`
through `0x8002f9bc` for the ground plane. The height is a rate limiter — 0x80,
0x100 or 0x200 a frame towards the surface, placed exactly when inside 0x80 —
with four fall states, two of which are falls with different accelerations
(`0x50` for the short one, `0x28` for the long). No gravity and no jump while
grounded. FORMATS.md section 4 has it in full.

`emu/bp15.lua` settled it, and the reason it could is worth keeping: it is a
**write watchpoint on the player's own coordinates**, not a breakpoint on a
routine somebody chose, so it cannot be wrong about where to look.
`python3 tools/movement.py bp15`:

```
48 of 48 of the game's own height stores chosen exactly (100 %)
15 of 15 consecutive falling frames advance by exactly the velocity
```

`godot/player.gd` carries the model and `godot/selftest.gd` holds the GDScript
copy to the Python one, 690 frames.

Both loose ends are now closed, by a recorder that logs a line a frame
(`emu/bp16.lua`) and a replay that runs the model over the same input
(`tools/replay.py`). Over about thirteen minutes of ordinary play:

```
speed ramp                      20902 of 20902 frames reproduced
rung 1 height only      locked  20902 of 20902 exact
rung 2 ground+height    locked  19889 of 20902 exact
rung 3 from the buttons locked  19889 of 20902 exact
   of the 1013 that differ, 788 are the wall slide and 212 are within reach
   of a placed object -- neither modelled -- leaving 13 unexplained
```

Rung 3 scoring exactly what rung 2 does means the chain from buttons to speed is
exact; every remaining disagreement is the **wall slide**, which is the one piece
still missing (see below). Two things the replay found that reading had not:

* **The step is not the speed.** `0x8002fc94` forms it as
  `speed^2 / isqrt(strafe^2 + forward^2)`, and the game's own square root
  (`0x80074508`, the library's SquareRoot0) comes back a unit short on a perfect
  square — `isqrt(40000) = 199`. So a speed of 200 steps 201. Using an exact
  root disagreed with the game on 1394 frames of 3632.
* **Acceleration and decay are different rates**, and the two ramps decay
  differently from each other: `max/4` while a button is held either way, then
  `max/8` for the forward speed (`sra 3` at `0x8002fad4`) and `max/4` for the
  strafe (`sra 2` at `0x8002fc38`). The replay caught each of them — the first on
  85 frames, the second on four — before either was read.
* **The head bob is a rectified sine** over a phase that accumulates the step's
  magnitude whether or not the step landed, which is why walking into a wall
  still bobs the camera. Reported from play first, then found at `0x8002f298`.

**The frame rate is still not settled, and an earlier note here claiming it was
is withdrawn.** The recorder carries a wall clock and measured 26 frames a second
in one session and 34 in the next — the emulator runs uncapped under the
interpreter, so wall time says nothing about the console in either direction. The
port runs at 30, which is the PlayStation's usual half-VSync and sits between the
two, and that is a guess. Counting game frames between VSync interrupts would
settle it in one recording.

What is left of movement:

1. **The wall slide.** `player_horizontal` turns a refused step along the wall's
   own facing, which `tile_collision` leaves at `0x801e6498` and `0x801e649c`
   and which only `0x80033764` writes. `tools/collision.py` does not compute
   them, so the port stops dead where the game slides. This is the last thing
   between rung 2 and 100 %.
2. **The turn rate**, `0x8002fe1c`. The per-frame increment lives at
   `0x801b264c` and was seen ramping 0, 8, 16, 24, 32; the routine is unread, so
   the replay takes the facing from the game rather than deriving it.
3. **Objects are solid and the port does not know it.** `collide_query`'s flag
   `0x10` asks `0x8004d644` about objects and `0x20` about actors, and
   `tools/collision.py` models neither. 212 of the frames that disagree are
   within a radius of a placed object, and the types involved are 287, 325 and
   324. This is the second-largest gap after the slide, and it overlaps item 2
   above: 287 is one of the 53 with no parseable model.
4. **Something else pushes the player.** Six of the X writes `emu/bp15.lua`
   caught came from `0x800482e4`, in the actor cluster, moving the player about
   37 a frame.

The Godot build no longer collides against the drawn geometry: `godot/collision.gd`
is `tools/collision.py` transcribed, and the player runs it per frame. Both of a
cell's layers are exported now, six fields rather than three, so a bridge stops
handing the player the floor of the room beneath it. The overlay (press G) draws
where the game's collision and the drawn geometry disagree, and that is still
worth looking at: it is where the unreachable rooms are.

The old plan of finding the renderer through a breakpoint on the geometry cache
is no longer needed and is withdrawn.

**The tile shapes are collision only** — three references to the working copy in
the whole executable, all accounted for. Appearance is an entirely separate
description of the same cell, and that is why no texture was ever going to turn
up in the shape records.

Worth keeping in mind for whatever is next: the winning move was not a better
metric against the map but **making the game state the answer**. The struct at
`0x801e6470` looks like it holds that answer and does not — ten call sites share
it — so the breakpoint takes the mask at the exit instead, before it is
returned.

## 5. Enemies — placed, and the model mapping found

58 creatures are live on level 0 in 14 kinds, and `tools/level3d.py` now draws
them. Two things fell out:

* the actor table at `0x80185da8` is 0x88 a slot — `+0` is 0xff when free, `+2`
  the kind, `+0x1c` and `+0x1e` the radius and body height, `+0x22` the fine
  offset in the cell, `+0x2c` the position;
* **`entity_table`'s first halfword is `0x400` plus the model number**. Kind 0
  reads `0x432` — model 50 — and a player looking at the catalogue named 50 as
  the flower enemy "of which there are many on this level". Kind 0 is eleven of
  the fifty-eight.

**Found since: the disc places them.** The 16-byte stride noticed in `FDAT`
entry `3n+1` near offset 13403 was it: link 1 of the same chain the objects come
from, starting at 13000 on level 0, is the actor table, read by
`actor_table_build` (`0x800530f8`). `tools/actors.py` rebuilds a level 0
snapshot's 58 slots from it, positions and heights to the unit, so the port no
longer borrows the snapshot. The rule for when each one is drawn is read and
ported too (`godot/actors.gd`), in FORMATS.md section 17. Still open:

* **who makes the two men by the house category 8.** The disc says 1, a
  snapshot says 8, and no store in GAME.EXE writes a literal 8 into an actor.
  `emu/bp19.lua` now watches both bytes;
* **the AI**, what an awake creature does (`actor_tick`, `0x800500a8`), so the
  port's creatures stand where they woke;
* followers (categories 3 and 4, entity flag `0x10`) and actors riding an
  object (entity flag `0x10000`) are built but not placed right. Level 0 has
  none; level 3 has three;
* `0x801b25e5`, set by `player_turn`, makes the activator look at every slot on
  every frame while it is 1. What it means is not read;
* model 110 (kind 15, ten of them on level 0) has its `+3` cleared on every
  frame unless `0x801b25d9` or `0x801b25da` holds `0x5c` and the halfword at
  `0x801b2500` is non-zero. What `+3` does to the drawing is not read.

Movement is a separate matter and half done already: `actor_move_horizontal`
(`0x8004dbc8`) and `actor_move_vertical` (`0x8004e330`) are both transcribed in
FORMATS.md section 4, with gravity per monster kind out of the entity record.
What is missing is the AI that decides where they go.

## 5b. Movement the player can change

Two things reported from play, both unverified and both worth a look when the
movement model is being finished:

* **Walking speed may rise as the character levels.** The port currently uses a
  fixed 2344 units a second, the median of a recorded walk, so if speed is a
  stat it is baked in at one value. The player stat block is at `0x801b24e0`
  and `tools/savemap.py` knows 57 persisted fields; a speed among them would
  show up as a field that moves when the character advances. Narrower now: the
  velocity `player_move` consumes is three s16 at `0x801b266c`, written by the
  helpers at `0x800307f4`–`0x80030908`, so whatever fills *those* is the speed,
  and `emu/bp14.lua` logs the number every frame.
* **Boots may change how steep a slope can be climbed, or how fast.** If so it
  is a modifier on the collision query rather than on the geometry — the radius
  and body height passed in are the only inputs the query has, and the fifth
  argument already varies from call to call. Against that: the player's radius
  `0x320` and body height `0x6a4` are *literals* in `player_move`, and so is the
  `0x100` step limit, so a boot would have to change something else — the
  velocity, or the state byte at `0x801b25e5`.

Neither has been looked for. Recorded so the observation is not lost.

## 5c. Doors that open, and the ones that are hidden

**The swinging doors are read and in the port** (FORMATS.md, "A door that
swings"): class 0x01, 42 in the game, nine on level 0 -- `godot/doors.gd` opens
them with USE, swings them, stamps the doorway's collision open and closed and
waits while the player stands in it. What is left, in order of how many doors
it would open:

* **class 0x02, 128 objects** -- `stamp_rect` from `p[+0x13] + 2w`, marked with
  radius 0x1130; its arm is not read.
* **the grid-drawn doors, classes 0x03 to 0x05 (82) and 0x54 (7)** --
  `stamp_table` writes their walls and tiles at load; opening one is their arms
  writing the table's other half (`sel` 1), which means the level geometry has
  to change at run time too, not only the collision.
* **classes 0x00 (12) and 0x1b (23)**, `find_object` points 0x700 in front of or
  behind them; 11 of the 12 class-0 doors carry lock byte `0x8c`, a key.
* **keys and messages**: a lock byte other than 0xff, 0xfd or 0xfe is either an
  item `use_item` takes or an `announce` code, and neither is in the port.
* **a frame-by-frame check**: `emu/bp24.lua` logs the door arm's state, counter
  and yaw and the doorway's shapes; nothing has been recorded with it yet.

Reported from play: some walls hide lift-up doors that open when pressed. Doors
in general are objects (see item 2), and the object record carries an
interaction state at `+0x08` that the use handler tests and sets (FORMATS.md
section 5), so a door that opens is that path. Whether the hidden ones are the
same mechanism or something in the level's own code is not known.

Worth checking against the collision opcodes that have never appeared in a log —
`0x25` (41 cells on level 0), `0x18` and `0x31`. A door that is solid until
pressed has to be solid *somehow*, and none of those three is transcribed.

## 6. Who branches on the story flags — done

`python3 tools/story.py quests` prints both ends. **43 flags are read by a
conversation** — through its `f1` guards or its `f9` — **26 are written by a
conversation hook**, and **15 are both**; those fifteen are the quest steps.
The writing end is entry 4 of a level's overlay, which the `0xf4` opcode
calls and which `tools/quest.py` reads arm by arm.

"no entity script tests or sets a flag" was the wrong corpus. A conversation
never writes a flag directly — `f7` does not occur anywhere in the 43 — but
78 `f9` and 18 guards read them, and `f4` is how a conversation asks the
level's own code to write one.

**What is left**: `story_flags` 93, 101 and 102 are not story at all —
`cutscene_step` and `level_overlay_tick` use them as phase state within a
single fade. Where the story part of the array ends is not settled.

## 7. Leftovers in the entity format

The container is read and the count corrected: **265 entities, 1617 blocks**,
sixteen pointers a record starting at `+0x38`, all dumped by
`tools/entities.py`. "3 to 8 scripts" counted from the wrong offset and
"the script bytes are transformed on load" was the same mistake seen from RAM
— block 0 is on the disc verbatim, and `entity_table_init` only turns the
offsets into pointers.

What is still open is the *first* byte of each block. Kind `0x70` is a
conversation; `0x00`, `0x02`, `0x03`, `0x06`, `0x13`, `0x18`, `0x19` and
`0x1a` are not, and nothing in `GAME.EXE` reads them.

KingsFieldRE documents a 124-byte entity structure for the first US game with
HP at `+0x1a`, dropped item at `+0x0b` and state at `+0x0e`. Our records are
definitions rather than live state, so it is a hint about the live copy at
`entity_table`, not about the disc format — see EXTERNAL.md.

## 8. The rest of the trigger graph

`tools/items.py` reads out everything the code decides directly: the three
inventory routines, the pickup rule that an object's type id is the item it
yields, and the six hardcoded use-item pairs in `0x8005cbe0` (see FORMATS.md
section 8). What is left is the data-driven majority — nine of thirteen
`take_item` calls take their id from a register, so the id is in the level's
records. Decoding those records turns the remaining conditions into a table.

## 9. Where the conditional logic actually lives

Two candidates have now been eliminated. The object parameter block does not
index the per-level table — withdrawn once the records were realigned — and
that table is not scripts at all but tile geometry, indexed by cell byte +8 and
read as fixed-point halfwords (FORMATS.md section 4).

What is left to look at: the 120-byte entity records in `FDAT.T` entry `3n + 1`,
and the object record fields, which already drive level transitions through
`+0x32..+0x3a`. Nine of the thirteen `take_item` calls take their id from a
register, so the ids are in one of those two.

## 10. The rest of the object parameter union

`+0x38..+0x3f` is settled for class `0x20` (gold) and partly for doors and
chests. The remaining classes, and the meaning of the object indices at `+0x3b`
and `+0x40`, are open.

---

## 11. What only a controller can settle

`emu/bp22.lua` arms nine breakpoints and every one is a reading nothing has
checked. TOOLS.md has the five numbered things to do in the game; in short:

* **the saved level record.** Both sides of it were read off the code and
  agree with each other, which after §4 is a weakness rather than a number.
  Pick something up and change level, and the `STATE` and `APPLY` lines are
  the stream itself.
* **the flat equipment bonuses.** `tools/equip.py` reproduces 16 of 16
  ratings from one snapshot. A second set with something else worn would
  settle the four bonuses that are read and unchecked.
* **the `0xf4` hook.** Sixty-two of them in the game and none has been seen
  run, though `tools/quest.py` now says exactly what each one does.
* **a guard or an `f9` taken.** Ninety-six branches in the conversation
  language, none yet seen taken in play.
* **the shop and the inn.** The arm of `script_interpreter` that runs when a
  talker's header `+0x12` is not `0xff`.

## Last: putting a translation back on the disc

**Lowest priority.** Nothing else depends on it, and reading the game is worth
more right now than rewriting it. Recorded here so the groundwork is not lost.

What it takes, and what we already have:

**The text is images, not strings.** Dialogue lives in `TALK.T` and `STALK.T`
as pre-rendered 4bpp TIMs, item and sign text in `ITEM.T`. Inserting a
translation means rendering new TIMs, not patching bytes. We can already read
all of it (`tools/ocr.py`, `tools/propocr.py`) and we have the three fonts
recovered as glyph templates, so the reverse direction is a matter of drawing
with them rather than of discovering anything.

**Every entry is checksummed, and a wrong checksum freezes the game.** This is
the trap that stopped earlier attempts at the King's Field games generally. The
algorithm, verified against our own disc by `tools/tsum.py`:

```
sum = 0x12345678
for each little-endian u32 of the entry, excluding the trailing checksum word:
    sum += word            (mod 2**32)
store sum in the last 4 bytes of the entry
```

The game's own copy of this routine is `0x80019b1c`, caught running over a
level as it loaded. `tools/tsum.py` verifies an entry and `stamp()` rewrites
the word after an edit. It matches every entry of `FDAT`, `ITEM`, `MO`, `MOF`, `RTMD`, `STALK`
and `TALK` — which is all the archives a translation touches. `RTIM` and `VAB`
are not checksummed.

**Entries are sector-aligned, so size is constrained.** An entry occupies whole
2048-byte sectors and the header is a table of sector offsets. A replacement
that fits in the same number of sectors can be dropped in place; a larger one
needs the offset table rebuilt and everything after it moved, which also means
rebuilding the ISO. `tools/tarc.py` reads the container; there is no writer yet.

**Prior art worth reading first:** the King's Field Texture Tool on
romhacking.net (utility 1063) does exactly this job for the other games in the
series, source included. See EXTERNAL.md.

## Where `object_type_table` is built — found

`FDAT.T` entry 97 at offset 4, behind a length word of 7200 = 300 × 24. All 300
rows match a level-0 snapshot byte for byte, and the table is the same on every
level. `tools/objops.py type_rows()` reads it and the port takes its class
bytes from there instead of from a snapshot.

The earlier note here said it was built at load time out of at least two
sources. That was wrong, and the way it was wrong is worth keeping: a 48-byte
search for one row hit a coincidental match in `FDAT.T` entry 1 first, and a
base derived from that one hit then agreed with 32 rows out of 819 — which
looked like partial evidence for a partial copy and was noise. The 819 was
wrong as well: the table is 300 rows, and the other 519 were whatever follows
it in RAM, read as type rows because the reader took `range(0x400)` on trust.

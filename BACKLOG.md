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
* **The save path -- read, and the card with it.** `OPEN.EXE` counts the
  saves on the card and passes the menu's answer in `overlay_arg2`;
  `read_overlay_arg2` (`0x8001fa60`) runs the list and `save_load_slot`
  (`0x8002860c`) reads the file, BOOT.md section 8. The file is three card
  blocks with the save buffer in them verbatim (FORMATS.md §15, "On the
  card"), and `tools/memcard.py` reads the emulator's cards, checked against
  the game's own `save_restore` and `save_serialise`. **The port loads them
  now**: CONTINUE lists the emulator's saves and puts one back (BOOT.md
  section 7). And a level the port leaves is remembered in the game's own
  stream: `godot/levelstate.gd` keeps a table of what `level_state_write`
  reads of each of the 396 slots -- the placement, the stream applied over
  it, the port's objects written in as the level is left -- and writes it as
  the game does (the self-test: 42 of 42 states written as
  `tools/levelstate.py` writes them, 46 of 46 tables read and written again),
  so the things a creature dropped, a key on a pedestal, a gate's lock and a
  door a key opened now last between visits, as in the game. What is left:
  the list is not drawn as the game draws it (`ui_panel` mode 8, `ui_prompt`
  kind 6); the port cannot write a save yet -- the streams are kept, the
  area's packing (`0x8001939c`) and `save_serialise`'s file are not made; and
  `save_loaded_fixup`'s bonus timers, `seq_state`, `map_seen_bits` and the
  two 150-byte tables are read and not used.
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

## 1. Cross-level teleport -- found, and in the port

The levels are pieces of one world and nothing marks a seam: an object of
opcode 0xe0 names a rectangle of cells, `object_trigger` starts the change to
its level block, and `level_load` shifts the world by the cells the placement
record names (FORMATS.md, "Walking from one level into the next";
`tools/crossing.py`, 2 of 2 crossings bp16 recorded). The port loads the other
level's world (`worldNN.tscn`, for each level `tools/level3d.py` has built) and
carries the player over (`godot/crossing.gd`); the comparison follows the game
into it. Left: what the other bytes of the block (0, 2, 3, 4) choose, the
level_state written for the level left, and the stairs (opcode 0xeb, which call
`level_load` themselves).

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

**Held to the game's own loader on all 28 levels** (FORMATS.md, the end of
"The first frame does more"): `tools/mipsrun.py` loads each level into a
snapshot by `load_object_placement` itself, and `tools/objload.py` is 4836 of
4838 records and every grid byte of it -- the two left are the level hooks'
(classes 0xa6, 0xa7). What the hooks (`level_hooks + 0x20`) do at load is
the one part of the loader not modelled.

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

## 4a. The sky, now that distance darkening is in

**Found and drawn.** It is a model: `render_walk` draws an object of class
`0xf0` -- type 265, model 44 of the resident bank, a dome -- on the eye and at
the back of the ordering table, while zones of class `0xe3` leave `sky_on` set
(FORMATS.md, "The sky"). `godot/sky.gd` draws it and follows the zones. Still
open: class `0xf2`, which level 4 places fifteen of (types 267 to 279) and
which `render_walk` also sends to `draw_model_at_eye` through `0x8018faf4` --
a backdrop of some other kind -- and what `0x801aeae9`, the zones' other byte
(13, 12 or 9), does in `view_matrix_build`. The note below was the plan for
the cue, kept for how it went:

What the port needed:
each vertex to carry its cell's lighting-class near and far (TEXCOORD_1 from
`tools/level3d.py`: the tiles' own cell, an object's or a creature's cell), and
every world material replaced at run time by one shader -- `godot/scroll.gd`
already swaps page 0x0f's and would become the general one -- that computes
`t = clamp((z - near) / (far - near), 0, 0x1f0f / 4096)` from the view depth in
game units, per face as the game does (a `flat` varying is the nearest Godot
has), and draws `texel * max(colour + t * (5/128 - colour), 0)`. It keeps the
scroll and the blend modes that file already sets. `tools/shots.py b` is the
check: the game's screenshot is black beyond the far wall.
`draw_model_lit` blends two records' near and far with `fixed_madd`; read that
before the objects get it.

## 4c. The models are culled, and the port draws them double-sided

`model_prims` (`0x80035ca4`) and `model_prims_lit` (`0x80038844`) both put each
face through NCLIP and drop it when the result is not positive (`blez` after
it, `0x80035e2c` and on), and the compass only reads right with that done
(FORMATS.md, "The compass"). `tools/level3d.py` makes every material
double-sided on the belief that the PlayStation does not cull -- which holds
for the tiles if `draw_tile` has no NCLIP, and is worth checking there -- and
turning triangles to their own normals was tried and made things worse. The
winding the GTE sees is the screen's, y down; a port of the cull would test
the same three points after projection.

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

1. **The wall slide — found, and it was a ramp's push.** `0x801e6498` and
   `0x801e649c` are written by the ramps (`0x30`, `0x35`) whose run is under
   `0x40`, and `player_horizontal` adds that push to any step it takes; the
   ceiling (`0x801e6478`) gates the step up. Both are in `tools/collision.py`,
   `tools/movement.py` and the port (FORMATS.md, "The ceiling, the push"), and
   rung 2 stands at 124 891 of 125 116 (the log has grown); 12 frames are
   still turned away at a wall where the game went on, and 20 of the newest
   session, at cell (10,26), the model walks into something solid it does not
   see -- the game stays at its height and is pushed back.
2. **The turn rate**, `0x8002fe1c`. The per-frame increment lives at
   `0x801b264c` and was seen ramping 0, 8, 16, 24, 32; the routine is unread, so
   the replay takes the facing from the game rather than deriving it.
3. **Objects and creatures are solid — done.** `collide_query`'s bit `0x20`
   is `object_collide`, bit `0x10` is `actor_spot_taken`, and
   `player_horizontal` slides along a rectangle or pushes out round anything
   else, the creature first (FORMATS.md, "Objects in the way"). 447 of the 455
   recorded frames that touch an object come out exact. The creatures have
   a recording behind them too: the first `bp16` session with `act=` ran into a
   logged creature on 76 frames, 76 of them exact. Not modelled: `+0xe == 3`
   (the port has no such state) and the follower's `+0x22` test. What moves
   the creatures -- the emulator's walk away and stand elsewhere, the port's
   stay home -- is the AI, now in the port (godot/ai.gd). A blow's knock-back
   is done too: tools/knock.py, 83 of 83 recorded frames, and player.gd's
   state 0x10 and 0x12. Left: the seven effects of a hit's +0x11 (poison and
   its kin), the armour and rings that cut an attack, and a death.
   **The creatures keep to their ground and face forward** now: the fence
   bit (a layer's byte +4 & 0x40) is a wall to their 0x93 and not to the
   player's 0x31, and they are drawn at yaw + 0x800. **They move their
   bodies** too: the vertex poses of tools/anim.py, 11 of 11 creature caches
   in the snapshots; godot/anim.gd. Left: the hit tint (+0x13, +0x14, +0x16)
   and the fade of the dying.
   **The player dies** as the game has it (state 0x11, the fade, a new
   character at the start); the crystal's revival waits on an inventory.
   **The machine against the recording**: `tools/ai.py --locked`, 8539 of
   8933 creature frames; the volley (0x19) scored and ticked. Left: the
   effects a volley launches -- the effect system, `effect_tick` -- and a
   bp16 session with the hidden fields to lock every frame. `emu/bp26.lua`
   records the effects: every live slot a frame, every `effect_spawn`, every
   hit on the player with its caller. Level 0's kind-3 creatures (model 57,
   cells (40,29), (26,27), (27,25), (15,20)...) cast effect 0x81/0x26 at the
   player through `actor_animation_effects` arm 0x26: spores that poison
   (FORMATS.md, "The spores") -- checked against bp26 and in the port. **The
   effect machine is in, byte for byte** (FORMATS.md, "The effect machine"):
   `tools/effects.py` holds 189 of 189 runs of the game's own `effect_spawn`
   and `effect_driver` slot for slot, and `godot/effects.gd` is the same
   machine; with it level 4's model-53 creatures throw their bolts (0x23,
   0x24), its model-67 ones and level 12's their darts and bobbing bolts
   (0x22, 0x1f), with the puffs they leave (0x6f), aimed by `effect_aim` (600
   of 600). Left: the other arms -- 0x20, 0x21 and 0x25 of the same volley
   arm on later levels, the `0x8004` list entry, then the player's own magic;
   `player_take_hit`'s effect arms 1 and 2 (the darts' and the bobbing bolts'),
   which the port does not run; the creatures' half of
   `effect_strike` (`0x8004ceac`); the drawing's matrices (+8 & 0xc), view
   test and light; and a recording -- bp26 on level 4 by a model-53 creature
   -- to hold the bolts' strikes and the damage to what the game did.
   **The player hits back too** (tools/weapon.py, godot/weapon.gd): the swing,
   the probe, the damage, the flinch, the dying and the push -- checked against
   `emu/bp25.lua`'s recording (817 of 817 frames). The weapon in the hand is
   drawn too (`godot/held.gd`, FDAT entry 0x62 + the weapon, animated by the
   swing), and a death leaves its gold and its thing, which fall and can be
   taken (FORMATS.md, "What a dying creature leaves"). The bows (0x1b, 0x1c)
   are in (FORMATS.md, "The bows"). Left: the spells a swing can carry (+3,
   +4), phase 1, the lighting class
   the hand is drawn with, and the dying creature's fade (+0x16, which the
   dying arm moves by 0x200 a frame either side of the clock's 0x800).
4. **The door shoves the player — found.** The X writes `emu/bp15.lua` caught
   at `0x800482e4` are the swinging door (opcode 1, `0x8004814c`): while it
   opens and the player is in its sweep it adds (0, 0, -0x4c) turned by its
   yaw + 0x800 to the position, sets `player_speed` (`0x801b2648`) to -0x4c
   and the strafe speed to 0. `godot/doors.gd` does all three; the replay
   counts the frames near a door apart (140 on rung 2).

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

*Since:* the speed cap is not a stat. `player_controller` writes 200 into it
every frame (`0x80031180`) and then changes it four ways only: **the run** --
USE held two frames, up to 336 (FORMATS "The run: USE held"; 150 129 of
150 129 logged frames, in the port as `frame_caps`) -- the slowing
(`turn_slow_timer`), the paralysis (`0x801b2568`) and a halving while
`0x801b25b4` is set -- Seath's sword's guard, set by `held_item_tick`
(FORMATS.md "The weapons' spells"), in the port now too. A faster walk
"as the character levels" would be the run, then.

## 5a'. The menu -- begun

`pause_menu` and its "use item" screen are read and in the port
(FORMATS.md, "The menus, as they are drawn"): `tools/ui.py` reproduces the
game's frames of the screen primitive for primitive (`inv1`, `inv2`, read by
`tools/gpuframe.py`), and `godot/menu.gd` draws what `tools/ui.py` draws.
Eating heals. Left, roughly in order:

* `ui_status_page` (`0x800227ec`) is in and holds: `menu1`'s frame is the
  model's, 428 of 428 primitives;
* `use_item` (`0x8005cbe0`) is whole in `tools/useitem.py`, held to the
  game's own over every level (2800 of 2800 runs), and in the port
  (`godot/useitem.gd`, the self-test 336 of 336): the truth glass, the flask,
  the figures, the keys, Silviera's key, Orladin's key, `0x80`'s 900 frames
  (FORMATS.md, "A thing used"), and the warp Ichrius' eye, wings and crown
  ask for (`warp_to`, FORMATS.md "The warp", 280 of 280 runs of the game's
  own; its fades in the port too, the flash to white and back -- FORMATS.md
  "The screen's fade", the game's own quad 840 of 840 and fade_frames 40 of
  40 -- but not for `cutscene_step`'s record `0xc` or `level_overlay_tick`'s
  `0xd`; `0x801b25ee`, which it sets, is read
  nowhere the walk finds). Left of it: block 6's two statues (`0x80` there runs a scene of the game's frames until a
  creature wakes); the level's own entry 2 of levels 4, 8 and 17 (scenes)
  -- 1, 2, 5, 7, 20, 23, 25 and 27's are in (FORMATS.md, "The levels' own
  use of a thing", 2800 of 2800; levels 1 and 2 hand a thing to a creature,
  which then talks, and level 2's opens its gate through `object_signal`),
  but for what opcodes `0x53` and `0xa7` then do with level 5's objects and
  level 7's pedestal -- and give_item's and take_item's entries 6 and 11.
  Every level's conversation hook (entry 4, 45 arms) is in (FORMATS.md,
  "What a conversation makes happen", 2400 of 2400 runs of the overlays'
  own), but for what the port does not act out: the light's frames
  (`0x8005d948`, `0x8003da10`) of levels 6, 8 and 17, level 3's pack chooser
  (`0x80021d94`, `ui_panel` mode `0xc`; the port answers nothing chosen),
  level 0's play clock (not kept by the port), objects switched by `+0` or
  their scale (level 5's opcode-`0x56` ones and level 17's 63, drawn in the
  level's one mesh), the tile a `stamp_rect` copies, and object_give's frames
  inside the conversation's call (the port flies the thing after it). The
  levels' entry 5, which `level_load` runs as each level comes in, is in
  (FORMATS.md, "What a level does as it comes in", 1120 of 1120 runs and 21
  of 21 snapshots' categories), but for the looks' routines of levels 4, 6
  and 26 (`0x801e83a4`, `0x801e83a8`, `0x801e8390`, tables of `0x8008xxxx`:
  not read), the bytes the port does not keep, the static objects' view byte
  and level 17's thing of type `0x8f` in the ring.
  What Orladin's key opens is in (FORMATS.md, "What Orladin's key opens"):
  the seals (opcode `0x17`) and what they lift (`0x10`), the pedestals
  (`0x1a`) and the key's own object in the gold ring, held to the game's own
  arms (`tools/seals.py`, 7600 of 7600 and 3240 of 3240 frames) -- but for
  their fade, which the port does not draw: `+2`'s semi-transparency and the
  lighting class `0x32` the model is blended towards by `+0x10`
  (`draw_model_plain`); no recording has a seal in it (PLAYTEST.md). No recording has a
  thing used yet: `emu/bp20.lua` logs the thing, the place, the floor, the
  page and the answer now (PLAYTEST.md);
* the chosen thing's model turning in the lists (`0x80025be8`), and the
  maps and notes (95..100); the guide is in (FORMATS.md, "The guide");
* "equipment" is in (FORMATS.md, "The equipment screen") but for its MAGIC
  and BUTTON lines (`0x8001d0c4`, `0x8001d3a0`), the thing's turning model
  and the guide; a bow in hand (weapons `0x1b`, `0x1c`) draws and looses
  its arrows (FORMATS.md, "The bows"). The screens hold against `equip1`..`equip4`, 8 of 8 frames;
* "status/records" is in but for its CONVERSATION line (`text_pager`,
  `0x8001d944`); "use magic" is in but for its guide (FORMATS.md, "USE
  MAGIC"), and "storage" but for the guide and the turning model
  (FORMATS.md, "STORAGE"); of "system" (`menu_system`) the page and BUTTON
  CONFIG are in (FORMATS.md, "SYSTEM"), and LOAD but for its boxes
  ("checking", "loading", the failures) and the directory's order (FORMATS.md,
  "LOAD"); not the music's fade in QUIT
  GAME's "please wait"; QUIT GAME itself is in (FORMATS.md, "QUIT GAME"). OPTION 2 is in
  (FORMATS.md, "OPTION 2"), and OPTION 1 but for the sound it plays and
  the music's volume (the brightness reaches the menus' text, not yet the
  panel's sprites, which render_frame colours by it); OPTION 2's third switch, the lists' turning model, is
  kept and does nothing until the model is ported. Neither the schemes nor
  the five display bytes are carried by a save in the port: `save_restore`
  writes `0x801b25dd..e0`, and `save_loaded_fixup`'s `apply_control_scheme`
  is one of the things its marker says it leaves out;
* the shops and the inn are in (FORMATS.md, "The shops", "The inn"), but
  for the inn's night the moves of player states 7 and 9 into and out of the
  scene's place, and the rest of `cutscene_step`'s machine (the scenes with
  movies of their own, `\STR\S04..S15`, and the gates on story flags);
  service `0x30` (`0x80021aac`, which opens when the wise fruit's count is
  4) is not;
* `pad_read_latch`'s repeat while a direction is held -- the port reads new
  presses only.

## 5b'. Chests, and what is in them -- in the port

The lids (opcode 6), the big chests (opcode 7) and `object_give` are read and
in the port (FORMATS.md, "Chests, and picking things up"): USE opens a chest,
its lid springs open, and what is inside or on the floor flies to the eye and
is taken or put back; gold is counted. Seven opened lids in the snapshots lie
on the lid's path. Left:

* **the trap**: a lid whose `+0x3c` is not 0xff (level 0's slot 168) spawns
  effect `0x83`/`0x23` at the player every frame it opens, aimed by
  `0x80046dcc` -- neither is read;
* **`+0xe`**, which the flight and the big chest move and `draw_model_plain`
  takes as its argument `0x30` -- by its use, the model's light; not read;
* **`object_give`'s special cases**: types `0x86`, `0x88` and `0x8d` with
  opcode `0x70` wait on another object's state (`+0x40`, then that one's
  `+0x3b`), and type `0x85` on level 7 on the facing; and a call with no
  object, which spawns one in front of the player -- the overlays' way of
  giving things;
* **what class 9 hides**: 24 things on level 0 are taken away on the first
  frame by opcode 9, and nothing in GAME.EXE calls `object_mode` to bring
  them back -- the level's own code, or a creature's death, presumably;
* **a recording**: nothing here has been checked frame by frame against the
  game; a bp script on the lid's arm and on `object_give`'s loop would. The
  drops (FORMATS.md, "What a dying creature leaves") lie in three snapshots as
  the model leaves them, which is consistent but not a frame-by-frame check;
  the splash a falling thing makes where it crosses the water
  (`sub_80056268`) and the layer it writes to its `+0` are not in the port.

The signs (classes `0x0d` and `0x14`) are read with USE too: `load_entry`
shows the ITEM.T page as the game does (`godot/document.gd`), and so are the
conversations -- one call of `script_interpreter` a USE (`godot/talk.gd`,
FORMATS.md "A conversation, one USE at a time"). Left in them:

* **the services** at the end of a call, by `+0x12`'s high nibble:
  `sub_80021114` (entity 6 on level 0 has 1), the shop (`0x30`,
  `sub_80021aac`), a scene (`0x40`, `sub_8002200c`, entity 7);
* **the animation**: the first line starts the talker's (`+1`, `+8`), the end
  its end one (`+0x11`, `+0xe`), and `seq_lookup` the voice;
* **level 0's entry 4 arms 2 and 4**, which read the play clock
  (`0x801b2588` over 60, `0x801b24e4`), and arm 1's unequipping of the sword;
  the other levels' hooks;
* **the speaker test**: an actor's `+1` is its model, so two talkers sharing
  a model would count as one; level 0 has none.

## 5c. Doors that open, and the ones that are hidden

**The swinging doors are read and in the port** (FORMATS.md, "A door that
swings"): class 0x01, 42 in the game, nine on level 0 -- `godot/doors.gd` opens
them with USE, swings them, stamps the doorway's collision open and closed and
waits while the player stands in it. What is left, in order of how many doors
it would open:

* **class 0x02, 128 objects -- read and in the port** (FORMATS.md, "A gate"):
  level 4's walls among them. The lift's rise, with `stamp_rect` laying the
  doorway down from three templates (open, moving, shut) and the fence bit
  with them; USE opens a lock of 0xff (0xfd, 0xfe but for type 0xae), a lock
  odd and in 0x96..0xc6 opens of itself for good. `godot/doors.gd` holds to
  `tools/doors.py gate_step`, 360 of 360 frames, and gate_step to the game's
  own arm run over silv1 by `tools/mipsrun.py`, 520 of 520 -- no recording has
  a gate in it yet: a bp27 session on level 4 opening gate 96 (cell (38,23))
  would show who holds a doorway in play. The pedestals that set the other
  gates' locks (opcode 0x18) are in too (5a', the keys).
* **the lift doors, classes 0x03 to 0x05 -- read and in the port** (FORMATS.md,
  "A door that lifts"): five on level 0 and one on level 8, all six in the game
  as `tools/objload.py` reads the twelve levels. Shut, each is a stretch of
  wall the grid draws; its arm swaps the wall tile for its animated model,
  lifts it 57 frames, stamps the doorway passable at 0xc18, stands eighteen
  frames, waits for the doorway to clear and drops. `godot/doors.gd` does all
  of it, with the door's cells as a node of their own. Against `emu/bp27.lua`:
  3528 of 3528 steps, and the doorway test against the game's own answers --
  the player 1078 of 1078, the creatures 457 of 457. Who holds a door shut
  out of the player's reach is settled: the two creatures of kind 4 that live
  behind doors 51 and 123 (slots 15 and 7).
* **class 0x54, the hidden wall -- read and in the port** (FORMATS.md, "A
  hidden wall"): level 0's opens when the player steps onto the strip two
  cells west of it; held to the game's own arm over a1 (`tools/mipsrun.py`),
  140 of 140 frames. What else levels 0 and 4 place is read too (FORMATS.md,
  "What else levels 0 and 4 place"): level 0's traps never run, 0xe6 is a
  depth bias and 0x1f an ambient sound -- nothing for the port -- and the
  0xe1 triggers call the levels' own entry 3, which is not in the port.
* **classes 0x00 (12) and 0x1b (23)**, `find_object` points 0x700 in front of or
  behind them; 11 of the 12 class-0 doors carry lock byte `0x8c`, a key.
* **keys -- in**: a lock byte other than 0xff, 0xfd or 0xfe is either the
  number of the key that opens it or a code no key is. A locked chest says
  "Locked", and the right key from the menu sets its lock to 0xff
  (FORMATS.md, "Keys"; `python3 tools/chests.py --keys`).
* **a frame-by-frame check -- done**: `emu/bp24.lua` recorded two cycles of the
  door at (41,10) and `tools/doors.py` reproduces 226 of 226 steps. What it
  cannot see is the shove, which moves the player in the same frame the player
  moves itself; a `bp16` session opening a door would hold that.

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

## 12. The port against the game

Every function in `godot/` now says what it is in the game (AGENT.md, "The port
and the game, one to one"; PORT.md the table). The pass that put the markers on
read each function against the code it names, and this is what it left open --
each one is also in its function's marker, as `partial` and what differs:

* **`player_recalc_stats` reads one thing the port does not keep**: the
  story byte `0x801ba9e9`; `player.gd` passes 0 for it. The curse's level is
  kept now (a hit's effect 1, `status_tick`), and the three bonus timers come
  off a save, though nothing in the port starts or counts them down yet --
  the spells that do are not read. The routine itself is whole (`equip.gd
  recalc`, 299 of 299 values).
* **What a hit leaves is whole; one of its inputs is not.** `0x801b25b4`,
  which lets no hit through and halves both of the walk's caps, is Seath's
  sword's guard: `held_item_tick` sets it when the combination's swing meets
  its blow with the action button held, clears it on every blow, and
  `equip_weapon` clears it (in the port, `guard`). `0x801b256c`, the other way out, is the
  refusal spell's timer. The lighting's background colour moves now (the
  vertex colour's alpha carries the class's; FORMATS, "What a hit leaves
  behind") -- untested by eye: the port's shaders compile only in a window.
* **`give_item` and `take_item` call the level's own hook** after the count
  changes (`level_hooks+0x18`, `+0x2c`); `godot/items.gd` does not.
* **The timers across a crossing -- fixed.** `player.gd carry_over` took the
  pack, the figures, HP and MP, the meters, the poison and the floor, and
  left the bonus timers, the curse, the dark and the light behind. The walk
  says the change of level writes nothing of the player's block but the
  place and `spawn_anywhere` (FORMATS.md, "What a change of level keeps"),
  and the port carries every field it keeps now. What the game does that
  the port cannot is the hundred-odd frames the load takes, through which
  the player and the timers run on; the port's load is at once.
* **`new_character` does much more than `KFLevels.fresh`**: the gold, the
  equipment slots, the place and the spells.
* **The movie's skip.** `godot/cutscene.gd` uses `OPEN.EXE`'s rule for
  GAME.EXE's `str_play`, whose own pad test sits in one of its unread
  sub-routines. And `play_movie` (`open:0x80013960`) tests START and the face
  buttons *held*, where `opening.gd` and `cutscene.gd` wait for a new press.
* **`actor_start_anim` adds 2** to the animation while `0x80199150` is set for
  the actor at `0x80199148`; `ai.gd start_anim` does not.
* **The effects are drawn without `render_walk`'s view test** (`+8 & 3`,
  `view_bits_at`), so a spore in a cell the game would not draw is drawn.
* **The "Program Loading" card's rectangle** in `opening.gd` was not checked
  against the primitive `open_main+0x3e4` fills.
* **A hit with no point on a kind with behaviour 0x16.** Bortecth hands
  `actor_attack_player` no point, and `actor_take_hit`'s spell path then
  reads the bearing from address 0 for a kind that has a behaviour 0x16;
  `actors.gd take_hit_flags` skips the test with no point. No kind in the
  snapshots has one.
* **One routine, several copies.** `in_range` is written three times
  (`collision.gd`, `doors.gd`, `actors.gd`), `facing_test` and
  `kind_behaviour_with_op` twice. Each copy is marked, and the self-test would
  show one drifting; folding them into one is a refactor nobody has needed yet.

* **What creatures throw: in, but for one arm.** `actor_animation_effects`'
  arms and the kinds only creatures throw are read and in the port
  (`effects.gd volley_fire`, FORMATS.md "What a creature's volley
  throws"), against the game's own, the lob and its arrows (0x50..0x53)
  and the charge (0x55, levels 17 and 26) among them; 0x76 (a creature
  made, `sub_8004b524`, `actor_wake`) is not read, and no creature's record
  names it. And the 0x8004 entry, a point along a limb pulled towards the
  player. The charge's loose ends: the branch for a creature that left its
  volley while it held one (gone) is read, never run; an 0x8002 entry's
  vertex is -1, which `model_vertex` reads before the table (no list does
  it; the port puts it at the place); `sub_800562f0`'s other modes (the
  head's vertex, a random spread, a still puff) are not in; and the port
  turns a creature's vertex by its yaw alone and one scale.
* **The player's step the lob leads by** (`player.gd step`, 0x801b2600):
  read off `player_horizontal` and `player_vertical`, written where they
  write it, but no recording has the word -- the lob's checks draw it at
  random. A bp log of `0x801b2600..0x801b2605` beside the position would
  hold it.
* **Casting is in, and what it casts.** `player.gd` has the
  buttons, `cast_spell`, the pending action, `skill_practice`, the USE
  stretch, the timers and the attacking arms (the aim, the creature in
  sight, the spawns), all held to the game's own code, and the effects of
  the fire ball, stone, wind cutter, haze, shudom (and its rings, 0x5e) and
  walwind (and its waves, 0x59), earth wave and bortecth (and its hold,
  0x65, with `actor_tick`'s held flinch and death), meteor (and its blast,
  0x5a, and its lead's tile test), orladin (its bursts, 0x58, and rays,
  0x5b), tornado, fire wall, fire storm (homing: `effect_home`,
  `effect_steer`) and flame (its head's vertex, its fire balls, its two
  bursts), flash (homing: `effect_seek`), lightning (its bolts and their
  spheres, and the earth wave it leaves), freeze and thedek (their trails,
  the hold, thedek's blades) -- every attacking spell -- with `effect_strike`'s creature
  half (`0x8004ceac`); and the weapons' charged swing -- the window, the
  shots, `weapon_may_cast` and
  `spell_begin` -- the combination and the second swing it starts, with
  Seath's sword's guard and the flame rod's fire ball, all held to the
  game's own (`tools/weapon.py`, `magic_check`), and the story flags 39 and
  45 unlocking their spells in `equip_weapon`. The bows (weapons `0x1b`,
  `0x1c`) draw and loose their arrows, held to the game's own the same way
  (`bow_runs`, 1688 of 1688 frames) -- but for the sound 0x60 at full draw,
  which the port does not play, and the view's angles: `held_item_tick`
  reads `0x801b2608` as `camera_pose` last left it, the port the view as it
  draws it this frame; no recording has held a bow yet (PLAYTEST.md).
  Not yet:
  `sub_8004eee0`'s arms for a creature whose `+0x28 & 3` is not 0 (freeze
  and thedek take hold by it; none in the snapshots, so the port turns
  kind 2's mark by the yaw alone); tornado's and fire wall's strike points, stack
  leftovers the first reader of a frame takes from the rest of the game's
  frame (FORMATS.md, "Tornado", "Fire wall"), and flash's second burst,
  whose life is one (FORMATS.md, "The weapons' spells") -- the port keeps
  the words the effects leave, not what the rest of the game's frame writes
  there; `effect_seek`'s other half, `sub_8002b80c` (an effect not the
  player's looking for the player), not read; creatures a model's vertex
  places (flag 0x400000) in `actor_spot_taken`; in the port's
  `actor_take_hit`, a part passing its hit to its actor and a follower's
  push handed to its leader (the healing and protecting six are in), the
  drawing of everything with `+8 & 0xc` set -- the protecting marks and the
  sparkles, in front of the eye -- of the weapons' magic, the sounds (every
  spell's effects are in now, the excellector's, triple fang's, dark
  slayer's, the moonlight swords' and `0x3c` the last; nothing has checked
  them in play: `emu/bp28.lua`, PLAYTEST.md). The button's thing is in
  (`0x8002ff28`, 1260 of 1260 runs of the game's own stretch). The equipment screen's MAGIC and BUTTON lines are in
  (light goes on the button: magic A lists the attacking spells alone); not
  their guide page or the spells' sound banks.

**Found later, and fixed: shape 255 is the void, not nothing.** Every
empty cell carries it, and the tools and the port answered nothing there;
`tile_collision` reads the level's last shape for it, a floor 32000 above the
cell -- everything in an empty cell is under the floor. A bolt flying into
one showed it (FORMATS.md, "Shape 255 is the void"); nothing the player does
reaches one, so no number changed.

**Found later, and fixed: a chest opened and left full hid its thing on
the next visit.** The rows `tools/level3d.py` wrote for what a chest holds
were the first frame's -- hidden -- and the port ran that frame again; a
chest the level's record says was opened hides nothing in the game, so its
thing lay there to take, and the port kept it hidden. The rows carry the
loader's `+0` and `+0x38` now, and `loot.gd` runs the first frame after the
record (FORMATS.md, "What Orladin's key opens"). Orladin's seals take the
same path.

**Found later, and fixed: a death reloaded the level in hand.** The game
loads level 0 after a death either way -- `level_state_writer(0, ...)` at
`0x80031e70`, after the crystal's `level_state_write` for the level left or a
new character's `reset_story_flags` -- and the port reloaded whatever level
the player died on, so a revive on level 4 stood the player at level 0's
crystal spot in level 4. It loads level 0 now, and the new character's path
clears the levels' records and the flags, and sets flag 9, as the game does.

**Found later, and fixed: every level but 0 ran level 0's creatures.**
`actors.gd` reads `actorsNN.json` and `aiNN.json` by its own `level`, which
nothing ever set -- the scene does not -- so on level 4 the port took level
0's 58 creatures, kinds and homes, and laid them over level 4's 41 nodes by
slot. It reads the level in hand off `KFGame` now: a headless run of
`world04.tscn` has 41 actors, every one with its node (before: 58, level 0's).
Nothing compared the port's level-4 creatures with anything, which is how it
lasted; `tools/ai.py`'s level-4 numbers are the Python model's.

Settled in the same pass rather than listed: a copy of `in_oriented_rect` in
`objcoll.gd` that nothing called, with arithmetic that was not the game's
(removed -- `collision.gd` has the faithful one); `_tick` and `_spring` in
`player.gd` carrying the markers of routines they only call; the names
`ai_driver` and `flag_gate` in `game.gd` and FORMATS.md, both withdrawn from
the symbol table long ago; a pointer misread as `0x801f825c` in
`cutscene.gd` (it is `0x801e825c`); and two steps of `game.gd`'s frame map
marked as not ported that are.

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

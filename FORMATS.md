# King's Field II (SLUS-00255) — recovered formats

Everything here was derived from the disc and from live RAM, or taken from
elsewhere and then checked against them. Each claim notes how it was
established, so anything marked *unverified* is a working guess.

Units: `u8/u16/u32` little-endian, `s32` signed. Addresses are PlayStation
KUSEG (`0x80000000`+). Offsets into RAM snapshots are `addr & 0x1FFFFF`.

Companion files: [TOOLS.md](TOOLS.md) is how to run any of this,
[BOOT.md](BOOT.md) follows the call tree from the entry point through the
logos, the title menu and the buttons, [EXTERNAL.md](EXTERNAL.md) holds what
other projects published and how much of it we have been able to confirm here,
[BACKLOG.md](BACKLOG.md) the open threads, and `data/symbols.json` a name and
the evidence for every address below.

**Addresses in this file are `GAME.EXE`'s.** `OPEN.EXE` and `END.EXE` load at
the same `0x80011000` and their names live in `data/symbols_open.json` and
`data/symbols_end.json`; see BOOT.md section 1.

---

## 1. The disc

| Property | Value |
| --- | --- |
| Image | CloneCD `.ccd` + `.img` + `.sub`, one MODE2/2352 track |
| Sectors | 243 098 × 2352 bytes |
| User data | 2048 bytes at offset 24 of each sector (Mode 2 Form 1) |
| Filesystem | plain ISO9660, PVD at sector 16 |

`emu/kf2.cue` describes the image as `MODE2/2352`; PCSX-Redux would not boot
from the `.ccd` directly but reads the `.cue` fine.

Reader: `tools/psxiso.py`.

### Files that matter

| Path | Size | Contents |
| --- | --- | --- |
| `SLUS_002.55` | 4 KB | boot loader; holds the strings `cdrom:OPEN.EXE;1`, `cdrom:GAME.EXE;1`, `cdrom:END.EXE;1` |
| `OPEN.EXE` | 192 KB | opening sequence, loads at `0x80011000` |
| `GAME.EXE` | 560 KB | the game, loads at `0x80011000`, entry `0x800144f8`, text `0x8b800` |
| `CD/COM/*.T` | 9 archives | see below |
| `END.EXE` | 156 KB | the ending, loads at `0x80011000` |
| `CD/COM/*.T` | 9 archives | see below |
| `OP/OP.D` | 168 KB | the title screen: five TIMs and a VAB — BOOT.md section 3 |
| `OP/L0.S`, `L1.S` | 2.9 MB | the ASCII and FromSoftware logos, as MDEC video |
| `OP/M0..M3.S` | 118 MB | the attract movies, the opening story, and the title music |
| `OP/M4..M6.S` | 91 MB | `END.EXE`'s three |
| `STR/S03..S15.S` | 190 MB | thirteen in-game cutscenes |
| `DRM/D00..D17.S` | 18 × 1.5 MB | eighteen more MDEC streams, 320×240, nine sectors a frame |

`extract/` holds only `/CD` and `/DRM`; `/OP` and `/STR` were never unpacked,
so anything that reads them goes to the disc image through `tools/psxiso.py`.
All 28 `.S` files are Sony STR — `tools/str.py` lists and decodes them, and
BOOT.md section 4 has the two version differences that matter.

---

## 2. `.T` archive container

```
u16          entry count N
u16[N+1]     start offset of each entry, in 2048-byte sectors
             (entry i spans sectors off[i] .. off[i+1]; equal values = empty slot)
```

Verified: for all nine archives `off[N] * 2048` equals the file size exactly.

| Archive | Entries | Holds |
| --- | --- | --- |
| `ITEM.T` | 970 | 613 TIMs + 150 TMD models: icons, descriptions, biographies, signs |
| `TALK.T` | 848 | dialogue, as pre-rendered TIM images |
| `STALK.T` | 883 | the same script in a smaller face |
| `MO.T` | 428 | object models — **indexed by object type id** |
| `MOF.T` | 992 | second model set |
| `FDAT.T` | 132 | level data, three entries per level |
| `RTIM.T` | 43 | **a level's textures**, 28 entries of VRAM upload blocks — `tools/rtim.py` |
| `RTMD.T` | 32 | **the tile models, one TMD of 240 objects per level** — `cell[+5]` picks the object |
| `VAB.T` | 594 | `pBAV` sound banks (111), `pQES` sequences (23) |

Reader: `tools/tarc.py`.

### `ITEM.T` index map

Ranges found by decoding the text. The index doubles as the global object-type
id (see §5).

| Range | Contents |
| --- | --- |
| 0–169 | mostly small data, few images |
| 150–196 | shop boards, inn signs, NPC nameplates, road signs (proportional font) |
| 230–269 | "examine" labels for world objects (tombs, statues, bodies) |
| 270–313 | character biographies |
| 320–386 | bestiary entries |
| 390–755 | item icons, item stat lines, item art |
| 788–806 | item lore text |
| 810–851 | 42 area names (`Quist` … `Seath's Space`) |

---

## 3. Text is stored as pictures — except the item names

Every string the player reads is a rendered image and this document is mostly
about decoding them. **The item names are not.** They are 150 rows of 24 bytes
at `0x8007f620` in `GAME.EXE`, in the plainest encoding there is:

```
0x00..0x19   a to z
0x7f         a space
0x32         an apostrophe      "seath's sword", "ichrius' key"
0x33         a hyphen           "ryu-ga"
0xff         the end
```

All 150 decode without one unknown code. `tools/itemtext.py names` prints
them, and nineteen are a single `a` — unused ids.

This was found from `0x8001af88`, the routine that builds the inventory page:
it walks the item array and indexes this table by the id. The OCR that has been
reading item names off pictures since this project started gave item 0 as
*"Excel Iecor"*. It is **`excellector`**. Item 104, the herb a player picked up
in the recorded session, is **`earth herb`**; 107, the one that stops a death,
is **`dragon crystal`**; 109 is **`moon stone`** and 141 is
**`silviera's key`** — which is what the player said they had picked up.

The *descriptions* are still pictures, in `ITEM.T[390 + n]`, and everything
below still applies to them.

## 3.1 The picture faces



No game string is ASCII. Dialogue, item text and signs are all pre-rendered
TIM images, which is why `strings` over the disc finds nothing but the Sony
library. Three typefaces are in use.

### Dialogue face — fixed grid (`tools/ocr.py`)

* character advance exactly **7 px**; the first column of each cell is the gap
* line pitch **16 px** in `TALK.T`, **14 px** in `STALK.T`
* the vertical origin varies per image, so cells are anchored on the **cap
  line** — the row, modulo the pitch, carrying the most ink
* images are dithered 4bpp, so no two instances of a letter share a bitmap:
  cells are classified against labelled templates by **Jaccard distance**,
  not hashed
* `I` and `l` are pixel-identical; they are separated afterwards against
  `/usr/share/dict/american-english`

81 glyph templates, seeded from one screen read by eye and grown from whatever
the current font could not explain. Result: 419 of 16 180 words fall outside
the dictionary, and all of them are proper nouns.

### Display face — proportional (`tools/propfont.py`, `tools/propocr.py`)

Used for item names, signposts, shop boards and gravestones, in a 9 px cut and
a 13–15 px cut. Glyphs are cut apart at blank columns; kerned pairs such as
`of` share one box, so seeding aligns a known string across the boxes with a
DP that lets one box swallow up to three characters.

---

## 4. `FDAT.T` — level data

Three consecutive entries per level, levels 0–27 at entries 0–83. Entries
84–95 are four empty triples; 96–131 hold something else.

### Entry `3n + 0` — the grid

```
u32          0x0000FA00  (= 64000, the size of the grid block)
u8[64000]    80 × 80 cells of 10 bytes, row-major: index = (z * 80 + x) * 10
u32          total size of the tile-shape block
u16[254]     offset of each tile shape, from the start of this table
...          the shapes themselves, variable length, 14 to 44 bytes
```

**These are tile shapes, not event scripts.** They had been recorded as scripts
with undecoded opcodes; they are neither. Cell byte +8 is the index into the
offset table: across all 28 levels every distinct value of that byte falls
inside the set of populated entries, 188 of them on level 0 alone, with not one
miss. Cell byte +5 misses heavily against the same set, so that one really is a
texture id and +8 is not.

The reader settles what the shapes are. At `0x800326d8` the game takes the
index byte, doubles it, reads the offset, adds it to the table base and then
walks the record two bytes at a time, feeding each halfword straight into
fixed-point arithmetic (`mult` then `sra` by 12, so 0x1000 is 1.0). Geometry,
consumed by a routine at `0x8003260c` full of the same fixed-point work.

Cell layout:

| Offset | Meaning | How established |
| --- | --- | --- |
| +0..+4 | a second layer with the same five fields, `ff 00 00 ff 00` on **every** cell of **every** level — its own shape id at +3 is always `255`, so the layer is simply absent | checked across all 28 levels |
| +5 | wall/surface texture id, `255` in solid rock | correlates with +8 |
| +6 | **floor height** | see the height relation below |
| +7 | orientation of the step face, 0–3 | `level_load` masks every cell's +7 and +2 to two bits (§16) |
| +8 | **tile shape id**, indexes the 254-entry table; `255` means no tile | matches the populated entries on all 28 levels with zero misses |
| +9 | flags; bit 6 (`0x40`) marks a cell carrying a vertical face | appears exactly along height changes |

**World Y = −128 × height byte.** Verified against live objects: height 100 →
`-12800`, 90 → `-11520`, 117 → `-14976`, exact on 83 % of objects.

**World X/Z = 2048 × cell.** The grid is indexed `[z][x]`; orientation was
confirmed by scoring every level and every flip against the height relation —
level 0 in plain `(x, z)` scored 82.9 %, every alternative ≤ 38.6 %.

Community maps are drawn **north up**, which is this grid with Z flipped; the
renderers do that flip for display only.

### The shapes are programs, and they carry the walls

A shape is not geometry but a **third bytecode**. `tile_shape_reader` fetches a
halfword, subtracts `0x10`, bounds it at `0x31` and dispatches through a
49-entry table at `0x80011b0c` — the same design as the entity scripts and the
level-state stream.

```
header   u16 u16   two values
         u16       0x1000, the fixed-point 1.0 this game uses throughout
         u16       how many instructions follow
```

Shapes **overlap**: one often runs past where the next begins, so the count is
what ends it and reading them by the gap between offsets fails on all 2351.

Every drawing instruction carries a **face direction** — the handler adds one of
its operands to the cell's own orientation byte and masks to two bits. For
`0x20` that is `(operand[3] + cell[+7]) & 3`; the others do the same at their
own offsets. Direction maps to a neighbour as `(1, 0, 2, 3)` against `+x, +z,
-x, -z`.

### The routine is collision, and the map is hand-drawn

Two things came out of chasing the discrepancy, and both matter more than the
answer that was wrong.

**`0x8003260c` does not draw anything.** Its face handlers compare each operand
against the player's position masked to `0x7ff` — the fraction of a cell — and
on a hit they write a struct at `0x801e6470` and set a bit in a running mask.
That is **collision**: what the player may walk through. Renamed
`tile_collision`. So the faces it reads are collision surfaces, which overlap
what a map draws without being the same thing.

**`ITEM.T` 721 is an image an artist drew.** It is a TIM in an archive, not
something generated from the level. It was good enough to settle orientation —
the Z-flip scores 72 % against 23 % for every alternative, and no stylisation
would produce that — but it cannot be ground truth for individual edges, and
comparing a mechanical extraction to it pixel for pixel was the wrong test.

The 12 % agreement therefore does not show the decode is wrong. It shows the
oracle was.

### Which instructions are walls, settled

**Settled, and reproduced exactly.** `0x20`, `0x21`, `0x22`, `0x24` and `0x23`
are walls; `0x10`, `0x30`, `0x32`, `0x33`, `0x34` are floors; `0x11` is a
ceiling. Not inferred from how the maps look — transcribed from the handlers and
then checked against the game's own answers: of the 4264 logged calls carrying
the fifth argument, `tools/collision.py` reproduces the mask on **all of them**.

**The whole table, read off the switch rather than off what the logs happened
to contain.** `tile_collision` dispatches at `0x800327e8` through
`tile_op_table` at `0x80011b0c`, indexed at **`opcode - 0x10`** and guarded by
`sltiu $v0, $v1, 0x31` — so the table covers opcodes `0x10` to `0x40`, and
anything outside that range falls straight through. Of the 49 arms, 31 point at
the shared do-nothing tail; the other 18 are:

| op | arm | what it is |
| --- | --- | --- |
| `0x10` | `0x800327f0` | floor |
| `0x11` | `0x80032840` | ceiling |
| `0x17` | `0x80033aa8` | publishes a surface into `0x801e6484` |
| `0x18` | `0x80033a10` | publishes a surface into `0x801e647c`, and takes part in the mask |
| `0x19` | `0x80033a80` | publishes a surface into `0x801e6480` |
| `0x20` `0x21` `0x22` | `0x800328c0` `0x800329b8` `0x80032a90` | walls: one plane, either, both |
| `0x23` | `0x80032b90` | diagonal wall |
| `0x24` | `0x80032c3c` | slab |
| `0x25` | `0x80032d3c` | **a wall with an L-shaped footprint** |
| `0x30` | `0x80032f78` | ramp, and a push when it is steep |
| `0x31` | `0x800338c4` | **a gap in a wall**: runs only when the mask already has bit 0 |
| `0x32` | `0x80033460` | diagonal ramp |
| `0x33` `0x34` | `0x800331b0` `0x80033308` | corners, inner and outer |
| `0x35` | `0x80033604` | a ramp with a top: overhead, it is the ceiling |
| `0x40` | `0x800339a8` | switches to the cell's other layer and **restarts the shape** |

Counted across every shape program in the game, the opcodes in use are exactly
these eighteen minus `0x40`: `0x10` 1866, `0x11` 1325, `0x17` 13, `0x18` 42,
`0x19` 143, `0x20` 2127, `0x21` 89, `0x22` 419, `0x23` 83, `0x24` 88,
**`0x25` 207 on all 28 levels**, `0x30` 616, `0x31` 11, `0x32` 34, `0x33` 39,
`0x34` 26, `0x35` 4. So **no shape in the game uses an opcode with no handler** —
the 31 empty arms are unused values, not a gap.

### The ceiling, the push, and the two ramps' other handlers

`tile_collision` leaves three more answers besides the mask and the nearest
surface, and `player_horizontal` reads all three:

```
collision_ceiling  0x801e6478   the base - 40000 on entry (0xffff63c0 at
                                0x80032628); overwritten, not kept lowest, by
                                  0x11      its top when the head is below it,
                                            or -100000 when you stand on it
                                  0x20-0x25 a wall whose bottom is not below
                                            the head: that bottom, a beam
                                            overhead (0x80032954, 0x80032e3c)
                                  0x31      its own, op3
                                  0x35      its top, when the head is below it
                                  0x18      itself, under arg5's bit 30
tile_push          0x801e6498   zeroed on entry; a ramp -- 0x30 or 0x35 --
tile_push_angle    0x801e649c   whose run op5 is under 0x40 writes
                                (op4 << 7) / op5 and face << 10 (0x80033710),
                                once the point is within its span
```

**`0x35`** (4 uses, none on level 0) is `0x30` with a top: the same span and
height, but when the head is not above `op0 + base` it only sets the ceiling
there. **`0x31`** (11 uses, always a shape's last opcode) is a doorway cut
through a wall: armed only if a wall before it has set bit 0, and within
`op0 + r <= u <= op1 - r` across its face it *sets* the surface to `op2` and
the ceiling to `op3`, adds bit 3 if the head is above that ceiling, and clears
bits 0, 2 and 9 if the floor is not above the feet -- the wall's refusal
withdrawn. When bit 0 is clear it returns without stepping over its five
operands, so the loop reads them as opcodes; being last, nothing follows.

`player_horizontal` climbs a step only if the ceiling is more than a body
(`0x6a4`) above the new surface, and every step it takes -- clear, or a step
up -- first adds a push of `0x40` or more along `-angle - 0x400`, once, and
asks again. Both of `player_step_distances`' calls to it are unconditional
(`0x8002fda0`, `0x8002fdb4`; `player_walk` falls through into it), so a step
of nothing still takes the push: **standing on a steep stair slides you down
it, two pushes a frame**. And the diagonal slide's rotation is byte +2 of
whatever cell and layer `0x801e6468` holds -- the *last* `tile_collision`
call's, which after the shorter tries is the last of those, not the target.

Checked against the recorded walking: at cells (31,18) and (32,18) of level 0
the game stepped 21 where the model stepped 141, with a ramp of run 16 and rise
15 at the target -- a push of 120. With the push, the ceiling, the two calls
and the last cell, rung 2 goes from 118 207 to **118 288 of 118 500**, and the
frames refused by a wall from 101 to 12.

### The L-shaped wall, which was the hole

`0x25` is the one that mattered. 207 uses across every level and
`tools/collision.py` ignored it entirely, which is a good candidate for "some
low walls can be walked through". In the face's own frame — `u` along it, `v`
across, the same rotation the other lateral handlers use — the region is

```
u >= op0 - a3   and   v <= op3 + a3   and   not (u > op1 + a3 and v < op2 - a3)
```

a quadrant with a bite out of its far corner, and the code says it in exactly
that shape: a pair of tests that reject only together (`0x80032da0`,
`0x80032db8`) and then two that reject on their own. The height span is `op4`
and `op5` and it joins the same shared tail every other wall uses, the one
`tile_block` labels at `0x80032e14`.

Transcribed into `tools/collision.py` and `godot/collision.gd`: level 0 goes
from **1304 wall planes to 1345** — the 41 the queue had counted — and of 775
probe points inside the 31 cells whose shapes use it, **622 change their mask**.
`tools/collision.py` still reproduces 8075 of 8078 logged calls, unchanged,
because no logged call ever stood in one of those cells.

### Three planes that are not walls at all

`0x17`, `0x18` and `0x19` each write one height into its own slot —
`0x801e6484`, `0x801e647c`, `0x801e6480` — and nothing else in `GAME.EXE`
writes those. The only reader is **`sync_player_pos` (`0x80028d54`)**, which
every frame takes `surface + 0x640` less the player's eye (Y plus the bob at
`0x801b2650` plus the landing crouch at `0x801b2654`) into `0x801b2638`,
`0x801b263c` and `0x801b2640`, and when the eye has gone past one it calls
`0x80030a6c` — which sets `player_state` to `0x11` and plays sound `0x6e`.

So these are planes that do something to you when you are under them, and that
is why no recording in this repository has ever hit one: nobody drowned while a
breakpoint was armed.

**Where those two flag bits come from.** `actor_move_vertical` builds its
fifth argument as

```
arg5 = actor[+0x1e] | ((actor[+0x28] & 0xc000) << 16)
```

-- the body height in the low bits and the creature's own two bits in the top,
landing exactly on `0x80000000` and `0x40000000`, which is what `0x18` tests.
`player_vertical` passes a plain `0x6a4` with nothing on top. So the planes act
on the *player* only through `sync_player_pos` and the eye height, and on a
*creature* through the mask, according to two bits in its record -- which is
how one thing can walk on a surface another drowns in.

`0x18` also takes part in the mask, and it is the only handler in the routine
that reads the **top nibble of the fifth argument**. `0x800326b0` splits `arg5`
into `arg5 & 0xf0000000` (kept in `$fp`) and `arg5 & 0x0fffffff` (the body
height everything else uses). With bit 31 set, `0x18` *sets* the nearest
surface rather than reducing it, and locks `0x10` out for the rest of the shape
(`[sp+0x10]`, which `0x10` tests at `0x800327f4`). With bit 30 set it can raise
the ceiling bit instead. Nothing else in the routine looks at those bits.

### `0x40` restarts the shape on the other layer

`0x800339a8` toggles `0x801e646e` between 0 and 5, re-reads the cell at the new
offset, sets the base from that layer's `+1`, and jumps back to the top of the
instruction loop — once only, guarded by `[sp+0x18]`. It is how a shape could
say "and now the other layer too". **No shape in the game uses it.**

**But this is collision, not rendering, and the distinction is total.** The
working copy of the shapes at `0x801e4464` has exactly three references in
`GAME.EXE` — the routine that copies it in, and the two inside
`tile_shape_reader`. **Nothing draws from these records.** They are what the
player bumps into; what the player sees is built somewhere else. A second
dispatch table sits immediately after the collision one, at `0x80011be0`,
pointing into a separate handler cluster at `0x80035954`, and that is the
obvious place to look next. Until it is read, a port built on this decode can
be walked through but not drawn: no surface here carries a texture, and the
`cell[+5]` texture id is one byte for the whole cell.

**The mask names the kind of surface**, because each handler ors in its own
bits: `1|4` a wall, `4` a floor, `2|4` a diagonal wall, `8` a ceiling. So the
return value is not "you are stuck" but "you are against this sort of thing",
which is what a port needs in order to slide, step or duck.

The fifth argument matters and cannot be faked: `s3 = y - (arg5 & 0x0fffffff)`
is the head where `y` is the feet, and `arg5` ranges 0..1997 across callers —
it is the body height being asked about. `emu/bp13.lua` logs it.

**A wall is a plane inside the cell, not an edge of it.** That is why every
attempt to predict walls as cell boundaries failed, and why the last one only
looked close.

```
face = (op[3] + cell[+7]) & 3        a3 = (radius * hw0) >> 12,  t6 = 0x800 - a3
lateral, per face:  0: tx <= op0 + a3        2: tx >= t6 - op0
                    1: tz >= t6 - op0        3: tz <= op0 + a3
lo = op1 + base, hi = op2 + base
block when  lateral  and  y - 128 < lo  and  y > hi        mask |= 5
```

`0x21` takes that condition **or** the next face's and `0x22` takes **and**, so
one is an L of two walls and the other a cut corner. `op[0]` offsets the plane
into the cell — often `1024`, dead centre — and `op[1]`, `op[2]` are a height
band, which is how the game lets you walk under an arch.

`0x30` is a **sloping floor**, its four faces meeting at `0x80033030`:

```
h = op0 + base - ((q / op5) + 1) * op4     q = tz, tx, 0x800-tz, 0x800-tx
                                             for faces 0..3
the lateral extent is tested on the other axis
if h < nearest:  nearest = h;  if h < y:  mask |= 4
```

`op[0]` is `128 * op[4]` in every instance seen, so a ramp descends by whole
height units across its cell — the same unit as `cell[+6]`. `0x10` is the flat
case of the same thing.

`0x24` is a wall of **limited length**: from its own face it occupies `op0..op1`
rather than the whole cell width, which is what a pillar or a free-standing
segment needs, and it shares `0x20`'s height test and tail.

`0x33` is a **diagonal**, its height driven by the nearer of the two axes —
`q = min(tx, tz)` and its three rotations. The diagonal is in *plan*: the lines
of equal height run cornerwise. The steepness is separate, and is usually tiny.
Level 0 cell (46,22) is `0x33 [128, 0, 1, 16]`, which falls **one height unit
across the whole 2048-wide cell** — about three degrees. These are step-smoothing
tiles, there to take the lip off a one-unit change, and they are meant to be
imperceptible: played over, that cell reads as flat ground, which is what
confirmed the reading rather than contradicting it.

**Two readings confirmed from play rather than from code.** The height band on a
wall is what makes a low wall climbable: blocking needs `y > hi`, so rising above
its top releases it, and a `0x24` wall on level 0 behaves exactly that way in
the game — steppable once the player rises. Its uneven top is neighbouring cells
carrying their own `hi`. Both were read out of the MIPS first and only then seen.

### What the caller does with the answer

**Withdrawn: `actor_move_horizontal` is not the player's movement.** It was
described here as "the movement", and it is not — it is the *monsters'*. It
works on `current_actor`, the pointer at `0x8018fab4` that `actor_select`
(`0x8004da2c`) fills from the 0x88-byte table at `0x80185da8`, and the player is
not in that table: no entry of it carries the player's position in any snapshot
we have. Its entry point is `0x8004dbc8`; `0x8004dca0` is an inner label, which
is why nothing in the executable ever calls it. The mistake cost a session
looking for "who writes `+0x30`" in the wrong module, and the answer to that
question is below.

What it does do is worth keeping, because the monsters use it:

```
s4 = max(s4, struct[+4])      over several probes -- the LOWEST surface
...
if actor_y < s4 - 0x44c:  the step is refused
else:                     commit X to +0x2c and Z to +0x34
```

Inside one cell `cur` keeps the **minimum**, the highest surface; across the
probes the caller keeps the **maximum**, the lowest. And it is not used as
"where to stand" at all — it is a **drop limit**: a step is refused when it
would leave the feet more than `0x44c` (1100) above the ground beneath them.
That is what stops a monster walking off a ledge.

The fifth argument is formed here too: `body height | (actor[+0x28] & 0xc000) << 16`,
which is why `tile_collision` masks it with `0x0fffffff` and pulls the top
nibble out separately.

An actor's vertical is `actor_move_vertical` (`0x8004e330`), a state machine on
`actor[+0xd]`, and it is where every write to an actor's `+0x30` in ordinary
motion happens:

| state | what it is | what it does |
| --- | --- | --- |
| `0` | grounded | compares the surface with the feet: sunk → `0x20`, in the air → `0x10`, level → nothing |
| `0x10` | falling | `y += v`, `v += def[+5]`; on a floor, snap to the surface and go to `0` |
| `0x20` | stepping up | `v = -0x64` on entry, `y += v`, `v += 5`; snap to the surface on reaching it |
| `0x30` | thrown | `y = actor[+0x3c] - t*(+0x6a) + t²*(+0x6c)/2`, a ballistic arc with `t` in `+0x52` |

`def` is the actor's entity definition, `entity_table + 120 * actor[+2]`, so
**fall acceleration is per monster kind** where the player's is a constant.

### The player's own movement

**Withdrawn, by the recording that was meant to confirm it.** What follows below
about `player_move` was described here as the player's movement. `emu/bp14.lua`
logged the routine for a whole session: **69 calls, every one of them in player
state 0x10 or 0x11**, which is the knockback after dying, while the control
point watched the position change through eight hundred frames without it. The
transcription is right about the routine and wrong about its job. It was reached
by asking which routine writes `0x801b25f4`, finding one that plainly does, and
never asking the game whether it was the one that mattered.

Walking is two other routines, both called from the controller (`0x80030fcc`)
on its ordinary path: `0x8002e3f8` through `0x8002f9bc` for the ground plane,
and **`player_vertical` (`0x8002ed60`)** for the height.

`player_vertical` is a state machine on the byte at `0x801b25e8` with a velocity
at `0x801b2656`, and its grounded state is **not a physics model at all**. It is
a rate limiter towards the surface, which `collide_surface` (`0x80033b10`) has
just left in `0x801e6474`:

```
d = surface - y                    Y is down, so d < 0 means the ground is higher

rising      d < -0x400   state 0x20, velocity -0x96 or -0x12c
            d < -0x200   y -= 0x200
            d < -0x100   y -= 0x100
            d < -0x80    y -= 0x80
            otherwise    y = surface            placed, not eased

falling     probe collide(x, y+1, z) first; if blocked, stay
            d < 0x81     y = surface            placed, not eased
            d < 0x101    y += 0x80
            d < 0x201    y += 0x100
            d < 0x401    state 0x10, velocity 0x28
            otherwise    state 0x40, velocity 0x28
```

The four other states, each with its own acceleration:

| state | height | velocity | ends |
| --- | --- | --- | --- |
| `0x10` | `y += v` | `+0x50` | when `surface + 0x64 < y`, placed on the surface, state 0 |
| `0x20` | `y += v` | `+0x0a` from `-0x96` | on meeting the surface, state 0 |
| `0x40` | `y += v` while the **collision mask** is clear | `+0x28` from `0x28` | on a blocked probe: placed on the surface, or `surface - v/2` past `0x200`, state `0x50` |
| `0x50` | none | `-0x12c` | when the crouch at `0x801b2654` and the bob at `0x801b2628` are both spent |

Two of those are worth stating plainly. **`0x10` and `0x40` are both falls and
the shorter one accelerates twice as fast** — `0x50` against `0x28` — which no
amount of reading would have made believable on its own. And **`0x50` owns no
height**: after its bookkeeping at `0x8002f068` it falls straight through into
state 0's code, so the ground is followed normally while the camera recovers.

So while walking there is **no gravity and no jump**: you are carried up and
down at a fixed rate, and only a gap wider than `0x400` becomes a fall. Within
`0x80` the height is *set* to the surface, which is why the game reads as
standing exactly on the ground. The `y+1` probe before descending is what keeps
you on a bridge instead of dropping to the room below.

**Checked against the game.** `emu/bp15.lua` is a write watchpoint on the
player's own coordinates rather than a breakpoint on a routine, so it cannot be
wrong about where to look: whatever moves the player names itself. Every
instruction it caught storing the height is in `player_vertical`, and
`python3 tools/movement.py bp15` reports

```
48 of 48 of the game's own height stores chosen exactly (100 %)
15 of 15 consecutive falling frames advance by exactly the velocity,
   and the velocity by its state's own constant
```

— that is, given the position, state and velocity the game had, the model
reaches the same store instruction, and the arithmetic between frames is exact.
The same watchpoint confirmed `0x8002e3f8` as the horizontal: 26 of the 41
writes to the player's X came from `0x8002e580` inside it. Six more came from
`0x800482e4`, in the actor cluster, nudging X by about 37 a frame — something
pushes the player, and that is not read yet.

What the recording cannot give is a **frame rate**: it carries no clock. It does
give the horizontal step, 201 units a frame at speed, ramping up from a
standstill through 15, 25, 35, 45, 54 — so `0x8002e3f8` accelerates, and that
ramp is not transcribed either.

### An object of type N uses model N + 128

Not `MO.T[type]`, which is what this project assumed for months and what nothing
had ever checked. The offset was **measured**: a player stood in the game beside
the port, read the type off a label over each object and the number off the model
gallery, and named four pairs.

| what | type | model | difference |
| --- | --- | --- | --- |
| helmet | 34 | 162 | 128 |
| healing grass | 104 | 232 | 128 |
| save point | 227 | 355 | 128 |
| bull's head | 253 | 381 | 128 |

The sizes agree independently. Under the rule the healing grass is
384 x 211 x 416 — a tuft; under the old assumption it was 4176 x 4096 x 3808,
two cells in every direction, which is exactly what the player had been
reporting as "a big white thing where the grass should be". The bull's head
comes out 1552 x 594 x 2003: wide, flat, lying down.

Past `MO.T`'s 428 entries the numbering **continues into `MOF.T`**. That part is
read from the shapes and not confirmed: type 301 is the *Broken Cart* and lands
on `MOF.T[1]`, which is 1711 x 1092 x 2886 — long, low, about a cell wide. It
wants one look before it is believed. 89 of level 0's 347 objects are past the
end, and the graves at types 324 to 326 are most of them.

`tools/gallery.py` is what made this findable: every model on a grid with its
number, every placed object in the world with its slot and its type, and a
player to say which is which. No static check could have done it — the wrong
model parsed, placed, scaled and lit exactly as cleanly as the right one.

### From type 300 up, the level is part of the model number

`model_of_type` (`0x80040568`) is eleven lines and it says the whole rule:

```
type <  300    model = type + 0x100
type >= 300    model = type + 0x100 + 32 * level
```

where the level is the byte at `current_level_block` (`0x8018fad8`), or
`pending_level` during the handover when `0x8018fad4` and `0x8018faeb` are both
1. The `+0x100` is the 128 a player measured off the model gallery, seen from
the other side of the resource table's own offset.

So past `MO.T`'s 428 entries, **`MOF.T` is banked, 32 models to a level**, and
the arithmetic puts level *n* in bank *n + 4*. Checked against the placement
records: over **all 1424 placed objects of type 300 and above, across 25
levels, the bank comes out as `level + 4` every time**. `MOF.T` has 992
entries, which is 31 banks; the first four belong to no level.

`tools/tmd.py` ignored the level, which is right on level 0 and picks a model
32 banks wrong on level 1 — and level 0 is the only one the port has ever
built, which is why it survived. With the level in, 1423 of the 1424 land on an
entry that holds a model, against 1410 before.

### An MO.T entry is not a bare TMD

```
+0   total size
+4   a count, 1 to 3
+8   the offset of the TMD          <- this one
+0xc ?
+0x10  0x14, the first of a table of offsets
```

Looking for the TMD id in the first 256 bytes instead finds it only for the
models that keep it near the front. The statue (`MO.T` 287) keeps its at 3448
and the chest (106) at 13964, so 53 of level 0's 347 objects were reported as
having no model at all and simply did not appear. Reading word 2 gives **347 of
347**.

Caught the same way as everything else here that no check would have found: a
player looked at the port beside the emulator and said a statue was missing and
a chest was distorted. The distortion was the wrapper being read as geometry.

### Object models are not culled, because the console does not cull

The PlayStation has **no backface culling in hardware**. What a game skips it
skips in software, with the GTE, and the object models plainly rely on that:
walk round a figure in the game and it is solid from every side.

Culling them here made about half of every model vanish and left the rest as
loose plates — which a player described as a boy who "splits into layers" from
some angles, with "some polygons transparent". The obvious repair, turning each
triangle to agree with its own normal, was tried and **made it worse**: the
per-face normal is not a reliable guide for these models, so the correction
flipped as many triangles as it fixed. Withdrawn.

Not culling is both simpler and what the console does, and it costs nothing:
the port's object materials are unlit and carry baked vertex colour, so which
way a face points has no effect on what it looks like. The level tiles keep
their culling — they were checked by eye and are right.

Worth keeping separately: the catalogue had its own copy of this loop and the
copies drifted, which is how the difference between the two windows appeared in
the first place. They call one `level3d.emit_object` now. Two copies of a rule
are two rules.

### The primitive layouts, read off the renderer's own handlers

`tmd_prim_walk` (`0x80035954`) dispatches on the mode byte through the table at
`0x80011be0`, index `mode - 0x20`, and each handler **multiplies the packet's
reference halfwords by eight** — turning the disc's plain indices into the byte
offsets the drawing code wants. Which halfwords it touches is therefore an exact
statement of the layout, with no guessing:

| mode | words | colour / uv | references |
| --- | --- | --- | --- |
| `0x20` tri flat | 3 | hw 0-1 colour | 2,3,4,5 = n0 v0 v1 v2 |
| `0x24` tri flat textured | 5 | hw 0-5 uv | 6,7,8,9 = n0 v0 v1 v2 |
| `0x28` quad flat | 4 | hw 0-1 colour | 2..6 = n0 v0 v1 v2 v3 |
| `0x2c` quad flat textured | 7 | hw 0-7 uv | 8..12 = n0 v0 v1 v2 v3 |
| `0x30` tri gouraud | 4 | hw 0-1 colour | 2..7 = n0 v0 n1 v1 n2 v2 |
| `0x34` tri gouraud textured | 6 | hw 0-5 uv | 6..11 = n0 v0 n1 v1 n2 v2 |
| `0x38` quad gouraud | 6 | hw 0-1 colour | 2..9 = n v, four times |
| `0x3c` quad gouraud textured | 8 | hw 0-7 uv | 8..15 = n v, four times |

Three rules fall straight out, and two of them had been wrong here:

* a **textured** primitive carries no colour word at all when it is lit;
* an **untextured** one carries exactly **one**, gouraud or not — not one per
  vertex, which is what this assumed and what left type 309's 704 primitives
  with nothing usable;
* **gouraud interleaves** the normal with its own vertex, flat does not.

Bit 1 of the mode is ignored: the walk masks with `0xfd`, so `0x26` is `0x24`.

The same walk is also where **the references become offsets**. On the disc they
are plain indices; the game multiplies by eight at load. Reading them back out
of RAM would find offsets, which is worth knowing before anyone compares the two.

### Gouraud primitives interleave their references

A TMD primitive that is **lit and gouraud** stores one normal beside its own
vertex — `n0 v0 n1 v1 n2 v2` — not all the normals and then all the vertices.
Reading them in blocks takes `n0, v0, n1` as the normals and `v1, n2, v2` as the
vertices, which is geometry from three different corners of the model. And a
**textured** primitive carries colour words only when it is *unlit*; reading one
for every gouraud primitive shifts every reference after it by a word.

Both together hit mode `0x34`, which is 58 000 of the game's object primitives.
The result was models that parsed, placed and lit without complaint and came out
as tangles. Fixing the two took level 0's objects from **44 of 82 types above
95 % usable primitives to 81 of 82**, and the port from 65 942 object triangles
to 82 502.

The level tiles were never affected: `RTMD.T` uses `0x2c`, `0x24`, `0x26` and
`0x2e`, all flat, and still reports zero references out of range.

The one type still at nothing is 309, which is 704 primitives of mode `0x30` —
untextured gouraud, and with `ilen` 4 where the format wants 6. It draws nothing
either way, since untextured primitives are skipped.

### Where the object textures are: `FDAT.T` entry 96

The placed objects name texture pages `0x0b` to `0x0f` — VRAM from x=704 across
— on 57 119 of their primitives, and `RTIM.T[lv]` leaves that region entirely
empty. Every one of those primitives therefore drew white, which is what a
player saw as "big white things where the grass should be".

**Withdrawn: "it is not a verbatim copy of any of the nine archives, so the
load packs or rearranges."** It is verbatim, in `FDAT.T` entry 96, and the
search missed it because it looked for whole rows of a page while the entry
stores a page as 64x64-pixel squares. Short samples found it: 39 of 159
sixteen-byte pieces of those pages turned up in the one entry.

Entry 96 is not a chain of blocks like its neighbours. It is **a `LoadImage`
stream in exactly `RTIM.T`'s format** — a rect written twice, then its
halfwords — 556 blocks: CLUTs of 16x1 and 64x64-pixel pieces of the object
pages. The code that sends it:

```
init_level_state   vram_stream(4, 96)                0x80017794
vram_stream        queue_vram_stream(archive, entry, fdat_load_buffer,
                                     vram_stream_ready)   0x80018c60
queue_vram_stream  res_queue(0x40, ...)              0x80019e48
res_upload_vram    for a request of type 0x40 whose +0x10 the callback has
                   set: compare the two rects, LoadImage, at most 0x8000
                   bytes a frame, until a zero size or x = 0xffff
```

**And the 0x8000 is a chunk, not a throttle.** The request reads the entry
sixteen sectors at a time into one buffer (`sub_80018c94` asks for 0x10 while
more remain), and each frame `res_upload_vram` walks that buffer from its
start: a header costs 0x10 and needs 0x10 left, a block that fits goes whole,
and a block that does not goes as many **whole rows** as the budget holds
(`0x80018d84`: budget / w, halved) -- the bytes left over are never sent. The
next frame's buffer is the next sixteen sectors, and the block's remaining rows
are read from its start, so they come from the chunk boundary rather than from
where the last row ended. Wherever a block's rows do not end on the boundary,
the rest of that block lands shifted by the bytes skipped. The game's own
interface shows it plainest: the block for (896, 256) straddles offset
0x50000 of entry 96 with 45 rows and 112 bytes before it, and from row 45 on
every snapshot holds that page 56 halfwords along from the disc. Walked this
way (`rtim.uploads`), entry 96 and `RTIM.T` 0 and 4 never meet a header that is
not doubled and each ends on its 0xffff; entry 96 cuts nine blocks and level
0's `RTIM.T` seven, and every one of those had been laid down unshifted.

and `level_load` calls `vram_stream(3, level)` — archive 3 is `RTIM.T` — so a
level's VRAM is entry 96 from game start with the level's own blocks on top.
`tools/rtim.py`'s `level_vram` builds exactly that, and against the 12
snapshots with a level loaded it matches **2 994 944 of 2 998 544** halfwords
the two streams write -- 2 865 923 before the chunking was read, and on
level 0 every halfword but the 256 of the scrolling water -- and **779 760 of
782 320** on the object pages. What is left is animation: entry 96 writes seven frames of a water
texture into the same 8x32 rect at (1016, 96), and a snapshot holds whichever
frame was showing -- which is not a frame at all: see below.

So nothing on the object pages is borrowed from a snapshot any more, and every
level has its objects' textures. It also settles something that looked like a
separate problem: level 0's geometry draws **its water** from page `0x0f` — a
flat sheet of 296 triangles at Y = -12160 — with a CLUT that only entry 96
writes, so while the geometry was drawn from `RTIM.T` alone the sea was
transparent. And twelve textures on page `0x0b` that the snapshot fill had got
wrong -- it copied a page only when `RTIM.T` left it entirely empty, and the
CLUT page was not -- went from 56 000 to 65 000 pixels off the game to 3 022.

**The water scrolls; it does not cycle frames.** `game_main` calls
`texture_scroll_add` (`0x800350fc`) once, with the rect at `0x8009c214` --
(1016, 96), 32 by 32 pixels -- a delay of 0 and a step of 1. That copies the
square to a stash 32 halfwords to its left, and `texture_scroll_step`
(`0x800351fc`), in every frame's `render_frame`, adds one to an offset, wraps it
at 32, and rebuilds the square from the stash with two `MoveImage`s so that row
`r` is stash row `(r - offset) mod 32`. Each of the eleven snapshots' VRAM is
the stash turned by the offset its own RAM holds, or by the next one (the VRAM
was fetched a frame after the RAM), and every stash equals what entry 96 leaves
in the square. With that copy applied, the object pages match on 779 760 of
782 320 halfwords, and all 2 560 left are the square at its snapshot's offset.

`godot/scroll.gd` does the same in a shader on every material of page `0x0f`:
inside the square, `v` moves by the game's frame count at 15 a second; outside
it nothing changes. The seven blocks entry 96 writes to the square are still
unexplained -- only the last survives, and it is the one the scroll moves.

### The opening scene is a movie, and this is what starts it

**Withdrawn, and it was mine.** I said the scene was played by the engine
because the sword, the painting and the three men are ordinary level 0 objects
and actors. They are — and the scene is still a movie. `/STR/S03.S`, frame 60,
decoded with `tools/str.py`, shows that room and carries the subtitle a player
quoted from it. The same words are `TALK` entry 676 because the three men
repeat them when you walk up and talk to them afterwards.

That one fact explains every empty log at once: during a movie nothing
interactive runs, so `give_item`, `object_interact` and `script_interpreter`
were never going to fire, and the sword was already in the inventory from
`reset_story_flags`.

The player is **`0x80060d20`**. `build_str_name` (`0x80060fec`) is not a
routine of its own but a label *inside* it, which is why nothing appeared to
call it. It reads the scene number through the pointer at `0x801f825c` and
splits it into two decimal digits with the usual multiply-by-`0xcccccccd`,
filling in the `SXX` of the `\STR\SXX.S;1` template at `0x80013680`.

It has exactly two callers:

| caller | when |
| --- | --- |
| `cutscene_step` (`0x80061a90`) | the story flags decide — which is how the rest of the game's thirteen cutscenes are reached |
| `0x80061bc4`, a bare wrapper, from `game_main` at `0x80014e74` | guarded by `bne $s1, 1` — and `$s1` is the new-game flag, set when `read_overlay_arg2` returns −1 |

So the opening plays on a new game and not on a loaded save, from `game_main`'s
own init block, a few instructions after `place_player_on_terrain`.

### The cutscene list is pairs of scene and gate flag

`0x801e825c` holds a **cursor**, and `build_str_name` takes the scene number
from the byte it points at. In a level 0 snapshot the cursor is `0x801e7f78`
and the bytes there are `3, 9, 31, 3, 0xff`. `cutscene_step` reads the *second*
byte of each entry, so the list is **pairs**, terminated by `0xff`:

```
b = cursor[1];
if (b == 0xff)          no gate
else if (b & 0x80)      skip the scene when story_flags[b & 0x7f] is set
else                    the same test the other way round
```

which reads the snapshot's list as **scene 3 gated by flag 9**, then scene 31
gated by flag 3. And that closes a loop: `emu/bp18.lua` caught `game_main`
writing **`story_flags[9]`** at `0x80014ea4`, thirty instructions after the
call that starts the opening. So

> **`story_flags[9]` means "the opening cutscene has been shown".**

### Where that list lives: FDAT entry 97

It is not per level and not assembled at run time. `init_level_state` reads
**`FDAT.T` entry 97** through `read_entry_b(4, 0x61)` and unpacks it as a chain
of length-prefixed blocks into fixed addresses; the **seventh block, 832
bytes**, goes to `0x801e7edc`. Its first sixteen bytes are identical to that
address in a RAM snapshot, which is what identifies it.

832 bytes is **16 records of 52**, and the record number *is* the scene number
for 3 to 15 — exactly the thirteen files under `/STR`. Records 0 to 2 do not
name themselves and there is no `S00`–`S02` on the disc.

| record | gate |
| --- | --- |
| `S03` | `story_flags[9]` — the opening, started by `game_main` on a new game |
| `S04` | `story_flags[67]` |
| `S05` | `story_flags[87]` |
| `S06` | `story_flags[93]` |
| `S07`, `S08`, `S11` | none: they play whenever reached |
| `S09` | `story_flags[84]` |
| `S10` | `story_flags[88]` |
| `S12` | `story_flags[123]` |
| `S13` | `story_flags[124]` |
| `S14` | `story_flags[126]` |
| `S15` | `story_flags[125]` |

**`cutscene_step` is the whole cutscene machine, and the gate is one phase of
it.** It was called `flag_gate` here for that one branch, because 53 of its
161 instructions -- everything past its indirect call -- were outside the walk
until `tools/rdis.py` learned to keep going after one. What it does, once a
frame from `game_main` and `player_controller`: take the scene number at
`cutscene_number` (`0x801e8260`, `0xff` for none), multiply it by 52 into
`seq_data`, leave the record pointer at `cutscene_record` (`0x801e825c`), and
dispatch `cutscene_phase` (`0x801e824c`) through a **17-arm table at
`0x800136a0`**. Phases that were invisible until now include the one that
copies the screen with `MoveImage` between `draw_env` and `disp_env`, and the
one that calls the level's own **entry 7** when `cutscene_pending`
(`0x801e824e`) is 1.

A conversation can start a scene: `script_interpreter`'s service arm for a
header `+0x12` in the `0x40` range writes `1` to `cutscene_phase` and `n & 3`
to `cutscene_number`.

And `story_flags` **93, 101 and 102 are not story**. `cutscene_step` and
`level_overlay_tick` move them from 1 to 2 and back as phase state within a
single fade. The array is at least `0x100` bytes and only its lower part is
what the conversations test.

**Withdrawn: the flag is not a key, it is an "already shown" mark.** This
document said bit `0x80` meant "skipped once that is set", and I told a player
that level 13's overlay *unlocks* `S04`. Both are backwards, and the answer is
in the delay slots. At `cutscene_step+0xc4` the branch taken when the flag is set
carries `v0 = 2` in its slot while the fall-through carries `v0 = 0x10`, and
the routine stores whichever it ends with into the state word at `0x801e824c`:
**2 goes on to the scene, `0x10` does not.** So

| gate byte | the scene plays |
| --- | --- |
| `0xff` | always |
| bit `0x80` clear — every gate in this table | **while the flag is clear**, and stops once it is set |
| bit `0x80` set | only once the flag is set |

The one case with independent evidence settles it: `game_main` sets flag 9
*immediately after* starting the opening, which reads as "do not play it again"
and cannot read as "now it may play".

So the table is a list of scenes and the marks that retire them:

| cutscene | mark | set by |
| --- | --- | --- |
| `S03` | 9 | `game_main` and `player_controller` |
| `S04` | 67 | level 13's overlay |
| `S05` | 87 | level 20's overlay |
| `S06` | 93 | level 24's overlay |
| `S09` | 84 | level 17's overlay |
| `S10` | 88 | level 20's overlay |
| `S12`–`S15` | 123–126 | nothing found yet |

`S07`, `S08` and `S11` carry no mark at all, and neither, in effect, do the
last four: nothing this project has found sets 123 to 126, so nothing stops
those scenes repeating. That is a smaller mystery than "four locked endgame
scenes" was, and it is what the code actually says.

**Byte 0 and byte 1 are what has been read**; the other fifty bytes of each
record are not. Reading them as further scene-and-flag pairs gives scene
numbers like 158 and 252 that no file answers to, so they are left alone.

**A correction that follows from it:** these indices reach 126, and `cutscene_step`
masks the byte with `0x7f`. So `story_flags` runs past 64 — and it runs past
128 as well. **The array is 256 bytes.** `reset_story_flags` clears it with
`block_zero(story_flags, 0, 0x40)`, and `block_zero` stores **words**: its
other call clears `0x1400` for the `0x5000` bytes of `level_state`, so `0x40`
words is 256 bytes. `save_serialise` and `save_restore` copy exactly that
span, `0x801ba988` to `0x801baa88`, which is where `level_state` begins.

That was not a cosmetic limit. With it raised, the level overlays turn out to
write **60** flags rather than 36: twenty-four writes were being discarded for
falling outside a boundary that was never established. Flags 67, 84, 87, 88 and
93 — five of the cutscene gates — are among them.

### The room itself, found by its painting

A player who had seen the game said the room where the sword is handed over has
a painting of two knights on the wall, and that it looked like model **428** in
the port's gallery. That is enough to locate the whole scene from the disc,
with no emulator:

* 428 in the gallery's continuous numbering is `MOF.T[0]`, which
  `model_of_type` reaches from **object type 300**. Level 0 places exactly one
  of those, slot 191, at **cell (62,3)**, at `h = -2000` — two metres up a
  wall, which is where a painting hangs. The model is a framed flat panel; the
  two knights are in its texture.
* Beside it at cell (62,3) stands type 299, the readable marker, so the
  painting is something the game lets you read.
* One cell away, at **(62,4)**, is object slot 62, **type 0**, model
  `MO.T[128]` — a sword, hanging at `h = -924`. That is the sword the port
  draws floating in mid-air, and it is a real placed object, not an effect.
* Three actors stand in the same corner: meshes **32, 33 and 34**, kinds 9, 10
  and 11 — one man in three poses. Two of them share cell (62,4), which is why
  the port draws him twice, once at the table and once with the watering can.
  All three have `+9 = 0` in the snapshot, so the game was drawing none of them
  at that moment.

**The scene uses none of the game's ordinary machinery.** `emu/bp17.lua` sat on
`give_item`, `take_item`, `object_interact` and `script_interpreter` while a
player started a new game and played the handover through. **Not one of the
four fired.** So the sword does not change hands the way every other item in
the game does, and the conversation is not the entity-script interpreter
either. That is a real result and it rules out four routines at once; what does
do it is still unknown.

`text_pager` shows three hits in the same log and they should not be believed:
`$ra` points four bytes inside `text_pager` itself and `$a1` is a scratchpad
address, so the routine was reached without a call and the registers are
somebody else's. Nothing about them says a page of dialogue was drawn.

**Withdrawn: "the three men are turned on by two different routines."** The
alive byte at `+9` of each actor was watched across the same session, and this
table was read as two routines switching them on:

| actor | mesh | written from |
| --- | --- | --- |
| 0 | 32 — the one at the table | a call at `0x8004b698+0x14` |
| 1 | 33 | a call at `0x8004c1f0+0xa4` |
| 2 | 34 — the one with the watering can | the same `0x8004c1f0+0xa4` |

Both entries are return addresses left over from the last call made, not the
routine that stored, and the watchpoint reported the value from before the
store. Read properly (section 17), all three went through one routine,
`actor_activate` at `0x8004c1f0`. The man at the table was **woken**:
`actor_spawn` calls `actor_wake` at `0x8004b698`, whose first call returns to
`+0x14`. The other two were **held**, in state 2, because in that session their
category was 8, and distance never wakes category 8.

**The sword never changes hands. You already have it.** `emu/bp18.lua` put a
write watchpoint on the whole inventory and a player played the scene through
again. Nothing wrote the inventory during it. What the watchpoint did catch is
`reset_story_flags` (`0x8005ea64`), which clears 75 words over both inventory
arrays and then writes four bytes into `inventory_a`:

| item | count | what it is |
| --- | --- | --- |
| 0 | 1 | the sword — *the greatest achievement of Leon Shore, the first stage* |
| 42 | 1 | body armour, standard issue for the soldiers of the Verdite army |
| 104 | 2 | the healing herb |
| 105 | 1 | the antidote herb |

Read off the code at `reset_story_flags+0x88` to `+0xa0`, and caught by the
watchpoint in the same order. `reset_story_flags` runs from `game_main` at the
start of a **new game**, so all four are in the inventory before the first
frame is drawn. The scene in the house is staging: the man appears to hand over
a sword the game gave you at the title screen. That is why bp17 found no
`give_item` and bp18 found no write — there is nothing to catch.

It also settles an old note: FORMATS said "id 104 went 2 → 3 on pickup", and 2
is where a new game starts it.

**The subtitles are `TALK.T`, and one routine reads that archive.** A player
quoted the line about the seal Alexander gave his life for; it is `TALK` entry
**676**, matched exactly in the decoded text. Searching all three decoded
archives, `STALK` holds none of that scene's text and `TALK` holds it — which
is why `text_pager` (`0x8001d944`), a walker of *STALK* indices, never fired
either. Of the six archive-entry readers, exactly **one call site anywhere in
`GAME.EXE` passes archive 7, `TALK.T`: `0x8005c5fc`, inside
`script_interpreter`** — and `script_interpreter` did not run during the scene.
So the opening's text reaches the screen by a path that is not the one every
other conversation uses, and that is the next thing to find.

**The overlay write was not the scene.** `0x801e9084`, the address the log
named, is `story_flags[3] = 0`, the else-branch of

```
if (has_item(2) && has_item(130) && has_item(131) && has_item(132))
     story_flags[3] = 1; else story_flags[3] = 0;
```

Item 2 is the sword's final stage, so flag 3 is an endgame condition the
overlay re-evaluates every time it runs. It says nothing about the opening.

### Withdrawn: the 108-byte records are the lighting table, not keyframes

This section said creatures are animated by blending two 108-byte keyframes out
of a table at `0x801aeefc`, 64 of them, each 54 signed halfwords read as
eighteen joints of three angles, filled from `FDAT` entry 97 block 5. Every
measurement in it was right and the reading on top of them was wrong.

**`0x801aeefc` is the lighting table**, and `draw_tile` settles it in six
instructions. It forms `tile_look + 108 * (cell[+9] & 0x3f) + 20 * rot` and
then does this:

```
lw   $t5, 0x0($t4)      ctc2 $t5, L11L12
lw   $t6, 0x4($t4)      ctc2 $t6, L13L21
lw   $t5, 0x8($t4)      ctc2 $t5, L22L23
lw   $t6, 0xc($t4)      ctc2 $t6, L31L32
lw   $t7, 0x10($t4)     ctc2 $t7, L33
```

— the record goes straight into **the GTE's light direction matrix**, and its
`+0x50` into the light colour matrix, and its `+0x64` into RBK, GBK and BBK.
`draw_held_item` does the same with the cell the player is standing in.
`data/symbols.json` has said so under the name `tile_look` the whole time: four
20-byte light matrices chosen by orientation, a colour matrix at `+0x50`,
the background colour at `+0x64`. That is 108 bytes and it accounts for all of
them.

Why the animation reading looked good is worth keeping. A light matrix is nine
signed halfwords of fixed point, so **±4096 is exactly what it looks like**,
and four of them plus a colour matrix is 54 halfwords — the same count an
eighteen-joint skeleton would give. Two entries being identical and a third
differing is what a lighting table does too: most cells are lit the same way.
Nothing in the shape of the data could have told the two apart. Only what the
code *does* with it could, and that was one instruction away.

The filler is `light_table_reset` (`0x800341e8`), which `game_main` calls **at
the top of every frame**, not once. It copies 64 entries, 48 bytes at the
source and 108 at the destination; block 5 of `FDAT[97]` is 2304 bytes, which
is the first 48 of those entries, and the last 16 come from `GAME.EXE`'s own
data past the block.

**Withdrawn: "a lighting table that `light_table_step` interpolates".** The
step interpolates nothing. The reset copies a source's first 20 bytes -- the
light direction matrix -- to the record's `+0x00` and its other 28 to `+0x50`,
and `light_table_step` fills the 60 bytes between with that matrix turned by
one, two and three quarter turns about Y (`light_matrix_turn`, `0x80016290`):
the four orientations `draw_tile` picks by `cell[+7] & 3`. `tools/lighting.py`
builds the whole table that way, and it is **6912 of 6912 bytes** of what
every snapshot holds, on level 0 and level 4 alike -- so the port no longer
reads it out of `out/tile_look.bin`.

**So where the creature animation lives is open again.** `0x8003e34c` really
does interpolate two records by a fraction — that part of the old reading is
unaffected — but what it interpolates is lighting, and creatures moving their
limbs has to be somewhere else.

### A creature carries one angle, and only one of a set is drawn

The actor branch of `render_walk` copies three halfwords into the scratchpad at
`0x1f800114`, `0x116` and `0x118` — the same slots the object branch fills, so
the same matrix builder turns both:

```
lhu $v0, 0x3d($s0)   ->  sh $v0, 0x114($s5)      $s0 = actor + 3
lhu $v0, 0x3f($s0)   ->  sh $v0, 0x116($s5)      so the fields are
lhu $v0, 0x41($s0)   ->  sh $v0, 0x118($s5)      +0x40, +0x42, +0x44
```

and the spawner at `0x8004b868` fills them:

```
v1 = actor[+0x20]
actor[+0x44] = 0        Z
actor[+0x40] = 0        X
actor[+0x42] = v1       Y
```

So a creature has a **yaw and nothing else**, and it comes from `+0x20`. In a
level 0 snapshot 29 of the 58 actors carry one. The three men by the house
carry zero, because none of them was spawned in that session.

**`+9` is a small state machine, not a flag.** A player killed monsters and
waited for them to come back with `emu/bp19.lua` armed, and the watchpoint saw
the byte holding **0, 1 and 2** at different moments, while `0x8004b770` writes
**3** into it — `ori $v0, 3` with the store in the delay slot of its call — and
is reached from both `actor_tick` and `0x8004c1f0`. Four sites clear it to
zero: `0x8004b6b4`, `0x8004c42c`, `0x8004c488` and `0x8004c4f4`, the last three
all inside `0x8004c1f0`.

> **How to read that log.** Its `alive->N` is the value the byte held *before*
> the write, not after: a write watchpoint's callback runs before the store
> lands. The first reading of it here said those sites set 1 and 2, and they do
> not — all four write zero. The three values are real, but they are what was
> there, not what was put there.

**And the renderer draws one of a set, not all of them.** The first thing the
actor loop does with a record is

```
lbu $v0, 9($s0)          ; $s0 = actor + 3
bne $v0, $s4, <loop tail>  ; $s4 = 1
```

so an actor is drawn only while its byte `+9` is 1 — **4 of the 58** in that
snapshot. `tools/level3d.py` used to ignore it and draw all 58, which is why a
player saw the same man twice in the house, one crafting and one waiting, and a
third outside; the port now runs the rule (section 17). What sets `+9` is the
chain `actor_tick_driver` → `0x8004c1f0` → `0x8004b868`, and section 17 reads
`0x8004c1f0` whole. Two things the first pass here got wrong: `0x801b24f2` is
not "something about the player" out of its stat block but a one-pass flag that
a level load sets, and the die is not a respawn rule of its own. It is the
chance byte the disc gives each actor, rolled every time the actor could
appear, first visit included.

### The three men are entities 9, 10 and 11

The number 676 is **nowhere in `GAME.EXE`'s code** — nothing loads it as a
constant. It is in the data: three halfwords in level 0's entity block, at
script-block offsets 1226, 1314 and 1440, which fall in the scripts of
**entities 8, 9 and 10**. Each sits in an identical 24-byte context followed by
bytes in the `0xf0`–`0xff` range interleaved with small ascending numbers —
the shape of a script, with what look like page numbers relative to a base.

The entities themselves tie the scene together. Byte 0 of an entity record is
the **mesh id**, not a kind:

| entity | byte 0 | the actor by the house |
| --- | --- | --- |
| 9 | `0x20` = 32 | slot 0, mesh 32 — the man at the table |
| 10 | `0x21` = 33 | slot 1, mesh 33 |
| 11 | `0x22` = 34 | slot 2, mesh 34 — the man with the watering can |

and the live actor's kind at `+2` is 9, 10 and 11 — the entity index itself.
Three for three, from two directions: the record's byte 0 equals the actor's
`+1`, and the actor's `+2` equals the record's position.

The scene's dialogue is `TALK` 676 to 691 and beyond, a contiguous run; entry
679 is the line where the sword is handed over.

### How a script reaches its dialogue, read off the interpreter

`script_interpreter` (`0x8005c308`) opens by turning an actor into a script:

```
kind   = actor[+2]                      /* the entity index */
record = entity_table + 120 * kind      /* 0x8018c7e8 */
script = *(void **)(record + 0x38)      /* and it must begin with 0x70 */
base   = *(u16 *)(script + 0x0c)
...for every opcode below 0xf0:  load_entry(7, base + opcode)
```

Checked in a RAM snapshot, following the game's own pointers: entities **9, 10
and 11** — the three men by the house, meshes 32, 33 and 34 — each hold a
script block beginning `0x70` whose `+0x0c` is **676**. Entity 8's is 292. So
the opening conversation is `TALK.T[676 + opcode]`, said by the script bytes
themselves.

**Two corrections to `tools/escript.py`, which documents this mechanism.**

*The base is read from the wrong structure.* The tool takes it from offset
`0x0c` of the **entity record**, where every entity on level 0 reads 0. The
interpreter takes it from offset `0x0c` of the **script block** the record's
`+0x38` points at. That is why the tool reports base 0 everywhere and renders
dialogue as animation frames.

*The `0x2b` test does not gate the dialogue.* The tool's note says `TALK.T` is
loaded "only when the entity's kind byte is `0x2b`". Reading the branch at
`script_interpreter+0x2c4`: it compares byte 0 of the entity record against
`0x2b` and, when they match, **skips the call to `0x800608ec`** — and the
`load_entry(7, base + opcode)` at `+0x2f4` sits past the branch target, so it
runs either way.

**Withdrawn twice over.** From the corrected base I said "the 12 179
instructions the tool counts as `say` are dialogue", then withdrew that to
"only 42 of 265 entities carry a base, and those 42 hold 267 of the 12 179
opcodes". **There are no 12 179 opcodes.** Both numbers came from decoding the
wrong bytes: each entity record holds *sixteen* block pointers starting at
`+0x38`, the reader took the list from `+0x3c`, and blocks 1..15 — which are
not scripts — were being disassembled while block 0, the only conversation,
was skipped as "a header". See §9 and `tools/entities.py`.

What is actually there: **43 entities in the game talk**, between them saying
**733 lines**, and `emu/bp21.lua` recorded two of those conversations in play
to settle it.

`tools/story.py` is the result: the game's talkers and their lines, level by
level, into `out/story.txt`.

### A conversation, one USE at a time

USE on a creature in front is the first thing `object_interact` asks:
`actor_spot_taken` at the player's point `0x1f4` up, the creature's radius +
`0x578`, `0xc80` as the point's height -- inside `player_controller`, where
`actor_skip_mask` is 4, so a creature whose flags carry 4 is not found -- and
the creature within `0x12c` of the facing. Then one call of
`script_interpreter`, and the walk over the objects after it.

A call keeps its place in the conversation's block -- the pc at `+0x10`, the
retry flag at `+0x13` -- and in `script_speaker` (`0x801baa2e`):

```
a zero pc       the speaker is this actor
script_prescan  the pc a guard picks, or past the 0xfe
speaker not this actor, retry set: on to past the next 0xf0 and its operand
op by op:
  a line        TALK.T[+0xc + op] through load_entry; one more step if the
                press that closed it had USE in it and +0x12 is 0xff
  0xf0 n        retry set, pc -= n          0xf8 n   pc -= n
  0xf9 i v t    story_flags[i] == v: label t
  0xf2 x        past it                     0xf6     speaker this actor, retry clear
  0xf4 a        the level's entry 4 (a)     0xf5 n   n steps
  0xf7 i v      story_flags[i] = v          -- these three then the step test
  0xf3          a step spent, or the end    0xff     the end
the step test   pc + 1; a step left: spend it and go on, else the end
the end         +0x12's service by its high nibble (0 sub_80021114, 0x30 the
                shop, 0x40 a scene); the speaker this actor; the end animation
```

So where `+0x12` is `0xff` -- level 0's men by the house, and entity 8 --
every USE that closes a line brings the next, and the last line before an
`0xf0` comes back for as long as USE closes it; any other button ends the
call, and the next USE on the talker starts there again. Talking to somebody
else first moves it past the `0xf0`. Successive calls show bp21's four
recorded conversations line for line (`tools/talk.py`, 4 of 4), and a second
bp21 session -- entity 8 a line a call, then three in one, entity 6 and 7's
single lines, entity 8 again from past its `0xf0` after the others -- is held
op for op: **21 of 21 calls** fetch the game's pcs and opcodes and show its
lines from the state the calls before them left. Which button closed a line
bp21 does not log, so that is read off the call (one that went on after a line
was closed with USE). The port (`godot/talk.gd`, through `godot/document.gd`)
is held to the model, 96 of 96 calls. Level 0's entry 4 arms 0, 1 and 5 are in it: whether the player holds
Ichrius' eye, wings and crown (130, 131, 132) and the sword (2), and the
trade; arms 2 and 4 read the play clock and are not.

### The story flags are allocated per level

`tools/story.py flags` puts the two sources together — the 36 flags a level
overlay writes and the 2 an entity script tests — and the condition comes out
of **dominance** rather than of folding the code: this is straight-line MIPS
with forward branches, so a store is reached only if every branch jumping over
it fell through, and a store branches jump *to* is reached when they were
taken. That answers 20 of the 47 writes with a real condition and says
"nothing jumps over it" for the unconditional rest, instead of borrowing a
guard from whatever test happened to be nearby.

The numbers group by level, which is the flags' coarse meaning:

| flags | written by the overlay of level |
| --- | --- |
| 1–7 | 0 |
| 11 | 1 |
| 16–21 | 2 |
| 22–26 | 4 |
| 30–32 | 5 |
| 33–39 | 6 |
| 42 | 7 |
| 45–49 | 8 |
| 50–54 | 9 |
| 60 | 11 |

and the conditions name the quest each one stands for — `story_flags[7]` on
level 0 wants items 0, 100 and 133 together, `story_flags[3]` wants the sword's
final stage and the three seals, `story_flags[48]` on level 8 wants item 16.

### Objects the game places and does not draw

**Type 299 is a readable marker, not a model.** `MO.T[299]` is a box 2088 by
4096 by 4116 — two cells across and two tall — carrying fourteen primitives,
which is a hundred times coarser than the next coarsest model in the game, and
**all 76 of its instances across the 28 levels carry a text index**. Seventy-six
is also exactly how many readable things `tools/readables.py` finds. It is the
volume that says an inscription can be read here, and it stands on the same cell
as the thing actually there: at level 0 (47,12) that is type 253, at (49,19)
type 301, the *Broken Cart*.

Drawing it put a stone column over both. That is how it was caught: a player
looked at the port beside the emulator and said the bull's head and the cart had
turned into pillars, and a monument elsewhere with them. No automated check was
going to notice — the column is geometry from the game's own archive, correctly
parsed, correctly placed and correctly lit.

The reason is read now: type 299 is class `0x14`, and `load_object_placement`'s
arm for it zeroes the record's `+0`, which `render_walk` ANDs with the view
byte. So the port no longer keeps a list -- `tools/objload.py` says which
records are drawn, by the game's own rule, for every level.

### The turn, which was the last guess in the port's movement

`godot/player.gd` carried `TURN_RATE = 24` with "A GUESS" written beside it.
The real thing is in **`player_look` (`0x8002f5c0`)** and it is the same shape
as the walk:

```
cap  = player_turn_max            0x801b2668, a word
rate = player_turn_rate           0x801b264c, s16

held left      rate += cap >> 2, clamped to  +cap     0x8002f5e0
held right     rate -= cap >> 2, clamped to  -cap     0x8002f648
neither        rate moves cap >> 2 towards zero       0x8002f6b4, 0x8002f6ec

facing = (facing + rate) & 0xfff                      0x8002f738
```

So a turn keeps going for a few frames after the button is let go, exactly as
the ground speed does — and `player_walk` uses the same quarter of the cap, which
is now three places that rule turns up.

**The cap is not constant, and a player can feel it.** `player_controller`
writes `0x20` into it every frame (`0x8003118c`) and then **`0x28` instead when
neither `bind_forward` nor `bind_back` is held** (`0x800311a4` branches past the
write when either is down). Out of `0x1000` to the circle that is 2.81 degrees a
frame walking and 3.52 standing still: **you turn about a fifth faster when you
stop**.

There is a third case: while `turn_slow_timer` (`0x801b2566`) is running,
`0x80031254` halves the cap every frame and `0x8003125c` counts it down. It is
`player_take_hit`'s effect 5 that starts it -- see "The run" below.

The order the four run in is off `player_controller`'s own call list —
`player_turn` (the button edges), `player_look` (the turn and the pitch),
`player_walk` (the speeds), then `player_vertical` or `player_move`. So the
facing a step uses is *this* frame's turn, which is what the port now does.

### The run: USE held

Both caps -- the speed's `0x801b2664` and the turn's `0x801b2668` -- are only
where `player_controller` starts each frame (`0x80031180`, 200 and the turn
above). Before `player_turn` runs it grows both by a signed half,
**`0x801b24f6`**, which it ramps by one of three rules (`0x800311b4`):

```
turn_slow_timer (0x801b2566) running:
    under 0x40 left   mod += 0x64, to at most 0
    else              mod -= 0x64, to at least -0xce4
    turn cap >>= 1, the timer -= 1
0x801b24f5 == 0       mod += 0x320, to at most 0xaf0
else                  mod -= 0x320, to at least 0
speed cap += mod * speed cap >> 12                     0x80031318
turn cap  += mod * turn cap >> 13                      0x80031330
0x801b2568 running    both caps 0, the timer -= 1, the forward and strafe
                      speeds halved                    0x80031344
```

and `player_turn`, later the same frame, sets the flag: **USE held this frame
and the last** (`0x801b265c`, `0x801b265e`, `bind_use`) counts `0x801b24f5`
down to 0 (`0x8003005c`), anything else puts it back to 1 (`0x800302a8`). So
holding USE for two frames runs: from the third, the cap climbs 39 a frame to
**336** (`200 + 0xaf0 * 200 >> 12`) and the turn to `0x20 + 0x15`; let go and
it falls back as fast. With the groundal boots (`0x4c`) on the feet
(`0x801b25d8`) the held branch is skipped altogether, so they cannot run. The
same branch is
what drains both meters by 500 a frame and lowers `damage_scale` -- the
running costs stamina and defence (see "The player's blow").

`turn_slow_timer` is `player_take_hit`'s effect 5 and `0x801b2568` its effect
4 ("What a hit takes off"): the one slows the player to `200 - 0xce4 *
200 >> 12` = 39 and halves the turn, the other stops both. A new character
and a loaded save start the flag and the ramp at 0.

`tools/replay.py` replays the rule over bp16's logged caps, **150 129 of
150 129 frames**, 92 of them above 200; `godot/player.gd` copies it as
`frame_caps` and `run_flag`, and `godot/selftest.gd` runs those over the same
frames (`runcheck.json`), 150 129 of 150 129.

### The head bob

The tail of `player_vertical`, at `0x8002f298`, and worth writing down because it
was **reported from play before it was found in the code**: walking into a wall
still bobs the camera.

```
phase = (phase + magnitude of the step) & 0xfff        0x801b2652
v     = sin(phase) >> 5
bob   = |v| - (|v| >> 2)                               0x801b2650, peaks at 96
camera height = (player Y + 0x640) - bob - crouch      0x801b2640, at 0x80028e24
```

A *rectified* sine, so two lifts a stride — one a footfall. The phase accumulates
the magnitude of the step the routine asked for, not the distance actually
covered, so being pressed against a wall keeps the gait running while the
position does not move. `godot/player.gd` reproduces it, including that.

### player_move, which does run — when you are thrown

`player_move` (`0x8002f320`) is the mover for the knockback and death states. The
position is three s32 at `0x801b25f0` and the velocity three s16 at
`0x801b266c`; radius `0x320`, body height `0x6a4` and collision flags `0x31` are
literals in the routine. One frame:

```
n = p + v
if collide(n) is clear:                       commit
n.y = p.y                                     try again at the current height
if that is clear:  v.y = 1;                   slide by 0x20, then commit
if mask & ~0x205:                             refuse -- nothing moves
if surface + 0x100 < p.y:                     refuse -- the step is too high
n.y = surface                                 step up onto it
                                              slide by 0x38, then commit

commit:  p = n;  v.y += 0x20
```

Three readings, each of which the Godot build had wrong:

* **Gravity is `+0x20` a frame and is never cleared.** There is no grounded
  state and nothing zeroes the velocity on landing. Standing still, `v.y` cycles
  1, 0x21, 1, 0x21: the full step is refused by the floor, the horizontal-only
  step is clear, so `v.y` is reset to 1 and the position commits unchanged. The
  player therefore rests in a band a few tens of units above the surface rather
  than on it, and **nothing ever snaps the player onto a floor** — where a fall
  stops depends on the last step taken.
* **A step up is at most `0x100`**, two height units of 128, measured against
  the nearest surface the blocked query returned, and it is taken with no
  further check. That is the stair rule.
* **A wall is steppable.** `mask & ~0x205` is the hard block and `5` is exactly
  what a wall handler contributes, so a wall low enough passes the `0x100` test
  and is climbed. This is the same reading as "a low wall is climbable" above,
  now with the number that decides it.

`slide` shortens the horizontal velocity by a fixed amount rather than
projecting it along the wall, and stops the player outright when what is left is
shorter than that amount. It is the velocity that is shortened, so the effect
lands on the following frame.

The one thing not read off the code is the **tick rate**: the routine runs once
a frame and gravity is per frame, so the arc of a fall depends on how many
frames there are in a second. `tools/movement.py` assumes 30.

Against the 69 frames `emu/bp14.lua` recorded, `tools/movement.py` reproduces
**69 of 69 exactly**, position, velocity and return code — so the transcription
of *this* routine is checked, for the state it actually runs in. What the same
recording showed is that the state it runs in is not walking.

Two other routines write the player's Y and neither is movement:
`place_player_on_terrain` (`0x8002b760`) drops the player onto the terrain when
a level is entered, and `0x80031d9c` in the controller teleports on item 107.

`select_cell_layer` (`0x800324f0`) belongs here too, because the collision
wrapper calls it first: a cell is **two** five-byte layers, and which one a
query lands in is decided by the height of the *middle* of the body,
`y - (height >> 1)`, against the two layers' own heights. A bridge over a room
needs both. `tools/collision.py` ignored this and was right to — it is handed a
cell and a base by the log — but anything simulating a position has to do it.

**The mask is what the routine returns**, in `$v0` from `$t4`, and each handler
contributes its own kind: 5 for a wall, 4 for a floor. Reading it out of the
struct at `0x801e6470` instead does not work — ten call sites reach the wrapper,
`object_motion` among them, so every monster overwrites it. That is what
`emu/bp13.lua` exists to avoid: it takes the arguments at entry and the mask at
exit, before it is returned.

**Two constants confirmed from the code, having first been guessed:** the grid
is at `0x801d4464` and a cell at `+ cz*800 + cx*10` (`0x80033b8c`), and
`base = -128 * cell[+6]`, formed as a `negu` and a shift by 7 (`0x80033bec`).

The earlier answer, for the record, read `0x20`–`0x25`, `0x31`, `0x32` as walls
and scored 90.6 % precision against the game's own map. That number was wrong,
and the way it was wrong is worth more than the attempt.

`mapcheck.score` counts an edge as predicted correctly when ink appears anywhere
in the two-pixel band along it. On a map drawn as densely as this one, that is
nearly always true, so a predicate can be badly wrong and still score above
90 %. Recall of 25 % was the real signal and it was explained away as an artefact
of the oracle rather than treated as the warning it was.

Rasterising the prediction at the map's own scale gives **2631 pixels ours
alone, 2638 theirs alone, 361 agreeing** — twelve per cent, and laid over each
other the two are visibly different geometry. That is what a hand-drawn map
against a collision model looks like, so it settles nothing either way, and the
maps stop drawing walls until there is a test that can.

Along the way the face table itself turned out to be **mirrored in X**: faces 0
and 2 were the wrong way round, which alone cost the decode two thirds of its
agreement with the map, 17 % against 45 %. That was read out of handler `0x20`
before any of the live work, and is the reason the rest of it was worth doing.

**The game's own map is a weak oracle, and was never the right one.** `ITEM.T`
721 is the level 0 map the player carries, 160×160 for the 80×80 grid. It
settles orientation outright — the Z-flip matches 72 % of the drawn walls where
every alternative manages about 23 % — but it is a drawing, at two pixels a
cell, and walls sit *inside* cells at offsets it cannot represent. It cannot
adjudicate an individual edge. The game's own collision answers can, and do.

`mapcheck.agreement()` remains useful as a sanity check and `tools/mapcheck.py`
still scores cell fields: **no cell field predicts the walls** — the void
boundary catches 9 % of drawn edges, height changes 18 %, the `+9` bit 26 %, and
a change of tile shape id 63 % at 40 % precision. Walls are part of the **tile
shape**, not of the cell.

### How a cell is drawn — a separate path from how it blocks

The renderer walks cells at `0x8003be50`, and it is recognisable at sight: it
forms the cell's world position as `cx << 11` and `cz << 11`, subtracts the
camera, adds `0x400` to reach the cell centre, takes the floor height as
`-(cell[+6]) << 7` — the same `128` unit as everywhere else — and drops the
three into the scratchpad at `0x1f800100`. Cells with `cell[+5] >= 0xf0` are
skipped, which is the solid-rock test.

It then calls **`0x8003bb04`, the tile drawing routine, with the same layer
pointer collision uses**, `&cell[+5]`. What it does with it is the discovery:

```
lbu $s1, 2($s3)        cell[+7] & 3      the orientation
lbu $v0, 4($s3)        cell[+9] & 0x3f   a six-bit index, not flags
record = 0x801aeefc + index * 108
entry  = record + orientation * 20
lw $t5, (entry) ; lw $t6, 4(entry) ; ctc2 ...
```

**`cell[+9]` is not merely flags.** Its low six bits select one of 64 records of
108 bytes at `tile_look`, and reading what the record is *for* needed
`tools/fdis.py`, since capstone stops dead at coprocessor 2 and this routine is
mostly coprocessor 2. It is **lighting**, not geometry:

| Offset | Size | Goes to |
| --- | --- | --- |
| `+0x00`..`+0x4f` | 4 × 20 | `L11L12`..`L33`, the light *direction* matrix, one per orientation |
| `+0x50` | 20 | `LR1LR2`..`LB3`, the light *colour* matrix |
| `+0x64`..`+0x66` | 3 | `RBK`/`GBK`/`BBK`, the background colour, shifted left by 4 |
| `+0x68`, `+0x6a` | 2 × 2 | arguments to `0x80035358` |

So `cell[+9]` is the cell's **lighting class** and the orientation swings the
light directions round with it. Computed out over level 0 the way the GTE does
— `IR = clamp(LLM . normal)`, then `colour = (BK * 4096 + LCM . IR) >> 12` — the
result runs 0.47 to 1.34 with a median of 0.89 and **never reaches black**,
because the background term is added after the light. Anything black in a port
of this level is the port's own doing. The table is zero inside `GAME.EXE` and filled
at runtime, and `tools/lighting.py` builds it off the disc exactly. Level 0 uses four
of the 64: index 0 on 4755 cells, 4 on 97, 3 on 45, 2 on 24.

**`cell[+5]` is a TMD object index — the cell's own little model.** This is
where the visible form lives, and the old note calling it a texture id
understated it:

```
lbu   $a0, ($s3)              cell[+5]
v0 = a0 * 28                  objects are 28 bytes
v1 = [0x1f800010]             the model file's base
v0 = v1 + 12 + a0 * 28        past the 12-byte TMD header
lw    $v0, ($v0)              the object's first word is vert_top
v0 = v1 + 12 + vert_top       TMD offsets run from the end of the header
jal   0x8003ab04              draw it
```

Twelve-byte header, twenty-eight-byte objects, offsets from the end of the
header: that is the TMD layout exactly. Every cell of the world is a small TMD
object, picked by `cell[+5]`, turned by `cell[+7]`, lit by the class in
`cell[+9]`. Brick against rough clay is therefore a different *model*, not a
different texture id, and the textures ride along inside its primitives, which
carry their own page, CLUT and UVs the way TMD always does.

**And the file is `RTMD.T[level]`.** The base the renderer reads from
`0x1f800010` was `0x8014f164` in a running game, and the 182 272 bytes there are
**byte for byte identical** to `RTMD.T` entry 0. Every one of the archive's 28
entries is a TMD of exactly 240 objects — one set of tile models per level.

That makes the world's appearance static: no emulator is needed to extract it,
only a TMD reader, which is a published format.

**The TMD reader works** (`tools/tmd.py`). `RTMD.T[0]` holds 240 objects, 5100
vertices and 3485 primitives, and **not one vertex reference lands outside its
own object** — which is the check that caught the one thing the published format
does not prepare you for here: the references are **byte offsets, not indices**.
The first quad of object 174 reads 8, 0, 16, 24, and at eight bytes a vertex
that is 1, 0, 2, 3. Read as indices, ten thousand of them run off the end.

Every primitive is textured — 2055 quads and 1414 triangles of modes `0x24` and
`0x2c`, plus a handful of semi-transparent `0x26`/`0x2e` — and all of tile 174's
name the same page and CLUT, so a tile model carries one texture.

### `RTIM.T` — the textures those primitives sample

Not TIM files despite the name. 28 entries again, one per level, each a run of
VRAM upload blocks:

```
s16 x, y, w, h        where in the 1024x512 framebuffer it goes
s16 x, y, w, h        the same rect a second time -- a 16-byte header
u16[w * h]            the halfwords
```

The doubled rect is what makes a block findable, and blocks are padded to an
alignment worth no effort to pin down: scanning for the next doubled rect
recovers **98 blocks and 231 424 of level 0's 233 472 bytes**. `tools/rtim.py`
lays them into a framebuffer, and `page` expands one through its CLUT.

Level 0's page 7 under CLUT `0x7a00`, which is what every primitive of tile
model 174 asks for, is brickwork, cobble and rough clay — the surfaces the level
is actually built from.

**None of this reads the tile shapes.** Collision and appearance are two
independent descriptions of the same cell: `cell[+8]` indexes the one,
`cell[+5]` and `cell[+9]` the other.

### Entry `3n + 1` — the entities on the level, and their scripts

```
u32            size of everything below, slots and scripts together
<record>[40]   120 bytes each, a fixed array; unused slots are all 0xff
...            the script block, starting at 4 + 40*120 = 4804
```

**The `u32` is a size, not an offset.** Reading it as the script base put the
decode 8192 bytes past the scripts, and everything §9 first said about them was
wrong as a result. The real base is fixed: the entity array is 40 slots whether
the level fills them or not, and the scripts follow. At that base the disc
matches RAM **byte for byte over 3000 bytes**; at the old one, 7 %.

**There are far fewer entities than the notes used to claim.** "~121 populated"
came from dividing the whole 28 672-byte entry by the record size, which counts
the block area as records. Reading it properly gives 16 entities on level 0,
12 on level 4, 10 on level 7 — **265 entities and 1617 blocks in the game**.
Reader: `tools/entities.py`.

A record ends with **sixteen** `u32` offsets into the block area, at `+0x38`
through `+0x74`, and `entity_table_init` (`0x80053084`) is what settles the
count: it walks 40 records and, for each, 16 words from `+0x38`, turning
`0xffffffff` into a null pointer and everything else into `offset +
entity_scripts`. Unused slots are `0xffffffff` and sit at the tail. The
offsets are monotonic across the whole level, so the area is one sequential
stream that the records carve up.

**The list starts at `+0x38`, not `+0x3c`.** Reading it one slot late dropped
every entity's block 0 and renumbered the rest, and that is the single mistake
behind every wrong claim this document made about entity scripts.

Each block begins with a **kind byte** and carries `0xff` at `+4`. **Only kind
`0x70` is a conversation** — `script_interpreter` tests for exactly that — and
it is always block 0. Forty-three entities in the game have one. Nothing in
`GAME.EXE` reads blocks 1..15; they are relocated for the level's own overlay
and what they mean is not settled.

A conversation block is a 20-byte header and then code: the TALK.T base at
`+0x0c`, the program counter at `+0x10`, what happens when the talking stops at
`+0x12`, the retry flag at `+0x13`, and `pc` counting from `+0x14`.

Fields, from columns that vary sensibly across the 265 records
(*names unverified*, they are read off the shape of the values):

| Offset | Looks like |
| --- | --- |
| +0x00 | a kind byte; +0x01 is `0x04` on every record, which is what identifies a record |
| +0x12 | HP — 1000, 1400, 800 on the first level-0 entities |
| +0x18 | scale, `0x1000` = 1.0, as everywhere else in this game |
| +0x1e..+0x36 | a run of `u16` stats, in the same shape as the player's ratings |
| +0x3c.. | the script offsets |

The records are loaded to `entity_table`, `0x8018c7e8`, keeping the 120-byte
stride, and thirteen pieces of code reach them — including the same walk inside
`object_motion` that steps the object table. Past roughly byte 40 the live copy
has already diverged from the disc, which is what a record being mutated as the
entity acts looks like.

On load the offsets are **relocated into absolute pointers** in place, and the
list starts at **+0x38**, not +0x3c — reading it from +0x3c loses the first
script of every entity. The pointers gave the block's address for free: entity
0 of level 0 has offset 0 pointing at `0x8018daa8`, so the script block sits
`0x12c0` past `entity_table`, which is 40 record slots — the array is a fixed
40 entities and the scripts follow it.

The opcodes are decoded; see §9.

### Entry `3n + 2` — the level's own code

4096 bytes: a `u32`, then 32 pointers into `0x801e8xxx`, then **MIPS machine
code**. Every level ships its own routines. See §12 — this is the piece that
explains why so much was missing everywhere else.

Renderers: `tools/maps.py` (all levels), `tools/level_map.py` (one level in
detail).

---

### What a frame is

`game_main` (`0x80014bd4`) zeroes twelve tables, loads a level, and then runs
**sixteen calls in a loop** until the word at `$gp+0x1e4` goes non-zero. That
word is how the game ends: 2 writes `0` into the shell's `next_exe` and goes
back to `OPEN.EXE`, 3 and 4 both go to `END.EXE` with `overlay_arg` 2 and 3.

| | | |
| --- | --- | --- |
| 1 | `light_table_reset` | `0x800341e8` — the 64 lighting entries refilled from `0x80081c8c` |
| 2 | `render_flags_reset` | `0x80034180` — eleven flags at `0x801aeafa` to their defaults |
| 3 | the object interpreter | `0x80047010`, with its own 236-arm switch |
| 4 | `player_controller` | `0x80030fcc` — pad, then turn, look, walk, height |
| 5 | `actor_tick_driver` | `0x80052e5c` — the 199 creature slots |
| 6 | `effect_driver` | `0x8005bc50` — 128 effect slots, each into `effect_tick` (it was called `ai_driver` here; see `data/symbols.json` for why it is not) |
| 7 | `spawn_anywhere = 0` | `0x801b24f2`, cleared every frame |
| 8 | `level_overlay_tick` | `0x8005eb20` — the level's own code, through `[0x8018fae0]+4` |
| 9 | `level_load` | `0x80018358` — acts only when a transition is pending |
| 10 | `cutscene_step` | `0x80061940` |
| 11 | `camera_pose` | `0x8002b330` — the eye and the three view angles |
| 12 | `audio_listener_set` | `0x800156bc` — the same pose, for 3D sound |
| 13 | `light_table_step` | `0x80034300` — the three turned copies of each light matrix |
| 14, 15 | the **resource queue** | `res_upload_vram` pushes a texture into VRAM when the request at `0x801c1728` is type `0x40`; `res_upload_spu` hands sound to the SPU at `0xa000` when it is `0x30`. One queue, two kinds of payload |
| 16 | `render_frame` | `0x800422b8` |

**The eye is `player_y + bob + crouch - 0x640`.** `camera_pose` forms it that
way and `sync_player_pos` adds the same `0x640` back when it compares the eye
with the three surface planes, so 1600 units is the eye above the feet — beside
a body height of `0x6a4` = 1700.

### And what render_frame is

Twenty-two more calls, and the shape is a PlayStation renderer exactly:

```
view_pose_set          0x800357e8   the pose into player_pos_view, and its cell
texture_scroll_step    0x800351fc   two VRAM rects moved: the water and the lava
message_tick           0x80041f9c   the on-screen banner queue
view_matrix_build      0x80034bf4   three game_cos/game_sin pairs into the GTE
frame_begin_3d         0x80035630   flip the buffer, ClearOTagR on 0x2000 entries
effect_timers_step     0x80043858   twelve byte timers at 0x801aab64
draw_held_item         0x8003df50   the thing in the player's hands
draw_model_cell_lit    0x8003c35c
draw_terrain           0x8003bfd0   the cell walk, into draw_tile
render_walk            0x80040ae4   the creatures, then the objects
overlay_plane_18       0x8003d280   the screen tint for being under that plane
overlay_plane_19       0x8003d38c
overlay_plane_17       0x8003d41c
frame_end_3d           0x80035700   DrawSync, PutDispEnv, PutDrawEnv, DrawOTag
resource_sweep         0x80043940
```

The three overlays are what closes the loop on the surface planes: collision
opcodes `0x17`, `0x18` and `0x19` place them, `sync_player_pos` measures how
far the eye is under each, `player_throw` fires when it goes under, and **each
depth has its own full-screen tint**. `0x801b2640` was named `camera_height`
from where it is formed; it is the third of those depths.

**`tile_look`'s stride is 108 bytes**, read off `draw_held_item` forming
`tile_look + 108 * (cell[+9] & 0x3f)` — 64 entries, refilled every frame.

`godot/game.gd` carries this order with each step either wired to the port's
copy or naming the address it stands for and saying nothing runs. Six of the
sixteen exist.

### Looking up and down: the other half of `player_look`

`player_look` (`0x8002f5c0`) turns the facing and then tilts the view. The
pitch, `0x801b2610`, is driven by a rate at `0x801b264e`:

```
look_b held (R2 in scheme A)   rate += 3, at most  0x20     looking down
look_a held (L2)               rate -= 3, at least -0x20    looking up
both                           back to level: the rate steps by 8 toward the
                               pitch that is left, no more than a quarter of it
neither                        the rate decays by 3 to 0
then                           pitch += rate, stopped at 0x2bc either way
                               (sub_80016a78 compares angles centred on 0)
```

The rate is the eighth halfword of the block `emu/bp16.lua` logs, and the rule
predicts it on **118 501 of 118 502** recorded frames, 1086 of them with a look
button held or the rate moving; the one it misses is a frame where CIRCLE opened
the menu. `godot/player.gd` runs it at 15 frames a second, so A and F -- L2 and
R2 on the emulator's keys -- tilt the port's view as they do the game's, and the
mouse moves the same pitch within the same limits.

### A step the game refuses: `player_horizontal`

`player_horizontal` (`0x8002e3f8`) asks `collide_query` about the destination at
the player's height with flags `0x31`, and when the answer is not clear:

* **a step up** is still taken if the mask has nothing outside `0x207`, the
  surface found is no more than `0x500` above the feet, the player state
  (`0x801b25e5`) is 0 and the ceiling leaves room for the body (`0xf95c`,
  -0x6a4). A wall's top is its surface, so a wall more than `0x500` high is
  never climbed;
* otherwise the same step is **tried shorter**, `0x16` at a time, once, and
  the first clear one taken -- a second `collide_query` in its own loop;
* then it **slides**: the X part dropped, then only the X part; against a
  diagonal wall (mask bit 2) along the diagonal the cell's rotation picks --
  `(dx + dz) / 2` both ways for rotations 0 and 2, `(dx - dz) / 2` and its
  negative for 1 and 3;
* and if none of that is clear, the player stays.

The port had none of it: `_move` took every step and `player_vertical` then
lifted the player onto whatever was in the way, so any wall could be climbed,
which a player reported. `tools/movement.py` and `godot/player.gd` carry it
now. Against the recorded walking, `tools/replay.py`'s rung 2 goes from 113 747
to 117 686 of 118 500 frames exact, and the frames it put down to the wall
slide from 4170 to 271.

### Objects in the way: the rest of `player_horizontal`

The `0x31` the player asks with has bit `0x20`, the objects. `collide_query`
(`0x80033f38`) goes on past the tiles only where the cell under the query has an
occupancy count -- byte +2 of its first layer, `& 0xfc` -- which `grid_mark`
(`0x80033c4c`) raises by 4 for every cell within an object's radius + `0x800`
at load. The player marks itself too, but `player_controller` takes its mark
off (`grid_mark(.., -1)` at `0x80031008`) before it moves and puts it back
(`0x800320d8`) after, so the player never runs into itself. Then
`object_collide` (`0x80045ac8`) answers with the first slot hit, the mask gains
`0x20`, and `current_object`, which it skips, is 0 by then -- the interpreter
clears it (`0x8004b4ec`) when its pass ends.

The two tests take the player's radius `0x320` and height `0x6a4`:

```
in_range          0x80016ec8   |dx|, |dz| <= r first, then the heights overlap,
  (pos, x, y, z,               then isqrt((dx>>3)^2 + (dz>>3)^2) << 3 <= r;
   r, top, own)                heights: at pos.y < y fail if pos.y < y - own,
                               else fail if y < pos.y - top (Y grows down)
in_oriented_rect  0x80016d3c   the offset to polar -- length by the root,
  (ang, pos, x, y,             bearing by vec_angle(x - pos.x, z - pos.z) --
   z, a, b, top, own)          and back out along the object's axes:
                               cos/sin(bearing - ang + 0x400) * length >> 12,
                               each within its half-extent; heights as above
```

What `player_horizontal` does with the answer, in the listing's order, after
the step up and before the wall's shorter tries:

* **an object whose byte +3 has bit 4** -- a rectangle -- is slid along. On the
  first try the step's bearing, `ratan2(dz, dx)` (`0x80074380`, the library's,
  over 1025 entries at `0x8009594c`), less `0x400` less the object's angle at
  +0x26 is kept at `sp+0x68`; each try turns the full step length into that
  frame and keeps one part -- the second on tries 1, 3 and 5 unless it is zero,
  the first on 2, 4 and 6 likewise -- and turns it back by the object's angle
  plus `0x400`, `0x3e8` or `0x418`. So a slide that fails is tried again
  24/4096 of a turn either side of square. The seventh try falls through;
* **anything else in the way** is gone round. `collide_target` (`0x80033d84`)
  puts the thing's position at `0x801e64a0` and its radius at `0x801e64b0` --
  a creature's +0x1c when `collide_query` found one, else the object's: the
  row's +4 scaled by +0x38 over 128 on byte +3 bit `0x10`, the row's +0x10 on
  bit 4, the row's +4 otherwise -- and the step becomes the point at radius +
  `0x370` from the centre along the bearing from the centre to where the step
  was going, each part rounded towards zero. If that point hits a thing too,
  the player stays where it is (`local_58` reaching 2).

**Checked**: 455 frames of the recorded walking touch an object -- 302 round
ones and 145 rectangles -- and 447 come out exact, which took rung 2 to
118 207 of 118 500; the ramp's push and the ceiling ("The ceiling, the push")
took it to **118 288**. Of the 212 left, 140 are within reach of a swinging
door, whose shove and restamped grid a recording of the player alone cannot
replay; 12 the model turned away at a wall; 60 the model took whole and the
game did not, which is creatures -- they collide with the player through bit
`0x10` and knock it back, and the log does not hold where they were. The
self-test holds `godot/player.gd` to the Python on 750 steps, 200 of them into
an object and 100 pushed by a ramp.

**And the creatures.** Bit `0x10` of the player's query is `actor_spot_taken`
(`0x8004d644`): the first of the 200 actor slots whose `+9` is 1 -- awake, and
drawn -- whose `+0xe` is not 3, that is not `current_actor`, and whose flags
word at `+0x28` has no bit in common with the byte at `0x8018faa8`, within
`in_range` of the point: its `+0x2c` position, its radius `+0x1c` plus the
asker's, its height `+0x1e` against the asker's. The flags are the entity's
`+0x34`, copied by `actor_copy_kind` (`0x8004b67c`); the byte is 4 while
`player_controller` moves the player (`0x80031004`, cleared at `0x80032104`)
and 0 otherwise, so **a creature whose flags carry 4 lets the player through**
-- on level 0 the ten of kind 15, flags `0x404`, radius 0 -- and none of the
others does. A follower (flag `0x10`) is tested `+0x26` higher and skipped when
its `+0x22` equals `0x8018fac0`. The answer lands at `0x801e648c`, and
`collide_target` prefers it to the object: the push-out goes round the
creature's centre at its radius + `0x370`.

`game_main` runs `object_interpreter`, then `player_controller`, then
`actor_tick_driver`, so the player collides with the creatures where the last
frame left them -- which is where `emu/bp16.lua` now logs them (`act=`), at the
start of the controller. **Checked on a recording**: the first session with
`act=` -- 1 293 frames of level 0 among its creatures -- ran into a logged
creature on 76 frames, and all 76 come out exact, going round it with the
creature's radius. `godot/player.gd` asks `actors.gd`'s awake ones, and the
self-test holds it to the Python on 384 steps made into level 0's creatures
from eight sides each. The same session's six frames that differ were one
knock-back, a push of 224, 193, 162, 131, 100 and 66 in one direction -- a
blow, and all of it is reproduced now ("A blow knocks the player back").

### How long a frame lasts: four vertical blanks

The port ran its movement at 30 frames a second on the strength of two
wall-clock measurements -- 26 and 34 -- taken from an emulator that runs
uncapped under the interpreter, which cannot measure the console at all. The
code settles it without a recording:

```
timers_init    0x8001a438   OpenEvent(RCntCNT3, ..., vblank_tick) and start it:
                            root counter 3 is the vertical blank
vblank_tick    0x80019570   each blank: frame_vblanks += 1, vblank_count += 1,
                            and play_minutes += 1 every 3600 of them
render_frame   0x800422b8   ... frame_end_3d (DrawSync, VSync(0), the flip),
                            then frame_limit, then resource_sweep
frame_limit    0x80019614   while frame_vblanks < 4: VSync(0)
                            frame_vblanks = 0
```

**A frame lasts at least four blanks, so the game runs at 15 frames a second**
at NTSC's 60 -- the 3600 blanks to a minute of play time is the game saying
60 itself -- and slower only when a frame's own work takes longer than four.
Nothing scales movement by elapsed time: every speed, turn rate and fall in
section 4 is per frame, so the port at 30 walked, turned and fell twice as
fast as the game. `godot/player.gd` and `godot/actors.gd` tick at 15 now.

### Semi-transparency, texel by texel

A TMD primitive whose mode has **bit 1 (ABE)** set is semi-transparent, and the
PlayStation applies that per texel: a CLUT colour with **bit 15 (STP)** set is
blended with what is behind it at the texture page's rate -- tpage bits 5 and 6:
0 half and half, 1 adds, 2 subtracts, 3 adds a quarter -- any other colour is
drawn solid, and colour 0 is not drawn at all. Across the game 11 318 textured
primitives carry ABE: 7916 at rate 0, 3045 at rate 1, 356 at rate 3 and one at
rate 2. On level 0 the tiles have sixteen, and all sixteen are the water, whose
CLUT has STP on every colour but 0.

The port drew them all solid, so its water was a bright blue sheet where the
game's is dark and shows the channel's bed through it. `tools/level3d.py` now
keeps semi-transparent primitives in materials of their own, blended, with the
texture's alpha carrying the rate for STP texels; rates 1 to 3 are named `_add`
or `_sub` for `godot/scroll.gd` to set the blend the glTF cannot. One thing it
approximates: in an adding material a texel without STP adds as well, where the
console would draw it solid. `tools/shots.py b` shows the water beside the
game's own screenshot.

### How far the game draws, and how it darkens

Every drawing routine -- `draw_tile`, `draw_model_lit`, `draw_model_plain`,
`draw_model_cell_lit`, `draw_held_item` -- calls `fog_range_set` (`0x80035358`)
with the `+0x68` and `+0x6a` of the lighting record of the cell it draws, a
**near** and a **far** in view-space Z. It keeps both at `0x801aec7c` and
`0x801aec80` and hands only the near to `SetFogFar(near, 200)` (`0x80077ad8`:
DQA = -320 * near / 200, DQB = 0x1400000); the tiles do not use that automatic
cue. `draw_tmd_object` (`0x8003ab04`) instead works out, for every vertex,

```
t = (SZ - near) * 4096 / (far - near)      0 below near, capped at 0x1f0f
```

-- 0 when near is 32000 or more -- and before each face's `NCDS` sets `IR0`
to the mean of its three vertices' `t` (the multiply by 0x55555556 is the
divide by three). NCDS then gives `colour + IR0 * (FC - colour)`, clamped at 0,
with the far colour FC set once to `5 << 4` (`0x8003551c`). So a face fades
from its lit colour at `near` to all but black at `far` and to black past it.
Level 0's class 0, on 6234 of its cells, is near 18000 and far 22000 -- 8.8 to
10.7 cells -- which is the black the game's screenshots show beyond about ten
cells. The tiles' vertices and their cell offsets are in world units -- the
view matrix is unscaled, rows of 4096, in every snapshot -- so SZ is the
distance along the view and the ranges are world units.

**In the port:** `tools/level3d.py` gives every vertex its cell's lighting-class
near and far as TEXCOORD_1 (tiles by their own cell, objects and creatures by
the cell they stand in), and `godot/scroll.gd` replaces every material of the
world with one shader that works out `t` from the view depth and draws
`texel * max(colour + t * (5/128 - colour), 0)`. It blends `t` per vertex where
the game takes one per face, the mean of its three. `tools/shots.py b` shows
the far wall's surroundings going to black, as the game's screenshot does.

The sky is not the cue's business; it is the next section.

### The sky: a dome on the eye, at the back of the ordering table

Looking north-east from level 0 the game draws a dark red, clouded sky over the
black horizon (`out/snap/inv1.png`). It is an **object**. `render_walk` gives
class `0xf0` a path of its own (`0x80040fac`): while `sky_on` (`0x801aeaea`) is
set and `object_in_view` passes -- with +0x38 and +0x39 both 0x28, forty cells,
it always does -- it draws `model_table[type - 0xdd]` through `draw_model_at_eye`
(`0x800400ac`):

```
matrix       the record's angles at +0x24 (sub_800166f4) turned by the view
             matrix -- and no + 0x800, which the ordinary path adds
translation  (0, 0x64, 0), set before the angles and never replaced: the
             model sits on the eye, 100 below it in view space, wherever
             the player stands
light        tile_look[+0x3b & 0x7f]: L at +0, colour at +0x50, BK at +0x64
depth        0x1fff - +0x3a, and sub_80039428 (0x80039ca8) files every face
             in the 8-entry side table render_walk hands it (0x801a9178,
             cleared by frame_begin_3d) at that & 7; frame_end_3d links the
             side table into the main one at 0x1ffe, so the dome is drawn
             before anything the world puts in front of it
```

Levels 0 to 7 and 9 to 11 place one, always type 265 with +0x38..+0x3b =
`28 28 00 3d`, and 25 places type 264. Type 265 is model 44 of the resident
bank (`FDAT.T` entry 97 block 10, `tools/modelbank.py`): a textured, lit dome
1000 across and 1250 high, 97 vertices and 96 faces, lit by class `0x3d`.

**Zones switch it.** Class `0xe3` objects are rectangles of cells: each frame
the interpreter's arm (`0x8004a954`) asks `player_in_rect` of the record's
cell and +0x38 by +0x39 cells, and one that holds the player writes its +0x3a
to `0x801aeae9` and its +0x3b to `sky_on` -- so the last in slot order wins,
and the value stays when none does; `load_object_placement` does the same once
at load (`0x8004576c`) and `game_main` starts `sky_on` at 1 (`0x80035610`).
Level 0's three zones all say 1; level 3's whole-map zone says 0 and five
smaller ones 1, level 7 turns it off in two small areas, and 8, 12 to 24 and
26 have no dome at all.

The port draws it (`godot/sky.gd`, `skyNN.gltf` and `skyNN.json` from
`tools/level3d.py`): the dome follows the camera, and its shader pushes each
vertex out along its own direction to just inside the far plane and writes no
depth, so it shows only where nothing nearer was drawn -- the back of the
ordering table by other means. `tools/shots.py inv1` puts the port's clouds
where the game's are.

The same records at `0x80081c20` that looked like a sky candidate are not: they
are `draw_model_cell_lit`'s, two 0x24-byte entries switched by the bits of
`0x801b25de`, their +0x18 the pitch and +0x1a the facing, and their
translation (290, 32, 50) -- the top-right corner of a 320x240 screen, where
the "N" of the compass stands in every screenshot.

### The panel: HP, MP and the two meters

The box in the top-left corner is thirty sprites in a table of GAME.EXE,
`hud_sprites` at `0x800819b4`, 0x14 bytes each and ended by 0xff:

```
+0    on       rewritten by render_frame every frame
+1    abr      SetDrawTPage(tpage | (abr & 3) << 5) unless 0xff: 3 adds a
               quarter, 0 and 4 mix half and half
+2,3  u, v     +4,5 w, h      +6,8 x, y on the 320x240 screen (s16)
+0xe  clut     +0x10 tpage (0x1e, the 4-bit page at 896, 256)
+0x12 depth    the ordering-table index, 24 to 40 -- in front of the world
```

`hud_draw` (`0x80041e68`), which `render_frame` calls between the compass and
the terrain, hands every record whose +0 is set to `hud_sprite` (`0x80041ad4`):
a SPRT, semi-transparent, coloured by the brightness byte `0x801b25e1` three
times, with a DR_TPAGE for the rate, both put at the head of the record's
ordering-table entry -- so the larger depth draws first and, within one, the
later record. `render_frame` switches the table by `hud_style` (`0x801b25dd`)
-- records 0 to 12 on its bit 0, 15 to 29 on its bit 1, 13 and 14 never -- and
writes the numbers in:

```
style 2   the default: new_character's options (0x8002b64c) set it and the
          compass's, 0x801b25de, to 2
  17-19   u = 12 * digit + 128 of HP % 1000 (0x801b24fc): hundreds, tens, ones
  22-24   the same of MP (0x801b2500)
  25, 26  w = weapon_meter * 64 / 5000, magic_meter * 64 / 5000
          (0x801b2502, 0x801b2506: the red and blue lines, full at 5000)
style 1
  4, 6    w = 48 * HP / HP max, 48 * MP / MP max (0x801b24fa, 0x801b24fe)
  5, 7    w = meter * 48 / 5000
```

The division by 5000 is a multiply-high by `0x68db8bad` and a shift of 11.
`render_frame_bare` (`0x80030568`), which the menus, the conversations and
`object_interact` call, zeroes both styles, draws a frame and puts them back:
that is why the item menu's screenshot has no panel.

Because the game rewrites the live table every frame, a snapshot's RAM holds
its own answer: `tools/hud.py --check` reproduces **520 of 520** fields over the
13 snapshots, two of them drawn bare. The page itself comes from entry 96 --
cut at a chunk boundary, which is how it was found that the stream loses a cut
block's tail ("The 0x8000 is a chunk"). `godot/hud.gd` draws the panel from
`hud.json`: each sprite as its solid texels and, over them, its STP texels
under the rate's blend, scaled with the window's height; HP, MP and the meters
are the player's, which follow the game's while comparing (`live.txt` fields
14 to 17).

### The compass: a model drawn flat

The ball with the N in the top-right corner is `model_table[0]` -- `FDAT.T`
entry 97 block 9, which is block 10's shape with one model in it: 26 vertices
and 32 faces, 2048 across, the letters W S N E round its equator on page 0x19
-- drawn by `draw_model_cell_lit` (`0x8003c35c`) from `compass_models`
(`0x80081c20`), two 0x24-byte records whose +0 `render_frame` sets from the
bits of `compass_style` (`0x801b25de`, 2 for a new character):

```
+2    class   0x30            +4 model   0
+8    scale   0x40 or 0x55 over 4096, all three axes
+0x10 place   (290, 32, 50)
+0x18 angles  the view pitch, the ball's own yaw, 0
```

The matrix is the library's `RotMatrix` (`0x80076168`), Rx(pitch) Ry(yaw)
Rz(0) with the textbook Ry -- not `rot_matrix_y`'s -- off its own table at
`0x800962e0`, a (sin, cos) pair a word, which differs from the quarter wave
`game_sin` reads on 3 888 of 4 096 angles by a unit or two (it repeats 0 at
2047 and 2048). The class's light direction matrix is turned by it, L R, so the
light stays put on the screen while the ball turns; then the matrix is scaled
and the model goes through **MVMVA alone**: x and y of R v + place are the
screen position, z >> 2 the depth -- no perspective. `model_prims` drops a
face whose NCLIP over its first three points is not positive, and every face
is semi-transparent (modes 0x36 and 0x3e): the texels with STP mix half and
half with the wall behind and the letter's do not, which is why the N reads.

The yaw lags. `render_frame` (`0x80042448`) runs a spring each frame, its
velocity the word at $gp+0xd8: the signed difference to the view yaw
(`0x80016a98`) is added to the velocity, the velocity loses an eighth --
`(v + 7) >> 3` or `(v - 7) >> 3` by its sign -- and the yaw moves by
`v >> 6`, into both records with the view pitch. So the N swings round after a
turn, overshoots and settles. `tools/compass.py --check` holds the switches,
the pitch and the twin yaws on 65 of 65 fields over 13 snapshots; a render
from `a1`'s state with the snapshot's own yaw lays the N where the game's
screenshot has it. `godot/compass.gd` draws it that way, spring and all.

### What the camera sees

`0x80035394`, the graphics set-up `game_main` runs once, calls
`SetGeomOffset(160, 120)` and `SetGeomScreen(200)` -- `ctc2 $t4, H` with 0xc8 at
`0x800353f8`, again at `0x800354d4`, and `sub_8004290c` asks for 200 too -- on a
320x240 screen. So the vertical field of view is `2 * atan(120 / 200)`, **61.93
degrees**, and the horizontal 77.3 at 4:3. The port's camera had Godot's default
of 75 vertical and showed more above and below than the game; it has 61.93 now,
and a render from the `b` snapshot's pose lays the water, the wall and the herb
on the same rows as the game's own screenshot. The eye is `player Y + EYE_HEIGHT`,
0x640 above the feet, formed in `sync_player_pos` -- the port's 1.6 was already
that.

How often a frame overruns is a question for a recording, and a cheap one:
`emu/bp16.lua` logs `vblank_count` beside each frame as `vb=`, and
`tools/replay.py` counts the blanks between consecutive frames.

## 5. Live RAM

Found by diffing snapshots taken around a pickup, then pinned down against
`GAME.EXE`. The object and type tables are at fixed addresses — the same in
every snapshot we hold, and formed from constants in the code rather than
allocated — so nothing here depends on the session.

| Address | Contents |
| --- | --- |
| `0x80011000` | whichever of `OPEN.EXE` / `GAME.EXE` / `END.EXE` is resident |
| `0x8009c800` | end of `GAME.EXE` text; anything below is code |
| `0x800c85e8` | **inventory**, one byte per item id (id 104 went 2 → 3 on pickup) |
| `0x80116e14`–`0x8011ffff` | geometry cache, rewritten when the camera moves |
| `0x80120000`–`0x8014ffff` | GPU packet buffers, rewritten every frame |
| `0x801d11ac` | the level's tile-shape block as it came off the disc — staging, nothing points at it |
| `0x801e4464` | the **working copy** of that block, which is what `0x8003260c` reads |
| `0x8018fb3c` | **object type table**, 332 entries of 24 bytes (see below) |
| `0x80191a5c` | **object table**, `0x44` per record — a fixed address, not per-session |
| `0x801aec4c` | **player position** `s32 X, Y, Z`, mirrored at `0x801b0a10` |
| `0x801b24e0` | **player stat block** — see §5.1 |
| `0x8018fad9` | **current level index** — see below |

### Object table

A fixed array of **396 records** of 68 bytes (`0x44`), `0x80191a5c` to
`0x8019838c`.

**Free slots sit among the live ones, not after them.** Reading the table by
walking until the records stop parsing was wrong, and wrong in a way that hid
itself: level 0 happens to fill its first 158 slots contiguously, so the walk
looked right there, while level 4 frees its third slot and the walk stopped
dead at two records out of 209. Everything the notes below once said about
level 4 rested on those two. A removed object keeps its slot and gets id `0xff`
— literally what the pickup handler writes — so the array has to be read by
index and filtered, which `objects.slots()` now does.

| Level | Live records | Seen before the fix |
| --- | --- | --- |
| 0 | 346 | 158 |
| 4 | 209 | 2 |

**The record boundary was four bytes out for a while.** The table was first
found by diffing snapshots, which fixes the stride but not the phase, and the
phase was guessed wrong. The game's own code settles it: the routine at
`0x8005db40` allocates a record and initialises it field by field, and the
routine at `0x8005dd10` forms the array address as `0x8018fb3c + 0x1f20`, which
is `0x80191a5c` — exactly four bytes below where the diff put the first record.
Every offset below is now one the game itself uses.

| Offset | Type | Meaning | How established |
| --- | --- | --- | --- |
| +0x00 | u8 | visible / flags | spawner writes `2` |
| +0x04 | u8 | `0xff` on a fresh record | spawner |
| +0x06 | u16 | **object type id**; `0xffff` when the slot is free | read and written all over |
| +0x08 | u16 | interaction state | the use handler tests and sets it |
| +0x14,+0x18,+0x1c | s32 | world X, Y, Z | spawner copies the player position from `0x801b25f0` into +0x14..+0x20 |
| +0x24,+0x26,+0x28 | s16 | rotation | spawner zeroes all three |
| +0x2c,+0x2e,+0x30 | s16 | **scale**, `0x1000` = 1.0 | the equal triple we saw; `0x1fe0` on monsters is ×1.98 |
| +0x36 | s16 | velocity, for whatever moves | `0x8004b288` adds it to X and accelerates it by 20 |
| +0x38 | u8 | `0xff` on spawn; the use handler acts only on `0xff` | `0x8005dc70`, `0x8005e704` |
| +0x3a | u16 | **gold**, class `0x20` only | `0x8005dcc0`: `gold += this` |
| +0x3b | u8 | index of another object | `0x8005dd24`, scaled by `0x44` |
| +0x3e | u8 | `0` makes the handler skip the object | `0x8005e594`; level data leaves `0xff` |
| +0x3c | u16 | allocation sequence number | `find_free_slot` evicts the lowest when nothing is free |
| +0x40 | u16 | index of another object | `0x8005dd0c`, scaled by `0x44` |

**A slot is free when the `u16` at `+0x06` is `0x00ff`.** `find_free_slot`
(`0x80046034`) scans for that, and failing it evicts whichever record carries
the smallest `+0x3c`. Five routines allocate through it, among them
`spawn_object` and `spawn_gold`.

Everything from +0x38 up is a **union the class byte selects between**, so no
single name fits a field across all types. Trees keep round numbers 120–230 in
+0x38 where a chest keeps `0xff`; doors keep their own cell in +0x39/+0x3a
where a coin pile keeps its value.

### Three machines of the same shape, and what they add up to

The game dispatches on a byte three times, and all three are built the same
way — a routine that switches on one byte through a big table, most of whose
arms are the same target:

| | switches on | arms | shared | what the shared one is |
| --- | --- | --- | --- | --- |
| `object_interpreter` | `record[+4]` of 396 objects | 236 | 191 | **a call through `level_hooks`** |
| `actor_tick` | `actor[+0xe]` of 199 creatures | 241 | 209 | **a call through `level_hooks`** |
| `player_action` | its own argument | 77 | 35 | the routine's own epilogue |

Two of the three **hand an opcode they do not know to the level's own code**,
through `level_hooks + 0x24`, the same entry of the same structure. That is the
game's extension point: a level can give a creature or an object behaviour the
executable has never heard of. The player's machine has no such escape — the
opcodes it does not know do nothing.

And the three join up. `player_turn` reads the button edges and calls
`player_action`; its arms call **`effect_spawn`**, which takes a slot from the
128 at `effect_slots` and writes the kind byte; `effect_driver` ticks that slot
once a frame through **`effect_tick`**, whose own 130-arm switch is on the same
kind byte; and `render_walk`'s third loop draws it. So

```
a button  ->  player_action (77)  ->  effect_spawn  ->  a slot
          ->  effect_tick (130)   ->  render_walk    ->  the screen
```

is the whole of attacking and casting, and `cast_spell` and `spell_begin` are
the two halves of paying for the second — one checks `spell_table[n] + 0x16`
and the other subtracts it.

### The type row, and the 49 types that are places rather than things

Each of the 300 rows is 24 bytes and this much of it is read:

| | |
| --- | --- |
| +0 | the behaviour opcode, and the render class — **the same byte** |
| +1, +2 | `0x00` and `0xff` on all 300 |
| +3 | copied into the live record's `+3` by `load_object_placement` |
| +6 | `u16`, a size: 800, 900, 1000, 1200, 1350, 1400, 1500, 2000 — the shapes the player's own radius (800) and body height (1700) come in |
| +8 | `u16`, a second size |
| +0xa | copied into the live record's `+0x6a` |
| +0x17 | the byte `object_set_present` puts back into the cell when the object goes |

**49 of the 300 types have nothing at all after +3**, and every one of them
carries an opcode from the trigger range — `0x1f`, `0x5f`, `0xe0`–`0xea`,
`0xf0`, `0xf2`, or `0xff` which is "skip". Types **264 to 297 are almost all of
them**, in runs: 264–266 on `0xf0`, 267–279 on `0xf2`, then one type per opcode
from `0xe0` up. A type with no size, no second size and nothing to copy is not
a thing. **It is a place** — a volume that does something when the player walks
into it.

### Why 707 objects have no model, and it is mostly on purpose

The queue's fourth item was "the 53 objects with no model, `MO.T` type 287
among them". Across the whole game it is 707 of 4838 placed objects, and
`python3 tools/objops.py --types` accounts for 696 of them:

| | |
| --- | --- |
| 578 | a **marker** — the type row is empty past +3 |
| 76 | type 299, the volume that says an inscription can be read here |
| 42 | a class that means **never drawn**, `0xe5` or `0xe9` |
| 1 | past the end of the type table, type 300 or above |
| **10** | **still unexplained** — all of them type 298, opcode `0x15` |

Type 287, the one the queue named, is a marker: 136 placed across 13 levels,
`0xe6`, and an empty row. It has no model because it is not meant to have one.

### What the opcodes are, from a session that ran them

`emu/bp20.lua` recorded a player opening a door, taking things out of chests,
picking up herbs and getting killed. **13 of the 44 targets ran**, and every
one of them ran on exactly the opcode the table says, which is the instrument
checking out. What they ran on:

| opcode | types it ran on | what those are |
| --- | --- | --- |
| `0x01` | 177, 178 | the **doors** — section 5 had 175–178 as doors from the parameter block |
| `0x03` | 171 | |
| `0x06` | 152, 154 | |
| `0x07` | 159 | the **open chest**; `0xe5` is 158, the closed one, and it does nothing |
| `0x09` | 183, 186, 190, 192, 196, 212 | |
| `0x51` | 219 | |
| `0x54` | 224 | |
| `0x62` | 149 | a **spawned pickup**, in slot 350 — past the 350 placement records — following the floor; taking it was followed by `give_item` |
| `0xe0` `0xe1` `0xe3` `0xe6` | 280, 284, 282, 287 | markers, all four |

The items the session produced name themselves against `tools/itemtext.py`:
`give_item(104)` twice is *"this herb will heal the wounded body"*,
`give_item(109)` is *"the stone which contains the moon's magical power"*,
`give_item(141)` is *"the key for the pedestals built upon the defence walls"*
and `give_item(34)` is a helmet — which is what the player said they picked up,
in that order. **After every `give_item` the game asks `has_item(0)` and
`has_item(133)`**, the first sword and the key of Ichrius.

Two corrections the same log forced: `use_item`'s `a0` is a **pointer** —
`2149262832`, which is `0x801b25f0`, `player_pos` (both callers pass it; it
was once misconverted to `0x80195ff0`, inside `object_table`) — and not an
item id, and
`script_interpreter` is given an **actor** record, `0x80185da8` and
`0x80186d10` being slots 0 and 58 of `actor_table`.

### The object interpreter, and where its table does not come from

`object_interpreter` (`0x80047010`) is the third call in every frame. It walks
all 396 slots of `object_table`, publishes the record at `0x80198394` and its
type's 24-byte row at `0x80198390` so the handlers need no arguments, skips a
record whose `+4` is `0xff`, and switches on that byte through the 236-arm
table at `0x8001209c`. **Byte `+4` is the behaviour opcode**, and it is the
same class byte `render_walk` draws on — the two dispatches that looked like
separate ideas are one number.

236 opcodes, 44 arms, 191 opcodes sharing the tail. [OBJECTS.md](OBJECTS.md)
has every arm with what it calls and touches, generated by
`tools/objops.py`; the groups read as doors that shove the player, teleports,
the stairs between levels, things that come and go, and things that follow the
floor.

**`object_type_table` is `FDAT.T` entry 97 at offset 4.** The entry opens with
a length word of **7200 = 300 × 24** and the table follows it, and all **300 of
300 rows are byte for byte what a level-0 snapshot holds** — so it is loaded
whole, and it is the same on every level. Nothing about it is per-level, which
is what an earlier paragraph here assumed and why the port was borrowing the
class bytes from a snapshot. It no longer is.

**300 is where `model_of_type` changes its mind too.** Below that type the
model is `type + 0x100`; from 300 up the level is added — and from 300 up there
is no row in this table either. The two are the same boundary seen from either
side, and either on its own reads like a coincidence. **1424 of the game's
4838 placed objects are past it** and therefore have no class byte and no
behaviour opcode at all.

The census over every level, from the disc, is in [OBJECTS.md](OBJECTS.md). It
confirms the chest reading from the other direction: opcode `0xe5` is type 158
and `0x07` is types 159, 172 and 173, and `0x07`'s arm is one of the three that
calls `object_set_present` — which is what opening a chest *is*, since that
routine is the visible/not-visible switch.

### Object type table, `0x8018fb3c`

24 bytes per type, ending exactly where the object array begins, so it holds
`0x1f20 / 24` = **332 types** — one more than the highest id ever seen (326).
Byte +1 is the **class**, which is what the use handler dispatches on:

| Class | Count | What |
| --- | --- | --- |
| `0x00` | 189 | scenery, no pickup handler |
| `0x10`–`0x19` | 142 | interactables; `0x16` (28) covers chests, `0x17` (4) is consumables — ids 104, 105, 107, 127 |
| `0x20` | 1 | gold, and the only type in it is **149** |

This retires the old guess that the `u16` in the parameter block was a script
index. There is exactly one gold type, its record on level 0 carries `100` in
+0x3a, and the 100 gold coins that came out of it in play is that number. The
tombstone with `89` beside it was a coincidence: it is a different object, of a
class the pickup path never reaches.

**The type id indexes `MO.T`**: all 48 distinct ids in the sample have a model
there, while `ITEM.T` is missing 11 of them and `MOF.T` 4. `ITEM.T[id]`, when
present, is that type's description — which is why unique landmarks resolve
correctly and appear exactly once each (one *Statue of the Hero*, one *Royal
Emblem*, one *Rest in Peace*). Ids in the biography range resolve to names that
repeat implausibly often, so the two archives share numbering only in part.

### Byte +0 is the render class, and two values mean "never drawn"

Separate from the use class above. `render_walk` (`0x80040ae4`) dispatches on
the class byte the live record carries at `+0x04`, which is a copy of byte `+0`
of the type's record here — checked against fifteen types, all fifteen
matching. Two values jump straight to the loop tail:

| Class | Types on level 0 | What |
| --- | --- | --- |
| `0xe5` | 158 | a treasure chest **closed** |
| `0xe9` | 318 | — |

Type 158 and type 159 are the same chest closed and open. **19 cells across
the 28 levels hold both of them and not one cell holds either alone**, so they
are two states of one object and this byte is how the game shows one of them.
Drawing both, which `tools/level3d.py` did, is a chest open and closed at the
same time — reported by a player looking at the port.

What sets a live record's class is read now: `load_object_placement`'s
256-arm switch on the type's byte `+0`, which for most classes stores the
class itself as the opcode (below, "read whole"). The type table is off the
disc -- `FDAT.T` entry 97 and each level's own 32 rows -- so nothing here is
borrowed from a snapshot any more. What flips a chest from one state to the
other at run time is still the object interpreter's business.

### Type ids confirmed by experiment

Each was established by snapshotting either side of a deliberate action and
keeping the record nearest the player that changed.

| id | What it is | Evidence |
| --- | --- | --- |
| 104 | **Earth Herb** | inventory screen showed `EARTH HERB ×2`; slot 104 held 2 |
| 105 | **Antidote** | same screen showed `ANTIDOTE ×1`; slot 105 held 1 |
| 106 | **Chest** | opening it set `+0x38` from 0 to 255, 866 units from the player |
| 154 | revealed when the chest opens | changed alongside 106; the open chest shows an item inside |
| 175 | **Locked door with a keyhole** | reported from play; it is the object nearest the player at 3847 units on level 4, 8 instances |
| 177 | **Door** | opening it changed `+0x08`, `+0x0e`, `+0x0f`, `+0x27`, `+0x40`, 1354 units away |
| 257 | the keyhole that door 175 needs a green key for | reported from play; 7 instances against 8 doors, each sitting beside one — so the lock, not the key (*the key item itself is still unidentified*) |
| 192 | **Tombstone** | reported from play; may hold an item |
| 196 | **Chipped tombstone** | reported from play |
| 227 | **Save point** | reported from play |
| 283 | something animated | `+0x40`/`+0x41` tick on every instance in every pair of snapshots, so the *Varde* text at that index is a false match |
| 324 | **Tree** | reported from play; the *Two Headed Grave Pot* text at that index is another false match. No instance is class `0x20`, so a tree holds no gold. Its `+0x38` takes round values 120–230 in steps of 10, plausibly a height (*unverified*) |

Names confirmed this way are written with a trailing `!` in the tools; a name
merely taken from `ITEM.T` at the same index gets a `?`, because that archive
shares numbering with the object types only in part.

### `FDAT.T` entry `3n + 1` is a chain of six blocks

`level_load` walks it the way it walks entry 97: read a `u32` length, use the
bytes after it, step over both, read the next. Six blocks, at the same offsets
on every level:

| # | at | bytes | where it goes |
| --- | --- | --- | --- |
| 0 | 4 | 12992 | `entity_table`, 0xcb0 words — the 40 records and the blocks they point at |
| 1 | 13000 | 3200 | `actor_table_build` |
| 2 | 16204 | 768 | `0x8019175c` — **32 more rows of `object_type_table`** |
| 3 | 16976 | 8400 | `load_object_placement` |
| 4 | 25380 | 2048 | not read yet |
| 5 | 27432 | 640 | `0x801ba6fc` |

`0x8019175c` is `object_type_table + 7200`, which is 300 rows of 24 — so
block 2 is **types 300 to 331, and they belong to the level**.

**Withdrawn: "1424 placed objects have a type of 300 or above, which is where
the table stops, so they have no row and no opcode."** The table is 332 rows
in two pieces, and with the level's own 32 in place **every one of the 4838
placed objects in the game has a row**. Against a level-0 RAM snapshot the
whole table is **7968 of 7968 bytes**.

It also dissolves a coincidence this document recorded. `model_of_type` takes
an object's model as `type + 0x100` below 300 and adds the level from 300 up;
that was filed as "the same boundary seen from either side". It is one fact:
from 300 up the *row* is the level's own too, so the model has to be.

What found it was `emu/bp23.lua` logging the game colliding with types 301,
308, 314, 324, 325 and 326 — types that, by the old reading, did not exist.

### A door that swings: opcode 1

Class `0x01` -- 42 objects in the game, nine on level 0, types 177 and 178 there
-- is a door on a hinge. `load_object_placement` gives it opcode 1, keeps its yaw
twice (`+0x26`, and `+0x42` to come back to), sets `+0x40` to 999, and stamps its
closed state into the grid: `stamp_rect` copies `tr[+0xd]` x `tr[+0xe]` cells of
layer 1 from `(p[+0x13] + 1, p[+0x14])` to `(p[+0x11], p[+0x12])` -- the doorway's
collision shape becomes a wall. The door itself stops nothing as an object:
its type row has radius 0 and no rectangle bit.

**Opening.** USE runs `object_interact` (`0x8005e2d0`), which takes every
object `find_object` offers in front of the player -- for class 1 the player's
point moved `0x400` back along the door's own yaw, within the type's `+6` plus
`0x320` of the door, and the door within `0x200` of the facing. For a door whose
state `+8` is 0 it looks at the lock byte `+0x38`: `0xff` opens it (state 1), so
do `0xfd` and `0xfe` unless the type is `0xae`; `0xf0`, `0xf1`, `0xf2`, `0x96`,
`0x98` and `0x9a` are messages, and anything else is "locked". The loop does
not stop at the first door, which is how both leaves of a double door open.

**The swing** is `object_interpreter`'s arm for opcode 1 (`0x8004814c`), once a
frame:

```
state 1           state 2, counter 0, keep the facing
counter < 0x20    yaw += 0x20: a quarter turn in 32 frames. Under 0x15, if the
                  player stands in the swing, shove them 0x4c along it
  counter 0x18    stamp the open state -- the template at p[+0x13] + 0
  counter 0x1f    counter = 0x118: twenty frames of standing open
counter 0x12c     collide_query(the point 0x400 along the door, 0x5dc, 0xc0):
                  if player_in_range (0x80028e48) or a creature says the
                  doorway is taken, wait here; else stamp the template at
                  p[+0x13] + 2 and start back
counter < 0x14c   yaw -= 0x20
after             state 0, +1 = 0x80, +0xe = -0x32
```

**Checked against two snapshots, as end states.** `door1` and `door2` hold the
same door, slot 114 at (41,10), before and after the player pressed USE, from
the same spot. door1: state 0, counter `0x14d`, yaw 0, `+1` `0x80`, `+0xe` -50,
and shape 46 in both doorway cells -- one full cycle done. door2: state 2,
counter `0x121`, yaw `0x400`, `+1` `0x81`, `+0xe` 240, shape 64 in both -- open
and nine frames into the wait. The port, started from door1's player position
and facing, opens exactly that door, reaches shape 64 at counter `0x18` and
yaw `0x400` at `0x1f`, and -- once the player walks clear -- comes back to
state 0, counter `0x14d` and shape 46. Every field it keeps agrees with both
snapshots. **And a recording**: `emu/bp24.lua` stops at the arm's head each
frame, and caught two full cycles of that door -- the first waiting at `0x12c`
for 41 frames while the player stood in the doorway, the second walking clear.
`tools/doors.py`, the arm in Python, replays it locked: from each logged door
and the player position the arm saw (`object_interpreter` runs before
`player_controller`), one step, against the next line -- **226 of 226** steps
give the game's state, counter, yaw and the two doorway shapes, the wait
included. The two openings are `object_interact` on USE, not the arm. The
record's `+0xe` the log carries is the arm's other write: while the door is
drawn (+3 bit 0x80) it holds -0x30 or 0xf0 by which side of the door the player
is on, and `render_walk` hands it to `draw_model_plain`.

### A door that lifts: opcodes 3, 4 and 5

Reported from play as walls that open when pressed, and that is what they are.
Classes `0x03`, `0x04` and `0x05` -- five on level 0, type `0xab` in slots 20,
51, 74, 86 and 123, one of `0x133` on level 8 -- get their class as the opcode,
`+1` = 0 and a scale of 0, and `load_object_placement` stamps two tables into
the grid with `stamp_table` at `sel` 0. Each names two cells, the door's own
and the one behind it (`(0, 0)` and `(0, -1)` turned by the yaw), and writes
layer 1 (the upper layer, since `b0` is 2):

| op | shape table | shut | open | tile table | shut | open |
|----|-------------|------|------|------------|------|------|
| 3  | `0x800828dc` | `0x81` | `0xb2` | `0x800828fc` | `0x7d` | `0xfc` |
| 4  | `0x800828dc` | `0x81` | `0xb2` | `0x8008291c` | `0x7f` | `0xfc` |
| 5  | `0x8008293c` | `0xc1` | `0xdf` | `0x8008295c` | `0x1a` | `0xfc` |

Tile `0x7d` is half a cell of wall, `0x40a` thick and two cells high, and the
cells either side of a level-0 door carry the same tile and shape: shut, the
door is a stretch of the wall, drawn by the grid, and its model is not drawn
at all. Tile `0xfc` is one `draw_terrain` skips: it calls `draw_tile` only
for a tile under `0xf0` (`0x8003c1b8`).

**Opening.** `object_interact` takes it through `find_object`'s plain test for
any class past 2 (`0x80045f30`): `in_range(the door, the player 0x1f4 up, the
type's +6 plus 0x320, the type's +8 as the door's top, 0x9c4 as the point's)`,
then the door within `0x200` of the facing -- type `0xab` has `+6` = `0x5dc`
and `+8` = `0xe00`. Its arm for classes 3 to 5 opens a door whose state is 0
and whose lock byte `+0x38` is `0xff` (state 1); any other lock is "locked".

**The lift** is one arm written out three times (`0x800470c4`, `0x80047290`,
`0x80047444`), each with its pair of tables:

```
state 1         counter 0: sound, the tile table at sel 1 -- the wall tile
                goes -- and the scale 0x1000, so the model is drawn instead;
                counter += 0x48; at 0xc18 the shape table at sel 1 (passable);
                from 0x1000 on, counter 0xfff and state 2
state 2..0x13   state += 1: eighteen frames standing open
state 0x14      collide_query(x, y, z, 0x700, 0xc80, 0xc0) clear: the shape
                table at sel 0 (solid), state 0x15, sound; else wait
state 0x15      counter -= 0x48; at 0 or under: the tile table at sel 0, the
                counter, the state and the scale 0
```

57 frames up, the doorway passable from the 43rd; eighteen standing; 57 down,
solid from the first. `collide_query` with 0xc0 asks `actor_in_range`
(`0x8004d838`: the first awake creature, but for model `0x6e`, in range at its
radius + `0x700`) and `player_in_range` (`0x700 + 0x320`, the body `0x6a4` as
its top), and only where the door's cell has an occupancy count -- which it
has whenever either answer could be yes, since the player marks every cell
within `0x320 + 0x800` of itself and a creature within its radius + `0x800`.

**The model moves by animation.** `render_walk` draws the record through
`draw_model_plain` (its `+3` is 3: neither `0x40` nor `8`) and hands it the
record's `+1` as the animation and the counter `+0xa` as the clock -- the
stack arguments `0x1c` and `0x20` of the call at `0x800414a4`, which the
routine passes on to `0x800431e8` exactly as it does a creature's. Model 299
(MO.T, type `0xab + 0x80`) has one animation, a single segment of `0x1000`
blending towards pose 0, which names vertices 0 to 11 -- the slab -- `0xf80`
higher and skips the frame. So the counter is how far up the slab is.

**In the port** (`godot/doors.gd`): the cells each door's tile table rewrites
are left out of the level mesh and built as a node of their own, `tNNN`
(`tools/level3d.py lift_tiles`), shown while their tile is one `draw_terrain`
draws; the model is `lNNN` in the objects, with the vertices unturned so
`godot/anim.gd` can pose them, shown while the scale is not 0; and the shapes
go into the collision cells. `tools/doors.py lift_step` is the arm in Python;
`godot/selftest.gd` holds the port to it (273 of 273 frames, a door let drop
at once and one held open).

**Checked against a recording.** `emu/bp27.lua` stops at the head of the arm
for every lift door not at rest and logs its state, counter and scale, the
player, and the tile and shape of its two cells; `tools/doors.py` replays it
locked, one step from each line against the next. Fifteen lifts over three
recordings, of doors 51 and 123: **3528 of 3528** steps -- the 57 frames up
with both stamps, the eighteen standing, the waits and the drops; one more
step shut the door and USE opened it again in the same frame. The later
recordings also stopped after each arm's `collide_query` and logged the mask
it returned: in **1078 of 1078** of those answers bit `0x80` is set exactly
when `player_in_range` -- the player within `0x700 + 0x320` of the door, the
body `0x6a4` as its top -- puts the player in reach. (A log holds several
sessions, each counting vertical blanks from its own start: its lines are
matched within their session.)

The other bit is the creatures': **544 frames** the game held the doorway on
bit `0x10`, alone or with the player's. `collide_query` writes
`actor_in_range`'s answer to `0x801e648c` and then, on its way to the
objects, **writes -1 over it** (`0x800340a8`), so whoever asks after it never
learns who -- so bp27 lists the awake creatures within `0x2000` of the door
with each answer, and `tools/doors.py` asks `actor_in_range`'s question of
them: in **457 of 457** answers that list them it finds one exactly when the
game's bit is set. Who: **two creatures of kind 4 (model 60)**, the one of
slot 15 that lives a few cells behind door 51 (404 frames between them; 174
of them it) and the one of slot 7 behind door 123 (230). They hold the door
open while they stand in its doorway's reach -- `0x700` past their radius of
300, their 1812 of height against the door's `0xc80` -- the player anywhere.
The 35 frames of the first recording, which logged no answers, are counted
apart.

### A gate: opcode 2

Class `0x02` -- 128 objects in the game, ten of them level 4's walls of
types `0xaf` (model 303) and `0xb0` (304) -- gets opcode 2 and `+1` = 0;
`load_object_placement` stamps its doorway **shut** with `stamp_rect` from the
record's templates and marks the cells within `0x1130` as occupied. The
templates are three blocks of layer-1 cells side by side, `type[+0xd]` wide
and `type[+0xe]` deep, from `(p[+0x13], p[+0x14])` -- the tail's `+3` and
`+4`: the first **open**, the next **moving**, the third **shut**. The
doorway is `(p[+0x11], p[+0x12])`, turned by the yaw as a swinging door's.
Level 4's are 3 by 2 at x 0..8 and 9..17 of z 78..79. With the mask `0x2d`
the tile, the rotation, the shape and bit `0x40` of `+9` are copied; the
tiles are the same in all three, the shapes are not (26..28 open, 98..100
moving and shut) -- and bit `0x40`, **the fence**, is in the open template
alone: an open gate is a wall to the creatures (`collide_query`'s flag 2 in
their `0x93`), not to the player.

**The arm** (`0x800475f8`) is the lift's rise with `stamp_rect` for the
tables:

```
state 0         +3 |= 2; a lock (+0x38) that is odd and in 0x96..0xc6
                ((lock + 0x6a) & 0xff < 0x31) starts it: state 1
state 1         counter 0: +3 &= ~2, the "moving" template, sound;
                counter += 0x48; at 0xc18 the "open" template;
                from 0x1000 on, counter 0xfff and state 2
state 2..0x13   state += 1: eighteen frames standing open
state 0x14      the lock as in state 0: open for good. Else
                collide_query(x, y, z, 0x1130, 0xc80, 0xc0) clear: state
                0x15, the "moving" template, sound
state 0x15      counter -= 0x48; at 0 or under: counter and state 0, the
                "shut" template
```

`+3`'s bit 2, while it rests, makes `render_walk` ask `view_bits_around`
the cell (the type's `+0xc`) rather than `view_bits_at` it -- the shut gate is
drawn when the cells beside it are seen. The model moves as a lift door's:
`draw_model_plain` with `+1` (0) as the animation and the counter as its
clock -- model 303 lifts by `0xa00` from 0 to `0xfff`.

**Opening.** `find_object` takes class 2 through its plain test
(`0x80045f30`, as the lifts), and `object_interact`'s arm for classes 0 to 2
opens a gate whose state is 0 and whose lock is `0xff` -- or `0xfd` or `0xfe`,
unless the type is `0xae`. Level 4's locks: `0xff` on gates 96, 113 and 117,
which USE opens; `0xfc` on 51, 75, 91, 92, 115 and 120, which the pedestals
open (opcode `0x18`: each ORs its mask into its gate's lock once the key
stands on it, and one bit is enough for types `0xaf` and `0xb0`); `0xf0` on
74.

**In the port** (`godot/doors.gd` `gate_step`, `_gate_clear`, `_draw_gate`):
the model is `lNNN` in the objects, built by `tools/level3d.py build_lifts`
with the lifts, and the stamps go into the collision cells and the fence
(`_stamp`, the swinging doors' too). `tools/doors.py gate_step` is the arm in
Python, and `godot/selftest.gd` holds the port to it over three runs -- a gate
let drop at once, one held nine frames (lock `0xfe`), one that opened itself
(`0x97`) and stays: 360 of 360 frames.

**Checked against the game's own code.** `tools/mipsrun.py` runs the arm
itself over `silv1`'s RAM, a frame at a time, with `collide_query` answering
from a script (its arguments kept): gates 96, 113 (a quarter turn, type
`0xb0`) and 91 (a half) opened by USE and held 0, 6 and 3 frames, and gate 51
with its lock set to `0x97` -- **520 of 520** frames are `gate_step`'s, state,
counter and the doorway's shapes and fence as the game's `stamp_rect` left
them in its grid, and **12 of 12** doorway tests ask
`collide_query(the gate, 0x1130, 0xc80, 0xc0)` (`tools/doors.py
gate_game_check`). Left for a recording: who holds a doorway in play -- in
`silv1` a creature of model 53 within its radius plus `0x1130` of gate 96
would -- and the sound; a bp27 session on level 4 opening gate 96 (cell
(38,23)) would show both.

### A hidden wall: opcode 0x54

Class `0x54` -- seven in the game, one on level 0, slot 323 in cell (7,2) --
is a piece of wall that goes when the player comes near it from one side.
`load_object_placement` keeps the record's `+0` at `+0x40`, sets `+0` to 2,
zeroes the scale and lays its table down at `sel` 0 with `stamp_table`: the
table at `0x8008288c + 40 * (2 * type[+0xe] + (p[+0x16] & 1))`, three cells
(its own and one either side along the yaw), each entry's first half a wall
tile and a solid shape, its second the tile `0xfc` and a passable one. The
arm (`0x80048ecc`):

```
state 0       the player in player_in_rect(p[+0x11] - (p[+0x13] - 1) / 2,
              p[+0x12] - (p[+0x14] - 1) / 2, p[+0x13], p[+0x14],
              -(p[+0x15] << 7)) -- or the lock (+0x38) 0xff: the table at
              sel 1 with the flag 0x80, state 1, the scale 0x1000
state 1       the counter += 0x100; at 0x400: with p[+0x16] & 2 state 0x63
              and the lock 0xff, else state 2
2..0x1f       state += 1
state 0x20    the counter += 0x80; at 0xfff the counter, +1 and the state
              0, the table at sel 0 with the flag 0, the scale 0
state 0x63    nothing
```

The model is drawn while the scale is not 0, the counter its clock, as a lift
door's. Level 0's: the strip of cells x 5, z 0..2 at the height -8832, two
cells west of the wall; tiles 35 and 125 give way to `0xfc`, shapes 76 and 77
to 78 and 79, and with `p[+0x16]` `0xff` it stays open. The flag is the cell
byte's bit 7 (`+4`, `+9`), which the drawing reads, not the collision.

**Checked against the game's own code**: `tools/mipsrun.py` runs the arm over
`a1`'s RAM with the player put into the strip on the third frame -- and again
with `p[+0x16]`'s bit 2 cleared and the player gone on the fifth -- beside
`tools/doors.py wall_step` and the loader's `stamp_table`: **140 of 140**
frames, the state, counter, scale, `+1` and the three cells' tile, shape and
`+9`. **In the port** it is a lift door with one table (`godot/doors.gd`
`wall_step`): its cells are a node of their own, `t323`, its model `l323`.

### What else levels 0 and 4 place

* **Opcode `0x51`, level 0's four of type 219** (slots 209 to 212): a trap
  that swings its model and tests two of its vertices (the type's `+0xc` and
  `+0xd`, through `0x80046760`, the vertex at the animation's clock, scaled,
  turned and placed) against the player and the creatures, striking through
  `actor_attack_player` with the type's `+0x12..+0x15`. Level 0's never run:
  their `+0x3b` is `0xfe`, which state 0 takes for "nothing", and the loader
  has already taken them away (`object_set_present` 0, the scale 0) because
  it is not `0xff`; `sub_800463bc`, which toggles a trap's `+0x38` by the
  group at its `+0x3d`, finds none (`0xff`). They are drawn nowhere.
* **Opcode `0xe6`** (28 on level 0, 4 on level 4): while the player is in its
  rectangle, `+0x3d` is added to the `+0xe` of `+0x3c` objects from the slot at
  `+0x3a`, and taken off again when they leave. `+0xe` is what
  `draw_model_plain` adds to each triangle's mean depth before it files it in
  the ordering table (`model_prims_semi`, `0x80037f54`) -- a **depth bias**,
  127 for all of level 0's: the PS1's painter's order put right from where the
  player stands. Nothing for a port that draws with a depth buffer.
* **Opcode `0x1f`** (5 on level 0): handed to `level_hooks + 0x24`, which on
  levels 0 and 4 is `jr $ra`; what reads them is `render_walk`, which plays a
  sound for the rectangle the player is in, louder further in -- an
  **ambient sound**. The port has no sound.
* **Opcode `0xe1`** (3 on each): when the player steps into its rectangle,
  once (or every frame with `+0x3a`'s bit 7), by `+0x3a & 0xf`: the level's
  entry 3 with the record, `sub_800463bc(+0x3b)`, or a byte at
  `0x801baa2f + +0x3b` set to `+0x3c`. All six here call the entry. Level 4's
  moves gate 115's x to the trigger's less `0x400` or plus `0x3ff`, by which of
  the two the player crossed (`+0x3b` 0 and 1), and with `+0x3b` 10 swaps a
  strip of three cells at (55,12) between two templates by whether the player
  stands there having arrived by a warp (`0x801b25ee`, which the warp routine
  `0x8005c864` sets); level 0's does the same strip at (9,55), and its case 0
  also wakes three creatures and changes four objects once two story bytes
  (`0x801ba98e`, `0x801ba98f`) say so. Not in the port.

### Chests, and picking things up

A **small chest** is three objects in one cell: the body (type 155, class
`0xff`, a solid rectangle), a lid of class 6 (opcode 6, types 152, 154, 156)
`0x280` above it, and what is in it, a class-`0x40` object whose slot is the
lid's u16 at `+0x3a`. A **big chest** is one object of class 7 (type 159,
model 287) with a class-`0xe5` record for its body. Level 0 has eleven lids
and two big chests; its other class-`0x40` objects lie about in the open.

**Opening.** `object_interact` (`0x8005e2d0`) reaches a chest through
`find_object`'s plain test -- in range of the player's point `0x1f4` up at
the type's `+6` plus `0x320`, the type's `+8` as its top and `0x9c4` as the
point's, and within `0x200` of the facing -- and a lid only while it faces
the player within `0x155` (`facing_test(facing, yaw + 0x800, 0x155)`). Then
the lock byte `+0x38` (`.L28`): `0xff` becomes `0xfe`, the arm's signal; an
opened chest (`0xfe`) whose contents are gone says "Empty" (`announce(0x1a)`);
`0xf1` "Sealed" (5), `0xf0` "Spell is Cast" (`0x17`), and anything else
"Locked" (6) -- level 0's locks of 135, 137 and 138 are the royal, copper and
silver keys, which `use_item` tries on them (below).

**The lid** is `object_interpreter`'s arm for opcode 6 (`0x80048790`), on the
state `+8`, the lid's X angle `+0x24` and an angular velocity `+0x40`:

```
state 0   lock 0xfe already: angle 0xa00, state 3. Else what is inside is
          hidden -- object_mode(slot, 0) zeroes its +0 and +0x38, mode 3
          its +0xe -- and state 1. (load_object_placement's first frame.)
state 1   lock 0xfe: velocity -0x10, state 2, object_mode(slot, 1, the lid's
          +0) puts the contents back, a sound
state 2   velocity = spring_to(0xa00, angle, velocity, 8, 4); angle += it,
          & 0xfff; under 0xc00 object_mode(slot, 2) sets the contents' +0x38
          to 0xff -- now they can be taken; at rest on 0xa00, state 3.
          A trap byte +0x3c other than 0xff spawns effect 0x83/0x23 at the
          player every frame of it (0x80046dcc aims it)
```

The kick sends the angle the long way round, down through `0xfec`, and the
spring carries it on to `0xa00` -- `0x600` short of a turn -- in 82 frames,
the contents free from the 19th. **Checked against the snapshots:** seven
opened lids on level 0 lie on that path -- six at rest on `0xa00` with no
velocity, and one, slot 130 in `chest2`, caught moving at angle `0x9d4` with
velocity 4, which is frame 69 of it, its contents present and free as the
path says by then (`tools/chests.py`, 7 of 7).

**The big chest** -- opcode 7 (`0x80048960`): state 0 adds `0xc8` to its
contents' `+0xe` and hides them as the lid does; state 1 waits for the lock
to read `0xfe`, then puts them back; state 2 counts `+0xa` up by `0x80` a
frame and at `0xfff` frees them, state 3. `+1` is 0, so `render_walk` draws
its model animated, the counter the clock: model 287's one animation, six
segments run backwards, opens the lid. No snapshot holds one opened.

**Taking a thing** -- `object_interact`'s `.L13` calls `object_give`
(`0x8005db30`) for a class-`0x40` object, and stops the walk once one has been
taken (its type `0xff`). `object_give` does nothing unless `+0x38` is `0xff`;
gold -- the type row's `+1` is `0x20` -- is counted on the spot: the amount
`+0x3a` into `player_gold`, `announce(0x19, amount)`, the type `0xff`.
Anything else runs frames of its own (`render_frame` and `PadRead` in a loop:
the creatures, the doors and the player stand still):

```
the view's pitch s7 levels to s3 -- 0 below 0x800, 0xfff above -- while the
thing flies in nine frames, t = 0, 0x200 .. 0x1000 (object_lerp: fixed_madd
on the place, angle_lerp on the angles), from where it lies to
object_give_point: (0, 0x1f4 + row[+0xc], 0x5dc + row[+0xe]) turned by
(-s3, facing, 0) about the eye, and row[+0xc] lower again; turning to
(0, facing + 0x800, 0)
then +0x26 += 0x40 a frame until a button goes down -- the pad all up first,
then any; one during the flight cuts it short
USE: give_item. Arrows (0x93) gain 4 + (6 * rand() >> 15) more and light
arrows (0x94) 4, to 99; it flies in nine frames to (-0x1f4, 0x1f4, 0) about
the eye, the pitch going back to s7, and its type is 0xff
anything else, or give_item full ("Can't Carry Any More"): it turns 0x100 a
frame until it faces the player within 0x80, and flies back in nine frames
to where it lay and how it was turned
then clear_movement_state, and object_interact goes on with the next object
```

The row's `+0xe` -- the record's `+0xe` approaches `row[+0x10]` during the
flight, and the big chest adds `0xc8` to it -- reaches `draw_model_plain` as
its argument `0x30`; it is not read further, and the port leaves it.

**Keys.** A lock is a number, and the key that opens it is the item of that
number. Seven keys share one arm of `use_item` (`0x8005d188`): royal (135),
copper (137), silver (138), magician's (139), jail (140), dwarves' (142) and
Lyn's (144). It asks `find_object` for each object in front of `player_pos`
itself -- not the point `0x1f4` up that USE asks from: `0x320` past the type's
reach, `0x6a4` as the point's height, within `0x200` of the facing, the
doors' points moved as for USE -- and tries the key on it (`key_test`,
`0x80046608`), by the object's opcode:

```
0x0f, 0x11, 0xa7                  4, whatever the key
0..5 and 0x1b, while +8 is not 0  0 -- a door on the move is not asked
0..5, 0x1b; 6, 7, 8, 0x17, 0x18, 0x1a: the lock +0x38 --
    0xfe or 0xff                  2, open already
    the key's own number          1, and the lock 0xff
    anything else                 3
anything else                     0
```

1 is a sound (`0x8005bd34`: `0x8001576c(0x10, 0x64)`) and the end; 3 or 4
"Wrong key!" (`announce(7)`) and the end; 0 or 2 the next object; none left,
"Nothing Happens". The key is kept, and nothing opens: the lock is `0xff`, so
the next USE opens it as it would any other. Two keys have arms of their own.
Orladin's key (136, `0x8005d300`) goes through every object in front: a
type-`0xa2` lock (opcode `0x17`) reading 136 becomes `0xfe` at once -- opened
-- and a key is spent on each; a type-`0x102` pedestal (opcode `0x1a`) whose
lock is `0xff` takes the key -- its lock 136, its state 0 -- and a new object
of type 136 in the gold ring (`find_free_slot(350, 10)`) shows it lying
there, the pedestal's `+0x39` its place in the ring; anything else gets the
test above, and "Wrong key!" on a 3 without ending the walk. Silviera's key
(141, `0x8005d244`) asks for the first object only: a type-`0x101` pedestal
with its lock `0xff` takes it -- the lock the key's number, the state 0, the
key out of the pack -- and **`pedestal_put_key`** (`0x8005c7e8`) stands it
there: `find_free_slot(380, 16)` gives a slot of the ring 380..395, whose
type becomes the key's, and the pedestal's `+0x39` its place in the ring;
anything else, the test. **Checked**: the snapshots `silv1` and `silv2`, either
side of the key used at level 4's pedestal in cell (33,23) (slot 108), hold
7 of 7 of it -- the lock `0xff` to 141, the key gone from the pack, slot 380
free and then of type 141 at the pedestal's x and z, standing on it, its
`+0x40` the pedestal's slot and the pedestal's `+0x39` 0 (`tools/chests.py`).
By then the pedestal's own opcode (`0x18`) has its state at 99 and the key's
(`0x70`) its lock at `0xff`.

**The pedestal's arm** (`0x8004aeb8`) does the rest, once a frame. A pedestal
not at state 0 whose key -- the object in slot 380 + its `+0x39` -- has the
type `0xff`, taken, goes back to state 0 with its lock `0xff`, and the object
its `+0x3b` names loses the pedestal's mask (`+0x3d`, or `+0x3a` when that is
`0xff`). Then **`object_use_state`** (`0x80046914`), with the two vectors at
`0x8009c318` and `0x8009c320`, 0 and 20:

```
state 0, lock not 0xff   init_object_record on the key, then its opcode 0x70,
                         its +0 the pedestal's, +1 0x80, +0x40 the pedestal's
                         slot, its yaw the pedestal's; the count (+0x40) 19 if
                         the key's +0x38 is not 0, else 0; state 1 -- and on
state 1                  the count + 1; the key at the pedestal plus
                         fixed_madd((0, -0x600, 0x190), (0, -0x500, 0),
                         count * 0x1000 / 20), both turned by the pedestal's
                         angles; at 20 a sound (0x12), the key's +0x38 0xff,
                         state 0x63, and 1
```

-- and on that 1 the arm ORs the pedestal's mask (`+0x3a`) into the lock of
the object `+0x3b` names: a gate (opcode 2, "A gate"), which USE then opens.
So the key comes down from 0x600 above and 0x190 in front of the pedestal to
0x500 above it in twenty frames, and the gate is open to USE from the last.
**Checked**: replayed from `silv1`'s pedestal and gate, the model ends where
`silv2` has them -- the pedestal at 0x63 with its count at 20, the key at the
pedestal's x and z and 0x500 above, its angles the pedestal's and its scale
0x1000, its `+0`, `+1` and opcode, its `+0x38` 0xff, and gate 91's lock from
`0xfc` to `0xfe` -- **13 of 13** of the claims together
(`tools/chests.py check_pedestal`). And the frames between: `tools/mipsrun.py`
runs the game's own `pedestal_put_key` and then the arm, with
`object_use_state`, `vec_rotate` and its GTE matrix, over `silv1` for
pedestals 108, 192 and 110 (a half, no and a quarter turn), each to rest and
then with the key taken -- **72 of 72** frames are `pedestal_step`'s: the
pedestal's state, lock and count, the key's place, opcode, `+0x38`, `+0x40`
and angles, and the gate's lock (`tools/chests.py pedestal_game_check`). The key's own opcode, `0x70`, is one the
executable hands to `level_hooks + 0x24` -- level 4's is `jr $ra`, so the key
just stands there.

Being of class `0x40`, the key can be **taken back**: `object_give`'s `.L3`
sees a key of type `0x86`, `0x8d` or `0x88` with opcode `0x70`, finds its
pedestal at its `+0x40` and the object the pedestal serves, and refuses while
that is a gate (opcode 2) not at state 0; otherwise it flies to the eye as
anything else, and the pedestal's arm, finding the type `0xff`, takes the
mask out of the gate's lock again. Level 4 has seven pedestals: 63 → gate 51
(mask 3), 86 → 75 (2), 108 → 91 (2), 192 → 91 (1), 110 → 92 (3), 116 → 115
(3), 119 → 120 (3); gate 91 has two, and either opens it. Level 23's two
pairs serve gates of type `0xae`, which want both.

Silviera's key asks `find_object` for **the first object** in front, whatever
it is -- a gate within reach and lower in the table than the pedestal gets
"Wrong key!" -- so the port exports every object's place, class, reach
and top (`lootNN.json`'s `find`) and asks the same question of them
(`godot/loot.gd find_object`). A plain fit on anything but a pedestal is no
answer here: the shared arm's sound and flag are not in this one, and the menu
says "Nothing Happens".

`python3 tools/chests.py --keys` lists every lock on the disc a key is asked
about: 169 of them on 23 levels. Level 0 has seven -- slot 9 the copper key,
202 the silver, 204 (the big chest) the royal; 33, 116 and the door 70 read
200 and 344 reads 241, which no key is, so every key there is "Wrong key!".
Eleven of level 12's and 22's twelve class-0 doors take the jail key, level
3's three opcode-2 doors the dwarves', and level 14's, 16's and 17's
type-`0xa2` locks Orladin's.

### What a dying creature leaves

A creature dying is its kind's opcode-3 behaviour; in its first part, the
frame its animation clock crosses `0x800` (`actor_clock_passed`, `0x800506c0`):

```
gold    the kind's +0x30 + random_spread(it) -- ((rand() + rand() - 0x8000) * n)
        >> 15, two rolls whatever the gold -- and, if that is not 0, spawn_gold:
        a coin, type 0x95, 600 from the creature along rand() >> 3, half its
        height up, turned by rand() >> 3, the amount at +0x3a
a thing categories 0 and 4: the dying behaviour's +0xc, when not 0xff and
        rand() >> 7 is under its +0xd; category 1: what the creature was placed
        with, its +0xb (the placement's byte 6). spawn_thing (0x800460bc): at the
        creature's place, half its height up, turned by rand() >> 3
```

Each goes to a ring of ten object slots -- the gold to 350, a dying
behaviour's thing to 360, a carried thing to 370 -- through `find_free_slot`
(`0x80046034`): the first slot whose type is `0xff`, else the oldest by a count
the ring keeps (`0x8019839a`, `c`, `e`) and writes to `+0x3c`. Its `+0x38` is
`0xff` at once, so it can be taken while it falls, and it falls by an opcode:

```
0x60  (things whose row +1 is 0x10, 0x13, 0x16) y += v, v += 0x14; on the
      floor v = 0x10 turns the X angle, += 0x10 a frame, to 0x400: it tips over
0x61  (0x17) y += 0x14 and the yaw += 0x100 a frame, to the floor
0x62  (the gold; 0x11 0x12 0x14 0x15 0x18 0x19 0x20) y += v, the X angle
      +-0xa0, v += 0x1e; on the floor under 0x50 it lies, else it bounces with
      -(v >> 1) and turns the other way; lying, the X angle goes to its +0x2a --
      0 for types 0x5c, 0x86, 0x88, 0x8d, 0x8f and the gold, else 0x400 -- by
      0xa0 a frame (angle_approach), then state 0x63
```

the gold starting at `v = -0x78`, a thing at 0, and the floor `collide_surface`
under it. On level 0 no dying behaviour names a thing; seven category-1
creatures carry one: earth herbs, leather gloves, a blood stone, the dragon
crystal and creature 27's Silviera's key (141, `0x8d`).

**Against the snapshots.** Three things lie at rest in the rings of level 0's
snapshots: gold of 8 in slot 350 (`chest1`, `chest2`), gold of 14 in slot 350
(`door1`, `door2`) and the key `0x8d` in slot 370 -- the ring a carried thing
goes to, and creature 27's. Their resting velocities, 75, 75 and 68, are the
last of the fall the model gives from half a creature's height -- 1625, kinds 0
and 1, whose gold is 15 -- the gold from `-0x78` and the key from 0, both with
an X angle of 0 (`tools/chests.py`, 3 of 3). It is a consistency, not a proof:
several heights end the same way, and the snapshot does not say which creature
it was. In the port, killing creature 27 leaves 18 gold in slot 350 and the key
in 370, at rest with 75 and 68 on its floor.

### The menus, as they are drawn

Every menu screen is built out of a few routines that file sprites and
POLY_FT4s into the ordering table, against static descriptors at `0x8007e564`
onwards -- 12 bytes each: texture page, CLUT, u, v, width, height. GAME.EXE's
`$gp`, which its header leaves 0, is **`0x8009c214`**: the menu snapshots hold
the colours their frames carry at gp + 0x58 (0x78, the boxes), + 0x5c..0x64
(0x80, the text) and + 0x68 (0x30, the shadow).

```
ui_draw_label    a DR_TPAGE at depth 4; each glyph g twice, at (x - 1, y - 1)
                 in the text colour at depth 2 and at (x, y) in the shadow's
                 at depth 3; 7 apart, 7 x 15 cells of page 29, u = (g & 15) * 8,
                 v = (g >> 4) * 15. The glyphs are the game's alphabet, a..z 0..25
ui_draw_number   the same from a column at u 238: codes under 11 at v = 15 * c,
                 the rest at u 245 (0x13 is the 'x' of "x 2")
ui_label_plate   a quad of the record's size at (x - 6, y - 6), depth 50
ui_frame         pieces 9..17 of 0x8007e588: 33-square corners, edges in 28s
                 and what is left; top row, bottom row, middle rows 28 high --
                 a frame lower than 66 draws one middle row at a negative
                 height, flipped, over the top row's foot. Depth 50
ui_panel         a list: the title and its plate, the rows from (x + 13,
                 y + 8 + 16 * row), the mode's columns (1: "x N" at x + 0xe9),
                 the frame of 0x10a by rows * 16 + 12, the selected row's bar
                 (piece 8, depth 49) pulsing with gp + 0x4c, and the legend --
                 ui_button (16-square, page 28) and ui_small_text (8 x 8 ASCII)
```

Order is the ordering table's: the deeper drawn first, and within a depth the
one filed last first. **`tools/ui.py` draws the "use item" screen this way and
reproduces its 116 2D primitives in both buffers of `inv1` and `inv2` exactly**
-- read back by `tools/gpuframe.py`.

**Using a thing.** The menu (`pause_menu`, on the menu button while no swing
is under way) offers use item, use magic, equipment, status/records, storage
and system. "Use item" (`0x8001aa84`) lists the things 95..149 in inventory_a
(`item_list`); choosing one of 104..120 eats it (`item_consume`, `0x8001b254`):

| thing | |
|---|---|
| earth herb | HP + 50 |
| antidote | the poison gone, HP + 15 |
| herbal liquid | HP to the full |
| dragon crystal | HP and MP to the full |
| blood stone | clears 0x801b2568, holds turn_slow_timer to 0x40 |
| moon stone | MP + 40 |
| blue potion | HP + 100, a crystal flask back |
| gold potion | HP + 200, MP + 100, a crystal flask back |

and then `use_item` runs for it, whose last step is the level's own entry 2
and, when nothing has answered, "Nothing Happens".

The choice itself goes through `ui_prompt` (`0x80024c70`) of kind 0: two
answers, "use" at (45, 58) and "cancel" at (45, 84), each on a 54-wide plate
(piece 1), the chosen one lit with the pulse and the other dimmed
(`sub_80026158`: the text colour 0x57) -- over the list, drawn again with the
two-button legend (mode 1 | 0x8000). The pulse is `frame_begin`'s: gp + 0x4c
goes round 0..0x5f one a frame, and back to 0x30 when the choice moves. The
main page is `sub_800252f4`: the six lines of page 0 on 118-wide plates, the
chosen one lit, the two-button legend.

Behind it, every frame, **`ui_status_page`** (`0x800227ec`): two records on
the stack, a label's (x, y, glyphs) and a number's, moved down and written
over in place as it goes. At x `0xa3` from y `0x24`, 17 lines apart:
"EXPERIENCE" and `player_exp` in seven digits at `+0x4d`; "LEVEL" and the
level; "HP" (glyphs 7, 15 written over the record) and HP, a stroke (number
code `0x14`) and the maximum at `+0x3f`, `+0x5b`, `+0x62`; "MP" the same;
"PWR·WIS" (the immediates `0f 16 11 3b 16 08 12`), the effective stat in five
digits at `+0x46` and `0x801b2530 + 1` -- which only the wise fruit raises,
to 4 -- in four at `+0x62`, with a dot (`0x3b`) at `+0x69`; "MAG", and from x
`0xc6` the five working skills in six digits, 15 lines apart in pairs `0x31`
across, each over a 14-square icon of page `0x1d` at v `0xc0` (`ui_prim_*`,
depth `0x1e`): u 0, `0x10`, `0x20`, `0x30`, `0x40` under the CLUTs `0x7d04`
to `0x7e04`, for skills 4, 0, 1, 3, 2. Drawn, the icons are a sun, a flame, a
rock, a whirlwind and a drop -- so skill 4, the one a new character has, is
light, and 0 fire, 1 earth, 2 water, 3 wind. Then "CONDITION" and, at
`+0x38`, the first of paralyse (`0x801b2568`), curse (`0x801b255e`), slow
(`turn_slow_timer`), poison (`poison_frames`), dark (`0x801b2562`) that is
set, or "NORMAL"; "GOLD" and the gold; and `ui_frame(0x9b, 0x1a, 0x8d, 0xb4)`
round it all. `tools/ui.py status_page` draws it, and the snapshot `menu1`
holds it to the game: both buffers, **428 of 428 primitives** each, are the
main page the model draws out of the snapshot's own figures, line 0 lit.

**In the port** (`godot/menu.gd`) the menu button opens the main page, the
status page behind it; "use item", its list, the prompt and eating are there,
drawn by a transcription of the same routines -- 17 of 17 screens give
`tools/ui.py`'s primitive lists, and the use-item ones give the game's own
frames. "Equipment" is there too (below); "use magic", "status/records",
"storage" and "system", the chosen thing's model turning in "use item"
(`0x80025be8`) and `use_item`'s arms for Orladin's and Silviera's keys, the
flask, the truth glass and Ichrius' things are not yet. The seven keys
of the shared arm are (`godot/loot.gd`, `try_key`, "Keys" above); anything
else that is not eaten says "Nothing Happens".

### Status/records, and running the game's own code

The main page's fourth line, **status/records** (`menu_records`,
`0x8001d784`), is page 1 of the label table -- OFFENSE/DEFENSE and
CONVERSATION under the title STATUS/RECORDS, chosen as the main page is
(`sub_800221e8`). The first is **`ui_ratings_page`** (`0x80023300`), held up
by `menu_ratings` (`0x8001d8a4`) until any button: OFFENSE at (30, 34) and
its eight halves 16 apart from y 50, DEFENSE at (164, 34) and its nine 17
apart from y 51, each label two spaces in and its number in six digits `0x4d`
to the right; `ui_frame(20, 26, 276, 180)` and "return" under it. The
second, CONVERSATION, is `text_pager` (`0x8001d944`), not read yet.

No snapshot shows that page, and none had to. **`tools/mipsrun.py`** is enough
of an R3000 to run GAME.EXE's own code over a snapshot's RAM -- the integer
instructions, the delay slots, the RAM and the scratchpad, the hardware
registers read as 0, ClearOTagR (the console's DMA) and the sound stood in
for. A menu's frame is plain code, so `frame_begin` and a screen's routine
run that way leave in the RAM the packets the game would have sent, and
`tools/gpuframe.py` reads them back. It is checked the way everything here
is: `ui_status_page` and the main page, run over `menu1`'s RAM, draw both of
its buffers' 428 primitives exactly, each at its own pulse. The port's
ratings page and status/records' page are held to what the routine itself
draws (4 sets of ratings, both lines chosen), not to a transcription of it.

### The equipment screen

The main page's third line is **`menu_equipment`** (`0x8001c7a8`). It
builds a list with `ui_menu_label` and then takes its title away (`+0` = 0)
and makes it ten rows from x `0x1b`, y `0x23`, drawn by `ui_panel` in **mode
3**: each row's heading -- ten 24-byte glyph rows at `0x8007f230`, WEAPON,
MAGIC, SHIELD, HEAD, BODY, ARMS, FEET, ITEM 1, ITEM 2 and "[square] BUTTON"
-- and `0x54` to the right of it the name **`equip_names`** (`0x8001c9c0`)
gives: the weapon (`0x801b25af`), magic A (`0x801b25ab`), then
`0x801b25d6`, `d4`, `d5`, `d7`, `d8`, `d9`, `da`, and the button's spell
(`0x801b25ac`) or, with none, its thing (`0x801b25ad`). A spell's name comes
from `0x80080430` (31 rows of 24), a thing's from `0x8007f620`, `0xff` is
nothing. The two-button legend; `ui_menu_chrome` moves the choice.

A line chosen opens **`ui_equip_page`** (`0x8001cbb8`) -- or, for MAGIC and
BUTTON, `0x8001d0c4` and `0x8001d3a0` (below). It lists, with
`item_list`, what `inventory_a` holds of the line's range:

| line | range | then |
| --- | --- | --- |
| weapon | 0..`0x21` | `equip_weapon(id)` |
| shield | `0x33`..`0x3e` | `equip_armour(id, 4)` -- `0x801b25d6` |
| head | `0x22`..`0x29` | slot 0, `0x801b25d4` |
| body | `0x2a`..`0x32` | slot 1, `0x801b25d5` |
| arms | `0x3f`..`0x47` | slot 2, `0x801b25d7` |
| feet | `0x48`..`0x50` | slot 3, `0x801b25d8` |
| items 1, 2 | `0x51`..`0x5e` | slots 5, 6, `0x801b25d9`, `da` |

and a last row "TAKE OFF" (`0x8007f338`) whose id is `0xff`. For an item line
the other item line's thing is counted one less while the list is up, so a
single ring cannot be worn twice: **what is worn is still counted in
`inventory_a`** -- a new character's excellector and leather plate are there, put
in by `reset_story_flags` (`0x8005eacc`: both arrays cleared, then the
excellector (weapon 0), the plate, two earth herbs and an antidote, which every snapshot of
a new character holds). The list is `ui_menu_label`'s -- title EQUIPMENT,
three rows from y `0x93` -- in mode 5, counts "x N" and three buttons, its
selection put on what is worn now (`list_place`). The choice goes through
`ui_prompt(s, 5, 5, id)`: kind 5's words are kind 0's, USE and CANCEL; USE
hands the id to the line's routine and goes back to the ten lines, anything
else back to the list. The thing chosen turns as a model beside the list
(`0x80025be8`), and triangle shows its page (`0x80024f88`).

**`equip_weapon`** (`0x8002bdc0`) puts the id in `0x801b25af`, empties the
weapon meter and the swing strength, sets the swing's pause to `0xa` and its
clock to -1, and, unless the id is `0xff`, points `held_item_record` at the
weapon's record and installs FDAT.T entry `0x62 + id` as `model_table[0x20]`
-- the hand and weapon `draw_held_item` draws (four entries, 18, 19, 25 and
26, hold no model). With no weapon `sub_8002c040` starts no swing and
`held_item_tick` does nothing. **`equip_armour`** (`0x8002bb84`) writes its
slot -- 0..6 are `0x801b25d4`, `d5`, `d7`, `d8`, `d6`, `d9`, `da` -- and
both end in `player_recalc_stats`.

**MAGIC** (`0x8001d0c4`) lists, with `sub_8001c6c0`, the spells **0 to
`0x16`** whose record's `+0` is 1 -- the attacking ones only -- each name off
`spell_names` and its MP (`+0x16`) beside it, then "TAKE OFF"; the list four
rows from y `0x83` (`ui_menu_label`'s kind 2 with `+0x1d` 0x83, `+0x1f` 4),
drawn by `ui_panel` mode 4, the selection on magic A, `ui_prompt(s, 5, 4)`,
and `set_spell_a` with the choice. **BUTTON** (`0x8001d3a0`) lists the
things `0x65..0x92` carried (`0x85` left out by zeroing its count while the
list is made) with their counts, then **every** spell unlocked (`0..0x1e`)
with its MP, then "TAKE OFF", in mode `0x10`; the choice goes to
`set_spell_b` and `set_button_item`, each of which clears the other. So the
healing and protecting spells, light among them, are cast from the button
(`bind_map`) and never from magic A.

`ui_panel`'s columns for the two modes: mode 4 a three-digit number from the
`u32` array at `+0x30` behind the MP sign (`number_digits` mode 3) at x +
0xdb, unless it is -1; mode `0x10` the count (`+0x2c`, "x N", two digits) at
x + 0xe9 unless 0xff, then the cost 0xce further on unless -1 -- the place
carried from one to the next. **Against the game's own `ui_panel`**, run by
`tools/mipsrun.py` over menu1's RAM with random lists laid in: **80 of 80
frames** primitive for primitive (`tools/ui.py panel_check`).

`ui_menu_chrome`'s up and down (`0x800223a4`), which every list uses: the
selection moves one and the bar with it, the rows shown moving only when the
bar is at their edge; past either end it goes round, to the last (the rows
showing the end) or to the first. An empty list closes at any button. The
port's "use item" list had placed the selection afresh on each move, which
scrolls differently; it moves as the game does now.

**Against the game**: the snapshots `equip1` and `equip4` (the ten lines,
the weapon and the plate on and then both taken off), `equip2` (the WEAPON
list) and `equip3` (its prompt) are, buffer for buffer, frames the model
draws out of their own state -- the slots, the inventory and the list
records `ui_menu_label` left on the stack (`0x801ffc48` for the ten lines,
`0x801ff7a0` for the list): 8 of 8, and `inv3`, a "use item" list scrolled
to its end, 2 of 2 (`tools/ui.py check_menus`). The turning model is filed
deeper than any 2D part (from depth 0x100 on), so it is left out.

**In the port** (`godot/menu.gd`): the ten lines, the lists, the prompt and
the equipping, as `tools/ui.py` draws them (8 of the 25 screens the
self-test holds); `godot/player.gd equip_weapon`, `equip_armour`, and every
weapon's model in hand (`tools/level3d.py build_held_gltf`). Not there: the
MAGIC and BUTTON lines, the turning model, the guide, and a bow's own path
through `held_item_tick` (weapons `0x1b`, `0x1c`).

### The banners

`announce` (`0x80041eec`) queues a code under `0xf0` in a ring of eight
(`0x801aeaed`, written at `0x801aeaf6`; a full place drops the code), with the
amount beside it for `0x19`. `message_tick` (`0x80041f9c`), which
`render_frame` calls every frame, object_give's included, shows one at a
time: state 1 brightens `0x801aeaf9` by `0x14` to `0x64` (five frames), state
2 holds fifteen, state 3 fades in five, then clears the code -- and the next
ones while they are the same, except the gold -- and starts again.

The words are pictures: a 4-bit page at VRAM (640, 256) under the CLUT at
(64, 480), 127 x 14 each, eighteen to a column, so code `c` is at
`u = 128 * (c / 18)`, `v = 14 * (c % 18)`. Read off the page:

| code | | code | |
|---|---|---|---|
| 0 | Level Up | 18 | Fire Magic Up |
| 1 | Strength Up | 19 | Earth Magic Up |
| 2 | Intelligence Up | 20 | Water Magic Up |
| 3 | Magic Learned | 21 | Wind Magic Up |
| 4 | Excellector Up | 22 | Light Magic Up |
| 5 | Sealed | 23 | Spell is Cast |
| 6 | Locked | 24 | Spell is Broken |
| 7 | Wrong key! | 25 | Gold |
| 8 | Tombstone | 26 | Empty |
| 9 | Need More MP | 27 | Worn Off |
| 10 | Nothing Happens | 28 | Broken Sword |
| 11 | Can't Carry Any More | 29 | Broken Shovel |
| 12 | Drew Some Water | 30 | Dead |
| 13 | Magic Power Up | 31 | Dead Body |
| 14 | Broken | 32 | Soldier's Body |
| 15 | Doesn't Open | 33 | Skeleton |
| 16 | No Qualifications | 34 | Skeleton |
| 17 | the digits 0-9, 8 wide at v 238 | 35 | Can't Used Here |

Each matches its caller: `give_item` full announces 11, a chest's lock 5, 6
and `0x17`, an empty chest 26, the broken shovel and sword (types `0xf8`,
`0xf9`) 29 and 28. The gold puts "Gold" in sprite 1 at (160, 203) and the
amount -- `number_digits(amount, 4, 0, 0)`, right-aligned, blanks 10 -- in
sprites 2 to 5. `message_draw` (`0x80041d9c`) draws the six records at
`0x80081928` that are on, each twice, additive and subtractive, coloured by
the brightness; every texel of the page has STP set, so both blend, and
what is left is the brighter of the scene and the word.

In the port: `godot/loot.gd` (the arms, the locks, object_give's frames and
`KFGame.modal` to stop the world while they run) and `godot/messages.gd`; the
chests and the things are nodes of their own, `kNNN` in the objects
(`tools/level3d.py build_loot`). `godot/selftest.gd` holds both to
`tools/chests.py`, 188 of 188 frames.

### What makes an object solid — found

`collide_query` takes a mask, and bit `0x20` of it means "test the objects".
That branch calls **`object_collide` (`0x80045ac8`)** and leaves its answer —
a slot index, or `-1` — in **`collide_object` (`0x801e6490`)**, beside the
actor answer at `0x801e648c`.

`object_collide` walks all 396 slots and skips three kinds: a type id of
`0xff`, a byte `+0` of zero, and whichever slot is `current_object`. What is
left it tests **two ways**:

| | |
| --- | --- |
| a **circle** | radius = the `u16` at `object_type_table[type] + 4`, through `in_range`. When the row's byte `+3` has bit `0x10` the radius is scaled by the object's own byte `+0x38` over 128 — the same byte `level_state_write` saves |
| an **oriented rectangle** | only when that radius is zero *and* the object's own byte `+3` has bit `4`: half-extents from the row's `+0xe` and `+0x10`, through `in_oriented_rect` (`0x80016d3c`), which turns the offset into the object's frame with `game_cos` and `game_sin` off the angle at `object+0x24` |

So an object's collision is **in its type's row, not in its placement
record** — which is why looking for it in the record found nothing. The
record carries the scale byte that stretches it and the angle that turns it,
and nothing else about it.

On level 0, of the objects live in a RAM snapshot, **24 have a non-zero
radius**, and the values are 128, 150, 200, 400, 450, 500, 600, 750 and
1792 — the same units as the player's own 800.

`player_horizontal` is the other half: it reads `collide_object`, checks the
object's byte `+3` for bit `4` again, and slides the player around it using
the angle at `object+0x26`.

**This is read and not yet checked against the game.** `emu/bp23.lua` logs
every call with the shape and the numbers it was given.

### The scale triple is a switch, and an object stamps itself into the terrain

`+0x2c`, `+0x2e` and `+0x30` were read as the object's size, `0x1000` being
1.0, and across level 0 they came out `x1.00` on 271 objects, **`x0.00` on 59**
and a scatter between. The zeroes were the clue and they are not a size at all.

One routine writes all three, `0x80044b40`, and it does exactly two things:

```
object_set_present(record, present, restore):
    cell = level_grid + (record.z >> 11) * 800 + (record.x >> 11) * 10
    if record[+0] == 1:  cell += 5           the upper of the cell's two layers
    if present:
        *cell = 0xfc                         the object's own tile id
        record[+0x2c] = record[+0x2e] = record[+0x30] = 0x1000
    else:
        *cell = restore                      the byte the caller hands it
        record[+0x2c] = record[+0x2e] = record[+0x30] = 0
```

So the triple is a **visible / not visible switch** that reaches the renderer
through `ScaleMatrix` (`0x80074910`, PSY-Q's, which multiplies each matrix cell
by the scale and shifts right 12): `0x1000` draws the model at 1:1 and `0`
collapses it to nothing. The 59 objects at `x0.00` are not tiny. They are
switched off, which is what the backlog suspected when it said "some of what
the port drew is not drawn by the game at all".

**Withdrawn: this is not the object collision.** The first reading of it here
said the cell byte was the tile *shape* and therefore that a door "is a terrain
cell while it is shut". Both halves were wrong and the way they were wrong is
worth keeping.

The byte it writes is the layer's **+0** — `cell + 0` when the live record's
`+0` is 1 and `cell + 5` otherwise — and in a cell's five-byte layer that is
the **tile index the drawing uses**, the one `draw_tile` takes the TMD object
from and `draw_cell_walk` skips on when it is `0xf0` or above. The *shape* the
collision reads is `+3` of the layer, `cell[+8]`, and nothing here touches it.
So being present sets the cell's drawn tile to `0xfc`, which is above `0xf0`
and therefore not drawn at all, and going away writes back the caller's byte.

And that byte does not come from the placement record. At
`load_object_placement`'s call site it is `type_row[+0x17]` — **byte 23 of the
object's 24-byte row in the type table**, which is `0` for 296 of the 300
types, `125` for three and `20` for one. The earlier note said "byte +23 of the
disc placement record", which is a different 24-byte record entirely, and the
resemblance is why it went unchecked: 321 placed objects have a non-`0xff`
byte there, and only 22 of them match their cell's own `+5`.

**What is left standing**, because it was established separately: the scale
reaches the renderer through `ScaleMatrix`, which by `0x1000` applies nothing,
and `object_set_present` switches it between `0x1000` and `0`.

**Withdrawn: "the triple is only a switch, and the 59 objects at `x0.00` are
switched off."** `load_object_placement` makes it a size on types with flag
`0x10` -- `p[+0x10] << 5`, so `0x80` is 1.0 -- and those are the trees, types
324 to 326, which is the "scatter" once put down to the graves. And of the 59
zeroes on level 0, **49 are empty slots**; the ten objects are five doors of
class `0x03`, one of `0x54`, and four of `0x51` that the loader takes away. The
doors are zero because a door is drawn by the grid, not as a model.

What the cell byte is *for* is now open again. It is a drawing change, not a
collision one, and the thing to find out is which objects call it with
`present = 1` -- `emu/bp20.lua` logs exactly that.

Read off `0x80044b40` in full, with the two call sites that pass `present = 1`
(`0x800489ec`, `0x8004995c`, in the object interpreter) and the one that passes
`0` (`0x80045570`, in `load_object_placement`, with `restore` from the disc
record). One wrinkle kept because it is in the code: on the "remove" path a
non-zero half at `0x801b2574` takes the *present* branch instead.

**What this does not answer** is the port's half-size objects. The draw path
applies the scale triple and nothing else — `ScaleMatrix` by `0x1000` is
exactly 1.0, the position at `+0x14..+0x1c` goes in unhalved, and the only
halving anywhere near it is in the class `0xf2` path, which draws at the
midpoint of the record's world position and a cell-anchored one. So the factor
is not applied at draw time by the game, and the remaining candidates are the
model's own units and the port's placement.

One thing the same reading does settle: **the Y angle is drawn with `0x800`
added** — half a turn, since `0x1000` is the full circle — at `0x80041374` on
the ordinary path and `0x80040f04` on the class `0xf2` one.

**And the Y matrix itself was the wrong way round in the port.** `rot_matrix_y`
(`0x8001660c`) stores cos at [0][0], `-sin` at [0][2] and `sin` at [2][0] --
`negu $v1, $s0; sh $v1, 4($s1)` and `sh $s0, 0xc($s1)` -- and `tools/level3d.py`
had those two signs swapped, so every object and creature turned by -yaw
instead of yaw: invisible at 0 and half a turn, half a turn wrong at the
quarters. A player caught it as a door swinging the wrong way, with the shove
it gives going the other way from the swing -- `godot/doors.gd` had taken its
offsets from the same wrong matrix. The X and Z builders (`0x80016598`,
`0x80016680`) were right.

**And the port left it out**, for as long as it placed objects: every object
stood half a turn round from the game. Trees, grass and pillars hid it; a
swinging door did not -- at rest its leaf lay inside the wall beside the
doorway, which read as an open doorway, where the game's own screenshot of the
same spot (`out/snap/door1.png`) is the door filling the view. `tools/level3d.py`
adds the half turn now.

### The parameter block, `+0x38..+0x3f`

Offsets here are four higher than they were written before the realignment
above; the block is the same bytes, `0xff` meaning unset, used by 64 of the 88
types seen. It is not a container inventory and it is not a script index — it
is a union, and the class byte in the type table says which reading applies:

| Type | Class | Pattern | Reading |
| --- | --- | --- | --- |
| coin pile 149 | `0x20` | `u16` at `+0x3a` | **gold**, spent by `0x8005dcc0` |
| doors 175–178 | `0x00` | `ff <x> <z> <n> 4e` | `<x>,<z>` is the door's own cell |
| keyhole 257 | `0x00` | `ff ff <k> <n>` | `<k>` is 1–3, presumably which key fits |
| chest 106 | `0x16` | `+0x38` = `00`, becomes `ff` when opened | the "still full" flag |
| tree 324 | `0x00` | `+0x38` = 120–230 in steps of 10 | **its size**, `<< 5` into the scale on flag `0x10`; read off `load_object_placement` |

The pickup path is worth reading in full, because it is the one place where a
field in this block is unambiguous:

```
lhu   $a2, 6($a1)         ; object type id
lbu   $v1, 0x38($a1)
bne   $v1, 0xff, end      ; only ever acts on 0xff
                          ; $s1 = 0x8018fb3c + id*24, the type table
lbu   $v1, 1($s1)
bne   $v1, 0x20, other    ; class 0x20 is gold, and only type 149 is in it
lhu   $a1, 0x3a($a1)
jal   0x80041eec          ; announce it, with 0x19 as the kind
sh    $v0, 6($v1)         ; retire the object: id := 0xff
lhu   $v0, 0x3a($v1)
lw    $v1, (0x801b2534)
addu  $v0, $v0, $v1       ; gold += the field
sw    $v0, (0x801b2534)
```

The type-149 record on level 0 holds `100` there, and 100 gold coins is what
came out of it in play, so this one is settled from both ends. Nothing else on
the level is class `0x20`.

For anything that moves, the neighbouring `+0x36` is motion state, not part of
this block: at `0x8004b288`, inside the object-table walk (`$s2` advances by
`0x44`), it is read, added to world X, then increased by 20 — a velocity under
constant acceleration, clamped at `0x400`.

The star marker on the maps now means "this is gold, and this much", which is
the only reading the code supports. The earlier tombstone table is withdrawn:
those values were the same bytes read at the wrong alignment, under a class
that never reaches the pickup path.

Counts on level 0, over all 346 records: 5 chests, 13 consumables (8 Earth
Herbs, 4 Antidotes, one of type 107) and **three** coin piles, holding 100, 500
and 1000. Three round values in the one field, on the one class, is the
strongest evidence yet that the reading is right. The earlier counts on this
line came from the truncated walk and were roughly half of the truth.

### The game's arctangent, and the UI's four calls

`vec_angle` (`0x80016ab8`) is what nineteen routines use to turn towards
something. It puts the larger of the two components underneath, so the ratio
never leaves [-1, 1], and folds the quadrant back with `0x400`, `0x800` and
`0xc00`:

```
|v| >= |u| and v > 0   ->  (-arctan((u << 12) / v)) & 0xfff
|v| >= |u| and v < 0   ->  0x800 - arctan((u << 12) / v)
|v| >= |u| and v == 0  ->  0
|u| >  |v| and u < 0   ->  arctan((v << 12) / u) + 0x400
|u| >  |v| and u >= 0  ->  arctan((v << 12) / u) + 0xc00
```

Underneath it, `arctan_unit` (`0x800742ac`) is **CORDIC**: twelve iterations
rotating `(0x1000, ratio)` towards the axis and accumulating what each rotation
was worth, out of the table at `0x8009591c` — `511, 302, 159, 81, 41, 20, 10,
5, 3, 1, 0, 0` against `atan(2**-i)` computed as `512.00, 302.25, 159.70,
81.07, 40.69, 20.37, 10.19, 5.09, 2.55, 1.27, 0.64, 0.32`. The last two entries
are zero, so the answer settles before the loop runs out.

Over 20000 random directions the transcription tracks a real `atan2` to within
**4.37 of 4096 units**, and that is not slack in the copy: the table's own
rounding errors sum to 4.66, so the game is that much off from the true angle
and the copy is on it. `tools/movement.py` carries it and
`godot/collision.gd` reproduces it on **400 of 400** directions.

Four routines around `0x80027000` are the whole of how a menu draws, and they
are worth naming because everything above them reads as nonsense otherwise:
`ui_prim_begin` (`0x80027414`) takes the primitive buffer out of
`current_draw_slot + 8`, calls `SetPolyFT4` on it and stamps the current
colour; `ui_prim_quad` (`0x80027494`) fills its four corners and four UV pairs
— the `POLY_FT4` layout exactly; `ui_prim_add` (`0x80027530`) files it into the
ordering table at a depth the caller picks; and `pad_read_latch`
(`0x800279a4`) reads the pad and sets a flag if anything at all is down.

### What a creature is worth

`actor_take_hit` (`0x8004c668`) is what hurts a creature, and when one dies it
calls **`award_exp(entity[+0x1e])`** — so `+0x1e` of the 120-byte entity
definition is the experience it is worth. Level 0 reads:

| entity | 0 | 1 | 2 | 3 | 4 | 5 | 6..11 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HP (`+0x12`) | 1000 | 1000 | 1400 | 800 | 300 | 800 | 100..350 |
| experience (`+0x1e`) | 9 | 11 | 28 | 15 | 36 | 18 | **0** |

The six that are worth nothing are the townspeople — entities 9, 10 and 11 are
the three men by the house — so killing a villager gives you nothing, which the
data says outright. And the first threshold is 50, so level 2 is five or six
monsters away.

`actor_attack_player` (`0x800533e8`) is the other direction: it hands three of
its own arguments to `player_take_hit` as damage values.

### Dying, and the crystal that stops it

The recorded session includes a death, and `player_controller` says what
happens. First **all 128 `ai_slots` are cleared to `0xff`** — every creature
behaviour stops. Then:

```
if has_item(107):                     the total-recovery crystal
    actors_retire_marked()
    take_item(107)                    it is consumed
    player_facing = 0x2d5
    player_pos    = 0x1c800           cell 57 exactly, no fine offset
    player_z      = 0xc000            cell 24
    player_y      = -0x3a80
    player_pitch  = 0
    layer         = 5
    level_state_write(current_level_block)
else:
    new_character()                   level 1, and the block seeded afresh
    reset_story_flags()
```

**`-0x3a80` is `-128 × 117`, and 117 is the height byte of cell (57, 24) on
level 0** — so the revival spot is a real place with the floor under it, and
the branch is level 0's. Item 107 is *"this crystal gives total recovery to the
injured body and mind"*, which is exactly what it does: one death, consumed.

Without it the game makes a new character and clears the story flags, and the
log shows the seven-state level load running straight afterwards. `has_item(0x6b)`
is the last thing in the log before that load.

### The spell table, and every spell in the game

`FDAT.T` entry 97 block 4 is **96 records of 24 bytes**, and 95 of them are
byte for byte what a RAM snapshot holds at `0x801b77ec`. The one that differs
is record 29, whose `+0` is 1 in RAM and 0 on the disc — because `+0` is the
**unlocked** flag and a fresh character has exactly one spell, *light*.

| | |
| --- | --- |
| +0 | unlocked. `skill_unlock` sets it when a skill crosses a threshold |
| +0x05 | a one-bit group: 1, 2, 4, 8, `0x10`, in runs down the table |
| +0x16 | the **MP cost**, which `cast_spell` reads |

The names are the last 31 rows of the string table at `0x8007f530` and they
line up one for one:

| | | | |
| --- | --- | --- | --- |
| fire ball 3 | fire wall 10 | fire storm 15 | flame 28, thedek 36 |
| stone 10 | earth wave 17 | meteor 26 | shudom 32 |
| haze 19 | bortecth 27 | | |
| wind cutter 3 | tornado 20 | freeze 26 | walwind 34 |
| lightning bolt 18 | flash 24 | orladin 38 | |
| earth heal 8 | antidote 6 | fire resist 8 | refusal 100 |
| missile shield 8 | light 5 | blessings 18 | |

**Which element each group bit is, is not settled.** 1 is fire and 2 is earth
from the names, and the other three do not line up with a guess: bit 4 holds
*haze* and *bortecth* while bit 8 holds *wind cutter*, *tornado* and *walwind*,
so calling 4 "wind" would be wrong in the obvious direction. The status page's
icons (below, "The menus, as they are drawn") name the five skills -- 0 fire,
1 earth, 2 water, 3 wind, 4 light -- and that order would make bit 4 water
(*haze*) and 8 wind; how a skill's thresholds reach a group is
`skill_unlock_list`'s, not yet read against the bits.

Six of the 31 have no name, at 3, 10, 14, 18, 22 and 24 — the end of each group,
so the elements have room for more spells than the game ships with.

### Casting: the buttons, cast_spell, and what keeps running

(`tools/magic.py`.) **The buttons** are `player_turn`'s (`0x8002fe1c`): the
action button's edge casts magic A (`0x801b25ab`) unless the weapon's own
magic is firing (`0x801b25b2`) or `0x801b25aa` is set; `bind_map`'s edge
casts the button's spell (`0x801b25ac`), or uses its thing (`0x801b25ad`), or
announces `0xa` when there is none left.

**`cast_spell`** (`0x8002deec`) does nothing while an action is pending
(`0x801b25e9` not `0xff`). The cost is `+0x16`, doubled by the groundal crown
(head `0x26`), halved by orladin's mail (body `0x2e`); short of it, announce
9. Weapon `0x1f` in hand casts nothing. Then the healing and protecting
spells' conditions (`0x80011920`, spell - `0x17`):

```
0x17 earth heal       HP below its most
0x19 antidote         poisoned
0x1a fire resist      0x801b256a not running
0x1b refusal          0x801b256c not running
0x1c missile shield   0x801b256e not running
0x1d light            0x801b2572 not running -- set to 0x384, the MP spent,
                      skill_practice, done: light needs no full meter
0x1e blessings        HP below its most, or cursed, dark, slowed, paralysed
```

Every other spell needs the **magic meter full** (5000). The healing five
practise here; the attacking ones when they strike (`actor_take_hit` calls
`skill_practice` too). Then the meter and the swing's pause go to 0, MP down
by the cost, the spell pending a frame on (`0x801b25ec` = 1), `casting_spell`
(`0x801b2590`) its record, and the cast's offset from the eye (`0x801b2630`,
`2632`, `2634`) -200, 200, 400, which the spell's own arm of `0x80011940`
changes along with **how many shots** (`0x801b25ea`) and **how many frames
apart** (`0x801b25eb`): fire wall 5 three apart from (-2000, 1600, 1000),
fire storm and tornado 3, haze 12, earth wave 2, meteor 4 two apart, flash 5
two apart, flame from (0, -512, 2000), shudom and walwind their own offsets,
the rest one.

**The pending action** (`0x8002ff88`): the delay counts down and at 0
`player_action(spell)` fires -- a 77-arm switch (`0x800117e8`) whose arms 0
to `0x1e` are the 31 spells in table order and `0x36` to `0x4c` the weapons'
magic. While shots remain the delay starts again at the interval.

**`skill_practice`** (`0x8002a10c`): for each skill k whose bit the record's
group has, `+3` is added to the count at `0x801b250a + 2k`; at 400 the count
is 0 again and the skill one higher -- 999 at most, announce `0x12 + k` below
it -- then `skill_unlock(k)` and the stats.

**The healing and protecting arms** of `player_action`: fire resist and
missile shield spawn two effects of their own kind at the player and set
`0x801b256a` (fire defence +50) / `0x801b256e` (slash, blow and stab +30) to
`0x708` frames, two minutes; refusal spawns one and sets `0x801b256c` to
`0xc8`, the timer that lets no hit through at all; each then the stats. Earth
heal, antidote and blessings only spawn their effect: the healing is the
effect's own (below).

**What those effects do** (`effect_spawn` and `effect_tick`'s arms of their
kinds, `tools/effects.py`):

```
0x17 earth heal    life 8; 4 frames before its end HP + 0x50, to the most
0x19 antidote      life 0x10; 12 before its end the poison gone
0x1e blessings     life 0x10; 12 before its end HP + 0xc8 and sub_8002aa54(7)
0x1a fire resist   two marks (model 0x18) turning +0x40 a frame, gone with
                   0x801b256a
0x1b refusal       one mark (model 0x2f), -0x100 a frame, gone with 256c
0x1c missile shield  two marks (0x18), -0x40 a frame, gone with 256e
```

The three healing ones pulse the lighting every frame of their life through
`sub_8003456c` -- earth heal toward (0xe6, 0xc8, 0xa0), near 0, far 0x59d8 by
`sin(life << 8)`; antidote toward (0xa0, 0xb4, 0xdc) and blessings toward
(0xf0, 0xf0, 0xa0), far 0x4650, by `sin(life << 7)` -- and antidote and
blessings throw sparkles, one and three a frame: puffs (`0x6f`) at
(`rand >> 5` - 0x200, `rand >> 8` + 0xc8, 0x400). The marks and the sparkles
have draw mode `0xe`, whose `+8 & 0xc` picks another matrix than the view's in
`render_walk` (`0x800416d8`) -- they are drawn in front of the eye; the marks
sit at (0xa0, 0x78 +- 7), two half a turn apart (`sub_80053c20`).

**`sub_8002aa54`** is the cure: bit 1 the curse and 2 the darkness (the level
cut to 0x40, the timer 0, so it ramps out), either of them the poison, 1 or 4
the slowing cut to 0x40, 4 the paralysis. Blessings cure all seven.

**Against the game's own `effect_spawn` and `effect_driver`**, the six kinds
spawned as `player_action` spawns them over every snapshot, the player hurt,
poisoned, cursed or not: **126 of 126 runs, 2698 of 2698 frames**, all 128
slots, the player's fields and the 48 lighting records alike.

**The attacking arms** -- spells 0 to `0x16` and the weapons' `0x36` to
`0x4c` -- each aim through **`sub_8002c164`** and spawn effects. The aim: the
start is the cast offset (`0x801b2630`) turned by the view's angles, the
pitch negated, from the eye (0x640 above the feet); the velocity the view's
direction (`direction_from_angles`) times the arm's speed (`vec_scale`); and
between them **`sub_8004d3c4`** picks the creature in sight -- awake (`+9`
1), not `+0xe` 3, within 0x55f0 (twice that with flag `0x20000`), its
bearing and pitch from the player within 0x200 of the view's (flag `0x20000`
instead: a quarter of the distance and 0x200 off each), the least of the two
differences and the distance over 128 -- leaves it at `0x8018fad0` and wakes
it with its behaviour `0x82` (`kind_behaviour_with_op`, `actor_switch`)
unless its `+0x28` has `0x100`. The arms (speed; what they spawn besides the
velocity):

```
fire ball 0 0x384; stone 6, 0x37, 0x46 (and 0), 0x36 (four, the offset's z
800 * 3..0) 0x1f4; 0x3e 0x2ee; 0x40 0x1b8; 0x4c 0x1c2; 0x3c 0x140; 0x3a 0x226;
0x4b 0x2d0; orladin 0x15 0x104                                  -- the velocity
wind cutter 0xd, 0x38, 0x39 0x2bc; flame 4, thedek 5, shudom 9, freeze 0x10,
walwind 0x11 0xfa; 0x42 0x384                         -- and view_angles
0x44 kind 0x7c, 0x45 kind 0x7b (and view_angles), 0x3e8
fire wall 1     0x23a, and view_angles; the offset's x 1000 on each shot
fire storm 2    0x1f4, the creature's slot (0xff none) and the shots left
earth wave 7    kind 7 at the player's feet, 0x43: 0, 0x1000, 0x100, 0x1000, 1
meteor 8        kind 0x5f (0x43), 0x1b58 ahead -- on the creature, led by its
                velocity (+0x50.. << 14 over 650) unless that collides
bortecth 0xc    kind 0xc on the creature, or 0x1b58 ahead at the feet
haze 0xb        0x104, the velocity jittered by rand, 0xe - the shots left
tornado 0xf     two, 0x540 lower, flat, and view_angles, 0 and 1
lightning 0x13  kind 0x71, flat, the creature's distance / 600 - 8 (2 at
                least; 10 with none)
flash 0x14, 0x47  0xaa from the yaw less twice the offset's x (then x + 100),
                and view_angles, 0x258, 0x3c, 0x80, 0x8c, 0xa0
0x48, 0x49/0x4a a weapon's: kind 0x78 / 0x7a from (0, 0, 100) and four more,
                0x5c / 0x5d, from (+-1500, 0, 0) and (+-3000, 0, -2000),
                handed the first's slot
```

**Against the game's own `player_action`**, its effect_spawn,
`kind_behaviour_with_op`, `actor_switch` and `collide_wrapper_actor` stood
in for and what they are handed compared, over every snapshot and its
creatures: **840 of 840 casts** -- every spawn's point, velocity and
argument, the creature woken, and the state left (`tools/magic.py
attack_check`). The effects these spawn are not in the port yet.

**The fire ball** (kind 0), the first of these effects in the machine.
Spawned as a particle (`sub_80053be4`: model 9 -- `model_table[0x31]` -- mode
5, scale 0x1000), `+0xe` 0x40, its sound (`sub_800532d4`), a life of 0x32,
`+0xd` 1. In flight (`+7` 0) `effect_move` at radius 0xb4 with the height's
top bit set and nothing below it (`effect_collide` takes the low twelve
bits for the half-height, `tile_collision` the low 28), turning 0x12c a
frame. A hit: `sub_80056580` splashes on the water (kind 0x70) when the
point is within 0x1f4 under `surface_plane_18`; then the ball steps back --
**half** its velocity when `game_isqrt((x - the player's x) ^ 2)` is under
0x400, the whole of it otherwise (`0x80056968`: the compiler's `xori`, a
square the source must have meant) -- and `sub_800536f8` hands what it hit
to `actor_attack_player` with its record's attacks, 0x1388 and the caster's
strength (`sub_80053624`: the mean of the working skills whose bit the
spell's group has; 5 for a creature's effect), from eight velocities back.
Then two frames of growth -- `+4` 0x80 + the phase, the scale 0x800 more each
-- and at phase 3 it is gone. `actor_attack_player` is a creature's
`actor_take_hit` for code 0x10 (the creature `collide_query` met, at
`0x801e648c`), `player_take_hit` for 0x80.

**`game_isqrt` and a negative word.** The GTE's `LZCR` counts the leading
*ones* of a negative input and the shift keeps it negative, so the root
reads the 192 halfwords 640 bytes before its table (another table, 446 to
512); `0xfffffff0` gives 0, `0x80000010` 0xdf0. `tools/movement.py` and the
port's `isqrt` read them now: 5010 of 5010 inputs as the game's own.

**Against the game's own `effect_spawn` and `effect_driver`**, `collide_query`,
the sound and `actor_attack_player` stood in for on both sides and what they
are handed compared: **168 of 168 runs, 914 of 914 frames**, all 128 slots,
every query, every hit with its strength and point (`tools/effects.py
fire_check`, water laid under a third of the paths so the splash is in).

**And in the game's own world.** What the ball meets is `collide_query`'s,
flags `0x31`: the tiles; where the cell is marked, the creatures --
`actor_spot_taken`: the first awake one, not dying, not masked by
`actor_skip_mask` (0 while effects run: the controller clears it at
`0x80032104`), not the one acting, its place `+0x26` higher for a follower,
within the asker's radius and its own `+0x1c`, heights its own `+0x1e` and
the asker's -- left at `0x801e648c` for `actor_attack_player`; then the
objects. **The height's top bits are flags**, and only shape opcode `0x18`,
the water's plane, reads them (`0x80033a30`): with `0x80000000` the surface
is the floor -- set, not lowered, and opcode `0x10` no longer heard -- so a
fire ball bursts on water; with `0x40000000` it is the ceiling. Every query
also leaves the three planes (`0x801e647c` the water) in RAM, seeded 100000,
which is where the splash looks. The **splash**, kind `0x70`, three of them on
the surface within 0x190 of the point (rand), each sized by
`random_spread(0x400)` + 0x1000 -- 0x2000 across, 0x2000 its rise -- and
bobbing its height scale by `sin(phase << 8)` for eight frames; their
velocity is the stack's leftover. **Against the game's own code with its own
`collide_query`**, the balls sent at the snapshots' creatures or anywhere:
**210 of 210 runs, 2512 of 2512 frames**, 34 hits on a creature, the splash
among them (`fire_world_check`). The port's `collide_query` asks the
creatures now (`actors.gd spot_taken`, a cell counting as marked within a
creature's radius + 0x800) and its tile query reads the flags, so a fire
ball meets a creature, bursts on water and splashes; what the hit then does
to the creature is the next piece.

**At `player_controller`'s end** (`0x80031f0c`), after the poison:
`0x801b256a`, `256c` and `256e` count down and recalculate the stats at 0;
`0x801b2576` counts down **holding MP at its most** every frame, announce
`0x1b` at its end; `0x801b2578` (`use_item`'s, five on every skill) counts
down, and at 0 the stats and announce `0x1b`.

**And the USE stretch** (`0x80030010`) is whole now: held this frame and the
last, with the feet not the groundal boots, the run's flag counts down, 500
goes from each meter -- an empty one pauses 60 frames, 1 (the weapon's) and 0
(the magic's) with the fu-jin or ichrius' boots (`0x4d`, `0x4f`) -- and
`damage_scale` falls by `0x80` to `0x400`, **and `player_turn` returns
there**: while USE is held no swing starts. Otherwise the magic meter refills
by `meter_gain(the five working skills' mean, rate)` where the rate is the
last cast record's `+1` (a quarter less with helm `0x25`, twice with armour
`0x30`; 0 before any cast), to 5000.

**Against the game's own code**, run over every snapshot with the deciding
fields at random: **1260 of 1260 casts, 1260 of 1260 healing and protecting
actions, 1260 of 1260 frames** each of the pending action, the timers and the
USE stretch -- every field, and every call out (`announce`, `skill_unlock`,
`player_recalc_stats`, `effect_spawn`, `player_action`). `godot/player.gd`
(`cast_spell`, `skill_practice`, `player_action`, `pending_tick`,
`timers_tick`, `use_tick`): 1000 of 1000 as the model.

### The five "rolled stats" are skills, and they unlock spells

`award_exp` rolls for five halfwords at `0x801b2518`..`0x801b2520` on every
level, and then calls **`skill_unlock` (`0x80029f1c`)** for each of them. That
routine compares the skill with five thresholds at `skill_thresholds`
(`0x80081884`, twelve bytes per skill):

```
skills 0-3   20, 35, 50, 65, 80
skill  4     10, 35, 50, 85, 115
```

and for each threshold crossed it walks a seven-byte list at
`skill_unlock_list + 7*k`, finds the first record in **`spell_table`**
(`0x801b77ec`, 24 bytes each) whose `+0` is zero, sets it to 1 and calls
`announce(3)`. So a skill reaching a number **makes a spell available**.

`cast_spell` (`0x8002deec`) settles what that table is: it takes
`spell_table + 24 * spell`, reads the **MP cost at `+0x16`**, doubles it when
the equipment byte at `0x801b25d4` holds `0x26` and halves it when
`0x801b25d5` holds `0x2e`, and announces 9 when `player_mp` is short.

And casting puts an instance in **`effect_slots`** (`0x801b80ec`): 128 slots of
`0x4c` bytes, `0xff` at `+0` when free, a kind at `+1`, a countdown at `+0x10`
that `effect_driver` spends, and a position at `+0x18`. `effect_driver`
(`0x8005bc50`) ticks them once a frame through **`effect_tick`**
(`0x800568bc`), whose first instruction is a **130-arm switch** on that kind
byte, and **`render_walk` has a third loop that draws them** — which is what
says they are things in the world rather than bookkeeping. `player_controller`
clears all 128 on death.

**This subsystem was called "AI" in this repository until now**, on the
strength of `effect_tick` reading the player's position and writing the
player's HP. It does both because a fireball in flight does both. The
creatures are somewhere else entirely: the `0x88` table at `actor_table`, ticked
by `actor_tick`.

### Four of the five skills never grow

`new_character` seeds the five skills from `level_table + 6`, which is
**zero** — the first row is `50, 30, 20, 0, 50` and
that fourth field is what all five are set to. And `award_exp` **tests a stat
before it rolls for it**: a stat at zero is skipped.

A level-1 snapshot has `[0, 0, 0, 0, 10]`, so one of the five is non-zero and
the other four are not. `new_character` sets that one itself: `+10` on skill
4 after the table's zero (`0x8002b56c`). So levelling only ever grows one of
them -- and the others grow two other ways, both read now:

* **Casting.** `skill_practice` (`sub_8002a10c`, given the spell's record)
  goes through the five from 4 down with a bit from `0x10` down: where the
  spell's group (`+5`) has bit `1 << k`, its `+3` is added to a practice
  count at `0x801b250a + 2k`, and at 400 the count goes back to 0 and skill k
  rises by one -- a banner (`0x12 + k`), `skill_unlock`, the stats again. So
  **group bit `1 << k` is skill k**, and with the status page's icons: 1 fire,
  2 earth, 4 water, 8 wind, `0x10` light. The unlock lists agree: skill 0's
  is fire ball, fire wall, fire storm, flame, thedek; skill 2's has haze and
  bortecth; skill 3's wind cutter, tornado, walwind; skill 4's light first.
* **Things.** `use_item`: **verdite** (110) raises every skill by one, the
  five **crystals** (113..117: fire, earth, water, wind, light) their own by
  three, each step with `skill_unlock` and the stats again; the **power fruit**
  (111) raises stat 36 by three, the **wise fruit** (112) `0x801b2530` -- the
  status page's second figure on the "PWR·WIS" line, shown plus one -- by one,
  to 4. A banner the first time each answers: `0xd`, `1`, `2`, `0x12 + k`.

And `skill_unlock` (`0x80029f1c`) does nothing for skills 0..3 until story
flag `0x6d + k` (`0x801ba9f5`) is set; it sets `0x7b + k` when one of k's
spells unlocks. For each threshold reached it unlocks the first spell not yet
unlocked among the first (index + 1) of the skill's list, `announce(3)` each.
21 of 21 snapshots hold exactly the spells it leaves a new character with
their skills (`tools/levelup.py`); the port has all of it (`godot/levelup.gd`
`skill_unlock`, `use_arm`; `award` calls it after each level, as
`award_exp` does at `0x8002a574`).

### Experience, and the table that is not in the executable

`award_exp` (`0x8002a310`) is all of levelling and it is short: add the
experience, cap it at **999999** (`0xf423f`), and while the total reaches
`player_exp_next` and the level byte is below `0xff`, take a level. What a
level *gives* is not computed — it is read out of a table of **99 records of
twelve bytes**:

```
+0  u16   HP maximum at this level          50 at level 1, 999 by level 97
+2  u16   MP maximum                        30 ... 999
+4  u16   added to the stat at +0x36        20 once, then 0, 1 or 2
+8  u32   experience for the next level     50, 110, 187, ... 999999
```

**The table is not in `GAME.EXE`.** It is at `0x8009f114`, which is `0x2914`
past the end of the image, so it comes off the disc — and it is `FDAT.T` entry
**97 at offset 12592**, the same shared blob that carries the cutscene list, the object
type table and the spell table. Found by taking the first thirty-six bytes of
the live table out of a RAM snapshot and searching every file on the disc for
them; one hit.

Checked against every snapshot in `out/snap`: **13 of 13** hold the HP maximum,
the MP maximum and the next threshold their level's record says, and `+0x36`
holds the running sum of the third column — 20 at level 1, 21 at level 2.

Five more figures grow by a coin toss rather than by the table: the halfwords
at `0x801b2518` to `0x801b2520`. For each one **that is not already zero**,
`rand() < 0x6665` adds one — about four times in five. That is the only place
levelling uses `rand`, and it is why two characters at the same level are not
the same character. Everything is then clamped to 999.

Above level 99 the table runs out and the routine extrapolates by the
*difference between its last two records* (`0x8002a45c`): each further level
repeats the last step, for ever. In an ordinary game it never runs, because
record 98 asks for 1000000 experience and the total is capped at 999999.

`tools/levelup.py` reads the table off the disc and carries the model;
`godot/levelup.gd` is the same machine in the port, checked against it on 40 of
40 cases with the rolled stats held at zero on both sides — the game's `rand`
is not reproduced there, and comparing two different random sequences would
say nothing.

### What a hit takes off

`player_take_hit` (`0x8002ab18`) was read months after everything around it and
never checked, because nothing in this repository had ever recorded a creature
hitting the player. A session with `emu/bp20.lua` armed did, and the formula
comes out exactly.

It is given **eight attack values and an effect**: slash, blow and stab in
`a0`..`a2`, five magic types in `arg4`..`arg8`, and in `a3` not an attack at
all. Each of the eight goes through `damage_of_type` (`0x8002a5f8`) against the
matching one of the eight defence halves at `0x801b254a`..`0x801b2558` — eight
calls, not nine. `a3`'s low nibble picks one of seven effects off a table at
`0x800117a8` (`0x801b2560` with a stat recalculation, `0x801b2564`, a
percentage roll against `0x801b255a` — the ninth defence half is that
resistance, not a damage type — for `0x801b255c`, `0x801b2568`,
`turn_slow_timer`, a cure, an MP drain), and the whole of it goes on to
`apply_damage`, whose bits 0x40 and 0x80 change the push (below, "A blow knocks
the player back"). An earlier reading counted `a3` as a ninth, "dark" attack;
every hit that settles the formula carries 0 there, so nothing below changed.
Each attack goes through:

```
A = attack * 16
D = ((stat_2524 * 0x801b24f8) >> 8) + defence * 16      0x801b24f8 is 0x1000
if A == 0:  0                                           a type not in the attack
if D == 0:  D = 0x10
d = ( max(0, A - D) + (A * A) / (2 * D) ) / 5
```

**A hit gets through two ways at once**: the part that beats the defence
outright, and a quadratic term that never quite vanishes. So an attack always
does something, and a strong enough one grows faster than a defence can hold
it — which is why armour in this game feels like it slows the bleeding rather
than stopping it.

The eight are summed and scaled twice, and both scales are read off the call
site at `0x8004d358` rather than guessed — `0x1000` into `sp+0x24`, `0xa` into
`sp+0x28`, and `sp+0x10` through `sp+0x20`, the five magic types, all zero,
with `rec+0x11` in `a3`:

```
base = sum of the eight
s1   = (0x1000 * base + 0x8000) >> 16      = base / 16, rounded
dmg  = (0xa * s1) / 10                     = s1
player_hp -= dmg                            apply_damage, 0x8002a6f4
```

**Checked against the game.** In the recorded session a creature hit a fresh
character with `(slash 0, blow 40, stab 30)` three separate times and the log
shows 50 → 36 → 22 → 8, fourteen each time. Against that character's own
defence — slash 13, blow 6, stab 4, out of `out/snap/b.ram` — the model gives
143 for the blow, 79 for the stab, 222 for the sum and **14** for the damage.
`tools/damage.py` reproduces **6 of 6** recorded hits exactly. The seventh, the
one that killed the player, logged `(10, 10, 70)` with effect `0x40`: 30 from
those three against 33 HP, so the five magic attacks that session's bp20 did
not log were not all zero — it logs them now (`m=`), with the call site (`ra=`).
`godot/damage.gd` is the same formula and `selftest.gd` holds the two together
on the same six.

### What a hit leaves behind: the seven effects, and what is worn against them

The rest of `player_take_hit` (`tools/status.py`). Before anything, two things
let a hit through not at all: **`0x801b25b4` set** and **`0x801b256c`
running** (`0x8002ab9c`, `0x8002abb0`). Then five durations, which what is worn
cuts -- the worn bytes are `0x801b25d4` head, `d5` body, `d6` shield, `d7`
arms, `d8` feet, `d9` and `da` the two items:

```
                      paralysis  poison  darkness  curse   slowing
start                 0xc8       0x384   0xa8c     0x546   0x1c2
silver arms 0x41      0x96
silver boots 0x4a                0x2a3
groundal boots 0x4c   >> 1               0x546     0x2a3   0xe1
silver ring 0x53                 >> 2                              either item
gold ring 0x56        >> 2                                         either item
globe amulet 0x58                        >> 1      >> 1    >> 1    either item
luster wing 0x5b                         >> 2      >> 2    >> 2    either item
ichrius' helm 0x29                       >> 2      >> 2    >> 2
ichrius' boots 0x4f   >> 2       >> 2
```

in that order, and then what turns attacks away, `rand` drawn only for a
piece that is worn: the **fire mail** (`0x2d`) the fire attack always; the
**dragon head** (`0x27`), **groundal mail** (`0x30`) and **ichrius' armor**
(`0x31`) slash, blow and stab one time in four (`rand() < 0x2000`); the
**promeus five** -- helm `0x28`, armor `0x2f`, shield `0x3b`, hands `0x45`
(the word at `0x801b25d4` is `0x453b2f28`) and boots `0x4e` -- the three
always; the **groundal** and **ichrius' shields** (`0x3a`, `0x3c`) the five
magic attacks one in four, the **ebony bracelet** (`0x55`) one in two.

The effect's low nibble picks the arm (the table at `0x800117a8`):

```
1  the curse      0x801b255e = 1, 0x801b2560 = curse, player_recalc_stats --
                  before the damage, so the cursing hit meets the halved
                  defence already
2  darkness       0x801b2564 = darkness; 0x801b2572 = 0 puts out the light
3  poison         0x801b255c = poison when (100 * rand()) >> 15 is above the
                  resistance 0x801b255a
4  paralysis      0x801b2568
5  slowing        turn_slow_timer, 0x801b2566
6  MP             less a sixteenth of its most, to 0
7  the poison cured
```

and the damage of the eight goes to `apply_damage` with the whole effect.
**Against the game's own routine**, run by `tools/mipsrun.py` over every
snapshot with each case laid in -- what is worn, the timers, the two ways out,
the attacks, the LCG's seed: **840 of 840 hits**, the fields, the damage and
the `rand` values drawn alike, 743 of them reaching `apply_damage`.

**What keeps running: `sub_80030e14`**, which `player_controller` calls every
frame before it reads the pad (`0x80031118`). Four things go through one ramp,
`sub_80030b24(&level, &timer, most, scale)`: while the level is under the
timer it climbs one a frame; there the timer is zeroed and the level falls
back one a frame -- so an effect of timer T lasts about 2T frames, and the
answer is `level * scale / most`, `scale` itself from `most` up, -1 (and
nothing written) once both are 0.

```
darkness  0x801b2562/64   0x40, 0xc00   the 48 lighting records' background
                                        toward (10,10,10), near toward 0x1388,
                                        far toward 0x1770; a grey 0x80 taken
                                        off the screen by a quarter of it
light     0x801b2570/72   0x40, 0xe10   the background toward (0xdc,0xdc,0xa0),
                                        the far toward 0x4650
flash     0x801b2658 -= 0x801b265a, to 0; red 0x3c added by it (0x1000 most)
curse     0x801b255e/60   0x40, 0xc00   (0x1e,0x1e,0xa) added; its level back
                                        at 0 runs player_recalc_stats
```

The blending is `sub_8003456c` -> `sub_800344dc` -> `sub_80034394`: every one
of the first 48 records' `+0x64` colour, `+0x68` near and `+0x6a` far moved
by `fixed_madd` toward its target by the intensity / 0x1000 (a 0xff colour or
a 0xffff distance left alone) and the two distances kept 0x1000 apart.
`light_table_reset` refills the records at the top of every frame, so the
blend is from the level's own each time, not cumulative. The screen's colours
are two records at `0x801aeafe` -- a count, a mode, three s16 -- which
`sub_8003d8ec` adds to and `sub_8003da10` sets, and `render_frame` draws each
asked-for one as a rectangle over the whole screen (`sub_8003d64c`,
`sub_8003d79c`), the sum over the count a byte a channel, at the rate its
mode gives: 1 adds, 2 subtracts. The paralysis adds its own orange (0x3c,
0x1e, 0) every fourth frame (`0x800313ac`). The hit's flash is set by
`apply_damage` and the two knocks (0xdac, and the step it worked out) and by
the poison (0x960, 0x3c).

**Against the game's own `sub_80030e14`**, over every snapshot with each case
laid in and the records reset each frame as the game resets them: **84 of 84
runs, 13 057 of 13 057 frames**, every field, both screen records and all 48
lighting records byte for byte. In the port (`player.gd` `take_hit`,
`status_tick`): 300 of 300 hits and 40 of 40 runs (6312 frames) as the model
has them. The darkness's and the light's near and far go to the world's
shader (`scroll.gd`) and are blended vertex by vertex the same way, and so
does their background colour: `tools/level3d.py` bakes the light with the
class's background in it and puts the background's byte in the vertex
colour's alpha, which nothing else reads; the shader moves that byte toward
the darkness's (10, 10, 10), the light's (0xdc, 0xdc, 0xa0) or an effect's
pulse colour by `fixed_madd`, as `sub_80034394` moves the record's `+0x64`, and
adds 16 times the change over 0x1000 to the colour -- what the GTE's `BK`
term does. Every class a level's cells use (0, 2, 3, 4, 47) is among the 48
the game blends; the one tinted background, class 54's (30, 25, 20), is past
them and no cell uses it. What the bake cannot keep is a colour
already clamped at full light, which the darkness then dims from 1 rather
than from above it.

### The 191 opcodes that share a target are not doing nothing

`object_interpreter`'s table has 44 distinct targets and **two of them are not
handlers**:

* `0x8004b4b4`, which 191 opcodes reach, loads `level_hooks` (`0x8018fae0`),
  takes its `+0x24` and calls it. An object whose class has no handler of its
  own is **handed to the level's own code**, which is the opposite of the
  "shared do-nothing tail" this document called it at first.
* `0x8004b4d0` is the loop's `continue`, `$s2 += 0x44`. The two opcodes that
  point there, `0xe5` and `0xe9`, do nothing — which is what section 5 already
  said from the drawing side.

A breakpoint on `0x8004b4d0` therefore fires for every object that finishes,
not for those two opcodes, and that is what the recorded session showed.

### 5.1 The player stat block, `0x801b24e0`

The starting addresses are the GameShark code list for SLUS-00255 on
gamehacking.org — the one published source aimed at this exact disc. Each was
then checked here: all are referenced by `GAME.EXE`, and the values track the
HUD across `out/snap`. Reader: `tools/player.py`, and the live map shows the
line at the top of the sidebar.

| Address | Type | Contents | Check |
| --- | --- | --- | --- |
| `0x801b24e4` | u32 | experience | 0 → 48 → 59 as the character advances |
| `0x801b24e8` | u32 | experience for the next level | 50 at level 1, 110 at level 2 |
| `0x801b24f0` | u32 | level | 1 / 2 across the snapshots; `0x8002b4bc` writes it |
| `0x801b24fa` | u16 | **maximum** HP | 50 at level 1, 57 at level 2 |
| `0x801b24fc` | u16 | **current** HP | 22 while the HUD read `HP 022` |
| `0x801b24fe` | u16 | **maximum** MP | 30 at level 1, 34 at level 2 |
| `0x801b2500` | u16 | **current** MP | 30 while the HUD read `MP 030` |
| `0x801b2502` | u16 | weapon recharge, 5000 when full | matches the "Rapid Weapon" code |
| `0x801b2506` | u16 | magic recharge, 5000 when full | matches the "Rapid Magic" code |
| `0x801b2534` | u32 | gold | 0 → 37 → 51; `0x8005dcc0` adds pickups to it |
| `0x801b2538` | u16×9 | offensive rating | slash 39, blow 32, stab 9 at the start |
| `0x801b254a` | u16×9 | defensive rating | slash 13, blow 6, stab 4 at the start |

Two corrections to the published list, both of which it had no way to notice:

* **HP and MP are stored maximum first, current second.** The "Infinite HP"
  code writes both members, so it never had to tell them apart. `chest1.png`
  shows `HP 022` against 50 and 22 in RAM; `door1.png` shows `HP 050 MP 030`
  against maxima of 57 and 34.
* the two ratings are **9-wide arrays** — slash, blow, stab, then dark, holy,
  fire, earth, wind, water — filling `0x801b2538..0x801b2549` and
  `0x801b254a..0x801b255b` back to back. The list names a "dark" entry on the
  defensive side but not the offensive one, which puts every magic label it
  gives for offence one slot low. **Settled by the game's own page**:
  `ui_ratings_page` (`0x80023300`), run over a snapshot's RAM with each half
  set apart (`tools/mipsrun.py`), labels the offense halves slash, blow, stab,
  holy, fire, earth, wind, water magic and the defense ones slash, blow, stab,
  dark, fire, earth, wind, water magic -- and draws the ninth defense half
  (`0x801b255a`) fourth, as **POISON**. What the code says besides:
  `player_recalc_stats` (`0x80029500`) writes **eight** offense halves and
  **nine** defense halves, and the ninth defense half (`0x801b255a`) is filled
  from the armour record's `+8` -- the hole in the eight `+2..+0x12` it adds
  one per rating -- and is the **poison resistance** `player_take_hit` rolls
  against. Five pieces carry one (ids 74, 76, 79, 83, 86: 25, 50, 75, 75, 5).
  The routine whole -- the curse halving, the three bonus timers, thirteen
  things worn by id, the clamps -- is `tools/equip.py recalc()`, 483 of 483
  values over 21 snapshots (one, `equip4`, with nothing worn or wielded),
  and `godot/equip.gd recalc()`, which the
  player now calls where the game does: on a level, a strong blow, an item.

### The level index

`0x8018fad9` holds the level number directly, which retires the terrain
heuristic. It was found without breakpoints, by intersecting two sources:
snapshots gave 32 727 bytes that read 0 across every level-0 dump and 4 on the
level-4 dump, and the disassembly showed that only **28** of those are
addressed by any instruction at all. The survivors cluster in a small state
block, `0x8018fad8..0x8018fae9`, written by the level-setup code around
`0x800179xx`; live it reads `04 04 04 0d 0f`, with a second copy at
`0x8018fae4`. Confirmed against two levels so far, so the trailing `0d 0f`
fields are still unread.

The live map now takes the level from RAM and reports the terrain match beside
it, so a disagreement shows up instead of being silently papered over. A later
crossing re-confirmed it: the byte went 0 to 4 exactly when the player walked
from level 0 to level 4.

### Current level versus pending level

Tracing the writes to that block gives the transition mechanism:

| Address | Role |
| --- | --- |
| `0x8018fad8`..`0x8018fadc` | **current** level state, 5 bytes |
| `0x8018fae4`..`0x8018fae8` | **pending** level state, same shape |
| `0x80018358` | commits pending into current, byte by byte, skipping any byte left at `0xff` |
| `0x80029188` | fills the block with `0x63`, a reset between areas |
| `0x8005ffd0` | restores the block, and the position blocks at `0x801b25f0` / `0x801b2610`, from a saved structure — the save-load path |

So the game asks for a level by writing the pending block and letting
`0x80018358` pick it up. Writing the pending block alone does nothing — tested,
the game never picks it up, because `0x80018358` only runs inside a transition
rather than every frame.

### Crossing between levels

Three crossings under live breakpoints, and the earlier reading of this was
wrong in an instructive way.

**`0x80017c78` is not the level setter.** It had been identified as such by
inference — a boot-time hit inside it, no direct capture. Watched across a real
0 → 4 crossing it fired exactly once with *every argument zero*, and across the
4 → 0 crossing back it did not fire at all, while the level changed both times.
What it does do is take its eight arguments straight out of an object record:
the caller at `0x8004a824` sits in a loop stepping `$s2` by `0x44` and reads
`+0x32`, `+0x33`, `+0x34`, `+0x35` into `a0`–`a3` and `+0x36`, `+0x38`, `+0x39`,
`+0x3a` onto the stack. So it is driven by placed trigger objects, and `0xff` in
`a0` means "keep the current level" while `0xc8` in the fifth argument makes it
return immediately.

**What actually loads a level**, caught with a write watchpoint on the level
block rather than by guessing at routines:

```
0x8018fae4                     the pending level -- a byte
0x800187f0  lbu  $a0, (0x8018fae4)
0x800187f4  jal  0x8005f444     the loader; a0 = level, seen carrying 4
    0x8005f46c  jal 0x8005ee58  fills a pointer table on the stack
    0x8005f474  sll $s0, $s0, 2
    0x8005f47c  lw  $s0, 0x10($v0)   table[level] -> the level's descriptor
0x800189bc  sb   ...            stores the current level into 0x8018fad8
```

`0x8018fae4` was already visible as "a second copy" of the state block; it is
the *pending* half of the pair, and `0x800187f0` reading it is what settles
that. The store at `0x800189bc` is the instruction the watchpoint caught, so
the current-level block is written from there.

**A level change reads FDAT after all.** This document said for a long time
that "a level change reads no archives at all", on the strength of five
breakpoints that caught nothing. The breakpoints were on the wrong readers:
`level_load` uses `read_archive_entry` at `0x80019d48`, which was never among
them. It reads entry `3n + 0` and entry `3n + 2` with the archive index 4, and
the claim is withdrawn.

Cross-level travel therefore looks like: set `0x8018fae4`, then get the loader
invoked. *Not yet attempted* — writing the pending byte alone should do nothing
until something drives the load.

Other callers of `0x80017c78`, for whenever the trigger objects are decoded:
`0x80029244`, `0x800292a8`, `0x80029360`, `0x8004a3f4`, `0x8004a424`,
`0x8004a54c`, `0x8004a858`, `0x8005c9b8`, `0x8005c9e8`, `0x8005cb80`.

### Walking from one level into the next

**The levels are pieces of one world, and the player walks from one into the
next.** No teleport: an object of opcode **0xe0** (type 280, drawn as nothing)
names a rectangle of cells -- its own cell, `+0x38` wide, `+0x39` deep -- and
its arm in `object_interpreter` (`0x8004a7f8`) asks `player_in_rect` whether
the player's cell is in it, and their y within the object's (above
y - 0xc80, not below y + 0x800). If so, `object_trigger_args` calls
`object_trigger(+0x3a..+0x3e, +0x40, +0x41, +0x42)`: a **level block** of five
bytes -- the five at `0x8018fad8`, the level second, 0xff "as it is" -- and a
**shift in cells**. `object_trigger` starts a change only when none is under
way (`0x8018fad4`) and the block is not the one in hand: the pending block at
`0x8018fae4`, the shift at `0x8018faed`, `level_load`'s state machine at 0.
When `level_load` has the new grid it calls `world_shift(+0x40 * 2048,
-(+0x42 * 128), +0x41 * 2048)` -- unless the first is 0x7f -- over the player,
the effects, the objects and the creatures, so the player walks on where the
new level has the same ground; the level is current a hundred frames later.

**The shift is in the placement record.** `load_object_placement`'s arm for
class 0xe0 (`0x80045668`) reads p[+0xa], p[+8] and p[+0xc] -- which put any
other object somewhere inside its cell -- as the cell the player is to stand
in on the other side: it takes them back off the position and keeps target
minus own cell, or 0x7f when p[+0xa] is 0xff. Level 0's way into level 4 is
its slot 173, cell 46 of its southern edge (z 70 to 79), block
`[4, 4, 4, 13, 15]` and z -70: level 4's z 0..9 is level 0's 70..79. Level 4's
way back is its slot 1 at cell 52, +70; its slot 5 leads to level 12, shifted
(-36, +15). The crossings that would keep the level -- level 0's slot 120,
level 4's slots 4 and 16 -- have no shift, and are what tells the port each
level's own block.

**Checked against bp16**, which walked from level 0 into level 4 and back:
`tools/crossing.py` fires on frames 8105 and 13058, where the player steps
into the rectangles, and the log's player jumps by -70 and +70 cells nine
frames later each time -- the frames `level_load` spends on the disc -- and
the model fires nowhere else; the one other jump in the log is a new
character's start.

**In the port**: `tools/level3d.py N` writes `worldNN.tscn` for each level it
builds, beside the per-level data it always wrote; `godot/crossing.gd` runs the
arm over `crossNN.json` and, on a change, loads the other level's world on the
trigger's frame and puts the player down shifted, with what they carry. The
comparison (C) follows the game into the other level's world when it is built.

### Identifying the loaded level (fallback)

Walkability alone is useless — the levels whose grids carry no solid cells
match anything at 100 %. Scoring each object's world Y against the terrain
height byte beneath it is decisive:

| Snapshot | Best | Runner-up |
| --- | --- | --- |
| starting area | level 0 at 82.3 % | level 5 at 32.9 % |
| chest, door | level 0 at 81.6 % | level 5 at 32.9 % |
| second area | level 4 at 77.4 % | level 0 at 29.5 % |

`tools/objects.py: which_level()`. The table's address moves between sessions,
so `find_table()` locates it by scanning for the longest run of valid records.

Readers: `tools/objects.py`, `tools/psxlive.py`, `tools/snap.py`, `tools/diff.py`.

---

## 6. Running it

PCSX-Redux boots the disc on the bundled OpenBIOS, so no console BIOS image is
needed.

```
emu/run.sh            # start; HTTP API on :8080
emu/run.sh stop
```

The HTTP API is read-only but does not disturb the game, so it carries all the
polling:

```
GET /api/v1/execution-flow    {"running": true, ...}
GET /api/v1/cpu/ram/raw       2 MB
GET /api/v1/gpu/vram/raw      1 MB, 1024×512 16bpp
```

The GDB stub on port 3333 handles **writes**. An earlier note here claimed it
could not resume after halting; that was wrong — the CPU-usage check behind it
was reading the wrong pid. `/api/v1/execution-flow` is the reliable signal, and
against it the sequence halt → `M` → `c` resumes cleanly every time.

```
0x03            interrupt        -> running: false
M<addr>,<len>:<hex>              -> OK
Z0,<addr>,4     breakpoint       -> OK   (Z1 hardware also accepted)
z0,<addr>,4     clear it         -> OK
c               continue         -> running: true
```

**The GDB stub's breakpoints are a no-op**: `Z0` and `Z1` both answer `OK` and
neither is ever honoured, even against an address caught executing 14 times out
of 14. Its memory reads and writes do work.

**Breakpoints do work through Lua**, and getting there took three wrong turns
worth recording:

1. they need the interpreter — the binary itself warns that the debugger and
   the dynarec conflict;
2. they need `Debug` on, and **setting it in `pcsx.json` does not take** — it
   still reads `false` at startup. It has to be set at runtime;
3. the setting lives at `PCSX.settings.emulator.Debug.Debug` — lower-case
   `emulator`, and `emulator.Debug` is a nested group, so assigning to *it*
   succeeds while changing nothing.

With the flag set from Lua the API flips to `"debugger": true` and breakpoints
fire immediately. Launch with:

```
pcsx-redux -interpreter -lua_stdout -dofile emu/bp.lua -iso emu/kf2.cue -run
```

`emu/bp.lua` sets the switch, arms the archive readers and logs archive, entry
and return address for every hit to `out/lua_bp.log`.

There is still no way to press a button, so anything needing input has to come
from a person at the window.

### Never `return false` from a breakpoint callback

For most of this project every armed breakpoint fired exactly once and went
quiet, and that was written down as "breakpoints here are one-shot". It was
nothing of the kind. Every callback ended with `return false`, meant as "do not
halt the emulator" — and PCSX-Redux reads that as **do not keep this
breakpoint**. Returning nothing instead, a write watchpoint on the player
position fires on every frame, as it should.

The cost of the mistake was two conclusions drawn from silence, both withdrawn:
that `0x80017c78` is not the level setter because it did not fire on a return
trip, and that a level change reads no archives because five readers caught
nothing. The second was later disproved from the code, which is what exposed
the pattern.

**Silence from an instrument is only evidence once the instrument has been shown
to speak.** Arm a control on something known to happen constantly, in the same
run, and check it before believing a negative.

One thing the corrected control showed immediately: `level_load` is called
**every frame** from the main loop at `0x80014f6c`, not once per level change.
It decides for itself whether there is anything to do.

### Teleporting

The player position sits in **four copies** that the game keeps in step:

```
0x801B0A10   0x801B25F0   0x801AEC4C   0x801FFF98
```

Writing one alone is overwritten within a frame and the player snaps back;
writing all four together holds. Y is taken from the terrain (`-128 × height
byte`) so the landing is on the ground, and a target whose cell is solid rock
is refused.

This moves the player **inside the loaded level only**. Reaching another level
would mean driving the game's own level loader, which is not decoded yet, so
cross-level travel is not available.

### Live map

```
python3 tools/livemap.py          # then open http://localhost:8777
python3 tools/livemap.py stop
```

The server writes its own pid to `out/livemap.pid`; a shell that launches it
with `setsid` records the wrapper's pid instead, which is not the process to
kill.

Level detection is a heuristic and does drift, so the page can pin a map by
hand: pick it from the dropdown or press **Lock**, and auto-detection stops
touching the terrain. Object pins are always read straight from memory and stay
correct regardless — only the background image is affected.

Maps can be named as they are recognised. The dropdown offers the 41 real area
names lifted from `ITEM.T` entries 810-851 (`data/area_names.json`), and each
assignment is persisted to `data/level_names.json`, so the numbering fills in
with real names as the game is explored.

A published artifact cannot reach the emulator — different origin, sandboxed
page — so this serves the map itself and talks to the emulator API from the
same origin. It polls the player position about twice a second, drops a
breadcrumb trail, keeps a distance-sorted list of nearby objects, and reloads
the object list and terrain automatically when a new level loads.

Locating the table and matching the level are the slow steps, so both are
cached behind a cheap signature — record count plus the first few type ids —
and only redone when that signature changes.

Caching the table address across a level change is where this kept going wrong,
and it took two attempts to get right. The per-record check is loose, so other
places in RAM parse as runs of records — there is a 36-record decoy a few KB
from the real table. Demanding a minimum length was not enough: the decoy
cleared it, its signature never changed, and the map stayed empty forever
because a rescan was never triggered.

What works: treat the cached address purely as a fast path and rescan whenever
anything smells wrong — the signature changed, the run got short, the object
count fell below the floor, or the level match never rose above 40 %. A full
rescan costs about 0.1 s, so there is no reason to cling to a stale address.
`find_table` then picks the longest run, which is always the real table.

Level seams are not marked in the world, so `data/transitions.json` records the
player position at the moment the level changes and the map draws those points
as blue diamonds.

---

## 7. Disassembly

`tools/disasm.py` binds `libcapstone.so.4` out of the PCSX-Redux AppImage
through ctypes and decodes 129 286 instructions, about 90 % of the text
section. Three traps cost real time and are worth remembering:

* `cs_arch` has MIPS at **2**; 3 is x86, and asking for 3 returns confident
  x86 output instead of failing;
* capstone 4's `cs_insn.bytes` is **16** wide — v5 widened it to 24, and a
  wrong width silently shifts `mnemonic` and `op_str` into garbage;
* the code buffer must go over as `c_void_p`, never `c_char_p`, which stops at
  the first NUL — and MIPS is full of them, every `nop` being four zero bytes.

The text section opens with the archive filename strings, so disassembly starts
at the entry point rather than the section base.

### What it has turned up

| Address | What |
| --- | --- |
| `0x8001a34c` | opens an archive: `$a0` = archive index, `$a1` = filename |
| `0x801c172c` | archive descriptor table, 12 bytes per archive |
| `0x8004b288` | object-table walk applying motion, `$s2 += 0x44` per record |
| `0x800441d4` | `(archive, entry)` -> loads into the buffer at `*0x80199154`; five callers, all pulling text and art from `ITEM.T` and `TALK.T` |
| `0x8005d5f8` | loads `ITEM.T[810 + n]`, the **area name**, with `n` from field `+0x3a` |
| `0x80061088` | builds `\DRM\Dnn.S;1`, index clamped to 0..17 — the streaming path, alongside `\STR\Snn.S;1` at `0x80060fec` |
| `0x80035808` | forms the player position address |
| `0x80019f14` | entry extent: reads `off[n]` and `off[n+1]` from an archive |
| `0x80019cc4`, `0x8001a154`, `0x80027d88` | read an entry; `$a0` archive, `$a1` entry, `$a2` destination |
| `0x80044204` | reads with **both** archive and entry in registers — the generic path, and the likeliest level loader |
| `0x80018f5c` | block copier `(dest, src, words)` used to scatter a loaded entry |
| `0x8002bee8` | reads FDAT entry `id + 98` against a 68-byte-per-id table at `0x801d37a4` |

At boot the game reads FDAT entries **96 and 97** — the irregular tail of the
archive, not level data — and scatters blocks from them to `0x8018fb3c`,
`0x801d37a4` and `0x801e64b8`. The per-level triples at `3n` are loaded
elsewhere; finding that call is the open question.

Archive indices, from the registration block at `0x80017678`:

| 0 | 1 | 2 | 3 | **4** | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MO | MOF | VAB | RTIM | **FDAT** | RTMD | ITEM | TALK | STALK |

Six pieces of code form the player position and 32 the inventory base, so both
anchors are solid starting points for the next pass.

---

## 8. Items, and what they unlock

The question this answers is "which thing in the world wants which item", and
it is reachable without playing: any such condition has to touch the inventory,
and the inventory is at a known address. Extractor: `tools/items.py`.

### The inventory is two arrays, and item ids stop at 149

Three leaf routines carry every change:

| Address | What it does |
| --- | --- |
| `0x8005d7bc` | `has_item(id)` — true if `A[id]` or `B[id]` is non-zero |
| `0x8005d7f8` | `take_item(id)` — decrements `A[id]`, falling back to `B` |
| `0x8005d898` | `give_item(id)` — increments `A[id]` while under 99, else `B` |

`A` is `0x800c85e8` and `B` is `0x800c867e`, exactly 150 apart, and both are
indexed by the same id — so the ids these routines handle run **0 to 149**. All
four consumable types we have identified (104, 105, 107, 127) fall inside that.
What `B` is for is unread; it is not a second stack, since `give_item` only
reaches it once `A` is full at 99.

### An object's type id is the item it yields

Picking something up needs no table at all. At `0x8005e01c` the use handler
does `give_item(object->ObjectID)` — it hands over the object's own type id.
That is why inventory slot 104 tracked the Earth Herb on the ground, and it
means every pickup in the game is already readable from the object table with
no further decoding.

### Using an item on something is hardcoded, in one function

`0x8005cbe0`, 759 instructions. The selected item arrives in `$s5`; the
function branches on the type id of whatever the player is facing, and each
branch consumes, grants and announces. The complete set of pairs it holds:

| Facing type | Condition | Effect |
| --- | --- | --- |
| 91 | — | consumes item 128 |
| 257 (keyhole) | its `+0x38` must be 255 | consumes the selected item |
| 162 | its `+0x38` must be 136 | consumes the selected item |
| 162 | its `+0x38` must be 255 | consumes the selected item |
| 254 | — | **grants item 119**, consumes the selected item |
| 1 | — | **grants item 120**, consumes the selected item |

Only three literal item ids appear anywhere else: 1 and 2 around `0x8002a230`,
and 107 at `0x80031d60`. Everything else is taken from data, which is the
useful part — the conditions live in the level's own records, not in the code,
so they can be tabulated per level once those records are decoded.

### What this does *not* show

`+0x38` is read as a per-instance condition here, which is tempting to read as
the `KeyID` name the KingsFieldRE wiki gives it. The data says no: all seven
keyhole instances on level 4 carry `+0x38` = 255, the same value the branch
above requires, so it is a gate rather than an identity. Whatever selects
*which* key opens *which* lock is somewhere else.

---

## 9. The entity script language

Interpreter: `0x8005c308`. It fetches a byte and, for anything from `0xf0` up,
dispatches through a **16-entry jump table at `0x80013160`**; anything below
falls to a common handler. Reader and decoder: `tools/escript.py`.

| Opcode | Bytes | Meaning |
| --- | --- | --- |
| `< 0xf0`, `0xf1`, `0xfa`–`0xfe` | 1 | drives an animation, and *when the entity's kind byte is `0x2b`* also loads `TALK.T[base + opcode]` — so a talker says a line and everything else plays a frame. `base` is the `u16` at record +0x0c |
| `0xf0 n` | 2 | jump back `n`, setting the header's retry flag |
| `0xf2` | 2 | skip |
| `0xf3`, `0xf4`, `0xf5` | 1 | skip |
| `0xf6` | 1 | copy the actor's byte +1 into `0x801baa2e` |
| `0xf7 i v` | 3 | `flags[i] = v` |
| `0xf8 n` | 2 | jump back `n` |
| `0xf9 i v t` | 4 | if `flags[i] == v` jump to label `t`, else fall through |
| `0xff` | 1 | end |

`flags` is a byte array at **`0x801ba988`** — the game's own state. Nine pieces
of code reach it, among them the serialiser pair, `object_trigger` and the
object interaction handler.

### The nine users of `story_flags`

Every piece of code that reaches `0x801ba988`, and what it does there:

| Where | What |
| --- | --- |
| `script_interpreter+0x150` | opcode `0xf9`, the conditional |
| `script_interpreter+0x240` | opcode `0xf7`, the assignment |
| `script_prescan+0xa0` | the same conditional again, read ahead of the interpreter |
| `object_trigger+0x284` | **`flags[0] = max(flags[0], destination level)`** |
| `reset_story_flags` | zeroes `0x40` bytes at the base and more at `+0x100`; called at new game |
| `save_serialise+0x4d8` | copies the array **out** to the save buffer |
| `save_restore+0x4e4` | copies it back **in** |
| `cutscene_step+0xb4`, `cutscene_step+0xd8` | tests `flags[b & 0x7f]`, bit `0x80` picking which of two checks, returning 2 or 0x10 |

Three things follow. The array is **saved and restored** — the serialiser pair
moves it to and from the save buffer — so it is persistent game state, not per-level
scratch. It is **exactly `0x100` bytes**: the reset clears `0x40` *words* of
it, the serialiser copies `0x100` bytes of it, and `level_state` begins at the
byte after.
And **`flags[0]` is a progress counter**: `object_trigger` raises it to the
destination level number whenever that is higher than what it holds, and never
lowers it, so it records the furthest level the player has reached.

### A conversation gives you one section per visit

The 43 conversation blocks hold **733 lines**, 105 `f8`, 79 `f2`, 60 `f9`, 60
`f4`, 57 `f0`, 55 `f5` and 43 `ff` — and **no `f7`, `f3` or `f6` anywhere**. A
script *tests* story flags and never sets one; something else writes them.

Two opcodes had been read wrong. **`f2` is a label**, not a two-byte skip, and
**`f9` jumps to a label rather than to an offset**: `0x8005c18c` scans the code
from pc 0 for an `f2` byte, compares what follows against the operand and lands
just past it. The scan is over bytes rather than instructions and gives up at
the first `0xff`, so a label past the first stop cannot be reached.

**`f0` is the mechanic the whole language is built on.** It jumps back onto the
line before it *and sets the retry flag*, so pressing the button again repeats
that last line for ever. What moves a conversation on is talking to somebody
**else**: `script_interpreter` compares the global `script_speaker`
(`0x801baa2e`, the previous talker's `actor[+1]`) against this actor's, and
when they differ and the retry flag is set it scans forward from the stored pc
to the next `f0` and resumes just past it. `f8` jumps back *without* setting
the flag — that is where an entity runs out of things to say.

So the shopkeeper on level 0 hands out six sections over six visits and the
innkeeper twelve.

**The save file confirms all of this from the other side.**
`level_state_write` (`0x8005efd4`) walks the 40 entity records and, for each
one whose `+0x38` is not null **and whose first byte is `0x70`**, writes three
bytes: the entity index, the byte at `+0x10` and the byte at `+0x13`.
`apply_level_state` (`0x8005f444`) reads the same triples back, terminated by
`0xff`, and stores them into `+0x10` and `+0x13` of the block. Two fields out
of twenty, from the block reached through `+0x38`, gated on `0x70` — which is
the whole reading of the header arrived at independently, written by code that
has nothing to do with the interpreter. An entity remembering how much of its
conversation it has given you is a saved game's business, so it is saved.

Starting is its own small machine. `script_prescan` (`0x8005c1e8`) reads the
code from pc 0, where a chain of four-byte guards sits — `f1 flag value label`
— and the **first** one that holds wins, provided its label is further on than
the pc already stored. The chain ends with a lone `0xfe`, and a fresh
conversation starts just past it, which is why the recorded trace begins at
pc 1. Eighteen guards exist in the game, on ten conversations.

**Withdrawn:** "1086 scripts decode to 12 179 plain instructions, 876 ends and
four `0xf9` conditionals", "six `f4` calls in the whole game", and "it reaches
`TALK.T` only when the entity's kind byte is `0x2b`, and exactly one entity of
265 is that kind, so every other script is a list of animation frames". The
first two counted blocks 1..15 as scripts. The third misread the branch: the
`0x2b` comparison skips a call to `0x800608ec` and the `load_entry(7, base +
opcode)` sits past its target, so the text is fetched either way — which is
why `out/story.txt` is now full of English.

`FDAT.T` entry `3n + 1` is where the conversations are after all.

### A quest, end to end

Both ends of a quest are now legible and `python3 tools/story.py quests`
prints them together. **43 story flags are read by a conversation, 26 are
written by a conversation hook, and 15 are both** — those fifteen are the
quest steps.

Level 0's is the plainest. Entity 10 calls `f4 0`, which asks whether the
player holds items 2, 130, 131 and 132 and writes the answer into
`story_flags[3]`; the same entity's guard at pc 31 reads `story_flags[3] == 1`
and starts the conversation somewhere else when it does. Then `f4 1`, which
asks the same four questions, sets `story_flags[1]`, takes all four items and
unequips the sword if it was one of them.

Level 2's entity 7 is the elaborate one: **eight guards on `story_flags[16]`**,
against 1, 2, 3, 4, 104, 107, 108 and 109, and the level's hook writes 104,
107, 108 and 109 from four of its arms. One NPC with eight things to say
depending on how far along you are.

A flag a hook writes and no conversation reads is not a quest step — it is
read by native code, or by nothing.

### The `0x8001dxxx` cluster is the pause menu, not the conversations

The two routines that load `STALK.T` with a literal archive index turned out to
be a **text page viewer**: `0x8001d944` walks a list of entry indices held on
its own stack, calling `0x8001dbc4` to fetch a page and `0x8001dcd0` to draw
it. Above it, `0x8001d784` and `0x8001a774` are menu screens, and `0x8001a774`
has exactly one caller. Its siblings `0x8001dee4` and `0x8001e1b4`, the two
that read the inventory, are the item screen. So the whole cluster is UI, and
the choice of what to show is made before any of it runs.

Which pointed at the objects, and there the answer was — though not by the
route first proposed. The idea that "object types carry people's names, so NPCs
are objects" was worthless: those names come from `ITEM.T[type id]`, and this
document already records that the biography range resolves falsely, which is
why *Jamie Porter* shows up 28 times. Withdrawn.

The real path is in **`0x8005e2d0`**, the object interaction handler, and it is
short. See §10.

Every conversation in the game, in the order the game tells it, is written to
`out/story.txt` by `python3 tools/story.py`; `python3 tools/escript.py <level>`
disassembles them. Both are regenerated from the disc, so neither is
committed.

---

## 10. Object to text

Reading a sign, a grave or a plaque is four instructions of decision inside
`0x8005e2d0`, and it needs no table lookup at all:

```
lhu   $a1, 0x26($s0)     the object's own facing
addiu $a1, $a1, 0x800    turned around
jal   0x80016a2c         is the player looking at it, within 0x155?
beqz  $v0, skip
lhu   $a1, 0x38($s0)     the object's +0x38, read as a halfword
ori   $a0, $zero, 6      archive 6 is ITEM.T
addiu $a1, $a1, 0x96
jal   load_entry         show ITEM.T[150 + it]
```

So **the text an object shows is `ITEM.T[150 + u16 at +0x38]`**. 150 is
exactly where the signs and nameplates begin in our index of `ITEM.T`, which is
the corroboration — the offset was not chosen to fit, it fell out of the code.

**The whole branch** (`.L38`, `0x8005e7c4`) asks two bytes first, which the
excerpt above leaves out: the object's `+0x3e` must not be 0 (`object_mode` 0
zeroes it, which is how a sign is taken away), and the facing test is made
only while `+0x3d` is 0 -- level 0's signs carry 0 or 0xff there, so some are
read from any side. Classes `0x0d` and `0x14` both come here.

**How it is shown.** `load_entry` (`0x800441d4`) reads the entry, clears VRAM
(960, 256, 64, 240) to 0 and loads each of the entry's TIMs where it says --
the words sit at their place on a 4-bit page, under the CLUT the TIM brings to
(96, 480), the banners' palette -- keeps the screen, and runs
`load_wait_screen` (`0x80043bb8`), frames of its own:

```
each frame   the kept screen at 0x80 - s2 / 2; the page's (0,0)-(255,208) at
             (32, 32) twice, subtracted one texel down and right, then added,
             both at s2: the words and a shadow
fade in      s2 = 0, 0xc .. 0x6c: ten frames; the pad read after each -- up
             first, then a press ends it, and the fade out starts from there
wait         (load_entry, 0x800442c8) nothing drawn: the pad up, then any
fade out     from 0x50 by 0xc: seven frames, a press ending it early too
```

The same call shows a conversation's lines (`script_interpreter`, archive 7,
TALK.T) and `use_item`'s pictures. The port: `godot/document.gd`, started by
`godot/loot.gd`'s walk; `tools/readables.py` composes the pages and models the
frames, and the self-test holds the port to it (27 of 27).

`+0x38` belongs to the union each class reads its own way, so the index means
something only for the classes that read. **Type 299 is the readable one**: 13
on level 0, 4 on level 4, and their indices land in the sign and label ranges.
Every other type puts values there that run off the end of the archive, which
is how they can be told apart. Reader: `tools/readables.py`.

Level 0, from a snapshot, with our own OCR of `ITEM.T` supplying the words:

| Cell | Says |
| --- | --- |
| 29,60 | *Inn One Night 150G* |
| 46,62 | *Jack Leininger* |
| 45,51 | *Cristy Clemes* |
| 2,62 | *The Queen of Verdite* |
| 3,62 | *The Dead Body of Leon* |
| 2,61 | *The Tomb of Leon* |
| 63,55 | *The Statue of the Hero* |
| 0,63 | *The Royal Emblem* |
| 62,3 | *Picture of a Warrior* |
| 49,19 | *Broken Cart* |

This also retires an old coincidence. §5 once explained unique landmarks by
`ITEM.T[type id]` resolving correctly; it does not. They resolve because the
*instance* carries the index in `+0x38`, which is why two Statues of the Hero
sit in the same cell and read the same.

**It only works where we have a RAM snapshot.** Object placement has not been
decoded off the disc, so levels 0 and 4 are the whole of it for now — and that
is the one thing standing between this and a complete list for the game.

---

## 11. The save block

`0x8005ee58` is not one routine but four in a row, and together they describe
how the game keeps what you have done:

| Routine | What |
| --- | --- |
| `level_state_unpack` | reads 32 `u16` offsets and turns each into `level_state + offset`, or null for `0xffff` |
| `level_state_pack` | the inverse, for saving |
| `level_state_rebase_up` / `_down` | walk a chain of records, adding or subtracting a base from the pointer at `+8` of every record whose kind byte is 1..3; each step advances by the size at `+4` plus 12 |

Which lays out one contiguous save block:

| Address | Contents |
| --- | --- |
| `story_flags` `0x801ba988` | the flag array; `flags[0]` is the progress counter |
| `level_state` `0x801baa88` | `0x5000` bytes of chained variable-size records |
| `level_state_index` `0x801bfa88` | 32 `u16`, one per level, `0xffff` until that level has state |

`reset_story_flags` clearing `0x40` **words** at the base — 256 bytes, the
whole flag array — and `0x1400` more at `+0x100` is this block, and the
serialiser pair copying the array in and out is this block being saved and
restored.

**This was read as 64 bytes for a long time, and that was a `block_zero`
whose count is in words being read as if it were in bytes.** It cost
something real: `tools/escript.py` and `godot/escript.gd` both sized the
array 128, so the six flags a conversation reads past that — 135, 137, 140,
143, 144 and 147 — failed a bounds check inside the model and could never
hold. Nothing showed it, because every recorded conversation leaves them
zero and a guard on a zero flag does not hold either way.

**It is state, not placement.** On a fresh level 0 the index has *no* slots
used; after progressing, one. So these records are what the player has changed
— what has been picked up, what has been opened — and object placement is still
somewhere else. Which also settles why a level change reads no archive: the
game is applying saved state to a level whose contents arrive by another route
entirely.

### Proved against the memory card

Calling this the save block was an inference from three behaviours until a
controlled experiment settled it. Save the game; pick up one Earth Herb; save
again to a second slot. In RAM the inventory slot goes 2 → 3, so the action is
isolated.

| | Result |
| --- | --- |
| `level_state` changed between the two moments | **144 bytes** |
| the saved copy changed | **the same 144 bytes, same offsets, same values** |
| `level_state` against the save it produced | **6904 of 6904 bytes equal** |

`0x801baa88` is save data, and picking something up is recorded there.

### What a level's record actually says

The 144 bytes are not a diff. `level_state_write` (`0x8005efd4`) builds the
whole record from scratch every time something changes, on its own stack, and
`apply_level_state` (`0x8005f444`) reads it back at level load. Between them
they say what the format is, and it has **three sections**.

**One: the actors that are gone.** Walk all 200 slots of `actor_table`,
0x88 a slot. For each slot whose byte 0 is **1** — category 1, and no other
category — write the slot index and then `3` if the actor's `+9` is `3`,
otherwise `0`. Terminate with `0xff`. So a category-1 death is kept and
nothing else's is. (This said the walk stopped at the first byte 0 of `0xff`.
It does not: such a slot is skipped like any other category, and the game's
own routine, run below, settles it.)

**Two: how far each conversation has got.** Walk the 40 entity records; for
each whose `+0x38` is not null and whose block begins `0x70`, write the entity
index, the program counter at `+0x10` and the retry flag at `+0x13`.
Terminate with `0xff`. §9 has what those two bytes mean.

**Three: one opcode per object slot**, 396 of them, in lockstep — the decoder
advances its own pointer by `0x44` once per record and stops at 396, so there
is no terminator and no slot is skipped. The opcode is chosen by the object's
*class*, `object_type_table[type].byte0`, through a **233-arm table at
`0x80013298`**, and the arms land in six places:

| Arms | What is written |
| --- | --- |
| 200 | `0xfe` — nothing about this slot is worth keeping |
| 25 | `0xfd` and the object's state byte at `+0x38` |
| 5 | `0xf4`, the state at `+0x38`, and the byte at `+0x39` |
| 1 | `0xf5` and the byte at `+0x39` |
| 1 | the opcode the object's **kind** byte at `+0x04` chooses: `0x60`→`0xf0`, `0x61`→`0xf1`, `0x62`→`0xf2`, `0x70`→`0xf3`, anything else `0xfd` |
| 1 | `0xfd` and the state — **unless the state is below 2, in which case nothing at all is written** |

`0xf0`, `0xf1` and `0xf2` are **an object that was not there when the level
was built**: the decoder calls `init_object_record`, stamps the kind byte
`0x60`, `0x61` or `0x62`, and then reads the type id and a position — `x` and
`z` as two bytes each, which it shifts back up by 2 (the encoder wrote
`x >> 2` and `x >> 10`), `y` as two bytes it sign-extends — and puts `0x63` at
`+8`, `0xff` at `+0x38` and at `+0` the layer `select_cell_layer` finds there
(2 the upper, 1 the lower). `0xf0` adds an angle it shifts up by 4 and `0x400`
at `+0x28`; **`0xf2` adds one more byte**, `+0x3a >> 2`, which comes back as
`(byte << 2) + (rand() >> 13)`, and `0x400` at `+0x24` for type `0x79`. So
**what you drop is saved as a spawn instruction**, and the three kinds are
three flavours of it. `0xf3` is the fourth, and short: the kind `0x70` --
a key on a pedestal -- with only its type and its state.

So the lengths are `0xf0` 9, `0xf1` 8, `0xf2` 9, `0xf3` 3, `0xf4` 3, `0xf5` and
`0xfd` 2, and every other byte one. **`tools/levelstate.py` had `0xf2` and
`0xf3` at 8 and 8**, and held 3 of 3 with them only because neither is in
either recorded stream.

**Checked.** `emu/bp23.lua` logged both ends while the game was played. The
543-byte stream written on level 0 is **byte for byte** the one
`apply_level_state` was handed when the player came back, and it decodes to
34 actors with three gone, six conversations — entity 9 stopped at pc 7 with
the retry flag set, which is exactly where the first conversation recording
left it — and **396 object records ending on the last byte of the stream**.
A second, from level 4, decodes the same way and exercises the three-byte
`0xf4` form seven times. `tools/levelstate.py` holds all three and reports
3 of 3.

That last number is the one that mattered. A lockstep reading out by one
record ends early or runs off the end, and the arm that writes nothing when
the state is below 2 was the part to distrust for exactly that reason — it
never fired in either stream.

**Now both routines are held to the game's own code**, run by
`tools/mipsrun.py`. `level_state_write` over the 21 snapshots of `GAME.EXE`,
and over 63 copies of them whose actors, conversations, object states, kinds,
types, places and the level's own 32 type rows' classes were scrambled from a
fixed seed, builds **84 of 84 streams, 71 718 of 71 718 bytes,** as the model
does -- every arm taken, the class-0x53 one that writes nothing 322 times
among them. And `apply_level_state`, handed those streams, the ones the
memory card's saves keep and the recorded one, over a fresh load of their
level (`mipsrun.level_cpu`), leaves RAM as the model's reader does in **90 of
90**, 51 812 bytes changed and every one the same. A stream a slot short is
the game's: its reader reads on into whatever follows, and so does the model.
`tools/levelstate.py --check`.

The same experiment left two things open, and both are settled now (§15, "On
the card"). It said **`inventory_a` did not appear in the save verbatim, so
the carried items had to be written in some other form. That was wrong**: both
inventory arrays are in the buffer byte for byte at `+0x5508`, which
`save_restore` copies straight back -- 534 566 of 534 566 bytes, run over the
game's own code. And `story_flags` could not be judged from this save, one
non-zero byte in sixty-four making a "match" a match of zeros; the same
check's twenty random buffers judge it, at `+0x8`. The save assembles in a
buffer at `0x801eb9c4` and opens with `SC`, the standard PlayStation save
header.

---

## 12. Every level carries its own code

`FDAT.T` entry `3n + 2` had been filed as "a small pointer block relocated to
`0x801e8xxx`". It is a **code overlay**: past the 32-pointer table the bytes
disassemble cleanly — `03e00008`, `27bdffc8`, prologues, the lot — and the
pointers land exactly on them. The base is `0x801e8308`: bytes at entry offset
132 turn up in a RAM snapshot at `0x801e838c`, and the first pointer
`0x801e83b0` then falls on the prologue at entry offset 168.

Each level has **16 entry points and about 1000 instructions**, and they call
straight into the game's own routines. Across all 28 levels:

| Called | Times |
| --- | --- |
| `announce` | 190 |
| `has_item` | 34 |
| `take_item` | 16 |
| `give_item` | 3 |
| `object_table` referenced | 36 |

**So "which NPC wants which item" was never in a table.** It is per-level native
code, which is why it turned up in neither the entity scripts, nor the menu, nor
the object fields. Reader: `tools/overlay.py`.

What the game asks of the player, read straight off the disc:

| Level | Wants | Takes | Gives |
| --- | --- | --- | --- |
| 0 | 100, 130, 131, 132, 133, 2 | 130, 131, 132, 2 | |
| 1 | | 127 | |
| 2 | 75 | | |
| 3 | 124 | | |
| 4 | 132 | 123 | |
| 5 | 102 | 102 | |
| 6 | 131 | | |
| 7 | | 133 | |
| 8 | 125, 133, 16 | | |
| 9 | 125 | | |
| 17 | 56 | 56 | **57** |
| 20 | 125 | 125, 126 | **16** |
| 23 | | 134 | |
| 27 | 16 | 16 | **17** |

Three of those are trades — level 17 takes item 56 and hands back 57, level 27
takes 16 and hands back 17 — and level 20 both grants 16 and consumes 125 and
126. That is a quest chain, legible without playing a minute of the game.

The item ids are the inventory's own, 0..149; **which item each number is has
not been established**, and pairing them with names is the obvious next job.

### The overlays query objects, they do not place them

The 36 references to `object_table` looked at first like a level placing its own
objects. Counted properly — with stack saves excluded, which is what made the
first count misleading — they are overwhelmingly **reads**: `+0x02` 28 times,
`+0x06` (the type id) 30, `+0x3c` 27, against a handful of writes scattered over
nine fields. And 27 of those accesses sit around one call.

That call is `find_object` at `0x80045c7c`. It takes a starting index in `$a0`,
**bounds it at `0x18c` = 396**, forms `object_table + a0 * 0x44` and scans from
there within limits passed in the other arguments. Its other callers are the
`use_item` branches that ask what the player is facing. So it is a spatial
lookup, and the overlays use it to *find* objects and react to them.

The overlays do also *create* objects, through the stub at `0x8005db30` that
saves its arguments and falls into `spawn_object` — but only **44 times across
the whole game**, and 28 of those are one identical call per level at the head
of its code. That leaves about sixteen level-specific spawns, which is nowhere
near the 346 objects level 0 carries. They are special cases, not the furniture.

Two things follow. The 396-record array size is confirmed from a second,
independent place — the game's own bound check — and the record layout from a
third: `0x800448b8` initialises a record by writing `0x1000` to `+0x2c`, `+0x2e`
and `+0x30`, zeroing `+0x24`, `+0x26`, `+0x28`, and setting `+4` and `+5` to
`0xff`, exactly the scale, rotation and marker fields §5 describes.

And **object placement is still not found**: every hypothesis is eliminated,
the overlays included.

### What a level looks like is not fixed

Reported from play, and it constrains any answer: an NPC can stand in one place
on one visit and elsewhere, or nowhere, on the next. A button can be plugged in
the wall, and after doing something else and re-entering, the plug is out and
lying on the floor beside it.

So the object set is not a static list that gets loaded — it is derived, from
whatever the player has done. That is consistent with everything found so far:
`level_state` is proven save data recording exactly this kind of change (§11),
`apply_level_state` applies it, and the overlays query the result. Whatever
builds the base set has to be looked for as a *function of state*, not as a
table sitting on the disc, which is probably why looking for a table has failed
five times.

---

## 13. Item ids resolve to text

**Item `n`'s description is `ITEM.T[390 + n]`**, its icon `ITEM.T[540 + n]`.

The formula is at `0x80025044`, which adds `0x186`, `0x21c` or `0x2b2` to an
index and loads archive 6. What makes it a fact rather than a guess is that both
ends were already known: item 104 is the Earth Herb, established by watching the
inventory slot change on a pickup, and `ITEM.T[494]` reads *"Recovery Item. This
herb will heal the wounded body."* Item 105 is the Antidote, and `ITEM.T[495]`
is the medicinal herb that removes poison. Three parallel tables of 150 line up
exactly with the inventory's own 0..149.

Reader: `tools/itemtext.py`, and `itemtext.py <n> png` writes the image out to
be read by eye.

This puts words on the quest chain in §12. Every item the level code names,
decoded (a few glyphs still missing, marked `?`):

| Item | What it is |
| --- | --- |
| 16 | *Vallad made this sword with the light magic. The famous holy sword…* |
| 17 | *Vallad made this sword. The spirit of King Alfred added more light…* |
| 56, 57 | *Orlandin made this guard for himself* — the shield, twice over |
| 100 | *the message written by Leon when he realised it would cost him his life* |
| 102 | *the key to the switches found in the maze forest of Varde* |
| 125 | *The holy sword of your father, it was broken years ago* |
| 126 | *Orlandin trapped the fairies sent by the gods to spy on him* |
| **130, 131, 132** | *one of the three seals of Ichrius* — one line each |
| 133 | *This key has three essential parts: the Eye, Wing and Crown of Ichrius* |
| 134 | *The Key for the Door… will unlock the doors which lead to Verdite* |

Which makes the whole spine legible without playing. Level 0 asks for **130,
131 and 132 — the three seals — four times each, and takes all three**: that is
the gate the game is built around. Level 20 takes the broken sword 125 and the
trapped fairies 126 and hands back 16; level 27 takes 16 and hands back 17. A
reforging, twice.

**The font was the unfinished part, and it is now largely done.** These 131
images were never in the corpus the proportional font was grown on. Nine images
read by a human seeded **78 glyphs** — 206 shapes to 284 — and the corpus went
from unreadable to **91 % dictionary words**. `out/propfont_items.pkl` holds the
font; `out/items.txt` holds all 131 descriptions.

The `I`/`l` ambiguity §3 describes is handled the same way here, by dictionary
rather than by font: `itemtext.fix_il` turns *ltem* into *Item* and *lchrius*
into *Ichrius*.

What still falls out is thin: `R` in *Recovery*, an `S` in a kerned *Sword*, a
`t` in *Effect*, and the pair in *Key*. Automatic growing adds nothing —
`propocr.learn` returns zero new glyphs against this corpus — so those want the
same treatment if anyone wants them: one more line read by eye.

---

## 14. How a level changes between visits

Reported from play: an NPC stands somewhere on one visit and elsewhere, or
nowhere, on the next; a plug sits in a wall, and after doing something else and
coming back, the plug is out and lying on the floor beside the opened button.
Here is the machinery.

`apply_level_state` opens by fetching `level_state` for the level being loaded
and, if there is any, **interpreting it as a byte stream**. It is a second
bytecode, built exactly like the entity one: fetch a byte, and anything from
`0xf0` up dispatches through a 16-entry jump table — this one at `0x80013640`.

The stream has three sections, each ending in `0xff`:

| Section | Shape | What it sets |
| --- | --- | --- |
| 1 | `(index, value)` pairs | byte `+9` of a 0x88-stride table at `0x80185da8` |
| 2 | `(index, pc, flag)` triples | an entity's script program counter at `+0x10` and flag at `+0x13` — so entities resume mid-script |
| 3 | one opcode per object slot, 396 of them | the objects |

The third section is the interesting one. It walks the object array slot by
slot — `$s1 += 0x44`, `$s6 += 1`, `while $s6 < 0x18c` — and each opcode says
what becomes of that slot:

| Opcode | Effect |
| --- | --- |
| `0xf0`–`0xf3` | **create an object**: allocate the record through `0x800448b8`, write `0x60`/`0x61`/`0x62`/`0x70` to `+0x04`, then take the type id and the rest from the stream -- a position and an angle, a position, a position and a byte, or only the state (§11) |
| `0xf4` | two bytes into `+0x38`, `+0x39` |
| `0xf5`, `0xfd` | one byte into `+0x39` / `+0x38` |
| `0xff` | **empty the slot** — type id becomes `0xffff` |
| anything else | leave the slot alone |

### Verified against a picked-up herb

The controlled experiment from §11 answers this too. Save, pick up one Earth
Herb, save again:

| | before | after |
| --- | --- | --- |
| `0xff` (empty-slot) opcodes in the stream | 49 | **50** |
| live objects in the table | 346 | **345** |

Exactly one slot emptied, exactly one object gone. Picking something up appends
its slot to this stream, and that is what gets saved.

**So the stream is an override, not the placement.** Level 4 in one snapshot has
200 objects and no `level_state` entry at all, and level 0's stream creates
nothing — it only empties. The base set still comes from somewhere unfound. But
the *changes* the player sees between visits are all here: `0xff` removes what
was taken, `0xf0`–`0xf3` put things where they were not before, and section 2
restarts an entity's script wherever it left off — which is an NPC standing
somewhere else.

---

## 15. The save format, field by field

Two routines face each other and check each other: `save_serialise`
(`0x8005f7bc`, 98 writes into a buffer and no reads) and `save_restore`
(`0x8005ffd0`, which reads the same offsets back into the same globals).
Extracting both and keeping only what they agree on yields **57 fields** — the
agreement is the verification, since an error either way would not line up.

`data/savemap.json` holds them; `tools/savemap.py` prints the layout or reads
the fields out of a snapshot. The first few:

| Save offset | Global |
| --- | --- |
| `+0x56b0` | `player_exp` |
| `+0x56b4` | `player_exp_next` |
| `+0x56b8` | `player_gold` |
| `+0x56c2` | `player_hp_max` |
| `+0x56c4` | `player_hp` |
| `+0x56c6` | `player_mp_max` |
| `+0x56c8` | `player_mp` |
| `+0x5706` | `player_level` |

This settles a loose end from §11, where the player's stats could not be found
in the save as a verbatim copy of the RAM block: they are written **field by
field** at fixed offsets, not copied, which is why searching for the block found
nothing.

It is also worth more than a list of offsets. It answers *which* of the many
unnamed words around the player block are real state — roughly forty of them,
at `0x801b2508`–`0x801b2530`, `0x801b255c`–`0x801b2578` and
`0x801b25ab`–`0x801b25e4`. Anything the game bothers to persist is state;
anything it does not is scratch, and need not be chased.

### On the card: three blocks, and the buffer verbatim

The card layout was "a separate question" here, on the reasoning that a card
block is 8192 bytes and this buffer far larger, so the card must hold a
subset or a packing of it. **It holds neither: a save is three blocks, and the
buffer is in them byte for byte.** `0x8002860c`, which the load screen calls
with the slot picked, opens `bu00:BASLUS-00255` plus the slot's digit
(`0x80011758`, `0x80081818`, `slot + 0x30`), reads **0x6000 bytes**, and
believes them only if `0x80028c74` -- the sum of the 0x5c00 bytes from
`+0x400` -- equals the word at `+0x200`; then `save_restore` is handed
`+0x400`. The writer, `0x80028750`, zeroes the 0x6000 bytes, serialises into
`+0x400`, sums, and lays a 0x280-byte header over the front:

| File offset | What |
| --- | --- |
| `+0x000` | `SC`, `0x13` (an icon of three frames), 3 (blocks), the title in Shift-JIS -- `KING'S FIELD 2-3 EXP 11 LV 1`, the slot, experience and level put in by `0x80028b70` -- then the icon's palette and frames, stored out of VRAM |
| `+0x200` | the sum |
| `+0x204` | the rest of the writer's stack, up to `+0x280`: nothing |
| `+0x400` | the buffer `save_serialise` fills, 0x5ace bytes of it used |

and `save_restore` is 57 fields one at a time and ten blocks copied whole:

| Buffer offset | Bytes | Into |
| --- | --- | --- |
| `+0x0` | 5 | `current_level_block`; its **first** byte is then copied to `current_level` and `0x8018fada`, and is the level loaded |
| `+0x8` | 0x100 | `story_flags` |
| `+0x108` | 0x5000 | `level_state` |
| `+0x5108` | 0x40 | `level_state_index` |
| `+0x5148` | 0x3c0 | `0x80198588`, the table `build_seq_index` fills at boot |
| `+0x5508` | 0x12c | `inventory_a` and `inventory_b`, 150 counts each |
| `+0x5634` | 0x60 | **byte 0 of each of `spell_table`'s 96 records**, 24 bytes apart |
| `+0x5694` | 0x89 | the player: position, pitch and facing, minutes, experience, gold, HP, MP, the stat and the skills, the timers, the level, what is worn and wielded, the spells in hand, the panel's styles -- the fields above |
| `+0x571e` | 0x280 | `0x801b56cc`, **`map_mark_seen`'s bits**: 20 bytes for each of 32 maps, one bit for each of the 160 rectangles of `level_map_rects` |
| `+0x599e` | 0x96 | `0x80081780`, 150 bytes, one an item id, initialised in `GAME.EXE` |
| `+0x5a34` | 0x96 | `0x80080718`, 150 more, the same |
| `+0x5aca` | 4 | `0x8009c22c` |

**Checked** both ways round by running the game's own code over a
snapshot's RAM (`tools/mipsrun.py`). `save_restore` handed the three saves on
the emulator's card and twenty buffers of random bytes -- in which a field put
at the wrong offset cannot hide behind a zero -- writes **534 566 of 534 566**
bytes exactly where and as the table says, and nothing else; `save_serialise`
over the 21 snapshots of `GAME.EXE` builds **494 592 of 494 592** bytes as the
table builds them from the same RAM. And all three saves on the card carry the
game's checksum. `tools/memcard.py` holds the table, reads the card and runs
both checks.

### A correction to the function boundaries

`load_level_payload` was the name given to a function that turns out to end at
`0x8005f7b8`, 220 instructions in — everything past that is the serialiser and
its inverse, which had been swept into the same "1263 instructions". What the
routine actually does is apply the `level_state` stream, so it is now
`apply_level_state`.

---

## 16. What loading a level actually does

`level_load` at `0x80018358`, 578 instructions, in order:

1. **Tear down.** One pass over the 199 entries of the `0x88` table at
   `0x80185da8` and one over all 396 object records, freeing the pointers at
   `+0x34` and `+0x40` through `0x80043894` and stamping each record dead.
2. **Clear the object array.** 396 records, `0xff` into `+0x04` of each.
3. **Read the level off the disc.** `read_archive_entry(4, level*3, …)` and
   `read_archive_entry(4, level*3 + 2, …)` into `fdat_load_buffer`
   (`0x801c17a4`) — archive 4 is FDAT. This is the reader the old "reads no
   archives" claim missed.
4. **Scatter it.** `block_copy` moves 16000 bytes of grid to `0x801d4464` and
   2048 bytes of tile shapes to `0x801e4464`, and the entity records to
   `entity_table`.
5. **Normalise the grid.** A pass over all 6400 cells, ten bytes apart, masking
   bytes `+2` and `+7` to their low two bits.
6. **Apply the saved state**, through `apply_level_state` (§14).

Step 5 settles something §4 had marked unverified: cell byte `+7` is an
orientation in 0..3, because the loader itself masks it to two bits. Byte `+2`
is the same field in the unused second layer.

**And the base object set is still not built by any of this.** Steps 1 and 2
empty the array; step 6 only overrides slots.

The four routines `level_load` calls without naming have since been read, and
none of them is the answer either — but all four are worth having:

| Routine | What it is |
| --- | --- |
| `grid_mark` `0x80033c4c` | world x,z and a radius into a range of cells, indexing the grid as `z*800 + x*10` with 80×80 bounds, adding 4n to each cell's +2 -- the occupancy count. 15 callers. It was named `grid_query_area` and read as "the terrain and collision lookup"; it looks nothing up (section 16, "read whole") |
| `free_object_resource` `0x80043894` | hands a record's `+0x10` to `heap_free` |
| `free_resource` `0x80019518` | the same for other pointers, 10 callers |
| `entity_table_init` `0x80053084` | 29 instructions over `entity_table`, called once |

### The object placement, found at last

Measured properly — with a control in the same run proving the breakpoints were
alive — a level crossing produced exactly three writers of an object's type id:

| `pc` | called from | What |
| --- | --- | --- |
| `0x80018698` | `level_load+0x2a4` | the teardown pass, stamping every slot dead |
| **`0x80044e10`** | **`level_load+0x458`** | **the fill** |
| `0x8005f560` | `apply_level_state+0x11c` | the saved-state override |

The middle one is `load_object_placement` at **`0x80044d9c`**. It walks the
object array and a source array together — `$s0 += 0x44` for the records,
`$s3 += 0x18` for the source — for `0x15d` slots, and for each one:

```
lhu $v1, -8($s3)          a u16 from the source
if it is 0xffff:  sh 0xff, +0x06     the slot stays empty
else:             sh $v1, +0x06      that is the object's type
                  sb 0xff, +0x04
```

So **the placement is an array of 24-byte records, one per slot, up to 350**,
and the type id is a `u16` inside each.

### The level payload is a chain of length-prefixed blocks

Which also explains why the placement was never found by searching. `level_load`
walks its buffer with `lw $v0, ($s2); $s2 += $v0 + 4` — every block is a `u32`
length followed by that many bytes — and hands them out in order: the grid, the
tile shapes, a 200-byte block, the entity records, one to `0x800530f8`, one to
`0x8019175c`, and then the seventh to `load_object_placement`.

Entry `3n + 0` is the first two links of that chain, which is why its header
reads as "`u32` 0x0000FA00, the size of the grid block" — that is the length
prefix, not a constant. Following the chain into entry `3n + 1` finds the rest:

```
3n+1  @0     len 12992   entities and their scripts
      @12996 len  3200
      @16200 len   768   -> 0x8019175c
      @16972 len  8400   <- 350 records of 24: THE PLACEMENT
      @25376 len  2048
      @27428 len   640
```

**8400 is 350 × 24** — the slot count and record size the code had already
given. Identical block sizes on every level.

### The placement record

| Offset | Meaning |
| --- | --- |
| +0 | flags; `0x02` on a placed object |
| +1 | cell Z |
| +2 | cell X |
| +4 | `u16` type id, `0xffff` for an empty slot |
| +6 | `u16` rotation, negated by the loader before it reaches the live record |
| +8 | `u16` fine **Z** inside the cell |
| +10 | `u16` fine **X** |
| +12 | **`s16` height above the terrain** |
| +16 | `u16` that becomes the object's `+0x38` — the sign text index |

**The two fine offsets are the other way round** from how this document and
`tools/placement.py` had them: +8 is the offset along Z and +10 along X.
Reading them the old way put 112 of level 0's 347 objects where the game has
them; swapping puts **345 of 347** there. A player found it by looking — a
healing herb sitting a little to one side — and every object whose offset is
not the middle of its cell was displaced the same way.

**Objects turn about three axes, not one.** The live record carries three
halfwords at `+0x24`, `+0x26` and `+0x28`, and nine of level 0's objects are
tilted about X and three about Z. The negated `u16` at +6 of the disc record
reproduces the live Y for 336 of 347, so the yaw is read. Bytes 18 to 20 of
the record scale by 64 into exactly the right angles for all nine tilted
objects **and into nonsense for the rest**, so that field is conditional -- and
the condition is now read: it is the class, `0x0d` or `0x40`
(`load_object_placement`, read whole, below). With it, all three angles come
off the disc for 347 of 347 objects on level 0 and 200 of 200 on level 4, and
`tools/level3d.py` no longer borrows them. A player found this one: a helmet
standing on end in the port and lying on its side in the game.

**And the three are composed `M = Ry . Rx . Rz`** — a vertex is turned about Z
first, then X, then Y. Read off `0x800166f4`:

```
temp = Rz(angle[+4])       0x80016680 fills the Z matrix
dest = Rx(angle[+0])       0x80016598 fills the X matrix
0x80074628(dest, temp)     stores through $a0:  dest = dest . temp
temp = Ry(angle[+2])       0x8001660c fills the Y matrix
0x80074734(temp, dest)     stores through $a1:  dest = temp . dest
```

Each helper is named by the cells it fills — the X one puts `0x1000` in
`[0][0]` and `cos, -sin, sin, cos` in the lower right — and the two multiplies
are told apart by which argument they store through, which is the only
difference between them. The angle triple is read at +0, +2 and +4 as X, Y and
Z, which is what the live record's `+0x24`, `+0x26` and `+0x28` hold.

The first version of this composed them in the opposite order and said in its
own comment that the order was a choice rather than a reading. It was wrong,
and a player comparing a helmet in the two windows could see it.

**The height is in the record after all.** This document and `BACKLOG.md` both
said it was not, and that an object simply stands on the terrain at
`-128 * cell[+6]`. It does not: the terrain is only where an object with
`h = 0` stands, and the live Y is

```
y = -128 * cell[+6] + s16(record[12])
```

which reproduces the live object table for **345 of level 0's 347 placed
objects**. The two it misses are both type 280, whose records are mostly `0xff`
filler and whose live Y is a round `-12800` -- class `0xe0`, a trigger, whose
arm subtracts the fine offsets back out. With that, 347 of 347.

That single field is what a chest is made of. A chest is not one object but
three placed in the same cell: the body (type 155, 640 tall) at `h = 0`, the
lid (type 154, 320 tall) at `h = -640` — one body-height up, Y pointing down —
and what is in it at `h = -256`. With every object put on the floor, which is
what `tools/level3d.py` did while this was thought not to exist, the lid is
drawn *inside* the body. A player looking at the port reported exactly that:
chests drawn open and closed at the same time.

**Withdrawn: "the lock plate (type 106)".** Type 106 is the herbal liquid, an
item, and it is the chest's contents: the lid (opcode 6) names its slot at
+0x3a and hides it on the first frame (`load_object_placement`, read whole,
below). The "lock plates lying in mid-air with no chest under them" a player
reported were chest contents the port drew and the game keeps hidden.

Checked against a RAM snapshot slot by slot: **350 of 350 type ids match**, and
the block places 347 objects where the snapshot holds 346 — the difference being
the herb the player had picked up. The four readable signs it gives for level 4
are the same four cells the live table gave.

Reader: `tools/placement.py`. **6942 objects across the 28 levels**, and
`tools/readables.py` with no arguments now reads what all **76** signs in the
game say, from the disc, with no emulator involved.

*(Six attempts failed to find this because all six searched for a table. It was
never findable that way: the placement has no signature, no fixed offset from
anything, and sits behind two length prefixes. What found it was asking the
running game who wrote a byte.)*

### `load_object_placement`, read whole

`load_object_placement` (`0x80044d9c`, 843 instructions) was named for two of
its stores and read for none of the rest, so the port borrowed four things from
a level-0 RAM snapshot: the angles, the scale, whether an object is drawn, and
-- through the grid -- the walls of every door. It is transcribed now, in
`tools/objload.py`, and none of the four is borrowed.

It walks the 350 placement records beside 350 `object_table` slots, skips a
type of `0xffff` (or `0x00ff`), and fills every record the same way first:

| Live | From |
| --- | --- |
| `+0x00` | the placement's byte 0 -- 2 on every one of the game's 4838 |
| `+0x03` | `type_row[+3]`, the flags |
| `+0x04` | `0xff`, until the class arm sets an opcode |
| `+0x0c` | `type_row[+8]`, or `type_row[+8] * p[+0x10] >> 7` on flag `0x10` |
| `+0x14`, `+0x1c` | `p[+2] << 11 + s16 p[+0xa]`, `p[+1] << 11 + s16 p[+8]` |
| `+0x18` | `s16 p[+0xc] - (layer height << 7)`, the upper layer unless `+0` is 1 |
| `+0x24..+0x28` | `0`, `-p[+6] & 0xfff`, `0` |
| `+0x2c..+0x30` | `0x1000` each, or **`p[+0x10] << 5` on flag `0x10`** |
| `+0x38..+0x3f` | `p[+0x10..+0x17]`, the parameter block, verbatim |
| `+0x40..+0x43` | `0xff` |

and then switches on `type_row[+0]` through 256 arms at `0x80011c54`. Most
arms only store an opcode, and for most classes the opcode *is* the class. What
the others do is the part the port needed:

* **The angles.** Classes `0x0d`, and `0x40` unless `type_row[+1]` is `0x20`,
  set each of the three angles from `p[+0x12..+0x14] << 6`, leaving any byte of
  `0xff` alone. That is the condition the placement record section above was
  missing.
* **The doors are drawn by the grid.** Classes `0x03`, `0x04`, `0x05`, `0x54`
  and `0x57` zero the scale -- the model is never drawn -- and write the door
  into `level_grid` instead: `stamp_table` (`0x800443c8`) walks 10-byte entries
  in GAME.EXE at `0x8008288c..0x8008297c`, turning each cell offset by the
  object's angle through `game_cos` and `game_sin`, and writes shapes and tiles;
  `stamp_rect` (`0x800445b8`) copies a rectangle of layer-1 cells from
  elsewhere on the grid, turned by a quarter of the angle. The rooms of a level
  that the game never lets you into are the rectangles it copies from.
* **Some arms hide the object** by zeroing its `+0`, which `render_walk` ANDs
  with the cell's view byte: classes `0x0b`, `0x14`, `0x15`, `0x1f`, `0x59`,
  `0x5f`, `0xe0` to `0xe4`, `0xe6`, `0xe7` and `0xea`. Type 299, the readable
  marker, is class `0x14` -- which is why the game never drew it, and why
  `NOT_DRAWN` was right without anyone knowing the reason.
* **Some take themselves away**: `object_set_present(r, 0, type_row[+0x17])`
  in class `0x07` when `type_row[+0xc]` is set and in `0x51`/`0x52` when their
  byte in the block is.
* **Class `0xe0` is a trigger**, and stands at its cell's corner: the fine
  offsets are subtracted back out. That is the two type-280 objects this
  document said "something else positions".
* **200 classes go to the level's own code**, `level_hooks + 0x20`. On level 0
  that is two objects and on level 4 three.

Two more routines in the same neighbourhood were misnamed and are renamed:
`grid_query_area` (`0x80033c4c`) queries nothing -- it is **`grid_mark`**, which
adds 4 to byte `+2` of every cell within `r + 0x800` of a point. Byte `+2` is
the lower layer's rotation in its two low bits and this count above them. Every
object with a `type_row[+4]` marks its cells at load, the player marks its own
with `r = 800`, and creatures mark and unmark as they move. And
`object_flags_for_draw` is **`view_bits_at`**: it reads a 25x25 table of cells
round the camera (`view_table`, `0x801aec84`), whose bytes in every snapshot
are 0, 8, 26 or 30 -- bit 2 is what a placed record's `+0` selects.

**The first frame does more.** Opcode 9 (`0x80048c34`, 18 instructions)
runs once: it takes a slot number from the `u16` at `+0x3a`, zeroes that
object's `+0` and `+0x38`, and sets its own opcode to `0xff`. Every class-9
record in every snapshot is `0xff`, and the objects they name are items, which
from the first frame on are not drawn.

**And a chest hides what is in it.** Opcodes 6 (a lid, 178 in the game) and 7
(the big chest, 37) share a path at `0x80048b38` for a chest whose state is 0
and whose lock byte is not `0xfe` -- one not yet opened: `object_mode`
(`0x80044900`) in mode 0 takes away the slot `+0x3a` names -- `+0` and the
class's state byte zeroed -- mode 3 zeroes its `+0xe`, and the chest's own
state becomes 1. On level 0 that is eleven lids and two big chests, and what
they hide is herbal liquid, a shield, boots, a sword, a key, a gold coin, a
moon stone, a truth glass, a crystal flask and a triple fang.

**Checked** against all 13 snapshots with a level in them, twelve of level 0
and one of level 4:

    angles    4344 of 4352   the 8 are a door and chest lids, opened in play
    scale     4352 of 4352
    position  4352 of 4352
    opcode    4226 of 4226   the hook's objects and the runtime arms left out
    byte +0   4165 of 4226   the 61 are five objects on level 0, the same
                              in every snapshot: three items two cells from
                              where a new game starts, which the player took,
                              by all appearances, and two class-9 objects.
                              This read "18 on level 0 and 1 on level 4, taken
                              in play" until the chests' first frame was read:
                              thirteen of those and the one on level 4 were
                              chest contents
    the grid  exact on 7 of 13, outside the occupancy count; the other six
              are the ones where a door or chest had been opened

And the grid is the part that changes the port most: **every level but 0 was
built with no doors in it**, because the only grid with the stamps was a dump
of level 0. From the disc it differs from the live grid by 32 to 72 bytes;
from the loader, by none.

**And against the game's own loader, on every level.** `tools/mipsrun.py
level_cpu` puts a level into a snapshot's RAM as `level_load` would -- its
grid at `0x801d4464`, its 32 type rows at `0x8019175c`, its overlay at
`0x801e8308`, entry `3n + 1` where `level_load` reads it (`0x801c17a4`) --
and runs `load_object_placement` itself over the placement block. Over all
28 levels: **4836 of 4838** records are the model's, type, opcode, `+0`,
`+1`, `+3`, place, angles, scale, `+0xc` and `+0x38..+0x3f`; the other two
are records the loader hands to the level's own hook (classes `0xa6` on
level 2 and `0xa7` on level 7, which it gives their class as the opcode); and
**0 of 1 792 000** grid bytes differ (`python3 tools/objload.py --check`).
It found one thing wrong: a big chest (class 7) that the loader takes away
puts back the cell's tile from its type row's **`+0xc`** -- the byte it
tests for `0xff` -- not `+0x17`, as the classes `0x51` and `0x52` do. Level
12's slot 273 is one: tile 125, where the model had 0.

### What a watchpoint caught instead: the world shifts

A write watchpoint on the X coordinate of object slot 0, live across a level
change, fired at `0x80017b88`, inside **`world_shift`** (`0x80017aa4`), called
from `level_load+0x1ec`. It adds one vector `(a0, a1, a2)` to everything at
once:

| What it moves | How |
| --- | --- |
| the player | `0x801b25f0`, `+0x25f4`, `+0x25f8` |
| a 127-entry table of `0x4c` | `0x801c80ec` |
| **every object** | 395 records, `+0x14`, `+0x18`, `+0x1c` — skipping any whose type id is `0xff` |
| the `0x88` table | `0x80185da8` |

So crossing between levels does not move the player into a new coordinate
system; it **moves the world under the player**. That is worth having on its
own, and it explains why the four position copies have to be kept in step.

It looked at first as though this narrowed the remaining question sharply — the
loop skips slots whose type id is `0xff`, so the objects would have to be there
by `level_load+0x1ec`, while the array is cleared at `+0xbc`. **That inference
does not hold.** The clear loop writes `0xff` into `+0x04`; `world_shift` tests
`+0x06`. Different fields, so a slot can pass the shift's test on a stale id
left over from the previous level, and nothing about when the fill happens
follows. Withdrawn.

What the window between those points does contain is the shift's own set-up,
and that is worth having: three signed bytes at `0x8018faed`, `0x8018faee` and
`0x8018faef` become the vector, scaled by **2048** for X and Z and **128** for
Y — the same cell size and height unit §4 derives from the grid, arrived at
independently.

*(The watchpoint's own lesson: `0x80017aa4` has no stack prologue, so a
backwards scan for one walks straight past it into the previous function. Two
findings this session were mis-attributed that way before being caught.)*

One more loose thread: `FDAT.T` entry `3n + 1` has a **second** script-like
block at offset 12996, 15676 bytes of it, in the same shape as the entity
scripts but referenced by no record pointer. That is the block an early pass
mistook for the scripts proper. *(Resolved in section 17: the word at 12996 is
the length of the chain's link 1, and what follows it is the actor table and
the links after it, not a script.)*

---

## 17. The creatures: where they stand and when they are drawn

A player killed monsters with `emu/bp19.lua` armed, walked away and came back:
one returned, another never did. This section is the machinery behind that,
read whole out of `GAME.EXE`. `tools/actors.py` is its Python transcription and
`godot/actors.gd` the port's.

### The table comes off the disc

`level_load` reads `FDAT.T` entry `3n + 1` and walks it as a chain of
length-prefixed links, the same chain `tools/placement.py` takes the objects
from:

| link | level 0 | goes to |
| --- | --- | --- |
| 0 | 12992 bytes | `block_copy` into `entity_table` (`0xcb0` words): 40 records of 120 bytes, then their scripts |
| 1 | 3200 bytes | **`actor_table_build`** (`0x800530f8`), 200 records of 16 bytes |
| 2 | 768 bytes | `block_copy` to `0x8019175c` |
| 3 | 8400 bytes | `load_object_placement`, 350 records of 24 bytes |
| 4 | 2048 bytes | `0x80043a08` |
| 5 | 640 bytes | `block_copy` |

and then `apply_level_state` (section 14). `actor_table_build` turns each record
into a 0x88-byte slot of the table at `0x80185da8`:

| disc | slot | what |
| --- | --- | --- |
| +0 | +0 | **category**, the rule below; `0xff` is an empty slot |
| +1 | +2 | kind: the entity record that says what it is |
| +2 | +5 | flags; bit 0 keeps the placed yaw |
| +3 | +7 | home cell z |
| +4 | +8 | home cell x |
| +5 | +0x0a | the **chance** of appearing |
| +6 | +0x0b | copied; nothing below reads it |
| +7 | +6 | which of the cell's two floors: 2 the upper (`cell[+6]`), else the lower (`cell[+1]`) |
| +8 | +0x20 | yaw, stored negated: `-disc & 0xfff` |
| +10 | +0x22 | fine z in the cell (a follower's leader slot instead) |
| +12 | +0x24 | fine x |
| +14 | +0x26 | height above the floor |

It then calls `actor_copy_kind` (`0x8004b624`: model, radius `entity+0x12`,
height `entity+0x14`, flags `entity+0x34`) and `actor_stand_at_home`
(`0x8004b560`): x and z from the home cell and the fine offsets, y from
`collide_at_cell` on the chosen floor, kept only if negative, plus the height —
except that entity flag `0x400` stands it at the floor's base height instead and
flag `0x10` (a follower) adds no height. A follower that is not category 3
becomes category 4.

**Checked:** against the RAM snapshot of level 0, all 58 slots agree in every
field, and the 54 that were not awake stand exactly at the home this computes,
to the unit — heights on sloping cells included, through the ported floor query
in `tools/collision.py`. The one difference is the category of the two men by
the house: 1 on the disc, 8 in memory. No store in `GAME.EXE` writes a literal 8
into an actor, so something computes it; `emu/bp19.lua` now watches both bytes.

Across the 28 levels the disc uses categories 0 and 1 almost everywhere, 2 on
levels 15, 17, 25 and 27, and 3 on level 3. None carries 5 or 8.

### The state machine on `+9`

`actor_tick_driver` (`0x80052e5c`) runs **`actor_activate`** (`0x8004c1f0`) on
slot *k* in the frames where `frame & 3 == k & 3`, so each slot is looked at
once every four frames. It runs it on every slot on every frame while
**`spawn_anywhere`** (`0x801b24f2`) is set or `0x801b25e5` is 1. A level load or
a move sets `spawn_anywhere`, and `game_main` clears it at `0x80014f58`, right
after the actor pass, so it lasts exactly one pass.

Distances go through `in_range` (`0x80016ec8`): a box test, then the library's
inexact `SquareRoot0` of `(dx>>3)² + (dz>>3)²`, shifted back up by three.
Radii are in cells of 2048, from the entity record: **act** `entity+0x0a`,
**deact** `entity+0x0b`. Every kind on level 0 has 16 and 17.

| state | what it is | what moves it |
| --- | --- | --- |
| 0 | dormant | the player comes within `act + 1` cells: see below |
| 1 | **drawn** — `render_walk` draws only this | the player is beyond `deact` cells: back to 0, at home (`0x8004c488`) |
| 2 | held | the player is beyond `deact` cells: back to 0, at home (`0x8004c4f4`); a follower, when its leader is not up (`0x8004c4b8`) |
| 3 | gone | nothing |

A dormant actor inside `act + 1` cells, by category:

```
3, 4   the leader (actor_leader, 0x8018fabc) is up?   spawn
2      chance == 0xff, or rand()>>4 <= chance?        try to spawn
       else stay 0 and roll again next time
       -- the rest check a second, inner radius first --
       nearer than act cells, and not spawn_anywhere? held
1      try to spawn
0      chance == 0, or chance < rand()>>7?            held
       else try to spawn
5, 8, anything else                                  held
```

"Try to spawn" asks `actor_spot_taken` (`0x8004d644`) whether another actor that
is up overlaps the spot, radius on radius and height on height. If one does,
category 2 waits and the rest are held. So on level 0 a monster appears only
in the ring between 16 and 17 cells away, never in front of the player, and
only on the first pass after a load does the inner radius not count. That
explains the short sight range in the port before this: everything was drawn,
where the game draws what woke at the rim.

The **chance** is per actor, not per kind. For category 0 it is out of 256 and
rolled every time the actor could appear, first visit included: `0xff` always,
`0xc0` three times in four, `0x80` one in two. For category 2 it is a roll out
of 2048 on every look, so a category-2 actor appears after a random wait.

**Spawning** is `actor_spawn` (`0x8004b868`) and then `actor_wake`
(`0x8004b698`), which writes the 1 at `0x8004b6b4`. The earlier reading that "a
creature's yaw comes from `+0x20`" holds only when bit 0 of its flags is set:
otherwise `actor_wake` writes `rand() >> 3` over it, so most of level 0's
monsters face a new random direction every time they wake.

### What an awake creature does: its kind's behaviours

`FDAT.T` entry `3n + 1`'s link 0 is `block_copy`'d to `entity_table`: forty
120-byte records -- a creature's **kind** -- and after them, at
`entity_scripts` (`0x8018daa8`), the kinds' **behaviour records**. A kind lists
up to sixteen at +0x38, on the disc as offsets into that area with 0xffffffff
for none; `entity_table_init` (`0x80053084`) walks the kinds to the first whose
+0 is 0xff and makes each offset an address, each 0xffffffff a 0. Level 0 uses
16 kinds; its two monster kinds, models 50 and 51, list the same seven
behaviours, opcodes 6, 0, 5, 1, 4, 2, 3, and the townspeople 0x70, 0, 2, 3.

A behaviour record opens with its opcode -- which arm of `actor_tick` runs it
-- then the animation it starts (+1), a base score (+2), a sound (+4), the
rate of its animation clock (+8) and the opcode's own parameters. An awake
actor holds the running one at +0x60, its opcode at +0xe and a phase at +0xf:
0 just switched in, 0xf0 running, 0xff done. `actor_choose` (`0x8004c01c`),
run for each slot one frame in four by `actor_tick_driver` and again when a
behaviour ends (`actor_finish`, `0x8004c104`), measures the distance to the
player and hands it to `actor_pick` (`0x8004bf1c`), which -- unless the phase
is 0 or 0xf0 -- scores every behaviour of the kind through `actor_behaviour`
(`0x8004b984`, a 133-arm switch on the opcode), keeps the best above -2, and
switches to it through `actor_switch` (`0x8004b94c`) if it is another, or the
running one is done: +0x10 = the old opcode, +0x60 = the record, +0xe its
opcode, +0xf = 0. The animation clock is +0x18, 0 to 0xfff: `actor_clock`
(`0x8004db3c`) adds the rate and keeps its size at +0x66, `actor_clock_passed`
(`0x8004db98`) says whether a time was crossed this frame, and
`actor_start_anim` (`0x8004c130`) sets the animation at +0xc and the clock to 0.

Moving is a velocity at +0x50 and +0x54 eased towards a target, a turn of the
yaw at +0x42, and `actor_move_horizontal`; opcode 5 walks towards the player or
away by a flag at +0x70, which it sets from the distance against the
record's +0x14 and +0x16 -- the monsters that back off in the emulator.

**Checked**: rebuilt from the disc, the kinds and their behaviour area match
**168 896 of 168 896** bytes over 13 snapshots, and **69 of 69** awake actors
run one of their kind's behaviours with its opcode at +0xe (`tools/ai.py`).
`emu/bp16.lua` now logs each awake creature's phase, clock, yaw, velocity,
behaviour and flags, for stepping one frame at a time against the game.

**Which one first.** `actor_wake` leaves +0xe 0, the phase 0xff and +0x60 0;
`actor_activate` then looks through the kind for opcode 0x15, 6 or 0x1a
(`0x8004c068`) and switches it straight in -- the entrance -- and only a kind
with none of them is scored. Level 0's monsters come in on **opcode 6**.

**The scores** (`actor_behaviour`, `R(x) = ((rand() + rand()) * x) >> 15`, 0 to
2x): opcode 0 R(+2) when the player is farther than +0xc (10240 on level 0);
1 between +0x10 and +0x12 (10240 to 30720); 5 nearer than +0x10 (15000) --
doubled straight after a strike -- and, while running, until +0x12 (20000);
4 within +0x1a (3300), the bodies sharing height and the player within
(+0x10) << 4 of the yaw, less a sixth or a third with distance; 6, 2 and 3
nothing; 0x70 -1. The running behaviour scores on its +3. A behaviour runs to
the end of its animation clock -- phase 0xf0 is not interrupted -- and
`actor_finish` chooses again at once.

**What they do** (`actor_tick`'s arms, `tools/ai.py tick`):

```
0    idle     the velocity brakes by twice the kind's +3 along itself
1    wander   walk towards a random aim, a new one on a knock or a roll of +0x14
5    close in walk at the player -- or, flag +0x70, back straight away from it
              without turning: the ones that back off. The flag comes from
              the distance against +0x14 and +0x16 on a roll of 0x1770 in
              0x8000, after a strike, and flips when the step is blocked;
              at a ledge a roll of +0x18 lets it walk over
4    strike   brake; at clock +0x18 the blow (0x8004d254): the player within
              +0xe << 6 of the creature raised +0xf << 5, inside +0x10 << 4
              of its yaw, takes player_take_hit with the record's damage
6    burrow   radius and height from the record; crawl at +0xe on a looping
              clock until the player is within +0xc (16384) at the loop's end,
              then rise over a cycle -- radius and height from the record's
              to the kind's by fixed_madd -- and walk two frames more
```

**How they move.** A velocity at +0x50/+0x54 eases towards the record's speed
along the yaw -- `(-sin, cos) * speed >> 11`, so twice the speed -- by the
kind's +3 along the same line (`0x80015fdc`, per axis); the yaw turns by a rate
+0x58 that gains the kind's +4 a frame up to the record's limit, and lands on
the aim if it passes it (`0x8004e928`). `actor_move_horizontal` then steps: a
ledge more than 0x44c down is refused, a step of at most 0x320 up is taken, a
creature or the player is gone round a quarter turn off at half the step, and
a wall is slid along. `actor_move_vertical` rises onto a floor at -0x64 gaining
5, and falls at the kind's +5.

**Checked against the recording**: every run of one behaviour fully seen in
the log lasts a whole number of its animation cycles -- **31 of 31**, 26 frames
for rate 0xa0, 32 for 0x80, 16 for the strike's 0x100 -- and the commonest
step of a creature closing in is **48** a frame, of one wandering **32**, for
record speeds of 24 and 16. `fixed_madd` (`0x80017158`) is a linear
interpolation, `a + ((b - a) * t >> 12)`, not the multiply-accumulate an
earlier note took it for.

**A blow knocks the player back** (`tools/knock.py`). `actor_blow` hands
`player_take_hit` the record's slash, blow and stab (+0x12, +0x14, +0x16), its
effect (+0x11) and its own point raised by `+0xf << 5`; after the HP,
`apply_damage` (`0x8002a6f4`):

```
share = min((dmg << 12) / hp_max, 0x3b6)          the hit as a part of the HP
push  = direction from the point, its Y + 0x352, to the player  (sub_80016c90:
        yaw vec_angle(dx, dz), pitch -vec_angle(dy, vec_length_2d) & 0xfff)
        * max(share >> 2, 0x50), at most 0x1c2 -- x5 up to 0x258 for effect 0x40
        -- its Y held to +-0xc8
flash = max((0x514 - share / 2) >> 2, 0x46) frames at 0x801b265a, 0xdac at 0x801b2658
HP 0: player_throw(push). No attacker (a fall): the flash alone.
shake = isqrt(share << 2) held to 0x10..0x2a, doubled for 0x40
effect 0x80: (0, +-shake) and player_knock_hard -- state 0x12, a stun
else one of eight by ((yaw - view yaw) + 0x100) >> 9 as (pitch, roll):
        (-s,0) (-s,s) (0,s) (s,s) (s,0) (s,-s) (0,-s) (-s,-s)
        and player_knock (0x80030908): state 0x10, the push into
        player_velocity, the shake into the tilt velocity 0x801b2674,
        vertical state 0x40 with the push's Y
```

In state 0x10 the controller (`0x80031b98`) still turns, looks and walks, then
sets the push's Y to 1 and runs `player_move` (`0x8002f320`): the push whole if
the way is clear; else at the same height, clear, and the push 0x20 shorter for
the next frame; else a step up of at most 0x100 if nothing but `0x205` is in
the way, 0x38 shorter; else nowhere, the push kept. `0x8003047c` drives each of
three tilts (`0x801b2618`, pitch yaw roll) back to 0 with the spring at
`0x80016168` -- within 4 and no faster than 8, snap; else 8 towards it and 4 of
friction -- and when all three are 0, `0x8003078c` ends it: state 0, both
walking speeds 0, the view offsets 0. **The shake decides how long a knock-back
lasts**: 0x10 settles in 4 frames, 0x20 in 16, 0x2a in 28. State 0x12 runs the
spring alone. The view adds the tilts (`0x80032028`): pitch `0x801b2608` =
`player_pitch + tilt.x + 0x801b2620 + 0x801b2628`, yaw + `tilt.y`, roll
`0x801b260c` = `0x801b2614 + tilt.z + ...`, which `camera_pose` hands to
`RotMatrix`.

**Checked against the recording**: every knock-back in `emu/bp16.lua`'s log
that is hit once lasts 28 frames in state 0x10 -- 7 of 7; one hit again before
it settles starts the push and the shake over (`player_knock` again), 2 of 9 -- -- a shake of 0x2a, which any hit of 12 or more on
50 HP reaches. The push is **predicted from the creature**: kind 0's strike
(lift 0x20) at its logged position gives (224, 22, -74), and 22 is the Y the
game put into `player_vvel`; carried through the walk, `player_move` and
`player_vertical`, **83 of 83** frames of the two land where the game put the
player -- one pinned against a wall for fourteen frames and then let go on the
same frame as in the game. The last frame of each needs the end's order: the
walk ran before `0x8003078c` zeroed the speeds. The third, from a session that logged `player_velocity` (`pv=`), climbs a
slope on the push -- the step up of `player_move`, the push 0x38 shorter -- and
then walks backwards on it: `player_horizontal` takes no step up outside player
state 0 (`0x8002e5cc`), so the walk there keeps its height and takes no ramp's
push. 27 of 27 of its frames leave `player_velocity` what the game logged.

**Landing, and falling hard.** A fall (state 0x40) that lands does not wait a
frame: `crouch` (`0x801b2654`) = 1, state 0x50, and on into 0x50's code at once
(`0x8002f068`) -- the crouch takes a quarter of the velocity while positive,
the velocity loses 0x12c, the nod at `0x801b2628` (half the velocity on each
falling frame, added to the view's pitch) gains 0xa or loses 0x1e, and both
spent ends it -- then into state 0's. The recording shows it: 15 -> -285 with a
crouch of 4, 22 -> -278 and 6, state 0 the frame after, 2 of 2. A landing at
0x1e0 or faster first costs `t^3 / 118000` HP, `t = v^2 >> 12` (the multiply by
`0x8e2e0727` at `0x8002ef9c` is that division): 1 at 0x1e0, 25 at 0x300, 142 at
0x400. The eye is `player_y + bob + crouch - 0x640` (`camera_pose`), so the bob
and the crouch both lower it -- the port had the bob raising it.

### The creatures, frame by frame against the recording

`python3 tools/ai.py --locked` takes every creature bp16 logged with the full
`act=` (4932 frames of the newest session), steps it once from what the log
says it was -- position, yaw, velocity, phase, clock, the running record, +0x70
and +0x71 -- and compares the next frame's position, yaw, velocity and clock.
Only frames that keep their behaviour: a switch is a choice, and a choice is
`rand()`. A step that calls `rand()` is tried with every call at 0 and at
0x7fff, both sides of any one test. What the log did not hold is carried from
our own step of the frame before (the vertical state and speed, the aim, +0x72)
or, for the turn rate, taken from the yaw's last step that was not zero --
opcode 5 turns every other frame, as +0x70 toggles. **8539 of 8933** frames
land exactly: idle 3953 of 3967, strike 40 of 42, close-in 3995 of 4026,
burrow 258 of 298, the volley 42 of 42, wander 251 of 558 (its aim, +0x64,
was not logged). bp16 logs the rest from now on -- +0x58, +0x64, +0xd, +0x52,
+0x70, +0x72, +0x1a, +0xc -- and the check uses them when they are there.
**With every field logged, 3939 of 3942 frames are exact**, the flinch (225)
and the dying (336) included -- and, with a longer session on 2026-10-05,
**12 095 of 12 098** on level 0 and **7200 of 7272 on level 4**, whose
creatures the machine had never been held to: the log walks from one level to
the other, and its frames are now checked a level at a time, each with its
own creatures in the slots (261 and 221 behaviour runs, every one a whole
number of cycles). What the first session taught: opcode 6's last
sub-state is `walk_to` the aim with no turn of its own (most 0, turn accel 0,
`0x80052284`) -- a rate it already has still turns it -- not a drive; lower
slots have moved already when a higher one looks at them; and a player by a
swinging door is shoved (`object_interpreter`) after the creatures looked, so
those frames are set apart as the replay sets them.

**Level 4's 72 were one creature at the edge of the log.** bp16 logs the awake
creatures within `0x3000` of the player; all 72 are slot 17, a model-53
creature some 9700 to 10300 east of the player, walking a corridor (cells
(36..41, 25)) that slot 10, another of the kind, shares -- `silv2` has them
5500 apart there -- and slot 10 is beyond the edge and so in no log line. In
56 of them the game's step is what `actor_move_horizontal` does with a thing
in its way (`.L11`): the stride turned a quarter off the bearing to it at half
its length (the logged z steps by 15 where the velocity says 31), or, the way
round blocked as well, no move at all; the model, which does not know of slot
10, walks straight on. `tools/ai.py --locked` sets those apart -- a creature
within its radius, the largest logged and its stride of the edge, whose
move is that half stride or nothing -- and counts the other 16, all of the
same creature in the same stretch, as misses: what such a neighbour changes
besides is the turn and the aim. bp16 now logs `0x5000` round the player.

**The volley, opcode 0x19** (`0x800523f0`), which level 0's kinds 2 and 3 use
and most kinds on the next levels: the clock; fire times at +0x70 from the
record's +0xe, +0x12 apart and back to 0 past +0x10, each running the list at
+0x1a -- `0x8000` restart, `0x8001 n` repeat, `0x8002 n` skip, `0x8003`/`0x8004`
with arguments -- through `actor_animation_effects`; `actor_finish` at 0xfff;
`brake(kind +3, 0xa)`. It is scored (`0x8004bcdc`) when the player is between
+0x14 and +0x16 away and within `+0xd << 4` of its yaw, unless flag 0x100 holds
it back -- a record whose +0xc is 0x27 lifts that. The port had taken it for
the default arm and had no tick for it, so a creature that chose it stood
still for good; both are in now. The effects it launches are the effect
system's (`effect_tick`, 5326 instructions): the spores (0x26) and the bolts
(0x23, 0x24) are in -- "The effect machine, byte for byte", below -- and the
other kinds are not.

### The spores

What level 0's kind-3 creatures (model 57) throw -- `tools/effects.py`,
`godot/effects.gd` -- **checked against `emu/bp26.lua`'s recording**: 118 of 118
frames of the spores from the frame before (life, height, scale, growth, the
one freed on the floor), 118 of 118 strikes on the player hit or miss as the
model says with the scale it hands on, and on 31 of 32 frames that follow a
strike the player has lost 1 HP (the other: the roll resisted). Slot 40's
spore starts at the point bp26 logged, to the unit: its animated vertex 45
at clock 1080, turned by its yaw 0xc00 + 0x800. The collision asks at the
point's y **plus half the height** -- the point is the middle. The port draws
the spore with resident model 0x4c, lit by the level's class 0 (the class the
effect draw uses is not read yet). **This said model 0x40**, which is the
spore's +0xe: `render_walk` puts +0xe in the scratchpad (`0x1f800084`) and
hands `draw_model_plain` `model_table[+3 + 0x28]` (`0x80041794`), and the
spore's +3 is 0x24.

* **Launch.** The volley's list entry (0x2d) goes to `actor_animation_effects`
  as a vertex number: `0x8004ede0` takes that vertex of the creature's
  animated model (`0x8004352c`) turned by its angles, yaw + 0x800. Arm 0x26
  aims at the player's eye (`0x8004f1d0`, `vec_to_angles` to player + 0x640)
  and calls `effect_spawn(rec+0x18, 0x81, 0x26, point, angles)`, then sets
  the grace count +0xb to 0.
* **Setup** (`effect_spawn` arm 0x26, `0x80054338`): `0x80053ba8` -- +8 1,
  +4 0x80, +0xc 0x34, +2 and +3 0x24, +9 5, +0x12 0x1000, the scale 0x400 --
  then +0xe 0x40 (not the model, above), a life +0x10 of 0x32 frames, the
  half-step test +0xd 1, growth +0x44 0x14 frames, and 200 higher.
* **Each frame** (`effect_driver` counts +0x10 down and frees the slot at -1;
  `effect_tick` arm 0x26, `0x80056de8`): while +0x44 lasts, +0x30 and +0x34
  grow 0x96; +0x32 grows 0x96 to 0x1000; it rises 0x28 a frame until the
  life is down to 0x20, then sinks 0x55. As 0x81 it asks `0x80053850`:
  bit 1 of +0 is `sub_8002b114` -- the player within the radius +0x30
  (`0x80016fb4`, a box then a 3D length through the game's root, the
  player's 0x320 and 0x6a4), the damage scaled down to 0x400 at the edge --
  into `player_take_hit` with the record's attacks. Then as 0x84 it moves by
  its velocity through `sub_800566d4` -- tiles only (`sub_80053310`: +0 & 7
  picks 0xa1, 0x31, 0xb1 or 1) -- and is freed if it hits.
* **Poison.** `spell_table` record 0x26 carries no attack at all, only the
  effect 3: `player_take_hit`'s arm for it rolls `(100 * rand()) >> 15`
  against the resistance at `0x801b255a` and on a loss sets `0x801b255c` to
  0x384 (0x2a3 with ring 0x4a, a quarter with 0x53). The controller counts it
  down (`0x80031e78`): every 30th frame a flash (0x960, 60 frames) and
  `0x8002a6a0(-1)`, one HP -- thirty in all, and a throw if it is the last.
  0x384 is itself a multiple of 30, so a spore that strikes every frame,
  setting it back each time, **takes 1 HP every frame** -- which is what the
  recording shows: 50 down to 40 in ten frames.

### The effect machine, byte for byte

`tools/effects.py` now runs `effect_spawn`, `effect_driver` and the arms of
`effect_tick` it has over the 128 slots of 0x4c bytes **where the game keeps
them**, in RAM, so the game's own code can be put beside it a byte at a time:
`tools/mipsrun.py` runs the game's `effect_spawn` and `effect_driver` over
every snapshot of a level, the same scenarios -- bolts at the player from
round about, aimed as a volley aims them and not, spores beside them -- and
after every frame **all 128 slots** must be the machine's. **189 of 189 runs,
5144 of 5144 frames, 4284 of 4284 strikes on the player** handed the same
arguments; the runs met the tiles, the void, objects and the player.
`godot/effects.gd` is the same machine, and the self-test runs it on the same
runs with the world's answers replayed (54 of 54 runs, 1868 of 1868 frames).

**`effect_spawn`** (`0x80053c84`), before its kind's arm: `effect_alloc` the
first free slot from the top -- 0 when none is -- +0 and +1 the flags and the
kind; the 16 bytes at a3, the point, into +0x18; +0xa 3; the eight bytes the
fifth argument points at into +0x38 (velocity, and a fourth halfword), else
0; the three scales 0x1000; +7 0, +6 the first argument, the angles 0, +0x14
0, +5 0, +8 1; the grace count +0xb 8 when the flags have 0x40 and
`player_state` is 1, else 1; +0x12 0, +9 0, +0xc 0xff, the life -1; the
half-step test +0xd when the speed squared is past 0xc5c10; +0xe 0; a kind
past 0x81 frees it again. `effect_alloc` does not clear the slot, so what an
arm leaves unwritten is the slot's last tenant's.

**The walk** (`effect_driver`, `0x8005bc50`) runs slot 0 to 127; a slot made
during it lands in the first free one from the top, so one above the slot
that made it is run in the same frame and one below waits.

**`effect_collide`** (`0x80053310`) asks after the grace count -- each ask
spends one -- `collide_query` at the point's y plus half the height with the
flags +0 & 7 chooses: 1 0xa1 (the tiles, the objects, the player), 2 0x31,
3 0xb1, 4 1 (the tiles); **0 answers 1 and 5..7 answer 4 without asking**.
`effect_move` (`0x800566d4`) adds the velocity, collides, and with +0xd asks
again half a step back; +0xa is then 2 or 1 by the layer the tiles were asked
in, and +0x2c turns by its third argument. `effect_strike` (`0x80053850`):
bit 1 of +0 calls `effect_hurt_player` with the kind's `spell_table` record
-- +6, +8, +0xa, the effect byte +4, +0xc..+0x14 -- bit 2 the creatures
(`0x8004ceac`, not read).

### The bolts: kinds 0x1f, 0x22, 0x23 and 0x24

What level 4's model-53 creatures (kind 1, fourteen of them) throw is 0x23
and 0x24; its model-67 ones (kind 8) and level 12's models 66, 67 and 63
throw 0x22 and 0x1f. A volley record whose +0xc is in 0x1f..0x25 reaches
`actor_animation_effects`' arm for them (`0x8004fc18`), which aims with
`effect_aim` at a speed of 0x12c, the spread 0x400 and one pass, and calls
`effect_spawn(pct, 0x83, kind, point, velocity, the creature's angles)`. The
point is a vertex of the creature's animated model for a plain list entry;
**an `0x8002 x y z` entry** -- the model-66 and -67 creatures' -- is the
offset it carries turned by the creature's own angles (`vec_rotate`, no half
turn), and `0x8004` aims along two vertices (not read further).

* **Setup** (`0x80054be4`, `0x80054c2c`): +8 0 -- **not drawn** -- the life
  0x14 (0x23) or 0x3c (0x24), the angles the creature's, +0xe 0xc0; 0x23 also
  the half-step test.
* **Each frame** (`0x80058f3c`): as 0x81, `effect_strike` with the scale x
  >> 3 -- 0x200 -- edge 0x400; as 0x81 again, `effect_move(0x64, 0xc8)`:
  meeting the tiles, an object or the player, the move is taken back
  (`0x80056800`) and the slot freed; and either way **a puff**, kind 0x6f,
  is made at its point with two fifths of its velocity (`x * 2 / 5` through
  0x66666667) -- `effect_spawn(10, 0, 0x6f, point, v, 0xe10, -0x80, 5, 0x16,
  0, 1, 3)`. The velocity's fourth halfword is whatever the stack held.
* **The record** (`spell_table` 0x23): stab 50 and the fifth magic 40 (45
  for 0x24), and the effect 3 -- **poison**, as a spore's.
* **0x22, a dart** (`0x80054b5c`, tick `0x80058bb4`): drawn -- +8 1, the
  model 0x49 (+3 0x21), +9 5 -- a life of 0x46 and the scale 0x1800, its
  pitch `ratan2(vy, vec_length_2d(vx, vz))` and its yaw `ratan2(vz, vx)`
  less a quarter, all off the velocity. Each frame it strikes within the scale
  >> 4 (0x180) as 0x81, moves as 0x84 -- **the tiles alone** -- is taken back
  and freed when it meets them, and leaves a puff (+9 5, +0xe 0x100). The
  record: blow 50 and the fourth attack 40, the effect 1.
* **0x1f, a bolt that bobs** (`0x80054d50`, tick `0x80058a2c`): the same
  setting up with the model 0x4a (+3 0x22) and +9 0, but its vertical speed
  zeroed and +0x44 1. Each frame +0x46 runs by 10 up or down as +0x44 says,
  the height by +0x46, the direction turning at -0x45 and 0x46; the strike and
  the move as the dart's, but freed where it stands, and a puff (+9 6, +0xe
  0x140). The record: slash 50 and the fourth attack 40, the effect 2.

**A puff** (`0x80055738`, tick `0x8005b45c`): `0x80053be4` -- +8 5, +4 0x80,
+0xc 0x33, +2 and +3 0x16 (model 0x3e), +9 5, +0x12 0x1000 -- the scale 0xe10
shrinking 0x80 a frame (+0x44), a life of 5, +0x46 0, +0xe 0xc0; each frame
the vertical speed by +0x46, the place by the speed, the three scales by
+0x44. No strike, no collision.

**`effect_aim`** (`0x8004f1d0`): `vec_to_angles` from the point to the
target's eye (0x640 above its feet) -- the yaw `vec_angle(dx, dz)`, the pitch
`-vec_angle(dy, vec_length_2d(dx, dz))`; the yaw pulled towards the
creature's own (+0x42) by `angle_lerp` with t = the distance between them
over the spread, at most 0x1000; the pitch by its own distance from the
creature's (+0x40) as t; `direction_from_angles` and `vec_scale` by the
speed. With more than one pass it leads the target by its velocity
(`0x801b2600`). **600 of 600** random cases of the game's own as
`tools/effects.py aim`, once its `vec_length_2d` went through the game's own
root: `tools/movement.py vlen` takes `math.isqrt`, and the game's comes back
one short on a square.

### Shape 255 is the void

The grid's empty cells carry shape 255 in both layers, and every tool here,
and the port, read 255 as "no shape" and answered nothing. **`tile_collision`
reads it like any other**: the level's table of 256 offsets (the tools read
254) gives 255 the last eight bytes of the level's block -- a floor 32000
above the cell's base, so anything in an empty cell is under the floor: mask
4. Nothing walks into one, which is how 8075 of 8078 held; a bolt flies into
one and stops there, which is how the effect machine found it.
`tools/tiles.py` reads all 256 now, and `tools/collision.py`,
`tools/gdcoll.py` and `godot/collision.gd` keep the void shape; the numbers
above are unchanged.

**The creatures are drawn at their kind's scale.** `render_walk` hands
`draw_model_plain` the actor's +0x48, which `actor_copy_kind` fills from the
kind's +0x32: 0x1400 for level 0's kinds 0, 1 and 2, the commonest monsters, a
quarter larger than the port had them; 0x1800 and 0x1c00 for kinds 15 and 14.

### Where a creature may go, and which way it is drawn

**The fences.** `collide_query` (`0x80033f38`) has a flag the player never
passes: with bit 2 set, after the tile collision it looks at the layer
`tile_collision` read -- `collision_cell_layer`, `0x801e6468` -- and if that
layer's byte +4 has 0x40 it writes `0xfffe7960` over the surface and adds 1,
a wall, to the mask (`0x80033f94`). The player asks with 0x31; the creatures
with `collision_layers` (`0x8018faac`), which is 0x93 in eleven snapshots and
3 in two -- bit 2 either way -- from `actor_move_horizontal` and both of
`actor_move_vertical`'s queries. So those layers are walls to the creatures
alone: the invisible bounds that keep each in its own ground. Level 0 has the
bit on 977 of its 6400 cells, always on the second layer (byte 9); **5006 of
5006** distinct creature positions `emu/bp16.lua` logged stand in cells with
no fence at all. `tools/ai.py` (`fenced`, `creature_query`) and `godot/ai.gd`
have it; `coll00.json` carries a fence byte per cell, and the self-test holds
the port to the Python on 600 points around them. The surface query
(`collide_surface`) and the ledge test (`collide_wrapper_actor`) do not look.

**The turn it is drawn with.** `render_walk` (`0x80040c94`) hands
`draw_model_plain` the creature's +0x40, **+0x42 + 0x800** and +0x44, and
`draw_model_plain` builds `Ry Rx Rz` with the game's own `rot_matrix_y` (cos,
-sin / sin, cos) at `0x800166f4`. With that Y matrix a model's (0, 0, -1) goes
to (-sin yaw, cos yaw) under yaw + 0x800 -- the way `facing_vector` walks it --
so a model's front is its -z and the half turn is what faces it forward.
Flipping Y and Z into Godot's axes turns `Ry(a)` into a turn of `a` about up,
so the port draws a creature at yaw + 0x800; it had left the half turn out and
every creature walked and struck backwards. A kind with flag 0x20 (+0x28) is
drawn with no turn (`0x80040c34`).

### A creature's animation

`tools/anim.py`, and `godot/anim.gd` for the port. The creatures have no
skeletons: `draw_model_plain` hands `0x800431e8` the model, the animation
byte +0xc (+0xd is the vertical state; 0x80 and up draws the model still), the
clock +0x18 and the vertex count of the model's first TMD object, and gets
that object's vertices for the frame.

An MO.T entry keeps, after the TMD's own offset at +8, the number of
animations at +4, a pose table at +0xc and an animation table at +0x10,
offsets from the entry's start. An animation is `u16 n, u16 0` and n offsets
to segments -- `u16 reverse, u16 length, u16 target pose, u16 count, count u16
start poses` -- and a pose is `s16 n` and n entries, an absolute `(x, y, z)`
for the next vertex or `0x8000, k` to leave the next k alone.

`0x80042cac` adds the segments' lengths until the clock falls inside one; the
factor is `((clock - start) << 12) / length`, `0x1000 -` it for a reversed
segment, 0x1000 past the end. The segment's start is the model's vertices with
its start poses written over them (`0x80042d70`, then `0x80042e34`) -- kept in
the actor's cache (the handle at +0x5c: +4 the animation, +6 the segment, +8
the target, +0xc the vertices) -- and `0x80042eb0` moves every vertex the
target pose names by `((target - v) * t) >> 12`, three at a time through
`ScaleMatrix`. Model 50's first animation is six segments of 0x2aa -- one turn
of the clock -- from its own vertices to pose 12, on to 13, back to 12 and
back again.

**Checked against the snapshots**: all 11 awake creatures with a cache hold
the segment and the start vertices this builds from their animation and
clock, and in 3 snapshots the scratch buffer at `0x801acb98` -- the last
creature drawn -- is the blend exactly, at the clock or one step before (the
snapshot fell between `actor_tick` and the draw). The port matches every
imported vertex back to its model vertex by position -- 70 167 of 70 167 on
level 0; the models put no two vertices in one place but for a pair in model
32 -- and moves them when the animation or the clock changes; the self-test
holds it to the Python on 288 frames. The normals stay: the game's poses move
only positions.

### The weapon in the hand

`draw_held_item` (`0x8003df50`) returns while the swing clock (`0x801b25a4`)
is -1, so the weapon is seen only in a swing. It draws `model_table[0x20]`,
which `sub_8002bdc0` fills when a weapon is equipped from **FDAT.T entry
0x62 + the weapon** (archive 4, `read_entry_b`) -- the MO.T wrapper again,
a hand and the weapon: weapon 0 is 441 vertices with one animation of eight
segments of 0x200, the whole clock. It is drawn straight into the camera's
space, with no view matrix: `RotMatrix` of the weapon record's +0x3c and its
+0x34..+0x38 as the translation -- (204, 130, 202) for the dagger, low and to
the right -- lit by the player's cell's class, and animated by
`model_animate` with the swing's phase (`0x801b25ae`) and clock. The port's
`godot/held.gd` does the same under the camera (`Rx(a) Ry(-b) Rz(-c)` once Y and
Z are flipped), with the level's class 0 baked in for now; the VRAM the port
builds holds the weapon's pages as the snapshot has them (0xd and 0xe exactly).

### The player's blow

`tools/weapon.py`, and `godot/weapon.gd` for the port. `player_turn` starts a
swing on the attack button's edge once the pause after the last blow
(`0x801b24f3`) is over (`0x8002c040`, phase 0): the clock `0x801b25a4` at 0 --
it is -1 between swings -- the hit time `0x801b25a6` at the weapon record's
+0x1e, the sound time `0x801b25a8` at +0x2c, the meter kept in `0x801b2504` as
**the blow's strength** and emptied. `held_item_tick` (`0x8002d2a0`), last in
the controller, adds +0x1c to the clock a frame; the frame it crosses the hit
time the blow falls -- a pause of 10, the meter 0 -- and at 0x1000 the swing is
over. Between swings, with the button up, the meter refills after the pause at
`2 * min((stat << 6) / (+1 + 1) + 1, 5000)` a frame (`0x80029390`). The
dagger a new character holds (weapon 0): +0x1c 0x180, the blow on the 8th
frame of 11, refill 11 -- 214 a frame, 24 frames from empty.

The blow walks a quarter of `(0, 0, +0x1a)` turned by `vec_rotate`
(`Ry(facing) Rx(-pitch) Rz(0)`, each product through the GTE's `>> 12`; the Y
scaled by `(0xe10 - reach) / 1800`) four times from 0x320 above the feet, and
asks `actor_spot_taken` at radius 0x190 and height 0x258 with nothing let
through. The first creature is struck if the view's yaw is within its kind's
+0x16 of the bearing (250 for level 0's monsters, about 22 degrees) and its
own yaw within +0x18 of the bearing back (4096, always, on level 0).

`actor_take_hit` (`0x8004c668`) takes the eight offense ratings against the
kind's eight defences (+0x20..+0x2e) through `0x8004c5ec` --
`max(0, A - D) + A*A / (2D)` with `A = (attack + stat) * 16` for a non-zero
attack and `D = defence * 16` -- sums them to at most 0x68db7 and makes
`((sum * strength / 5000) + 0x80) >> 4` of it (the multiply by `0x68db8bad`
and the shift by 11 are the division by 5000). The dagger at a full meter does
67 to a kind-0 creature's 200 HP; at half, 37. The level's hook at
`level_hooks+0x48` may change it -- level 0's zeroes the damage to actor slot
0x20 (kind 13) unless it kills. A blow of strength 2500 or more on a creature
with HP counts towards the stat, one in a hundred (`0x8002a074`). Then the HP
at +0x1a, which `actor_copy_kind` fills from the kind's +0x1a at waking (**69
of 69** awake creatures in 13 snapshots carry it):

* **at 0 or below**, `award_exp(kind+0x1e)` if it had any, and the kind's
  opcode-3 behaviour: dying (`0x800505a4`) runs its clock -- gold and an item
  drop at 0x800, not in the port -- then counts +0x70 from 0xf to 0x26 while it
  fades, and goes where its category sends it, as the death branch does;
* **else** the first of the kind's opcode-2 behaviours whose +0xc the damage
  reaches and whose chance +2 the roll `rand() >> 7` is under (0xff: always) --
  a **flinch** (`0x80050400`): the clock, and +0x70 from 0 through 3, tinted
  up to the clock's half and down to its end, then `actor_finish`.

Either way a kind lighter than 0xf0 (+2) is pushed away from the player's
point 0x3e8 above the feet: `isqrt(isqrt(dmg << 11)) << 10`, over the weight,
`<< 5`, over the weight again, at most 0x200, X and Z `>> 3`, Y `>> 6`, and
the creature goes into vertical state 0x10 -- a hop, which the shared tail's
`brake(accel << 1, 0xa)` carries while it is off the ground.

**Checked against the recording** `emu/bp25.lua` made -- swings at the air and
at creatures from the front and the side: **817 of 817** frames of the weapon
come out of the frame before (the clock, the meter, the pause, the hit and
sound times, the strength); **11 of 11** blows leave the HP, the flinch or not
(kind 1's opcode-2 record: 65 or more, always), the push and the vertical
state the model gives, at strengths from 214 to 5000 -- 10, 13, 28, 53 and 67
of damage; the probe from where the player stood reaches the creature on all
11; both kills give 11 experience. Two frames first came out wrong and named
the missing piece: **the USE button held** (`player_turn`, `0x80030010`) --
both meters 500 down a frame, their pauses 1 (60 when one empties), and
`damage_scale` (`0x801b24f8`, the K by which `damage_of_type` scales the
stat's share of the defence) 0x80 down to 0x400; let go, the magic meter
refills after its pause by `meter_gain(the five working skills' average, 0)`
and K climbs back to 0x1000. A new character's skills are [0, 0, 0, 0, 10]
(`new_character`: the table's +6, zero, and 10 more on the fifth), as every
snapshot has them. The self-test holds `weapon.gd` to the Python on 2336
cases.

### A creature takes a hit: actor_take_hit whole

`actor_take_hit` (`0x8004c668`) takes (slot, the striker's stat, eight
attacks, strength, flags, the striker's spell record, the point). The blow's
path (flags 0x50) is above; all of it (`tools/hit.py`):

```
nothing for models (+1) 0x6e, 1, 2, 0x1d, 0x16; a part (+0 3) passes the
  hit to the actor its +0x22 names
dying (op 3, +0x18 at 0x60c or past) or op 0x1a: nothing; op 0x15: +0x70
  to 2 if 0, nothing more; op 6: +0x70 to 2 if 0
flags & 0xc0 0x80 (a creature's) against +0x28 bit 0x100000: nothing
damage: creature_type_damage x 8 against the kind's +0x20.., summed to
  0x68db7 at most, * strength / 5000, + 0x80, >> 4; the level's hook
  (level_hooks + 0x48) may change it; 0 is nothing
HP left and flags 0x40 (the player's): 0x20 skill_practice(the record),
  0x10 at strength 2500 or more strong_blow
a blow (0x10) on op 0x13 with +0x70 0x10: no HP lost
a spell (0x20): +0x28 bit 0x40000 is immune; a kind with a behaviour 0x16
  whose yaw faces the point within 0x200 switches to it and loses no HP
the player's blow: weapon 0x1f rolls 0x80030c4c(rand * 9 >> 15 + 1);
  weapon 0x20 takes all the HP of models 0x3b-0x3d, 0x3f, 0x42, 0x43,
  0x4f, 0x58, 0x59, 0x5b
HP left <= 0: award_exp(kind +0x1e) for the player's hit (flags & 0xc0
  exactly 0x40) on a creature that had HP; kill_flag and kill_count (story
  flags 0x79, 0x7a) for a model under 0x2b; opcode 3; HP 0
else: the first of its sixteen behaviours of op 2 whose +0xc the damage
  reaches and whose chance (+2: 0xff always, else rand >> 7 under it) comes
  up; one it does not reach sets +0x28 bit 0x200000 and +0x84 0
the push (tools/weapon.py knock) unless the kind's weight is 0xf0 or more
  -- a follower's handed to its leader, opcode 2 unless dying -- and +0xd
  0x10
```

**Against the game's own**, run over every snapshot's creatures with random
hits on every flag path (a behaviour 0x16 laid into some kinds, which no
snapshot's have), only the leaves stood in for: **1260 of 1260**, all 200
actors' bytes and every call out. The port's blow went without the kill
flags; `actors.gd take_hit_flags` is the whole routine now and the blow
goes through it: 400 of 400 in the self-test, the weapon's 2336 unchanged.

**`actor_attack_player`** (`0x800533e8`) is what an effect's hit is handed
to: code 0x80 the player (`player_take_hit`, the record's attacks and
effect, the strength as its scale); 0x10 the creature at `0x801e648c` --
nothing when the point is outside its back arc (`facing_test` against the
kind's `+0x18`), else the record's eight attacks at the caster's strength
(`sub_80053624`) into `actor_take_hit` with flags `+0 & 0xc0` and 0x20 (0x10
for code bit 0x20000), and code bit 0x10000 sets its `+0x28` bit 0x800. A
code with other bits -- a creature and a wall met at once -- does nothing.
**The fire ball end to end**, the game's own `collide_query`,
`actor_attack_player` and `actor_take_hit` over the snapshots, the balls sent
at their creatures: **84 of 84 runs, 988 of 988 frames**, all 128 slots and
all 200 creatures alike, 15 frames a creature struck, 11 killed
(`tools/effects.py fire_hit_check`). In the port a fire ball now hurts,
flinches and kills, practises the caster's fire and gives the experience.

### Stone and wind cutter

Two more of the attacking spells' effects, each held to the game's own code
end to end the way the fire ball is -- `collide_query`, `actor_attack_player`
and `actor_take_hit` the game's, the stones and cutters sent at the
snapshots' creatures at their arms' speeds (`tools/effects.py
spell_hit_check`):

```
stone (6)        model 0xf (model_table 0x37), +0xe 0x40, life 0x46, its
                 sound 0x32. Flying (+0x44 0) it spins its pitch 0xc8 a
                 frame, effect_move at 0x1f4 / 0x1f4 turning 0xfa; the first
                 hit strikes (sub_800537e8), steps it back and drops it from
                 vy -0x64, falling 0xd a frame (+0x44 1); the next hit
                 strikes again and it lies (+0x44 2): +9 5, +0xc 0x32, its
                 +0x12 from 0x400 up 0x100 a frame, gone at 0x1000. A splash
                 a frame in the water (sub_80056268: one kind 0x70 within
                 0x1f4 under the surface).                 63 of 63 runs
wind cutter (0xd) effect_setup(0xd, 0x1400, 5), its sound 0x2b, life 0x2d,
                 the view's yaw, scale 0x1800 / 0x1000 / 0x2000; flat
                 through effect_move at 0xb4 and the height's top bit, its
                 yaw turning 0x2bc a frame; each thing it passes it strikes
                 once -- +0x44 latches, a clear frame unlatches -- and the
                 tiles (any of the hit's low four bits) end it.  63 of 63
```

In the port both fly, hit and splash as the game's (`effects.gd`), 150 of
150 runs of the machine in the self-test.

### Haze, shudom, walwind, and the strike on the creatures

Three more, two of which leave children behind, and the children strike an
area rather than what they meet -- `effect_strike`'s creature half,
`0x8004ceac`, which no effect before had used:

```
haze (0xb)       particle(0x16, 0x1000, 5), +0xe 0xc0, life 0x46; its sound
                 0x94 only when its second argument is 3. effect_move at
                 0xb4 with no height and no turn; each thing it meets it
                 strikes once (sub_800537e8, +0x44 the latch a clear frame
                 lifts), and the tiles end it. No splash.
shudom (9)       model 0x33, +9 5, scale 0x4b0, the view's yaw (the eight
                 bytes args[1] points at, pitch and roll then zeroed),
                 level (+0x3a 0), life 0x96, its sound 0x92, +0x46 the
                 view's yaw again. effect_move at 0xfa and the height's top
                 bit; it strikes nothing itself, the tiles end it; when its
                 count (+0x44, 0 its first frame) is 12, 18, 24 ... -- the
                 game asks 11 or more and a multiple of 6 -- a ring (0x5e)
                 at its point with +0x46 as the ring's yaw.
  ring (0x5e)    model 0x1e, +9 0, life 0x1e, its sound 0x26, scale 0xa
                 growing 0xc0 a frame in x and z; from 0x300 it strikes the
                 creatures from its point 0x3e8 lower, between 15/16 and 9/8
                 of its scale, mode 0x8002; past 0xc80 gone -- 17 frames.
walwind (0x11)   shudom's but model 0x32, scale 0xbb8, sound 0x98; it
                 strikes what it meets every frame (no latch); at counts
                 20, 30, 40 ... (16 or more, a multiple of 10) a wave
                 (0x59) at its point, falling
                 at 0x54 a frame (the velocity's fourth halfword the
                 stack's).
  wave (0x59)    model 0x1f, +9 5, a grace of 5, life 0x50, scale 0x28 x
                 0x7d0 x 0x28, turning 0x140 a frame. Falling (+0x44 0)
                 through effect_move at 0xb4 until the tiles stop it (its
                 sound 0x27), up 0xa0 once (1), then growing 0x280 a frame
                 (2): from 0x300 it strikes the creatures between 29/32 and
                 35/32 of it, mode 0x800; past 0x36b0 gone.
```

**The wave's last strike is nobody's.** The arm frees the slot (`+0 0xff`)
*before* it strikes in that frame, and `effect_strike` reads its bits from
`+0`: bit 1 strikes **the player** (`effect_hurt_player` mode 0x800, the
player between 29/32 and 35/32 of 0x3728 -- 12796 to 15443 -- from the
wave's middle, heights overlapping), bit 2 the creatures with flags `0xff &
0xc0 | 0x20` = 0xe0, which practises the caster's skills but, not being
exactly 0x40, gives **no experience for a kill**.

**The strike on the creatures** (`0x8004ceac`, from `effect_strike` when `+0`
has bit 2): (point, near, radius, mode, edge, the caster's strength, the
record's eight attacks, scale, flags `+0 & 0xc0 | 0x20`, the record). Every
creature awake (`+9` 1) but the one acting, by its distance from the point:

```
0x8000   in_range_3d(point, radius, its place, its radius +0x1c, height +0x1e)
0x8001   the same, a point above its top (y less its height) missing
0x8002   the same, and missing when ratan2(dz, dx) lies within 0x40 of both
         the point's fourth word + 0x400 and - 0x400 -- 0x800 apart, so never
other    in_range(its place, the point, radius, its height, the mode as the
         asker's height): a flat ring with the heights overlapping
```

not nearer than `near` (FAR, -0x98967f, always is), then `actor_take_hit`
with the scale falling to `edge`/0x1000 at the rim exactly as
`effect_hurt_player`'s (`scale & 0x7fff`, the quotient's low half) and the
point -- none when the scale has bit 0x8000. `effect_hurt_player` takes the
same modes for the player: 0x8001 a point above the player's top (y less
0x6a4) missing, any other mode `sub_8002b8d8` -- `in_range` from the
player, height 0x6a4.

**Against the game's own**, sent at the snapshots' creatures at their arms'
speeds with the game's `collide_query`, `actor_attack_player`, `actor_take_hit`
and `effect_hurt_player`, all 128 slots and all 200 creatures every frame
(`tools/effects.py spell_hit_check`): haze **126 of 126** runs, 4098
frames, 8 with a creature struck; shudom **126 of 126**, 6582 frames, 111
struck, 39 killed; walwind **126 of 126**, 7939 frames, 425 struck, 76
killed and **the player struck 40 times** -- each a wave's last frame, the
only strike of these with bit 1 in `+0`. The port has all five
(`effects.gd`), and the strike as `actors.gd strike_area`: 400 of 400
cases of `strike_creatures` in the self-test, every mode, every creature
after; the machine's runs 222 of 222.

### The player's death

`apply_damage` that leaves no HP calls `player_throw` (`0x80030a6c`) with the
blow's push: player state 0x11, the push as the velocity, the view's pitch
tilt still, the count at `0x801b261e` from 0. The controller's arm for 0x11
(`0x80031c54`) runs no turn, walk or height: the HP held at 0, the pitch tilt
sprung to -0x400 by `spring_to` with 8 and 4 and moved by half again of its
velocity -- the player ends on their back, looking up -- the head bob
(`0x801b2650`) sinking the eye 0x1f4 a frame to 0x5dc, 100 above the feet,
and the throw through `player_move` with its own gravity. From frame 0x20
the screen fades over 0x20 frames (`0x8003d624`); at 0x41 every effect slot
is cleared and `has_item(107)` decides: the crystal is taken and the player
put back on level 0 at (0x1c800, -0x3a80, 0xc000) facing 0x2d5 with the HP
and MP full (`0x8002b3a8`), or a new character is made (`new_character`) and
the story flags cleared; `level_state_writer(0, 0, 0)` loads level 0 either
way. **bp20's recording shows the order**: the killing hit's `HURT out hp=0`,
then `has_item(107)`, then the level load's states. The port does all of it
(`godot/player.gd` `_dying`) but the crystal's branch, since it keeps no
inventory for the player yet.

### What a death does, and what is remembered

The death branch of `actor_tick`, at `0x80052b7c`, also goes by category:

| category | state after death |
| --- | --- |
| 1 | 3, through `actor_retire` (`0x8004b770`) — gone |
| 2 | 0 (`0x80052ba8`) — may wake again at once |
| 5 | the slot is freed, `+0 = 0xff` (`0x80052bb8`) |
| anything else, 0 included | 2 (`0x80052bc4`) — held until the player leaves |

and all but category 5 are stood back at home. When a level is left,
`level_state_write` (`0x8005efd4`) writes, for **every category-1 actor and no
other**, its slot and 3 or 0 into `level_state`, and `apply_level_state` writes
them back into `+9` on the next load (section 14, the stream's first section).
So a category-1 monster that dies stays dead, across visits and in the save.
A category-0 monster is rebuilt from the disc on the next visit. Within one
visit it comes back once the player has been more than 17 cells away and
returns to the rim, if its chance allows.

### Checked against play

The second `bp19` run logged 79 transitions, every one at an address this
reading predicts:

| transition | times | where |
| --- | --- | --- |
| 0 → 1 | 36 | `actor_wake` |
| 1 → 0 | 30 | `actor_activate`, beyond `deact` |
| 0 → 2 | 6 | `actor_activate`, held |
| 2 → 0 | 5 | `actor_activate`, beyond `deact` |
| 1 → 2 | 1 | `actor_tick`, a death |
| 1 → 3 | 1 | `actor_retire`, a death |

* **The one that came back** is slot 3, model 51, category 0, chance `0xff`:
  killed at frame 730 (1 → 2), released at 980 when the player was 17 cells
  off (2 → 0, standing at home again), woken at 1264 when the player came back
  to the rim.
* **The one that never did** is slot 5, model 51, **category 1**: 1 → 3 at
  frame 928. Same model, different placement: whether a monster returns is a
  byte of its record, not a property of its kind.
* The two men by the house, category 8 in that session, went 0 → 2 and back
  as the player came and went, never 1, as category 8 must.
* The first pass after the load woke slots 0, 3 and 4. `tools/actors.py 0 --at
  62 8` agrees for 0 and 3, and slot 4 sits right on the 17-cell rim, reached
  from half of the player's cell.
* No `ROLL` line appeared, and that was the script's fault: it watched the
  category-2 roll at `0x8004c304`, and level 0 has no category 2. The
  category-0 roll is at `0x8004c370`, and `bp19` now watches that as well.

### In the port

`tools/level3d.py` writes the creatures as one glTF node per slot, `a<slot>`,
standing at home, with `actors<lv>.json` beside it. `godot/actors.gd` runs the
machine above on the same 30 Hz clock as `player.gd`, so what is drawn is what
the game would draw. V shows every actor instead. X kills the nearest awake
one under the death rule, so the rules can be tried without combat, and a
static keeps category-1 deaths when the world is loaded again.

**The AI is ported** for the opcodes level 0's monsters use -- 0, 1, 4, 5 and
6 (`godot/ai.gd`, run from `actors.gd`'s pass: activation, then choosing on
the awake count's frame, then the tick), so they rise out of the ground, close
in, strike, back off and wander as in the emulator; the self-test holds
`ai.gd` to `tools/ai.py` on 480 of 480 frames of one creature with the same
seed. A blow's reach and arc are tested; what it does to the player is the
next thing. Not ported: the hit and death arms (2, 3), the level's own
opcodes, followers and riders; the cell marks through `grid_mark`; where followers and object riders stand; the model
110 rule in `actor_tick_driver`; `0x801b25e5`; and the game's `rand` seed. The
port also uses the disc's category for the two men by the house, so it shows
the man at (57,3), whom that session held. The one at (62,4) is held by
`actor_spot_taken` in the port, because the man at the table stands on the
same spot.

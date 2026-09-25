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
| `0x30` | `0x80032f78` | ramp |
| `0x31` | `0x800338c4` | runs only when the mask already has bit 0 — not transcribed |
| `0x32` | `0x80033460` | diagonal ramp |
| `0x33` `0x34` | `0x800331b0` `0x80033308` | corners, inner and outer |
| `0x35` | `0x80033604` | not transcribed |
| `0x40` | `0x800339a8` | switches to the cell's other layer and **restarts the shape** |

Counted across every shape program in the game, the opcodes in use are exactly
these eighteen minus `0x40`: `0x10` 1866, `0x11` 1325, `0x17` 13, `0x18` 42,
`0x19` 143, `0x20` 2127, `0x21` 89, `0x22` 419, `0x23` 83, `0x24` 88,
**`0x25` 207 on all 28 levels**, `0x30` 616, `0x31` 11, `0x32` 34, `0x33` 39,
`0x34` 26, `0x35` 4. So **no shape in the game uses an opcode with no handler** —
the 31 empty arms are unused values, not a gap.

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

and `level_load` calls `vram_stream(3, level)` — archive 3 is `RTIM.T` — so a
level's VRAM is entry 96 from game start with the level's own blocks on top.
`tools/rtim.py`'s `level_vram` builds exactly that, and against the 12
snapshots with a level loaded it matches **2 865 923 of 2 998 544** halfwords
the two streams write, and **776 955 of 782 320** on the object pages. What is
left is animation and the interface: entry 96 writes seven frames of a water
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

There is a third case, not in the port: while the counter at `0x801b2566` is
running, `0x80031254` halves the cap every frame and `0x8003125c` counts it
down. What starts it is not read yet.

The order the four run in is off `player_controller`'s own call list —
`player_turn` (the button edges), `player_look` (the turn and the pitch),
`player_walk` (the speeds), then `player_vertical` or `player_move`. So the
facing a step uses is *this* frame's turn, which is what the port now does.

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
| 6 | `ai_driver` | `0x8005bc50` — 128 behaviour slots, each into `actor_ai` |
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
`0x80195ff0`, inside `object_table` — and not an item id, and
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
so calling 4 "wind" would be wrong in the obvious direction.

Six of the 31 have no name, at 3, 10, 14, 18, 22 and 24 — the end of each group,
so the elements have room for more spells than the game ships with.

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
the other four are not. Whatever sets that one — `sub_8002a10c` and `use_item`
both write it — the consequence is that **the game has five skills and only ever
grows one of them** — and since a skill that never grows never crosses a
threshold, four fifths of the spell list is unreachable by levelling.

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

It is given **nine attack values, one per damage type** — slash, blow, stab,
dark, holy, fire, earth, wind, water, the same nine the player's block carries
as ratings — in `a0`..`a3` and `arg4`..`arg8`. Each goes through
`damage_of_type` (`0x8002a5f8`) against the matching defence:

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

The nine are summed and scaled twice, and both scales are read off the call
site at `0x8004d358` rather than guessed — `0x1000` into `sp+0x24`, `0xa` into
`sp+0x28`, and `sp+0x10` through `sp+0x20`, the other five damage types, all
zero:

```
base = sum of the nine
s1   = (0x1000 * base + 0x8000) >> 16      = base / 16, rounded
dmg  = (0xa * s1) / 10                     = s1
player_hp -= dmg                            apply_damage, 0x8002a6f4
```

**Checked against the game.** In the recorded session a creature hit a fresh
character with `(slash 0, blow 40, stab 30)` three separate times and the log
shows 50 → 36 → 22 → 8, fourteen each time. Against that character's own
defence — slash 13, blow 6, stab 4, out of `out/snap/b.ram` — the model gives
143 for the blow, 79 for the stab, 222 for the sum and **14** for the damage.
`tools/damage.py` reproduces **6 of 6** recorded hits exactly, and the seventh —
the one that killed the player — comes out at 59 against 33 HP. `godot/damage.gd`
is the same formula and `selftest.gd` holds the two together on the same six.

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
  gives for offence one slot low. Untested: no snapshot we hold has a character
  with any magic rating at all (*unverified*).

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

So **the text an object shows is `ITEM.T[150 + u16 at +0x38]`**, and the only
condition is geometric: you have to be facing it. 150 is exactly where the
signs and nameplates begin in our index of `ITEM.T`, which is the corroboration
— the offset was not chosen to fit, it fell out of the code.

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

**One: the actors that are gone.** Walk `actor_table`, 0x88 a slot, stopping
at the first byte-0 of `0xff`. For each slot whose byte 0 is **1** — category
1, and no other category — write the slot index and then `3` if the actor's
`+9` is `3`, otherwise `0`. Terminate with `0xff`. So a category-1 death is
kept and nothing else's is.

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
`x >> 2` and `x >> 10`), `y` as two bytes unshifted, and for `0xf0` an angle
that it shifts up by 4. So **what you drop is saved as a spawn instruction**,
and the three kinds are three flavours of it.

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
never fired in either stream, so it remains unexercised rather than wrong.

Two things the same experiment shows are *not* settled. `inventory_a` does not
appear in the save verbatim, so the carried items are written in some other
form. And `story_flags` cannot be judged from this save at all: one non-zero
byte in sixty-four means a "match" is a match of zeros, which is no evidence.
The save also assembles in a buffer at `0x801eb9c4` and opens with `SC`, the
standard PlayStation save header.

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
| `0xf0`–`0xf3` | **create an object**: allocate the record through `0x800448b8`, write `0x60`/`0x61`/`0x62`/`0x70` to `+0x04`, then take the type id and five more bytes from the stream |
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

The card layout is a separate question: the memory-card block is 8192 bytes and
this buffer is far larger, so the card holds a subset or a packing of it.

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
| `grid_query_area` `0x80033c4c` | world x,z and a radius into a range of cells, indexing the grid as `z*800 + x*10` with 80×80 bounds. 15 callers — this is the terrain and collision lookup |
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
and the lock plate (type 106, 300 tall) at `h = -256` on the front of it. With
every object put on the floor, which is what `tools/level3d.py` did while this
was thought not to exist, the lid is drawn *inside* the body. A player looking
at the port reported exactly that: chests drawn open and closed at the same
time, and lock plates lying in mid-air with no chest under them.

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

**The first frame does one more thing.** Opcode 9 (`0x80048c34`, 18
instructions) runs once: it takes a slot number from the `u16` at `+0x3a`,
zeroes that object's `+0` and `+0x38`, and sets its own opcode to `0xff`. Every
class-9 record in every snapshot is `0xff`, and the objects they name are
items, which from the first frame on are not drawn. What shows one again is
not read.

**Checked** against all 13 snapshots with a level in them, twelve of level 0
and one of level 4:

    angles    4344 of 4352   the 8 are a door and chest lids, opened in play
    scale     4352 of 4352
    position  4352 of 4352
    opcode    4226 of 4226   the hook's objects and the runtime arms left out
    byte +0   4016 of 4226   18 items on level 0 and 1 on level 4, the same
                              in every snapshot -- taken, by all appearances
    the grid  exact on 7 of 13, outside the occupancy count; the other six
              are the ones where a door or chest had been opened

And the grid is the part that changes the port most: **every level but 0 was
built with no doors in it**, because the only grid with the stamps was a dump
of level 0. From the disc it differs from the live grid by 32 to 72 bytes;
from the loader, by none.

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

Not ported: the AI, so an awake creature stands at home; the cell marks
through `grid_query_area`; where followers and object riders stand; the model
110 rule in `actor_tick_driver`; `0x801b25e5`; and the game's `rand` seed. The
port also uses the disc's category for the two men by the house, so it shows
the man at (57,3), whom that session held. The one at (62,4) is held by
`actor_spot_taken` in the port, because the man at the table stands on the
same spot.

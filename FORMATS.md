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

## 3. Text is stored as pictures

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

### Where the object textures are not

The placed objects name texture pages `0x0b` to `0x0f` — VRAM from x=704 across
— on 57 119 of their primitives, and `RTIM.T[lv]` leaves that region entirely
empty. Every one of those primitives therefore drew white, which is what a
player saw as "big white things where the grass should be".

A RAM snapshot shows all 32 pages full while the game runs, so the region is
loaded by something we have not found. It is not a verbatim copy of any of the
nine archives — searching for the first rows of it finds nothing — so the load
packs or rearranges. `tools/level3d.py` fills those pages from a snapshot in the
meantime and says so when it does.

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
| `flag_gate` (`0x80061a90`) | the story flags decide — which is how the rest of the game's thirteen cutscenes are reached |
| `0x80061bc4`, a bare wrapper, from `game_main` at `0x80014e74` | guarded by `bne $s1, 1` — and `$s1` is the new-game flag, set when `read_overlay_arg2` returns −1 |

So the opening plays on a new game and not on a loaded save, from `game_main`'s
own init block, a few instructions after `place_player_on_terrain`.

### The cutscene list is pairs of scene and gate flag

`0x801e825c` holds a **cursor**, and `build_str_name` takes the scene number
from the byte it points at. In a level 0 snapshot the cursor is `0x801e7f78`
and the bytes there are `3, 9, 31, 3, 0xff`. `flag_gate` reads the *second*
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

**Withdrawn: the flag is not a key, it is an "already shown" mark.** This
document said bit `0x80` meant "skipped once that is set", and I told a player
that level 13's overlay *unlocks* `S04`. Both are backwards, and the answer is
in the delay slots. At `flag_gate+0xc4` the branch taken when the flag is set
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

**A correction that follows from it:** these indices reach 126, and `flag_gate`
masks the byte with `0x7f`. So `story_flags` runs to **128 entries**, not the
64 this document and `tools/story.py flags` assumed — `reset_story_flags`
clearing "0x40 bytes and more at +0x100" fits that better than it fits 64.

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

**The three men are turned on by two different routines.** The alive byte at
`+9` of each actor was watched across the same session:

| actor | mesh | written from |
| --- | --- | --- |
| 0 | 32 — the one at the table | a call at `0x8004b698+0x14` |
| 1 | 33 | a call at `0x8004c1f0+0xa4` |
| 2 | 34 — the one with the watering can | the same `0x8004c1f0+0xa4` |

`0x8004c1f0` reads the player's own X and Z at `0x801b25f0` and `0x801b25f8`,
so it activates actors by how near the player is. Whatever `0x8004b698` is, it
is not that, and it is what puts the man at the table there.

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

**Withdrawn, and it was mine:** from that I said "the 12 179 instructions the
tool counts as `say` are dialogue". They are not, and fixing the base is what
showed it. **Only 42 of the game's 265 entities carry a base at all**, and
those 42 hold **267** of the 12 179 opcodes, of which **242 land on text this
project has decoded — 90 %**. The other 11 912 belong to entities whose base is
zero. Every opcode does drive an animation *and* fetch `TALK.T[base + opcode]`,
which is what the code says; what a zero base fetches is not dialogue anybody
sees. The reading was right and the conclusion drawn from it was too wide.

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

`tools/level3d.py` keeps the list in `NOT_DRAWN`. Whether any other type belongs
there is open; 299 is alone in being both always-readable and a coarse box, so
nothing else is excluded on suspicion.

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
at runtime — read it live; a snapshot is `out/tile_look.bin`. Level 0 uses four
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
the script block as records. Reading it properly gives 16 entities on level 0,
12 on level 4, 10 on level 7 — **265 entities and 1350 scripts in the game**.
Reader: `tools/entities.py`.

A record ends with a list of `u32` offsets into the script block, **starting at
+0x38** and terminated by `0xffffffff`. Those offsets are monotonic across the
whole level: entity 0 owns the first run, entity 1 the next, so the block is one
sequential stream that the records carve up.

The **first offset is a header, not code**. The interpreter keeps the program
counter in its `+0x10` and a flag in `+0x13`, and reaches code at header+0x14,
so decoding that entry as instructions decodes a struct.

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

What sets a live record's class, and so what would flip a chest from one state
to the other, is not read. The 24-byte type records are not a verbatim run
anywhere in `GAME.EXE`, so something builds the table; `tools/level3d.py` takes
it from a RAM snapshot, which means it carries that session's state and not a
new game's.

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
| tree 324 | `0x00` | `+0x38` = 120–230 in steps of 10 | a height, probably (*unverified*) |

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
| `flag_gate+0xb4`, `flag_gate+0xd8` | tests `flags[b & 0x7f]`, bit `0x80` picking which of two checks, returning 2 or 0x10 |

Three things follow. The array is **saved and restored** — the serialiser pair
moves it to and from the save buffer — so it is persistent game state, not per-level
scratch. It is **at least `0x100` bytes**, since the reset clears two regions.
And **`flags[0]` is a progress counter**: `object_trigger` raises it to the
destination level number whenever that is higher than what it holds, and never
lowers it, so it records the furthest level the player has reached.

### Entity scripts barely branch

With the base corrected, 1086 scripts decode to 12 179 plain instructions, 876
ends, and **four `0xf9` conditionals with no `0xf7` anywhere**: two on flag 0
(`== 10`, on levels 24 and 27) and two on flag 14 (`== 0`, levels 11 and 13).
Flag 0 is the progress counter, so a late-game entity gating on it reads true.

An earlier pass here reported *zero* conditionals. That was the wrong base, and
the claim is withdrawn — though the corrected number is small enough that four
instances in twelve thousand instructions deserve confirming in play before
anything is built on them.

And the dialogue reading of the common opcode barely applies: it reaches
`TALK.T` **only when the entity's kind byte is `0x2b`**, and across the whole
game exactly **one entity of 265 is that kind**. Every other script is a list
of animation frames. `tools/escript.py` prints `frame n` for those rather than
inventing a line of dialogue beside them.

So `FDAT.T` entry `3n + 1` is an animation sequencer, and neither the quest
conditions nor the conversations are in it.

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

A full decode of all 1350 scripts is written to `out/scripts.txt` by
`for lv in $(seq 0 27); do tools/escript.py $lv; done`. It is regenerated from
the disc, so it is not committed.

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

`reset_story_flags` clearing "0x40 bytes at the base and more at `+0x100`" is
this block, and the serialiser pair copying the array in and out is this block
being saved and restored.

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
reproduces the live Y for 336 of 347, so the yaw is read; the other two are
not. Bytes 18 to 20 of the record scale by 64 into exactly the right angles for
all nine tilted objects **and into nonsense for the rest** — 40 of 347 on the
Y axis against the yaw field's 336 — so that field is conditional on something
not yet found. `tools/level3d.py` takes the triple from a RAM snapshot instead,
labelled borrowed like the scales and the object textures. A player found this
one too: a helmet standing on end in the port and lying on its side in the game.

**The height is in the record after all.** This document and `BACKLOG.md` both
said it was not, and that an object simply stands on the terrain at
`-128 * cell[+6]`. It does not: the terrain is only where an object with
`h = 0` stands, and the live Y is

```
y = -128 * cell[+6] + s16(record[12])
```

which reproduces the live object table for **345 of level 0's 347 placed
objects**. The two it misses are both type 280, whose records are mostly `0xff`
filler and whose live Y is a round `-12800`, so something else positions them.

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
mistook for the scripts proper.

# King's Field II (SLUS-00255) — recovered formats

Everything here was derived from the disc and from live RAM; there was no prior
documentation. Each claim notes how it was established, so anything marked
*unverified* should be treated as a working guess.

Units: `u8/u16/u32` little-endian, `s32` signed. Addresses are PlayStation
KUSEG (`0x80000000`+). Offsets into RAM snapshots are `addr & 0x1FFFFF`.

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
| `DRM/D00..D17.S` | 18 × 1.5 MB | fixed-size streams, not yet identified |
| `OP/`, `STR/` | ~340 MB | MDEC video |

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
| `RTIM.T` | 43 | texture pages |
| `RTMD.T` | 32 | TMD models |
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
u32          total size of the script block
u16[254]     offsets into the script block
...          variable-length event scripts (opcodes not yet decoded)
```

Cell layout:

| Offset | Meaning | How established |
| --- | --- | --- |
| +0..+4 | constant `ff 00 00 ff 00` on **every** cell of **every** level — an unused second layer | checked across all 28 levels |
| +5 | wall/surface texture id, `255` in solid rock | correlates with +8 |
| +6 | **floor height** | see the height relation below |
| +7 | orientation of the step face, 0–3 | *unverified* |
| +8 | floor texture id, `255` in solid rock | `255` marks the void in every level |
| +9 | flags; bit 6 (`0x40`) marks a cell carrying a vertical face | appears exactly along height changes |

**World Y = −128 × height byte.** Verified against live objects: height 100 →
`-12800`, 90 → `-11520`, 117 → `-14976`, exact on 83 % of objects.

**World X/Z = 2048 × cell.** The grid is indexed `[z][x]`; orientation was
confirmed by scoring every level and every flip against the height relation —
level 0 in plain `(x, z)` scored 82.9 %, every alternative ≤ 38.6 %.

Community maps are drawn **north up**, which is this grid with Z flipped; the
renderers do that flip for display only.

### Entry `3n + 1` — entity records

28 672 bytes: `u32` header then 120-byte records, ~121 populated. Fields look
like an id, stats and a list of `u32` offsets terminated by `0xffffffff`.
*Not yet decoded.*

### Entry `3n + 2` — pointer block

Small; a count followed by pointers relocated to `0x801e8xxx`.

Renderers: `tools/maps.py` (all levels), `tools/level_map.py` (one level in
detail).

---

## 5. Live RAM

Found by diffing snapshots taken around a pickup. Addresses are from a
`GAME.EXE` session and are **static across that session**; they have not been
checked across level loads.

| Address | Contents |
| --- | --- |
| `0x80011000` | whichever of `OPEN.EXE` / `GAME.EXE` / `END.EXE` is resident |
| `0x8009c800` | end of `GAME.EXE` text; anything below is code |
| `0x800c85e8` | **inventory**, one byte per item id (id 104 went 2 → 3 on pickup) |
| `0x80116e14`–`0x8011ffff` | geometry cache, rewritten when the camera moves |
| `0x80120000`–`0x8014ffff` | GPU packet buffers, rewritten every frame |
| `0x80192984` | a record inside the **object table** (see below) |
| `0x801aec4c` | **player position** `s32 X, Y, Z`, mirrored at `0x801b0a10` |
| `0x8018fad9` | **current level index** — see below |

### Object table

68-byte (`0x44`) records, walked outward from the known record; 158 live
entries in the sample.

| Offset | Type | Meaning |
| --- | --- | --- |
| +0x00 | u16 | state; `0xffff` on most, drops to other values per type |
| +0x02 | u16 | **object type id**; set to `0xffff` when the object is removed |
| +0x10 | s32 | world X |
| +0x14 | s32 | world Y |
| +0x18 | s32 | world Z |
| +0x28,+0x2a,+0x2c | u16 | equal triple, `0x1000` normally and `0x1fe0` on monsters — probably scale (*unverified*) |

**The type id indexes `MO.T`**: all 48 distinct ids in the sample have a model
there, while `ITEM.T` is missing 11 of them and `MOF.T` 4. `ITEM.T[id]`, when
present, is that type's description — which is why unique landmarks resolve
correctly and appear exactly once each (one *Statue of the Hero*, one *Royal
Emblem*, one *Rest in Peace*). Ids in the biography range resolve to names that
repeat implausibly often, so the two archives share numbering only in part.

### Type ids confirmed by experiment

Each was established by snapshotting either side of a deliberate action and
keeping the record nearest the player that changed.

| id | What it is | Evidence |
| --- | --- | --- |
| 104 | **Earth Herb** | inventory screen showed `EARTH HERB ×2`; slot 104 held 2 |
| 105 | **Antidote** | same screen showed `ANTIDOTE ×1`; slot 105 held 1 |
| 106 | **Chest** | opening it set `+0x34` from 0 to 255, 866 units from the player |
| 154 | revealed when the chest opens | changed alongside 106; the open chest shows an item inside |
| 175 | **Locked door with a keyhole** | reported from play; it is the object nearest the player at 3847 units on level 4, 8 instances |
| 177 | **Door** | opening it changed `+0x04`, `+0x0a`, `+0x0b`, `+0x23`, `+0x3c`, 1354 units away |
| 257 | the keyhole that door 175 needs a green key for | reported from play; 7 instances against 8 doors, each sitting beside one — so the lock, not the key (*the key item itself is still unidentified*) |
| 192 | **Tombstone** | reported from play; may hold an item |
| 196 | **Chipped tombstone** | reported from play |
| 227 | **Save point** | reported from play |
| 283 | something animated | `+0x3c`/`+0x3d` tick on every instance in every pair of snapshots, so the *Varde* text at that index is a false match |
| 324 | **Tree** | reported from play; the *Two Headed Grave Pot* text at that index is another false match. None of the 71 instances carries a script, so a tree holds nothing. Its `+0x34` takes round values 120–230 in steps of 10, plausibly a height (*unverified*) |

Names confirmed this way are written with a trailing `!` in the tools; a name
merely taken from `ITEM.T` at the same index gets a `?`, because that archive
shares numbering with the object types only in part.

### The parameter block, `+0x34..+0x3b`

Eight bytes, `0xff` meaning unset, used by 64 of the 88 types seen. It is not a
container inventory — the meaning depends on the type:

| Type | Pattern | Reading |
| --- | --- | --- |
| doors 175–178 | `ff <x> <z> <n> 4e` | `<x>,<z>` is the door's own cell |
| keyhole 257 | `ff ff <k> <n>` | `<k>` is 1–3, presumably which key fits |
| chest 106 | `+0x34` = `00`, becomes `ff` when opened | the "still full" flag |
| tombstones, statues, signs | `ff ff <u16>` at `+0x36` | see below |

The `u16` at `+0x36` runs from 8 to 254, which happens to fit the level's
254-entry script table, and the one tombstone on level 0 carrying a value —
cell 12,60 — did yield 100 gold coins while the five plain ones beside it gave
nothing.

**The disassembly does not support reading it as a script index.** At
`0x8004b288`, inside the loop that walks the object table (`$s2` advances by
`0x44`), the field is used as a *velocity*:

```
lh    $v0, 0x36($s2)      ; take the field
lw    $v1, 0x10($s2)      ; world X
addu  $v0, $v0, $v1       ; X += field
sw    $v0, 0x10($s2)
lhu   $v0, 0x36($s2)
addiu $v0, $v0, 0x14      ; field += 20, i.e. acceleration
sh    $v0, 0x36($s2)
```

with the same pattern a few instructions later against `+0x1c`, clamped at
`0x400`. So `+0x34..+0x3b` really is a per-type scratch block, and for anything
that moves it holds motion state. The gold-coin correlation is a single data
point and may well be coincidence; treat the star marker on the maps as "this
instance has a non-default parameter", not as "this contains treasure".

54 of the 158 objects on level 0 carry one. Tombstones with a script:

| Level | Cell | Script | Result |
| --- | --- | --- | --- |
| 0 | 12,60 | 89 | 100 gold coins (confirmed) |
| 4 | 15,34 | 196 | unopened |
| 4 | 34,61 | 161 | unopened |
| 4 | 56,56 | 163 | unopened |
| 4 | 4,33 (chipped) | 183 | unopened |

Trees (id 324) never carry one across 71 instances, so they hold nothing.

Counts: level 0 has 1 chest, 4 doors, 6 Earth Herbs, 2 Antidotes; level 4 has
1 chest, 1 door, 6 Earth Herbs, 3 Antidotes.

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

### The transition function

With breakpoints finally working, a walk from level 0 to level 4 fired
`0x80018358` exactly once, returning to `0x8001830c`, which puts the call
inside **`0x80017c78`** — the level transition routine.

```
0x80017c78(a0 = level, a1, a2, a3, and four more on the stack)
```

`0xff` in an argument means "leave this one alone": the body compares each
against `0xff` before touching the corresponding byte of the block at
`0x8018fad8`. One caller, `0x80029244`, sets the stack arguments to
`ff 7f 7f 7f`.

Called from at least: `0x80029244`, `0x800292a8`, `0x80029360`, `0x8004a3f4`,
`0x8004a424`, `0x8004a54c`, `0x8004a858`, `0x8005c9b8`, `0x8005c9e8`,
`0x8005cb80`.

**A level change reads no archives at all** — five breakpoints across every
archive reader caught three hits in a whole session, all during boot. So the
level payload arrives by some other route; the streamed `\DRM\Dnn.S` files,
whose filename builder clamps the index to 0..17 for the 18 files present, are
the obvious suspect.

Cross-level travel therefore means calling `0x80017c78` with the right
arguments rather than faking memory. *Not yet attempted.*

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

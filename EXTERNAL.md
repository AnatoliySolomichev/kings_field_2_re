# Outside sources

Findings taken from other people's work. Anything that has since been checked
against our own disc or RAM has moved into [FORMATS.md](FORMATS.md) with the
evidence attached; what is left here is **unverified for SLUS-00255** and should
be treated as a hypothesis, not a fact.

A note on numbering, because it is the easiest way to read one of these sources
wrong. The series is numbered differently in Japan and the West:

| Japan | West | Disc | Ours? |
| --- | --- | --- | --- |
| King's Field | never released | SLPS-00017 | no |
| King's Field II | *King's Field* (US) | SLUS-00158 | no |
| King's Field III | ***King's Field II*** (US) | **SLUS-00255** | **yes** |
| King's Field III: Pilot Style | never released | SLPM-80029 | no |
| King's Field IV | King's Field: The Ancient City | SLUS-01324 | no |

Projects use the Japanese numbering. When KingsFieldRE says "KF2" it means the
first US game, not ours; ours is its `KF3U`. The two 2026 ports below do the
same — their "King's Field III" is our disc, and verdite3's sibling Verdite2 is
SLUS-00158 — while kf2-60fps goes by the box, so its "King's Field II" is ours
too. Not ours, whatever their names say: MoonlightRuin's Spanish "King's Field
2" patch (the game of SLUS-00158), alexbeavs' kings-field-recomp and Acranon's
kf1-enhanced (both SLPS-00017).

## Sources

| What | Where | Covers our disc? |
| --- | --- | --- |
| KingsFieldRE — tools, notes | [github.com/IvanDSM/KingsFieldRE](https://github.com/IvanDSM/KingsFieldRE) | partly, as `KF3U` |
| KingsFieldRE wiki — formats and structures | [the wiki](https://github.com/IvanDSM/KingsFieldRE/wiki) | no, SLUS-00158 |
| GameShark codes for SLUS-00255 | [gamehacking.org/game/89071](https://gamehacking.org/game/89071) | **yes** |
| King's Field Texture Tool | [romhacking.net utility 1063](https://www.romhacking.net/utilities/1063/) | series-wide |
| Ghidra PSX loader | [lab313ru/ghidra_psx_ldr](https://github.com/lab313ru/ghidra_psx_ldr) | generic PS1 |
| FromSoft Modding Committee | [Discord](https://discord.gg/XgDtp8A9) | where the KF3 knowledge is |
| kf3-enhanced — a PC port by static recompilation (MIPS to C#, on RecompOne), with research notes and function maps | [github.com/Acranon/kf3-enhanced](https://github.com/Acranon/kf3-enhanced): `docs/research/`, `config/funcmaps/` | **yes** |
| verdite3 — another RecompOne port | [github.com/Voicedrew11/verdite3](https://github.com/Voicedrew11/verdite3): `docs/GAME_INTERNALS.md` | **yes** |
| kf2-60fps — a 60 fps patch, and the research behind it | [github.com/JonathanDC64/kf2-60fps](https://github.com/JonathanDC64/kf2-60fps): `docs/RESEARCH.md` | **yes** |
| kings-field-2-decomp — a binary-matching decompilation, 564 of 564 functions | [github.com/Voicedrew11/kings-field-2-decomp](https://github.com/Voicedrew11/kings-field-2-decomp) | no, SLPS-00069, the game before ours |
| KINGSFIELDIII-KR — a Korean patch, v0.9-RC1 | [github.com/ps1-kor-patches/KINGSFIELDIII-KR](https://github.com/ps1-kor-patches/KINGSFIELDIII-KR) | no, SLPS-00377 v1.4; a README alone |
| Community maps, for names and places (kf3-enhanced's pointer; not read here) | [kingsfield.fandom.com](https://kingsfield.fandom.com), [kings-field.neocities.org](https://kings-field.neocities.org) | series-wide |
| CodeBreaker and Action Replay lists | [almarsguides.com, King's Field 3](https://almarsguides.com/retro/walkthroughs/PS1/Games/KingsField3/ActionReplay) | no, the Japanese release; not read, below |

KFModTool identifies SLUS-00255 explicitly and loads its maps and models, but
prints "support for the game you loaded is INCOMPLETE" for it: the name and id
databases in its `kf2/` directory are for SLUS-00158 only, and grepping the
source shows KF3 handling confined to the map and model viewers.

What its source says of our disc and its Japanese siblings
(`Tools/KFModTool/core/kfmtcore.cpp`, `kfmtcore.h`): the Japanese King's
Field III comes as v1.3 (SLPS-00377) and v1.4 (SLPS-03580, SLPS-91089), told
apart by the string in `COPY.TXT`; ours is known by `SLUS_002.55` alone; and
all three, with Pilot Style, go through one loader — the nine archives in
`CD/COM`, `OP/OP.D` as a "MIX", and `LOAD.MSG` — with the texture database in
`FDAT.T` entry 84 (81 for Pilot Style; FDAT.md has the entries from 84 on as
shared). Its sound-bank reader is commented out: a generic VAB header, nothing
of the game's own.

## Already checked, and it held

Listed so nobody re-derives them; the detail is in FORMATS.md.

* the `.T` container layout — matched what we had worked out independently
* the entry checksum, `0x12345678` plus the u32s — verified on every entry of
  seven of our nine archives by `tools/tsum.py`
* the object structure offsets: `Visible` at `+0x00`, `ObjectID` at `+0x06`,
  position at `+0x14`, rotation at `+0x24`, scale at `+0x2c`, gold at `+0x3a`,
  and `0x44` bytes overall. Three of those matching at once is what exposed our
  four-byte record misalignment
* the inventory base `0x800c85e8` — the same address we had found by diffing
* `FDAT.T` as a (map, placement, code) triple per area followed by shared
  entries from 84 on, and every area module linked at `0x801e8308` — FDAT.md
  and `tools/overlay.py`; kf3-enhanced (`docs/research/boot-and-cd.md`,
  "FDAT.T") and KFModTool read the same
* the frame gate: `frame_limit` waits for the fourth vertical blank, 15 frames
  a second (FORMATS.md, "How long a frame lasts"); kf3-enhanced and kf2-60fps
  measured the same
* the gamehacking list's **eight** offensive and **nine** defensive figures,
  the ninth defence half (`0x801b255a`) the poison resistance — settled by the
  game's own ratings page (FORMATS.md, 5.1), and kf3-enhanced's table has the
  same eight. Moved here from below, where this file had read them wrongly
* what armour turns away and what it changes — the fire mail against fire
  always; the dragon head, the groundal mail and ichrius' armor against slash,
  blow and stab one time in four; the promeus five always; the two shields
  against magic one time in four and the ebony bracelet one in two; the
  groundal crown doubling a spell's cost and orladin's mail halving it, and
  weapon `0x1f` casting nothing; the bow `0x1c` costing 3..7 HP a draw; the
  magic gauge's rate a quarter less with helm `0x25` and twice with armour
  `0x30`: kf3-enhanced's "Hidden gear effects" (`game-systems.md`) gives what
  FORMATS.md read off `player_take_hit`, `cast_spell`, `held_item_tick` and
  the controller's USE stretch
* level 0's slots 70, 33 and 116, unlocked by story flag `0x16` (FORMATS.md,
  "What a level does as it comes in: entry 5") — kf3-enhanced's "Marilyn's
  quest and Quist's mystery door" names the same three, a door and two chests
* the save file: verdite3's `BASLUS-002551` is BOOT.md's `BASLUS-00255` and the
  slot's digit

## Taken but not verified

**Entity structure**, from the KingsFieldRE wiki, for SLUS-00158. 124 bytes.
Offered as a starting hypothesis for the 120-byte records in `FDAT.T` entry
`3n + 1` and for the live monster records, both of which are undecoded here.
The object structure needed a four-byte shift between the two games, so expect
this one to need adjusting too.

| Offset | Field |
| --- | --- |
| +0x00 | disabled, false only when `0xff` |
| +0x01 | mesh id |
| +0x02 | entity class |
| +0x06 | layer |
| +0x07, +0x08 | tile position |
| +0x09 | alive |
| +0x0a | respawn chance |
| +0x0b | dropped item |
| +0x0c | current animation |
| +0x0e | current state |
| +0x10 | previous state |
| +0x1a | HP |
| +0x22 | parent index — the kraken's head points at its body |
| +0x2c | position |
| +0x40 | rotation, wraps at 4096 |
| +0x48 | scale |
| +0x60 | state pointer |

**Entity states**, from the same project's notes, observed in SLUS-00158:

| Value | State |
| --- | --- |
| `0x01` | wandering |
| `0x02` | taking damage |
| `0x03` | dying |
| `0x04` | melee attack |
| `0x05` | approaching the player |
| `0x0f` | dash |
| `0x17`, `0x18` | secondary attacks |
| `0x19` | casting — archers' arrows are a spell internally |

**Object fields whose names did not survive contact with our game.** The wiki
calls `+0x38` `KeyID` and `+0x3e` `MessageID`. On SLUS-00255 the code says
otherwise: `+0x38` is a gate the pickup handler tests against `0xff`, with
`0xf0`, `0xf1` and `0xfe` selecting different refusals, and `+0x3e` is a flag
whose only test is against zero. Both may still be key and message related, but
neither is a plain id here, so we do not carry the names over. The wiki's
pointer at `+0x40` is an object *index* in our build, not an address.

**Withdrawn: the offensive rating layout.** This file read the gamehacking
list's eight offensive and nine defensive figures as two 9-wide arrays, with a
dark entry on the offensive side as well, which put the list's offensive magic
labels one slot low. The game's own ratings page says otherwise: eight offence
halves — slash, blow, stab, holy, fire, earth, wind, water — and nine defence
halves, the ninth (`0x801b255a`) the poison resistance (FORMATS.md, 5.1). The
list's eight and nine were right and the 9-wide reading was wrong; it is under
"Already checked" now.

## Found in 2026, for our disc — not verified here

Read on 2026-11-04 from the three projects in the table that target
SLUS-00255 — kf3-enhanced at its commit of 2026-10-10 (0.1.0), verdite3 at
2026-10-18, kf2-60fps at 2026-06-17 (v1.6.0) — and from KFModTool's source,
whose last commit is 2022-09-28. kf3-enhanced says each fact in its notes "has
been shown by a watchpoint, a RAM diff, the disassembly or a test in the game";
verdite3 dates what it read and what it measured; kf2-60fps probed the game
live in PCSX-Redux and read Ghidra's and psxrecomp's output. **None of it has
been run against our disc.** Addresses are GAME.EXE's, under
`data/symbols.json`'s name where it has one; a `kf_*` or `func_*` name is the
outside project's. What holds goes to FORMATS.md with our own evidence, as the
items under "Already checked" did.

### Is ours a copy of the Japanese release?

* **The data, probably.** KFModTool loads the Japanese v1.3 and v1.4 and ours
  by one path: the same nine archives, the textures in the same `FDAT.T` entry
  (above). Nobody has published a comparison of the archives' bytes.
* **The programs, no.** kf3-enhanced accepts our disc alone: "Other regions are
  different programs and will not work" (its README). Its function maps, and
  verdite3's, are for ours.
* **Two Japanese revisions.** v1.3 and v1.4, told apart by `COPY.TXT`
  (KFModTool). The Korean patch targets "SLPS-00377, Version 1.4 / Rev 1", so
  the first serial was pressed as both, where KFModTool has SLPS-00377 as v1.3
  alone. PSX Data Center lists the reprints
  [SLPS-91089](https://psxdatacenter.com/games/J/K/SLPS-91089.html)
  (PlayStation the Best) and
  [SLPS-91426](https://psxdatacenter.com/games/J/K/SLPS-91426.html) (PSOne
  Books). Which revision ours was made from, nobody says.
* **What a player sees.** A post on the
  [Agetec forum](https://www.tapatalk.com/groups/agetec/need-help-king-s-field-releases-t2684.html),
  read only through a search engine's summary: the translation is the one
  difference, but for "the 2D guy swinging the sword in the loading screens",
  whom the Japanese releases do not have.
* **The game before ours moved by a constant.** KingsFieldRE's
  `Notes/japanese magic mem positions`: "add F44 to get US KF mem positions"
  from the Japanese King's Field II's codes. No such shift has been published
  for King's Field III.

### Walking through walls: a guess on two readings

The Action Replay list for the Japanese release (almarsguides.com, read only
through a search engine's summary) gives "Walk Through/Climb Over Walls:
800297A6 1400". `0x1400` over the top half of an instruction makes it
`bne $zero, $zero`, a branch never taken. kf2-60fps names the branch that
refuses a step in `player_horizontal` (`0x8002e3f8`): `0x8002e4cc`,
`bne $s5, $zero` on `collide_query`'s mask (`RESEARCH.md` §17.2). *If* the
Japanese code clears the same branch, that instruction sits `0x4d28` lower in
the Japanese GAME.EXE, and the code for ours is `8002E4CE 1400`. **Guessed**,
not read: with the disc, `tools/rdis.py game 0x8002e3f8` settles the first
half in a minute. It would carry a session onto the cells of collision opcodes
`0x31` and `0x35`, which no log has crossed yet (AGENT.md, the queue, item 2).

### Names, from kf3-enhanced's function map

`config/funcmaps/game.json` lists 1203 routines of GAME.EXE and names 108 of
them `kf_*`; the rest carry PSY-Q's names or their address. 87 of the 108 sit
at addresses `data/symbols.json` names, and nearly all mean the same:
`kf_FrameGate` is `frame_limit`, `kf_GainExp` `award_exp`, `kf_PlayerHurt`
`player_take_hit`, `kf_RecalcStats` `player_recalc_stats`, `kf_CreatureTalk`
`script_interpreter`, `kf_WarpTable` `warp_to`, `kf_RunCollisionShape`
`tile_collision`, `kf_UseItem` `use_item`. That is two independent readings
agreeing, not the game's answer. The 21 it names and we do not:

| Address | Theirs | Address | Theirs |
| --- | --- | --- | --- |
| `0x8001576c` | `kf_PlaySound2D` | `0x80027ea8` | `kf_ItemSectorReady` |
| `0x80019b68` | `kf_ArchiveChecksum`, the routine after `file_checksum` | `0x800305d8` | `kf_Interact` |
| `0x8001a634` | `kf_Pause` | `0x80030be0` | `kf_AddHp`, among FORMATS.md's HP writers |
| `0x800221e8` | `kf_MenuButtonInput` | `0x8003456c` | `kf_SetFog` |
| `0x800252f4` | `kf_MenuButtons`, one of the routines OPTION 2 is checked against | `0x80035394` | `kf_LayoutPrimPools` |
| `0x80025be8` | `kf_ItemPreview` | `0x80039428` | `kf_DrawModelPolys2` |
| `0x80027198` | `kf_MenuEnter` | `0x8003d64c` | `kf_DrawScreenTint` |
| `0x80027310` | `kf_MenuLeave` | `0x80041514` | `kf_StepModelAnims` |
| `0x80027a9c` | `kf_MenuShowItem` | `0x80043b38` | `kf_LoadTims` |
| `0x80027ac0` | `kf_ItemModelLoad` | `0x800616dc` | `kf_MovieFetchFrame` |
| | | `0x80061878` | `kf_MovieFlip` |

### Where a reading differs from ours

| Address | Ours | Theirs |
| --- | --- | --- |
| `0x80028d54` | `sync_player_pos`, called at the end of `player_move` | `kf_DeathPlaneCheck` (kf3-enhanced) |
| `0x8003ab04` | `draw_tmd_object`; `tile_prims` is the same call at another level of detail | `kf_DrawGroundNear` (kf3-enhanced) — perhaps only the name |
| `0x80034bf4` | `view_matrix_build`, the camera's rotation for the frame | `kf_BuildTileGrid` (kf3-enhanced); to kf2-60fps the visible-cell builder, with the cone's half-angle `0x1b8` (38.7°) at `+0x8c`, a near band of five cells still cone-tested at `+0x2b0`, a far ring of `0x100` at `+0x2f8` (`RESEARCH.md` §13.3, §13.6). Both may hold: the two name different parts of one routine of 307 instructions |
| `0x801e824e` | `cutscene_pending`: at 1, `cutscene_step` calls the level's entry 7 | the STR player's status: `0x63` when the frame fetch (`0x800616dc`) sees the stream end, which ends `str_play`'s loop (kf3-enhanced, `boot-and-cd.md`, "Movies") |
| `0x801aeaea` | `sky_on`, written from a class-`0xe3` zone's `+0x3b` | the byte a zone's `+0x33` sets and the earth shield (`0x35`) reads (kf3-enhanced, `game-systems.md`, "Regeneration") |
| `0x80053c84` | `effect_spawn`, which kf2-60fps calls "the universal effect spawner" too | "monster AI", in passing (kf3-enhanced, `audio.md`) |

### The level block, and what a level change loads (BACKLOG.md §1)

kf3-enhanced (`world.md`, "Changing area") reads `object_trigger`'s five block
bytes as the area's map, placement and code — each *n* for area *n* — and two
banks: the sounds, whose VAB entry bank + 1 is loaded at `level_load+0x820`
(`0x80018b78`), and the music, at `level_load+0x888` (`0x80018be0`). `0xff`
keeps either, and the three bytes after are the arrival shift, `0x7f` keeping
the place. verdite3 warps with `object_trigger(N, N, N, 0xFF, 0xFF, 0x7F, 0x7F,
0x7F)` and says `level_load+0x228` (`0x80018580`) reads entry `3n + 1` by the
area byte at `0x8018fae4` (`GAME_INTERNALS.md`, "Saves"). Ours: the block's
byte 1 is the level, byte 0 the bank `model_of_type` adds, and `level_load`
reads entries `3n + 0` and `3n + 2` through `read_archive_entry` (FORMATS.md,
"Walking from one level into the next"). The two readings want laying over the
code together before §1's "bytes 0, 2, 3, 4" can be answered.

### Sound (BACKLOG.md §0)

kf3-enhanced, `docs/research/audio.md`:

* `sound_play_3d` (`0x80015410`; the sound with flag `0x8000`, a position, the
  volume, the farthest distance, and on the stack the fade and the note): the
  listener at `0x801b0a10`/`14`/`18` (three s32), its yaw at `0x801b0a24`. d is
  `SquareRoot0` of the offsets `>> 3`, then `<< 3`; past the farthest distance
  nothing plays; g = 128·(fade − d)/fade, at most 127; the base g + (127 − g)/4,
  or with the flag g + 32 + (127 − g)/2, at most 127; the angle −atan2(dx, dz),
  4096 a turn, less the yaw; one ear is lowered by base·|sin angle|·(127 − g)/128.
  Front and back fold together, and the levels are set once, at key-on.
* `sound_play` (`0x80015790`) keys on through `0x8006dce8`; `0x8001576c` plays
  a sound with no place (the sound, the volume), and the player's own sounds go
  through it.
* the area's ambient sounds come from zones `render_walk` meets (`0x8004104c`,
  `0x800410a8`): X at `+0x11`, Z at `+0x19`, a half-size in units of 1024 at
  `+0x35`/`+0x36`, the box running from X to X + 2048·size.
* libsnd's 24 voices: records of `0x34` at `0x8009e9c4` (`+0x1e` the envelope
  last read, `+0x33` busy). A voice is freed once its envelope has read 0 for
  15 vertical blanks, and key-ons are flushed from the vertical-blank interrupt.
* what a level change loads of it: above.

### The picture

* the cone `view_matrix_build` builds: above.
* fog: kf2-60fps reads `fog_range_set` (`0x80035358`) as `SetFog(20000,
  24000)`, with `SetFogNear(a, 200)` at `0x80035380` — `SetFogFar(near, 200)`
  in our reading. Ours takes the two from the lighting record's `+0x68`/`+0x6a`,
  so 20000 and 24000 are likely one level's pair. The projection, 200
  (`SetGeomScreen`), agrees with FORMATS.md.
* the groundal shield (`0x3a`) calls `0x8003456c` with `(10, 10, 10, 0xd05,
  6000)` every frame: a dimmer view, as the darkness gives from `0x80030e14`
  with `0x1388` (kf3-enhanced, `game-systems.md`, "Each tick").
* a clock at `0x80182964` and 128 slots of `0x18` from `0x80182968`, the frame
  byte at `+5`, stepped by `0x80041514`; the flames' sprites cycle off it, one
  frame a frame at period 1 (kf3-enhanced, `graphics.md`, "Model animation
  slots"; kf2-60fps §4). The water's colour scroll, 0..31 at `0x801aeb20`
  (kf2-60fps §8), is the `+4` offset of `texture_scroll_step`'s first record at
  `0x801aeb1c` in ours: the same thing.

### Movies (BACKLOG.md §12)

`str_play`'s loop ends at the stream's last frame or when `0x801e824e` reads
`0x63` (above). `0x80061878` is a one-line buffer flip, called once a frame at
the top of the loop and nowhere else, which is where kf3-enhanced checks for a
skip of its own (`boot-and-cd.md`, "Movies"). Neither project names a pad test
of the game's own, which §12 still wants.

### Gear effects our documents do not mention yet

kf3-enhanced, `game-systems.md`, "Hidden gear effects" and "Regeneration",
from "a capstone sweep" of every read of the equipped slots. A text search of
FORMATS.md finds none of these, but for two routines the regeneration uses:

* the evil crescent (`0x16`): every 150 frames, one time in eight, paralysis
  200; the evil ring (`0x52`): one time in 256 a frame, poison 900.
* weapon `0x1f`: each hit heals 1..9 HP (`0x80030be0`).
* the silence rod (`0x20`): a hit takes the creature's whole HP for types
  `0x3b`, `0x3c`, `0x3d`, `0x3f`, `0x42`, `0x43`, `0x4f`, `0x58`, `0x59` and
  `0x5b`.
* regeneration, whose HP writers FORMATS.md names (`0x80030be0`, `0x80030c6c`,
  a point at a time) and not its periods: on frame *n* (`0x801b2580`), a point
  whenever *n* is a multiple of a period the equipped records carry — the
  weapon's `+0x16` HP and `+0x18` MP; an armour piece's `+0x14` HP gained,
  `+0x16` HP lost, `+0x18` MP gained, `+0x1a` MP lost. Their examples: the
  ivory bracelet's HP every 90 frames, the phantom crown's MP lost every 60.
* the earth shield (`0x35`): MP + 1 every 900 frames while `0x801aeaea` is set
  (above).
* the King of the East's four pieces (`0x08`, `0x37`, `0x42`, `0x4d`) are never
  tested together: no set bonus.

### The engine came from the game before

verdite3 matches routines of ours to its sibling port's of SLUS-00158 by their
code (`match_code.py`): `actor_choose` (`0x8004c01c`), the creatures' think,
"is Verdite2's think ... under other addresses"; `actor_turn` (`0x8004e928`)
is Verdite2's `func_8003C8D8`; `draw_terrain` (`0x8003bfd0`) walks a 25×25
window where SLUS-00158's walks 24×24; `render_walk` (`0x80040ae4`) ranks first
of 1155 against Verdite2's `func_800331B4`, "the same four tables in the same
order ... with other strides" (`GAME_INTERNALS.md`). If that holds,
kings-field-2-decomp, the matching decompilation of the Japanese King's Field
II, is C for much of our engine's ancestor: a source of names and structure,
never of addresses.

### The dump they expect

kf2-60fps checks for `King's Field II (USA).bin`, raw MODE2/2352, 571 766 496
bytes, CRC32 `F8A4C585` (its README). kf3-enhanced and verdite3 look for
`SLUS_002.55` and an `FDAT.T` at least as long as their last area module.

### Not read yet

* [tcrf.net](https://tcrf.net), The Cutting Room Floor, for the series' unused
  content and the differences between releases — not reachable from the
  session that wrote this section.
* [gamehacking.org/game/89071](https://gamehacking.org/game/89071), the list
  FORMATS.md 5.1 began from — not re-read for codes added since, for the same
  reason.
* almarsguides.com's
  [Action Replay](https://almarsguides.com/retro/walkthroughs/PS1/Games/KingsField3/ActionReplay)
  and
  [CodeBreaker](https://almarsguides.com/retro/walkthroughs/PS1/Games/KingsField3/CodeBreaker)
  lists for the Japanese release, and its "King's Field 2" pages, region not
  checked — seen only through a search engine, as was the Agetec thread.

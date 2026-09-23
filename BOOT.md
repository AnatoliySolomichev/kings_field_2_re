# From power-on to the first frame

Everything else in this project was found by watching the game run: a snapshot
either side of an action, a watchpoint on a value, a breakpoint on a routine.
That works, and it is how the collision and the movement were settled, but it
can only answer questions about a moment you can already reach. It cannot say
what happens *before* you can reach anything.

This document is the other direction. It starts at the address the BIOS jumps
to and follows the calls down: the shell, the logos, the attract movies, the
title screen, the menu, and the first frame of the game with a controller in
it. Every routine named here was read off the MIPS with `tools/calltree.py` and
`tools/fdis.py`, and each one says which file in `godot/` reproduces it.

Companion documents: [FORMATS.md](FORMATS.md) for the data formats,
[TOOLS.md](TOOLS.md) for how to run any of this, [AGENT.md](AGENT.md) for the
method, and `data/symbols_boot.json`, `data/symbols_open.json`,
`data/symbols_end.json` and `data/symbols.json` for the addresses.

---

## 1. Four programs at one address

`SYSTEM.CNF` boots `cdrom:SLUS_002.55;1`, and that is not the game. It is a
four-kilobyte shell whose whole job is to load one of three overlays:

| File | Loads at | Size | What it is |
| --- | --- | --- | --- |
| `SLUS_002.55` | `0x80010000` | 2 KB of text | the shell, resident for the whole session |
| `OPEN.EXE` | `0x80011000` | 190 KB | logos, attract movies, title screen, menu |
| `GAME.EXE` | `0x80011000` | 558 KB | the game |
| `END.EXE` | `0x80011000` | 154 KB | the ending |

**The three overlays load at the same address.** That single fact shapes the
whole boot chain: an overlay cannot call another one, cannot leave anything in
its own memory for the next, and has to *return* to the shell to hand over. It
also means an address alone does not identify code in this game — `0x80013a20`
is one routine in `OPEN.EXE` and a different one in `GAME.EXE` — which is why
every tool here takes the executable with it and every symbol table is per
executable.

---

## 2. The shell — `SLUS_002.55`

```
entry_point (0x80010120)
|-- InitHeap
`-- shell_main (0x80010038)
    |-- SetMem(2)      CdRemove()      CdInit()
    |-- Load(exe_name_table[next_index], exec_header)   until it returns 1
    |-- CdRemove()     EnterCriticalSection()
    |-- Exec(exec_header, 0, 0)        <- the overlay runs, and returns
    `-- CdInit()                       then round again
```

`shell_main` is ninety instructions and it is the entire program:

```c
SetMem(2); CdRemove(); CdInit();
*next_exe = 0; *overlay_arg = 0;
for (;;) {
    while (Load(exe_name_table[next_index], exec_header) != 1) ;
    CdRemove();
    exec_header.s_addr = 0; exec_header.s_size = 0;   /* keep this stack */
    EnterCriticalSection();
    Exec(&exec_header, 0, 0);
    next_index = *(unsigned char *)0x800102f0;
    CdInit();
}
```

`exe_name_table` at `0x8001024c` holds three pointers, in this order:

| index | name |
| --- | --- |
| 0 | `cdrom:OPEN.EXE;1` |
| 1 | `cdrom:GAME.EXE;1` |
| 2 | `cdrom:END.EXE;1` |

`next_index` lives at `0x80010260` and is zero in the file, so a cold boot runs
`OPEN.EXE`. When an overlay returns, the shell reads a **byte at `0x800102f0`**
and uses it as the next index. That byte, and two more beside it, are the only
channel between the overlays:

| Address | Name | Who writes it | What it says |
| --- | --- | --- | --- |
| `0x800102f0` | `next_exe` | `open_main` through its own `$gp+0` pointer; `game_main` at `0x80015000`, `0x80015020`, `0x80015040` | which overlay runs next |
| `0x800102f8` | `overlay_arg` | `game_main`, beside `next_exe` | read by `open_main` at its very top: 1 means "you have already seen the logos" |
| `0x800102fa` | `overlay_arg2` | `open_main` at `0x80012008` | the title menu's answer, read by `GAME.EXE` at `0x8001fa60` |

They survive because the shell sits at `0x80010000` and the overlays start at
`0x80011000`. Three bytes of shared memory is the whole inter-overlay protocol.

**In the port:** [godot/boot.gd](godot/boot.gd). `next_exe`, `overlay_arg` and
`overlay_arg2` are static variables for the same reason the shell keeps them
out of the overlays' way — a scene change in Godot is an `Exec` here.

---

## 3. `OPEN.EXE` — the opening

The entry point is three instructions: set `$gp` and jump to `open_main` at
`0x80011e14`, which is 1464 bytes and contains the entire overlay. What it does,
in its order:

```c
heap_init(0x80100000, 0xf8000);      /* the top 992 KB of RAM */
CdInit(); PadInit(0); card_init();
init_sound();                        /* SPU, CD volume 0x30 each side */
init_graphics();                     /* two 640x240 buffers at 0x800a6f00 */

if (*overlay_arg != 1) {             /* not just handed back by the game */
    if (play_movie(3) != 1) {                    /* L0.S, the ASCII logo */
        play_movie(seen_attract ? 1 : 0);        /* M0.S or M1.S          */
        seen_attract = !seen_attract;
    }
}
load_opening_data();                 /* OP.D, once per session */
card_start(); spu_master_volume(0x7f, 0x7f); play_title_music();  /* M2.S */

/* the fade in: any button at all cuts it short */
while (!title_layer_a_done || !title_layer_c_done) {
    frame_begin(); title_layer_a(0); title_layer_b(0); title_layer_c(2);
    if (PadRead(1)) break;
    frame_end();
}

saves = card_probe() ? 0 : card_list_saves(&dir, &count);
choice = saves ? 1 : 0;              /* CONTINUE if there is one to continue */
for (;;) {
    frame_begin(); title_layer_a(1); title_layer_b(1);
    if (title_menu(&choice, saves) == 1) break;      /* a confirm button */
    if (++frames >= 0x178) {                         /* 376 frames, no answer */
        title_confirm_fade(choice);
        play_movie(4);                               /* L1.S, FromSoftware */
        goto attract;                                /* and round again */
    }
    title_layer_c(choice); frame_end();
}

*overlay_arg2 = choice;
title_confirm_fade(choice);
if (choice == 0) { wait 29 frames; play_movie(2); }  /* M3.S, the story */
*next_exe = 1;  *overlay_arg = 0;
draw "Program Loading"; card_stop(); PadStop(); ResetGraph(1);
return;                                              /* back to the shell */
```

### `play_movie` (`0x800136d8`)

Takes an index and plays a stream off the disc. It copies a five-entry table of
twenty-byte names from `0x80011028` onto its stack and indexes it by the
argument:

| index | file | what it is |
| --- | --- | --- |
| 0 | `\OP\M0.S` | the attract movie — the dragon |
| 1 | `\OP\M1.S` | the second attract movie |
| 2 | `\OP\M3.S` | the opening story, played only when a new game starts |
| 3 | `\OP\L0.S` | the ASCII Entertainment logo |
| 4 | `\OP\L1.S` | the FromSoftware logo |

Its frame loop is `frame_begin`, an MDEC decode into the back buffer, a
`LoadImage`, `frame_end`, and then `PadRead(1)`:

* **START** (`0x0800`) returns **1** — skip everything and go to the title;
* any of **TRIANGLE, SQUARE, CIRCLE, CROSS** (`0x10`, `0x80`, `0x20`, `0x40`)
  returns **2** — skip this movie only;
* otherwise it runs to the end of the file and returns 0.

`open_main` treats 1 as "the player wants the title screen now" and anything
else as "carry on down the chain", which is what makes the attract loop.

`\OP\M2.S` is not in that table. `play_title_music` (`0x8001273c`) streams it
separately behind the title screen, and its video track is 16×16 — so what that
file actually carries is the music.

### The title screen

`load_opening_data` (`0x80012494`) allocates `0x32000` bytes and reads `OP.D`
into it whole. `OP.D` is five TIM images followed by a VAB:

| # | size | VRAM | what |
| --- | --- | --- | --- |
| 0 | 256×240, 8-bit | (640, 0) | the artwork: the dragon and the king |
| 1 | 256×89, 8-bit | (640, 256) | `KING'S` |
| 2 | 256×89, 8-bit | (640, 384) | `FIELD II` |
| 3 | 256×56, 4-bit, three CLUTs | (896, 0) | `NEW`, `CONTINUE` and the two copyright lines |
| 4 | 160×144, 4-bit | (960, 0) | `Program Loading` |
| — | 44832 bytes | — | a VAB: the menu's sounds |

Those coordinates are not inferred from the file. The three layer routines ask
`GetTPage` for exactly them — `GetTPage(1, 0, 640, 0)` for the 8-bit artwork,
`GetTPage(0, 1, 960, 0)` for the 4-bit loading screen — so the file and the code
agree independently.

The screen is **640×240**: `init_graphics` hands `SetDefDrawEnv` a width of
`0x280`. Every rectangle below is in that space.

| routine | draws |
| --- | --- |
| `title_layer_a` (`0x8001279c`) | the artwork stretched over the whole 640×240 screen, `KING'S` at (64,44)–(320,133), `FIELD II` at (320,128)–(576,217) |
| `title_layer_b` (`0x80012b0c`) | the two copyright lines, 255×12 each, at x 124–379 |
| `title_layer_c` (`0x80012ea0`) | the menu: `NEW` is u 0–96 of the row at v 16 and `CONTINUE` u 96–192, each into a 96×8 rectangle at x 272–368, y 190 and 202 |

`python3 tools/opening.py title` composes exactly that and writes it out, which
is what makes the rectangles checkable rather than merely transcribed.

### The menu — `title_menu` (`0x800131ac`)

```c
now = PadRead(1);  prev = *pad_prev;
if (fresh(CIRCLE) || fresh(CROSS) || fresh(START)) { play_sound(0x3a); ret = 1; }
if (fresh(UP) || fresh(DOWN)) {
    play_sound(0x5a);
    if (saves) *choice = !*choice;      /* nothing to move to without a save */
}
*pad_prev = now;
return ret;
```

Two entries, `NEW` (0) and `CONTINUE` (1). The cursor only moves when the
memory card scan found a save, and the scan is `card_probe` (`0x80014174`,
which opens, writes and erases `bu00:BASLUS-00255TEMP`) followed by
`card_list_saves` (`0x80014264`, `firstfile`/`nextfile` over `bu00:*` matching
`BASLUS-00255`).

### What choosing `NEW` does

1. `*overlay_arg2 = 0`.
2. Because it is zero, `open_main` waits 29 vertical blanks and plays
   `play_movie(2)` — `\OP\M3.S`, the opening story. Choosing `CONTINUE` skips
   it, which is the only place the two answers diverge inside `OPEN.EXE`.
3. `*next_exe = 1`, `*overlay_arg = 0`.
4. The `Program Loading` screen goes up, the card and the pad are stopped,
   `ResetGraph(1)`, and `open_main` returns.
5. The shell reads `next_exe`, loads `GAME.EXE` and `Exec`s it.

**In the port:** [godot/opening.gd](godot/opening.gd) runs that state machine
over the images `tools/opening.py` extracts, at the coordinates above.

---

## 4. The movies

Twenty-eight Sony STR streams, none of them in `extract/` because the original
extraction only took `/CD` and `/DRM`:

| where | what |
| --- | --- |
| `/OP/L0.S`, `L1.S` | the two logos, 320×240 |
| `/OP/M0.S`, `M1.S`, `M3.S` | the attract movies and the opening story |
| `/OP/M2.S` | 16×16 video: the title screen's music |
| `/OP/M4.S`, `M5.S`, `M6.S` | `END.EXE`'s, by the same table in that overlay |
| `/STR/S03.S` … `S15.S` | thirteen in-game cutscenes |
| `/DRM/D00.S` … `D17.S` | eighteen more, 767 sectors each |

`tools/str.py` reads and decodes them. Three things had to be right and each
was wrong first:

* **Version 3 has no DC coefficient.** It carries the *difference* from the
  previous block of the same colour, variable-length coded with MPEG-1's DC
  size tables and stored in units of four. Read as version 2, a frame decodes
  about eight blocks and then desynchronises.
* **Version 2 is not the sixteen-bit quantiser-and-DC word** the format is
  usually described with. It is a plain signed ten-bit DC, with the quantiser
  coming from the frame header. The first frame of `M0.S` settles it by
  arithmetic: 1320 blocks in 15936 bits is twelve bits a block, which is a
  ten-bit DC and a two-bit end-of-block, and cannot be eighteen.
* **Macroblocks come column by column**, not in raster order. Getting this
  wrong gives a picture whose content is right and whose bands are shuffled.

The check is that each frame's bitstream is consumed to within a word of the
end with every block a valid Huffman code: **20 of 20 frames of `L0.S`, `M0.S`
and `M3.S` each, with at most 42 bits of padding left over.** A wrong table
desynchronises long before that.

**The port plays them.** ffmpeg carries a `psxstr` demuxer and an `mdec`
decoder, so `python3 tools/opening.py video` turns each of `play_movie`'s five
files and the title screen's music stream into Ogg Theora that a
VideoStreamPlayer takes — 37 MB in total, into `out/godot/opening/`. Two
numbers fall out of that which nothing here had settled: the movies run at
**15 frames a second** and their XA audio is **37800 Hz stereo**, both read off
the stream. `tools/str.py` is still this project's own reading of the format
and is what checked it; ffmpeg is how the port gets the pixels without a fast
decoder. If the transcodes are missing, `opening.gd` falls back to one decoded
still per movie and the state machine runs the same.

---

## 5. `GAME.EXE` — the game

`entry_point` (`0x800144f8`) reaches `game_main` (`0x80014bd4`), which zeroes
twelve tables — the object table, the actor table, the player block, the cell
grid — brings up every subsystem, calls `reset_story_flags`, and then asks
`0x8001fa60`, the routine that reads `overlay_arg2`, what the title menu chose.
After that it runs one loop until something ends the session:

```
game_main
`-- L6, one frame:
    |-- 0x800341e8, 0x80034180, 0x80047010
    |-- player_controller      the pad, and everything the player does
    |-- actor_tick_driver      the monsters
    |-- 0x8005bc50, level_load, cutscene_step, 0x8002b330, 0x800156bc
    |-- 0x80034300, 0x80018cd0, 0x80015a48, 0x800422b8
    `-- round again
```

Three exits leave the loop, and each writes the shell's `next_exe`: two write a
register, and the third writes **zero** — back to `OPEN.EXE`, which is how the
game returns to the title screen.

---

## 6. The buttons

### `PadRead`

`0x800785ac` in `GAME.EXE`, `0x8001f9f0` in `OPEN.EXE`, and both are the same
Sony library routine: call the BIOS `OutdatedPadGetButtons` (`B0 0x16`) and
return **NOT** of the word it left in the buffer. The BIOS records a pressed
button as a zero, so after that inversion **a set bit means pressed**.

`player_controller` calls it once a frame and keeps two words:

* `0x801b265c` — this frame's buttons, stored at `0x80031140`;
* `0x801b265e` — last frame's, copied at the end of the frame at `0x80031e94`.

Every menu and every action in the game asks for a bit **set in the first and
clear in the second**. That is the whole of the game's input edge detection.

### The bits

| mask | button | | mask | button |
| --- | --- | --- | --- | --- |
| `0x1000` | UP | | `0x0010` | TRIANGLE |
| `0x2000` | RIGHT | | `0x0020` | CIRCLE |
| `0x4000` | DOWN | | `0x0040` | CROSS |
| `0x8000` | LEFT | | `0x0080` | SQUARE |
| `0x0001` | L2 | | `0x0100` | SELECT |
| `0x0002` | R2 | | `0x0800` | START |
| `0x0004` | L1 | | | |
| `0x0008` | R1 | | | |

This is the PSY-Q layout — the two halves of the hardware's word swapped — and
it is not taken on trust. Four separate places in the game agree with it and
with nothing else:

* the slot holding `0x0800` is read only by the pause menu;
* the slot holding `0x0100` opens the map;
* `play_movie` skips one movie on `0x10`, `0x20`, `0x40` or `0x80` — the four
  face buttons — and the whole chain on `0x0800`;
* `title_menu` confirms on `0x20`, `0x40` or `0x0800` and moves its cursor on
  `0x1000` and `0x4000`.

Under the raw hardware reading those would be R1 opening the menu, L2 opening
the map, the four *directions* skipping a movie, and the title cursor moving on
TRIANGLE and CROSS.

> **Withdrawn.** `data/symbols.json` used to carry the raw reading, as
> "forward is TRIANGLE, back CROSS". The *masks* in it were right — and are
> independently confirmed by `tools/replay.py`, which reproduces 19889 of 20902
> recorded frames from them — but the button *names* were the other layout. The
> entry now says so.

### The binding table

The game never tests a button directly. It reads a **slot**, and the options
screen decides which button that slot holds. The slots are fourteen `u16` at
`0x80081868`:

| address | slot | read by |
| --- | --- | --- |
| `0x80081868` | forward | `player_walk`, `player_controller` |
| `0x8008186a` | back | `player_walk` |
| `0x8008186c` | turn / step left | `player_look` (`0x8002f5c0`) |
| `0x8008186e` | turn / step right | `player_look` |
| `0x80081870` | attack | `player_turn`, `0x8002d2a0` |
| `0x80081872` | menu, alternate | `0x800305d8` |
| `0x80081874` | action | `player_turn`, `0x8002d2a0` |
| `0x80081876` | use | `player_turn`, `script_interpreter`, `load_entry`, `use_item`'s neighbour |
| `0x80081878` | strafe, negative | `player_walk` at `0x8002fba0` |
| `0x8008187a` | look A | `player_look` |
| `0x8008187c` | strafe, positive | `player_walk` at `0x8002fb3c` |
| `0x8008187e` | look B | `player_look` |
| `0x80081880` | **map — always SELECT** | `player_controller` at `0x8003112c` |
| `0x80081882` | **menu — always START** | `player_controller` at `0x80031154` |

The last two are never written by the options screen, which is what pins the
bit names to real buttons.

`apply_control_scheme` (`0x8001f4c0`) fills the rest. Seven movement schemes,
every value an immediate in the code:

| scheme | forward | back | left slot | right slot | strafe − | look A | strafe + | look B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | UP | DOWN | LEFT | RIGHT | L1 | L2 | R1 | — |
| B | UP | DOWN | LEFT | RIGHT | R1 | L1 | R2 | — |
| C | UP | DOWN | LEFT | RIGHT | L1 | R1 | L2 | — |
| D | UP | DOWN | L1 | R1 | LEFT | L2 | RIGHT | — |
| E | UP | DOWN | R1 | R2 | LEFT | L1 | RIGHT | — |
| F | UP | DOWN | L1 | L2 | LEFT | R1 | RIGHT | — |
| G | UP | DOWN | LEFT | RIGHT | L2 | R1 | R2 | L1 |

A, B, C and G turn with the D-pad and step sideways with the shoulders; D, E
and F swap the two. And four action schemes:

| scheme | attack | action | use | menu |
| --- | --- | --- | --- | --- |
| 0 | SQUARE | SQUARE | CIRCLE | — |
| 1 | CROSS | TRIANGLE | CIRCLE | — |
| 2 | CROSS | — | — | — |
| 3 | SQUARE | TRIANGLE | CROSS | CIRCLE |

The options screen that presents them is `options_screen` (`0x80023fd4`), and
its labels are two arrays of strings: nine sixteen-byte action names at
`0x8001137c` — `move{left`, `view{up`, `move{right`, `view{down`,
`forward{back`, `turn`, `move`, `turn{left`, `turn{right` — and seven eight-byte
scheme names at `0x8001140c`, `type{a` to `type{g`.

**In the port:** [godot/pad.gd](godot/pad.gd) carries the bits, the slots, all
eleven schemes and the edge detection, and [godot/player.gd](godot/player.gd)
now takes its input through the slots instead of reading keys directly.

---

## 7. The port, routine by routine

| PlayStation | in the port |
| --- | --- |
| `shell_main` (`SLUS_002.55` `0x80010038`) | `boot.gd`, `_exec` and `overlay_returned` |
| `next_exe`, `overlay_arg`, `overlay_arg2` | `boot.gd`, the three static variables |
| `init_graphics` (`OPEN` `0x80012500`) | `boot.gd`, `_fit` — the 640×240 screen and its 4:3 stretch |
| `open_main` (`OPEN` `0x80011e14`) | `opening.gd`, `_tick` |
| `play_movie` (`OPEN` `0x800136d8`) | `opening.gd`, `_movie_tick` — the same skip rules over a still |
| `title_layer_a/b/c` (`0x8001279c`, `0x80012b0c`, `0x80012ea0`) | `opening.gd`, `_draw_title` |
| `title_menu` (`OPEN` `0x800131ac`) | `opening.gd`, `_title_tick` |
| `load_opening_data` (`OPEN` `0x80012494`) and `OP.D` | `tools/opening.py`, into `out/godot/opening/` |
| `PadRead` (`GAME` `0x800785ac`) | `pad.gd`, `read` |
| `buttons` / `buttons_prev` (`0x801b265c`, `0x801b265e`) | `pad.gd`, `now` and `prev`, filled by `poll` |
| `apply_control_scheme` (`GAME` `0x8001f4c0`) | `pad.gd`, `MOVE_PRESETS`, `ACTION_PRESETS`, `apply` |
| the binding slots (`0x80081868`…) | `pad.gd`, the `FORWARD`…`PAUSE` constants |
| `player_walk` (`GAME` `0x8002f9bc`) | `player.gd`, `_tick` — now reading the slots |
| `player_vertical` (`GAME` `0x8002ed60`) | `player.gd`, `_move` (unchanged; see FORMATS.md §4) |

Run it with `python3 tools/level3d.py 0` and then `godot-4 --path out/godot`.
The project now starts at `boot.tscn`, goes through the logos and the title
screen, and `NEW` loads the level.

---

## 8. What is guessed here, and what is missing

Kept separate on purpose, because a guess presented as a reading is the worst
failure available in this project.

**Read off the code:** everything in sections 1 to 6 above — the shell's loop
and its three bytes, `play_movie`'s table and its skip masks, the title
screen's rectangles, the menu's buttons and its 376-frame timeout, `PadRead`'s
inversion, the fourteen binding slots and all eleven schemes.

**Guessed, and marked as such in the code:**

* `TURN_RATE` in `player.gd`. `player_look` (`0x8002f5c0`) and `player_turn`
  (`0x8002fe1c`) hold the real rate and neither is transcribed.
* `FADE` and `STILL_FRAMES` in `opening.gd`. The first stands in for the fade
  `title_layer_a` runs itself; the second only matters when a movie could not
  be transcoded.
* The **title screen's** frame rate. It counts 376 frames, and whether that is
  six seconds or twelve depends on whether its loop runs at 60 or 30 — the same
  open question `player.gd`'s `TICK_HZ` carries. The *movies* are settled at 15
  a second, off the stream itself.

**Not done:**

* **`END.EXE` is not read.** Its own `play_movie` table names `\OP\M4.S`,
  `M5.S` and `M6.S`, and its symbols file has the library named and nothing
  else.
* **The save path.** `card_list_saves` finds the saves and `overlay_arg2`
  carries the answer, but `0x8001fa60` — the screen on the `GAME.EXE` side that
  reads it — is not read, so the port always starts a new game.
* **The menu's sounds.** `OP.D`'s trailing VAB is extracted and unparsed, so
  the cursor and confirm sounds — ids `0x5a` and `0x3a` into that bank — are
  silent in the port. The title *music* does play: it is `M2.S`'s XA track.
* **`tools/str.py` is slow.** It decodes any frame of any movie correctly, in
  pure Python, at seconds a frame. The port plays ffmpeg's transcodes instead.

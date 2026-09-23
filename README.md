# King's Field II, taken apart

Reverse-engineering notes and tools for the PlayStation game released in North
America as **King's Field II** (SLUS-00255; *King's Field III* in Japan), and a
port of its logic to Godot 4 that is being built one verified routine at a
time.

**This repository contains no part of the game.** No disc image, no
executables, no textures, models, sounds, movies or text. Every tool reads your
own copy of the disc, and everything it derives goes into `extract/` and
`out/`, which are never committed.

## What is here

| | |
| --- | --- |
| [FORMATS.md](FORMATS.md) | the file formats and the systems they drive, with the evidence for each claim |
| [BOOT.md](BOOT.md) | the chain from the entry point through the logos, the opening and the title menu |
| [FDAT.md](FDAT.md) | the `FDAT.T` archive, block by block |
| [MAP.md](MAP.md) | where each routine belongs in the frame |
| [OBJECTS.md](OBJECTS.md) | what an object does, opcode by opcode |
| [CONSTANTS.md](CONSTANTS.md) | the numbers in the code, and what each one means |
| [PORT.md](PORT.md) | which routines the Godot port reproduces, and how far each is checked |
| [BACKLOG.md](BACKLOG.md) | what is still unknown |
| [TOOLS.md](TOOLS.md) | every tool, and how to run it |
| [EXTERNAL.md](EXTERNAL.md) | other people's work on the series |
| [AGENT.md](AGENT.md) | how to work on this without repeating its mistakes |
| `tools/` | the Python that reads the disc, the executables and live RAM |
| `data/` | names for addresses, and why each one is believed |
| `emu/` | breakpoint scripts for PCSX-Redux |
| `godot/` | the port |

## Getting started

You need your own copy of SLUS-00255 as a raw image (`.bin`/`.img`, 2352 bytes
a sector), Python 3, and for the live tools PCSX-Redux; the port needs Godot 4.

```
python3 tools/psxiso.py path/to/image.bin extract
python3 tools/build.py
```

The first unpacks the disc into `extract/`; the second rebuilds everything
derived into `out/` and prints the checks the findings rest on. TOOLS.md goes
from there.

## Legal

This is an unofficial fan project for study and preservation. It is not
affiliated with or endorsed by FromSoftware, Sony Interactive Entertainment, or
any other rights holder of the game. *King's Field* and all related names are
trademarks of their owners.

The [licence](LICENSE) covers this project's own code and notes and nothing
else; it grants no rights in the game.

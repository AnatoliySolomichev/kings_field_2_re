#!/usr/bin/env python3
"""The memory card, and the saves King's Field II keeps on it.

    python3 tools/memcard.py               every save on the emulator's cards
    python3 tools/memcard.py 3             slot 3's fields
    python3 tools/memcard.py --check       the reading against the game's own
                                           save_restore and save_serialise

**How the game finds a save.** `0x8002860c`, which the load screen calls with
the slot the player picked, builds a name out of `bu00:` (`0x80011758`),
`BASLUS-00255` (`0x80081818`) and the slot's digit (`slot + 0x30`), opens it
through the BIOS, reads **0x6000 bytes** -- three of the card's 8 KB blocks --
and believes them only if `0x80028c74`, the sum of the 0x5c00 bytes from
`+0x400`, equals the word at `+0x200`. Then `save_restore` (`0x8005ffd0`) is
handed `+0x400`. The writer, `0x80028750`, does the same backwards: it zeroes
the 0x6000 bytes, `save_serialise`s into `+0x400`, sums them, and copies over
the first 0x280 a header built on its own stack -- `SC`, `0x13` (an icon of
three frames), 3 (blocks), the title in Shift-JIS from `0x80081828` with the
slot, the experience and the level put in by `0x80028b70`, the icon's palette
and frames stored out of VRAM -- with the sum at `+0x200`. So `+0x204..+0x280`
is whatever that stack held, and means nothing.

**The card itself is the console's**, not the game's: 16 blocks of 8 KB, the
first a directory of 128-byte frames, each naming a file's first block (state
`0x51`, then `0x52` and `0x53` down the chain, the next block at `+8`, the name
at `+0xa`). The BIOS reads it for the game; this reads it the same way.

**What `save_restore` puts where** is below, read off its 524 instructions:
57 fields one at a time and ten blocks copied whole. The level's five bytes
come first, and the level the game loads is their *first* byte, copied to
`current_level` and `0x8018fada` -- the block is not re-read for it. Of the
ten blocks, four were not named until this was written:

    0x80198588  0x3c0  the table build_seq_index fills at boot
    0x801b56cc  0x280  map_mark_seen's bits: 20 bytes, 160 of the map's
                       rectangles, for each of 32 maps
    0x80081780  0x96   150 bytes, one an item id, initialised in GAME.EXE
    0x80080718  0x96   150 more, the same

and the spells are not a block but **byte 0 of each of spell_table's 96
records**, 24 bytes apart.

**Checked**, both ways round, by running the game's own code (tools/mipsrun.py)
over a snapshot's RAM: `save_restore` handed each save on the cards and
twenty buffers of random bytes -- where a misplaced field cannot hide behind a
zero -- writes exactly the bytes this table says, where it says; and
`save_serialise` over every snapshot in `out/snap` builds exactly the buffer
this table builds from the same RAM. `--check` prints the counts.
"""
import json
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CARDS = [os.path.join(ROOT, "emu", "memcard1.mcd"), os.path.join(ROOT, "emu", "memcard2.mcd")]

CARD_SIZE = 0x20000
BLOCK = 0x2000
FRAME = 0x80
FIRST, MIDDLE, LAST = 0x51, 0x52, 0x53          # a directory frame's state
NAME = b"BASLUS-00255"                          # 0x80081818, then the slot's digit
FILE_SIZE = 0x6000                              # what 0x8002860c reads
SUM_AT = 0x200                                  # the word 0x80028c74's sum is held to
DATA_AT = 0x400                                 # what save_restore is handed
SUMMED = 0x5C00                                 # 0x80028c74's count
USED = 0x5ACE                                   # the last byte save_restore reads, + 1

SAVE_RESTORE = 0x8005FFD0
SAVE_SERIALISE = 0x8005F7BC
CURRENT_LEVEL, LEVEL_COPY = 0x8018FAD9, 0x8018FADA

# save_restore, one field at a time: (save offset, bytes, address, name).
# Runs of halves and bytes it moves one by one into consecutive addresses are
# one entry here; the loop of five that writes 0x801b2520 and 0x801b2512
# downwards is two.
FIELDS = [
    (0x0000, 5, 0x8018FAD8, "current_level_block"),
    (0x5694, 4, 0x801B25F0, "player_pos"),
    (0x5698, 4, 0x801B25F4, "player_y"),
    (0x569C, 4, 0x801B25F8, "player_pos+8"),
    (0x56A0, 4, 0x801B25FC, "player_pos+0xc"),
    (0x56A4, 4, 0x801B2610, "player_pitch, and the facing beside it"),
    (0x56A8, 4, 0x801B2614, "0x801b2614"),
    (0x56AC, 4, 0x801B2588, "play_minutes"),
    (0x56B0, 4, 0x801B24E4, "player_exp"),
    (0x56B4, 4, 0x801B24E8, "player_exp_next"),
    (0x56B8, 4, 0x801B2534, "player_gold"),
    (0x56BC, 4, 0x801B24EC, "0x801b24ec"),
    (0x56C0, 2, 0x801B2644, "0x801b2644"),
    (0x56C2, 2, 0x801B24FA, "player_hp_max"),
    (0x56C4, 2, 0x801B24FC, "player_hp"),
    (0x56C6, 2, 0x801B24FE, "player_mp_max"),
    (0x56C8, 2, 0x801B2500, "player_mp"),
    (0x56CA, 2, 0x801B2516, "player_stat_36"),
    (0x56CC, 10, 0x801B2518, "the five skills, 0x801b2518..0x801b2520"),
    (0x56D6, 2, 0x801B2522, "0x801b2522"),
    (0x56D8, 2, 0x801B2530, "0x801b2530"),
    (0x56DA, 2, 0x801B2508, "strong_blows"),
    (0x56DC, 10, 0x801B250A, "0x801b250a..0x801b2512"),
    (0x56E6, 2, 0x801B2514, "0x801b2514"),
    (0x56E8, 2, 0x801B255C, "poison_frames"),
    (0x56EA, 28, 0x801B255E, "the curse and the timers, 0x801b255e..0x801b2578"),
    (0x5706, 1, 0x801B24F0, "player_level"),
    (0x5707, 1, 0x801B24F1, "0x801b24f1"),
    (0x5708, 7, 0x801B25D4, "what is worn, 0x801b25d4..0x801b25da"),
    (0x570F, 3, 0x801B25AB, "the spells in hand and the button's thing"),
    (0x5712, 1, 0x801B25AF, "equipped_weapon"),
    (0x5713, 10, 0x801B25DB, "0x801b25db..0x801b25e4, hud_style and compass_style among them"),
]

# ...and the blocks it copies whole: (save offset, bytes, address, stride, name).
BLOCKS = [
    (0x0008, 0x100, 0x801BA988, 1, "story_flags"),
    (0x0108, 0x5000, 0x801BAA88, 1, "level_state"),
    (0x5108, 0x40, 0x801BFA88, 1, "level_state_index"),
    (0x5148, 0x3C0, 0x80198588, 1, "build_seq_index's table"),
    (0x5508, 0x12C, 0x800C85E8, 1, "inventory_a and inventory_b"),
    (0x5634, 0x60, 0x801B77EC, 24, "spell_table's byte 0, one a spell"),
    (0x571E, 0x280, 0x801B56CC, 1, "map_mark_seen's bits, 20 bytes a map"),
    (0x599E, 0x96, 0x80081780, 1, "150 bytes, one an item id"),
    (0x5A34, 0x96, 0x80080718, 1, "150 more"),
    (0x5ACA, 4, 0x8009C22C, 1, "four bytes"),
]


# --- the card ---------------------------------------------------------------

def directory(card):
    """[(frame, state, size, next block, name)] for every frame in use."""
    out = []
    for i in range(1, 16):
        f = card[i * FRAME:(i + 1) * FRAME]
        state, size, nxt = struct.unpack_from("<IIH", f, 0)
        if state & 0xF0 == 0x50:
            out.append((i, state, size, nxt, f[0xA:0xA + 21].split(b"\0")[0]))
    return out


def files(card):
    """{name: bytes} for every file, its blocks followed down the chain."""
    out = {}
    for i, state, size, _nxt, name in directory(card):
        if state != FIRST:
            continue
        data, b, seen = b"", i - 1, set()
        while b not in seen and 0 <= b < 15:
            seen.add(b)
            data += card[(b + 1) * BLOCK:(b + 2) * BLOCK]
            b = struct.unpack_from("<H", card, (b + 1) * FRAME + 8)[0]
        out[name.decode("ascii", "replace")] = data[:size]
    return out


def saves(paths=None):
    """[(card path, slot, the file's 0x6000 bytes)], the slots as the game
    names them."""
    out = []
    for path in paths or CARDS:
        if not os.path.exists(path):
            continue
        card = open(path, "rb").read()
        if len(card) != CARD_SIZE or card[:2] != b"MC":
            continue
        for name, data in sorted(files(card).items()):
            tail = name[len(NAME):]
            if name.startswith(NAME.decode()) and len(tail) == 1 and tail.isdigit():
                out.append((path, int(tail), data))
    return out


def checksum(f):
    """0x80028c74: the sum of the 0x5c00 bytes from +0x400."""
    return sum(f[DATA_AT:DATA_AT + SUMMED]) & 0xFFFFFFFF


def valid(f):
    return len(f) >= FILE_SIZE and checksum(f) == struct.unpack_from("<I", f, SUM_AT)[0]


def title(f):
    """The header's title, the Shift-JIS turned into plain text."""
    s = f[4:0x44].split(b"\0")[0].decode("shift_jis", "replace")
    out = []
    for ch in s:
        c = ord(ch)
        if 0xFF01 <= c <= 0xFF5E:
            out.append(chr(c - 0xFEE0))
        elif ch == "　":
            out.append(" ")
        else:
            out.append({"’": "'", "−": "-"}.get(ch, ch))
    return " ".join("".join(out).split())


# --- the fields ---------------------------------------------------------------

def restore(buf):
    """{address: byte}: what save_restore writes, handed `buf` (the file from
    +0x400)."""
    out = {}
    for off, n, addr, _name in FIELDS:
        for k in range(n):
            out[addr + k] = buf[off + k]
    out[CURRENT_LEVEL] = out[LEVEL_COPY] = buf[0]
    for off, n, addr, stride, _name in BLOCKS:
        for k in range(n):
            out[addr + k * stride] = buf[off + k]
    return out


def serialise(rd):
    """save_serialise's buffer, 0x5c00 bytes, from `rd(address) -> byte`."""
    buf = bytearray(SUMMED)
    for off, n, addr, _name in FIELDS:
        for k in range(n):
            buf[off + k] = rd(addr + k)
    for off, n, addr, stride, _name in BLOCKS:
        for k in range(n):
            buf[off + k] = rd(addr + k * stride)
    return bytes(buf)


def fields(buf):
    """The save as names and numbers, for reading."""
    def u(off, n, signed=False):
        return int.from_bytes(buf[off:off + n], "little", signed=signed)
    face = u(0x56A4, 4)
    idx = struct.unpack_from("<32H", buf, 0x5108)
    return {
        "level": buf[0], "block": list(buf[0:5]),
        "pos": [u(0x5694, 4, True), u(0x5698, 4, True), u(0x569C, 4, True)],
        "pitch": face & 0xFFFF, "facing": face >> 16,
        "minutes": u(0x56AC, 4), "exp": u(0x56B0, 4), "exp_next": u(0x56B4, 4),
        "gold": u(0x56B8, 4), "level_of_player": buf[0x5706],
        "hp": [u(0x56C4, 2), u(0x56C2, 2)], "mp": [u(0x56C8, 2), u(0x56C6, 2)],
        "stat36": u(0x56CA, 2),
        "skills": [u(0x56CC + 2 * k, 2) for k in range(5)],
        "worn": list(buf[0x5708:0x570F]), "weapon": buf[0x5712],
        "spell_a": buf[0x570F], "spell_b": buf[0x5710], "item_b": buf[0x5711],
        "inventory": {k: buf[0x5508 + k] for k in range(150) if buf[0x5508 + k]},
        "inventory_b": {k: buf[0x559E + k] for k in range(150) if buf[0x559E + k]},
        "spells": [k for k in range(96) if buf[0x5634 + k]],
        "flags": {k: buf[8 + k] for k in range(256) if buf[8 + k]},
        "levels_kept": [k for k in range(32) if idx[k] != 0xFFFF],
    }


# --- the check --------------------------------------------------------------

BUFFER = 0x801F0000             # free RAM in a snapshot, above the overlay's end


def _snapshots():
    """The snapshots with GAME.EXE in them: the code of both routines as the
    executable has it (one taken over another program has something else
    there)."""
    import mips
    snap = os.path.join(ROOT, "out", "snap")
    if not os.path.isdir(snap):
        return []
    exe = mips.load("game")
    code = [(a, exe.bytes(a, 0x40)) for a in (SAVE_RESTORE, SAVE_SERIALISE)]
    out = []
    for f in sorted(os.listdir(snap)):
        if f.endswith(".ram"):
            ram = open(os.path.join(snap, f), "rb").read()
            if all(ram[a & 0x1FFFFF:(a & 0x1FFFFF) + len(b)] == b for a, b in code):
                out.append(os.path.join(snap, f))
    return out


def check(out=sys.stdout):
    import mipsrun
    ok = True
    found = saves()
    good = sum(1 for _p, _s, f in found if valid(f))
    print(f"  saves on the cards: {len(found)}, {good} of them with the game's "
          f"checksum right", file=out)
    ok &= good == len(found)

    snaps = _snapshots()
    if not snaps:
        print("  no snapshots in out/snap: the game's own routines not run", file=out)
        return ok
    base = open(snaps[0], "rb").read()
    rng = random.Random(0x5A7E)
    cases = [(f"slot {s}", f[DATA_AT:DATA_AT + SUMMED]) for _p, s, f in found]
    cases += [(f"random {k}", bytes(rng.randrange(256) for _ in range(SUMMED)))
              for k in range(20)]
    total = same = 0
    for label, buf in cases:
        cpu = mipsrun.CPU(base)
        for k in range(0, SUMMED, 4):
            cpu.wr(BUFFER + k, 4, int.from_bytes(buf[k:k + 4], "little"))
        got = {}
        wr = cpu.wr

        def log(a, n, v, wr=wr, got=got):
            for k in range(n):
                got[(a + k) & 0x1FFFFFFF] = (v >> (8 * k)) & 0xFF
            wr(a, n, v)
        cpu.wr = log
        cpu.call(SAVE_RESTORE, BUFFER)
        want = {a & 0x1FFFFFFF: v for a, v in restore(buf).items()}
        keys = set(want) | set(got)
        n = sum(1 for a in keys if want.get(a) == got.get(a) and a in want and a in got)
        total += len(keys)
        same += n
        if n != len(keys):
            bad = sorted(a for a in keys if want.get(a) != got.get(a))[:4]
            print(f"  {label}: {n} of {len(keys)} -- e.g. "
                  + ", ".join(f"{0x80000000 | a:#x} game {got.get(a)} here {want.get(a)}"
                              for a in bad), file=out)
            ok = False
    print(f"  save_restore, the game's, handed {len(cases)} buffers ({len(found)} "
          f"saves, {len(cases) - len(found)} random): {same} of {total} bytes "
          f"written where and as this table says", file=out)

    total = same = 0
    for path in snaps:
        ram = open(path, "rb").read()
        cpu = mipsrun.CPU(ram)
        for k in range(0, SUMMED, 4):
            cpu.wr(BUFFER + k, 4, 0)
        cpu.call(SAVE_SERIALISE, BUFFER)
        game = bytes(cpu.ram[BUFFER & 0x1FFFFF:(BUFFER & 0x1FFFFF) + SUMMED])
        mine = serialise(lambda a: ram[a & 0x1FFFFF])
        n = sum(1 for x, y in zip(game, mine) if x == y)
        total += SUMMED
        same += n
        if n != SUMMED:
            k = next(i for i in range(SUMMED) if game[i] != mine[i])
            print(f"  {os.path.basename(path)}: {n} of {SUMMED}, first at +{k:#x}", file=out)
            ok = False
    print(f"  save_serialise, the game's, over {len(snaps)} snapshots: {same} of "
          f"{total} bytes as this table builds them", file=out)
    return ok


def export(out_dir):
    """cards.json -- the emulator's card files, by absolute path, which the
    port reads at the title (godot/card.gd) -- and savecheck.json, what this
    makes of them and its table, for godot/selftest.gd to hold the port's
    reading to."""
    cards = [os.path.abspath(p) for p in CARDS]
    with open(os.path.join(out_dir, "cards.json"), "w") as fh:
        json.dump({"cards": cards}, fh, indent=1)
    rows = [{"path": os.path.abspath(p), "slot": s, "title": title(f), "sum": checksum(f),
             "valid": valid(f), "level": f[DATA_AT], "pos": fields(f[DATA_AT:])["pos"]}
            for p, s, f in saves()]
    path = os.path.join(out_dir, "savecheck.json")
    with open(path, "w") as fh:
        json.dump({"fields": [[o, n, a] for o, n, a, _nm in FIELDS],
                   "blocks": [[o, n, a, st] for o, n, a, st, _nm in BLOCKS],
                   "saves": rows}, fh, separators=(",", ":"))
    return path


def show(slot=None, out=sys.stdout):
    found = saves()
    if not found:
        print("no King's Field II saves on " + ", ".join(CARDS), file=out)
        return
    for path, s, f in found:
        if slot is not None and s != slot:
            continue
        buf = f[DATA_AT:]
        d = fields(buf)
        print(f"{os.path.relpath(path, ROOT)} slot {s}: {title(f)!r}"
              f"{'' if valid(f) else '  (the checksum is wrong: the game would refuse it)'}",
              file=out)
        print(f"  level {d['level']} at {d['pos']} facing {d['facing']:#x}, "
              f"{d['minutes']} minutes; HP {d['hp'][0]}/{d['hp'][1]} MP "
              f"{d['mp'][0]}/{d['mp'][1]}, level {d['level_of_player']}, "
              f"{d['exp']} exp, {d['gold']} gold", file=out)
        if slot is not None:
            for k in ("block", "pitch", "stat36", "skills", "worn", "weapon", "spell_a",
                      "spell_b", "item_b", "inventory", "inventory_b", "spells", "flags",
                      "levels_kept"):
                print(f"  {k:12s} {d[k]}", file=out)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--check":
        sys.exit(0 if check() else 1)
    show(int(a[0]) if a else None)

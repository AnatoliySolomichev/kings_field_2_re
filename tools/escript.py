#!/usr/bin/env python3
"""The conversation language, and every conversation in the game decoded.

    python3 tools/escript.py            the language, then a census
    python3 tools/escript.py 0          level 0, every conversation disassembled
    python3 tools/escript.py flags      which flag is tested where
    python3 tools/escript.py check      replay the traces emu/bp21.lua recorded

A talking entity's **block 0** — the `u32` at `record+0x38`, relocated by
`entity_table_init` — begins with the byte `0x70`, and that byte is what
`script_interpreter` (`0x8005c308`) tests before it will run anything. There
are **43 such blocks in the game**, one per entity that talks. Every other
block belongs to something else; see `tools/entities.py`.

The block is a 20-byte header and then code:

    +0x00  0x70, the tag
    +0x01  the animation handed to 0x8005c0d4 while a line is on screen,
           0xff for none
    +0x08  u16, that animation's second argument
    +0x0c  u16, the TALK.T entry a line counts from
    +0x0e  u16, the closing animation's argument
    +0x10  u8   the program counter, which the interpreter keeps here
    +0x11  u8   the closing animation, 0xff for none
    +0x12  u8   what happens when the talking stops -- see SERVICE below
    +0x13  u8   the retry flag
    +0x14  the code, and `pc` counts from here

**Starting.** `script_prescan` (`0x8005c1e8`) reads the code from pc 0. The
code opens with a chain of four-byte guards

    f1 <flag> <value> <label>

and the **first** guard whose `story_flags[flag] == value` wins: the script
starts at that label instead, provided the label is further on than the pc
already stored. The chain ends with a lone `0xfe`; if no guard matched and the
pc is 0 the script starts at the byte after it, which is why a fresh
conversation's first opcode is at **pc 1** when there are no guards. If the pc
is not 0 the conversation resumes where it stopped -- an entity remembers.

**The opcodes.** Anything below `0xf0`, and `0xf1` and `0xfa`..`0xfe`, is a
line: the interpreter drives the animation, calls `render_frame`, loads
`TALK.T[base + byte]` through `load_entry(7, ...)` and waits for the use
button. `0xf0`..`0xff` dispatch through `script_opcode_table` (`0x80013160`):

    f0 n   pc -= n, and set the retry flag
    f2 n   a **label**, and a two-byte no-op when it is executed
    f3     spend one of the run-on count
    f4 a n call the level's own code -- `[0x8018fae0]->+0x10(actor, a)` -- and
           then take `n` as a run-on count
    f5 n   run the next n lines without waiting
    f6     copy the actor's +1 into script_speaker, clear the retry flag
    f7 i v story_flags[i] = v
    f8 n   pc -= n
    f9 i v t  if story_flags[i] == v, jump to **label** t
    ff     stop

**`f9` and the guards jump to a label, not to an offset.** `0x8005c18c`
resolves one: it scans the code from pc 0 for a `0xf2` byte, compares the byte
after it with the label, and lands on the byte after that. The scan is over
bytes, not instructions, so an operand that happens to be `0xf2` is a label as
far as it is concerned -- and it gives up at the first `0xff`, so a label
after the first stop is unreachable. Both are reproduced here.

**What is in the 43.** 593 lines, 105 `f8`, 79 `f2`, 60 `f9`, 60 `f4`, 57
`f0`, 55 `f5`, 43 `ff` -- and **no `f7`, `f3` or `f6` anywhere**. Scripts
*test* story flags and never set one; something else writes them.

**Withdrawn.** Everything this file said before came from decoding blocks
1..15 of each record as if they were scripts -- 1086 of them, "12 179 plain
instructions, 876 ends, four conditionals". They are not scripts and that
whole census is gone, along with "six `f4` calls in the game" (there are 60)
and the 1086-of-1086 agreement with `godot/escript.gd`, which was two copies
agreeing about the wrong bytes. `emu/bp21.lua` caught it: the game ran
`04 05 06 07 08 09 f0 01` for level 0's entity 9 where this file had `02 00
ff`, and `tools/escript.py check` now replays that recording instead.
"""
import collections
import json
import os
import struct
import sys

sys.path.insert(0, "tools")
import entities                                                      # noqa: E402

FLAGS = 0x801BA988
TALK = 7
INTERPRETER = 0x8005C308
PRESCAN = 0x8005C1E8
FIND_LABEL = 0x8005C18C
HEADER = 0x14                  # the code starts here, and pc counts from here
FLAG_COUNT = 0x80

# opcode -> (length, mnemonic). Read off the sixteen arms of
# `script_opcode_table` (0x80013160). Length None would mean "ends the script";
# 0xff is one byte and stops.
OPS = {
    0xF0: (2, "loop_back"),        # pc -= arg, and set the retry flag at +0x13
    0xF2: (2, "label"),
    0xF3: (1, "run_on"),           # spend one of the run-on count
    0xF4: (3, "call_overlay"),     # level_hooks->+0x10(actor, arg), then a count
    0xF5: (2, "no_wait"),          # run this many more lines without waiting
    0xF6: (1, "set_speaker"),      # script_speaker = actor[+1]; clears the retry
    0xF7: (3, "set_flag"),         # story_flags[arg1] = arg2
    0xF8: (2, "jump_back"),        # pc -= arg
    0xF9: (4, "if_flag"),          # story_flags[arg1] == arg2 -> label arg3
    0xFF: (1, "end"),
}

# What `script_interpreter`'s .L19 does with the header's +0x12 once a line is
# not run on from: the high nibble picks the arm and the low nibble is its
# argument. All five arms first call 0x80030568.
SERVICE = {
    0x00: "0x80021114(n)",
    0x10: "nothing further",
    0x20: "nothing further",
    0x30: "the shop: 0x80021aac, then load_entry(6, item + 0x1e8)",
    0x40: "0x8002200c(n), then [0x801e824c] = 1 and [0x801e8260] = n & 3",
}
NO_SERVICE = 0xFF              # +0x12 == 0xff is also what lets the use button
                               # add to the run-on count


def is_line(op):
    """The arms that fall through to the dialogue handler at .L14."""
    return op < 0xF0 or op in (0xF1, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE)


def header(raw, base, rec):
    """The 20 bytes at block 0, or None when this entity does not talk."""
    if len(rec) < entities.PTRS + 4:
        return None
    off = struct.unpack_from("<I", rec, entities.PTRS)[0]
    if off == 0xFFFFFFFF:
        return None
    p = base + off
    if not (0 <= p < len(raw) - HEADER) or raw[p] != entities.CONVERSATION:
        return None
    return off


def fields(raw, base, off):
    """The header read out, as `script_interpreter` reads it."""
    p = base + off
    return {"anim": raw[p + 1], "anim_arg": struct.unpack_from("<H", raw, p + 8)[0],
            "talk": struct.unpack_from("<H", raw, p + 0x0C)[0],
            "end_arg": struct.unpack_from("<H", raw, p + 0x0E)[0],
            "pc": raw[p + 0x10], "end_anim": raw[p + 0x11],
            "service": raw[p + 0x12], "retry": raw[p + 0x13]}


def conversations(levels=range(28)):
    """Yield (level, entity index, record, header fields, code bytes)."""
    for lv in levels:
        raw, base, recs = entities.entry(lv)
        if not recs:
            continue
        span = entities.spans(raw, base, recs)
        for k, (rec, offs) in enumerate(recs):
            off = header(raw, base, rec)
            if off is None:
                continue
            end = span[off][1]
            yield lv, k, rec, fields(raw, base, off), raw[base + off + HEADER:base + end]


def find_label(code, want):
    """`0x8005c18c`: the pc just past `f2 <want>`, or None.

    A byte scan, not an instruction scan, and it gives up at the first 0xff.
    """
    i = 0
    while i < len(code):
        b = code[i]
        i += 1
        if b == 0xF2:
            if i < len(code) and code[i] == want:
                return i + 1
            i += 1
        elif b == 0xFF:
            return None
    return None


def guards(code):
    """[(pc, flag, value, label)] for the chain at the head, and where it ends."""
    out, i = [], 0
    while i + 3 < len(code) and code[i] == 0xF1:
        out.append((i, code[i + 1], code[i + 2], code[i + 3]))
        i += 4
    return out, i


def start_pc(code, flags=None, pc=0):
    """`script_prescan`: where a conversation begins.

    The first guard that holds wins, and only if its label is further on than
    the pc already stored. With no guard holding, a stored pc resumes and a
    zero one starts just past the `0xfe`.
    """
    f = flags if flags is not None else [0] * FLAG_COUNT
    chain, stop = guards(code)
    for _at, flag, value, label in chain:
        if flag < len(f) and f[flag] == value:
            t = find_label(code, label)
            return t if t is not None and t > pc else pc
    if stop < len(code) and code[stop] == 0xFE and pc == 0:
        return stop + 1
    return pc


def decode(code, start=0):
    """[(pc, opcode, operands, mnemonic)] laid out linearly from `start`."""
    out, i = [], start
    while i < len(code):
        op = code[i]
        if is_line(op):
            out.append((i, op, (), "say"))
            i += 1
            continue
        n, mn = OPS.get(op, (1, f"op_{op:02x}"))
        out.append((i, op, tuple(code[i + 1:i + n]), mn))
        i += n
    return out


def run(code, flags=None, limit=400, stop_on_loop=True):
    """Step a conversation the way `script_interpreter` steps it.

    What is reproduced is the **order of execution**: every line is taken at
    once, where the game stops at each one until the use button is pressed.
    Returns `(trace, talk, why)` -- `trace` is `[(pc, opcode)]`, `talk` is the
    TALK.T offsets the lines asked for, and `why` is `end`, `loop` (came back
    to a pc it had already run, with nothing between to change it), `off` or
    `limit`. A conversation that ends on `f0` really does loop for ever in
    play -- the game repeats the last line every time the button is pressed --
    so `stop_on_loop=False` runs it out to the limit instead, which is what
    replaying a recording needs.
    """
    f = list(flags) if flags is not None else [0] * FLAG_COUNT
    pc = start_pc(code, f)
    trace, talk, seen = [], [], set()
    for _step in range(limit):
        if not 0 <= pc < len(code):
            return trace, talk, "off"
        op = code[pc]
        if stop_on_loop and (pc, op) in seen and op == 0xF0:
            trace.append((pc, op))
            return trace, talk, "loop"
        seen.add((pc, op))
        trace.append((pc, op))
        if is_line(op):
            talk.append(op)
            pc += 1
            continue
        if op == 0xFF:
            return trace, talk, "end"
        if op in (0xF0, 0xF8):
            pc -= code[pc + 1] if pc + 1 < len(code) else 0
            continue
        if op == 0xF9:
            i, v, label = (code[pc + 1], code[pc + 2], code[pc + 3])
            if i < len(f) and f[i] == v:
                t = find_label(code, label)
                pc = t if t is not None else pc + 4
            else:
                pc += 4
            continue
        if op == 0xF7 and pc + 2 < len(code):
            if code[pc + 1] < len(f):
                f[code[pc + 1]] = code[pc + 2]
        pc += OPS.get(op, (1, ""))[0]
    return trace, talk, "limit"


def visits(code, flags=None, count=16, limit=400):
    """What the entity says on the first visit, the second, and so on.

    This is the mechanic the language is built around. `f0` is a **section
    break**: running it sets the retry flag and jumps back onto the line
    before it, so pressing the button again repeats that last line for ever.
    What moves the conversation on is talking to *somebody else*:
    `script_interpreter` compares the global `script_speaker`
    (`0x801baa2e`, the previous talker's `actor[+1]`) against this actor's,
    and when they differ and the retry flag is set it scans forward from the
    stored pc to the next `f0` and resumes just past it. `f8` jumps back
    without setting the flag, so a section that ends on one repeats for ever
    and is where an entity runs out of things to say.

    Returns `[[TALK.T offsets], ...]`, one list per visit, stopping early at
    an `ff` or when a visit says nothing new.
    """
    f = list(flags) if flags is not None else [0] * FLAG_COUNT
    pc, retry, out = 0, 0, []
    for _ in range(count):
        p = start_pc(code, f, pc)
        if retry:
            i = p
            while i < len(code) and code[i] != 0xF0:
                i += 1
            p = min(i + 2, len(code))
            retry = 0
        said = []
        why = "off"
        for _step in range(limit):
            if not 0 <= p < len(code):
                why = "off"
                break
            op = code[p]
            if is_line(op):
                said.append(op)
                p += 1
                continue
            if op == 0xFF:
                why = "end"
                break
            if op == 0xF0:                       # the section break
                retry, why = 1, "break"
                break
            if op == 0xF8:                       # nothing more, for ever
                why = "repeat"
                break
            if op == 0xF9:
                i, v, label = code[p + 1], code[p + 2], code[p + 3]
                t = find_label(code, label) if i < len(f) and f[i] == v else None
                p = t if t is not None else p + 4
                continue
            if op == 0xF7 and p + 2 < len(code) and code[p + 1] < len(f):
                f[code[p + 1]] = code[p + 2]
            p += OPS.get(op, (1, ""))[0]
        out.append(said)
        pc = p
        if why in ("end", "repeat", "off"):
            break
    return out


def render(code, base=0, text=None):
    """Human-readable lines for one conversation."""
    text = text or {}
    chain, stop = guards(code)
    lines = []
    for at, flag, value, label in chain:
        lines.append(f"  {at:3d}: start at label {label} if flags[{flag}] == {value}")
    if stop < len(code) and code[stop] == 0xFE:
        lines.append(f"  {stop:3d}: (start here)")
    begin = stop + 1 if stop < len(code) and code[stop] == 0xFE else stop
    for off, op, args, mn in decode(code, begin):
        if mn == "say":
            entry = base + op
            said = text.get(entry, "")
            lines.append(f"  {off:3d}: say TALK[{entry}]" + (f"   {said[:62]}" if said else ""))
        elif mn == "if_flag" and len(args) == 3:
            lines.append(f"  {off:3d}: if flags[{args[0]}] == {args[1]} goto label {args[2]}")
        elif mn == "label" and args:
            lines.append(f"  {off:3d}: label {args[0]}:")
        elif mn == "call_overlay" and len(args) == 2:
            lines.append(f"  {off:3d}: level_hooks->0x10(actor, {args[0]}), "
                         f"then {args[1]} without waiting")
        elif mn == "end":
            lines.append(f"  {off:3d}: end")
        else:
            lines.append(f"  {off:3d}: {mn} {' '.join(str(x) for x in args)}")
    return lines


def talk_text():
    """TALK.T entry -> its first line, from the OCR pass, when we have one."""
    import pickle
    try:
        d = pickle.load(open("out/text.pkl", "rb"))["TALK"]
    except (OSError, KeyError):
        return {}
    out = {}
    for i, ents in d.items():
        for t, q in ents:
            if q < 0.15 and t.strip():
                out[i] = " ".join(t.split())
                break
    return out


def flag_graph():
    """flag -> [(level, entity, value, where)] for every test in the game."""
    g = collections.defaultdict(list)
    for lv, k, _rec, h, code in conversations():
        chain, _stop = guards(code)
        for at, flag, value, _label in chain:
            g[flag].append((lv, k, value, "guard"))
        for off, op, args, mn in decode(code):
            if mn == "if_flag" and len(args) == 3:
                g[args[0]].append((lv, k, args[1], f"pc {off}"))
    return g


def export(out_dir, levels=range(28)):
    """Every conversation in the game, and the trace `run` makes of it."""
    rows = []
    for lv, k, rec, h, code in conversations(levels):
        trace, talk, why = run(code)
        rows.append({"level": lv, "entity": k, "kind": rec[0], "header": h,
                     "code": list(code)[:256], "steps": len(trace), "why": why,
                     "talk": [h["talk"] + t for t in talk][:64],
                     "last": trace[-1][0] if trace else -1})
    path = os.path.join(out_dir, "escript.json")
    with open(path, "w") as fh:
        json.dump({"_note": "every conversation in the game -- FDAT.T entry 3n+1, "
                            "block 0 of each entity record, kind 0x70 -- with the "
                            "trace tools/escript.py run() makes of it",
                   "scripts": rows}, fh, separators=(",", ":"))
    return path


# What emu/bp21.lua recorded while the game was played on 2026-09-22: the
# instruction stream of two real conversations, pc and opcode as
# `script_interpreter` fetched them, and the TALK.T entry each line loaded.
RECORDED = [
    {"level": 0, "entity": 9, "cell": (62, 5),
     "trace": [(1, 0x04), (2, 0x05), (3, 0x06), (4, 0x07), (5, 0x08), (6, 0x09),
               (7, 0xF0), (6, 0x09), (7, 0xF0), (6, 0x09), (7, 0xF0),
               (6, 0x09), (7, 0xF0), (6, 0x09)],
     "talk": [680, 681, 682, 683, 684, 685, 685, 685, 685, 685]},
    {"level": 0, "entity": 7, "cell": (28, 60),
     "trace": [(1, 0x00)], "talk": [124]},
]


def check():
    """Replay the recording. The game is the answer; this file is the claim."""
    ok = bad = 0
    for rec in RECORDED:
        lv, k = rec["level"], rec["entity"]
        got = next((c for c in conversations([lv]) if c[1] == k), None)
        if got is None:
            print(f"level {lv} entity {k}: no conversation block found")
            bad += 1
            continue
        _lv, _k, _r, h, code = got
        trace, talk, why = run(code, limit=len(rec["trace"]),
                               stop_on_loop=False)
        want_t = rec["trace"]
        mine = trace[:len(want_t)]
        said = [h["talk"] + t for t in talk][:len(rec["talk"])]
        for n, (w, m) in enumerate(zip(want_t, mine)):
            if w == m:
                ok += 1
            else:
                bad += 1
                print(f"  L{lv}/e{k} step {n}: game ran pc={w[0]} op={w[1]:#04x}, "
                      f"this file runs pc={m[0]} op={m[1]:#04x}")
        if len(mine) < len(want_t):
            bad += len(want_t) - len(mine)
            print(f"  L{lv}/e{k}: the game ran {len(want_t)} steps, this file {len(mine)} ({why})")
        for n, (w, m) in enumerate(zip(rec["talk"], said)):
            if w == m:
                ok += 1
            else:
                bad += 1
                print(f"  L{lv}/e{k} line {n}: game loaded TALK[{w}], this file TALK[{m}]")
        if len(said) < len(rec["talk"]):
            bad += len(rec["talk"]) - len(said)
    print(f"{ok} of {ok + bad} recorded steps and lines reproduced")
    return bad == 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "check":
        sys.exit(0 if check() else 1)
    elif arg == "flags":
        g = flag_graph()
        print(f"{len(g)} distinct flags tested, array at {FLAGS:#x}\n")
        for f in sorted(g):
            t = g[f]
            print(f"flag {f:3d}: tested {len(t):3d}x  " +
                  ", ".join(f"L{lv}/e{k}=={v} ({w})" for lv, k, v, w in t[:6]))
    elif arg is not None:
        lv = int(arg)
        text = talk_text()
        for _lv, k, rec, h, code in conversations([lv]):
            svc = ("none" if h["service"] == NO_SERVICE
                   else SERVICE.get(h["service"] & 0xF0, "?") + f"  n={h['service'] & 0xF:#x}")
            print(f"=== level {lv} entity {k} (kind {rec[0]:#04x}, TALK base {h['talk']}, "
                  f"anim {h['anim']:#04x}, after: {svc}) ===")
            for line in render(code, h["talk"], text):
                print(line)
            trace, talk, why = run(code)
            print(f"  -- {len(trace)} steps, stops: {why}")
            vs = visits(code)
            print(f"  -- {len(vs)} visits before it runs dry: " +
                  " | ".join("+".join(str(h["talk"] + t) for t in v) or "-" for v in vs))
            print()
    else:
        print(__doc__)
        n = collections.Counter()
        for lv, k, rec, h, code in conversations():
            n["conversations"] += 1
            chain, _stop = guards(code)
            n["guards"] += len(chain)
            for off, op, args, mn in decode(code):
                n[mn] += 1
        print("across every conversation in the game:")
        for key, v in n.most_common():
            print(f"  {key:16s} {v}")

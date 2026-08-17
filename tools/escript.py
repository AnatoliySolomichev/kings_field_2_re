#!/usr/bin/env python3
"""The entity script language, and every script in the game decoded.

    python3 tools/escript.py            what each opcode is, then a summary
    python3 tools/escript.py 0          level 0, every script disassembled
    python3 tools/escript.py flags      which flag is set where and tested where

The interpreter is `0x8005c308`. It fetches a byte, and anything from 0xf0 up
is dispatched through a 16-entry jump table at `0x80013160`; anything below is
a line of dialogue. That is the whole language:

    < 0xf0   one byte, and what it means depends on the entity. The handler
             first drives an animation through 0x8005c0d4, and then, only when
             the entity's kind byte is 0x2b, loads TALK.T[base + opcode] --
             archive 7, through the same `load_entry` as every other bit of
             text. So a talker says a line and everything else plays a frame.
             0xf1 and 0xfa..0xfe dispatch to this same handler.
    0xf0 n   jump back n bytes, and set the header's retry flag
    0xf2     skip, two bytes
    0xf3     skip, one byte
    0xf4     skip, one byte
    0xf5     skip, one byte
    0xf6     copy the actor's byte +1 into 0x801baa2e
    0xf7 i v flags[i] = v
    0xf8 n   jump back n bytes
    0xf9 i v t   if flags[i] == v, jump to label t; else fall through, 4 bytes
    0xff     end

`flags` is a byte array at **0x801ba988** -- game state, nine pieces of code
reach it, among them `apply_level_state`, `object_trigger` and the object
interaction handler.

Entity scripts **barely** branch. 1086 of them decode to 12 179 plain
instructions, 876 ends, and four `0xf9` conditionals with no `0xf7` anywhere:
two on flag 0 (`== 10`, levels 24 and 27) and two on flag 14 (`== 0`, levels 11
and 13). Flag 0 is the progress counter, so a late entity gating on it reads
true, but four instances in twelve thousand instructions is thin enough to want
confirming in play.

An earlier pass reported *zero* conditionals across 1350 scripts. That was the
wrong script base -- `entities.py` explains which -- and the claim is withdrawn.
"""
import collections
import pickle
import sys

sys.path.insert(0, "tools")
import entities                                                      # noqa: E402

FLAGS = 0x801BA988
TALK = 7
INTERPRETER = 0x8005C308

# opcode -> (length, mnemonic). Length None means "ends the script".
OPS = {
    0xF0: (2, "loop_back"),
    0xF2: (2, "skip2"),
    0xF3: (1, "skip1"),
    0xF4: (1, "skip1"),
    0xF5: (1, "skip1"),
    0xF6: (1, "set_actor_byte"),
    0xF7: (3, "set_flag"),
    0xF8: (2, "jump_back"),
    0xF9: (4, "if_flag"),
    0xFF: (1, "end"),
}


def decode(code):
    """[(offset, opcode, operands, mnemonic)] for one script slice."""
    out, i = [], 0
    while i < len(code):
        op = code[i]
        if op < 0xF0 or op in (0xF1, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE):
            out.append((i, op, (), "say"))     # animation frame, or a line
            i += 1
            continue
        n, mn = OPS.get(op, (1, f"op_{op:02x}"))
        out.append((i, op, tuple(code[i + 1:i + n]), mn))
        i += n
        if op == 0xFF:
            break
    return out


def talk_text():
    """TALK.T entry -> its first line, from the OCR pass, when we have one."""
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


TALKER = 0x2B          # the only entity kind whose bytes reach TALK.T


def render(code, base=0, text=None, kind=None):
    """Human-readable lines for one script.

    `kind` is the entity's byte +0. Only 0x2b reaches TALK.T; for every other
    kind the same byte drives an animation, and printing a line of dialogue
    beside it would be an invention.
    """
    text = text or {}
    talker = kind == TALKER
    lines = []
    for off, op, args, mn in decode(code):
        if mn == "say" and talker:
            entry = base + op
            said = text.get(entry, "")
            lines.append(f"  {off:3d}: say TALK[{entry}]" + (f"   {said[:66]}" if said else ""))
        elif mn == "say":
            lines.append(f"  {off:3d}: frame {op}")
        elif mn == "set_flag":
            lines.append(f"  {off:3d}: flags[{args[0]}] = {args[1]}"
                         if len(args) == 2 else f"  {off:3d}: set_flag ?")
        elif mn == "if_flag":
            lines.append(f"  {off:3d}: if flags[{args[0]}] == {args[1]} goto {args[2]}"
                         if len(args) == 3 else f"  {off:3d}: if_flag ?")
        elif mn in ("jump_back", "loop_back"):
            lines.append(f"  {off:3d}: {mn} {args[0] if args else '?'}")
        elif mn == "end":
            lines.append(f"  {off:3d}: end")
        else:
            lines.append(f"  {off:3d}: {mn} {' '.join(str(x) for x in args)}")
    return lines


def walk(levels=range(28)):
    """Yield (level, entity index, script offset, code slice, entity record)."""
    for lv in levels:
        raw, base, recs = entities.entry(lv)
        if not recs:
            continue
        flat = sorted(v for _, o in recs for v in o)
        pieces = entities.cut(raw, base, flat)
        for k, (rec, offs) in enumerate(recs):
            # offs[0] is the header, not code: the interpreter keeps the program
            # counter at its +0x10 and a flag at +0x13, and counts code from
            # header+0x14. Decoding it as instructions is decoding a struct.
            for a in offs[1:]:
                yield lv, k, a, pieces[a], rec


def flag_graph():
    """flag -> {'set': [(level, entity, value)], 'tested': [(level, entity, value)]}"""
    g = collections.defaultdict(lambda: {"set": [], "tested": []})
    for lv, k, a, code, rec in walk():
        for off, op, args, mn in decode(code):
            if mn == "set_flag" and len(args) == 2:
                g[args[0]]["set"].append((lv, k, args[1]))
            elif mn == "if_flag" and len(args) == 3:
                g[args[0]]["tested"].append((lv, k, args[1]))
    return g


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == "flags":
        g = flag_graph()
        print(f"{len(g)} distinct flags referenced, array at {FLAGS:#x}\n")
        for f in sorted(g):
            s, t = g[f]["set"], g[f]["tested"]
            print(f"flag {f:3d}: set {len(s):3d}x, tested {len(t):3d}x")
            if s:
                print("    set by    " + ", ".join(f"L{lv}/e{k}={v}" for lv, k, v in s[:8]))
            if t:
                print("    tested by " + ", ".join(f"L{lv}/e{k}=={v}" for lv, k, v in t[:8]))
    elif arg is not None:
        lv = int(arg)
        text = talk_text()
        raw, base, recs = entities.entry(lv)
        flat = sorted(v for _, o in recs for v in o)
        pieces = entities.cut(raw, base, flat)
        for k, (rec, offs) in enumerate(recs):
            hdr = int.from_bytes(rec[0x0C:0x0E], "little")
            tag = "talker" if rec[0] == TALKER else "not a talker"
            print(f"=== level {lv} entity {k} (kind {rec[0]:#04x}, {tag}, base {hdr}, "
                  f"header at +{offs[0] if offs else '-'}) ===")
            for a in offs[1:]:
                print(f" script +{a}")
                for line in render(pieces[a], hdr, text, rec[0]):
                    print(line)
            print()
    else:
        print(__doc__)
        n = collections.Counter()
        for lv, k, a, code, rec in walk():
            n["scripts"] += 1
            for off, op, args, mn in decode(code):
                n[mn] += 1
        print("across every script in the game:")
        for key, v in n.most_common():
            print(f"  {key:16s} {v}")

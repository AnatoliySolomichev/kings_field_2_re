#!/usr/bin/env python3
"""A conversation as the game holds one: a call of script_interpreter a USE.

    python3 tools/talk.py              level 0's talkers, what each USE shows
    python3 tools/talk.py --check      the calls against bp21's recording

`tools/escript.py` reads the conversations and steps them in the order the
interpreter takes; this is the interpreter as the player meets it. USE on a
creature in front -- `object_interact` asks `actor_spot_taken` at the
player's point 0x1f4 up, the creature's radius + 0x578, 0xc80 as the point's
height, and the creature within 0x12c of the facing -- is one call of
`script_interpreter` (`0x8005c308`), and the conversation's state lives in its
block between calls: the pc at +0x10, the retry flag at +0x13, and the global
`script_speaker` (`0x801baa2e`), the actor[+1] of whoever talked last.

    a zero pc       the speaker is this actor
    script_prescan  the pc a guard picks, or past the 0xfe
    the speaker not this actor and the retry flag set: on to past the next
                    0xf0 and its operand, the flag clear
    then, op by op:
      a line        (below 0xf0, and 0xf1, 0xfa..0xfe) the first one starts the
                    talking animation (+1, +8); TALK.T[+0xc + op] is shown
                    through load_entry -- faded in, held to a press, faded
                    out -- and if that press had USE in it and +0x12 is 0xff,
                    one more step is allowed
      0xf0 n        the retry flag, and pc -= n        (on at once)
      0xf8 n        pc -= n                            (on at once)
      0xf9 i v t    story_flags[i] == v: the label t    (on at once)
      0xf2 x        a label: past it                   (on at once)
      0xf6          the speaker this actor, retry clear (on at once)
      0xf4 a        the level's hook, entry 4, with a   then the step test
      0xf5 n        n steps allowed                     then the step test
      0xf7 i v      story_flags[i] = v                  then the step test
      0xf3          a step spent, or the end if none is left
      0xff          the end
    the step test   pc on one; a step left: spend it and go on, else the end
    the end         +0x12's service (& 0xf0: 0 sub_80021114, 0x30 a shop,
                    0x40 a scene); the speaker this actor; the end animation
                    (+0x11, +0xe); clear_movement_state

So with +0x12 0xff -- level 0's men by the house -- each USE that closes a line
brings the next, and anything else stops the call until the next USE on the
talker. `godot/talk.gd` is the port; the self-test holds it to `call`.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escript                                                       # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LINE_OPS = (0xF1, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE)
NO_SERVICE = 0xFF


def is_line(op):
    return op < 0xF0 or op in LINE_OPS


def call(sc, state, flags, speaker, model, use, hook=None, limit=1000,
         fetches=None):
    """One call of script_interpreter for an actor whose +1 is `model`.

    `sc` is escript.json's script (its code and header), `state` the block's
    {pc, retry}, kept between calls, `flags` the story flags (written to),
    `speaker` script_speaker before the call. `use(i)` says whether the press
    that closed the i-th line shown had USE in it; `hook(a)` is the level's
    entry 4. Returns (TALK.T entries shown, hook arguments, the speaker after,
    why it ended)."""
    code, h = sc["code"], sc["header"]
    shown, called = [], []
    s3 = 0
    if state["pc"] == 0:
        speaker = model
    pc = escript.start_pc(code, flags, state["pc"])
    if speaker != model and state["retry"] == 1:
        i = pc
        if code[i] == 0xF0:
            i += 1
        else:
            i += 1
            while True:
                v = code[i]
                i += 1
                if v == 0xF0:
                    break
        pc = i + 1
        state["retry"] = 0
    why = "limit"
    for _ in range(limit):
        if not 0 <= pc < len(code):
            why = "off"
            break
        op = code[pc]
        if fetches is not None:
            fetches.append((pc, op))
        step = False                    # whether the op goes to the step test
        if is_line(op):
            shown.append(h["talk"] + op)
            if use(len(shown) - 1) and h["service"] == NO_SERVICE:
                s3 += 1
            step = True
        elif op in (0xF0, 0xF8):
            if op == 0xF0:
                state["retry"] = 1
            pc -= code[pc + 1]
            continue
        elif op == 0xF9:
            if flags[code[pc + 1]] == code[pc + 2]:
                t = escript.find_label(code, code[pc + 3])
                pc = t if t is not None else pc + 4
            else:
                pc += 4
            continue
        elif op == 0xF2:
            pc += 2
            continue
        elif op == 0xF6:
            speaker = model
            state["retry"] = 0
            pc += 1
            continue
        elif op == 0xF4:
            pc += 1
            called.append(code[pc])
            if hook:
                hook(code[pc])
            step = True
        elif op == 0xF5:
            pc += 1
            s3 = code[pc]
            step = True
        elif op == 0xF7:
            flags[code[pc + 1]] = code[pc + 2]
            pc += 2
            step = True
        elif op == 0xF3:
            pc += 1
            if s3 == 0:
                why = "spent"
                break
            s3 -= 1
            continue
        else:                           # 0xff
            why = "end"
            break
        if step:
            pc += 1
            if s3 == 0:
                why = "wait"
                break
            s3 -= 1
    state["pc"] = pc
    return shown, called, model, why


def talkers(lv=0):
    """{entity: escript.json's script} for level `lv`'s conversations."""
    import json
    path = os.path.join(ROOT, "out", "godot", "escript.json")
    if not os.path.exists(path):
        escript.export(os.path.join(ROOT, "out", "godot"))
    d = json.load(open(path))
    return {s["entity"]: s for s in d["scripts"] if s["level"] == lv}


def check(out=sys.stdout, verbose=False):
    """bp21's recorded conversations: the TALK.T entries the game loaded, in
    order, against what successive calls show when every line is closed with
    USE. The recording logged the interpreter's steps and the entries; each
    line of it is a line of a call here."""
    import json
    d = json.load(open(os.path.join(ROOT, "out", "godot", "escript.json")))
    ok = bad = 0
    for rec in d.get("recorded", []):
        sc = next((s for s in d["scripts"] if s["level"] == rec["level"]
                   and s["entity"] == rec["entity"]), None)
        if sc is None:
            continue
        want = rec["talk"]
        state, flags, speaker = {"pc": 0, "retry": 0}, [0] * 256, -1
        got = []
        model = sc["kind"]
        while len(got) < len(want):
            left = len(want) - len(got)
            # every line closed with USE, the last one the recording holds
            # with something else -- or the 0xf0 repeat would go on for ever
            shown, _c, speaker, why = call(sc, state, flags, speaker, model,
                                           lambda i, n=left: i < n - 1)
            got += shown
            if not shown and why in ("end", "off"):
                break
        got = got[:len(want)]
        good = got == want
        ok += good
        bad += not good
        if verbose or not good:
            print(f"  level {rec['level']} entity {rec['entity']}: game {want}, "
                  f"calls {got} -- {'agrees' if good else 'DIFFERS'}", file=out)
    print(f"  {ok} of {ok + bad} recorded conversations shown line for line by "
          f"successive calls (tools/talk.py)", file=out)
    return bad == 0


LOG_ENTER = re.compile(r"ENTER rec=([0-9a-f]+) slot=(\d+) entity=(\d+)")
LOG_FETCH = re.compile(r"FETCH pc=\s*(\d+) op=([0-9a-f]{2})")
LOG_TEXT = re.compile(r"TEXT TALK\.T\[(\d+)\]")


def bp21_calls(path=None):
    """emu/bp21.lua's log as [[call]] by session (each `armed` line starts
    one): a call is {slot, entity, fetch [(pc, op)], text [n]}."""
    path = path or os.path.join(ROOT, "out", "lua_bp21.log")
    sessions = []
    if not os.path.exists(path):
        return sessions
    cur = None
    for line in open(path):
        if line.startswith("=== bp21") and "armed" in line:
            sessions.append([])
            cur = None
            continue
        if not sessions:
            continue
        m = LOG_ENTER.match(line)
        if m:
            cur = {"slot": int(m.group(2)), "entity": int(m.group(3)),
                   "fetch": [], "text": []}
            sessions[-1].append(cur)
            continue
        if cur is None:
            continue
        m = LOG_FETCH.match(line)
        if m:
            cur["fetch"].append((int(m.group(1)), int(m.group(2), 16)))
            continue
        m = LOG_TEXT.match(line)
        if m:
            cur["text"].append(int(m.group(1)))
    return sessions


def check_calls(out=sys.stdout, verbose=False):
    """Every call bp21 caught, op for op: the pcs and opcodes it fetched and the
    lines it showed, against `call` from the state the calls before it left.
    Which button closed a line the log does not say, so it is read off the
    call itself: a line after which the call went on was closed with USE,
    the last one -- the call ending there -- with something else."""
    import json
    rows = {a["slot"]: a for a in json.load(open(os.path.join(
        ROOT, "out", "godot", "actors00.json")))}
    scripts = talkers(0)
    ok = bad = 0
    for calls in bp21_calls():
        states, flags, speaker = {}, [0] * 256, -1
        for c in calls:
            sc = scripts.get(c["entity"])
            if sc is None or c["slot"] not in rows:
                continue
            st = states.setdefault(c["entity"], {"pc": 0, "retry": 0})
            n = len(c["text"])
            # the last line closed with USE only if the call fetched past it
            last_line = max((i for i, (_pc, op) in enumerate(c["fetch"]) if is_line(op)),
                            default=-1)
            went_on = last_line >= 0 and last_line < len(c["fetch"]) - 1
            fetched = []
            shown, _hooks, speaker, why = call(
                sc, st, flags, speaker, rows[c["slot"]]["model"],
                lambda i, n=n, w=went_on: i < n - 1 or w, fetches=fetched)
            # the game's call can be cut off by the log ending
            want_f, got_f = c["fetch"], fetched[:len(c["fetch"])]
            good = got_f == want_f and shown[:len(c["text"])] == c["text"]
            ok += good
            bad += not good
            if verbose or not good:
                print(f"  entity {c['entity']}: game {c['fetch']} {c['text']}, model "
                      f"{fetched} {shown} ({why}) -- {'agrees' if good else 'DIFFERS'}",
                      file=out)
    print(f"  {ok} of {ok + bad} calls bp21 caught fetch the game's pcs and opcodes "
          f"and show its lines, from the state the calls before them left", file=out)
    return bad == 0


def export(out_dir, lv=0):
    """talk/<n>.png for every TALK.T entry level `lv`'s talkers can show, and
    talkcheck.json: a run of calls per talker for godot/selftest.gd."""
    import json
    import readables
    import tim
    arc = readables.archive(7)
    os.makedirs(os.path.join(out_dir, "talk"), exist_ok=True)
    cases = []
    for ent, sc in sorted(talkers(lv).items()):
        # every byte that decodes as a line -- the guard chain's closing 0xfe
        # among them, which never runs and can point past the archive's end
        for op in sorted({o for _pc, o, _a, m in escript.decode(sc["code"])
                          if m == "say"}):
            n = sc["header"]["talk"] + op
            if n + 1 >= len(arc.off):
                continue
            png = os.path.join(out_dir, "talk", f"{n}.png")
            if not os.path.exists(png):
                tim.write_png(png, readables.PAGE_W, readables.PAGE_H,
                              readables.page_entry(arc, n))
        # USE on every line but each sixth, and on none: the two ways out
        for pattern in ([True] * 5 + [False], [False]):
            state, flags, speaker = {"pc": 0, "retry": 0}, [0] * 256, -1
            calls = []
            k = [0]

            def use(_i, p=pattern):
                v = p[k[0] % len(p)]
                k[0] += 1
                return v
            for _ in range(8):
                shown, called, speaker, why = call(sc, state, flags, speaker,
                                                   sc["kind"], use)
                calls.append([shown, called, state["pc"], state["retry"], why])
            cases.append({"entity": ent, "pattern": pattern, "calls": calls})
    path = os.path.join(out_dir, "talkcheck.json")
    with open(path, "w") as fh:
        json.dump({"cases": cases}, fh, separators=(",", ":"))
    return path


if __name__ == "__main__":
    if "--check" in sys.argv:
        a = check()
        b = check_calls()
        sys.exit(0 if a and b else 1)
    lv = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    for ent, sc in sorted(talkers(lv).items()):
        state, flags, speaker = {"pc": 0, "retry": 0}, [0] * 256, -1
        print(f"entity {ent} (mesh {sc['kind']}), service {sc['header']['service']:#x}:")
        for n in range(6):
            shown, called, speaker, why = call(sc, state, flags, speaker,
                                               sc["kind"], lambda i: i < 7)
            print(f"  USE {n + 1}: {shown} hooks {called} -> pc {state['pc']} ({why})")
    check(verbose=True)

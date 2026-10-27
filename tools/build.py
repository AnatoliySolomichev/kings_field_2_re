#!/usr/bin/env python3
"""Rebuild everything derived, in order, and say what came out.

    python3 tools/build.py            the whole pipeline
    python3 tools/build.py --quick    everything but the level geometry
    python3 tools/build.py --check    only the things that report a number

Nothing here is new work. It is the order the other tools have to run in, in
one place, because that order is not obvious and getting it wrong produces
output that is quietly a version behind: `tools/consts.py` reads the walk,
`tools/rdis.py`'s listings read the constants *and* the port markers, and
`PORT.md` reads the walk again. A listing regenerated before the symbol table
was reloaded carries the old names and says nothing about it.

The three numbers at the end are the ones that say whether anything is broken:

  * every logged call `tile_collision` made, reproduced;
  * every frame of the movement recording, reproduced by the GDScript copy;
  * every function in the port placed against the game -- an `@orig` that
    resolves under the symbol table's own name, or an `@port` -- and every
    address the port cites carrying its executable.

A step that cannot run -- no disc, no Godot -- says so and does not stop the
rest, because most of this works from the disc alone and some of it does not
need even that.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EXES = ("boot", "open", "game", "end")


def _exec(args):
    """One step's process: (its return code or the error, its lines, seconds)."""
    t = time.time()
    try:
        r = subprocess.run([sys.executable] + args, cwd=ROOT,
                           capture_output=True, text=True, timeout=3600)
    except Exception as e:
        return e, [], time.time() - t
    return r.returncode, (r.stdout + r.stderr).splitlines(), time.time() - t


def _report(why, res, out=sys.stdout, keep=None, timed=False):
    """What a step said worth keeping; its lines."""
    rc, lines, dt = res
    took = f" [{dt:.0f}s]" if timed else ""
    if isinstance(rc, Exception):
        print(f"  {why}{took}: could not run -- {rc}", file=out)
        return []
    if rc != 0:
        print(f"  {why}{took}: failed", file=out)
        for line in lines[-4:]:
            print(f"      {line}", file=out)
        return lines
    shown = [x for x in lines if keep is None or any(k in x for k in keep)]
    head = f"  {why}{took}"
    if shown:
        print(f"{head}: {shown[0].strip()}", file=out)
        for line in shown[1:12]:
            print(f"      {line.strip()}", file=out)
    else:
        print(f"{head}: done in {dt:.1f}s", file=out)
    return lines


def run(args, why, out=sys.stdout, keep=None):
    """One step. Prints the lines worth keeping and returns them."""
    return _report(why, _exec(args), out, keep)


def run_all(steps, out=sys.stdout):
    """Steps that only read and report, side by side on every core; said in
    their own order, each with the seconds it took. Whether all went."""
    import concurrent.futures
    t = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        futs = [pool.submit(_exec, args) for args, _why, _keep in steps]
        res = [f.result() for f in futs]
    good = True
    for (args, why, keep), r in zip(steps, res):
        _report(why, r, out, keep, timed=True)
        good = good and r[0] == 0
    print(f"  -- {len(steps)} steps side by side in {time.time() - t:.0f}s", file=out)
    return good


def effect_parts():
    """tools/effects.py's checks by name (--parts), or the whole as one."""
    rc, lines, _dt = _exec(["tools/effects.py", "--parts"])
    return lines[-1].split() if rc == 0 and lines else None


def main(quick=False, only_check=False):
    print("Walking the four executables")
    if not only_check:
        for e in EXES:
            run(["tools/rdis.py", e, "--build"], e, keep=["routines"])

        print("\nNumbers, and the documents that index them")
        run(["tools/consts.py", "--build"], "the cross reference",
            keep=["distinct"])
        run(["tools/consts.py", "--doc"], "CONSTANTS.md", keep=["wrote"])

        print("\nListings, profiles and the call graph")
        for e in EXES:
            run(["tools/rdis.py", e, "--listing"], f"{e} listings",
                keep=["wrote"])
            run(["tools/rdis.py", e, "--graph"], f"{e} call graph",
                keep=["wrote"])
            run(["tools/rdis.py", e, "--describe"], f"{e} profiles",
                keep=["wrote"])
            run(["tools/pseudo.py", e, "--all"], f"{e} pseudocode",
                keep=["wrote"])

        print("\nThe strings that are not pictures")
        run(["tools/strings.py"], "the three tables", keep=["=== "])

        print("\nWhere each routine belongs")
        run(["tools/subsys.py", "--doc"], "MAP.md", keep=["wrote"])

        print("\nThe disc's own layout")
        run(["tools/fdat.py", "--doc"], "FDAT.md", keep=["wrote"])

        print("\nWhat an object does")
        run(["tools/objops.py", "--doc"], "OBJECTS.md", keep=["wrote"])

        print("\nThe port, against the game")
        run(["tools/portmap.py", "--doc"], "PORT.md", keep=["wrote", "progress", "recorded"])

    print("\nWhat has to still be true")
    steps = []
    steps.append((["tools/collision.py"], "the collision, against the game's own answers",
        ["reproduced"]))
    steps.append((["tools/levelup.py"], "the level table, against the snapshots",
        ["snapshots match", "snapshots have unlocked", "excellector's word"]))
    steps.append((["tools/levelup.py", "--game"],
        "award_exp and the excellector's growth, against the game's own over every level",
        ["award_exp, against", "levels taken", "model "]))
    steps.append((["tools/movement.py", "bp15"], "the movement, against the watchpoint",
        ["of 48", "of 15"]))
    steps.append((["tools/escript.py", "check"], "the conversations, against what was played",
        ["reproduced"]))
    steps.append((["tools/equip.py", "--check", "out/ram.bin"],
        "the equipment tables, against a RAM snapshot",
        ["match RAM", "reproduced", "player_recalc_stats over"]))
    steps.append((["tools/actors.py", "0", "--check"],
        "the creatures of level 0, against a RAM snapshot",
        ["of 200", "match", "slots", "categories differ"]))
    steps.append((["tools/levelmap.py", "--check"],
        "the level maps, against the floor they should cover",
        ["open cells covered"]))
    steps.append((["tools/modelbank.py", "--check"],
        "the resident model bank, against a RAM snapshot",
        ["model pointers"]))
    steps.append((["tools/props.py", "--check"],
        "the level's own props, against a RAM snapshot",
        ["fields of"]))
    steps.append((["tools/levelstate.py", "--check"],
        "the saved level record, against what was played and the game's own two routines",
        ["decode exactly", "level_state_write, the game's", "apply_level_state, the game's",
              "differ", "part at"]))
    steps.append((["tools/memcard.py", "--check"],
        "the saves on the memory card, against the game's own restore and serialise",
        ["saves on the cards", "bytes written where", "bytes as this table"]))
    steps.append((["tools/objcoll.py", "--check"],
        "the object collision, against what was played",
        ["recorded touches"]))
    steps.append((["tools/lighting.py", "--check"],
        "the lighting table, against every snapshot with a level",
        ["over every snapshot"]))
    steps.append((["tools/rtim.py", "--check"],
        "the video memory, against every snapshot with a level",
        ["over every snapshot"]))
    steps.append((["tools/hud.py", "--check"],
        "the panel's sprite table, against every snapshot's RAM",
        ["fields of the live sprite table"]))
    steps.append((["tools/ai.py", "--check"],
        "the creatures' behaviours, against every snapshot's RAM",
        ["bytes of the kinds", "runs of one behaviour", "creature frames exact",
              "the hold (+0x28 bit 0x800)"]))
    steps.append((["tools/doors.py", "--check"],
        "the doors, the gates and the hidden wall, against what was played and the game's code",
        ["steps of a moving door", "steps of a lift door", "more at 0x14",
              "doorway answers", "no out/lua_bp27", "steps of a gate", "no gate lines",
              "game's own gate arm", "game's own hidden-wall arm"]))
    steps.append((["tools/crossing.py", "--check"],
        "the crossings between levels, against what was played",
        ["crossings the model makes", "routines object_trigger"]))
    steps.append((["tools/mipsrun.py", "--check"],
        "the game's own code, run over a snapshot",
        ["exactly", "NOT"]))
    steps.append((["tools/ui.py", "--check"],
        "the menus' drawing, against the menu snapshots' frames",
        ["primitive for primitive"]))
    steps.append((["tools/talk.py", "--check"],
        "the conversations a USE at a time, against what was played",
        ["recorded conversations", "calls bp21 caught"]))
    steps.append((["tools/chests.py", "--check"],
        "the chests' lids, the drops and the pedestals, against every snapshot",
        ["opened lids", "things lying", "Silviera's key", "pedestal lines",
              "game's own pedestal arm"]))
    steps.append((["tools/useitem.py", "--check"],
        "a thing used and the warp, against the game's own use_item and warp_to",
        ["use_item, against", "  level ", "object_signal, against", "the warp, against",
         "  record "]))
    steps.append((["tools/hooks.py", "--check"],
        "what a conversation's 0xf4 runs, against every level's own entry 4",
        ["entry 4, against", ": model "]))
    steps.append((["tools/levelin.py", "--check"],
        "what a level does as it comes in, against every level's own entry 5 and the snapshots",
        ["entry 5, against", ": model ", "] differ"]))
    steps.append((["tools/triggers.py", "--check"],
        "the trigger rectangles, against the game's own opcode 0xe1 and every level's entry 3",
        ["opcode 0xe1 and entry 3, against", ": calls:", "(actor", "(object", "(flag"]))
    steps.append((["tools/givetake.py", "--check"],
        "a thing into the pack and out, against the game's own give_item, take_item and every level's entries 6 and 11",
        ["give_item and take_item, against", ": model "]))
    steps.append((["tools/seals.py", "--check"],
        "what Orladin's key opens, against the game's own arms",
        ["the seals", "Orladin's pedestals"]))
    steps.append((["tools/fade.py", "--check"],
        "the screen's fade, against the game's own screen_fade, its quad and fade_frames",
        ["screen_fade_draw's quad", "fade_frames, the game's", "its texture", "first difference"]))
    steps.append((["tools/weapon.py", "--check"],
        "the creatures' HP and the player's weapon, against snapshots and bp25",
        ["awake creatures", "frames of the weapon", "blows landed", "the weapons' magic"]))
    steps.append((["tools/anim.py", "--check"],
        "the creatures' animation, against every snapshot's actor caches",
        ["caches hold", "last drawn"]))
    fx_keep = ["frames of a spore", "strikes a frame after", "effect_aim, the game's",
               "effect_spawn and effect_driver, the game's",
               "the healing and protecting spells' effects", "the fire ball",
               "end to end, the game's own collide_query",
               "the game's own effect_spawn and effect_driver over the",
               "actor_animation_effects, the game's own", "not in the machine"]
    names = effect_parts()
    if names:
        for name in names:
            steps.append((["tools/effects.py", "--part", name],
                          f"the effects ({name}), against what was played and the game's own code",
                          fx_keep))
    else:
        steps.append((["tools/effects.py", "--check"],
                      "the effects, against what was played and the game's own code", fx_keep))
    steps.append((["tools/status.py", "--check"],
        "what a hit leaves behind, against the game's own player_take_hit and sub_80030e14",
        ["player_take_hit:", "sub_80030e14:", "first difference"]))
    steps.append((["tools/magic.py", "--check"],
        "casting, against the game's own cast_spell, player_action, player_turn and the controller's end",
        ["casting, against", "attacking arms", "square button", "first difference"]))
    steps.append((["tools/hit.py", "--check"],
        "a creature's hit, against the game's own actor_take_hit",
        ["actor_take_hit, against", "first difference"]))
    steps.append((["tools/knock.py", "--check"],
        "the knock-back, against what was played",
        ["knock-backs", "landings", "frames of a knock-back",
              "player_velocity what", "pushes predicted"]))
    steps.append((["tools/compass.py", "--check"],
        "the compass's records, against every snapshot's RAM",
        ["switches, pitches"]))
    steps.append((["tools/objload.py", "--check"],
        "the object loader, against every snapshot with a level and the game's own",
        ["over every snapshot", "load_object_placement leaves them", "differs:"]))
    steps.append((["tools/objops.py", "--types"],
        "the object type table, against a RAM snapshot",
        ["of 7968", "rows"]))
    steps.append((["tools/quest.py", "--check"],
        "the conversation hooks, two readings of the same table",
        ["agree"]))
    steps.append((["tools/pseudo.py", "--check"],
        "the pseudocode, against the instructions it is read from",
        ["every block's statements", "differs"]))
    steps.append((["tools/portmap.py"], "the port, function by function, against the game",
        ["functions in", "markers,", "every function", "problems", "godot/", "progress"]))
    good = run_all(steps)
    if not quick and not only_check:
        print("\nThe Godot build")
        run(["tools/level3d.py", "0"], "level 0",
            keep=["godot loads", "movement:", "levels:", "problems"])
    return good


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(0 if main(quick="--quick" in a, only_check="--check" in a) else 1)

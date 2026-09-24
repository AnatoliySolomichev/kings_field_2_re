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
  * every marker in the port resolving to a routine the walk found.

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


def run(args, why, out=sys.stdout, keep=None):
    """One step. Prints the lines worth keeping and returns them."""
    t = time.time()
    try:
        r = subprocess.run([sys.executable] + args, cwd=ROOT,
                           capture_output=True, text=True, timeout=3600)
    except Exception as e:
        print(f"  {why}: could not run -- {e}", file=out)
        return []
    lines = (r.stdout + r.stderr).splitlines()
    if r.returncode != 0:
        print(f"  {why}: failed", file=out)
        for line in lines[-4:]:
            print(f"      {line}", file=out)
        return lines
    shown = [x for x in lines if keep is None or any(k in x for k in keep)]
    head = f"  {why}"
    if shown:
        print(f"{head}: {shown[0].strip()}", file=out)
        for line in shown[1:4]:
            print(f"      {line.strip()}", file=out)
    else:
        print(f"{head}: done in {time.time() - t:.1f}s", file=out)
    return lines


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
        run(["tools/portmap.py", "--doc"], "PORT.md", keep=["wrote"])

    print("\nWhat has to still be true")
    run(["tools/collision.py"], "the collision, against the game's own answers",
        keep=["reproduced"])
    run(["tools/levelup.py"], "the level table, against the snapshots",
        keep=["snapshots match"])
    run(["tools/movement.py", "bp15"], "the movement, against the watchpoint",
        keep=["of 48", "of 15"])
    run(["tools/escript.py", "check"], "the conversations, against what was played",
        keep=["reproduced"])
    run(["tools/equip.py", "--check", "out/ram.bin"],
        "the equipment tables, against a RAM snapshot",
        keep=["match RAM", "reproduced"])
    run(["tools/levelstate.py", "--check"],
        "the saved level record, against what was played",
        keep=["decode exactly"])
    run(["tools/objcoll.py", "--check"],
        "the object collision, against what was played",
        keep=["recorded touches"])
    run(["tools/objops.py", "--types"],
        "the object type table, against a RAM snapshot",
        keep=["of 7968", "rows"])
    run(["tools/quest.py", "--check"],
        "the conversation hooks, two readings of the same table",
        keep=["agree"])
    run(["tools/portmap.py"], "the port's markers",
        keep=["markers", "resolve", "broken"])
    if not quick and not only_check:
        print("\nThe Godot build")
        run(["tools/level3d.py", "0"], "level 0",
            keep=["godot loads", "movement:", "levels:", "problems"])


if __name__ == "__main__":
    a = sys.argv[1:]
    main(quick="--quick" in a, only_check="--check" in a)

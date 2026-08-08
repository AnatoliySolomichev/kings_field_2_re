#!/usr/bin/env python3
"""Capture a labelled snapshot of the running game: RAM, VRAM and a screenshot.

    python3 tools/snap.py a1        # take a snapshot called "a1"
    python3 tools/snap.py --list    # what has been captured so far

Snapshots land in out/snap/. Comparing two of them is what actually locates a
structure, so always take a pair around the action you care about.
"""
import os
import sys
import time

sys.path.insert(0, "tools")
import psxlive as L      # noqa: E402

DIR = "out/snap"


def take(label):
    os.makedirs(DIR, exist_ok=True)
    state = L.running()
    if not state.get("running"):
        print("warning: emulation is paused in PCSX-Redux — resume it first",
              file=sys.stderr)
    ram, vram = L.ram(), L.vram()
    open(f"{DIR}/{label}.ram", "wb").write(ram)
    open(f"{DIR}/{label}.vram", "wb").write(vram)
    L.vram_png(f"{DIR}/{label}.png", vram, 0, 0, 320, 240)
    print(f"{label}: {len(ram)} bytes RAM, screen -> {DIR}/{label}.png "
          f"(running={state.get('running')}) at {time.strftime('%H:%M:%S')}")


def listing():
    if not os.path.isdir(DIR):
        print("no snapshots yet")
        return
    for f in sorted(os.listdir(DIR)):
        if f.endswith(".ram"):
            print(f"  {f[:-4]:12s} {os.path.getsize(DIR + '/' + f)} bytes")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        listing()
    else:
        take(sys.argv[1])

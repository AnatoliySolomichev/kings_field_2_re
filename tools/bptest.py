#!/usr/bin/env python3
"""Wait until GAME.EXE is resident, then check whether breakpoints really fire.

Breakpoints were first tested while the intro executable was loaded, so the
addresses under test belonged to code that was not even in memory. This waits
for the game proper, arms a breakpoint on a routine that runs every frame, and
reports what happens.
"""
import json
import socket
import sys
import time
import urllib.request

sys.path.insert(0, "tools")
from psxdbg import Dbg          # noqa: E402

HOT = 0x8004B288                # inside the per-frame object motion loop
LOG = "out/bptest.log"


def ram():
    with urllib.request.urlopen(
            "http://127.0.0.1:8080/api/v1/cpu/ram/raw", timeout=25) as r:
        return r.read()


def running():
    with urllib.request.urlopen(
            "http://127.0.0.1:8080/api/v1/execution-flow", timeout=5) as r:
        return json.load(r)


def game_resident(buf):
    ref = open("extract/GAME.EXE", "rb").read()[0x800:0x800 + 64]
    return buf[0x11000:0x11000 + 64] == ref


def main(wait_minutes=20):
    out = open(LOG, "a", buffering=1)
    def say(m):
        print(m, flush=True)
        out.write(f"{time.strftime('%H:%M:%S')} {m}\n")

    say(f"waiting for GAME.EXE; emulator {running()}")
    end = time.time() + wait_minutes * 60
    while time.time() < end:
        try:
            if game_resident(ram()):
                break
        except Exception as e:
            say(f"read failed: {e}")
        time.sleep(3)
    else:
        say("gave up waiting")
        return
    say("GAME.EXE is resident; arming a breakpoint on the object loop")

    d = Dbg(timeout=5)
    try:
        d.halt()
        say(f"set {HOT:#010x}: {d.cmd(f'Z0,{HOT:x},4')}")
        d._send("c")
        t = time.time()
        fired = False
        try:
            d._recv()
            fired = True
        except socket.timeout:
            pass
        say(f"fired within {time.time()-t:.1f}s: {fired}")
        if fired:
            r = d.regs()
            say(f"  pc={r['pc']:08x} ra={r['ra']:08x} s2={r['s2']:08x}")
            say("  breakpoints DO work in game -- the earlier test was invalid")
        else:
            say("  still no fire with the game running: the stub accepts Z0 "
                "but does not enforce it")
        d.halt()
        d.cmd(f"z0,{HOT:x},4")
        d._send("c")
    finally:
        d.close()
        say(f"disarmed; emulator {running()}")


if __name__ == "__main__":
    main()

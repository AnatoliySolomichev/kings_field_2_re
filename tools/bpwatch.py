#!/usr/bin/env python3
"""Arm breakpoints in the running game and log what hits them.

    python3 tools/bpwatch.py            # watch the archive readers
    python3 tools/bpwatch.py 0x8004b288 # or any addresses you name

The GDB stub takes plain breakpoints only, so "break when the archive is FDAT"
is done here: every hit is inspected and anything uninteresting is resumed
immediately. Breakpoints are always cleared and the game resumed on the way
out, including on Ctrl-C, so a crashed watcher never leaves the game frozen.
"""
import json
import signal
import socket
import sys
import time
import urllib.request

sys.path.insert(0, "tools")
from psxdbg import Dbg          # noqa: E402

# the archive read helpers found by disassembly
WATCH = [0x80019CC4, 0x8001A154, 0x80027D88, 0x80044204]
ARCHIVES = ["MO", "MOF", "VAB", "RTIM", "FDAT", "RTMD", "ITEM", "TALK", "STALK"]
INTERESTING = 4                 # FDAT
LOG = "out/bphits.log"


def running():
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:8080/api/v1/execution-flow", timeout=5) as r:
            return json.load(r)["running"]
    except Exception:
        return None


class Watch:
    def __init__(self, addrs):
        self.addrs = addrs
        self.d = Dbg(timeout=2)
        self.armed = []
        self.hits = 0
        self.kept = 0

    def arm(self):
        self.d.halt()
        for a in self.addrs:
            if self.d.cmd(f"Z0,{a:x},4") == "OK":
                self.armed.append(a)
        self.d._send("c")

    def disarm(self):
        try:
            self.d.halt()
            for a in self.armed:
                self.d.cmd(f"z0,{a:x},4")
            self.d._send("c")
        except Exception:
            pass

    def loop(self, seconds=600):
        end = time.time() + seconds
        out = open(LOG, "a")
        while time.time() < end:
            try:
                self.d._recv()                    # blocks until a stop reply
            except socket.timeout:
                continue
            except Exception:
                break
            self.hits += 1
            r = self.d.regs()
            pc, a0, a1, a2 = r["pc"], r["a0"], r["a1"], r["a2"]
            arch = a0 & 0xFFFF
            if arch == INTERESTING or pc not in self.addrs:
                self.kept += 1
                name = ARCHIVES[arch] if arch < len(ARCHIVES) else str(arch)
                line = (f"{time.strftime('%H:%M:%S')} pc={pc:08x} "
                        f"archive={arch} ({name}) entry={a1 & 0xFFFF} "
                        f"dest={a2:08x} ra={r['ra']:08x}")
                print(line, flush=True)
                out.write(line + "\n")
                out.flush()
            self.d._send("c")
        out.close()


if __name__ == "__main__":
    addrs = [int(a, 0) for a in sys.argv[1:]] or WATCH
    w = Watch(addrs)

    def bail(*_):
        w.disarm()
        print(f"\ndisarmed; {w.hits} hits, {w.kept} logged; "
              f"running={running()}")
        sys.exit(0)

    signal.signal(signal.SIGINT, bail)
    signal.signal(signal.SIGTERM, bail)
    w.arm()
    print(f"armed at {[hex(a) for a in w.armed]}; logging to {LOG}")
    print("walk across the level seam now")
    try:
        w.loop()
    finally:
        bail()

#!/usr/bin/env python3
"""King's Field II (SLUS-00255) .T container reader.

Layout:  u16 count, then count+1 u16 entry offsets in 2048-byte sectors.
Entry i spans sectors [off[i], off[i+1]).  Equal offsets mean an empty slot.
"""
import os
import struct
import sys

SECT = 2048


class TArc:
    def __init__(self, path):
        self.path = path
        self.buf = open(path, "rb").read()
        self.count = struct.unpack("<H", self.buf[:2])[0]
        self.off = list(struct.unpack("<%dH" % (self.count + 1), self.buf[2:2 + 2 * (self.count + 1)]))

    def __len__(self):
        return self.count

    def raw(self, i):
        a, b = self.off[i] * SECT, self.off[i + 1] * SECT
        return self.buf[a:b]

    def sane(self):
        mono = all(self.off[i] <= self.off[i + 1] for i in range(self.count))
        fits = self.off[-1] * SECT <= len(self.buf)
        return mono, fits, self.off[-1] * SECT, len(self.buf)


def main():
    for path in sys.argv[1:]:
        t = TArc(path)
        mono, fits, end, total = t.sane()
        empty = sum(1 for i in range(t.count) if t.off[i] == t.off[i + 1])
        sizes = [t.off[i + 1] - t.off[i] for i in range(t.count)]
        print(f"{os.path.basename(path):10s} count={t.count:5d} monotonic={mono} "
              f"fits={fits} end={end} file={total} empty={empty} "
              f"maxsect={max(sizes)} first={t.off[0]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reader for raw CD images (CloneCD .img / .bin, 2352 bytes per sector).

Handles Mode 1 and Mode 2 (Form 1/2) sectors and walks the ISO9660 filesystem
without needing an intermediate 2048-byte ISO on disk.
"""
import os
import struct
import sys

RAW = 2352
USER = 2048


class Disc:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.sectors = os.path.getsize(path) // RAW

    def raw(self, lba):
        self.f.seek(lba * RAW)
        return self.f.read(RAW)

    def mode(self, lba):
        return self.raw(lba)[15]

    def submode(self, lba):
        """Mode 2 subheader byte 2: bit 5 (0x20) set => Form 2."""
        return self.raw(lba)[18]

    def data(self, lba, size=USER):
        """User data of a sector. Mode 2 Form 1 -> 2048 @24, Form 2 -> 2324 @24."""
        d = self.raw(lba)
        if d[15] == 1:  # Mode 1
            return d[16:16 + size]
        if d[18] & 0x20:  # Mode 2 Form 2 (XA audio / video)
            return d[24:24 + 2324]
        return d[24:24 + size]

    def read(self, lba, nbytes):
        out = bytearray()
        while len(out) < nbytes:
            out += self.data(lba)
            lba += 1
        return bytes(out[:nbytes])


def _dirrecs(block):
    off = 0
    while off < len(block):
        ln = block[off]
        if ln == 0:
            break
        yield block[off:off + ln]
        off += ln


def _name(rec):
    nlen = rec[32]
    n = rec[33:33 + nlen]
    if nlen == 1 and n in (b"\x00", b"\x01"):
        return "." if n == b"\x00" else ".."
    return n.decode("latin-1").split(";")[0]


def walk(disc, lba, size, prefix=""):
    """Yield (path, lba, size, is_dir) for everything under a directory extent."""
    blob = disc.read(lba, size)
    for i in range(0, size, USER):
        for rec in _dirrecs(blob[i:i + USER]):
            nm = _name(rec)
            if nm in (".", ".."):
                continue
            ext = struct.unpack("<I", rec[2:6])[0]
            sz = struct.unpack("<I", rec[10:14])[0]
            isdir = bool(rec[25] & 0x02)
            path = prefix + "/" + nm
            yield path, ext, sz, isdir
            if isdir:
                yield from walk(disc, ext, sz, path)


def pvd_root(disc):
    for lba in range(16, 32):
        d = disc.data(lba)
        if d[1:6] == b"CD001" and d[0] == 1:
            root = d[156:156 + 34]
            return (struct.unpack("<I", root[2:6])[0],
                    struct.unpack("<I", root[10:14])[0], d)
    raise RuntimeError("no primary volume descriptor found")


def main():
    img = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else None
    disc = Disc(img)
    rlba, rsize, pvd = pvd_root(disc)
    print(f"volume: {pvd[40:72].decode('latin-1').strip()!r}  "
          f"sectors={self_sectors(disc)}  root lba={rlba} size={rsize}")
    total = 0
    for path, lba, size, isdir in walk(disc, rlba, rsize):
        kind = "DIR " if isdir else "FILE"
        print(f"{kind} {lba:8d} {size:10d}  {path}")
        if isdir or not outdir:
            continue
        total += size
        dst = os.path.join(outdir, path.lstrip("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(disc.read(lba, size))
    if outdir:
        print(f"extracted {total} bytes to {outdir}")


def self_sectors(disc):
    return disc.sectors


if __name__ == "__main__":
    main()

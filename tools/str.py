#!/usr/bin/env python3
"""The movies: the Sony STR streams the opening and the cutscenes are made of.

Nine files under `/OP` and thirteen under `/STR` on the disc, none of them in
`extract/` because the extraction only took `/CD` and `/DRM`. They are standard
Sony STR: MDEC video in Mode 2 Form 1 sectors, XA audio interleaved in Form 2
sectors, and `OPEN.EXE`'s `play_movie` streams them straight off the disc.

    python3 tools/str.py list                 every movie on the disc
    python3 tools/str.py info /OP/L0.S        one, frame by frame
    python3 tools/str.py check /OP/L0.S 40    decode 40 frames, report the count
    python3 tools/str.py png /OP/L0.S 0 out/  write frames as PNG

Two things worth knowing before reading the numbers:

* a *frame* is spread over several consecutive video sectors, and the sector
  header says which of how many it is, so a frame is complete only when its
  chunks are all present -- a movie read past a seek can start mid-frame;
* the bitstream is checked by **decoding** it, not by looking at it. The frame
  header declares how many MDEC codes the frame holds; a wrong Huffman table
  desynchronises and misses that count, so "1088 of 1088 frames consumed
  exactly their declared code count" is a real check on the decoder and not a
  restatement of the header.
"""
import os
import struct
import sys

sys.path.insert(0, "tools")
import psxiso  # noqa: E402

IMG = "emu/kf2.img"
STR_MAGIC = 0x0160

# MPEG-1 table B.14, which is the table the PlayStation's MDEC uses. Entries are
# (bit string, run, level); "ESC" is the escape into a literal run and level.
AC_TABLE = [
    ("10", "EOB", 0),
    ("11", 0, 1), ("011", 1, 1), ("0100", 0, 2), ("0101", 2, 1),
    ("00101", 0, 3), ("00111", 3, 1), ("00110", 4, 1),
    ("000110", 1, 2), ("000111", 5, 1), ("000101", 6, 1), ("000100", 7, 1),
    ("0000110", 0, 4), ("0000100", 2, 2), ("0000111", 8, 1), ("0000101", 9, 1),
    ("000001", "ESC", 0),
    ("00100110", 0, 5), ("00100001", 0, 6), ("00100101", 1, 3),
    ("00100100", 3, 2), ("00100111", 10, 1), ("00100011", 11, 1),
    ("00100010", 12, 1), ("00100000", 13, 1),
    ("0000001010", 0, 7), ("0000001100", 1, 4), ("0000001011", 2, 3),
    ("0000001111", 4, 2), ("0000001001", 5, 2), ("0000001110", 14, 1),
    ("0000001101", 15, 1), ("0000001000", 16, 1),
    ("000000011101", 0, 8), ("000000011000", 0, 9), ("000000010011", 0, 10),
    ("000000010000", 0, 11), ("000000011011", 1, 5), ("000000010100", 2, 4),
    ("000000011100", 3, 3), ("000000010010", 4, 3), ("000000011110", 6, 2),
    ("000000010101", 7, 2), ("000000010001", 8, 2), ("000000011111", 17, 1),
    ("000000011010", 18, 1), ("000000011001", 19, 1), ("000000010111", 20, 1),
    ("000000010110", 21, 1),
    ("0000000011010", 0, 12), ("0000000011001", 0, 13), ("0000000011000", 0, 14),
    ("0000000010111", 0, 15), ("0000000010110", 1, 6), ("0000000010101", 1, 7),
    ("0000000010100", 2, 5), ("0000000010011", 3, 4), ("0000000010010", 5, 3),
    ("0000000010001", 9, 2), ("0000000010000", 10, 2), ("0000000011111", 22, 1),
    ("0000000011110", 23, 1), ("0000000011101", 24, 1), ("0000000011100", 25, 1),
    ("0000000011011", 26, 1),
    ("00000000011111", 0, 16), ("00000000011110", 0, 17),
    ("00000000011101", 0, 18), ("00000000011100", 0, 19),
    ("00000000011011", 0, 20), ("00000000011010", 0, 21),
    ("00000000011001", 0, 22), ("00000000011000", 0, 23),
    ("00000000010111", 0, 24), ("00000000010110", 0, 25),
    ("00000000010101", 0, 26), ("00000000010100", 0, 27),
    ("00000000010011", 0, 28), ("00000000010010", 0, 29),
    ("00000000010001", 0, 30), ("00000000010000", 0, 31),
    ("000000000011000", 0, 32), ("000000000010111", 0, 33),
    ("000000000010110", 0, 34), ("000000000010101", 0, 35),
    ("000000000010100", 0, 36), ("000000000010011", 0, 37),
    ("000000000010010", 0, 38), ("000000000010001", 0, 39),
    ("000000000010000", 0, 40), ("000000000011111", 1, 8),
    ("000000000011110", 1, 9), ("000000000011101", 1, 10),
    ("000000000011100", 1, 11), ("000000000011011", 1, 12),
    ("000000000011010", 1, 13), ("000000000011001", 1, 14),
    ("0000000000010011", 1, 15), ("0000000000010010", 1, 16),
    ("0000000000010001", 1, 17), ("0000000000010000", 1, 18),
    ("0000000000010100", 6, 3), ("0000000000011010", 11, 2),
    ("0000000000011001", 12, 2), ("0000000000011000", 13, 2),
    ("0000000000010111", 14, 2), ("0000000000010110", 15, 2),
    ("0000000000010101", 16, 2), ("0000000000011111", 27, 1),
    ("0000000000011110", 28, 1), ("0000000000011101", 29, 1),
    ("0000000000011100", 30, 1), ("0000000000011011", 31, 1),
]
AC = {code: (run, lvl) for code, run, lvl in AC_TABLE}
MAXBITS = max(len(c) for c in AC)

# Version 3 frames do not carry a DC coefficient per block. They carry the
# *difference* from the previous block of the same colour, variable-length
# coded with MPEG-1's DC size tables (B.12 luma, B.13 chroma) and stored in
# units of four. Reading a version 3 frame as a version 2 one -- a 16-bit
# header word holding the quantiser and the DC -- decodes about eight blocks
# and then desynchronises, which is what the code count first reported.
DC_LUMA = {"100": 0, "00": 1, "01": 2, "101": 3, "110": 4, "1110": 5,
           "11110": 6, "111110": 7, "1111110": 8}
DC_CHROMA = {"00": 0, "01": 1, "10": 2, "110": 3, "1110": 4, "11110": 5,
             "111110": 6, "1111110": 7, "11111110": 8}

ZIGZAG = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]

QUANT = [
    2, 16, 19, 22, 26, 27, 29, 34, 16, 16, 22, 24, 27, 29, 34, 37,
    19, 22, 26, 27, 29, 34, 34, 38, 22, 22, 26, 27, 29, 34, 37, 40,
    22, 26, 27, 29, 32, 35, 40, 48, 26, 27, 29, 32, 35, 40, 48, 58,
    26, 27, 29, 34, 38, 46, 56, 69, 27, 29, 35, 38, 46, 56, 69, 83]


class Bits:
    """MSB-first bits out of little-endian 16-bit words, which is how the MDEC
    reads them. Getting this backwards produces a stream that decodes for a few
    codes and then falls apart, which is the failure the code count catches."""

    def __init__(self, data):
        self.s = "".join(f"{data[i + 1]:08b}{data[i]:08b}"
                         for i in range(0, len(data) - 1, 2))
        self.p = 0

    def bits(self, n):
        v = self.s[self.p:self.p + n]
        self.p += n
        return v

    def value(self, n):
        v = self.bits(n)
        return int(v, 2) if v else 0

    def signed(self, n):
        v = self.value(n)
        return v - (1 << n) if v & (1 << (n - 1)) else v


def sectors(disc, lba, size):
    """Every sector of a file, with its submode, as (lba, submode, data)."""
    n = (size + 2047) // 2048
    for i in range(n):
        raw = disc.raw(lba + i)
        yield lba + i, raw[18], raw


def frames(disc, lba, size):
    """Video frames, reassembled from their chunks.

    Yields (frame number, width, height, frame data). Audio sectors are skipped;
    a frame missing any chunk is skipped and counted by the caller.
    """
    want, got, hdr = None, [], None
    n = (size + 2047) // 2048
    for i in range(n):
        raw = disc.raw(lba + i)
        if raw[18] & 0x20:                   # Form 2: XA audio
            continue
        d = raw[24:24 + 2048]
        magic, kind, idx, cnt = struct.unpack_from("<HHHH", d, 0)
        if magic != STR_MAGIC:
            continue
        num, dsize, w, h = struct.unpack_from("<IIHH", d, 8)
        if idx == 0:
            want, got, hdr = (num, cnt), [], (num, w, h, dsize)
        if want is None or want[0] != num:
            continue
        got.append(d[32:])
        if len(got) == want[1]:
            num, w, h, dsize = hdr
            yield num, w, h, b"".join(got)[:dsize]
            want = None


def dc_delta(bs, table):
    """A version 3 DC difference: a size code, then that many bits."""
    for n in range(2, 9):
        code = bs.s[bs.p:bs.p + n]
        if code in table:
            bs.p += n
            size = table[code]
            break
    else:
        return None
    if size == 0:
        return 0
    v = bs.value(size)
    if not (v >> (size - 1)):                  # top bit clear: negative
        v -= (1 << size) - 1
    return v * 4


def block(bs, qs, version, plane, dc_pred):
    """One 8x8 block. Returns (coefficients, codes consumed, quantiser)."""
    coef = [0] * 64
    if version >= 3:
        q = qs
        d = dc_delta(bs, DC_LUMA if plane == 2 else DC_CHROMA)
        if d is None:
            return None, 0, q
        dc = dc_pred[plane] + d
        dc_pred[plane] = dc
    else:
        # Version 2 carries the DC as a plain signed 10-bit value and takes the
        # quantiser from the frame header. It is not the 16-bit
        # quantiser-and-DC word the format is often described with: the first
        # frame of \OP\M0.S has 1320 blocks in 15936 bits, and 18 bits a block
        # does not fit in that while 12 does, which is exactly a 10-bit DC and
        # a two-bit end-of-block.
        q = qs
        dc = bs.value(10)
        if bs.p > len(bs.s):
            return None, 0, 0
        if dc & 0x200:
            dc -= 0x400
    coef[0] = dc * QUANT[0]
    i, codes = 0, 1
    while True:
        for n in range(2, MAXBITS + 1):
            code = bs.s[bs.p:bs.p + n]
            if code in AC:
                bs.p += n
                run, lvl = AC[code]
                break
        else:
            return None, codes, q                      # not a code: desynced
        if run == "EOB":
            break
        if run == "ESC":
            run = bs.value(6)
            lvl = bs.signed(10)
        else:
            lvl = -lvl if bs.value(1) else lvl
        i += run + 1
        if i > 63:
            return None, codes, q
        # The quantiser matrix is written out in natural order, so it is
        # indexed by the coefficient's natural position, not by its place in
        # the zigzag. Indexing it by the zigzag position instead scales every
        # AC coefficient by the wrong amount and turns the picture into
        # coloured blocks that still decode without an invalid code.
        coef[ZIGZAG[i]] = (lvl * q * QUANT[ZIGZAG[i]]) >> 3
        codes += 1
    return coef, codes + 1, q


def idct(coef):
    import math
    if not hasattr(idct, "cos"):
        idct.cos = [[math.cos((2 * x + 1) * u * math.pi / 16) *
                     (math.sqrt(0.5) if u == 0 else 1.0) for u in range(8)]
                    for x in range(8)]
    c = idct.cos
    tmp = [[0.0] * 8 for _ in range(8)]
    for y in range(8):
        row = coef[y * 8:y * 8 + 8]
        if not any(row):
            continue
        for x in range(8):
            tmp[y][x] = sum(row[u] * c[x][u] for u in range(8) if row[u]) * 0.5
    out = [0] * 64
    for x in range(8):
        col = [tmp[v][x] for v in range(8)]
        for y in range(8):
            out[y * 8 + x] = sum(col[v] * c[y][v] for v in range(8)) * 0.5
    return out


def decode(data, w, h, pixels=True):
    """A frame. Returns (RGB rows or None, codes consumed, codes declared)."""
    ncodes, magic, qs, ver = struct.unpack_from("<HHHH", data, 0)
    bs = Bits(data[8:])
    mbx, mby = (w + 15) // 16, (h + 15) // 16
    img = bytearray(w * h * 3) if pixels else None
    used = 0
    dc_pred = [0, 0, 0]                     # Cr, Cb and the shared luma
    # Macroblocks come column by column, not row by row: the MDEC hands the
    # GPU vertical strips 16 pixels wide. Reading them in raster order gives a
    # picture whose content is right and whose bands are shuffled, which looks
    # like a decoder bug and is not one.
    for mx in range(mbx):
        for my in range(mby):
            planes = []
            for b in range(6):
                coef, n, _q = block(bs, qs, ver, min(b, 2), dc_pred)
                used += n
                if coef is None:
                    return None, used, ncodes, len(bs.s) - bs.p
                planes.append(idct(coef) if pixels else None)
            if not pixels:
                continue
            cr, cb = planes[0], planes[1]
            for i, lum in enumerate(planes[2:]):
                ox, oy = (i & 1) * 8, (i >> 1) * 8
                for y in range(8):
                    for x in range(8):
                        px, py = mx * 16 + ox + x, my * 16 + oy + y
                        if px >= w or py >= h:
                            continue
                        cxi = ((ox + x) >> 1) + ((oy + y) >> 1) * 8
                        Y = lum[y * 8 + x] + 128
                        r = Y + 1.402 * cr[cxi]
                        g = Y - 0.344136 * cb[cxi] - 0.714136 * cr[cxi]
                        bl = Y + 1.772 * cb[cxi]
                        o = (py * w + px) * 3
                        img[o] = max(0, min(255, int(r)))
                        img[o + 1] = max(0, min(255, int(g)))
                        img[o + 2] = max(0, min(255, int(bl)))
    return img, used, ncodes, len(bs.s) - bs.p


def write_png(path, w, h, rgb):
    import zlib
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgb[y * w * 3:(y + 1) * w * 3]

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    open(path, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b""))


def find(disc, path):
    rlba, rsize, _pvd = psxiso.pvd_root(disc)
    for p, lba, size, isdir in psxiso.walk(disc, rlba, rsize):
        if p.upper() == path.upper() and not isdir:
            return lba, size
    raise SystemExit(f"{path} is not on the disc")


def listing(disc):
    rlba, rsize, _pvd = psxiso.pvd_root(disc)
    for p, lba, size, isdir in psxiso.walk(disc, rlba, rsize):
        if isdir or not p.upper().endswith(".S"):
            continue
        d = disc.data(lba)
        magic, _kind, _i, cnt = struct.unpack_from("<HHHH", d, 0)
        if magic != STR_MAGIC:
            print(f"{p:16s} {size:10d}  not an STR stream")
            continue
        w, h = struct.unpack_from("<HH", d, 16)
        nsec = (size + 2047) // 2048
        audio = sum(1 for i in range(0, nsec, 64) if disc.raw(lba + i)[18] & 0x20)
        print(f"{p:16s} {size:10d}  {w}x{h}  {cnt} sectors a frame, "
              f"{nsec} sectors{'  with XA audio' if audio else ''}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    disc = psxiso.Disc(IMG)
    if cmd == "list":
        listing(disc)
    elif cmd == "info":
        lba, size = find(disc, sys.argv[2])
        n = 0
        for num, w, h, data in frames(disc, lba, size):
            if n < 5:
                ncodes, _m, qs, ver = struct.unpack_from("<HHHH", data, 0)
                print(f"  frame {num:5d}  {w}x{h}  {len(data):6d} bytes  "
                      f"{ncodes} codes  quant {qs}  version {ver}")
            n += 1
        print(f"{n} whole frames in {sys.argv[2]}")
    elif cmd == "check":
        lba, size = find(disc, sys.argv[2])
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        ok = bad = 0
        worst = 0
        for num, w, h, data in frames(disc, lba, size):
            _img, used, want, left = decode(data, w, h, pixels=False)
            if _img is None and used == 0 or left is None:
                bad += 1
                continue
            # A frame is decoded when every block yielded a valid code and the
            # bitstream ran out within a word of the end. Leftover bits are the
            # encoder's padding to the next 32-bit boundary; anything more
            # means the decode drifted and stopped early.
            if left < 64:
                ok += 1
                worst = max(worst, left)
            else:
                bad += 1
                if bad < 4:
                    print(f"  frame {num}: {left} bits left over, "
                          f"{used} codes read, header declares {want}")
            if ok + bad >= limit:
                break
        print(f"{ok} of {ok + bad} frames of {sys.argv[2]} decoded with every "
              f"block a valid code and at most {worst} bits of padding left")
    elif cmd == "png":
        lba, size = find(disc, sys.argv[2])
        want = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        out = sys.argv[4] if len(sys.argv) > 4 else "out/op"
        os.makedirs(out, exist_ok=True)
        for num, w, h, data in frames(disc, lba, size):
            if num < want:
                continue
            img, used, decl, left = decode(data, w, h)
            if img is None:
                print(f"frame {num} did not decode ({used} of {decl} codes)")
                break
            name = os.path.basename(sys.argv[2]).replace(".", "_")
            write_png(f"{out}/{name}_{num:04d}.png", w, h, img)
            print(f"wrote {out}/{name}_{num:04d}.png  {w}x{h}  "
                  f"{used} codes read, {left} bits left over")
            break

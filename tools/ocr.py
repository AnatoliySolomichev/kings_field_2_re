#!/usr/bin/env python3
"""Bitmap-font OCR for King's Field II pre-rendered text.

Dialogue is stored as dithered 4bpp TIMs, so no two instances of a letter are
pixel-identical: cells are classified against labelled templates by Jaccard
distance rather than hashed.

Layout facts recovered from the data:
  * character advance is a strict 7 px, with the cell's first column acting as
    the inter-character gap;
  * line pitch depends on the font: TALK.T renders at 16 px, STALK.T is the
    same script in a smaller face at 14 px;
  * the vertical origin of the text block varies per image, so cells are
    anchored on the cap line (the densest row) rather than the image top.
"""
import pickle
import sys
from collections import Counter

sys.path.insert(0, "tools")
from glyphs import xphase          # noqa: E402

CW = 7
GH = 16                            # rows of a cell
CAP = 5                            # cap-line sits this far into the cell
BLANK = tuple([0] * GH)

SEED_TEXT = [
    "If you see something you like...",
    "take it -- this stuff is just",
    "going to go to waste with no",
    "customers to buy anything...",
    "Anyway, I'll probably be dead by",
    "the time anyone comes around",
    "here again.",
]


def bits(bm):
    v = 0
    for y in range(GH):
        v |= bm[y] << (y * CW)
    return v


def jac(a, b):
    u = bin(a | b).count("1")
    return bin(a ^ b).count("1") / u if u else 0.0


def bands(w, h, b):
    out, s = [], None
    for y in range(h + 1):
        v = sum(b[y * w:(y + 1) * w]) if y < h else 0
        if v and s is None:
            s = y
        elif not v and s is not None:
            out.append((s, y - 1))
            s = None
    return out


def capline(w, h, b, pitch=16):
    """Row offset of the cap line: line pitch is a constant 16 px, but the
    block's vertical origin varies per image, so anchor on the densest row
    (the top edge of the capitals, where nearly every glyph has ink)."""
    acc = [0] * pitch
    for y in range(h):
        acc[y % pitch] += sum(b[y * w:(y + 1) * w])
    return max(range(pitch), key=lambda o: acc[o])


def bestalign(w, h, b, font, pitch=16):
    """Pick the (cap, xphase) pair the font itself recognises best.

    Ink statistics alone mislabel a fair number of images (few lines, leading
    quotes, sparse punctuation), so the alignment is chosen by decoding with
    every candidate offset and keeping the one with the lowest mean distance.
    """
    cands = []
    for px in range(CW):
        for cap in range(pitch):
            tot = d = 0
            for r, c, bm in grid(w, h, b, cap, px, pitch):
                if bm == BLANK:
                    continue
                tot += 1
                d += font.match(bm)[1]
            if tot >= 4:
                cands.append((d / tot, -tot, cap, px))
    if not cands:
        return capline(w, h, b, pitch), xphase(w, h, b)
    cands.sort()
    return cands[0][2], cands[0][3]


def grid(w, h, b, cap=None, px=None, pitch=16):
    """Yield (row, col, 7x16 bitmap), anchored on the cap line so that images
    with different vertical origins produce identical glyph bitmaps."""
    if cap is None:
        cap = capline(w, h, b, pitch)
    if px is None:
        px = xphase(w, h, b)
    y0 = cap - CAP
    while y0 - pitch > -GH:
        y0 -= pitch
    nrow = -(-(h - y0) // pitch)
    for r in range(nrow):
        for c in range((w - px) // CW):
            bm = []
            for y in range(GH):
                yy = y0 + r * pitch + y
                row = 0
                if 0 <= yy < h:
                    for x in range(CW):
                        xx = px + c * CW + x
                        if xx < w and b[yy * w + xx]:
                            row |= 1 << x
                bm.append(row)
            yield r, c, tuple(bm)


class Font:
    def __init__(self, tpl=None):
        self.tpl = list(tpl or [])
        self._cache = {}

    def add(self, bm, ch):
        v = bits(bm)
        if v and (v, ch) not in self.tpl:
            self.tpl.append((v, ch))
            self._cache.clear()

    def match(self, bm):
        v = bits(bm)
        if v == 0:
            return " ", 0.0
        hit = self._cache.get(v)
        if hit is None:
            best, bestd = "?", 1.0
            for tv, tc in self.tpl:
                d = jac(v, tv)
                if d < bestd:
                    best, bestd = tc, d
            hit = self._cache[v] = (best, bestd)
        return hit

    def decode(self, w, h, b, maxd=0.34, unk="�", cap=None, px=None, pitch=16):
        rows = {}
        for r, c, bm in grid(w, h, b, cap, px, pitch):
            ch, d = self.match(bm)
            rows.setdefault(r, {})[c] = ch if d <= maxd else unk
        out = []
        for r in sorted(rows):
            m = rows[r]
            out.append("".join(m.get(c, " ") for c in range(max(m) + 1)).rstrip())
        return "\n".join(l for l in out).strip("\n")


def seed(imgs):
    f = Font()
    n, i, j, w, h, b = imgs[0]
    g = {}
    for r, c, bm in grid(w, h, b):
        g.setdefault(r, {})[c] = bm
    for r, text in enumerate(SEED_TEXT):
        for c, ch in enumerate(text):
            if ch == " ":
                continue
            bm = g.get(r, {}).get(c)
            if bm:
                f.add(bm, ch)
    return f


def load(path="out/font.pkl"):
    return Font(pickle.load(open(path, "rb")))


if __name__ == "__main__":
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    f = seed(imgs)
    print(f"seed templates: {len(f.tpl)}")
    pc = Counter()
    for n, i, j, w, h, b in imgs:
        if n in ("TALK", "STALK") and w >= 200:
            pc[capline(w, h, b)] += 1
    print("per-image cap line:", pc.most_common())
    for k in (0, 3, 42):
        n, i, j, w, h, b = imgs[k]
        print(f"--- {n}[{i}] cap={capline(w,h,b)}")
        print(f.decode(w, h, b))
    pickle.dump(f.tpl, open("out/font_seed.pkl", "wb"))

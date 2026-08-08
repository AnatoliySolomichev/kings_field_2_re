#!/usr/bin/env python3
"""Cut every text image into 7x16 monospace cells and cluster unique glyphs.

Phase detection per image:
  x-phase = offset whose columns carry the least ink (the inter-character gap)
  y-phase = offset that puts the most ink in the x-height band (rows 3..9)
"""
import pickle
import sys
from collections import Counter

CW, CH = 7, 16


def xphase(w, h, b):
    best, bestv = 0, None
    for p in range(CW):
        v = sum(b[y * w + x] for y in range(h) for x in range(p, w, CW))
        if bestv is None or v < bestv:
            best, bestv = p, v
    return best


def yphase(w, h, b):
    best, bestv = 0, -1
    for p in range(CH):
        v = 0
        for y in range(h):
            if 3 <= (y - p) % CH <= 9:
                v += sum(b[y * w:(y + 1) * w])
        if v > bestv:
            best, bestv = p, v
    return best


def cells(w, h, b):
    """Yield (row, col, 7x16 bitmap tuple)."""
    px, py = xphase(w, h, b), yphase(w, h, b)
    x0 = px + 1                      # gap column belongs to the previous cell
    for r in range((h - py) // CH):
        for c in range((w - x0) // CW):
            bm = []
            for y in range(CH):
                yy = py + r * CH + y
                row = 0
                for x in range(CW):
                    xx = x0 + c * CW + x
                    if xx < w and yy < h and b[yy * w + xx]:
                        row |= 1 << x
                bm.append(row)
            yield r, c, tuple(bm)


def main():
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    freq = Counter()
    for n, i, j, w, h, b in imgs:
        if w < 60:
            continue
        for r, c, bm in cells(w, h, b):
            freq[bm] += 1
    blank = tuple([0] * CH)
    print(f"unique cells: {len(freq)}  total: {sum(freq.values())}  "
          f"blank: {freq[blank]}")
    common = [g for g, n in freq.most_common() if n >= 3 and g != blank]
    rare = [g for g, n in freq.most_common() if n < 3 and g != blank]
    print(f"glyphs seen >=3 times: {len(common)}   rare/noise: {len(rare)}")
    pickle.dump((freq, common), open("out/glyphs.pkl", "wb"))
    return freq, common


def sheet(glyphs, path, cols=16, scale=4):
    """Render candidate glyphs into a labelled grid PNG for manual reading."""
    sys.path.insert(0, "tools")
    import tim
    pad, lab = 2, 6
    ch = len(glyphs[0]) if glyphs else CH
    gw, gh = CW * scale + pad * 2, ch * scale + pad * 2 + lab
    rows = (len(glyphs) + cols - 1) // cols
    W, H = cols * gw, rows * gh
    px = [(20, 20, 30, 255)] * (W * H)
    for idx, g in enumerate(glyphs):
        gx, gy = (idx % cols) * gw, (idx // cols) * gh
        for y in range(ch):
            for x in range(CW):
                if g[y] >> x & 1:
                    for sy in range(scale):
                        for sx in range(scale):
                            X, Y = gx + pad + x * scale + sx, gy + pad + y * scale + sy
                            px[Y * W + X] = (255, 255, 255, 255)
        for x in range(gw):                       # separator strip
            Y = gy + gh - 1
            px[Y * W + gx + x] = (90, 90, 120, 255)
    tim.write_png(path, W, H, px)
    print(f"wrote {path}  {W}x{H}  ({len(glyphs)} glyphs, {cols} per row)")


if __name__ == "__main__":
    freq, common = main()
    sheet(common, "out/glyphsheet.png")

#!/usr/bin/env python3
"""Robust monospace grid alignment.

Instead of guessing the phase from ink minima/maxima per image (which drifts
when an image has few lines or no ascenders), fold each image's row/column ink
profile onto the grid period and cross-correlate it with a reference profile
learned from the whole corpus.
"""
import pickle
from collections import Counter

CW, CH = 7, 16


def rowprof(w, h, b):
    p = [0] * CH
    for y in range(h):
        p[y % CH] += sum(b[y * w:(y + 1) * w])
    return p


def colprof(w, h, b):
    p = [0] * CW
    for y in range(h):
        base = y * w
        for x in range(w):
            if b[base + x]:
                p[x % CW] += 1
    return p


def _norm(p):
    s = sum(p) or 1
    return [v / s for v in p]


def bestshift(prof, ref, period):
    prof = _norm(prof)
    best, bestv = 0, None
    for s in range(period):
        v = sum(prof[(i + s) % period] * ref[i] for i in range(period))
        if bestv is None or v > bestv:
            best, bestv = s, v
    return best


def align(w, h, b, rref, cref):
    """Return (xphase, yphase) that put the grid where the reference says."""
    return (bestshift(colprof(w, h, b), cref, CW),
            bestshift(rowprof(w, h, b), rref, CH))


def cells(w, h, b, px, py):
    x0 = px
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


def build_refs(imgs, seed_idx=0):
    """Bootstrap reference profiles from one known-good image, then refine."""
    n, i, j, w, h, b = imgs[seed_idx]
    rref, cref = _norm(rowprof(w, h, b)), _norm(colprof(w, h, b))
    for _ in range(3):
        racc, cacc = [0.0] * CH, [0.0] * CW
        for n, i, j, w, h, b in imgs:
            if w < 200:
                continue
            sx, sy = align(w, h, b, rref, cref)
            rp, cp = _norm(rowprof(w, h, b)), _norm(colprof(w, h, b))
            for k in range(CH):
                racc[k] += rp[(k + sy) % CH]
            for k in range(CW):
                cacc[k] += cp[(k + sx) % CW]
        rref, cref = _norm(racc), _norm(cacc)
    return rref, cref


if __name__ == "__main__":
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    rref, cref = build_refs(imgs)
    print("row ref:", [f"{v:.3f}" for v in rref])
    print("col ref:", [f"{v:.3f}" for v in cref])
    pickle.dump((rref, cref), open("out/refs.pkl", "wb"))

    freq = Counter()
    for n, i, j, w, h, b in imgs:
        if n == "ITEM" or w < 200:
            continue
        sx, sy = align(w, h, b, rref, cref)
        for r, c, bm in cells(w, h, b, sx, sy):
            freq[bm] += 1
    blank = tuple([0] * CH)
    mc = [(g, x) for g, x in freq.most_common() if g != blank]
    nb = sum(x for g, x in mc)
    print(f"unique={len(freq)} nonblank={nb}")
    for k in (60, 80, 100, 150, 300):
        print(f"  top{k}: {sum(x for g, x in mc[:k]) * 100 / nb:.2f}%")
    pickle.dump(mc, open("out/mc2.pkl", "wb"))

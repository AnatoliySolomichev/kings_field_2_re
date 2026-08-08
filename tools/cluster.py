#!/usr/bin/env python3
"""Cluster anti-aliasing-noisy glyph cells into a real alphabet.

The pre-rendered text is dithered, so the same letter never has a byte-identical
bitmap. Greedy agglomeration by Hamming distance recovers the alphabet.
"""
import pickle
from collections import Counter

CW, CH = 7, 16
NBITS = CW * CH


def bits(bm):
    v = 0
    for y in range(CH):
        v |= bm[y] << (y * CW)
    return v


def popcount(x):
    return bin(x).count("1")


def collect(imgs, refs, want=("TALK", "STALK", "ITEM"), minw=200):
    from align import align, cells
    rref, cref = refs
    freq = Counter()
    where = {}
    for n, i, j, w, h, b in imgs:
        if n not in want or w < minw:
            continue
        sx, sy = align(w, h, b, rref, cref)
        for r, c, bm in cells(w, h, b, sx, sy):
            freq[bm] += 1
            where.setdefault(bm, (n, i, j, r, c))
    return freq, where


def agglomerate(freq, thresh=10, minsize=1):
    """Greedy: strongest remaining bitmap becomes a centroid, absorb neighbours."""
    items = [(bits(bm), n, bm) for bm, n in freq.most_common()]
    centers = []          # (centroid_int, total_count, exemplar_bm, members)
    for v, n, bm in items:
        placed = False
        for k, (cv, cn, cbm, mem) in enumerate(centers):
            if popcount(cv ^ v) <= thresh:
                centers[k] = (cv, cn + n, cbm, mem + [(bm, n)])
                placed = True
                break
        if not placed:
            centers.append((v, n, bm, [(bm, n)]))
    centers.sort(key=lambda c: -c[1])
    return [c for c in centers if c[1] >= minsize]


if __name__ == "__main__":
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    refs = pickle.load(open("out/refs.pkl", "rb"))
    import sys
    sys.path.insert(0, "tools")
    freq, where = collect(imgs, refs)
    blank = tuple([0] * CH)
    nb = sum(n for bm, n in freq.items() if bm != blank)
    print(f"cells: unique={len(freq)} nonblank={nb}")

    for th in (4, 6, 8, 10, 12, 14):
        cs = agglomerate(freq, th)
        cs = [c for c in cs if c[2] != blank]
        cov = sum(c[1] for c in cs[:100])
        print(f"thresh={th:2d} -> {len(cs):5d} clusters, "
              f"top100 cover {cov * 100 / nb:.2f}%, "
              f"clusters>=20 hits: {sum(1 for c in cs if c[1] >= 20)}")
    pickle.dump((freq, where), open("out/cellfreq.pkl", "wb"))

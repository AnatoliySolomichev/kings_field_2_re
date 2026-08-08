#!/usr/bin/env python3
"""Collect cells the current font cannot explain, cluster them, and render a
numbered sheet so the missing glyphs can be labelled by eye."""
import pickle
import sys
from collections import Counter

sys.path.insert(0, "tools")
from ocr import Font, grid, bits, jac, seed, BLANK, CH   # noqa: E402
from glyphs import sheet                                 # noqa: E402


def all_cells(imgs, minw=60):
    freq = Counter()
    for n, i, j, w, h, b in imgs:
        if w < minw:
            continue
        for r, c, bm in grid(w, h, b):
            freq[bm] += 1
    return freq


def unknown(freq, font, maxd=0.34):
    out = []
    for bm, n in freq.most_common():
        if bm == BLANK:
            continue
        ch, d = font.match(bm)
        if d > maxd:
            out.append((bm, n, d))
    return out


def dedup(unk, th=0.18):
    reps = []
    for bm, n, d in unk:
        v = bits(bm)
        hit = False
        for k, (rv, rbm, rn) in enumerate(reps):
            if jac(v, rv) <= th:
                reps[k] = (rv, rbm, rn + n)
                hit = True
                break
        if not hit:
            reps.append((v, bm, n))
    reps.sort(key=lambda r: -r[2])
    return reps


if __name__ == "__main__":
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    font = Font()
    font.tpl = pickle.load(open("out/font_seed.pkl", "rb"))
    try:
        font.tpl += pickle.load(open("out/font_extra.pkl", "rb"))
    except FileNotFoundError:
        pass
    print(f"font templates: {len(font.tpl)}")

    freq = all_cells(imgs)
    total = sum(n for bm, n in freq.items() if bm != BLANK)
    unk = unknown(freq, font)
    nunk = sum(n for _, n, _ in unk)
    print(f"unique cells {len(freq)}  nonblank {total}  "
          f"unexplained {nunk} ({nunk*100/total:.2f}%) in {len(unk)} shapes")

    reps = dedup(unk)
    print(f"deduped to {len(reps)} distinct unknown glyphs; top counts: "
          f"{[r[2] for r in reps[:20]]}")
    pickle.dump(reps, open("out/unknown.pkl", "wb"))
    sheet([r[1] for r in reps[:120]], "out/unknown.png", cols=10, scale=6)

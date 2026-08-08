#!/usr/bin/env python3
"""Load every text TIM from the .T archives as a binary ink bitmap and
probe the monospace character grid (advance width / line height / phase)."""
import sys
import pickle
from collections import Counter

sys.path.insert(0, "tools")
from tarc import TArc          # noqa: E402
import tim                     # noqa: E402

ARCS = ["TALK", "STALK", "ITEM"]


def ink(px, w, h):
    """1 where a pixel is opaque and bright enough to be glyph ink."""
    return [1 if (p[3] and (p[0] + p[1] + p[2]) > 200) else 0 for p in px]


def load():
    imgs = []
    for n in ARCS:
        t = TArc(f"extract/CD/COM/{n}.T")
        for i in range(len(t)):
            for j, (off, (w, h, px, nx, org, cl)) in enumerate(tim.scan(t.raw(i))):
                imgs.append((n, i, j, w, h, ink(px, w, h)))
    return imgs


def probe(imgs):
    for period, axis in ((7, "col"), (16, "row")):
        hist = Counter()
        for n, i, j, w, h, b in imgs:
            if w < 100:
                continue
            for y in range(h):
                for x in range(w):
                    if b[y * w + x]:
                        hist[(x if axis == "col" else y) % period] += 1
        tot = sum(hist.values()) or 1
        print(f"{axis} ink distribution mod {period}:")
        for k in range(period):
            print(f"  {k:2d} {hist[k]*100/tot:5.2f}% {'#'*int(hist[k]*300/tot)}")


if __name__ == "__main__":
    imgs = load()
    print(f"loaded {len(imgs)} text images")
    pickle.dump(imgs, open("out/imgs.pkl", "wb"))
    probe(imgs)

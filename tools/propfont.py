#!/usr/bin/env python3
"""OCR for King's Field II's proportional display face.

Item names, shop titles and sign text are set in a second, proportional font,
so the fixed 7 px grid used for dialogue does not apply. Glyphs are instead cut
apart at blank columns and matched on their bounding-box bitmap plus the offset
of that box from the line's top, which is what separates 'o' from 'a' or a
comma from an apostrophe.
"""
import pickle
import sys

sys.path.insert(0, "tools")

MINW, MAXW, MAXH = 40, 200, 40


def candidates(imgs, arc="ITEM"):
    for n, i, j, w, h, b in imgs:
        if n == arc and MINW <= w <= MAXW and h <= MAXH:
            yield i, j, w, h, b


def lines(w, h, b):
    """Row bands holding one text line each."""
    out, s = [], None
    for y in range(h + 1):
        ink = any(b[y * w:(y + 1) * w]) if y < h else False
        if ink and s is None:
            s = y
        elif not ink and s is not None:
            out.append((s, y))
            s = None
    return out


def glyphs(w, h, b, y0, y1):
    """Cut a line into glyph boxes at blank columns.

    Yields (x_start, advance_gap, bitmap tuple, top offset within the line).
    """
    cols = [any(b[y * w + x] for y in range(y0, y1)) for x in range(w)]
    runs, s = [], None
    for x in range(w + 1):
        on = cols[x] if x < w else False
        if on and s is None:
            s = x
        elif not on and s is not None:
            runs.append((s, x))
            s = None
    prev_end = None
    for a, bnd in runs:
        rows = [y for y in range(y0, y1) if any(b[y * w + x] for x in range(a, bnd))]
        top, bot = rows[0], rows[-1] + 1
        bm = tuple(
            sum(1 << (x - a) for x in range(a, bnd) if b[y * w + x])
            for y in range(top, bot))
        gap = a - prev_end if prev_end is not None else 0
        prev_end = bnd
        yield a, gap, bm, top - y0, bnd - a


def parse(w, h, b):
    """Yield (line_index, list of glyph records)."""
    for li, (y0, y1) in enumerate(lines(w, h, b)):
        yield li, list(glyphs(w, h, b, y0, y1))


def key(bm, top):
    return (top, bm)


if __name__ == "__main__":
    from collections import Counter
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    cand = list(candidates(imgs))
    freq, gaps = Counter(), Counter()
    for i, j, w, h, b in cand:
        for li, gl in parse(w, h, b):
            for x, gap, bm, top, adv in gl:
                freq[key(bm, top)] += 1
                gaps[gap] += 1
    print(f"images: {len(cand)}  glyph boxes: {sum(freq.values())}  "
          f"distinct: {len(freq)}")
    mc = freq.most_common()
    tot = sum(freq.values())
    for k in (40, 60, 80, 120):
        print(f"  top{k}: {sum(n for _, n in mc[:k]) * 100 / tot:.1f}%")
    print("gap histogram:", gaps.most_common(8))
    pickle.dump((cand, freq), open("out/propfont.pkl", "wb"))

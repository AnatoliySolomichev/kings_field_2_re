#!/usr/bin/env python3
"""Decode every pre-rendered text image in the game to plain text.

'I' and 'l' are pixel-identical in this font, so the bar glyph is decoded to a
placeholder and resolved afterwards against the system word list.
"""
import os
import pickle
import re
import sys

sys.path.insert(0, "tools")
from ocr import Font, grid, bestalign, BLANK, CW, GH   # noqa: E402

BAR = "\x01"
DICT = "/usr/share/dict/american-english"
CONTRACTIONS = {"I", "I'll", "I'm", "I've", "I'd", "I'd"}


def load_words():
    w = set()
    try:
        for line in open(DICT, encoding="latin-1"):
            w.add(line.strip())
    except OSError:
        pass
    return w


WORDS = load_words()


def known(tok):
    return tok in WORDS or tok.lower() in WORDS or tok.capitalize() in WORDS


def resolve(tok):
    """Choose I/l for every bar in a word, preferring a real English word."""
    k = tok.count(BAR)
    if not k:
        return tok
    best, bestscore = None, None
    for mask in range(1 << k):
        out, bit = [], 0
        for ch in tok:
            if ch == BAR:
                out.append("I" if (mask >> bit) & 1 else "l")
                bit += 1
            else:
                out.append(ch)
        cand = "".join(out)
        score = 0
        if cand in CONTRACTIONS:
            score += 6
        if known(cand):
            score += 4
        if cand[0].isupper() and known(cand.lower()) and cand[1:].islower():
            score += 1                       # sentence-initial capital
        score -= sum(1 for i, c in enumerate(cand)
                     if c == "I" and i > 0 and cand[i - 1].islower())
        if cand[0] == "I" and len(cand) > 1 and cand[1:].islower():
            score += 1                       # unknown proper noun: Ichrius
        if bestscore is None or score > bestscore:
            best, bestscore = cand, score
    return best


CONFUSIONS = [("d", "q"), ("b", "o"), ("O", "C"), ("N", "M"), ("e", "c"),
              ("h", "b"), ("i", "l"), ("t", "f"), ("u", "n"), ("v", "y")]


def repair(tok):
    """Fix residual glyph confusions when doing so yields a real word.

    Several letter pairs differ by only a pixel or two once the dithering has
    been binarised, so the dictionary is the tie-breaker of last resort.
    """
    if len(tok) < 2 or known(tok):
        return tok
    hits = set()
    for a, b in CONFUSIONS:
        for src, dst in ((a, b), (b, a)):
            for i, ch in enumerate(tok):
                if ch != src:
                    continue
                cand = tok[:i] + dst + tok[i + 1:]
                if known(cand):
                    hits.add(cand)
    return hits.pop() if len(hits) == 1 else tok


def fix_bars(text):
    text = re.sub(r"[A-Za-z'\x01]+", lambda m: resolve(m.group(0)), text)
    return re.sub(r"[A-Za-z][A-Za-z']*", lambda m: repair(m.group(0)), text)


def main():
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    big = Font(pickle.load(open("out/font_big.pkl", "rb")))
    out = {}
    for k, (n, i, j, w, h, b) in enumerate(imgs):
        if w < 200:
            continue
        pitch = 14 if n == "STALK" else 16
        cap, px = bestalign(w, h, b, big, pitch)
        rows = {}
        bad = tot = 0
        for r, c, bm in grid(w, h, b, cap, px, pitch):
            ch, d = big.match(bm)
            if bm != BLANK:
                tot += 1
                if d > 0.34:
                    bad += 1
            rows.setdefault(r, {})[c] = ch if d <= 0.34 else "�"
        lines = []
        for r in sorted(rows):
            m = rows[r]
            lines.append("".join(m.get(c, " ") for c in range(max(m) + 1)).rstrip())
        txt = fix_bars("\n".join(lines).strip("\n"))
        out.setdefault(n, {}).setdefault(i, []).append(
            (txt, bad / tot if tot else 0.0))
        if k % 200 == 0:
            print(f"  {k}/{len(imgs)}", flush=True)
    pickle.dump(out, open("out/text.pkl", "wb"))
    os.makedirs("out/text", exist_ok=True)
    for n, entries in out.items():
        with open(f"out/text/{n}.txt", "w") as fh:
            for i in sorted(entries):
                for t, q in entries[i]:
                    fh.write(f"=== {n}[{i}]  (unread {q*100:.1f}%)\n{t}\n\n")
        print(f"{n}: {len(entries)} entries -> out/text/{n}.txt")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Decode the proportional display face used for item names and sign text.

Two sizes of the same face appear: a 9 px cut for the "examine" labels on world
objects, and a 13-15 px cut for signposts, shop boards and NPC nameplates.
Both are proportional, so the fixed grid used for dialogue does not apply.
"""
import pickle
import sys
from collections import Counter

sys.path.insert(0, "tools")
from propfont import parse, candidates, key      # noqa: E402

WORDGAP = 5            # gaps at or above this are word breaks
MAXRUN = 3             # characters one glyph box may swallow

SEEDS = {
    150: "Inn  One Night 150G\nRene Thomas",
    151: "Jack Leininger",
    152: "Christy Clements",
    153: "Leon Shore",
    154: "Janan Green\nAiron Green",
    155: "Jamie Porter",
    156: "Lyn Reinhardt",
    157: "Michael Hansen",
    158: "Jane Cowley",
    159: "Joe Santos",
    160: "Marilyn Miller",
    161: "Ed Edmund",
    162: "Robert Shreve",
    163: "Toni Gomez\nPriscilla Gomez",
    164: "Olivier Veyrac",
    165: "Krone Licht",
    166: "Lyn Reinhardt",
    167: "Mark Johnson",
    168: "Marilyn's Inn",
    169: "Stay Here Tonight\nMichael Hansen",
    179: "The Dwarve's Cave",
    180: "Verdite  East Edge\nValley of the Edge",
    183: "The Village of Cason",
    184: "No Entrance\nThe Royal Cemetery",
    185: "Ralugo>",
    186: "<The Palace of Wind",
    188: "<The Palace of Wind\nRalugo>",
    189: "DANGER!",
    190: "Gullick's Shop",
    191: "Jens, the Blacksmith",
    195: "Captain's Room",
    196: "Commander's Room",
    230: "Throne of Ichrius",
    235: "Lake Noel",
    236: "Danger\nDo Not Look",
    237: "The Land of Garan",
    238: "Varde's House>",
    239: "<Varde's House",
    242: "The Queen of Verdite\nNoel Forester",
    243: "Buried in the Darkness\nPrince Austin Lyle Forester",
    244: "Rest in Peace\nRojee",
    246: "Road Sign",
    247: "The Cave of Shudom",
    248: "The Emblem of the Wind",
    249: "Skeleton",
    250: "The Statue of the Hero",
    252: "The Royal Emblem",
    253: "Marilyn's Son",
    254: "Picture of a Warrior",
    255: "Broken Cart",
    256: "Animal's Skeleton",
    257: "The Dead Body of Nora",
    258: "A Wrecked Ship",
    259: "The Tomb of the Samurai",
    260: "The Dead Body of Leon",
    261: "The Tomb of Leon",
    262: "The Tomb of Rojee",
    263: "The Skeleton of the Giant",
    264: "The Dead Body of Sal",
    265: "The Dead Body of Endt",
    266: "The Dead Body of Lyn",
    267: "Yvette Bince",
    268: "The Skeleton of Elrus",
    269: "The Statue of Warren",
    550: "Special Weapon  128cm  3.1kg",
    621: "Special Armor      Others",
    651: "Special Effect Item",
    660: "Healing Related Special Item",
    680: "The Key to the Door",
}


def boxes(w, h, b):
    return [gl for li, gl in parse(w, h, b)]


def words(gl):
    """Group glyph boxes into words on the wide gaps."""
    out, cur = [], []
    for g in gl:
        if cur and g[1] >= WORDGAP:
            out.append(cur)
            cur = []
        cur.append(g)
    if cur:
        out.append(cur)
    return out


def align(boxword, word, font):
    """Split `word` across the boxes, letting kerned pairs share a box.

    Pairs such as 'of' segment as a single box, so a strict one-box-one-letter
    alignment never lines up. Boxes already in the font score higher, so
    repeated passes converge on a consistent reading of each merged pair.
    """
    nb, nc = len(boxword), len(word)
    if nb > nc:
        return None
    best = {(0, 0): (0, [])}
    for bi in range(nb):
        for ci in range(nc + 1):
            if (bi, ci) not in best:
                continue
            score, path = best[(bi, ci)]
            k = key(boxword[bi][2], boxword[bi][3])
            for take in range(1, MAXRUN + 1):
                if ci + take > nc:
                    break
                if nc - (ci + take) > (nb - bi - 1) * MAXRUN:
                    continue
                sub = word[ci:ci + take]
                bonus = 2 if (k in font and sub in font[k]) else 0
                bonus += 1 if take == 1 else 0
                cur = best.get((bi + 1, ci + take))
                if cur is None or score + bonus > cur[0]:
                    best[(bi + 1, ci + take)] = (score + bonus, path + [sub])
    hit = best.get((nb, nc))
    return hit[1] if hit else None


def learn(idx, rounds=4):
    """Grow the glyph table from the hand-read seed strings."""
    votes = {}
    for _ in range(rounds):
        for i, text in SEEDS.items():
            if i not in idx:
                continue
            w, h, b = idx[i]
            ls = boxes(w, h, b)
            want = text.split("\n")
            if len(ls) != len(want):
                continue
            for gline, tline in zip(ls, want):
                gw, tw = words(gline), tline.split()
                if len(gw) != len(tw):
                    continue
                for boxword, word in zip(gw, tw):
                    al = align(boxword, word, votes)
                    if al is None:
                        continue
                    for (x, gap, bm, top, adv), sub in zip(boxword, al):
                        votes.setdefault(key(bm, top), Counter())[sub] += 1
    return {k: c.most_common(1)[0][0] for k, c in votes.items()}


def decode(w, h, b, font, unk="?"):
    out = []
    for li, gl in parse(w, h, b):
        line = ""
        for x, gap, bm, top, adv in gl:
            if line and gap >= WORDGAP:
                line += " "
            line += font.get(key(bm, top), unk)
        out.append(line)
    return "\n".join(out)


def index(imgs, arc="ITEM"):
    return {i: (w, h, b) for i, j, w, h, b in candidates(imgs, arc)}


if __name__ == "__main__":
    import os
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    idx = index(imgs)
    font = learn(idx)
    print(f"glyphs learned: {len(font)}")
    rows = [(i, decode(*idx[i], font)) for i in sorted(idx)]
    clean = [r for r in rows if r[1] and "?" not in r[1]]
    print(f"clean entries: {len(clean)}/{len(rows)}")
    pickle.dump(font, open("out/propfont_map.pkl", "wb"))
    os.makedirs("out/text", exist_ok=True)
    with open("out/text/SIGNS.txt", "w") as fh:
        for i, t in rows:
            fh.write(f"=== ITEM[{i}]\n{t}\n\n")
    for i, t in rows:
        if "?" in t:
            print(f"  unresolved {i}: {t!r}")

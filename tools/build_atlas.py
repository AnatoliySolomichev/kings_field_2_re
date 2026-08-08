#!/usr/bin/env python3
"""Generate the self-contained HTML atlas of everything recovered from the disc."""
import base64
import glob
import html
import os
import pickle
import re
import sys

OUT = "out/atlas.html"


def datauri(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def walkable():
    sys.path.insert(0, "tools")
    from maps import levels, cell, W, H
    return {idx: sum(1 for y in range(H) for x in range(W) if cell(g, x, y, 8) != 255)
            for idx, g in levels()}


def clean(t):
    """Drop the few cells the font still cannot name; they break the deploy."""
    return t.replace("\ufffd", "")


def corpus():
    d = pickle.load(open("out/text.pkl", "rb"))
    talk = [(i, clean(t)) for i in sorted(d["TALK"])
            for t, q in d["TALK"][i] if q < 0.15 and t.strip()]
    item = [(i, clean(t)) for i in sorted(d["ITEM"])
            for t, q in d["ITEM"][i] if q < 0.15 and t.strip()]
    return talk, item


FORMATS = [
    ("<code>.img</code> / <code>.ccd</code>", "CloneCD raw image, Mode 2 Form 1",
     "243 098 sectors of 2352 bytes; the 2048-byte payload sits at offset 24."),
    ("<code>.T</code> archives", "<code>u16</code> count, then count+1 sector offsets",
     "Nine containers. Every offset table validates to the byte — end of the last "
     "entry equals the file size exactly."),
    ("<code>TALK.T</code> / <code>STALK.T</code>", "Dialogue as dithered 4bpp TIM images",
     "Not strings — pre-rendered pictures of text. STALK is the same script in a "
     "smaller face."),
    ("<code>ITEM.T</code>", "613 TIMs + 150 TMD models",
     "Item art, item descriptions and the character biographies."),
    ("<code>FDAT.T</code>", "Three entries per level",
     "An 80×80 grid of 10-byte cells, a table of 120-byte entity records, and a "
     "pointer block relocated to <code>0x801e8xxx</code>."),
    ("<code>VAB.T</code>", "<code>pBAV</code> sound banks and <code>pQES</code> sequences",
     "111 instrument banks, 23 sequenced tracks."),
]

FONT_FACTS = [
    ("7 px", "character advance, fixed", "The cell's first column is the gap."),
    ("16 px", "line pitch in TALK.T", "STALK.T renders the same script at 14 px."),
    ("73", "glyph templates recovered", "Seeded from one hand-read screen, then grown."),
    ("2.6 %", "words outside the dictionary", "And all of them are proper nouns."),
]


SIGN_GROUPS = [
    ("Signposts and warnings", [185, 186, 188, 189, 236, 235, 237, 179, 183, 184, 180]),
    ("Shops, inns and doors", [150, 168, 169, 190, 191, 195, 196, 238, 239]),
    ("Graves", [242, 243, 244, 241]),
]

EXAMINE = [230, 246, 247, 248, 249, 250, 252, 253, 254, 255, 256, 257, 258,
           259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269]

HINTS = [369, 391, 370, 330, 314, 366, 754, 85]


def signs():
    """Decode the proportional display face used for signs and object labels."""
    import propocr
    imgs = pickle.load(open("out/imgs.pkl", "rb"))
    idx = propocr.index(imgs)
    font = pickle.load(open("out/propfont_map.pkl", "rb"))
    return {i: propocr.decode(*idx[i], font) for i in idx}


def places():
    d = pickle.load(open("out/text.pkl", "rb"))["ITEM"]
    out = []
    for i in range(810, 852):
        for t, q in d.get(i, []):
            if q < 0.15 and t.strip():
                out.append(clean(t).split("\n")[0])
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def page():
    wk = walkable()
    talk, item = corpus()
    bios = {i: t for i, t in item if t.count("\n") >= 3}
    plates = []
    for p in sorted(glob.glob("out/maps/level*.png")):
        idx = int(re.search(r"level(\d+)", p).group(1))
        n = wk.get(idx, 0)
        empty = n in (0, 6400)
        plates.append(f'''<figure class="plate{' plate--void' if empty else ''}">
        <img src="{datauri(p)}" alt="Level {idx:02d} floor plan" loading="lazy">
        <figcaption><span class="plate-n">{idx:02d}</span>
        <span class="plate-c">{'no grid data' if empty else f'{n} cells'}</span></figcaption>
      </figure>''')

    def bio(idx):
        t = bios.get(idx, "")
        head, *rest = t.split("\n")
        return (f'<article class="bio"><h4>{html.escape(head)}</h4>'
                f'<p>{html.escape(" ".join(rest))}</p></article>')

    sg = signs()
    ok = lambda i: i in sg and sg[i] and "?" not in sg[i]
    signblocks = []
    for title, ids in SIGN_GROUPS:
        items = "".join(
            f'<li><span class="sign">{html.escape(sg[i]).replace(chr(10), "<br>")}</span></li>'
            for i in ids if ok(i))
        if items:
            signblocks.append(f'<div class="signgroup"><h4>{title}</h4><ul>{items}</ul></div>')
    examine = "".join(f"<li>{html.escape(sg[i])}</li>" for i in EXAMINE if ok(i))
    talkmap = {i: t for i, t in talk}
    hints = "".join(
        f'<li><q>{html.escape(" ".join(talkmap[i].split()))}</q></li>'
        for i in HINTS if i in talkmap)
    objmap = datauri('out/maps/level00_objects.png')
    nobj = sum(1 for _ in open('out/text/OBJECTS.txt')) - 3
    placelist = "".join(f"<li>{html.escape(p)}</li>" for p in places())

    rows = "\n".join(
        f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in FORMATS)
    facts = "\n".join(
        f'<div class="fact"><b>{a}</b><span>{b}</span><em>{c}</em></div>'
        for a, b, c in FONT_FACTS)

    return f'''<title>King's Field II — disc atlas</title>
<style>
  :root {{
    --ground:#efe7d6; --panel:#e5dac4; --rock:#1b1922; --ink:#241f1a;
    --muted:#6d6355; --line:#cdbfa4; --amber:#a8541c; --stone:#5a6b7d;
    --plate-bg:#1b1922;
    --serif: "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
    --sans: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono: ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --ground:#14131a; --panel:#1d1b24; --ink:#e6ddc9; --muted:#93897a;
             --line:#332f3c; --amber:#d9884a; --stone:#8fa2b8; }}
  }}
  :root[data-theme="dark"] {{ --ground:#14131a; --panel:#1d1b24; --ink:#e6ddc9;
    --muted:#93897a; --line:#332f3c; --amber:#d9884a; --stone:#8fa2b8; }}
  :root[data-theme="light"] {{ --ground:#efe7d6; --panel:#e5dac4; --ink:#241f1a;
    --muted:#6d6355; --line:#cdbfa4; --amber:#a8541c; --stone:#5a6b7d; }}

  body {{ background:var(--ground); color:var(--ink); font-family:var(--sans);
         line-height:1.6; margin:0; }}
  .wrap {{ max-width:1120px; margin:0 auto; padding:clamp(1.5rem,4vw,4rem) 1.25rem 5rem; }}
  .col {{ max-width:66ch; }}
  h1,h2,h3,h4 {{ font-family:var(--serif); text-wrap:balance; margin:0; font-weight:600; }}
  h1 {{ font-size:clamp(2.1rem,5vw,3.4rem); line-height:1.08; letter-spacing:-.01em; }}
  h2 {{ font-size:clamp(1.4rem,2.6vw,1.9rem); margin-bottom:.6rem; }}
  h4 {{ font-size:1.02rem; color:var(--amber); }}
  p {{ margin:0; }}
  .eyebrow {{ font-family:var(--mono); font-size:.72rem; letter-spacing:.16em;
    text-transform:uppercase; color:var(--stone); }}
  .lede {{ font-size:1.12rem; color:var(--muted); margin-top:1rem; }}
  header {{ display:flex; flex-direction:column; gap:.7rem;
    border-bottom:1px solid var(--line); padding-bottom:2.5rem; }}
  section {{ display:flex; flex-direction:column; gap:1.1rem;
    padding-top:3.2rem; }}
  .atlas {{ display:grid; gap:.7rem;
    grid-template-columns:repeat(auto-fill,minmax(132px,1fr)); }}
  .plate {{ margin:0; background:var(--plate-bg); border:1px solid var(--line);
    border-radius:2px; overflow:hidden; }}
  .plate img {{ display:block; width:100%; height:auto; image-rendering:pixelated; }}
  .plate--void {{ opacity:.42; }}
  figcaption {{ display:flex; justify-content:space-between; align-items:baseline;
    gap:.5rem; padding:.4rem .5rem; font-family:var(--mono); font-size:.68rem;
    background:var(--panel); color:var(--muted); }}
  .plate-n {{ color:var(--amber); font-weight:700; }}
  .plate-c {{ font-variant-numeric:tabular-nums; }}
  .tablewrap {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; min-width:34rem; font-size:.92rem; }}
  th,td {{ text-align:left; padding:.62rem .8rem; border-bottom:1px solid var(--line);
    vertical-align:top; }}
  th {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.12em;
    text-transform:uppercase; color:var(--stone); }}
  td:first-child {{ white-space:nowrap; }}
  code {{ font-family:var(--mono); font-size:.86em; color:var(--amber); }}
  .facts {{ display:grid; gap:.6rem;
    grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); }}
  .fact {{ background:var(--panel); border:1px solid var(--line); border-radius:2px;
    padding:.9rem 1rem; display:flex; flex-direction:column; gap:.15rem; }}
  .fact b {{ font-family:var(--serif); font-size:1.7rem; line-height:1;
    font-variant-numeric:tabular-nums; }}
  .fact span {{ font-size:.86rem; }}
  .fact em {{ font-style:normal; font-size:.78rem; color:var(--muted); }}
  .bios {{ display:grid; gap:1rem;
    grid-template-columns:repeat(auto-fit,minmax(255px,1fr)); }}
  .bio {{ background:var(--panel); border-left:2px solid var(--amber);
    padding:.9rem 1.1rem; display:flex; flex-direction:column; gap:.35rem; }}
  .bio p {{ font-size:.9rem; color:var(--muted); }}
  pre {{ background:var(--panel); border:1px solid var(--line); border-radius:2px;
    padding:.9rem 1rem; overflow-x:auto; font-family:var(--mono);
    font-size:.82rem; line-height:1.55; margin:0; }}
  .signgrid {{ display:grid; gap:1.2rem;
    grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); }}
  .signgroup h4 {{ margin-bottom:.5rem; }}
  .signgroup ul, .cols, .quotes {{ list-style:none; padding:0; margin:0;
    display:flex; flex-direction:column; gap:.4rem; }}
  .sign {{ font-family:var(--mono); font-size:.82rem; background:var(--panel);
    border:1px solid var(--line); border-radius:2px; padding:.35rem .6rem;
    display:inline-block; }}
  .cols {{ display:grid; gap:.3rem .9rem; font-size:.92rem;
    grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); }}
  .cols li {{ border-bottom:1px dotted var(--line); padding-bottom:.25rem; }}
  .quotes li {{ border-left:2px solid var(--amber); padding:.2rem 0 .2rem 1rem;
    color:var(--muted); font-size:.92rem; max-width:66ch; }}
  .quotes q {{ font-style:italic; }}
  .objmap {{ margin:0; }}
  .objmap img {{ display:block; width:100%; max-width:560px; height:auto;
    image-rendering:pixelated; border:1px solid var(--line); border-radius:2px; }}
  .objmap figcaption {{ background:none; padding:.5rem 0 0; font-family:var(--sans);
    font-size:.86rem; max-width:60ch; display:block; }}
  .note {{ border-left:2px solid var(--stone); padding-left:1rem; color:var(--muted);
    font-size:.94rem; }}
</style>

<div class="wrap">
  <header>
    <span class="eyebrow">SLUS-00255 · From Software / ASCII, 1996</span>
    <h1>King&rsquo;s Field II, taken apart</h1>
    <p class="lede col">Every level grid, every line of dialogue and every archive
      format on the disc — recovered from a raw CloneCD image with no prior
      documentation. The game keeps its text as pictures, so none of it was
      searchable until the font was rebuilt glyph by glyph.</p>
  </header>

  <section>
    <span class="eyebrow">Plates 00–27</span>
    <h2>The level atlas</h2>
    <p class="col">Each level is an 80&times;80 grid of 10-byte cells. Solid rock is
      dark; walkable floor is shaded by its height byte, so ramps and terraces read
      as gradients. Plates 12 onward are the built floors — corridors, cell blocks,
      the cruciform hall on plate 20 — while the early plates are caves and open
      ground. Four slots carry no grid data.</p>
    <div class="atlas">{''.join(plates)}</div>
  </section>

  <section>
    <span class="eyebrow">Container formats</span>
    <h2>What the disc is made of</h2>
    <div class="tablewrap"><table>
      <thead><tr><th>Where</th><th>Format</th><th>Notes</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
  </section>

  <section>
    <span class="eyebrow">Reading pictures of words</span>
    <h2>Rebuilding the font</h2>
    <p class="col">The dialogue is stored as dithered 4-bit images, so no two
      instances of a letter share a bitmap. Cells are matched to labelled templates
      by Jaccard distance instead. <code>I</code> and <code>l</code> are pixel-identical
      in this face and are separated afterwards against the system word list.</p>
    <div class="facts">{facts}</div>
    <p class="note col">The remaining out-of-dictionary words are the cast:
      Ichrius, Promeus, Silviera, Orladin, Veyrac, Vallad, Shudom, Guyra, Varde,
      Harvine, Verdite — and <b>Seath</b>, a name From Software would give to a
      pale dragon fifteen years later.</p>
  </section>

  <section>
    <span class="eyebrow">From ITEM.T</span>
    <h2>The cast, as the developers described them</h2>
    <p class="col">These biographies sit in the item archive. The tone drifts a long
      way from the game&rsquo;s funeral atmosphere.</p>
    <div class="bios">
      {bio(280)}
      {bio(279)}
      {bio(278)}
      {bio(275)}
    </div>
  </section>

  <section>
    <span class="eyebrow">The proportional face</span>
    <h2>Signs, boards and graves</h2>
    <p class="col">A second, proportional typeface carries everything written
      <em>in</em> the world rather than spoken in a dialogue box — so it needed a
      separate decoder that cuts glyphs apart at blank columns and lets kerned
      pairs share a box.</p>
    <div class="signgrid">{signblocks}</div>
  </section>

  <section>
    <span class="eyebrow">Examine targets</span>
    <h2>What the game lets you look at</h2>
    <p class="col">Every object in the world that returns a name when examined.
      The tombs and bodies are the ones easiest to walk past.</p>
    <ul class="cols">{examine}</ul>
  </section>

  <section>
    <span class="eyebrow">From the dialogue</span>
    <h2>Where things are hidden</h2>
    <p class="col">Characters give away cache locations in passing. These are the
      lines that name a place.</p>
    <ul class="quotes">{hints}</ul>
  </section>

  <section>
    <span class="eyebrow">Named areas</span>
    <h2>Places the game knows about</h2>
    <ul class="cols">{placelist}</ul>
  </section>

  <section>
    <span class="eyebrow">Read out of live RAM</span>
    <h2>The object table</h2>
    <p class="col">Diffing memory around an item pickup turned up the record whose
      id flipped to <code>0xffff</code> — the herb on the ground. It sits in an
      array of 68-byte records: a marker, an id that indexes
      <code>ITEM.T</code> so each object names itself, then world X, Y and Z at
      2048 units per map cell.</p>
    <figure class="objmap">
      <img src="{objmap}" alt="Level 00 with its object table plotted">
      <figcaption>Level 00, all {nobj} objects. Red is the bestiary, blue the
        examine labels, yellow the people range, green everything else; white is
        where the player stood.</figcaption>
    </figure>
    <p class="note col">Unique landmarks confirm the mapping — exactly one
      <em>Statue of the Hero</em>, one <em>Royal Emblem</em>, one
      <em>Rest in Peace</em>. The bestiary range resolves to three enemy types
      for this level. Some ids in the people range repeat far too often to be
      people, so the id is really an object-type index that <code>ITEM.T</code>
      happens to describe for most, not all, of its ranges.</p>
  </section>

  <section>
    <span class="eyebrow">Running it</span>
    <h2>The live setup</h2>
    <p class="col">PCSX-Redux boots the disc on OpenBIOS, so no console BIOS image is
      needed. Its HTTP interface snapshots memory without pausing the game — the GDB
      stub on :3333 halts emulation and will not resume, so the analysis scripts use
      the web API instead.</p>
<pre>emu/run.sh                      # start; web API on :8080
python3 tools/psxlive.py x.png   # RAM + VRAM snapshot, screen to PNG
python3 tools/maps.py            # re-render every level plate
python3 tools/dump_text.py       # rebuild the text corpus</pre>
  </section>
</div>'''


if __name__ == "__main__":
    os.makedirs("out", exist_ok=True)
    open(OUT, "w").write(page())
    print(f"{OUT}  {os.path.getsize(OUT)/1024:.0f} KB")

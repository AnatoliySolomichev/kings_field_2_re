#!/usr/bin/env python3
"""Build the interactive level maps: terrain plus every object, labelled.

Object ids are global object-type ids. MO.T always has a model for them; ITEM.T
carries description text for most, which is where the generic names come from.
Ids confirmed by experiment override that text.
"""
import base64
import html
import json
import os
import struct
import sys

sys.path.insert(0, "tools")
from objects import find_table, table, names, which_level, CELL, EMPTY, RAM_BASE  # noqa: E402
from maps import W, H                                                            # noqa: E402

SCALE = 12
OUT = "out/levelmap.html"
PLAYER = 0x801AEC4C

# Established by diffing snapshots taken around a deliberate action.
# Confirmed either by a controlled experiment or by the player reporting it in
# game. These are rendered with a trailing "!"; guesses taken from ITEM.T text
# get a "?" instead.
KNOWN = {
    104: ("Earth Herb", "pick"),
    105: ("Antidote", "pick"),
    106: ("Chest", "act"),
    154: ("Revealed with the chest", "act"),
    175: ("Locked door with a keyhole", "act"),
    177: ("Door", "act"),
    192: ("Tombstone", "act"),
    196: ("Chipped tombstone", "act"),
    227: ("Save point", "act"),
    257: ("Keyhole for door 175", "act"),
    324: ("Tree", "scenery"),
}


def naming(i, nm):
    """A confirmed name ends in '!', a guess from ITEM.T in '?'."""
    if i in KNOWN:
        return KNOWN[i][0] + "!", True
    t = nm.get(i, "")
    return (t + "?", False) if t else ("", False)

CATS = [
    ("act", "Chests and doors", "#f0722c"),
    ("scenery", "Scenery", "#6b7f6b"),
    ("pick", "Named pickups", "#3fb27f"),
    ("beast", "Bestiary", "#d4544a"),
    ("mark", "Examine targets", "#4d9fe0"),
    ("folk", "Biography range", "#e8bf4e"),
    ("prop", "Other props", "#8aa0b8"),
]


def cat(i):
    if i in KNOWN:
        return KNOWN[i][1]
    if 320 <= i <= 386:
        return "beast"
    if 230 <= i <= 269:
        return "mark"
    if 270 <= i <= 313:
        return "folk"
    return "prop"


def datauri(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def collect(snap):
    buf = open(f"out/snap/{snap}.ram", "rb").read()
    objs = [o for o in table(buf, find_table(buf)) if o["id"] != EMPTY]
    lv = which_level(objs)[0]
    px, py, pz = struct.unpack_from("<iii", buf, PLAYER - RAM_BASE)
    return objs, lv[1], lv[0], (px, py, pz)


def level_payload(snap, nm, mo):
    objs, lv, conf, player = collect(snap)
    items = []
    for o in objs:
        i = o["id"]
        items.append({
            "id": i, "x": o["x"], "y": o["y"], "z": o["z"],
            "name": naming(i, nm)[0],
            "sure": i in KNOWN,
            "gold": o.get("gold"),
            "cat": cat(i),
            "model": (mo.off[i + 1] - mo.off[i]) * 2048 if i + 1 < len(mo.off) else 0,
        })
    items.sort(key=lambda d: (d["cat"], d["id"]))
    return {"level": lv, "conf": round(conf * 100, 1), "player": player,
            "objs": items, "img": datauri(f"out/maps/level{lv:02d}_detail.png")}


def build(snaps):
    nm = names()
    from tarc import TArc
    mo = TArc("extract/CD/COM/MO.T")
    levels = [level_payload(s, nm, mo) for s in snaps]
    tabs = "".join(
        f'<button class="tab" data-lv="{n}"{" aria-pressed=\"true\"" if n == 0 else ""}>'
        f'Level {L["level"]:02d}<em>{len(L["objs"])}</em></button>'
        for n, L in enumerate(levels))
    legend = "".join(
        f'<button class="cat" data-cat="{k}" style="--c:{c}" aria-pressed="true">'
        f'<span class="dot"></span>{lbl}</button>' for k, lbl, c in CATS)

    return f'''<title>King's Field II — levels in detail</title>
<style>
  :root {{
    --bg:#f2eee3; --panel:#e7e0d0; --ink:#26221c; --muted:#6f6658;
    --line:#cec3ad; --accent:#a8541c;
    --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  }}
  @media (prefers-color-scheme:dark) {{
    :root {{ --bg:#15141a; --panel:#1e1c24; --ink:#e7dfcd; --muted:#968b7b;
             --line:#343040; --accent:#dc8b4c; }}
  }}
  :root[data-theme="dark"] {{ --bg:#15141a; --panel:#1e1c24; --ink:#e7dfcd;
    --muted:#968b7b; --line:#343040; --accent:#dc8b4c; }}
  :root[data-theme="light"] {{ --bg:#f2eee3; --panel:#e7e0d0; --ink:#26221c;
    --muted:#6f6658; --line:#cec3ad; --accent:#a8541c; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:var(--sans); line-height:1.55; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:2rem 1.1rem 4rem;
    display:flex; flex-direction:column; gap:1.2rem; }}
  h1 {{ font-family:var(--serif); font-size:clamp(1.8rem,4vw,2.7rem);
    margin:0; line-height:1.1; text-wrap:balance; }}
  .eyebrow {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.16em;
    text-transform:uppercase; color:var(--muted); }}
  p {{ margin:0; max-width:68ch; color:var(--muted); }}
  .bar {{ display:flex; flex-wrap:wrap; gap:.45rem; align-items:center; }}
  .tab, .cat {{ font:inherit; font-size:.83rem; cursor:pointer; color:var(--ink);
    background:var(--panel); border:1px solid var(--line); border-radius:999px;
    padding:.3rem .8rem; display:inline-flex; align-items:center; gap:.45rem; }}
  .tab[aria-pressed="true"] {{ border-color:var(--accent); color:var(--accent); }}
  .tab em, .cat em {{ font-style:normal; color:var(--muted);
    font-variant-numeric:tabular-nums; }}
  .cat .dot {{ width:.6rem; height:.6rem; border-radius:50%; background:var(--c); }}
  .cat[aria-pressed="false"] {{ opacity:.32; }}
  .tab:focus-visible, .cat:focus-visible {{ outline:2px solid var(--accent);
    outline-offset:2px; }}
  .mapwrap {{ position:relative; overflow:auto; border:1px solid var(--line);
    border-radius:3px; background:#12111a; }}
  .map {{ position:relative; width:{W*SCALE}px; height:{H*SCALE}px; }}
  .map img {{ display:block; width:100%; height:100%; image-rendering:pixelated; }}
  .pin {{ position:absolute; width:11px; height:11px; margin:-5.5px 0 0 -5.5px;
    border-radius:50%; border:1.5px solid rgba(0,0,0,.65); cursor:pointer; }}
  .pin.big {{ width:15px; height:15px; margin:-7.5px 0 0 -7.5px; border-width:2px; }}
  .pin[hidden] {{ display:none; }}
  .pin.sel {{ box-shadow:0 0 0 3px #fff, 0 0 0 6px rgba(0,0,0,.65); z-index:5; }}
  @keyframes ping {{ from {{ transform:scale(1); opacity:1; }}
                     to {{ transform:scale(3.2); opacity:0; }} }}
  .pin.sel::after {{ content:""; position:absolute; inset:-2px; border-radius:50%;
    border:2px solid #fff; animation:ping .9s ease-out 2; }}
  @media (prefers-reduced-motion:reduce) {{ .pin.sel::after {{ animation:none; }} }}
  tbody tr {{ cursor:pointer; }}
  tr.sel {{ background:var(--panel); outline:2px solid var(--accent);
    outline-offset:-2px; }}
  .you {{ position:absolute; width:17px; height:17px; margin:-8.5px 0 0 -8.5px;
    border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 2px rgba(0,0,0,.6); }}
  .tip {{ position:fixed; z-index:20; pointer-events:none; background:var(--panel);
    color:var(--ink); border:1px solid var(--line); border-radius:3px;
    padding:.4rem .6rem; font-size:.8rem; font-family:var(--mono);
    box-shadow:0 6px 20px rgba(0,0,0,.3); max-width:22rem; }}
  .tip[hidden] {{ display:none; }}
  table {{ border-collapse:collapse; width:100%; font-size:.87rem; }}
  th,td {{ text-align:left; padding:.35rem .6rem; border-bottom:1px solid var(--line); }}
  th {{ font-family:var(--mono); font-size:.68rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--muted); }}
  td.id, td.num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}
  td .sure {{ color:var(--accent); }}
  tr[hidden] {{ display:none; }}
  tr.hot {{ background:var(--panel); }}
  .tablewrap {{ max-height:24rem; overflow:auto; border:1px solid var(--line);
    border-radius:3px; }}
  .selcard {{ display:flex; gap:1rem; align-items:center; background:var(--panel);
    border:1px solid var(--accent); border-radius:3px; padding:.7rem 1rem; }}
  .selcard[hidden] {{ display:none; }}
  .selname {{ font-family:var(--serif); font-size:1.15rem; }}
  .selmeta {{ font-family:var(--mono); font-size:.78rem; color:var(--muted); }}
  #unsel {{ margin-left:auto; font:inherit; font-size:.8rem; cursor:pointer;
    background:none; color:var(--muted); border:1px solid var(--line);
    border-radius:999px; padding:.2rem .7rem; }}
</style>

<div class="wrap">
  <header>
    <span class="eyebrow">SLUS-00255 · 80&times;80 cells of 2048 units · north up</span>
    <h1>Every object on the level, read from memory</h1>
  </header>
  <p>Ground is shaded by its height byte, so terraces and water channels read as
    steps and solid rock is dark. Each pin is a live entry in the level's object
    table. Names in orange were confirmed by experiment — opening the chest,
    opening the door, reading the item screen; the rest are whatever
    <code>ITEM.T</code> holds at that index, which is not reliable for every
    range.</p>

  <div class="bar" id="tabs">{tabs}</div>
  <div class="bar" id="cats">{legend}</div>
  <p id="meta"></p>

  <div class="mapwrap"><div class="map" id="map"><img id="terrain" alt="Level terrain"></div></div>

  <div class="selcard" id="selcard" hidden>
    <div>
      <div class="selname" id="selname"></div>
      <div class="selmeta" id="selmeta"></div>
    </div>
    <button id="unsel">clear</button>
  </div>

  <div class="tablewrap"><table>
    <thead><tr><th>id</th><th>What it is</th><th>cell</th><th>height</th></tr></thead>
    <tbody id="rows"></tbody>
  </table></div>
</div>

<div class="tip" id="tip" hidden></div>
<script>
const LEVELS = {json.dumps(levels)};
const COL = {json.dumps({k: c for k, _, c in CATS})};
const SCALE = {SCALE}, H = {H}, CELL = {CELL};
const map = document.getElementById('map'), tip = document.getElementById('tip');
const rows = document.getElementById('rows'), meta = document.getElementById('meta');
const img = document.getElementById('terrain');
const off = new Set();
let cur = 0, pins = [];

function draw() {{
  const L = LEVELS[cur];
  img.src = L.img;
  map.querySelectorAll('.pin,.you').forEach(e => e.remove());
  meta.textContent = 'Level ' + String(L.level).padStart(2, '0') + ' — ' +
    L.objs.length + ' objects, identified by the height relation at ' + L.conf + '%.';
  pins = L.objs.map((o, i) => {{
    const p = document.createElement('div');
    p.className = 'pin' + (o.sure ? ' big' : '');
    p.dataset.idx = i;
    p.style.left = (o.x / CELL * SCALE).toFixed(1) + 'px';
    p.style.top = ((H - o.z / CELL) * SCALE).toFixed(1) + 'px';
    p.style.background = COL[o.cat];
    p.hidden = off.has(o.cat);
    map.appendChild(p);
    return p;
  }});
  const you = document.createElement('div');
  you.className = 'you';
  you.title = 'where the player stood';
  you.style.left = (L.player[0] / CELL * SCALE).toFixed(1) + 'px';
  you.style.top = ((H - L.player[2] / CELL) * SCALE).toFixed(1) + 'px';
  map.appendChild(you);
  rows.innerHTML = L.objs.map((o, i) =>
    '<tr data-cat="' + o.cat + '" data-idx="' + i + '"' + (off.has(o.cat) ? ' hidden' : '') + '>' +
    '<td class="id">' + o.id + '</td><td' + (o.sure ? ' class="sure"' : '') + '>' +
    (o.name || '<i>no description entry</i>') + '</td>' +
    '<td class="num">' + Math.floor(o.x / CELL) + ',' + Math.floor(o.z / CELL) + '</td>' +
    '<td class="num">' + o.y + '</td></tr>').join('');
}}

map.addEventListener('mousemove', e => {{
  const t = e.target.closest('.pin');
  document.querySelectorAll('tr.hot').forEach(r => r.classList.remove('hot'));
  if (!t) {{ tip.hidden = true; return; }}
  const o = LEVELS[cur].objs[+t.dataset.idx];
  tip.innerHTML = 'id ' + o.id + (o.name ? ' — ' + o.name : '') +
    '<br>cell ' + Math.floor(o.x / CELL) + ',' + Math.floor(o.z / CELL) +
    '  ·  y ' + o.y + '<br>model ' + o.model + ' bytes in MO.T';
  tip.hidden = false;
  tip.style.left = Math.min(e.clientX + 14, innerWidth - 260) + 'px';
  tip.style.top = (e.clientY + 14) + 'px';
  const row = rows.querySelector('tr[data-idx="' + t.dataset.idx + '"]');
  if (row) {{ row.classList.add('hot'); row.scrollIntoView({{block: 'nearest'}}); }}
}});
map.addEventListener('mouseleave', () => tip.hidden = true);

const selcard = document.getElementById('selcard');
function select(i) {{
  pins.forEach(p => p.classList.remove('sel'));
  rows.querySelectorAll('tr').forEach(r => r.classList.remove('sel'));
  const p = pins[i], r = rows.querySelector('tr[data-idx="' + i + '"]');
  const o = LEVELS[cur].objs[i];
  if (!p || !o) {{ selcard.hidden = true; return; }}
  p.classList.remove('sel'); void p.offsetWidth; p.classList.add('sel');
  if (r) r.classList.add('sel');
  p.scrollIntoView({{block: 'center', inline: 'center', behavior: 'smooth'}});
  document.getElementById('selname').textContent = o.name || 'unidentified';
  document.getElementById('selmeta').innerHTML =
    'type id ' + o.id + ' &middot; cell ' + Math.floor(o.x / CELL) + ',' +
    Math.floor(o.z / CELL) + ' &middot; height ' + o.y +
    ' &middot; model ' + o.model + ' bytes' +
    (o.gold != null ? ' &middot; &#9733; ' + o.gold + ' gold' : '');
  selcard.hidden = false;
}}
document.getElementById('unsel').onclick = () => {{
  pins.forEach(p => p.classList.remove('sel'));
  rows.querySelectorAll('tr').forEach(r => r.classList.remove('sel'));
  selcard.hidden = true;
}};
rows.addEventListener('click', e => {{
  const tr = e.target.closest('tr');
  if (tr) select(+tr.dataset.idx);
}});
map.addEventListener('click', e => {{
  const t = e.target.closest('.pin');
  if (t) select(+t.dataset.idx);
}});

document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {{
  cur = +b.dataset.lv;
  document.querySelectorAll('.tab').forEach(x =>
    x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
  draw(); selcard.hidden = true;
}}));
document.querySelectorAll('.cat').forEach(b => b.addEventListener('click', () => {{
  const c = b.dataset.cat;
  off.has(c) ? off.delete(c) : off.add(c);
  b.setAttribute('aria-pressed', off.has(c) ? 'false' : 'true');
  pins.forEach((p, i) => p.hidden = off.has(LEVELS[cur].objs[i].cat));
  rows.querySelectorAll('tr').forEach(r => r.hidden = off.has(r.dataset.cat));
}}));
draw();
</script>'''


if __name__ == "__main__":
    os.makedirs("out", exist_ok=True)
    open(OUT, "w").write(build(["b", "lvl2"]))
    print(f"{OUT}  {os.path.getsize(OUT)/1024:.0f} KB")

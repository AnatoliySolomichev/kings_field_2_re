#!/usr/bin/env python3
"""Live map: follow the player around the level in a browser, in real time.

    python3 tools/livemap.py          # then open http://localhost:8777

A published artifact cannot reach the emulator (different origin, and the page
is sandboxed), so this serves the map itself and reads the emulator's HTTP API
on the same origin. The heavy steps -- locating the object table and matching
the level -- are cached and only redone when the table stops looking valid,
which is what happens when a new level loads.
"""
import http.server
import json
import os
import socketserver
import struct
import sys
import threading
import urllib.request

sys.path.insert(0, "tools")
from objects import (find_table, table, names, which_level, slots,       # noqa: E402
                     CELL, EMPTY, RAM_BASE, STRIDE)
from maps import levels, W, H                                            # noqa: E402
import player                                                            # noqa: E402
from build_levelmap import KNOWN, CATS, cat, naming                      # noqa: E402
import level_map                                                         # noqa: E402
import tim                                                               # noqa: E402

NAMES_FILE = "data/level_names.json"
AREAS_FILE = "data/area_names.json"
IGNORE_FILE = "data/ignored_ids.json"
HIDE_FILE = "data/hidden_objects.json"      # single instances, keyed id@cx,cz
TRANS_FILE = "data/transitions.json"        # where one level hands over to another
POS_COPIES = [0x801B0A10, 0x801B25F0, 0x801AEC4C, 0x801FFF98]
PORT = 8777
EMU = "http://127.0.0.1:8080/api/v1"
PLAYER = 0x801AEC4C
# Current level index, found by intersecting a snapshot diff (0 on level 0,
# 4 on level 4) with the disassembly's cross-references: of 32 727 raw byte
# candidates only 28 are addressed by code at all, and this one sits in a small
# state block that the level-setup code around 0x800179xx writes.
LEVEL_ID = 0x8018FAD9
SCALE = 12

_lock = threading.Lock()
_state = {"tbl": None, "level": None, "conf": 0.0, "gen": 0, "objs": [], "sig": None,
          "digest": [], "changed": set()}
_names = None
_grids = None


def ram():
    with urllib.request.urlopen(EMU + "/cpu/ram/raw", timeout=10) as r:
        return r.read()


def signature(buf, tbl):
    """Cheap fingerprint of the table: how many live records and their first ids."""
    if tbl is None:
        return None
    ids = [struct.unpack_from("<H", buf, off + 6)[0] for _, off in slots(buf, tbl)]
    return (len(ids), tuple(ids[:6])) if ids else None


STICKY = 0.08          # a rival level must beat the current one by this much
MIN_RECORDS = 20       # a real level table is far longer than this


def runlen(buf, tbl):
    return sum(1 for _ in slots(buf, tbl))


def note_transition(old_lv, new_lv, px, pz):
    """Record where the game swapped levels. The seams are not marked in the
    world, so the only way to map them is to catch the moment they happen."""
    if old_lv is None or new_lv is None or old_lv == new_lv:
        return
    d = load_json(TRANS_FILE, [])
    entry = {"from": old_lv, "to": new_lv,
             "cell": [px // CELL, pz // CELL], "x": px, "z": pz}
    if entry not in d:
        d.append(entry)
        os.makedirs(os.path.dirname(TRANS_FILE), exist_ok=True)
        json.dump(d, open(TRANS_FILE, "w"), indent=1)
    return d


def refresh(buf, px=0, pz=0):
    """Recompute the object list, and the level only when it is worth it.

    Two things made the map jump to the wrong level while the player was just
    walking: rescanning for the table on every change (the scan can land on a
    different run of records), and taking the top scoring level even when it
    barely edged out the current one. So the known table address is kept while
    it still parses, and a rival level has to win by a clear margin.
    """
    global _names
    if _names is None:
        _names = names()
    # Never trust the cached address here. RAM holds other runs of records that
    # pass the loose per-record check -- one of 36 sits a few KB from the real
    # table -- so a stale address can look healthy forever and the map stays
    # empty. find_table picks the longest run, which is the real one.
    tbl = find_table(buf)
    if tbl is None or runlen(buf, tbl) < MIN_RECORDS:
        return
    objs = [o for o in table(buf, tbl) if o["id"] != EMPTY]
    score = which_level(objs)
    if not score:
        return
    conf, lv = score[0]
    cur = _state["level"]
    if cur is not None and lv != cur:
        cur_conf = next((c for c, i in score if i == cur), 0.0)
        if conf < cur_conf + STICKY:
            lv, conf = cur, cur_conf
    note_transition(_state["level"], lv, px, pz)
    changed = (lv != _state["level"] or len(objs) != len(_state["objs"]))
    _state["changed"] = set()
    _state["digest"] = digests(buf, tbl)
    _state.update(
        tbl=tbl, level=lv, conf=round(conf * 100, 1), sig=signature(buf, tbl),
        gen=_state["gen"] + 1 if changed else _state["gen"],
        objs=[{"id": o["id"], "x": o["x"], "y": o["y"], "z": o["z"],
               "name": naming(o["id"], _names)[0], "gold": o.get("gold"),
               "sure": o["id"] in KNOWN, "cat": cat(o["id"])} for o in objs])


def digests(buf, tbl):
    """One fingerprint per record, so a record that changes can be flagged.
    The coordinate block is skipped: things that walk would flag constantly."""
    return [buf[off:off + 0x14] + buf[off + 0x20:off + STRIDE]
            for _, off in slots(buf, tbl)]


def poll():
    buf = ram()
    px, py, pz = struct.unpack_from("<iii", buf, PLAYER - RAM_BASE)
    lvid = buf[LEVEL_ID - RAM_BASE]
    with _lock:
        # The cached address is only a fast path. Anything that smells wrong --
        # a changed signature, too few records, a level match that never
        # convinced us -- forces a full rescan.
        stale = (_state["tbl"] is None
                 or len(_state["objs"]) < MIN_RECORDS
                 or _state["conf"] < 40.0
                 or runlen(buf, _state["tbl"]) < MIN_RECORDS
                 or signature(buf, _state["tbl"]) != _state["sig"])
        if stale:
            refresh(buf, px, pz)
        elif _state["tbl"] is not None:
            now = digests(buf, _state["tbl"])
            old = _state["digest"]
            if old and len(old) == len(now):
                for i, (a, b) in enumerate(zip(old, now)):
                    if a != b:
                        _state["changed"].add(i)
            _state["digest"] = now
        # The byte is authoritative when it agrees with the terrain match;
        # both are reported so a disagreement is visible rather than hidden.
        lv = lvid if lvid < 28 else _state["level"]
        stats = player.read(buf)
        return {"ok": True, "changed": sorted(_state["changed"]),
                "stats": {k: stats[k] for k in
                          ("level", "hp", "hp_max", "mp", "mp_max", "gold",
                           "exp", "exp_next")},
                "levelId": lvid, "guessed": _state["level"],
                "gen": _state["gen"], "level": lv,
                "conf": _state["conf"], "player": [px, py, pz],
                "cell": [px // CELL, pz // CELL], "count": len(_state["objs"]),
                "table": _state["tbl"] + RAM_BASE if _state["tbl"] else 0}


def load_json(path, default):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def save_level_name(lv, name):
    d = load_json(NAMES_FILE, {})
    if name:
        d[str(lv)] = name
    else:
        d.pop(str(lv), None)
    os.makedirs(os.path.dirname(NAMES_FILE), exist_ok=True)
    json.dump(d, open(NAMES_FILE, "w"), indent=1, ensure_ascii=False)
    return d


def save_ignore(oid, on):
    d = set(load_json(IGNORE_FILE, []))
    d.add(oid) if on else d.discard(oid)
    os.makedirs(os.path.dirname(IGNORE_FILE), exist_ok=True)
    out = sorted(d)
    json.dump(out, open(IGNORE_FILE, "w"))
    return out


def save_hidden(key, on):
    d = set(load_json(HIDE_FILE, []))
    d.add(key) if on else d.discard(key)
    os.makedirs(os.path.dirname(HIDE_FILE), exist_ok=True)
    out = sorted(d)
    json.dump(out, open(HIDE_FILE, "w"))
    return out


def teleport(x, z):
    """Move the player. The position lives in four copies that the game keeps
    in step; writing only one is overwritten again within a frame, so all four
    go at once. Y is taken from the terrain so we land on the ground."""
    import psxdbg
    global _grids
    if _grids is None:
        _grids = dict(levels())
    lv = _state["level"]
    grid = _grids.get(lv)
    gx, gz = x // CELL, z // CELL
    from maps import cell as gcell
    if grid is None or gcell(grid, gx, gz, 8) == 0xFF:
        return {"ok": False, "error": "that cell is solid rock"}
    y = -128 * gcell(grid, gx, gz, 6)
    d = psxdbg.Dbg()
    try:
        d.halt()
        for a in POS_COPIES:
            d.write(a, struct.pack("<iii", x, y, z))
        d._send("c")
    finally:
        d.close()
    return {"ok": True, "cell": [gx, gz], "y": y}


def terrain_png(lv):
    path = f"out/maps/level{lv:02d}_detail.png"
    if not os.path.exists(path):
        global _grids
        if _grids is None:
            _grids = dict(levels())
        w, h, px = level_map.render(_grids[lv], SCALE, lv=lv)
        os.makedirs("out/maps", exist_ok=True)
        tim.write_png(path, w, h, px)
    return open(path, "rb").read()


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>King's Field II - live map</title>
<style>
:root{--bg:#15141a;--panel:#1e1c24;--ink:#e7dfcd;--muted:#968b7b;--line:#343040;--accent:#dc8b4c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
.wrap{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:14px;padding:14px;height:100vh}
@media(max-width:900px){.wrap{grid-template-columns:1fr;height:auto}}
.mapwrap{overflow:auto;border:1px solid var(--line);border-radius:4px;background:#12111a}
.map{position:relative;width:__MW__px;height:__MH__px}
.map img{display:block;width:100%;height:100%;image-rendering:pixelated}
.pin{position:absolute;width:11px;height:11px;margin:-5.5px 0 0 -5.5px;border-radius:50%;
  border:1.5px solid rgba(0,0,0,.65);cursor:pointer}
.pin.big{width:15px;height:15px;margin:-7.5px 0 0 -7.5px;border-width:2px}
.pin.sel{box-shadow:0 0 0 3px #fff,0 0 0 6px rgba(0,0,0,.7);z-index:6}
.pin.sc{background:none!important;border:none;width:17px;height:17px;margin:-8.5px 0 0 -8.5px;
  font:15px/17px system-ui;text-align:center;text-shadow:0 0 3px #000,0 0 4px #000;z-index:5}
.pin.chg{outline:2px solid #ffd166;outline-offset:2px;border-radius:50%}
.tp{background:#8a4a1a;border-color:#dc8b4c}
.seam{position:absolute;width:15px;height:15px;margin:-7.5px 0 0 -7.5px;z-index:7;
  background:#63b3ed;border:2px solid #0b1a2a;transform:rotate(45deg);cursor:help}
.pin[hidden]{display:none}
.you{position:absolute;width:19px;height:19px;margin:-9.5px 0 0 -9.5px;border-radius:50%;
  background:#fff;border:3px solid #dc8b4c;box-shadow:0 0 12px rgba(255,255,255,.8);
  z-index:8;transition:left .18s linear,top .18s linear}
.trail{position:absolute;width:5px;height:5px;margin:-2.5px 0 0 -2.5px;border-radius:50%;
  background:rgba(220,139,76,.5);z-index:4}
aside{display:flex;flex-direction:column;gap:10px;min-height:0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:10px 12px}
h1{font-size:15px;margin:0 0 4px}
.big{font:600 26px/1.1 ui-monospace,monospace;font-variant-numeric:tabular-nums}
.muted{color:var(--muted);font-size:12.5px}
.near{list-style:none;margin:0;padding:0;overflow:auto;flex:1;min-height:120px}
.near li{display:flex;gap:8px;align-items:baseline;padding:5px 6px;border-bottom:1px solid var(--line);cursor:pointer}
.near li:hover{background:#26232e}
.dot{width:9px;height:9px;border-radius:50%;flex:none}
.d{margin-left:auto;font:12px ui-monospace,monospace;color:var(--muted)}
.err{color:#e07a6a}
button{font:inherit;font-size:12.5px;background:var(--panel);color:var(--ink);
  border:1px solid var(--line);border-radius:999px;padding:3px 10px;cursor:pointer}
</style></head><body>
<div class="wrap">
  <div class="mapwrap" id="mapwrap"><div class="map" id="map"><img id="terrain" alt=""></div></div>
  <aside>
    <div class="card">
      <h1>Where you are</h1>
      <div class="big" id="cell">--</div>
      <div class="muted" id="lvl">waiting for the emulator...</div>
      <div class="muted" id="pos"></div>
    </div>
    <div class="card">
      <h1>You</h1>
      <div class="big" id="hp">--</div>
      <div class="muted" id="stats"></div>
    </div>
    <div class="card">
      <h1>Map</h1>
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
        <select id="pick" style="flex:1;min-width:0"><option value="">auto-detect</option></select>
        <button id="lock" title="stop the map changing on its own">Lock</button>
      </div>
      <div style="display:flex;gap:6px;align-items:center">
        <input id="rename" list="areas" placeholder="name this map" style="flex:1;min-width:0">
        <button id="save">Save</button>
      </div>
      <datalist id="areas"></datalist>
      <div class="muted" id="saved"></div>
    </div>
    <div class="card" style="display:flex;gap:6px;flex-wrap:wrap">
      <button id="follow">Follow: on</button>
      <button id="clear">Clear trail</button>
    </div>
    <div class="card" id="selcard" hidden>
      <h1>Selected <button id="unsel" style="float:right">clear</button></h1>
      <div id="selinfo"></div>
    </div>
    <div class="card" style="display:flex;flex-direction:column;min-height:0;flex:1">
      <h1>Nearest objects <span class="muted" id="hidnote"></span></h1>
      <ul class="near" id="near"></ul>
    </div>
    <div class="card" style="display:flex;flex-direction:column;min-height:0;flex:1">
      <h1>Types on this map <span class="muted">click to hide</span></h1>
      <ul class="near" id="types"></ul>
    </div>
  </aside>
</div>
<script>
const SCALE=__SCALE__, CELL=__CELL__, H=__H__, COL=__COL__;
const map=document.getElementById('map'), img=document.getElementById('terrain');
const near=document.getElementById('near');
let gen=-1, objs=[], pins=[], follow=true, sel=-1, last=null, shownLv=null;
let locked=false, lvNames={}, ignored=new Set(), last3=null;
let hidden=new Set(), changed=new Set();
const keyOf=o=>o.id+'@'+Math.floor(o.x/CELL)+','+Math.floor(o.z/CELL);
const you=document.createElement('div'); you.className='you'; map.appendChild(you);
const pick=document.getElementById('pick'), lockBtn=document.getElementById('lock');
const rename=document.getElementById('rename'), saved=document.getElementById('saved');

function label(i){ return 'level '+String(i).padStart(2,'0')+(lvNames[i]?' - '+lvNames[i]:''); }
function fillPicker(){
  const keep=pick.value;
  pick.innerHTML='<option value="">auto-detect</option>';
  for(let i=0;i<28;i++){
    const o=document.createElement('option'); o.value=i; o.textContent=label(i);
    pick.appendChild(o);
  }
  pick.value=keep;
}
async function loadNames(){
  const d=await (await fetch('/names')).json();
  lvNames=d.levels||{};
  document.getElementById('areas').innerHTML=(d.areas||[])
    .map(a=>'<option value="'+a.replace(/"/g,'&quot;')+'">').join('');
  fillPicker();
}
loadNames();
async function loadIgnore(){
  ignored=new Set(await (await fetch('/ignore')).json());
}
async function toggleIgnore(id){
  const on=!ignored.has(id);
  const r=await (await fetch('/ignore',{method:'POST',
    body:JSON.stringify({id:id,on:on})})).json();
  if(r.ok){ ignored=new Set(r.ignored); drawObjs(); renderTypes(); }
}
function renderTypes(){
  const c={};
  objs.forEach(o=>{ c[o.id]=c[o.id]||{n:0,name:o.name,cat:o.cat}; c[o.id].n++; });
  const rows=Object.entries(c).sort((a,b)=>b[1].n-a[1].n);
  document.getElementById('types').innerHTML=rows.map(([id,v])=>
    '<li data-id="'+id+'" style="opacity:'+(ignored.has(+id)?.4:1)+'">'+
    '<span class="dot" style="background:'+(COL[v.cat]||'#888')+'"></span>'+
    '<span>'+(v.name||('id '+id))+'</span>'+
    '<span class="d">'+(ignored.has(+id)?'hidden':v.n)+'</span></li>').join('');
  document.querySelectorAll('#types li').forEach(li=>
    li.onclick=()=>toggleIgnore(+li.dataset.id));
  const hid=objs.filter(o=>ignored.has(o.id)).length;
  document.getElementById('hidnote').textContent=hid?'('+hid+' hidden)':'';
}
loadIgnore();
async function loadHidden(){ hidden=new Set(await (await fetch('/hidden')).json()); }
async function drawSeams(){
  const t=await (await fetch('/transitions')).json();
  map.querySelectorAll('.seam').forEach(e=>e.remove());
  const lv = pick.value!==''? +pick.value : shownLv;
  t.filter(e=>e.from===lv||e.to===lv).forEach(e=>{
    const s=document.createElement('div'); s.className='seam';
    s.style.left=(e.x/CELL*SCALE).toFixed(1)+'px';
    s.style.top=((H-e.z/CELL)*SCALE).toFixed(1)+'px';
    s.title='level '+e.from+' \u2192 '+e.to+' here (cell '+e.cell.join(',')+')';
    map.appendChild(s);
  });
}
async function toggleHidden(i){
  const o=objs[i], k=keyOf(o), on=!hidden.has(k);
  const r=await (await fetch('/hidden',{method:'POST',
    body:JSON.stringify({key:k,on:on})})).json();
  if(r.ok){ hidden=new Set(r.hidden); drawObjs(); updateNear(last3?last3[0]:0,last3?last3[2]:0); }
}
async function gotoObj(i){
  const o=objs[i];
  const r=await (await fetch('/goto',{method:'POST',
    body:JSON.stringify({x:o.x,z:o.z})})).json();
  document.getElementById('selinfo').insertAdjacentHTML('beforeend',
    r.ok?'<div class="muted">teleported to '+r.cell.join(',')+'</div>'
        :'<div class="err">'+r.error+'</div>');
}
loadHidden();

pick.onchange=()=>{ shownLv=null; locked=pick.value!==''; lockBtn.textContent=locked?'Unlock':'Lock'; };
lockBtn.onclick=()=>{
  if(locked){ locked=false; pick.value=''; lockBtn.textContent='Lock'; }
  else if(shownLv!==null){ locked=true; pick.value=String(shownLv); lockBtn.textContent='Unlock'; }
  shownLv=null;
};
document.getElementById('save').onclick=async()=>{
  const lv = pick.value!==''? +pick.value : shownLv;
  if(lv===null||lv===undefined) return;
  const r=await (await fetch('/names',{method:'POST',
    body:JSON.stringify({level:lv,name:rename.value})})).json();
  if(r.ok){ lvNames=r.levels; fillPicker(); saved.textContent='saved for level '+lv; }
  else saved.innerHTML='<span class="err">'+r.error+'</span>';
};
document.getElementById('follow').onclick=e=>{follow=!follow;e.target.textContent='Follow: '+(follow?'on':'off')};
document.getElementById('clear').onclick=()=>map.querySelectorAll('.trail').forEach(t=>t.remove());
const X=o=>o.x/CELL*SCALE, Y=o=>(H-o.z/CELL)*SCALE;
function drawObjs(){
  map.querySelectorAll('.pin').forEach(p=>p.remove());
  pins=objs.map((o,i)=>{
    const p=document.createElement('div');
    p.className='pin'+(o.sure?' big':''); p.dataset.i=i;
    p.hidden=ignored.has(o.id);
    p.style.left=X(o).toFixed(1)+'px'; p.style.top=Y(o).toFixed(1)+'px';
    if(o.gold!=null){ p.classList.add('sc'); p.textContent='\u2605';
      p.style.color=COL[o.cat]||'#888'; }
    else p.style.background=COL[o.cat]||'#888';
    if(changed.has(i)) p.classList.add('chg');
    if(hidden.has(keyOf(o))) p.hidden=true;
    p.title='id '+o.id+(o.name?' - '+o.name:'')+(o.gold!=null?'  ['+o.gold+' gold]':'');
    p.onclick=()=>select(i);
    map.appendChild(p); return p;
  });
}
function select(i){
  pins.forEach(p=>p.classList.remove('sel'));
  sel=i;
  const o=objs[i];
  if(!o){ document.getElementById('selcard').hidden=true; return; }
  if(pins[i]){ pins[i].classList.add('sel');
    pins[i].scrollIntoView({block:'center',inline:'center',behavior:'smooth'}); }
  document.getElementById('selcard').hidden=false;
  showSel();
}
function showSel(){
  const o=objs[sel]; if(!o) return;
  const d=last3?Math.hypot(o.x-last3[0],o.z-last3[2])/CELL:null;
  document.getElementById('selinfo').innerHTML=
    '<div class="big" style="font-size:17px">'+(o.name||'unidentified')+'</div>'+
    '<div class="muted">type id '+o.id+' &middot; cell '+Math.floor(o.x/CELL)+','+
      Math.floor(o.z/CELL)+' &middot; height '+o.y+'</div>'+
    (o.gold!=null?'<div class="muted">&#9733; picks up as '+o.gold+' gold</div>':'')+
    (d!=null?'<div class="muted">'+d.toFixed(1)+' cells from you</div>':'')+
    (changed.has(sel)?'<div style="color:#ffd166">record changed since you arrived</div>':'')+
    '<div style="display:flex;gap:6px;margin-top:6px">'+
      '<button class="tp" onclick="gotoObj('+sel+')">Take me there</button>'+
      '<button onclick="toggleHidden('+sel+')">'+
        (hidden.has(keyOf(o))?'Unhide this one':'Hide just this one')+'</button>'+
    '</div>';
}
document.getElementById('unsel').onclick=()=>{
  pins.forEach(p=>p.classList.remove('sel'));
  sel=-1; document.getElementById('selcard').hidden=true;
};
function updateNear(px,pz){
  const list=objs.map((o,i)=>({o,i,d:Math.hypot(o.x-px,o.z-pz)}))
    .filter(e=>!ignored.has(e.o.id)&&!hidden.has(keyOf(e.o)))
    .sort((a,b)=>a.d-b.d).slice(0,12);
  near.innerHTML=list.map(({o,i,d})=>
    '<li data-i="'+i+'"><span class="dot" style="background:'+(COL[o.cat]||'#888')+'"></span>'+
    '<span>'+(o.name||('id '+o.id))+(o.gold!=null?' \u2605':'')+
    (changed.has(i)?' <b style="color:#ffd166">changed</b>':'')+
    '</span><span class="d">'+Math.round(d/CELL*10)/10+' cells</span></li>').join('');
  near.querySelectorAll('li').forEach(li=>li.onclick=()=>select(+li.dataset.i));
}
async function tick(){
  try{
    const r=await fetch('/live'); const s=await r.json();
    if(!s.ok){document.getElementById('lvl').innerHTML='<span class="err">'+s.error+'</span>';return;}
    if(s.gen!==gen){
      gen=s.gen;
      objs=await (await fetch('/objs')).json(); drawObjs(); renderTypes(); drawSeams();
    }
    const want = pick.value===''? s.level : +pick.value;
    if(want!==shownLv){ shownLv=want; img.src='/terrain/'+want+'.png'; drawSeams(); }
    const px=s.player[0], pz=s.player[2];
    const x=px/CELL*SCALE, y=(H-pz/CELL)*SCALE;
    if(last&&Math.hypot(x-last[0],y-last[1])>6){
      const t=document.createElement('div'); t.className='trail';
      t.style.left=last[0].toFixed(1)+'px'; t.style.top=last[1].toFixed(1)+'px';
      map.appendChild(t);
    }
    last=[x,y];
    you.style.left=x.toFixed(1)+'px'; you.style.top=y.toFixed(1)+'px';
    document.getElementById('cell').textContent=s.cell[0]+', '+s.cell[1];
    document.getElementById('lvl').innerHTML=
      (locked?'<b>locked to '+label(shownLv)+'</b><br>detected: ':'')+
      label(s.level)+' - '+s.count+' objects'+
      (s.guessed!=null&&s.guessed!==s.levelId
        ? ' <span class="err">(byte says '+s.levelId+', terrain says '+s.guessed+')</span>'
        : ' - from RAM, terrain agrees')+
      '';
    if(!rename.matches(':focus')) rename.value=lvNames[locked?shownLv:s.level]||'';
    document.getElementById('pos').textContent='x '+px+'  y '+s.player[1]+'  z '+pz;
    if(s.stats){ const t=s.stats;
      document.getElementById('hp').textContent=
        'HP '+t.hp+'/'+t.hp_max+'   MP '+t.mp+'/'+t.mp_max;
      document.getElementById('stats').textContent=
        'level '+t.level+' - '+t.gold+' gold - exp '+t.exp+'/'+t.exp_next; }
    if(s.changed){ const before=changed.size; changed=new Set(s.changed);
      if(changed.size!==before) drawObjs(); }
    last3=[px,s.player[1],pz];
    updateNear(px,pz);
    if(sel>=0) showSel();
    if(follow) you.scrollIntoView({block:'center',inline:'center'});
  }catch(e){ document.getElementById('lvl').innerHTML='<span class="err">emulator not reachable</span>'; }
}
setInterval(tick,600); tick();
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path.startswith("/live"):
                self._send(json.dumps(poll()).encode())
            elif self.path.startswith("/objs"):
                with _lock:
                    self._send(json.dumps(_state["objs"]).encode())
            elif self.path.startswith("/ignore"):
                self._send(json.dumps(load_json(IGNORE_FILE, [])).encode())
            elif self.path.startswith("/hidden"):
                self._send(json.dumps(load_json(HIDE_FILE, [])).encode())
            elif self.path.startswith("/transitions"):
                self._send(json.dumps(load_json(TRANS_FILE, [])).encode())
            elif self.path.startswith("/names"):
                self._send(json.dumps({
                    "levels": load_json(NAMES_FILE, {}),
                    "areas": load_json(AREAS_FILE, []),
                }).encode())
            elif self.path.startswith("/terrain/"):
                lv = int(self.path.split("/")[2].split(".")[0])
                self._send(terrain_png(lv), "image/png")
            else:
                page = (PAGE.replace("__MW__", str(W * SCALE))
                            .replace("__MH__", str(H * SCALE))
                            .replace("__SCALE__", str(SCALE))
                            .replace("__CELL__", str(CELL))
                            .replace("__H__", str(H))
                            .replace("__COL__", json.dumps({k: c for k, _, c in CATS})))
                self._send(page.encode(), "text/html; charset=utf-8")
        except Exception as e:
            self._send(json.dumps({"ok": False, "error": str(e)}).encode(), code=200)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path.startswith("/ignore"):
                d = save_ignore(int(body["id"]), bool(body.get("on")))
                self._send(json.dumps({"ok": True, "ignored": d}).encode())
                return
            if self.path.startswith("/hidden"):
                d = save_hidden(str(body["key"]), bool(body.get("on")))
                self._send(json.dumps({"ok": True, "hidden": d}).encode())
                return
            if self.path.startswith("/goto"):
                self._send(json.dumps(teleport(int(body["x"]), int(body["z"]))).encode())
                return
            d = save_level_name(int(body["level"]), body.get("name", "").strip())
            self._send(json.dumps({"ok": True, "levels": d}).encode())
        except Exception as e:
            self._send(json.dumps({"ok": False, "error": str(e)}).encode())

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


PIDFILE = "out/livemap.pid"


def stop():
    """Stop a running server. The pid file holds this process's own pid, not
    the pid of whatever shell wrapper started it."""
    try:
        pid = int(open(PIDFILE).read().strip())
    except (OSError, ValueError):
        print("no pid file; nothing to stop")
        return
    try:
        os.kill(pid, 15)
        print(f"stopped {pid}")
    except ProcessLookupError:
        print(f"pid {pid} is not running")
    finally:
        try:
            os.remove(PIDFILE)
        except OSError:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        stop()
        sys.exit(0)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    os.makedirs("out", exist_ok=True)
    with open(PIDFILE, "w") as fh:
        fh.write(str(os.getpid()))
    print(f"live map on http://localhost:{port}   (emulator API: {EMU})")
    print(f"stop it with: python3 tools/livemap.py stop")
    try:
        Server(("127.0.0.1", port), Handler).serve_forever()
    finally:
        try:
            os.remove(PIDFILE)
        except OSError:
            pass

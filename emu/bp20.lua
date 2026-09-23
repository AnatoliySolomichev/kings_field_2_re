-- The interactive systems, which nothing in this repository has ever recorded.
--
--   ./emu/run.sh debug bp20.lua
--
-- Then **play normally for a minute or two**: open a door, take something out
-- of a chest, talk to somebody, use an item, get hit. Each of those goes
-- through one of the routines below and none of them has a recording, which is
-- why five subsystems are read but not checked.
--
-- What it logs, and why each one:
--
--   OBJ   every arm of `object_interpreter` (0x80047010) that is not the
--         shared tail, with the object's slot, its opcode and its cell. 236
--         opcodes go through 44 arms and OBJECTS.md says what each one
--         touches; this says which ones actually run while somebody plays,
--         and on what. The tail is skipped or this would be 396 lines a frame.
--
--   HURT  `0x8002ab18` on the way in and on the way out, with the player's HP
--         either side and the four arguments. The damage roll is 383
--         instructions of `rand` and a seven-arm switch and nobody has seen it
--         run.
--
--   ITEM  `use_item` (0x8005cbe0) with the selected item, and `give_item`,
--         `take_item` and `has_item` with the id -- so a session says which
--         items the game actually asks about.
--
--   TALK  `script_interpreter` (0x8005c308) per call, with the entity, and the
--         opcode it is about to run. `emu/bp21.lua` is the script that does
--         this properly, and what it recorded showed the corpus both copies
--         were decoding was not scripts at all.
--
--   LVL   `level_load`'s state each time it changes, so the seven-state load
--         can be watched happening.
--
-- Anything reached through a table is logged by *instruction*, not by watching
-- memory: a write watchpoint's callback runs before the store lands, so
-- reading the memory there gives the value the byte had. bp19 made that
-- mistake and reported two `sb $zero` instructions as setting 1 and 2.
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint", and the silence afterwards would mean nothing. There is a
-- heartbeat below for the same reason -- an empty log has to be tellable from
-- breakpoints that never armed.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp20.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 40000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp20 (the interactive systems) armed; debug = '
    .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function u8(a) return mem[a % 0x200000] end
local function u16(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256
end
local function u32(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256 + mem[b + 2] * 65536 + mem[b + 3] * 16777216
end
local function s32(a)
    local v = u32(a)
    if v >= 0x80000000 then v = v - 0x100000000 end
    return v
end

local GPR = {'zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'}

local function cpu()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, 0 end
    local g = r.GPR
    if g and g.n then g = g.n end
    return g, tonumber(r.pc) or 0
end

local function reg(g, n)
    if n == 0 then return 0 end
    local v = g[GPR[n + 1]]
    if v == nil and n == 30 then v = g['s8'] end
    return tonumber(v) or 0
end

-- the addresses this watches
local OBJECT_TABLE  = 0x80191A5C
local CURRENT_OBJ   = 0x80198394   -- object_interpreter publishes the record
local PLAYER_HP     = 0x801B24FC   -- player.py: BASE + 0x1c
local PLAYER_POS    = 0x801B25F0
local PLAYER_Z      = 0x801B25F8
local LEVEL_BYTE    = 0x8018FAD9
local LOAD_STATE    = 0x8018FAD6

local function where()
    return string.format('lv=%d cell=(%d,%d)', u8(LEVEL_BYTE),
        math.floor(s32(PLAYER_POS) / 2048), math.floor(s32(PLAYER_Z) / 2048))
end

bp20 = {}
local counts = {}
local function bump(k) counts[k] = (counts[k] or 0) + 1 end

-- The `false` below is this helper's own answer to "did it arm", not a
-- breakpoint callback's return. A callback here never returns anything.
local function arm(addr, tag, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, tag, fn)
    if not ok then
        log(string.format('arm %08x %s -> FAILED', addr, tag))
        return false
    end
    bp20[#bp20 + 1] = bp
    return true
end

-- ---- the object interpreter's arms -------------------------------------
--
-- The 43 arms that are not the shared tail, out of the 236-entry table at
-- 0x8001209c as tools/objops.py resolves it -- checked against that tool, not
-- copied by hand: `python3 tools/objops.py` prints the same list. The tail (0x8004b4b4) is left
-- alone: 191 opcodes reach it and most of the 396 slots take it every frame.
local ARMS = {
    0x80047cbc, 0x8004814c, 0x800475f8, 0x800470c4, 0x80047290, 0x80047444,
    0x80048790, 0x80048960, 0x80048a8c, 0x80048c34, 0x8004b1d4, 0x8004ae34,
    0x8004b204, 0x8004847c, 0x8004aeb8, 0x8004b000, 0x80047858, 0x8004b154,
    0x8004b168, 0x80049188, 0x80049888, 0x80048c7c, 0x80048ecc, 0x80049b40,
    0x80049fcc, 0x80049574, 0x8004ab40, 0x8004ac90, 0x800496b8, 0x800490b8,
    0x8004b228, 0x8004b300, 0x8004b388, 0x8004a7f8, 0x8004a868, 0x8004a954,
    0x8004a9a8, 0x8004b4d0, 0x8004aa60, 0x8004a120, 0x8004a66c, 0x8004a5b8,
    0x8004a2e0,
}

-- An arm can run for every object of its class every frame, so each one is
-- logged the first eight times and then only counted. Without that a door you
-- are standing next to fills the file on its own.
local seen_arm = {}
for _, a in ipairs(ARMS) do
    local addr = a
    arm(addr, 'objarm', function()
        bump('obj')
        seen_arm[addr] = (seen_arm[addr] or 0) + 1
        if seen_arm[addr] > 8 then return end
        local rec = u32(CURRENT_OBJ)
        if rec < 0x80000000 then return end
        local slot = math.floor((rec - OBJECT_TABLE) / 0x44)
        log(string.format('OBJ arm=%08x op=%02x slot=%d type=%d %s n=%d',
            addr, u8(rec + 4), slot, u16(rec + 6), where(), seen_arm[addr]))
    end)
end

-- ---- the damage roll ----------------------------------------------------
arm(0x8002ab18, 'hurt', function()
    bump('hurt')
    local g = cpu()
    if g == nil then return end
    log(string.format('HURT in  a0=%d a1=%d a2=%d a3=%d hp=%d %s',
        reg(g, 4), reg(g, 5), reg(g, 6), reg(g, 7), u16(PLAYER_HP), where()))
end)
arm(0x8002b110, 'hurtout', function()
    bump('hurtout')
    log(string.format('HURT out hp=%d', u16(PLAYER_HP)))
end)

-- ---- items --------------------------------------------------------------
arm(0x8005cbe0, 'use', function()
    bump('use')
    local g = cpu()
    if g == nil then return end
    log(string.format('ITEM use a0=%d %s', reg(g, 4), where()))
end)
for addr, name in pairs({[0x8005d7bc] = 'has', [0x8005d7f8] = 'take',
                         [0x8005d898] = 'give'}) do
    local a, n = addr, name
    arm(a, 'inv', function()
        bump('inv')
        local g = cpu()
        if g == nil then return end
        log(string.format('ITEM %s id=%d', n, reg(g, 4)))
    end)
end

-- ---- the script interpreter ---------------------------------------------
--
-- 0x8005c308 is the call; the fetch is at .L4, which is where the next opcode
-- is decided. Logging the call alone says who is talking; logging the fetch
-- says what the script does, and that is the thing godot/escript.gd would be
-- held against.
arm(0x8005c308, 'talk', function()
    bump('talk')
    local g = cpu()
    if g == nil then return end
    local rec = reg(g, 4)
    log(string.format('TALK enter rec=%08x entity=%d %s', rec,
        rec >= 0x80000000 and u8(rec + 2) or -1, where()))
end)

-- ---- the level load ------------------------------------------------------
local last_state = -1
arm(0x80018358, 'load', function()
    bump('load')
    local st = u16(LOAD_STATE)
    if st == last_state then return end
    last_state = st
    log(string.format('LVL state=%04x pending=%d current=%d', st,
        u8(0x8018FAE4), u8(LEVEL_BYTE)))
end)

-- ---- the heartbeat -------------------------------------------------------
--
-- A control, because silence proves nothing. If this prints and the others do
-- not, the breakpoints are armed and the player has not done the thing yet; if
-- this does not print either, nothing is armed.
local frame = 0
arm(0x800422b8, 'frame', function()
    frame = frame + 1
    if frame % 600 ~= 0 then return end
    local parts = {}
    for k, v in pairs(counts) do parts[#parts + 1] = k .. '=' .. v end
    table.sort(parts)
    log(string.format('-- frame %d  %s  %s', frame, where(),
        table.concat(parts, ' ')))
end)

log(string.format('=== %d breakpoints armed (%d object arms) ===',
    #bp20, #ARMS))

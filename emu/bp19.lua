-- Every change of state of every creature, with the value that is written.
--
--   ./emu/run.sh debug bp19.lua
--
-- Then kill some monsters, walk away, come back, and let them return.
--
-- The byte at actor+9 is a small state machine: render_walk draws a creature
-- only while it is 1, 0x8004b770 puts 3 there, and four sites clear it. The
-- previous version of this script watched the *memory* and printed the value it
-- found there -- which is the value **before** the store, because a write
-- watchpoint's callback runs before the store lands. It reported "sets 1" for
-- two instructions that write zero, and the disassembly caught it.
--
-- So this one does not watch the memory at all. It puts an execution
-- breakpoint on **each of the 39 instructions** in the actor cluster that store
-- a byte at +9 -- listed by scanning GAME.EXE for `sb rt, 9(rs)` -- and when one
-- is about to run it decodes that instruction, reads the new value out of the
-- source register and the old one out of memory, and logs the pair. That is a
-- transition, old -> new, with the routine that made it, for every actor on
-- the level rather than the three by the house.
--
-- It also catches the die. Inside 0x8004c1f0 the code does
--     jal rand; sra $v0, $v0, 4; slt $v0, $s1, $v0
-- so at 0x8004c304 $v0 is the raw roll and $s1 the threshold it is held to.
--
-- And it writes res://live.txt, so the Godot build's C key has something to
-- compare against.
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint", and silence afterwards would mean nothing.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp19.log'
local LIVE = '/home/solo/my/projects/kings_field_2_english/out/godot/live.txt'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 20000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp19 (transitions) armed; debug = '
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
local function s16(v) if v >= 0x8000 then return v - 0x10000 end return v end
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

local ACTORS, STRIDE, SLOTS = 0x80185DA8, 0x88, 200
local frame = 0
-- A control, because silence proves nothing: how often the store breakpoints
-- fire at all, how many of those were actor records, how many changed the
-- byte. A heartbeat below prints them, so an empty log can be told apart from
-- breakpoints that never fired.
local fired, on_actor, transitions, rolls = 0, 0, 0, 0

local function where()
    return string.format('lv=%d player=(%d,%d)', u8(0x8018FAD9),
        math.floor(s32(0x801B25F0) / 2048), math.floor(s32(0x801B25F8) / 2048))
end

bp19 = {}
local function arm(addr, tag, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, tag, fn)
    if not ok then log(string.format('arm %08x %s -> FAILED', addr, tag)) end
    if ok then bp19[#bp19 + 1] = bp end
    return ok
end

-- the 39 stores, from a scan of GAME.EXE for `sb rt, 9(rs)` in the actor cluster
local SITES = {
    0x8004b6b4, 0x8004b780, 0x8004c42c, 0x8004c488, 0x8004c4b8, 0x8004c4f4,
    0x8004fd90, 0x800508a0, 0x80052ba8, 0x80052bc0, 0x80052bc4, 0x80052c54,
    0x80053bcc, 0x80053c08, 0x80053c34, 0x80053dd8, 0x80053ed0, 0x80053fb4,
    0x80054050, 0x800542b4, 0x80054814, 0x800548d0, 0x80054bb4, 0x80054c88,
    0x80054d00, 0x80054d80, 0x80054de4, 0x80054e60, 0x80054f68, 0x80055078,
    0x80055180, 0x800551f4, 0x80055350, 0x80055438, 0x800554e4, 0x8005553c,
    0x8005562c, 0x80055680, 0x800557a8,
}

local armed = 0
for _, site in ipairs(SITES) do
    local ok = arm(site, 'state', function()
        local g, pc = cpu()
        if g == nil then return end
        fired = fired + 1
        -- Decode the instruction this breakpoint was armed on, not whatever
        -- pc reports: if the emulator gives the next address at an execution
        -- breakpoint, decoding pc would reject every hit and log nothing.
        local w = u32(site)
        if math.floor(w / 0x4000000) ~= 0x28 or w % 0x10000 ~= 9 then return end
        local rs = math.floor(w / 0x200000) % 32
        local rt = math.floor(w / 0x10000) % 32
        local base = reg(g, rs)
        local slot = (base - ACTORS) / STRIDE
        if slot < 0 or slot >= SLOTS or slot ~= math.floor(slot) then return end
        on_actor = on_actor + 1
        local old = u8(base + 9)
        local new = reg(g, rt) % 256
        if old == new then return end
        transitions = transitions + 1
        log(string.format('STATE f=%d actor %3d mesh=%3d kind=%3d  %d -> %d  '
            .. 'pc=%08x ra=%08x  at=(%d,%d)  %s',
            frame, slot, u8(base + 1), u8(base + 2), old, new, site,
            reg(g, 31), math.floor(s32(base + 0x2C) / 2048),
            math.floor(s32(base + 0x34) / 2048), where()))
    end)
    if ok then armed = armed + 1 end
end
log(string.format('armed %d of %d state stores', armed, #SITES))

-- the roll inside the activator: $v0 is rand(), $s1 the threshold for >> 4
arm(0x8004C304, 'roll', function()
    local g, _pc = cpu()
    if g == nil then return end
    local raw = reg(g, 2)
    rolls = rolls + 1
    log(string.format('ROLL f=%d rand=%d  (rand>>4)=%d  threshold=%d  %s',
        frame, raw, math.floor(raw / 16), reg(g, 17), where()))
end)

-- the port's feed, from the head of the movement chain, once per game frame
arm(0x8002FE1C, 'live', function()
    frame = frame + 1
    if frame % 600 == 0 then
        log(string.format('HEART f=%d  store breakpoints fired %d, on actors %d, '
            .. 'transitions %d, rolls %d  %s', frame, fired, on_actor,
            transitions, rolls, where()))
    end
    local f = io.open(LIVE .. '.tmp', 'w')
    if f == nil then return end
    f:write(string.format('%d %d %d %d %d %d %d %d %d %d %d %d\n',
        frame, s32(0x801B25F0), s32(0x801B25F4), s32(0x801B25F8),
        u16(0x801B2612), u8(0x801B25E8), s16(u16(0x801B2656)),
        s16(u16(0x801B2648)), s16(u16(0x801B2646)), u16(0x801B265C),
        u8(0x8018FAD9), s16(u16(0x801B2610))))
    f:close()
    os.rename(LIVE .. '.tmp', LIVE)
end)

log('=== bp19 watching: kill, walk away, come back ===')

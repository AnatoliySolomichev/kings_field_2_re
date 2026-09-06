-- The opening scene: who hands over the sword, and what the man at the table says.
--
--   ./emu/run.sh debug bp17.lua
--   ...or from the emulator's Lua console:
--   dofile('/home/solo/my/projects/kings_field_2_english/emu/bp17.lua')
--
-- Then start a new game and play until the sword is yours.
--
-- What is already known without the emulator, from the disc: the house is
-- around level 0 cell (62,3) -- the painting is object slot 191, type 300,
-- hanging 2000 units up the wall -- and the sword floating in front of you is
-- slot 62, type 0, model MO.T[128], 924 units up in cell (62,4). Three actors
-- stand there, meshes 32, 33 and 34, and two of them share the cell, which is
-- why the port draws the same man twice.
--
-- What is not known, and what this is for:
--
--   * whether the handover goes through `give_item` at all. The port shows the
--     sword as a placed object, so it may; but the scene does not look like an
--     ordinary pickup, and if `give_item` never fires the log says so, which
--     is an answer too.
--   * which of the three actors the game actually turns on, and when. The
--     watchpoint on slot 0's `+9` reports every write to it with the caller.
--   * what the conversation says. `text_pager` walks a list of STALK.T entry
--     indices; log the indices and `tools/dump_text.py` reads them back.
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint", so the point fires once and the silence afterwards means
-- nothing. Return nothing.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp17.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 8000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp17 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function u8(a) return mem[a % 0x200000] end
local function u16(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256
end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

-- Where the player is, so every line says which room it happened in.
local function where()
    local x = u16(0x801b24e0 + 0)      -- the stat block's position, low halves
    local z = u16(0x801b24e0 + 8)
    return string.format('lv=%d cell~(%d,%d)', u8(0x8018fad8), x / 2048, z / 2048)
end

bp17 = {}
local seen = {}
local function arm(addr, tag, kind, width, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, kind, width, tag, fn)
    log(string.format('arm %08x %-14s %-5s -> %s', addr, tag, kind, tostring(ok)))
    if ok then bp17[#bp17 + 1] = bp end
end

-- The item routines. give_item takes the id in $a0; the caller in $ra is the
-- point of the whole exercise.
arm(0x8005d898, 'give_item', 'Exec', 4, function()
    local g = regs()
    if g == nil then return end
    log(string.format('GIVE  item=%d  ra=%08x  %s',
        tonumber(g.a0), tonumber(g.ra), where()))
end)

arm(0x8005d7f8, 'take_item', 'Exec', 4, function()
    local g = regs()
    if g == nil then return end
    log(string.format('TAKE  item=%d  ra=%08x  %s',
        tonumber(g.a0), tonumber(g.ra), where()))
end)

-- The conversation. text_pager walks a list of STALK.T indices and
-- text_fetch_page loads one; the indices are what `tools/dump_text.py` reads.
arm(0x8001d944, 'text_pager', 'Exec', 4, function()
    local g = regs()
    if g == nil then return end
    log(string.format('PAGER a0=%08x a1=%d  ra=%08x  %s',
        tonumber(g.a0), tonumber(g.a1), tonumber(g.ra), where()))
end)

arm(0x8001dbc4, 'text_fetch', 'Exec', 4, function()
    local g = regs()
    if g == nil then return end
    local key = 'p' .. tostring(g.a0)
    seen[key] = (seen[key] or 0) + 1
    if seen[key] <= 3 then
        log(string.format('PAGE  entry=%d  ra=%08x  %s',
            tonumber(g.a0), tonumber(g.ra), where()))
    end
end)

-- The object the player is acting on, and the entity script that answers.
arm(0x8005e2d0, 'object_interact', 'Exec', 4, function()
    local g = regs()
    if g == nil then return end
    log(string.format('USE   a0=%08x a1=%08x  ra=%08x  %s',
        tonumber(g.a0), tonumber(g.a1), tonumber(g.ra), where()))
end)

arm(0x8005c308, 'script', 'Exec', 4, function()
    local g = regs()
    if g == nil then return end
    local key = 's' .. tostring(g.a0)
    seen[key] = (seen[key] or 0) + 1
    if seen[key] <= 2 then
        log(string.format('SCRIPT a0=%08x  ra=%08x  %s',
            tonumber(g.a0), tonumber(g.ra), where()))
    end
end)

-- The three actors by the house are slots 0, 1 and 2 of the actor table, and
-- the renderer draws one only while its +9 is 1. A write watchpoint on each
-- says what turns the man at the table on and the man with the watering can
-- off -- which is the thing the port has no idea about.
for slot = 0, 2 do
    local a = 0x80185da8 + slot * 0x88 + 9
    arm(a, 'actor' .. slot .. '_on', 'Write', 1, function()
        local g = regs()
        if g == nil then return end
        log(string.format('ACTOR %d alive -> (write) pc=%08x  mesh=%d  %s',
            slot, tonumber(g.ra), u8(0x80185da8 + slot * 0x88 + 1), where()))
    end)
end

log('=== bp17 watching; start a new game and play until the sword is yours ===')

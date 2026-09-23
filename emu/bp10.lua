-- Who allocates the level's objects?
--
-- Load from the emulator's own Lua console, so the session survives:
--
--   dofile('bp10.lua')      -- run.sh starts the emulator in emu/
--
-- Every object slot in the game is taken through find_free_slot at 0x80046034,
-- which scans for a record whose type id is 0xff and evicts the oldest if none
-- is free. Five routines call it. If a level's objects are allocated one at a
-- time rather than written in bulk, then building a level is a loop of calls to
-- it -- and the return address names the loop.
--
-- So this keys its log on **ra**, not pc: pc is always the same address, while
-- ra is the answer. Three lines per distinct caller, so a fill loop of three
-- hundred allocations still leaves a readable log and every distinct caller
-- shows up exactly once.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp10.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 2000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp10 armed; debug switch = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function levelByte() return mem[0x8018fad9 % 0x200000] end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

local byCaller = {}
local total = 0

bp10 = {}
local ok, bp = pcall(PCSX.addBreakpoint, 0x80046034, 'Exec', 4, 'alloc',
    function(address)
        local g = regs()
        local ra = g and tonumber(g.ra) or 0
        total = total + 1
        byCaller[ra] = (byCaller[ra] or 0) + 1
        if byCaller[ra] > 3 then return false end
        log(string.format('alloc #%-4d ra=%08x  a0=%-4d a1=%-4d a2=%08x  level=%d',
            total, ra,
            (g and tonumber(g.a0) or 0) % 0x10000,
            (g and tonumber(g.a1) or 0) % 0x10000,
            g and tonumber(g.a2) or 0, levelByte()))
        return false
    end)
log('arm 80046034 Exec find_free_slot -> ' .. tostring(ok))
if ok then bp10[#bp10 + 1] = bp end

-- a second one on the level loader, so the log shows which allocations belong
-- to a level being built and which are ordinary play
local ok2, bp2 = pcall(PCSX.addBreakpoint, 0x80018358, 'Exec', 4, 'load',
    function(address)
        local g = regs()
        log(string.format('--- level_load, ra=%08x, level=%d, %d allocations so far ---',
            g and tonumber(g.ra) or 0, levelByte(), total))
        return false
    end)
log('arm 80018358 Exec level_load -> ' .. tostring(ok2))
if ok2 then bp10[#bp10 + 1] = bp2 end
log('=== bp10 watching; cross between levels ===')

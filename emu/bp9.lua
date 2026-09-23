-- Do write watchpoints work here at all?
--
-- Load from the emulator's own Lua console, so the session survives:
--
--   dofile('bp9.lua')      -- run.sh starts the emulator in emu/
--
-- bp8 watched the type id of the first three object slots across a save load
-- and a level change, and caught nothing but the BIOS clearing memory at boot.
-- Yet the ids are there afterwards, written at exactly those addresses. So
-- either the game does not reach them with ordinary CPU stores, or the
-- watchpoint does not see the ones it makes.
--
-- Silence from an instrument is only evidence once the instrument is known to
-- work, so this arms a control alongside the question:
--
--   CONTROL   player_pos, which changes every time the player moves. If this
--             never fires, write watchpoints are the problem, not the game.
--   OBJ-X     the X coordinate of object slot 0, a different field of the same
--             record bp8 watched.
--   LOAD      an Exec breakpoint on level_load, which is the kind that has
--             demonstrably worked all along.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp9.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 2000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp9 armed; debug switch = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function levelByte() return mem[0x8018fad9 % 0x200000] end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

local seen = {}
local function hit(tag)
    return function(address)
        local g, all = regs()
        local pc = all and tonumber(all.pc) or 0
        local key = tag .. ':' .. pc
        seen[key] = (seen[key] or 0) + 1
        if seen[key] > 2 then return false end
        log(string.format('%-8s pc=%08x ra=%08x  a0=%08x s0=%08x  level=%d',
            tag, pc, g and tonumber(g.ra) or 0,
            g and tonumber(g.a0) or 0, g and tonumber(g.s0) or 0, levelByte()))
        return false
    end
end

bp9 = {}
local function arm(addr, kind, width, tag)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, kind, width, tag, hit(tag))
    log(string.format('arm %08x %-5s x%-2d %-8s -> %s', addr, kind, width, tag, tostring(ok)))
    if ok then bp9[#bp9 + 1] = bp end
end

arm(0x801aec4c, 'Write', 4, 'CONTROL')     -- must fire as soon as the player moves
arm(0x80191a70, 'Write', 4, 'OBJ-X')       -- slot 0, world X
arm(0x80018358, 'Exec', 4, 'LOAD')         -- level_load, the kind that works
log('=== bp9 watching; walk a step and the control should fire at once ===')

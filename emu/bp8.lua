-- Who fills the object array?
--
--   ./emu/run.sh debug bp8.lua
--
-- Five rounds of reading the code have covered every path into the array
-- without finding the writer: level_load empties all 396 slots, reads FDAT,
-- scatters the grid and hands over to apply_level_state, which only overrides
-- slots that the player has changed. Something else fills them.
--
-- So stop reading and catch it. A write watchpoint on the type id of the first
-- few slots names the writer the moment a level is built, and loading a save is
-- enough to build one -- no level transition needed.
--
-- object_table is 0x80191a5c, records are 0x44 apart and the type id is at +6:
--
--   slot 0 -> 0x80191a62
--   slot 1 -> 0x80191aa6
--   slot 2 -> 0x80191aea
--
-- Watching three of them rather than one guards against the array being filled
-- in some order other than front to back.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp8.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 3000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp8 armed; debug switch = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function byteAt(a) return mem[a % 0x200000] end
local function levelByte() return byteAt(0x8018fad9) end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

-- one line per distinct pc, so a fill loop does not flood the log
local seen = {}
local function hit(tag)
    return function(address)
        local g, all = regs()
        local pc = all and tonumber(all.pc) or 0
        local key = tag .. ':' .. pc
        seen[key] = (seen[key] or 0) + 1
        if seen[key] > 3 then return false end
        log(string.format('%-7s pc=%08x ra=%08x  a0=%08x a1=%08x v0=%08x v1=%08x s0=%08x  level=%d',
            tag, pc,
            g and tonumber(g.ra) or 0, g and tonumber(g.a0) or 0,
            g and tonumber(g.a1) or 0, g and tonumber(g.v0) or 0,
            g and tonumber(g.v1) or 0, g and tonumber(g.s0) or 0,
            levelByte()))
        return false
    end
end

bp8 = {}
local function arm(addr, width, tag)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Write', width, tag, hit(tag))
    log(string.format('arm %08x Write x%-2d %-7s -> %s', addr, width, tag, tostring(ok)))
    if ok then bp8[#bp8 + 1] = bp end
end

arm(0x80191a62, 2, 'slot0')
arm(0x80191aa6, 2, 'slot1')
arm(0x80191aea, 2, 'slot2')
log('=== bp8 watching the object array ===')

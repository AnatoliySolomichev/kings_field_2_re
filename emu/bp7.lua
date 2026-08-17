-- Who reads the per-level 254-entry table?
--
--   dofile('/home/solo/my/projects/kings_field_2_english/emu/bp7.lua')
--
-- The table lives at a fixed address: comparing four RAM snapshots against
-- FDAT on the disc puts the offsets at 0x801d11ac and the data they point into
-- at 0x801d13a8, on every level, with only the contents swapping. So a read
-- watchpoint catches whoever walks it, and pc names the instruction. From the
-- instruction we get the function, and from the function its dispatch -- which
-- is the whole point, because one dispatch decodes the entire table format.
--
-- Two watchpoints rather than one: reading an offset and reading the record it
-- points at are different steps and may well be different code.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp7.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 4000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp7 armed; debug switch = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function levelByte() return mem[0x8018fad9 % 0x200000] end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

-- pc is what matters here, so keep one line per distinct pc and count repeats
local seen = {}
local function hit(tag)
    return function(address)
        local g, all = regs()
        local pc = all and tonumber(all.pc) or 0
        local key = tag .. pc
        seen[key] = (seen[key] or 0) + 1
        if seen[key] > 3 then return false end
        log(string.format('%-10s pc=%08x ra=%08x  a0=%08x a1=%08x v0=%08x v1=%08x  level=%d',
            tag, pc,
            g and tonumber(g.ra) or 0, g and tonumber(g.a0) or 0,
            g and tonumber(g.a1) or 0, g and tonumber(g.v0) or 0,
            g and tonumber(g.v1) or 0, levelByte()))
        return false
    end
end

bp7 = {}
local function arm(addr, width, tag)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Read', width, tag, hit(tag))
    log(string.format('arm %08x Read x%-4d %-10s -> %s', addr, width, tag, tostring(ok)))
    if ok then bp7[#bp7 + 1] = bp end
end

arm(0x801d11ac, 508, 'OFFSETS')
arm(0x801d13a8, 64, 'RECORDS')
log('=== bp7 watching ===')

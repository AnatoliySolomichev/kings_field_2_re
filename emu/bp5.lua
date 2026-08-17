-- Who actually sets the level?
--
-- Load this into a running emulator from the Lua console, without restarting:
--
--   dofile('/home/solo/my/projects/kings_field_2_english/emu/bp5.lua')
--
-- Two crossings under bp.lua showed that 0x80017c78 is not the answer: going
-- one way it fired once with every argument zero, going back it did not fire
-- at all, and the level byte changed both times. So this stops guessing which
-- routine is responsible and watches the byte itself. A write breakpoint on
-- 0x8018fad8 catches whoever stores there, and pc names the exact instruction.
--
-- The four routines that hold a store to the block, from the disassembly, are
-- 0x8001796c, 0x80018358, 0x80029188 and 0x8005f444; they are armed as well so
-- the order of events is visible even if the watchpoint proves unreliable.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp5.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 20000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp5 armed; debug switch = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function byteAt(addr) return mem[addr % 0x200000] end
local function levelBlock()
    local t = {}
    for i = 0, 4 do t[#t + 1] = string.format('%02x', byteAt(0x8018fad8 + i)) end
    return table.concat(t, ' ')
end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

local counts = {}
local function hit(tag)
    return function(address)
        counts[tag] = (counts[tag] or 0) + 1
        local n = counts[tag]
        if n > 12 and n % 50 ~= 0 then return false end
        local g, all = regs()
        local pc = all and tonumber(all.pc) or 0
        log(string.format('%-14s #%-3d pc=%08x ra=%08x a0=%02x a1=%02x a2=%02x a3=%02x  level=[%s]',
            tag, n, pc, g and tonumber(g.ra) or 0,
            (g and tonumber(g.a0) or 0) % 256, (g and tonumber(g.a1) or 0) % 256,
            (g and tonumber(g.a2) or 0) % 256, (g and tonumber(g.a3) or 0) % 256,
            levelBlock()))
        return false
    end
end

bp5 = {}
local ok, bp = pcall(PCSX.addBreakpoint, 0x8018fad8, 'Write', 5, 'level byte', hit('WRITE-level'))
log('watchpoint 8018fad8 Write x5 -> ' .. tostring(ok))
if ok then bp5[#bp5 + 1] = bp end

local FUNCS = {
    [0x8001796c] = 'fn_8001796c',
    [0x80029188] = 'fn_80029188',
    [0x8005f444] = 'fn_8005f444',
}
for a, name in pairs(FUNCS) do
    local o, b = pcall(PCSX.addBreakpoint, a, 'Exec', 4, name, hit(name))
    log(string.format('arm %08x %-14s -> %s', a, name, tostring(o)))
    if o then bp5[#bp5 + 1] = b end
end
log('=== bp5 watching ===')

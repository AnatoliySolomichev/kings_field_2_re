-- Who writes an object's type id?
--
--   dofile('/home/solo/my/projects/kings_field_2_english/emu/bp12.lua')
--
-- This question was asked twice before, by bp8 and bp9, and both times the
-- answer was silence -- but both returned `false` from their callbacks, which
-- PCSX-Redux reads as "remove this breakpoint", so both were dead after their
-- first hit and the silence meant nothing.
--
-- Now measured properly. `find_free_slot` has since been ruled out for real:
-- with a live control proving the instrument, a full level crossing produced
-- zero calls to it while 345 objects appeared. So the array is filled by
-- writing, not by allocating, and this catches the write.
--
-- Watched: the type id of the first four slots, and slot 0's X. Four rather
-- than one in case the fill does not start at the front. CONTROL rides along
-- so that a negative result is worth something.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp12.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 4000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp12 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function levelByte() return mem[0x8018fad9 % 0x200000] end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

local count = {}
local seenpc = {}
bp12 = {}

local function arm(addr, kind, width, tag, cap)
    cap = cap or 10
    count[tag] = 0
    local ok, bp = pcall(PCSX.addBreakpoint, addr, kind, width, tag,
        function(address)
            count[tag] = count[tag] + 1
            local g, all = regs()
            local pc = all and tonumber(all.pc) or 0
            -- one line per distinct pc, so a fill loop shows its shape without
            -- burying the log, and every distinct writer appears
            local key = tag .. ':' .. pc
            seenpc[key] = (seenpc[key] or 0) + 1
            if seenpc[key] <= 3 or count[tag] % 500 == 0 then
                log(string.format('%-7s #%-5d pc=%08x ra=%08x  a0=%08x s0=%08x  level=%d',
                    tag, count[tag], pc,
                    g and tonumber(g.ra) or 0,
                    g and tonumber(g.a0) or 0,
                    g and tonumber(g.s0) or 0,
                    levelByte()))
            end
            -- no return value: returning false would delete the breakpoint
        end)
    log(string.format('arm %08x %-5s x%-2d %-7s -> %s', addr, kind, width, tag, tostring(ok)))
    if ok then bp12[#bp12 + 1] = bp end
end

arm(0x801aec4c, 'Write', 4, 'CONTROL')     -- proves the instrument is speaking
arm(0x80191a62, 'Write', 2, 'ID0')         -- slot 0 type id
arm(0x80191aa6, 'Write', 2, 'ID1')         -- slot 1
arm(0x80191aea, 'Write', 2, 'ID2')         -- slot 2
arm(0x80191b2e, 'Write', 2, 'ID3')         -- slot 3
arm(0x80191a70, 'Write', 4, 'X0')          -- slot 0 world X
log('=== bp12 watching; cross between levels ===')

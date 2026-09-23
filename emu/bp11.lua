-- Do breakpoints stop because they are one-shot, or because we asked them to?
--
--   dofile('bp11.lua')      -- run.sh starts the emulator in emu/
--
-- Every breakpoint in this project so far has fired exactly once and gone
-- quiet, which was written down as "breakpoints here are one-shot". But every
-- callback so far also ended with `return false`, meant as "do not halt the
-- emulator" -- and that same value may equally be read as "do not keep this
-- breakpoint". If so the one-shot behaviour was ours, not the debugger's.
--
-- This tests it the only honest way: a control on something that happens
-- constantly. CONTROL sits on the player position and its callback returns
-- nothing at all. Walk a few steps:
--
--   many CONTROL lines  -> `return false` was removing them, and the earlier
--                          "breakpoints are one-shot" note is wrong
--   one CONTROL line    -> they really are one-shot, and every live experiment
--                          needs re-arming by hand
--
-- Either answer is worth having, and the two real breakpoints ride along under
-- the same convention so a crossing measured now is measured properly.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp11.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 4000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp11 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

-- what the API actually offers, logged once so the next script need not guess
local names = {}
for k, v in pairs(PCSX) do
    if tostring(k):lower():find('break') then names[#names + 1] = tostring(k) end
end
log('PCSX breakpoint API: ' .. (#names > 0 and table.concat(names, ', ') or '(none found)'))

local mem = PCSX.getMemPtr()
local function levelByte() return mem[0x8018fad9 % 0x200000] end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

local count = {}
bp11 = {}

local function arm(addr, kind, width, tag, cap)
    cap = cap or 12
    count[tag] = 0
    local ok, bp = pcall(PCSX.addBreakpoint, addr, kind, width, tag,
        function(address)
            count[tag] = count[tag] + 1
            if count[tag] <= cap then
                local g, all = regs()
                log(string.format('%-8s #%-4d pc=%08x ra=%08x  a0=%08x  level=%d',
                    tag, count[tag],
                    all and tonumber(all.pc) or 0,
                    g and tonumber(g.ra) or 0,
                    g and tonumber(g.a0) or 0,
                    levelByte()))
            elseif count[tag] % 200 == 0 then
                log(string.format('%-8s #%d (still firing)', tag, count[tag]))
            end
            -- deliberately return nothing: see the note at the top
        end)
    log(string.format('arm %08x %-5s x%-2d %-8s -> %s', addr, kind, width, tag, tostring(ok)))
    if ok then bp11[#bp11 + 1] = bp end
end

arm(0x801aec4c, 'Write', 4, 'CONTROL')          -- must repeat as the player walks
arm(0x80046034, 'Exec', 4, 'ALLOC')             -- find_free_slot
arm(0x80018358, 'Exec', 4, 'LOAD')              -- level_load
log('=== bp11 watching; walk a few steps first, then cross ===')

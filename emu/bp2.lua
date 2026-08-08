-- Second attempt at breakpoints, this time reporting why they do or do not work.
--
-- The first script armed four addresses successfully and never saw a hit, even
-- with the item screen open, which should certainly read ITEM.T. So this one
-- checks its own assumptions: whether the debug setting is on, whether each
-- breakpoint reports itself enabled, and whether a breakpoint on an address
-- that provably executes ever fires.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp2.log'
local out = io.open(LOG, 'a')
local lines = 0

local function log(s)
    if lines > 5000 then return end
    lines = lines + 1
    out:write(s .. '\n')
    out:flush()
end

log('=== bp2 loaded ===')

-- 1. what does the settings tree look like, and is Debug on?
local function probeSettings()
    local ok, s = pcall(function() return PCSX.settings end)
    if not ok or s == nil then
        log('PCSX.settings not reachable')
        return
    end
    log('PCSX.settings is reachable')
    local ok2, dbg = pcall(function() return s.Emulator.Debug.Debug end)
    if ok2 then
        log('settings Emulator.Debug.Debug = ' .. tostring(dbg))
        local ok3, err = pcall(function() s.Emulator.Debug.Debug = true end)
        log('tried to enable it: ' .. (ok3 and 'ok' or tostring(err)))
    else
        log('could not read Emulator.Debug.Debug: ' .. tostring(dbg))
    end
end
pcall(probeSettings)

-- 2. arm, then ask each breakpoint whether it considers itself enabled
local ARCHIVES = { [0] = 'MO', 'MOF', 'VAB', 'RTIM', 'FDAT', 'RTMD', 'ITEM',
                   'TALK', 'STALK' }
local hits = 0

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

local function onHit(address, width, cause)
    hits = hits + 1
    local g = regs()
    if g == nil then
        log(string.format('HIT %08x (registers unreadable)', address))
        return false
    end
    local a0 = (tonumber(g.a0) or 0) % 65536
    local a1 = (tonumber(g.a1) or 0) % 65536
    log(string.format('HIT %08x  archive=%d (%s)  entry=%d  ra=%08x',
        address, a0, ARCHIVES[a0] or '?', a1, tonumber(g.ra) or 0))
    return false
end

-- the exception vector: caught executing 14 times out of 14 when sampling, so
-- if breakpoints work at all this one must fire immediately
local canary = 0x80000080
local targets = { canary, 0x80019cc4, 0x8001a154, 0x80027d88, 0x80044204 }

bps = {}
for _, a in ipairs(targets) do
    local ok, bp = pcall(PCSX.addBreakpoint, a, 'Exec', 4, 'probe', onHit)
    if ok and bp then
        bps[#bps + 1] = bp
        local ok2, en = pcall(function() return bp:isEnabled() end)
        log(string.format('armed %08x   enabled=%s', a,
            ok2 and tostring(en) or ('unknown: ' .. tostring(en))))
    else
        log(string.format('arm %08x FAILED: %s', a, tostring(bp)))
    end
end

log(string.format('=== armed %d breakpoints; the canary at %08x should fire at once ===',
    #bps, canary))

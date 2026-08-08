-- The debug switch is PCSX.settings.emulator.Debug.Debug.
--
-- Earlier attempts missed it twice: the tree uses a lower-case `emulator`, and
-- `emulator.Debug` is a nested settings group rather than the flag itself, so
-- assigning to it succeeded while changing nothing. Set the real boolean, read
-- it back, then let the canary answer whether breakpoints evaluate at last.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp4.log'
local out = io.open(LOG, 'a')
local function log(s) out:write(tostring(s) .. '\n') out:flush() end

log('=== bp4 loaded ===')

local dbg = PCSX.settings.emulator.Debug
local ok, before = pcall(function() return dbg.Debug end)
log('emulator.Debug.Debug before = ' .. (ok and tostring(before) or ('unreadable: ' .. tostring(before))))

local ok2, err = pcall(function() dbg.Debug = true end)
log('set true -> ' .. (ok2 and 'ok' or tostring(err)))

local ok3, after = pcall(function() return dbg.Debug end)
log('reads back = ' .. (ok3 and tostring(after) or ('unreadable: ' .. tostring(after))))

-- some settings expose a value through a call rather than a field
if not ok3 or type(after) ~= 'boolean' then
    local ok4, v = pcall(function() return dbg.Debug:value() end)
    log('as :value() -> ' .. (ok4 and tostring(v) or tostring(v)))
    local ok5, e5 = pcall(function() dbg.Debug:setValue(true) end)
    log('setValue(true) -> ' .. (ok5 and 'ok' or tostring(e5)))
end

local hits = 0
local function onHit(address)
    hits = hits + 1
    if hits <= 10 then log(string.format('HIT %08x', address)) end
    if hits == 10 then log('(further hits suppressed)') end
    return false
end

bps = {}
for _, a in ipairs({ 0x80000080, 0x80019cc4, 0x8001a154, 0x80027d88, 0x80044204 }) do
    local okb, bp = pcall(PCSX.addBreakpoint, a, 'Exec', 4, 'probe', onHit)
    log(string.format('armed %08x -> %s', a, tostring(okb)))
    if okb then bps[#bps + 1] = bp end
end
log('=== waiting; the canary fires immediately if breakpoints now evaluate ===')

-- Find the debug switch, flip it, then see if the canary finally fires.
--
-- Breakpoints register and report enabled=true, yet a breakpoint on the
-- exception vector -- an address caught executing 14 times out of 14 -- never
-- fires. So they are registered but never evaluated, and the remaining suspect
-- is the debug setting. PCSX.settings is reachable but PCSX.settings.Emulator
-- is nil, so the tree is walked here to find where the switch actually lives.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp3.log'
local out = io.open(LOG, 'a')
local function log(s) out:write(tostring(s) .. '\n') out:flush() end

log('=== bp3 loaded ===')

local function keysOf(t)
    local ks = {}
    local ok = pcall(function()
        for k in pairs(t) do ks[#ks + 1] = tostring(k) end
    end)
    if not ok then return nil end
    table.sort(ks)
    return ks
end

-- 1. what is in the settings tree, two levels deep
local s = PCSX.settings
local top = keysOf(s)
if top == nil then
    log('settings is not iterable')
else
    log('settings keys: ' .. table.concat(top, ', '))
    for _, k in ipairs(top) do
        local ok, sub = pcall(function() return s[k] end)
        if ok and type(sub) == 'table' or type(sub) == 'userdata' then
            local ks = keysOf(sub)
            if ks then log('  ' .. k .. ': ' .. table.concat(ks, ', ')) end
        end
    end
end

-- 2. hunt for anything named Debug and turn it on
local function tryFlip(path, node)
    local ks = keysOf(node)
    if ks == nil then return end
    for _, k in ipairs(ks) do
        local full = path .. '.' .. k
        if k == 'Debug' then
            local ok, val = pcall(function() return node[k] end)
            log('found ' .. full .. ' = ' .. tostring(val))
            local ok2, err = pcall(function() node[k] = true end)
            log('  set true -> ' .. (ok2 and 'ok' or tostring(err)))
            local ok3, now = pcall(function() return node[k] end)
            log('  now reads ' .. (ok3 and tostring(now) or '?'))
        else
            local ok, sub = pcall(function() return node[k] end)
            if ok and (type(sub) == 'table' or type(sub) == 'userdata') then
                pcall(tryFlip, full, sub)
            end
        end
    end
end
pcall(tryFlip, 'settings', s)

-- 3. arm the canary again and see whether flipping the switch changed anything
local hits = 0
local function onHit(address)
    hits = hits + 1
    if hits < 12 then log(string.format('HIT %08x', address)) end
    return false
end
bps = {}
for _, a in ipairs({ 0x80000080, 0x80019cc4, 0x8001a154, 0x80044204 }) do
    local ok, bp = pcall(PCSX.addBreakpoint, a, 'Exec', 4, 'probe', onHit)
    log(string.format('armed %08x -> %s', a, tostring(ok)))
    if ok then bps[#bps + 1] = bp end
end
log('=== waiting for the canary ===')

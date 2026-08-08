-- Watch the level transition itself.
--
-- Breakpoints on the five archive readers caught only three hits, all during
-- boot, and none while walking from level 0 to level 4. So a level change does
-- not read the .T archives at all, and the interesting code is the transition
-- machinery instead: the routine that commits the pending level block, the one
-- that resets it, the save-state restore, and the builder for the streamed
-- \DRM\Dnn.S filenames.
--
-- The switch is PCSX.settings.emulator.Debug.Debug and must be set here at
-- runtime -- putting it in pcsx.json does not take. It also needs the
-- interpreter, since the binary warns the debugger and dynarec conflict.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 20000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== armed; debug switch = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local NAMES = {
    [0x80018358] = 'commit pending->current level',
    [0x80029188] = 'reset level block to 0x63',
    [0x8005ffd0] = 'restore state from a save',
    [0x80061088] = 'build \\DRM\\Dnn.S filename',
    [0x80060fcc] = 'build \\STR\\Snn.S filename',
    [0x800441d4] = 'archive read (archive, entry)',
}

local counts = {}

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

local function onHit(address)
    counts[address] = (counts[address] or 0) + 1
    -- routines called every frame would drown the log; keep the first few of
    -- each and then only every hundredth
    local n = counts[address]
    if n > 6 and n % 100 ~= 0 then return false end
    local g = regs()
    local a0, a1, ra = -1, -1, 0
    if g then
        a0 = (tonumber(g.a0) or 0) % 65536
        a1 = (tonumber(g.a1) or 0) % 65536
        ra = tonumber(g.ra) or 0
    end
    log(string.format('%08x #%-5d %-32s a0=%-6d a1=%-6d ra=%08x',
        address, n, NAMES[address] or '?', a0, a1, ra))
    return false
end

bps = {}
for a in pairs(NAMES) do
    local ok, bp = pcall(PCSX.addBreakpoint, a, 'Exec', 4, 'transition', onHit)
    if ok then bps[#bps + 1] = bp end
    log(string.format('arm %08x %-32s -> %s', a, NAMES[a], tostring(ok)))
end
log('=== watching the transition machinery ===')

-- Where does a level actually come from?
--
-- Breakpoints on every archive reader caught three hits in a whole session,
-- all during boot and none while crossing from level 0 to level 4. So the
-- level payload does not come through the .T archives. This watches the CD
-- path instead -- the filename builders for the streamed \DRM\Dnn.S and
-- \STR\Snn.S files, and the BIOS CD entry points -- alongside the transition
-- routine itself, so the whole sequence is visible in order.
--
-- The switch is PCSX.settings.emulator.Debug.Debug and must be set here at
-- runtime; putting it in pcsx.json does not take. It also needs the
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
    [0x80017c78] = 'TRANSITION(level,...)',
    [0x80018358] = 'commit pending->current',
    [0x80061088] = 'build \\DRM\\Dnn.S name',
    [0x80060fcc] = 'build \\STR\\Snn.S name',
    [0x80063ef0] = 'CD_read',
    [0x800641a8] = 'CD_datasync',
    [0x800441d4] = 'archive read',
    [0x8005ffd0] = 'restore state',
}

local counts = {}

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

-- the first four arguments arrive in registers, the rest on the stack at
-- sp+0x10 upwards, and the transition call passes eight in total
local mem = PCSX.getMemPtr()
local function byteAt(addr)
    local off = addr % 0x200000
    return mem[off]
end
local function wordAt(addr)
    local off = addr % 0x200000
    return mem[off] + mem[off + 1] * 256 + mem[off + 2] * 65536 + mem[off + 3] * 16777216
end
local function levelBlock()
    local t = {}
    for i = 0, 4 do t[#t + 1] = string.format('%02x', byteAt(0x8018fad8 + i)) end
    return table.concat(t, ' ')
end

local function onHit(address)
    counts[address] = (counts[address] or 0) + 1
    local n = counts[address]
    if n > 8 and n % 50 ~= 0 then return false end
    local g = regs()
    -- keep the arguments full width as well as byte-wide. The body of the
    -- transition compares each against 0xff, so the low byte is what carries
    -- the level numbers, but if any of the eight is a landing coordinate then
    -- masking it to a byte is exactly how we would miss it.
    local w0, w1, w2, w3, ra, sp = 0, 0, 0, 0, 0, 0
    if g then
        w0 = tonumber(g.a0) or 0
        w1 = tonumber(g.a1) or 0
        w2 = tonumber(g.a2) or 0
        w3 = tonumber(g.a3) or 0
        ra = tonumber(g.ra) or 0
        sp = tonumber(g.sp) or 0
    end
    if address == 0x80017c78 and sp ~= 0 then
        local s0, s1 = wordAt(sp + 0x10), wordAt(sp + 0x14)
        local s2, s3 = wordAt(sp + 0x18), wordAt(sp + 0x1c)
        log(string.format('%08x #%-3d TRANSITION  args=%02x %02x %02x %02x | stack=%02x %02x %02x %02x'
            .. '  level=[%s]  ra=%08x',
            address, n, w0 % 256, w1 % 256, w2 % 256, w3 % 256,
            s0 % 256, s1 % 256, s2 % 256, s3 % 256, levelBlock(), ra))
        log(string.format('                  full  a=%08x %08x %08x %08x  sp=%08x %08x %08x %08x',
            w0, w1, w2, w3, s0, s1, s2, s3))
    else
        log(string.format('%08x #%-3d %-24s a0=%-6d a1=%-6d a2=%08x a3=%-5d ra=%08x  level=[%s]',
            address, n, NAMES[address] or '?', w0 % 256, w1 % 256, w2, w3 % 256, ra, levelBlock()))
    end
    return false
end

bps = {}
for a in pairs(NAMES) do
    local ok, bp = pcall(PCSX.addBreakpoint, a, 'Exec', 4, 'level load', onHit)
    if ok then bps[#bps + 1] = bp end
    log(string.format('arm %08x %-24s -> %s', a, NAMES[a], tostring(ok)))
end
log('=== watching the level load path ===')

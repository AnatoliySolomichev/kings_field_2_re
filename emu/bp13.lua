-- What does tile_collision actually answer, and who is asking?
--
--   dofile('bp13.lua')      -- run.sh starts the emulator in emu/
--
-- The struct at 0x801e6470 is global scratch and ten call sites reach the
-- wrapper above it, object_motion among them -- so reading the mask out of RAM
-- samples whichever monster moved last, not the player. Every positive control
-- built on those reads came out meaningless, which is what this fixes.
--
-- Two points, paired: the entry keeps the arguments, the exit reads the mask
-- the routine is about to return in $t4. `ra` at entry separates the player's
-- calls from everything else, which is the whole reason for doing this at all.
--
-- Volume is the hazard: the routine runs per object per frame. Hits are
-- therefore logged in full only while they are new, and sparsely after that.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp13.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 6000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp13 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function u8(a) return mem[a % 0x200000] end
local function u32(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256 + mem[b + 2] * 65536 + mem[b + 3] * 16777216
end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

local pend = nil          -- arguments of the call now running
local seen = {}           -- how many times each caller has been logged
local n = 0
bp13 = {}

local function arm(addr, tag, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, tag, fn)
    log(string.format('arm %08x %-6s -> %s', addr, tag, tostring(ok)))
    if ok then bp13[#bp13 + 1] = bp end
end

arm(0x8003260c, 'enter', function()
    local g = regs()
    if g == nil then return end
    -- the fifth argument, which the routine reads at 0x98($sp) once its own
    -- prologue has moved sp by 0x88. The breakpoint is on that prologue's first
    -- instruction, so sp is still the caller's and the argument sits at +0x10.
    -- It is what turns the player's height into the `s3` the wall test uses,
    -- and without it three calls in a thousand cannot be told apart.
    pend = {x = tonumber(g.a0), y = tonumber(g.a1), z = tonumber(g.a2),
            r = tonumber(g.a3), ra = tonumber(g.ra),
            arg5 = u32(tonumber(g.sp) + 0x10),
            cell = u32(0x801e6464), base = u32(0x801e6470)}
end)

-- 0x80033adc is `move $v0, $t4`: the mask, before it becomes the return value
arm(0x80033adc, 'leave', function()
    if pend == nil then return end
    local g = regs()
    if g == nil then return end
    local mask = tonumber(g.t4)
    n = n + 1
    -- Key on the *shape*, not on the caller. Keying on the caller starved the
    -- log the moment the interesting question became "what does this opcode
    -- do": the caller had long since used up its quota, so walking onto new
    -- geometry recorded almost nothing.
    local sid = u8(pend.cell + 8)
    local key = string.format('%d/%d', sid, mask)
    seen[key] = (seen[key] or 0) + 1
    if seen[key] <= 40 or n % 997 == 0 then
        log(string.format(
            '%08x mask=%2d x=%8d y=%8d z=%8d r=%5d cell=%08x base=%d arg5=%d lv=%d',
            pend.ra, mask, pend.x, pend.y, pend.z, pend.r,
            pend.cell, pend.base, pend.arg5, u8(0x8018fad9)))
    end
    pend = nil
end)

log('=== bp13 watching; walk into a wall, then walk about ===')

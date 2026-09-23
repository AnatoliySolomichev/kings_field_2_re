-- Who writes the player's Y? Not by reading the code -- by catching the store.
--
--   ./emu/run.sh debug bp15.lua
--
-- `player_move` (0x8002f320) was read out of the MIPS and transcribed, and the
-- first recording said it never runs while walking: 69 calls in a whole
-- session, every one of them in player state 0x10 or 0x11, which is the
-- knockback after dying. Meanwhile the control point fired eight hundred times
-- with the position visibly changing. So the routine is real and the claim that
-- it is *the* movement was not.
--
-- Reading further found `0x8002ed60`, a second state machine on `0x801b25e8`
-- with its own velocity at `0x801b2656` -- but that is another reading, and the
-- last one cost a day. A write watchpoint on the player's own coordinates does
-- not need to be right about which routine to look at: whatever moves the
-- player has to store into them, and this prints its address.
--
-- One line per distinct storing instruction, with a count, so a per-frame
-- writer does not flood the log and a rare one is not lost behind it. Note
-- `pc` is the store; `ra` says who called the routine it is in.
--
-- Never `return false` from the callback: PCSX-Redux reads that as "delete this
-- breakpoint", and a watchpoint that fires once tells you nothing afterwards.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp15.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 4000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp15 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function u8(a) return mem[a % 0x200000] end
local function u16(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256
end
local function s16(a)
    local v = u16(a)
    if v >= 0x8000 then v = v - 0x10000 end
    return v
end
local function s32(a)
    local b = a % 0x200000
    local v = mem[b] + mem[b + 1] * 256 + mem[b + 2] * 65536 + mem[b + 3] * 16777216
    if v >= 0x80000000 then v = v - 0x100000000 end
    return v
end

local PX, PY, PZ = 0x801b25f0, 0x801b25f4, 0x801b25f8

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil, nil end
    if r.GPR and r.GPR.n then return r.GPR.n, r end
    return r.GPR or r, r
end

local seen = {}
local order = {}
bp15 = {}

local function hit(tag)
    return function()
        local g, all = regs()
        local pc = all and tonumber(all.pc) or 0
        local key = string.format('%s@%08x', tag, pc)
        if seen[key] == nil then
            seen[key] = 0
            order[#order + 1] = key
        end
        seen[key] = seen[key] + 1
        -- The first few in full, then every 200th, so a steady writer keeps
        -- reporting where it has got to without filling the file.
        if seen[key] <= 6 or seen[key] % 200 == 0 then
            log(string.format(
                '%-2s pc=%08x ra=%08x n=%6d  pos=%9d %9d %9d  ' ..
                'vstate=%3d vvel=%6d  pstate=%3d  vel=%6d %6d %6d  lv=%d',
                tag, pc, g and tonumber(g.ra) or 0, seen[key],
                s32(PX), s32(PY), s32(PZ),
                u8(0x801b25e8), s16(0x801b2656), u8(0x801b25e5),
                s16(0x801b266c), s16(0x801b266e), s16(0x801b2670),
                u8(0x8018fad9)))
        end
    end
end

local function arm(addr, width, kind, tag)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, kind, width, tag, hit(tag))
    log(string.format('arm %08x %-5s x%-2d %-3s -> %s', addr, kind, width, tag,
        tostring(ok)))
    if ok then bp15[#bp15 + 1] = bp end
end

arm(PY, 4, 'Write', 'Y')       -- the height: the question
arm(PX, 4, 'Write', 'X')       -- and one horizontal, to tell the two apart
arm(0x801b2656, 2, 'Write', 'V')   -- the candidate vertical velocity

log('=== bp15 watching; walk on the flat, up and down stairs, off a ledge ===')

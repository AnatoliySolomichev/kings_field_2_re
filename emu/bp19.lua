-- What fills the animation frames, and what picks which one is drawn.
--
--   ./emu/run.sh debug bp19.lua
--
-- Then walk up to something that moves -- the men in the house at level 0
-- (62,3), or any monster -- and watch it for a few seconds.
--
-- What is known without the emulator: the routine that draws a creature,
-- 0x8003e34c, is an interpolator. It forms two frame pointers as
--
--     base = 0x801aac54 + 0x42a8 = 0x801aeefc
--     frame = base + 108 * (n & 0x3f)
--
-- and blends them with 0x80017158. A frame is 108 bytes -- 54 signed
-- halfwords, values inside +/-4096, so eighteen joints of three angles. Frames
-- 0 and 1 of a level 0 snapshot are identical and frame 2 differs, which is
-- what keyframes look like.
--
-- What is not known, and what this asks:
--
--   * **who fills the table.** The bytes are not a verbatim run in any of the
--     seven archives, so it is built or unpacked at run time, and scanning for
--     code that names the address finds nothing -- the fill must go through a
--     pointer. A write watchpoint does not care: whatever writes it says so.
--   * **what picks the frame.** The two indices come in as arguments; the
--     watchpoint on the actor's +0x0c reports the field EXTERNAL.md calls the
--     current animation, with the caller beside it.
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint", and silence afterwards would mean nothing.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp19.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 4000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp19 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function u8(a) return mem[a % 0x200000] end
local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end
local function pc()
    local ok, r = pcall(PCSX.getRegisters)
    if ok and r and r.pc then return tonumber(r.pc) end
    return 0
end

bp19 = {}
local seen = {}
local function arm(addr, tag, kind, width, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, kind, width, tag, fn)
    log(string.format('arm %08x+%-5d %-14s %-5s -> %s', addr, width, tag, kind,
        tostring(ok)))
    if ok then bp19[#bp19 + 1] = bp end
end

-- The first eight frames of the table. Watching all 64 would be 6912 bytes and
-- every blend would trip it; eight is enough to name the writer.
arm(0x801AEEFC, 'frames', 'Write', 108 * 8, function(addr)
    local g = regs()
    if g == nil then return end
    local a = tonumber(addr) or 0x801AEEFC
    local frame = math.floor((a - 0x801AEEFC) / 108)
    local key = 'w' .. tostring(pc())
    seen[key] = (seen[key] or 0) + 1
    if seen[key] <= 8 then
        log(string.format('FILL frame %d (+%d)  pc=%08x ra=%08x',
            frame, (a - 0x801AEEFC) % 108, pc(), tonumber(g.ra)))
    end
end)

-- The three actors by the house, and their animation field. EXTERNAL.md calls
-- +0x0c the current animation and +0x0e the state; both are unverified for
-- this game, which is the point of looking.
for slot = 0, 2 do
    local base = 0x80185da8 + slot * 0x88
    arm(base + 0x0C, 'actor' .. slot .. '_anim', 'Write', 2, function()
        local g = regs()
        if g == nil then return end
        log(string.format('ANIM actor %d mesh=%d +0x0c=%d +0x0e=%d alive=%d '
            .. 'pc=%08x ra=%08x', slot, u8(base + 1), u8(base + 0x0C),
            u8(base + 0x0E), u8(base + 9), pc(), tonumber(g.ra)))
    end)
end

-- And what raises the byte that decides a creature is drawn at all, which is
-- the other half of the question: render_walk skips any actor whose +9 is not 1.
for slot = 0, 2 do
    local base = 0x80185da8 + slot * 0x88
    arm(base + 9, 'actor' .. slot .. '_on', 'Write', 1, function()
        local g = regs()
        if g == nil then return end
        log(string.format('DRAW actor %d mesh=%d alive->%d pc=%08x ra=%08x',
            slot, u8(base + 1), u8(base + 9), pc(), tonumber(g.ra)))
    end)
end

-- The port reads res://live.txt once per game frame and stands a marker where
-- the real player is. bp16 writes it; without it the Godot build's C key has
-- nothing to compare against, which is exactly what happened the first time
-- this script was run. So write it here too, from the same head-of-movement
-- breakpoint bp16 uses.
local LIVE = '/home/solo/my/projects/kings_field_2_english/out/godot/live.txt'
local frame = 0
local function s16(v) if v >= 0x8000 then return v - 0x10000 end return v end
local function u16(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256
end
local function s32(a)
    local b = a % 0x200000
    local v = mem[b] + mem[b + 1] * 256 + mem[b + 2] * 65536 + mem[b + 3] * 16777216
    if v >= 0x80000000 then v = v - 0x100000000 end
    return v
end

arm(0x8002fe1c, 'live', 'Exec', 4, function()
    frame = frame + 1
    local f = io.open(LIVE .. '.tmp', 'w')
    if f == nil then return end
    f:write(string.format('%d %d %d %d %d %d %d %d %d %d %d %d\n',
        frame, s32(0x801b25f0), s32(0x801b25f4), s32(0x801b25f8),
        u16(0x801b2612), u8(0x801b25e8), s16(u16(0x801b2656)),
        s16(u16(0x801b2648)), s16(u16(0x801b2646)), u16(0x801b265c),
        u8(0x8018fad8), s16(u16(0x801b2610))))
    f:close()
    os.rename(LIVE .. '.tmp', LIVE)
end)

log('=== bp19 watching; stand near something that moves ===')

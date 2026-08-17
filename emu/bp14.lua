-- The player's own move routine, in and out.
--
--   dofile('/home/solo/my/projects/kings_field_2_english/emu/bp14.lua')
--
-- `actor_move_horizontal` (0x8004dbc8) turned out to belong to the monsters:
-- its actor comes from the pointer at 0x8018fab4, which `actor_select`
-- (0x8004da2c) fills from the 0x88-byte table at 0x80185da8. The player is not
-- in that table -- no entry in any snapshot carries the player's position -- and
-- has a routine of its own, `player_move` at 0x8002f320, which is the only code
-- that writes the player's Y at 0x801b25f4 during ordinary play.
--
-- This logs one line per call: the position and velocity going in, and the same
-- coming out, together with the returned code and the nearest surface the
-- collision left at 0x801e6474. That is everything a reimplementation needs in
-- order to be checked call for call rather than by eye, which is the point:
-- `tools/movement.py` replays this log and either reproduces every line or
-- names the ones it does not.
--
-- Never `return false` from a callback here: PCSX-Redux reads it as "delete
-- this breakpoint", the point fires once, and the silence afterwards means
-- nothing.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp14.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 40000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp14 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

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
local function u32(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256 + mem[b + 2] * 65536 + mem[b + 3] * 16777216
end
local function s32(a)
    local v = u32(a)
    if v >= 0x80000000 then v = v - 0x100000000 end
    return v
end

local PX, PY, PZ = 0x801b25f0, 0x801b25f4, 0x801b25f8   -- the master copy
local VX, VY, VZ = 0x801b266c, 0x801b266e, 0x801b2670   -- s16 velocity
local SURF = 0x801e6474                                 -- nearest surface
local STATE = 0x801b25e5                                -- player state byte

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

local pend = nil
local calls = 0
bp14 = {}

local function arm(addr, tag, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, tag, fn)
    log(string.format('arm %08x %-6s -> %s', addr, tag, tostring(ok)))
    if ok then bp14[#bp14 + 1] = bp end
end

arm(0x8002f320, 'enter', function()
    local g = regs()
    pend = {x = s32(PX), y = s32(PY), z = s32(PZ),
            vx = s16(VX), vy = s16(VY), vz = s16(VZ),
            ra = g and tonumber(g.ra) or 0,
            st = u8(STATE), lv = u8(0x8018fad9), surf = nil}
end)

-- The committing path calls 0x80028d54 on the way out, and that reaches the
-- collision again, so the surface read at the exit would be another query's.
-- Take it here instead, before the call, and keep the exit reading for the
-- paths that return without one.
arm(0x8002f59c, 'surf', function()
    if pend ~= nil then pend.surf = s32(SURF) end
end)

-- 0x8002f5a8 is `lw $ra, 0x30($sp)`: every return path has already put its
-- answer in $v0 and every commit to the position has already happened.
arm(0x8002f5a8, 'leave', function()
    if pend == nil then return end
    local g = regs()
    if g == nil then return end
    calls = calls + 1
    log(string.format(
        'mv i=%9d %9d %9d v=%6d %6d %6d o=%9d %9d %9d v=%6d %6d %6d ' ..
        'ret=%d surf=%9d st=%3d lv=%2d ra=%08x',
        pend.x, pend.y, pend.z, pend.vx, pend.vy, pend.vz,
        s32(PX), s32(PY), s32(PZ), s16(VX), s16(VY), s16(VZ),
        tonumber(g.v0), pend.surf or s32(SURF), pend.st, pend.lv, pend.ra))
    pend = nil
end)

-- A control on something known to run constantly, in the same session. If this
-- one is silent the arming failed and the absence of `mv` lines means nothing.
arm(0x80028d54, 'sync', function()
    if calls % 300 == 0 then
        log(string.format('-- alive: %d moves logged, player at %d %d %d',
            calls, s32(PX), s32(PY), s32(PZ)))
    end
end)

log('=== bp14 watching; walk, climb a stair, jump off something ===')

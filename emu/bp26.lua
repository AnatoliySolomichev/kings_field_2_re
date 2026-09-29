-- The effects: what a creature's volley throws, frame by frame.
--
--   ./emu/run.sh debug bp26.lua
--
-- Then go near one of level 0's kind-3 creatures (model 57) -- one stands at
-- cell (40,29), others at (26,27), (27,25), (15,20) -- and let it cast at you
-- from the front for a while: its volley (opcode 0x19) launches an effect,
-- effect kind 0x26, from about 1000 into its clock. Get hit by a few, dodge a
-- few. tools/effects.py is what this is for.
--
-- FX     at the head of effect_driver (0x8005bc50), once a frame: every live
--        slot of the 128 at effect_slots (0x801b80ec, 0x4c bytes each), as its
--        index and the whole 0x4c bytes in hex; and the player's position
-- SPAWN  effect_spawn (0x80053c84): its four arguments, the 16 bytes of the
--        point a3 points at, the fifth argument's 8 bytes, and the caller
-- HURT   player_take_hit (0x8002ab18): the four register arguments, the five
--        stack ones, the scale, percent and point, the HP, and the caller
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint".

local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local out = io.open(OUT .. 'lua_bp26.log', 'a')
local lines = 0
local function log(s)
    if lines > 200000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp26 (effects) armed ===')

local mem = PCSX.getMemPtr()
local function u8(a) return mem[a % 0x200000] end
local function u16(a)
    local b = a % 0x200000
    return mem[b] + mem[b + 1] * 256
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
local function hex(a, n)
    local t = {}
    for i = 0, n - 1 do t[#t + 1] = string.format('%02x', u8(a + i)) end
    return table.concat(t)
end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end
local function reg(g, name)
    return (tonumber(g[name]) or 0) % 0x100000000
end

local VBLANKS = 0x801c12e8
local SLOTS, STRIDE = 0x801b80ec, 0x4c
local PLAYER = 0x801b25f0
local HP = 0x801b24fc

local function arm(addr, name, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, name, fn)
    log(string.format('arm %08x %s -> %s', addr, name, tostring(ok)))
    return bp
end

bp26 = {}
bp26[1] = arm(0x8005bc50, 'fx', function()
    local live = {}
    for k = 0, 127 do
        local a = SLOTS + k * STRIDE
        if u8(a) ~= 0xff then
            live[#live + 1] = string.format('%d:%s', k, hex(a, STRIDE))
        end
    end
    if #live == 0 then return end
    log(string.format('FX vb=%d pos=%d,%d,%d hp=%d %s', s32(VBLANKS), s32(PLAYER),
        s32(PLAYER + 4), s32(PLAYER + 8), u16(HP), table.concat(live, ' ')))
end)
bp26[2] = arm(0x80053c84, 'spawn', function()
    local g = regs()
    if not g then return end
    local a3 = reg(g, 'a3')
    local sp = reg(g, 'sp')
    local p = u32(sp + 0x10)
    log(string.format('SPAWN vb=%d a0=%x a1=%x a2=%x pt=%s arg4=%s ra=%08x',
        s32(VBLANKS), reg(g, 'a0'), reg(g, 'a1'), reg(g, 'a2'),
        a3 >= 0x80000000 and hex(a3, 16) or 'none',
        p >= 0x80000000 and hex(p, 8) or 'none', reg(g, 'ra')))
end)
bp26[3] = arm(0x8002ab18, 'hurt', function()
    local g = regs()
    if not g then return end
    local sp = reg(g, 'sp')
    local pt = u32(sp + 0x2c)
    log(string.format('HURT vb=%d a=%d,%d,%d,%d m=%d,%d,%d,%d,%d scale=%d pct=%d pt=%s hp=%d ra=%08x',
        s32(VBLANKS), reg(g, 'a0'), reg(g, 'a1'), reg(g, 'a2'), reg(g, 'a3'),
        u16(sp + 0x10), u16(sp + 0x14), u16(sp + 0x18), u16(sp + 0x1c),
        u16(sp + 0x20), u32(sp + 0x24), u32(sp + 0x28),
        pt >= 0x80000000 and string.format('%d,%d,%d', s32(pt), s32(pt + 4), s32(pt + 8)) or 'none',
        u16(HP), reg(g, 'ra')))
end)
log('=== bp26 recording; let a kind-3 creature cast at you ===')

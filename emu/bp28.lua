-- The weapons' spells, flash and lightning in play, frame by frame: what the
-- effect machine does with them, and what it is handed.
--
--   ./emu/run.sh debug bp28.lua
--
-- Then, with a weapon whose spell is unlocked (PLAYTEST.md, B, says which and
-- where), stand a few cells from a creature and:
--   * charge both meters full, swing, and press the action button once the
--     swing's window opens -- the charged swing's spell;
--   * with both meters full, press CROSS, SQUARE, TRIANGLE in turn (the
--     default scheme), each within twenty frames -- the second swing's;
--   * cast flash and lightning bolt (the magic menu) at a creature and at a
--     wall, and lightning once off a ledge, over a drop.
-- Once each is enough. tools/effects.py is what this is for: the machine is
-- held to the game's own code already, and this holds it to the game in play.
--
-- FX     at the head of effect_driver (0x8005bc50), once a frame while a
--        slot lives: every live slot of the 128 at effect_slots (0x801b80ec,
--        0x4c bytes), its index and its bytes in hex; the player's place and
--        HP; and effect_tick's outgoing words (sp+0x10..0x2c of its frame,
--        below effect_driver's), which flash's second burst reads
-- ACT    the same frame: each awake creature (+9 1) -- slot, place, +0xe, HP
-- SPAWN  effect_spawn (0x80053c84): a0..a2, the point's 16 bytes, the eight
--        stack words from sp+0x10, the velocity's 8 bytes, and the caller
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint".

local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local out = io.open(OUT .. 'lua_bp28.log', 'a')
local lines = 0
local function log(s)
    if lines > 300000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp28 (the weapons\' spells) armed ===')

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
local ACTORS, ASTRIDE = 0x80185da8, 0x88
local PLAYER = 0x801b25f0
local HP = 0x801b24fc
-- effect_driver's frame is 0x28 (0x8005bc50: addiu sp, -0x28) and
-- effect_tick's 0x2b8 below it
local TICK_BELOW = 0x28 + 0x2b8

local function arm(addr, name, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, name, fn)
    log(string.format('arm %08x %s -> %s', addr, name, tostring(ok)))
    return bp
end

bp28 = {}
bp28[1] = arm(0x8005bc50, 'fx', function()
    local live = {}
    for k = 0, 127 do
        local a = SLOTS + k * STRIDE
        if u8(a) ~= 0xff then
            live[#live + 1] = string.format('%d:%s', k, hex(a, STRIDE))
        end
    end
    if #live == 0 then return end
    local g = regs()
    local words = 'none'
    if g then
        local tsp = reg(g, 'sp') - TICK_BELOW
        words = hex(tsp + 0x10, 0x20)
    end
    log(string.format('FX vb=%d pos=%d,%d,%d hp=%d out=%s %s', s32(VBLANKS), s32(PLAYER),
        s32(PLAYER + 4), s32(PLAYER + 8), u16(HP), words, table.concat(live, ' ')))
    local acts = {}
    for k = 0, 199 do
        local a = ACTORS + k * ASTRIDE
        if u8(a + 9) == 1 then
            acts[#acts + 1] = string.format('%d:%d,%d,%d,%x,%d', k, s32(a + 0x2c), s32(a + 0x30),
                s32(a + 0x34), u8(a + 0xe), u16(a + 0x1a))
        end
    end
    log(string.format('ACT vb=%d %s', s32(VBLANKS), table.concat(acts, ' ')))
end)
bp28[2] = arm(0x80053c84, 'spawn', function()
    local g = regs()
    if not g then return end
    local a3 = reg(g, 'a3')
    local sp = reg(g, 'sp')
    local p = u32(sp + 0x10)
    log(string.format('SPAWN vb=%d a0=%x a1=%x a2=%x pt=%s stack=%s vel=%s ra=%08x',
        s32(VBLANKS), reg(g, 'a0'), reg(g, 'a1'), reg(g, 'a2'),
        a3 >= 0x80000000 and hex(a3, 16) or 'none', hex(sp + 0x10, 0x20),
        p >= 0x80000000 and hex(p, 8) or 'none', reg(g, 'ra')))
end)
log('=== bp28 recording; charge a sword, swing at a creature, cast flash ===')

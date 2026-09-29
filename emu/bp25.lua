-- The player's weapon, frame by frame, and every blow that lands.
--
--   ./emu/run.sh debug bp25.lua
--
-- Then fight something: swing at the air a few times with a full meter and
-- with a part-empty one, hit a creature from the front and from the side, and
-- kill one. tools/weapon.py is the model this checks.
--
-- SWING  at the head of held_item_tick (0x8002d2a0), whenever a swing is
--        running or the meter is not full: the clock 0x801b25a4, the meter
--        0x801b2502, the strength 0x801b2504, the pause 0x801b24f3, the hit
--        and sound times 0x801b25a6 and 0x801b25a8, the weapon, the pitch and
--        facing, the player's position
-- HIT    at the head of actor_take_hit (0x8004c668): the slot, the stat, the
--        eight attacks, the strength (arg10), the flags (arg11), the point
--        (arg13), and the creature's HP, opcode, sub-state and position
-- HITOUT at its return (0x8004cea4): the creature's HP, opcode, vertical
--        state and velocity after
-- EXP    award_exp (0x8002a310) with what it is given
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint".

local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local out = io.open(OUT .. 'lua_bp25.log', 'a')
local lines = 0
local function log(s)
    if lines > 200000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp25 (the weapon) armed ===')

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

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end
local function reg(g, name)
    local v = g[name]
    if v == nil and name == 'fp' then v = g['s8'] end
    return (tonumber(v) or 0) % 0x100000000
end

local VBLANKS = 0x801c12e8
local ACTORS, STRIDE = 0x80185da8, 0x88
local cur = nil

local function arm(addr, name, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, name, fn)
    log(string.format('arm %08x %s -> %s', addr, name, tostring(ok)))
    return bp
end

bp25 = {}
bp25[1] = arm(0x8002d2a0, 'swing', function()
    local clock = s16(0x801b25a4)
    local meter = u16(0x801b2502)
    if clock == -1 and meter == 5000 and u8(0x801b24f3) == 0 then return end
    log(string.format(
        'SWING vb=%d clock=%d meter=%d str=%d pause=%d hit=%d snd=%d wpn=%d pitch=%d facing=%d view=%d btn=%04x pos=%d,%d,%d',
        s32(VBLANKS), clock, meter, u16(0x801b2504), u8(0x801b24f3),
        s16(0x801b25a6), s16(0x801b25a8), u8(0x801b25af), s16(0x801b2610),
        s16(0x801b2612), s16(0x801b260a), u16(0x801b265c),
        s32(0x801b25f0), s32(0x801b25f4), s32(0x801b25f8)))
end)
bp25[2] = arm(0x8004c668, 'hit', function()
    local g = regs()
    if not g then return end
    local sp = reg(g, 'sp')
    local k = reg(g, 'a0') % 0x10000
    local a = ACTORS + STRIDE * k
    cur = a
    local pt = u32(sp + 0x34)
    local p = 'none'
    if pt >= 0x80000000 then
        p = string.format('%d,%d,%d', s32(pt), s32(pt + 4), s32(pt + 8))
    end
    log(string.format(
        'HIT vb=%d slot=%d stat=%d att=%d,%d,%d,%d,%d,%d,%d,%d str=%d flags=%x point=%s hp=%d op=%d sub=%d yaw=%d pos=%d,%d,%d kind=%d',
        s32(VBLANKS), k, reg(g, 'a1') % 0x10000, reg(g, 'a2') % 0x10000,
        reg(g, 'a3') % 0x10000, u16(sp + 0x10), u16(sp + 0x14), u16(sp + 0x18),
        u16(sp + 0x1c), u16(sp + 0x20), u16(sp + 0x24), u16(sp + 0x28),
        u16(sp + 0x2c), p, u16(a + 0x1a), u8(a + 0xe), s16(a + 0x70),
        s16(a + 0x42), s32(a + 0x2c), s32(a + 0x30), s32(a + 0x34), u8(a + 2)))
end)
bp25[3] = arm(0x8004cea4, 'hitout', function()
    if cur == nil then return end
    local a = cur
    log(string.format('HITOUT hp=%d op=%d vst=%d vel=%d,%d,%d',
        u16(a + 0x1a), u8(a + 0xe), u8(a + 0xd), s16(a + 0x50), s16(a + 0x52),
        s16(a + 0x54)))
end)
bp25[4] = arm(0x8002a310, 'exp', function()
    local g = regs()
    if not g then return end
    log(string.format('EXP vb=%d a0=%d', s32(VBLANKS), reg(g, 'a0')))
end)
log('=== bp25 recording; swing, hit, kill ===')

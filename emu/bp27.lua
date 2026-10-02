-- A door that lifts, frame by frame.
--
--   ./emu/run.sh debug bp27.lua
--
-- Level 0 has five, and each looks like any other piece of wall: slots 20,
-- 51, 74, 86 and 123, in cells (10,4) (2,56) (18,2) (23,2) and (28,4) -- the
-- door stands on the edge of its cell and the one behind it. Face one, press
-- USE, walk through while it stands open, and once stand in the doorway so it
-- has to wait before it drops.
--
-- Six breakpoints. Three at the heads of object_interpreter's arms for opcodes 3,
-- 4 and 5 (0x800470c4, 0x80047290, 0x80047444), which run once a frame for
-- every such door, shut or not. There $s2 is the record plus 8. A line is
-- written while the door's state is not 0, and once more when it gets back to
-- 0, so a door standing shut costs nothing.
--
-- Each line: the frame (vblank_count, 0x801c12e8), the slot and opcode, the
-- state (+8), the counter (+0xa), the scale (+0x2c), the player's position,
-- and for the door's own cell and the one behind it -- (0, -1) turned by the
-- yaw, a quarter turn at a time -- layer 1's tile (+5) and shape (+8), which
-- the arm's two stamp tables write. tools/doors.py lift_check reads it.
--
-- Never `return false` from the callback: PCSX-Redux reads it as "delete this
-- breakpoint", and the silence afterwards would mean nothing.

local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local out = io.open(OUT .. 'lua_bp27.log', 'a')
local lines = 0
local function log(s)
    if lines > 50000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp27 (lift doors) armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

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

local OBJECT_TABLE, STRIDE = 0x80191a5c, 0x44
local LEVEL_GRID = 0x801d4464
local VBLANKS = 0x801c12e8
local PLAYER = 0x801b25f0
local BEHIND = { [0] = {0, -1}, [1] = {1, 0}, [2] = {0, 1}, [3] = {-1, 0} }

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

local last = {}

local function cell(cx, cz)
    if cx < 0 or cz < 0 or cx > 79 or cz > 79 then return '-1,-1' end
    local c = LEVEL_GRID + cz * 800 + cx * 10
    return string.format('%d,%d', u8(c + 5), u8(c + 8))
end

local function arm(op)
    return function()
        local g = regs()
        if not g then return end
        local rec = (tonumber(g.s2) % 0x100000000) - 8
        local slot = math.floor((rec - OBJECT_TABLE) / STRIDE)
        local st = u16(rec + 8)
        if st == 0 and (last[slot] or 0) == 0 then return end
        last[slot] = st
        local x, z = s32(rec + 0x14), s32(rec + 0x1c)
        local cx, cz = math.floor(x / 2048), math.floor(z / 2048)
        local b = BEHIND[math.floor((u16(rec + 0x26) % 4096) / 1024)]
        log(string.format(
            'vb=%d slot=%d op=%d st=%d ctr=%d scale=%d pos=%d %d %d cells=%s %s',
            s32(VBLANKS), slot, op, st, u16(rec + 0xa), u16(rec + 0x2c),
            s32(PLAYER), s32(PLAYER + 4), s32(PLAYER + 8),
            cell(cx, cz), cell(cx + b[1], cz + b[2])))
    end
end

-- And the doorway test's answer, in state 0x14: a breakpoint on the branch
-- right after each arm's collide_query returns (0x800471f4, 0x800473a8,
-- 0x8004755c), where $v0 is the mask -- 0x80 the player, 0x10 a creature --
-- and 0x801e648c the creature actor_in_range found, -1 for none. For that
-- creature: its slot, model (+1), state (+9), position (+0x2c), radius (+0x1c),
-- height (+0x1e) and flags (+0x28), so tools/doors.py can ask in_range itself.
local ACTORS, ASTRIDE = 0x80185da8, 0x88
local COLLIDE_ACTOR = 0x801e648c

local function query(op)
    return function()
        local g = regs()
        if not g then return end
        local rec = (tonumber(g.s2) % 0x100000000) - 8
        local slot = math.floor((rec - OBJECT_TABLE) / STRIDE)
        local mask = tonumber(g.v0) % 0x100000000
        local k = s32(COLLIDE_ACTOR)
        local who = 'actor=-1'
        if k >= 0 and k < 200 then
            local a = ACTORS + k * ASTRIDE
            who = string.format('actor=%d model=%d st=%d at=%d %d %d r=%d h=%d flags=%d',
                k, u8(a + 1), u8(a + 9), s32(a + 0x2c), s32(a + 0x30), s32(a + 0x34),
                u16(a + 0x1c), u16(a + 0x1e), s32(a + 0x28))
        end
        log(string.format('Q vb=%d slot=%d op=%d mask=%d %s', s32(VBLANKS), slot, op,
            mask, who))
    end
end

bp27 = {}
for i, a in ipairs({ {0x800470c4, 3}, {0x80047290, 4}, {0x80047444, 5} }) do
    local ok, bp = pcall(PCSX.addBreakpoint, a[1], 'Exec', 4, 'lift' .. a[2], arm(a[2]))
    log(string.format('arm %08x lift %d -> %s', a[1], a[2], tostring(ok)))
    if ok then bp27[i] = bp end
end
for i, a in ipairs({ {0x800471f4, 3}, {0x800473a8, 4}, {0x8004755c, 5} }) do
    local ok, bp = pcall(PCSX.addBreakpoint, a[1], 'Exec', 4, 'liftq' .. a[2], query(a[2]))
    log(string.format('query %08x lift %d -> %s', a[1], a[2], tostring(ok)))
    if ok then bp27[3 + i] = bp end
end
log('=== bp27 recording; open a lift door with USE, walk through, let it drop ===')

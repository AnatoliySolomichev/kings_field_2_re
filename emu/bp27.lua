-- A door that lifts, frame by frame -- and level 4's gates and pedestals.
--
--   ./emu/run.sh debug bp27.lua
--
-- On level 4: gate 96 in cell (38,23) opens to USE; the others open once a
-- key stands on their pedestal (Silviera's key on the pedestal in cell
-- (33,23), slot 108, opens gate 91). The G, GQ and P lines below are theirs.
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
-- 0x8004755c), where $v0 is the mask -- 0x80 the player, 0x10 a creature.
-- 0x801e648c would be the creature, but collide_query writes -1 over it on its
-- way out (0x800340a8), so the A lines after each Q line list every awake
-- creature within 0x2000 of the door instead -- its slot, model (+1),
-- position (+0x2c), radius (+0x1c), height (+0x1e) and flags (+0x28) -- and
-- tools/doors.py asks actor_in_range's question of each.
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
        -- collide_query writes -1 over the creature actor_in_range found
        -- (0x800340a8) before it returns, so name the candidates instead: every
        -- awake creature within 0x2000 of the door, as actor_in_range reads it
        local dx0, dz0 = s32(rec + 0x14), s32(rec + 0x1c)
        for k = 0, 199 do
            local a = ACTORS + k * ASTRIDE
            if u8(a + 9) == 1 then
                local ax, az = s32(a + 0x2c), s32(a + 0x34)
                if math.abs(ax - dx0) < 0x2000 and math.abs(az - dz0) < 0x2000 then
                    log(string.format('A vb=%d slot=%d actor=%d model=%d at=%d %d %d r=%d h=%d flags=%d',
                        s32(VBLANKS), slot, k, u8(a + 1), ax, s32(a + 0x30), az,
                        u16(a + 0x1c), u16(a + 0x1e), s32(a + 0x28)))
                end
            end
        end
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

-- The gates, opcode 2 (0x800475f8): a G line for each gate not at rest, as
-- for the lifts, with its lock (+0x38) and the doorway's cells -- layer 1's
-- shape (+8), plus 1000 where +9 carries 0x40, the fence -- over the
-- rectangle stamp_rect writes: (+0x39, +0x3a), the type's +0xd by +0xe,
-- across and along swapped for an odd quarter turn. And a GQ line with the
-- doorway test's mask, after the gate's collide_query (0x800477a0).
local TYPES = 0x8018fb3c
local LEVEL = 0x8018fad9           -- current_level_block's second byte: the level

local function doorway(rec)
    local row = TYPES + u16(rec + 6) * 24
    local w, h = u8(row + 0xd), u8(row + 0xe)
    local rot = (-math.floor(s16(rec + 0x26) / 1024)) % 4
    local nx, nz = w, h
    if rot % 2 == 1 then nx, nz = h, w end
    local dx, dz = u8(rec + 0x39), u8(rec + 0x3a)
    local cs = {}
    for r = 0, nz - 1 do
        for c = 0, nx - 1 do
            local cx, cz = dx + c, dz + r
            if cx >= 0 and cz >= 0 and cx < 80 and cz < 80 then
                local a = LEVEL_GRID + cz * 800 + cx * 10
                local fence = math.floor(u8(a + 9) / 0x40) % 2
                cs[#cs + 1] = tostring(u8(a + 8) + 1000 * fence)
            end
        end
    end
    return table.concat(cs, ',')
end

local function gate()
    local g = regs()
    if not g then return end
    local rec = (tonumber(g.s2) % 0x100000000) - 8
    local slot = math.floor((rec - OBJECT_TABLE) / STRIDE)
    local st = u16(rec + 8)
    if st == 0 and (last[slot] or 0) == 0 then return end
    last[slot] = st
    log(string.format('G vb=%d lv=%d slot=%d st=%d ctr=%d lock=%d pos=%d %d %d cells=%s',
        s32(VBLANKS), u8(LEVEL), slot, st, u16(rec + 0xa), u8(rec + 0x38),
        s32(PLAYER), s32(PLAYER + 4), s32(PLAYER + 8), doorway(rec)))
end

local function gate_query()
    local g = regs()
    if not g then return end
    local rec = (tonumber(g.s2) % 0x100000000) - 8
    local slot = math.floor((rec - OBJECT_TABLE) / STRIDE)
    log(string.format('GQ vb=%d slot=%d mask=%d', s32(VBLANKS), slot,
        tonumber(g.v0) % 0x100000000))
end

-- The pedestals, opcode 0x18 (0x8004aeb8): a P line whenever one changes --
-- its state (+8), lock (+0x38), ring index (+0x39), object_use_state's frame
-- count (+0x40), the key in slot 380 + the ring index -- its opcode (+4),
-- type (+6), lock (+0x38) and position (+0x14) -- and the gate it serves
-- (+0x3b) with that gate's lock.
local seen = {}

local function pedestal()
    local g = regs()
    if not g then return end
    local rec = (tonumber(g.s2) % 0x100000000) - 8
    local slot = math.floor((rec - OBJECT_TABLE) / STRIDE)
    local ring = u8(rec + 0x39)
    local key = OBJECT_TABLE + (380 + ring) * STRIDE
    local gs = u8(rec + 0x3b)
    local gr = OBJECT_TABLE + gs * STRIDE
    local s = string.format('st=%d lock=%d ring=%d n=%d key=%d,%d,%d,%d,%d,%d gate=%d,%d',
        u16(rec + 8), u8(rec + 0x38), ring, u8(rec + 0x40),
        u8(key + 4), u16(key + 6), u8(key + 0x38),
        s32(key + 0x14), s32(key + 0x18), s32(key + 0x1c), gs, u8(gr + 0x38))
    if seen[slot] == s then return end
    seen[slot] = s
    log(string.format('P vb=%d lv=%d slot=%d %s', s32(VBLANKS), u8(LEVEL), slot, s))
end

for i, a in ipairs({ {0x800475f8, 'gate', gate}, {0x800477a0, 'gateq', gate_query},
                     {0x8004aeb8, 'pedestal', pedestal} }) do
    local ok, bp = pcall(PCSX.addBreakpoint, a[1], 'Exec', 4, a[2], a[3])
    log(string.format('%s %08x -> %s', a[2], a[1], tostring(ok)))
    if ok then bp27[6 + i] = bp end
end
log('=== bp27 recording; open a lift door or a gate with USE, walk through, let it drop ===')

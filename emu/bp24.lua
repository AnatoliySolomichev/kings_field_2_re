-- A swinging door, frame by frame.
--
--   ./emu/run.sh debug bp24.lua
--
-- Then open a door that swings -- level 0 has nine, one of them at cell (41,10),
-- which the snapshots door1 and door2 caught closed and open -- walk through,
-- and let it close behind you. Once standing in the doorway so it has to wait,
-- once standing clear.
--
-- One breakpoint, at the head of object_interpreter's arm for opcode 1
-- (0x8004814c), which runs once a frame for every door whose state is not 0.
-- There $s2 is the record plus 8 -- the arm reads the state at 0($s2), the
-- flags at -5($s2) and the position at 0xc($s2) -- so the record is $s2 - 8.
--
-- Each line: the frame (the game's own vblank_count, 0x801c12e8, so gaps show),
-- the slot, the state (+8), the counter (+0x40), the yaw now and at load
-- (+0x26, +0x42), the side the player was on (+0xe), the player's position,
-- and the collision shape of the doorway's two cells -- layer 1's +3, cell
-- byte 8 -- at the destination the door stamps (+0x39, +0x3a), which is what
-- changes at counter 0x18 and 0x12c. godot/doors.gd is the model it checks.
--
-- Never `return false` from the callback: PCSX-Redux reads it as "delete this
-- breakpoint", and the silence afterwards would mean nothing.

local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local out = io.open(OUT .. 'lua_bp24.log', 'a')
local lines = 0
local function log(s)
    if lines > 50000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp24 (doors) armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

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

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

bp24 = {}
local ok, bp = pcall(PCSX.addBreakpoint, 0x8004814c, 'Exec', 4, 'door', function()
    local g = regs()
    if not g then return end
    local rec = (tonumber(g.s2) % 0x100000000) - 8
    local slot = math.floor((rec - OBJECT_TABLE) / STRIDE)
    local dx, dz = u8(rec + 0x39), u8(rec + 0x3a)
    local shape = function(cx, cz)
        if cx > 79 or cz > 79 then return -1 end
        return u8(LEVEL_GRID + cz * 800 + cx * 10 + 8)
    end
    log(string.format(
        'vb=%d slot=%d st=%d ctr=%d yaw=%d yaw0=%d side=%d pos=%d %d %d shapes=%d,%d',
        s32(VBLANKS), slot, u16(rec + 8), u16(rec + 0x40), s16(rec + 0x26),
        s16(rec + 0x42), s16(rec + 0x0e), s32(PLAYER), s32(PLAYER + 4),
        s32(PLAYER + 8), shape(dx, dz), shape(dx, dz + 1)))
end)
log('arm 8004814c door -> ' .. tostring(ok))
if ok then bp24[1] = bp end
log('=== bp24 recording; open a swinging door, walk through, let it close ===')

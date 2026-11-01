-- What the flight recorder (bp29.lua) and its replay (replay.lua) share: one
-- record a game frame, read off RAM the same way by both, so that the two can
-- be set side by side byte for byte.
--
-- A game frame is one pass of game_main's loop: frame_limit (0x80019614) comes
-- at the end of every pass. The buttons are taken at PadRead's own return
-- (0x800785d4, $v0 the word), because every reader of the pad in GAME.EXE goes
-- through it, the menus too, and they run many calls to a frame or none: the
-- stream is one word a call, not one a frame.
--
-- The addresses mean this only while GAME.EXE is in memory, and three of the
-- disc's four programs load at 0x80011000, so both breakpoints ask `in_game`.
--
-- `seed` is where OpenBIOS keeps rand's state. It is the emulator's BIOS, not
-- Sony's, so the address is the BIOS's own and belongs to this setup: A0:2F is
-- 0xbfc06228, lui/lw of 0x85ec. Stepping the generator from that word in one
-- RAM snapshot reaches the word in the next in 13 of 16 pairs of snapshots
-- (out/snap); the other three are not one session.
local ffi = require 'ffi'

pcall(ffi.cdef, [[
typedef struct {
    uint32_t frame, calls, vblank, seed;
    int32_t x, y, z;
    uint16_t facing, hp;
    uint8_t level, pstate, spare0, spare1;
    uint32_t objects, actors, effects, player, state, grid;
} kf_frame;
]])

local M = {}
M.PAD_RET, M.FRAME = 0x800785d4, 0x80019614
M.REGIONS = {
    {'objects', 0x80191a5c, 396 * 68}, {'actors', 0x80185da8, 200 * 0x88},
    {'effects', 0x801b80ec, 128 * 0x4c}, {'player', 0x801b24e4, 0x67 * 4},
    {'state', 0x801ba984, 0x1451 * 4}, {'grid', 0x801d4464, 64000},
}
M.FIELDS = {'frame', 'calls', 'vblank', 'seed', 'x', 'y', 'z', 'facing', 'hp', 'level', 'pstate',
    'objects', 'actors', 'effects', 'player', 'state', 'grid'}

local mem = PCSX.getMemPtr()
local words = ffi.cast('uint32_t*', mem)
local bytes = ffi.cast('uint8_t*', mem)
local halves = ffi.cast('uint16_t*', mem)
M.mem = mem

local function at(a) return bit.band(a, 0x1fffff) end
local function w32(a) return words[bit.rshift(at(a), 2)] end
M.w32 = w32
function M.u8(a) return bytes[at(a)] end
function M.u16(a) return halves[bit.rshift(at(a), 1)] end

-- frame_limit's first four words and PadRead's last: GAME.EXE, not another
-- program at the same addresses.
function M.in_game()
    return w32(0x80019614) == 0x27bdffe8 and w32(0x80019618) == 0x3c03801c
        and w32(0x8001961c) == 0x246312ec and w32(0x800785d4) == 0x03e00008
end

local function hash(a, n)
    local h = 5381
    local lo = bit.rshift(at(a), 2)
    for i = lo, lo + n / 4 - 1 do
        h = bit.bxor(bit.tobit(h * 33), words[i])
    end
    return h
end

function M.fill(r, frame, calls)
    r.frame, r.calls = frame, calls
    r.vblank, r.seed = w32(0x801c12e8), w32(0x000085ec)
    r.x, r.y, r.z = w32(0x801b25f0), w32(0x801b25f4), w32(0x801b25f8)
    r.facing, r.hp = M.u16(0x801b2612), M.u16(0x801b24fc)
    r.level, r.pstate = M.u8(0x8018fad9), M.u8(0x801b25e5)
    r.objects = hash(0x80191a5c, 396 * 68)
    r.actors = hash(0x80185da8, 200 * 0x88)
    r.effects = hash(0x801b80ec, 128 * 0x4c)
    r.player = hash(0x801b24e4, 0x67 * 4)
    r.state = hash(0x801ba984, 0x1451 * 4)
    r.grid = hash(0x801d4464, 64000)
end

-- What happened, off the tables a frame apart: a line for each change worth
-- reading, which a replay writes to events.txt. A creature's state is its +9 (0
-- asleep, 1 awake, 3 gone), its HP +0x1a; waking and sleeping, which the creatures
-- do all day as the player walks, are left out. An object is said when it is
-- made or freed (+6 0xff) and when a door, a chest, a lever or the like changes
-- state or lock; the pack is the 150 bytes at 0x800c85e8 and the story's flags the
-- 256 at 0x801ba988. Traps and things that cycle on their own are left out, and
-- so are the tables while level_change_busy is set, when the next level's come
-- in over them and nothing has happened to anybody.
local SAYS = {[0x53] = true, [0x54] = true, [0x58] = true, [0x59] = true, [0x5a] = true, [0x5f] = true}
local shadow

local function ev_read(a, n)
    local t = {}
    for i = 0, n - 1 do t[i] = bytes[at(a) + i] end
    return t
end

local function ev_objects()
    local t = {}
    for k = 0, 395 do
        local r = 0x80191a5c + 68 * k
        t[k] = {typ = M.u16(r + 6), op = M.u8(r + 4), st = M.u16(r + 8), lock = M.u8(r + 0x38)}
    end
    return t
end

local function ev_actors()
    local t = {}
    for k = 0, 199 do
        local a = 0x80185da8 + 0x88 * k
        t[k] = {cat = M.u8(a), st = M.u8(a + 9), hp = M.u16(a + 0x1a), kind = M.u8(a + 2),
            cx = bit.arshift(tonumber(ffi.cast('int32_t', w32(a + 0x2c))), 11),
            cz = bit.arshift(tonumber(ffi.cast('int32_t', w32(a + 0x34))), 11)}
    end
    return t
end

local function ev_now()
    return {level = M.u8(0x8018fad9), objects = ev_objects(), actors = ev_actors(),
        items = ev_read(0x800c85e8, 150), flags = ev_read(0x801ba988, 256)}
end

function M.events(frame, out)
    local now = ev_now()
    local old = shadow
    shadow = now
    if not old then return end
    local function say(...) out:write(string.format('%d ', frame), string.format(...), '\n') end
    if now.level ~= old.level then say('level %d', now.level) end
    local settled = M.u16(0x8018fad4) == 0
    for k = 0, settled and 199 or -1 do
        local a, b = old.actors[k], now.actors[k]
        if a.st ~= b.st and (a.st > 1 or b.st > 1) then
            say('creature %d kind %d cell (%d, %d) state %d -> %d hp %d', k, b.kind, b.cx, b.cz, a.st, b.st, b.hp)
        elseif a.hp > 0 and b.hp == 0 then
            say('creature %d kind %d cell (%d, %d) hp 0', k, b.kind, b.cx, b.cz)
        end
    end
    for k = 0, settled and 395 or -1 do
        local a, b = old.objects[k], now.objects[k]
        if a.typ ~= b.typ then
            if b.typ == 0xff then say('object %d type %d gone', k, a.typ)
            elseif a.typ == 0xff then say('object %d type %d made', k, b.typ) end
        elseif (b.op <= 7 or b.op == 0x1b or SAYS[b.op]) and (a.st ~= b.st or a.lock ~= b.lock) then
            say('object %d type %d opcode 0x%02x state %d -> %d lock %d -> %d', k, b.typ, b.op, a.st, b.st, a.lock, b.lock)
        end
    end
    for i = 0, 149 do
        if old.items[i] ~= now.items[i] then say('pack %d: %d -> %d', i, old.items[i], now.items[i]) end
    end
    for i = 0, 255 do
        if old.flags[i] ~= now.flags[i] then say('flag %d: %d -> %d', i, old.flags[i], now.flags[i]) end
    end
end

-- The tables whole, for a replay asked to dump them: the regions in order.
function M.tables(out)
    for _, g in ipairs(M.REGIONS) do
        out:write(ffi.string(bytes + at(g[2]), g[3]))
    end
end

return M

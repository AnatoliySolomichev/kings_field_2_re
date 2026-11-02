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

-- A frame for the port to show (godot/ghost.gd), one line in live.txt: bp16's
-- seventeen numbers and its w=, d= and a=, and two more. o= is every object in
-- use: slot, opcode, state, clock, +0, +1, type, scale, x, y, z, yaw, and the X
-- and Z angles (+0x24, +0x28), which a thing taken spins by. e= is every live
-- effect, slot:bytes in hex, the 76 of them as effects.gd keeps them.
-- Written beside and renamed, because Godot reads on its own clock.
local function s16(a)
    local v = M.u16(a)
    return v >= 0x8000 and v - 0x10000 or v
end

local function s32(a) return tonumber(ffi.cast('int32_t', w32(a))) end

local function live_line(frame)
    local doors, objs, acts, fx = {}, {}, {}, {}
    for k = 0, 395 do
        local r = 0x80191a5c + 68 * k
        local op, typ = M.u8(r + 4), M.u16(r + 6)
        if op == 1 then
            doors[#doors + 1] = string.format('%d,1,%d,%d,%d', k, M.u16(r + 8), M.u16(r + 0x40), s16(r + 0x26))
        elseif op >= 3 and op <= 5 then
            doors[#doors + 1] = string.format('%d,%d,%d,%d,%d', k, op, M.u16(r + 8), M.u16(r + 0xa), M.u16(r + 0x2c))
        elseif op == 2 then
            doors[#doors + 1] = string.format('%d,2,%d,%d,%d', k, M.u16(r + 8), M.u16(r + 0xa), M.u8(r + 0x38))
        end
        if typ ~= 0xff then
            objs[#objs + 1] = string.format('%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d', k, op,
                M.u16(r + 8), M.u16(r + 0xa), M.u8(r), M.u8(r + 1), typ, M.u16(r + 0x2c), s32(r + 0x14),
                s32(r + 0x18), s32(r + 0x1c), M.u16(r + 0x26), M.u16(r + 0x24), M.u16(r + 0x28))
        end
    end
    for k = 0, 199 do
        local a = 0x80185da8 + k * 0x88
        if M.u8(a) ~= 0xff then
            acts[#acts + 1] = string.format('%d,%d,%d,%d,%d,%d,%d,%d,%d', k, M.u8(a + 9), s32(a + 0x2c),
                s32(a + 0x30), s32(a + 0x34), s16(a + 0x42), M.u8(a + 0xc), M.u16(a + 0x18), M.u16(a + 0x1a))
        end
    end
    for k = 0, 127 do
        local s = 0x801b80ec + k * 0x4c
        if M.u8(s) ~= 0xff then
            local h = {}
            for i = 0, 0x4b do h[i + 1] = string.format('%02x', M.u8(s + i)) end
            fx[#fx + 1] = k .. ':' .. table.concat(h)
        end
    end
    return string.format('%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d w=%d,%d,%d d=%s a=%s o=%s e=%s\n',
        frame, s32(0x801b25f0), s32(0x801b25f4), s32(0x801b25f8), s16(0x801b2612), M.u8(0x801b25e8),
        s16(0x801b2656), s16(0x801b2648), s16(0x801b2646), M.u16(0x801b265c), M.u8(0x8018fad9),
        s16(0x801b2610), s32(0x801c12e8), M.u16(0x801b24fc), M.u16(0x801b2500), M.u16(0x801b2502),
        M.u16(0x801b2506), s16(0x801b25a4), M.u8(0x801b25ae), M.u8(0x801b25af),
        table.concat(doors, ';'), table.concat(acts, ';'), table.concat(objs, ';'), table.concat(fx, ';'))
end

function M.live(frame, path)
    local f = io.open(path .. '.tmp', 'w')
    if not f then return end
    f:write(live_line(frame))
    f:close()
    os.rename(path .. '.tmp', path)
end

-- The menus, for the port to draw beside the emulator (godot/menu.gd follow).
-- A menu runs frames of its own -- frame_begin, its drawing, frame_end -- and
-- none of game_main's, so live.txt stands still while one is up. Each of the
-- drawing routines the port has a copy of is caught as it is entered, with its
-- arguments and what it reads through them, and each menu frame is one line in
-- `path`: the game frame it came after, the menu frame's count, K= the colours
-- (gp+0x58 the boxes, +0x5c the text, +0x68 the shadow, +0x4c and +0x50 the
-- pulses, +0x40 and +0x44 the confirm and cancel buttons, 0x801b25e4 the
-- panel's switch, 0x801b25e1 the brightness), then the calls in the order made,
-- which is the order the ordering table files them in:
--
--   S=  ui_status_page: what it reads -- experience, level, HP and its maximum,
--       MP and its, the stat, 0x801b2530, the five skills, paralysis, curse,
--       slowing, poison, dark, gold
--   P=  sub_800252f4 (page, lines, chosen, legend)
--   L=  ui_panel (list, mode): mode, the record's title (x, y, glyphs in hex,
--       none when x is 0), x, y, count, rows, first, selection, its row, the
--       names' length, the quantity (gp+0x48) and the gold; then |row/name/
--       second name/count/cost for each row shown -- names length apart, second
--       names 24, counts a byte, costs a word
--   A=  sub_80025b24 (one, two, chosen): chosen|x/y/glyphs|x/y/glyphs
--   G=  ui_gold, called by itself (menu_inn) and not from ui_panel's own
--   O=  options_screen (action, movement, row)
--   D=  ui_display_values: its five bytes
--   V=  sub_80024a78: its three bytes
--   B=  sub_8001eb3c (title, lines, n, x, y, w, h, legend): title, x, y, w, h,
--       legend, then |x/y/glyphs a line, 28 bytes apart
--   R=  ui_ratings_page: the eight offense ratings, the eight defense ones and
--       the resistance (0x801b2538, 0x801b254a, 0x801b255a)
--
-- What the port has no copy of -- the thing's model turning, the guide, the
-- maps, a conversation's pages -- is not sent, and is not drawn there.
local GP = 0x8009c214
local function hex(a, n)
    local t = {}
    for i = 0, n - 1 do t[i + 1] = string.format('%02x', M.u8(a + i)) end
    return table.concat(t)
end
local function glyphs(a)
    local n = 0
    while n < 24 and M.u8(a + n) ~= 0xff do n = n + 1 end
    return hex(a, math.min(n + 1, 24))
end
local function label(a) return string.format('%d/%d/%s', s16(a), s16(a + 2), glyphs(a + 4)) end

local menu_calls, menu_frames = {}, 0
local MENU_DRAW = {
    [0x800227ec] = function()
        local w = {}
        for i = 0, 4 do w[i + 1] = M.u16(0x801b2526 + 2 * i) end
        return string.format('S=%d,%d,%d,%d,%d,%d,%d,%d,%s,%d,%d,%d,%d,%d,%d', w32(0x801b24e4),
            M.u8(0x801b24f0), M.u16(0x801b24fc), M.u16(0x801b24fa), M.u16(0x801b2500),
            M.u16(0x801b24fe), M.u16(0x801b2524), M.u16(0x801b2530), table.concat(w, ','),
            s16(0x801b2568), s16(0x801b255e), s16(0x801b2566), s16(0x801b255c), s16(0x801b2562),
            w32(0x801b2534))
    end,
    [0x800252f4] = function(r)
        return string.format('P=%d,%d,%d,%d', r.a0, r.a1, r.a2, r.a3)
    end,
    [0x80025468] = function(r)
        local s = r.a0
        local tx = s16(s)
        local first, rows, count, len = M.u8(s + 0x20), M.u8(s + 0x1f), M.u8(s + 0x1e), M.u8(s + 0x23)
        local names, names2, counts, costs = w32(s + 0x24), w32(s + 0x28), w32(s + 0x2c), w32(s + 0x30)
        local out = {string.format('L=%d,%d,%d,%s,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d', r.a1, tx, s16(s + 2),
            tx ~= 0 and glyphs(s + 4) or '', M.u8(s + 0x1c), M.u8(s + 0x1d), count, rows, first,
            M.u8(s + 0x21), M.u8(s + 0x22), len, w32(GP + 0x48), w32(0x801b2534))}
        for k = first, math.min(first + rows, count) - 1 do
            out[#out + 1] = string.format('%d/%s/%s/%d/%d', k, hex(names + k * len, len),
                bit.band(r.a1, 0xfff) == 3 and hex(names2 + 24 * k, 24) or '', M.u8(counts + k),
                s32(costs + 4 * k))
        end
        return table.concat(out, '|')
    end,
    [0x80025b24] = function(r)
        return string.format('A=%d|%s|%s', r.a2, label(r.a0), label(r.a1))
    end,
    [0x80025e80] = function(r)
        -- ui_panel's and ui_quantity's own calls are drawn by the port's panel
        if r.ra >= 0x80025468 and r.ra < 0x80025b24 or r.ra >= 0x80025db8 and r.ra < 0x80025e80 then
            return nil
        end
        return string.format('G=%d', w32(0x801b2534))
    end,
    [0x80023fd4] = function(r) return string.format('O=%d,%d,%d', r.a0, r.a1, r.a2) end,
    [0x800246bc] = function(r) return 'D=' .. hex(r.a0, 5) end,
    [0x80024a78] = function(r) return 'V=' .. hex(r.a0, 3) end,
    [0x8001eb3c] = function(r)
        local out = {string.format('B=%d,%d,%d,%d,%d,%d', r.a0, r.a3, s32(r.sp + 0x10),
            s32(r.sp + 0x14), s32(r.sp + 0x18), s32(r.sp + 0x1c))}
        for i = 0, math.min(r.a2, 8) - 1 do out[#out + 1] = label(r.a1 + 28 * i) end
        return table.concat(out, '|')
    end,
    [0x80023300] = function()
        local v = {}
        for i = 0, 7 do v[i + 1] = M.u16(0x801b2538 + 2 * i) end
        for i = 0, 8 do v[i + 9] = M.u16(0x801b254a + 2 * i) end
        return 'R=' .. table.concat(v, ',')
    end,
}

-- Arms the breakpoints; `frame_of` answers the game frame the session is on.
function M.menu_arm(path, frame_of)
    kf_menu_bps = {}
    local function bp(a, fn) kf_menu_bps[#kf_menu_bps + 1] = PCSX.addBreakpoint(a, 'Exec', 4, 'kf menu', fn) end
    bp(0x80026fe4, function()
        if M.in_game() then menu_calls = {} end
    end)
    for a, fn in pairs(MENU_DRAW) do
        bp(a, function()
            if not M.in_game() then return end
            local g = PCSX.getRegisters().GPR.n
            local t = fn({a0 = g.a0, a1 = g.a1, a2 = g.a2, a3 = g.a3, sp = g.sp, ra = g.ra})
            if t then menu_calls[#menu_calls + 1] = t end
        end)
    end
    bp(0x800270f8, function()
        if not M.in_game() then return end
        menu_frames = menu_frames + 1
        local f = io.open(path .. '.tmp', 'w')
        if not f then return end
        f:write(string.format('%d %d K=%d,%d,%d,%d,%d,%d,%d,%d,%d', frame_of(), menu_frames,
            bit.band(w32(GP + 0x58), 0xff), bit.band(w32(GP + 0x5c), 0xff),
            bit.band(w32(GP + 0x68), 0xff), w32(GP + 0x4c), w32(GP + 0x50), w32(GP + 0x40),
            w32(GP + 0x44), M.u8(0x801b25e4), M.u8(0x801b25e1)))
        for _, t in ipairs(menu_calls) do f:write(' ', t) end
        f:write('\n')
        f:close()
        os.rename(path .. '.tmp', path)
    end)
end

-- The tables whole, for a replay asked to dump them: the regions in order.
function M.tables(out)
    for _, g in ipairs(M.REGIONS) do
        out:write(ffi.string(bytes + at(g[2]), g[3]))
    end
end

return M

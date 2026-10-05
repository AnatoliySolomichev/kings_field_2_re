-- One line per frame: what you pressed, and everything the game did with it.
--
--   ./emu/run.sh debug bp16.lua
--
-- This is the flight recorder the side-by-side comparison is built on. Play
-- normally; every frame of ordinary movement writes a line carrying the input
-- and the whole player state, so `tools/replay.py` can run the model over the
-- same input and say -- with a number -- where the two part company. It also
-- overwrites `out/godot/live.txt` every frame, which is what the Godot build
-- reads to stand a marker where the real player is.
--
-- One breakpoint, at the head of the movement chain the controller runs each
-- frame: 0x8002fe1c (turning), then 0x8002f5c0, then 0x8002f9bc (which drives
-- the horizontal), then player_vertical. Logging at the first of them means
-- consecutive lines are consecutive frames, so line N is the state going in and
-- line N+1 is the state coming out. No pairing, no exit point to get wrong.
--
-- The fields, and how each was established:
--
--   btn   0x801b265c  the decoded button word; one store in the executable, at
--                     0x8002b754. 0x801b265e is the previous frame's, which the
--                     game ands against to find a fresh press.
--   ang   0x801b2612  facing, 0..0xfff. player_horizontal is called twice, from
--                     0x8002fda0 and 0x8002fdb4 -- once at ang + 0x400 with the
--                     forward distance and once at ang with the strafe, so
--                     forward runs a quarter turn off the facing.
--   pit   0x801b2610  where the player is looking up or down, and it was found
--                     rather than reasoned about. The first guess was
--                     0x801b2614, on the grounds that the controller writes it
--                     beside the facing at all five sites -- and it reads zero
--                     for a whole session. So nine candidates went into the log
--                     and one recording of looking up and down named the
--                     answer: only 0x801b2610 moved, over 136 values, and read
--                     signed it runs -596 to +700, give or take sixty degrees.
--                     It rests near -190, the slight downward tilt the game
--                     starts at, so negative is down.
--   fwd   0x801b2648  forward speed, accelerated by max/4 a frame at 0x8002f9fc
--                     and decaying by max/8; the strafe at 0x801b2646 decays by
--                     max/4 instead, which is a different shift in the code.
--   max   0x801b2664  the ceiling on it. Written only at 0x80031188 and
--                     0x800313e4, which is where a stat could change how fast
--                     the character walks -- an open question in BACKLOG.md.
--   mag   0x801b264a  isqrt(forward^2 + strafe^2), formed at 0x8002fd80; this is
--                     the value player_vertical tests against 0xc9 when it
--                     launches you.
--   vst   0x801b25e8  player_vertical's state, vv 0x801b2656 its velocity.
--
-- The twelve halfwords from 0x801b2640 go out raw as well, which is how the
-- strafe speed was identified without needing another session.
--
-- `t` is wall clock, and it turned out to say less than hoped: the emulator runs
-- uncapped under the interpreter, so two sessions measured 26 and 34 frames a
-- second and neither bounds the console.
--
--   vb    0x801c12e8  vblank_count, the game's own clock: one per vertical blank,
--                     counted by vblank_tick. The difference between two lines is
--                     how many blanks that frame took, whatever speed the
--                     emulator runs at. frame_limit holds a frame to at least 4
--                     -- 15 a second -- and this says how often one takes more.
--
-- Never `return false` from the callback: PCSX-Redux reads it as "delete this
-- breakpoint", and then the silence afterwards means nothing.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp16.log'
-- The same state, one line, overwritten every frame, inside the Godot project so
-- the port can read it as res://live.txt. Written to a temporary name and
-- renamed, because Godot polls it on its own clock and would otherwise catch
-- half a line.
local LIVE = OUT .. 'godot/live.txt'
local LIVE_TMP = LIVE .. '.tmp'

local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 40000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp16 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

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

local PX, PY, PZ = 0x801b25f0, 0x801b25f4, 0x801b25f8
local BTN, BTNPREV = 0x801b265c, 0x801b265e
local PITCH, ANG = 0x801b2610, 0x801b2612
local STRAFE, FWD, MAG, MAX = 0x801b2646, 0x801b2648, 0x801b264a, 0x801b2664
local VSTATE, VVEL = 0x801b25e8, 0x801b2656
local PSTATE = 0x801b25e5
local VBLANKS = 0x801c12e8        -- vblank_count
local BLOCK = 0x801b2640          -- twelve halfwords, logged raw
local ACTORS = 0x80185da8         -- actor_table: 200 slots of 0x88
local NEAR = 0x5000               -- how far from the player an actor is logged: far
                                  -- enough that one at the edge has its neighbours too

-- The creatures the player can run into this frame: actor_spot_taken asks
-- every slot whose +9 is 1, and the player moves before actor_tick_driver in
-- game_main, so the positions here are the ones its collision sees. One
-- `k:x:y:z:radius:height:flags:b0e:lift` per awake actor within NEAR, for
-- tools/replay.py to put in the player's way -- and since 2026-09-28 eight
-- more, for tools/ai.py to step the creature itself: the phase +0xf, the
-- animation clock +0x18, the yaw +0x42, the velocity +0x50 and +0x54, the
-- running behaviour's address +0x60 (hex), and the approach and turn flags
-- +0x70 and +0x71. And since 2026-09-29 what tools/ai.py --locked had to
-- guess: the turn rate +0x58, the aim +0x64, the vertical state +0xd and
-- velocity +0x52, the whole halfwords +0x70 and +0x72, the HP +0x1a and the
-- animation +0xc.
local function awake()
    local px, pz = s32(PX), s32(PZ)
    local out = {}
    for k = 0, 199 do
        local a = ACTORS + k * 0x88
        if u8(a + 9) == 1 then
            local x, z = s32(a + 0x2c), s32(a + 0x34)
            if math.abs(x - px) < NEAR and math.abs(z - pz) < NEAR then
                out[#out + 1] = string.format(
                    '%d:%d:%d:%d:%d:%d:%x:%d:%d:%d:%d:%d:%d:%d:%x:%d:%d:%d:%d:%d:%d:%d:%d:%d:%d',
                    k, x, s32(a + 0x30), z, u16(a + 0x1c), u16(a + 0x1e),
                    s32(a + 0x28) % 0x100000000, u8(a + 0xe), s16(a + 0x26),
                    u8(a + 0xf), u16(a + 0x18), s16(a + 0x42), s16(a + 0x50),
                    s16(a + 0x54), s32(a + 0x60) % 0x100000000, u8(a + 0x70),
                    u8(a + 0x71), s16(a + 0x58), s16(a + 0x64), u8(a + 0xd),
                    s16(a + 0x52), s16(a + 0x70), s16(a + 0x72), u16(a + 0x1a),
                    u8(a + 0xc))
            end
        end
    end
    return table.concat(out, ',')
end

-- For the port to follow the game, not only the player: what else the frame
-- shows, after the seventeen numbers of live.txt, as three tokens --
--   w=clock,phase,weapon   the swing: 0x801b25a4 (s16, -1 at rest), 0x801b25ae,
--                          0x801b25af
--   d=slot,op,state,counter,third;...   every door of object_table: op 1's
--                          state +8, counter +0x40 and yaw +0x26 (bp24's), the
--                          lifts' (3, 4, 5) state +8, counter +0xa, scale +0x2c
--                          (bp27's)
--   a=k,b9,x,y,z,yaw,anim,clock,hp;...  every actor slot in use (+0 not 0xff):
--                          +9 (render_walk draws it while 1), +0x2c..+0x34,
--                          the yaw +0x42, the animation +0xc, its clock +0x18
--                          and the HP +0x1a
local OBJECTS = 0x80191a5c        -- object_table: 396 records of 0x44
local function swing()
    return string.format('w=%d,%d,%d', s16(0x801b25a4), u8(0x801b25ae), u8(0x801b25af))
end
local function doors()
    local out = {}
    for k = 0, 395 do
        local r = OBJECTS + k * 0x44
        local op = u8(r + 4)
        if op == 1 then
            out[#out + 1] = string.format('%d,1,%d,%d,%d', k, u16(r + 8), u16(r + 0x40),
                                          s16(r + 0x26))
        elseif op >= 3 and op <= 5 then
            out[#out + 1] = string.format('%d,%d,%d,%d,%d', k, op, u16(r + 8),
                                          u16(r + 0xa), u16(r + 0x2c))
        elseif op == 2 then
            -- a gate (level 4's walls): its state, counter and lock
            out[#out + 1] = string.format('%d,2,%d,%d,%d', k, u16(r + 8),
                                          u16(r + 0xa), u8(r + 0x38))
        end
    end
    return 'd=' .. table.concat(out, ';')
end
local function actors()
    local out = {}
    for k = 0, 199 do
        local a = ACTORS + k * 0x88
        if u8(a) ~= 0xff then
            out[#out + 1] = string.format('%d,%d,%d,%d,%d,%d,%d,%d,%d', k, u8(a + 9),
                s32(a + 0x2c), s32(a + 0x30), s32(a + 0x34), s16(a + 0x42),
                u8(a + 0xc), u16(a + 0x18), u16(a + 0x1a))
        end
    end
    return 'a=' .. table.concat(out, ';')
end

local clock = os and os.clock or function() return 0 end
local t0 = clock()
local frame = 0
bp16 = {}

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

-- The key bindings are fourteen masks, and the config menu rewrites them, so the
-- defaults in GAME.EXE are not necessarily what you are playing with. Dump the
-- live copy -- but on the first *frame*, not at load: this file runs at emulator
-- startup, before the game has loaded GAME.EXE at all, and reading it then gets
-- fourteen zeroes. That is exactly what the first recording got.
--
-- Named only where the code says what the mask is for: 0x8002f9bc reads +0 and
-- +2 to drive the forward speed and +0x14 and +0x10 to drive the strafe. The
-- rest are logged unnamed rather than guessed at.
local names = {'forward', 'back', 'b2', 'b3', 'b4', 'b5', 'b6', 'b7',
               'strafe_neg', 'b9', 'strafe_pos', 'b11', 'b12', 'b13'}
local binds_done = false

local function dump_binds()
    if binds_done then return end
    local binds = {}
    local any = false
    for i = 0, 13 do
        local v = u16(0x80081868 + i * 2)
        if v ~= 0 then any = true end
        binds[#binds + 1] = string.format('%s=%04x', names[i + 1], v)
    end
    if not any then return end          -- the game has not loaded yet
    binds_done = true
    log('binds ' .. table.concat(binds, ' '))
end

local function arm(addr, tag, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, tag, fn)
    log(string.format('arm %08x %-5s -> %s', addr, tag, tostring(ok)))
    if ok then bp16[#bp16 + 1] = bp end
end

arm(0x8002fe1c, 'frame', function()
    local g = regs()
    frame = frame + 1
    dump_binds()

    local live = io.open(LIVE_TMP, 'w')
    if live then
        -- 14-17: HP, MP and the weapon and magic meters, for the port's panel
        live:write(string.format('%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %s %s %s\n',
            frame, s32(PX), s32(PY), s32(PZ), s16(ANG), u8(VSTATE), s16(VVEL),
            s16(FWD), s16(STRAFE), u16(BTN), u8(0x8018fad9), s16(PITCH),
            s32(VBLANKS), u16(0x801b24fc), u16(0x801b2500), u16(0x801b2502),
            u16(0x801b2506), swing(), doors(), actors()))
        live:close()
        os.rename(LIVE_TMP, LIVE)
    end

    local raw = {}
    for i = 0, 11 do raw[#raw + 1] = string.format('%04x', u16(BLOCK + i * 2)) end
    log(string.format(
        'f=%6d t=%9.3f btn=%04x prev=%04x ang=%5d fwd=%6d mag=%6d max=%8d ' ..
        'pos=%9d %9d %9d vst=%3d vv=%6d pst=%3d lv=%2d ra=%08x blk=%s vb=%d act=%s ' ..
        'pv=%d,%d,%d hp=%d/%d',
        frame, clock() - t0, u16(BTN), u16(BTNPREV), s16(ANG),
        s16(FWD), s16(MAG), s32(MAX),
        s32(PX), s32(PY), s32(PZ), u8(VSTATE), s16(VVEL), u8(PSTATE),
        u8(0x8018fad9), g and tonumber(g.ra) or 0, table.concat(raw, ','),
        s32(VBLANKS), awake(),
        -- player_velocity, the knock-back player_move spends in state 0x10
        s16(0x801b266c), s16(0x801b266e), s16(0x801b2670),
        -- the HP and its maximum, which decide a knock-back's strength
        u16(0x801b24fc), u16(0x801b24fa)))
end)

log('=== bp16 recording; play normally ===')

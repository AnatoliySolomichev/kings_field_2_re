-- A conversation, opcode by opcode.
--
--   ./emu/run.sh debug bp21.lua
--
-- Then **talk to somebody**, and let the whole conversation run -- press the
-- use button through every line. Walk up to one of the three men by the house
-- on level 0 if you are starting fresh; `python3 tools/entities.py 0` lists
-- every entity on a level and `python3 tools/escript.py 0` prints their
-- scripts, so what this logs can be held against what the script says.
--
-- This script has been run and it broke the reading it was written to check:
-- the game fetched `04 05 06 07 08 09 f0 01` for level 0's entity 9 where
-- `tools/escript.py` had `02 00 ff`. Both copies had been decoding blocks
-- 1..15 of each entity record, which are not scripts. What it recorded is
-- kept in `tools/escript.py` as RECORDED and replayed by `escript.py check`.
--
-- What it logs:
--
--   FETCH  every opcode `script_interpreter` is about to run, at 0x8005c3f8 --
--          the top of its dispatch -- with the program counter out of the
--          state block's +0x10 and the retry flag at +0x13. That is the
--          instruction stream, and it is what the port has to reproduce.
--   ENTER  each call, with the actor record and the entity index.
--   TEXT   the TALK.T entry a line loads: `load_entry(7, base + byte)`, so the
--          base at the state's +0x0c and the byte together.
--   FLAG   every story flag the script writes (0xf7) or tests (0xf9), read out
--          of the operands rather than out of memory.
--   HOOK   the 0xf4 opcode calling into the level's own code -- six of these
--          exist in the whole game and none has ever been seen run.
--
-- Two other things worth catching while somebody is playing, both found by
-- reading and never checked:
--
--   SPELL  cast_spell (0x8002deec) with the spell and the MP before and after.
--   SKILL  skill_unlock (0x80029f1c) with the skill, which award_exp calls on
--          every level.
--
-- Never `return false` from a callback: PCSX-Redux reads it as "remove this
-- breakpoint", and the silence afterwards would mean nothing. The heartbeat
-- below is there so an empty log can be told from breakpoints that never
-- armed.

-- out/ beside emu/, wherever the project lives: from this file's own path when
-- dofile was given one, else from the working directory, which run.sh makes
-- emu/.
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local OUT = HERE .. '/../out/'
local LOG = OUT .. 'lua_bp21.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 40000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp21 (a conversation) armed; debug = '
    .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

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

local GPR = {'zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
             't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
             's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
             't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'}

local function cpu()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    local g = r.GPR
    if g and g.n then g = g.n end
    return g
end

local function reg(g, n)
    if n == 0 then return 0 end
    local v = g[GPR[n + 1]]
    if v == nil and n == 30 then v = g['s8'] end
    return tonumber(v) or 0
end

local ACTOR_TABLE = 0x80185DA8
local ACTOR_STRIDE = 0x88
local STORY_FLAGS = 0x801BA988
local PLAYER_MP = 0x801B2500          -- player.py: BASE + 0x20
local LEVEL_BYTE = 0x8018FAD9
local PLAYER_POS, PLAYER_Z = 0x801B25F0, 0x801B25F8

local function where()
    return string.format('lv=%d cell=(%d,%d)', u8(LEVEL_BYTE),
        math.floor(s32(PLAYER_POS) / 2048), math.floor(s32(PLAYER_Z) / 2048))
end

bp21 = {}
local counts = {}
local function bump(k) counts[k] = (counts[k] or 0) + 1 end

-- The `false` here is this helper's answer to "did it arm", not a callback's
-- return value. A callback in this file never returns anything.
local function arm(addr, tag, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, 'Exec', 4, tag, fn)
    if not ok then
        log(string.format('arm %08x %s -> FAILED', addr, tag))
        return false
    end
    bp21[#bp21 + 1] = bp
    return true
end

-- ---- the conversation ----------------------------------------------------

-- 0x8005c308: the call. $a0 is an actor record.
arm(0x8005C308, 'enter', function()
    bump('enter')
    local g = cpu()
    if g == nil then return end
    local rec = reg(g, 4)
    if rec < 0x80000000 then return end
    local slot = math.floor((rec - ACTOR_TABLE) / ACTOR_STRIDE)
    log(string.format('ENTER rec=%08x slot=%d entity=%d %s',
        rec, slot, u8(rec + 2), where()))
end)

-- 0x8005c3f8: `lbu $v0, 0($s0)` at the top of the dispatch. $s0 is the program
-- pointer and $s1 the state block, so this is the instruction stream.
local last_pc = -1
arm(0x8005C3F8, 'fetch', function()
    bump('fetch')
    local g = cpu()
    if g == nil then return end
    local s0 = reg(g, 16)
    local s1 = reg(g, 17)
    if s0 < 0x80000000 then return end
    local op = u8(s0)
    local pc = (s1 >= 0x80000000) and u8(s1 + 0x10) or -1
    if pc == last_pc and op == 0xFF then return end   -- an ended script spins
    last_pc = pc
    local extra = ''
    if op == 0xF7 then
        extra = string.format('  flags[%d] = %d', u8(s0 + 1), u8(s0 + 2))
    elseif op == 0xF9 then
        extra = string.format('  if flags[%d] == %d -> %d  (now %d)',
            u8(s0 + 1), u8(s0 + 2), u8(s0 + 3),
            u8(STORY_FLAGS + u8(s0 + 1)))
    elseif op == 0xF4 then
        extra = string.format('  HOOK level code with %d, no-wait %d',
            u8(s0 + 1), u8(s0 + 2))
    elseif op == 0xF0 or op == 0xF8 then
        extra = string.format('  back %d', u8(s0 + 1))
    elseif op == 0xF5 then
        extra = string.format('  no-wait %d', u8(s0 + 1))
    end
    log(string.format('FETCH pc=%3d op=%02x%s', pc, op, extra))
end)

-- 0x8005c5fc: load_entry(7, base + byte) -- the line itself.
arm(0x8005C5FC, 'text', function()
    bump('text')
    local g = cpu()
    if g == nil then return end
    log(string.format('TEXT TALK.T[%d]', reg(g, 5) % 0x10000))
end)

-- ---- the two other unchecked readings ------------------------------------

arm(0x8002DEEC, 'cast', function()
    bump('cast')
    local g = cpu()
    if g == nil then return end
    log(string.format('SPELL cast %d  mp=%d %s', reg(g, 4),
        u16(PLAYER_MP), where()))
end)

arm(0x80029F1C, 'skill', function()
    bump('skill')
    local g = cpu()
    if g == nil then return end
    local k = reg(g, 4)
    log(string.format('SKILL check %d  value=%d', k,
        u16(0x801B2518 + 2 * k)))
end)

arm(0x80041EEC, 'announce', function()
    bump('announce')
    local g = cpu()
    if g == nil then return end
    log(string.format('SAY banner %d', reg(g, 4)))
end)

-- ---- the heartbeat -------------------------------------------------------
local frame = 0
arm(0x800422B8, 'frame', function()
    frame = frame + 1
    if frame % 600 ~= 0 then return end
    local parts = {}
    for k, v in pairs(counts) do parts[#parts + 1] = k .. '=' .. v end
    table.sort(parts)
    log(string.format('-- frame %d  %s  %s', frame, where(),
        table.concat(parts, ' ')))
end)

log(string.format('=== %d breakpoints armed ===', #bp21))

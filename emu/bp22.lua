-- bp22.lua -- what the game writes down about a level, and what it hands out.
--
-- Three readings exist that nothing has ever checked against the running
-- game, and this is the script that would check them.
--
--   STATE  `level_state_write` (0x8005efd4) builds a byte stream on its own
--          stack and hands it to `level_state_unpack`. This dumps that stream
--          at 0x8005f3a4, where it is finished: `$sp + 0x90` to `$s0`. The
--          reading to check is in FORMATS.md -- three sections (the actors
--          that are gone, each talker's conversation pc, then one opcode per
--          object slot, 396 of them in lockstep) -- and it is read off the
--          encoder and the decoder and confirmed by neither.
--          **Pick something up, open a chest, kill something, then change
--          level**, because that is when the stream is written.
--
--   APPLY  `apply_level_state` (0x8005f444) on the way in, with the stream it
--          is about to apply, so the round trip can be seen closing.
--
--   EQUIP  `player_recalc_stats` (0x80029500) on the way out, with what is
--          worn and the sixteen ratings it came to. tools/equip.py reproduces
--          16 of 16 from one RAM snapshot; a second set with something else
--          equipped is what would settle the flat bonuses, which are read and
--          unchecked. **Equip and unequip a few things.**
--
--   HOOK   the `0xf4` opcode in a conversation calling the level's own code
--          (script_interpreter 0x8005c4d0). Sixty of these exist in the game
--          and none has ever been seen run. It is how a conversation makes
--          something happen in the world.
--
--   GUARD  `script_prescan` taking a guard (0x8005c2a4) and the interpreter
--          taking an `0xf9` (0x8005c474) -- the two branches in the
--          conversation language, 78 of them in the game, none yet seen.
--
--   SHOP   the arm of script_interpreter that opens a shop or an inn when a
--          conversation's header +0x12 is not 0xff (0x8005c6d4 and
--          0x8005c72c). **Stay at the inn and buy something.**
--
-- Never `return false` from a callback: PCSX-Redux reads it as "remove this
-- breakpoint", and the silence afterwards would mean nothing.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp22.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 40000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp22 (the world's saved state) armed; debug = '
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

bp22 = {}
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
    bp22[#bp22 + 1] = bp
    return true
end

-- ---- what a level remembers ----------------------------------------------

local function dump(addr, n, tag)
    local parts = {}
    for i = 0, n - 1 do
        parts[#parts + 1] = string.format('%02x', u8(addr + i))
    end
    log(string.format('%s %d bytes', tag, n))
    for i = 1, #parts, 32 do
        log('   ' .. table.concat(parts, ' ', i, math.min(i + 31, #parts)))
    end
end

-- 0x8005f3a4: the `jal level_state_unpack` after the stream is complete.
-- $sp + 0x90 is where level_state_write started writing and $s0 is where it
-- stopped.
arm(0x8005F3A4, 'state', function()
    bump('state')
    local g = cpu()
    if g == nil then return end
    local from = reg(g, 29) + 0x90
    local to = reg(g, 16)
    local n = to - from
    if n <= 0 or n > 4096 then
        log(string.format('STATE %s  buffer %08x..%08x is not sane', where(), from, to))
        return
    end
    log(string.format('STATE written %s', where()))
    dump(from, n, '  stream')
end)

-- 0x8005f444: apply_level_state, with the stream it is handed. $a0 is the
-- level; the stream is found the way the routine finds it.
local LEVEL_STATE, LEVEL_STATE_INDEX = 0x801BAA88, 0x801BFA88
arm(0x8005F444, 'apply', function()
    bump('apply')
    local g = cpu()
    if g == nil then return end
    local lv = reg(g, 4) % 32
    local off = u16(LEVEL_STATE_INDEX + 2 * lv)
    log(string.format('APPLY level %d  index=%04x', lv, off))
    if off ~= 0xffff then dump(LEVEL_STATE + off, 256, '  stream') end
end)

-- ---- what the player is carrying -----------------------------------------

local OFFENSE, DEFENSE = 0x801B2538, 0x801B254A
local WEAPON_SLOT, ARMOUR_SLOTS = 0x801B25AF, 0x801B25D4

-- 0x80029f14: the last instruction of player_recalc_stats before its jr.
arm(0x80029F14, 'equip', function()
    bump('equip')
    local worn = {}
    for i = 0, 6 do worn[#worn + 1] = u8(ARMOUR_SLOTS + i) end
    local off, dfn = {}, {}
    for i = 0, 7 do
        off[#off + 1] = u16(OFFENSE + 2 * i)
        dfn[#dfn + 1] = u16(DEFENSE + 2 * i)
    end
    log(string.format('EQUIP weapon=%d worn=[%s]', u8(WEAPON_SLOT),
        table.concat(worn, ',')))
    log(string.format('   offense [%s]  defense [%s]',
        table.concat(off, ','), table.concat(dfn, ',')))
end)

-- ---- the parts of a conversation nothing has seen -------------------------

-- 0x8005c4d0: the 0xf4 arm, about to call [0x8018fae0]->+0x10(actor, arg).
arm(0x8005C4D0, 'hook', function()
    bump('hook')
    local g = cpu()
    if g == nil then return end
    local hooks = u32(0x8018FAE0)
    -- $s0 has already stepped past the opcode here, so it points at the
    -- argument byte: 0x8005c4d8 reads it as `lbu $a1, 0x0($s0)`.
    log(string.format('HOOK arg=%d  level_hooks=%08x  +0x10=%08x  %s',
        u8(reg(g, 16)), hooks, u32(hooks + 0x10), where()))
end)

-- 0x8005c2a4: script_prescan, a guard held. It is the `lbu $a1, 0x0($a0)`
-- that fetches the label, so $a1 is not loaded yet and $a0 is the label byte
-- itself; the flag and the value are the two before it. $s0 is the block.
arm(0x8005C2A4, 'guard', function()
    bump('guard')
    local g = cpu()
    if g == nil then return end
    local at = reg(g, 4)
    log(string.format('GUARD flags[%d] == %d held -> label %d  (pc was %d)  %s',
        u8(at - 2), u8(at - 1), u8(at), u8(reg(g, 16) + 0x10), where()))
end)

-- 0x8005c474: the 0xf9 arm, with the flag that held.
arm(0x8005C474, 'if', function()
    bump('if')
    local g = cpu()
    if g == nil then return end
    local s0 = reg(g, 16)
    log(string.format('IF flags[%d] == %d -> label %d',
        u8(s0 + 1), u8(s0 + 2), u8(s0 + 3)))
end)

-- 0x8005c6d4 and 0x8005c72c: the two service arms, taken when a talker's
-- header +0x12 is not 0xff.
arm(0x8005C6D4, 'shop', function()
    bump('shop')
    local g = cpu()
    if g == nil then return end
    log(string.format('SHOP service=%02x  [0x801b2530]=%d',
        u8(reg(g, 17) + 0x12), u16(0x801B2530)))
end)

arm(0x8005C72C, 'service', function()
    bump('service')
    local g = cpu()
    if g == nil then return end
    log(string.format('SERVICE %02x', u8(reg(g, 17) + 0x12)))
end)

-- ---- the heartbeat -------------------------------------------------------
local frame = 0
arm(0x800422B8, 'frame', function()
    frame = frame + 1
    if frame % 900 ~= 0 then return end
    local parts = {}
    for k, v in pairs(counts) do parts[#parts + 1] = k .. '=' .. v end
    table.sort(parts)
    log(string.format('-- frame %d  %s  %s', frame, where(),
        table.concat(parts, ' ')))
end)

log(string.format('=== %d breakpoints armed ===', #bp22))

-- What actually hands over the sword, asked of the value instead of the code.
--
--   ./emu/run.sh debug bp18.lua
--
-- Then start a new game and play the opening scene again.
--
-- bp17 asked the routines and they all said no: over the whole scene,
-- `give_item`, `take_item`, `object_interact` and `script_interpreter` never
-- ran once. So the sword does not change hands the way every other item in the
-- game does, and picking another routine to watch would only be another guess.
--
-- This asks the *value*. A write watchpoint on the inventory array makes
-- whatever writes it name itself, whichever routine that turns out to be --
-- the same shape of question that found the player's movement after two
-- readings had picked the wrong routine. `story_flags` is watched beside it,
-- because a scene that happens once has to record that it happened.
--
-- Never `return false` from a callback: PCSX-Redux reads that as "remove this
-- breakpoint", and the silence afterwards would mean nothing.

local LOG = '/home/solo/my/projects/kings_field_2_english/out/lua_bp18.log'
local out = io.open(LOG, 'a')
local lines = 0
local function log(s)
    if lines > 8000 then return end
    lines = lines + 1
    out:write(tostring(s) .. '\n')
    out:flush()
end

PCSX.settings.emulator.Debug.Debug = true
log('=== bp18 armed; debug = ' .. tostring(PCSX.settings.emulator.Debug.Debug) .. ' ===')

local mem = PCSX.getMemPtr()
local function u8(a) return mem[a % 0x200000] end
local function s32(a)
    local b = a % 0x200000
    local v = mem[b] + mem[b + 1] * 256 + mem[b + 2] * 65536 + mem[b + 3] * 16777216
    if v >= 0x80000000 then v = v - 0x100000000 end
    return v
end

local function regs()
    local ok, r = pcall(PCSX.getRegisters)
    if not ok or r == nil then return nil end
    if r.GPR and r.GPR.n then return r.GPR.n end
    return r.GPR or r
end

-- bp15 established these: the player's own X, Y and Z, the three words a
-- watchpoint caught the game storing. bp17 printed cell (0,0) for everything
-- because it read the stat block instead, which is not where the position is.
local function where()
    local x, z = s32(0x801b25f0), s32(0x801b25f8)
    return string.format('lv=%d cell=(%d,%d)', u8(0x8018fad8),
        math.floor(x / 2048), math.floor(z / 2048))
end

local function pc_of(g)
    local ok, r = pcall(PCSX.getRegisters)
    if ok and r and r.pc then return tonumber(r.pc) end
    return 0
end

bp18 = {}
local seen = {}
local function arm(addr, tag, kind, width, fn)
    local ok, bp = pcall(PCSX.addBreakpoint, addr, kind, width, tag, fn)
    log(string.format('arm %08x+%-4d %-12s %-5s -> %s',
        addr, width, tag, kind, tostring(ok)))
    if ok then bp18[#bp18 + 1] = bp end
end

-- inventory_a: one byte per item id, 0 to 149. The sword is object type 0 and
-- an object's type id is the item it yields, so id 0 is the one to expect --
-- but the whole array is watched, because expecting is what bp17 did.
arm(0x800c85e8, 'inventory_a', 'Write', 150, function(addr)
    local g = regs()
    if g == nil then return end
    local id = (tonumber(addr) or 0x800c85e8) - 0x800c85e8
    log(string.format('INV_A item=%-3d now=%-3d pc=%08x ra=%08x  %s',
        id, u8(0x800c85e8 + id), pc_of(g), tonumber(g.ra), where()))
end)

arm(0x800c867e, 'inventory_b', 'Write', 150, function(addr)
    local g = regs()
    if g == nil then return end
    local id = (tonumber(addr) or 0x800c867e) - 0x800c867e
    log(string.format('INV_B item=%-3d now=%-3d pc=%08x ra=%08x  %s',
        id, u8(0x800c867e + id), pc_of(g), tonumber(g.ra), where()))
end)

-- A scene that happens once records that it happened. flags[0] is a progress
-- counter, so it moves often; the rest are the interesting ones.
arm(0x801ba988, 'story_flags', 'Write', 64, function(addr)
    local g = regs()
    if g == nil then return end
    local i = (tonumber(addr) or 0x801ba988) - 0x801ba988
    local key = 'f' .. tostring(i)
    seen[key] = (seen[key] or 0) + 1
    if seen[key] <= 6 then
        log(string.format('FLAG  %-3d now=%-3d pc=%08x ra=%08x  %s',
            i, u8(0x801ba988 + i), pc_of(g), tonumber(g.ra), where()))
    end
end)

-- Kept from bp17 because it worked: which of the three men by the house the
-- game turns on. This time the writing PC is logged beside the return address.
for slot = 0, 2 do
    arm(0x80185da8 + slot * 0x88 + 9, 'actor' .. slot, 'Write', 1, function()
        local g = regs()
        if g == nil then return end
        local base = 0x80185da8 + slot * 0x88
        log(string.format('ACTOR %d mesh=%-3d alive=%d pc=%08x ra=%08x  %s',
            slot, u8(base + 1), u8(base + 9), pc_of(g), tonumber(g.ra), where()))
    end)
end

log('=== bp18 watching; new game, then play the scene through ===')

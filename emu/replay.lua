-- A session of bp29.lua played back: the emulator from a keyframe, PadRead
-- answered from the recording, every frame's record (kfrec.lua) set beside the
-- one the session wrote. tools/playlog.py runs it, with no window, and says what
-- came of it.
--
--   KF_RUN      the session's directory
--   KF_STATE    the keyframe's state, uncompressed
--   KF_FROM     the frame and the calls it was taken at, as "frame calls"
--   KF_UNTIL    the last frame to run, 0 for the end of the recording
--   KF_DUMP     "a b out": frames a..b's tables whole into `out`, through zstd
--   KF_REPORT   where to write the report
--   KF_EVENTS   where to write what happened (kfrec.lua), if anywhere
--   KF_LIVE     where to write each frame for the port to show, if anywhere;
--               a menu's frames go to menu.txt beside it (kfrec.lua menu_arm)
--
-- The answer is written at PadRead's return, so the emulated pad stays idle and
-- nothing about the buttons reaches the machine but the word the game reads.

local ffi = require 'ffi'
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local K = dofile(HERE .. '/kfrec.lua')
local DIR = os.getenv('KF_RUN') .. '/'
local frame0, calls0 = (os.getenv('KF_FROM') or '0 0'):match('(%d+) (%d+)')
frame0, calls0 = tonumber(frame0), tonumber(calls0)
local UNTIL = tonumber(os.getenv('KF_UNTIL') or '0')
local report = io.open(os.getenv('KF_REPORT'), 'w')

PCSX.settings.emulator.Debug.Debug = true

local function slurp(name)
    local f = io.open(name, 'rb')
    local s = f:read('*a')
    f:close()
    return s
end

-- Held in globals: the pointers below keep nothing alive, and a string the
-- collector takes leaves them reading rubbish, which the game gets as buttons.
replay_frames, replay_pads = slurp(DIR .. 'frames.bin'), slurp(DIR .. 'pad.bin')
local frames_s, pads_s = replay_frames, replay_pads
local SIZE = ffi.sizeof('kf_frame')
local nframes = #frames_s / SIZE
local want = ffi.cast('const kf_frame*', frames_s)
local pads = ffi.cast('const uint32_t*', pads_s)
local npads = #pads_s / 8
if UNTIL == 0 or UNTIL > nframes then UNTIL = nframes end

-- the stream's place: skip the calls before the keyframe
local pi, left = 0, 0
local skip = calls0
while pi < npads and skip >= pads[pi * 2 + 1] do
    skip = skip - pads[pi * 2 + 1]
    pi = pi + 1
end
if pi < npads then left = pads[pi * 2 + 1] - skip end

local dump_a, dump_b, dump_f
local d = os.getenv('KF_DUMP')
if d and d ~= '' then
    local a, b, name = d:match('(%d+) (%d+) (.+)')
    dump_a, dump_b = tonumber(a), tonumber(b)
    dump_f = io.popen('zstd -q -3 -f -o "' .. name .. '"', 'w')
end

local ev_name = os.getenv('KF_EVENTS')
local events = ev_name and ev_name ~= '' and io.open(ev_name, 'w') or nil

local live_path = os.getenv('KF_LIVE')
local shot_at = tonumber(os.getenv('KF_SHOT_AT') or '0')
local running = false
local frame, calls = frame0, calls0
if live_path and live_path ~= '' then
    K.menu_arm(live_path:gsub('[^/]*$', 'menu.txt'), function() return frame end)
end
local rec = ffi.new('kf_frame')
local same, diffs = 0, {}
local fieldbad = {}
local first = nil

local function finish()
    if dump_f then dump_f:close() end
    if events then events:close() end
    report:write(string.format('frames %d same %d of %d, from %d\n', frame - frame0, same,
        frame - frame0, frame0))
    for _, n in ipairs(K.FIELDS) do
        if fieldbad[n] then report:write(string.format('field %s %d\n', n, fieldbad[n])) end
    end
    for _, l in ipairs(diffs) do report:write(l, '\n') end
    report:close()
    PCSX.quit(0)
end

pad_bp = PCSX.addBreakpoint(K.PAD_RET, 'Exec', 4, 'replay pad', function()
    if not running or not K.in_game() then return end
    calls = calls + 1
    if pi >= npads then return end
    PCSX.getRegisters().GPR.n.v0 = pads[pi * 2]
    left = left - 1
    if left == 0 then
        pi = pi + 1
        if pi < npads then left = pads[pi * 2 + 1] end
    end
end)

frame_bp = PCSX.addBreakpoint(K.FRAME, 'Exec', 4, 'replay frame', function()
    if not running or not K.in_game() then return end
    frame = frame + 1
    K.fill(rec, frame, calls)
    if frame <= nframes then
        local w = want[frame - 1]
        local bad = false
        for _, n in ipairs(K.FIELDS) do
            if rec[n] ~= w[n] then
                -- a blank landing either side of frame_limit's first instruction,
                -- which the next frame's wait takes up: counted, not held against it
                if n ~= 'vblank' then bad = true end
                fieldbad[n] = (fieldbad[n] or 0) + 1
                if #diffs < 40 then
                    diffs[#diffs + 1] = string.format('frame %d %s want %s got %s', frame, n,
                        tostring(w[n]), tostring(rec[n]))
                end
            end
        end
        if not bad then same = same + 1 end
    end
    if dump_f and frame >= dump_a and frame <= dump_b then K.tables(dump_f) end
    if events then K.events(frame, events) end
    if live_path then K.live(frame, live_path) end
    if frame == shot_at then
        local ss = PCSX.GPU.takeScreenShot()
        local g = Support.File.open(os.getenv('KF_SHOT'), 'TRUNCATE')
        g:writeMoveSlice(ss.data)
        g:close()
        print('shot ', ss.width, ss.height, tonumber(ss.bpp))
    end
    if frame % 300 == 0 then
        report:write(string.format('at %d same %d\n', frame, same))
        report:flush()
    end
    if frame >= UNTIL then running = false; finish() end
end)

local n = 0
vb = PCSX.Events.createEventListener('GPU::Vsync', function()
    n = n + 1
    if n == 30 then
        local f = Support.File.open(os.getenv('KF_STATE'), 'READ')
        PCSX.loadSaveState(f)
        f:close()
        running = true
    end
end)
print('replay: armed, ' .. nframes .. ' frames, until ' .. UNTIL)

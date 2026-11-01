-- The flight recorder: a whole playthrough, small enough to keep and exact
-- enough to play back. Play normally, from the title screen on:
--
--   ./emu/run.sh debug bp29.lua
--   python3 tools/playlog.py                   what has been recorded
--   python3 tools/playlog.py replay            the emulator, no window, same buttons
--   python3 tools/playlog.py mark "..."        a note, from another terminal
--
-- It records from the first frame of GAME.EXE into out/run/<date>/. What it
-- keeps is what cannot be worked out again, and little of that:
--
--   key-NNNN.state.gz, .mc1, .mc2   the emulator's whole state and both memory
--                                   cards, at the start and every KEY_EVERY frames
--   pad.bin                         every word PadRead gave, as (word, count)
--   frames.bin                      a record a frame: where the player is, rand's
--                                   state, and a hash of each of the game's tables
--                                   (kfrec.lua) -- what a replay is held to
--   notes.txt, note-NNN.ram, .shot  a note: its frame, the RAM and the picture
--
-- Everything else -- where the creatures stood, what was killed, what was taken,
-- the tables byte for byte -- comes out of a replay, as often as it is asked and
-- about things nobody has thought of yet, because the game repeats: the same
-- state and the same buttons give the same frames (tools/playlog.py).
--
-- Two ways to leave a note, both at the frame you are on. In the small window
-- the script opens: type, press the button; Pause holds the game while you do.
-- Or from a terminal: python3 tools/playlog.py mark "text". Its window is
-- ImGui's, so it is only there with a display; the terminal's way needs none.
--
-- Load a save state in the emulator and the timeline is another: the time goes
-- back, and the recorder starts a new session of its own. Saving and loading on
-- the game's own memory card is all inside the one.
--
-- Never `return false` from a breakpoint: PCSX-Redux reads it as "delete me".

local ffi = require 'ffi'
local HERE = debug and debug.getinfo(1, 'S').source:match('^@(.*)[/\\][^/\\]*$') or '.'
local RUNS = HERE .. '/../out/run/'
local K = dofile(HERE .. '/kfrec.lua')
local KEY_EVERY = 4500            -- game frames, five minutes of them
local FLUSH_EVERY = 150           -- ten seconds: what a crash can take with it
local MARK_EVERY = 15             -- how often the terminal's note is looked for
local PACK_AFTER = 150            -- frames before a keyframe is packed: the emulator
                                  -- writes files on a thread of its own, and a gzip
                                  -- started at once reads one half written
local MARK = RUNS .. 'mark.txt'

PCSX.settings.emulator.Debug.Debug = true

local dir
local frames_f, pads_f, keys_f, notes_f
local frame, calls, last_vb, nkeys, nnotes = 0, 0, 0, 0, 0
local word, run = 0, 0
local rec = ffi.new('kf_frame')
local pair = ffi.new('uint32_t[2]')
local paused, note_text, said = false, '', ''
local to_pack, pack_at

local function pad_out()
    if run > 0 then
        pair[0], pair[1] = word, run
        pads_f:write(ffi.string(pair, 8))
        run = 0
    end
end

local function copy(from, to)
    local f = io.open(from, 'rb')
    if not f then return end
    local g = io.open(to, 'wb')
    g:write(f:read('*a'))
    g:close()
    f:close()
end

local function take_key()
    local name = dir .. string.format('key-%04d', nkeys)
    local f = Support.File.open(name .. '.state', 'TRUNCATE')
    f:writeMoveSlice(PCSX.createSaveState())
    f:close()
    copy(PCSX.settings.emulator.Mcd1, name .. '.mc1')
    copy(PCSX.settings.emulator.Mcd2, name .. '.mc2')
    to_pack, pack_at = name .. '.state', frame + PACK_AFTER
    keys_f:write(string.format('%d %d %d\n', nkeys, frame, calls))
    keys_f:flush()
    nkeys = nkeys + 1
end

local function close_session()
    if not dir then return end
    pad_out()
    frames_f:close()
    pads_f:close()
    keys_f:close()
    notes_f:close()
    dir = nil
end

local function start_session()
    close_session()
    dir = RUNS .. os.date('%Y%m%d-%H%M%S') .. '/'
    os.execute('mkdir -p "' .. dir .. '"')
    frames_f = io.open(dir .. 'frames.bin', 'wb')
    pads_f = io.open(dir .. 'pad.bin', 'wb')
    keys_f = io.open(dir .. 'keys.txt', 'w')
    notes_f = io.open(dir .. 'notes.txt', 'w')
    frame, calls, run, nkeys, nnotes = 0, 0, 0, 0, 0
    take_key()
    print('bp29: recording into ' .. dir)
end

local function take_note(text)
    if not dir then return end
    nnotes = nnotes + 1
    local name = dir .. string.format('note-%03d', nnotes)
    local f = io.open(name .. '.ram', 'wb')
    f:write(ffi.string(K.mem, 0x200000))
    f:close()
    local ok, ss = pcall(PCSX.GPU.takeScreenShot)
    if ok then
        local g = Support.File.open(name .. '.shot', 'TRUNCATE')
        g:writeMoveSlice(ss.data)
        g:close()
        local h = io.open(name .. '.txt', 'w')
        h:write(string.format('%d %d %d\n', ss.width, ss.height, tonumber(ss.bpp)))
        h:close()
    end
    notes_f:write(string.format('%d\t%d\t%d\t%s\n', nnotes, frame, calls,
        text:gsub('[\r\n\t]', ' ')))
    notes_f:flush()
    said = string.format('note %d, frame %d', nnotes, frame)
    print('bp29: ' .. said)
end

local function terminal_note()
    local f = io.open(MARK, 'r')
    if not f then return end
    local text = f:read('*a')
    f:close()
    os.remove(MARK)
    take_note(text or '')
end

pad_bp = PCSX.addBreakpoint(K.PAD_RET, 'Exec', 4, 'bp29 pad', function()
    if not dir or not K.in_game() then return end
    local v = PCSX.getRegisters().GPR.n.v0
    calls = calls + 1
    if run > 0 and v ~= word then pad_out() end
    word = v
    run = run + 1
end)

frame_bp = PCSX.addBreakpoint(K.FRAME, 'Exec', 4, 'bp29 frame', function()
    if not K.in_game() then return end
    local vb = K.w32(0x801c12e8)
    if not dir or vb < last_vb then start_session() end
    last_vb = vb
    if frame > 0 and frame % KEY_EVERY == 0 then take_key() end
    frame = frame + 1
    K.fill(rec, frame, calls)
    frames_f:write(ffi.string(rec, ffi.sizeof(rec)))
    if frame % FLUSH_EVERY == 0 then
        pad_out()
        pads_f:flush()
        frames_f:flush()
    end
    if frame % MARK_EVERY == 0 then terminal_note() end
    if to_pack and frame >= pack_at then
        os.execute('gzip -1 -f "' .. to_pack .. '" &')
        to_pack = nil
    end
end)

-- The small window. An error in it costs the window and not the recording, and
-- End is called whatever happens, or ImGui takes the emulator's own windows with it.
local function window()
    if not imgui.Begin('KF2 flight recorder') then return end
    if dir then
        imgui.TextUnformatted(string.format('frame %d, level %d, cell (%d, %d)', frame, rec.level,
            bit.arshift(rec.x, 11), bit.arshift(rec.z, 11)))
    else
        imgui.TextUnformatted('waiting for the first frame of GAME.EXE')
    end
    local changed, t = imgui.extra.InputText('##note', note_text)
    if changed then note_text = t end
    if imgui.Button('Note') then
        take_note(note_text)
        note_text = ''
    end
    imgui.SameLine()
    if imgui.Button(paused and 'Go on' or 'Pause') then
        paused = not paused
        if paused then PCSX.pauseEmulator() else PCSX.resumeEmulator() end
    end
    if said ~= '' then imgui.TextUnformatted(said) end
end

local told = false
function DrawImguiFrame()
    local ok, err = pcall(window)
    imgui.End()
    if not ok and not told then
        told = true
        print('bp29: the window: ' .. tostring(err))
    end
end

quitting = PCSX.Events.createEventListener('Quitting', close_session)
print('bp29: armed, waiting for GAME.EXE')

#!/usr/bin/env bash
# Launch King's Field II in PCSX-Redux with OpenBIOS and the HTTP debug API.
#
#   ./run.sh            start the emulator (web API on :8080)
#   ./run.sh debug      the same, plus bp.lua and its breakpoints
#   ./run.sh debug X.lua   the same, with X.lua instead of bp.lua
#   ./run.sh stop       stop it
#
# The HTTP API is what the analysis scripts use; unlike the GDB stub on :3333
# it snapshots RAM/VRAM without pausing the game.
#
# Breakpoints only fire under `debug`: they need the interpreter, since the
# binary itself warns that the debugger and the dynarec conflict, and they need
# bp.lua to turn the debug switch on at runtime because setting it in pcsx.json
# does not take.
set -euo pipefail
cd "$(dirname "$0")"

APP=./PCSX-Redux-HEAD-x86_64.AppImage
BIOS="$PWD/squashfs-root/usr/share/pcsx-redux/resources/openbios.bin"
CUE="$PWD/kf2.cue"

if [ "${1:-start}" = "stop" ]; then
    pkill -x AppRun && echo "stopped" || echo "not running"
    exit 0
fi

if pgrep -x AppRun >/dev/null; then
    echo "already running (web API: http://127.0.0.1:8080/api/v1)"
    exit 0
fi

EXTRA=()
if [ "${1:-start}" = "debug" ]; then
    EXTRA=(-interpreter -lua_stdout -dofile "${2:-bp.lua}")
fi

setsid nohup "$APP" -stdout -bios "$BIOS" -iso "$CUE" -run \
    "${EXTRA[@]}" -webserver -webserver-port 8080 > pcsx.log 2>&1 < /dev/null &
echo $! > pcsx.pid
sleep 8
if pgrep -x AppRun >/dev/null; then
    echo "started; web API: http://127.0.0.1:8080/api/v1"
    [ ${#EXTRA[@]} -gt 0 ] && echo "loaded ${2:-bp.lua}; it writes its own log under out/"
else
    echo "failed to start; see pcsx.log" >&2
    exit 1
fi

#!/usr/bin/env bash
# The game and the port side by side: play in the emulator, and the port beside
# it stands where the game stands and shows what the game has -- the creatures,
# the doors, every object and the flying effects -- with nothing of its own
# running, so a difference on the screen is a difference in how the two draw.
# The session is recorded as under bp29.lua.
#
#   ./emu/side.sh
set -euo pipefail
cd "$(dirname "$0")"
./run.sh stop >/dev/null 2>&1 || true
sleep 1
export KF_LIVE=1
./run.sh debug bp29.lua
cd ../out/godot
exec godot-4 --path . res://world00.tscn -- --follow

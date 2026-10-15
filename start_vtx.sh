#!/bin/sh
set -eu

PROJECT_DIR=/home/droneaitraf/droneAItraffic
LOG_FILE=/home/droneaitraf/.local/state/drone-ai-vtx.log

mkdir -p /home/droneaitraf/.local/state
sleep 8
cd "$PROJECT_DIR"
exec .venv/bin/python main.py >> "$LOG_FILE" 2>&1

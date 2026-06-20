#!/bin/bash
# Double-click this file to start the exam transcriber.
#
# A Terminal window will open and stay open while the app is running — that is
# normal, just leave it open. Your web browser will open to the app a few
# seconds later. When you are finished, close this Terminal window to stop.

cd "$(dirname "$0")" || exit 1

# Make sure the 'uv' tool is findable no matter how it was installed.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "Could not find 'uv'. Please finish the one-time setup in the README first."
  echo "Press any key to close." ; read -n 1 -s -r ; exit 1
fi

echo "Starting up (the first run may take a minute to install things)…"
uv sync --quiet

# Open the browser shortly after the server is ready.
( sleep 4 ; open "http://localhost:8000" ) &

echo "The app is running. Your browser should open automatically."
echo "Leave this window open while you work; close it when you are done."
uv run uvicorn ocr_grade.web.app:app --host 127.0.0.1 --port 8000

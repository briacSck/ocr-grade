#!/bin/bash
# Double-click this file when you have finished grading and downloaded your
# transcripts. It erases the scanned exams and generated transcripts from this
# computer (the privacy "clean up when done" step). It does NOT touch anything
# you already saved to your Downloads folder.

cd "$(dirname "$0")" || exit 1

rm -rf web-work .cache out

echo "Done — all uploaded scans and generated transcripts have been erased from this computer."
echo "Anything you already downloaded is untouched."
echo "You can close this window."

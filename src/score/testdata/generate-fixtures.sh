#!/usr/bin/env bash
# Generates the synthetic fixture clips this repo's own tests, README
# examples, and CG02/CG03 threshold calibration are derived from. No real
# short-drama footage is available for this build, so every fixture is a
# fully synthetic, deterministically reproducible ffmpeg-generated clip --
# not a stand-in claiming to be real footage.
#
# Fixture set:
#   mei_shot01.mp4 / mei_shot02.mp4     -- same character, consistent look
#                                          (CG02: should NOT be flagged)
#   aiko_shot01.mp4 / aiko_shot02.mp4   -- same character, consistent look
#                                          (CG02: should NOT be flagged)
#   kenji_shot01.mp4 / kenji_shot02.mp4 -- same claimed character, shot02
#                                          deliberately different visual
#                                          identity (CG02: SHOULD be flagged)
#   action-discontinuity.mp4            -- smooth motion with one abrupt
#                                          jump (CG03: SHOULD be flagged).
#                                          Named with a hyphen, not
#                                          "<name>_<id>", so it is NOT
#                                          parsed as a character clip by
#                                          CG02's filename convention.
#   calm-baseline.mp4                   -- smooth motion, no jump
#                                          (CG03: should NOT be flagged).
#                                          Same hyphen-naming note applies.
#
# Run from anywhere; writes into this same directory.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

mkdir -p clips
SIZE=320x240

echo "Generating mei_shot01.mp4 / mei_shot02.mp4 (consistent character)..."
ffmpeg -y -loglevel error -f lavfi -i "color=c=0xE8B98A:s=${SIZE}:d=2" -r 24 clips/mei_shot01.mp4
ffmpeg -y -loglevel error -f lavfi -i "color=c=0xE8B98A:s=${SIZE}:d=2" -vf "eq=brightness=0.03:contrast=1.02" -r 24 clips/mei_shot02.mp4

echo "Generating aiko_shot01.mp4 / aiko_shot02.mp4 (consistent character)..."
ffmpeg -y -loglevel error -f lavfi -i "color=c=0x6B4226:s=${SIZE}:d=2" -r 24 clips/aiko_shot01.mp4
ffmpeg -y -loglevel error -f lavfi -i "color=c=0x6B4226:s=${SIZE}:d=2" -vf "eq=brightness=-0.02:saturation=0.97" -r 24 clips/aiko_shot02.mp4

echo "Generating kenji_shot01.mp4 / kenji_shot02.mp4 (deliberately inconsistent)..."
ffmpeg -y -loglevel error -f lavfi -i "color=c=0x4A6572:s=${SIZE}:d=2" -r 24 clips/kenji_shot01.mp4
ffmpeg -y -loglevel error -f lavfi -i "color=c=0xE63946:s=${SIZE}:d=2" -r 24 clips/kenji_shot02.mp4

echo "Generating action-discontinuity.mp4 (motion discontinuity)..."
TMP=$(mktemp -d)
ffmpeg -y -loglevel error -f lavfi -i "testsrc=size=${SIZE}:rate=24:duration=2" "$TMP/a.mp4"
ffmpeg -y -loglevel error -f lavfi -i "color=c=0xFF00FF:s=${SIZE}:d=0.6" -r 24 "$TMP/b.mp4"
ffmpeg -y -loglevel error -f lavfi -i "testsrc2=size=${SIZE}:rate=24:duration=2" "$TMP/c.mp4"
printf "file '%s'\nfile '%s'\nfile '%s'\n" "$TMP/a.mp4" "$TMP/b.mp4" "$TMP/c.mp4" > "$TMP/concat.txt"
ffmpeg -y -loglevel error -f concat -safe 0 -i "$TMP/concat.txt" -c:v libx264 -pix_fmt yuv420p clips/action-discontinuity.mp4
rm -rf "$TMP"

echo "Generating calm-baseline.mp4 (smooth motion, no discontinuity)..."
ffmpeg -y -loglevel error -f lavfi -i "testsrc=size=${SIZE}:rate=24:duration=4.5" clips/calm-baseline.mp4

echo "Done. Fixtures written to $(pwd)/clips"
ls -la clips

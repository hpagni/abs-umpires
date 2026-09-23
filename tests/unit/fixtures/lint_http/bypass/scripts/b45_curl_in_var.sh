#!/bin/sh
BIN="curl"
"$BIN" -sS https://statsapi.mlb.com/api/v1/schedule -o schedule.json

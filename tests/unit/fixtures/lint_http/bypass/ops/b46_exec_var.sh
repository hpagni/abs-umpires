#!/bin/sh
BIN=${FETCH:-curl}
"$BIN" -sS https://statsapi.mlb.com/api/v1/schedule -o schedule.json

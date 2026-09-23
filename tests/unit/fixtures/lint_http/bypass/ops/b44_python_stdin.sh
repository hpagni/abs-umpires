#!/bin/sh
python3 - <<'PY'
import requests
print(requests.get("https://statsapi.mlb.com/api/v1/schedule").status_code)
PY

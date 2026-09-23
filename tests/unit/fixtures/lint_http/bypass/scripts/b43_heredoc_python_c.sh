#!/bin/sh
python3 -c "$(cat <<'PY'
import requests
print(requests.get("https://statsapi.mlb.com/api/v1/schedule").status_code)
PY
)"

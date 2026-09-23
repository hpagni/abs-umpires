import importlib

mod = importlib.import_module("requests")
SCHEDULE = mod.get("https://statsapi.mlb.com/api/v1/schedule").json()

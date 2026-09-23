import importlib

hx = importlib.import_module("httpx")
BOX = hx.get("https://statsapi.mlb.com/api/v1/game/1/feed/live").json()

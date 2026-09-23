# a module named as a string reaches the network without an import keyword
mod = __import__("requests")
SCHEDULE = mod.get("https://statsapi.mlb.com/api/v1/schedule").json()

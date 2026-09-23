import shlex
import subprocess

CMD = "cu" "rl -sS https://statsapi.mlb.com/api/v1/schedule"  # fmt: skip
subprocess.run(shlex.split(CMD), check=True)

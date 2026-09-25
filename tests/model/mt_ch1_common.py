"""Shared paths, loaders and thresholds for the Chapter 1 MT pack, tests/model/test_mt_ch1_*.py.

Owner: the model-tests lane. Each threshold is quoted where it is used, from
sop/SOP-final.md section 6.5 (MT-01 to MT-05, MT-09) or from the pre-registered acceptance
in docs/prereg/ch1.md section 8.7, which restates SOP W3.12(a) and CH1-A7. The tests read
what W3.12 wrote under out/dev/ch1_synth/ and refit nothing. out/ never enters git, so on a
clean clone each module skips and names the missing path.
"""

import gzip
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SYN = ROOT / "out" / "dev" / "ch1_synth"
REC = SYN / "recovery"
SBC = SYN / "sbc"
POWER = SYN / "power"
CURVE_CSV = ROOT / "out" / "tables" / "ch1_power_curve.csv"
PREREG_MD = ROOT / "docs" / "prereg" / "ch1.md"
PREREG_ROOT = ROOT / "PREREGISTRATION.md"
SCRIPT = ROOT / "R" / "ch1" / "21_synthetic.R"

SHIFTS = ("top_in", "bot_in", "half_width_in")
INJECTED = {"top_in": -0.60, "bot_in": 0.30, "half_width_in": -0.10}  # SOP W3.12(a)
TAUS = ("0.10", "0.20", "0.30")  # SOP W3.12(c), D-60
N_SEEDS = 5
ESTIMATORS = ("sop", "ue_us")


def need(*paths):
    """Skip the calling module when an artefact is absent, naming it."""
    missing = [str(p.relative_to(ROOT)) for p in paths if not p.exists()]
    if missing:
        pytest.skip(
            "absent, run W3.12 first (out/ is not in git): " + ", ".join(missing),
            allow_module_level=True,
        )


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def reps(directory, expected):
    """rep001.json .. rep<expected>.json, in order; asserts none is missing or extra."""
    files = sorted(pathlib.Path(directory).glob("rep[0-9][0-9][0-9].json"))
    got = [int(f.stem[3:]) for f in files]
    assert got == list(range(1, expected + 1)), (
        f"{directory.relative_to(ROOT)}: {len(got)} replicate files, expected 1..{expected}"
    )
    return [read_json(f) for f in files]


def seed_dir(est, tau, seed):
    return POWER / est / f"tau{tau}_seed{seed}"


def tau_draws(est, tau, seed):
    """The stored tau_abs draws of one power seed."""
    with gzip.open(seed_dir(est, tau, seed) / "tau_draws.csv.gz", "rt", encoding="utf-8") as fh:
        head = fh.readline().strip().replace('"', "").split(",")
        j = head.index("tau_abs")
        return [float(line.split(",")[j]) for line in fh if line.strip()]

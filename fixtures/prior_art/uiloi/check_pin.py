"""Check the pinned prior-art snapshot against the constants in SOP step W5.1.

Usage: python fixtures/prior_art/uiloi/check_pin.py [--dir DIR]

DIR defaults to the directory this file sits in. When snapshot B is pinned, snapshot A
moves to fixtures/prior_art/uiloi_2026-09-22/ and this check is pointed there with --dir.

The constants below are the SOP's verified literals for snapshot A, 2026-09-22T14:34Z.
They are copied, not re-derived. The check uses the standard library only, so it runs
without numpy.

Exit 0 when every assertion holds. Exit 1 on the first class of failure, with each
failing assertion printed.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

# The seven files W5.1 names.
NAMED = (
    "dp_V_2026.npy",
    "dp_C_2026.npy",
    "tier1_results_2026.json",
    "tier1_card_2026.csv",
    "tier1_teams_2026.csv",
    "tier1_mtv_2026.csv",
    "perception_fit_2026.json",
)
# The four snapshot A files that were overwritten upstream before the pin was taken.
# PROVENANCE.txt must name each one. They enter the pin with snapshot B.
LOST_FROM_A = (
    "dp_C_2026.npy",
    "tier1_teams_2026.csv",
    "tier1_mtv_2026.csv",
    "perception_fit_2026.json",
)

SHA256_LITERAL = {
    "dp_V_2026.npy": "e1f3b782e60e489a0eb57d5754dbb46222b9b1a6d401ec830aa68872be3aa084",
    "tier1_results_2026.json": "3c1c8ade6f87663157d7c828a62510f9f040b230aecfa24f065bdcd4157306f8",
}
NPY_HEADER = {"descr": "<f8", "fortran_order": False, "shape": (26, 13, 3)}
V_1_6_ROUNDED = (0.000942, 0.016234)  # stated to 6 decimals in the SOP
V_1_6_2 = 0.02482455343483908
GAINS = {
    "optimal": 0.025664653020004317,
    "observed_realized": 0.021194162481928715,
    "oracle": 0.0643380612995814,
    "card": 0.023793061369243137,
    "naive50": 0.011846482651462244,
    "late50": 0.0038184048326990196,
    "observed_model": 0.019090033874778346,
    "never": 0.0,
}
CAPTURE_POINT = 0.8258113782176958
CAPTURE_CI95 = [0.7972195382417352, 0.8543853020992268]
CAPTURE_N_GAMES = 2338
V2_START_TIE = 0.02482455343483908
CONCAVITY_VIOLATIONS = 36
CONCAVITY_H = {19, 21, 22, 23}
EXTRAS_EQUAL_H = (19, 21, 23)
V_1_7_2_PP = 2.4066
V_1_5_2_PP = 2.3156


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_npy(path: Path) -> tuple[dict, list[float]]:
    raw = path.read_bytes()
    if raw[:6] != b"\x93NUMPY":
        raise ValueError(f"{path.name}: not an .npy file")
    major = raw[6]
    if major == 1:
        (hlen,) = struct.unpack("<H", raw[8:10])
        start = 10
    else:
        (hlen,) = struct.unpack("<I", raw[8:12])
        start = 12
    header = ast.literal_eval(raw[start : start + hlen].decode("latin1").strip())
    body = raw[start + hlen :]
    count = math.prod(header["shape"])
    values = list(struct.unpack(f"<{count}d", body[: 8 * count]))
    return header, values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parent))
    pin = Path(parser.parse_args().dir)
    failures: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            failures.append(what)

    # 1. SHA256SUMS: every listed file hashes as listed, and the list is the named set
    #    minus the four files recorded as lost.
    sums = {}
    for line in (pin / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.lstrip("*")] = digest
    for name in sorted(sums):
        check(sha256(pin / name) == sums[name], f"{name} matches SHA256SUMS")
    expected = sorted(set(NAMED) - set(LOST_FROM_A))
    check(sorted(sums) == expected, f"SHA256SUMS lists exactly {', '.join(expected)}")
    for name, digest in sorted(SHA256_LITERAL.items()):
        check(sums.get(name) == digest, f"{name} sha256 equals the SOP literal {digest[:12]}")

    # 2. Every named file is either pinned or recorded in PROVENANCE.txt as lost.
    provenance = (pin / "PROVENANCE.txt").read_text()
    check(
        provenance.startswith('Snapshot 2026-09-22T14:34Z of the "data" release of\n'),
        "PROVENANCE.txt opens with the snapshot A line",
    )
    check("(MIT)" in provenance and "Licence: MIT" in provenance, "PROVENANCE.txt states MIT")
    check((pin / "LICENSE").read_text().startswith("MIT License"), "LICENSE is the MIT text")
    for name in LOST_FROM_A:
        pinned = (pin / name).exists()
        check(
            pinned or name in provenance,
            f"{name} {'pinned' if pinned else 'not pinned, and named in PROVENANCE.txt'}",
        )
    print(f"note  snapshot A: {len(sums)} of {len(NAMED)} named files pinned")

    # 3. dp_V_2026.npy: header and values.
    header, flat = load_npy(pin / "dp_V_2026.npy")
    check(header == NPY_HEADER, f"dp_V header is {NPY_HEADER}")
    nh, nd, nt = NPY_HEADER["shape"]

    def v(h: int, d: int, t: int) -> float:
        return flat[(h * nd + d) * nt + t]

    check(
        [round(v(1, 6, t), 6) for t in (0, 1)] == list(V_1_6_ROUNDED),
        f"V[1, 6, 0:2] rounds to {list(V_1_6_ROUNDED)}",
    )
    check(v(1, 6, 2) == V_1_6_2, f"V[1, 6, 2] == {V_1_6_2}")
    mono = sum(
        v(h, d, t + 1) < v(h, d, t) for h in range(nh) for d in range(nd) for t in range(nt - 1)
    )
    check(mono == 0, f"V monotone non-decreasing in t: {mono} violations")
    concave = [
        (h, d)
        for h in range(nh)
        for d in range(nd)
        if v(h, d, 2) - v(h, d, 1) > v(h, d, 1) - v(h, d, 0)
    ]
    hs = {h for h, _ in concave}
    check(
        len(concave) == CONCAVITY_VIOLATIONS and hs == CONCAVITY_H,
        f"concavity fails in {len(concave)} cells, h in {sorted(hs)}",
    )
    worst = max(abs(v(h, d, 0) - v(h, d, 1)) for h in EXTRAS_EQUAL_H for d in range(nd))
    check(
        worst <= sys.float_info.epsilon,
        f"V(h, d, 0) == V(h, d, 1) for h in {list(EXTRAS_EQUAL_H)}: max gap {worst:.1e}",
    )
    check(
        round(100 * v(1, 7, 2), 4) == V_1_7_2_PP and round(100 * v(1, 5, 2), 4) == V_1_5_2_PP,
        f"V(1, 7, 2) = {V_1_7_2_PP} pp and V(1, 5, 2) = {V_1_5_2_PP} pp, not symmetric in d",
    )

    # 4. tier1_results_2026.json.
    res = json.loads((pin / "tier1_results_2026.json").read_text())
    for key, gain in GAINS.items():
        check(res[key]["gain"] == gain, f"{key}.gain == {gain}")
    cap = res["capture_ratio"]
    check(cap["point"] == CAPTURE_POINT, f"capture_ratio.point == {CAPTURE_POINT}")
    check(cap["ci95"] == CAPTURE_CI95, f"capture_ratio.ci95 == {CAPTURE_CI95}")
    check(cap["n_games"] == CAPTURE_N_GAMES, f"capture_ratio.n_games == {CAPTURE_N_GAMES}")
    check(res["dp"]["V2_start_tie"] == V2_START_TIE, f"dp.V2_start_tie == {V2_START_TIE}")

    print(
        f"W5.1 pin check: {'FAIL' if failures else 'OK'}, "
        f"{len(failures)} failed assertion(s), snapshot A in {pin.name}/"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

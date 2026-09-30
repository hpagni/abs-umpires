"""W7.24 and W6.10, synthetic only: the abstract's ledger export.

The base ledger is written by W6.3's and W6.4's own renderers from made-up integers, so it
has their bytes: feed slots first, join slots last. export_numbers.R then exports the
dry run's SYNTHETIC inputs into it. The tests require that:

- both renderers reproduce the exported file byte for byte, because their --check
  compares the whole file and a moved entry would turn W6.3's or W6.4's verify red;
- the Methods counts are P0's, from T1 and T2, and W6.4's N_CALLED and N_GAMES are
  left alone (D-R0-02, D-P4-05, DEV-47);
- D_PRE is printed signed and D_BUF and D_ABS in the contraction orientation;
- a second export changes nothing;
- before prereg-v1, a fit-result input is refused with exit 4 (GD-12).

No real data file is read and no real number is written.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "tools" / "comms" / "export_numbers.R"
RSCRIPT = shutil.which("Rscript")
pytestmark = pytest.mark.skipif(RSCRIPT is None, reason="Rscript is not on PATH")


def _module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ops" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FEED = _module("sprint_feed_checkpoint")
JOIN = _module("sprint_join_checkpoint")


def _export(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([RSCRIPT, str(EXPORT), *args], capture_output=True, text=True)


def _entries(text: str) -> dict:
    return {e["slot"]: e for e in json.loads(text)["entries"]}


@pytest.fixture(scope="module")
def dry(tmp_path_factory):
    d = tmp_path_factory.mktemp("abstract_ledger")
    gen = ROOT / "tools" / "comms" / "synthetic_abstract_inputs.py"
    subprocess.run([sys.executable, str(gen), "--out", str(d)], check=True, capture_output=True)
    feed = {s: 101 + i for i, s in enumerate(FEED.SLOT_ORDER)}
    join = {s: 201 + i for i, s in enumerate(JOIN.SLOT_ORDER)}
    base = json.loads(FEED.render_ledger({"_what": "SYNTHETIC base", "entries": []}, feed))
    base_path = d / "numbers-base.SYNTHETIC.json"
    base_path.write_text(JOIN.render_ledger(base, join), encoding="utf-8")
    out = d / "numbers.SYNTHETIC.json"
    r = _export(
        "--inputs",
        str(d / "in"),
        "--base",
        str(base_path),
        "--out",
        str(out),
        "--tag",
        "SYNTHETIC",
        "--synthetic",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return d, out, feed, join


def test_feed_and_join_renderers_reproduce_the_export(dry):
    _, out, feed, join = dry
    text = out.read_text(encoding="utf-8")
    assert JOIN.render_ledger(json.loads(text), join) == text
    assert FEED.render_ledger(json.loads(text), feed) == text


def test_exported_entries_sit_between_feed_and_join(dry):
    _, out, _, _ = dry
    slots = [e["slot"] for e in json.loads(out.read_text(encoding="utf-8"))["entries"]]
    nf, nj = len(FEED.SLOT_ORDER), len(JOIN.SLOT_ORDER)
    assert slots[:nf] == list(FEED.SLOT_ORDER)
    assert slots[-nj:] == list(JOIN.SLOT_ORDER)
    assert {"D_BUF", "N_CALLED_P0", "N_CHAL", "T1_ABS_AREA"} <= set(slots[nf:-nj])


def test_methods_counts_are_p0_and_w64_counts_are_untouched(dry):
    _, out, _, join = dry
    e = _entries(out.read_text(encoding="utf-8"))
    assert (e["N_CALLED_P0"]["value"], e["N_GAMES_P0"]["value"], e["N_CHAL"]["value"]) == (
        1000000,
        10000,
        5000,
    )
    assert e["N_CALLED_P0"]["source"].endswith("T1_sample.SYNTHETIC.csv")
    assert e["N_CHAL"]["source"].endswith("T2_zone_gate.SYNTHETIC.csv")
    assert (e["N_CALLED"]["value"], e["N_GAMES"]["value"]) == (join["N_CALLED"], join["N_GAMES"])
    slots = json.loads((ROOT / "tools" / "comms" / "abstract_slots.json").read_text())["slots"]
    assert slots["N_CALLED"]["ledger_slot"] == "N_CALLED_P0"
    assert slots["N_GAMES"]["ledger_slot"] == "N_GAMES_P0"


def test_orientation_of_the_results_slots(dry):
    _, out, _, _ = dry
    e = _entries(out.read_text(encoding="utf-8"))
    assert "print_contraction" not in e["D_PRE"]
    assert e["D_PRE"]["print"] == {"point": "-1.0", "lo95": "-2.0", "hi95": "0.0"}
    assert e["D_BUF"]["print_contraction"] == {"point": "10.0", "lo95": "5.0", "hi95": "15.0"}


def test_a_second_export_changes_nothing(dry):
    d, out, _, _ = dry
    before = out.read_bytes()
    r = _export(
        "--inputs",
        str(d / "in"),
        "--base",
        str(out),
        "--out",
        str(out),
        "--tag",
        "SYNTHETIC",
        "--synthetic",
    )
    assert r.returncode == 0, r.stderr
    assert out.read_bytes() == before


def test_list_inputs_names_every_input():
    r = _export("--list-inputs")
    assert r.returncode == 0
    listed = r.stdout.split()
    assert "out/ch1/tab/T1_sample.csv" in listed and "out/ch1/tab/T2_zone_gate.csv" in listed
    assert "out/ch1/tab/T5_placebos.csv" in listed
    assert "out/ch1/tab/T3_estimands.csv" in listed  # AREA_2022..AREA_2026, the owner-voice variant
    assert len(listed) == 9


def test_gd12_refuses_a_fit_result_before_the_tag(dry, tmp_path):
    tag = "prereg-v1"
    anc = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", tag, "HEAD"], capture_output=True
    )
    if anc.returncode == 0:
        pytest.skip(f"HEAD descends from {tag}; the refusal no longer applies")
    d, _, _, _ = dry
    src = d / "in" / "out" / "tables" / "abstract_slots_ch1.SYNTHETIC.csv"
    (tmp_path / "out" / "tables").mkdir(parents=True)
    shutil.copy(src, tmp_path / "out" / "tables" / "abstract_slots_ch1.csv")
    out = tmp_path / "numbers.json"
    r = _export(
        "--inputs",
        str(tmp_path),
        "--base",
        str(d / "numbers-base.SYNTHETIC.json"),
        "--out",
        str(out),
    )
    assert r.returncode == 4, r.stdout + r.stderr
    assert "REFUSED (GD-12)" in r.stderr
    assert not out.exists()

#!/usr/bin/env python3
"""quality/write_receipt.py -- the step registry reader and the receipt writer.

Owner: SOP step W9.1, fleet phase 01. SOP section 0.2: test evidence is a receipt, and
receipts are verified, not trusted. Receipts live at quality/receipts/<step-id>.json and
carry at least the step id, the command, the exit code, the duration, the git sha and a
Madrid-stamped timestamp.

Standard library only, and Python 3.9 compatible, because scripts/prove.sh calls it with
the system python3 before any virtual environment is guaranteed to exist.

Modes:
  --step ID --cmd CMD --exit N --duration S   write quality/receipts/ID.json
  --field NAME --step ID                      print one registry field, for prove.sh
  --registry                                  dump the registry, unit-separated, for prove.sh
  --check                                     validate the registry, SOP W9.1
  --selftest                                  write and read back a receipt in a temp dir
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEPS = os.path.join(ROOT, "quality", "steps.yml")
RECEIPTS = os.path.join(ROOT, "quality", "receipts")
PLACEHOLDER = "ABSUMP" + "_PLACEHOLDER"

# The twenty-one steps fleet phase 01 owns, and the three ids it registers as retired.
PHASE01 = [
    "W1.1",
    "W1.2",
    "W1.3",
    "W1.4",
    "W1.5",
    "W1.6",
    "W1.7",
    "W1.8",
    "W1.12",
    "W1.13",
    "W1.14",
    "W1.16",
    "W2.1",
    "W2.2",
    "W2.3",
    "W2.4",
    "W6.1",
    "W9.1",
    "W9.2",
    "W9.3",
    "W9.7",
]
RETIRED = ["W3.0", "W3.1", "W7.11"]

ID_RE = re.compile(r"^W\d+\.\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ----------------------------------------------------------------- the small YAML reader
class RegistryError(Exception):
    pass


def _scalar(raw, lineno):
    """Parse one scalar: bare, 'single-quoted' or "double-quoted"."""
    raw = raw.strip()
    if raw == "":
        return ""
    if raw[0] == "'":
        if len(raw) < 2 or raw[-1] != "'":
            raise RegistryError(f"line {lineno}: unterminated single-quoted scalar")
        return raw[1:-1].replace("''", "'")
    if raw[0] == '"':
        if len(raw) < 2 or raw[-1] != '"':
            raise RegistryError(f"line {lineno}: unterminated double-quoted scalar")
        body, out, i = raw[1:-1], [], 0
        while i < len(body):
            c = body[i]
            if c == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                i += 2
                continue
            out.append(c)
            i += 1
        return "".join(out)
    if raw[0] in "[]{}|>&*!%@`":
        raise RegistryError(
            f"line {lineno}: {raw[0]!r} is outside the YAML subset this registry uses"
        )
    if raw in ("true", "false"):
        return raw == "true"
    if re.match(r"^-?\d+$", raw):
        return int(raw)
    return raw


def _split(text, lineno):
    if ":" not in text:
        raise RegistryError(f"line {lineno}: expected `key: value`, got {text!r}")
    key, _, value = text.partition(":")
    key = key.strip()
    if not re.match(r"^[a-z_]+$", key):
        raise RegistryError(f"line {lineno}: {key!r} is not a registry field name")
    return key, _scalar(value, lineno)


def load_registry(path=STEPS):
    """Read quality/steps.yml into a list of dicts. Strict: it raises, it never guesses."""
    if not os.path.exists(path):
        raise RegistryError(f"{path} does not exist")
    records, current = [], None
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh.read().splitlines(), start=1):
            if line.strip() == "" or line.lstrip().startswith("#"):
                continue
            if line.startswith("- "):
                current = {"_line": lineno}
                records.append(current)
                key, value = _split(line[2:], lineno)
                current[key] = value
            elif line.startswith("  ") and not line[2:3].isspace():
                if current is None:
                    raise RegistryError(f"line {lineno}: continuation before any record")
                key, value = _split(line[2:], lineno)
                if key in current:
                    raise RegistryError(f"line {lineno}: field {key!r} repeated")
                current[key] = value
            else:
                raise RegistryError(
                    f"line {lineno}: indentation is outside the YAML subset: {line!r}"
                )
    for rec in records:
        rec["needs"] = [p.strip() for p in str(rec.get("needs", "")).split(",") if p.strip()]
        rec["retired"] = bool(rec.get("retired", False))
    return records


def find(step, records=None):
    for rec in records if records is not None else load_registry():
        if rec.get("id") == step:
            return rec
    return None


# W1.14's stubs open a comment line with the marker and a full stop. Prose that merely
# names the marker, as this file and steps.yml do, never matches.
STUB_RE = re.compile(r"(?m)^#\s*" + PLACEHOLDER + r"\.")


def missing_needs(rec, root=ROOT):
    """Return the needed paths that are absent or still carry the W1.14 placeholder."""
    out = []
    for rel in rec.get("needs", []):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            out.append(rel)
            continue
        try:
            with open(path, "rb") as fh:
                head = fh.read(4096).decode("utf-8", "ignore")
            if STUB_RE.search(head):
                out.append(rel + " (placeholder)")
        except (OSError, ValueError):
            pass
    return out


# --------------------------------------------------------------------------- the receipt
def madrid_now():
    """Madrid-stamped timestamp. Never a hand-computed offset from UTC."""
    env = dict(os.environ, TZ="Europe/Madrid")
    return subprocess.check_output(["date", "+%Y-%m-%d %H:%M:%S %Z"], env=env).decode().strip()


def _git(args, root=ROOT):
    try:
        return (
            subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, OSError):
        return ""


def write_receipt(step, cmd, exit_code, duration, out_dir=RECEIPTS, root=ROOT):
    rec = find(step) or {}
    expect = rec.get("expect_exit", 0)
    log = os.path.join("quality", "receipts", f"{step}.log")
    receipt = {
        "step": step,
        "title": rec.get("title", ""),
        "owner": rec.get("owner", ""),
        "cmd": cmd,
        "exit": exit_code,
        "expect_exit": expect,
        "status": "PASS" if exit_code == expect else "FAIL",
        "duration_s": duration,
        "git_sha": _git(["rev-parse", "HEAD"], root),
        "git_branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "git_dirty": _git(["status", "--porcelain"], root) != "",
        "timestamp_madrid": madrid_now(),
        "log": log if os.path.exists(os.path.join(root, log)) else None,
        "host": os.uname().nodename,
        "schema": "absump/receipt/1",
    }
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(out_dir, f"{step}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"receipt {step} {receipt['status']} exit={exit_code} {duration}s -> {path}")
    return receipt


# ----------------------------------------------------------------------------- the check
def check(records=None):
    """Validate the registry. Returns a list of problems, empty when the registry is sound."""
    problems = []
    try:
        records = records if records is not None else load_registry()
    except RegistryError as exc:
        return [f"quality/steps.yml does not parse: {exc}"]

    seen = {}
    for rec in records:
        step = rec.get("id")
        line = rec.get("_line")
        if not step:
            problems.append(f"line {line}: record has no id")
            continue
        if not ID_RE.match(str(step)):
            problems.append(f"line {line}: {step!r} is not a W<workstream>.<number> id")
            continue
        if step in seen:
            problems.append(f"{step} registered twice, lines {seen[step]} and {line}")
            continue
        seen[step] = line
        workstream = str(step).split(".")[0]
        if rec.get("owner") != workstream:
            problems.append("{}: owner {!r} does not match the id".format(step, rec.get("owner")))
        if not rec.get("title"):
            problems.append(f"{step}: no title")
        if rec["retired"]:
            if rec.get("verify"):
                problems.append(f"{step}: a retired step carries no verify command")
            if not rec.get("reason"):
                problems.append(f"{step}: retired without a reason")
            if not DATE_RE.match(str(rec.get("date", ""))):
                problems.append(f"{step}: retired without a YYYY-MM-DD date")
        else:
            if not str(rec.get("verify", "")).strip():
                problems.append(f"{step}: no verify command")
            if rec.get("expect_exit") != 0:
                problems.append(
                    "{}: expect_exit is {!r}, not 0".format(step, rec.get("expect_exit"))
                )

    for step in PHASE01:
        rec = seen.get(step)
        if rec is None:
            problems.append(f"{step} is a phase 01 step and is not registered")
        elif find(step, records)["retired"]:
            problems.append(f"{step} is a live phase 01 step and is marked retired")
    for step in RETIRED:
        rec = find(step, records)
        if rec is None:
            problems.append(f"{step} must be registered as retired and is absent")
        elif not rec["retired"]:
            problems.append(f"{step} must be marked retired")
    return problems


def selftest():
    """Write a receipt into a temp dir and read it back. Proves the writer runs."""
    with tempfile.TemporaryDirectory() as tmp:
        rec = write_receipt("W9.1", "true", 0, 0, out_dir=tmp)
        with open(os.path.join(tmp, "W9.1.json"), encoding="utf-8") as fh:
            back = json.load(fh)
    for field in ("step", "cmd", "exit", "duration_s", "git_sha", "timestamp_madrid"):
        if field not in back:
            raise SystemExit(f"selftest: receipt is missing {field}")
    if back["step"] != "W9.1" or back["exit"] != 0 or back["status"] != "PASS":
        raise SystemExit("selftest: receipt does not read back as written")
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+$", back["timestamp_madrid"]):
        raise SystemExit(
            "selftest: timestamp is not Madrid-stamped: {!r}".format(back["timestamp_madrid"])
        )
    print("selftest OK: receipt written and read back, stamped {}".format(rec["timestamp_madrid"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="the step registry reader and receipt writer")
    ap.add_argument("--step")
    ap.add_argument("--cmd")
    ap.add_argument("--exit", dest="exit_code", type=int)
    ap.add_argument("--duration", type=int, default=0)
    ap.add_argument("--field")
    ap.add_argument("--registry", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        selftest()
        return 0

    if args.check:
        problems = check()
        for line in problems:
            sys.stderr.write(f"steps.yml: {line}\n")
        if problems:
            return 1
        records = load_registry()
        live = [r for r in records if not r["retired"]]
        print(
            f"steps.yml OK: {len(records)} registered, {len(live)} live, "
            f"{len(records) - len(live)} retired"
        )
        return 0

    if args.registry:
        # ASCII unit separator, not a tab: the shell reader in scripts/prove.sh must see
        # empty fields as empty, and a tab in IFS collapses runs of tabs into one.
        for rec in load_registry():
            sys.stdout.write(
                "\x1f".join(
                    [
                        str(rec.get("id", "")),
                        str(rec.get("owner", "")),
                        "1" if rec["retired"] else "0",
                        str(rec.get("expect_exit", 0)),
                        ", ".join(missing_needs(rec)),
                        str(rec.get("reason", rec.get("title", ""))),
                        str(rec.get("verify", "")),
                        str(rec.get("pending_owner", "")),
                    ]
                )
                + "\n"
            )
        return 0

    if args.field:
        if not args.step:
            sys.stderr.write("--field needs --step\n")
            return 2
        rec = find(args.step)
        if rec is None:
            sys.stderr.write(f"{args.step} is not registered in quality/steps.yml\n")
            return 3
        value = rec.get(args.field, "")
        print(", ".join(value) if isinstance(value, list) else value)
        return 0

    if args.step and args.exit_code is not None:
        write_receipt(args.step, args.cmd or "", args.exit_code, args.duration)
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RegistryError as exc:
        sys.stderr.write(f"quality/steps.yml: {exc}\n")
        sys.exit(4)

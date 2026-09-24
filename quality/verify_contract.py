#!/usr/bin/env python3
"""quality/verify_contract.py -- the warehouse contract checker, SOP step W9.4.

SOP section 2.6 states one set of table names, one grain and one key per table,
and the required columns of each. This script checks the built warehouse against
that statement, table by table, and exits non-zero when the warehouse and the
contract disagree.

WHERE THE NAMES COME FROM. Every table name, column name, key and edge is read
from quality/warehouse_contract.yml. This file carries none of its own. A table
renamed in the contract is a table renamed in the check, and a check that passes
because its own copy of a name drifted is not possible.

That has a second effect worth stating plainly. GD-04 rule 3 fails a read of a
raw fact table that the enclosing statement does not restrict to the open label.
The reads this script issues are built from the contract at run time, so no such
read is written down here for the scan to find. The reads are also deliberately
unrestricted: DT-18 and DT-19 are assertions about the whole table, and a key
check that skipped part of the table would assert nothing about it. The control
on held-out rows is the seal itself, not this script, and this script writes no
row anywhere. The deviation is recorded in the W9.4 return and in docs/warehouse.md.

THE CHECKS.

  C1  every contracted table exists in the marts schema and is a table
  C2  every required column is present, or is listed as deferred with an owner
  C3  DT-18, each declared key is unique, 0 duplicate groups
  C4  DT-19, each declared edge has 0 orphans
  C5  each open view returns exactly the open rows of its base table
  C6  the layers materialise as section 2.6 states
  C7  model code reads only the open views
  C8  every declared vocabulary holds

C7 runs without a warehouse. So does the model-file half of C1. With no
warehouse file on disk the rest report SKIP and the exit code is 0, which is how
a clean clone with no data proves the half of the contract that is on disk.

USAGE
  uv run --locked python quality/verify_contract.py
  uv run --locked python quality/verify_contract.py --json
  uv run --locked python quality/verify_contract.py --database <duckdb file>

EXIT CODES
  0  no check failed
  1  at least one check failed
  2  the contract file or the warehouse could not be read
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "quality" / "warehouse_contract.yml"

PASS = "PASS"
FAIL = "FAIL"
DEFER = "DEFERRED"
INFO = "INFO"
SKIP = "SKIP"

# The suffixes C7 will not read, whatever the contract lists. A compiled or
# binary file carries no statement a line scan can read.
_TEXT_ERRORS = "replace"


def quote(name: str) -> str:
    """A DuckDB identifier, quoted, with any embedded quote doubled."""
    return '"' + str(name).replace('"', '""') + '"'


def qualified(schema: str, name: str) -> str:
    return quote(schema) + "." + quote(name)


def literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


class Report:
    """One line per check, in the order the checks ran."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, check: str, status: str, detail: str, **extra) -> None:
        row = {"check": check, "status": status, "detail": detail}
        row.update(extra)
        self.rows.append(row)

    @property
    def failures(self) -> list[dict]:
        return [row for row in self.rows if row["status"] == FAIL]

    def counts(self) -> dict:
        out: dict = {}
        for row in self.rows:
            out[row["status"]] = out.get(row["status"], 0) + 1
        return out

    def text(self) -> str:
        width = max([len(row["check"]) for row in self.rows] + [4])
        lines = []
        for row in self.rows:
            lines.append(
                "{:<{w}}  {:<8}  {}".format(row["check"], row["status"], row["detail"], w=width)
            )
        return "\n".join(lines)


def load_contract(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        contract = yaml.safe_load(handle)
    for key in ("tables", "views", "references", "target", "layers"):
        if key not in contract:
            raise SystemExit(f"verify-contract: {path} has no {key} block")
    return contract


def required_columns(contract: dict, table: str) -> list[str]:
    """The required columns of one table, with an inherited list expanded."""
    spec = contract["tables"][table]
    columns: list[str] = []
    parent = spec.get("inherits")
    if parent:
        columns.extend(required_columns(contract, parent))
        columns.extend(contract["tables"][parent]["key"])
    columns.extend(spec["key"])
    columns.extend(spec.get("columns", []))
    seen: set[str] = set()
    ordered: list[str] = []
    for column in columns:
        if column not in seen:
            seen.add(column)
            ordered.append(column)
    return ordered


# ------------------------------------------------------------------ C1 static half
def check_models(contract: dict, report: Report) -> None:
    """Every contracted table and view names a dbt model, and the file is there."""
    missing = []
    counted = 0
    for block in ("tables", "views"):
        for name, spec in sorted(contract[block].items()):
            model = spec.get("model")
            if not model:
                missing.append(name + " names no model")
                continue
            counted += 1
            if not (ROOT / model).is_file():
                missing.append(name + " -> " + model)
    if missing:
        report.add("C1 models", FAIL, "model file absent: " + "; ".join(sorted(missing)))
    else:
        report.add("C1 models", PASS, f"{counted} contracted models on disk")


# ------------------------------------------------------------------ C7 the read rule
def check_read_rule(contract: dict, report: Report) -> None:
    """Model code reads only the open views.

    A read is FROM, JOIN, a dbt ref or source, read_parquet or a .table call
    that reaches a contracted fact table by name. The read is forgiven when the
    same statement restricts it to the open label, which is the one restriction
    that makes the read safe.
    """
    rule = contract.get("open_view_only") or {}
    paths = rule.get("paths") or []
    suffixes = tuple(rule.get("suffixes") or [])
    allow = set(rule.get("allow") or [])
    label_column = contract["open_label_column"]
    label = contract["open_label"]

    names = sorted(contract["tables"], key=len, reverse=True)
    reader = r"(?:\bFROM\b|\bJOIN\b|\bref\s*\(|\bsource\s*\(|read_parquet|\.table\s*\()"
    patterns = [
        (
            name,
            re.compile(
                reader + r"[^;]{0,120}?(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])",
                re.IGNORECASE | re.DOTALL,
            ),
        )
        for name in names
    ]
    qualifies = re.compile(
        re.escape(label_column)
        + r"\b\s*(?:=|==|IN|in)\s*\(?\s*['\"]"
        + re.escape(label)
        + r"['\"]",
        re.IGNORECASE,
    )

    scanned = 0
    hits: list[str] = []
    for prefix in paths:
        base = ROOT / prefix
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or (suffixes and path.suffix not in suffixes):
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative in allow:
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8", errors=_TEXT_ERRORS)
            for name, pattern in patterns:
                for match in pattern.finditer(text):
                    end = text.find(";", match.end())
                    stop = len(text) if end < 0 else end
                    tail = text[match.end() : min(stop, match.end() + 1000)]
                    if qualifies.search(match.group(0)) or qualifies.search(tail):
                        continue
                    line = text.count("\n", 0, match.start()) + 1
                    hits.append(f"{relative}:{line} reads {name}")
    if hits:
        report.add("C7 read rule", FAIL, "; ".join(sorted(set(hits))[:8]))
    else:
        report.add(
            "C7 read rule",
            PASS,
            f"{scanned} files under {len(paths)} paths, 0 direct fact-table reads",
        )


# ------------------------------------------------------------------ the warehouse
def connect(database: Path, wait_seconds: int = 60):
    """A read-only connection. A concurrent dbt build holds the write lock, so
    the connection is retried before it is called a failure."""
    import duckdb

    deadline = time.time() + wait_seconds
    last = None
    while True:
        try:
            return duckdb.connect(str(database), read_only=True)
        except Exception as error:
            last = error
            if time.time() >= deadline:
                raise SystemExit(
                    f"verify-contract: cannot open {database} read-only"
                    f" after {wait_seconds} s: {last}"
                ) from last
            time.sleep(2)


def catalogue(connection, schemas: dict) -> dict:
    wanted = sorted(set(schemas.values()))
    holder = ", ".join(literal(name) for name in wanted)
    tables = {
        (row[0], row[1])
        for row in connection.execute(
            "select schema_name, table_name from duckdb_tables()"
            f" where not internal and schema_name in ({holder})"
        ).fetchall()
    }
    views = {
        (row[0], row[1], row[2])
        for row in connection.execute(
            "select schema_name, view_name, sql from duckdb_views()"
            f" where not internal and schema_name in ({holder})"
        ).fetchall()
    }
    columns: dict = {}
    for schema, table, column in connection.execute(
        "select schema_name, table_name, column_name from duckdb_columns()"
        f" where internal = false and schema_name in ({holder})"
    ).fetchall():
        columns.setdefault((schema, table), []).append(column)
    return {"tables": tables, "views": views, "columns": columns}


def check_tables(contract, cat, report) -> set:
    marts = contract["target"]["schemas"]["marts"]
    view_names = {name for schema, name, _ in cat["views"] if schema == marts}
    present, missing, wrong = [], [], []
    for name in sorted(contract["tables"]):
        if (marts, name) in cat["tables"]:
            present.append(name)
        elif name in view_names:
            wrong.append(name + " is a view")
        else:
            missing.append(name)
    if missing or wrong:
        report.add(
            "C1 tables",
            FAIL,
            "; ".join(["absent: " + n for n in missing] + wrong),
        )
    else:
        report.add(
            "C1 tables",
            PASS,
            "{}/{} contracted tables present in {} as tables".format(
                len(present), len(contract["tables"]), marts
            ),
        )
    others = sorted(
        name for schema, name in cat["tables"] if schema == marts and name not in contract["tables"]
    )
    if others:
        report.add("C1 other marts", INFO, "not gated by section 2.6: " + ", ".join(others))
    return set(present)


def check_columns(contract, cat, present, report) -> None:
    marts = contract["target"]["schemas"]["marts"]
    deferred_spec = contract.get("deferred") or {}
    required_total = 0
    missing: list[str] = []
    deferred_open: list[str] = []
    arrived: list[str] = []
    for table in sorted(present):
        have = {c.lower() for c in cat["columns"].get((marts, table), [])}
        deferred = deferred_spec.get(table) or {}
        for column in required_columns(contract, table):
            required_total += 1
            if column.lower() in have:
                if column in deferred:
                    arrived.append(table + "." + column)
                continue
            if column in deferred:
                deferred_open.append(
                    "{}.{} (owner {})".format(table, column, deferred[column].get("owner", "?"))
                )
                continue
            missing.append(table + "." + column)
    for table, columns in sorted(deferred_spec.items()):
        if table not in present:
            continue
        for column in sorted(columns):
            if column not in required_columns(contract, table):
                missing.append(f"{table}.{column} is deferred but not in the contract")
    if missing:
        report.add("C2 columns", FAIL, "; ".join(sorted(missing)[:12]))
    else:
        report.add(
            "C2 columns",
            PASS,
            f"{required_total - len(deferred_open)} required columns present"
            f" across {len(present)} tables",
        )
    if deferred_open:
        report.add("C2 deferred", DEFER, "; ".join(sorted(deferred_open)))
    if arrived:
        report.add(
            "C2 deferred arrived",
            INFO,
            "listed as deferred and now present, trim the block: " + "; ".join(sorted(arrived)),
        )


def check_keys(contract, connection, present, report) -> None:
    """DT-18. Each declared key is unique, 0 duplicate groups."""
    marts = contract["target"]["schemas"]["marts"]
    exceptions = contract.get("key_exceptions") or {}
    failures: list[str] = []
    notes: list[str] = []
    checked = 0
    for table in sorted(present):
        key = contract["tables"][table]["key"]
        target = qualified(marts, table)
        columns = ", ".join(quote(column) for column in key)
        exception = exceptions.get(table)
        scope = exception.get("scope") if exception else None
        where = " where " + scope if scope else ""
        groups = connection.execute(
            f"select count(*) from (select {columns} from {target}{where}"
            f" group by {columns} having count(*) > 1)"
        ).fetchone()[0]
        checked += 1
        if groups:
            failures.append(
                "{} has {} duplicate group(s) on ({})".format(table, groups, ", ".join(key))
            )
            continue
        if not exception:
            continue
        # The exception is allowed only where a key column is null.
        populated = " and ".join(f"{quote(column)} is not null" for column in key)
        outside = connection.execute(
            f"select count(*) from (select {columns} from {target} where not ({scope})"
            f" group by {columns} having count(*) > 1 and ({populated}))"
        ).fetchone()[0]
        if outside:
            failures.append(
                f"{table} has {outside} duplicate group(s) outside its scope"
                " with every key column set"
            )
        surrogate = exception.get("surrogate") or []
        if not surrogate:
            failures.append(f"{table} declares a key exception with no surrogate")
            continue
        scols = ", ".join(quote(column) for column in surrogate)
        dupes, nulls, total = connection.execute(
            f"select count(*) - count(distinct ({scols})),"
            f" count(*) filter (where {quote(surrogate[0])} is null), count(*) from {target}"
        ).fetchone()
        if dupes or nulls:
            failures.append(
                "{} surrogate ({}) has {} repeat(s) and {} null(s)".format(
                    table, ", ".join(surrogate), dupes, nulls
                )
            )
        else:
            outside_rows = connection.execute(
                f"select count(*) from {target} where not ({scope})"
            ).fetchone()[0]
            notes.append(
                "{}: declared key unique where {}; {} of {} rows outside that scope,"
                " surrogate ({}) unique on all".format(
                    table, scope, outside_rows, total, ", ".join(surrogate)
                )
            )
    if failures:
        report.add("C3 keys DT-18", FAIL, "; ".join(failures))
    else:
        report.add("C3 keys DT-18", PASS, f"{checked}/{checked} declared keys unique, 0 dupes")
    for note in notes:
        report.add("C3 key exception", INFO, note)


def check_references(contract, connection, present, report) -> None:
    """DT-19. Each declared edge has 0 orphans."""
    marts = contract["target"]["schemas"]["marts"]
    failures: list[str] = []
    ran = 0
    skipped: list[str] = []
    for edge in contract["references"]:
        child, parent = edge["child"], edge["parent"]
        if child["table"] not in present or parent["table"] not in present:
            skipped.append(edge["name"])
            continue
        on = " and ".join(
            f"c.{quote(a)} = p.{quote(b)}"
            for a, b in zip(child["columns"], parent["columns"], strict=True)
        )
        if edge.get("null_child_keys") == "allow":
            guard = " and ".join(f"c.{quote(a)} is not null" for a in child["columns"])
        else:
            guard = "true"
        orphans = connection.execute(
            "select count(*) from {ctbl} c where {guard} and not exists"
            " (select 1 from {ptbl} p where {on})".format(
                ctbl=qualified(marts, child["table"]),
                ptbl=qualified(marts, parent["table"]),
                guard=guard,
                on=on,
            )
        ).fetchone()[0]
        ran += 1
        if orphans:
            failures.append("{}: {} orphan(s)".format(edge["name"], orphans))
    if failures:
        report.add("C4 refs DT-19", FAIL, "; ".join(failures))
    else:
        sop = sum(1 for edge in contract["references"] if edge.get("sop"))
        report.add(
            "C4 refs DT-19",
            PASS,
            f"{ran} edges, 0 orphans, {sop} of them named by the SOP",
        )
    if skipped:
        report.add("C4 refs skipped", FAIL, "table absent for: " + ", ".join(skipped))


def check_views(contract, connection, cat, present, report) -> None:
    """Each open view returns exactly the open rows of its base table.

    Two clauses, because either one alone can pass on a warehouse that holds no
    held-out row. The counts must agree, and the stored view definition must
    name the base table and carry the restriction to the open label. A view with
    no restriction at all matches on counts today and is caught by the second.
    """
    marts = contract["target"]["schemas"]["marts"]
    label_column = contract["open_label_column"]
    label = contract["open_label"]
    stored = {name: sql for schema, name, sql in cat["views"] if schema == marts}
    restriction = re.compile(
        re.escape(label_column) + r"\b\s*(?:=|IN)\s*\(?\s*['\"]" + re.escape(label) + r"['\"]",
        re.IGNORECASE,
    )
    failures: list[str] = []
    ran = 0
    for name in sorted(contract["views"]):
        base = contract["views"][name]["base"]
        if name not in stored:
            failures.append(name + " is not a view in " + marts)
            continue
        if base not in present:
            failures.append(name + " has no base table " + base)
            continue
        sql = stored[name]
        if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(base) + r"(?![A-Za-z0-9_])", sql):
            failures.append(name + " does not read " + base)
        if not restriction.search(sql):
            failures.append(f"{name} has no restriction to {label_column} = {literal(label)}")
        seen = connection.execute(f"select count(*) from {qualified(marts, name)}").fetchone()[0]
        expected = connection.execute(
            f"select count(*) from {qualified(marts, base)}"
            f" where {quote(label_column)} = {literal(label)}"
        ).fetchone()[0]
        ran += 1
        if seen != expected:
            failures.append(f"{name}: {seen} rows, base gives {expected}")
    if failures:
        report.add("C5 open views", FAIL, "; ".join(failures))
    else:
        report.add(
            "C5 open views",
            PASS,
            "{}/{} views restrict to their base and agree on row counts".format(
                ran, len(contract["views"])
            ),
        )


def check_layers(contract, cat, report) -> None:
    """staging and intermediate materialise as views, marts as tables."""
    schemas = contract["target"]["schemas"]
    tables = {(schema, name) for schema, name in cat["tables"]}
    views = {(schema, name) for schema, name, _ in cat["views"]}
    failures: list[str] = []
    summary: list[str] = []
    for layer in ("staging", "intermediate"):
        schema = schemas[layer]
        directory = ROOT / "dbt" / "models" / layer
        models = sorted(path.stem for path in directory.glob("*.sql")) if directory.is_dir() else []
        as_view = [m for m in models if (schema, m) in views]
        as_table = [m for m in models if (schema, m) in tables]
        absent = [m for m in models if m not in as_view and m not in as_table]
        if as_table:
            failures.append(
                "{} models materialised as tables: {}".format(layer, ", ".join(as_table))
            )
        if absent:
            failures.append("{} models not built: {}".format(layer, ", ".join(absent)))
        summary.append(f"{layer} {len(as_view)}/{len(models)} views")
    marts = schemas["marts"]
    marts_dir = ROOT / "dbt" / "models" / "marts"
    marts_models = (
        sorted(path.stem for path in marts_dir.glob("*.sql")) if marts_dir.is_dir() else []
    )
    uncontracted = [
        m for m in marts_models if m not in contract["tables"] and m not in contract["views"]
    ]
    summary.append(
        "marts {} contracted tables and {} contracted views of {} models".format(
            len(contract["tables"]), len(contract["views"]), len(marts_models)
        )
    )
    if failures:
        report.add("C6 layers", FAIL, "; ".join(failures))
    else:
        report.add("C6 layers", PASS, ", ".join(summary))
    if uncontracted:
        shaped = []
        for name in uncontracted:
            kind = (
                "table"
                if (marts, name) in tables
                else "view"
                if (marts, name) in views
                else "absent"
            )
            shaped.append(f"{name} ({kind})")
        report.add("C6 other marts", INFO, "outside section 2.6: " + ", ".join(shaped))


def check_vocabularies(contract, connection, present, report) -> None:
    marts = contract["target"]["schemas"]["marts"]
    failures: list[str] = []
    ran = 0
    for table in sorted(present):
        for column, allowed in (contract["tables"][table].get("accepted_values") or {}).items():
            rows = connection.execute(
                "select distinct {col} from {tbl} where {col} is not null".format(
                    col=quote(column), tbl=qualified(marts, table)
                )
            ).fetchall()
            ran += 1
            extra = sorted({str(row[0]) for row in rows} - {str(value) for value in allowed})
            if extra:
                failures.append("{}.{} carries {}".format(table, column, ", ".join(extra)))
    if failures:
        report.add("C8 vocabularies", FAIL, "; ".join(failures))
    elif ran:
        report.add("C8 vocabularies", PASS, f"{ran} declared vocabulary holds")


def row_counts(contract, connection, present, report) -> None:
    marts = contract["target"]["schemas"]["marts"]
    parts = []
    for table in sorted(present):
        count = connection.execute(f"select count(*) from {qualified(marts, table)}").fetchone()[0]
        parts.append(f"{table} {count:,}")
    report.add("rows", INFO, "; ".join(parts))


def _dev_database(contract):
    """The dev target named by the contract, with a layout token resolved.

    src/absump/paths.py is where the repository layout is written down, and
    tests/unit/test_paths.py holds it to one copy: the warehouse file may be
    spelled there and nowhere else. The contract therefore names it as the
    token `{duckdb}`, which is looked up in absump.paths here. A literal path
    still works, so an operator can point the checker at a copy by hand.
    """
    raw = str(contract["target"]["dev_database"]).strip()
    if raw.startswith("{") and raw.endswith("}"):
        from absump.paths import templates

        key = raw[1:-1]
        try:
            return ROOT / templates()[key]
        except KeyError:
            raise SystemExit(
                f"verify_contract: the contract names {raw}, which absump.paths does not define"
            ) from None
    return ROOT / raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="the warehouse contract, SOP section 2.6")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument(
        "--database", default=None, help="the DuckDB file, default from the contract"
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--wait", type=int, default=60, help="seconds to wait for the write lock")
    args = parser.parse_args(argv)

    contract_path = Path(args.contract)
    if not contract_path.is_file():
        print(f"verify-contract: no contract at {contract_path}", file=sys.stderr)
        return 2
    contract = load_contract(contract_path)
    database = Path(args.database) if args.database else _dev_database(contract)

    report = Report()
    check_models(contract, report)
    check_read_rule(contract, report)

    if not database.is_file():
        report.add(
            "warehouse",
            SKIP,
            f"no warehouse at {database}; the checks that read it did not run."
            " Build it with make warehouse.",
        )
        for name in (
            "C1 tables",
            "C2 columns",
            "C3 keys DT-18",
            "C4 refs DT-19",
            "C5 open views",
            "C6 layers",
            "C8 vocabularies",
        ):
            report.add(name, SKIP, "needs the warehouse")
    else:
        connection = connect(database, wait_seconds=args.wait)
        try:
            cat = catalogue(connection, contract["target"]["schemas"])
            present = check_tables(contract, cat, report)
            check_columns(contract, cat, present, report)
            check_keys(contract, connection, present, report)
            check_references(contract, connection, present, report)
            check_views(contract, connection, cat, present, report)
            check_layers(contract, cat, report)
            check_vocabularies(contract, connection, present, report)
            row_counts(contract, connection, present, report)
        finally:
            connection.close()

    failed = report.failures
    counts = report.counts()
    verdict = "FAIL" if failed else "PASS"
    if args.json:
        print(
            json.dumps(
                {
                    "step": "W9.4",
                    "contract": str(contract_path),
                    "database": str(database),
                    "verdict": verdict,
                    "counts": counts,
                    "checks": report.rows,
                },
                indent=2,
                sort_keys=False,
            )
        )
    else:
        print("warehouse contract, SOP section 2.6, step W9.4")
        print(f"contract  {contract_path}")
        print(f"database  {database}")
        print()
        print(report.text())
        print()
        print(
            f"{verdict}: {counts.get(PASS, 0)} pass, {counts.get(FAIL, 0)} fail,"
            f" {counts.get(DEFER, 0)} deferred, {counts.get(SKIP, 0)} skipped"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""W2.12 Retrosheet: the per-season plays archives, the header fixture, the notice.

SOP W2.12. Per-season ``https://www.retrosheet.org/downloads/plays/{YEAR}plays.zip``
for 2015-2025, eleven archives, plus ``notice.txt``, whose statement goes
verbatim into ATTRIBUTION.md. Retrosheet is a cross-check only: DT-27 holds the
``plays.csv`` header identical across the eleven years and equal to a committed
fixture, and ``absump.verify.re288_crosscheck`` rebuilds the RE288 table from
these files and compares it with Statcast ``delta_run_exp``.

The pull ran on 2026-09-30 from ``data/raw/retrosheet/w212_pull.py``, the only
place its builder could write; this module is that script moved to its home,
with the same behaviour. Running it again costs nothing: every URL is in
``data/raw/_manifest.csv`` with its body on disk, so ``absump.http.get``
returns the cached copy and sends nothing, and every file below is written only
when its bytes would change.

    uv run --locked python -m absump.ingest.retrosheet

Every call goes through ``absump.http.get``, so the 10 s spacing, the 500/day
cap, the User-Agent, the raw cache and the manifest row all come from
``config/throttle.yml``. The client exposes GET only, so the Content-Length and
Last-Modified of the GET itself stand in for the SOP's HEAD check; they are
kept once per archive in ``_pull/<YEAR>plays.headers.json``.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile
import zlib
from pathlib import Path
from typing import Any, Final

from absump import http, paths

__all__ = [
    "FIXTURE",
    "NOTICE_URL",
    "PLAYS_URL",
    "VERIFIED",
    "YEARS",
    "base_dir",
    "main",
    "unzipped_csv",
]

#: SOP W2.12: the eleven seasons.
YEARS: Final[tuple[int, ...]] = tuple(range(2015, 2026))
PLAYS_URL: Final[str] = "https://www.retrosheet.org/downloads/plays/{year}plays.zip"
NOTICE_URL: Final[str] = "https://www.retrosheet.org/notice.txt"

#: SOP W2.12, HEAD-verified 2026-09-22: 2025plays.zip is exactly this size.
VERIFIED: Final[dict[int, dict[str, Any]]] = {
    2025: {"bytes": 7_496_795, "last_modified": "Sun, 09 Aug 2026 17:05:54 GMT"}
}
STEP_TOTAL_MB: Final[int] = 83

FIXTURE: Final[Path] = paths.REPO_ROOT / "tests" / "fixtures" / "retrosheet_plays_header.txt"


def base_dir() -> Path:
    """The Retrosheet subtree of the raw lake."""
    return paths.data_root() / "raw" / "retrosheet"


def _pull_dir() -> Path:
    return base_dir() / "_pull"


def _unzip_dir() -> Path:
    return base_dir() / "unzipped"


def unzipped_csv(year: int) -> Path:
    """The unzipped ``<YEAR>plays.csv`` for one season."""
    return _unzip_dir() / str(int(year)) / f"{int(year)}plays.csv"


def _write_if_changed(path: Path, data: bytes) -> bool:
    """Write through a temporary file only when the bytes differ. True if written."""
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def _write_once(path: Path, data: bytes) -> str:
    """Raw bytes are immutable: write if absent, refuse a different body."""
    if path.exists():
        if path.read_bytes() == data:
            return "kept"
        raise SystemExit(f"FAIL {path} exists with different bytes; raw files are never rewritten")
    _write_if_changed(path, data)
    return "written"


def _crc_of(path: Path) -> int:
    crc = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            crc = zlib.crc32(block, crc)
    return crc & 0xFFFFFFFF


def _first_line(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.readline()


def _year(year: int, record: dict[str, Any]) -> tuple[int, bytes, str] | None:
    """Fetch (or read back) one archive, unzip it, return its size and header."""
    url = PLAYS_URL.format(year=year)
    resp = http.get(url)
    body = resp.content
    if resp.status_code != 200 or not body:
        print(f"FAIL {year} status {resp.status_code}, {len(body)} B")
        return None
    sha = hashlib.sha256(body).hexdigest()
    if sha != resp.sha256:
        print(f"FAIL {year} body sha256 {sha} != manifest {resp.sha256}")
        return None
    source = "cache" if resp.from_cache else "wire"
    print(f"{year} {source:5s} {len(body):>10,} B sha256 {sha[:16]}  {url}")

    # The response headers exist only on the wire fetch; keep them once.
    hdr_path = _pull_dir() / f"{year}plays.headers.json"
    if not resp.from_cache:
        keep = {
            k: resp.headers.get(k)
            for k in (
                "content-length",
                "last-modified",
                "etag",
                "content-type",
                "content-encoding",
                "date",
            )
        }
        _write_once(hdr_path, (json.dumps(keep, indent=2, sort_keys=True) + "\n").encode())
    wire_headers = json.loads(hdr_path.read_text()) if hdr_path.exists() else {}

    entry: dict[str, Any] = {
        "url": url,
        "bytes": len(body),
        "sha256": sha,
        "content_length": wire_headers.get("content-length"),
        "last_modified": wire_headers.get("last-modified"),
    }
    ref = VERIFIED.get(year)
    if ref:
        entry["verified_2026_09_22"] = ref
        same_size = len(body) == ref["bytes"]
        same_lm = wire_headers.get("last-modified") in (None, ref["last_modified"])
        entry["matches_verified"] = same_size and same_lm
        if not (same_size and same_lm):
            record["size_changes"].append(
                {
                    "year": year,
                    "verified": ref,
                    "observed_bytes": len(body),
                    "observed_last_modified": wire_headers.get("last-modified"),
                }
            )
            print(
                f"RECORDED CHANGE {year}: verified {ref}, observed {len(body)} B, "
                f"Last-Modified {wire_headers.get('last-modified')}"
            )
        else:
            print(f"{year} matches the 2026-09-22 HEAD: {ref['bytes']:,} B, {ref['last_modified']}")

    zpath = paths.raw_retrosheet_plays(year)
    state = _write_once(zpath, body)

    archive = zipfile.ZipFile(io.BytesIO(body))
    bad = archive.testzip()
    if bad is not None:
        print(f"FAIL {year} zip member {bad} fails its CRC")
        return None
    members = []
    for info in sorted(archive.infolist(), key=lambda i: i.filename):
        name = info.filename
        if info.is_dir() or "/" in name or "\\" in name or name.startswith("."):
            print(f"FAIL {year} unexpected zip member {name!r}")
            return None
        dest = _unzip_dir() / str(year) / name
        if not (
            dest.exists() and dest.stat().st_size == info.file_size and _crc_of(dest) == info.CRC
        ):
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".tmp")
            with archive.open(info) as src, tmp.open("wb") as out:
                for block in iter(lambda: src.read(1 << 20), b""):
                    out.write(block)
            os.replace(tmp, dest)
        members.append({"name": name, "bytes": info.file_size, "crc32": f"{info.CRC:08x}"})
    entry["zip_path"] = str(zpath.relative_to(paths.data_root()))
    entry["members"] = members
    csvs = [m["name"] for m in members if m["name"].lower().endswith(".csv")]
    if len(csvs) != 1:
        print(f"FAIL {year} expected one .csv member, found {csvs}")
        return None
    line = _first_line(_unzip_dir() / str(year) / csvs[0])
    terminator = "CRLF" if line.endswith(b"\r\n") else ("LF" if line.endswith(b"\n") else "none")
    header = line.rstrip(b"\r\n")
    entry["plays_csv"] = csvs[0]
    entry["header_sha256"] = hashlib.sha256(header).hexdigest()
    entry["line_terminator"] = terminator
    record["years"][str(year)] = entry
    listed = ", ".join(f"{m['name']} {m['bytes']:,} B" for m in members)
    print(f"{year} zip {state}; members {listed}")
    return len(body), header, terminator


def main(argv: list[str] | None = None) -> int:
    """Pull (or read back) the eleven archives and the notice, then check them."""
    del argv
    record: dict[str, Any] = {"step": "W2.12", "years": {}, "size_changes": []}
    total = 0
    headers_seen: dict[int, bytes] = {}
    terminators: dict[int, str] = {}

    for year in YEARS:
        got = _year(year, record)
        if got is None:
            return 1
        size, headers_seen[year], terminators[year] = got
        total += size

    record["total_bytes"] = total
    print(
        f"total {total:,} B ({total / 1e6:.1f} MB) over {len(YEARS)} files; "
        f"step text says about {STEP_TOTAL_MB} MB"
    )

    # The first job after unzipping: one header across all eleven years.
    distinct = sorted(set(headers_seen.values()))
    record_path = _pull_dir() / "record.json"
    if len(distinct) != 1:
        for year in YEARS:
            print(f"header {year} sha256 {hashlib.sha256(headers_seen[year]).hexdigest()}")
        print(f"FAIL {len(distinct)} distinct plays.csv headers across {len(YEARS)} years")
        _write_if_changed(
            record_path, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
        )
        return 1
    header = distinct[0]
    if header.startswith(b"\xef\xbb\xbf"):
        print("note: the header carries a UTF-8 BOM")
    columns = header.decode("utf-8").split(",")
    record["header"] = {
        "sha256": hashlib.sha256(header).hexdigest(),
        "n_columns": len(columns),
        "line_terminators": sorted(set(terminators.values())),
    }
    changed = _write_if_changed(FIXTURE, header + b"\n")
    print(
        f"header identical across {len(YEARS)} years: {len(columns)} columns, sha256 "
        f"{record['header']['sha256']}, terminator {', '.join(sorted(set(terminators.values())))}"
    )
    print(f"fixture {FIXTURE.relative_to(paths.REPO_ROOT)} {'written' if changed else 'unchanged'}")

    # The licence notice, kept byte for byte as served.
    resp = http.get(NOTICE_URL)
    if resp.status_code != 200 or not resp.content:
        print(f"FAIL notice.txt status {resp.status_code}")
        return 1
    state = _write_once(base_dir() / "notice.txt", resp.content)
    record["notice"] = {
        "url": NOTICE_URL,
        "bytes": len(resp.content),
        "sha256": hashlib.sha256(resp.content).hexdigest(),
        "crlf": b"\r\n" in resp.content,
    }
    print(
        f"notice.txt {'cache' if resp.from_cache else 'wire'} {len(resp.content)} B, {state}, "
        f"sha256 {record['notice']['sha256'][:16]}, CRLF {record['notice']['crlf']}"
    )

    changed = _write_if_changed(
        record_path, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    )
    print(f"record {'written' if changed else 'unchanged'}: {record_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    sys.exit(main())

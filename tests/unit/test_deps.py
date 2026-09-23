"""W2.2 dependency audit.

SOP section 2.2, "Python pins". W1.4 wrote pyproject.toml and uv.lock. W2.2 does
not rewrite them; it audits what W1.4 resolved and fails if a pin drifts.

Four things are asserted:

1. The 24 entries of ``[project].dependencies`` and the 11 entries of
   ``[dependency-groups]`` match section 2.2 character for character.
2. ``uv.lock`` pins ``dbt-adapters==1.24.5`` and ``dbt-common==1.39.0``, the two
   transitive versions section 2.2 names by hand.
3. ``pybaseball`` appears nowhere. Its docs still claim a 30,000-row Savant cap,
   which is wrong, and its threaded puller conflicts with the section 2.3
   throttle. ``great-expectations`` likewise: the data tests are dbt_expectations
   (section 2.2, dbt packages), not a second framework.
4. The default install set, meaning ``[project].dependencies`` and everything
   they pull with no dependency group synced, is exactly the 106 distributions
   listed in RESOLVED_DEFAULT_SET below.

On the count: section 2.2 states the set "resolves on Python 3.12 in 0.8 s to 74
packages". Measured on 2026-09-23 against the W1.4 lock it resolves to 106, and
the 32-package gap is real, not a resolution that went wrong. See
``logs/evidence/W2.2-build.log`` for the enumeration and the W2.2 OWNER DECISION
in DECISIONS.md. The number below is the audited one; 74 is superseded and is
recorded in this file so that a future reader does not re-derive the discrepancy.

The default set is computed from uv.lock alone, by walking the dependency graph
from the ``absump`` root and following only the extras that are actually
requested. That walk was checked against
``uv export --frozen --no-default-groups --no-emit-project`` on 2026-09-23 and
returns the identical set of names, so the test needs no subprocess and no
network.
"""

from __future__ import annotations

import re
import tomllib
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
UV_LOCK = REPO_ROOT / "uv.lock"

# Section 2.2, the [project].dependencies block, in file order.
SOP_DEPENDENCIES = [
    "httpx==0.28.1",
    "tenacity==9.1.4",
    "orjson==3.12.0",
    "zstandard==0.25.0",
    "polars==1.44.2",
    "pyarrow==25.0.1",
    "duckdb==1.5.5",
    "pandas>=2.3.3,<3.0",
    "numpy==2.5.3",
    "scipy==1.18.1",
    "numba==0.67.0",
    "scikit-learn==1.9.1",
    "lightgbm==4.7.0",
    "statsmodels==0.15.0",
    "matplotlib==3.11.2",
    "joblib==1.6.0",
    "dbt-core==1.12.5",
    "dbt-duckdb[md]==1.11.0",
    "typer==0.27.2",
    "tqdm==4.70.1",
    "python-dotenv==1.2.3",
    "pandera[polars]==0.33.1",
    "jsonschema==4.26.0",
    "pypdf==6.1.3",
]

# Section 2.2, [dependency-groups].
SOP_DEV_GROUP = [
    "pytest==9.1.1",
    "pytest-xdist==3.8.0",
    "pytest-cov==7.1.0",
    "hypothesis==6.168.0",
    "ruff==0.16.8",
    "pre-commit==4.6.2",
    "b2==5.0.0",
    "ipykernel==7.3.0",
]
SOP_BAYES_FALLBACK_GROUP = ["pymc==6.3.2", "nutpie==0.16.11", "arviz==1.3.0"]

# Section 2.2 names these two transitive versions in prose, so they are pinned
# facts and not incidental resolution output.
SOP_NAMED_TRANSITIVES = {"dbt-adapters": "1.24.5", "dbt-common": "1.39.0"}

# Section 2.2 forbids pybaseball outright. great-expectations is the framework
# dbt_expectations replaces; neither may enter the lock by any route.
FORBIDDEN = ("pybaseball", "great-expectations", "great_expectations")

# The audited default install set, 2026-09-23. 24 direct, 82 transitive.
RESOLVED_DEFAULT_SET = {
    "agate",
    "annotated-doc",
    "annotated-types",
    "anyio",
    "attrs",
    "babel",
    "certifi",
    "charset-normalizer",
    "click",
    "cloudpickle",
    "colorama",
    "contourpy",
    "cycler",
    "daff",
    "dbt-adapters",
    "dbt-common",
    "dbt-core",
    "dbt-core-experimental-parser",
    "dbt-duckdb",
    "dbt-extractor",
    "dbt-protos",
    "deepdiff",
    "duckdb",
    "fonttools",
    "formulaic",
    "h11",
    "httpcore",
    "httpx",
    "idna",
    "importlib-metadata",
    "interface-meta",
    "isodate",
    "jinja2",
    "joblib",
    "jsonschema",
    "jsonschema-specifications",
    "kiwisolver",
    "leather",
    "lightgbm",
    "llvmlite",
    "markdown-it-py",
    "markupsafe",
    "mashumaro",
    "matplotlib",
    "mdurl",
    "metricflow",
    "more-itertools",
    "msgpack",
    "mypy-extensions",
    "narwhals",
    "networkx",
    "numba",
    "numpy",
    "opentelemetry-api",
    "orderly-set",
    "orjson",
    "packaging",
    "pandas",
    "pandera",
    "parsedatetime",
    "pathspec",
    "patsy",
    "pillow",
    "polars",
    "polars-runtime-32",
    "protobuf",
    "pyarrow",
    "pydantic",
    "pydantic-core",
    "pygments",
    "pyparsing",
    "pypdf",
    "python-dateutil",
    "python-dotenv",
    "python-slugify",
    "pytimeparse",
    "pytz",
    "pyyaml",
    "rapidfuzz",
    "referencing",
    "requests",
    "rich",
    "rpds-py",
    "scikit-learn",
    "scipy",
    "shellingham",
    "six",
    "snowplow-tracker",
    "sqlglot",
    "sqlparse",
    "statsmodels",
    "tabulate",
    "tenacity",
    "text-unidecode",
    "threadpoolctl",
    "tqdm",
    "typeguard",
    "typer",
    "typing-extensions",
    "typing-inspect",
    "typing-inspection",
    "tzdata",
    "urllib3",
    "wrapt",
    "zipp",
    "zstandard",
}

# The count section 2.2 states, kept so the gap is visible rather than forgotten.
SOP_STATED_COUNT = 74


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def lock() -> dict:
    with UV_LOCK.open("rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def lock_packages(lock: dict) -> dict:
    return {p["name"]: p for p in lock["package"]}


def _edges(packages: dict, name: str, extras: tuple[str, ...]) -> list:
    """Requirements of one locked package under one set of requested extras."""
    pkg = packages.get(name)
    if pkg is None:
        return []
    out = [(d["name"], tuple(d.get("extra", ()))) for d in pkg.get("dependencies", [])]
    optional = pkg.get("optional-dependencies", {})
    for extra in extras:
        for d in optional.get(extra, []):
            out.append((d["name"], tuple(d.get("extra", ()))))
    return out


def _default_set(packages: dict) -> dict[str, set[str]]:
    """Every distribution `uv sync --no-default-groups` installs, by direct root."""
    root = packages["absump"]
    direct = [(d["name"], tuple(d.get("extra", ()))) for d in root.get("dependencies", [])]
    reached: dict[str, set[str]] = defaultdict(set)
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for direct_name, direct_extras in direct:
        stack = [(direct_name, direct_extras)]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            reached[node[0]].add(direct_name)
            stack.extend(_edges(packages, *node))
    return reached


def test_dependencies_match_sop_section_2_2(pyproject: dict) -> None:
    assert pyproject["project"]["dependencies"] == SOP_DEPENDENCIES


def test_dependency_groups_match_sop_section_2_2(pyproject: dict) -> None:
    groups = pyproject["dependency-groups"]
    assert groups["dev"] == SOP_DEV_GROUP
    assert groups["bayes-fallback"] == SOP_BAYES_FALLBACK_GROUP
    assert set(groups) == {"dev", "bayes-fallback"}


def test_bayes_fallback_is_not_synced_by_default(pyproject: dict) -> None:
    # Section 2.2: the group costs ~600 MB and chapter 2 uses PyMC only if brms
    # fails after reparameterisation.
    assert pyproject["tool"]["uv"]["default-groups"] == ["dev"]


def test_duckdb_is_pinned_explicitly(pyproject: dict) -> None:
    # dbt-duckdb declares duckdb>=1.0.0 and only the md extra narrows it, so
    # without an explicit pin `uv lock --upgrade` can move Python's duckdb off
    # the 1.5.5 the CLI writes. Section 2.2, version-contradiction table.
    deps = pyproject["project"]["dependencies"]
    assert "duckdb==1.5.5" in deps
    assert "dbt-duckdb[md]==1.11.0" in deps


def test_named_transitive_versions(lock_packages: dict) -> None:
    for name, version in SOP_NAMED_TRANSITIVES.items():
        assert name in lock_packages, f"{name} absent from uv.lock"
        assert lock_packages[name]["version"] == version


@pytest.mark.parametrize("name", FORBIDDEN)
def test_forbidden_package_absent(name: str, pyproject: dict, lock_packages: dict) -> None:
    normalised = name.replace("_", "-")
    assert normalised not in lock_packages
    blob = "\n".join(
        pyproject["project"]["dependencies"]
        + [e for group in pyproject["dependency-groups"].values() for e in group]
    )
    assert name not in blob


def test_requests_is_not_a_direct_dependency(pyproject: dict) -> None:
    # Section 2.2 drops W6's requests==2.34.2: exactly one HTTP client is
    # allowed and it is httpx behind src/absump/http.py. requests still arrives
    # transitively under dbt-core, which is unavoidable and harmless, because
    # rule 0.5.2 is about call sites in this repository and ops/lint_http.sh
    # checks those.
    direct = {re.split(r"[\[=><!~]", entry)[0] for entry in pyproject["project"]["dependencies"]}
    assert "requests" not in direct


def test_default_install_set_is_unchanged(lock_packages: dict) -> None:
    resolved = set(_default_set(lock_packages))
    added = sorted(resolved - RESOLVED_DEFAULT_SET)
    removed = sorted(RESOLVED_DEFAULT_SET - resolved)
    assert not added and not removed, f"added={added} removed={removed}"
    assert len(resolved) == len(RESOLVED_DEFAULT_SET)


def test_sop_stated_count_is_superseded(lock_packages: dict) -> None:
    # Guards the audit itself. If a later edit ever makes the real count 74, the
    # W2.2 OWNER DECISION in DECISIONS.md should be retired rather than left to
    # contradict the tree.
    assert len(_default_set(lock_packages)) != SOP_STATED_COUNT

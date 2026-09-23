"""W9.2 seed audit. Gate RP-06, plus the contract for ``config/seeds.yml``.

SOP section 6.1 states RP-06 as: "every stochastic call seeded --
``pytest tests/unit/test_seeds.py`` -- fails on ``np.random.`` without
``default_rng``, or R sampling without ``set.seed``; parallel R uses
``RNGkind("L'Ecuyer-CMRG")``."

Two things are asserted here.

1. ``config/seeds.yml`` holds exactly the eight seeds SOP W9.2 names, with those
   values, as integers, in that order. An extra key fails as loudly as a missing
   one: a seed that is not in the SOP is a seed no step owns.

2. Every tracked source file in the production trees is scanned for an unseeded
   stochastic call. Python is parsed with ``ast``, so a mention of
   ``np.random.rand`` inside a comment or a docstring is not a hit and a real
   call is. R is scanned with regexes after comments are stripped.

The scan covers the production trees only -- ``src/``, ``R/``, ``app/``,
``scripts/``, ``tools/``, ``quality/``, ``notebooks/``, ``dbt/`` -- and not
``tests/``. Test code draws through pytest and hypothesis, which carry their own
seeding, and a test fixture that shuffles a list of three strings is not a
result anyone reproduces. W9.2 chose that boundary and recorded it as a step
default.

A scan alone would be vacuous today, because phase 01 has almost no stochastic
code yet: it would pass on an empty tree and keep passing if the scanner were
broken. So the rules are also run against snippets that are known violations and
snippets that are known to be clean. Those controls are what make RP-06 a test
rather than a formality; the repository scan is what makes it a gate.

Both scanners are deliberately file-level for the seeding question: a file that
samples must also seed. Line-level proof that a particular draw took a particular
seed is not something a linter can establish, and RP-07 (determinism, SOP W9.9)
is the check that actually settles it by running the pipeline twice.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDS_PATH = REPO_ROOT / "config" / "seeds.yml"

# SOP-final.md section 6.1, under W9.2. Order included: this is the list as the
# SOP prints it.
EXPECTED_SEEDS: list[tuple[str, int]] = [
    ("ch1_gam_bootstrap", 20260922),
    ("ch1_ump_power", 20260923),
    ("ch2_brms_chain_base", 424242),
    ("ch2_sbc", 7001),
    ("ch2_recovery", 7002),
    ("ch2_power_grid", 7003),
    ("ch3_dp_bootstrap", 19730317),
    ("p8_walkforward", 20261208),
]

# Trees that produce results. tests/ is excluded on purpose; see the docstring.
PY_SCAN_DIRS = ("src", "scripts", "tools", "quality", "notebooks", "app", "dbt")
R_SCAN_DIRS = ("R", "app", "scripts", "tools", "notebooks")

# The only members of the numpy.random namespace that are not the legacy global
# RNG. Everything else there -- rand, randn, normal, choice, shuffle, seed --
# mutates process-global state and is banned.
NUMPY_RANDOM_ALLOWED = frozenset(
    {
        "default_rng",
        "Generator",
        "SeedSequence",
        "BitGenerator",
        "PCG64",
        "PCG64DXSM",
        "Philox",
        "SFC64",
        "MT19937",
    }
)

STDLIB_RANDOM_STOCHASTIC = frozenset(
    {
        "random",
        "randint",
        "randrange",
        "choice",
        "choices",
        "shuffle",
        "sample",
        "uniform",
        "gauss",
        "normalvariate",
        "lognormvariate",
        "expovariate",
        "betavariate",
        "gammavariate",
        "triangular",
        "vonmisesvariate",
        "paretovariate",
        "weibullvariate",
        "getrandbits",
        "randbytes",
    }
)

_R_STOCHASTIC_NAMES = (
    "sample",
    "rnorm",
    "runif",
    "rbinom",
    "rpois",
    "rgamma",
    "rbeta",
    "rexp",
    "rcauchy",
    "rchisq",
    "rlnorm",
    "rnbinom",
    "rweibull",
    "rlogis",
    "rgeom",
    "rhyper",
    "rmultinom",
    "rmvn",
    "rt",
    "jitter",
    "boot",
    "bootMer",
    "simulate",
    "brm",
)
R_STOCHASTIC_RE = re.compile(r"(?<![A-Za-z0-9._])(" + "|".join(_R_STOCHASTIC_NAMES) + r")\s*\(")

_R_PARALLEL_NAMES = (
    "mclapply",
    "mcmapply",
    "mcparallel",
    "parLapply",
    "parSapply",
    "parApply",
    "parLapplyLB",
    "makeCluster",
    "makeForkCluster",
    "makePSOCKcluster",
    "registerDoParallel",
    "future_lapply",
    "future_map",
    "future_map_dbl",
    "future_pmap",
)
R_PARALLEL_RE = re.compile(r"(?<![A-Za-z0-9._])(" + "|".join(_R_PARALLEL_NAMES) + r")\s*\(|%dopar%")

R_SET_SEED_RE = re.compile(r"(?<![A-Za-z0-9._])set\.seed\s*\(")
# RNGkind("L'Ecuyer-CMRG"). The apostrophe is inside the stream name, so the
# argument is written with double quotes in practice; accept either quoting.
R_LECUYER_RE = re.compile(r"(?<![A-Za-z0-9._])RNGkind\s*\(\s*[\"']L'Ecuyer-CMRG")


# --------------------------------------------------------------------------
# config/seeds.yml
# --------------------------------------------------------------------------


def _load_seeds() -> dict[str, object]:
    return yaml.safe_load(SEEDS_PATH.read_text(encoding="utf-8"))


def test_seeds_file_exists() -> None:
    assert SEEDS_PATH.is_file(), f"{SEEDS_PATH} is missing; SOP W9.2 writes it"


def test_seeds_keys_and_values_match_the_sop() -> None:
    seeds = _load_seeds()
    assert isinstance(seeds, dict), "config/seeds.yml must parse to a mapping"
    expected = dict(EXPECTED_SEEDS)
    missing = sorted(set(expected) - set(seeds))
    extra = sorted(set(seeds) - set(expected))
    assert not missing, f"config/seeds.yml is missing SOP W9.2 seeds: {missing}"
    assert not extra, f"config/seeds.yml has seeds no SOP step names: {extra}"
    wrong = {k: (seeds[k], v) for k, v in expected.items() if seeds[k] != v}
    assert not wrong, f"seed value drift (found, expected): {wrong}"


def test_seeds_are_integers_and_distinct() -> None:
    seeds = _load_seeds()
    not_int = sorted(k for k, v in seeds.items() if not isinstance(v, int) or isinstance(v, bool))
    assert not not_int, f"seeds must be plain integers, not strings or dates: {not_int}"
    values = list(seeds.values())
    assert len(set(values)) == len(values), "two keys share one seed value"


def test_seeds_order_is_the_sop_order() -> None:
    seeds = _load_seeds()
    assert list(seeds) == [k for k, _ in EXPECTED_SEEDS]


# --------------------------------------------------------------------------
# the scanners
# --------------------------------------------------------------------------


def _dotted(node: ast.AST) -> str | None:
    """Return ``a.b.c`` for an attribute chain rooted at a plain name, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def python_violations(source: str, label: str = "<snippet>") -> list[str]:
    """Unseeded stochastic calls in one Python source string."""
    tree = ast.parse(source, filename=label)
    found: list[tuple[int, str]] = []
    stdlib_hits: list[tuple[int, str]] = []
    stdlib_seeded = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {
            "numpy.random",
            "numpy.random.mtrand",
        }:
            for alias in node.names:
                if alias.name not in NUMPY_RANDOM_ALLOWED:
                    found.append(
                        (
                            node.lineno,
                            f"from {node.module} import {alias.name} -- legacy global RNG, "
                            "use numpy.random.default_rng(seed)",
                        )
                    )
            continue
        if not isinstance(node, ast.Attribute):
            continue
        name = _dotted(node)
        if name is None:
            continue
        for prefix in ("np.random.", "numpy.random."):
            if name.startswith(prefix):
                leaf = name[len(prefix) :].split(".")[0]
                if leaf not in NUMPY_RANDOM_ALLOWED:
                    found.append(
                        (
                            node.lineno,
                            f"{name} -- np.random. without default_rng; "
                            "use rng = np.random.default_rng(seed)",
                        )
                    )
                break
        else:
            if name.startswith("random."):
                leaf = name.split(".", 1)[1]
                if leaf in {"seed", "Random"}:
                    stdlib_seeded = True
                elif leaf in STDLIB_RANDOM_STOCHASTIC:
                    stdlib_hits.append(
                        (
                            node.lineno,
                            f"{name} -- stdlib random with no random.seed() and no "
                            "random.Random(seed) in this file",
                        )
                    )

    if not stdlib_seeded:
        found.extend(stdlib_hits)
    return [f"{label}:{line}: {msg}" for line, msg in sorted(found)]


def _strip_r_comments(text: str) -> str:
    """Drop ``#`` comments, leaving string literals intact."""
    out: list[str] = []
    for line in text.splitlines():
        buf: list[str] = []
        quote: str | None = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote is not None:
                buf.append(ch)
                if ch == "\\" and i + 1 < len(line):
                    buf.append(line[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
                buf.append(ch)
            elif ch == "#":
                break
            else:
                buf.append(ch)
            i += 1
        out.append("".join(buf))
    return "\n".join(out)


def r_violations(source: str, label: str = "<snippet>") -> list[str]:
    """Unseeded sampling, or unseeded parallelism, in one R source string."""
    code = _strip_r_comments(source)
    found: list[str] = []

    stochastic = [m for m in R_STOCHASTIC_RE.finditer(code)]
    if stochastic and not R_SET_SEED_RE.search(code):
        names = sorted({m.group(1) for m in stochastic})
        found.append(f"{label}: R sampling ({', '.join(names)}) with no set.seed() in this file")

    parallel = [m for m in R_PARALLEL_RE.finditer(code)]
    if parallel and not R_LECUYER_RE.search(code):
        names = sorted({m.group(1) or "%dopar%" for m in parallel})
        found.append(f'{label}: parallel R ({", ".join(names)}) without RNGkind("L\'Ecuyer-CMRG")')
    return found


# --------------------------------------------------------------------------
# the repository scan
# --------------------------------------------------------------------------


def _files(dirs: tuple[str, ...], suffixes: tuple[str, ...]) -> list[Path]:
    hits: list[Path] = []
    for name in dirs:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            parts = set(path.relative_to(REPO_ROOT).parts)
            if parts & {".venv", "renv", "node_modules", "__pycache__", "target", "site-packages"}:
                continue
            hits.append(path)
    return hits


def test_no_unseeded_stochastic_call_in_python() -> None:
    offences: list[str] = []
    for path in _files(PY_SCAN_DIRS, (".py",)):
        rel = str(path.relative_to(REPO_ROOT))
        offences.extend(python_violations(path.read_text(encoding="utf-8"), rel))
    assert not offences, "RP-06, Python:\n" + "\n".join(offences)


def test_no_unseeded_stochastic_call_in_r() -> None:
    offences: list[str] = []
    for path in _files(R_SCAN_DIRS, (".R", ".r")):
        rel = str(path.relative_to(REPO_ROOT))
        offences.extend(r_violations(path.read_text(encoding="utf-8"), rel))
    assert not offences, "RP-06, R:\n" + "\n".join(offences)


def test_the_scan_actually_reaches_files() -> None:
    """A scanner that reads nothing passes everything. Prove it reads something."""
    assert _files(PY_SCAN_DIRS, (".py",)), "no Python source found to scan"
    assert _files(R_SCAN_DIRS, (".R", ".r")), "no R source found to scan"


# --------------------------------------------------------------------------
# controls: snippets that must fail, snippets that must pass
# --------------------------------------------------------------------------

PY_DIRTY = [
    ("np.random.rand", "import numpy as np\nx = np.random.rand(3)\n"),
    ("np.random.seed", "import numpy as np\nnp.random.seed(0)\nx = np.random.normal()\n"),
    ("numpy.random.choice", "import numpy\nx = numpy.random.choice([1, 2, 3])\n"),
    ("np.random.shuffle", "import numpy as np\nnp.random.shuffle(xs)\n"),
    ("bare reference", "import numpy as np\nf = np.random.normal\n"),
    ("from numpy.random", "from numpy.random import normal\nx = normal()\n"),
    ("stdlib random", "import random\nx = random.choice([1, 2])\n"),
    ("stdlib shuffle", "import random\nrandom.shuffle(xs)\n"),
]

PY_CLEAN = [
    (
        "default_rng",
        "import numpy as np\nrng = np.random.default_rng(20260922)\nx = rng.normal()\n",
    ),
    (
        "generator method",
        "import numpy as np\nrng = np.random.default_rng(7001)\nxs = rng.choice([1, 2], size=4)\n",
    ),
    ("SeedSequence", "import numpy as np\nss = np.random.SeedSequence(7002)\n"),
    (
        "from numpy.random import default_rng",
        "from numpy.random import default_rng\nrng = default_rng(7003)\n",
    ),
    ("seeded stdlib", "import random\nrandom.seed(424242)\nx = random.choice([1, 2])\n"),
    (
        "stdlib Random instance",
        "import random\nrng = random.Random(19730317)\nx = rng.random()\n",
    ),
    (
        "mention in a docstring",
        '"""Do not call np.random.rand here."""\n# np.random.seed(0) would be wrong\nX = 1\n',
    ),
    ("attribute on something else", "x = self.random.shuffle\ny = cfg.random.seed\n"),
]

R_DIRTY = [
    ("rnorm", "x <- rnorm(10)\n"),
    ("sample", 'draws <- sample(c("a", "b"), 2)\n'),
    ("cmdstanr sample", "fit <- mod$sample(data = d, chains = 4)\n"),
    ("brm", "fit <- brm(y ~ x, data = d)\n"),
    ("boot", "b <- boot(d, statistic = f, R = 2000)\n"),
    (
        "parallel without L'Ecuyer",
        "set.seed(20260922)\nres <- mclapply(1:4, function(i) rnorm(1))\n",
    ),
    (
        "dopar without L'Ecuyer",
        "set.seed(7001)\nres <- foreach(i = 1:4) %dopar% rnorm(1)\n",
    ),
]

R_CLEAN = [
    ("seeded rnorm", "set.seed(20260922)\nx <- rnorm(10)\n"),
    ("seeded sample", "set.seed(20260923)\nd <- sample(1:10, 3)\n"),
    (
        "seeded cmdstanr",
        "set.seed(424242)\nfit <- mod$sample(data = d, chains = 4, seed = 424242)\n",
    ),
    (
        "seeded parallel",
        'RNGkind("L\'Ecuyer-CMRG")\nset.seed(7003)\nres <- mclapply(1:4, function(i) rnorm(1))\n',
    ),
    ("mention in a comment", "# rnorm() is called in ch1_fit.R, not here\nx <- 1\n"),
    ("no stochastic call", 'library(arrow)\nd <- read_parquet("x.parquet")\n'),
    ("resample is not sample", "y <- my_resample(d)\n"),
]


@pytest.mark.parametrize("label,src", PY_DIRTY, ids=[c[0] for c in PY_DIRTY])
def test_python_scanner_fires_on_a_violation(label: str, src: str) -> None:
    assert python_violations(src, label), f"scanner missed a real violation: {label}"


@pytest.mark.parametrize("label,src", PY_CLEAN, ids=[c[0] for c in PY_CLEAN])
def test_python_scanner_is_quiet_on_clean_code(label: str, src: str) -> None:
    assert python_violations(src, label) == [], f"false positive: {label}"


@pytest.mark.parametrize("label,src", R_DIRTY, ids=[c[0] for c in R_DIRTY])
def test_r_scanner_fires_on_a_violation(label: str, src: str) -> None:
    assert r_violations(src, label), f"scanner missed a real violation: {label}"


@pytest.mark.parametrize("label,src", R_CLEAN, ids=[c[0] for c in R_CLEAN])
def test_r_scanner_is_quiet_on_clean_code(label: str, src: str) -> None:
    assert r_violations(src, label) == [], f"false positive: {label}"


def test_r_comment_stripper_keeps_strings() -> None:
    kept = _strip_r_comments('x <- "a # b"  # trailing\ny <- 2\n')
    assert '"a # b"' in kept
    assert "trailing" not in kept

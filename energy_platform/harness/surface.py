"""The target capability boundary, mechanically (ADR-027 §1-§2; 05 rows C-01...C-19).

A target may contain only the files of the ADR-027 surface; its parser may import only the
platform contracts package and a short list of pure-data standard-library modules; no file in a
target may carry a suppression, a placeholder, a hardcoded URL, a ``float()`` call or an unbounded
loop; a parser may not normalise (arithmetic, sign flip, timezone conversion) or parse by
position; and a target is complete only with a Bronze fixture, a golden with checked values and
a test module. Run by ``make lint`` (``scripts/check_target_surface.py``), by ``energyctl`` and
by every MCP write; ``conftest.py`` refuses an incomplete target at session start (ADR-020).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from energy_platform import contracts
from energy_platform.bronze.bronze import BronzeError
from energy_platform.bronze.fixtures import BLOB_FILE, ENTRY_FILE, load_fixture
from energy_platform.contracts.golden import GoldenError, load_golden

ALLOWED_TOP_FILES = frozenset({"__init__.py", "manifest.yaml", "parser.py", "README.md"})
ALLOWED_TEST_FILES = frozenset({"__init__.py"})
FIXTURE_FILES = frozenset({ENTRY_FILE, BLOB_FILE})
TEST_FILE = re.compile(r"^test_[a-z0-9_]+\.py$")
GOLDEN_FILE = re.compile(r"^[a-z0-9_.-]+\.ya?ml$")
TARGET_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

PARSER_STDLIB = frozenset(
    {
        "decimal",
        "datetime",
        "zoneinfo",
        "re",
        "typing",
        "dataclasses",
        "collections",
        "collections.abc",
        "enum",
        "itertools",
        "functools",
        "math",
        "fractions",
    }
)
PARSER_PLATFORM_PREFIX = "energy_platform.contracts"

# Line-level tokens that have no legitimate use inside a target (ADR-027 §1; 05 C-01, C-05, C-07,
# C-10). Applied to every ``.py`` file of the target.
FORBIDDEN_TOKENS: dict[str, re.Pattern[str]] = {
    "lint suppression": re.compile(r"#\s*noqa"),
    "type suppression": re.compile(r"#\s*type:\s*ignore"),
    "coverage/pragma suppression": re.compile(r"#\s*pragma"),
    "test skip": re.compile(r"pytest\.mark\.(skip|xfail)|pytest\.importorskip|pytest\.skip\("),
    "dynamic import": re.compile(r"__import__|importlib"),
    "code execution": re.compile(r"\b(exec|eval)\("),
    "file access": re.compile(r"\bopen\("),
    "builtins access": re.compile(r"__builtins__"),
    "hardcoded URL (fetch lives in the manifest)": re.compile(r"https?://"),
    "float() on a raw value (use Decimal, 01 §9)": re.compile(r"\bfloat\("),
    "unbounded loop": re.compile(r"\bwhile\s+(True|1)\b"),
}

# A scaffold is not a target (05 C-13). Applied to manifest, parser, tests and goldens.
PLACEHOLDER = re.compile(r"\b(REPLACE_ME|TODO|FIXME)\b")
PLACEHOLDER_FILES = re.compile(r"^(manifest\.yaml|parser\.py|tests/.*)$")

# Names a parser may not define again: the platform already has them (05 C-06).
PLATFORM_UTILITIES = frozenset(
    name for name in contracts.__all__ if callable(getattr(contracts, name, None))
) - frozenset(name for name in contracts.__all__ if isinstance(getattr(contracts, name), type))

NORMALISE_BINOPS: dict[type[ast.operator], str] = {
    ast.Mult: "multiplication",
    ast.Div: "division",
    ast.FloorDiv: "floor division",
    ast.Pow: "power",
}


def _rel(target: Path, path: Path) -> str:
    return path.relative_to(target).as_posix()


def _classify(target: Path, path: Path) -> str | None:
    """Return None when the file is allowed, else the reason it is not (ADR-027 §1)."""
    parts = path.relative_to(target).parts
    if len(parts) == 1:
        return None if parts[0] in ALLOWED_TOP_FILES else "file outside the target surface"
    if parts[0] == "fixtures":
        if len(parts) == 3 and parts[2] in FIXTURE_FILES:
            return None
        return "file outside the target surface (a fixture is fixtures/<name>/{entry.json,blob})"
    if parts[0] == "tests":
        if len(parts) == 2:
            name = parts[1]
            if name in ALLOWED_TEST_FILES or TEST_FILE.match(name):
                return None
            if name == "conftest.py":
                return "conftest.py is not allowed in a target"
            return "file outside the target surface"
        if len(parts) == 3 and parts[1] == "golden" and GOLDEN_FILE.match(parts[2]):
            return None
        return "file outside the target surface"
    return "file outside the target surface"


# ------------------------------------------------------------------ parser.py rules


def _parser_imports(path: Path, tree: ast.AST) -> list[str]:
    problems: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append(f"{path}:{node.lineno}: relative import in parser")
                continue
            names = [node.module or ""]
        else:
            continue
        for name in names:
            ok = name in PARSER_STDLIB or name.startswith(PARSER_PLATFORM_PREFIX)
            if not ok:
                problems.append(f"{path}:{node.lineno}: import not allowed in a parser: {name}")
    return problems


def _is_int_literal(node: ast.expr) -> bool:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return True
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    )


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _parser_ast(path: Path, tree: ast.AST) -> list[str]:
    """05 C-03 (normalise), C-04 (positional), C-06 (duplicated utility), 04 §3.1 (one Parser)."""
    problems: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Subscript) and _is_int_literal(node.slice):
            problems.append(
                f"{path}:{line}: positional access (key by header or element name, 05 C-04)"
            )
        elif isinstance(node, ast.BinOp) and type(node.op) in NORMALISE_BINOPS:
            what = NORMALISE_BINOPS[type(node.op)]
            problems.append(
                f"{path}:{line}: normalise code in a parser: {what} "
                "(units and factors belong to the mapping, 05 C-03)"
            )
        elif (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and not isinstance(node.operand, ast.Constant)
        ):
            problems.append(
                f"{path}:{line}: normalise code in a parser: sign flip (declare `sign` in the "
                "mapping, 05 C-03)"
            )
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "astimezone" or any(k.arg == "tzinfo" for k in node.keywords):
                problems.append(
                    f"{path}:{line}: normalise code in a parser: timezone conversion "
                    "(declare `time.timezone` in the mapping, 05 C-03)"
                )
            elif name == "timedelta":
                problems.append(
                    f"{path}:{line}: normalise code in a parser: interval arithmetic "
                    "(the platform tiles the day, 04 §2.2; 05 C-03)"
                )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in PLATFORM_UTILITIES:
                problems.append(
                    f"{path}:{line}: duplicated platform utility {node.name!r} "
                    "(import it from energy_platform.contracts, 05 C-06)"
                )
    classes = [
        n
        for n in getattr(tree, "body", [])
        if isinstance(n, ast.ClassDef)
        and any(isinstance(m, ast.FunctionDef) and m.name == "parse" for m in n.body)
    ]
    if len(classes) != 1:
        problems.append(
            f"{path}: parser.py must define exactly one class with a parse() method "
            f"(found {len(classes)}; 04 §3.1)"
        )
    return problems


def _check_parser(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}: syntax error: {exc.msg} (line {exc.lineno})"]
    return _parser_imports(path, tree) + _parser_ast(path, tree)


# ------------------------------------------------------------------ text rules


def _check_tokens(path: Path) -> list[str]:
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for reason, pat in FORBIDDEN_TOKENS.items():
            if pat.search(line):
                problems.append(f"{path}:{lineno}: {reason}")
    return problems


def _check_placeholders(target: Path, path: Path) -> list[str]:
    if not PLACEHOLDER_FILES.match(_rel(target, path)):
        return []
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if PLACEHOLDER.search(line):
            problems.append(f"{path}:{lineno}: placeholder left in the target (05 C-13)")
    return problems


def _manifest_target_id(target: Path) -> list[str]:
    manifest = target / "manifest.yaml"
    if not manifest.exists():
        return [f"{target}: manifest.yaml missing"]
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{manifest}: not valid YAML: {exc}"]
    declared = data.get("target_id") if isinstance(data, dict) else None
    if declared != target.name:
        return [
            f"{manifest}: target_id {declared!r} must equal the directory name "
            f"{target.name!r} (05 C-19)"
        ]
    return []


# ------------------------------------------------------------------ completeness (ADR-020)


def fixture_names(target: Path) -> tuple[str, ...]:
    root = target / "fixtures"
    if not root.is_dir():
        return ()
    return tuple(sorted(p.name for p in root.iterdir() if p.is_dir()))


def golden_paths(target: Path) -> tuple[Path, ...]:
    root = target / "tests" / "golden"
    if not root.is_dir():
        return ()
    return tuple(sorted(p for p in root.iterdir() if p.is_file() and GOLDEN_FILE.match(p.name)))


def completeness(target: Path) -> list[str]:
    """What a target must have before it is a target at all (ADR-020; 05 C-14…C-16, C-18)."""
    problems: list[str] = []
    if not (target / "manifest.yaml").is_file():
        problems.append(f"{target}: manifest.yaml missing")
    for init in (target / "__init__.py", target / "tests" / "__init__.py"):
        if not init.is_file():
            problems.append(f"{init}: missing (packaging, ADR-027 §1)")
    fixtures = fixture_names(target)
    if not fixtures:
        problems.append(
            f"{target}: no fixture — record one with `energyctl record-fixture` (05 C-14)"
        )
    for name in fixtures:
        directory = target / "fixtures" / name
        try:
            load_fixture(directory)
        except (BronzeError, ValidationError, OSError, ValueError) as exc:
            problems.append(f"{directory}: not a Bronze object: {exc} (05 C-18)")
    goldens = golden_paths(target)
    if not goldens:
        problems.append(f"{target}: no golden under tests/golden/ (05 C-15)")
    for path in goldens:
        try:
            golden = load_golden(path)
        except (GoldenError, ValidationError, OSError) as exc:
            problems.append(f"{path}: {_one_line(exc)} (05 C-16)")
            continue
        if golden.fixture not in fixtures:
            problems.append(f"{path}: fixture {golden.fixture!r} does not exist (05 C-15)")
    tests_dir = target / "tests"
    if not tests_dir.is_dir() or not any(
        TEST_FILE.match(p.name) for p in tests_dir.iterdir() if p.is_file()
    ):
        problems.append(f"{target}: no tests/test_*.py module (05 C-15)")
    return problems


def _one_line(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if len(text) == 1 else "; ".join(t.strip() for t in text[:3])


# ------------------------------------------------------------------ entry points


def check_target(target: Path) -> list[str]:
    problems: list[str] = []
    if not TARGET_ID.match(target.name):
        problems.append(f"{target}: target id must match {TARGET_ID.pattern}")
    problems.extend(_manifest_target_id(target))
    for path in sorted(p for p in target.rglob("*") if p.is_file()):
        if "__pycache__" in path.parts:
            continue
        reason = _classify(target, path)
        if reason:
            problems.append(f"{path}: {reason}")
            continue
        if path.name == "__init__.py" and path.read_text(encoding="utf-8").strip():
            problems.append(f"{path}: __init__.py must be empty")
        if path.suffix == ".py":
            problems.extend(_check_tokens(path))
        problems.extend(_check_placeholders(target, path))
        if path.name == "parser.py":
            problems.extend(_check_parser(path))
    problems.extend(completeness(target))
    return problems


def target_dirs(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(sorted(p for p in root.iterdir() if p.is_dir() and p.name not in {"__pycache__"}))


def check_root(root: Path) -> list[str]:
    problems: list[str] = []
    if not root.is_dir():
        return [f"{root}: missing"]
    for entry in sorted(root.iterdir()):
        if entry.name in {"__init__.py", "__pycache__"}:
            continue
        if not entry.is_dir():
            problems.append(f"{entry}: only target directories may live under {root}")
            continue
        problems.extend(check_target(entry))
    return problems


def incomplete_targets(root: Path) -> list[str]:
    """Completeness only, for pytest session start (ADR-020: fails collection)."""
    problems: list[str] = []
    for target in target_dirs(root):
        problems.extend(completeness(target))
    return problems


def report(root: Path) -> tuple[int, list[str]]:
    """Exit code and lines for the Make target; the script prints them."""
    problems = check_root(root)
    if problems:
        return 1, ["target-surface: violations of ADR-027:", *(f"  {p}" for p in problems)]
    return 0, ["target-surface: OK"]

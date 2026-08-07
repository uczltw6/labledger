"""Verify LabLedger's local P0 repository and compliance gate.

The verifier never prints file contents, credential values, remote user info,
or secret matches. It is dependency-free so it can run before P1 packaging.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "AGENTS.md",
    "TODO.md",
    "RUNBOOK.md",
    "STATUS.md",
    "README.md",
    "LICENSE",
    ".gitignore",
    ".env.example",
    "scripts/verify_p0.py",
)

REQUIRED_TRACKED_FILES = (
    "AGENTS.md",
    "TODO.md",
    "RUNBOOK.md",
    "STATUS.md",
    "README.md",
    "LICENSE",
    ".gitignore",
    ".env.example",
    "scripts/verify_p0.py",
)

REQUIRED_IGNORE_RULES = (
    ".env",
    "node_modules/",
    ".aws-sam/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
)

DISALLOWED_TRACKED_NAMES = re.compile(
    r"(^|/)(\.env($|\.)|credentials(?:\.[^/]*)?|secrets?(?:\.[^/]*)?|"
    r"id_rsa(?:\.[^/]*)?|[^/]+\.(?:pem|p12|pfx|key))$",
    re.IGNORECASE,
)

SECRET_PATTERNS = (
    re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(rb"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"(?:postgres(?:ql)?|cockroachdb)://[^\s:/]+:[^\s@]+@", re.IGNORECASE),
)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def tracked_files() -> tuple[set[str], str | None]:
    result = run("git", "ls-files", "-z")
    if result.returncode != 0:
        return set(), "git ls-files failed"
    return {name for name in result.stdout.split("\0") if name}, None


def check_required_files() -> Check:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    return Check(
        "required P0 files",
        not missing,
        "all required files exist" if not missing else f"missing: {', '.join(missing)}",
    )


def check_license() -> Check:
    path = ROOT / "LICENSE"
    if not path.is_file():
        return Check("MIT license", False, "LICENSE is missing")
    text = path.read_text(encoding="utf-8")
    passed = text.startswith("MIT License\n") and "Permission is hereby granted" in text
    return Check("MIT license", passed, "MIT text detected" if passed else "MIT text is incomplete")


def check_env_example() -> Check:
    path = ROOT / ".env.example"
    if not path.is_file():
        return Check("placeholder-only .env.example", False, ".env.example is missing")

    invalid_names: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            invalid_names.append("<malformed line>")
            continue
        name, value = line.split("=", 1)
        if not name or not (value.startswith("<") and value.endswith(">")):
            invalid_names.append(name or "<unnamed>")

    return Check(
        "placeholder-only .env.example",
        not invalid_names,
        "every value is an explicit placeholder"
        if not invalid_names
        else f"non-placeholder entries: {', '.join(invalid_names)}",
    )


def check_ignore_rules() -> Check:
    path = ROOT / ".gitignore"
    if not path.is_file():
        return Check("required ignore rules", False, ".gitignore is missing")
    rules = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = [rule for rule in REQUIRED_IGNORE_RULES if rule not in rules]
    return Check(
        "required ignore rules",
        not missing,
        "Python, Node, env, AWS/SAM, and test artifacts are covered"
        if not missing
        else f"missing rules: {', '.join(missing)}",
    )


def check_tracked_files(files: set[str], git_error: str | None) -> Check:
    if git_error:
        return Check("required files tracked", False, git_error)
    missing = [name for name in REQUIRED_TRACKED_FILES if name not in files]
    return Check(
        "required files tracked",
        not missing,
        "all P0 repository files are tracked"
        if not missing
        else f"untracked: {', '.join(missing)}",
    )


def check_tracked_secrets(files: set[str], git_error: str | None) -> Check:
    if git_error:
        return Check("tracked secret scan", False, git_error)

    bad_names = sorted(
        name for name in files if name != ".env.example" and DISALLOWED_TRACKED_NAMES.search(name)
    )
    bad_contents: list[str] = []
    for name in sorted(files):
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            bad_contents.append(name)

    passed = not bad_names and not bad_contents
    if passed:
        detail = "no credential-like filenames or high-confidence secret patterns found"
    else:
        affected = sorted(set(bad_names + bad_contents))
        detail = "potential secret material in tracked file(s): " + ", ".join(affected)
    return Check("tracked secret scan", passed, detail)


def check_public_github_repo() -> Check:
    if not shutil.which("gh"):
        return Check("public GitHub repository", False, "GitHub CLI is unavailable")

    auth = run("gh", "auth", "status")
    if auth.returncode != 0:
        return Check("public GitHub repository", False, "GitHub CLI is not authenticated")

    remote = run("git", "remote", "get-url", "origin")
    if remote.returncode != 0 or not remote.stdout.strip():
        return Check("public GitHub repository", False, "origin remote is not configured")

    view = run("gh", "repo", "view", "--json", "isPrivate", "--jq", ".isPrivate")
    passed = view.returncode == 0 and view.stdout.strip().lower() == "false"
    return Check(
        "public GitHub repository",
        passed,
        "origin is visible and public" if passed else "origin is missing, inaccessible, or private",
    )


def main() -> int:
    files, git_error = tracked_files()
    checks = [
        check_required_files(),
        check_license(),
        check_env_example(),
        check_ignore_rules(),
        check_tracked_files(files, git_error),
        check_tracked_secrets(files, git_error),
        check_public_github_repo(),
    ]

    for check in checks:
        marker = "PASS" if check.passed else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")

    failures = sum(not check.passed for check in checks)
    print(f"P0 local/repository verification: {len(checks) - failures}/{len(checks)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

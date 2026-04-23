"""R-2604 isolation sentinel for the historical eight-file subset.

This sentinel stays stdlib-only and re-runs the subset in a fresh child
process. It inherits the ambient environment so the same check covers both the
default suite and pool-enabled suite executions.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
R2604_SUBSET = (
    "tests/test_rate_limit.py",
    "tests/test_audit_log.py",
    "tests/test_audit_query.py",
    "tests/test_fk_enforcement.py",
    "tests/test_sqlite_migration.py",
    "tests/test_storage_concurrency.py",
    "tests/test_retrieval_quality.py",
    "tests/test_retrieval_quality_regression.py",
)


def _run_pytest(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args, *R2604_SUBSET],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "") + ("\n" if result.stderr else "") + (result.stderr or "")


def _extract_count(pattern: str, output: str, description: str) -> int:
    match = re.search(pattern, output)
    assert match is not None, (
        f"Could not find {description} in pytest output.\n\n"
        f"--- stdout/stderr ---\n{output}"
    )
    return int(match.group(1))


def test_r2604_subset_passes_in_fresh_child_process() -> None:
    collect_result = _run_pytest("--collect-only", "-q")
    collect_output = _combined_output(collect_result)
    assert collect_result.returncode == 0, (
        "Historical R-2604 subset failed during collection.\n\n"
        f"--- stdout/stderr ---\n{collect_output}"
    )
    expected_count = _extract_count(
        r"(\d+)\s+tests\s+collected",
        collect_output,
        "collected test count",
    )
    assert expected_count > 0, "Historical R-2604 subset collected zero tests."

    run_result = _run_pytest("-q")
    run_output = _combined_output(run_result)
    assert run_result.returncode == 0, (
        "Historical R-2604 subset failed in the isolated child process.\n\n"
        f"--- stdout/stderr ---\n{run_output}"
    )
    passed_count = _extract_count(r"(\d+)\s+passed", run_output, "passed test count")
    assert passed_count == expected_count, (
        "Historical R-2604 subset pass count drifted from collect count.\n\n"
        f"expected: {expected_count}\n"
        f"passed: {passed_count}\n\n"
        f"--- stdout/stderr ---\n{run_output}"
    )

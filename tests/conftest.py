from __future__ import annotations

import shutil
from pathlib import Path

import pytest


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def isolated_project_root() -> Path:
    """Run tests from a writable project-shaped root, leaving repo output/ alone."""

    root = WORKSPACE_ROOT / ".test-output" / "pytest-project"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    for file_name in ("README.md", "AGENTS.md", "CURSOR.md", "pyproject.toml", ".env.example"):
        source = WORKSPACE_ROOT / file_name
        if source.is_file():
            shutil.copy2(source, root / file_name)

    for dir_name in ("docs", "examples", "resources", "tooling", "concepts", "profiles", "knowledge"):
        source = WORKSPACE_ROOT / dir_name
        if source.is_dir():
            shutil.copytree(
                source,
                root / dir_name,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"),
            )

    (root / "output").mkdir()
    return root


@pytest.fixture(autouse=True)
def run_from_isolated_project_root(monkeypatch: pytest.MonkeyPatch, isolated_project_root: Path) -> None:
    monkeypatch.chdir(isolated_project_root)

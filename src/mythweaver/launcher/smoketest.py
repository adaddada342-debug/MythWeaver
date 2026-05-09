from __future__ import annotations

import os
import shutil
from pathlib import Path

from mythweaver.schemas.contracts import SmokeTestInjectionReport

SMOKE_TEST_MOD_ID = "mythweaver-smoketest"
SMOKE_TEST_JAR_NAME = f"{SMOKE_TEST_MOD_ID}.jar"


def locate_smoke_test_helper(explicit_path: Path | None = None, *, search_root: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    env_path = os.getenv("MYTHWEAVER_SMOKETEST_MOD_PATH")
    if env_path:
        candidates.append(Path(env_path))
    if explicit_path is not None:
        candidates.append(Path(explicit_path))
    root = Path(search_root or Path.cwd())
    candidates.append(root / "resources" / SMOKE_TEST_JAR_NAME)
    tooling_libs = root / "tooling" / "mythweaver-smoketest" / "build" / "libs"
    if tooling_libs.is_dir():
        candidates.extend(
            sorted(
                (
                    path
                    for path in tooling_libs.glob("*.jar")
                    if "sources" not in path.name.lower() and "javadoc" not in path.name.lower()
                ),
                key=lambda path: path.name,
            )
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def inject_smoke_test_mod(instance_path: Path, *, helper_mod_path: Path | None = None) -> SmokeTestInjectionReport:
    if helper_mod_path is not None:
        helper = Path(helper_mod_path) if Path(helper_mod_path).is_file() else None
    else:
        helper = locate_smoke_test_helper()
    if helper is None:
        return SmokeTestInjectionReport(
            status="missing_helper",
            notes=[
                "MythWeaver smoke-test helper jar is unavailable; runtime proof cannot be faked.",
                "Set MYTHWEAVER_SMOKETEST_MOD_PATH, place mythweaver-smoketest.jar in resources/, or run tooling/mythweaver-smoketest/build_smoketest.py.",
            ],
        )
    mods_path = Path(instance_path) / ".minecraft" / "mods"
    target = mods_path / SMOKE_TEST_JAR_NAME
    try:
        mods_path.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return SmokeTestInjectionReport(
                status="already_present",
                helper_mod_path=str(helper),
                instance_mods_path=str(mods_path),
                injected_file_path=str(target),
                notes=["Smoke-test helper mod was already present in the validation instance."],
            )
        shutil.copy2(helper, target)
        return SmokeTestInjectionReport(
            status="injected",
            helper_mod_path=str(helper),
            instance_mods_path=str(mods_path),
            injected_file_path=str(target),
            notes=["Injected validation-only smoke-test helper mod."],
        )
    except OSError as exc:
        return SmokeTestInjectionReport(
            status="failed",
            helper_mod_path=str(helper),
            instance_mods_path=str(mods_path),
            errors=[str(exc)],
        )


def remove_injected_smoke_test_mod(report: SmokeTestInjectionReport) -> SmokeTestInjectionReport:
    if report.status != "injected" or not report.injected_file_path:
        return report
    target = Path(report.injected_file_path)
    try:
        if target.exists():
            target.unlink()
        report.removed_after_validation = True
        report.notes.append("Removed validation-only smoke-test helper mod.")
    except OSError as exc:
        report.status = "failed"
        report.errors.append(str(exc))
    return report


def is_smoke_test_mod_path(path: Path) -> bool:
    name = path.name.lower()
    return name == SMOKE_TEST_JAR_NAME or name.startswith(f"{SMOKE_TEST_MOD_ID}-")

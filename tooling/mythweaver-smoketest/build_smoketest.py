from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    repo_root = project_dir.parents[1]
    gradle = _find_gradle(project_dir)
    if gradle is None:
        print(
            "No Gradle wrapper or system Gradle found. Run `gradle wrapper` inside tooling/mythweaver-smoketest or install Gradle.",
            file=sys.stderr,
        )
        return 2

    try:
        completed = subprocess.run(
            [str(gradle), "clean", "build"],
            cwd=project_dir,
            check=False,
            text=True,
        )
    except OSError as exc:
        print(f"Failed to run Gradle: {exc}", file=sys.stderr)
        return 2
    if completed.returncode != 0:
        print(f"Gradle build failed with exit code {completed.returncode}. Ensure JDK 17 is installed.", file=sys.stderr)
        return completed.returncode

    jar = _find_built_jar(project_dir / "build" / "libs")
    if jar is None:
        print("Gradle completed but no smoke-test runtime jar was found in build/libs.", file=sys.stderr)
        return 3

    resources = repo_root / "resources"
    resources.mkdir(parents=True, exist_ok=True)
    target = resources / "mythweaver-smoketest.jar"
    shutil.copy2(jar, target)
    print(target)
    return 0


def _find_gradle(project_dir: Path) -> Path | None:
    wrapper = project_dir / ("gradlew.bat" if sys.platform.startswith("win") else "gradlew")
    if wrapper.is_file():
        return wrapper
    executable = shutil.which("gradle")
    return Path(executable) if executable else None


def _find_built_jar(libs: Path) -> Path | None:
    if not libs.is_dir():
        return None
    jars = sorted(
        path
        for path in libs.glob("*.jar")
        if "sources" not in path.name.lower() and "javadoc" not in path.name.lower()
    )
    return jars[0] if jars else None


if __name__ == "__main__":
    raise SystemExit(main())

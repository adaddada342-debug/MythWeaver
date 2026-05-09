import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


def _load_module():
    path = Path.cwd() / "tooling" / "mythweaver-smoketest" / "build_smoketest.py"
    spec = importlib.util.spec_from_file_location("build_smoketest", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class BuildSmokeTestGradleSelectionTests(unittest.TestCase):
    def test_prefers_windows_wrapper_when_present(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            wrapper = project_dir / "gradlew.bat"
            wrapper.write_text("@echo off\r\n", encoding="utf-8")
            with patch.object(module.sys, "platform", "win32"), patch.object(module.shutil, "which", return_value="C:/Gradle/bin/gradle.exe"):
                self.assertEqual(module._find_gradle(project_dir), wrapper)

    def test_prefers_unix_wrapper_when_present(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            wrapper = project_dir / "gradlew"
            wrapper.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            with patch.object(module.sys, "platform", "linux"), patch.object(module.shutil, "which", return_value="/usr/bin/gradle"):
                self.assertEqual(module._find_gradle(project_dir), wrapper)

    def test_falls_back_to_system_gradle_when_wrapper_missing(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            with patch.object(module.sys, "platform", "linux"), patch.object(module.shutil, "which", return_value="/usr/bin/gradle"):
                self.assertEqual(module._find_gradle(project_dir), Path("/usr/bin/gradle"))

    def test_reports_clear_error_when_no_wrapper_or_system_gradle(self):
        module = _load_module()
        message = "No Gradle wrapper or system Gradle found. Run `gradle wrapper` inside tooling/mythweaver-smoketest or install Gradle."
        with patch.object(module, "_find_gradle", return_value=None):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = module.main()
        self.assertEqual(code, 2)
        self.assertIn(message, stderr.getvalue())

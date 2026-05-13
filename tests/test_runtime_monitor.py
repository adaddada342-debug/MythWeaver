import subprocess
import unittest
from pathlib import Path


class FakeProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0, timeout: bool = False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False

    def communicate(self, timeout=None):
        if self.timeout:
            raise subprocess.TimeoutExpired(["java"], timeout or 1)
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.returncode


class PollingFakeProcess(FakeProcess):
    def poll(self):
        return None if not self.killed else self.returncode


class LogWritingProcess(FakeProcess):
    def __init__(self, latest_log: Path):
        super().__init__("")
        self.latest_log = latest_log
        self.polls = 0

    def poll(self):
        self.polls += 1
        if self.polls == 1:
            self.latest_log.parent.mkdir(parents=True, exist_ok=True)
            self.latest_log.write_text(
                smoke_log("CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"),
                encoding="utf-8",
            )
        return None if not self.killed else self.returncode


def smoke_log(*markers: str) -> str:
    return "\n".join(f"[00:00:00] [Render thread/INFO]: [MythWeaverSmokeTest] {marker}" for marker in markers)


class RuntimeMonitorTests(unittest.TestCase):
    def test_stable_60_markers_cause_passed_report(self):
        from mythweaver.runtime.monitor import monitor_command

        latest = Path(".test-output") / "monitor-stable" / ".minecraft" / "logs" / "latest.log"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(smoke_log("CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"), encoding="utf-8")

        result = monitor_command(
            ["java"],
            instance_path=latest.parents[2],
            timeout_seconds=5,
            success_grace_seconds=0,
            smoke_test_mod_used=True,
            process_factory=lambda command: FakeProcess(""),
        )

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.proof.proof_level, "stable_60")
        self.assertTrue(result.proof.required_markers_met)

    def test_client_ready_only_does_not_pass_when_proof_required(self):
        from mythweaver.runtime.monitor import monitor_command

        latest = Path(".test-output") / "monitor-client-only" / ".minecraft" / "logs" / "latest.log"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(smoke_log("CLIENT_READY"), encoding="utf-8")

        result = monitor_command(
            ["java"],
            instance_path=latest.parents[2],
            timeout_seconds=5,
            success_grace_seconds=0,
            smoke_test_mod_used=True,
            process_factory=lambda command: FakeProcess("Sound engine started"),
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.proof.proof_level, "client_initialized")
        self.assertEqual(result.issues[0].kind, "runtime_proof_missing")

    def test_world_join_without_stability_marker_does_not_pass(self):
        from mythweaver.runtime.monitor import monitor_command

        latest = Path(".test-output") / "monitor-world-only" / ".minecraft" / "logs" / "latest.log"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(smoke_log("CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD"), encoding="utf-8")

        result = monitor_command(
            ["java"],
            instance_path=latest.parents[2],
            timeout_seconds=5,
            success_grace_seconds=0,
            smoke_test_mod_used=True,
            process_factory=lambda command: FakeProcess(""),
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.proof.proof_level, "world_joined")

    def test_crash_report_creation_fails_even_with_stable_marker(self):
        from mythweaver.runtime.monitor import monitor_command

        root = Path(".test-output") / "monitor-crash"
        latest = root / ".minecraft" / "logs" / "latest.log"
        crash = root / ".minecraft" / "crash-reports" / "crash.txt"
        latest.parent.mkdir(parents=True, exist_ok=True)
        crash.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(smoke_log("CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"), encoding="utf-8")
        crash.write_text("---- Minecraft Crash Report ----\nException in thread main\n", encoding="utf-8")

        result = monitor_command(
            ["java"],
            instance_path=root,
            timeout_seconds=5,
            success_grace_seconds=0,
            smoke_test_mod_used=True,
            process_factory=lambda command: FakeProcess(""),
        )

        self.assertEqual(result.status, "failed")

    def test_nonzero_exit_fails_even_after_stable_marker(self):
        from mythweaver.runtime.monitor import monitor_command

        root = Path(".test-output") / "monitor-nonzero"
        latest = root / ".minecraft" / "logs" / "latest.log"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(smoke_log("CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"), encoding="utf-8")

        result = monitor_command(
            ["java"],
            instance_path=root,
            timeout_seconds=5,
            success_grace_seconds=0,
            stop_after_success=False,
            smoke_test_mod_used=True,
            process_factory=lambda command: FakeProcess("", returncode=1),
        )

        self.assertEqual(result.status, "failed")

    def test_stop_after_success_kills_process_after_stable_proof(self):
        from mythweaver.runtime.monitor import monitor_command

        root = Path(".test-output") / "monitor-stop"
        latest = root / ".minecraft" / "logs" / "latest.log"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(smoke_log("CLIENT_READY", "SERVER_STARTED", "PLAYER_JOINED_WORLD", "STABLE_60_SECONDS"), encoding="utf-8")
        fake = PollingFakeProcess("")

        result = monitor_command(
            ["java"],
            instance_path=root,
            timeout_seconds=5,
            success_grace_seconds=0,
            stop_after_success=True,
            smoke_test_mod_used=True,
            process_factory=lambda command: fake,
        )

        self.assertEqual(result.status, "passed")
        self.assertTrue(fake.killed)

    def test_monitor_watches_latest_log_while_process_runs(self):
        from mythweaver.runtime.monitor import monitor_command

        root = Path(".test-output") / "monitor-live-log"
        latest = root / ".minecraft" / "logs" / "latest.log"
        fake = LogWritingProcess(latest)

        result = monitor_command(
            ["java"],
            instance_path=root,
            timeout_seconds=5,
            success_grace_seconds=0,
            stop_after_success=True,
            smoke_test_mod_used=True,
            poll_interval_seconds=0.01,
            process_factory=lambda command: fake,
        )

        self.assertEqual(result.status, "passed")
        self.assertTrue(fake.killed)
        self.assertGreaterEqual(fake.polls, 1)

    def test_fatal_log_pattern_fails_early_and_writes_bounded_evidence(self):
        from mythweaver.runtime.monitor import monitor_command

        root = Path(".test-output") / "monitor-fatal-bounded"
        latest = root / ".minecraft" / "logs" / "latest.log"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(("x" * 250_000) + "\nException in thread main\n", encoding="utf-8")
        fake = PollingFakeProcess("")

        result = monitor_command(
            ["java"],
            instance_path=root,
            timeout_seconds=5,
            success_grace_seconds=0,
            process_factory=lambda command: fake,
        )

        evidence = root / "runtime_evidence.txt"
        self.assertEqual(result.status, "failed")
        self.assertTrue(fake.killed)
        self.assertTrue(evidence.is_file())
        self.assertLessEqual(len(evidence.read_text(encoding="utf-8")), 200_000)

    def test_monitor_timeout_kills_process_and_returns_timeout_issue(self):
        from mythweaver.runtime.monitor import monitor_command

        fake = FakeProcess("", timeout=True)
        result = monitor_command(
            ["java"],
            instance_path=Path(".test-output") / "monitor-timeout",
            timeout_seconds=1,
            success_grace_seconds=0,
            process_factory=lambda command: fake,
        )

        self.assertEqual(result.status, "timed_out")
        self.assertTrue(fake.killed)
        self.assertEqual(result.issues[0].kind, "timeout")


if __name__ == "__main__":
    unittest.main()

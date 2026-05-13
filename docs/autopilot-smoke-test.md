# MythWeaver Autopilot Smoke Test Guide

Autopilot V1 validates generated packs through MythWeaver's private Fabric runtime. This is not a
public launcher UI, does not use Microsoft auth, and does not join servers. Real launch testing is
opt-in and local; CI/unit tests use fixtures and fake processes.

## Requirements

- Java 17 for Minecraft 1.18 through 1.20.4; Java 21 for 1.20.5/1.21+.
- Fabric is the only private runtime target in V1.
- A validation-only smoke-test helper jar, usually `resources/mythweaver-smoketest.jar` or the path
  pointed to by `MYTHWEAVER_SMOKETEST_MOD_PATH`.

Forge, NeoForge, Quilt, and unknown loaders return `unsupported_loader_runtime` in private runtime
V1. They may still be valid export targets elsewhere, but Autopilot cannot privately prove them yet.

## Running A Local Validation

```powershell
$env:PYTHONPATH = "src"
$env:MYTHWEAVER_SMOKETEST_MOD_PATH = "C:\MythWeaver\resources\mythweaver-smoketest.jar"
python -m mythweaver.cli.main autopilot selected_mods.json --sources modrinth --loader fabric --minecraft-version 1.20.1 --target-export local_instance --minimum-stability-seconds 60
```

Use `--json` when another tool needs the machine-readable `AutopilotReport`. JSON mode prints only
JSON.

## Outputs

Autopilot writes under the configured `--output-root`, or next to the selected list in an
`autopilot/` directory by default.

- Runtime cache: `<output-root>/runtime-cache/`
- Runtime attempts: `<output-root>/runtime/<pack-name>-<run-id>/`
- Built local instances: `<output-root>/attempt-<n>/instances/`
- Final reports: `<output-root>/autopilot_report.json` and `<output-root>/autopilot_report.md`
- Runtime evidence: `runtime_launch_report.json`, `runtime_evidence.txt`, `marker_summary.json`,
  and `crash_analysis.json` when fatal evidence exists.

`runtime_evidence.txt` is bounded. Full launcher logs may be larger, but MythWeaver keeps report JSON
compact by storing evidence paths and snippets.

## Proof Meaning

`verified_playable` requires strict smoke-test proof by default:

- `CLIENT_READY`
- `SERVER_STARTED`
- `PLAYER_JOINED_WORLD`
- `STABLE_60_SECONDS` unless a higher minimum is configured

Client boot, sound engine, narrator, or main-menu-like messages are weak proof. They are recorded in
reports, but they do not prove playability while `--require-smoke-test-proof` is enabled.

If the helper jar is missing and smoke proof is required, Autopilot blocks/fails clearly instead of
pretending the pack is playable. The helper is copied only into isolated runtime attempt instances
and is excluded from final exported pack artifacts.

## Cleanup

Temporary runtime attempts can be removed safely after inspecting reports:

```powershell
Remove-Item .test-output\runtime -Recurse -Force
```

Only remove directories you intentionally used as Autopilot output roots. Do not delete user-managed
Prism or launcher instances unless you created them for validation.

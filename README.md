# MythWeaver

MythWeaver is a local Modrinth-powered modpack search and build engine for AI agents.

It is designed for external coding agents such as Codex, Cursor, Claude Code, and other
OpenAI-compatible tools. MythWeaver does not require a paid AI provider or hosted model to work.
Agents provide taste, creative interpretation, and external research. MythWeaver provides
deterministic Modrinth search, inspection, compatibility verification, dependency resolution,
download, `.mrpack` export, Prism instance building, launch validation, and failure explanation.

## Easiest Use With Codex Or Cursor

Open this folder in Codex or Cursor and type:

```text
start
```

The agent should answer:

```text
State your modpack idea.
```

Then describe the pack you want. The folder includes `AGENTS.md`, `CURSOR.md`, and Cursor rules that
tell the agent to use MythWeaver's deterministic tools instead of inventing mods.

CLI fallback:

```powershell
python -m mythweaver.cli.main start
python -m mythweaver.cli.main start "A horrifying infinite winter survival world"
```

## Normal User Mode

If you are not using Cursor, Codex, or another local coding agent, start the guided terminal HUD:

```powershell
python -m mythweaver.cli.main hud
```

The HUD walks you through building from a `selected_mods.json`, checking it against the expected
format, verifying the mods through Modrinth, building the pack, optionally validating launch through
Prism, and creating a repair plan if launch validation fails. It also prints the exact CLI command
for each step so power users can leave the wizard at any time.

If you use ChatGPT, Claude, Gemini, or another cloud AI, choose:

```text
I need ChatGPT/Claude/Gemini to make me a selected_mods.json
```

MythWeaver will create a handoff folder under `output/handoff/<pack-name>/` containing:

- `cloud_ai_request.md`
- `selected_mods.schema.json`
- `example_selected_mods.json`
- `README_FOR_AI.md`

Upload or paste the request into your cloud AI and ask it to return `selected_mods.json` as valid
JSON only. Then return to the HUD and choose `Build a pack from a selected_mods.json`.

Command equivalents:

```powershell
python -m mythweaver.cli.main handoff export --concept "medieval survival with castles and dangerous nights" --output mythweaver_handoff.zip
python -m mythweaver.cli.main handoff validate selected_mods.json
python -m mythweaver.cli.main build-from-list selected_mods.json --output output/generated/<pack-name>
```

MythWeaver can create the handoff prompt, but it does not magically choose a perfect curated mod list
without a local agent, cloud AI, configured AI provider, or manual selection. It remains strict about
Modrinth verification and will not invent mods or fake successful builds.

## MythWeaver as an AI agent backend

MythWeaver does not try to replace Cursor, Codex, Claude, Gemini, or another AI agent as the
creative modpack designer. The intended workflow is: let the AI agent interpret the fantasy, choose
mods, decide theme fit, and keep the pack fun; use MythWeaver for verified Modrinth metadata,
loader/version checks, dependency resolution, dropped-mod audits, compatibility memory, dry-run
packaging, build safety, and repair prompts.

Create a complete Cursor/Codex workflow prompt from a concept file:

```powershell
python -m mythweaver.cli.main agent-workflow-prompt concepts/cozy_beautiful_world.md
```

Then:

1. Paste `cursor_composer_prompt.md` into Cursor Composer, Codex, Claude, or Gemini.
2. Let the agent generate `selected_mods.json` from the concept, design, and blueprint.
3. Run `agent-check` to separate hard technical blockers from AI judgment signals.
4. Run `verify-list` to confirm real Modrinth loader/version support.
5. Run `build-from-list --dry-run` before exporting the final pack.

Warnings and `ai_judgment_needed` findings are signals for the creative agent, not automatic taste
decisions. Hard blockers such as unsupported loader/version metadata, invalid projects, missing
required dependencies, and known critical conflicts must be fixed before build/export.

## Multi-source mod acquisition

MythWeaver separates source acquisition from loader compatibility. Modrinth remains the default
automated source. CurseForge is supported only through the official API via `CURSEFORGE_API_KEY`;
MythWeaver does not scrape CurseForge pages. Local jar files can be inspected when they have
verifiable metadata and hashes. GitHub Releases, Planet Minecraft, and direct URLs are conservative
sources: they are manual, discovery-only, or risky unless version, loader, dependency, permission,
download, and hash metadata can be proven.

Use `source-resolve` before autonomous builds when a selected list uses anything beyond ordinary
Modrinth refs:

```powershell
python -m mythweaver.cli.main source-search "cozy building" --mc-version 1.20.1 --loader fabric --sources modrinth,curseforge
python -m mythweaver.cli.main source-inspect local:C:/mods/example.jar --mc-version 1.20.1 --loader fabric
python -m mythweaver.cli.main source-resolve selected_mods.json --mc-version 1.20.1 --loader fabric --sources modrinth,curseforge,local --target-export local_instance
```

Autonomous mode accepts only `verified_auto` source candidates by default. `manual_required`,
`metadata_incomplete`, `download_blocked`, `license_blocked`, and `unsafe_source` candidates are
surfaced to Cursor/Codex through reports instead of being silently trusted. A local or Prism
instance can use more verified local files than a redistributable `.mrpack`; Modrinth pack export is
kept stricter because external source redistribution and launcher behavior may be limited.

## Runtime stabilization

`verify-list` checks metadata/installability: real Modrinth projects, loader/version support,
compatible files, and dependency metadata. In short, verify-list checks metadata/installability.
`build-from-list --dry-run` checks packaging: whether
MythWeaver can assemble the pack manifest and reports without downloading jars. Neither step proves
the pack is playable. In short, build dry-run checks packaging.

Use `launch-check` or `stabilize-pack` before calling a pack finished. `launch-check` makes the
runtime proof explicit: if Prism launch automation is unavailable, it returns `manual_required`
instead of pretending success. If you pass a crash report, MythWeaver analyzes it and writes a
runtime repair prompt.

```powershell
python -m mythweaver.cli.main launch-check selected_mods.json --pack-dir output/generated/<pack>
python -m mythweaver.cli.main analyze-crash crash-report.txt --against selected_mods.json
python -m mythweaver.cli.main stabilize-pack selected_mods.json --against output/generated/<pack>/pack_design.json --manual-crash-report crash-report.txt
```

## Runtime proof and smoke testing

A `.mrpack` build is not playable proof. Launcher metadata validation is not playable proof. Prism
starting is not playable proof. MythWeaver treats a pack as runtime-proven only when deterministic
smoke-test markers show the generated client entered a world and stayed alive long enough.

The validation helper mod is named `mythweaver-smoketest` and lives in
`tooling/mythweaver-smoketest/`. It is a tiny Fabric 1.20.1 Java 17 mod with no gameplay content. It
is injected only into validation instances, logs `[MythWeaverSmokeTest]` markers, and is excluded
from final exports. The minimum useful pass is `CLIENT_READY`, `SERVER_STARTED`,
`PLAYER_JOINED_WORLD`, and `STABLE_60_SECONDS`. `STABLE_120_SECONDS` is preferred for a 120 second
validation window. Broad vanilla log lines, Prism opening, main menu, and world join alone are not
enough.

If the helper jar is unavailable, MythWeaver reports `manual_required` rather than faking stability.
Build the helper jar or point MythWeaver at one with `MYTHWEAVER_SMOKETEST_MOD_PATH`.

```powershell
$env:PYTHONPATH='src'; python tooling/mythweaver-smoketest/build_smoketest.py
$env:MYTHWEAVER_SMOKETEST_MOD_PATH = "C:\MythWeaver\resources\mythweaver-smoketest.jar"
python -m mythweaver.cli.main launch-check --launcher prism --instance-path <instance-path> --wait-seconds 120 --inject-smoke-test-mod --validation-world
python -m mythweaver.cli.main launch-check --latest-log latest.log --wait-seconds 120
python -m mythweaver.cli.main launch-check --crash-report crash-report.txt --output-dir output/generated/<pack>
python -m mythweaver.cli.main autonomous-build concepts/peacekeeper_worldbreaker.md --selected-mods examples/peacekeeper_worldbreaker.selected_mods.json --launcher prism --memory-mb 8192 --wait-seconds 120 --inject-smoke-test-mod --validation-world
```

Prism is the canonical runtime automation target. MythWeaver registers or copies generated Prism
instances into Prism's configured instances folder before using `--launch <instance-id>`. It records
the generated instance path, registered Prism instance path, instance id, latest.log, process exit
code, crash report path, freeze detection, and `runtime_evidence_report.json`. If the generated
instance cannot be registered or identified, MythWeaver returns `manual_required` instead of
launching a random similarly named instance.

### Runtime proof self-test

The test module `tests/test_end_to_end_runtime_contract.py` is a simulated runtime proof contract
check. It validates MythWeaver's proof plumbing with fixture Prism metadata, a fake helper jar,
validation-world lifecycle, and exact `[MythWeaverSmokeTest]` log markers. It does not launch
Minecraft and does not replace a real `launch-check`; it only proves the automation wiring cannot
call a pack stable without explicit smoke-test proof.

`stabilize-pack` runs the backend loop: `agent-check`, `verify-list`, dry-run build, launch/manual
crash analysis, and safe selected-list repair. For known optional runtime failures, such as HWG
requiring an incompatible AzureLib API or Inventory Profiles Next crashing on world join, MythWeaver
prefers removing or replacing the risky optional mod with an audit entry instead of asking the user
to hand-edit jars or debug stack traces.

## Autonomous pack creation

MythWeaver's target workflow is concept -> selected mods -> build -> launcher setup -> launch
validation -> auto repair. Cursor/Codex remains the creative agent, but MythWeaver provides the
deterministic backend checks so the user is not left manually fixing vanilla imports, missing Fabric
loaders, RAM settings, crash reports, or optional broken mods.

Dry-run is not enough. Launcher setup validates Fabric, Minecraft version, the mods folder, and RAM.
`launch-check`, `stabilize-pack`, or `autonomous-build` should pass before a pack is called finished.

```powershell
python -m mythweaver.cli.main autonomous-build concepts/peacekeeper_worldbreaker.md --launcher modrinth --memory-mb 8192
python -m mythweaver.cli.main autonomous-build concepts/peacekeeper_worldbreaker.md --launcher prism --memory-mb 8192
```

If direct launcher automation is unavailable, MythWeaver returns `manual_required`, writes exact
launcher import/configuration instructions, and can validate the resulting instance files afterward.
It does not claim success unless launcher validation and MythWeaver smoke-test runtime markers
provide real evidence.

## What Works In This Milestone

- Fabric-first contracts and scoring.
- Modrinth API v2 search/client layer with user-agent, retry, rate-limit, and SQLite cache support.
- Deterministic candidate scoring and hard rejection for loader/version/status/file issues.
- Required dependency resolution with machine-readable rejection reasons.
- Official `.mrpack` export with safe override path validation.
- Prism/MultiMC-style instance folder writer.
- Verified download and SHA-1/SHA-512 checking.
- Datapack/lore generation through a known safe recipe.
- Prism launch validation skip/pass/fail reporting.
- Crash analysis for common dependency, mixin, version, duplicate, Java, and config failures.
- REST, CLI, TUI fallback, and MCP-style stdio surfaces.
- Optional OpenAI-compatible/local adapter layer, disabled by default.

## Install

Install Python 3.12 or newer, then from `C:\MythWeaver`:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .[dev]
```

In this Codex desktop workspace, Python is available at:

```powershell
C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

The bundled Python does not include all runtime web dependencies, but it can run the core test
suite:

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

## Configuration

Copy `.env.example` and set paths as needed:

```powershell
copy .env.example .env
```

Important variables:

- `MYTHWEAVER_MODRINTH_USER_AGENT`: unique Modrinth API user-agent.
- `MYTHWEAVER_DATA_DIR`: local cache and state directory.
- `MYTHWEAVER_OUTPUT_DIR`: generated pack output directory.
- `MYTHWEAVER_PRISM_PATH`: Prism executable path for launch validation.
- `MYTHWEAVER_PRISM_ROOT`: Prism root directory.
- `MYTHWEAVER_PRISM_PROFILE`: optional Prism account profile for launch.
- `MYTHWEAVER_PRISM_EXECUTABLE_PATH`: preferred Prism executable path; overrides `MYTHWEAVER_PRISM_PATH`.
- `MYTHWEAVER_PRISM_INSTANCES_PATH`: preferred Prism instances/root path; overrides `MYTHWEAVER_PRISM_ROOT`.
- `MYTHWEAVER_PRISM_ACCOUNT_NAME`: optional Prism account/profile name; overrides `MYTHWEAVER_PRISM_PROFILE`.
- `MYTHWEAVER_LAUNCH_TIMEOUT_SECONDS`: launch validation timeout; default `300`.
- `MYTHWEAVER_JAVA_PATH`: optional Java executable path for future validation adapters.
- `MYTHWEAVER_VALIDATION_ENABLED`: set to `true` to allow automatic Prism launch validation.
- `MYTHWEAVER_AI_BASE_URL`: optional local/OpenAI-compatible endpoint. Leave unset for agent-first mode.

Compatibility memory is advisory local state stored under:

```text
<MYTHWEAVER_DATA_DIR>/knowledge/local/compatibility_memory.json
```

It records successful and failed local pack combinations, including manual validation notes. It never
overrides Modrinth verification; search, inspect, compare, and verify-list only use it for warnings
and confidence hints.

## CLI

```powershell
mythweaver tools
mythweaver search "volcanic caves" --minecraft 1.20.1 --loader fabric --limit 20
mythweaver inspect sodium --minecraft 1.20.1 --loader fabric
mythweaver compare sodium lithium ferrite-core --minecraft 1.20.1 --loader fabric
mythweaver agent-workflow-prompt concepts\cozy_beautiful_world.md
mythweaver verify-list docs\examples\selected_mods\ashfall-frontier.json
mythweaver review-list profiles\kingdoms-after-dark.selected_mods.json
mythweaver agent-check profiles\kingdoms-after-dark.selected_mods.json --against output\generated\kingdoms-after-dark\pack_design.json
mythweaver resolve docs\examples\selected_mods\ashfall-frontier.json
mythweaver build-from-list docs\examples\selected_mods\ashfall-frontier.json --output output\generated\ashfall-frontier
mythweaver build-from-list docs\examples\selected_mods\ashfall-frontier.json --output output\generated\ashfall-frontier --validate-launch
mythweaver agent-pack docs\examples\selected_mods\ashfall-frontier.json
mythweaver agent-pack docs\examples\selected_mods\ashfall-frontier.json --validate-launch
mythweaver validate-pack output\generated\ashfall-frontier
mythweaver repair-plan output\generated\ashfall-frontier
mythweaver apply-repair output\generated\ashfall-frontier\repair_report.json --option-id repair_001 --selected-mods docs\examples\selected_mods\ashfall-frontier.json --output output\generated\ashfall-frontier\selected_mods.repaired.json
mythweaver hud
mythweaver handoff export --concept "medieval survival with castles" --output mythweaver_handoff.zip
mythweaver handoff validate selected_mods.json
mythweaver handoff import selected_mods.json --output profiles\imported.selected_mods.json
mythweaver generate "A horrifying infinite winter survival world" --dry-run
mythweaver analyze-failure .\latest.log
mythweaver serve
mythweaver tui
```

## REST

Run:

```powershell
mythweaver serve
```

Then call:

- `GET /v1/health`
- `GET /v1/tools`
- `POST /v1/search_modrinth`
- `POST /v1/search_mods`
- `POST /v1/inspect_mod`
- `POST /v1/compare_mods`
- `POST /v1/verify_mod_list`
- `POST /v1/resolve_mod_list`
- `POST /v1/build_from_list`
- `POST /v1/export_pack`
- `POST /v1/analyze_mods`
- `POST /v1/score_candidates`
- `POST /v1/resolve_dependencies`
- `POST /v1/detect_conflicts`
- `POST /v1/build_pack`
- `POST /v1/generate_configs`
- `POST /v1/validate_launch`
- `POST /v1/analyze_failure`
- `POST /v1/generate`
- `POST /v1/plan_modpack_searches`
- `POST /v1/discover_candidates`
- `POST /v1/expand_dependencies`

## MCP-Style Stdio

Run:

```powershell
mythweaver-mcp
```

The server accepts JSON-RPC-style lines:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

Tool calls use:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"analyze_failure","arguments":{"log_text":"Mixin apply failed"}}}
```

## Agent Workflow

The recommended path is now agent-selected-list first. Cursor, Codex, or another external agent
should do the creative interpretation and optional web research. MythWeaver should act as the local
Modrinth verification/build engine.

Recommended workflow:

1. User gives a fantasy to Cursor/Codex.
2. Cursor/Codex makes the concept and searches MythWeaver:

```powershell
python -m mythweaver.cli.main search "volcanic caves" --loader fabric --minecraft 1.20.1 --limit 20
python -m mythweaver.cli.main inspect sodium --loader fabric --minecraft 1.20.1
python -m mythweaver.cli.main compare sodium lithium ferrite-core --loader fabric --minecraft 1.20.1
```

3. Cursor/Codex researches externally if useful, then writes `selected_mods.json`.
4. Cursor/Codex verifies, reviews, and builds:

```powershell
python -m mythweaver.cli.main verify-list docs/examples/selected_mods/ashfall-frontier.json
python -m mythweaver.cli.main review-list docs/examples/selected_mods/ashfall-frontier.json
python -m mythweaver.cli.main build-from-list docs/examples/selected_mods/ashfall-frontier.json --output output/generated/ashfall-frontier
```

`verify-list` checks installability for the selected loader/version. `review-list` checks list quality
before build: pillar coverage, duplicate systems, stale or low-signal mods, novelty picks,
dependency impact, and compatibility-memory risks. `build-from-list` is the step that writes pack
artifacts.

5. Cursor/Codex inspects `review_report.json`, `generation_report.json`, and `generation_report.md`, replaces failed or weak mods, and reruns.

Cursor prompt example:

```text
Use MythWeaver as a local Modrinth search/build engine. Search for compatible Fabric mods, choose a curated mod list yourself, then ask MythWeaver to verify and build it.
```

The older prompt/profile generator remains available as a convenience path:

```powershell
python -m mythweaver.cli.main generate --profile docs/examples/profiles/the-sun-forgot-us.json --dry-run --limit 35
```

Lower-level deterministic tools:

1. `search_mods`
2. `inspect_mod`
3. `compare_mods`
4. `verify_mod_list`
5. `resolve_mod_list`
6. `build_from_list` / `export_pack`
7. `validate_launch`
8. `analyze_failure`

The service never accepts hallucinated mod names as truth. Every installable file must resolve to
verified Modrinth metadata and hashes.

## Tests

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

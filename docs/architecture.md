# Architecture

MythWeaver is split into three layers.

## Agent Tool Layer

External agents call deterministic operations through:

- REST: `src/mythweaver/api/app.py`
- CLI/TUI: `src/mythweaver/cli/`
- MCP-style stdio: `src/mythweaver/mcp/server.py`

These surfaces share one facade: `src/mythweaver/tools/facade.py`. Agent-selected-list commands
delegate to `src/mythweaver/pipeline/agent_service.py` so CLI, REST, and MCP do not duplicate
verification, dependency, or build logic.

## Deterministic Intelligence Layer

Core modules do the real work:

- `modrinth`: API v2 calls, facets, response mapping, caching.
- `sources`: official/API/manual source providers and export policy for Modrinth, CurseForge,
  local jars, GitHub releases, Planet Minecraft/manual pages, and direct URLs.
- `pipeline/agent_service`: selected mod list verification, inspect/compare/search wrappers,
  dependency hydration, and build/export reports for external agents.
- `catalog`: scoring, Minecraft version policy, loader normalization, and target negotiation.
- `resolver`: required dependencies, incompatibilities, rejection reasons.
- `builders`: downloads, hash checks, `.mrpack`, Prism instance folders.
- `runtime`: private Java/Mojang/Fabric runtime preparation, isolated validation instances,
  launch command construction, monitoring, deterministic classifiers, and runtime repair actions.
- `autopilot`: autonomous target/build/runtime/repair retry loop with memory and stop limits.
- `configs`: typed generated-content recipes.
- `validation`: Prism launch adapter and crash analysis.
- `db`: SQLite JSON cache.

AI output is never trusted as installable truth. LLMs can propose structured intent or select a mod
list, but MythWeaver verifies real project IDs, versions, loaders, game versions, file URLs, and
hashes before build. CurseForge support is official API only. Planet Minecraft is manual discovery
only. Direct URLs are blocked by default.

Autopilot reuses these source/export decisions. It can only validate jars that are eligible for
`local_instance` use, so CurseForge manifest-only files, manual-only pages, and unsafe direct URLs
never become private-runtime inputs. V1 private runtime supports Fabric. Forge, NeoForge, and Quilt
return explicit unsupported runtime issues until dedicated installers exist.

Runtime proof is shared with the older launcher smoke-test system. The private runtime parses the
same `[MythWeaverSmokeTest]` markers and only allows Autopilot `verified_playable` when the required
client-ready, integrated-server-started, world-joined, and stability markers are present. Main-menu
or client-start log lines are stored as weak proof levels for diagnostics, not as playable proof.
Evidence artifacts are written under each isolated runtime attempt, including
`runtime_launch_report.json`, `runtime_evidence.txt`, and `marker_summary.json`.

Runtime failure intelligence is centralized in `runtime/diagnosis.py`. It turns bounded log/crash
evidence into deterministic diagnoses such as missing dependency, Fabric API missing, wrong loader,
Java incompatibility, mixin failure, duplicate mod, config parse error, access widener failure,
missing class, method mismatch, side mismatch, and unknown runtime failure. Repair planning stays
separate: only diagnoses with safe, trusted actions are auto-applied by Autopilot, and all others
are recorded as blocking/manual instead of being guessed around.

Real private-runtime smoke tests are documented in `docs/autopilot-smoke-test.md` and are opt-in.
Automated tests use fake processes and fixture metadata so CI does not require Mojang, Fabric,
CurseForge, or Microsoft network/auth access.

## Optional AI Layer

`src/mythweaver/ai_optional/` contains an OpenAI-compatible adapter for local endpoints such as
Ollama, LM Studio, llama.cpp servers, and compatible hosted APIs.

The adapter is off by default. The system works without it.

## Build Outputs

The first milestone produces:

- Official `.mrpack` archives with `modrinth.index.json`.
- CurseForge manifest zips with `manifest.json` when every file has official projectID/fileID.
- Prism/MultiMC-style instance folders with `instance.cfg`, `mmc-pack.json`, and `.minecraft/mods`.
- Generated datapack/resource files through safe recipes.
- Machine-readable validation reports.

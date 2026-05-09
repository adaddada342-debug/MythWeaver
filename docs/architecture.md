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
- `pipeline/agent_service`: selected mod list verification, inspect/compare/search wrappers,
  dependency hydration, and build/export reports for external agents.
- `catalog`: scoring and Minecraft version policy.
- `resolver`: required dependencies, incompatibilities, rejection reasons.
- `builders`: downloads, hash checks, `.mrpack`, Prism instance folders.
- `configs`: typed generated-content recipes.
- `validation`: Prism launch adapter and crash analysis.
- `db`: SQLite JSON cache.

AI output is never trusted as installable truth. LLMs can propose structured intent or select a mod
list, but MythWeaver verifies Modrinth project IDs, versions, loaders, game versions, file URLs, and
hashes before build.

## Optional AI Layer

`src/mythweaver/ai_optional/` contains an OpenAI-compatible adapter for local endpoints such as
Ollama, LM Studio, llama.cpp servers, and compatible hosted APIs.

The adapter is off by default. The system works without it.

## Build Outputs

The first milestone produces:

- Official `.mrpack` archives with `modrinth.index.json`.
- Prism/MultiMC-style instance folders with `instance.cfg`, `mmc-pack.json`, and `.minecraft/mods`.
- Generated datapack/resource files through safe recipes.
- Machine-readable validation reports.

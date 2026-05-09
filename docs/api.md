# Public Tool API

All surfaces expose the same conceptual tools.

The primary path for external agents is now selected-list first: agents search, inspect, compare,
and choose mods; MythWeaver verifies and builds from that deterministic list.

## `search_mods`

Input: query plus loader, Minecraft version, limit, include/exclude keywords, capability, role, side
support, minimum downloads, and sort.

Returns agent-friendly search results with installability, latest compatible version, likely
capabilities, probable role, dependency count, warnings, and novelty/micro-mod signals.

## `inspect_mod`

Input: Modrinth slug or project ID plus loader/Minecraft version.

Returns project metadata, compatible versions, dependencies, side support, files and hashes,
installability status, capability guesses, and source links from Modrinth metadata.

## `compare_mods`

Input: a list of Modrinth slugs/IDs plus loader/Minecraft version.

Returns comparable compatibility, dependency, capability, update, download/follower, side support,
and warning fields for each candidate.

## `verify_mod_list`

Input: `SelectedModList`

Verifies every user/agent-selected mod exists on Modrinth, is a mod project, has a compatible
loader/Minecraft version, has installable HTTPS files and hashes, and records rejected or
incompatible mods.

## `resolve_mod_list`

Input: `SelectedModList`

Runs verification, hydrates required dependency metadata, distinguishes `user_selected_mods` from
`dependency_added_mods`, and fails clearly when a required dependency chain cannot resolve.

## `build_from_list` / `export_pack`

Input: `SelectedModList`, output directory, `download`, optional `validate_launch`

Verifies, resolves dependencies, downloads when requested, writes `.mrpack` and Prism artifacts, and
writes `generation_report.json` / `generation_report.md` for the agent to inspect. When
`validate_launch=true`, launch validation runs only if Prism is configured and validation is enabled.
Otherwise the report records a skipped validation state.

Reports include launch validation and advisory local memory fields:

- `validation_status`
- `launch_validation`
- `logs_collected`
- `crash_analysis`
- `compatibility_memory_updates`
- `known_good_matches`
- `known_risk_matches`

Compatibility memory is stored locally at
`<MYTHWEAVER_DATA_DIR>/knowledge/local/compatibility_memory.json`.

## `validate_pack`

Input: generated pack directory plus optional pack name or Prism instance ID.

Collects `latest.log` and `crash-reports/*.txt` when available, optionally launches through Prism,
classifies failures, and returns a `ValidationReport`. If Prism is missing or validation is disabled,
the status is `skipped`; MythWeaver never reports a fake launch success.

## `create_repair_plan`

Input: generated pack directory or explicit `generation_report.json` path.

Reads validation results and available logs, classifies the failure, records advisory compatibility
memory, and writes `repair_report.json` / `repair_report.md`. It only proposes repair options and
does not modify selected mod lists or generated pack files.

## `apply_repair_option`

Input: `repair_report.json`, one `option_id`, original `selected_mods.json`, and output path.

Applies exactly one selected repair option to a new selected mod list, preserves the original file,
and writes a repair changelog entry. Risky options still require the external agent to choose the
option explicitly.

## `search_modrinth`

Input: `SearchPlan`

Searches Modrinth with official facets for project type, loader category, Minecraft version,
project categories, and side support.

## `analyze_mods`

Input: list of `CandidateMod`

Returns compact metadata summaries for external agents.

## `score_candidates`

Input: `RequirementProfile`, list of `CandidateMod`

Scores candidates by:

- theme/system relevance
- explicit profile search keywords, anchors, and capabilities
- negative keywords, forbidden capabilities, and explicit exclusions
- loader and Minecraft compatibility
- project quality signals
- release stability
- performance category
- dependency penalty

Hard rejects invalid loader/version/status/file candidates and explicit exclusion or forbidden
capability matches.

## `resolve_dependencies`

Input: requested project IDs, candidate pool, `RequirementProfile`

Builds a resolved pack graph, adds required dependencies from the candidate pool, and reports
missing or incompatible dependencies.

## `detect_conflicts`

Input: list of candidates

Reports duplicate functionality groups such as performance, worldgen, mobs, magic, quests, storage,
and maps.

## `build_pack`

Input: `ResolvedPack`, output directory, `download`

Always writes `.mrpack`. When `download=true`, downloads verified Modrinth files, checks hashes, and
creates a Prism instance.

## `generate_configs`

Input: `RequirementProfile`, output directory

Applies known safe recipes. Current milestone generates a datapack with pack metadata and startup
lore hooks.

## `validate_launch`

Input: Prism instance ID

Uses Prism CLI when configured. If Prism path/root is missing, returns a skipped report.

## `analyze_failure`

Input: log text

Classifies common Minecraft failures and returns repair candidates.

## `generate_modpack`

Input: `GenerationRequest`

Runs the full deterministic pipeline: prompt/profile, search planning, Modrinth discovery, version
verification, scoring, pre-dependency quality gate, dependency hydration/expansion, resolution,
build, config generation, optional Prism validation, and report writing.

Profile-first generation remains available as a convenience path:

```powershell
python -m mythweaver.cli.main generate --profile docs/examples/profiles/the-sun-forgot-us.json --dry-run --limit 35
```

## `plan_modpack_searches`

Input: `RequirementProfile`

Creates weighted Fabric Modrinth search plans. Priority is explicit `search_keywords`, required
capabilities, anchors, preferred capabilities, normal profile fields, then fallback prompt
extraction. Search plans include `source_field`, `weight`, and `origin` so agents can correct bad
profile inputs.

## `discover_candidates`

Input: `SearchStrategy`

Searches Modrinth, fetches versions for each project hit, verifies installable files, and returns
candidate mods plus rejection reasons.

## `expand_dependencies`

Input: candidates, `RequirementProfile`, Minecraft version

Fetches missing required dependency versions from Modrinth and returns the expanded candidate pool
plus unresolved dependency rejections. Dependencies are hydrated from Modrinth project metadata and
marked as `dependency_added`, not selected theme mods.

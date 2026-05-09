from __future__ import annotations

from pathlib import Path

from mythweaver.schemas.contracts import BuildArtifact

START_MESSAGE = "State your modpack idea."


def build_agent_prompt(idea: str) -> str:
    """Create the exact handoff prompt an external coding agent should follow."""

    cleaned = idea.strip()
    if not cleaned:
        raise ValueError("modpack idea must not be empty")
    return f"""# MythWeaver Agent Run

User modpack idea:

{cleaned}

You are the external AI orchestrator. MythWeaver is the deterministic local Minecraft
modpack intelligence service in this folder. No internal MythWeaver AI provider is required.

Follow this workflow:

1. Convert the idea into a structured RequirementProfile.
2. Search Modrinth with search_modrinth using Fabric first and minecraft_version "auto" unless the user asked otherwise.
3. Fetch and verify real Modrinth project/version/file metadata before selecting any mod.
4. Score candidates with score_candidates.
5. Resolve dependencies with resolve_dependencies.
6. Check duplicate functionality with detect_conflicts.
7. Build the pack with build_pack. Use download=false only when doing a dry run.
8. Generate safe datapack/config content with generate_configs.
9. Validate launch with validate_launch when Prism is configured.
10. If launch or validation fails, call analyze_failure and repair the plan before trying again.

Rules:

- Do not invent Modrinth projects, IDs, versions, loaders, hashes, or URLs.
- Do not install anything that MythWeaver cannot verify.
- Prefer coherent, playable curation over many loosely related mods.
- Explain every selected and rejected mod in the final response.
- Put artifacts under output/generated/<short-pack-name>/.
"""


def write_agent_session(idea: str, output_dir: Path) -> BuildArtifact:
    """Write user-friendly request files that agents can read and continue from."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "modpack_request.txt").write_text(idea.strip() + "\n", encoding="utf-8")
    prompt = build_agent_prompt(idea)
    (output_dir / "agent_next_steps.md").write_text(prompt, encoding="utf-8")
    return BuildArtifact(
        kind="agent-session",
        path=str(output_dir),
        metadata={
            "request_file": str(output_dir / "modpack_request.txt"),
            "agent_steps_file": str(output_dir / "agent_next_steps.md"),
        },
    )


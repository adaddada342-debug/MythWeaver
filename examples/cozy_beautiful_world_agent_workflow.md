# Cozy Beautiful World Agent Workflow

Cozy Beautiful World is a peaceful Fabric 1.20.1 pack concept about farming, cooking, decorating a home base, gentle village life, soft exploration, and a beautiful world that feels welcoming instead of punishing.

Generate the Cursor/Codex workflow prompt:

```powershell
python -m mythweaver.cli.main agent-workflow-prompt examples/cozy_beautiful_world.md --output-dir output/generated/cozy-beautiful-world-agent-workflow
```

Paste `output/generated/cozy-beautiful-world-agent-workflow/cursor_composer_prompt.md` into Cursor Composer, Codex, Claude, or Gemini. The AI agent should use MythWeaver as the backend verifier while it makes the creative decisions: preserve the cozy fantasy, choose real Modrinth mods, avoid bloat, and keep removals or replacements auditable.

After the agent creates or updates `selected_mods.json`, run:

```powershell
python -m mythweaver.cli.main agent-check selected_mods.json --against output/generated/cozy-beautiful-world-agent-workflow/pack_design.json --output-dir output/generated/cozy-beautiful-world-agent-workflow
python -m mythweaver.cli.main verify-list selected_mods.json
python -m mythweaver.cli.main build-from-list selected_mods.json --dry-run
```

Done means there are no hard blockers, no unsupported loader/version issues, no missing required dependencies, no silent dropped mods, and the dry run produces clean build artifacts. Subjective duplicate or theme-fit notes should be reviewed by the AI agent as creative signals, not obeyed blindly.

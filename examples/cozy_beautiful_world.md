# Cozy Beautiful World Example

This example is a cozy, building-focused survival pack concept for Fabric 1.20.1.

Intended experience:
- spawn into a pretty world and explore nearby biomes/villages
- gather materials and build a charming home
- expand farms, cooking, and animal areas
- decorate interiors/exteriors, paths, bridges, and gardens
- slowly grow a beautiful long-term settlement (solo or small SMP)

## Regenerate design

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m mythweaver.cli.main design-pack concepts/cozy_beautiful_world.md --output output/generated/cozy-beautiful-world --name "Cozy Beautiful World" --minecraft-version 1.20.1 --loader fabric
```

## Regenerate design review

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m mythweaver.cli.main review-design output/generated/cozy-beautiful-world/pack_design.json --output output/generated/cozy-beautiful-world
```

## Regenerate blueprint and cloud selection prompt

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m mythweaver.cli.main blueprint-pack output/generated/cozy-beautiful-world/pack_design.json --output output/generated/cozy-beautiful-world
```

## Review selected mods against design

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m mythweaver.cli.main review-list examples/cozy_beautiful_world.selected_mods.json --against output/generated/cozy-beautiful-world/pack_design.json
```

## Verify and dry-run build

```powershell
$env:PYTHONPATH='src'
& 'C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m mythweaver.cli.main verify-list examples/cozy_beautiful_world.selected_mods.json
& 'C:\Users\Adrian Iliev\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m mythweaver.cli.main build-from-list examples/cozy_beautiful_world.selected_mods.json --dry-run --output output/generated/cozy-beautiful-world
```

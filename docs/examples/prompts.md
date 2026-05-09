# Example Prompts

External agents should convert these into `RequirementProfile` JSON before calling MythWeaver.

## Infinite Winter Survival

```text
I want a horrifying infinite winter survival world with ancient ruins, abandoned villages,
realistic terrain, terrifying creatures, and progression similar to The Long Dark.
```

Suggested profile:

```json
{
  "name": "Infinite Winter",
  "themes": ["winter", "horror", "survival"],
  "terrain": ["snow", "mountains", "frozen oceans", "ruins"],
  "gameplay": ["resource scarcity", "hostile nights", "exploration"],
  "mood": ["isolated", "hopeless"],
  "desired_systems": ["temperature", "dynamic weather", "structures", "hostile mobs"],
  "performance_target": "balanced",
  "multiplayer": "singleplayer",
  "loader": "fabric",
  "minecraft_version": "auto"
}
```

## Anime Apocalypse

```text
I want an anime apocalypse modpack where the player becomes a reality-destroying god.
```

Suggested profile:

```json
{
  "name": "Anime Apocalypse",
  "themes": ["anime", "apocalypse", "godlike progression"],
  "terrain": ["ruined cities", "wasteland"],
  "gameplay": ["combat progression", "boss fights", "power scaling"],
  "mood": ["dramatic", "cataclysmic"],
  "desired_systems": ["magic", "skills", "quests", "bosses"],
  "performance_target": "balanced",
  "multiplayer": "both",
  "loader": "fabric",
  "minecraft_version": "auto"
}
```

## Cozy Fantasy Farming

```text
A peaceful fantasy farming RPG with kingdoms, magic, dragons, cozy villages, and deep exploration.
```

Suggested profile:

```json
{
  "name": "Cozy Kingdoms",
  "themes": ["fantasy", "farming", "rpg", "cozy"],
  "terrain": ["villages", "kingdoms", "forests"],
  "gameplay": ["farming", "exploration", "trading", "magic"],
  "mood": ["peaceful", "wonder"],
  "desired_systems": ["crops", "villages", "dragons", "quests"],
  "performance_target": "balanced",
  "multiplayer": "both",
  "loader": "fabric",
  "minecraft_version": "auto"
}
```


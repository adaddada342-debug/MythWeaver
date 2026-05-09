# Ironwood Frontier

Ironwood Frontier is a Fabric 1.20.1 cozy frontier survival and settlement pack. The fantasy is
simple: spawn in scenic wild terrain, build a cabin or camp, farm and cook, lay roads and bridges,
add windmills or waterwheels and small workshop machinery with Create kept light and aesthetic, and
slowly shape the wilderness into a warm home.

The stack prioritizes performance, Terralith-style scenic terrain, improved villages, light
exploration structures, wildlife, ambience, polished visuals, cozy building palettes (Chipped,
Rechiseled, Macaw suites, furniture mods), Farmer's Delight with optional More Delight on Modrinth,
Tom's Simple Storage and Traveler's Backpack, Xaero maps with Nature's Compass, Waystones and
Comforts for measured travel, and relaxed client QoL (EMI, Jade, Mod Menu, AppleSkin, Mouse Tweaks,
Shulker Box Tooltip). Croptopia is not listed when only Modrinth resolves cleanly; CurseForge is
only used if the official API accepts requests. Inventory Profiles Next is omitted unless future
runtime checks prove it stable.

Shaders are not required. Heavy tech, guns, and hardcore survival realism are out of scope.

Stability rules:

- Required dependency closure must pass before export.
- CurseForge is used only through the official API when `CURSEFORGE_API_KEY` is configured; the key
  must never be printed or persisted in reports.
- Runtime stability must be proven by MythWeaver or reported honestly as `manual_required`.
- Optional mods that break resolution or runtime should be removed or replaced with verified
  alternatives while preserving the frontier homestead identity.

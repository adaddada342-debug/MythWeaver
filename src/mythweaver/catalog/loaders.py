from __future__ import annotations

SUPPORTED_LOADERS = (
    "fabric",
    "forge",
    "neoforge",
    "quilt",
    "vanilla",
    "liteloader",
    "rift",
    "babric",
    "legacy_fabric",
    "unknown",
)

loader_aliases: dict[str, str] = {
    "fabric loader": "fabric",
    "minecraft forge": "forge",
    "neo forge": "neoforge",
    "neo-forge": "neoforge",
    "neo_forge": "neoforge",
    "neoforged": "neoforge",
    "quilt loader": "quilt",
    "legacy fabric": "legacy_fabric",
    "legacy-fabric": "legacy_fabric",
    "liteloader": "liteloader",
    "lite loader": "liteloader",
}

_CURSEFORGE_NAMES = {
    "fabric": "Fabric",
    "forge": "Forge",
    "neoforge": "NeoForge",
    "quilt": "Quilt",
    "liteloader": "LiteLoader",
    "rift": "Rift",
}

_PRISM_COMPONENT_UIDS = {
    "fabric": "net.fabricmc.fabric-loader",
    "forge": "net.minecraftforge",
    "neoforge": "net.neoforged",
    "quilt": "org.quiltmc.quilt-loader",
}

_MODRINTH_CATEGORIES = {
    "fabric": "fabric",
    "forge": "forge",
    "neoforge": "neoforge",
    "quilt": "quilt",
}


def normalize_loader(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", " ")
    normalized = " ".join(normalized.split())
    if not normalized:
        return "unknown"
    if normalized in {"auto", "any"}:
        return normalized
    canonical = loader_aliases.get(normalized, normalized.replace(" ", "_"))
    return canonical if canonical in SUPPORTED_LOADERS else "unknown"


def is_modded_loader(value: str) -> bool:
    return normalize_loader(value) not in {"vanilla", "unknown", "auto", "any"}


def curseforge_loader_name(loader: str) -> str | None:
    return _CURSEFORGE_NAMES.get(normalize_loader(loader))


def prism_component_uid(loader: str) -> str | None:
    return _PRISM_COMPONENT_UIDS.get(normalize_loader(loader))


def modrinth_loader_category(loader: str) -> str | None:
    return _MODRINTH_CATEGORIES.get(normalize_loader(loader))

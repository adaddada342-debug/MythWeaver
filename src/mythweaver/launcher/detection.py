from __future__ import annotations

from .base import LauncherAdapter
from .modrinth import ModrinthLauncherAdapter
from .prism import PrismLauncherAdapter


def detect_launcher(launcher: str = "auto", *, env: dict[str, str] | None = None) -> LauncherAdapter:
    normalized = (launcher or "auto").strip().lower()
    if normalized in {"modrinth", "modrinth-app", "modrinth_app"}:
        return ModrinthLauncherAdapter(env=env)
    if normalized in {"prism", "prismlauncher", "prism-launcher", "multimc"}:
        return PrismLauncherAdapter(env=env)
    if normalized == "auto":
        for adapter in (PrismLauncherAdapter(env=env), ModrinthLauncherAdapter(env=env)):
            if adapter.detect_installation().status == "found":
                return adapter
        return PrismLauncherAdapter(env=env)
    return ModrinthLauncherAdapter(env=env)

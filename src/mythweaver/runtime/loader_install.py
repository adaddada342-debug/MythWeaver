from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any, Callable, cast

from pydantic import Field

from mythweaver.catalog.loaders import normalize_loader
from mythweaver.runtime.classifiers import unsupported_loader_issue
from mythweaver.runtime.contracts import RuntimeIssue
from mythweaver.schemas.contracts import AgentSafeModel

FABRIC_LOADER_VERSIONS_URL = "https://meta.fabricmc.net/v2/versions/loader"


class LoaderRuntime(AgentSafeModel):
    loader: str
    loader_version: str
    main_class: str
    classpath: list[str] = Field(default_factory=list)
    game_arguments: list[str] = Field(default_factory=list)


class LoaderInstallResult(AgentSafeModel):
    runtime: LoaderRuntime | None = None
    issues: list[RuntimeIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def install_loader_runtime(
    loader: str,
    minecraft_version: str,
    cache_root: Path,
    *,
    loader_version: str | None = None,
    fetch_json: Callable[[str], Any] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
) -> LoaderInstallResult:
    normalized = normalize_loader(loader)
    if normalized != "fabric":
        return LoaderInstallResult(issues=[unsupported_loader_issue(loader)])
    fetch_json = fetch_json or _fetch_json
    fetch_bytes = fetch_bytes or _fetch_bytes
    selected_version = loader_version or _latest_stable_fabric_loader(fetch_json(FABRIC_LOADER_VERSIONS_URL))
    profile_url = f"https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{selected_version}/profile/json"
    profile = fetch_json(profile_url)
    classpath = _download_libraries(profile, Path(cache_root) / "fabric-libraries", fetch_bytes)
    main_class = _fabric_main_class(profile)
    return LoaderInstallResult(
        runtime=LoaderRuntime(
            loader="fabric",
            loader_version=selected_version,
            main_class=main_class,
            classpath=classpath,
            game_arguments=_profile_game_arguments(profile),
        )
    )


def _latest_stable_fabric_loader(items: list[dict[str, Any]]) -> str:
    for item in items:
        if item.get("stable", True) and item.get("version"):
            return str(item["version"])
    if items and items[0].get("version"):
        return str(items[0]["version"])
    raise ValueError("Fabric loader metadata did not include any loader versions.")


def _fabric_main_class(profile: dict[str, Any]) -> str:
    main_class = profile.get("mainClass")
    if isinstance(main_class, dict):
        return str(main_class.get("client") or "net.fabricmc.loader.impl.launch.knot.KnotClient")
    if isinstance(main_class, str):
        return main_class
    return "net.fabricmc.loader.impl.launch.knot.KnotClient"


def _download_libraries(profile: dict[str, Any], root: Path, fetch_bytes: Callable[[str], bytes]) -> list[str]:
    libs: list[str] = []
    libraries = profile.get("libraries") or {}
    items: list[dict[str, Any]] = []
    if isinstance(libraries, dict):
        for key in ("common", "client"):
            items.extend(libraries.get(key) or [])
    for library in items:
        name = library.get("name")
        base_url = library.get("url")
        if not name or not base_url:
            continue
        target = root / _maven_path(str(name))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            target.write_bytes(fetch_bytes(str(base_url).rstrip("/") + "/" + _maven_path(str(name)).replace(os.sep, "/")))
        libs.append(os.fspath(target))
    return libs


def _maven_path(coordinate: str) -> str:
    group, artifact, version = coordinate.split(":")[:3]
    return os.path.join(*group.split("."), artifact, version, f"{artifact}-{version}.jar")


def _profile_game_arguments(profile: dict[str, Any]) -> list[str]:
    arguments = profile.get("arguments", {}).get("game") if isinstance(profile.get("arguments"), dict) else None
    return [item for item in arguments if isinstance(item, str)] if isinstance(arguments, list) else []


def _fetch_json(url: str) -> Any:
    import json

    return json.loads(_fetch_bytes(url).decode("utf-8"))


def _fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return cast(bytes, response.read())

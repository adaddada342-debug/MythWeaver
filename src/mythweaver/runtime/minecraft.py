from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, cast

from pydantic import Field

from mythweaver.schemas.contracts import AgentSafeModel

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


class MinecraftClientRuntime(AgentSafeModel):
    version_id: str
    client_jar: str
    libraries: list[str] = Field(default_factory=list)
    assets_dir: str
    asset_index: str
    natives_dir: str
    main_class: str
    game_arguments: list[str] = Field(default_factory=list)


def prepare_minecraft_client(
    minecraft_version: str,
    cache_root: Path,
    *,
    fetch_json: Callable[[str], Any] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
) -> MinecraftClientRuntime:
    fetch_json = fetch_json or _fetch_json
    fetch_bytes = fetch_bytes or _fetch_bytes
    cache_root = Path(cache_root)
    manifest = fetch_json(VERSION_MANIFEST_URL)
    version_meta = _find_version(manifest, minecraft_version)
    version_json = fetch_json(str(version_meta["url"]))
    version_id = str(version_json.get("id") or minecraft_version)
    version_dir = cache_root / "versions" / version_id
    libraries_dir = cache_root / "libraries"
    assets_dir = cache_root / "assets"
    natives_dir = version_dir / "natives"
    version_dir.mkdir(parents=True, exist_ok=True)
    libraries_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    natives_dir.mkdir(parents=True, exist_ok=True)

    client_meta = version_json["downloads"]["client"]
    client_jar = version_dir / f"{version_id}.jar"
    _download_verified(str(client_meta["url"]), client_jar, client_meta.get("sha1"), fetch_bytes)

    libraries: list[str] = []
    for library in version_json.get("libraries", []):
        artifact = ((library.get("downloads") or {}).get("artifact") or {})
        if artifact.get("url") and artifact.get("path"):
            target = libraries_dir / str(artifact["path"])
            _download_verified(str(artifact["url"]), target, artifact.get("sha1"), fetch_bytes)
            libraries.append(os.fspath(target))
        classifiers = (library.get("downloads") or {}).get("classifiers") or {}
        native = _native_classifier(classifiers)
        if native:
            archive = libraries_dir / str(native.get("path") or Path(str(native["url"])).name)
            _download_verified(str(native["url"]), archive, native.get("sha1"), fetch_bytes)
            _extract_natives(archive, natives_dir)

    asset_index = ""
    asset_meta = version_json.get("assetIndex")
    if isinstance(asset_meta, dict) and asset_meta.get("url"):
        asset_index = str(asset_meta.get("id") or "")
        asset_index_json = fetch_json(str(asset_meta["url"]))
        index_path = assets_dir / "indexes" / f"{asset_index}.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(asset_index_json, indent=2, sort_keys=True), encoding="utf-8")
        _download_assets(asset_index_json, assets_dir, fetch_bytes)

    return MinecraftClientRuntime(
        version_id=version_id,
        client_jar=os.fspath(client_jar),
        libraries=libraries,
        assets_dir=os.fspath(assets_dir),
        asset_index=asset_index,
        natives_dir=os.fspath(natives_dir),
        main_class=str(version_json.get("mainClass") or "net.minecraft.client.main.Main"),
        game_arguments=_game_arguments(version_json),
    )


def _find_version(manifest: dict[str, Any], minecraft_version: str) -> dict[str, Any]:
    for item in manifest.get("versions", []):
        if item.get("id") == minecraft_version:
            return cast(dict[str, Any], item)
    raise ValueError(f"Minecraft version not found in Mojang manifest: {minecraft_version}")


def _download_verified(url: str, path: Path, sha1: str | None, fetch_bytes: Callable[[str], bytes]) -> None:
    if path.is_file() and (not sha1 or _sha1(path.read_bytes()) == sha1):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = fetch_bytes(url)
    if sha1 and _sha1(data) != sha1:
        raise ValueError(f"sha1 mismatch for {url}")
    path.write_bytes(data)


def _download_assets(asset_index_json: dict[str, Any], assets_dir: Path, fetch_bytes: Callable[[str], bytes]) -> None:
    objects = asset_index_json.get("objects") or {}
    for meta in objects.values():
        digest = meta.get("hash")
        if not digest:
            continue
        target = assets_dir / "objects" / digest[:2] / digest
        _download_verified(f"https://resources.download.minecraft.net/{digest[:2]}/{digest}", target, digest, fetch_bytes)


def _native_classifier(classifiers: dict[str, Any]) -> dict[str, Any] | None:
    if os.name == "nt":
        keys: tuple[str, ...] = ("natives-windows", "natives-windows-64", "natives-windows-32")
    elif sys_platform() == "darwin":
        keys = ("natives-macos", "natives-osx")
    else:
        keys = ("natives-linux",)
    for key in keys:
        if key in classifiers:
            return cast(dict[str, Any], classifiers[key])
    return None


def sys_platform() -> str:
    import sys

    return sys.platform


def _extract_natives(archive: Path, natives_dir: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as zipped:
            for name in zipped.namelist():
                if name.startswith("META-INF/") or name.endswith("/"):
                    continue
                zipped.extract(name, natives_dir)
    except zipfile.BadZipFile:
        return


def _game_arguments(version_json: dict[str, Any]) -> list[str]:
    arguments = version_json.get("arguments", {}).get("game")
    if isinstance(arguments, list):
        return [item for item in arguments if isinstance(item, str)]
    legacy = version_json.get("minecraftArguments")
    if isinstance(legacy, str):
        return legacy.split()
    return []


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _fetch_json(url: str) -> Any:
    return json.loads(_fetch_bytes(url).decode("utf-8"))


def _fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return cast(bytes, response.read())

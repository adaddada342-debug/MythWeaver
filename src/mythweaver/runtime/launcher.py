from __future__ import annotations

import os

from mythweaver.runtime.loader_install import LoaderRuntime
from mythweaver.runtime.minecraft import MinecraftClientRuntime


def build_launch_command(
    *,
    java_path: str,
    memory_mb: int,
    minecraft: MinecraftClientRuntime,
    loader: LoaderRuntime | None,
    game_dir: str,
    offline_username: str,
) -> list[str]:
    classpath = [minecraft.client_jar, *minecraft.libraries]
    main_class = minecraft.main_class
    game_arguments = list(minecraft.game_arguments)
    if loader is not None:
        classpath.extend(loader.classpath)
        main_class = loader.main_class
        game_arguments.extend(loader.game_arguments)
    command = [
        java_path,
        f"-Xmx{memory_mb}M",
        f"-Djava.library.path={minecraft.natives_dir}",
        "-cp",
        os.pathsep.join(classpath),
        main_class,
    ]
    command.extend(
        _replace_placeholders(
            game_arguments
            + [
                "--username",
                offline_username,
                "--version",
                minecraft.version_id,
                "--gameDir",
                game_dir,
                "--assetsDir",
                minecraft.assets_dir,
                "--assetIndex",
                minecraft.asset_index,
                "--uuid",
                "00000000-0000-0000-0000-000000000000",
                "--accessToken",
                "0",
                "--userType",
                "legacy",
            ],
            offline_username=offline_username,
            minecraft=minecraft,
            game_dir=game_dir,
        )
    )
    return command


def _replace_placeholders(args: list[str], *, offline_username: str, minecraft: MinecraftClientRuntime, game_dir: str) -> list[str]:
    replacements = {
        "${auth_player_name}": offline_username,
        "${version_name}": minecraft.version_id,
        "${game_directory}": game_dir,
        "${assets_root}": minecraft.assets_dir,
        "${assets_index_name}": minecraft.asset_index,
        "${auth_uuid}": "00000000-0000-0000-0000-000000000000",
        "${auth_access_token}": "0",
        "${user_type}": "legacy",
    }
    output = []
    for arg in args:
        for old, new in replacements.items():
            arg = arg.replace(old, new)
        output.append(arg)
    return output

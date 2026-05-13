import unittest


class RuntimeLauncherTests(unittest.TestCase):
    def test_build_command_is_list_with_offline_credentials_and_no_shell(self):
        from mythweaver.runtime.launcher import build_launch_command
        from mythweaver.runtime.loader_install import LoaderRuntime
        from mythweaver.runtime.minecraft import MinecraftClientRuntime

        command = build_launch_command(
            java_path="C:/Java/bin/java.exe",
            memory_mb=4096,
            minecraft=MinecraftClientRuntime(
                version_id="1.20.1",
                client_jar="client.jar",
                libraries=["lib.jar"],
                assets_dir="assets",
                asset_index="5",
                natives_dir="natives",
                main_class="net.minecraft.client.main.Main",
                game_arguments=[],
            ),
            loader=LoaderRuntime(
                loader="fabric",
                loader_version="0.15.11",
                main_class="net.fabricmc.loader.impl.launch.knot.KnotClient",
                classpath=["fabric-loader.jar"],
                game_arguments=[],
            ),
            game_dir=".minecraft",
            offline_username="MythWeaver",
        )

        self.assertIsInstance(command, list)
        self.assertIn("-Xmx4096M", command)
        self.assertIn("net.fabricmc.loader.impl.launch.knot.KnotClient", command)
        self.assertIn("--username", command)
        self.assertIn("MythWeaver", command)


if __name__ == "__main__":
    unittest.main()

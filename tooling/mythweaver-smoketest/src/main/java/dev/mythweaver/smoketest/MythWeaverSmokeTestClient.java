package dev.mythweaver.smoketest;

import net.fabricmc.api.ClientModInitializer;

public final class MythWeaverSmokeTestClient implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        MythWeaverSmokeTest.logMarker("CLIENT_READY");
    }
}

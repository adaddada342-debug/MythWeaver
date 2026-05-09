package dev.mythweaver.smoketest;

import java.util.HashSet;
import java.util.Set;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class MythWeaverSmokeTest implements ModInitializer {
    public static final String MOD_ID = "mythweaver_smoketest";
    public static final String PREFIX = "[MythWeaverSmokeTest]";
    private static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    private static final Set<String> LOGGED_STABILITY_MARKERS = new HashSet<>();
    private static boolean playerJoinedWorld = false;
    private static int ticksAfterJoin = 0;

    @Override
    public void onInitialize() {
        ServerLifecycleEvents.SERVER_STARTING.register(server -> logMarker("SERVER_STARTING"));
        ServerLifecycleEvents.SERVER_STARTED.register(server -> logMarker("SERVER_STARTED"));
        ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> {
            playerJoinedWorld = true;
            ticksAfterJoin = 0;
            LOGGED_STABILITY_MARKERS.clear();
            logMarker("PLAYER_JOINED_WORLD");
        });
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if (!playerJoinedWorld) {
                return;
            }
            ticksAfterJoin++;
            logStabilityMarker("STABLE_30_SECONDS", 20 * 30);
            logStabilityMarker("STABLE_60_SECONDS", 20 * 60);
            logStabilityMarker("STABLE_120_SECONDS", 20 * 120);
        });
    }

    public static void logMarker(String marker) {
        LOGGER.info("{} {}", PREFIX, marker);
    }

    private static void logStabilityMarker(String marker, int requiredTicks) {
        if (ticksAfterJoin >= requiredTicks && LOGGED_STABILITY_MARKERS.add(marker)) {
            logMarker(marker);
        }
    }
}

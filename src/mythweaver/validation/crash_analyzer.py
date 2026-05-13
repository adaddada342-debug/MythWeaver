from __future__ import annotations

import re

from mythweaver.schemas.contracts import FailureAnalysis


def _evidence(log_text: str, patterns: list[str]) -> list[str]:
    lines = log_text.splitlines()
    matched: list[str] = []
    for line in lines:
        lower = line.lower()
        if any(pattern in lower for pattern in patterns):
            matched.append(line.strip())
        if len(matched) >= 5:
            break
    return matched


def analyze_failure(log_text: str) -> FailureAnalysis:
    lower = log_text.lower()

    if "some of your mods are incompatible" in lower or "incompatible mods found" in lower:
        return FailureAnalysis(
            classification="final_artifact_invalid",
            summary="Fabric Loader reported a mass mod incompatibility (often duplicate Fabric mod IDs or wrong-edition jars).",
            evidence=_evidence(log_text, ["incompatible", "mods", "remove", "fabric"]),
            repair_candidates=[
                "Run MythWeaver build_from_list with downloads enabled and inspect final_artifact_validation_report.json.",
                "Remove duplicate Fabric mod IDs (same id in multiple jars) and jars whose fabric.mod.json excludes this Minecraft version.",
                "Re-resolve dependencies so optional duplicates are not both exported.",
            ],
            likely_causes=["duplicate_mod_ids", "wrong_minecraft_version_jars", "invalid_dependency_closure"],
        )

    if "requires" in lower and ("install" in lower or "dependency" in lower or "depends" in lower):
        return FailureAnalysis(
            classification="missing_dependency",
            summary="Minecraft reported an unsatisfied mod dependency.",
            evidence=_evidence(log_text, ["requires", "dependency", "depends", "install"]),
            repair_candidates=[
                "Search Modrinth for the missing project ID or slug.",
                "Resolve the dependency against the same loader and Minecraft version.",
                "Rebuild the pack with the dependency included.",
            ],
        )
    if "mixin" in lower and ("failed" in lower or "apply" in lower):
        return FailureAnalysis(
            classification="mixin_failure",
            summary="A mixin failed while transforming Minecraft classes.",
            evidence=_evidence(log_text, ["mixin", "failed"]),
            repair_candidates=[
                "Check for incompatible optimization, rendering, or library mods.",
                "Prefer newer release versions for mods mentioned near the mixin error.",
            ],
        )
    if "mod initialization" in lower or "failed to initialize" in lower or "initialization failed" in lower:
        return FailureAnalysis(
            classification="mod_initialization_failure",
            summary="A mod failed during initialization.",
            evidence=_evidence(log_text, ["initialize", "initialization", "failed"]),
            repair_candidates=["Inspect the mod named near the initialization error and try a newer compatible version."],
        )
    if ("iris" in lower or "shader" in lower or "renderer" in lower) and ("conflict" in lower or "failed" in lower):
        return FailureAnalysis(
            classification="renderer_shader_conflict",
            summary="Rendering or shader-related mods appear to be involved in the failure.",
            evidence=_evidence(log_text, ["iris", "shader", "renderer", "conflict", "failed"]),
            repair_candidates=["Try updating or replacing the renderer/shader stack."],
        )
    if re.search(r"wrong (minecraft|mc) version|requires minecraft", lower):
        return FailureAnalysis(
            classification="minecraft_version_mismatch",
            summary="At least one mod targets a different Minecraft version.",
            evidence=_evidence(log_text, ["minecraft", "version", "requires"]),
            repair_candidates=[
                "Replace the mod with a version matching the pack Minecraft version.",
            ],
        )
    if "duplicate mod" in lower or "duplicate mods" in lower or "mod id" in lower:
        return FailureAnalysis(
            classification="duplicate_mod",
            summary="The launch log indicates duplicate mod IDs or duplicated files.",
            evidence=_evidence(log_text, ["duplicate", "mod id"]),
            repair_candidates=["Remove the lower-scored duplicate functionality candidate."],
        )
    if "unsupportedclassversionerror" in lower or "java" in lower and "version" in lower:
        return FailureAnalysis(
            classification="java_mismatch",
            summary="The configured Java runtime is not compatible with this pack.",
            evidence=_evidence(log_text, ["java", "version", "unsupportedclassversionerror"]),
            repair_candidates=["Configure Prism to use the Java version required by Minecraft."],
        )
    if "outofmemoryerror" in lower or "out of memory" in lower or "java heap space" in lower:
        return FailureAnalysis(
            classification="out_of_memory",
            summary="Minecraft ran out of memory during launch or gameplay.",
            evidence=_evidence(log_text, ["outofmemoryerror", "out of memory", "heap"]),
            repair_candidates=["Increase allocated memory in Prism or reduce heavy content mods."],
        )
    if "toml" in lower or "json" in lower and "parse" in lower:
        return FailureAnalysis(
            classification="config_parse_error",
            summary="A generated or edited configuration file could not be parsed.",
            evidence=_evidence(log_text, ["toml", "json", "parse", "config"]),
            repair_candidates=["Rollback the latest config recipe and validate syntax again."],
        )
    return FailureAnalysis(
        classification="unknown",
        summary="The crash log did not match a known MythWeaver classifier.",
        evidence=log_text.splitlines()[:5],
        repair_candidates=["Inspect the full log and add a classifier fixture for this failure."],
    )

from __future__ import annotations

import re

from mythweaver.schemas.contracts import CrashAnalysisReport, CrashFinding, SelectedModList


PACKAGE_TO_MOD = {
    "mod/azure/azurelib/": "azurelib",
    "mod.azure.azurelib": "azurelib",
    "software/bernie/geckolib": "geckolib",
    "dev/architectury": "architectury",
    "me/shedaniel/clothconfig": "cloth-config",
    "net/fabricmc/fabric/api": "fabric-api",
    "vazkii/patchouli": "patchouli",
    "org.anti_ad.mc.ipnext": "inventoryprofilesnext",
}


def analyze_crash_report(
    crash_text: str,
    selected: SelectedModList | None = None,
    crash_report_path: str | None = None,
) -> CrashAnalysisReport:
    text = crash_text or ""
    findings: list[CrashFinding] = []
    crashing_mod = _entrypoint_mod(text)
    missing_class = _missing_class(text)
    missing_mod = _map_missing_class(missing_class or text)

    if crashing_mod:
        findings.append(
            CrashFinding(
                severity="critical",
                kind="entrypoint_failure",
                title="Mod entrypoint failed at runtime",
                detail=f"Entrypoint stage failed for {crashing_mod}.",
                crashing_mod_id=crashing_mod,
                suspected_mods=[crashing_mod],
                suggested_actions=[f"Remove, replace, or repair {crashing_mod} before treating the pack as playable."],
                ai_instruction="Treat this as a hard runtime blocker, not a dry-run packaging issue.",
            )
        )

    if missing_class:
        findings.append(
            CrashFinding(
                severity="critical",
                kind="missing_class",
                title="Runtime class is missing",
                detail=f"Minecraft could not load {missing_class}.",
                crashing_mod_id=crashing_mod,
                suspected_mods=[mod for mod in [crashing_mod, missing_mod] if mod],
                missing_class=missing_class,
                missing_mod_id=missing_mod,
                suggested_actions=["Check for a dependency version mismatch or an unsupported runtime dependency."],
                ai_instruction="Fix this before launch validation can pass.",
            )
        )

    if "kotlin.reflect.jvm.internal.kotlinreflectioninternalerror" in text.lower():
        suspects = ["inventoryprofilesnext", "libipn", "fabric-language-kotlin"] if "org.anti_ad.mc.ipnext" in text else []
        findings.append(
            CrashFinding(
                severity="critical",
                kind="kotlin_reflection_error",
                title="Kotlin reflection runtime error",
                detail="A Kotlin reflection crash occurred during runtime.",
                crashing_mod_id="inventoryprofilesnext" if suspects else crashing_mod,
                suspected_mods=suspects or ([crashing_mod] if crashing_mod else []),
                suggested_actions=[
                    "Remove Inventory Profiles Next and libIPN if advanced inventory sorting is optional.",
                    "Clear Inventory Profiles Next config/rule files and relaunch.",
                    "Pin/update/downgrade Inventory Profiles Next, libIPN, and Fabric Language Kotlin as a compatible set only if keeping IPN is required.",
                ],
                ai_instruction="Prefer removing optional inventory automation over asking the user to debug Kotlin internals.",
            )
        )

    if "org.anti_ad.mc.ipnext" in text:
        crashing_mod = "inventoryprofilesnext"
        suspects = ["inventoryprofilesnext", "libipn", "fabric-language-kotlin"]
        if "clienteventhandler.onjoinworld" in text.lower() or "joinworld" in text.lower():
            findings.append(
                CrashFinding(
                    severity="critical",
                    kind="world_join_crash",
                    title="Inventory Profiles Next crashed on world join",
                    detail="The stack trace points at org.anti_ad.mc.ipnext while joining a world.",
                    crashing_mod_id="inventoryprofilesnext",
                    suspected_mods=suspects,
                    suggested_actions=[
                        "Remove Inventory Profiles Next and libIPN if optional.",
                        "Clear Inventory Profiles Next rule/config files before retrying if keeping it.",
                    ],
                    ai_instruction="Keep the pack playable; do not force hand-editing item rules.",
                )
            )

    if crashing_mod == "hwg" and missing_mod == "azurelib":
        findings.append(
            CrashFinding(
                severity="critical",
                kind="dependency_version_mismatch",
                title="HWG expects a different AzureLib runtime API",
                detail="Happiness is a Warm Gun referenced AzureLib GeoItem, which is missing from the runtime AzureLib API.",
                crashing_mod_id="hwg",
                suspected_mods=["hwg", "azurelib"],
                missing_class=missing_class,
                missing_mod_id="azurelib",
                suggested_actions=[
                    "Remove/replace Happiness is a Warm Gun.",
                    "Pin exact AzureLib version required by HWG only if known.",
                    "Avoid manual CurseForge-only dependency patching for automated Modrinth-first packs.",
                ],
                ai_instruction="Prefer replacing/removing this optional weapon mod over forcing manual library patching.",
            )
        )
        findings.append(
            CrashFinding(
                severity="high",
                kind="external_dependency_risk",
                title="External dependency risk from AzureLib mismatch",
                detail="This crash may require a very specific runtime library version outside the safe automated path.",
                crashing_mod_id="hwg",
                suspected_mods=["hwg", "azurelib"],
                missing_class=missing_class,
                missing_mod_id="azurelib",
                suggested_actions=["Use a Modrinth-compatible replacement that does not require manual dependency patching."],
                ai_instruction="Preserve the combat fantasy with safer alternatives instead of asking for manual jar surgery.",
            )
        )

    if not findings:
        findings.append(
            CrashFinding(
                severity="warning",
                kind="unknown_runtime_error",
                title="Unknown runtime crash",
                detail="No deterministic MythWeaver crash pattern matched this report.",
                suggested_actions=["Ask an AI agent to inspect the stack trace and propose a conservative selected_mods.json repair."],
                ai_instruction="Do not call this pack stable until a launch/world-join test passes.",
            )
        )

    recommendation = _repair_recommendation(findings)
    status = "identified" if any(f.severity == "critical" for f in findings) else ("partial" if findings else "unknown")
    summary = _summary(findings, recommendation)
    return CrashAnalysisReport(
        status=status,
        crash_report_path=crash_report_path or "",
        selected_mods_path=None,
        summary=summary,
        crashing_mod_id=crashing_mod or _first_crashing_mod(findings),
        findings=findings,
        repair_recommendation=recommendation,
    )


def _entrypoint_mod(text: str) -> str | None:
    match = re.search(r"provided by ['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
    return _normalize_mod_id(match.group(1)) if match else None


def _missing_class(text: str) -> str | None:
    patterns = [
        r"NoClassDefFoundError:\s+([A-Za-z0-9_.$/-]+)",
        r"ClassNotFoundException:\s+([A-Za-z0-9_.$/-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _map_missing_class(value: str) -> str | None:
    normalized = value.replace(".", "/")
    dotted = value.replace("/", ".")
    for prefix, mod_id in PACKAGE_TO_MOD.items():
        if prefix in value or prefix in normalized or prefix in dotted:
            return mod_id
    return None


def _repair_recommendation(findings: list[CrashFinding]) -> str:
    kinds = {finding.kind for finding in findings}
    crashing = {finding.crashing_mod_id for finding in findings}
    if "dependency_version_mismatch" in kinds and "hwg" in crashing:
        return "replace_mod"
    if "kotlin_reflection_error" in kinds and "inventoryprofilesnext" in crashing:
        return "remove_mod"
    if "missing_mod" in kinds:
        return "add_missing_dependency"
    if "missing_class" in kinds:
        return "pin_dependency_version"
    return "manual_review_required" if findings else "unknown"


def _summary(findings: list[CrashFinding], recommendation: str) -> str:
    top = findings[0]
    return f"{top.title}. Recommended repair: {recommendation}."


def _first_crashing_mod(findings: list[CrashFinding]) -> str | None:
    for finding in findings:
        if finding.crashing_mod_id:
            return finding.crashing_mod_id
    return None


def _normalize_mod_id(value: str) -> str:
    aliases = {
        "inventory-profiles-next": "inventoryprofilesnext",
        "inventory_profiles_next": "inventoryprofilesnext",
    }
    lower = value.strip().lower()
    return aliases.get(lower, lower)

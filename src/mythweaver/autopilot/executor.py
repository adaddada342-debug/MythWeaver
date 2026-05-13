from __future__ import annotations

from mythweaver.autopilot.contracts import AutopilotAppliedAction, AutopilotRequest
from mythweaver.runtime.contracts import RuntimeAction
from typing import Any, Awaitable, Callable, cast

from mythweaver.schemas.contracts import RequestedLoader, SelectedModEntry, SelectedModList, SourceResolveReport
from mythweaver.sources.resolver import resolve_sources_for_selected_mods

SourceResolver = Callable[..., Awaitable[SourceResolveReport]]


async def apply_runtime_actions(
    selected: SelectedModList,
    actions: list[RuntimeAction],
    request: AutopilotRequest,
    *,
    minecraft_version: str,
    loader: str,
    preflight_resolver: SourceResolver | None = None,
) -> tuple[SelectedModList, list[AutopilotAppliedAction]]:
    preflight_resolver = preflight_resolver or resolve_sources_for_selected_mods
    working = selected.model_copy(deep=True)
    applied: list[AutopilotAppliedAction] = []
    for action in actions:
        if action.safety != "safe":
            applied.append(AutopilotAppliedAction(action=action, status="blocked", reason="Only safe actions may be applied automatically."))
            continue
        if action.action == "add_mod":
            if not action.query or action.query.startswith(("http://", "https://", "direct_url:")):
                applied.append(AutopilotAppliedAction(action=action, status="blocked", reason="Unsafe or missing add_mod query."))
                continue
            if _contains_identifier(working, action.query):
                applied.append(AutopilotAppliedAction(action=action, status="skipped", reason="Selected mods already contain this dependency."))
                continue
            preflight = await _preflight_add_mod(action, request, minecraft_version=minecraft_version, loader=loader, resolver=preflight_resolver)
            if preflight is not None:
                applied.append(preflight)
                continue
            working.mods.append(
                SelectedModEntry(
                    slug=action.query,
                    role="dependency",
                    source="auto",
                    reason_selected=f"Added by MythWeaver Autopilot: {action.reason}",
                    required=action.required,
                    allowed_sources=cast(Any, list(action.source_preference or request.sources)),
                )
            )
            applied.append(AutopilotAppliedAction(action=action, status="applied", reason="Added dependency to working selection.", changed_selection=True))
            continue
        if action.action == "remove_mod":
            if not request.allow_remove_content_mods:
                applied.append(AutopilotAppliedAction(action=action, status="blocked", reason="Content mod removal is disabled."))
                continue
            removed = _remove_exact_duplicate(working, action.query)
            if removed:
                applied.append(AutopilotAppliedAction(action=action, status="applied", reason="Removed one exact duplicate entry.", changed_selection=True))
            else:
                applied.append(AutopilotAppliedAction(action=action, status="blocked", reason="No exact duplicate was available for deterministic removal."))
            continue
        if action.action == "rerun_target_matrix" and not request.allow_target_switch:
            applied.append(AutopilotAppliedAction(action=action, status="blocked", reason="Target switching is disabled."))
            continue
        applied.append(AutopilotAppliedAction(action=action, status="skipped", reason=f"{action.action} is not safely auto-applicable in V1."))
    working.minecraft_version = minecraft_version
    working.loader = cast(RequestedLoader, loader)
    return working, applied


def _contains_identifier(selected: SelectedModList, identifier: str) -> bool:
    wanted = identifier.strip().lower()
    return any(entry.identifier().strip().lower() == wanted or (entry.slug or "").strip().lower() == wanted for entry in selected.mods)


async def _preflight_add_mod(
    action: RuntimeAction,
    request: AutopilotRequest,
    *,
    minecraft_version: str,
    loader: str,
    resolver: SourceResolver,
) -> AutopilotAppliedAction | None:
    candidate_selection = SelectedModList(
        name="Autopilot dependency preflight",
        minecraft_version=minecraft_version,
        loader=cast(RequestedLoader, loader),
        mods=[
            SelectedModEntry(
                slug=action.query or "",
                role="dependency",
                source="auto",
                required=action.required,
                allowed_sources=cast(Any, list(action.source_preference or request.sources)),
            )
        ],
    )
    report = await resolver(
        candidate_selection,
        minecraft_version=minecraft_version,
        loader=loader,
        sources=list(action.source_preference or request.sources),
        target_export="local_instance",
        autonomous=not request.allow_manual_sources,
        allow_manual_sources=request.allow_manual_sources,
    )
    if report.status == "resolved" and report.export_supported and report.selected_files and not report.manual_required and not report.blocked and not report.export_blockers:
        return None
    details = "; ".join(report.export_blockers or report.warnings or ["dependency did not resolve to a verified runtime-installable file"])
    return AutopilotAppliedAction(action=action, status="blocked", reason=f"Dependency preflight blocked add_mod: {details}")


def _remove_exact_duplicate(selected: SelectedModList, identifier: str | None) -> bool:
    if not identifier:
        return False
    wanted = identifier.strip().lower()
    matching = [
        index
        for index, entry in enumerate(selected.mods)
        if entry.identifier().strip().lower() == wanted or (entry.slug or "").strip().lower() == wanted
    ]
    if len(matching) < 2:
        return False
    selected.mods.pop(matching[-1])
    return True

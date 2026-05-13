from __future__ import annotations

from mythweaver.runtime.contracts import RuntimeAction, RuntimeDiagnosis, RuntimeIssue


def actions_for_diagnoses(diagnoses: list[RuntimeDiagnosis]) -> list[RuntimeAction]:
    actions: list[RuntimeAction] = []
    for diagnosis in diagnoses:
        if diagnosis.kind in {"missing_dependency", "missing_fabric_api", "missing_mod_dependency", "fabric_api_missing"} and "add_mod" in diagnosis.suggested_repair_action_kinds:
            for mod_id in diagnosis.affected_mod_ids:
                if mod_id.startswith(("http://", "https://", "direct_url:")):
                    continue
                actions.append(
                    RuntimeAction(
                        action="add_mod",
                        safety="safe",
                        reason=diagnosis.summary,
                        query=mod_id,
                        source_preference=["modrinth", "curseforge"],
                    )
                )
            continue
        if diagnosis.kind == "duplicate_mod":
            actions.append(
                RuntimeAction(
                    action="remove_mod",
                    safety="manual",
                    reason="Duplicate mod diagnosis requires human confirmation before removal.",
                    query=_first(diagnosis.affected_mod_ids),
                )
            )
        elif diagnosis.kind in {"java_version_mismatch", "java_version_incompatible"}:
            actions.append(RuntimeAction(action="change_java", safety="manual", reason=diagnosis.summary))
        elif diagnosis.kind in {"loader_mismatch", "wrong_loader", "wrong_loader_version", "unsupported_mod_environment", "unsupported_loader_runtime"}:
            actions.append(RuntimeAction(action="manual_review", safety="manual", reason=diagnosis.summary))
        elif diagnosis.kind in {"minecraft_version_mismatch", "wrong_minecraft_version"}:
            actions.append(RuntimeAction(action="rerun_target_matrix", safety="manual", reason=diagnosis.summary))
        else:
            actions.append(RuntimeAction(action="manual_review", safety="manual", reason=diagnosis.summary))
    return actions


def actions_for_issues(issues: list[RuntimeIssue]) -> list[RuntimeAction]:
    actions: list[RuntimeAction] = []
    for issue in issues:
        if issue.kind == "missing_dependency" and issue.missing_mods:
            for missing in issue.missing_mods:
                actions.append(
                    RuntimeAction(
                        action="add_mod",
                        safety="safe",
                        reason=f"Runtime reported missing required dependency {missing}.",
                        query=missing,
                        source_preference=["modrinth", "curseforge"],
                    )
                )
            continue
        if issue.kind == "wrong_dependency_version":
            actions.append(RuntimeAction(action="replace_mod", safety="manual", reason=issue.message, query=_first(issue.affected_mods)))
        elif issue.kind == "duplicate_mod":
            actions.append(RuntimeAction(action="remove_mod", safety="manual", reason=issue.message, query=_first(issue.affected_mods)))
        elif issue.kind == "java_version_mismatch":
            actions.append(RuntimeAction(action="change_java", safety="manual", reason=issue.message))
        elif issue.kind == "loader_mismatch":
            actions.append(RuntimeAction(action="update_loader", safety="manual", reason=issue.message))
        elif issue.kind == "minecraft_version_mismatch":
            actions.append(RuntimeAction(action="rerun_target_matrix", safety="manual", reason=issue.message))
        elif issue.kind == "unsupported_loader_runtime":
            actions.append(RuntimeAction(action="manual_review", safety="manual", reason=issue.message))
        else:
            actions.append(RuntimeAction(action="manual_review", safety="manual", reason=issue.message))
    return actions


def _first(values: list[str]) -> str | None:
    return values[0] if values else None

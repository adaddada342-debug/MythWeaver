from __future__ import annotations

from mythweaver.autopilot.contracts import AutopilotRequest
from mythweaver.autopilot.memory import AutopilotMemory
from mythweaver.runtime.contracts import RuntimeAction, RuntimeLaunchReport
from mythweaver.runtime.repair_actions import actions_for_diagnoses, actions_for_issues


def plan_runtime_repairs(
    report: RuntimeLaunchReport,
    request: AutopilotRequest,
    memory: AutopilotMemory,
) -> list[RuntimeAction]:
    suggested = list(report.recommended_next_actions) or actions_for_diagnoses(report.diagnoses) or actions_for_issues(report.issues)
    return filter_applicable_actions(suggested, request, memory)


def filter_applicable_actions(
    actions: list[RuntimeAction],
    request: AutopilotRequest,
    memory: AutopilotMemory,
) -> list[RuntimeAction]:
    output: list[RuntimeAction] = []
    for action in actions:
        if action.safety != "safe":
            continue
        if action.action == "remove_mod" and not request.allow_remove_content_mods:
            continue
        if action.action == "rerun_target_matrix" and not request.allow_target_switch:
            continue
        if action.action == "update_loader" and not request.allow_loader_switch:
            continue
        if action.action == "add_mod" and action.query and action.query.startswith(("http://", "https://", "direct_url:")):
            continue
        output.append(action)
    return sorted(output, key=_priority)


def _priority(action: RuntimeAction) -> int:
    return {
        "add_mod": 0,
        "replace_mod": 1,
        "remove_mod": 2,
        "update_loader": 3,
        "rerun_target_matrix": 4,
    }.get(action.action, 99)

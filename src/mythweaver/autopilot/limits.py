from __future__ import annotations

from mythweaver.autopilot.contracts import AutopilotRequest
from mythweaver.autopilot.memory import AutopilotMemory
from mythweaver.runtime.contracts import RuntimeAction, RuntimeIssue


def blocking_reasons(
    *,
    request: AutopilotRequest,
    memory: AutopilotMemory,
    issues: list[RuntimeIssue],
    planned_actions: list[RuntimeAction],
    attempt_count: int,
) -> list[str]:
    reasons: list[str] = []
    if attempt_count >= request.max_attempts:
        reasons.append("max attempts reached")
    if not planned_actions and request.stop_on_manual_required:
        reasons.append("no safe automatic repair is available")
    for issue in issues:
        if memory.repeated_issue(issue):
            reasons.append(f"repeated issue fingerprint: {issue.kind}")
            break
    for issue in issues:
        for action in planned_actions:
            if memory.repeated_after_same_action(issue, action):
                reasons.append(f"repeated issue after same repair: {issue.kind}")
                return reasons
    if any(action.safety == "dangerous" for action in planned_actions):
        reasons.append("dangerous repair action is not allowed")
    if any(issue.kind == "unsupported_loader_runtime" for issue in issues):
        reasons.append("runtime unsupported for selected loader")
    return reasons

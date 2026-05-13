from __future__ import annotations

from dataclasses import dataclass, field

from mythweaver.runtime.contracts import RuntimeAction, RuntimeIssue


@dataclass
class AutopilotMemory:
    issue_fingerprints: list[str] = field(default_factory=list)
    action_fingerprints: list[str] = field(default_factory=list)
    target_fingerprints: set[str] = field(default_factory=set)
    changed_mods: set[str] = field(default_factory=set)
    issue_action_pairs: list[tuple[str, str]] = field(default_factory=list)

    def record_attempt(self, target: list[str] | tuple[str, str], issues: list[RuntimeIssue], actions: list[RuntimeAction]) -> None:
        self.target_fingerprints.add("|".join(target))
        for issue in issues:
            issue_fp = issue_fingerprint(issue)
            self.issue_fingerprints.append(issue_fp)
            for action in actions:
                action_fp = action_fingerprint(action)
                self.action_fingerprints.append(action_fp)
                self.issue_action_pairs.append((issue_fp, action_fp))

    def repeated_issue(self, issue: RuntimeIssue) -> bool:
        return self.issue_fingerprints.count(issue_fingerprint(issue)) >= 2

    def repeated_after_same_action(self, issue: RuntimeIssue, action: RuntimeAction) -> bool:
        pair = (issue_fingerprint(issue), action_fingerprint(action))
        return pair in self.issue_action_pairs


def issue_fingerprint(issue: RuntimeIssue) -> str:
    pieces = [issue.kind, ",".join(sorted(issue.missing_mods)), ",".join(sorted(issue.affected_mods)), ",".join(sorted(issue.suspected_mods))]
    return "|".join(pieces)


def action_fingerprint(action: RuntimeAction) -> str:
    return "|".join([action.action, action.safety, action.query or "", action.minecraft_version or "", action.loader or "", action.loader_version or ""])

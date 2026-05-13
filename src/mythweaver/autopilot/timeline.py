from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from mythweaver.schemas.contracts import AgentSafeModel


class TimelineEvent(AgentSafeModel):
    timestamp: str
    run_id: str
    type: str
    attempt_number: int | None = None
    status: str | None = None
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class TimelineWriter:
    def __init__(self, *, run_id: str, path: Path) -> None:
        self.run_id = run_id
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        event_type: str,
        *,
        summary: str,
        attempt_number: int | None = None,
        status: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        event = TimelineEvent(
            timestamp=datetime.now(UTC).isoformat(),
            run_id=self.run_id,
            type=event_type,
            attempt_number=attempt_number,
            status=status,
            summary=summary,
            data=data or {},
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        return event

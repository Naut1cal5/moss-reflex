"""The durable episode record stored in JSONL and Moss payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Episode:
    """One execution-grounded context/action/outcome triple."""

    id: str
    timestamp: str
    repo: str
    session_id: str
    context: str
    action: str
    outcome: str
    raw_trace: str
    normalized_context: str
    language: str = "unknown"
    error_class: str = "none"
    tool_name: str = "unknown"
    file_path: str = ""
    exit_code: int | None = None
    test_before: int | None = None
    test_after: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Episode:
        known = {item.name for item in cls.__dataclass_fields__.values()}
        return cls(**{key: item for key, item in value.items() if key in known})

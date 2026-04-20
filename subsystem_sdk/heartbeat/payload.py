"""Ex-0 heartbeat payload construction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal, get_args

from subsystem_sdk.validate.semantics import EX0_SEMANTIC

HeartbeatState = Literal["healthy", "degraded", "unhealthy"]
_HEARTBEAT_STATES: Final[frozenset[str]] = frozenset(get_args(HeartbeatState))
_STATUS_MAPPING_FIELDS: Final[frozenset[str]] = frozenset(
    {"status", "last_output_at", "pending_count"}
)
# Wire-format mapping: SDK's user-facing HeartbeatState literal lives in
# Pythonic terms ({healthy,degraded,unhealthy}), but the published
# contracts schema (contracts.core.types.HeartbeatStatus) uses the
# Layer-B-canonical enum ({ok,degraded,failed}). build_ex0_payload emits
# the wire-format value so the payload validates against
# contracts.schemas.Ex0Metadata.status (which is the contracts
# HeartbeatStatus enum). Keys MUST cover every member of HeartbeatState;
# import-time check below.
HEARTBEAT_STATE_TO_CONTRACTS_STATUS: Final[dict[str, str]] = {
    "healthy": "ok",
    "degraded": "degraded",
    "unhealthy": "failed",
}
if set(HEARTBEAT_STATE_TO_CONTRACTS_STATUS) != _HEARTBEAT_STATES:  # pragma: no cover
    raise RuntimeError(
        "HEARTBEAT_STATE_TO_CONTRACTS_STATUS must cover every HeartbeatState; "
        f"missing {_HEARTBEAT_STATES - set(HEARTBEAT_STATE_TO_CONTRACTS_STATUS)}"
    )


@dataclass(frozen=True)
class HeartbeatStatus:
    """Producer-owned heartbeat status details."""

    status: HeartbeatState
    last_output_at: datetime | None = None
    pending_count: int = 0

    def __post_init__(self) -> None:
        _validate_status(self.status)
        _validate_optional_datetime("last_output_at", self.last_output_at)
        _validate_pending_count(self.pending_count)


def _validate_status(status: Any) -> HeartbeatState:
    if status not in _HEARTBEAT_STATES:
        allowed = ", ".join(sorted(_HEARTBEAT_STATES))
        raise ValueError(f"heartbeat status must be one of: {allowed}")
    return status


def _validate_pending_count(pending_count: Any) -> int:
    if not isinstance(pending_count, int) or isinstance(pending_count, bool):
        raise TypeError("pending_count must be an integer")
    if pending_count < 0:
        raise ValueError("pending_count must be non-negative")
    return pending_count


def _validate_optional_datetime(field_name: str, value: Any) -> datetime | None:
    if value is not None and not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")
    return value


def _format_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        utc_value = value.replace(tzinfo=UTC)
    else:
        utc_value = value.astimezone(UTC)
    return utc_value.isoformat().replace("+00:00", "Z")


def _coerce_status(
    status: HeartbeatStatus | HeartbeatState | Mapping[str, Any],
) -> HeartbeatStatus:
    if isinstance(status, HeartbeatStatus):
        return HeartbeatStatus(
            status=_validate_status(status.status),
            last_output_at=_validate_optional_datetime(
                "last_output_at", status.last_output_at
            ),
            pending_count=_validate_pending_count(status.pending_count),
        )
    if isinstance(status, str):
        return HeartbeatStatus(status=_validate_status(status))
    if isinstance(status, Mapping):
        extra_fields = set(status).difference(_STATUS_MAPPING_FIELDS)
        if extra_fields:
            fields = ", ".join(sorted(extra_fields))
            raise ValueError(
                f"heartbeat status includes unsupported field(s): {fields}"
            )
        if "status" not in status:
            raise ValueError("heartbeat status mapping must include status")
        return HeartbeatStatus(
            status=_validate_status(status["status"]),
            last_output_at=_validate_optional_datetime(
                "last_output_at", status.get("last_output_at")
            ),
            pending_count=_validate_pending_count(status.get("pending_count", 0)),
        )

    raise TypeError("status must be a HeartbeatStatus, heartbeat state, or mapping")


def build_ex0_payload(
    subsystem_id: str,
    version: str,
    status: HeartbeatStatus | HeartbeatState | Mapping[str, Any],
    *,
    heartbeat_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a producer-owned Ex-0 heartbeat payload."""

    heartbeat_status = _coerce_status(status)
    heartbeat_time = heartbeat_at if heartbeat_at is not None else datetime.now(UTC)

    return {
        "ex_type": "Ex-0",
        "semantic": EX0_SEMANTIC,
        "subsystem_id": subsystem_id,
        "version": version,
        "heartbeat_at": _format_utc_datetime(
            _validate_optional_datetime("heartbeat_at", heartbeat_time)
        ),
        # Wire format = contracts.core.types.HeartbeatStatus (ok/degraded/failed).
        # SDK's user-facing API still accepts {healthy,degraded,unhealthy} via
        # the HeartbeatState literal; mapping happens here at the wire boundary.
        "status": HEARTBEAT_STATE_TO_CONTRACTS_STATUS[heartbeat_status.status],
        "last_output_at": _format_utc_datetime(heartbeat_status.last_output_at)
        if heartbeat_status.last_output_at is not None
        else None,
        "pending_count": heartbeat_status.pending_count,
    }

"""Transport-independent submit receipt models."""

from __future__ import annotations

import uuid
from typing import Any, Final, Literal, Mapping, Sequence, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

BackendKind = Literal["lite_pg", "full_kafka", "mock"]
BACKEND_KINDS: Final[tuple[BackendKind, ...]] = ("lite_pg", "full_kafka", "mock")

if BACKEND_KINDS != get_args(BackendKind):  # pragma: no cover - import-time guard.
    raise RuntimeError("BACKEND_KINDS must match BackendKind")

RESERVED_PRIVATE_KEYS: Final[frozenset[str]] = frozenset(
    {"pg_queue_id", "kafka_topic", "kafka_offset", "kafka_partition"}
)


class SubmitReceipt(BaseModel):
    """Stable receipt shape returned by submit and heartbeat paths."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    receipt_id: str = Field(min_length=1)
    backend_kind: BackendKind
    transport_ref: str | None = None
    validator_version: str
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @field_validator("errors")
    @classmethod
    def _accepted_receipts_have_no_errors(
        cls, errors: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        if info.data.get("accepted") is True and errors:
            raise ValueError("accepted receipts cannot include errors")
        return errors


def assert_no_private_leak(extra: Mapping[str, Any]) -> None:
    """Reject backend-private response keys before receipt normalization."""

    leaked_keys = RESERVED_PRIVATE_KEYS.intersection(extra)
    if leaked_keys:
        joined = ", ".join(sorted(leaked_keys))
        raise ValueError(
            f"backend private keys cannot leak into SubmitReceipt: {joined}"
        )


def normalize_receipt(
    *,
    accepted: bool,
    backend_kind: BackendKind,
    transport_ref: str | None,
    validator_version: str,
    warnings: Sequence[str] = (),
    errors: Sequence[str] = (),
    receipt_id: str | None = None,
) -> SubmitReceipt:
    """Create the public receipt contract from backend-neutral values."""

    return SubmitReceipt(
        accepted=accepted,
        receipt_id=receipt_id if receipt_id is not None else uuid.uuid4().hex,
        backend_kind=backend_kind,
        transport_ref=transport_ref,
        validator_version=validator_version,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )

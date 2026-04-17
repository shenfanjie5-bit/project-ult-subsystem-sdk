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
    {
        "pg_queue_id",
        "pg_table",
        "queue_table",
        "sql",
        "kafka_topic",
        "kafka_offset",
        "kafka_partition",
    }
)
_BACKEND_RECEIPT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "accepted",
        "receipt_id",
        "backend_kind",
        "transport_ref",
        "validator_version",
        "warnings",
        "errors",
    }
)


def _coerce_diagnostics(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, bytes):
        raise TypeError(f"{field_name} must contain strings, not bytes")

    try:
        coerced = tuple(value)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be a sequence of strings") from exc

    if not all(isinstance(item, str) for item in coerced):
        raise TypeError(f"{field_name} must contain only strings")
    return coerced


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

    @field_validator("warnings", "errors", mode="before")
    @classmethod
    def _coerce_diagnostic_fields(
        cls, value: Any, info: ValidationInfo
    ) -> tuple[str, ...]:
        return _coerce_diagnostics(value, field_name=info.field_name)

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
    warnings: Sequence[str] | str = (),
    errors: Sequence[str] | str = (),
    receipt_id: str | None = None,
) -> SubmitReceipt:
    """Create the public receipt contract from backend-neutral values."""

    return SubmitReceipt(
        accepted=accepted,
        receipt_id=receipt_id if receipt_id is not None else uuid.uuid4().hex,
        backend_kind=backend_kind,
        transport_ref=transport_ref,
        validator_version=validator_version,
        warnings=_coerce_diagnostics(warnings, field_name="warnings"),
        errors=_coerce_diagnostics(errors, field_name="errors"),
    )


def normalize_backend_receipt(
    raw_receipt: Mapping[str, Any] | SubmitReceipt,
    *,
    backend_kind: BackendKind,
    validator_version: str,
) -> SubmitReceipt:
    """Normalize an adapter receipt through the public receipt boundary."""

    if isinstance(raw_receipt, SubmitReceipt):
        receipt_data = raw_receipt.model_dump(mode="python")
    elif isinstance(raw_receipt, Mapping):
        receipt_data = raw_receipt
    else:
        raise TypeError("raw_receipt must be a mapping or SubmitReceipt")

    assert_no_private_leak(receipt_data)

    unknown_keys = set(receipt_data).difference(_BACKEND_RECEIPT_KEYS)
    if unknown_keys:
        joined = ", ".join(sorted(unknown_keys))
        raise ValueError(f"unsupported backend receipt field(s): {joined}")

    accepted = receipt_data.get("accepted")
    if not isinstance(accepted, bool):
        raise TypeError("backend receipt accepted must be a bool")

    return normalize_receipt(
        accepted=accepted,
        receipt_id=receipt_data.get("receipt_id"),
        backend_kind=backend_kind,
        transport_ref=receipt_data.get("transport_ref"),
        validator_version=validator_version,
        warnings=receipt_data.get("warnings", ()),
        errors=receipt_data.get("errors", ()),
    )

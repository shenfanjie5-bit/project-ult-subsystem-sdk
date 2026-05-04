"""Section 14 backends package: Lite and Full backend adapters."""

from subsystem_sdk.backends.config import SubmitBackendConfig
from subsystem_sdk.backends.data_platform_queue import (
    DataPlatformQueueSubmitBackend,
    SubmitCandidateFunc,
)
from subsystem_sdk.backends.full_kafka import (
    KafkaBrokerAck,
    KafkaCompatibleSubmitBackend,
    KafkaProducerProtocol,
)
from subsystem_sdk.backends.factory import build_submit_backend
from subsystem_sdk.backends.heartbeat import SubmitBackendHeartbeatAdapter
from subsystem_sdk.backends.lite_pg import PgSubmitBackend
from subsystem_sdk.backends.mock import MockSubmitBackend

__all__ = [
    "build_submit_backend",
    "DataPlatformQueueSubmitBackend",
    "KafkaBrokerAck",
    "KafkaCompatibleSubmitBackend",
    "KafkaProducerProtocol",
    "MockSubmitBackend",
    "PgSubmitBackend",
    "SubmitBackendHeartbeatAdapter",
    "SubmitBackendConfig",
    "SubmitCandidateFunc",
]

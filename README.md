# subsystem-sdk

Producer-side client SDK for subsystem modules. It validates Ex payloads,
strips SDK-local envelope fields, dispatches to a configured submit backend,
and returns a stable `SubmitReceipt`.

This SDK owns client semantics only. It is not the Layer B runtime: queue
tables, freeze/selection behavior, graph promotion, and cycle ownership stay
in data-platform, graph-engine, orchestrator, and assembly.

Source of truth:

- `docs/subsystem-sdk.project-doc.md`

## Current state

Implementation exists under `subsystem_sdk/` and `tests/`.

Implemented and relevant to the M4 bridge:

- `submit(payload) -> SubmitReceipt` is the stable producer-facing submit
  shape, both through `SubmitClient.submit(...)` and the runtime helper
  `subsystem_sdk.submit.submit(...)`.
- `DataPlatformQueueSubmitBackend` implements
  `backend_kind="data_platform_queue"` by preparing the public
  data-platform `candidate_queue` envelope and calling an injected or
  installed `data_platform.queue.api.submit_candidate(...)`.
- Backend responses are normalized before callers receive them. Public
  receipts remain transport-neutral and immutable.
- `SubmitReceipt` is guarded against backend-private leakage: PG/Kafka
  internals such as queue IDs, topics, offsets, and partitions are rejected
  by `assert_no_private_leak(...)` / `RESERVED_PRIVATE_KEYS` and never become
  receipt fields.

Evidence to keep current when changing this surface:

```bash
.venv/bin/python -m pytest tests/backends/test_data_platform_queue_backend.py \
  tests/integration/test_data_platform_queue_bridge.py \
  tests/submit/test_client.py \
  tests/submit/test_receipt.py -q
.venv/bin/python -m pytest -q
```

Execution rule:

1. read the project doc first
2. keep work inside this module unless the issue explicitly targets shared contracts
3. keep this SDK on producer/client semantics; do not add Layer B runtime
   ownership here

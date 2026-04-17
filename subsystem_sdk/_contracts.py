"""Gateway for contract schema imports."""

try:
    import contracts
except ImportError:  # pragma: no cover - placeholder until contracts is wired.
    contracts = None

SUPPORTED_EX_TYPES: tuple[str, ...] = ("Ex-0", "Ex-1", "Ex-2", "Ex-3")


def get_ex_schema(ex_type: str) -> type | None:
    raise NotImplementedError("populated in milestone-1")

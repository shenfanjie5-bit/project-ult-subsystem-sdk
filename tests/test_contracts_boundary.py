import ast
from pathlib import Path

import pytest

from subsystem_sdk._contracts import SUPPORTED_EX_TYPES, UnknownExTypeError, get_ex_schema


ALLOWED_CONTRACTS_IMPORT = Path("subsystem_sdk/_contracts.py")


def _scan_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def test_no_direct_contracts_import_outside_gateway(PROJECT_ROOT: Path) -> None:
    sdk_files = sorted((PROJECT_ROOT / "subsystem_sdk").glob("**/*.py"))
    assert sdk_files

    offenders = [
        path.relative_to(PROJECT_ROOT)
        for path in sdk_files
        if path.relative_to(PROJECT_ROOT) != ALLOWED_CONTRACTS_IMPORT
        and any(
            name == "contracts" or name.startswith("contracts.")
            for name in _scan_imports(path)
        )
    ]

    assert offenders == []


def test_supported_ex_types_are_fixed() -> None:
    assert SUPPORTED_EX_TYPES == ("Ex-0", "Ex-1", "Ex-2", "Ex-3")


def test_get_ex_schema_rejects_unknown_type_before_contracts_import() -> None:
    with pytest.raises(UnknownExTypeError, match="unsupported Ex type"):
        get_ex_schema("Ex-9")

from pathlib import Path

import pytest


@pytest.fixture
def PROJECT_ROOT() -> Path:
    return Path(__file__).resolve().parents[1]

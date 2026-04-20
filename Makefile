# subsystem-sdk Makefile — stage-2 plan canonical lane targets.
#
# Per stage-2 plan iron rules:
# - test-fast / smoke run only against [dev] (offline-first per
#   SUBPROJECT_TESTING_STANDARD §2.2). Subsystem-sdk imports `contracts`
#   at top-level, so callers must have project-ult-contracts installed
#   (CI does this via the @v0.1.2 git pin; locally use sibling
#   `contracts/src` on PYTHONPATH).
# - contract: also installs [contracts-schemas] so cross-repo align
#   tests against `contracts.schemas` actually run (no importorskip).
# - regression: installs [shared-fixtures] so audit_eval_fixtures is
#   importable; per iron rule #1, the regression module hard-imports.
# - full(ci): installs all extras, runs the entire test suite. Acts as
#   the umbrella check. CI's `ci` job is the equivalent.

PYTHON ?= python3.12
PIP    := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest

# Local dev convenience: when the contracts package isn't pip-installed,
# point PYTHONPATH at the sibling contracts/src so subsystem_sdk imports
# work. CI does NOT use this — it installs contracts via the git pin.
PYTHONPATH_LOCAL := $(CURDIR):$(CURDIR)/../contracts/src

.PHONY: help install-dev install-contracts-schemas install-shared install-all \
        test-fast smoke contract regression test ci clean

help:
	@echo "Targets:"
	@echo "  install-dev               — pip install -e .[dev]"
	@echo "  install-contracts-schemas — pip install -e .[dev,contracts-schemas]"
	@echo "  install-shared            — pip install -e .[dev,shared-fixtures]"
	@echo "  install-all               — pip install -e .[dev,contracts-schemas,shared-fixtures]"
	@echo "  test-fast                 — tests/unit + tests/boundary"
	@echo "  smoke                     — tests/smoke"
	@echo "  contract                  — tests/contract (incl. cross-repo align)"
	@echo "  regression                — tests/regression (real audit_eval_fixtures)"
	@echo "  test                      — full pytest collection"
	@echo "  ci                        — install-all + test (used by CI full(ci))"

install-dev:
	$(PIP) install -e ".[dev]"

install-contracts-schemas:
	$(PIP) install -e ".[dev,contracts-schemas]"

install-shared:
	$(PIP) install -e ".[dev,shared-fixtures]"

install-all:
	$(PIP) install -e ".[dev,contracts-schemas,shared-fixtures]"

test-fast:
	PYTHONPATH=$(PYTHONPATH_LOCAL) $(PYTEST) tests/unit tests/boundary -q

smoke:
	PYTHONPATH=$(PYTHONPATH_LOCAL) $(PYTEST) tests/smoke -q

contract:
	PYTHONPATH=$(PYTHONPATH_LOCAL) $(PYTEST) tests/contract -q

regression:
	PYTHONPATH=$(PYTHONPATH_LOCAL) $(PYTEST) tests/regression -q

test:
	PYTHONPATH=$(PYTHONPATH_LOCAL) $(PYTEST)

ci: install-all test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

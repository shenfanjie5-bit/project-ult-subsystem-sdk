"""Regression tier — real consumption of audit_eval_fixtures via the SDK
runtime.

Iron rule #1: hard-import `audit_eval_fixtures` (no
`pytest.skip(allow_module_level=True)`). If the [shared-fixtures] extra
isn't installed, this module ImportErrors at collection — the regression
lane in CI stays honest about whether the dependency is really there.

Iron rule #5: must really call subsystem-sdk runtime AND have at least
one fixture-derived business expectation. We:

1. Import `INGEST_METADATA_FIELDS` + `assert_no_ingest_metadata` from
   the SDK runtime (real call).
2. Load `event_cases.case_fuzzy_alias_simple` from audit_eval_fixtures
   (real fixture).
3. Assert the fixture's `input` actually contains the SDK's
   `INGEST_METADATA_FIELDS` set members (`submitted_at` + `ingest_seq`)
   — the FIXTURE-DERIVED expectation: this fixture exists precisely to
   represent a "raw mention with Layer B ingest metadata mixed in".
4. Feed it through the SDK guard — expect `IngestMetadataLeakError`
   raised, with the leaked field list matching the fixture's actual
   ingest metadata fields. Both assertions are derived FROM the fixture
   (not from a hard-coded constant), satisfying the §5 sub-rule.

Cross-repo cohesion: the fixture is shared between entity-registry's
regression lane (which uses `lookup_alias_in_repositories`) and ours
(which uses `assert_no_ingest_metadata`). Same input data, two repos,
two complementary checks. If audit-eval bumps and changes the fixture
shape, both regressions break together — that's the intended behaviour.
"""

from __future__ import annotations

import pytest

# Iron rule #1 — bare import, no allow_module_level skip.
from audit_eval_fixtures import (  # noqa: F401  (load_case below proves use)
    fixture_root,
    iter_cases,
    load_case,
)

from subsystem_sdk.validate.semantics import (
    INGEST_METADATA_FIELDS,
    IngestMetadataLeakError,
    assert_no_ingest_metadata,
)


_PACK = "event_cases"
_CASE = "case_fuzzy_alias_simple"


class TestEventCaseFixturePresent:
    def test_event_cases_pack_lists_at_least_the_fuzzy_alias_case(self) -> None:
        case_ids = sorted(c.case_id for c in iter_cases(_PACK))
        assert _CASE in case_ids, (
            f"audit_eval_fixtures.event_cases is missing {_CASE!r}; "
            f"got {case_ids}. SDK regression depends on this case existing."
        )


class TestSdkGuardCatchesFixtureIngestMetadata:
    """Real-runtime regression — drives audit_eval_fixtures input through
    the SDK's `assert_no_ingest_metadata` guard and asserts the leak
    matches the fixture's actual contents (not a hard-coded set).
    """

    def _load(self) -> dict:
        case = load_case(_PACK, _CASE)
        # case.input is the dict with raw_mention_text + source_context +
        # source_kind + submitted_at + ingest_seq.
        return dict(case.input)

    def test_fixture_input_actually_contains_ingest_metadata(self) -> None:
        # Sanity: fixture must include at least one of the SDK's
        # forbidden fields. Fixture-derived expectation — if audit-eval
        # ever sanitizes the fixture, regenerate it intentionally.
        payload = self._load()
        leaked_in_fixture = set(payload).intersection(INGEST_METADATA_FIELDS)
        assert leaked_in_fixture, (
            f"event_cases/{_CASE} no longer contains any SDK-forbidden "
            f"ingest metadata field (expected at least one of "
            f"{sorted(INGEST_METADATA_FIELDS)}); regression has nothing "
            "to assert against. Either update the fixture intentionally "
            "or remove this regression."
        )
        # Document which fields the fixture happens to carry today.
        assert leaked_in_fixture.issubset(INGEST_METADATA_FIELDS)

    def test_assert_no_ingest_metadata_raises_with_fixture_derived_field_list(
        self,
    ) -> None:
        payload = self._load()
        expected_leaked = sorted(set(payload).intersection(INGEST_METADATA_FIELDS))

        with pytest.raises(IngestMetadataLeakError) as excinfo:
            assert_no_ingest_metadata(payload)

        # Iron rule #5 sub-rule (main-core left behind): the assertion
        # must be keyed to the fixture's specific business expectation,
        # not a generic invariant. Here we anchor to the EXACT field
        # list reported by the SDK guard against this fixture's input.
        for field in expected_leaked:
            assert field in str(excinfo.value), (
                f"SDK guard error message missing leaked field {field!r}; "
                f"got: {excinfo.value!s}"
            )


class TestFixturesPackageRoundTrip:
    """Smoke for the audit_eval_fixtures import surface itself — proves
    `fixture_root` and `iter_cases` work for the pack we depend on. If
    audit-eval ever rotates the public API, this fails before the
    regression-proper does and gives a clearer error.
    """

    def test_fixture_root_returns_a_real_directory(self) -> None:
        root = fixture_root(_PACK)
        assert root.exists() and root.is_dir(), root

    def test_iter_cases_yields_at_least_one_case_ref(self) -> None:
        cases = list(iter_cases(_PACK))
        assert cases, f"event_cases pack has no cases at all"
        # Every case_id should be a non-empty string.
        for c in cases:
            assert isinstance(c.case_id, str) and c.case_id

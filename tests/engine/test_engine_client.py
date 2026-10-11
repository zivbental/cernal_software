"""The Platform-facing engine client: resolution, protocol conformance, capabilities.

``LocalEngine`` is the only engine (the deterministic ``MockEngine`` was removed — the
product reports real science or it reports a failure, never fabricated numbers). The
behaviour that used to be proved against the mock lives here against the real client,
with the scientific success paths in ``test_pipeline.py``.
"""

import pytest

from engine.client import EngineClient, LocalEngine, load_engine
from engine.contract import FAILED

# --- Client resolution ------------------------------------------------------------


def test_load_engine_resolves_a_dotted_path():
    assert isinstance(load_engine("engine.client.LocalEngine"), LocalEngine)


def test_load_engine_rejects_a_missing_module():
    with pytest.raises(ValueError, match="Cannot import engine module"):
        load_engine("engine.nonexistent.Thing")


def test_load_engine_rejects_a_missing_class():
    with pytest.raises(ValueError, match="has no attribute"):
        load_engine("engine.client.NoSuchEngine")


def test_load_engine_rejects_something_that_is_not_an_engine():
    with pytest.raises(TypeError, match="does not implement"):
        load_engine("engine.contract.SCHEMA_VERSION")


def test_the_local_engine_satisfies_the_protocol():
    assert isinstance(LocalEngine(), EngineClient)


def test_the_removed_mock_engine_is_not_resolvable():
    """The default ``CERNAL_ENGINE`` once pointed here. A stale .env or deployment
    config must fail loudly at resolution rather than silently fall back to anything."""
    with pytest.raises(ValueError, match="has no attribute"):
        load_engine("engine.client.MockEngine")


# --- Failure convention -----------------------------------------------------------


def test_de_mode_fails_cleanly_on_bad_input(make_request, progress):
    """`de` mode is real (``test_pipeline.py`` has the success case), but the default
    fixture's ``organism`` is deliberately free text ('E. coli', not 'ecoli' —
    docs/ROADMAP.md P1), so this run fails on host resolution. An expected scientific
    failure is data, not a raised exception."""
    result = LocalEngine().run(make_request(), progress)  # default input_mode is "de"

    assert result.status == FAILED
    assert result.error is not None and "organism" in result.error.lower()


# --- Capabilities -----------------------------------------------------------------


def test_capabilities_advertise_what_the_engine_supports():
    """The Platform validates submissions against this instead of importing the
    registries directly, which docs/architecture.md §3 forbids."""
    caps = LocalEngine().capabilities()

    assert caps.engine_version == LocalEngine.ENGINE_VERSION
    assert "toehold" in caps.available_families
    assert "default" in caps.scoring_profiles

    by_name = {family.name: family for family in caps.gate_families}
    assert by_name["toehold"].available
    assert by_name["toehold"].label == "Toehold Riboswitch"
    # Planned families are advertised but not selectable, so the UI can show them
    # greyed out instead of hardcoding a "coming soon" list.
    assert not by_name["crispr"].available
    assert by_name["crispr"].description


def test_capabilities_do_not_require_a_job():
    """Cheap enough to call on every request."""
    assert LocalEngine().capabilities().schema_version

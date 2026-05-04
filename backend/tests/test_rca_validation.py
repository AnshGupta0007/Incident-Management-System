"""
Unit tests for RCA validation logic and state machine transitions.

These tests cover the core business rules:
1. RCA fields must meet minimum length and completeness requirements
2. incident_end must be after incident_start
3. Cannot transition to CLOSED without an RCA
4. State machine only allows legal transitions
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.schemas.rca import RCACreate
from app.models.rca import RootCauseCategory
from app.patterns.state import validate_transition
from app.models.work_item import WorkItemStatus


# ── RCA Validation Tests ──────────────────────────────────────────────────────

def make_valid_rca(**overrides) -> dict:
    base = {
        "incident_start": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        "incident_end": datetime(2024, 1, 1, 11, 30, 0, tzinfo=timezone.utc),
        "root_cause_category": RootCauseCategory.INFRASTRUCTURE,
        "root_cause_detail": "Primary database ran out of connections due to a connection leak in the ORM layer",
        "fix_applied": "Restarted connection pool and deployed hotfix to close connections properly",
        "prevention_steps": "Add connection pool monitoring, set max_overflow=0, and add integration tests",
    }
    base.update(overrides)
    return base


def test_valid_rca_passes():
    rca = RCACreate(**make_valid_rca())
    assert rca.root_cause_category == RootCauseCategory.INFRASTRUCTURE


def test_rca_end_before_start_raises():
    with pytest.raises(Exception, match="incident_end must be after incident_start"):
        RCACreate(**make_valid_rca(
            incident_end=datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        ))


def test_rca_end_equals_start_raises():
    ts = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(Exception):
        RCACreate(**make_valid_rca(incident_start=ts, incident_end=ts))


def test_rca_root_cause_too_short_raises():
    with pytest.raises(Exception):
        RCACreate(**make_valid_rca(root_cause_detail="short"))


def test_rca_fix_applied_too_short_raises():
    with pytest.raises(Exception):
        RCACreate(**make_valid_rca(fix_applied="fix"))


def test_rca_prevention_steps_too_short_raises():
    with pytest.raises(Exception):
        RCACreate(**make_valid_rca(prevention_steps="steps"))


def test_rca_mttr_calculation():
    start = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 11, 30, 0, tzinfo=timezone.utc)
    rca = RCACreate(**make_valid_rca(incident_start=start, incident_end=end))
    delta = rca.incident_end - rca.incident_start
    mttr = delta.total_seconds() / 60
    assert mttr == 90.0


# ── State Machine Tests ───────────────────────────────────────────────────────

def test_open_to_investigating_allowed():
    validate_transition(WorkItemStatus.OPEN, WorkItemStatus.INVESTIGATING)


def test_investigating_to_resolved_allowed():
    validate_transition(WorkItemStatus.INVESTIGATING, WorkItemStatus.RESOLVED)


def test_resolved_to_closed_with_rca_allowed():
    validate_transition(WorkItemStatus.RESOLVED, WorkItemStatus.CLOSED, has_rca=True)


def test_resolved_to_closed_without_rca_raises():
    with pytest.raises(ValueError, match="without a complete RCA"):
        validate_transition(WorkItemStatus.RESOLVED, WorkItemStatus.CLOSED, has_rca=False)


def test_open_to_closed_directly_raises():
    with pytest.raises(ValueError):
        validate_transition(WorkItemStatus.OPEN, WorkItemStatus.CLOSED, has_rca=True)


def test_closed_to_open_allowed():
    validate_transition(WorkItemStatus.CLOSED, WorkItemStatus.OPEN)


def test_investigating_to_open_regression_allowed():
    validate_transition(WorkItemStatus.INVESTIGATING, WorkItemStatus.OPEN)


def test_resolved_to_investigating_regression_allowed():
    validate_transition(WorkItemStatus.RESOLVED, WorkItemStatus.INVESTIGATING)


def test_open_to_resolved_direct_raises():
    with pytest.raises(ValueError):
        validate_transition(WorkItemStatus.OPEN, WorkItemStatus.RESOLVED)


# ── Alert Strategy Tests ──────────────────────────────────────────────────────

def test_rdbms_resolves_to_p0():
    from app.patterns.strategy import resolve_severity
    result = resolve_severity("RDBMS", "P3")
    assert result.value == "P0"


def test_cache_resolves_minimum_p2():
    from app.patterns.strategy import resolve_severity
    result = resolve_severity("CACHE", "P4")
    assert result.value == "P2"


def test_reported_severity_can_escalate():
    from app.patterns.strategy import resolve_severity
    result = resolve_severity("API", "P0")
    assert result.value == "P0"

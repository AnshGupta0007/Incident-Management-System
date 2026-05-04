"""
State Pattern for Incident Lifecycle Management.

Why State Pattern?
  Each status has its own rules about which transitions are legal.
  Encoding these as if/elif chains scattered across services leads to
  bugs when new statuses or constraints are added. The State Pattern
  centralises transition logic so each state "knows" what it allows.

  OPEN → INVESTIGATING → RESOLVED → CLOSED (requires RCA)
  CLOSED → OPEN (re-open if issue recurs)
  RESOLVED → INVESTIGATING (regression)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from ..models.work_item import WorkItemStatus


class WorkItemState(ABC):
    """Base state. Subclasses define legal transitions."""

    @abstractmethod
    def allowed_transitions(self) -> set[WorkItemStatus]:
        ...

    def transition_to(self, new_status: WorkItemStatus, has_rca: bool = False) -> None:
        if new_status not in self.allowed_transitions():
            raise ValueError(
                f"Transition from {self.status} → {new_status} is not allowed. "
                f"Valid transitions: {[s.value for s in self.allowed_transitions()]}"
            )
        if new_status == WorkItemStatus.CLOSED and not has_rca:
            raise ValueError(
                "Cannot transition to CLOSED without a complete RCA. "
                "Submit an RCA first."
            )

    @property
    @abstractmethod
    def status(self) -> WorkItemStatus:
        ...


class OpenState(WorkItemState):
    @property
    def status(self) -> WorkItemStatus:
        return WorkItemStatus.OPEN

    def allowed_transitions(self) -> set[WorkItemStatus]:
        return {WorkItemStatus.INVESTIGATING}


class InvestigatingState(WorkItemState):
    @property
    def status(self) -> WorkItemStatus:
        return WorkItemStatus.INVESTIGATING

    def allowed_transitions(self) -> set[WorkItemStatus]:
        return {WorkItemStatus.RESOLVED, WorkItemStatus.OPEN}


class ResolvedState(WorkItemState):
    @property
    def status(self) -> WorkItemStatus:
        return WorkItemStatus.RESOLVED

    def allowed_transitions(self) -> set[WorkItemStatus]:
        # Can go back to INVESTIGATING on regression, or CLOSED if RCA exists
        return {WorkItemStatus.CLOSED, WorkItemStatus.INVESTIGATING}


class ClosedState(WorkItemState):
    @property
    def status(self) -> WorkItemStatus:
        return WorkItemStatus.CLOSED

    def allowed_transitions(self) -> set[WorkItemStatus]:
        # Re-open if the same issue recurs
        return {WorkItemStatus.OPEN}


_STATE_MAP: dict[WorkItemStatus, WorkItemState] = {
    WorkItemStatus.OPEN: OpenState(),
    WorkItemStatus.INVESTIGATING: InvestigatingState(),
    WorkItemStatus.RESOLVED: ResolvedState(),
    WorkItemStatus.CLOSED: ClosedState(),
}


def get_state(status: WorkItemStatus) -> WorkItemState:
    return _STATE_MAP[status]


def validate_transition(
    current_status: WorkItemStatus,
    new_status: WorkItemStatus,
    has_rca: bool = False,
) -> None:
    """Raises ValueError if the transition is illegal."""
    state = get_state(current_status)
    state.transition_to(new_status, has_rca=has_rca)

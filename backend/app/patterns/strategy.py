"""
Strategy Pattern for Alert Routing.

Why Strategy Pattern?
  Different component types require different alerting channels and urgency.
  An RDBMS failure (P0) wakes someone up at 3am via PagerDuty; a Cache
  degradation (P2) sends a Slack notification. Hard-coding these rules in
  a monolithic alert function makes the code brittle and untestable.
  The Strategy Pattern lets us swap alert implementations at runtime
  based on the component type without changing caller code.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
from ..models.work_item import Severity, ComponentType

logger = logging.getLogger(__name__)


@dataclass
class AlertContext:
    work_item_id: str
    component_id: str
    component_type: str
    severity: str
    title: str
    signal_count: int


class AlertStrategy(ABC):
    """Base alerting strategy."""

    @abstractmethod
    async def send_alert(self, ctx: AlertContext) -> None:
        ...

    @property
    @abstractmethod
    def channel(self) -> str:
        ...


class PagerDutyAlertStrategy(AlertStrategy):
    """P0/P1 — immediate escalation via PagerDuty (simulated)."""

    @property
    def channel(self) -> str:
        return "pagerduty"

    async def send_alert(self, ctx: AlertContext) -> None:
        logger.critical(
            "[PAGERDUTY][%s] 🚨 CRITICAL: %s | component=%s | signals=%d",
            ctx.severity,
            ctx.title,
            ctx.component_id,
            ctx.signal_count,
        )
        # Production: call PagerDuty Events API v2 here


class SlackAlertStrategy(AlertStrategy):
    """P2 — team notification via Slack (simulated)."""

    @property
    def channel(self) -> str:
        return "slack"

    async def send_alert(self, ctx: AlertContext) -> None:
        logger.warning(
            "[SLACK][%s] ⚠️  Incident: %s | component=%s | signals=%d",
            ctx.severity,
            ctx.title,
            ctx.component_id,
            ctx.signal_count,
        )
        # Production: call Slack Webhooks API here


class EmailAlertStrategy(AlertStrategy):
    """P3/P4 — low-urgency email notification (simulated)."""

    @property
    def channel(self) -> str:
        return "email"

    async def send_alert(self, ctx: AlertContext) -> None:
        logger.info(
            "[EMAIL][%s] ℹ️  Alert: %s | component=%s | signals=%d",
            ctx.severity,
            ctx.title,
            ctx.component_id,
            ctx.signal_count,
        )
        # Production: call SendGrid / SES here


class SilentAlertStrategy(AlertStrategy):
    """No-op — used for already-active incidents to avoid alert storms."""

    @property
    def channel(self) -> str:
        return "silent"

    async def send_alert(self, ctx: AlertContext) -> None:
        logger.debug("[SILENT] Suppressed alert for active incident: %s", ctx.work_item_id)


# Priority map: component_type → severity override
_COMPONENT_SEVERITY_MAP: dict[str, Severity] = {
    ComponentType.RDBMS: Severity.P0,
    ComponentType.MCP_HOST: Severity.P1,
    ComponentType.API: Severity.P2,
    ComponentType.QUEUE: Severity.P2,
    ComponentType.CACHE: Severity.P2,
    ComponentType.NOSQL: Severity.P3,
}

_SEVERITY_STRATEGY_MAP: dict[Severity, AlertStrategy] = {
    Severity.P0: PagerDutyAlertStrategy(),
    Severity.P1: PagerDutyAlertStrategy(),
    Severity.P2: SlackAlertStrategy(),
    Severity.P3: EmailAlertStrategy(),
    Severity.P4: EmailAlertStrategy(),
}


def resolve_severity(component_type: str, reported_severity: str) -> Severity:
    """
    Component type can escalate severity beyond what the signal reports.
    RDBMS failures are always at least P0 regardless of what the signal says.
    """
    floor_severity = _COMPONENT_SEVERITY_MAP.get(component_type, Severity.P2)
    # Take the higher priority (lower numeric suffix = more severe)
    severity_order = [Severity.P0, Severity.P1, Severity.P2, Severity.P3, Severity.P4]
    floor_idx = severity_order.index(floor_severity)
    try:
        reported_idx = severity_order.index(Severity(reported_severity))
    except ValueError:
        reported_idx = 2  # default P2
    final_idx = min(floor_idx, reported_idx)
    return severity_order[final_idx]


def get_alert_strategy(severity: Severity, is_new_incident: bool = True) -> AlertStrategy:
    """Returns the correct strategy. Suppresses alerts for duplicate signals."""
    if not is_new_incident:
        return SilentAlertStrategy()
    return _SEVERITY_STRATEGY_MAP.get(severity, SlackAlertStrategy())

import asyncio
import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import asyncpg
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode

_log = logging.getLogger(__name__)

_provider = TracerProvider(
    resource=Resource.create({"service.name": "postgres-mcp"})
)
_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=os.environ.get("PHOENIX_ENDPOINT", "http://localhost:4317")
        )
    )
)
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("postgres-mcp")


# --- alert hook interface ---

@dataclass
class AlertEvent:
    span_name: str
    error_type: str
    error_message: str
    is_timeout: bool
    attributes: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class AlertHook(Protocol):
    """Implement this protocol and call register_alert_hook() to receive error alerts."""
    async def fire(self, event: AlertEvent) -> None: ...


_alert_hooks: list[AlertHook] = []


def register_alert_hook(hook: AlertHook) -> None:
    """Register a hook that will be called on every error or timeout span."""
    _alert_hooks.append(hook)


async def _fire_alert_hooks(event: AlertEvent) -> None:
    for hook in _alert_hooks:
        try:
            await hook.fire(event)
        except Exception as exc:
            _log.warning("Alert hook %s raised: %s", type(hook).__name__, exc)


class SlackAlertHook:
    """Posts to a Slack incoming webhook. Activated by SLACK_WEBHOOK_URL."""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    async def fire(self, event: AlertEvent) -> None:
        label = "TIMEOUT" if event.is_timeout else "ERROR"
        text = (
            f":red_circle: *{label}* in `{event.span_name}`\n"
            f">{event.error_type}: {event.error_message}"
        )
        payload = json.dumps({"text": text}).encode()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._post, payload)

    def _post(self, payload: bytes) -> None:
        req = urllib.request.Request(
            self._url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()


class PagerDutyAlertHook:
    """Triggers PagerDuty incidents via Events API v2. Activated by PAGERDUTY_ROUTING_KEY."""

    _EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, routing_key: str) -> None:
        self._key = routing_key

    async def fire(self, event: AlertEvent) -> None:
        summary = (
            f"{event.span_name} {'timed out' if event.is_timeout else 'errored'}: "
            f"{event.error_message}"
        )
        payload = json.dumps({
            "routing_key": self._key,
            "event_action": "trigger",
            "payload": {
                "summary": summary[:1024],
                "severity": "error",
                "source": "postgres-mcp",
                "custom_details": {
                    "error_type": event.error_type,
                    "span": event.span_name,
                    "is_timeout": event.is_timeout,
                },
            },
        }).encode()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._post, payload)

    def _post(self, payload: bytes) -> None:
        req = urllib.request.Request(
            self._EVENTS_URL, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()


if os.environ.get("SLACK_WEBHOOK_URL"):
    register_alert_hook(SlackAlertHook(os.environ["SLACK_WEBHOOK_URL"]))
if os.environ.get("PAGERDUTY_ROUTING_KEY"):
    register_alert_hook(PagerDutyAlertHook(os.environ["PAGERDUTY_ROUTING_KEY"]))


# --- span error helpers ---

def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, (asyncio.TimeoutError, asyncpg.QueryCanceledError))


def mark_span_error(span, exc: Exception) -> None:
    """Set ERROR status, attach stack trace, and set error.type attribute."""
    span.set_status(Status(StatusCode.ERROR, str(exc)))
    span.record_exception(exc)
    span.set_attribute("error.type", "timeout" if _is_timeout(exc) else type(exc).__name__)


def trigger_alerts(span, exc: Exception) -> None:
    """Schedule registered alert hooks as a background task. Call from tool.* spans only."""
    if not _alert_hooks:
        return
    event = AlertEvent(
        span_name=span.name,
        error_type=type(exc).__name__,
        error_message=str(exc),
        is_timeout=_is_timeout(exc),
    )
    asyncio.create_task(_fire_alert_hooks(event))

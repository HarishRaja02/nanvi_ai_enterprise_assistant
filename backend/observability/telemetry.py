from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def configure_telemetry(enabled: bool, service_name: str, endpoint: str) -> None:
    if not enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("OTEL_ENABLED is true but OpenTelemetry packages are not installed")
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint or None)))
    trace.set_tracer_provider(provider)

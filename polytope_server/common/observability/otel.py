from opentelemetry import trace
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind, Status, StatusCode
from contextlib import contextmanager
import logging
from typing import Optional, Generator

def add_or_update_trace_context(request, update: bool = False) -> None:
    """
    Injects the current trace context into the request's OpenTelemetry trace context attribute.

    Args:
        request: The request object to update.
        update: Whether this is an update operation (default: False).
    """
    carrier = {}
    inject(carrier)

    if not hasattr(request, "otel_trace"):
        request.otel_trace = {}

    request.otel_trace['carrier'] = carrier

    action = "Updated" if update else "Added"
    logging.debug(f"[OTEL] {action} trace context with carrier: {carrier}")

    # Optionally set additional attributes on the current span
    current_span = trace.get_current_span()
    current_span.set_attribute("polytope.request.id", request.id)

def add_trace_context(request) -> None:
    """Adds a new trace context to the request."""
    add_or_update_trace_context(request, update=False)

def update_trace_context(request) -> None:
    """Updates the trace context in the request."""
    add_or_update_trace_context(request, update=True)

def restore_trace_context(request) -> Optional[trace.Span]:
    """
    Restores the trace context from the request.

    Args:
        request: The request object containing the trace context.

    Returns:
        The restored context, or None if not available.
    """
    if not hasattr(request, 'otel_trace') or 'carrier' not in request.otel_trace:
        logging.debug("[OTEL] No trace context found to restore.")
        return None

    carrier = request.otel_trace['carrier']
    logging.debug(f"[OTEL] Restoring context from carrier: {carrier}")
    extracted_context = extract(carrier)

    current_span = trace.get_current_span()
    current_span.set_attribute("polytope.request.id", request.id)

    return extracted_context

@contextmanager
def create_new_span(
    span_name: str,
    request_id: Optional[str] = None,
    parent_context: Optional[trace.SpanContext] = None,
    kind: SpanKind = SpanKind.SERVER,
) -> Generator[trace.Span, None, None]:
    """
    Creates a new span with the specified attributes.

    Args:
        span_name: Name of the span.
        request_id: Optional request ID to associate with the span.
        parent_context: Optional parent span context.
        kind: The kind of span to create (default: SERVER).
        role: Optional role to set as a span attribute.

    Yields:
        The created span.
    """
    tracer = trace.get_tracer(__name__)
    attributes = {"polytope.request.id": request_id} if request_id else {}

    with tracer.start_as_current_span(span_name, context=parent_context, kind=kind, attributes=attributes) as span:
        logging.debug(f"[OTEL] Created new span: {span_name}, parent: {parent_context}")
        yield span

@contextmanager
def create_new_span_internal(span_name: str, request_id: Optional[str] = None, parent_context: Optional[trace.SpanContext] = None) -> Generator[trace.Span, None, None]:
    """Creates an internal span."""
    yield from create_new_span(span_name, request_id, parent_context, kind=SpanKind.INTERNAL)

# Forcing span kind Server because of AWS representation
@contextmanager
def create_new_span_producer(span_name: str, request_id: Optional[str] = None, parent_context: Optional[trace.SpanContext] = None) -> Generator[trace.Span, None, None]:
    """Creates a producer span."""
    yield from create_new_span(span_name, request_id, parent_context, kind=SpanKind.SERVER)

# Forcing span kind Server because of AWS representation
@contextmanager
def create_new_span_consumer(span_name: str, request_id: Optional[str] = None, parent_context: Optional[trace.SpanContext] = None) -> Generator[trace.Span, None, None]:
    """Creates a consumer span."""
    yield from create_new_span(span_name, request_id, parent_context, kind=SpanKind.SERVER)

@contextmanager
def create_new_span_server(span_name: str, request_id: Optional[str] = None, parent_context: Optional[trace.SpanContext] = None) -> Generator[trace.Span, None, None]:
    """Creates a server span."""
    yield from create_new_span(span_name, request_id, parent_context, kind=SpanKind.SERVER)

def set_span_error(span: trace.Span, exception: Exception) -> None:
    """
    Marks a span as having an error.

    Args:
        span: The span to mark as an error.
        exception: The exception to log.
    """
    span.set_status(Status(StatusCode.ERROR, str(exception)))
    logging.error(f"[OTEL] Span error set with exception: {exception}")

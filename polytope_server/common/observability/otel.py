from opentelemetry import trace
from opentelemetry.propagate import inject, extract
from contextlib import contextmanager
import logging

def add_trace_context(request):
    carrier = {}

    # Inject the context into the carrier
    inject(carrier)

    # Adding trace_id and span_id to the request data for logging
    request.otel_trace_ctx = {
        'carrier': carrier  # Store the injected carrier
    }

    current_span = trace.get_current_span()
    current_span.set_attribute("polytope.request.id", request.id)

    logging.debug(f"[OTEL] Request created with carrier: {request.otel_trace_ctx['carrier']}")

def update_trace_context(request):
    carrier = {}

    # Inject the context into the carrier
    inject(carrier)

    # Adding trace_id and span_id to the request data for logging
    request.otel_trace_ctx = {
        'carrier': carrier  # Store the injected carrier
    }

    logging.debug(f"[OTEL] Request created with carrier: {request.otel_trace_ctx['carrier']}")


def restore_trace_context(request):
    # If otel context is not set, return
    if not hasattr(request, 'otel_trace_ctx'):
        return

    logging.debug(f"[OTEL] Restoring context from carrier: {request.otel_trace_ctx['carrier']}")

    # Extract the context from the stored request's carrier
    extracted_context = extract(carrier=request.otel_trace_ctx['carrier'])

    current_span = trace.get_current_span()
    current_span.set_attribute("polytope.request.id", request.id)

    return extracted_context

@contextmanager
def create_new_span_internal(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.INTERNAL):
    with create_new_span(span_name, request_id, parent_context, kind) as span:
        span.set_attribute("role", "internal")
        yield span

# Forcing span kind Server because of AWS representation
@contextmanager
def create_new_span_producer(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.SERVER):
    with create_new_span(span_name, request_id, parent_context, kind) as span:
        span.set_attribute("role", "producer")
        yield span

# Forcing span kind Server because of AWS representation
@contextmanager
def create_new_span_consumer(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.SERVER):
    with create_new_span(span_name, request_id, parent_context, kind) as span:
        span.set_attribute("role", "consumer")
        yield span

@contextmanager
def create_new_span_server(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.SERVER):
    with create_new_span(span_name, request_id, parent_context, kind) as span:
        span.set_attribute("role", "server")
        yield span

@contextmanager
def create_new_span(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.SERVER):
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(span_name, context=parent_context, kind=kind, attributes={"polytope.request.id": request_id }) as span:
        logging.debug(f"[OTEL] Creating new span: {span_name} parent: {parent_context}")
        yield span

def set_span_error(span, exception):
    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))

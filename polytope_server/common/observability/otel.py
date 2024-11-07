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


def create_new_span_producer(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.SERVER):
    return create_new_span(span_name, request_id, parent_context, kind)

def create_new_span_consumer(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.SERVER):
    return create_new_span(span_name, request_id, parent_context, kind)

@contextmanager
def create_new_span(span_name, request_id=None, parent_context=None, kind=trace.SpanKind.SERVER):
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(span_name, context=parent_context, kind=kind, attributes={"polytope.request.id": request_id }) as span:
        # if parent_context:
        #     # Extract SpanContext from the parent_context
        #     parent_span = trace.get_current_span(parent_context)
        #     span_context = parent_span.get_span_context()
        #     # Only add the link if the SpanContext is valid
        #     if span_context.is_valid:
        #         span.add_link(span_context)

        logging.debug(f"[OTEL] Creating new span: {span_name}")
        yield span

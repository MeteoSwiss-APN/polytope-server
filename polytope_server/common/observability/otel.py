from opentelemetry import trace
from opentelemetry.trace import SpanContext, TraceFlags, NonRecordingSpan
import logging

def add_trace_context(request):
        # Get the current active span
        current_span = trace.get_current_span()

        # Get key context values, this ensure the proper propagation for async requests
        # https://opentelemetry.io/docs/concepts/context-propagation

        trace_id = current_span.get_span_context().trace_id
        span_id = current_span.get_span_context().span_id
        sampled = current_span.get_span_context().trace_flags.sampled

        # Adding trace_id and span_id to the request data
        # We store the trace_id and span_id as strings to avoid issues with JSON serialization
        # We also store the sampled flag to propagate the sampling decision
        request.otel_trace_ctx = {
            'trace_id': str(trace_id),
            'span_id': str(span_id),
            'sampled': sampled
        }

        logging.debug(f"[OTEL] Request created with trace_id: {request.otel_trace_ctx['trace_id']} and span_id: {request.otel_trace_ctx['span_id']}")

def restore_trace_context(request):
    # If otel context is not set, return
    if not hasattr(request, 'otel_trace_ctx'):
        return

    logging.debug(f"[OTEL] Restoring context request with trace_id: {request.otel_trace_ctx}")

    # Retrieve the trace_id and span_id from the stored request
    trace_id = int(request.otel_trace_ctx['trace_id'], 16)  # Convert hex string to int
    span_id = int(request.otel_trace_ctx['span_id'], 16)    # Convert hex string to int
    sampled = bool(request.otel_trace_ctx['sampled'])

    # Create a SpanContext with the retrieved trace_id, span_id and sample flag
    span_context = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=True,
        trace_flags=TraceFlags(sampled)
    )

    # Set the current span as a non-recording span with the restored context
    current_span = NonRecordingSpan(span_context)

    # Set the restored span as the current context
    return trace.use_span(current_span)

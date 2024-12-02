import unittest
from polytope_server.common.observability.otel import (
    add_trace_context,
    update_trace_context,
    restore_trace_context,
    create_new_span,
    set_span_error,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import get_current_span, StatusCode

class MockRequest:
    def __init__(self, request_id):
        self.id = request_id
        self.otel_trace = {}

class TestOpenTelemetryUtils(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set up a real TracerProvider with an in-memory exporter
        cls.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(cls.span_exporter))
        # Set the TracerProvider globally
        trace.set_tracer_provider(tracer_provider)
        cls.tracer = tracer_provider.get_tracer(__name__)

    def setUp(self):
        # Clear the exported spans before each test
        self.span_exporter.clear()

    def test_add_trace_context(self):
        with self.tracer.start_as_current_span("test_span"):
            mock_request = MockRequest("test_id")
            add_trace_context(mock_request)

            # Ensure a carrier was injected into the request's trace context
            self.assertIn("carrier", mock_request.otel_trace)
            self.assertIn("traceparent", mock_request.otel_trace["carrier"])

            # Ensure the span has the correct attribute
            current_span = get_current_span()
            self.assertIn("polytope.request.id", current_span.attributes)
            self.assertEqual(current_span.attributes["polytope.request.id"], "test_id")

    def test_update_trace_context(self):
        with self.tracer.start_as_current_span("test_span"):
            mock_request = MockRequest("test_id")
            update_trace_context(mock_request)

            # Ensure the carrier was updated
            self.assertIn("carrier", mock_request.otel_trace)
            self.assertIn("traceparent", mock_request.otel_trace["carrier"])

            # Validate the span attributes
            current_span = get_current_span()
            self.assertIn("polytope.request.id", current_span.attributes)
            self.assertEqual(current_span.attributes["polytope.request.id"], "test_id")

    def test_restore_trace_context(self):
        with self.tracer.start_as_current_span("test_span"):
            # Add a carrier to the request
            mock_request = MockRequest("test_id")
            mock_request.otel_trace["carrier"] = {"traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"}

            restored_context = restore_trace_context(mock_request)
            self.assertIsNotNone(restored_context)

            # Ensure the current span has the correct attribute
            current_span = get_current_span()
            self.assertIn("polytope.request.id", current_span.attributes)
            self.assertEqual(current_span.attributes["polytope.request.id"], "test_id")

    def test_create_new_span(self):
        with create_new_span("test_span", request_id="test_id") as span:
            self.assertTrue(span.is_recording())
            self.assertIn("polytope.request.id", span.attributes)
            self.assertEqual(span.attributes["polytope.request.id"], "test_id")

        # Verify the span was recorded correctly
        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        recorded_span = spans[0]
        self.assertEqual(recorded_span.name, "test_span")
        self.assertIn("polytope.request.id", recorded_span.attributes)
        self.assertEqual(recorded_span.attributes["polytope.request.id"], "test_id")

    def test_set_span_error(self):
        with self.tracer.start_as_current_span("test_span") as span:
            exception = Exception("Test exception")
            set_span_error(span, exception)

            # Verify the span status
            self.assertEqual(span.status.status_code, StatusCode.ERROR)
            self.assertEqual(span.status.description, "Test exception")

        # Verify the span was recorded with error
        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        recorded_span = spans[0]
        self.assertEqual(recorded_span.status.status_code, StatusCode.ERROR)
        self.assertEqual(recorded_span.status.description, "Test exception")

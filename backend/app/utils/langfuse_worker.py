
import os
import base64
from app.utils.logging import get_logger

try:
    from langfuse.langchain import CallbackHandler
except ImportError:
    CallbackHandler = None

try:
    from openinference.instrumentation.dspy import DSPyInstrumentor
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
except ImportError:
    DSPyInstrumentor = None


logger = get_logger(__name__)

_langfuse_handler = None

def get_langfuse_handler():
    """
    Returns a singleton Langfuse CallbackHandler for LangChain.
    """
    global _langfuse_handler
    
    # helper to check if configured
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        logger.warning("Langfuse credentials not found. Skipping handler initialization.")
        return None

    if _langfuse_handler is None:
        try:
            if CallbackHandler:
                _langfuse_handler = CallbackHandler()
                logger.info("Langfuse CallbackHandler initialized.")
            else:
                 logger.error("Could not import langfuse.callback.CallbackHandler. Is langfuse-langchain installed?")
                 return None
        except Exception as e:
            logger.error(f"Error initializing Langfuse CallbackHandler: {e}")
            return None

    return _langfuse_handler

def setup_dspy_instrumentation():
    """
    Sets up OpenInference instrumentation for DSPy if credentials are present.
    """
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        logger.warning("Langfuse credentials not found. Skipping DSPy instrumentation.")
        return

    try:
        # Langfuse OTLP endpoint: <base_url>/api/public/otlp/v1/traces
        base_url = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        endpoint = f"{base_url.rstrip('/')}/api/public/otlp/v1/traces"
        
        # Encode credentials for Basic Auth
        credentials = f"{os.getenv('LANGFUSE_PUBLIC_KEY')}:{os.getenv('LANGFUSE_SECRET_KEY')}"
        auth_token = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {auth_token}"
        }

        if not DSPyInstrumentor:
             logger.warning("OpenInference/DSPy instrumentation packages not found.")
             return

        trace_provider = TracerProvider()
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
        trace_provider.add_span_processor(processor)
        trace.set_tracer_provider(trace_provider)

        DSPyInstrumentor().instrument()
        logger.info("DSPy OpenInference instrumentation enabled.")

    except Exception as e:
        logger.error(f"Failed to setup DSPy instrumentation: {e}")

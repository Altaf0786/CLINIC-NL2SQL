"""Structured logging with JSON support, request tracing, and performance monitoring.

Provides a StructuredLogger that attaches a unique request ID (via
ContextVar) to every log entry, a PerformanceMonitor context manager
for timing operations, and a RequestLogger for HTTP audit trails.
"""

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Dict, Optional

try:
    from pythonjsonlogger import jsonlogger
except ImportError:
    jsonlogger = None

from backend.config.settings import settings

# Context variable for request tracing
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """Return the current request ID, generating one if not set."""
    current_request_id = _request_id.get()
    if not current_request_id:
        current_request_id = str(uuid.uuid4())
        _request_id.set(current_request_id)
    return current_request_id


def set_request_id(request_id: str):
    """Set the request ID for the current async context."""
    _request_id.set(request_id)


def reset_request_id():
    """Clear the request ID after a request completes."""
    _request_id.set(None)


class StructuredLogger:
    """Application logger with JSON output and per-request tracing."""

    def __init__(self, name: str):
        """Create a named logger and attach configured handlers."""
        self.logger = logging.getLogger(name)
        self._setup_handlers()

    def _setup_handlers(self):
        """Configure console or file handlers based on settings."""
        if not self.logger.handlers:
            level = getattr(logging, settings.LOG_LEVEL)
            self.logger.setLevel(level)

            use_file_handler = bool(settings.LOG_FILE) and settings.is_production

            if settings.LOG_FORMAT == "json" and jsonlogger and use_file_handler:
                handler = logging.FileHandler(settings.LOG_FILE)
                formatter = jsonlogger.JsonFormatter()
                handler.setFormatter(formatter)
            else:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s"
                )
                handler.setFormatter(formatter)

            self.logger.addHandler(handler)
            self.logger.propagate = False

    def _add_context(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Inject request ID and timestamp into the log extra dict."""
        return {
            "request_id": get_request_id(),
            "timestamp": datetime.now(UTC).isoformat(),
            **extra,
        }

    def info(self, message: str, **extra):
        """Log an informational message."""
        self.logger.info(message, extra=self._add_context(extra))

    def error(self, message: str, **extra):
        """Log an error message with traceback."""
        self.logger.error(message, extra=self._add_context(extra), exc_info=True)

    def warning(self, message: str, **extra):
        """Log a warning message."""
        self.logger.warning(message, extra=self._add_context(extra))

    def debug(self, message: str, **extra):
        """Log a debug-level message."""
        self.logger.debug(message, extra=self._add_context(extra))

    def exception(self, message: str, exc: Exception, **extra):
        """Log an exception with full traceback and error metadata."""
        context = self._add_context(
            {"error_type": type(exc).__name__, "error_message": str(exc), **extra}
        )
        self.logger.exception(message, extra=context)


# Global logger instance
logger = StructuredLogger("clinic-nl2sql")


class PerformanceMonitor:
    """Context manager that logs operation duration on exit."""

    def __init__(self, operation: str, logger_instance: StructuredLogger = None):
        """Initialise with the operation name and optional logger."""
        self.operation = operation
        self.log = logger_instance or logger
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        """Record the start timestamp."""
        self.start_time = time.time()
        self.log.debug(f"Starting operation: {self.operation}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Log the elapsed time and whether the operation succeeded."""
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000

        if exc_type:
            self.log.error(
                f"Operation failed: {self.operation}",
                duration_ms=duration_ms,
                error_type=exc_type.__name__,
            )
        else:
            self.log.info(
                f"Operation completed: {self.operation}", duration_ms=duration_ms
            )
        return False


@contextmanager
def monitor_performance(operation: str):
    """Convenience wrapper around PerformanceMonitor."""
    monitor = PerformanceMonitor(operation)
    with monitor:
        yield monitor


class RequestLogger:
    """Static helper for logging HTTP request/response audit entries."""

    @staticmethod
    def log_request(method: str, path: str, body: Optional[Dict] = None):
        """Log an incoming HTTP request."""
        logger.info(
            "API request received",
            method=method,
            path=path,
            body=str(body)[:500] if body else None,
        )

    @staticmethod
    def log_response(method: str, path: str, status_code: int, duration_ms: float):
        """Log an outgoing HTTP response with status and timing."""
        level = "info" if 200 <= status_code < 300 else "warning"
        log_func = getattr(logger, level)
        log_func(
            "API response sent",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=f"{duration_ms:.2f}",
        )

    @staticmethod
    def log_error(method: str, path: str, error: Exception):
        """Log an unhandled error during request processing."""
        logger.exception(
            f"API error occurred: {method} {path}",
            exc=error,
            method=method,
            path=path,
        )


__all__ = [
    "logger",
    "StructuredLogger",
    "PerformanceMonitor",
    "RequestLogger",
    "monitor_performance",
    "get_request_id",
    "set_request_id",
    "reset_request_id",
]

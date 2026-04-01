"""Security primitives: JWT tokens, input validation, rate limiting.

Provides reusable components for authentication (HS256 JWT),
user-input sanitisation, and per-client sliding-window rate limiting
with thread-safe operations for concurrent request handling.
"""

import threading
from datetime import UTC, datetime, timedelta
from typing import Dict, Optional

import jwt
from jwt.exceptions import InvalidTokenError

from backend.config.settings import settings
from backend.utils.logger import logger


class TokenManager:
    """Stateless JWT token creation and verification."""

    @staticmethod
    def create_access_token(
        data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a signed JWT with an expiration claim."""
        to_encode = data.copy()
        expire = datetime.now(UTC) + (
            expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> Optional[Dict]:
        """Decode and verify a JWT, returning claims or None on failure."""
        try:
            return jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
        except InvalidTokenError as e:
            logger.error(f"Token verification failed: {str(e)}")
            return None


class InputValidator:
    """Validate and sanitise user-submitted questions."""

    @staticmethod
    def validate_question(question: str) -> tuple[bool, str]:
        """Check length, emptiness, and dangerous patterns; return (ok, error_msg)."""
        if not question:
            return False, "Question cannot be empty"
        if len(question) < 3:
            return False, "Question must be at least 3 characters"
        if len(question) > settings.MAX_REQUEST_SIZE:
            return False, f"Question exceeds maximum length of {settings.MAX_REQUEST_SIZE}"

        dangerous_patterns = [
            "DROP",
            "DELETE FROM",
            "TRUNCATE",
            "ALTER",
            "exec(",
            "eval(",
            "__import__",
        ]
        question_upper = question.upper()
        for pattern in dangerous_patterns:
            if pattern in question_upper:
                logger.warning(f"Suspicious pattern detected in question: {pattern}")
                return False, "Question contains potentially harmful content"

        return True, ""

    @staticmethod
    def sanitize_response(response: str) -> str:
        """Truncate a response string to a safe maximum length."""
        return response[:10000] if response else ""


class RateLimiter:
    """Thread-safe in-memory sliding-window rate limiter keyed by client identifier.

    Uses a lock to prevent race conditions when multiple async requests
    read/write the same client's timestamp list concurrently.
    """

    def __init__(self) -> None:
        """Initialise with an empty request log and a lock for thread safety."""
        self.requests: Dict[str, list] = {}
        self._lock = threading.Lock()

    def is_allowed(self, identifier: str) -> bool:
        """Return True if the client has not exceeded the per-minute limit."""
        if not settings.RATE_LIMITING_ENABLED:
            return True

        now = datetime.now(UTC)
        one_minute_ago = now - timedelta(minutes=1)

        with self._lock:
            if identifier in self.requests:
                self.requests[identifier] = [
                    ts for ts in self.requests[identifier] if ts > one_minute_ago
                ]
            else:
                self.requests[identifier] = []

            if len(self.requests[identifier]) >= settings.RATE_LIMIT_PER_MINUTE:
                logger.warning(
                    f"Rate limit exceeded for {identifier}",
                    requests_count=len(self.requests[identifier]),
                )
                return False

            self.requests[identifier].append(now)
            return True

    def get_remaining(self, identifier: str) -> int:
        """Return the number of requests the client can still make this minute."""
        with self._lock:
            if identifier not in self.requests:
                return settings.RATE_LIMIT_PER_MINUTE

            now = datetime.now(UTC)
            one_minute_ago = now - timedelta(minutes=1)
            recent = [ts for ts in self.requests[identifier] if ts > one_minute_ago]
            return max(0, settings.RATE_LIMIT_PER_MINUTE - len(recent))


def get_client_identifier(client_host: Optional[str]) -> str:
    """Derive a rate-limiting key from the client's IP address."""
    return client_host or "unknown-client"


# Global rate limiter instance
rate_limiter = RateLimiter()

__all__ = [
    "TokenManager",
    "InputValidator",
    "RateLimiter",
    "get_client_identifier",
    "rate_limiter",
]

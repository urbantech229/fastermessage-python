"""SDK Python officiel de l'API FasterMessage v2."""

from . import webhook
from ._http import VERSION as __version__
from .client import DEFAULT_BASE_URL, FasterMessage
from .errors import (
    ApiConnectionError,
    ApiError,
    AuthenticationError,
    ConflictError,
    FasterMessageError,
    InsufficientBalanceError,
    InvalidRequestError,
    NotFoundError,
    NotServedError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "FasterMessage",
    "webhook",
    "__version__",
    "ApiConnectionError",
    "ApiError",
    "AuthenticationError",
    "ConflictError",
    "FasterMessageError",
    "InsufficientBalanceError",
    "InvalidRequestError",
    "NotFoundError",
    "NotServedError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
]

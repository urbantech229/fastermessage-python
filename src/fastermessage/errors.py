"""Erreurs levées par le SDK."""

from typing import Optional


class FasterMessageError(Exception):
    """Toute erreur levée par le SDK."""


class ApiError(FasterMessageError):
    """Refus de l'API.

    Testez ``code``, qui est stable : le message est un libellé en anglais,
    susceptible d'être reformulé.
    """

    def __init__(
        self,
        message: str,
        status: int,
        code: str,
        type: str = "",
        param: Optional[str] = None,
        request_id: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.type = type
        self.param = param
        self.request_id = request_id
        self.retry_after = retry_after


class InvalidRequestError(ApiError):
    """400 : la requête est à corriger."""


class AuthenticationError(ApiError):
    """401 : identifiant, mot de passe ou clé refusés."""


class InsufficientBalanceError(ApiError):
    """402 : solde insuffisant, le compte débité est à recharger."""


class PermissionDeniedError(ApiError):
    """403 : opération interdite à ce compte."""


class NotFoundError(ApiError):
    """404 : ressource introuvable."""


class ConflictError(ApiError):
    """409 : conflit, par exemple un groupe non vide."""


class RateLimitError(ApiError):
    """429 : débit dépassé, voir ``retry_after``."""


class NotServedError(ApiError):
    """501 : fonction déclarée au contrat mais pas encore servie."""


class ServerError(ApiError):
    """5xx : panne côté API."""


class ApiConnectionError(FasterMessageError):
    """Coupure réseau ou délai dépassé.

    L'appel a pu aboutir : rejouez avec ``idempotency_key``, jamais avec une
    nouvelle clé.
    """

    def __init__(self, message: str, idempotency_key: Optional[str] = None) -> None:
        super().__init__(message)
        self.idempotency_key = idempotency_key

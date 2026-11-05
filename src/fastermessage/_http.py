"""Le chemin unique de tous les appels : en-têtes, idempotence, reprises, erreurs."""

import http.client
import json
import random
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Mapping, NamedTuple, Optional, Type

from .errors import (
    ApiConnectionError,
    ApiError,
    AuthenticationError,
    ConflictError,
    InsufficientBalanceError,
    InvalidRequestError,
    NotFoundError,
    NotServedError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
)

VERSION = "0.1.0"

# Un même appel rejoué garde sa clé : c'est ce qui rend une reprise sans risque.
_MUTATING = {"POST", "PATCH", "PUT", "DELETE"}


class Response(NamedTuple):
    status: int
    headers: Mapping[str, str]  # noms en minuscules
    body: str


Transport = Callable[[str, str, Mapping[str, str], Optional[bytes], float], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Une redirection recopierait les identifiants vers l'adresse de destination."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Optional[bytes],
    timeout: float,
) -> Response:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with _opener.open(request, timeout=timeout) as reply:
            return Response(reply.status, _lower(reply.headers), reply.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        with error:
            return Response(error.code, _lower(error.headers), error.read().decode("utf-8", "replace"))
    except (OSError, http.client.HTTPException) as error:
        raise ApiConnectionError(f"Connexion à l'API impossible : {error}") from error


def _lower(headers: Any) -> Dict[str, str]:
    return {str(name).lower(): str(value) for name, value in headers.items()}


class Requester:
    __slots__ = ("_authorization", "_api_key", "_base_url", "_timeout", "_max_retries", "_transport", "_sleep")

    def __init__(
        self,
        authorization: str,
        api_key: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        transport: Optional[Transport] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._authorization = authorization
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport or urllib_transport
        self._sleep = sleep or time.sleep

    def __repr__(self) -> str:
        return "<Requester>"

    def request(
        self,
        method: str,
        path: str,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Any:
        url = self._base_url + path + _query_string(query)
        headers = {
            "Authorization": self._authorization,
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
            "User-Agent": f"fastermessage-python/{VERSION}",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if request_id is not None:
            headers["X-Request-Id"] = request_id

        key: Optional[str] = None
        if method in _MUTATING:
            key = idempotency_key or f"sdk-{secrets.token_hex(16)}"
            headers["Idempotency-Key"] = key

        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")

        attempt = 0
        while True:
            try:
                response = self._transport(method, url, headers, payload, self._timeout)
            except ApiConnectionError as error:
                if attempt >= self._max_retries:
                    error.idempotency_key = key
                    raise
                self._sleep(_backoff(attempt))
                attempt += 1
                continue

            if response.status < 300:
                return _decode(response)

            failure = _to_error(response)
            wait = _retry_delay(failure, attempt)
            if wait is None or attempt >= self._max_retries:
                raise failure
            self._sleep(wait)
            attempt += 1


def _query_string(query: Optional[Mapping[str, Any]]) -> str:
    if not query:
        return ""
    kept = {name: value for name, value in query.items() if value is not None}
    return "?" + urllib.parse.urlencode(kept) if kept else ""


def _retry_delay(failure: ApiError, attempt: int) -> Optional[float]:
    """Reprise seulement si la même requête peut réussir plus tard.

    Un 429 sans ``Retry-After`` est le plafond OTP par numéro, à l'échelle de
    l'heure : le rejouer ne servirait à rien. Le 501 dit une fonction non servie,
    jamais une panne.
    """
    if failure.status == 429:
        return None if failure.retry_after is None else float(failure.retry_after)
    if failure.code == "idempotency_key_in_flight":
        return _backoff(attempt)
    if failure.status >= 500 and failure.status != 501:
        return _backoff(attempt)
    return None


def _backoff(attempt: int) -> float:
    return min(8.0, 0.5 * 2**attempt) * (1 + random.random() * 0.25)


def _parse(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _decode(response: Response) -> Any:
    if response.status == 204 or not response.body.strip():
        return None
    data = _parse(response.body)
    if not isinstance(data, (dict, list)):
        raise ServerError(
            "Réponse illisible de l'API.",
            response.status,
            "invalid_response",
            "api_error",
            None,
            response.headers.get("x-request-id"),
        )
    return data


def _string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _error_class(status: int) -> Type[ApiError]:
    classes: Dict[int, Type[ApiError]] = {
        400: InvalidRequestError,
        401: AuthenticationError,
        402: InsufficientBalanceError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        429: RateLimitError,
        501: NotServedError,
    }
    return classes.get(status, ServerError if status >= 500 else ApiError)


def _to_error(response: Response) -> ApiError:
    decoded = _parse(response.body)
    error = decoded.get("error") if isinstance(decoded, dict) else None
    if not isinstance(error, dict):
        error = {}
    retry_after = response.headers.get("retry-after", "").strip()
    status = response.status

    return _error_class(status)(
        _string(error.get("message")) or f"Erreur HTTP {status}.",
        status,
        _string(error.get("code")) or f"http_{status}",
        _string(error.get("type")) or "",
        _string(error.get("param")),
        _string(error.get("request_id")) or response.headers.get("x-request-id"),
        int(retry_after) if retry_after.isdigit() else None,
    )

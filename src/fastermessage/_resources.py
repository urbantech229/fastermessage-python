"""Les ressources de l'API. Paramètres et réponses gardent les noms de champs de l'API."""

import urllib.parse
from typing import Any, Dict, Iterator, List, Mapping, Optional

from ._http import Requester

Params = Mapping[str, Any]
Result = Dict[str, Any]


def _segment(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


class _Resource:
    __slots__ = ("_http",)

    def __init__(self, http: Requester) -> None:
        self._http = http

    def _paginate(self, path: str, query: Optional[Params]) -> Iterator[Result]:
        """Parcourt toutes les pages, en demandant la suivante seulement quand il le faut."""
        current = dict(query or {})
        while True:
            page = self._http.request("GET", path, query=current) or {}
            yield from page.get("data") or []
            cursor = page.get("next_cursor")
            if page.get("has_more") is not True or cursor is None:
                return
            current["cursor"] = cursor


class Sms(_Resource):
    def send(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        return self._http.request("POST", "/v2/sms/send", body=params, idempotency_key=idempotency_key, request_id=request_id)

    def send_batch(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        """Jusqu'à 500 lignes. Lisez toujours ``errors`` : un retour normal ne garantit pas que toutes soient parties."""
        return self._http.request("POST", "/v2/sms/batch", body=params, idempotency_key=idempotency_key, request_id=request_id)


class Email(_Resource):
    def send(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        return self._http.request("POST", "/v2/email/send", body=params, idempotency_key=idempotency_key, request_id=request_id)


class Messages(_Resource):
    def send(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        """Envoi avec le canal en paramètre. WhatsApp et la voix répondent aujourd'hui ``501``."""
        return self._http.request("POST", "/v2/messages", body=params, idempotency_key=idempotency_key, request_id=request_id)

    def get(self, id: str) -> Result:
        return self._http.request("GET", f"/v2/messages/{_segment(id)}")

    def list(self, **query: Any) -> Result:
        return self._http.request("GET", "/v2/messages", query=query)

    def all(self, **query: Any) -> Iterator[Result]:
        return self._paginate("/v2/messages", query)


class Otp(_Resource):
    def request(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        return self._http.request("POST", "/v2/otp", body={"channel": "sms", **params}, idempotency_key=idempotency_key, request_id=request_id)

    def verify(self, id: str, code: str) -> Result:
        return self._http.request("POST", "/v2/otp/verify", body={"id": id, "code": code})


class Contacts(_Resource):
    def create(self, params: Params) -> Result:
        return self._http.request("POST", "/v2/contacts", body=params)

    def create_batch(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        """Crée jusqu'à 500 contacts dans un groupe."""
        return self._http.request("POST", "/v2/contacts/batch", body=params, idempotency_key=idempotency_key, request_id=request_id)

    def get(self, id: str) -> Result:
        return self._http.request("GET", f"/v2/contacts/{_segment(id)}")

    def list(self, **query: Any) -> Result:
        return self._http.request("GET", "/v2/contacts", query=query)

    def all(self, **query: Any) -> Iterator[Result]:
        return self._paginate("/v2/contacts", query)

    def update(self, id: str, params: Params) -> Result:
        return self._http.request("PATCH", f"/v2/contacts/{_segment(id)}", body=params)

    def delete(self, id: str) -> None:
        """Suppression définitive. Ce n'est pas un désabonnement : pour cela, ``consent: out``."""
        self._http.request("DELETE", f"/v2/contacts/{_segment(id)}")


class ContactGroups(_Resource):
    def create(self, params: Params) -> Result:
        return self._http.request("POST", "/v2/contact-groups", body=params)

    def get(self, id: str) -> Result:
        return self._http.request("GET", f"/v2/contact-groups/{_segment(id)}")

    def list(self, **query: Any) -> Result:
        return self._http.request("GET", "/v2/contact-groups", query=query)

    def all(self, **query: Any) -> Iterator[Result]:
        return self._paginate("/v2/contact-groups", query)

    def update(self, id: str, params: Params) -> Result:
        return self._http.request("PATCH", f"/v2/contact-groups/{_segment(id)}", body=params)

    def delete(self, id: str) -> None:
        """Refusé en ``409`` tant que le groupe contient des contacts."""
        self._http.request("DELETE", f"/v2/contact-groups/{_segment(id)}")


class Account(_Resource):
    def balance(self) -> List[Result]:
        return (self._http.request("GET", "/v2/balance") or {}).get("balances") or []

    def credits(self, **query: Any) -> Result:
        return self._http.request("GET", "/v2/credits", query=query)

    def all_credits(self, **query: Any) -> Iterator[Result]:
        return self._paginate("/v2/credits", query)

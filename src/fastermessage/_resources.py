"""Les ressources de l'API. Paramètres et réponses gardent les noms de champs de l'API.

Repli entre canaux : ``sms.send``, ``email.send``, ``whatsapp.send``, ``messages.send`` et ``otp.request``
acceptent ``fallback``, une liste ordonnée d'étapes ``{"channel": "sms"|"email"|"whatsapp", "to", "from", "content"}``.
``content`` est obligatoire vers le SMS (chaîne ou ``{"text", "unicode"}``), facultatif vers l'e-mail (sauf
après un modèle WhatsApp), et vers WhatsApp un modèle (``template``, ``language``, ``variables``) ou un texte
(``text``, qui ne part que si la fenêtre de 24 h est ouverte).
La réponse porte alors ``fallback`` (``will_run``, ``state``, ``steps``), ``None`` sans repli.
``test_outcome`` (``failed`` ou ``delivered``) simule l'issue, avec une clé ``fm_test_`` seulement.
"""

import urllib.parse
from typing import Any, Dict, Iterator, List, Mapping, Optional

from ._http import Requester

Params = Mapping[str, Any]
Result = Dict[str, Any]


def _segment(value: str) -> str:
    text = str(value)
    # ``..`` changerait la route visée, et un identifiant vide viserait la collection.
    if text in ("", ".", ".."):
        raise ValueError("Identifiant de ressource invalide.")
    return urllib.parse.quote(text, safe="")


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
        """Jusqu'à 500 lignes. Lisez toujours ``errors`` : un retour normal ne garantit pas que toutes soient parties.

        Le lot refuse ``fallback`` (400) : envoyez un par un avec ``send``.
        """
        return self._http.request("POST", "/v2/sms/batch", body=params, idempotency_key=idempotency_key, request_id=request_id)


class Email(_Resource):
    def send(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        """Envoie un e-mail. ``content`` : ``{"subject", "html", "text", "reply_to"}`` — ``subject`` et
        ``html`` et/ou ``text`` obligatoires ; ``reply_to`` facultatif, l'adresse qui recevra les réponses,
        sans nom affiché.
        """
        return self._http.request("POST", "/v2/email/send", body=params, idempotency_key=idempotency_key, request_id=request_id)

    def list_senders(self, **query: Any) -> Result:
        """Une page des adresses expéditrices utilisables dans ``from`` : ``data``, ``has_more``, ``next_cursor``.

        Adresses actives (domaine authentifié), et l'adresse par défaut de votre marque si vous y avez droit.
        Chaque adresse : ``address`` (à mettre dans ``from``), ``name``, ``domain``, ``brand_default``.
        Filtres : ``limit`` (50 par défaut, 200 au plus) et ``cursor``.
        """
        return self._http.request("GET", "/v2/email/senders", query=query)

    def all_senders(self, **query: Any) -> Iterator[Result]:
        """Toutes les adresses expéditrices utilisables, page après page."""
        return self._paginate("/v2/email/senders", query)

    def list_templates(self, **query: Any) -> Result:
        """Une page des modèles e-mail publiés : ``data``, ``has_more``, ``next_cursor``.

        Chaque modèle : ``id``, ``name``, ``subject``, ``html``, ``from_email`` (``None`` si l'adresse du modèle
        n'est plus utilisable), ``from_name``, ``reply_to``. Filtres : ``limit`` et ``cursor``.
        """
        return self._http.request("GET", "/v2/email/templates", query=query)

    def all_templates(self, **query: Any) -> Iterator[Result]:
        """Tous les modèles e-mail publiés, page après page."""
        return self._paginate("/v2/email/templates", query)


class Whatsapp(_Resource):
    def send(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        """Envoie un message WhatsApp. ``from`` (numéro raccordé au compte) est obligatoire.

        ``content`` : un modèle approuvé, à tout moment — ``{"template", "language", "variables"}``, variables
        ``"1"``, ``"2"``… pour ``{{1}}``, ``{{2}}``… du corps, ``"header"`` pour l'en-tête texte, ``"button_1"``…
        pour le lien d'un bouton — ou un texte libre ``{"text"}``, seulement si le destinataire a écrit à ce
        numéro dans les 24 h (sinon ``409 session_window_closed``). Un message lu reste ``delivered`` ; sa
        lecture se lit dans ``read_at``. L'envoi programmé n'est pas encore ouvert sur WhatsApp.
        """
        return self._http.request("POST", "/v2/whatsapp/send", body=params, idempotency_key=idempotency_key, request_id=request_id)

    def list_numbers(self, **query: Any) -> Result:
        """Une page des numéros WhatsApp qui peuvent envoyer maintenant : ``data``, ``has_more``, ``next_cursor``.

        Chaque numéro : ``number`` (à mettre dans ``from``), ``display_name``, ``label``, ``quality``,
        ``is_default``. Filtres : ``limit`` (50 par défaut, 200 au plus) et ``cursor``.
        """
        return self._http.request("GET", "/v2/whatsapp/numbers", query=query)

    def all_numbers(self, **query: Any) -> Iterator[Result]:
        """Tous les numéros WhatsApp envoyables, page après page."""
        return self._paginate("/v2/whatsapp/numbers", query)

    def list_templates(self, **query: Any) -> Result:
        """Une page des modèles approuvés et envoyables par l'API : ``data``, ``has_more``, ``next_cursor``.

        Chaque modèle : ``id``, ``name``, ``language``, ``category``, ``header_text``, ``body``, ``footer``,
        ``variables`` (les clés attendues dans ``content.variables`` : ``"1"``, ``"2"``…, ``"header"``,
        ``"button_1"``…) et ``number``, le numéro de son compte WhatsApp Business (Meta refuse un modèle envoyé
        depuis un autre compte). Un modèle de catégorie ``authentication`` sert ``fm.otp.request()``, pas
        ``send()``. Filtres : ``limit`` et ``cursor``.
        """
        return self._http.request("GET", "/v2/whatsapp/templates", query=query)

    def all_templates(self, **query: Any) -> Iterator[Result]:
        """Tous les modèles envoyables, page après page."""
        return self._paginate("/v2/whatsapp/templates", query)


class Messages(_Resource):
    def send(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        """Envoi avec le canal en paramètre. La voix répond aujourd'hui ``501``."""
        return self._http.request("POST", "/v2/messages", body=params, idempotency_key=idempotency_key, request_id=request_id)

    def get(self, id: str) -> Result:
        return self._http.request("GET", f"/v2/messages/{_segment(id)}")

    def list(self, **query: Any) -> Result:
        return self._http.request("GET", "/v2/messages", query=query)

    def all(self, **query: Any) -> Iterator[Result]:
        return self._paginate("/v2/messages", query)


class Otp(_Resource):
    def request(self, params: Params, *, idempotency_key: Optional[str] = None, request_id: Optional[str] = None) -> Result:
        """Émet un code, par SMS sans ``channel``. Conservez ``id`` : le code n'est jamais renvoyé.

        ``"channel": "whatsapp"`` envoie le code par votre modèle d'authentification approuvé : ``from`` est
        alors le numéro WhatsApp (obligatoire), ``template`` le nom du modèle et ``language`` sa langue, tous
        deux facultatifs s'il est unique.

        ``fallback`` (vers le SMS, l'e-mail ou WhatsApp) : un ``content`` propre (SMS, e-mail) doit contenir ``{code}``. ``callback_url``
        reçoit le rappel de repli, à défaut l'adresse du compte.
        """
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

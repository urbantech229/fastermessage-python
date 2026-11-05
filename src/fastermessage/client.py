"""Point d'entrée du SDK."""

import base64
import urllib.parse
from typing import Callable, Optional

from ._http import Requester, Transport
from ._resources import Account, ContactGroups, Contacts, Email, Messages, Otp, Sms

DEFAULT_BASE_URL = "https://api.fastermessage.com"


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _checked_base_url(value: str) -> str:
    """Les identifiants ne partent qu'en https, sauf vers la machine locale."""
    message = "base_url doit être une adresse https, sans identifiants (http seulement vers la machine locale)."
    try:
        parts = urllib.parse.urlsplit(value)
        host = parts.hostname
        has_credentials = parts.username is not None or parts.password is not None
    except ValueError:
        raise ValueError(message) from None
    allowed = parts.scheme == "https" or (parts.scheme == "http" and host in _LOCAL_HOSTS)
    if not allowed or not host or has_credentials or parts.query or parts.fragment:
        raise ValueError(message)
    return value.rstrip("/")


class FasterMessage:
    """Client de l'API v2.

    :param username: identifiant d'API, compte débité
    :param password: mot de passe d'API
    :param api_key: clé ``fm_live_…`` (réel) ou ``fm_test_…`` (simulé)
    :param base_url: le domaine d'API de votre marque, le cas échéant
    :param timeout: délai d'attente réseau de chaque tentative, en secondes
    :param max_retries: nombre de reprises après la première tentative
    :param transport: remplace l'envoi HTTP, surtout utile dans vos tests
    :param sleep: remplace l'attente entre deux reprises, surtout utile dans vos tests
    """

    def __init__(
        self,
        username: str,
        password: str,
        api_key: str,
        *,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: Optional[Transport] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> None:
        if not username or not password or not api_key:
            raise ValueError("L'identifiant, le mot de passe et la clé d'API sont tous obligatoires.")

        if not all(33 <= ord(char) <= 126 for char in api_key):
            # Le message ne cite jamais la valeur : il finirait dans vos journaux.
            raise ValueError("La clé d'API contient des caractères invalides : vérifiez son copier-coller.")

        self._test_mode = "_test_" in api_key
        credentials = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")

        http = Requester(
            f"Basic {credentials}",
            api_key,
            _checked_base_url(base_url or DEFAULT_BASE_URL),
            timeout,
            max(0, max_retries),
            transport,
            sleep,
        )

        self.sms = Sms(http)
        self.email = Email(http)
        self.messages = Messages(http)
        self.otp = Otp(http)
        self.contacts = Contacts(http)
        self.contact_groups = ContactGroups(http)
        self.account = Account(http)

    @property
    def test_mode(self) -> bool:
        """Vrai avec une clé de test : messages et OTP simulés, mais contacts et soldes réels."""
        return self._test_mode

    def __repr__(self) -> str:
        # Évite d'écrire le moindre identifiant dans un journal.
        return f"FasterMessage(test_mode={self._test_mode})"

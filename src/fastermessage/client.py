"""Point d'entrée du SDK."""

import base64
from typing import Callable, Optional

from ._http import Requester, Transport
from ._resources import Account, ContactGroups, Contacts, Email, Messages, Otp, Sms

DEFAULT_BASE_URL = "https://api.fastermessage.com"


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

        self._test_mode = "_test_" in api_key
        credentials = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")

        http = Requester(
            f"Basic {credentials}",
            api_key,
            (base_url or DEFAULT_BASE_URL).rstrip("/"),
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

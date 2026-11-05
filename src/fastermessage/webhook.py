"""Vérification des rappels reçus sur votre serveur."""

import hashlib
import hmac
from typing import Optional, Union


def is_genuine(raw_body: Union[str, bytes], signature: Optional[str], secret: str) -> bool:
    """Vrai si le rappel vient bien de la plateforme.

    :param raw_body: le corps BRUT, avant tout décodage JSON
    :param signature: l'en-tête ``X-Fastermessage-Signature``
    :param secret: le secret généré dans « Intégration & API »
    """
    if not isinstance(signature, str) or not secret:
        return False
    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode("utf-8"), signature.strip().encode("utf-8"))

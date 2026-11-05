# FasterMessage Python

SDK Python officiel de l'API FasterMessage v2 : SMS, e-mail, codes de vérification (OTP), contacts et webhooks.

Python 3.9 ou plus récent. Aucune dépendance. Annotations de types incluses.

```bash
pip install fastermessage
```

## Démarrage

```python
import os
from fastermessage import FasterMessage

fm = FasterMessage(
    os.environ["FM_API_USER"],
    os.environ["FM_API_PASSWORD"],
    os.environ["FM_API_KEY"],  # fm_test_… simule, fm_live_… envoie et débite
)

message = fm.sms.send({
    "to": "+2290160000000",
    "from": "FASTERMSG",
    "content": "Votre commande est prete.",
    "client_reference": "cmd-42",
})

print(message["id"], message["status"])  # queued
```

Sur le domaine d'API de votre marque : `FasterMessage(user, password, key, base_url="https://api.votre-marque.com")`.

## Ce que fait le SDK

| Besoin | Appel |
|---|---|
| SMS | `fm.sms.send()`, `fm.sms.send_batch()` (500 lignes) |
| E-mail | `fm.email.send()` |
| Canal en paramètre | `fm.messages.send()` |
| Suivi | `fm.messages.get()`, `list()`, `all()` |
| OTP | `fm.otp.request()`, `fm.otp.verify()` |
| Contacts | `fm.contacts`, `fm.contact_groups` : `create`, `get`, `list`, `all`, `update`, `delete` |
| Compte | `fm.account.balance()`, `credits()`, `all_credits()` |
| Webhooks | `webhook.is_genuine()` |

Les réponses sont des dictionnaires, aux noms de champs de l'API : un champ ajouté par l'API est disponible sans mise à jour du SDK. La référence complète est dans la [documentation de l'API](https://www.fastermessage.com/docs).

`all()` parcourt toutes les pages et ne demande la suivante que si vous continuez :

```python
for contact in fm.contacts.all(group_id="g_123"):
    print(contact["phone_number"])
```

WhatsApp et la voix ne sont pas encore servis par l'API v2.

## Rejeux sans double envoi

Chaque écriture porte une clé `Idempotency-Key` générée. Le SDK rejoue seul, avec la même clé et deux fois au plus, une coupure réseau, un `5xx` (sauf `501`) et un `429` qui annonce `Retry-After`.

Passez votre propre clé pour survivre à un redémarrage de votre programme :

```python
fm.sms.send(params, idempotency_key="commande-42-confirmation")
```

## Erreurs

```python
from fastermessage import ApiConnectionError, ApiError, InsufficientBalanceError

try:
    fm.sms.send(params)
except InsufficientBalanceError:
    ...  # Rechargez le compte débité.
except ApiError as error:
    # Testez code, stable, et non le message.
    print(error.status, error.code, error.param, error.request_id)
except ApiConnectionError as error:
    ...  # L'appel a pu aboutir : rejouez avec error.idempotency_key, jamais avec une nouvelle clé.
```

Erreurs : `InvalidRequestError` (400), `AuthenticationError` (401), `InsufficientBalanceError` (402), `PermissionDeniedError` (403), `NotFoundError` (404), `ConflictError` (409), `RateLimitError` (429), `NotServedError` (501), `ServerError` (5xx).

Dans un lot, lisez toujours `errors` : un retour normal ne garantit pas que toutes les lignes soient parties.

## Webhooks

Vérifiez la signature sur le corps **brut**, avant tout décodage JSON. Avec Flask :

```python
import json
import os
from flask import Flask, request
from fastermessage import webhook

app = Flask(__name__)

@app.post("/webhooks/fastermessage")
def fastermessage_webhook():
    body = request.get_data()
    if not webhook.is_genuine(body, request.headers.get("X-Fastermessage-Signature"), os.environ["FM_WEBHOOK_SECRET"]):
        return "", 401

    event = json.loads(body)
    return "", 200  # Répondez sous 10 secondes : confiez le traitement à une tâche de fond.
```

Générez le secret dans « Intégration & API ». Le rappel SMS a le format `uuid`, `level`, `status` ; le rappel e-mail `id`, `status`, `error`.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Licence

MIT.

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

Sur le domaine d'API de votre marque : `FasterMessage(user, password, key, base_url="https://api.votre-marque.com")`. L'adresse doit être en `https` : `http` n'est accepté que vers la machine locale.

## Ce que fait le SDK

| Besoin | Appel |
|---|---|
| SMS | `fm.sms.send()`, `fm.sms.send_batch()` (500 lignes) |
| E-mail | `fm.email.send()` |
| WhatsApp | `fm.whatsapp.send()` |
| Ce que vous pouvez utiliser (WhatsApp) | `fm.whatsapp.list_numbers()`, `list_templates()`, `all_numbers()`, `all_templates()` |
| Ce que vous pouvez utiliser (e-mail) | `fm.email.list_senders()`, `list_templates()`, `all_senders()`, `all_templates()` |
| Canal en paramètre | `fm.messages.send()` |
| Suivi | `fm.messages.get()`, `list()`, `all()` |
| OTP | `fm.otp.request()` (SMS ou WhatsApp), `fm.otp.verify()` |
| Contacts | `fm.contacts`, `fm.contact_groups` : `create`, `get`, `list`, `all`, `update`, `delete` |
| Compte | `fm.account.balance()`, `credits()`, `all_credits()` |
| Repli | `fallback` sur `send()` et `fm.otp.request()` |
| Webhooks | `webhook.is_genuine()` |

Les réponses sont des dictionnaires, aux noms de champs de l'API : un champ ajouté par l'API est disponible sans mise à jour du SDK. La référence complète est dans la [documentation de l'API](https://www.fastermessage.com/docs).

`all()` parcourt toutes les pages et ne demande la suivante que si vous continuez :

```python
for contact in fm.contacts.all(group_id="g_123"):
    print(contact["phone_number"])
```

## Ce que vous pouvez utiliser

Ces lectures ne rendent que ce qui est validé et utilisable sur votre compte, exactement ce que l'envoi accepte : un élément listé ne sera pas refusé à l'envoi.

```python
for number in fm.whatsapp.all_numbers():
    print(number["number"])                      # à mettre dans `from`
for template in fm.whatsapp.all_templates():
    print(template["name"], template["language"], ",".join(template["variables"]))  # 1,2,header…
for sender in fm.email.all_senders():
    print(sender["address"])                     # à mettre dans `from` d'un e-mail
page = fm.email.list_templates(limit=20)         # modèles publiés : subject, html, from_email…
```

Un modèle WhatsApp de catégorie `authentication` sert `fm.otp.request()`, pas `send()`.

## WhatsApp

`from` est le numéro WhatsApp raccordé à votre compte : il est obligatoire. Deux contenus, selon la règle de Meta :

```python
# Un modèle approuvé, à tout moment. Variables : "1", "2"… pour {{1}}, {{2}}… du corps.
fm.whatsapp.send({
    "to": "+2290160000000",
    "from": "+2290161000000",
    "content": {"template": "confirmation_commande", "language": "fr", "variables": {"1": "Awa", "2": "1187"}},
})

# Un texte libre, seulement si le destinataire vous a écrit dans les 24 h (sinon 409 session_window_closed).
fm.whatsapp.send({"to": "+2290160000000", "from": "+2290161000000", "content": {"text": "Votre commande est prête."}})
```

Un message lu reste `delivered` ; sa lecture se lit dans `read_at`. L'envoi programmé, le lot et les en-têtes média ne sont pas encore ouverts sur WhatsApp. La voix n'est pas encore servie par l'API v2.

## Repli entre canaux

`fallback` est une liste ordonnée d'étapes `channel`, `to`, `from`, `content`, essayées dans l'ordre si le message principal échoue. `channel` vaut `sms`, `email` ou `whatsapp` (la voix est acceptée mais répond « non disponible »). Vers l'e-mail, `content` est facultatif (sauf après un modèle WhatsApp) ; vers le SMS, il est obligatoire ; vers WhatsApp, c'est un modèle (`template`, `language`, `variables`) ou un texte (`text`), qui ne part que si la fenêtre de 24 h est ouverte. Accepté par `fm.sms.send()`, `fm.email.send()`, `fm.whatsapp.send()`, `fm.messages.send()` et `fm.otp.request()`, refusé par `fm.sms.send_batch()`.

```python
message = fm.sms.send({
    "to": "+2290160000000",
    "from": "FASTERMSG",
    "content": "Votre commande est prete.",
    "fallback": [
        {"channel": "email", "to": "client@exemple.com", "from": "no-reply@votre-marque.com", "content": {"subject": "Votre commande"}},
    ],
})

print((message["fallback"] or {}).get("state"))  # watching
```

La réponse porte `fallback` (`None` sans repli) : `will_run`, `state` (`blocked`, `watching`, `triggered`, `not_needed`, `failed`, `expired`) et `steps`, une entrée par étape (`channel`, `will_run`, `reason`, `message_id`), avec son `reason` quand elle ne partira pas (`insufficient_balance`, `sender_not_allowed`…). Le message de repli porte `fallback_of`, l'identifiant du message d'origine.

Pour un OTP, un `content` propre doit contenir `{code}`, et `callback_url` reçoit le rappel de repli :

```python
otp = fm.otp.request({
    "to": "+2290160000000",
    "fallback": [
        {"channel": "email", "to": "client@exemple.com", "from": "no-reply@votre-marque.com", "content": {"text": "Votre code : {code}"}},
    ],
    "callback_url": "https://votre-site.com/webhooks/fastermessage",
})
```

Le code peut aussi partir par WhatsApp, par votre modèle d'authentification approuvé (`template` facultatif s'il est unique), `from` étant alors le numéro WhatsApp :

```python
otp = fm.otp.request({"to": "+2290160000000", "channel": "whatsapp", "from": "+2290161000000"})
```

Avec une clé `fm_test_`, `"test_outcome": "failed"` (ou `"delivered"`) simule l'issue du message principal pour voir le repli partir ; avec une clé réelle, c'est un `400`.

## Rejeux sans double envoi

Chaque écriture porte une clé `Idempotency-Key` générée. Le SDK rejoue seul, avec la même clé et deux fois au plus, une coupure réseau, un `5xx` (sauf `501`) et un `429` qui annonce `Retry-After` (60 secondes au plus : au-delà, il lève `RateLimitError` avec `retry_after`).

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
    if event.get("event") == "fallback":
        if event["fallback"]["state"] == "triggered":
            ...  # Le repli est parti : event["fallback"]["steps"][…]["message_id"] donne les messages envoyés.
        elif event["fallback"]["state"] == "failed":
            ...  # Aucune étape n'a pu partir : event["fallback"]["steps"][…]["reason"] dit pourquoi.
    return "", 200  # Répondez sous 10 secondes : confiez le traitement à une tâche de fond.
```

Générez le secret dans « Intégration & API ». Le rappel SMS a le format `uuid`, `level`, `status` ; le rappel e-mail `id`, `status`, `error`.

Le rappel de repli se reconnaît à `event` qui vaut `fallback` : `id` (le message principal, ou la demande OTP si `kind` vaut `otp`), `kind`, `channel`, `client_reference`, `fallback` et `event_at`. Il part quand le repli part (`state` `triggered`) ou ne peut pas partir (`state` `failed`), en POST, signé comme les autres, vers le `callback_url` de la demande, sinon vers l'adresse du compte. Jamais avec une clé de test, et rien pour un compte aux événements vidés.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Licence

MIT.

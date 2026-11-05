import base64
import hashlib
import hmac
import http.server
import json
import threading
import unittest

import fastermessage
from fastermessage import (
    ApiConnectionError,
    ApiError,
    AuthenticationError,
    ConflictError,
    FasterMessage,
    InsufficientBalanceError,
    InvalidRequestError,
    NotFoundError,
    NotServedError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    webhook,
)
from fastermessage._http import Response

BASE = "https://api.fastermessage.com"


def ok(status, body=None, headers=None):
    return Response(status, headers or {}, "" if body is None else json.dumps(body))


def refus(status, code, extra=None, headers=None):
    error = {"type": "invalid_request", "code": code, "message": f"refus {code}"}
    error.update(extra or {})
    return Response(status, headers or {}, json.dumps({"error": error}))


class Banc:
    """Un faux transport qui rejoue ses réponses dans l'ordre et note chaque appel."""

    def __init__(self, reponses, **options):
        self.reponses = list(reponses)
        self.calls = []
        self.sleeps = []
        self.fm = FasterMessage(
            "alice", "motdepasse", "fm_test_abc", transport=self._transport, sleep=self.sleeps.append, **options
        )

    def _transport(self, method, url, headers, body, timeout):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "json": json.loads(body) if body else None, "timeout": timeout}
        )
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


SMS = {"to": "1", "from": "F", "content": "c"}


class Construction(unittest.TestCase):
    def test_refuse_un_identifiant_absent(self):
        for args in (("", "b", "c"), ("a", "", "c"), ("a", "b", "")):
            with self.assertRaises(ValueError):
                FasterMessage(*args)

    def test_reconnait_le_mode_test(self):
        self.assertTrue(FasterMessage("a", "b", "fm_test_x").test_mode)
        self.assertFalse(FasterMessage("a", "b", "fm_live_x").test_mode)

    def test_n_ecrit_aucun_identifiant(self):
        fm = FasterMessage("alice", "motdepasse", "fm_live_secret")
        for texte in (repr(fm), str(fm), repr(fm.sms), repr(fm.sms._http)):
            self.assertNotRegex(texte, "alice|motdepasse|fm_live_secret|YWxpY2U")


class EnTetesEtChemins(unittest.TestCase):
    def test_authentification_cle_et_corps(self):
        banc = Banc([ok(201, {"id": "m1", "status": "queued"})])
        message = banc.fm.sms.send({"to": "+2290160000000", "from": "FASTERMSG", "content": "é"})
        self.assertEqual(message["status"], "queued")
        call = banc.calls[0]
        self.assertEqual(call["url"], f"{BASE}/v2/sms/send")
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["headers"]["Authorization"], "Basic " + base64.b64encode(b"alice:motdepasse").decode())
        self.assertEqual(call["headers"]["X-Api-Key"], "fm_test_abc")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertRegex(call["headers"]["User-Agent"], r"^fastermessage-python/\d")
        self.assertEqual(call["json"]["content"], "é")

    def test_domaine_de_marque_sans_double_barre_et_delai(self):
        banc = Banc([ok(200, {"balances": []})], base_url="https://api.marque.test/", timeout=7.5)
        banc.fm.account.balance()
        self.assertEqual(banc.calls[0]["url"], "https://api.marque.test/v2/balance")
        self.assertEqual(banc.calls[0]["timeout"], 7.5)

    def test_encode_l_identifiant_et_ignore_les_filtres_vides(self):
        banc = Banc([ok(200, {"id": "x"}), ok(200, {"data": [], "has_more": False, "next_cursor": None})])
        banc.fm.messages.get("a/b c")
        banc.fm.messages.list(channel="email", status=None, limit=5)
        self.assertEqual(banc.calls[0]["url"], f"{BASE}/v2/messages/a%2Fb%20c")
        self.assertEqual(banc.calls[1]["url"], f"{BASE}/v2/messages?channel=email&limit=5")
        self.assertNotIn("Idempotency-Key", banc.calls[1]["headers"])

    def test_transmet_x_request_id(self):
        banc = Banc([ok(201, {})])
        banc.fm.email.send({"to": "a@b.test", "content": {"subject": "s", "text": "t"}}, request_id="r-1")
        self.assertEqual(banc.calls[0]["url"], f"{BASE}/v2/email/send")
        self.assertEqual(banc.calls[0]["headers"]["X-Request-Id"], "r-1")

    def test_routes_des_autres_ressources(self):
        banc = Banc([ok(200, {"id": "i"}) for _ in range(9)])
        banc.fm.sms.send_batch({"from": "F", "content": "c", "messages": [{"to": "1"}]})
        banc.fm.messages.send({"channel": "sms", "to": "1", "content": "c"})
        banc.fm.contacts.create({"group_id": "g", "phone_number": "1"})
        banc.fm.contacts.create_batch({"group_id": "g", "contacts": [{"phone_number": "1"}]})
        banc.fm.contacts.update("c1", {"consent": "out"})
        banc.fm.contact_groups.create({"name": "n"})
        banc.fm.contact_groups.update("g1", {"name": "m"})
        banc.fm.contact_groups.get("g1")
        banc.fm.account.credits(limit=3)
        self.assertEqual(
            [f"{c['method']} {c['url'].replace(BASE, '')}" for c in banc.calls],
            [
                "POST /v2/sms/batch",
                "POST /v2/messages",
                "POST /v2/contacts",
                "POST /v2/contacts/batch",
                "PATCH /v2/contacts/c1",
                "POST /v2/contact-groups",
                "PATCH /v2/contact-groups/g1",
                "GET /v2/contact-groups/g1",
                "GET /v2/credits?limit=3",
            ],
        )


class OtpTests(unittest.TestCase):
    def test_sms_par_defaut_sans_ecraser_un_canal_choisi(self):
        banc = Banc([ok(201, {}), ok(201, {})])
        banc.fm.otp.request({"to": "1", "from": "F"})
        banc.fm.otp.request({"to": "1", "channel": "email"})
        self.assertEqual(banc.calls[0]["url"], f"{BASE}/v2/otp")
        self.assertEqual(banc.calls[0]["json"]["channel"], "sms")
        self.assertEqual(banc.calls[1]["json"]["channel"], "email")

    def test_verifie_avec_identifiant_et_code(self):
        banc = Banc([ok(200, {"status": "approved"})])
        self.assertEqual(banc.fm.otp.verify("o1", "000000")["status"], "approved")
        self.assertEqual(banc.calls[0]["url"], f"{BASE}/v2/otp/verify")
        self.assertEqual(banc.calls[0]["json"], {"id": "o1", "code": "000000"})


class IdempotenceEtReprises(unittest.TestCase):
    def test_une_cle_par_ecriture(self):
        banc = Banc([ok(201, {}), ok(201, {})])
        banc.fm.sms.send(SMS)
        banc.fm.sms.send(SMS)
        premiere = banc.calls[0]["headers"]["Idempotency-Key"]
        self.assertRegex(premiere, r"^sdk-[0-9a-f]{32}$")
        self.assertNotEqual(premiere, banc.calls[1]["headers"]["Idempotency-Key"])

    def test_respecte_la_cle_fournie(self):
        banc = Banc([ok(201, {})])
        banc.fm.sms.send(SMS, idempotency_key="cmd-42")
        self.assertEqual(banc.calls[0]["headers"]["Idempotency-Key"], "cmd-42")

    def test_rejoue_un_5xx_avec_la_meme_cle(self):
        banc = Banc([refus(500, "a"), refus(503, "b"), ok(201, {"id": "m"})])
        self.assertEqual(banc.fm.sms.send(SMS)["id"], "m")
        self.assertEqual(len(banc.calls), 3)
        self.assertEqual(banc.calls[0]["headers"]["Idempotency-Key"], banc.calls[2]["headers"]["Idempotency-Key"])
        self.assertEqual(len(banc.sleeps), 2)
        self.assertGreater(banc.sleeps[1], banc.sleeps[0])

    def test_s_arrete_apres_les_reprises_prevues(self):
        banc = Banc([refus(500, "a"), refus(500, "b"), refus(500, "c")])
        with self.assertRaises(ServerError):
            banc.fm.account.balance()
        self.assertEqual(len(banc.calls), 3)

    def test_zero_reprise(self):
        banc = Banc([refus(500, "a")], max_retries=0)
        with self.assertRaises(ServerError):
            banc.fm.account.balance()
        self.assertEqual(len(banc.calls), 1)

    def test_ne_rejoue_jamais_400_402_501(self):
        for status, code in ((400, "missing_parameter"), (402, "insufficient_balance"), (501, "not_implemented")):
            banc = Banc([refus(status, code)])
            with self.assertRaises(ApiError):
                banc.fm.sms.send(SMS)
            self.assertEqual(len(banc.calls), 1)

    def test_attend_retry_after(self):
        banc = Banc([refus(429, "rate_limited", headers={"retry-after": "7"}), ok(200, {"balances": []})])
        banc.fm.account.balance()
        self.assertEqual(len(banc.calls), 2)
        self.assertEqual(banc.sleeps, [7.0])

    def test_ne_rejoue_pas_un_429_sans_retry_after(self):
        banc = Banc([refus(429, "otp_rate_limited")])
        with self.assertRaises(RateLimitError) as ctx:
            banc.fm.otp.request({"to": "1"})
        self.assertIsNone(ctx.exception.retry_after)
        self.assertEqual(len(banc.calls), 1)

    def test_rejoue_une_cle_en_cours(self):
        banc = Banc([refus(409, "idempotency_key_in_flight"), ok(201, {"id": "m"})])
        banc.fm.sms.send(SMS)
        self.assertEqual(len(banc.calls), 2)

    def test_coupure_reseau_rejouee_puis_cle_donnee(self):
        banc = Banc([ApiConnectionError("coupure"), ApiConnectionError("coupure"), ApiConnectionError("coupure")])
        with self.assertRaises(ApiConnectionError) as ctx:
            banc.fm.sms.send(SMS)
        self.assertEqual(len(banc.calls), 3)
        self.assertEqual(ctx.exception.idempotency_key, banc.calls[0]["headers"]["Idempotency-Key"])


class Erreurs(unittest.TestCase):
    def test_classe_par_statut(self):
        table = {
            400: InvalidRequestError,
            401: AuthenticationError,
            402: InsufficientBalanceError,
            403: PermissionDeniedError,
            404: NotFoundError,
            409: ConflictError,
            429: RateLimitError,
            501: NotServedError,
            503: ServerError,
        }
        for status, classe in table.items():
            banc = Banc([refus(status, "code_stable")], max_retries=0)
            with self.assertRaises(classe) as ctx:
                banc.fm.account.balance()
            self.assertIsInstance(ctx.exception, ApiError)
            self.assertEqual(ctx.exception.status, status)
            self.assertEqual(ctx.exception.code, "code_stable")

    def test_garde_les_details(self):
        banc = Banc([refus(400, "missing_parameter", {"param": "from", "request_id": "r-9"})])
        with self.assertRaises(InvalidRequestError) as ctx:
            banc.fm.sms.send({"to": "1", "content": "c"})
        erreur = ctx.exception
        self.assertEqual((erreur.param, erreur.request_id, erreur.type), ("from", "r-9", "invalid_request"))
        self.assertEqual(str(erreur), "refus missing_parameter")

    def test_identifiant_de_requete_dans_l_en_tete(self):
        banc = Banc([refus(404, "not_found", headers={"x-request-id": "r-h"})])
        with self.assertRaises(NotFoundError) as ctx:
            banc.fm.messages.get("x")
        self.assertEqual(ctx.exception.request_id, "r-h")

    def test_corps_d_erreur_qui_n_est_pas_du_json(self):
        banc = Banc([Response(400, {}, "<html>Bad gateway</html>")])
        with self.assertRaises(InvalidRequestError) as ctx:
            banc.fm.account.balance()
        self.assertEqual(ctx.exception.code, "http_400")
        self.assertEqual(ctx.exception.message, "Erreur HTTP 400.")

    def test_autre_4xx_et_redirection(self):
        for status in (422, 302):
            banc = Banc([refus(status, "autre")])
            with self.assertRaises(ApiError) as ctx:
                banc.fm.account.balance()
            self.assertIs(type(ctx.exception), ApiError)

    def test_reponse_reussie_illisible(self):
        banc = Banc([Response(200, {}, "pas du json")])
        with self.assertRaises(ServerError) as ctx:
            banc.fm.account.balance()
        self.assertEqual(ctx.exception.code, "invalid_response")


class ReponsesEtPagination(unittest.TestCase):
    def test_204(self):
        banc = Banc([Response(204, {}, ""), Response(204, {}, "")])
        self.assertIsNone(banc.fm.contacts.delete("c/1"))
        self.assertIsNone(banc.fm.contact_groups.delete("g1"))
        self.assertEqual(banc.calls[0]["method"], "DELETE")
        self.assertEqual(banc.calls[0]["url"], f"{BASE}/v2/contacts/c%2F1")
        self.assertIn("Idempotency-Key", banc.calls[0]["headers"])

    def test_soldes(self):
        soldes = [{"channel": "sms", "amount": 3, "currency": "XOF"}]
        self.assertEqual(Banc([ok(200, {"balances": soldes})]).fm.account.balance(), soldes)

    def test_all_parcourt_les_pages(self):
        banc = Banc(
            [
                ok(200, {"data": [{"id": 1}, {"id": 2}], "has_more": True, "next_cursor": "c2"}),
                ok(200, {"data": [{"id": 3}], "has_more": False, "next_cursor": None}),
            ]
        )
        self.assertEqual([c["id"] for c in banc.fm.contacts.all(group_id="g", limit=2)], [1, 2, 3])
        self.assertEqual(banc.calls[0]["url"], f"{BASE}/v2/contacts?group_id=g&limit=2")
        self.assertEqual(banc.calls[1]["url"], f"{BASE}/v2/contacts?group_id=g&limit=2&cursor=c2")

    def test_all_n_appelle_rien_avant_le_premier_element(self):
        banc = Banc([ok(200, {"data": [{"id": 1}, {"id": 2}], "has_more": True, "next_cursor": "c2"})])
        parcours = banc.fm.messages.all()
        self.assertEqual(len(banc.calls), 0)
        self.assertEqual(next(parcours)["id"], 1)
        self.assertEqual(len(banc.calls), 1)

    def test_all_s_arrete_sans_curseur(self):
        banc = Banc([ok(200, {"data": [{"id": 1}], "has_more": True, "next_cursor": None})])
        self.assertEqual(len(list(banc.fm.contact_groups.all())), 1)
        self.assertEqual(len(banc.calls), 1)

    def test_all_credits(self):
        banc = Banc([ok(200, {"data": [{"id": "m"}], "has_more": False, "next_cursor": None})])
        self.assertEqual([m["id"] for m in banc.fm.account.all_credits(type="debit")], ["m"])
        self.assertEqual(banc.calls[0]["url"], f"{BASE}/v2/credits?type=debit")


class Webhooks(unittest.TestCase):
    corps = '{"id":"m1","status":"delivered"}'

    def signe(self, texte, secret="whsec"):
        return "sha256=" + hmac.new(secret.encode(), texte.encode(), hashlib.sha256).hexdigest()

    def test_accepte_une_signature_juste(self):
        self.assertTrue(webhook.is_genuine(self.corps, self.signe(self.corps), "whsec"))
        self.assertTrue(webhook.is_genuine(self.corps.encode(), f" {self.signe(self.corps)} ", "whsec"))

    def test_refuse_le_reste(self):
        self.assertFalse(webhook.is_genuine(self.corps + " ", self.signe(self.corps), "whsec"))
        self.assertFalse(webhook.is_genuine(self.corps, self.signe(self.corps, "autre"), "whsec"))
        self.assertFalse(webhook.is_genuine(self.corps, None, "whsec"))
        self.assertFalse(webhook.is_genuine(self.corps, self.signe(self.corps), ""))

    def test_mauvaise_longueur_sans_planter(self):
        self.assertFalse(webhook.is_genuine(self.corps, "sha256=court", "whsec"))
        self.assertFalse(webhook.is_genuine(self.corps, "é" * 71, "whsec"))


class TransportReel(unittest.TestCase):
    """Le transport par défaut, contre un petit serveur local."""

    def setUp(self):
        test = self
        test.recu = []

        class Serveur(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                test.recu.append(self.path)
                if self.path == "/v2/balance":
                    self._repondre(200, {"balances": []})
                elif self.path == "/v2/messages/redir":
                    self.send_response(302)
                    self.send_header("Location", "/v2/balance")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self._repondre(404, {"error": {"code": "not_found", "message": "absent"}})

            def _repondre(self, status, corps):
                donnees = json.dumps(corps).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Request-Id", "r-local")
                self.send_header("Content-Length", str(len(donnees)))
                self.end_headers()
                self.wfile.write(donnees)

            def log_message(self, *args):
                pass

        self.serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Serveur)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.serveur.server_port}"
        self.fm = FasterMessage("a", "b", "c", base_url=self.base, max_retries=0)

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()

    def test_reussite_et_refus(self):
        self.assertEqual(self.fm.account.balance(), [])
        with self.assertRaises(NotFoundError) as ctx:
            self.fm.messages.get("absent")
        self.assertEqual(ctx.exception.request_id, "r-local")

    def test_ne_suit_pas_une_redirection(self):
        with self.assertRaises(ApiError) as ctx:
            self.fm.messages.get("redir")
        self.assertEqual(ctx.exception.status, 302)
        self.assertEqual(self.recu, ["/v2/messages/redir"])

    def test_serveur_injoignable(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        fm = FasterMessage("a", "b", "c", base_url=self.base, max_retries=0, timeout=2)
        with self.assertRaises(ApiConnectionError) as ctx:
            fm.sms.send(SMS)
        self.assertRegex(ctx.exception.idempotency_key, "^sdk-")


class Version(unittest.TestCase):
    def test_version_alignee_sur_le_paquet(self):
        import os
        import re

        chemin = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(chemin, encoding="utf-8") as fichier:
            attendu = re.search(r'^version = "(.+)"', fichier.read(), re.M).group(1)
        self.assertEqual(fastermessage.__version__, attendu)


if __name__ == "__main__":
    unittest.main()

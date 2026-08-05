# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The served service worker, EXECUTED.

Everything in `PUSH_HANDLERS` is a Python string until a phone runs it, and a
Python suite can only assert that substrings are present. That is a real gap,
not a theoretical one: an adversarial mutation run deleted the entire
base64url re-encoding of the VAPID key -- the one thing that keeps push alive
after the push service rotates an endpoint -- and every test stayed green,
because none of them ran a single line of JavaScript.

These tests fetch the worker from its own route and run it inside a
`ServiceWorkerGlobalScope` emulator (`service_worker_harness.js`), driving the
`push`, `notificationclick` and `pushsubscriptionchange` handlers against
stubs that model the parts of the browser contract the worker relies on. The
assertions all live here; the harness only observes and reports.

Why `node` and not a Python JS interpreter: the worker uses `URL`, `btoa`,
async/await and spec-shaped `Promise` semantics. `node` is present in the
image the CI functional-tests job runs Odoo in (Doodba 19.0, node 18), while
`js2py`, `dukpy`, `quickjs` and `pythonmonkey` are all absent from it -- and
the ones that could be added parse ES5, which this worker is not. A missing
`node` FAILS these tests loudly rather than skipping them: a harness that
quietly opts out is the gap it was written to close.
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile

from odoo.tests import HttpCase, tagged

from odoo.addons.website_pwa_push.controllers.main import WebsitePWAPush

HARNESS = os.path.join(os.path.dirname(__file__), "service_worker_harness.js")

# The origin the harness installs the worker on. Every same-origin decision is
# judged against this, so it has to agree with the constant in the harness.
ORIGIN = "https://microsite.example"

# 65 bytes: exactly the shape of a VAPID public key, an uncompressed P-256
# point (0x04 || X || Y). Deterministic, and picked so its standard base64
# contains BOTH "+" and "/" AND needs padding -- so this single value exercises
# all three substitutions the re-encoding performs.
VAPID_KEY_BYTES = [(i * 37 + 11) % 256 for i in range(65)]
VAPID_KEY_B64URL = (
    base64.urlsafe_b64encode(bytes(VAPID_KEY_BYTES)).rstrip(b"=").decode()
)

OLD_ENDPOINT = "https://push.example/old"
CHANNEL_SUB = {"model": "discuss.channel", "res_id": 7}

# Each one passes `startsWith("/") && !startsWith("//")` and is then read by
# the URL parser as `https://evil.com/`: backslashes are path separators for a
# special scheme, and tabs are stripped before parsing.
REDIRECT_VECTORS = {
    "backslash": "/\\evil.com",
    "backslash_slash": "/\\/evil.com",
    "tab_slash": "/\t/evil.com",
    "protocol_relative": "//evil.com",
    "javascript": "javascript:alert(1)",
    "absolute": "https://evil.com/x",
}


def _run_worker(source, cases):
    """Execute `source` in the emulator and return the per-case observations."""
    if not shutil.which("node"):
        raise RuntimeError(
            "website_pwa_push: `node` is required to execute the service "
            "worker under test and was not found on PATH. It ships with the "
            "Doodba image the CI functional-tests job runs in; install "
            "nodejs to run this suite locally. These tests must not be "
            "skipped -- an unexecuted worker is exactly the gap they close."
        )
    with tempfile.TemporaryDirectory() as tmp:
        worker_path = os.path.join(tmp, "service-worker.js")
        input_path = os.path.join(tmp, "input.json")
        with open(worker_path, "w", encoding="utf-8") as handle:
            handle.write(source)
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump({"keyBytes": VAPID_KEY_BYTES, "cases": cases}, handle)
        proc = subprocess.run(
            ["node", HARNESS, worker_path, input_path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        # The harness crashed before it could report anything -- most likely a
        # SyntaxError in the served worker, which on a real phone aborts the
        # whole install and takes website_pwa's offline cache with it. Say so
        # with node's own output rather than a KeyError three lines down.
        raise AssertionError(
            "the emulator produced no result for the served worker "
            "(exit %s)\nstdout: %s\nstderr: %s"
            % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
        ) from None
    if "harnessError" in result:
        raise AssertionError(
            "the served service worker failed to run:\n%s" % result["harnessError"]
        )
    return result["cases"]


@tagged("post_install", "-at_install")
class TestServiceWorkerJS(HttpCase):
    """Behaviour of the worker as the browser sees it, not as a substring."""

    #: Filled by the first ``setUp``; see why it cannot be done in setUpClass.
    cases = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.website.write({"pwa_enabled": True, "pwa_push_enabled": True})

    def setUp(self):
        super().setUp()
        # The worker is fetched here and NOT in setUpClass: in Odoo 19
        # ``url_open`` is an instance method that reads ``self.opener``, which
        # ``setUp`` is what creates. Calling it one level up raises TypeError
        # before a single test can start -- and a class that cannot start is a
        # suite that reports nothing while looking installed.
        if type(self).cases is None:
            res = self.url_open("/service-worker.js")
            self.assertEqual(res.status_code, 200)
            worker_source = res.content.decode()
            # One `node` run for the whole class: every case gets a brand new
            # realm and a brand new evaluation of the worker inside it, so they
            # cannot leak state into each other.
            type(self).worker_source = worker_source
            type(self).cases = _run_worker(worker_source, self._cases())

    @classmethod
    def _cases(cls):
        cases = [
            {"name": "vapid", "base64urlOf": VAPID_KEY_BYTES},
            # A payload that is readable but whose `options` the browser
            # refuses. Both of these reject `showNotification`.
            {
                "name": "renotify_without_tag",
                "event": "push",
                "payload": {"title": "Hola", "options": {"renotify": True}},
            },
            {
                "name": "actions_not_a_sequence",
                "event": "push",
                "payload": {"title": "Hola", "options": {"actions": "x"}},
            },
            # A payload that is not readable at all.
            {"name": "unreadable", "event": "push", "payloadInvalid": True},
            {"name": "no_payload", "event": "push", "noData": True},
            # A tag the payload supplied for a payload that names no record.
            {
                "name": "payload_tag",
                "event": "push",
                "payload": {"options": {"tag": "attacker", "body": "b"}},
            },
            {
                "name": "channel_tag",
                "event": "push",
                "payload": {"title": "m", "options": {"data": CHANNEL_SUB}},
            },
            # A cross-origin URL must not even choose the PATH we navigate to.
            {
                "name": "foreign_url",
                "event": "notificationclick",
                "notificationData": dict(CHANNEL_SUB, url="https://evil.com/steal?x=1"),
            },
            {
                "name": "res_id_traversal",
                "event": "notificationclick",
                "notificationData": {
                    "model": "discuss.channel",
                    "res_id": "1/../../odoo/settings",
                },
            },
            {
                "name": "same_origin_url",
                "event": "notificationclick",
                "notificationData": {"url": "/discuss/channel/7?a=1#z"},
            },
            {
                "name": "channel_click",
                "event": "notificationclick",
                "notificationData": CHANNEL_SUB,
            },
            {
                "name": "uncontrolled_tab",
                "event": "notificationclick",
                "notificationData": CHANNEL_SUB,
                "windowClients": [ORIGIN + "/discuss/channel/7"],
            },
            # Chrome's shape: `oldSubscription`, expects a re-subscribe.
            {
                "name": "renewal_ok",
                "event": "subscriptionchange",
                "subscriptions": {"oldSubscription": {"endpoint": OLD_ENDPOINT}},
                "fetchResponse": {"ok": True, "status": 200, "json": {"result": {}}},
            },
            # No `dgid` cookie: the public route answers 404.
            {
                "name": "renewal_404",
                "event": "subscriptionchange",
                "subscriptions": {"oldSubscription": {"endpoint": OLD_ENDPOINT}},
                "fetchResponse": {"ok": False, "status": 404, "json": {}},
            },
            # JSON-RPC failure: HTTP 200 with an `error` member.
            {
                "name": "renewal_jsonrpc_error",
                "event": "subscriptionchange",
                "subscriptions": {"oldSubscription": {"endpoint": OLD_ENDPOINT}},
                "fetchResponse": {
                    "ok": True,
                    "status": 200,
                    "json": {"error": {"message": "no guest"}},
                },
            },
            {
                "name": "renewal_offline",
                "event": "subscriptionchange",
                "subscriptions": {"oldSubscription": {"endpoint": OLD_ENDPOINT}},
                "fetchResponse": {"networkError": True},
            },
            # Firefox's shape: no `oldSubscription`.
            {
                "name": "renewal_firefox",
                "event": "subscriptionchange",
                "subscriptions": {
                    "newSubscription": {"endpoint": "https://push.example/ff"}
                },
                "fetchResponse": {"ok": True, "status": 200, "json": {"result": {}}},
            },
            {
                "name": "renewal_nothing",
                "event": "subscriptionchange",
                "subscriptions": {},
            },
        ]
        cases += [
            {
                "name": "redirect_" + name,
                "event": "notificationclick",
                "notificationData": {"url": url},
            }
            for name, url in REDIRECT_VECTORS.items()
        ]
        return cases

    def _opened(self, case):
        return self.cases[case]["openWindow"]

    # ------------------------------------------------------------------
    # The VAPID key: what keeps push alive after an endpoint rotation
    # ------------------------------------------------------------------

    def test_the_vapid_key_is_re_encoded_as_unpadded_base64url(self):
        """Sin este re-encoding la renovación se rechaza y el push muere.

        `applicationServerKey` vuelve a leerse como ArrayBuffer aunque se
        suscribiera con una cadena, y `/mail/push/subscribe` compara la clave
        devuelta con el parámetro guardado. Base64 estándar no vale: `+`, `/` y
        el relleno `=` la hacen inválida como clave VAPID. Tres mutaciones
        distintas borraban justo esa parte y ningún test se enteraba, porque
        ninguno ejecutaba JavaScript.
        """
        self.assertEqual(self.cases["vapid"]["base64url"], VAPID_KEY_B64URL)
        self.assertNotIn("=", self.cases["vapid"]["base64url"])
        self.assertNotIn("+", self.cases["vapid"]["base64url"])
        self.assertNotIn("/", self.cases["vapid"]["base64url"])

    def test_the_renewal_echoes_the_key_the_route_compares(self):
        """La clave que viaja en el POST es la re-codificada, no otra."""
        sent = self.cases["renewal_ok"]["fetch"][0]["body"]["params"]
        self.assertEqual(sent["vapid_public_key"], VAPID_KEY_B64URL)
        self.assertEqual(sent["previous_endpoint"], OLD_ENDPOINT)

    # ------------------------------------------------------------------
    # userVisibleOnly: SIEMPRE se pinta algo
    # ------------------------------------------------------------------

    def test_a_hostile_options_payload_still_shows_a_notification(self):
        """Un `showNotification` rechazado dentro de `waitUntil` no pinta NADA.

        Y eso es justo la promesa que rompe `userVisibleOnly`: Chrome enseña su
        propio aviso de "esta web se ha actualizado en segundo plano" y, si se
        repite, retira el permiso a todo el origen. `options` viene del payload,
        así que puede ser perfectamente legible y aun así inválido: `renotify`
        sin `tag`, o `actions` que no es una secuencia. El respaldo del título
        genérico solo cubría el payload ILEGIBLE.
        """
        for case in ("renotify_without_tag", "actions_not_a_sequence"):
            with self.subTest(case=case):
                observed = self.cases[case]
                self.assertEqual(
                    len(observed["attempts"]),
                    2,
                    "el primer intento tiene que fallar y provocar el respaldo",
                )
                self.assertFalse(observed["attempts"][0]["ok"])
                self.assertEqual(
                    [shown["title"] for shown in observed["shown"]], ["Nuevo mensaje"]
                )

    def test_an_unreadable_payload_still_shows_a_notification(self):
        """El push sin cuerpo legible tampoco puede quedarse en silencio."""
        for case in ("unreadable", "no_payload"):
            with self.subTest(case=case):
                self.assertEqual(
                    [shown["title"] for shown in self.cases[case]["shown"]],
                    ["Nuevo mensaje"],
                )

    # ------------------------------------------------------------------
    # El clic no puede convertirse en un redirector
    # ------------------------------------------------------------------

    def test_the_open_redirect_vectors_are_refused(self):
        """`startsWith("/")` no es lo mismo que "mismo origen".

        Los tres primeros vectores pasaban el guardia anterior y el navegador
        los abría como `https://evil.com/`. Hoy el destino se RESUELVE y se
        comparan orígenes, que es lo único que sabe de verdad qué es un origen.
        """
        for name in REDIRECT_VECTORS:
            with self.subTest(vector=name):
                self.assertEqual(self._opened("redirect_" + name), [ORIGIN + "/"])

    def test_a_cross_origin_url_does_not_even_choose_our_path(self):
        """Ni el destino ajeno ni la ruta que elige: gana el registro."""
        self.assertEqual(self._opened("foreign_url"), [ORIGIN + "/discuss/channel/7"])

    def test_a_same_origin_url_is_honoured_with_its_query_and_fragment(self):
        """El caso legítimo tiene que seguir funcionando entero."""
        self.assertEqual(
            self._opened("same_origin_url"), [ORIGIN + "/discuss/channel/7?a=1#z"]
        )

    def test_a_non_numeric_res_id_cannot_walk_out_of_the_channel_path(self):
        """`res_id` se concatena a una ruta; sin coerción se sale de ella.

        `"1/../../odoo/settings"` daba `/discuss/odoo/settings`, o sea el
        backend, que es precisamente donde este módulo NO quiere mandar a un
        invitado.
        """
        self.assertEqual(self._opened("res_id_traversal"), [ORIGIN + "/"])
        self.assertEqual(self._opened("channel_click"), [ORIGIN + "/discuss/channel/7"])

    # ------------------------------------------------------------------
    # El tag
    # ------------------------------------------------------------------

    def test_messages_of_the_same_channel_share_one_tag(self):
        """Sin `tag` una ráfaga son veinte avisos y un visitante que se va."""
        shown = self.cases["channel_tag"]["shown"]
        self.assertEqual(shown[0]["options"]["tag"], "cc-push-discuss.channel-7")

    def test_a_payload_tag_does_not_survive_a_payload_naming_no_record(self):
        """ "Sin registro, sin tag" es un contrato, no una preferencia.

        Un `tag` puesto por el payload sobrevivía a la rama que devuelve cadena
        vacía, y avisos sin relación entre sí colapsaban en uno solo que nadie
        puede leer.
        """
        self.assertNotIn("tag", self.cases["payload_tag"]["shown"][0]["options"])

    # ------------------------------------------------------------------
    # Abrir o enfocar
    # ------------------------------------------------------------------

    def test_the_click_reuses_a_tab_this_worker_does_not_control(self):
        """`includeUncontrolled: true` o cada clic abre una copia de la página.

        La pestaña que el visitante está mirando se abrió normalmente ANTES de
        que este worker tomara el control, así que sin la bandera no aparece en
        `matchAll` y siempre se abre una segunda.
        """
        observed = self.cases["uncontrolled_tab"]
        self.assertEqual(
            observed["matchAll"], [{"type": "window", "includeUncontrolled": True}]
        )
        self.assertEqual(observed["focus"], [ORIGIN + "/discuss/channel/7"])
        self.assertFalse(observed["openWindow"])

    # ------------------------------------------------------------------
    # La renovación tras rotar el endpoint
    # ------------------------------------------------------------------

    def test_the_renewal_is_posted_to_the_public_route_with_the_session(self):
        """La identidad es la sesión: la cookie `dgid` o el usuario conectado.

        Sin `credentials: "same-origin"` la ruta no sabe a quién pertenece la
        suscripción y responde 404, y la renovación se pierde.
        """
        sent = self.cases["renewal_ok"]["fetch"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["url"], "/mail/push/subscribe")
        self.assertEqual(sent[0]["method"], "POST")
        self.assertEqual(sent[0]["credentials"], "same-origin")
        self.assertFalse(self.cases["renewal_ok"]["errors"])

    def test_a_refused_renewal_is_logged_instead_of_lost_in_silence(self):
        """Este evento salta SIN ninguna página abierta: nadie está mirando.

        Una respuesta que no se lee es una renovación que desaparece para
        siempre y un visitante que deja de recibir sin que nada lo explique.
        Los tres modos de fallo -- 404 de la ruta, `error` de JSON-RPC y caída
        de red -- tienen que dejar rastro.
        """
        for case in ("renewal_404", "renewal_jsonrpc_error", "renewal_offline"):
            with self.subTest(case=case):
                self.assertTrue(
                    self.cases[case]["errors"],
                    "un fallo de renovación no puede ser silencioso",
                )

    def test_the_renewal_survives_a_firefox_shaped_event(self):
        """Firefox dispara el evento con `oldSubscription` a null.

        Salir por ahí dejaba el manejador en no-op justo en el navegador que sí
        entrega la suscripción nueva en `newSubscription`.
        """
        sent = self.cases["renewal_firefox"]["fetch"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(
            sent[0]["body"]["params"]["endpoint"], "https://push.example/ff"
        )
        self.assertFalse(self.cases["renewal_firefox"]["errors"])

    def test_a_rotation_with_nothing_to_register_says_so(self):
        """Quedarse sin ninguna de las tres fuentes se registra, no se traga."""
        observed = self.cases["renewal_nothing"]
        self.assertFalse(observed["fetch"])
        self.assertTrue(observed["errors"])

    # ------------------------------------------------------------------
    # El hook de extensión no es una superficie de inyección
    # ------------------------------------------------------------------

    def test_an_overriding_module_cannot_inject_code_through_the_hook(self):
        """`_pwa_push_worker_values` está anunciado como punto de extensión.

        Interpolado en crudo dentro de un literal JS, un valor devuelto como
        ``/mi-chat/"; fetch(...); //`` cerraba la cadena y SE EJECUTABA al
        instalar el worker; uno con un salto de línea era un SyntaxError que
        abortaba la instalación entera y se llevaba por delante la caché
        offline de website_pwa. Aquí se ejecuta el worker resultante: si algo
        de esto siguiera pasando, no llegaría ni a arrancar.
        """
        hostile = '/mi-chat/"; globalThis.PWNED = true; //'
        multiline = "/salto\nde-linea"

        class _Overriding(WebsitePWAPush):
            def _pwa_push_worker_values(self, website):
                values = super()._pwa_push_worker_values(website)
                values["channel_path"] = hostile
                values["generic_title"] = multiline
                return values

        source = _Overriding()._pwa_service_worker_content(self.website)
        observed = _run_worker(source, [{"name": "hook"}])["hook"]
        # Llegan como DATOS, con su valor intacto: ni ejecutados ni rotos.
        self.assertEqual(observed["constants"]["channel"], hostile)
        self.assertEqual(observed["constants"]["generic"], multiline)

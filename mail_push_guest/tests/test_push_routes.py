# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import HttpCase, tagged
from odoo.tests.common import JsonRpcException
from odoo.tools import mute_logger

from odoo.addons.mail.models import mail_thread
from odoo.addons.mail_push_guest.models.mail_push_device import MAX_DEVICES_PER_PERSONA

from .common import (
    BROWSER_KEYS,
    FCM_ENDPOINT,
    JSONRPC_INVALID_VAPID,
    JSONRPC_VALIDATION_ERROR,
    MOZILLA_ENDPOINT,
    VAPID_PUBLIC_KEY_PARAM,
    MailPushGuestMixin,
)


@tagged("post_install", "-at_install")
class TestPushRoutes(MailPushGuestMixin, HttpCase):
    """Las rutas públicas: la única puerta que tiene un visitante.

    `register_devices` vive detrás de `/web/dataset/call_kw`, que es
    `auth="user"`, y `ir.http._authenticate` rechaza al usuario público en esas
    rutas. Por eso hay rutas nuevas, y por eso se prueban por HTTP de verdad
    (`requests.Session`) y no llamando al método: lo que se valida es lo que
    pasa por el hilo por donde entra un anónimo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()

    def _subscribe(self, guest=None, **params):
        payload = {
            "endpoint": FCM_ENDPOINT % "route-default",
            "keys": dict(BROWSER_KEYS),
            "vapid_public_key": self.vapid_public_key,
        }
        payload.update(params)
        return self.make_jsonrpc_request(
            "/mail/push/subscribe",
            payload,
            cookies=self._guest_cookies(guest) if guest else None,
        )

    def _device_of(self, endpoint):
        return self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])

    # ------------------------------------------------------------------
    # /mail/push/vapid
    # ------------------------------------------------------------------

    def test_vapid_route_returns_only_the_public_key(self):
        """Devuelve la clave pública y nada más.

        La privada nunca sale: es lo que firma el JWT que autoriza a este
        servidor ante el servicio de push.
        """
        self._forget_guest_cookie()
        result = self.make_jsonrpc_request("/mail/push/vapid", {})
        self.assertEqual(result, {"vapid_public_key": self.vapid_public_key})

    def test_vapid_route_does_not_wipe_devices(self):
        """LA TRAMPA DE CORE: pedir la clave no puede borrar los dispositivos.

        `get_web_push_vapid_public_key()` regenera el par cuando falta el
        parámetro, y lo primero que hace es
        `self.sudo().search([]).unlink()` -- TODOS los dispositivos de la base
        (mail/models/mail_push_device.py:33-45). Detrás de `auth="user"` es un
        pie de plomo; expuesto en una ruta pública sería un botón de "borrar
        todas las suscripciones" sin autenticar.

        La prueba borra el parámetro a posta, que es exactamente el estado en
        el que core dispara el borrado.
        """
        device = self._create_device(FCM_ENDPOINT % "survivor", guest=self.guest_b)
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", VAPID_PUBLIC_KEY_PARAM)]
        ).unlink()
        self.env.flush_all()

        self._forget_guest_cookie()
        result = self.make_jsonrpc_request("/mail/push/vapid", {})

        self.assertFalse(result["vapid_public_key"])
        self.assertTrue(
            device.exists(), "La ruta pública borró los dispositivos existentes"
        )
        self.assertFalse(
            self.env["ir.config_parameter"].sudo().get_param(VAPID_PUBLIC_KEY_PARAM),
            "La ruta pública generó claves nuevas: la rotación no es suya",
        )

    # ------------------------------------------------------------------
    # /mail/push/subscribe
    # ------------------------------------------------------------------

    def test_subscribe_binds_the_device_to_the_guest(self):
        """Un visitante con cookie se suscribe y el dispositivo es suyo."""
        endpoint = FCM_ENDPOINT % "route-guest"
        self.assertTrue(self._subscribe(guest=self.guest_b, endpoint=endpoint))
        device = (
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertFalse(device.partner_id)

    @mute_logger("odoo.http")
    def test_subscribe_without_persona_is_404(self):
        """Sin cookie y sin sesión: 404, no un dispositivo huérfano.

        Un dispositivo sin persona sería una suscripción que nada puede
        direccionar y, aun así, un endpoint al que este servidor hace POST.
        """
        self._forget_guest_cookie()
        with self.assertRaises(JsonRpcException) as capture:
            self._subscribe(endpoint=FCM_ENDPOINT % "route-anon")
        self.assertEqual(capture.exception.code, 404)
        self.assertFalse(
            self.env["mail.push.device"]
            .sudo()
            .search([("endpoint", "=", FCM_ENDPOINT % "route-anon")])
        )

    def test_portal_user_binds_to_its_own_partner(self):
        """Un usuario de portal se ata a SU socio, no al socio público.

        Si la persona se resolviera con `self.env.user.partner_id` sin más, un
        usuario público autenticado ataría el dispositivo al socio público
        compartido, y ahí acabarían llegando los mensajes de todo el mundo.
        """
        endpoint = FCM_ENDPOINT % "route-portal"
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self.assertTrue(self._subscribe(endpoint=endpoint))
        device = (
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )
        self.assertEqual(device.partner_id, self.portal_user.partner_id)
        self.assertNotEqual(device.partner_id, self.public_user.partner_id)
        self.assertFalse(device.guest_id)

    def test_authenticated_session_wins_over_a_stale_guest_cookie(self):
        """Con sesión Y cookie de visitante manda la cuenta.

        Las dos conviven en un navegador que inicia sesión sin limpiar `dgid`;
        la identidad que sobrevive es la cuenta.
        """
        endpoint = FCM_ENDPOINT % "route-both-personas"
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self.assertTrue(self._subscribe(guest=self.guest_b, endpoint=endpoint))
        device = (
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )
        self.assertEqual(device.partner_id, self.portal_user.partner_id)
        self.assertFalse(device.guest_id)

    def test_reregistering_the_same_endpoint_updates_the_caller_own_row(self):
        """El mismo endpoint NO se duplica: se actualiza la fila del que llama.

        `endpoint` es único en core (mail/models/mail_push_device.py:28-31),
        así que "crear siempre" no sería una fila de más, sería un error. Y es
        el caso NORMAL: el servicio de push devuelve el mismo endpoint en cada
        `pushManager.subscribe`, así que un navegador re-registra lo suyo
        continuamente y tiene que poder refrescar sus claves.
        """
        endpoint = FCM_ENDPOINT % "route-repoint"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)
        first_id = self._device_of(endpoint).id
        self.assertTrue(
            self._subscribe(
                guest=self.guest_b,
                endpoint=endpoint,
                expiration_time="2099-01-01 00:00:00",
            )
        )
        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.id, first_id)
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertEqual(str(device.expiration_time), "2099-01-01 00:00:00")

    # ------------------------------------------------------------------
    # /mail/push/subscribe: de quién es el endpoint
    #
    # Suscribir es la primitiva FUERTE de esta pareja. El módulo ya blindó
    # `/mail/push/unsubscribe` porque borrar por endpoint sin mirar el dueño
    # es un oráculo de borrado; reapuntar por endpoint sin mirar el dueño
    # consigue lo mismo Y ADEMÁS deja el endpoint de la víctima en manos del
    # atacante, que puede hacer sonar su navegador con nombre de autor y
    # cuerpo del mensaje. Estas pruebas van por la ruta pública de verdad
    # porque es por donde entra el ataque.
    # ------------------------------------------------------------------

    def test_another_guest_cannot_take_over_an_endpoint(self):
        """Otro visitante NO se queda con la suscripción ajena.

        Y la respuesta es la misma que la de un registro correcto: decir "ese
        endpoint no es tuyo" confirmaría que existe a quien lo tenga sin
        deberlo tener.
        """
        endpoint = FCM_ENDPOINT % "route-takeover"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)

        self.assertTrue(
            self._subscribe(guest=self.guest_outsider, endpoint=endpoint),
            "El rechazo se distingue del éxito desde fuera",
        )

        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertFalse(
            self.env["mail.push.device"]
            .sudo()
            .search([("guest_id", "=", self.guest_outsider.id)]),
            "El atacante acabó con un dispositivo propio",
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_a_stolen_endpoint_keeps_notifying_its_real_owner(self):
        """La víctima sigue recibiendo: el ataque no la silencia.

        Es la mitad que el propio módulo describe al blindar el borrado, y la
        que una comprobación de la fila en la base de datos no demuestra: lo
        que importa no es a qué `guest_id` apunta la columna, es a quién le
        suena el móvil.
        """
        endpoint = FCM_ENDPOINT % "route-takeover-push"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)
        self._subscribe(guest=self.guest_outsider, endpoint=endpoint)

        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author, body="<p>hola gente</p>")

        self.assertEqual(self._pushed_endpoints(mocked_push), [endpoint])
        payload = self._pushed_payloads(mocked_push)[0]
        self.assertIn(self.channel.name, payload["title"])

    def test_a_portal_user_cannot_take_over_a_guest_endpoint(self):
        """Iniciar sesión no da derecho al endpoint de OTRO visitante.

        Sin la cookie `dgid` de ese visitante, una cuenta identificada es
        exactamente igual de ajena que un visitante cualquiera. Es el caso que
        separa "el navegador es el mismo" de "el navegador dice que sí".
        """
        endpoint = FCM_ENDPOINT % "route-portal-takeover"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)

        self._forget_guest_cookie()
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self.assertTrue(self._subscribe(endpoint=endpoint))

        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertFalse(device.partner_id)

    def test_a_guest_cannot_take_over_a_partner_endpoint(self):
        """Y al revés tampoco: una cookie no reclama la fila de una cuenta.

        La transferencia sólo va en el sentido visitante -> cuenta, porque en
        ese sentido la petición TRAE la prueba (la cookie del visitante dueño).
        Al revés la sesión que lo probaría es justo la que se acaba de cerrar.
        Consecuencia asumida y documentada en el README.
        """
        endpoint = FCM_ENDPOINT % "route-downgrade"
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self._subscribe(endpoint=endpoint)

        self.logout()
        self.assertTrue(self._subscribe(guest=self.guest_b, endpoint=endpoint))

        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.partner_id, self.portal_user.partner_id)
        self.assertFalse(device.guest_id)

    def test_the_guest_of_this_request_may_upgrade_to_its_account(self):
        """EL CASO QUE NO SE PUEDE ROMPER: visitante que inicia sesión.

        Un visitante se suscribe, luego crea cuenta o entra con la suya, y el
        MISMO endpoint del navegador tiene que pasar al socio. La petición
        lleva la cookie `dgid` del visitante dueño de la fila, y esa cookie
        está validada contra su `access_token` antes de llegar al contexto
        (mail/tools/discuss.py:16-38): tenerla es ser ese visitante.
        """
        endpoint = FCM_ENDPOINT % "route-upgrade"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)
        first_id = self._device_of(endpoint).id

        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self.assertTrue(self._subscribe(guest=self.guest_b, endpoint=endpoint))

        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.id, first_id, "Se creó una fila nueva en vez de mover")
        self.assertEqual(device.partner_id, self.portal_user.partner_id)
        self.assertFalse(device.guest_id)

    # ------------------------------------------------------------------
    # /web/dataset/call_kw: la otra puerta, la de core
    # ------------------------------------------------------------------

    def _call_register_devices(self, guest=None, cookies=None, **kwargs):
        """`register_devices` por donde lo llama el cliente web de core.

        Se hace por HTTP de verdad y no con `with_user` porque lo que hay que
        demostrar es la ALCANZABILIDAD: `/web/dataset/call_kw` es `auth="user"`
        y no comprueba ACL de modelo, así que una cuenta de portal llega a un
        método de un modelo concedido sólo a `base.group_system`.

        `cookies` va aparte de `guest` para poder mandar una cookie de
        visitante que NO viene de un visitante real.
        """
        payload = {
            "keys": dict(BROWSER_KEYS),
            "vapid_public_key": self.vapid_public_key,
            "expirationTime": None,
        }
        payload.update(kwargs)
        if cookies is None and guest:
            cookies = self._guest_cookies(guest)
        return self.make_jsonrpc_request(
            "/web/dataset/call_kw",
            {
                "model": "mail.push.device",
                "method": "register_devices",
                "args": [],
                "kwargs": payload,
            },
            cookies=cookies,
        )

    def test_the_orm_door_cannot_take_over_a_guest_endpoint(self):
        """Una cuenta de portal LLEGA a `register_devices`, y aun así no puede.

        La primera mitad de esta prueba es el hallazgo: la petición no da 403,
        entra. La segunda es el arreglo: entra y no se lleva nada.
        """
        endpoint = FCM_ENDPOINT % "callkw-takeover"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)

        self._forget_guest_cookie()
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self._call_register_devices(endpoint=endpoint)

        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertFalse(device.partner_id)

    def test_the_orm_door_allows_the_guest_login_upgrade(self):
        """Y por esta puerta el ascenso visitante -> cuenta SÍ pasa.

        Es la que usa el cliente web de core al iniciar sesión, y la petición
        trae la cookie `dgid` del visitante dueño. `/web/dataset/call_kw` no
        lleva `add_guest_to_context`, así que el visitante no está en el
        contexto: se lee de la cookie, con la misma comprobación de
        `access_token` que haría el decorador. Sin eso, este ascenso sería
        imposible por el camino que de verdad lo dispara.
        """
        endpoint = FCM_ENDPOINT % "callkw-upgrade"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)
        first_id = self._device_of(endpoint).id

        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self._call_register_devices(guest=self.guest_b, endpoint=endpoint)

        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.id, first_id, "Se creó una fila nueva en vez de mover")
        self.assertEqual(device.partner_id, self.portal_user.partner_id)
        self.assertFalse(device.guest_id)

    def test_a_corrupt_guest_cookie_does_not_break_the_orm_door(self):
        """Una cookie `dgid` rota NO puede volverse un 500.

        `/web/dataset/call_kw` no lleva `add_guest_to_context`, así que el
        visitante lo lee `_current_guest` de la cookie -- y
        `_get_guest_from_token` hace un `int(guest_id)` pelado
        (mail/models/discuss/mail_guest.py:50-60). En una ruta pública
        decorada, una cookie corrupta ya revienta dentro de core y eso es cosa
        de core; aquí somos NOSOTROS quienes metemos el parseo de la cookie en
        un camino que antes no la tocaba, así que el visitante con la cookie
        estropeada no puede empezar a ver errores por eso.

        Se pide un endpoint AJENO a posta: es el único caso que llega a
        `_current_guest` (la rama del ascenso visitante -> cuenta). Y como el
        visitante no se resuelve, el resultado correcto es el rechazo
        silencioso de siempre, no una excepción.
        """
        endpoint = FCM_ENDPOINT % "callkw-corrupt-cookie"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)

        self._forget_guest_cookie()
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self._call_register_devices(
            endpoint=endpoint,
            cookies={self.env["mail.guest"]._cookie_name: "abc|def"},
        )

        device = self._device_of(endpoint)
        self.assertEqual(len(device), 1)
        self.assertEqual(device.guest_id, self.guest_b)
        self.assertFalse(device.partner_id)

    @mute_logger("odoo.http")
    def test_the_orm_door_refuses_an_endpoint_that_is_not_a_push_service(self):
        """El SSRF tampoco entra por la puerta del ORM.

        Es el mismo `_check_endpoint` de la ruta pública, aplicado ahora al
        camino autenticado: `/web/dataset/call_kw` no comprueba ACL de modelo y
        en esta plataforma una cuenta identificada es cualquiera que se haya
        registrado, así que "detrás de `auth="user"`" no es una pared.
        """
        endpoint = "https://169.254.169.254/latest/meta-data/"
        self._forget_guest_cookie()
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        with self._assert_refused_with(
            JSONRPC_VALIDATION_ERROR,
            "el endpoint interno se rechaza por la lista blanca, no por otra cosa",
        ):
            self._call_register_devices(endpoint=endpoint)
        self.assertFalse(self._device_of(endpoint))

    @mute_logger("odoo.http")
    def test_device_cap_is_enforced(self):
        """Una persona no puede abrir suscripciones sin fin.

        Una identidad de visitante es una cookie: se copia. Sin tope, cada
        copia multiplicaría las peticiones salientes que este servidor hace en
        nombre de un solo anónimo.
        """
        for index in range(MAX_DEVICES_PER_PERSONA):
            self._subscribe(guest=self.guest_b, endpoint=FCM_ENDPOINT % index)
        with self._assert_refused_with(
            JSONRPC_VALIDATION_ERROR, "el tope contesta con un rechazo, no con un fallo"
        ):
            self._subscribe(guest=self.guest_b, endpoint=FCM_ENDPOINT % "one-too-many")
        self.assertEqual(
            self.env["mail.push.device"]
            .sudo()
            .search_count([("guest_id", "=", self.guest_b.id)]),
            MAX_DEVICES_PER_PERSONA,
        )

    @mute_logger("odoo.http")
    def test_subscribe_rejects_an_endpoint_that_is_not_a_push_service(self):
        """El SSRF no entra por la ruta pública.

        Registrar `169.254.169.254` haría que el worker lo consultara desde
        dentro de la red en cada mensaje, y el cuerpo de la respuesta acabaría
        en el log (mail/tools/web_push.py:183-185).
        """
        with self._assert_refused_with(
            JSONRPC_VALIDATION_ERROR,
            "lo rechaza la lista blanca, no un error de más abajo",
        ):
            self._subscribe(
                guest=self.guest_b,
                endpoint="https://169.254.169.254/latest/meta-data/",
            )
        self.assertFalse(
            self.env["mail.push.device"]
            .sudo()
            .search([("guest_id", "=", self.guest_b.id)])
        )

    @mute_logger("odoo.http")
    def test_subscribe_rejects_a_stale_vapid_key(self):
        """Si el cliente devuelve otra clave VAPID, no se registra nada.

        Es la comprobación que hace core (`_verify_vapid_public_key`): un
        service worker suscrito con un par antiguo produciría un dispositivo
        para el que nadie puede cifrar.
        """
        with self._assert_refused_with(
            JSONRPC_INVALID_VAPID, "tiene que ser la clave, no otra pared"
        ):
            self._subscribe(
                guest=self.guest_b,
                endpoint=MOZILLA_ENDPOINT % "stale",
                vapid_public_key="not-the-key",
            )
        self.assertFalse(
            self.env["mail.push.device"]
            .sudo()
            .search([("endpoint", "=", MOZILLA_ENDPOINT % "stale")])
        )

    @mute_logger("odoo.http")
    def test_subscribe_rejects_malformed_browser_keys(self):
        """La forma de `{p256dh, auth}` se valida al registrar, no al cifrar.

        Se comprueba QUÉ excepción sale, y no sólo que salga alguna: sin
        `_check_browser_keys` la petición también falla, pero con un `KeyError`
        de `json.dumps` un par de líneas más abajo -- justamente el fallo que
        la comprobación existe para evitar. Un `assertRaises(JsonRpcException)`
        pelado no distingue el rechazo limpio del reventón, así que pasaría
        igual con el candado quitado.

        Se recorren las tres formas malas que llegan de verdad: falta una
        clave, sobra una, y el valor no es una cadena.
        """
        for keys in (
            {"p256dh": "only-one-key"},
            {"p256dh": "a", "auth": "b", "extra": "c"},
            {"p256dh": "a", "auth": 42},
        ):
            with self.subTest(keys=keys):
                with self._assert_refused_with(
                    JSONRPC_VALIDATION_ERROR,
                    "el rechazo tiene que ser limpio, no un KeyError al cifrar",
                ):
                    self._subscribe(
                        guest=self.guest_b,
                        endpoint=MOZILLA_ENDPOINT % "badkeys",
                        keys=keys,
                    )

    # ------------------------------------------------------------------
    # /mail/push/unsubscribe
    # ------------------------------------------------------------------

    def test_unsubscribe_removes_the_caller_own_device(self):
        endpoint = FCM_ENDPOINT % "route-unsub"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)
        result = self.make_jsonrpc_request(
            "/mail/push/unsubscribe",
            {"endpoint": endpoint},
            cookies=self._guest_cookies(self.guest_b),
        )
        self.assertTrue(result)
        self.assertFalse(
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )

    def test_unsubscribe_cannot_silence_somebody_else(self):
        """Core borra por endpoint sin mirar de quién es.

        `unregister_devices` (mail/models/mail_push_device.py:75-84) hace
        `search([("endpoint", "=", endpoint)]).unlink()`. Detrás de
        `auth="user"` pasa; en una ruta pública sería un oráculo de borrado:
        quien conociera el endpoint de otro podría callarlo.
        """
        endpoint = FCM_ENDPOINT % "route-victim"
        self._subscribe(guest=self.guest_b, endpoint=endpoint)
        result = self.make_jsonrpc_request(
            "/mail/push/unsubscribe",
            {"endpoint": endpoint},
            cookies=self._guest_cookies(self.guest_outsider),
        )
        self.assertFalse(result)
        self.assertTrue(
            self.env["mail.push.device"].sudo().search([("endpoint", "=", endpoint)])
        )

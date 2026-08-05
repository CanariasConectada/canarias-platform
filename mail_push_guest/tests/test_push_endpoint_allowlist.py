# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from odoo.addons.mail_push_guest.models.mail_push_device import (
    PUSH_ENDPOINT_ALLOWED_HOST_SUFFIXES,
    PUSH_ENDPOINT_ALLOWED_HOSTS,
)

from .common import MailPushGuestMixin


@tagged("post_install", "-at_install")
class TestPushEndpointAllowlist(MailPushGuestMixin, TransactionCase):
    """La lista blanca es lo único que separa "registrar" de "pedir por mí".

    `push_to_end_point` hace `session.post(endpoint, ...)` con una URL que
    manda el cliente y sólo comprueba que el TLD no sea `.invalid`
    (mail/tools/web_push.py:143-153). Con el registro abierto a anónimos, eso
    sería un SSRF sin autenticar; y como el cuerpo del error se registra a
    WARNING (`:183-185`), además con canal de vuelta.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()

    def test_accepts_every_allowlisted_host(self):
        """Todos los servicios reales de la lista pasan.

        Recorre la constante en vez de repetir los hosts a mano: si alguien
        añade un servicio nuevo, esta prueba lo cubre sola.
        """
        for host in PUSH_ENDPOINT_ALLOWED_HOSTS:
            with self.subTest(host=host):
                self.assertTrue(
                    self.Device._check_endpoint("https://%s/wpush/v2/abc123" % host)
                )

    def test_accepts_regional_host_suffixes(self):
        """Los nodos regionales (WNS, autopush) también.

        Son hosts con prefijo variable, de ahí la comparación por sufijo.
        """
        for suffix in PUSH_ENDPOINT_ALLOWED_HOST_SUFFIXES:
            with self.subTest(suffix=suffix):
                self.assertTrue(
                    self.Device._check_endpoint("https://db5p%s/w/abc123" % suffix)
                )

    def test_rejects_plain_http(self):
        """Sin TLS no: el token VAPID de la cabecera viaja como credencial."""
        self.assertFalse(
            self.Device._check_endpoint("http://fcm.googleapis.com/fcm/send/abc")
        )

    def test_rejects_userinfo_in_url(self):
        """`https://fcm.googleapis.com@attacker.example/` NO es Google.

        Se lee como un host permitido y resuelve a otro. Es el disfraz clásico
        de una lista blanca hecha con `in endpoint`.
        """
        self.assertFalse(
            self.Device._check_endpoint("https://fcm.googleapis.com@attacker.example/x")
        )
        self.assertFalse(
            self.Device._check_endpoint(
                "https://user:pass@fcm.googleapis.com.attacker.example/x"
            )
        )

    def test_rejects_cloud_metadata_address(self):
        """La dirección de metadatos del proveedor: el objetivo clásico.

        Un POST desde el worker a 169.254.169.254 devuelve credenciales de la
        instancia, y el cuerpo de la respuesta acabaría en el log.
        """
        self.assertFalse(
            self.Device._check_endpoint(
                "https://169.254.169.254/latest/meta-data/iam/security-credentials/"
            )
        )

    def test_rejects_internal_hosts(self):
        """Cualquier host que no sea un servicio de push, incluido el interno."""
        for endpoint in (
            "https://localhost/push",
            "https://127.0.0.1/push",
            "https://10.0.0.5/push",
            "https://redis.internal/push",
            "https://attacker.example/collect",
            # El dominio propio también: la lista es de servicios de push, no
            # de "sitios de confianza".
            "https://canariasconectada.es/push",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertFalse(self.Device._check_endpoint(endpoint))

    def test_rejects_invalid_tld(self):
        """`.invalid` cae por la lista blanca, no por el caso especial de core.

        Core lo trata al enviar, lanzando `DeviceUnreachableError`
        (mail/tools/web_push.py:149-153); aquí no llega a registrarse.
        """
        self.assertFalse(self.Device._check_endpoint("https://something.invalid/push"))

    def test_rejects_lookalike_hosts(self):
        """Un sufijo no puede colarse como prefijo ni como subdominio ajeno."""
        for endpoint in (
            "https://evilnotify.windows.com/w/abc",
            "https://notify.windows.com.attacker.example/w/abc",
            "https://fcm.googleapis.com.attacker.example/fcm/send/abc",
            "https://attacker.example/fcm.googleapis.com/fcm/send/abc",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertFalse(self.Device._check_endpoint(endpoint))

    def test_rejects_non_default_port(self):
        """Ningún servicio de push usa puerto: es la forma de sondear servicios."""
        self.assertFalse(
            self.Device._check_endpoint("https://fcm.googleapis.com:6379/fcm/send/abc")
        )

    def test_rejects_junk(self):
        """Vacío, tipo equivocado, esquema raro y longitud absurda."""
        for endpoint in (
            None,
            "",
            42,
            {"endpoint": "https://fcm.googleapis.com/x"},
            "file:///etc/passwd",
            "gopher://fcm.googleapis.com/x",
            "https://fcm.googleapis.com/%s" % ("a" * 1024),
        ):
            with self.subTest(endpoint=endpoint):
                self.assertFalse(self.Device._check_endpoint(endpoint))

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.models import mail_thread

from .common import FCM_ENDPOINT, MOZILLA_ENDPOINT, MailPushGuestMixin


@tagged("post_install", "-at_install")
class TestPushNotification(MailPushGuestMixin, TransactionCase):
    """Que el mensaje llegue al visitante, y sólo a quien toca.

    El envío se sustituye parcheando
    `odoo.addons.mail.models.mail_thread.push_to_end_point`, NO
    `odoo.addons.mail.tools.web_push.push_to_end_point`: `mail_thread` importa
    el símbolo al cargarse (`from ..tools.web_push import push_to_end_point`,
    mail/models/mail_thread.py:31-33), así que parchear el módulo de origen no
    interceptaría nada y la prueba pasaría sin haber enviado ni comprobado
    nada. Es el mismo objetivo que usa el helper de core
    (`MockEmail.mock_push_to_end_point`, mail/tests/common.py:81-86).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()
        cls.device_partner_author = cls._create_device(
            FCM_ENDPOINT % "author-partner", partner=cls.partner_author
        )
        cls.device_guest_b = cls._create_device(
            FCM_ENDPOINT % "guest-b", guest=cls.guest_b
        )
        cls.device_guest_muted = cls._create_device(
            MOZILLA_ENDPOINT % "guest-muted", guest=cls.guest_muted
        )
        cls.device_guest_author = cls._create_device(
            FCM_ENDPOINT % "guest-author", guest=cls.guest_author
        )
        cls.device_guest_outsider = cls._create_device(
            FCM_ENDPOINT % "guest-outsider", guest=cls.guest_outsider
        )
        cls.member_muted.write(
            {"mute_until_dt": fields.Datetime.now() + timedelta(days=1)}
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_partner_message_reaches_guest_member(self):
        """Un socio escribe y al visitante le suena el móvil.

        Es lo que core no puede hacer: `_notify_get_recipients` de canal filtra
        miembros por `partner_id.active`
        (mail/models/discuss/discuss_channel.py:874-904), así que un miembro
        visitante nunca entra en `recipients_data`.
        """
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author, body="<p>hola gente</p>")
        self.assertCountEqual(
            self._pushed_endpoints(mocked_push),
            [self.device_guest_b.endpoint, self.device_guest_author.endpoint],
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_channel_with_only_guests_still_notifies(self):
        """EL CASO PRINCIPAL, y el que casi se queda fuera.

        `_notify_thread` corta con `if not recipients_data: return` ANTES de
        llamar a `_notify_thread_by_web_push`
        (mail/models/mail_thread.py:3295-3296). Y `recipients_data` sólo lleva
        socios. En un canal donde sólo hay visitantes la lista sale vacía y
        core vuelve sin llegar nunca al paso de push: enganchar únicamente
        `_notify_thread_by_web_push` habría funcionado en todas partes MENOS
        en el escenario para el que existe el módulo.
        """
        guest_channel = self.env["discuss.channel"].create(
            {
                "name": "Solo visitantes",
                "channel_type": "channel",
                "group_public_id": False,
            }
        )
        guest_channel.add_members(
            guest_ids=(self.guest_b + self.guest_outsider).ids,
            post_joined_message=False,
        )
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_guest(
                self.guest_outsider, body="<p>hay alguien</p>", channel=guest_channel
            )
        self.assertEqual(
            self._pushed_endpoints(mocked_push), [self.device_guest_b.endpoint]
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_notification_is_not_sent_twice(self):
        """Los dos enganches no pueden solaparse.

        `_notify_thread` cubre la salida temprana y
        `_notify_thread_by_web_push` el camino normal; si ambos dispararan en
        el mismo mensaje, cada visitante recibiría dos avisos idénticos. La
        condición que lo impide (`not rdata`) es exactamente la de la salida
        temprana de core, y esto lo comprueba en el camino en el que core SÍ
        llega al paso de push: lo publica un visitante, así que el socio del
        canal entra en `recipients_data` y la lista no está vacía.
        """
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_guest(self.guest_author, body="<p>hola</p>")
        pushed = self._pushed_endpoints(mocked_push)
        self.assertEqual(
            pushed.count(self.device_guest_b.endpoint),
            1,
            "El visitante recibió el mismo mensaje dos veces",
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_author_own_device_is_never_called(self):
        """Nadie se notifica a sí mismo, sea socio o visitante.

        El caso del socio lo garantiza core (`partner_id != author_id` en el
        dominio de miembros); el del visitante hay que garantizarlo aquí,
        porque el visitante autor ES miembro del canal y tiene dispositivo.
        """
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author, body="<p>hola</p>")
        pushed = self._pushed_endpoints(mocked_push)
        self.assertNotIn(self.device_partner_author.endpoint, pushed)

        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_guest(self.guest_author, body="<p>hola</p>")
        pushed = self._pushed_endpoints(mocked_push)
        self.assertNotIn(self.device_guest_author.endpoint, pushed)
        self.assertIn(self.device_guest_b.endpoint, pushed)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_muted_member_is_skipped(self):
        """Un miembro silenciado sigue silenciado por esta vía.

        Añadir un canal de notificación nuevo y no mirar los ajustes de
        siempre es la forma más rápida de convertir un "silenciar" en mentira.

        Se comprueba TAMBIÉN que el otro visitante recibe: sin ese control
        positivo la prueba pasaría igual con el push entero roto, que es
        justo el fallo que no puede pasar desapercibido.
        """
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author)
        pushed = self._pushed_endpoints(mocked_push)
        self.assertNotIn(self.device_guest_muted.endpoint, pushed)
        self.assertIn(
            self.device_guest_b.endpoint,
            pushed,
            "No se envió nada: la prueba del silencio no probaba el silencio",
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_member_who_turned_notifications_off_is_skipped(self):
        """`custom_notifications = "no_notif"` también manda aquí.

        Se comprueba que el otro visitante SÍ recibe: así la prueba distingue
        "se respetó el ajuste de este miembro" de "no se envió nada".
        """
        member = self.env["discuss.channel.member"].search(
            [("channel_id", "=", self.channel.id), ("guest_id", "=", self.guest_b.id)]
        )
        member.write({"custom_notifications": "no_notif"})
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author)
        self.assertEqual(
            self._pushed_endpoints(mocked_push), [self.device_guest_author.endpoint]
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_guest_outside_the_channel_is_not_notified(self):
        """Tener dispositivo no es estar en el canal.

        La consulta parte de los MIEMBROS, no de los dispositivos; si se
        hubiera escrito al revés, cualquier visitante suscrito recibiría todo
        lo que se escribe en cualquier canal.

        El control positivo (el visitante que SÍ es miembro recibe) distingue
        "al de fuera no le llegó" de "no le llegó a nadie".
        """
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author)
        pushed = self._pushed_endpoints(mocked_push)
        self.assertNotIn(self.device_guest_outsider.endpoint, pushed)
        self.assertIn(
            self.device_guest_b.endpoint,
            pushed,
            "No se envió nada: la prueba no distinguía 'de fuera' de 'roto'",
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_payload_carries_author_and_body(self):
        """Decisión de producto: autor + principio del mensaje, no sólo el canal.

        "Maria in Guanarteme: hola gente" en vez de "Nuevo mensaje". Se avisa
        en el README de que ese texto se lee en una pantalla bloqueada.
        """
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author, body="<p>hola gente</p>")
        payload = self._pushed_payloads(mocked_push)[0]
        self.assertIn(self.partner_author.name, payload["title"])
        self.assertIn(self.channel.name, payload["title"])
        self.assertIn("hola gente", payload["options"]["body"])

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_guest_devices_never_take_the_payload_by_lang_path(self):
        """A un dispositivo de visitante SIEMPRE se le manda `payload=`.

        `_web_push_send_notification` indexa `payload_by_lang` con
        `device.partner_id.lang` (mail/models/mail_thread.py:3928 y :3947).
        Para un dispositivo sin socio eso es `False` como clave: KeyError, y
        el mensaje se pierde entero. La prueba no se conforma con que "haya
        funcionado": espía la llamada y comprueba el argumento, porque es el
        contrato lo que no puede romperse cuando alguien toque el envío.
        """
        calls = []
        channel_cls = type(self.channel)
        original = channel_cls._web_push_send_notification

        def spy(
            channel,
            devices,
            private_key,
            public_key,
            payload_by_lang=None,
            payload=None,
        ):
            calls.append((devices, payload_by_lang, payload))
            return original(
                channel,
                devices,
                private_key,
                public_key,
                payload_by_lang=payload_by_lang,
                payload=payload,
            )

        with patch.object(
            channel_cls, "_web_push_send_notification", spy
        ), patch.object(mail_thread, "push_to_end_point"):
            self._post_as_partner(self.user_author)

        guest_calls = [call for call in calls if call[0].filtered("guest_id")]
        self.assertTrue(guest_calls, "El envío a visitantes no llegó a ocurrir")
        for devices, payload_by_lang, payload in guest_calls:
            self.assertIsNone(payload_by_lang)
            self.assertTrue(payload)
            self.assertFalse(
                devices.filtered("partner_id"),
                "Un envío a visitantes no debe arrastrar dispositivos de socio",
            )

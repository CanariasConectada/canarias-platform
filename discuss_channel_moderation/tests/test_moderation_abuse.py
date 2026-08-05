# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import (
    JSONRPC_SESSION_EXPIRED,
    DiscussModerationHttpMixin,
    DiscussModerationMixin,
)


@tagged("post_install", "-at_install")
class TestModerationAbuse(DiscussModerationMixin, DiscussModerationHttpMixin, HttpCase):
    """La puerta se cruza por la ruta pública real, no por la API interna.

    Todo lo demás del módulo se prueba llamando a ``message_post`` en Python.
    Aquí se ataca por donde ataca un abusador: ``/mail/message/post``, que es
    ``auth="public"``.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()

    def test_context_flag_cannot_bypass_moderation(self):
        """EL test que justifica no colgar ningún bypass del contexto.

        mail/controllers/thread.py:205 ejecuta ``request.update_context(**context)``
        dentro de una ruta ``auth="public"``: el visitante controla TODAS las
        claves del contexto. Cualquier "puerta de servicio" basada en una clave
        de contexto sería falsificable por la misma persona a la que modera.
        """
        result = self._post_over_http(
            self.channel_a,
            self.guest_1,
            body="bypass attempt",
            context={
                "moderation_bypass": True,
                "discuss_channel_moderation_skip": True,
                "skip_moderation": True,
            },
        )
        self.assertFalse(
            result["message_id"],
            "la ruta debe informar de que no se publicó nada",
        )
        self.assertFalse(
            self._channel_comments(self.channel_a),
            "ninguna clave de contexto puede crear un mail.message",
        )
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.state, "pending")
        self.assertEqual(pending.guest_id, self.guest_1)

    def test_raw_route_post_is_still_held(self):
        """Sin contexto trucado y sin UI: la ruta cruda tampoco publica."""
        result = self._post_over_http(self.channel_a, self.guest_1, body="raw post")
        self.assertFalse(result["message_id"])
        self.assertFalse(self._channel_comments(self.channel_a))
        self.assertEqual(
            self.Pending.search_count([("channel_id", "=", self.channel_a.id)]), 1
        )

    def test_raw_route_post_on_free_channel_is_published(self):
        """Control positivo: la ruta funciona, lo que la frena es la moderación."""
        result = self._post_over_http(self.channel_free, self.guest_1, body="free")
        self.assertTrue(result["message_id"])
        self.assertTrue(self._channel_comments(self.channel_free))
        self.assertIn(
            result["message_id"],
            self._fetch_over_http(self.channel_free, self.guest_1)["messages"],
            "el canal sin moderar sí sirve el mensaje: la ruta de lectura vale",
        )

    def test_no_message_type_survives_the_route_with_a_guest_cookie(self):
        """El barrido por la ruta REAL, con cookie de visitante válida.

        La validación adversaria observó ``notification``, ``email``,
        ``email_outgoing``, ``auto_comment``, ``snailmail`` y ``sms`` publicando
        el HTML del atacante y sirviéndose después a terceros por
        ``/discuss/channel/messages``. Seis de siete puertas abiertas con
        cambiar una clave del JSON. Aquí se recorre la selección entera.
        """
        message_types = self._message_type_values()
        for message_type in message_types:
            with self.subTest(message_type=message_type):
                result = self._post_over_http(
                    self.channel_a,
                    self.guest_1,
                    body="<b>abuse %s</b>" % message_type,
                    message_type=message_type,
                )
                self.assertFalse(
                    result["message_id"],
                    "%s no puede publicar nada" % message_type,
                )
                self.assertFalse(
                    self._channel_all_messages(self.channel_a),
                    "%s no puede crear ningún mail.message" % message_type,
                )
                self.assertFalse(
                    self._fetch_over_http(self.channel_a, self.guest_2)["messages"],
                    "%s no puede acabar servido a un tercero" % message_type,
                )
        self.assertEqual(
            self.Pending.search_count([("channel_id", "=", self.channel_a.id)]),
            len(message_types),
            "todo el barrido acabó en la cola de moderación",
        )

    def test_no_message_type_survives_the_route_without_any_cookie(self):
        """El mismo barrido SIN cookie: la persona más anónima posible.

        Es el caso que observó la validación: ni sesión ni visitante, y aun así
        seis tipos publicaban. Sin cookie no hay ``mail.guest``, así que la
        retención se queda con el partner público como autor.
        """
        message_types = self._message_type_values()
        for message_type in message_types:
            with self.subTest(message_type=message_type):
                result = self._post_over_http(
                    self.channel_a,
                    body="<b>anon %s</b>" % message_type,
                    message_type=message_type,
                )
                self.assertFalse(result["message_id"])
                self.assertFalse(self._channel_all_messages(self.channel_a))
                self.assertFalse(self._fetch_over_http(self.channel_a)["messages"])
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.assertEqual(len(pending), len(message_types))
        self.assertFalse(pending.guest_id, "sin cookie no hay visitante que anotar")

    def test_held_bodies_are_never_served_to_a_third_party(self):
        """La fuga sólo es fuga cuando alguien la lee: se mira lo que se sirve."""
        self._post_over_http(
            self.channel_a,
            self.guest_1,
            body="<b>leak me</b>",
            message_type="notification",
        )
        for label, guest in (("otro visitante", self.guest_2), ("anónimo", None)):
            with self.subTest(persona=label):
                served = self._fetch_over_http(self.channel_a, guest)
                self.assertFalse(served["messages"])
                self.assertNotIn("leak me", str(served["data"]))

    @mute_logger("odoo.http")
    def test_guest_cannot_approve_over_rpc(self):
        """Aprobar es una acción de backend: un visitante no la alcanza.

        Y NO LA ALCANZA POR LA AUTENTICACIÓN, no por el ACL del módulo, que es
        una distinción que este test tiene que decir en voz alta porque leerlo
        al revés invita a relajar la seguridad del modelo creyéndola respaldada
        aquí. ``/web/dataset/call_kw`` es ``auth="user"``
        (web/controllers/dataset.py), y ``_auth_method_user``
        (odoo/addons/base/models/ir_http.py:257-259) levanta
        ``SessionExpiredException`` en cuanto el ``uid`` es el público -- que es
        el de una sesión de visitante. La petición muere ANTES de tocar el ORM:
        ni la regla de registro ni el ``ir.model.access`` de la cola llegan a
        evaluarse. Quien los prueba de verdad es ``test_moderation_scoping`` y
        ``test_moderation_visibility``, por ORM y afirmando ``AccessError``.

        Lo que sí queda probado aquí, y no es poco, es lo de después del
        bloque: el intento no mueve la retención ni publica nada.
        """
        self._post_over_http(self.channel_a, self.guest_1, body="held")
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.assertEqual(pending.state, "pending")
        with self._assert_refused_with(
            JSONRPC_SESSION_EXPIRED,
            "la ruta de backend ni siquiera autentica a un visitante",
        ):
            self.make_jsonrpc_request(
                "/web/dataset/call_kw",
                {
                    "model": "discuss.channel.pending.message",
                    "method": "action_approve",
                    "args": [pending.ids],
                    "kwargs": {},
                },
                cookies=self._guest_cookies(self.guest_1),
            )
        self.env.invalidate_all()
        self.assertEqual(
            pending.state, "pending", "la retención sigue en pie tras el intento"
        )
        self.assertFalse(self._channel_comments(self.channel_a))

    @mute_logger("odoo.http")
    def test_guest_cannot_read_the_queue_over_rpc(self):
        """La otra mitad de la misma puerta, y con el mismo matiz.

        También muere en ``auth="user"``, no en el ACL de la cola: ver el
        docstring de arriba. Se conserva porque la ruta de backend es una
        superficie pública real y alguien podría abrirla; el aislamiento del
        modelo se prueba en otro sitio.
        """
        self._post_over_http(self.channel_a, self.guest_1, body="held")
        with self._assert_refused_with(
            JSONRPC_SESSION_EXPIRED,
            "leer la cola por RPC muere en la autenticación, antes del ACL",
        ):
            self.make_jsonrpc_request(
                "/web/dataset/call_kw",
                {
                    "model": "discuss.channel.pending.message",
                    "method": "search_read",
                    "args": [[], ["body", "author_name"]],
                    "kwargs": {},
                },
                cookies=self._guest_cookies(self.guest_1),
            )

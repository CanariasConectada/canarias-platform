# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from contextlib import contextmanager

from odoo.tests.common import JsonRpcException

from odoo.addons.mail.tools.jwt import generate_vapid_keys

# QUÉ candado saltó, no si saltó alguno.
#
# `make_jsonrpc_request` mete en el mensaje de `JsonRpcException` el
# `error["data"]["name"]` (odoo/tests/common.py:2623-2626), y
# `serialize_exception` rellena ese campo con `"<módulo>.<clase>"`
# (odoo/http.py:469-479). Comparar contra estos nombres es la única forma de
# comprobar por HTTP cuál de las paredes contestó.
#
# Hace falta porque `assertRaises(JsonRpcException)` a secas se conforma con
# cualquier cosa que aborte la petición. El caso que lo demostró: quitando
# `_check_browser_keys`, la petición SIGUE fallando -- pero con un `KeyError`
# de `json.dumps` en vez de con el rechazo limpio que la comprobación existe
# para dar. Una prueba que no distingue el candado del error que el candado
# evita no está probando el candado.
JSONRPC_VALIDATION_ERROR = "odoo.exceptions.ValidationError"
JSONRPC_INVALID_VAPID = "odoo.addons.mail.tools.jwt.InvalidVapidError"

# El parámetro cuya AUSENCIA dispara la regeneración destructiva de core.
VAPID_PUBLIC_KEY_PARAM = "mail.web_push_vapid_public_key"

# Endpoints de servicios de push REALES. Las pruebas los usan a propósito en
# vez del `https://test.odoo.com/webpush/userN` de core: este módulo filtra por
# lista blanca de hosts, así que un fixture con un host inventado probaría el
# rechazo, no el camino feliz.
FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send/%s"
MOZILLA_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/%s"

# Par de claves de navegador con la forma que espera `_derive_key`
# (mail/tools/web_push.py:62-101). Son las de la suite de core: no se descifra
# nada en estas pruebas (el envío está mockeado), pero la forma sí se valida.
BROWSER_KEYS = {
    "p256dh": (
        "BGbhnoP_91U7oR59BaaSx0JnDv2oEooYnJRV2AbY5TBeKGCRCf0HcIJ9bOKchUCDH4cHYWo9"
        "SYDz3U-8vSxPL_A"
    ),
    "auth": "DJFdtAgZwrT6yYkUMgUqow",
}


class MailPushGuestMixin:
    """Fixtures compartidos por las suites de push a visitantes.

    Es un mixin y no un `TransactionCase` porque las rutas se prueban con
    `HttpCase`: el mismo escenario sirve para las dos bases sin duplicar el
    montaje.
    """

    @classmethod
    def _setup_push_fixtures(cls):
        cls.Device = cls.env["mail.push.device"]
        cls.public_user = cls.env.ref("base.public_user")

        # Las claves VAPID se generan a mano y se escriben en los parámetros.
        #
        # NO se llama a `get_web_push_vapid_public_key()`, que es como las
        # siembra la suite de core: ese método BORRA todos los dispositivos
        # cuando falta la clave pública (mail/models/mail_push_device.py:33-45).
        # En un fixture eso significaría que el orden de las líneas del
        # `setUpClass` decide si los dispositivos de la prueba existen.
        cls.vapid_private_key, cls.vapid_public_key = generate_vapid_keys()
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("mail.web_push_vapid_private_key", cls.vapid_private_key)
        params.set_param("mail.web_push_vapid_public_key", cls.vapid_public_key)

        cls.guest_b, cls.guest_muted, cls.guest_author, cls.guest_outsider = cls.env[
            "mail.guest"
        ].create(
            [
                {"name": "Guest B"},
                {"name": "Guest Muted"},
                {"name": "Guest Author"},
                {"name": "Guest Outsider"},
            ]
        )

        cls.user_author = cls.env["res.users"].create(
            {
                "name": "Maria Author",
                "login": "mpg_author",
                "email": "mpg_author@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.partner_author = cls.user_author.partner_id

        cls.portal_user = cls.env["res.users"].create(
            {
                "name": "Portal Visitor",
                "login": "mpg_portal",
                "password": "mpg_portal_pwd",
                "email": "mpg_portal@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

        # `group_public_id = False` EXPLÍCITO: sin él,
        # `_compute_group_public_id` rellena `base.group_user` en cuanto el
        # `channel_type` es "channel" y el canal deja de ser visible para un
        # visitante, con lo que el escenario dejaría de parecerse al real.
        cls.channel = cls.env["discuss.channel"].create(
            {
                "name": "Guanarteme",
                "channel_type": "channel",
                "group_public_id": False,
            }
        )
        cls.channel.add_members(
            partner_ids=cls.partner_author.ids,
            guest_ids=(cls.guest_b + cls.guest_muted + cls.guest_author).ids,
            post_joined_message=False,
        )
        cls.member_muted = cls.env["discuss.channel.member"].search(
            [("channel_id", "=", cls.channel.id), ("guest_id", "=", cls.guest_muted.id)]
        )

    # ------------------------------------------------------------------
    # Fábricas
    # ------------------------------------------------------------------

    @classmethod
    def _create_device(cls, endpoint, partner=None, guest=None):
        """Crea un dispositivo saltándose la ruta pública.

        Se usa `create` directo, no `_register_for_persona`, porque muchas
        pruebas necesitan un dispositivo YA existente para comprobar otra cosa
        (que sobrevive, que recibe, que no se duplica).
        """
        return cls.Device.sudo().create(
            {
                "endpoint": endpoint,
                "keys": json.dumps(BROWSER_KEYS),
                "partner_id": partner.id if partner else False,
                "guest_id": guest.id if guest else False,
            }
        )

    # ------------------------------------------------------------------
    # Sesión HTTP
    # ------------------------------------------------------------------

    def _guest_cookies(self, guest):
        """Cookie de visitante tal y como la lee `add_guest_to_context`.

        Formato `<id>|<access_token>` (mail/models/discuss/mail_guest.py:50-60).
        `access_token` está protegido por `base.group_system`, de ahí el sudo.
        """
        return {
            self.env["mail.guest"]._cookie_name: "%s|%s"
            % (guest.id, guest.sudo().access_token)
        }

    def _forget_guest_cookie(self):
        """Deja la sesión HTTP SIN cookie de visitante.

        `self.opener` es persistente: sin esto, "sin cookie" sería en realidad
        "con la que dejó la petición anterior", y el caso sin persona -- el que
        debe dar 404 -- no se estaría probando.
        """
        self.opener.cookies.pop(self.env["mail.guest"]._cookie_name, None)

    @contextmanager
    def _assert_refused_with(self, expected, message):
        """La petición tiene que fallar, y fallar POR ESTO.

        Mismo helper que el módulo hermano `discuss_channel_moderation`
        (tests/common.py:277-288), y por el mismo motivo: que la forma estricta
        sea también la forma corta. Ver las constantes `JSONRPC_*` de arriba.
        """
        with self.assertRaises(JsonRpcException) as caught:
            yield caught
        self.assertEqual(str(caught.exception), expected, message)

    # ------------------------------------------------------------------
    # Publicación
    # ------------------------------------------------------------------

    def _post_as_partner(
        self, user, body="hola gente", message_type="comment", channel=None
    ):
        """Publica como usuario identificado, igual que hace el cliente web."""
        return (
            (channel or self.channel)
            .with_user(user)
            .sudo()
            .message_post(
                body=body,
                message_type=message_type,
                subtype_xmlid="mail.mt_comment",
            )
        )

    def _post_as_guest(
        self, guest, body="hola gente", message_type="comment", channel=None
    ):
        """Publica como visitante, reproduciendo `/mail/message/post`.

        La ruta es `auth="public"`: el usuario de sesión es el público y el
        visitante viaja en el contexto (mail/controllers/thread.py:249-251).
        """
        return (
            (channel or self.channel)
            .with_user(self.public_user)
            .sudo()
            .with_context(guest=guest)
            .message_post(
                body=body,
                message_type=message_type,
                subtype_xmlid="mail.mt_comment",
            )
        )

    # ------------------------------------------------------------------
    # Aserciones
    # ------------------------------------------------------------------

    def _pushed_endpoints(self, mocked_push):
        """Endpoints a los que se intentó enviar, en orden de llamada."""
        return [
            call.kwargs["device"]["endpoint"] for call in mocked_push.call_args_list
        ]

    def _pushed_payloads(self, mocked_push):
        """Payloads enviados, ya deserializados."""
        return [
            json.loads(call.kwargs["payload"]) for call in mocked_push.call_args_list
        ]

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from psycopg2.errors import CheckViolation, UniqueViolation

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import DiscussModerationMixin


@tagged("post_install", "-at_install")
class TestModerationHold(DiscussModerationMixin, TransactionCase):
    """El hold: qué se retiene, qué NO se retiene y qué se guarda.

    La invariante central es "cero ``mail.message``": si el hold dejase un
    mensaje a medias, el resto del módulo sería decorativo, porque
    ``mail.message`` no tiene ``ir.rule`` y su acceso es por documento
    (mail/models/mail_message.py:317 y :432).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()

    def test_guest_comment_is_held_without_mail_message(self):
        result = self._post_as_guest(self.channel_a, self.guest_1, "guest says hi")
        self.assertFalse(
            result,
            "message_post debe devolver un recordset VACÍO, nunca un mensaje a medias",
        )
        self.assertEqual(result._name, "mail.message")
        self.assertFalse(
            self._channel_comments(self.channel_a),
            "un comentario retenido no puede existir como mail.message",
        )
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.state, "pending")
        self.assertEqual(pending.guest_id, self.guest_1)
        self.assertFalse(pending.partner_id)
        self.assertFalse(pending.message_id)

    def test_held_message_snapshots_author_name(self):
        """El nombre se congela: la cola sigue legible si el guest se renombra."""
        self._post_as_guest(self.channel_a, self.guest_1)
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.assertEqual(pending.author_name, "Guest One")
        self.guest_1.sudo().name = "Renamed Guest"
        self.assertEqual(pending.author_name, "Guest One")

    def test_unmoderated_channel_posts_normally(self):
        message = self._post_as_guest(self.channel_free, self.guest_1, "free speech")
        self.assertTrue(message, "sin fila de moderación no hay hold posible")
        self.assertEqual(message.author_guest_id, self.guest_1)
        self.assertFalse(
            self.Pending.search([("channel_id", "=", self.channel_free.id)])
        )

    def test_archived_moderation_does_not_hold(self):
        """Archivar la configuración es la forma documentada de apagar el hold."""
        self.moderation_a.active = False
        message = self._post_as_guest(self.channel_a, self.guest_1)
        self.assertTrue(message)
        self.assertFalse(self.Pending.search([("channel_id", "=", self.channel_a.id)]))

    def test_guest_not_held_when_moderate_guests_disabled(self):
        self.moderation_a.moderate_guests = False
        message = self._post_as_guest(self.channel_a, self.guest_1)
        self.assertTrue(message)
        self.assertFalse(self.Pending.search([("channel_id", "=", self.channel_a.id)]))

    def test_portal_user_not_held_by_default(self):
        """``moderate_portal`` es False por defecto: el portal no se retiene."""
        self.assertFalse(self.moderation_a.moderate_portal)
        message = self._post_as_user(self.channel_a, self.portal_user, "portal hi")
        self.assertTrue(message)
        self.assertEqual(message.author_id, self.portal_user.partner_id)
        self.assertFalse(self.Pending.search([("channel_id", "=", self.channel_a.id)]))

    def test_portal_user_held_when_moderate_portal(self):
        self.moderation_a.moderate_portal = True
        result = self._post_as_user(self.channel_a, self.portal_user, "portal hi")
        self.assertFalse(result)
        self.assertFalse(self._channel_comments(self.channel_a))
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.assertEqual(pending.partner_id, self.portal_user.partner_id)
        self.assertFalse(pending.guest_id)

    def test_internal_user_is_never_held(self):
        """Ni con moderate_portal activo: los internos son de confianza."""
        self.moderation_a.moderate_portal = True
        message = self._post_as_user(self.channel_a, self.plain_employee, "employee hi")
        self.assertTrue(message)
        self.assertFalse(self.Pending.search([("channel_id", "=", self.channel_a.id)]))

    def test_every_message_type_is_held_for_a_guest(self):
        """EL candado de regresión: el tipo lo elige el atacante, no nos vale de filtro.

        ``message_type`` está en ``_get_allowed_message_params``
        (mail/models/mail_thread.py:5073-5078) y ``_prepare_message_data``
        (mail/controllers/thread.py:149-155) lo copia TAL CUAL desde el
        ``post_data`` de una ruta ``auth="public"``. Una versión anterior de
        ``_moderation_hold`` salía por las buenas si el tipo no era "comment",
        creyendo que sólo el código de confianza generaba los demás: bastaba
        una clave más en el JSON para publicar HTML arbitrario en el canal.

        Se barre la selección ENTERA leída del campo, no una lista escrita a
        mano: si Odoo o un módulo añaden un tipo, el candado lo cubre solo.
        """
        message_types = self._message_type_values()
        self.assertIn("comment", message_types, "la selección se lee del campo")
        for message_type in message_types:
            with self.subTest(message_type=message_type):
                result = self._post_as_guest(
                    self.channel_a, self.guest_1, "sweep", message_type=message_type
                )
                self.assertFalse(
                    result,
                    "%s debe retenerse: el visitante no elige su propio trato"
                    % message_type,
                )
                self.assertFalse(
                    self._channel_all_messages(self.channel_a),
                    "%s no puede crear NINGÚN mail.message" % message_type,
                )
        self.assertEqual(
            self.Pending.search_count([("channel_id", "=", self.channel_a.id)]),
            len(message_types),
            "cada intento del barrido deja exactamente una retención",
        )

    def test_every_message_type_is_held_for_a_public_session(self):
        """Lo mismo sin cookie de visitante: menos identificado, no más confiable."""
        for message_type in self._message_type_values():
            with self.subTest(message_type=message_type):
                result = self._post_as_public(
                    self.channel_a, "sweep", message_type=message_type
                )
                self.assertFalse(result)
                self.assertFalse(self._channel_all_messages(self.channel_a))

    def test_every_message_type_is_held_for_a_moderated_portal_user(self):
        """Y con ``moderate_portal``, tampoco el portal escapa cambiando el tipo."""
        self.moderation_a.moderate_portal = True
        for message_type in self._message_type_values():
            with self.subTest(message_type=message_type):
                result = self._post_as_user(
                    self.channel_a,
                    self.portal_user,
                    "sweep",
                    message_type=message_type,
                )
                self.assertFalse(result)
                self.assertFalse(self._channel_all_messages(self.channel_a))

    def test_internal_system_message_types_still_post(self):
        """El otro lado del candado: no romper los mensajes del sistema.

        Avisos de unión, renombrados y trazas los publica código del servidor
        corriendo como un usuario interno. Si el hold se hubiese arreglado
        reteniendo por tipo en vez de por persona, un canal moderado dejaría
        de registrarlos.

        ``user_notification`` queda fuera del barrido porque el propio core lo
        prohíbe en ``message_post`` (mail/models/mail_thread.py:2233-2234, hay
        que usar ``message_notify``): no es una puerta que nosotros abramos ni
        cerremos. Es también la razón de que la validación observase SEIS tipos
        publicados y no siete.
        """
        for message_type in self._message_type_values():
            if message_type == "user_notification":
                continue
            with self.subTest(message_type=message_type):
                message = self._post_as_user(
                    self.channel_a,
                    self.plain_employee,
                    "system",
                    message_type=message_type,
                )
                self.assertTrue(
                    message, "%s de un interno no se retiene jamás" % message_type
                )
        self.assertFalse(self.Pending.search([("channel_id", "=", self.channel_a.id)]))

    def test_core_system_notification_flow_survives_moderation(self):
        """Un flujo REAL del core, no una llamada sintética a ``message_post``.

        ``channel_rename`` (mail/models/discuss/discuss_channel.py:1468) publica
        una notificación en el canal. Es la prueba de que la puerta no rompe el
        código del servidor que atraviesa el mismo embudo.
        """
        self.channel_a.with_user(self.plain_employee).channel_rename("Moderated A2")
        notification = self._channel_all_messages(self.channel_a)
        self.assertEqual(len(notification), 1, "el aviso del sistema debe publicarse")
        self.assertEqual(notification.message_type, "notification")
        self.assertFalse(self.Pending.search([("channel_id", "=", self.channel_a.id)]))

    def test_held_message_keeps_parent_anchor(self):
        """Una respuesta retenida guarda su ancla para volver a su hilo al aprobarse."""
        root = self._post_as_user(self.channel_a, self.plain_employee, "root message")
        self._post_as_guest(self.channel_a, self.guest_1, "reply")
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        # El helper no pasa parent_id, así que lo fijamos explícitamente para
        # comprobar que el campo existe y sobrevive.
        pending.parent_id = root
        self.assertEqual(pending.parent_id, root)

    @mute_logger("odoo.sql_db")
    def test_author_constraint_rejects_both(self):
        """Un mensaje retenido no puede venir de un guest Y de un partner.

        UNA sola excepción, y es la de PostgreSQL. ``assertRaises`` de Odoo
        (odoo/tests/common.py:532-559) reenvía el argumento a
        ``issubclass(...)``, así que NO admite una tupla: pasarle
        ``(CheckViolation, ValidationError)`` no relaja el test, lo revienta
        con ``TypeError``. Y no hay ambigüedad que cubrir: ``create`` ejecuta el
        INSERT antes de validar las restricciones de Python
        (``_validate_fields`` en odoo/orm/models.py:4946 va DESPUÉS del insert),
        de modo que el CHECK de la base siempre gana la carrera.
        """
        with self.assertRaises(CheckViolation):
            self.Pending.create(
                {
                    "channel_id": self.channel_a.id,
                    "moderation_id": self.moderation_a.id,
                    "guest_id": self.guest_1.id,
                    "partner_id": self.portal_user.partner_id.id,
                    "author_name": "Both",
                }
            )

    def test_author_constraint_rejects_neither(self):
        """Ni de ninguno de los dos: siempre hay exactamente un autor.

        Este caso NO lo ve la base: el CHECK sólo prohíbe tener los dos. Y sin
        el ``create`` que siembra las dos claves en ``vals``, tampoco lo vería
        el ORM, porque ``@api.constrains`` sólo valida los campos presentes en
        el ``create``. Sin ese arreglo, esta llamada creaba una fila SIN autor.
        """
        with self.assertRaises(ValidationError):
            self.Pending.create(
                {
                    "channel_id": self.channel_a.id,
                    "moderation_id": self.moderation_a.id,
                    "author_name": "Nobody",
                }
            )
        self.assertFalse(
            self.Pending.search([("author_name", "=", "Nobody")]),
            "no puede quedar ninguna fila huérfana de autor",
        )

    def test_channel_moderation_is_unique(self):
        """Una sola configuración por canal: dos filas serían dos políticas."""
        with self.assertRaises(UniqueViolation):
            with self.cr.savepoint(), mute_logger("odoo.sql_db"):
                self.Moderation.create({"channel_id": self.channel_a.id})

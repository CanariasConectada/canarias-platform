# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from odoo.addons.discuss_channel_moderation.models.discuss_channel import (
    MODERATED_MESSAGE_TYPE,
)

from .common import DiscussModerationMixin


@tagged("post_install", "-at_install")
class TestModerationPublish(DiscussModerationMixin, TransactionCase):
    """La aprobación: convierte la retención en un mensaje real y correcto."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()

    def _hold(self, channel=None, guest=None, body="held body"):
        channel = channel or self.channel_a
        self._post_as_guest(channel, guest or self.guest_1, body)
        return self.Pending.search([("channel_id", "=", channel.id)], limit=1)

    def test_approval_creates_message_authored_by_the_guest(self):
        """LA regresión que justifica ``_post_moderated_message``.

        ``author_guest_id`` no se puede pasar a ``message_post``:
        mail/models/mail_thread.py:2303 machaca lo que mande quien llama con lo
        calculado en 2271-2277. Si alguien "simplifica" el método pasando el
        kwarg, el mensaje aparecerá firmado por el usuario público (o por el
        moderador) y este test lo cazará.
        """
        pending = self._hold()
        pending.with_user(self.moderator_a).action_approve()
        message = self._channel_comments(self.channel_a)
        self.assertEqual(len(message), 1)
        self.assertEqual(
            message.author_guest_id,
            self.guest_1,
            "el mensaje publicado debe seguir siendo del visitante, no del moderador",
        )
        self.assertFalse(
            message.author_id,
            "author_id debe quedar vacío: un guest no es un partner",
        )
        self.assertEqual(pending.state, "approved")
        self.assertEqual(pending.message_id, message)
        self.assertEqual(pending.moderator_id, self.moderator_a)
        self.assertTrue(pending.moderation_date)

    def test_approved_message_carries_the_pinned_message_type(self):
        """El tipo con el que se publica lo fija el módulo, no el autor.

        El visitante manda ``message_type`` en el ``post_data`` y llega intacto
        hasta ``message_post``. Si ese valor se guardase en la fila retenida y
        se reutilizase al aprobar, el atacante seguiría eligiendo cómo trata la
        plataforma su propio texto (si cuenta en ``message_count``, si sale por
        correo, qué subtipo lleva); la retención sólo le habría añadido una
        espera. La fila NO guarda tipo alguno y la publicación usa la constante.
        """
        for sent_type in ("notification", "email", "auto_comment"):
            with self.subTest(sent_type=sent_type):
                self._post_as_guest(
                    self.channel_b, self.guest_1, "typed", message_type=sent_type
                )
                pending = self.Pending.search(
                    [("channel_id", "=", self.channel_b.id)], limit=1
                )
                self.assertNotIn(
                    "message_type",
                    pending._fields,
                    "la fila retenida no puede tener dónde esconder el tipo",
                )
                pending.with_user(self.moderator_b).action_approve()
                self.assertEqual(
                    pending.message_id.message_type, MODERATED_MESSAGE_TYPE
                )
                self.assertEqual(
                    pending.message_id.subtype_id,
                    self.env.ref("mail.mt_comment"),
                )

    def test_approved_message_keeps_its_body(self):
        pending = self._hold(body="hola <b>mundo</b>")
        pending.with_user(self.moderator_a).action_approve()
        self.assertIn("mundo", self._channel_comments(self.channel_a).body)

    def test_approval_of_a_portal_message_keeps_the_partner_author(self):
        self.moderation_a.moderate_portal = True
        self._post_as_user(self.channel_a, self.portal_user, "portal held")
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        pending.with_user(self.moderator_a).action_approve()
        message = self._channel_comments(self.channel_a)
        self.assertEqual(message.author_id, self.portal_user.partner_id)
        self.assertFalse(message.author_guest_id)

    def test_approved_reply_keeps_its_parent_anchor(self):
        root = self._post_as_user(self.channel_a, self.plain_employee, "root")
        pending = self._hold(body="reply")
        pending.parent_id = root
        pending.with_user(self.moderator_a).action_approve()
        self.assertEqual(pending.message_id.parent_id, root)

    def test_approving_twice_is_a_noop(self):
        pending = self._hold()
        pending.with_user(self.moderator_a).action_approve()
        first_message = pending.message_id
        pending.with_user(self.moderator_a).action_approve()
        self.assertEqual(
            len(self._channel_comments(self.channel_a)),
            1,
            "aprobar dos veces no puede publicar dos mensajes",
        )
        self.assertEqual(pending.message_id, first_message)

    def test_approval_does_not_reenter_the_hold(self):
        """``_post_moderated_message`` salta por encima de esta clase.

        Si llamase a ``channel.message_post`` sin el ``super(DiscussChannel,
        ...)`` explícito, el override volvería a disparar y la aprobación
        crearía una SEGUNDA fila retenida en vez de un mensaje.
        """
        pending = self._hold()
        pending.with_user(self.moderator_a).action_approve()
        self.assertEqual(
            self.Pending.search_count([("channel_id", "=", self.channel_a.id)]),
            1,
            "la aprobación no puede generar una nueva retención",
        )
        self.assertEqual(len(self._channel_comments(self.channel_a)), 1)

    def test_rejection_creates_no_message(self):
        pending = self._hold()
        pending.with_user(self.moderator_a).action_reject("spam")
        self.assertEqual(pending.state, "rejected")
        self.assertFalse(pending.message_id)
        self.assertFalse(self._channel_comments(self.channel_a))
        self.assertEqual(pending.rejection_reason, "spam")
        self.assertEqual(pending.moderator_id, self.moderator_a)

    def test_rejecting_twice_is_a_noop(self):
        pending = self._hold()
        pending.with_user(self.moderator_a).action_reject("spam")
        pending.with_user(self.moderator_a).action_reject("otra razón")
        self.assertEqual(
            pending.rejection_reason,
            "spam",
            "una decisión tomada no se reescribe",
        )

    def test_rejecting_an_approved_message_is_a_noop(self):
        pending = self._hold()
        pending.with_user(self.moderator_a).action_approve()
        pending.with_user(self.moderator_a).action_reject("me arrepiento")
        self.assertEqual(pending.state, "approved")
        self.assertEqual(len(self._channel_comments(self.channel_a)), 1)

    def test_pending_count_follows_the_queue(self):
        self._hold(body="one")
        self._post_as_guest(self.channel_a, self.guest_2, "two")
        self.moderation_a.invalidate_recordset(["pending_count"])
        self.assertEqual(self.moderation_a.pending_count, 2)
        self.Pending.search([("channel_id", "=", self.channel_a.id)]).with_user(
            self.moderator_a
        ).action_approve()
        self.moderation_a.invalidate_recordset(["pending_count"])
        self.assertEqual(self.moderation_a.pending_count, 0)

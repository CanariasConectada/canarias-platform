# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import DiscussModerationMixin

RULE_LOGGERS = (
    "odoo.addons.base.models.ir_rule",
    "odoo.addons.base.models.ir_model",
)


@tagged("post_install", "-at_install")
class TestModerationScoping(DiscussModerationMixin, TransactionCase):
    """Cada moderador ve su cola y sólo la suya.

    Ser moderador de un canal no puede convertirte en moderador de la
    plataforma entera: sería una escalada de privilegios silenciosa en cuanto
    alguien delegue la moderación de un canal a un tercero.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()

    def setUp(self):
        super().setUp()
        self._post_as_guest(self.channel_a, self.guest_1, "held in A")
        self._post_as_guest(self.channel_b, self.guest_2, "held in B")
        self.pending_a = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.pending_b = self.Pending.search([("channel_id", "=", self.channel_b.id)])

    def test_moderator_sees_only_their_own_queue(self):
        visible = self.Pending.with_user(self.moderator_a).search([])
        self.assertEqual(visible, self.pending_a)

    @mute_logger(*RULE_LOGGERS)
    def test_moderator_cannot_read_another_channel_queue(self):
        with self.assertRaises(AccessError):
            self.pending_b.with_user(self.moderator_a).read(["body"])

    @mute_logger(*RULE_LOGGERS)
    def test_moderator_cannot_write_another_channel_queue(self):
        with self.assertRaises(AccessError):
            self.pending_b.with_user(self.moderator_a).write(
                {"rejection_reason": "no es mi canal"}
            )

    @mute_logger(*RULE_LOGGERS)
    def test_moderator_cannot_approve_another_channel_queue(self):
        with self.assertRaises(AccessError):
            self.pending_b.with_user(self.moderator_a).action_approve()
        self.assertEqual(self.pending_b.state, "pending")
        self.assertFalse(self._channel_comments(self.channel_b))

    @mute_logger(*RULE_LOGGERS)
    def test_moderator_cannot_reject_another_channel_queue(self):
        with self.assertRaises(AccessError):
            self.pending_b.with_user(self.moderator_a).action_reject("spam")
        self.assertEqual(self.pending_b.state, "pending")

    @mute_logger(*RULE_LOGGERS)
    def test_plain_employee_cannot_approve(self):
        """Sin ninguno de los dos grupos no hay moderación posible."""
        with self.assertRaises(AccessError):
            self.pending_a.with_user(self.plain_employee).action_approve()
        self.assertEqual(self.pending_a.state, "pending")

    @mute_logger(*RULE_LOGGERS)
    def test_moderator_cannot_add_themselves_to_another_channel(self):
        """El ACL de la configuración es de sólo lectura para los moderadores.

        Si pudiesen escribirla, se añadirían a ``moderator_user_ids`` de
        cualquier canal y la regla de la cola dejaría de aislar nada.
        """
        with self.assertRaises(AccessError):
            self.moderation_b.with_user(self.moderator_a).write(
                {"moderator_user_ids": [(4, self.moderator_a.id)]}
            )

    @mute_logger(*RULE_LOGGERS)
    def test_moderator_cannot_read_another_channel_configuration(self):
        with self.assertRaises(AccessError):
            self.moderation_b.with_user(self.moderator_a).read(["moderate_guests"])

    def test_administrator_sees_every_queue(self):
        visible = self.Pending.with_user(self.manager).search([])
        self.assertEqual(visible, self.pending_a + self.pending_b)

    def test_administrator_can_approve_any_channel(self):
        self.pending_b.with_user(self.manager).action_approve()
        self.assertEqual(self.pending_b.state, "approved")

    def test_user_in_both_groups_sees_everything(self):
        """Las reglas de distintos grupos se combinan con OR, no con AND.

        Si se combinasen con AND, dar el grupo de administrador a un moderador
        concreto le RESTARÍA acceso en vez de sumárselo.
        """
        visible = self.Pending.with_user(self.both_groups).search([])
        self.assertEqual(visible, self.pending_a + self.pending_b)

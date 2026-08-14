# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import DiscussModerationMixin


@tagged("post_install", "-at_install")
class TestModerationVisibility(DiscussModerationMixin, TransactionCase):
    """Nadie salvo el autor sabe que el mensaje retenido existe.

    Es la razón de ser del modelo aparte: ``mail.message`` no tiene ninguna
    ``ir.rule`` y su acceso es POR DOCUMENTO
    (``_find_allowed_doc_ids``, mail/models/mail_message.py:397), así que
    cualquiera que pueda leer el canal leería TODOS sus mensajes. Un
    ``mail.message`` "oculto" sería un mensaje visible.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()

    #: Personas que NO son el autor del mensaje retenido. Ninguna puede verlo,
    #: y todas tienen que ver el mensaje publicado del canal: eso último es lo
    #: que impide que estas pruebas pasen por vacías.
    OUTSIDER_PERSONAS = (
        ("guest", {"guest": "guest_2"}),
        ("portal", {"user": "portal_user"}),
        ("employee", {"user": "plain_employee"}),
    )

    def _persona_kwargs(self, spec):
        return {key: getattr(self, name) for key, name in spec.items()}

    def test_control_a_published_message_is_visible_to_everyone(self):
        """Control positivo: sin él, las demás pruebas serían vacuas.

        Comprueba que el canal es legible de verdad: el mensaje publicado tiene
        que llegar a las tres personas ajenas por la misma vía que usa
        ``/discuss/channel/messages``. Si el canal no fuese legible -- por
        ejemplo con ``group_public_id`` en ``base.group_user``, que es lo que
        pone el ``compute`` del core cuando el campo no se pasa en el
        ``create`` -- nadie vería nunca nada y "no ve el mensaje retenido" no
        demostraría absolutamente nada.
        """
        published = self._post_as_user(
            self.channel_a, self.plain_employee, "public message"
        )
        self.assertTrue(published, "el control positivo necesita un mensaje real")
        for label, spec in self.OUTSIDER_PERSONAS:
            with self.subTest(persona=label):
                self.assertIn(
                    published.id,
                    self._channel_messages(
                        self.channel_a, **self._persona_kwargs(spec)
                    ).ids,
                    "el canal es legible: %s debe ver el mensaje publicado" % label,
                )

    def test_outsiders_see_the_published_message_and_not_the_held_one(self):
        """La prueba central, con su control positivo DENTRO.

        Cada persona ajena mira el mismo canal después de una retención. Ve el
        mensaje publicado (luego está mirando de verdad) y el canal entero
        sigue teniendo los mismos ``mail.message`` que antes de la retención
        (luego el retenido no existe en ninguna parte). Sin la primera mitad,
        la segunda pasaría también en un canal ilegible.
        """
        published = self._post_as_user(self.channel_a, self.plain_employee, "published")
        before = self._channel_all_messages(self.channel_a)
        held = self._post_as_guest(self.channel_a, self.guest_1, "held")
        self.assertFalse(held, "el mensaje del visitante debe quedar retenido")
        self.assertEqual(
            self._channel_all_messages(self.channel_a),
            before,
            "la retención no puede añadir ni un mail.message al canal",
        )
        for label, spec in self.OUTSIDER_PERSONAS:
            with self.subTest(persona=label):
                self.assertIn(
                    published.id,
                    self._channel_messages(
                        self.channel_a, **self._persona_kwargs(spec)
                    ).ids,
                    "%s tiene que estar viendo el canal para que esto valga algo"
                    % label,
                )

    def test_the_author_guest_does_not_see_their_own_held_message_either(self):
        """Ni el propio autor: la retención no es un mensaje "sólo para mí".

        Su UI se entera por el bus (``BUS_AUTHOR_STATUS``), no por un
        ``mail.message`` a medias que el canal tendría que ocultar a los demás.
        """
        published = self._post_as_user(self.channel_a, self.plain_employee, "published")
        self._post_as_guest(self.channel_a, self.guest_1, "held")
        visible = self._channel_messages(self.channel_a, guest=self.guest_1)
        self.assertIn(published.id, visible.ids)
        self.assertEqual(
            set(visible.ids),
            set(self._channel_all_messages(self.channel_a).ids),
            "el autor no ve nada extra: el retenido no es un mail.message",
        )

    def test_no_mail_message_exists_at_all_after_a_hold(self):
        """La invariante de fondo, mirada sin ningún filtro de acceso.

        Las comprobaciones anteriores pasan por el control de acceso. Ésta mira
        la tabla directamente: si la retención dejase un ``mail.message``, no
        habría ``ir.rule`` que lo escondiese, porque ``mail.message`` no tiene
        ninguna y su acceso es por documento.
        """
        self._post_as_guest(self.channel_a, self.guest_1, "held")
        self.assertFalse(self._channel_all_messages(self.channel_a))

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.addons.base.models.ir_model")
    def test_public_user_cannot_read_pending_messages(self):
        self._post_as_guest(self.channel_a, self.guest_1, "held")
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        with self.assertRaises(AccessError):
            pending.with_user(self.public_user).read(["body"])

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.addons.base.models.ir_model")
    def test_portal_user_cannot_read_pending_messages(self):
        self._post_as_guest(self.channel_a, self.guest_1, "held")
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        with self.assertRaises(AccessError):
            pending.with_user(self.portal_user).read(["body"])

    @mute_logger("odoo.addons.base.models.ir_rule", "odoo.addons.base.models.ir_model")
    def test_internal_non_moderator_cannot_read_pending_messages(self):
        """El ACL sólo lo abre a los dos grupos del módulo, no a base.group_user."""
        self._post_as_guest(self.channel_a, self.guest_1, "held")
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        with self.assertRaises(AccessError):
            pending.with_user(self.plain_employee).read(["body"])

    def test_moderator_of_the_channel_does_see_the_queue(self):
        """Control positivo del lado moderador."""
        self._post_as_guest(self.channel_a, self.guest_1, "held")
        pending = self.Pending.with_user(self.moderator_a).search(
            [("channel_id", "=", self.channel_a.id)]
        )
        self.assertEqual(len(pending), 1)
        self.assertIn("held", pending.body)

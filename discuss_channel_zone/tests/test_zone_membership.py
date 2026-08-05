# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from .common import ZoneChannelMixin


@tagged("post_install", "-at_install")
class TestZoneMembership(ZoneChannelMixin, TransactionCase):
    """Quién acaba en qué canal, y por qué.

    Toda la lógica del módulo se reduce a una función --
    ``_get_chat_zone`` -- y a su proyección sobre la pertenencia. Aquí se
    prueba la función a través de su efecto observable, que es donde el
    usuario la nota: los canales en los que aparece sentado.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_zone_fixtures()

    def test_merchant_lands_in_general_and_own_zone_only(self):
        """El comerciante entra en el general y en SU barrio, en ninguno más.

        Es el caso central del producto y también el que más fácil se rompe al
        revés: un fallo que meta a todo el mundo en los cuatro canales pasaría
        cualquier aserción de "está en su barrio". Por eso la comparación es de
        igualdad exacta.
        """
        self.assertEqual(self.merchant._get_chat_zone(), "guanarteme")
        self.assertChannels(
            self.merchant,
            self.channel_general | self.channel_guanarteme,
        )

    def test_resident_without_company_uses_the_manual_zone(self):
        """El vecino sin negocio SÍ tiene barrio: el que él mismo eligió.

        La zona de un vecino no puede venir de una compañía porque no tiene
        ninguna que cuente, y dejarlo sólo en el canal general lo expulsaría de
        la conversación de su propio barrio. ``chat_zone`` es justamente esa
        pieza.
        """
        self.assertEqual(self.resident._get_chat_zone(), "tamaraceite")
        self.assertChannels(
            self.resident,
            self.channel_general | self.channel_tamaraceite,
        )

    def test_company_zone_beats_a_contradicting_manual_zone(self):
        """La compañía manda: el barrio de un negocio no es una preferencia.

        Si ganase el campo manual, cualquier comerciante podría sacarse de su
        barrio editando un desplegable de su perfil, y el canal de Guanarteme
        dejaría de ser "los negocios de Guanarteme" para pasar a ser "quien
        quiera". La precedencia se comprueba con los dos valores en conflicto a
        la vez, que es la única forma de distinguir "gana la compañía" de "el
        campo manual estaba vacío".
        """
        self.merchant.chat_zone = "lomolosfrailes"
        self.assertEqual(self.merchant.chat_zone, "lomolosfrailes")
        self.assertEqual(self.merchant._get_chat_zone(), "guanarteme")
        self.assertChannels(
            self.merchant,
            self.channel_general | self.channel_guanarteme,
            "escribir chat_zone no puede mover a un comerciante de barrio",
        )

    def test_platform_staff_gets_the_general_channel_only(self):
        """El equipo de la plataforma no vive en ningún barrio.

        Su compañía es ``base.main_company``, que
        ``_get_own_company_for_directory`` documenta como "de nadie": tratarla
        como un negocio más metería a todo el personal en el barrio que
        casualmente tuviera configurada la compañía de la plataforma.
        """
        self.assertEqual(self.staff._get_chat_zone(), "canarias")
        self.assertChannels(self.staff, self.channel_general)

    def test_user_with_neither_company_nor_manual_zone_gets_general_only(self):
        """Sin negocio y sin elección: canal general y nada más.

        Es el estado de toda cuenta recién registrada, así que es el caso más
        frecuente de todos. Tiene que resolverse sin barrio y sin error.
        """
        newcomer = self._create_portal_user("dcz_newcomer", self.main_company)
        self.assertEqual(newcomer._get_chat_zone(), "canarias")
        self.assertChannels(newcomer, self.channel_general)

    def test_public_user_has_no_zone_and_no_seat(self):
        """El visitante no tiene zona, y tampoco asiento en ningún canal.

        Que pueda LEER el canal general es cosa del grupo del canal, no de la
        pertenencia. Sentar al usuario público sería sentar a todos los
        visitantes anónimos del planeta en la misma fila.

        La segunda mitad exige activarlo. ``base.public_user`` está archivado
        en cualquier base real y ``_zone_syncable_users`` empieza por
        ``filtered("active")``: sin el ``active = True``, el conjunto se vacía
        ahí y ``_sync_zone_channels`` no llega nunca a la EXCLUSIÓN POR GRUPO,
        que es lo que esta prueba dice comprobar.
        """
        self.assertFalse(self.public_user._get_chat_zone())

        self.public_user.active = True
        self.assertFalse(
            self.public_user._zone_syncable_users(),
            "al usuario público lo saca el grupo, no el estar archivado",
        )
        self.assertEqual(
            self.public_user._sync_zone_channels(),
            {"added": 0, "removed": 0},
        )
        self.assertFalse(self._members_of(self.public_user))

    def test_seeded_channels_are_gated_as_designed(self):
        """El contrato de seguridad, leído en los propios datos sembrados.

        Si alguien quita el ``eval="False"`` del canal general,
        ``_compute_group_public_id`` le pone ``base.group_user`` y el canal
        "abierto a todo el mundo" se cierra hasta para los vecinos, sin que
        falle nada más. Este test es el que se entera.
        """
        self.assertFalse(
            self.channel_general.group_public_id,
            "el canal general tiene que quedar sin grupo para ser público",
        )
        for channel in (
            self.channel_guanarteme,
            self.channel_tamaraceite,
            self.channel_lomo,
        ):
            self.assertEqual(channel.group_public_id, self.zone_group)

    def test_zone_group_admits_registered_users_and_excludes_the_visitor(self):
        """El grupo elegido, comprobado contra las tres personas reales.

        Es la propiedad de la que cuelga todo el diseño y no se puede deducir
        de la lista de grupos del usuario a ojo: la regla
        ``ir_rule_discuss_channel_all`` lee ``user.all_group_ids``, o sea los
        grupos IMPLICADOS, que es donde vive la pertenencia de portal e
        interno a este grupo.
        """
        self.assertIn(self.zone_group, self.merchant.all_group_ids)
        self.assertIn(self.zone_group, self.staff.all_group_ids)
        self.assertNotIn(self.zone_group, self.public_user.all_group_ids)

    def test_all_four_channels_are_pre_moderated_for_guests(self):
        """Los cuatro canales llegan con la retención de visitantes puesta.

        El general es el único que un visitante alcanza hoy, pero los otros
        tres cargan la misma fila para que reabrir un barrio no pueda dejar,
        de paso, una puerta anónima sin moderar.
        """
        moderations = (
            self.env["discuss.channel.moderation"]
            .sudo()
            .search([("channel_id", "in", self.managed_channels.ids)])
        )
        self.assertEqual(len(moderations), 4)
        self.assertTrue(all(moderations.mapped("moderate_guests")))

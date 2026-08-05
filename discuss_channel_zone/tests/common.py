# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


class ZoneChannelMixin:
    """Escenario mínimo pero completo de la comunidad.

    Se define como mixin (y no como ``TransactionCase``) porque la suite de
    seguridad necesita ``HttpCase``: el mismo escenario tiene que servir para
    las dos bases sin duplicar el setup, igual que en
    ``discuss_channel_moderation``.

    El escenario tiene una compañía por barrio, un comerciante en cada una, un
    vecino SIN negocio y un miembro del equipo de la plataforma. Es el reparto
    mínimo con el que "la zona la manda la compañía, salvo que no haya
    compañía" se puede afirmar Y refutar.
    """

    @classmethod
    def _setup_zone_fixtures(cls):
        cls.main_company = cls.env.ref("base.main_company")
        cls.portal_group = cls.env.ref("base.group_portal")
        cls.internal_group = cls.env.ref("base.group_user")
        cls.public_user = cls.env.ref("base.public_user")
        cls.zone_group = cls.env.ref("discuss_channel_zone.group_zone_channel_member")
        cls.Member = cls.env["discuss.channel.member"]

        cls.channel_general = cls.env.ref("discuss_channel_zone.channel_canarias")
        cls.channel_guanarteme = cls.env.ref("discuss_channel_zone.channel_guanarteme")
        cls.channel_tamaraceite = cls.env.ref(
            "discuss_channel_zone.channel_tamaraceite"
        )
        cls.channel_lomo = cls.env.ref("discuss_channel_zone.channel_lomolosfrailes")
        cls.managed_channels = (
            cls.channel_general
            | cls.channel_guanarteme
            | cls.channel_tamaraceite
            | cls.channel_lomo
        )

        cls.company_guanarteme = cls.env["res.company"].create(
            {"name": "DCZ Panadería", "commercial_zone": "guanarteme"}
        )
        cls.company_tamaraceite = cls.env["res.company"].create(
            {"name": "DCZ Ferretería", "commercial_zone": "tamaraceite"}
        )

        cls.merchant = cls._create_portal_user(
            "dcz_merchant", company=cls.company_guanarteme
        )
        # El vecino NO tiene negocio, y "no tener negocio" en esta base de
        # datos es tener la compañía DE LA PLATAFORMA: ``company_id`` es
        # obligatorio en ``res.users``, así que nadie está literalmente sin
        # compañía. Que ``base.main_company`` no cuente como negocio es
        # exactamente lo que documenta
        # ``res.company._get_own_company_for_directory``.
        cls.resident = cls._create_portal_user(
            "dcz_resident", company=cls.main_company, chat_zone="tamaraceite"
        )
        cls.staff = cls.env["res.users"].create(
            {
                "name": "DCZ Staff",
                "login": "dcz_staff",
                "password": "dcz_staff",
                "email": "dcz_staff@example.com",
                "company_id": cls.main_company.id,
                "company_ids": [(6, 0, cls.main_company.ids)],
                "group_ids": [(6, 0, cls.internal_group.ids)],
            }
        )

    @classmethod
    def _create_portal_user(cls, login, company, chat_zone=False):
        """Usuario portal: es lo que son de verdad comerciantes y vecinos.

        La contraseña se fija igual que el login porque las pruebas HTTP
        necesitan autenticarse de verdad contra la ruta pública.
        """
        return cls.env["res.users"].create(
            {
                "name": "DCZ %s" % login,
                "login": login,
                "password": login,
                "email": "%s@example.com" % login,
                "company_id": company.id,
                "company_ids": [(6, 0, company.ids)],
                "group_ids": [(6, 0, cls.portal_group.ids)],
                "chat_zone": chat_zone,
            }
        )

    # ------------------------------------------------------------------
    # Aserciones sobre la pertenencia
    # ------------------------------------------------------------------

    def _members_of(self, user):
        """Filas de pertenencia del usuario en los CUATRO canales del módulo.

        Acotado a los canales que gestiona el módulo a propósito: ``mail``
        suscribe automáticamente a todo usuario interno a
        ``mail.channel_all_employees`` (``discuss.channel.group_ids``), así que
        un "no está en ningún sitio más" sin acotar estaría probando el
        comportamiento de otro módulo.
        """
        return (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("channel_id", "in", self.managed_channels.ids),
                    ("partner_id", "=", user.partner_id.id),
                ]
            )
        )

    def _channels_of(self, user):
        """Los canales del módulo en los que el usuario está sentado."""
        return self._members_of(user).channel_id

    def assertChannels(self, user, expected, msg=None):
        """Igualdad EXACTA de canales, no inclusión.

        ``assertIn`` dejaría pasar justo el fallo que importa: estar además en
        un barrio que no es el tuyo.
        """
        self.assertEqual(self._channels_of(user), expected, msg)

    def _channel_messages(self, channels):
        """Todo ``mail.message`` colgado de esos canales.

        Sirve para afirmar el silencio: entrar y salir de un canal de tipo
        ``channel`` no debe dejar ni un aviso de "se ha unido" / "ha salido".
        """
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", "discuss.channel"),
                    ("res_id", "in", channels.ids),
                ]
            )
        )

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from .common import ZoneChannelMixin


@tagged("post_install", "-at_install")
class TestZoneSync(ZoneChannelMixin, TransactionCase):
    """La proyección de la zona sobre la pertenencia: disparadores y deriva.

    Que la función esté bien (``test_zone_membership``) no basta: hay que
    volver a aplicarla cada vez que cambia una de sus entradas, y hay que
    poder re-aplicarla en masa sin que pase nada. Eso es lo que se prueba
    aquí.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_zone_fixtures()

    def test_changing_the_company_zone_moves_every_user_silently(self):
        """Mudar el negocio muda a TODA su gente, y sin ruido en el canal.

        Dos cosas en un solo test porque son la misma decisión de producto: el
        traslado tiene que ser completo (si sólo se moviera el primer usuario
        de la compañía, el segundo se quedaría leyendo el barrio equivocado) y
        tiene que ser mudo. Un canal comunitario que escupe "fulano se ha
        unido" cada vez que un comercio cambia de zona es un canal que la
        gente silencia.
        """
        colleague = self._create_portal_user("dcz_colleague", self.company_guanarteme)
        for user in (self.merchant, colleague):
            self.assertChannels(user, self.channel_general | self.channel_guanarteme)

        messages_before = self._channel_messages(self.managed_channels)
        self.company_guanarteme.commercial_zone = "tamaraceite"

        for user in (self.merchant, colleague):
            self.assertChannels(
                user,
                self.channel_general | self.channel_tamaraceite,
                "cambiar la zona de la compañía mueve a todos sus usuarios",
            )
        self.assertEqual(
            self._channel_messages(self.managed_channels),
            messages_before,
            "entrar o salir de un canal no puede dejar ni un mensaje",
        )

    def test_writing_the_manual_zone_reseats_the_resident(self):
        """Cambiar de barrio a mano surte efecto en el acto.

        El vecino que se muda de barrio no puede quedarse en el canal del
        anterior hasta la noche: el disparador de ``write`` existe justo para
        esto.
        """
        self.resident.chat_zone = "lomolosfrailes"
        self.assertChannels(self.resident, self.channel_general | self.channel_lomo)

    def test_an_unrelated_write_does_not_touch_membership(self):
        """Escribir cualquier otro campo no dispara ningún barrido.

        ``res.users.write`` se ejecuta en cada login (``login_date``). Si el
        disparador no filtrase por campo, cada inicio de sesión pagaría un
        recorrido de la pertenencia.
        """
        members_before = self._members_of(self.merchant)
        self.merchant.write({"name": "DCZ Panadería Nueva"})
        self.assertEqual(self._members_of(self.merchant), members_before)

    def test_sync_is_idempotent(self):
        """Ejecutarlo dos veces no escribe NADA la segunda.

        La idempotencia es lo que permite colgarlo de ``create``, de ``write``
        y de un cron nocturno a la vez. Se comprueba de dos formas porque una
        sola engaña: los IDS de pertenencia tienen que ser los mismos (borrar y
        volver a crear daría el mismo conjunto de canales con filas nuevas) y
        los contadores devueltos tienen que ser cero (el propio método
        declarando que no tuvo nada que corregir).
        """
        users = self.merchant | self.resident | self.staff
        users._sync_zone_channels()
        member_ids = self._members_of(self.merchant).ids
        member_ids += self._members_of(self.resident).ids

        counters = users._sync_zone_channels()

        self.assertEqual(counters, {"added": 0, "removed": 0})
        second_pass = self._members_of(self.merchant).ids
        second_pass += self._members_of(self.resident).ids
        self.assertEqual(
            second_pass,
            member_ids,
            "las mismas filas, no filas equivalentes",
        )

    def test_sync_reports_and_repairs_drift(self):
        """La deriva se detecta y se corrige, y el método la cuenta.

        Es el escenario del cron: alguien salió del canal a mano desde Discuss,
        o una migración dejó una fila de más. Los contadores son además la
        línea de log del cron, así que probarlos es probar lo que un
        administrador va a leer.
        """
        self._members_of(self.merchant).unlink()
        self.env["discuss.channel.member"].sudo().create(
            {
                "channel_id": self.channel_lomo.id,
                "partner_id": self.merchant.partner_id.id,
            }
        )

        counters = self.merchant._sync_zone_channels()

        self.assertEqual(counters, {"added": 2, "removed": 1})
        self.assertChannels(
            self.merchant, self.channel_general | self.channel_guanarteme
        )

    def test_legacy_zone_spelling_is_normalised(self):
        """La grafía antigua del barrio sigue llevando al canal correcto.

        La base migrada guarda ``lomo_los_frailes`` junto a la clave canónica
        -- por eso existe ``ZONE_ALIASES`` -- y el ORM sólo valida un Selection
        al ESCRIBIR: una fila heredada se lee tal cual. Se fuerza por SQL
        precisamente porque por el ORM ese valor no se puede escribir, que es
        la razón de que el problema exista sólo en producción.
        """
        self.assertEqual(
            self.env["res.users"]._zone_channel("lomo los frailes"),
            self.channel_lomo,
        )

        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_company SET commercial_zone = %s WHERE id = %s",
            ("lomo_los_frailes", self.company_guanarteme.id),
        )
        self.env.invalidate_all()

        self.assertEqual(self.merchant._get_chat_zone(), "lomolosfrailes")
        self.merchant._sync_zone_channels()
        self.assertChannels(self.merchant, self.channel_general | self.channel_lomo)

    def test_archiving_the_company_falls_back_to_the_manual_zone(self):
        """Un negocio dado de baja devuelve a su gente al barrio que eligieron.

        Es la mitad no probada de la regla de "compañía usable"
        (``res.company._get_own_company_for_directory``): que una compañía
        ARCHIVADA no cuenta como negocio. Sin esta prueba, quitar el
        ``search`` por ``browse`` en ``_get_chat_zones`` -- que parece un
        ahorro de una consulta -- dejaría a los comerciantes de un negocio
        cerrado atados para siempre al canal de un barrio en el que ya no
        opera nadie, y ninguna prueba se enteraría.

        Se archiva por SQL porque es el ÚNICO camino real: el ORM se niega a
        archivar una compañía que es la compañía por defecto de algún usuario,
        y ese es justamente el caso que llega a producción por otras vías --
        una migración, un script de bajas, un restore. Mismo motivo y misma
        técnica que ``test_legacy_zone_spelling_is_normalised``.
        """
        # Con la compañía activa manda ella, con el campo manual en contra:
        # es la línea base sin la cual el cambio de abajo no prueba nada.
        self.merchant.chat_zone = "lomolosfrailes"
        self.assertEqual(self.merchant._get_chat_zone(), "guanarteme")
        self.assertChannels(
            self.merchant, self.channel_general | self.channel_guanarteme
        )

        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_company SET active = FALSE WHERE id = %s",
            (self.company_guanarteme.id,),
        )
        self.env.invalidate_all()

        self.assertEqual(
            self.merchant._get_chat_zone(),
            "lomolosfrailes",
            "una compañía archivada no es un negocio: manda el campo manual",
        )
        self.assertEqual(
            self.merchant._sync_zone_channels(),
            {"added": 1, "removed": 1},
            "la mudanza es una entrada y una salida, no un alta suelta",
        )
        self.assertChannels(self.merchant, self.channel_general | self.channel_lomo)

    def test_cron_does_not_reseat_an_archived_user(self):
        """Una cuenta desactivada no vuelve a los canales por la puerta de atrás.

        Desactivar a alguien y encontrárselo de vuelta en el chat a la mañana
        siguiente convertiría el cron en un desactivador de bajas. El cron
        recorre sólo cuentas activas.
        """
        self._members_of(self.merchant).unlink()
        self.merchant.active = False

        self.env["res.users"]._cron_sync_zone_channels()

        self.assertFalse(
            self._members_of(self.merchant),
            "el cron no sienta a usuarios archivados",
        )

    def test_cron_batches_and_reconciles_everyone(self):
        """El cron corrige a todo el mundo, y lo hace por lotes.

        El tamaño de lote se pasa explícitamente para que el bucle se recorra
        de verdad con los usuarios de la prueba: con el valor por defecto (500)
        siempre habría una sola pasada y el troceado quedaría sin ejercitar.

        El contador se comprueba con ``>=`` y no con ``==`` a propósito: el
        cron recorre TODA la plataforma, así que el número exacto depende de
        las cuentas que haya en la base. La cifra exacta se afirma en
        ``test_sync_reports_and_repairs_drift``, que sí está acotado a un
        usuario.
        """
        self._members_of(self.merchant).unlink()
        self._members_of(self.resident).unlink()

        totals = self.env["res.users"]._cron_sync_zone_channels(batch_size=1)

        self.assertGreaterEqual(totals["added"], 4)
        self.assertChannels(
            self.merchant, self.channel_general | self.channel_guanarteme
        )
        self.assertChannels(
            self.resident, self.channel_general | self.channel_tamaraceite
        )

    def test_the_public_user_is_never_seated_by_the_cron(self):
        """Ni el cron ni nada sienta al usuario público.

        Es la contraparte de la propiedad de seguridad: el visitante lee el
        canal general por grupo, no por pertenencia, y sentarlo sería sentar a
        todos los anónimos en una sola fila compartida.

        ``active = True`` A PROPÓSITO, y es lo que hace que este test exista.
        ``base.public_user`` viene archivado en cualquier base real, y el cron
        hace ``search([])`` con el active_test por defecto: sin activarlo, el
        usuario público ni siquiera entra en el recorrido y la aserción de
        abajo no puede fallar por más que se rompa la EXCLUSIÓN POR GRUPO, que
        es la pieza que aquí se quiere probar. Se comprueban las tres capas por
        separado -- la zona, el filtro y los contadores -- porque un cero al
        final no distingue "lo excluyó el filtro" de "no llegó a mirarlo".
        """
        self.public_user.active = True

        self.assertFalse(
            self.public_user._get_chat_zone(),
            "el usuario público no tiene zona ni estando activo",
        )
        self.assertFalse(
            self.public_user._zone_syncable_users(),
            "la exclusión por grupo lo saca aunque el filtro activo no lo haga",
        )
        # Acotado al usuario público: los contadores del cron entero dependen
        # de cuántas cuentas tenga la base (por eso
        # ``test_cron_batches_and_reconciles_everyone`` usa ``>=``), así que la
        # cifra exacta sólo se puede afirmar sobre un usuario.
        self.assertEqual(
            self.public_user._sync_zone_channels(),
            {"added": 0, "removed": 0},
            "sincronizar al usuario público no puede escribir nada",
        )

        self.env["res.users"]._cron_sync_zone_channels()
        self.assertFalse(self._members_of(self.public_user))

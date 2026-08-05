# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from .common import DiscussModerationHttpMixin, DiscussModerationMixin

# Lo que devolvería el fetcher del core si el atacante hubiese cambiado los
# ``og:`` de su página DESPUÉS de que el moderador aprobase el enlace.
ATTACKER_URL = "https://attacker.example/innocent"
ATTACKER_OG = {
    "og_title": "LINKPREVIEW-ATTACKER-TITLE",
    "og_description": "LINKPREVIEW-ATTACKER-DESCRIPTION",
    "og_image": "https://attacker.example/LINKPREVIEW-ATTACKER-BEACON.png",
    "og_site_name": "LINKPREVIEW-ATTACKER-SITE",
    "og_type": "website",
    "og_mimetype": "image/png",
    "source_url": ATTACKER_URL,
}

# Sólo estos campos se afirman contra lo servido: cada uno lleva una marca
# irrepetible. ``og_type`` ("website") y ``og_mimetype`` ("image/png") quedan
# fuera a propósito porque son cadenas genéricas que aparecen por su cuenta en
# cualquier ``Store`` -- afirmarlas daría un verde o un rojo por casualidad.
MARKED_FIELDS = ("og_title", "og_description", "og_image", "og_site_name")

# Los DOS modelos por los que una ficha puede llegar al lector. ``Store`` agrupa
# lo servido por nombre de modelo (``mail/tools/discuss.py:200-208``) y
# ``mail.message.link.preview._to_store_defaults``
# (``mail/models/mail_message_link_preview.py:40-44``) arrastra su
# ``link_preview_id``, así que si naciera una tarjeta AMBAS claves estarían en la
# respuesta.
#
# Se afirma sobre estas claves y NO sobre la respuesta entera. La URL desnuda
# SIGUE en el cuerpo a propósito -- ``models/mail_link_preview.py:52-56`` lo
# documenta: "the link itself still renders as an ordinary clickable anchor" --
# porque es el enlace que el moderador leyó y aprobó. Lo que se suprime es la
# decoración, no el enlace, así que buscar ``ATTACKER_URL`` en todo lo servido
# afirmaba lo contrario de lo que el módulo promete.
PREVIEW_MODELS = ("mail.link.preview", "mail.message.link.preview")

# El módulo donde ``get_link_preview_from_url`` está IMPORTADO, que es donde hay
# que parchearlo: ``mail/models/mail_link_preview.py:13`` lo trae al espacio de
# nombres del modelo, así que parchear ``mail.tools.link_preview`` no lo tocaría.
FETCHER = "odoo.addons.mail.models.mail_link_preview.get_link_preview_from_url"


@tagged("post_install", "-at_install")
class TestModerationLinkPreview(
    DiscussModerationMixin, DiscussModerationHttpMixin, HttpCase
):
    """La puerta que se abre DESPUÉS de aprobar, y ya no se cierra.

    ``/mail/link_preview`` es ``auth="public"`` y su única comprobación es
    ``is_current_user_or_guest_author`` (mail/controllers/link_preview.py:18).
    Tras UNA aprobación el visitante ES el autor, así que puede pedir una
    previsualización cuando quiera, y lo que se guarda -- ``og_title``,
    ``og_description``, ``og_image``, ``og_site_name`` -- lo dicta el servidor
    del enlace, no el mensaje que el moderador leyó.

    Es peor que una fuga puntual, por dos motivos que estas pruebas fijan:

    - ``og_image`` se guarda como URL y la re-pide el NAVEGADOR DE CADA LECTOR
      en cada visita: un hueco de imagen vivo y nunca revisado, más un faro de
      IPs sobre todo el que lee el canal.
    - ``get_link_preview_from_url`` (mail/tools/link_preview.py:10-37) hace un
      ``requests.get`` con redirecciones y sin filtro de host ni de IP sobre una
      URL que elige una persona no confiable: SSRF.

    Por eso el fetcher se PARCHEA en vez de dejarlo salir a la red: además de
    hacer la prueba determinista, permite afirmar que NO SE LLAMÓ, que es la
    única forma de comprobar el SSRF sin montar un servidor cómplice.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()

    def _link_body(self, text="un enlace"):
        return '<p>mira esto <a href="%s">%s</a></p>' % (ATTACKER_URL, text)

    def _approved_message_with_link(self, channel, moderator=None):
        """Publica un mensaje del visitante con un enlace de aspecto inocente.

        Es el paso 2 del ataque observado: el moderador lee el CUERPO, ve un
        enlace normal y aprueba. Lo que la página devuelva más tarde no formó
        parte de esa decisión.
        """
        self._post_over_http(channel, self.guest_1, body=self._link_body())
        pending = self.Pending.search([("channel_id", "=", channel.id)])
        pending.with_user(moderator or self.moderator_a).action_approve()
        self.env.flush_all()
        return pending.message_id

    def _assert_not_served(self, channel, guest, label):
        """Ni una marca del atacante, ni una sola fila de ficha.

        Las dos mitades hacen falta. Las marcas cazan el contenido concreto que
        el atacante puso; las claves de ``PREVIEW_MODELS`` cazan la ESTRUCTURA,
        y son las que siguen siendo verdad el día que alguien cambie los ``og:``
        del payload de prueba. El control positivo de abajo afirma las mismas
        claves en positivo, que es lo que impide que esto sea una comprobación
        vacía.
        """
        data = self._fetch_over_http(channel, guest)["data"]
        served = str(data)
        for field in MARKED_FIELDS:
            self.assertNotIn(
                ATTACKER_OG[field],
                served,
                "%s no puede recibir %s" % (label, field),
            )
        for model in PREVIEW_MODELS:
            self.assertFalse(
                data.get(model),
                "%s tampoco recibe ninguna fila de %s" % (label, model),
            )

    # ------------------------------------------------------------------
    # El PoC
    # ------------------------------------------------------------------

    def test_author_cannot_grow_a_preview_after_approval(self):
        """El PoC completo: postear, aprobar, pedir previsualización, mirar.

        Se comprueban cuatro cosas a la vez, porque cerrar sólo una deja el
        agujero en pie: no se hace la petición saliente (SSRF), no nace la
        ficha, no nace el vínculo con el mensaje, y ningún tercero -- ni otro
        visitante ni un anónimo -- recibe un solo byte del atacante.
        """
        message = self._approved_message_with_link(self.channel_a)
        with patch(FETCHER, return_value=dict(ATTACKER_OG)) as fetcher:
            self._link_preview_over_http(message, self.guest_1)
        self.env.invalidate_all()
        fetcher.assert_not_called()
        self.assertFalse(
            self.env["mail.link.preview"].search([("source_url", "=", ATTACKER_URL)]),
            "no se llega a guardar la ficha del atacante",
        )
        self.assertFalse(
            self.env["mail.message.link.preview"]
            .sudo()
            .search([("message_id", "=", message.id)]),
            "y el mensaje aprobado no gana ninguna tarjeta",
        )
        for label, guest in (("otro visitante", self.guest_2), ("anónimo", None)):
            with self.subTest(persona=label):
                self._assert_not_served(self.channel_a, guest, label)

    def test_control_a_free_channel_does_serve_the_preview(self):
        """Control positivo: la cadena entera FUNCIONA, lo que la frena es la moderación.

        Sin esto, todas las aserciones de arriba pasarían igual si la ruta
        estuviese rota, si el parche no llegase al sitio correcto o si
        ``message_link_preview_ids`` hubiese dejado de servirse: no se vería
        nada porque no hay nada, no porque la puerta cierre.
        """
        result = self._post_over_http(
            self.channel_free, self.guest_1, body=self._link_body()
        )
        message = self.env["mail.message"].browse(result["message_id"])
        with patch(FETCHER, return_value=dict(ATTACKER_OG)) as fetcher:
            self._link_preview_over_http(message, self.guest_1)
        self.env.invalidate_all()
        fetcher.assert_called()
        data = self._fetch_over_http(self.channel_free, self.guest_2)["data"]
        served = str(data)
        self.assertIn(
            ATTACKER_OG["og_title"],
            served,
            "en un canal sin moderar la tarjeta sí llega al tercero",
        )
        self.assertIn(
            ATTACKER_OG["og_image"],
            served,
            "incluida la URL de imagen que el navegador del lector re-pedirá",
        )
        for model in PREVIEW_MODELS:
            self.assertTrue(
                data.get(model),
                "y viaja bajo la clave %s, que es la que mira _assert_not_served"
                % model,
            )

    def test_a_held_message_is_not_reachable_by_the_preview_route(self):
        """Una previsualización sobre una retención delataría la retención misma.

        La fila retenida no es un ``mail.message``, así que la ruta no tiene
        nada que buscar: esta prueba fija esa propiedad para que nadie la rompa
        "dando de alta" el mensaje antes de aprobarlo. Si existiese, un tercero
        sabría que hay un mensaje pendiente y, con la tarjeta, buena parte de su
        contenido.
        """
        self._post_over_http(self.channel_a, self.guest_1, body=self._link_body())
        pending = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        self.assertEqual(pending.state, "pending")
        self.assertFalse(
            self._channel_all_messages(self.channel_a),
            "no hay ningún mail.message al que una previsualización pueda colgarse",
        )
        unreachable = self.env["mail.message"].browse(
            self.env["mail.message"].search([], order="id desc", limit=1).id + 1000
        )
        with patch(FETCHER, return_value=dict(ATTACKER_OG)) as fetcher:
            self._link_preview_over_http(unreachable, self.guest_1)
        self.env.invalidate_all()
        fetcher.assert_not_called()
        self.assertFalse(
            self.env["mail.link.preview"].search([("source_url", "=", ATTACKER_URL)])
        )

    def test_the_wall_holds_when_the_route_is_bypassed(self):
        """El modelo, no la ruta: crear el vínculo a mano tampoco publica nada.

        ``_create_from_message_and_notify`` es hoy el único que crea estas
        filas, pero el módulo no apuesta por eso: la comprobación vive también
        en ``mail.message.link.preview.create``, que es lo que hace correcto a
        cualquier lector presente o futuro de ``message_link_preview_ids``.
        """
        message = self._approved_message_with_link(self.channel_a)
        preview = self.env["mail.link.preview"].create(dict(ATTACKER_OG))
        linked = self.env["mail.message.link.preview"].create(
            {"message_id": message.id, "link_preview_id": preview.id, "sequence": 0}
        )
        self.assertFalse(linked, "el vínculo se descarta en vez de crearse")
        self._assert_not_served(self.channel_a, self.guest_2, "otro visitante")

    def test_a_sub_channel_inherits_the_preview_rule(self):
        """Abrir un hilo bajo un canal moderado no crea un sitio sin reglas.

        Va aquí y no en el suite de alcance porque la regla de previsualización
        es POR CANAL y no por persona: si la herencia se rompiese, es la primera
        que lo notaría.
        """
        sub_channel = self.channel_a._create_sub_channel(name="Hilo")
        message = self._approved_message_with_link(sub_channel)
        with patch(FETCHER, return_value=dict(ATTACKER_OG)) as fetcher:
            self._link_preview_over_http(message, self.guest_1)
        self.env.invalidate_all()
        fetcher.assert_not_called()
        self._assert_not_served(sub_channel, self.guest_2, "otro visitante")

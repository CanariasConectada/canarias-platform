# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.discuss_channel_moderation.tests.common import (
    DiscussModerationHttpMixin,
)

from .common import ZoneChannelMixin

# QUÉ puerta contestó, no si contestó alguna.
#
# ``make_jsonrpc_request`` mete en el mensaje de ``JsonRpcException``
# ``error["data"]["name"]`` (odoo/tests/common.py:2566-2571), que
# ``serialize_exception`` rellena con ``"<módulo>.<clase>"``
# (odoo/http.py:459-469). Es el único dato por el que se puede saber, desde
# fuera y por HTTP, cuál de las paredes respondió.
#
# Este módulo espera ESTA y no otra: el controlador de ``/discuss/channel/...``
# empieza por un ``search`` sobre ``discuss.channel``, así que un canal que la
# regla de registro filtra no llega a existir para esa petición y el
# controlador levanta ``NotFound`` -- un 404 de verdad, no un ``AccessError``
# enmascarado. Comprobar sólo que la petición aborta dejaría pasar un 404 de
# una ruta renombrada, una sesión caducada o un fallo de biblioteca, y estas
# tres pruebas SON la propiedad de seguridad del módulo: si pasan por el motivo
# equivocado, la afirmación central se queda sin probar.
#
# Las constantes de las otras paredes (``AccessError``, ``UserError``,
# ``SessionExpiredException``) ya viven en
# ``discuss_channel_moderation/tests/common.py``; aquí sólo se añade la que
# aquel módulo no necesita.
JSONRPC_NOT_FOUND = "werkzeug.exceptions.NotFound"


@tagged("post_install", "-at_install")
class TestZoneGuestAccess(ZoneChannelMixin, HttpCase):
    """LA propiedad de seguridad del módulo, atacada por las rutas reales.

    El diseño entero se apoya en una frase: el visitante entra en el canal
    general y NO entra en los de barrio. Probarlo por el ORM no valdría: el
    ORM se llama con ``sudo()`` en media docena de sitios y con el entorno de
    pruebas como usuario, así que un canal mal cerrado seguiría contestando.
    Lo que decide de verdad es la regla ``ir_rule_discuss_channel_all``
    aplicada dentro de una petición ``auth="public"``, y eso sólo se ve
    entrando por ``/discuss/channel/messages`` y ``/mail/message/post``.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_zone_fixtures()
        cls.guest = cls.env["mail.guest"].create({"name": "DCZ Visitante"})

    # ------------------------------------------------------------------
    # Helpers de sesión
    # ------------------------------------------------------------------

    # EL MISMO helper de la suite hermana, no una copia suya: es el objeto
    # función de ``DiscussModerationHttpMixin._assert_refused_with``, prestado
    # tal cual. ``discuss_channel_zone`` depende de ``discuss_channel_moderation``
    # de forma dura (__manifest__.py), así que el import está garantizado allá
    # donde este test puede correr.
    #
    # Se toma el método suelto y NO se hereda el mixin entero a propósito: ese
    # mixin trae su propio ``_fetch_over_http``, ``_post_over_http`` y
    # ``_cookies_for``, con la misma FIRMA y distinta semántica que los de esta
    # suite. Heredarlo dejaría cuatro colisiones de nombre resueltas por MRO,
    # que es exactamente la clase de trampa silenciosa que estas pruebas
    # existen para evitar.
    _assert_refused_with = DiscussModerationHttpMixin._assert_refused_with

    def _forget_guest_cookie(self):
        """Deja la sesión HTTP SIN cookie de visitante.

        ``self.opener`` es una sesión persistente: sin esto, "sin visitante"
        sería en realidad "con el visitante que dejó la petición anterior", y
        el caso anónimo puro no se estaría probando. Sólo se retira la cookie
        del visitante; la del cursor de pruebas tiene que sobrevivir.
        """
        self.opener.cookies.pop(self.env["mail.guest"]._cookie_name, None)

    def _cookies_for(self, guest):
        """Cookies de la persona, limpiando la sesión cuando no hay visitante.

        Formato ``<id>|<access_token>``
        (mail/models/discuss/mail_guest.py:50-60). ``access_token`` está
        protegido por ``base.group_system``, de ahí el ``sudo``.
        """
        if not guest:
            self._forget_guest_cookie()
            return None
        return {
            self.env["mail.guest"]._cookie_name: "%s|%s"
            % (guest.id, guest.sudo().access_token)
        }

    def _fetch_over_http(self, channel, guest=None):
        """Lo que ``/discuss/channel/messages`` le sirve a esa persona.

        La ruta empieza por un ``search`` sobre ``discuss.channel``
        (mail/controllers/discuss/channel.py:90), o sea que es la regla de
        registro la que decide, y un canal no visible sale por 404.
        """
        return self.make_jsonrpc_request(
            "/discuss/channel/messages",
            {"channel_id": channel.id},
            cookies=self._cookies_for(guest),
        )

    def _post_over_http(self, channel, guest=None, body="hola vecinos"):
        """Publica por ``/mail/message/post``, que es ``auth="public"``."""
        return self.make_jsonrpc_request(
            "/mail/message/post",
            {
                "thread_model": "discuss.channel",
                "thread_id": channel.id,
                "post_data": {
                    "body": body,
                    "message_type": "comment",
                    "subtype_xmlid": "mail.mt_comment",
                },
            },
            cookies=self._cookies_for(guest),
        )

    def _pending_of(self, channel, guest):
        return (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search([("channel_id", "=", channel.id), ("guest_id", "=", guest.id)])
        )

    # ------------------------------------------------------------------
    # El visitante SÍ en el general
    # ------------------------------------------------------------------

    def test_guest_can_read_the_general_channel(self):
        """El visitante lee el canal general sin cuenta y sin asiento.

        Sin pertenencia ninguna: para ``channel_type == "channel"`` la regla
        ni siquiera mira ``is_member``, sólo el grupo. Es lo que permite que
        el canal de la plataforma se vea desde la web pública.
        """
        self.authenticate(None, None)
        result = self._fetch_over_http(self.channel_general, self.guest)
        self.assertIn("messages", result)

    def test_guest_can_post_in_the_general_channel(self):
        """El visitante puede publicar en el general: entra, pero moderado.

        "Puede publicar" aquí significa que la ruta lo ACEPTA (no hay 404: el
        canal es alcanzable y el mensaje llega a ``message_post``). Que el
        texto no aparezca todavía es la pre-moderación de
        ``discuss_channel_moderation`` haciendo su trabajo, y por eso la
        prueba de que el mensaje entró es la fila retenida: sin acceso al
        canal no habría ni eso.
        """
        self.authenticate(None, None)
        result = self._post_over_http(self.channel_general, self.guest)

        self.assertFalse(
            result["message_id"],
            "el mensaje de un visitante queda retenido, no publicado",
        )
        pending = self._pending_of(self.channel_general, self.guest)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending.state, "pending")

    def test_anonymous_session_without_any_cookie_reaches_the_general_channel(
        self,
    ):
        """Sin NINGUNA cookie tampoco hace falta cuenta.

        La persona menos identificada de todas -- usuario público pelado, sin
        cookie de visitante -- es la que de verdad prueba que el canal está
        abierto por grupo. Es también el caso que la sesión persistente de
        ``HttpCase`` falsearía si no se limpiara la cookie.
        """
        self.authenticate(None, None)
        result = self._fetch_over_http(self.channel_general, guest=None)
        self.assertIn("messages", result)

    # ------------------------------------------------------------------
    # El visitante NO en los barrios
    # ------------------------------------------------------------------

    @mute_logger("odoo.http")
    def test_guest_cannot_read_a_zone_channel(self):
        """EL test del módulo: el barrio no existe para un visitante.

        ``group_public_id`` apunta al grupo de miembros registrados, que
        ``base.group_public`` no implica, así que
        ``group_public_id IN user.all_group_ids`` es falso para toda petición
        anónima. La regla filtra el canal del ``search`` y el controlador
        levanta ``NotFound``: 404, no un canal vacío.

        Se fija el nombre serializado de la excepción, no sólo el hecho de que
        la petición aborte: 404 es la respuesta correcta y es distinta de un
        ``AccessError``, que significaría que el canal SÍ salió del ``search``
        y lo paró otra pared después.
        """
        self.authenticate(None, None)
        for channel in (
            self.channel_guanarteme,
            self.channel_tamaraceite,
            self.channel_lomo,
        ):
            with self.subTest(channel=channel.name):
                with self._assert_refused_with(
                    JSONRPC_NOT_FOUND,
                    "el canal de barrio no debe EXISTIR para un visitante",
                ):
                    self._fetch_over_http(channel, self.guest)

    @mute_logger("odoo.http")
    def test_anonymous_session_cannot_read_a_zone_channel(self):
        """Y sin cookie de visitante, tampoco.

        Quitar la cookie no es un caso menos capaz sino uno distinto: si el
        cierre dependiera de la identidad del visitante en lugar del grupo del
        usuario de sesión, este caso se colaría.
        """
        self.authenticate(None, None)
        with self._assert_refused_with(
            JSONRPC_NOT_FOUND,
            "sin cookie de visitante el barrio tampoco existe",
        ):
            self._fetch_over_http(self.channel_guanarteme, guest=None)

    @mute_logger("odoo.http")
    def test_guest_cannot_post_in_a_zone_channel(self):
        """Tampoco puede escribir en un barrio.

        Leer y escribir son dos puertas distintas y las dos pasan por el mismo
        ``search``: cerrar sólo la de lectura dejaría a un anónimo metiendo
        texto en la cola de moderación de un barrio al que no pertenece.

        El nombre exacto importa el doble aquí: un ``NotFound`` dice que la
        petición murió en el ``search``, ANTES de llegar a ``message_post``. Si
        contestara la moderación en vez de la regla de registro, la cola de
        abajo también estaría vacía y la prueba pasaría igual.
        """
        self.authenticate(None, None)
        with self._assert_refused_with(
            JSONRPC_NOT_FOUND,
            "publicar en un barrio ajeno tiene que morir en el search",
        ):
            self._post_over_http(self.channel_guanarteme, self.guest)
        self.assertFalse(self._pending_of(self.channel_guanarteme, self.guest))

    # ------------------------------------------------------------------
    # El vecino registrado SÍ en su barrio
    # ------------------------------------------------------------------

    def test_portal_user_can_read_a_zone_channel(self):
        """El control positivo, sin el cual lo anterior no prueba nada.

        Un canal que nadie puede leer también daría 404 al visitante. Este es
        el test que distingue "cerrado al anónimo" de "roto para todos", y el
        que justifica el grupo elegido: un usuario PORTAL, que no tiene
        ``base.group_user``, entra igualmente porque
        ``base.group_portal`` implica el grupo del canal.
        """
        self.authenticate("dcz_merchant", "dcz_merchant")
        self._forget_guest_cookie()
        result = self._fetch_over_http(self.channel_guanarteme, guest=None)
        self.assertIn("messages", result)

    def test_portal_user_can_read_a_zone_channel_that_is_not_theirs(self):
        """La pertenencia decide el barrio propio, no el permiso de lectura.

        Es una decisión de producto explícita: los canales de barrio están
        cerrados a los visitantes, no compartimentados entre vecinos. Se
        afirma aquí para que quede dicho: si algún día hacen falta barrios
        estancos, la regla de registro NO basta y hará falta otra cosa.
        """
        self.authenticate("dcz_resident", "dcz_resident")
        self._forget_guest_cookie()
        result = self._fetch_over_http(self.channel_guanarteme, guest=None)
        self.assertIn("messages", result)

    def test_internal_user_can_read_a_zone_channel(self):
        """El personal interno también entra, aunque no sea de ningún barrio.

        Si el canal se hubiera cerrado con ``base.group_portal`` -- el atajo
        evidente -- este caso fallaría: un usuario interno no tiene ese grupo.
        """
        self.authenticate("dcz_staff", "dcz_staff")
        self._forget_guest_cookie()
        result = self._fetch_over_http(self.channel_tamaraceite, guest=None)
        self.assertIn("messages", result)

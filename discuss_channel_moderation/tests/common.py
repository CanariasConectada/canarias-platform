# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from contextlib import contextmanager

from odoo.http import Request
from odoo.tests.common import JsonRpcException

# QUÉ candado saltó, no si saltó alguno.
#
# ``make_jsonrpc_request`` mete en el mensaje de ``JsonRpcException``
# ``error["data"]["name"]`` (odoo/tests/common.py:2566-2571), y
# ``serialize_exception`` rellena ese campo con ``"<módulo>.<clase>"``
# (odoo/http.py:459-469). Comparar contra estos nombres es la ÚNICA forma de
# comprobar por HTTP cuál de las paredes contestó.
#
# Hace falta porque ``assertRaises(JsonRpcException)`` a secas se conforma con
# cualquier cosa que aborte la petición: un fichero ilegible, una cookie que
# dejó de valer, un 404 de una ruta que ya no encuentra el registro. Una prueba
# de seguridad que pasa por el motivo equivocado es peor que una que falla,
# porque nadie va a mirarla.
JSONRPC_ACCESS_ERROR = "odoo.exceptions.AccessError"
JSONRPC_USER_ERROR = "odoo.exceptions.UserError"
# ``auth="user"`` con una sesión pública o de visitante NO llega al ORM: falla
# en la autenticación, antes de cualquier ACL o regla de registro
# (``_auth_method_user``, odoo/addons/base/models/ir_http.py:257-259, y
# ``_authenticate_explicit`` la re-lanza tal cual, línea 285-286).
JSONRPC_SESSION_EXPIRED = "odoo.http.SessionExpiredException"


class DiscussModerationMixin:
    """Fixtures compartidos por las suites de moderación.

    Se define como mixin (y no como ``TransactionCase``) porque la suite de
    abusos necesita ``HttpCase``: así el mismo escenario sirve para ambas
    bases sin duplicar el setup.

    Escenario: dos canales moderados (A y B) con moderadores DISTINTOS -- es lo
    que permite probar el aislamiento de colas -- y un tercer canal sin
    moderación que actúa de control negativo.
    """

    @classmethod
    def _setup_moderation_fixtures(cls):
        cls.public_user = cls.env.ref("base.public_user")
        cls.Pending = cls.env["discuss.channel.pending.message"]
        cls.Moderation = cls.env["discuss.channel.moderation"]

        # ``group_public_id = False`` EXPLÍCITO. Omitirlo NO deja el canal
        # abierto: ``_compute_group_public_id``
        # (mail/models/discuss/discuss_channel.py:352-358) rellena
        # ``base.group_user`` en cuanto el ``channel_type`` es "channel", y la
        # regla ``ir_rule_discuss_channel_all``
        # (mail/security/mail_security.xml:15-26) sólo abre el canal cuando
        # ``group_public_id`` es False o está entre los grupos del usuario. Un
        # canal así no lo ve ni un visitante ni un portal: la ruta pública
        # responde 404 y las pruebas de visibilidad pasan por vacías, viendo
        # nada porque no hay nada que ver, no porque la retención funcione.
        #
        # El campo es ``compute`` con ``readonly=False`` y ``store=True``, así
        # que pasarlo en el ``create`` lo protege del cálculo
        # (odoo/orm/models.py:4682-4686): el False sobrevive.
        cls.channel_a, cls.channel_b, cls.channel_free = cls.env[
            "discuss.channel"
        ].create(
            [
                {
                    "name": "Moderated A",
                    "channel_type": "channel",
                    "group_public_id": False,
                },
                {
                    "name": "Moderated B",
                    "channel_type": "channel",
                    "group_public_id": False,
                },
                {
                    "name": "Free Channel",
                    "channel_type": "channel",
                    "group_public_id": False,
                },
            ]
        )

        cls.moderator_a = cls._create_user("dcm_mod_a", "group_moderation_user")
        cls.moderator_b = cls._create_user("dcm_mod_b", "group_moderation_user")
        cls.manager = cls._create_user("dcm_manager", "group_moderation_manager")
        cls.both_groups = cls._create_user(
            "dcm_both", "group_moderation_user", "group_moderation_manager"
        )
        cls.plain_employee = cls.env["res.users"].create(
            {
                "name": "DCM Employee",
                "login": "dcm_employee",
                "email": "dcm_employee@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.portal_user = cls.env["res.users"].create(
            {
                "name": "DCM Portal",
                "login": "dcm_portal",
                "email": "dcm_portal@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_portal").id])],
            }
        )

        cls.moderation_a = cls.Moderation.create(
            {
                "channel_id": cls.channel_a.id,
                "moderator_user_ids": [(6, 0, cls.moderator_a.ids)],
            }
        )
        cls.moderation_b = cls.Moderation.create(
            {
                "channel_id": cls.channel_b.id,
                "moderator_user_ids": [(6, 0, cls.moderator_b.ids)],
            }
        )

        cls.guest_1, cls.guest_2 = cls.env["mail.guest"].create(
            [{"name": "Guest One"}, {"name": "Guest Two"}]
        )

    @classmethod
    def _create_user(cls, login, *group_names):
        groups = [
            cls.env.ref("discuss_channel_moderation.%s" % name).id
            for name in group_names
        ]
        return cls.env["res.users"].create(
            {
                "name": "DCM %s" % login,
                "login": login,
                "email": "%s@example.com" % login,
                "group_ids": [(6, 0, groups)],
            }
        )

    # ------------------------------------------------------------------
    # Helpers de publicación
    # ------------------------------------------------------------------

    def _post_as_guest(self, channel, guest, body="hello", message_type="comment"):
        """Reproduce exactamente lo que hace ``/mail/message/post``.

        La ruta es ``auth="public"``: el usuario de sesión es el público, el
        guest viaja en contexto y el post se hace con ``sudo()``
        (mail/controllers/thread.py:226). El ``sudo()`` NO cambia
        ``env.user`` (odoo/orm/models.py:5948), que es justamente lo que
        permite que la identidad siga siendo detectable dentro del hold.
        """
        return (
            channel.with_user(self.public_user)
            .sudo()
            .with_context(guest=guest)
            .message_post(
                body=body,
                message_type=message_type,
                subtype_xmlid="mail.mt_comment",
            )
        )

    def _post_as_public(self, channel, body="hello", message_type="comment"):
        """Sesión pública SIN cookie de visitante: la persona MENOS identificada.

        Es lo que llega a ``message_post`` cuando alguien golpea
        ``/mail/message/post`` sin ninguna cookie. No tener guest no es tener
        más confianza, sino menos, y el hold debe tratarlo como tal.
        """
        return (
            channel.with_user(self.public_user)
            .sudo()
            .message_post(
                body=body,
                message_type=message_type,
                subtype_xmlid="mail.mt_comment",
            )
        )

    def _post_as_user(self, channel, user, body="hello", message_type="comment"):
        """Publicación de un usuario identificado, también con sudo como la ruta."""
        return (
            channel.with_user(user)
            .sudo()
            .message_post(
                body=body,
                message_type=message_type,
                subtype_xmlid="mail.mt_comment",
            )
        )

    def _channel_messages(self, channel, user=None, guest=None):
        """Mensajes del canal tal y como los devolvería ``/discuss/channel/messages``.

        Misma llamada que el controlador (mail/controllers/discuss/channel.py:93):
        ``mail.message._message_fetch(domain=None, thread=channel)``.
        """
        messages = self.env["mail.message"].with_user(user or self.public_user)
        if guest:
            messages = messages.with_context(guest=guest)
        return messages._message_fetch(None, thread=channel)["messages"]

    def _channel_comments(self, channel):
        """Los ``mail.message`` de tipo comentario realmente creados en el canal."""
        return self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", channel.id),
                ("message_type", "=", "comment"),
            ]
        )

    def _channel_all_messages(self, channel):
        """TODOS los ``mail.message`` del canal, sea cual sea su ``message_type``.

        ``_channel_comments`` filtra por ``comment`` y por eso NO sirve para
        probar la puerta: justamente lo que se cuela es lo que no es
        ``comment``. Una retención de verdad deja el canal a cero filas.
        """
        return self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", channel.id),
            ]
        )

    def _message_type_values(self):
        """Todos los valores de ``mail.message.message_type``, LEÍDOS del campo.

        Nunca una lista escrita a mano: ``fields_get`` devuelve la selección ya
        fusionada con los ``selection_add`` de otros módulos (``sms`` añade
        "sms", ``snailmail`` añade "snailmail"...), y una versión futura de
        Odoo puede añadir más. Si alguien amplía la selección, el barrido cubre
        el valor nuevo el día que se instala, sin tocar este test.
        """
        return [
            value
            for value, _label in self.env["mail.message"].fields_get(["message_type"])[
                "message_type"
            ]["selection"]
        ]


class DiscussModerationHttpMixin:
    """Ataque por las rutas públicas REALES, no por la API interna.

    Vive aparte de ``DiscussModerationMixin`` porque sólo sirve sobre
    ``HttpCase``: todo lo de aquí golpea rutas ``auth="public"`` con un
    ``requests.Session``, que es por donde entra un abusador.

    Una fuga no es una fuga hasta que alguien la LEE, así que casi todos los
    helpers vienen por parejas: uno escribe (postea, sube, edita, reacciona) y
    otro comprueba qué se le sirve después a un tercero.
    """

    def setUp(self):
        """Abre una sesión anónima ANTES de la primera petición.

        Hace falta para el token CSRF de las rutas ``type="http"``:
        ``Request.csrf_token`` firma ``self.session.sid``
        (odoo/http.py:1903) y ``HttpCase`` deja ``session`` a ``None`` hasta
        que alguien llama a ``authenticate`` (odoo/tests/common.py:2162). Sin
        sesión no hay token, y sin token la subida devolvía 400 -- que es
        exactamente cómo cuatro pruebas de adjuntos pasaron meses sin
        ejecutarse.

        ``authenticate(None, None)`` es la sesión PÚBLICA: no autentica a
        nadie, sólo crea la sesión y planta su cookie. Se hace en el ``setUp``
        y no dentro del helper porque ``authenticate`` REEMPLAZA
        ``self.opener`` (odoo/tests/common.py:2358) y hacerlo a mitad de una
        prueba tiraría las cookies que ya hubiese puesto.
        """
        super().setUp()
        self.authenticate(None, None)

    @contextmanager
    def _assert_refused_with(self, expected, message):
        """La petición tiene que fallar, y fallar POR ESTO.

        Existe para que la forma estricta sea también la forma corta: el
        ``assertRaises(JsonRpcException)`` pelado es lo bastante cómodo como
        para que se cuele solo, y no distingue el candado del módulo de un
        error de biblioteca ni de un 404.
        """
        with self.assertRaises(JsonRpcException) as caught:
            yield caught
        self.assertEqual(str(caught.exception), expected, message)

    def _csrf_token(self):
        """Token CSRF de la sesión de la prueba.

        Sólo lo necesitan las rutas ``type="http"``: las ``type="jsonrpc"``
        están exentas por el propio dispatcher, de ahí que
        ``make_jsonrpc_request`` no lo mande nunca.
        """
        return Request.csrf_token(self)

    def _guest_cookies(self, guest):
        """Cookie de sesión de visitante que lee ``add_guest_to_context``.

        Formato ``<id>|<access_token>`` (mail/models/discuss/mail_guest.py:50-60,
        separador ``_cookie_separator``). ``access_token`` está protegido por
        ``base.group_system``, de ahí el sudo.
        """
        return {
            self.env["mail.guest"]._cookie_name: "%s|%s"
            % (guest.id, guest.sudo().access_token)
        }

    def _forget_guest_cookie(self):
        """Deja la sesión HTTP SIN cookie de visitante.

        ``self.opener`` es una sesión persistente: sin esto, "sin cookie" sería
        en realidad "con la cookie que dejó la petición anterior" y el caso más
        anónimo de todos no se estaría probando. Sólo se quita la del visitante;
        la del cursor de test tiene que sobrevivir.
        """
        self.opener.cookies.pop(self.env["mail.guest"]._cookie_name, None)

    def _cookies_for(self, guest):
        """Cookies de la persona, limpiando la sesión cuando no hay visitante."""
        if guest:
            return self._guest_cookies(guest)
        self._forget_guest_cookie()
        return None

    def _post_over_http(
        self,
        channel,
        guest=None,
        body="abuse",
        context=None,
        message_type="comment",
        uploads=None,
    ):
        """Golpea ``/mail/message/post`` como lo haría un abusador.

        ``guest=None`` significa SIN NINGUNA COOKIE: la ruta es ``auth="public"``
        y responde igual, sólo que la persona es el usuario público pelado.

        ``uploads`` son respuestas de ``_upload_over_http``. Se mandan con su
        ``ownership_token`` porque ``_prepare_message_data``
        (mail/controllers/thread.py:156-162) exige uno por adjunto: sin él la
        ruta contesta un error y la prueba pasaría por no haber adjuntado nada.
        """
        params = {
            "thread_model": "discuss.channel",
            "thread_id": channel.id,
            "post_data": {
                "body": body,
                # Va tal cual desde aquí hasta message_post: está en
                # _get_allowed_message_params (mail/models/mail_thread.py:5073-5078)
                # y _prepare_message_data lo copia sin filtrar
                # (mail/controllers/thread.py:149-155).
                "message_type": message_type,
                "subtype_xmlid": "mail.mt_comment",
            },
        }
        if uploads:
            params["post_data"]["attachment_ids"] = [
                upload["attachment_id"] for upload in uploads
            ]
            params["post_data"]["attachment_tokens"] = [
                self._ownership_token(upload) for upload in uploads
            ]
        if context is not None:
            params["context"] = context
        return self.make_jsonrpc_request(
            "/mail/message/post", params, cookies=self._cookies_for(guest)
        )

    def _ownership_token(self, upload):
        """El token con el que quien subió el fichero demuestra que es suyo.

        Lo devuelve la propia ruta de subida
        (``_get_store_ownership_fields``, mail/models/ir_attachment.py:89-90).
        """
        return upload["store_data"]["ir.attachment"][0]["ownership_token"]

    def _fetch_over_http(self, channel, guest=None):
        """Lo que ``/discuss/channel/messages`` sirve a terceros después.

        Publicar y ser servido son cosas distintas: esto comprueba la segunda,
        que es la que convierte una fuga en un mensaje que la gente lee.
        """
        return self.make_jsonrpc_request(
            "/discuss/channel/messages",
            {"channel_id": channel.id},
            cookies=self._cookies_for(guest),
        )

    def _upload_over_http(
        self,
        channel,
        guest=None,
        name="evidence.txt",
        is_pending=False,
        content=b"held-bytes",
        mimetype="text/plain",
    ):
        """Sube un fichero por ``/mail/attachment/upload`` (``auth="public"``).

        ``is_pending=False`` a propósito: es el valor con el que la ruta escribe
        ``res_model='discuss.channel'`` directamente
        (mail/controllers/attachment.py:55-69) y el que usó la validación
        adversaria. El cliente real manda ``is_pending`` según tenga composer o
        no, así que un atacante no tiene que hacer nada raro para elegir esta
        rama: basta con no mandar la clave.

        ``csrf_token`` NO es decorativo. La ruta es ``type="http"``, así que el
        dispatcher exige el token y sin él responde 400: las cuatro pruebas de
        adjuntos que dependían de este helper reventaban en el
        ``raise_for_status`` de abajo y nunca llegaron a ejercitar ni la
        retención ni ``/web/content``. Una prueba que no alcanza su primera
        aserción no está en verde, está invisible.
        """
        response = self.url_open(
            "/mail/attachment/upload",
            data={
                "csrf_token": self._csrf_token(),
                "thread_id": channel.id,
                "thread_model": "discuss.channel",
                "is_pending": "true" if is_pending else "false",
            },
            files={"ufile": (name, content, mimetype)},
            cookies=self._cookies_for(guest),
        )
        response.raise_for_status()
        return response.json()["data"]

    def _upload_pdf_over_http(self, channel, guest=None):
        """Un PDF de verdad, porque la ruta de miniaturas sólo acepta PDFs.

        ``/mail/attachment/update_thumbnail`` comprueba
        ``mimetype == "application/pdf"`` (mail/controllers/attachment.py:146),
        y ``ir.attachment`` deduce el mimetype del contenido y del nombre.

        AVISO PARA QUIEN LEA EL LOG DE ESTA SUITE: estos bytes de PDF (y los de
        la miniatura PNG de ``test_moderation_bypass``) acaban EMBEBIDOS en la
        salida de las pruebas. ``grep`` clasifica entonces el fichero entero
        como binario y se lo salta ENTERO, imprimiendo a lo sumo "binary file
        matches" -- o nada -- de modo que ``grep "ERROR" test.log`` puede
        contestar "0 errores" sobre un log lleno de ellos. Hay que forzar el
        tratamiento como texto: ``grep -a`` (o ``rg -a`` / ``rg --text``). Un
        recuento de errores hecho sin esa opción no es un recuento.
        """
        return self._upload_over_http(
            channel,
            guest,
            name="evidence.pdf",
            content=b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
            mimetype="application/pdf",
        )

    def _update_thumbnail_over_http(self, upload, thumbnail, guest=None):
        """Cambia la miniatura por ``/mail/attachment/update_thumbnail``.

        ``auth="public"``, y acepta el ``ownership_token`` de la subida como
        alternativa al permiso de escritura
        (mail/controllers/attachment.py:139-142): el autor lo conserva mucho
        después de que su fichero se haya aprobado.
        """
        return self.make_jsonrpc_request(
            "/mail/attachment/update_thumbnail",
            {
                "attachment_id": upload["attachment_id"],
                "thumbnail": thumbnail,
                "access_token": self._ownership_token(upload),
            },
            cookies=self._cookies_for(guest),
        )

    def _delete_attachment_over_http(self, upload, guest=None):
        """Borra un adjunto por ``/mail/attachment/delete`` (``auth="public"``).

        Se manda el ``ownership_token`` que devolvió la subida porque es el
        único requisito de la ruta (mail/controllers/attachment.py:92): quien
        subió el fichero lo conserva aunque el fichero haya cambiado de padre.
        """
        return self.make_jsonrpc_request(
            "/mail/attachment/delete",
            {
                "attachment_id": upload["attachment_id"],
                "access_token": self._ownership_token(upload),
            },
            cookies=self._cookies_for(guest),
        )

    def _link_preview_over_http(self, message, guest=None):
        """Pide una previsualización por ``/mail/link_preview`` (``auth="public"``).

        La ruta concede la llamada a ``is_current_user_or_guest_author``
        (mail/controllers/link_preview.py:18), y tras UNA aprobación el
        visitante ES el autor.
        """
        return self.make_jsonrpc_request(
            "/mail/link_preview",
            {"message_id": message.id},
            cookies=self._cookies_for(guest),
        )

    def _list_attachments_over_http(self, channel, guest=None):
        """Lo que ``/discuss/channel/attachments`` sirve a terceros.

        Es LA ruta de la fuga: busca por ``res_model``/``res_id`` y nada más
        (mail/controllers/discuss/channel.py:166-173), sin idea alguna de si el
        adjunto pertenece a un mensaje publicado, y devuelve el
        ``raw_access_token`` de cada fila dentro del ``Store``
        (mail/models/ir_attachment.py:100).
        """
        return self.make_jsonrpc_request(
            "/discuss/channel/attachments",
            {"channel_id": channel.id},
            cookies=self._cookies_for(guest),
        )

    def _attachment_tokens_over_http(self, channel, guest=None):
        """``{id: raw_access_token}`` de lo que el listado le regala a la persona."""
        listed = self._list_attachments_over_http(channel, guest)
        records = listed["store_data"].get("ir.attachment", [])
        return {record["id"]: record.get("raw_access_token") for record in records}

    def _download_over_http(self, attachment_id, access_token=None):
        """``/web/content`` es el último eslabón: el que devuelve los bytes.

        Con ``access_token`` salta el ACL vía ``verify_limited_field_access_token``
        (odoo/addons/base/models/ir_binary.py:50), que es exactamente lo que
        convertía el token del listado en una descarga con HTTP 200.
        """
        url = "/web/content/%s" % attachment_id
        if access_token:
            url += "?access_token=%s" % access_token
        return self.url_open(url)

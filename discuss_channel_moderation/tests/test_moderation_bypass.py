# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.discuss_channel_moderation.models.discuss_channel import (
    MAX_HELD_BODY_LENGTH,
    MAX_PENDING_PER_PERSONA,
)
from odoo.addons.discuss_channel_moderation.models.mail_guest import (
    MAX_GUEST_NAME_LENGTH,
)

from .common import (
    JSONRPC_ACCESS_ERROR,
    JSONRPC_USER_ERROR,
    DiscussModerationHttpMixin,
    DiscussModerationMixin,
)

# Un PNG de 1x1 en base64: lo mínimo que ``fields.Image`` acepta como imagen
# válida, para que lo que se rechace sea la REGLA y no un fichero corrupto.
#
# Este NO es cualquier PNG de internet. Lo genera Pillow (``Image.new("RGB",
# (1, 1)).save(..., format="PNG")``) y se ha comprobado que sobrevive a
# ``odoo.tools.image.image_process(source, size=(0, 0), verify_resolution=True)``,
# que es EXACTAMENTE la llamada que hace ``fields.Image()`` sin ``max_width`` ni
# ``max_height`` al escribir el valor (``odoo/orm/fields_binary.py:264-300`` y
# ``312-320``). El literal anterior parecía un PNG y no lo era: llevaba dos bytes
# de basura (``8c 21``) entre el CRC del ``IDAT`` y el ``IEND``, así que la
# validez de la imagen dependía de lo tolerante que fuese la versión de Pillow
# instalada. Un fichero así hace daño en las DOS direcciones: revienta el control
# positivo, donde la escritura tiene que llegar hasta el final, y sostiene el
# candado por el motivo equivocado en la prueba negativa, donde cualquier fallo
# de PIL también aborta la petición.
ATTACKER_THUMBNAIL = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mP4z8AAAAMBAQD3A0FD"
    "AAAAAElFTkSuQmCC"
)

# Por eso ninguna prueba de aquí se conforma con ``assertRaises(JsonRpcException)``
# a secas: todas pasan por ``_assert_refused_with``, que además afirma QUÉ error
# fue. Los nombres viven en ``common.py``.


@tagged("post_install", "-at_install")
class TestModerationBypass(
    DiscussModerationMixin, DiscussModerationHttpMixin, HttpCase
):
    """Las puertas que NO pasan por ``message_post``.

    El módulo nació defendiendo un embudo, ``discuss.channel.message_post``, y
    ese embudo es de verdad el único que CREA un ``mail.message``. Pero servir
    contenido a un tercero no requiere crear un mensaje: tres rondas de
    validación adversaria sobre una copia de producción publicaron a lectores
    anónimos -- o ensuciaron la cola, o destruyeron pruebas -- por caminos que
    no lo tocan: subir un fichero, editar un mensaje ya aprobado, reaccionar con
    texto libre, renombrarse, BORRAR el adjunto retenido, abrir un hilo bajo el
    canal, y entrar en una llamada. Las previsualizaciones de enlace, que son la
    tercera ronda entera, tienen suite propia en
    ``test_moderation_link_preview``.

    Cada prueba de aquí ataca por la ruta pública REAL donde estaba la fuga y
    termina mirando lo que se le sirve a un tercero, porque una fuga sólo
    existe cuando alguien la lee. Una prueba por ORM no habría cazado ninguna:
    el agujero estaba entre la ruta y el modelo.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()

    def _pending(self, channel=None, **extra):
        channel = channel or self.channel_a
        return self.Pending.search(
            [("channel_id", "=", channel.id)] + [(k, "=", v) for k, v in extra.items()]
        )

    # ------------------------------------------------------------------
    # F2 -- subir un fichero no es publicar, pero se servía igual
    # ------------------------------------------------------------------

    def test_guest_upload_never_becomes_a_channel_attachment(self):
        """La fuga que no necesitaba ni aprobación ni mensaje previo.

        ``/mail/attachment/upload`` es ``auth="public"`` y escribía
        ``ir.attachment(res_model='discuss.channel')`` fuera de la puerta;
        ``/discuss/channel/attachments``, también ``auth="public"``, busca por
        ``res_model``/``res_id`` y nada más, así que devolvía el fichero -- con
        su ``raw_access_token`` -- a cualquiera. La validación observó un
        adjunto sin ningún vínculo con un mensaje ni con una retención, y aun
        así descargable con HTTP 200. Subir bastaba.
        """
        uploaded = self._upload_over_http(self.channel_a, self.guest_1)
        attachment = self.env["ir.attachment"].sudo().browse(uploaded["attachment_id"])
        self.assertNotEqual(
            attachment.res_model,
            "discuss.channel",
            "una subida de un visitante no puede colgar del canal moderado",
        )
        for label, guest in (("otro visitante", self.guest_2), ("anónimo", None)):
            with self.subTest(persona=label):
                self.assertNotIn(
                    attachment.id,
                    self._attachment_tokens_over_http(self.channel_a, guest),
                    "%s no puede listar el fichero retenido" % label,
                )
        self.assertNotEqual(
            self._download_over_http(attachment.id).status_code,
            200,
            "y sin token del listado tampoco se descarga por id",
        )

    def test_control_an_upload_on_a_free_channel_is_served(self):
        """Control positivo: la ruta de fuga FUNCIONA, lo que la frena es la moderación.

        Sin esto, las comprobaciones anteriores pasarían igual si el listado
        estuviese roto, si la subida fallase o si el canal fuese ilegible: no
        se vería nada porque no hay nada, no porque la puerta cierre.
        """
        uploaded = self._upload_over_http(self.channel_free, self.guest_1)
        attachment_id = uploaded["attachment_id"]
        tokens = self._attachment_tokens_over_http(self.channel_free)
        self.assertIn(
            attachment_id, tokens, "en un canal sin moderar el listado sí lo sirve"
        )
        self.assertEqual(
            self._download_over_http(attachment_id, tokens[attachment_id]).status_code,
            200,
            "y el token del listado descarga los bytes: la cadena entera vale",
        )

    def test_held_attachment_is_evidence_for_the_moderator_only(self):
        """Retener no puede ser esconder: el moderador tiene que poder abrirlo.

        Es la mitad que se olvida al cerrar una fuga de adjuntos. El fichero es
        parte de la decisión -- se aprueba o se rechaza MIRÁNDOLO -- así que
        pasa a colgar de la fila retenida y hereda su control de acceso: lo ve
        quien modera ese canal, y nadie más, ni siquiera un interno.
        """
        uploaded = self._upload_over_http(self.channel_a, self.guest_1)
        self._post_over_http(
            self.channel_a, self.guest_1, body="con adjunto", uploads=[uploaded]
        )
        pending = self._pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending.attachment_ids.ids,
            [uploaded["attachment_id"]],
            "el fichero viaja con la retención",
        )
        self.env.invalidate_all()
        Attachment = self.env["ir.attachment"]
        self.assertTrue(
            Attachment.with_user(self.moderator_a)
            .browse(uploaded["attachment_id"])
            .read(["name"]),
            "quien modera el canal tiene que poder abrir la prueba",
        )
        with self.assertRaises(AccessError):
            Attachment.with_user(self.plain_employee).browse(
                uploaded["attachment_id"]
            ).read(["name"])

    def test_attachment_is_served_only_after_approval(self):
        """El otro lado del candado: aprobar sí publica el fichero.

        Si la retención dejase el adjunto fuera del canal para siempre, el
        módulo no estaría moderando adjuntos, estaría rompiéndolos.
        """
        uploaded = self._upload_over_http(self.channel_a, self.guest_1)
        attachment_id = uploaded["attachment_id"]
        self._post_over_http(
            self.channel_a, self.guest_1, body="con adjunto", uploads=[uploaded]
        )
        pending = self._pending()
        self.assertNotIn(
            attachment_id, self._attachment_tokens_over_http(self.channel_a)
        )
        pending.with_user(self.moderator_a).action_approve()
        self.env.flush_all()
        self.assertEqual(
            pending.message_id.attachment_ids.ids,
            [attachment_id],
            "el mensaje publicado se queda con el fichero aprobado",
        )
        tokens = self._attachment_tokens_over_http(self.channel_a)
        self.assertIn(
            attachment_id, tokens, "aprobado, el listado público ya sí lo sirve"
        )
        self.assertEqual(
            self._download_over_http(attachment_id, tokens[attachment_id]).status_code,
            200,
        )

    @mute_logger("odoo.http")
    def test_the_author_cannot_destroy_the_moderators_evidence(self):
        """Quien sube conserva el token de propiedad DESPUÉS de la retención.

        ``/mail/attachment/delete`` (``auth="public"``) sólo comprueba
        ``_has_attachments_ownership`` (mail/controllers/attachment.py:92), y
        re-emparentar el fichero a la fila retenida no revoca el token que la
        ruta de subida le devolvió al autor. La validación borró el adjunto de
        su PROPIO mensaje retenido: la fila desapareció y el moderador se quedó
        mirando un pendiente sin adjuntos, obligado a decidir sobre una prueba
        que el autor acababa de destruir.
        """
        uploaded = self._upload_over_http(self.channel_a, self.guest_1)
        self._post_over_http(
            self.channel_a, self.guest_1, body="con adjunto", uploads=[uploaded]
        )
        pending = self._pending()
        # AccessError y no otra cosa, porque el error EQUIVOCADO aquí probaría
        # lo contrario de lo que dice el docstring. Si el token de propiedad
        # dejase de valer tras la retención, ``_has_attachments_ownership``
        # fallaría y la ruta contestaría ``NotFound``
        # (mail/controllers/attachment.py:92-94): la prueba seguiría verde
        # mientras la premisa entera -- "el autor CONSERVA el token" -- se
        # habría venido abajo. Con el nombre afirmado, ese día esto se pone
        # rojo, que es lo que tiene que pasar.
        with self._assert_refused_with(
            JSONRPC_ACCESS_ERROR,
            "corta _moderation_check_evidence, no un 404 por token inválido",
        ):
            self._delete_attachment_over_http(uploaded, self.guest_1)
        self.env.invalidate_all()
        attachment = self.env["ir.attachment"].sudo().browse(uploaded["attachment_id"])
        self.assertTrue(attachment.exists(), "el fichero sigue ahí")
        self.assertEqual(
            pending.attachment_ids.ids,
            [uploaded["attachment_id"]],
            "y la fila retenida sigue teniendo su prueba",
        )

    @mute_logger("odoo.http")
    def test_the_author_cannot_re_parent_held_evidence_either(self):
        """Borrar es el verbo observado; re-emparentar es el mismo ataque.

        Devolver ``res_model`` a ``discuss.channel`` publicaría el fichero por
        ``/discuss/channel/attachments`` sin aprobación ninguna, así que la
        guarda mira el estado del REGISTRO y no el campo que se toca.
        """
        uploaded = self._upload_over_http(self.channel_a, self.guest_1)
        self._post_over_http(
            self.channel_a, self.guest_1, body="con adjunto", uploads=[uploaded]
        )
        attachment = self.env["ir.attachment"].sudo().browse(uploaded["attachment_id"])
        with self.assertRaises(AccessError):
            attachment.with_user(self.public_user).sudo().write(
                {"res_model": "discuss.channel", "res_id": self.channel_a.id}
            )
        self.env.invalidate_all()
        self.assertNotIn(
            uploaded["attachment_id"],
            self._attachment_tokens_over_http(self.channel_a, self.guest_2),
        )

    def test_control_deleting_an_upload_that_is_not_evidence_still_works(self):
        """El otro lado: quitar un adjunto del composer sigue siendo cosa del autor.

        Sin este control, la guarda podría haber roto el "quitar fichero" de
        cualquier canal y las pruebas de arriba seguirían en verde.
        """
        uploaded = self._upload_over_http(self.channel_free, self.guest_1)
        self._delete_attachment_over_http(uploaded, self.guest_1)
        self.env.invalidate_all()
        self.assertFalse(
            self.env["ir.attachment"].sudo().browse(uploaded["attachment_id"]).exists(),
            "en un canal sin moderar el autor sigue borrando lo suyo",
        )

    def test_a_moderator_can_still_remove_held_evidence(self):
        """Retener no puede convertir la cola en una tabla imborrable.

        La guarda es "sólo personas internas", no "nadie": quien modera tiene
        que poder limpiar.
        """
        uploaded = self._upload_over_http(self.channel_a, self.guest_1)
        self._post_over_http(
            self.channel_a, self.guest_1, body="con adjunto", uploads=[uploaded]
        )
        attachment = self.env["ir.attachment"].sudo().browse(uploaded["attachment_id"])
        attachment.with_user(self.moderator_a).sudo().unlink()
        self.assertFalse(attachment.exists())

    def _approved_pdf(self, channel, moderator=None):
        """Deja un PDF del ``guest_1`` publicado y aprobado en ``channel``."""
        uploaded = self._upload_pdf_over_http(channel, self.guest_1)
        self._post_over_http(channel, self.guest_1, body="mi pdf", uploads=[uploaded])
        pending = self._pending(channel)
        pending.with_user(moderator or self.moderator_a).action_approve()
        self.env.flush_all()
        return uploaded

    @mute_logger("odoo.http")
    def test_an_approved_file_cannot_be_swapped_afterwards(self):
        """Aprobar un fichero tampoco es barra libre para siempre.

        Esto NO salió de un informe: salió de recorrer las rutas públicas.
        ``/mail/attachment/update_thumbnail`` (``auth="public"``) acepta el
        ``ownership_token`` como alternativa al permiso de escritura
        (mail/controllers/attachment.py:139-142), y ese token es el que el autor
        se guardó al subir. Así que tras UNA aprobación podía escribir una
        imagen cualquiera en ``thumbnail``, y ``has_thumbnail`` +
        ``thumbnail_access_token`` (mail/models/ir_attachment.py:97-103) la
        sirven a todo el que lee el canal. Es el bypass de la edición de la
        segunda ronda con otro nombre de campo.
        """
        uploaded = self._approved_pdf(self.channel_a)
        attachment = self.env["ir.attachment"].sudo().browse(uploaded["attachment_id"])
        self.assertEqual(attachment.res_model, "discuss.channel", "está publicado")
        with self._assert_refused_with(
            JSONRPC_ACCESS_ERROR,
            "quien corta es _moderation_check_published_content, no PIL ni la ruta",
        ):
            self._update_thumbnail_over_http(uploaded, ATTACKER_THUMBNAIL, self.guest_1)
        self.env.invalidate_all()
        self.assertFalse(
            attachment.thumbnail, "no se le cuela ninguna imagen tras la aprobación"
        )

    def test_control_swapping_a_thumbnail_on_a_free_channel_still_works(self):
        """Control positivo: la ruta FUNCIONA; lo que la frena es la moderación."""
        uploaded = self._upload_pdf_over_http(self.channel_free, self.guest_1)
        self._post_over_http(
            self.channel_free, self.guest_1, body="mi pdf", uploads=[uploaded]
        )
        self._update_thumbnail_over_http(uploaded, ATTACKER_THUMBNAIL, self.guest_1)
        self.env.invalidate_all()
        self.assertTrue(
            self.env["ir.attachment"]
            .sudo()
            .browse(uploaded["attachment_id"])
            .thumbnail,
            "en un canal sin moderar el autor sí cambia su miniatura",
        )

    # ------------------------------------------------------------------
    # F6 -- los avisos del sistema no son contenido que moderar
    # ------------------------------------------------------------------

    @mute_logger("odoo.http")
    def test_a_call_notice_never_reaches_the_queue(self):
        """Un visitante que entra en una llamada no deja nada que decidir.

        Al crear la sesión RTC el core postea
        ``<div data-oe-type="call" class="o_mail_notification"></div>``
        (mail/models/discuss/discuss_channel_rtc_session.py:52) a través de
        ``message_post`` con la persona del visitante, así que se retenía como
        si fuese un comentario. Aprobarlo publica un "empezó una llamada" de una
        llamada que terminó mientras la fila esperaba -- la decisión del
        moderador fabricaría una mentira -- y mientras tanto gasta uno de los 20
        huecos reservados para texto que alguien tiene que leer de verdad.
        """
        self.make_jsonrpc_request(
            "/mail/rtc/channel/join_call",
            {"channel_id": self.channel_a.id},
            cookies=self._guest_cookies(self.guest_1),
        )
        self.env.invalidate_all()
        self.assertTrue(
            self.env["discuss.channel.rtc.session"]
            .sudo()
            .search([("channel_id", "=", self.channel_a.id)]),
            "el visitante SÍ entra en la llamada: no se está probando un 404",
        )
        self.assertFalse(
            self._channel_all_messages(self.channel_a),
            "y no publica ningún mail.message",
        )
        self.assertFalse(
            self._pending(),
            "ni deja en la cola un aviso que nadie escribió y nadie puede juzgar",
        )

    @mute_logger("odoo.http")
    def test_forging_a_system_notice_discards_it_instead_of_publishing(self):
        """Falsificar el aviso no publica: descarta. Que es el punto.

        El descarte se decide MIRANDO EL CUERPO, que un atacante controla. Eso
        sólo es seguro porque la rama que selecciona no publica nada: quien lo
        falsifique consigue que su propio mensaje desaparezca, un resultado
        estrictamente peor para él que la cola. Un discriminador basado en la
        entrada sólo es peligroso cuando la rama que elige es la permisiva --
        que es exactamente lo que pasaba con ``message_type``.
        """
        result = self._post_over_http(
            self.channel_a,
            self.guest_1,
            body='<div data-oe-type="call" class="o_mail_notification"></div>',
        )
        self.assertFalse(result["message_id"])
        self.env.invalidate_all()
        self.assertFalse(self._channel_all_messages(self.channel_a))
        self.assertFalse(self._pending(), "ni se publica ni se encola")

    @mute_logger("odoo.http")
    def test_a_notice_wrapper_with_words_in_it_is_still_held(self):
        """La clase del core no es un salvoconducto: lo que decide es que no haya texto.

        Si bastase con la clase, "envuélvelo en un div de aviso" sería el cuarto
        bypass. La prueba mete texto real dentro del envoltorio y comprueba las
        dos mitades: no se publica y sí acaba en la cola.
        """
        self._post_over_http(
            self.channel_a,
            self.guest_1,
            body='<div class="o_mail_notification">SPAM DISFRAZADO</div>',
        )
        self.env.invalidate_all()
        self.assertFalse(self._channel_all_messages(self.channel_a))
        self.assertEqual(len(self._pending()), 1, "el texto disfrazado sí se modera")
        self.assertNotIn(
            "SPAM DISFRAZADO",
            str(self._fetch_over_http(self.channel_a, self.guest_2)["data"]),
        )

    # ------------------------------------------------------------------
    # F7 -- un hilo bajo un canal moderado no es una habitación sin reglas
    # ------------------------------------------------------------------

    def test_a_sub_channel_inherits_the_moderation_of_its_parent(self):
        """Abrir un hilo no puede desactivar la moderación del canal.

        ``_get_for_channel`` comparaba ``channel_id`` exacto, así que un
        sub-canal no encontraba configuración ninguna. Y no es un rincón
        aislado: ``group_public_id`` se COPIA del padre
        (mail/models/discuss/discuss_channel.py:351-357), de modo que los mismos
        visitantes que están retenidos arriba leen y escriben abajo sin nada en
        medio. Crear el hilo requiere permisos que ellos no tienen, así que basta
        con que una persona interna pulse "abrir hilo" para regalarles la
        habitación; nada en ese clic dice "y quita la moderación".
        """
        sub_channel = self.channel_a._create_sub_channel(name="Hilo")
        result = self._post_over_http(
            sub_channel, self.guest_1, body="<b>en el hilo</b>"
        )
        self.assertFalse(result["message_id"])
        self.env.invalidate_all()
        self.assertFalse(self._channel_all_messages(sub_channel))
        pending = self._pending(sub_channel)
        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending.moderation_id,
            self.moderation_a,
            "la retención cae en la cola del canal padre, que es quien tiene moderadores",
        )
        self.assertNotIn(
            "en el hilo",
            str(self._fetch_over_http(sub_channel, self.guest_2)["data"]),
            "y ningún tercero lo lee mientras espera",
        )

    def test_an_approved_sub_channel_message_is_published_in_the_sub_channel(self):
        """Control positivo: heredar la moderación no rompe el hilo.

        El mensaje aprobado tiene que aparecer EN EL HILO, no en el padre: si
        cayese arriba, la herencia habría arreglado la fuga rompiendo la
        función.
        """
        sub_channel = self.channel_a._create_sub_channel(name="Hilo")
        self._post_over_http(sub_channel, self.guest_1, body="aportación legítima")
        pending = self._pending(sub_channel)
        pending.with_user(self.moderator_a).action_approve()
        self.env.flush_all()
        self.assertEqual(pending.message_id.res_id, sub_channel.id)
        self.assertIn(
            "aportación legítima",
            str(self._fetch_over_http(sub_channel, self.guest_2)["data"]),
        )

    def test_control_a_sub_channel_of_a_free_channel_stays_free(self):
        """La herencia sólo hereda lo que hay: un hilo de un canal libre sigue libre."""
        sub_channel = self.channel_free._create_sub_channel(name="Hilo libre")
        result = self._post_over_http(sub_channel, self.guest_1, body="libre")
        self.assertTrue(result["message_id"])
        self.assertFalse(self._pending(sub_channel))

    # ------------------------------------------------------------------
    # F1 -- aprobar una vez no puede ser barra libre para siempre
    # ------------------------------------------------------------------

    def _approved_message(self, body="texto original"):
        """Deja un mensaje del ``guest_1`` publicado y aprobado en el canal A."""
        self._post_over_http(self.channel_a, self.guest_1, body=body)
        pending = self._pending()
        pending.with_user(self.moderator_a).action_approve()
        self.env.flush_all()
        return pending.message_id

    def _edit_over_http(self, message, guest=None, body="editado", **update_data):
        return self.make_jsonrpc_request(
            "/mail/message/update_content",
            {
                "message_id": message.id,
                "update_data": {"body": body, **update_data},
            },
            cookies=self._cookies_for(guest),
        )

    def test_editing_an_approved_message_re_enters_the_queue(self):
        """ "Aprueba una vez y luego di lo que quieras", cerrado.

        ``_can_edit_message`` (mail/controllers/thread.py:253) concede la
        edición a ``is_current_user_or_guest_author``, y tras la aprobación el
        visitante ES el autor. La validación reescribió un cuerpo aprobado a
        spam arbitrario: HTTP 200, ninguna retención nueva, y tanto otro
        visitante como un anónimo recibieron el texto nuevo.

        Se comprueban las TRES cosas que tienen que pasar a la vez: el texto
        nuevo no se sirve, el viejo TAMPOCO (retirar a medias dejaría en pie lo
        que ya estaba publicado) y la edición acaba en la cola.
        """
        message = self._approved_message(body="texto original")
        self._edit_over_http(message, self.guest_1, body="<b>SPAM EDITADO</b>")
        self.env.invalidate_all()
        for label, guest in (("otro visitante", self.guest_2), ("anónimo", None)):
            with self.subTest(persona=label):
                served = str(self._fetch_over_http(self.channel_a, guest)["data"])
                self.assertNotIn("SPAM EDITADO", served, "%s no lee la edición" % label)
                self.assertNotIn(
                    "texto original",
                    served,
                    "%s tampoco puede seguir leyendo el cuerpo retirado" % label,
                )
        pending = self._pending(state="pending")
        self.assertEqual(len(pending), 1, "la edición vuelve a la cola")
        self.assertIn("SPAM EDITADO", pending.body)

    def test_an_edit_is_published_only_when_approved_again(self):
        """Control positivo de F1: el camino sigue existiendo, con decisión.

        Sin él, "el tercero no ve la edición" también sería cierto si editar
        hubiese dejado de funcionar del todo.
        """
        message = self._approved_message(body="texto original")
        self._edit_over_http(message, self.guest_1, body="corrección legítima")
        self.env.invalidate_all()
        pending = self._pending(state="pending")
        pending.with_user(self.moderator_a).action_approve()
        self.env.flush_all()
        self.assertIn(
            "corrección legítima",
            str(self._fetch_over_http(self.channel_a, self.guest_2)["data"]),
            "aprobada, la edición sí llega al tercero",
        )

    def test_deleting_an_own_message_is_not_held(self):
        """Borrar no publica nada, así que no se modera.

        El cliente borra un mensaje llamando a la MISMA ruta con el cuerpo
        vacío. Tratar eso como una edición llenaría la cola de filas vacías y
        haría que retirar lo propio necesitase permiso de un moderador, que es
        justo al revés de lo que la moderación protege.
        """
        message = self._approved_message(body="texto original")
        self._edit_over_http(message, self.guest_1, body="", attachment_ids=[])
        self.env.invalidate_all()
        self.assertFalse(
            self._pending(state="pending"), "un borrado no deja nada que decidir"
        )
        self.assertNotIn(
            "texto original",
            str(self._fetch_over_http(self.channel_a, self.guest_2)["data"]),
        )

    # ------------------------------------------------------------------
    # F3 -- una reacción es un grafema, no un campo de texto
    # ------------------------------------------------------------------

    def _react_over_http(self, message, guest=None, content="👍", action="add"):
        return self.make_jsonrpc_request(
            "/mail/message/reaction",
            {"message_id": message.id, "content": content, "action": action},
            cookies=self._cookies_for(guest),
        )

    @mute_logger("odoo.http")
    def test_arbitrary_text_reactions_are_refused(self):
        """``/mail/message/reaction`` acepta texto libre en el core.

        ``content`` es un ``Char`` sin validar (mail/models/mail_message_reaction.py:15)
        y ``_message_reaction`` lo escribe tal cual: la validación guardó
        ``"REACTION-ARBITRARY-TEXT"`` y después 5000 caracteres, ambos servidos
        a un tercero. La comprobación de emoji del cliente no es una
        comprobación.
        """
        message = self._approved_message()
        for label, content in (
            ("texto", "REACTION-ARBITRARY-TEXT"),
            ("parrafada", "x" * 5000),
            ("markup", "<b>spam</b>"),
        ):
            with self.subTest(content=label):
                # UserError, que es lo que levanta ``_moderation_check_reaction``
                # (models/mail_message.py:110-111). Importa el tipo: la ruta
                # también contesta ``NotFound`` si deja de encontrar el mensaje
                # o si el visitante deja de ser su autor, y con eso las tres
                # sub-pruebas pasarían sin haber ejercitado la forma del emoji.
                with self._assert_refused_with(
                    JSONRPC_USER_ERROR,
                    "lo rechaza la comprobación de forma, no un 404 de la ruta",
                ):
                    self._react_over_http(message, self.guest_1, content=content)
        self.env.invalidate_all()
        self.assertFalse(
            self.env["mail.message.reaction"].search([("message_id", "=", message.id)]),
            "ninguna de las tres puede llegar a la tabla",
        )

    def test_emoji_reactions_still_work(self):
        """El otro lado: no romper las reacciones de verdad.

        Se barren las formas compuestas legítimas -- tono de piel, familia con
        ZWJ, bandera, keycap -- porque una comprobación por longitud ingenua las
        rechazaría y el candado parecería correcto hasta que alguien reaccionase
        con algo que no fuese un pulgar.
        """
        message = self._approved_message()
        for label, content in (
            ("simple", "👍"),
            ("tono de piel", "👍🏽"),
            ("familia con ZWJ", "👨‍👩‍👧‍👦"),
            ("bandera", "🇪🇸"),
            ("keycap", "1️⃣"),
            ("corazón con variación", "❤️"),
        ):
            with self.subTest(emoji=label):
                self._react_over_http(message, self.guest_1, content=content)
        self.env.invalidate_all()
        self.assertEqual(
            self.env["mail.message.reaction"].search_count(
                [("message_id", "=", message.id)]
            ),
            6,
            "las seis reacciones legítimas se guardan",
        )
        self.assertIn(
            "👍", str(self._fetch_over_http(self.channel_a, self.guest_2)["data"])
        )

    # ------------------------------------------------------------------
    # F4 -- moderar el cuerpo y dejar la firma libre es medio control
    # ------------------------------------------------------------------

    def _rename_over_http(self, guest, name):
        return self.make_jsonrpc_request(
            "/mail/guest/update_name",
            {"guest_id": guest.id, "name": name},
            cookies=self._guest_cookies(guest),
        )

    def test_guest_name_is_stripped_and_capped_for_third_parties(self):
        """El nombre del visitante también se sirve a terceros.

        La validación puso ``GUESTNAME-<b>spam</b>`` con
        ``/mail/guest/update_name`` (``auth="public"``, 512 caracteres
        permitidos por el core) y quedó renderizado junto a su mensaje
        aprobado. Se comprueba lo que acaba viendo el tercero, no sólo lo que
        se guarda.
        """
        self._rename_over_http(self.guest_1, "GUESTNAME-<b>spam</b>")
        self.env.invalidate_all()
        self.assertEqual(
            self.guest_1.sudo().name,
            "GUESTNAME-spam",
            "el marcado se quita, el nombre sobrevive",
        )
        self._approved_message(body="firmado")
        served = str(self._fetch_over_http(self.channel_a, self.guest_2)["data"])
        self.assertIn("GUESTNAME-spam", served, "la firma llega al tercero: se mira")
        self.assertNotIn("<b>spam</b>", served)

    def test_guest_name_length_is_capped(self):
        """512 caracteres es un párrafo disfrazado de nombre."""
        self._rename_over_http(self.guest_1, "N" * 400)
        self.env.invalidate_all()
        self.assertEqual(len(self.guest_1.sudo().name), MAX_GUEST_NAME_LENGTH)

    @mute_logger("odoo.http")
    def test_guest_name_made_only_of_markup_is_refused(self):
        """Quitar el marcado no puede dejar un nombre vacío pasando por bueno."""
        original = self.guest_1.sudo().name
        # El UserError es el del propio módulo, con el mensaje del core:
        # ``_moderation_clean_name`` (models/mail_guest.py:103-106) lo levanta
        # cuando después de quitar el marcado no queda nada. Sin afirmar el
        # tipo, una cookie de visitante que dejase de valer daría un
        # ``NotFound`` y la prueba pasaría sin haber saneado nada.
        with self._assert_refused_with(
            JSONRPC_USER_ERROR,
            "lo rechaza el saneado del nombre, no la sesión",
        ):
            self._rename_over_http(self.guest_1, "<b></b>")
        self.env.invalidate_all()
        self.assertEqual(self.guest_1.sudo().name, original)

    def test_a_guest_is_born_with_a_clean_name_too(self):
        """El saneado se prometía "para todo visitante" y sólo cubría el RENOMBRADO.

        Un visitante NACE en ``_get_or_create_guest``
        (mail/models/discuss/mail_guest.py:70-81), que escribe ``guest_name`` tal
        cual. En ``mail`` a secas ese nombre es una constante, pero
        ``im_livechat`` -- que esta plataforma instalará -- le pasa por ahí el
        nombre que teclea el visitante. La guarda vive en ``create``, no en
        ``_get_or_create_guest``, por lo mismo que la de los adjuntos: la ruta es
        una puerta, ``create`` es la pared.
        """
        guest = self.env["mail.guest"].create({"name": "NACIDO-<b>spam</b>"})
        self.assertEqual(guest.name, "NACIDO-spam")
        self.assertEqual(
            len(
                self.env["mail.guest"]
                .create({"name": "N" * (MAX_GUEST_NAME_LENGTH + 100)})
                .name
            ),
            MAX_GUEST_NAME_LENGTH,
        )

    # ------------------------------------------------------------------
    # F5 -- la cola es una tabla que nadie mira: hay que acotarla
    # ------------------------------------------------------------------

    @mute_logger("odoo.http")
    def test_oversized_body_is_refused(self):
        """Se aceptaba y guardaba un cuerpo de 2 MB.

        Moderar convierte "el spam se ve, alguien se queja" en "el spam se
        acumula donde nadie mira", así que el tamaño deja de ser un problema
        cosmético.
        """
        # Es DONDE más fácil sería pasar por el motivo equivocado: 64 KB de
        # cuerpo pueden reventar en sitios que no son la comprobación de tamaño
        # (el ORM, la capa HTTP, un límite ajeno). El ``UserError`` es el de
        # ``_moderation_check_quota`` (models/discuss_channel.py:310-317), y es
        # además el único que el autor puede LEER, que es la mitad del punto.
        with self._assert_refused_with(
            JSONRPC_USER_ERROR,
            "lo corta el límite de tamaño, con un mensaje que el autor entiende",
        ):
            self._post_over_http(
                self.channel_a, self.guest_1, body="x" * (MAX_HELD_BODY_LENGTH + 1)
            )
        self.env.invalidate_all()
        self.assertFalse(self._pending(), "nada desmedido llega a la cola")

    @mute_logger("odoo.http")
    def test_outstanding_pending_rows_are_capped_per_persona(self):
        """Una persona no puede llenar la cola de un canal ella sola.

        Las primeras se crean por ORM -- el mismo embudo -- y las dos últimas
        por la ruta pública, que es donde tiene que verse el límite: la que
        hace el número máximo pasa, la siguiente se rechaza con un error que el
        autor lee.
        """
        for index in range(MAX_PENDING_PER_PERSONA - 1):
            self._post_as_guest(self.channel_a, self.guest_1, "flood %s" % index)
        self.env.flush_all()
        self._post_over_http(self.channel_a, self.guest_1, body="la última que cabe")
        with self._assert_refused_with(
            JSONRPC_USER_ERROR,
            "lo corta el tope por persona, con un error que el autor lee",
        ):
            self._post_over_http(self.channel_a, self.guest_1, body="una de más")
        self.env.invalidate_all()
        self.assertEqual(
            self.Pending.search_count(
                [("channel_id", "=", self.channel_a.id), ("state", "=", "pending")]
            ),
            MAX_PENDING_PER_PERSONA,
        )

    def test_the_cap_does_not_lock_out_another_persona(self):
        """El tope es por persona: llenar la cola no silencia a los demás.

        Sin esta prueba, un tope escrito por canal (o por el partner público
        compartido por todos los anónimos) pasaría igual y convertiría la
        defensa contra el spam en una forma de callar a todo el mundo.
        """
        for index in range(MAX_PENDING_PER_PERSONA):
            self._post_as_guest(self.channel_a, self.guest_1, "flood %s" % index)
        self.env.flush_all()
        self._post_over_http(self.channel_a, self.guest_2, body="otra persona")
        self.env.invalidate_all()
        self.assertEqual(
            self.Pending.search_count(
                [
                    ("channel_id", "=", self.channel_a.id),
                    ("guest_id", "=", self.guest_2.id),
                ]
            ),
            1,
        )

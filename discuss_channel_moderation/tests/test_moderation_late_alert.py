# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

# `MailDeliveryException` NO vive en `odoo.exceptions`: la define el propio
# servidor de correo (odoo/addons/base/models/ir_mail_server.py:64). Importarla
# del sitio equivocado es un ImportError, no un fallo silencioso, pero conviene
# que quede escrito para quien vaya a copiar este bloque.
from odoo.addons.base.models.ir_mail_server import IrMail_Server, MailDeliveryException

from .common import DiscussModerationMixin

# El correo fallido lo registra ADEMÁS `mail.mail` antes de re-lanzarlo
# (mail/models/mail_mail.py:951). Es ruido esperado en las pruebas de fallo, y
# silenciarlo por nombre evita confundirlo con un error real de la suite.
MAIL_MAIL_LOGGER = "odoo.addons.mail.models.mail_mail"

# El logger EXACTO del módulo bajo prueba. `assertLogs` sin nombre escucha la
# raíz y se conforma con cualquier línea que emita cualquier addon durante la
# llamada: una prueba así pasa el día que otro módulo tose y deja de vigilar la
# advertencia que le importa.
ALERT_LOGGER = (
    "odoo.addons.discuss_channel_moderation.models.discuss_channel_moderation"
)

LATE_ALERT_PARAM = "discuss_channel_moderation.late_alert_minutes"
LATE_ALERT_TEMPLATE = "discuss_channel_moderation.mail_template_late_pending_alert"


def _sending_on(cls):
    """Sustituto de `IrMailServer._disable_send`: aquí SÍ se envía.

    Se declara como función y se envuelve en `classmethod` al parchear para
    conservar la forma del original (odoo/addons/base/models/ir_mail_server.py
    :382-386); `mock.patch.object` restaura el descriptor tal cual lo encontró
    en `__dict__`, así que el corte del modo test vuelve a su sitio al salir
    del contexto y ninguna otra suite se lleva un servidor de correo abierto.
    """
    return False


def _no_smtp_session(self_srv, *args, **kwargs):
    """Sustituto de `IrMailServer._connect__`: ninguna conexión, ninguna sesión.

    `mail.mail.send` conecta ANTES de enviar (mail/models/mail_mail.py:719) y
    ese `_connect__` sólo devuelve `None` cuando el envío está desactivado
    (ir_mail_server.py:412-414). Al encender el envío hay que apagar esto a
    mano, o la prueba saldría a la red de la máquina donde se ejecuta.
    """
    return None


@tagged("post_install", "-at_install")
class TestModerationLateAlert(DiscussModerationMixin, TransactionCase):
    """Que la cola olvidada le suene a alguien, y una sola vez.

    El riesgo real de la pre-moderación no es técnico: es que el visitante que
    escribe y no ve su mensaje a los cuarenta minutos no vuelve. El contador de
    la ficha y el aviso por bus sólo llegan al moderador que YA está mirando
    Odoo; esta escalada es lo único que alcanza al que se fue a casa.

    Todo se prueba envejeciendo `create_date` a mano en lugar de congelar el
    reloj: `create_date` la escribe PostgreSQL (`now()` del servidor, no del
    proceso de Python), así que un `freeze_time` movería el corte y no la fila,
    y la prueba mediría el desfase entre dos relojes en vez de la regla.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_moderation_fixtures()
        cls.Moderation_ = cls.env["discuss.channel.moderation"]
        # EL REMITENTE TIENE QUE EXISTIR, y en un cron es quien lo ejecuta.
        # La plantilla NO fija `email_from` a propósito (que la cabecera la
        # ponga el dominio de alias que el servidor de IONOS acepta), así que
        # `mail.mail` la calcula a partir del autor -- el usuario del cron
        # (`_message_compute_author`, mail/models/mail_thread.py:2955-2960).
        # Ahora que el envío ya no se corta en seco en modo test, un autor sin
        # dirección haría saltar el `assert email_from` de `_build_email__`
        # (odoo/addons/base/models/ir_mail_server.py:589-590) y la clase entera
        # fallaría por la identidad del cron y no por la moderación. Se fija
        # aquí para que el remitente sea un dato de la prueba y no del volcado
        # de la base con la que se ejecute.
        cls.env.user.partner_id.email = "cron@example.com"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _capture_mails(self, failure=None):
        """Intercepta el ÚLTIMO eslabón real: `IrMail_Server.send_email`.

        Se observa ahí y no en `mail.template.send_mail` porque lo que hay que
        comprobar es que salió UN correo con UNOS destinatarios, no que se
        llamó a una función. Entre `send_mail` y el servidor hay agrupación por
        configuración, plantilla, `mail.mail` y `auto_delete`; contar antes de
        todo eso mediría la intención, no el resultado.

        Contar filas de `mail.mail` tampoco sirve: el aviso no deja fila detrás
        ni cuando sale ni cuando se descarta por falta de destinatarios
        (mail/models/mail_mail.py:281-282, y `_late_alert_send` la borra a mano
        cuando desactiva `auto_delete` para poder leerle el estado), así que la
        prueba vería cero en los dos casos.

        SON TRES PARCHES, NO UNO, y esa es la diferencia entre vigilar y hacer
        como que se vigila. Odoo 19 corta el envío UN NIVEL POR ENCIMA de
        `send_email`: `mail.mail._send` devuelve `True` en cuanto
        `IrMailServer._disable_send()` dice que sí (mail/models/mail_mail.py:
        765-768), y en modo test dice que sí SIEMPRE
        (odoo/addons/base/models/ir_mail_server.py:382-386). Con el parche sólo
        sobre `send_email`, `sent` valía `[]` pasara lo que pasase: la mitad de
        las aserciones de esta clase eran verdades vacías que no podían fallar
        ni aunque la alerta no enviase nada, que es exactamente lo que ocurría
        en producción.

        - `_disable_send` -> False: deja que el envío recorra el camino de
          verdad, que es el único en el que hay algo que observar.
        - `_connect__` -> None: y SÓLO por esto no se abre un SMTP real.
          `mail.mail.send` conecta antes de enviar (línea 719); sin este parche
          la suite intentaría hablar con `localhost:25` y mediría la máquina en
          la que corre.
        - `send_email`: el punto donde se lee QUÉ salió y hacia dónde.

        `failure` inyecta el fallo de entrega para comprobar que el cron no se
        lo traga. Puede ser una excepción (falla todo envío) o un invocable que
        recibe la cabecera `To` y devuelve la excepción, o `None` para dejarlo
        pasar: es lo que permite romper UN canal y no el otro con el mismo
        instrumento que usan las demás pruebas.
        """
        sent = []

        def _send_email(self_srv, message, *args, **kwargs):
            # `str()` explícito: con `email.policy.SMTP` las cabeceras no son
            # cadenas sino objetos de `email.headerregistry`
            # (odoo/addons/base/models/ir_mail_server.py:596). Son subclases de
            # `str`, así que comparar sin convertir FUNCIONA por accidente;
            # convertir deja escrito que el asunto se lee ya descodificado y no
            # como el `=?utf-8?...?=` que viaja por el cable.
            recipients = str(message["To"] or "")
            sent.append(
                {
                    "to": recipients,
                    "subject": str(message["Subject"] or ""),
                }
            )
            error = failure(recipients) if callable(failure) else failure
            if error:
                raise error
            return message["Message-Id"]

        with patch.object(IrMail_Server, "_disable_send", classmethod(_sending_on)):
            with patch.object(IrMail_Server, "_connect__", _no_smtp_session):
                with patch.object(IrMail_Server, "send_email", _send_email):
                    yield sent

    def _hold(self, channel, guest, body="hola"):
        """Retiene un mensaje y devuelve su fila pendiente."""
        self._post_as_guest(channel, guest, body)
        return self.Pending.search(
            [("channel_id", "=", channel.id)], order="id desc", limit=1
        )

    def _age(self, pending, minutes):
        """Envejece la fila: `create_date` la pone la base de datos, no el ORM.

        Se escribe por SQL directo porque `create_date` es `readonly` a nivel de
        ORM y un `write` normal lo ignoraría en silencio, dejando la fila
        recién nacida y la prueba en verde sin haber probado nada.
        """
        stamp = fields.Datetime.now() - timedelta(minutes=minutes)
        self.env.cr.execute(
            "UPDATE discuss_channel_pending_message SET create_date = %s WHERE id = %s",
            (stamp, pending.id),
        )
        pending.invalidate_recordset(["create_date"])
        return pending

    def _run_cron(self):
        return self.Moderation_._cron_alert_late_pending()

    # ------------------------------------------------------------------
    # El umbral
    # ------------------------------------------------------------------

    def test_recent_pending_is_not_alerted(self):
        """Un mensaje de hace cinco minutos NO es una emergencia.

        Es la mitad del valor de la alerta: si avisara de todo, avisaría de
        nada, porque el moderador acabaría filtrando el remitente.
        """
        pending = self._hold(self.channel_a, self.guest_1)
        self._age(pending, 5)
        with self._capture_mails() as sent:
            self._run_cron()
        self.assertEqual(sent, [], "cinco minutos no es un retraso, es la cola normal")
        self.assertFalse(
            pending.late_alert_date,
            "una fila no avisada no puede quedar marcada como avisada",
        )

    def test_late_pending_emails_channel_moderators(self):
        """Pasado el umbral, el correo va a los moderadores DE ESE canal.

        No a todos los moderadores de la plataforma: ser moderador del canal A
        no es tener que leer los problemas del canal B, y el aislamiento de
        colas que el módulo defiende en el backend no puede romperse por correo.
        """
        pending = self._hold(self.channel_a, self.guest_1)
        self._age(pending, 45)
        with self._capture_mails() as sent:
            self._run_cron()
        self.assertEqual(len(sent), 1, "un canal en retraso, un correo")
        self.assertIn(self.moderator_a.email, sent[0]["to"])
        self.assertNotIn(
            self.moderator_b.email,
            sent[0]["to"],
            "el moderador del canal B no modera el canal A",
        )
        self.assertIn(self.channel_a.name, sent[0]["subject"])
        self.assertTrue(
            pending.late_alert_date, "la fila avisada se marca para no repetir"
        )

    def test_threshold_parameter_is_honoured(self):
        """El umbral es un parámetro, no una constante escondida en el código.

        Se comprueba en los DOS sentidos con la misma fila: con 90 minutos no
        sale nada y con 10 sale el correo. Probar sólo el lado permisivo dejaría
        pasar una lectura del parámetro que devuelve siempre el valor por
        defecto.
        """
        pending = self._hold(self.channel_a, self.guest_1)
        self._age(pending, 45)
        params = self.env["ir.config_parameter"].sudo()

        params.set_param(LATE_ALERT_PARAM, "90")
        with self._capture_mails() as sent:
            self._run_cron()
        self.assertEqual(sent, [], "con umbral de 90 minutos, 45 no llega tarde")

        params.set_param(LATE_ALERT_PARAM, "10")
        with self._capture_mails() as sent:
            self._run_cron()
        self.assertEqual(len(sent), 1, "con umbral de 10 minutos, 45 sí llega tarde")

    # ------------------------------------------------------------------
    # Agrupación y repetición
    # ------------------------------------------------------------------

    def test_six_late_rows_produce_one_email(self):
        """Seis mensajes retenidos son UN problema, no seis correos.

        La auditoría previa de esta plataforma ya señaló amplificación de
        notificaciones. Un correo por fila la reproduciría justo en la función
        que existe para arreglarla, y el resultado práctico sería una regla de
        filtrado en el buzón del moderador.
        """
        pendings = self.Pending.browse()
        for index in range(6):
            pendings |= self._age(
                self._hold(self.channel_a, self.guest_1, "mensaje %s" % index), 45
            )
        self.assertEqual(len(pendings), 6)

        with self._capture_mails() as sent:
            self._run_cron()
        self.assertEqual(len(sent), 1, "seis filas de un canal, un solo correo")
        self.assertEqual(
            len(pendings.filtered("late_alert_date")),
            6,
            "las seis quedan marcadas, no sólo la que abrió el correo",
        )

    def test_already_alerted_row_is_not_alerted_again(self):
        """Al que ya avisaste y no ha actuado no le repites el aviso.

        Repetirlo cada cinco minutos convierte la alerta en ruido justo cuando
        más falta hace que se lea. Lo que mantiene audible un canal ACTIVO es
        que cada mensaje nuevo estrena su propio aviso, no que el viejo insista.
        """
        pending = self._age(self._hold(self.channel_a, self.guest_1), 45)
        with self._capture_mails() as first:
            self._run_cron()
        self.assertEqual(len(first), 1)
        stamped = pending.late_alert_date

        with self._capture_mails() as second:
            self._run_cron()
        self.assertEqual(second, [], "la segunda pasada no vuelve a avisar")
        self.assertEqual(
            pending.late_alert_date,
            stamped,
            "la marca original no se reescribe en cada pasada",
        )

        # Y un mensaje NUEVO sí estrena aviso: el canal no se queda mudo.
        self._age(self._hold(self.channel_a, self.guest_2, "otro"), 45)
        with self._capture_mails() as third:
            self._run_cron()
        self.assertEqual(len(third), 1, "una fila nueva merece su primer aviso")

    # ------------------------------------------------------------------
    # Qué NO se avisa
    # ------------------------------------------------------------------

    def test_decided_rows_are_never_alerted(self):
        """Aprobado o rechazado ya NO espera a nadie.

        Las filas decididas son historial y se conservan para siempre
        (el ACL niega `unlink`), así que sin este filtro la alerta acabaría
        avisando del archivo entero en cuanto envejeciese.
        """
        approved = self._age(self._hold(self.channel_a, self.guest_1, "sí"), 45)
        rejected = self._age(self._hold(self.channel_a, self.guest_2, "no"), 45)
        approved.with_user(self.moderator_a).action_approve()
        rejected.with_user(self.moderator_a).action_reject("spam")
        self.assertEqual(approved.state, "approved")
        self.assertEqual(rejected.state, "rejected")

        with self._capture_mails() as sent:
            self._run_cron()
        self.assertEqual(sent, [], "una decisión tomada no es una espera")
        self.assertFalse(approved.late_alert_date)
        self.assertFalse(rejected.late_alert_date)

    def test_archived_moderation_is_ignored(self):
        """Un canal cuya moderación se archivó ya no tiene SLA que incumplir.

        Archivar la fila es la forma documentada de apagar la moderación. Los
        mensajes que quedaron dentro siguen necesitando una decisión (está en el
        ROADMAP), pero nadie está obligado a tomarla en treinta minutos, y
        seguir mandando correos por ellos sería reclamar un compromiso que se
        retiró a propósito.
        """
        pending = self._age(self._hold(self.channel_a, self.guest_1), 45)
        self.moderation_a.active = False
        self.assertEqual(pending.state, "pending")

        with self._capture_mails() as sent:
            self._run_cron()
        self.assertEqual(sent, [], "moderación archivada, ninguna alerta")
        self.assertFalse(pending.late_alert_date)

    # ------------------------------------------------------------------
    # Nadie al otro lado
    # ------------------------------------------------------------------

    def test_channel_without_moderators_logs_warning_and_sends_nothing(self):
        """Un canal moderado SIN moderadores es la cola que nunca se vacía.

        Es exactamente el estado que esta alerta existe para evitar, así que no
        puede fallar en silencio: si no hay a quién escribir, hay que dejar
        escrito CUÁL es el canal, porque un log que dice "0 correos enviados" no
        se puede arreglar y uno que nombra el canal sí.
        """
        pending = self._age(self._hold(self.channel_a, self.guest_1), 45)
        self.moderation_a.moderator_user_ids = [(5, 0, 0)]

        with self._capture_mails() as sent:
            with self.assertLogs(ALERT_LOGGER, level="WARNING") as logs:
                self._run_cron()
        self.assertEqual(sent, [], "sin moderadores no hay a quién escribir")
        self.assertFalse(
            pending.late_alert_date,
            "no marcar la fila: el día que haya moderador, tiene que avisarse",
        )
        self.assertTrue(
            any(self.channel_a.name in line for line in logs.output),
            "la advertencia tiene que NOMBRAR el canal: %s" % logs.output,
        )

    def test_moderators_without_email_log_a_distinct_warning(self):
        """Tener moderador y poder escribirle no son lo mismo.

        Se separa del caso anterior porque se arreglan de forma distinta: uno
        pide asignar a alguien, el otro pide rellenar una dirección. Un único
        mensaje para ambos mandaría al administrador a buscar el problema
        equivocado.
        """
        pending = self._age(self._hold(self.channel_a, self.guest_1), 45)
        self.moderator_a.write({"email": False})

        with self._capture_mails() as sent:
            with self.assertLogs(ALERT_LOGGER, level="WARNING") as logs:
                self._run_cron()
        self.assertEqual(sent, [])
        self.assertFalse(pending.late_alert_date)
        self.assertTrue(
            any("email address" in line for line in logs.output),
            "la advertencia tiene que distinguir 'sin dirección': %s" % logs.output,
        )

    # ------------------------------------------------------------------
    # Fallos de entrega
    # ------------------------------------------------------------------

    @mute_logger(MAIL_MAIL_LOGGER)
    def test_delivery_failure_is_logged_and_retried(self):
        """Un envío que revienta NO puede pasar por avisado.

        En esta instalación ya hubo 956 correos atascados sin que nadie se
        enterase. Una escalada que se traga su propio fallo es peor que no
        tenerla, porque el problema queda marcado como atendido: por eso el
        `MailDeliveryException` se registra con traza y la fila se queda SIN
        marcar, para que la siguiente pasada lo reintente.
        """
        pending = self._age(self._hold(self.channel_a, self.guest_1), 45)
        failure = MailDeliveryException("IONOS dijo que no")

        with self._capture_mails(failure=failure) as attempted:
            with self.assertLogs(ALERT_LOGGER, level="ERROR") as logs:
                self._run_cron()
        self.assertEqual(len(attempted), 1, "se intentó el envío de verdad")
        self.assertFalse(
            pending.late_alert_date,
            "un envío fallido no marca la fila: hay que reintentarlo",
        )
        self.assertTrue(
            any("Late-moderation alert failed" in line for line in logs.output),
            "el fallo tiene que quedar en el log, no tragarse: %s" % logs.output,
        )

        # La siguiente pasada, con el correo funcionando, sí lo saca.
        with self._capture_mails() as retried:
            self._run_cron()
        self.assertEqual(len(retried), 1, "el reintento manda el aviso que faltó")
        self.assertTrue(pending.late_alert_date)

    @mute_logger(MAIL_MAIL_LOGGER)
    def test_one_broken_channel_does_not_silence_the_others(self):
        """Aislamiento de fila envenenada: un canal roto no se lleva al resto.

        Es el mismo patrón que `company_certification` usa en sus recordatorios:
        `try/except` por registro, `_logger.exception` y `continue`. Sin él, el
        primer canal con un problema de correo dejaría a todos los siguientes
        sin alerta y sin rastro de por qué.
        """
        self._age(self._hold(self.channel_a, self.guest_1), 45)
        self._age(self._hold(self.channel_b, self.guest_2), 45)

        def _only_channel_a_fails(recipients):
            if self.moderator_a.email in recipients:
                return MailDeliveryException("sólo el canal A falla")
            return None

        with self._capture_mails(failure=_only_channel_a_fails) as attempted:
            with self.assertLogs(ALERT_LOGGER, level="ERROR"):
                self._run_cron()
        self.assertEqual(len(attempted), 2, "se intentaron los dos canales")
        self.assertTrue(
            any(self.moderator_b.email in call["to"] for call in attempted),
            "el canal sano tiene que haber llegado al servidor: %s" % attempted,
        )
        pending_a = self.Pending.search([("channel_id", "=", self.channel_a.id)])
        pending_b = self.Pending.search([("channel_id", "=", self.channel_b.id)])
        self.assertFalse(pending_a.late_alert_date, "el canal que falló se reintenta")
        self.assertTrue(pending_b.late_alert_date, "el canal sano sí quedó avisado")

    # ------------------------------------------------------------------
    # El fallo que no levanta la voz
    # ------------------------------------------------------------------

    def test_a_send_that_delivers_nothing_is_not_counted_as_alerted(self):
        """El correo que se crea, no sale, y NO lanza ninguna excepción.

        Es el fallo real que se comió esta alerta en producción durante toda su
        primera versión: la plantilla iba con `use_default_to` puesto, así que
        el `email_to` nunca se evaluaba, `mail.mail` se quedaba sin
        destinatarios y recorría una lista de envíos VACÍA
        (mail/models/mail_mail.py:823-883) sin tocar el servidor ni levantar
        nada. El `try/except` del cron veía una vuelta limpia y estampaba las
        filas como avisadas: la pérdida silenciosa que esta función existe para
        romper, ejecutándose dentro de ella.

        Se reproduce encendiendo `use_default_to` en la propia plantilla en vez
        de simularlo con un parche, porque lo que hay que probar es que el cron
        detecta un envío VACÍO DE VERDAD, con su `mail.mail` y su estado, no
        que reacciona a un doble que devuelve lo que le digamos.
        """
        pending = self._age(self._hold(self.channel_a, self.guest_1), 45)
        template = self.env.ref(LATE_ALERT_TEMPLATE).sudo()
        template.use_default_to = True

        with self._capture_mails() as sent:
            with self.assertLogs(ALERT_LOGGER, level="ERROR") as logs:
                self._run_cron()
        self.assertEqual(sent, [], "sin destinatarios no llega nada al servidor")
        self.assertFalse(
            pending.late_alert_date,
            "un aviso que no salió no puede marcar la fila como avisada",
        )
        self.assertTrue(
            any("DELIVERED NOTHING" in line for line in logs.output),
            "el silencio tiene que nombrarse como tal: %s" % logs.output,
        )
        self.assertTrue(
            any("mail_email_missing" in line for line in logs.output),
            "y decir POR QUÉ no salió, que es lo que se arregla: %s" % logs.output,
        )

        # Reparada la plantilla, la siguiente pasada avisa: la fila seguía viva.
        template.use_default_to = False
        with self._capture_mails() as retried:
            self._run_cron()
        self.assertEqual(len(retried), 1, "el reintento manda el aviso que faltó")
        self.assertIn(self.moderator_a.email, retried[0]["to"])
        self.assertTrue(pending.late_alert_date)

    def test_the_shipped_template_resolves_its_own_recipients(self):
        """La plantilla instalada tiene que decidir ELLA a quién escribe.

        `use_default_to` viene a True de fábrica (mail/models/mail_template.py
        :57-59) y con él puesto Odoo ignora el `email_to` de la plantilla y
        pregunta al registro por su "cliente"
        (`_generate_template_recipients`, misma unidad, línea 447). Este modelo
        es un interruptor de moderación: no tiene cliente ni dirección, así que
        la respuesta es la lista vacía y el aviso no sale.

        Se afirma sobre el DATO instalado, no sobre el XML, porque el fichero
        va con `noupdate="1"`: lo que manda es el registro que hay en la base.
        """
        template = self.env.ref(LATE_ALERT_TEMPLATE)
        self.assertFalse(
            template.use_default_to,
            "con use_default_to el aviso no evalúa su propia lista de destinos",
        )
        self.assertIn(
            "moderator_user_ids",
            template.email_to or "",
            "la lista de destinos son los moderadores del canal, nadie más",
        )

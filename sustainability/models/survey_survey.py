# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# El cuestionario tiene UN dueño: company_certification. El xmlid es la vía
# directa; el tipo de certificación es la fuente de verdad real (su campo
# survey_id se declara por ref en company_certification/data/
# certification_type_data.xml, sin depender de ninguna marca booleana).
OWNER_SURVEY_XMLID = "company_certification.survey_sustainability"
OWNER_TYPE_XMLID = "company_certification.certification_type_sustainability"
OWNER_TYPE_CODE = "sustainability"


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    is_sustainability = fields.Boolean(
        string="Es evaluación Sostenibilidad",
        default=False,
        help="Si está marcado, esta encuesta se usa para certificación Sostenibilidad",
    )

    # Umbrales configurables de puntuación
    sustain_max_score = fields.Float(
        string="Puntuación máxima",
        default=80.0,
        help="Puntuación máxima posible (40 preguntas x 2 puntos)",
    )
    sustain_bronze_min = fields.Float(
        string="Mínimo Bronce",
        default=40.0,
        help="Puntuación mínima para obtener sello Bronce",
    )
    sustain_silver_min = fields.Float(
        string="Mínimo Plata",
        default=56.0,
        help="Puntuación mínima para obtener sello Plata",
    )
    sustain_gold_min = fields.Float(
        string="Mínimo Oro",
        default=71.0,
        help="Puntuación mínima para obtener sello Oro",
    )

    # Tiempos configurables
    sustain_cooldown_months = fields.Integer(
        string="Meses de espera tras reprobar",
        default=3,
        help="Número de meses que debe esperar el usuario para reintentar "
        "si no aprueba",
    )
    sustain_validity_years = fields.Integer(
        string="Años de validez del sello",
        default=1,
        help="Número de años que el sello permanece válido tras obtenerlo",
    )
    sustain_renewal_reminder_days = fields.Integer(
        string="Días de aviso previo a renovación",
        default=30,
        help="Días antes de la expiración para enviar recordatorio de renovación",
    )

    # ------------------------------------------------------------------
    # La marca is_sustainability se cura sola
    # ------------------------------------------------------------------
    # `is_sustainability` no es un dato del negocio: es un índice
    # desnormalizado del dueño real (certification.type.survey_id). Existe
    # porque el domain_force de una ir.rule no puede llamar a Python, y en
    # security/sustainability_security.xml hay reglas que lo consultan, más
    # los controladores públicos y las búsquedas de
    # models/survey_user_input.py.
    #
    # Si la marca se pierde, la vertical se degrada EN SILENCIO: las páginas
    # públicas se pintan con survey=False y las ir.rule no casan con nada.
    # Nadie ve un error. Antes de esto la marca sólo se ponía en el `-i`
    # (el <data noupdate="1"> se salta en cada `-u`, ver odoo/tools/convert.py)
    # y en una migración que corre una sola vez. Perderla era definitivo.

    @api.model
    def _sustainability_owner_survey(self):
        """Devuelve el cuestionario que ES la evaluación de Sostenibilidad.

        Se busca primero por xmlid, que es una lectura directa. Si el xmlid
        no está -borrado a mano, base restaurada a medias- se cae al tipo de
        certificación, que es quien de verdad sabe qué cuestionario usa la
        vertical. Devuelve un recordset vacío si no hay forma de saberlo.
        """
        survey = self.env.ref(OWNER_SURVEY_XMLID, raise_if_not_found=False)
        if survey:
            return survey
        cert_type = self.env.ref(OWNER_TYPE_XMLID, raise_if_not_found=False)
        if not cert_type:
            cert_type = (
                self.env["certification.type"]
                .with_context(active_test=False)
                .search([("code", "=", OWNER_TYPE_CODE)], limit=1)
            )
        if not cert_type:
            return self.browse()
        return cert_type.survey_id

    @api.model
    def _ensure_sustainability_flag(self):
        """Deja la marca donde tiene que estar, y sólo escribe si hace falta.

        Idempotente a propósito: en estado correcto no escribe nada, así se
        puede llamar en cada carga del registro sin coste. Devuelve el
        cuestionario dueño, o un recordset vacío si no se pudo resolver.

        No lanza NUNCA: se la llama desde `_register_hook`, y una excepción
        allí deja el registro sin cargar, o sea el servicio caído por una
        marca. Un fallo aquí se queda en el log, pero a voces.
        """
        surveys = self.with_context(active_test=False)
        try:
            # El savepoint es por si la escritura falla a nivel de base
            # (cursor de sólo lectura al recargar el registro dentro de una
            # petición): sin él, capturar la excepción en Python deja la
            # transacción abortada y revienta a quien nos llamó.
            with self.env.cr.savepoint():
                owner = surveys._sustainability_owner_survey()
                flagged = surveys.search([("is_sustainability", "=", True)])
                if not owner:
                    _logger.error(
                        "Sostenibilidad: no se puede resolver el cuestionario "
                        "dueño (ni %s ni %s ni un certification.type con "
                        "code=%s). La marca is_sustainability se deja como "
                        "está (%s cuestionario(s) marcado(s)); si son cero, "
                        "las ir.rule de la vertical no casan con nada y las "
                        "páginas públicas se pintan vacías.",
                        OWNER_SURVEY_XMLID,
                        OWNER_TYPE_XMLID,
                        OWNER_TYPE_CODE,
                        len(flagged),
                    )
                    return self.browse()
                intruders = flagged - owner
                if intruders:
                    _logger.warning(
                        "Sostenibilidad: %s cuestionario(s) llevan la marca "
                        "is_sustainability sin ser el dueño (%s); se les "
                        "quita. El dueño es %r (id=%s).",
                        len(intruders),
                        intruders.mapped("title"),
                        owner.title,
                        owner.id,
                    )
                    intruders.write({"is_sustainability": False})
                if owner not in flagged:
                    _logger.warning(
                        "Sostenibilidad: el cuestionario %r (id=%s) había "
                        "perdido la marca is_sustainability; se restaura. "
                        "Mientras faltaba, la vertical estaba muda: sin "
                        "evaluaciones visibles y sin sellos.",
                        owner.title,
                        owner.id,
                    )
                    owner.write({"is_sustainability": True})
                return owner
        except Exception:
            _logger.exception(
                "Sostenibilidad: fallo al asegurar la marca is_sustainability. "
                "La vertical puede estar degradada en silencio; revisar qué "
                "cuestionario la lleva."
            )
            return self.browse()

    def _register_hook(self):
        """Corre en CADA carga del registro: cada `-u` y cada arranque.

        Ésta es la pieza que hace la marca autorreparable. El `-i` lo cubre
        el post_init_hook del módulo, pero el `-i` sólo pasa una vez; esto
        pasa siempre. Barato: una búsqueda, y sólo escribe si no cuadra.

        El super() no es decorativo: silver_economy declara su propio
        `_register_hook` sobre este mismo modelo, y sin la llamada al padre
        sólo se ejecutaría el último de la cadena.
        """
        super()._register_hook()
        self._ensure_sustainability_flag()

    def action_start_sustainability_evaluation(self):
        """Acción para usuarios internos: inicia una evaluación real (no test)"""
        self.ensure_one()
        if not self.is_sustainability:
            raise UserError(
                _("Esta encuesta no está configurada como evaluación Sostenibilidad.")
            )

        user = self.env.user
        if not user.company_id:
            raise UserError(
                _("Debe tener una empresa asignada para realizar la evaluación.")
            )

        # Verificar cooldown
        last_attempt = self.env["survey.user_input"].search(
            [
                ("survey_id", "=", self.id),
                ("company_id", "=", user.company_id.id),
                ("state", "=", "done"),
                ("test_entry", "=", False),
            ],
            order="create_date desc",
            limit=1,
        )

        if (
            last_attempt
            and last_attempt.next_attempt_date
            and last_attempt.next_attempt_date > fields.Date.today()
        ):
            raise UserError(
                _("No puede realizar una nueva evaluación hasta el %s.")
                % last_attempt.next_attempt_date
            )

        # Crear respuesta real (no test) con company_id incluido para cumplir ir.rule
        answer = self.env["survey.user_input"].create(
            {
                "survey_id": self.id,
                "partner_id": user.partner_id.id,
                "company_id": user.company_id.id,
                "test_entry": False,
            }
        )

        return {
            "type": "ir.actions.act_url",
            "name": _("Iniciar evaluación Sostenibilidad"),
            "target": "new",
            "url": "/survey/start/%s?answer_token=%s"
            % (self.access_token, answer.access_token),
        }

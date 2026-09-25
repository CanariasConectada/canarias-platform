# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# A Font Awesome class and nothing else: the value is interpolated into a
# ``class`` attribute on public pages and into the backend preview.
ICON_RE = re.compile(r"^fa-[a-z0-9-]+$")
DEFAULT_ICON = "fa-check-circle"
# Question types whose score is one number: "score >= min_score" means
# something. A matrix or a multiple choice sums several answers, so a trigger
# on them would fire on a partial set; use answer triggers there instead.
SCORED_QUESTION_TYPES = ("simple_choice", "numerical_box")


class CertificationHighlight(models.Model):
    """One item of the icon list shown under a seal on a microsite.

    This is THE catalogue of a certification type: the administrator decides
    here which items exist, their icon and wording, and which answers of the
    questionnaire make each of them appear.

    An item without a trigger is a *baseline* item: every holder of the seal
    shows it. An item with a trigger shows up only when the company's
    awarding evaluation meets it:

    * ``question_id`` (+ ``min_score``): the score obtained on that question
      is at least ``min_score``;
    * ``answer_ids``: any of those answers was selected.

    When both are set, either one is enough.
    """

    _name = "certification.highlight"
    _description = "Certification Highlight"
    _order = "sequence, id"

    type_id = fields.Many2one(
        "certification.type",
        required=True,
        ondelete="cascade",
        index=True,
    )
    survey_id = fields.Many2one(related="type_id.survey_id")
    active = fields.Boolean(default=True)
    label = fields.Char(required=True, translate=True)
    description = fields.Char(
        translate=True,
        help="Optional second line, shown smaller under the label.",
    )
    icon = fields.Char(
        default=DEFAULT_ICON,
        required=True,
        help="Font Awesome 4 class shown next to the label, e.g. "
        "fa-wheelchair, fa-clock-o, fa-phone, fa-leaf. Lowercase letters, "
        "digits and hyphens only. The full list is at "
        "https://fontawesome.com/v4/icons/",
    )
    icon_preview = fields.Html(
        compute="_compute_icon_preview",
        sanitize=False,
        string="Preview",
    )
    sequence = fields.Integer(default=10)
    question_id = fields.Many2one(
        "survey.question",
        string="Trigger question",
        ondelete="set null",
        domain="[('survey_id', '=', survey_id), ('is_page', '=', False), "
        "('question_type', 'in', %r)]" % (list(SCORED_QUESTION_TYPES),),
        help="Show this item when the company scored at least the minimum "
        "score on this question (single choice or numeric questions). Leave "
        "both triggers empty to show the item to every holder of the seal.",
    )
    min_score = fields.Float(
        string="Minimum score",
        help="Score the answer to the trigger question must reach, e.g. 2 "
        "for a full 'Yes' in a No (0) / Partially (1) / Yes (2) question. "
        "Left at 0, it takes the question's best answer score.",
    )
    answer_ids = fields.Many2many(
        "survey.question.answer",
        "certification_highlight_answer_rel",
        "highlight_id",
        "answer_id",
        string="Trigger answers",
        domain="[('question_id.survey_id', '=', survey_id)]",
        help="Show this item when any of these answers was selected in the "
        "company's evaluation. Works on its own or together with the "
        "trigger question: either one is enough.",
    )
    is_baseline = fields.Boolean(
        compute="_compute_is_baseline",
        string="Always shown",
        help="No trigger: every holder of the seal shows this item.",
    )

    @api.depends("icon")
    def _compute_icon_preview(self):
        for highlight in self:
            icon = highlight.icon if ICON_RE.match(highlight.icon or "") else None
            highlight.icon_preview = (
                Markup('<i class="fa fa-lg %s" aria-hidden="true"></i>') % icon
                if icon
                else False
            )

    @api.depends("question_id", "answer_ids")
    def _compute_is_baseline(self):
        for highlight in self:
            highlight.is_baseline = highlight._is_baseline()

    def _is_baseline(self):
        self.ensure_one()
        return not self.question_id and not self.answer_ids

    @api.constrains("icon")
    def _check_icon(self):
        for highlight in self:
            if not ICON_RE.match(highlight.icon or ""):
                raise ValidationError(
                    _(
                        "The icon '%(icon)s' is not a Font Awesome class. "
                        "Use its name only, e.g. fa-wheelchair.",
                        icon=highlight.icon,
                    )
                )

    @api.constrains("question_id", "answer_ids", "type_id")
    def _check_triggers_belong_to_the_questionnaire(self):
        for highlight in self:
            survey = highlight.type_id.survey_id
            questions = highlight.question_id | highlight.answer_ids.question_id
            if questions and questions.survey_id != survey:
                raise ValidationError(
                    _(
                        "The triggers of '%(label)s' must come from the "
                        "questionnaire of %(type)s.",
                        label=highlight.label,
                        type=highlight.type_id.display_name,
                    )
                )
            if (
                highlight.question_id
                and highlight.question_id.question_type not in SCORED_QUESTION_TYPES
            ):
                raise ValidationError(
                    _(
                        "The trigger question of '%(label)s' must be a single "
                        "choice or numeric question. For other questions, use "
                        "trigger answers.",
                        label=highlight.label,
                    )
                )

    # A trigger question at min_score 0 would fire on any answer, "No"
    # included. Wherever the value comes from (form, import, code, data), an
    # empty minimum takes the question's best answer score.

    @api.model
    def _best_score(self, question):
        scores = question.suggested_answer_ids.mapped("answer_score")
        return max(scores) if scores else 0

    @api.onchange("question_id")
    def _onchange_question_id(self):
        if self.question_id and not self.min_score:
            self.min_score = self._best_score(self.question_id)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fill_empty_min_score()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "question_id" in vals or "min_score" in vals:
            self._fill_empty_min_score()
        return result

    def _fill_empty_min_score(self):
        for highlight in self:
            if highlight.question_id and not highlight.min_score:
                best = self._best_score(highlight.question_id)
                if best:
                    highlight.min_score = best

    def _is_triggered_by(self, lines):
        """Whether the evaluation lines ``lines`` meet this item's triggers.

        ``lines`` are the ``survey.user_input.line`` of the awarding
        evaluation. A baseline item is never "triggered": the caller decides
        about those.
        """
        self.ensure_one()
        if self.question_id and self.question_id.question_type in (
            SCORED_QUESTION_TYPES
        ):
            question_lines = lines.filtered(
                lambda line: line.question_id == self.question_id
            )
            if (
                question_lines
                and max(question_lines.mapped("answer_score")) >= self.min_score
            ):
                return True
        if self.answer_ids and lines.suggested_answer_id & self.answer_ids:
            return True
        return False

    def _to_amenity(self):
        """The dict the microsite template renders."""
        self.ensure_one()
        return {
            "label": self.label,
            "description": self.description or None,
            "icon": self.icon or DEFAULT_ICON,
        }

    # Migration to one catalogue (19.0.2.10.0) ----------------------------
    # Every step only fills what is empty, so running it again is a no-op.

    # Heading per seeded type: (English source, Spanish).
    _CC_DEFAULT_TITLES = {
        "company_certification.certification_type_silver": (
            "What this shop offers",
            "Lo que este comercio ofrece",
        ),
        "company_certification.certification_type_sustainability": (
            "Sustainable commitments of this shop",
            "Compromisos sostenibles de este comercio",
        ),
    }
    # THE source of the seeded items' triggers, for both paths: the data
    # file calls _cc_link_seed_triggers() on install, and the 19.0.2.10.0
    # migration calls it on update. The XML records carry no trigger fields.
    #   "question": question xmlid, "min_score": threshold;
    #   "best_answer_of": question xmlids whose top-scoring answer ("Sí")
    #   become the item's trigger answers (any one is enough).
    # Silver: a full "Sí" (2). Sostenibilidad: 1, the threshold the
    # administrator had set on its positive items.
    _CC_SEED_TRIGGERS = {
        "highlight_silver_access": {"question": "silver_economy_q1", "min_score": 2},
        "highlight_silver_seating": {"question": "silver_economy_q5", "min_score": 2},
        "highlight_silver_signage": {
            "best_answer_of": ["silver_economy_q2", "silver_economy_q3"]
        },
        "highlight_silver_pace": {"question": "silver_economy_q13", "min_score": 2},
        "highlight_silver_language": {
            "question": "silver_economy_q14",
            "min_score": 2,
        },
        "highlight_silver_support": {
            "question": "silver_economy_q18",
            "min_score": 2,
        },
        "highlight_silver_phone": {"question": "silver_economy_q20", "min_score": 2},
        "highlight_silver_web": {"question": "silver_economy_q7", "min_score": 2},
        "highlight_silver_personal": {
            "question": "silver_economy_q12",
            "min_score": 2,
        },
        "highlight_silver_adapted": {
            "question": "silver_economy_q29",
            "min_score": 2,
        },
        "highlight_silver_help": {"question": "silver_economy_q10", "min_score": 2},
        "highlight_sustainability_energy": {
            "question": "sust_economy_q1",
            "min_score": 1,
        },
        "highlight_sustainability_renewable": {
            "question": "sust_economy_q3",
            "min_score": 1,
        },
        "highlight_sustainability_waste": {
            "question": "sust_economy_q5",
            "min_score": 1,
        },
        "highlight_sustainability_water": {
            "question": "sust_economy_q8",
            "min_score": 1,
        },
        "highlight_sustainability_waste_food": {
            "question": "sust_economy_q9",
            "min_score": 1,
        },
        "highlight_sustainability_suppliers": {
            "question": "sust_economy_q10",
            "min_score": 1,
        },
        "highlight_sustainability_labour": {
            "question": "sust_economy_q15",
            "min_score": 1,
        },
        "highlight_sustainability_equality": {
            "question": "sust_economy_q17",
            "min_score": 1,
        },
        "highlight_sustainability_training": {
            "question": "sust_economy_q18",
            "min_score": 1,
        },
        "highlight_sustainability_governance": {
            "question": "sust_economy_q12",
            "min_score": 1,
        },
        "highlight_sustainability_local": {
            "question": "sust_economy_q24",
            "min_score": 1,
        },
    }

    @api.model
    def _cc_migrate_catalogue(self):
        """Merge the old positive items into this catalogue. Idempotent."""
        return {
            "titles": self._cc_fill_default_titles(),
            "seed_triggers": self._cc_link_seed_triggers(),
            **self._cc_fold_positive_items(),
        }

    @api.model
    def _cc_fill_default_titles(self):
        done = 0
        langs = {code for code, _name in self.env["res.lang"].get_installed()}
        for xmlid, (source, spanish) in self._CC_DEFAULT_TITLES.items():
            cert_type = self.env.ref(xmlid, raise_if_not_found=False)
            if not cert_type or cert_type.with_context(lang="en_US").amenities_title:
                continue
            cert_type.with_context(lang="en_US").amenities_title = source
            if "es_ES" in langs:
                cert_type.update_field_translations(
                    "amenities_title", {"es_ES": spanish}
                )
            done += 1
        return done

    @api.model
    def _cc_seed_trigger_values(self, spec):
        """Write values of one ``_CC_SEED_TRIGGERS`` entry, or None if a
        question it names is missing from this database."""

        def question(xmlid):
            return self.env.ref(
                "company_certification.%s" % xmlid, raise_if_not_found=False
            )

        if "question" in spec:
            trigger = question(spec["question"])
            if not trigger:
                return None
            return {"question_id": trigger.id, "min_score": spec["min_score"]}
        answers = self.env["survey.question.answer"]
        for xmlid in spec["best_answer_of"]:
            trigger = question(xmlid)
            if not trigger or not trigger.suggested_answer_ids:
                return None
            answers |= trigger.suggested_answer_ids.sorted("answer_score")[-1]
        return {"answer_ids": [(6, 0, answers.ids)]}

    @api.model
    def _cc_link_seed_triggers(self):
        """Give each seeded item its trigger, only where it has none."""
        done = 0
        for xmlid, spec in self._CC_SEED_TRIGGERS.items():
            highlight = self.env.ref(
                "company_certification.%s" % xmlid, raise_if_not_found=False
            )
            if not highlight or not highlight._is_baseline():
                continue
            values = self._cc_seed_trigger_values(spec)
            if values is None:
                continue
            highlight.write(values)
            done += 1
        return done

    @api.model
    def _cc_fold_positive_items(self):
        """Turn each unmigrated positive item into a catalogue item.

        An active item of the same type already triggered by the same
        question is reused (the positive item's minimum score wins: it is what the
        administrator chose); otherwise a new item is created with the
        positive item's label (every translation), icon and sequence.
        """
        folded = created = skipped = 0
        items = (
            self.env["certification.positive.item"]
            .with_context(active_test=False)
            .search([("migrated_highlight_id", "=", False)], order="id")
        )
        for item in items:
            cert_type = item.survey_id.certification_type_id or self.env[
                "certification.type"
            ].with_context(active_test=False).search(
                [("survey_id", "=", item.survey_id.id)], limit=1
            )
            if not cert_type or not item.question_id:
                skipped += 1
                _logger.warning(
                    "Positive item %s has no certification type or question; "
                    "left unmigrated.",
                    item.id,
                )
                continue
            # Active items only: folding into an archived one would hide
            # an item the old microsite showed. An archived match gets a new
            # active sibling instead, and the log says so.
            highlight = self.search(
                [
                    ("type_id", "=", cert_type.id),
                    ("question_id", "=", item.question_id.id),
                ],
                limit=1,
            )
            if not highlight and self.with_context(active_test=False).search_count(
                [
                    ("type_id", "=", cert_type.id),
                    ("question_id", "=", item.question_id.id),
                    ("active", "=", False),
                ]
            ):
                _logger.warning(
                    "Positive item %s: the catalogue item on the same question "
                    "is archived; a new active item is created so the "
                    "microsite keeps showing it.",
                    item.id,
                )
            if highlight:
                if highlight.min_score != item.min_score:
                    highlight.min_score = item.min_score
                folded += 1
            else:
                icon = item.icon if ICON_RE.match(item.icon or "") else DEFAULT_ICON
                highlight = self.create(
                    {
                        "type_id": cert_type.id,
                        "label": item.with_context(lang="en_US").label,
                        "icon": icon,
                        "sequence": item.sequence,
                        "question_id": item.question_id.id,
                        "min_score": item.min_score,
                    }
                )
                # Every translation of the label, as the administrator typed it.
                self.env.cr.execute(
                    "UPDATE certification_highlight SET label = src.label "
                    "FROM certification_positive_item src "
                    "WHERE src.id = %s AND certification_highlight.id = %s",
                    (item.id, highlight.id),
                )
                highlight.invalidate_recordset(["label"])
                created += 1
            item.migrated_highlight_id = highlight
            _logger.info(
                "Positive item %s (%s) migrated into catalogue item %s (%s).",
                item.id,
                item.label,
                highlight.id,
                highlight.label,
            )
        return {"folded": folded, "created": created, "skipped": skipped}

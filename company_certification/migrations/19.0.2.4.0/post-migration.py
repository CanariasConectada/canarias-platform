# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Turn the per-question recommendation into read-only guidance.

The certification questions used to carry their recommendation in
``comments_message`` with ``comments_allowed`` enabled, which the survey
frontend renders as a free-comment TEXTAREA using the recommendation as
placeholder — users thought they had to write something there. The XML
data now appends the recommendation to ``description`` (rendered as plain
read-only text under the question title) and drops ``comments_allowed``,
but both survey files are ``noupdate="1"``, so the live records get the
same transform here.

``comments_message`` itself is kept as data: the result page's
"Recomendaciones para mejorar" cards read it.
"""
import logging

from markupsafe import Markup, escape

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

RECOMMENDATION_P = Markup('<p class="text-muted fst-italic">%s</p>')


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    data = env["ir.model.data"].search(
        [
            ("module", "=", "company_certification"),
            ("model", "=", "survey.question"),
        ]
    )
    questions = (
        env["survey.question"]
        .browse(data.mapped("res_id"))
        .exists()
        .filtered(lambda q: not q.is_page)
    )
    if not questions:
        return

    langs = [code for code, _name in env["res.lang"].get_installed()]
    # Base language last: writing the en_US value also propagates to
    # translations that still equal the old base value, which must not
    # happen once those translations carry their own recommendation.
    langs.sort(key=lambda code: code == "en_US")

    appended = 0
    for question in questions:
        for lang in langs:
            localized = question.with_context(lang=lang)
            message = localized.comments_message
            if not message:
                continue
            description = localized.description or Markup("")
            if escape(message) in description:
                continue  # idempotent: recommendation already appended
            localized.description = description + RECOMMENDATION_P % message
            appended += 1

    questions.filtered("comments_allowed").write({"comments_allowed": False})
    _logger.info(
        "company_certification: recommendation appended to the description "
        "of %s questions (%s language values written), comment box disabled.",
        len(questions),
        appended,
    )

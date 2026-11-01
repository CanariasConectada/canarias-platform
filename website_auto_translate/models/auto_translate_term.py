# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .text_tools import unmask


class AutoTranslateTerm(models.Model):
    """One sentence of a page, in one language.

    A page is not one piece of text. Odoo keeps it as a single ``arch_db``
    blob and translates it term by term, so the queue -- which has one row per
    field -- had nothing better to show than fourteen thousand characters of
    ``<section data-snippet=…>`` under the heading "Original". Reported on
    2026-08-16: "veo que en las traducciones te estás trayendo html completo,
    solo debes colocar los valores en los textos".

    Exploding the page into its own terms fixes more than the display. Locking
    used to be per field, so a person correcting one sentence froze the whole
    page and the other thirty-two stopped improving. Here the lock is on the
    sentence, and only on the sentence.
    """

    _name = "auto.translate.term"
    _description = "Automatic Translation Term"
    _order = "job_id, sequence, id"
    _rec_name = "source_text"

    job_id = fields.Many2one(
        "auto.translate.job",
        required=True,
        ondelete="cascade",
        index=True,
    )
    lang = fields.Char(related="job_id.lang", store=True, index=True, readonly=True)
    website_id = fields.Many2one(
        "website",
        string="Website",
        index=True,
        readonly=True,
        help="Which site the page belongs to. Every site has a page called "
        "“Inicio”, so without this they all pile up under one heading.",
    )
    page_name = fields.Char(
        string="Page",
        index=True,
        help="Which page this sentence belongs to.",
    )
    page_url = fields.Char(
        string="Address",
        readonly=True,
        help="Where the page lives, so two pages with the same title can be "
        "told apart.",
    )
    section = fields.Char(
        index=True,
        help="The part of the page it sits in, taken from the heading above it.",
    )
    sequence = fields.Integer(
        default=10, help="Where it appears on the page, top to bottom."
    )

    source_term = fields.Text(
        readonly=True, help="The exact term Odoo extracted, markup and all."
    )
    term_hash = fields.Char(required=True, index=True, readonly=True)
    translated_term = fields.Text(readonly=True)

    source_text = fields.Text(string="Original", readonly=True)
    translated_text = fields.Text(
        string="Translation",
        help="Correct it here and the machine will never touch this sentence "
        "again. 【0】, 【1】… stand for the styling and icons the sentence "
        "carries; leave them where they belong and the page keeps them.",
    )
    state = fields.Selection(
        [("auto", "Translated"), ("locked", "Written by hand")],
        default="auto",
        required=True,
        index=True,
    )

    _one_per_job_and_term = models.Constraint(
        "UNIQUE (job_id, term_hash)",
        "That sentence is already listed for this page and language.",
    )

    # ------------------------------------------------------------------
    # Correcting
    # ------------------------------------------------------------------
    def write(self, vals):
        """A correction typed here is applied to the page and kept forever.

        The context flag is what tells a person's edit apart from the queue
        refreshing its own rows after a run. Without it every synchronisation
        would look like a correction and lock the entire site after the first
        cron.
        """
        correcting = "translated_text" in vals and not self.env.context.get(
            "auto_translate_sync"
        )
        if not correcting:
            return super().write(vals)
        vals = dict(vals, state="locked")
        for term in self:
            typed = vals["translated_text"]
            raw = unmask(typed, term.translated_term or term.source_term)
            super(AutoTranslateTerm, term).write(dict(vals, translated_term=raw))
            term._apply()
        return True

    def _apply(self):
        """Write this sentence's translation back onto the page itself."""
        self.ensure_one()
        job = self.job_id
        record = job._record()
        if record is None or not record:
            return
        source_lang = job._source_lang()
        # See ``AutoTranslateJob._inverse_translated_text``: writing the base
        # language must never be the first write the source gets.
        job._ensure_source_key(record, source_lang)
        record.with_context(auto_translate_skip=True).update_field_translations(
            job.field_name,
            {job.lang: {self.source_term: self.translated_term or ""}},
            source_lang=source_lang,
        )

    def action_unlock(self):
        """Hand the sentence back to the machine.

        The current text is adopted as ours on the way out, so the next run
        does not read it as somebody's work and lock it straight back again.
        """
        self.with_context(auto_translate_sync=True).write({"state": "auto"})
        jobs = self.mapped("job_id")
        # A page locked before this table existed carries that lock at field
        # level; leaving it would make the queue skip the page for good.
        jobs.filtered(lambda job: job.state == "locked").write({"state": "done"})
        return jobs.action_translate_again()

    def action_translate_again(self):
        """Redo this page's sentences, leaving the corrected ones alone."""
        return self.mapped("job_id").action_translate_again()

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import psycopg2

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL, config

from .text_tools import digest as _digest
from .text_tools import mask, section_at, section_markers, term_has_words

_logger = logging.getLogger(__name__)

DEFAULT_BATCH = 50
MAX_ATTEMPTS = 3

# Progress is committed in slices. A batch can run for minutes, and losing all
# of it because the last record misbehaved is exactly what happened the first
# time this ran against production.
COMMIT_EVERY = 20

# PostgreSQL kills the *whole* transaction on these, not just back to the
# savepoint. Nothing afterwards can succeed -- not even recording the error on
# the job -- so the batch has to stop and let the next run retry.
TRANSACTION_LOST = (
    psycopg2.extensions.TransactionRollbackError,
    psycopg2.errors.InFailedSqlTransaction,
)

# Odoo keeps this language as the technical base of every translatable jsonb
# column, and any language without its own entry falls back to it. Writing it
# therefore changes what every *untranslated* language displays, so it is
# always translated last: until then the fallback is still the Spanish source,
# which is a far better thing for a German visitor to land on than English.
BASE_LANG = "en_US"

# Which part of the site a row belongs to. The queue used to be grouped by
# technical model name, which reads as "ir.ui.view" to somebody who only wants
# to find the page whose German is wrong.
CONTENT_KINDS = {
    "ir.ui.view": "page",
    "product.template": "product",
    "product.public.category": "category",
    "product.attribute": "category",
    "product.attribute.value": "category",
    "product.tag": "category",
    "website.menu": "menu",
    "event.event": "event",
    "res.partner": "shop",
}


class AutoTranslateJob(models.Model):
    """One field of one record in one language, and what we last wrote there.

    This table is both the work queue and the audit trail, and it has to be
    both: knowing what *we* wrote last time is the only way to tell a stale
    machine translation (safe to replace) from something a merchant typed by
    hand (never to be touched).
    """

    _name = "auto.translate.job"
    _description = "Automatic Translation Job"
    _order = "state, write_date desc, id desc"
    _rec_name = "field_name"

    model_name = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    field_name = fields.Char(required=True)
    lang = fields.Char(required=True, index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("done", "Translated"),
            ("locked", "Written by hand"),
            ("failed", "Failed"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    engine_id = fields.Many2one(
        "auto.translate.engine", string="Winning engine", ondelete="set null"
    )
    source_hash = fields.Char(readonly=True)
    target_hash = fields.Char(readonly=True)
    attempts = fields.Integer(default=0, readonly=True)
    error = fields.Char(readonly=True)

    _one_per_field_and_lang = models.Constraint(
        "UNIQUE (model_name, res_id, field_name, lang)",
        "That field is already queued for that language.",
    )

    record_label = fields.Char(
        string="Content", compute="_compute_texts", help="Which record this is."
    )
    source_text = fields.Text(
        string="Original", compute="_compute_texts", help="What the merchant wrote."
    )
    translated_text = fields.Text(
        string="Translation",
        compute="_compute_texts",
        inverse="_inverse_translated_text",
        help="Correct it here and the machine will never touch it again.",
    )
    correctable_here = fields.Boolean(
        compute="_compute_texts",
        help="A page is corrected sentence by sentence instead, because a "
        "page is a set of terms rather than one piece of text.",
    )
    content_kind = fields.Selection(
        [
            ("page", "Page"),
            ("product", "Product"),
            ("category", "Shop category"),
            ("menu", "Navigation"),
            ("event", "Event"),
            ("shop", "Shop profile"),
            ("other", "Other"),
        ],
        compute="_compute_content_kind",
        store=True,
        index=True,
        help="What kind of content this is, so the queue can be read by "
        "section instead of by technical model name.",
    )
    term_ids = fields.One2many("auto.translate.term", "job_id")
    term_count = fields.Integer(compute="_compute_term_count")

    @api.depends("model_name")
    def _compute_content_kind(self):
        for job in self:
            job.content_kind = CONTENT_KINDS.get(job.model_name, "other")

    @api.depends("term_ids")
    def _compute_term_count(self):
        counts = dict(
            self.env["auto.translate.term"]._read_group(
                domain=[("job_id", "in", self.ids)],
                groupby=["job_id"],
                aggregates=["__count"],
            )
        )
        for job in self:
            job.term_count = counts.get(job, 0)

    @api.model
    def _source_lang(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("website_auto_translate.source_lang", "es_ES")
        )

    def _record(self):
        self.ensure_one()
        if self.model_name not in self.env:
            return None
        return self.env[self.model_name].sudo().browse(self.res_id).exists()

    # ------------------------------------------------------------------
    # Reading and correcting the text itself
    # ------------------------------------------------------------------
    @api.depends("model_name", "res_id", "field_name", "lang", "state", "term_ids")
    def _compute_texts(self):
        """Put the original and the machine's answer side by side.

        Without this the queue is a list of row identifiers: to judge whether a
        translation is wrong you would have to open the product, switch
        language and read it, once per record. Nobody audits 5500 rows that
        way, which is how "Cheetos" stayed "Käse" until a person happened to
        look at the shop.
        """
        source_lang = self._source_lang()
        for job in self:
            record = job._record()
            field = record and record._fields.get(job.field_name)
            if not record or field is None:
                job.record_label = job.source_text = job.translated_text = False
                job.correctable_here = False
                continue
            job.record_label = record.display_name
            # A ``model_terms`` field -- a page -- is a bag of terms, not one
            # string, so it cannot be corrected by retyping the whole thing.
            job.correctable_here = not callable(field.translate)
            if not job.correctable_here:
                # Never the raw value here. A page is a fourteen-thousand
                # character blob of ``<section data-snippet=…>``; putting that
                # in a list column tells a human nothing and hides the one
                # thing they came for, which is the sentence that reads wrong.
                summary = self.env._(
                    "%(count)s sentences — open them to read and correct them",
                    count=job.term_count,
                )
                job.source_text = job.translated_text = summary
                continue
            job.source_text = record.with_context(lang=source_lang)[job.field_name]
            job.translated_text = record.with_context(lang=job.lang)[job.field_name]

    def _inverse_translated_text(self):
        """Take the correction, and take the record out of the machine's hands.

        Locking here rather than waiting for the next run is deliberate: a
        person who has just fixed a translation should not have to trust that
        some later job will notice.
        """
        source_lang = self._source_lang()
        for job in self:
            record = job._record()
            if record is None or not record:
                continue
            field = record._fields.get(job.field_name)
            if field is None or callable(field.translate):
                raise UserError(
                    self.env._(
                        "A page is corrected sentence by sentence: open its "
                        "sentences and fix the one that reads wrong."
                    )
                )
            # A correction into English is a write on the jsonb base; the
            # source has to own its key first or the Spanish is gone. Same
            # guard as :meth:`_run_one`, for the same reason.
            job._ensure_source_key(record, source_lang)
            record.with_context(auto_translate_skip=True).update_field_translations(
                job.field_name,
                {job.lang: job.translated_text or False},
                source_lang=source_lang,
            )
            super(AutoTranslateJob, job).write(
                {"state": "locked", "error": False, "attempts": 0}
            )

    # ------------------------------------------------------------------
    # Queueing
    # ------------------------------------------------------------------
    @api.model
    def _enqueue_many(self, records, field_names, langs):
        """Mark work to be done later, as cheaply as possible.

        This runs inside the merchant's own save, so it does exactly one search
        and one create: no reading of field values, no hashing, no network.
        """
        if not records or not field_names or not langs:
            return self.browse()
        model_name = records._name
        wanted = {(field_name, lang) for field_name in field_names for lang in langs}
        existing = self.search(
            [
                ("model_name", "=", model_name),
                ("res_id", "in", records.ids),
                ("field_name", "in", list(field_names)),
                ("lang", "in", list(langs)),
            ]
        )
        by_key = {(job.res_id, job.field_name, job.lang): job for job in existing}
        # A field a merchant translated by hand stays theirs, even when the
        # Spanish original changes afterwards. Unlocking is a deliberate act.
        reopen = existing.filtered(lambda job: job.state in ("done", "failed"))
        if reopen:
            reopen.write({"state": "pending", "attempts": 0, "error": False})
        missing = [
            {
                "model_name": model_name,
                "res_id": record.id,
                "field_name": field_name,
                "lang": lang,
            }
            for record in records
            for field_name, lang in wanted
            if (record.id, field_name, lang) not in by_key
        ]
        return existing + self.create(missing)

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------
    @api.model
    def _cron_run_pending(self):
        if not self.env["auto.translate.mixin"]._auto_translate_active():
            return 0
        params = self.env["ir.config_parameter"].sudo()
        limit = int(
            params.get_param("website_auto_translate.batch_size", DEFAULT_BATCH)
        )
        # Claim the rows instead of plainly searching them. Two runners over
        # the same page -- a cron and somebody draining the queue by hand -- is
        # enough for PostgreSQL to raise a serialization failure, and that
        # aborts the entire transaction rather than just the record being
        # worked on. ``SKIP LOCKED`` lets a second runner take different work
        # instead of colliding. The ``lang = base`` term sorts English last for
        # the reason given on ``BASE_LANG``.
        self.env.cr.execute(
            SQL(
                """
                SELECT id FROM auto_translate_job
                 WHERE state = 'pending'
                 ORDER BY (lang = %s), id
                 LIMIT %s
                   FOR UPDATE SKIP LOCKED
                """,
                BASE_LANG,
                limit,
            )
        )
        return self.browse([row[0] for row in self.env.cr.fetchall()])._run()

    # ------------------------------------------------------------------
    # A page, sentence by sentence
    # ------------------------------------------------------------------
    @api.model
    def _extract_terms(self, field, value):
        """The sentences Odoo would translate in ``value``, in reading order.

        ``get_trans_terms`` rather than our own parser: it is the very function
        the ORM uses to decide what a term is, so anything else would drift the
        first time a page used markup we had not thought of.
        """
        seen, ordered = set(), []
        for term in field.get_trans_terms(value or ""):
            if term in seen or not term_has_words(term):
                continue
            seen.add(term)
            ordered.append(term)
        return ordered

    def _page_label(self, record):
        """The site, the title and the address a person would recognise.

        ``display_name`` on its own is not enough to file a sentence under.
        Every one of the five sites has a homepage called "Inicio" and a
        "Términos y Condiciones", so grouping by it piled 123 sentences from
        five different pages under a single heading -- which is why the portal
        home looked missing when it had been there all along.

        The title comes from the ``website.page`` when there is one: a view is
        named for whoever built it ("Events (oe_structure_we_index_0)"), a page
        is named for what a visitor reads.
        """
        website = self.env["website"]
        if "website_id" in record._fields:
            website = record.website_id
        label, url = record.display_name, ""
        if record._name == "ir.ui.view":
            page = (
                self.env["website.page"]
                .sudo()
                .search([("view_id", "=", record.id)], limit=1)
            )
            if page:
                label = page.name or label
                url = page.url or ""
        return website, label, url

    def _sync_terms(self, record=None, source_value=None, written=None):
        """Materialise this page's sentences so a person can read and fix them.

        Also the moment a correction made on the website itself is noticed: a
        sentence whose stored translation is no longer the one we wrote was
        retyped by somebody, and from here on it is theirs.

        ``written`` is the ``{source_term: translation}`` mapping the run has
        just handed to ``update_field_translations``. Those sentences are ours
        by definition, however much they differ from the row: comparing the
        page against the row's *previous* text is exactly how a re-translation
        used to read as a person retyping the page. Measured on 2026-08-26:
        one cron pass locked every sentence it had itself just produced, and
        "translate again" then skipped them for good.
        """
        self.ensure_one()
        record = record if record is not None else self._record()
        if record is None or not record:
            return self.env["auto.translate.term"]
        field = record._fields.get(self.field_name)
        if field is None or not callable(field.translate):
            return self.env["auto.translate.term"]
        source_lang = self._source_lang()
        if source_value is None:
            source_value = record.with_context(lang=source_lang)[self.field_name] or ""
        Term = self.env["auto.translate.term"].sudo()
        stored_value = self._stored_translation(record) or source_value
        translations = field.get_translation_dictionary(
            source_value, {self.lang: stored_value}
        )
        markers = section_markers(source_value)
        existing = {row.term_hash: row for row in self.term_ids}
        website, label, url = self._page_label(record)
        # A page locked before this table existed was locked by a person, and
        # every sentence on it has to inherit that or the next run would undo
        # work somebody did by hand.
        born_locked = self.state == "locked"
        written = written or {}
        cursor = 0
        keep = Term.browse()
        for position, term in enumerate(self._extract_terms(field, source_value), 1):
            found = source_value.find(term, cursor)
            if found >= 0:
                cursor = found + len(term)
            raw = translations.get(term, {}).get(self.lang) or ""
            fingerprint = _digest(term)
            values = {
                "sequence": position,
                "section": section_at(markers, found),
                "website_id": website.id,
                "page_name": label,
                "page_url": url,
                "source_term": term,
                "source_text": mask(term),
            }
            row = existing.get(fingerprint)
            if row:
                retyped = (
                    row.state == "auto"
                    and raw
                    and raw != row.translated_term
                    and term not in written
                )
                if retyped:
                    # Retyped on the website. Nobody has to tell us.
                    values["state"] = "locked"
                values.update(translated_term=raw, translated_text=mask(raw))
                row.with_context(auto_translate_sync=True).write(values)
            else:
                row = Term.with_context(auto_translate_sync=True).create(
                    dict(
                        values,
                        job_id=self.id,
                        term_hash=fingerprint,
                        translated_term=raw,
                        translated_text=mask(raw),
                        state="locked" if born_locked else "auto",
                    )
                )
            keep |= row
        (self.term_ids - keep).unlink()
        return keep

    def action_sync_terms(self):
        """Rebuild the sentence list of every page selected."""
        for job in self:
            job._sync_terms()
        return True

    def action_open_terms(self):
        self.ensure_one()
        self._sync_terms()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Sentences — %(page)s", page=self.record_label or ""),
            "res_model": "auto.translate.term",
            "view_mode": "list",
            "domain": [("job_id", "=", self.id)],
            "context": {"search_default_group_section": 1, "create": False},
        }

    def _run(self):
        """Translate each job in its own transaction slice.

        One unreachable provider or one malformed record must not roll back the
        translations that already succeeded in this batch, so every job commits
        or rolls back alone.
        """
        source_lang = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("website_auto_translate.source_lang", "es_ES")
        )
        done = 0
        for position, job in enumerate(self, start=1):
            try:
                with self.env.cr.savepoint():
                    if job._run_one(source_lang):
                        done += 1
            except TRANSACTION_LOST as error:
                # Everything committed so far is safe; the rest stays pending.
                _logger.warning(
                    "Auto translate batch abandoned after %s jobs, "
                    "the transaction is gone: %s",
                    position - 1,
                    error,
                )
                raise
            except Exception as error:  # noqa: BLE001 - recorded on the job itself
                _logger.warning(
                    "Auto translate failed on %s(%s).%s [%s]: %s",
                    job.model_name,
                    job.res_id,
                    job.field_name,
                    job.lang,
                    error,
                )
                job.write(
                    {
                        "state": (
                            "failed" if job.attempts + 1 >= MAX_ATTEMPTS else "pending"
                        ),
                        "attempts": job.attempts + 1,
                        "error": str(error)[:255],
                    }
                )
            if position % COMMIT_EVERY == 0 and not config["test_enable"]:
                self.env.cr.commit()
        return done

    def _run_one(self, source_lang):
        self.ensure_one()
        record = self._record()
        if record is None or not record:
            self.unlink()
            return False
        field = record._fields.get(self.field_name)
        if field is None or not field.translate:
            self.write({"state": "failed", "error": "Field is not translatable"})
            return False

        # Before reading anything: the source language has to own its own key.
        self._ensure_source_key(record, source_lang)
        source_value = record.with_context(lang=source_lang)[self.field_name]
        if not source_value:
            self.write(
                {"state": "done", "source_hash": _digest(""), "target_hash": False}
            )
            return False
        stored = self._stored_translation(record)
        # A page is protected sentence by sentence, so it is read *before* the
        # engine is asked anything: whatever somebody retyped on the website
        # becomes locked here and is then left out of the request.
        per_term = callable(field.translate)
        if per_term:
            self._sync_terms(record, source_value)

        if not per_term and not self._may_overwrite(stored, source_value):
            self.write({"state": "locked"})
            return False
        # Already translated from exactly this source, and our text is still
        # the one in place: re-queueing it was a false alarm.
        if self.target_hash and self.source_hash == _digest(source_value):
            self.write({"state": "done", "error": False})
            return False

        payload, engine = self._translate_payload(field, source_value, source_lang)
        if payload is None:
            self.write(
                {
                    "state": "done",
                    "source_hash": _digest(source_value),
                    "target_hash": _digest(stored),
                    "error": False,
                }
            )
            return False

        # ``update_field_translations`` rather than a plain write. Writing a
        # translated value onto a *model_terms* field under a language context
        # does not store a translation at all: Odoo treats it as the definition
        # changing and copies it over every language, wiping the Spanish
        # original. Measured on 2026-08-14 -- one German write left
        # ``{'de_DE': …, 'en_US': …, 'es_ES': …}`` all holding the German.
        record.with_context(auto_translate_skip=True).update_field_translations(
            self.field_name, {self.lang: payload}, source_lang=source_lang
        )
        if per_term:
            # Refresh the rows with what the engine actually produced, so the
            # next run compares against our own output rather than the text
            # that was there before it. The payload is handed over so this
            # refresh cannot mistake our own fresh output for a correction.
            self._sync_terms(record, source_value, written=payload)
        stored_now = self._stored_translation(record)
        self.write(
            {
                "state": "done",
                "engine_id": engine.id if engine else False,
                "source_hash": _digest(source_value),
                "target_hash": _digest(stored_now),
                "attempts": self.attempts + 1,
                "error": False,
            }
        )
        return stored_now != stored

    def _ensure_source_key(self, record, source_lang):
        """Give the source language its own entry before anything writes the base.

        Content on this platform is written in Spanish and was stored *only* in
        ``en_US``, the technical base every unset language falls back to. English
        is a legitimate translation target, so when its turn came the machine
        wrote English over that base -- and because Spanish had no key of its
        own, every Spanish visitor started reading the machine's English.
        Measured on 2026-08-14: 1415 products, 400 categories and 32 pages lost
        their Spanish this way, and it had to be recovered from a dump.

        Translating the base *last*, which is what this module did until
        19.0.2.0.0, is not a defence. It only decides when the damage happens,
        not whether: the base is overwritten the moment its turn finally comes.
        The source has to own its key first, and this is the only place that can
        guarantee it -- one statement, in the same transaction slice as the
        write that would otherwise destroy it.

        Done in SQL rather than through ``update_field_translations`` because the
        jsonb value is the whole stored text for plain and ``model_terms`` fields
        alike. Copying a key across therefore needs no term extraction, cannot
        re-encode entities, and cannot be mistaken by the ORM for the definition
        changing.
        """
        self.ensure_one()
        if source_lang == BASE_LANG:
            return
        record.flush_recordset([self.field_name])
        column = SQL.identifier(self.field_name)
        self.env.cr.execute(
            SQL(
                """
                UPDATE %s
                   SET %s = jsonb_set(%s, %s, %s -> %s)
                 WHERE id = %s
                   AND %s ? %s
                   AND NOT %s ? %s
                """,
                SQL.identifier(record._table),
                column,
                column,
                [source_lang],
                column,
                BASE_LANG,
                record.id,
                column,
                BASE_LANG,
                column,
                source_lang,
            )
        )
        record.invalidate_recordset([self.field_name])

    def _stored_translation(self, record):
        """The raw value held for this job's language, or ``None`` if there is none.

        Reading the field in the target language cannot answer "is there a
        translation here?". Odoo stores a translatable column as jsonb keyed by
        language in which ``en_US`` is the *technical base*, and any language
        without its own key silently returns that base. So the moment English
        is written, every still-untranslated language starts reading English --
        which is indistinguishable from a human translation and would lock the
        record forever. Asking the column directly is the only honest answer.
        """
        self.ensure_one()
        record.flush_recordset([self.field_name])
        self.env.cr.execute(
            SQL(
                "SELECT %s FROM %s WHERE id = %s",
                SQL.identifier(self.field_name),
                SQL.identifier(record._table),
                record.id,
            )
        )
        row = self.env.cr.fetchone()
        stored = row[0] if row else None
        if not isinstance(stored, dict):
            return None
        return stored.get(self.lang)

    def _may_overwrite(self, stored, source_value):
        """Whether replacing what is stored would destroy somebody's work.

        ``stored`` is ``None`` when this language has never been written, which
        is the safe case. A value that is merely the untranslated source is
        also ours to replace. Anything else, on a field we have no record of
        writing, was typed by a human.
        """
        self.ensure_one()
        if self.target_hash:
            return _digest(stored) == self.target_hash
        return not stored or stored == source_value

    def _translate_payload(self, field, source_value, source_lang):
        """Build what ``update_field_translations`` expects for this field kind.

        A plain translated field takes the whole translated string. A
        *model_terms* field -- ``arch_db``, rich descriptions -- takes a
        ``{term: translation}`` mapping instead, and the terms have to come out
        of Odoo's own ``xml_translate``/``html_translate`` extraction. Handing
        the raw markup to a translation engine is how you get back a page whose
        ``t-if`` attributes have been helpfully translated into German.

        Two kinds of term are deliberately left out of the request:

        * anything with no letters in it -- a lone ``&amp;nbsp;``, an icon tag
          on its own. There is nothing to translate, and handing an entity to
          an engine is how the Italian pages came back reading ``&Nbsp;``;
        * a sentence somebody corrected by hand. Protecting the whole page
          because one line was fixed is what this used to do, and it stopped
          the other thirty-two lines ever improving.

        Returns ``(payload, engine)``, or ``(None, None)`` when the value holds
        nothing a translator could act on.
        """
        Engine = self.env["auto.translate.engine"]
        if not callable(field.translate):
            translated, engine = Engine._run(
                [source_value], source_lang, self.lang, is_html=False
            )
            return translated[0], engine

        locked = set(
            self.term_ids.filtered(lambda row: row.state == "locked").mapped(
                "source_term"
            )
        )
        unique = [
            term
            for term in self._extract_terms(field, source_value)
            if term not in locked
        ]
        if not unique:
            return None, None
        translated, engine = Engine._run(unique, source_lang, self.lang, is_html=True)
        return dict(zip(unique, translated)), engine

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_retry(self):
        self.write({"state": "pending", "attempts": 0, "error": False})

    def action_unlock(self):
        """Give up a hand-written translation and let the machine have it back.

        Unlocking has to *adopt* the text that is there as if we had written
        it. Simply clearing the hash would hand the record straight back to
        :meth:`_may_overwrite`, which would see a target that differs from the
        source, conclude a human wrote it, and lock it again on the very next
        run.
        """
        for job in self:
            record = job._record()
            current = job._stored_translation(record) if record else ""
            job.write(
                {
                    "state": "pending",
                    "target_hash": _digest(current),
                    "attempts": 0,
                    "error": False,
                }
            )

    def action_run_now(self):
        self._run()

    def action_translate_again(self):
        """Redo the translation even though the source has not changed.

        The ordinary skip -- same source, our own text still in place, nothing
        to do -- is right for every change on the *merchant's* side. It is
        wrong for a change on ours: a new protected term, a corrected glossary,
        a different engine. Those change the answer without changing the
        question, and without this the queue would answer "already done" to all
        1424 products.

        Two details that are not obvious and cost a run to find out:

        * the stored text is adopted as ours before the source hash is
          cleared. Leaving a hash that no longer matches would make
          :meth:`_may_overwrite` read the machine's own output as somebody's
          hand translation and lock the row instead of redoing it;
        * a row somebody corrected by hand is never touched. Regenerating a
          language must not quietly undo the corrections that were the whole
          reason for keeping this engine.
        """
        redo = self.filtered(lambda job: job.state != "locked")
        for job in redo:
            record = job._record()
            current = job._stored_translation(record) if record else ""
            job.write(
                {
                    "state": "pending",
                    "target_hash": _digest(current),
                    "source_hash": False,
                    "attempts": 0,
                    "error": False,
                }
            )
        return len(redo)

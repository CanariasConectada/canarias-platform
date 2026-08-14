# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import logging

import psycopg2

from odoo import api, fields, models
from odoo.tools import SQL, config

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


def _digest(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


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

    def _record(self):
        self.ensure_one()
        if self.model_name not in self.env:
            return None
        return self.env[self.model_name].sudo().browse(self.res_id).exists()

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

        source_value = record.with_context(lang=source_lang)[self.field_name]
        if not source_value:
            self.write(
                {"state": "done", "source_hash": _digest(""), "target_hash": False}
            )
            return False
        stored = self._stored_translation(record)

        if not self._may_overwrite(stored, source_value):
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

        Returns ``(payload, engine)``, or ``(None, None)`` when the value holds
        nothing a translator could act on.
        """
        Engine = self.env["auto.translate.engine"]
        translate = field.translate
        if not callable(translate):
            translated, engine = Engine._run(
                [source_value], source_lang, self.lang, is_html=False
            )
            return translated[0], engine

        terms = []

        def collect(term):
            terms.append(term)
            return term

        translate(collect, source_value)
        unique = list(dict.fromkeys(term for term in terms if term and term.strip()))
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

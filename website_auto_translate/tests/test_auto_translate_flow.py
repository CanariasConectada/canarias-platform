# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

import psycopg2

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

SOURCE = "es_ES"
TARGET = "en_US"


def fake_translate(engine, texts, source_lang, target_lang, is_html=False):
    """A deterministic stand-in so the tests never touch a translation service."""
    return ["[%s] %s" % (target_lang, text) for text in texts]


@tagged("post_install", "-at_install")
class TestAutoTranslateFlow(TransactionCase):
    """Saving content queues it, the cron writes it, and nobody's work is lost.

    Asked for on 2026-08-14: "que puedas traducir cada vez que alguien haga
    algun cambio en la pagina, en los eventos, en la tienda".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang(SOURCE)
        cls.env["res.lang"]._activate_lang(TARGET)
        cls.company = cls.env.ref("base.main_company")
        cls.company.auto_translate_enabled = True
        cls.engine = cls.env["auto.translate.engine"].create(
            {"name": "Flow Test Engine", "engine_type": "libretranslate"}
        )
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("website_auto_translate.enabled", "True")
        params.set_param("website_auto_translate.source_lang", SOURCE)
        params.set_param("website_auto_translate.mode", "single")
        params.set_param("website_auto_translate.engine_id", str(cls.engine.id))
        cls.Job = cls.env["auto.translate.job"]
        # Every real user of this platform runs the interface in Spanish, which
        # is what makes "the write came in under the source language" the
        # normal case rather than an assumption.
        cls.Product = cls.env["product.template"].with_context(lang=SOURCE)

    def _jobs_for(self, record, lang=TARGET):
        """Jobs for a record, in every language when ``lang`` is falsy."""
        domain = [("model_name", "=", record._name), ("res_id", "=", record.id)]
        if lang:
            domain.append(("lang", "=", lang))
        return self.Job.search(domain)

    def _run_queue(self):
        with patch.object(type(self.engine), "translate", fake_translate):
            return self.Job.search([("state", "=", "pending")])._run()

    # ------------------------------------------------------------------
    # Queueing
    # ------------------------------------------------------------------
    def test_saving_a_product_queues_every_target_language(self):
        product = self.Product.create({"name": "Queso de flor"})
        langs = self._jobs_for(product).mapped("lang")
        self.assertIn(TARGET, langs)
        self.assertNotIn(SOURCE, langs, "the source language is not a target")

    def test_the_queue_never_grows_a_second_row_for_the_same_field(self):
        """Saving ten times must leave one row, not ten."""
        product = self.Product.create({"name": "Gofio escaldado"})
        for attempt in range(3):
            product.write({"name": "Gofio escaldado %s" % attempt})
        rows = self._jobs_for(product).filtered(lambda job: job.field_name == "name")
        self.assertEqual(len(rows), 1)

    def test_editing_a_translation_does_not_queue_it_again(self):
        """Otherwise the cron would immediately undo what the merchant typed."""
        product = self.Product.create({"name": "Papas arrugadas"})
        self._jobs_for(product).unlink()

        product.with_context(lang=TARGET).write({"name": "Wrinkly potatoes"})

        self.assertFalse(self._jobs_for(product))

    def test_a_shop_that_did_not_opt_in_is_left_alone(self):
        """The rollout starts with the portal and the zones, not 216 shops."""
        outsider = self.env["res.company"].create(
            {"name": "Auto Translate Outsider", "auto_translate_enabled": False}
        )
        product = self.Product.create(
            {"name": "Fuera de alcance", "company_ids": [(6, 0, outsider.ids)]}
        )
        self.assertFalse(self._jobs_for(product))

    def test_nothing_is_queued_while_the_feature_is_off(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "website_auto_translate.enabled", "False"
        )
        product = self.Product.create({"name": "Mojo picón"})
        self.assertFalse(self._jobs_for(product))

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------
    def test_the_cron_writes_the_translation(self):
        product = self.Product.create({"name": "Bienmesabe"})
        self._run_queue()
        self.assertEqual(product.with_context(lang=TARGET).name, "[en_US] Bienmesabe")
        self.assertEqual(
            product.with_context(lang=SOURCE).name,
            "Bienmesabe",
            "the source text must come back untouched",
        )

    def test_running_twice_does_not_call_the_engine_again(self):
        """The source has not changed, so there is nothing to redo."""
        product = self.Product.create({"name": "Ropa vieja"})
        self._run_queue()
        job = self._jobs_for(product).filtered(lambda j: j.field_name == "name")
        job.action_retry()

        with patch.object(type(self.engine), "translate") as translate:
            job._run()
        translate.assert_not_called()
        self.assertEqual(job.state, "done")

    def test_a_changed_source_is_translated_again(self):
        product = self.Product.create({"name": "Sancocho"})
        self._run_queue()
        product.write({"name": "Sancocho canario"})
        self._run_queue()
        self.assertEqual(
            product.with_context(lang=TARGET).name, "[en_US] Sancocho canario"
        )

    def test_an_empty_source_is_not_sent_anywhere(self):
        product = self.Product.create({"name": "Sin descripción"})
        job = self._jobs_for(product).filtered(
            lambda j: j.field_name == "description_sale"
        )
        with patch.object(type(self.engine), "translate") as translate:
            job._run()
        translate.assert_not_called()
        self.assertEqual(job.state, "done")

    # ------------------------------------------------------------------
    # The promise that matters most
    # ------------------------------------------------------------------
    def test_a_hand_written_translation_is_never_overwritten(self):
        """The whole reason the queue keeps a hash of what it wrote.

        A merchant who bothered to translate their own product must not have it
        replaced by machine output the next time they fix a typo in Spanish.
        """
        product = self.Product.create({"name": "Quesillo"})
        product.with_context(lang=TARGET).write({"name": "Caramel flan"})

        product.write({"name": "Quesillo casero"})
        self._run_queue()

        self.assertEqual(product.with_context(lang=TARGET).name, "Caramel flan")
        job = self._jobs_for(product).filtered(lambda j: j.field_name == "name")
        self.assertEqual(job.state, "locked")

    def test_english_being_translated_first_does_not_poison_the_others(self):
        """The regression that only shows up with more than two languages.

        ``en_US`` is the technical base of Odoo's translatable jsonb, so once
        English is written every language that has no entry of its own starts
        reading English instead of the Spanish source. Judging "has a human
        translated this?" from the value Odoo hands back therefore locks German
        and Italian the moment English lands, and they end up frozen showing
        English forever. Found on real data on 2026-08-14.
        """
        self.env["res.lang"]._activate_lang("de_DE")
        product = self.Product.create({"name": "Mojo palmero"})
        jobs = self._jobs_for(product, lang=False)

        english = jobs.filtered(
            lambda job: job.lang == "en_US" and job.field_name == "name"
        )
        german = jobs.filtered(
            lambda job: job.lang == "de_DE" and job.field_name == "name"
        )
        self.assertTrue(english and german)

        with patch.object(type(self.engine), "translate", fake_translate):
            english._run()
            german._run()

        self.assertEqual(german.state, "done", "German must not be locked by English")
        self.assertEqual(
            product.with_context(lang="de_DE").name,
            "[de_DE] Mojo palmero",
            "German must be German, not the English fallback",
        )

    def test_english_is_translated_after_every_other_language(self):
        """While the queue drains, the fallback should stay Spanish.

        If English went first, a German visitor would see English for the
        seconds in between -- and forever, if the German job later failed.
        """
        self.env["res.lang"]._activate_lang("de_DE")
        self.Job.search([]).unlink()
        self.Product.create({"name": "Bienmesabe"})
        asked = []

        def record_order(engine, texts, source_lang, target_lang, is_html=False):
            asked.append(target_lang)
            return fake_translate(engine, texts, source_lang, target_lang, is_html)

        with patch.object(type(self.engine), "translate", record_order):
            self.Job._cron_run_pending()

        self.assertIn("en_US", asked)
        self.assertIn("de_DE", asked)
        self.assertEqual(asked[-1], "en_US", "English must be written last")

    def test_editing_our_output_by_hand_locks_it_too(self):
        """Correcting the machine counts as writing it by hand."""
        product = self.Product.create({"name": "Almogrote"})
        self._run_queue()
        product.with_context(lang=TARGET).write({"name": "Cheese spread"})

        product.write({"name": "Almogrote gomero"})
        self._run_queue()

        self.assertEqual(product.with_context(lang=TARGET).name, "Cheese spread")

    def test_a_locked_translation_can_be_handed_back_deliberately(self):
        product = self.Product.create({"name": "Frangollo"})
        product.with_context(lang=TARGET).write({"name": "Mine"})
        product.write({"name": "Frangollo dulce"})
        self._run_queue()
        job = self._jobs_for(product).filtered(lambda j: j.field_name == "name")
        self.assertEqual(job.state, "locked")

        job.action_unlock()
        self._run_queue()

        self.assertEqual(
            product.with_context(lang=TARGET).name, "[en_US] Frangollo dulce"
        )

    # ------------------------------------------------------------------
    # Surviving the database
    # ------------------------------------------------------------------
    def test_a_lost_transaction_stops_the_batch_instead_of_flailing(self):
        """A serialization failure kills the whole transaction, not one record.

        Rolling back to the savepoint does not revive it, so everything
        afterwards fails too -- including writing the error onto the job. The
        first production run swallowed that and lost 230 seconds of finished
        translation. It has to stop and let the next run retry instead.
        """
        self.Product.create({"name": "Sancocho"})
        jobs = self.Job.search([("state", "=", "pending")])
        self.assertTrue(jobs)

        boom = psycopg2.extensions.TransactionRollbackError(
            "could not serialize access due to concurrent update"
        )
        with patch.object(type(self.engine), "translate", side_effect=boom):
            with self.assertRaises(psycopg2.extensions.TransactionRollbackError):
                jobs._run()

    def test_an_ordinary_failure_is_recorded_and_the_batch_carries_on(self):
        """One unreachable provider must not stop the other records."""
        product = self.Product.create({"name": "Escaldón"})
        # Only the filled-in fields ever reach an engine; an empty one is
        # marked done without a round-trip, so it cannot carry a failure.
        jobs = self._jobs_for(product, lang=False).filtered(
            lambda job: job.field_name == "name"
        )

        with patch.object(
            type(self.engine), "translate", side_effect=ValueError("connection refused")
        ):
            jobs._run()

        self.assertTrue(all(job.state == "pending" for job in jobs))
        self.assertTrue(all(job.attempts == 1 for job in jobs))
        self.assertTrue(all("connection refused" in (job.error or "") for job in jobs))

    def test_a_job_gives_up_after_three_attempts(self):
        product = self.Product.create({"name": "Gofio"})
        job = self._jobs_for(product).filtered(
            lambda candidate: candidate.field_name == "name"
        )

        with patch.object(
            type(self.engine), "translate", side_effect=ValueError("still down")
        ):
            for _attempt in range(3):
                job._run()

        self.assertEqual(job.state, "failed")

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    def test_a_page_keeps_its_qweb_directives(self):
        """Handing raw markup to a translator is how ``t-if`` gets translated.

        Terms go through Odoo's own ``xml_translate`` extraction, so only text
        nodes travel and every attribute stays exactly as the builder wrote it.
        """
        view = (
            self.env["ir.ui.view"]
            .with_context(lang=SOURCE)
            .create(
                {
                    "name": "Auto Translate Test Page",
                    "type": "qweb",
                    "key": "website_auto_translate.flow_test_page",
                    "website_id": 1,
                    "arch": '<div><t t-if="is_open">Estamos abiertos</t>'
                    "<p>Buenos días</p></div>",
                }
            )
        )
        self._run_queue()

        translated = view.with_context(lang=TARGET).arch_db
        self.assertIn('t-if="is_open"', translated)
        self.assertIn("[en_US] Estamos abiertos", translated)
        self.assertIn("[en_US] Buenos días", translated)

    def test_translating_a_page_leaves_the_spanish_original_alone(self):
        """The corruption that only appears once a page has several languages.

        Measured on 2026-08-14: writing a translated ``arch_db`` under a
        language context does not store a translation at all. Odoo reads it as
        the view definition changing and copies the value into *every*
        language, so one German write left ``de_DE``, ``en_US`` and ``es_ES``
        all holding the German and the Spanish source was gone. Each language
        must end up with its own text and the source must come back untouched.
        """
        for code in ("de_DE", "it_IT"):
            self.env["res.lang"]._activate_lang(code)
        view = (
            self.env["ir.ui.view"]
            .with_context(lang=SOURCE)
            .create(
                {
                    "name": "Auto Translate Multi Lang Page",
                    "type": "qweb",
                    "key": "website_auto_translate.multi_lang_page",
                    "website_id": 1,
                    "arch": "<div><p>Buenos días</p></div>",
                }
            )
        )
        self._run_queue()

        spanish = view.with_context(lang=SOURCE).arch_db
        self.assertIn("Buenos días", spanish)
        self.assertNotIn("[", spanish, "the Spanish source must stay pristine")
        for lang in ("en_US", "de_DE", "it_IT"):
            self.assertIn(
                "[%s] Buenos días" % lang,
                view.with_context(lang=lang).arch_db,
                "%s must hold its own translation" % lang,
            )

    def test_a_core_view_is_never_touched(self):
        """Views without a website belong to the ``.po`` files, not to us."""
        core_view = self.env["ir.ui.view"].search(
            [("website_id", "=", False), ("type", "=", "qweb")], limit=1
        )
        self.assertTrue(core_view, "expected at least one core qweb view")
        self.assertFalse(
            self.Job.search(
                [("model_name", "=", "ir.ui.view"), ("res_id", "=", core_view.id)]
            )
        )

    def test_page_edits_are_noticed_even_though_odoo_writes_arch(self):
        """``arch`` is an inverse onto ``arch_db``; watching the stored field alone would miss every page edit."""
        view = (
            self.env["ir.ui.view"]
            .with_context(lang=SOURCE)
            .create(
                {
                    "name": "Auto Translate Arch Test",
                    "type": "qweb",
                    "key": "website_auto_translate.arch_test_page",
                    "website_id": 1,
                    "arch": "<div>Hola</div>",
                }
            )
        )
        self._run_queue()
        self._jobs_for(view).write({"state": "done"})

        view.with_context(lang=SOURCE).write({"arch": "<div>Adiós</div>"})

        self.assertEqual(self._jobs_for(view).state, "pending")

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import SQL

from odoo.addons.partner_microsite_manager.models.res_company import _CLEAR_CACHE_KEY

SOURCE = "es_ES"
TARGET = "fr_FR"

TEXT_FIELDS = (
    "microsite_button_text",
    "microsite_intro_title",
    "microsite_banner_title",
    "microsite_about_title",
    "microsite_about_text",
    "microsite_services_title",
    "microsite_services_text",
    "microsite_parking_info",
    "microsite_delivery_info",
)


def fake_translate(engine, texts, source_lang, target_lang, is_html=False):
    """A deterministic stand-in so the tests never touch LibreTranslate."""
    return ["[%s] %s" % (target_lang, text) for text in texts]


@tagged("post_install", "-at_install")
class TestCompanyTextTranslation(TransactionCase):
    """The texts a merchant writes in "Contenido de la página" are translated.

    Asked for on 2026-11-16: "cuando se genera o cambia un texto, su traduccion
    se genera automaticamente". Until then the nine company texts were plain
    fields, so every language showed the Spanish.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "auto.translate.job" not in cls.env:
            cls.skipTest(cls, "website_auto_translate is not installed")
        cls.env["res.lang"]._activate_lang(SOURCE)
        cls.env["res.lang"]._activate_lang(TARGET)
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("website_auto_translate.enabled", "True")
        params.set_param("website_auto_translate.source_lang", SOURCE)
        params.set_param("website_auto_translate.mode", "single")
        cls.engine = cls.env["auto.translate.engine"].create(
            {"name": "Company Text Test Engine", "engine_type": "libretranslate"}
        )
        params.set_param("website_auto_translate.engine_id", str(cls.engine.id))
        cls.Job = cls.env["auto.translate.job"]
        cls.Company = cls.env["res.company"].with_context(lang=SOURCE)
        cls.shop = cls.Company.create(
            {"name": "Textos Traducibles", "auto_translate_enabled": True}
        )
        cls.shop.write(
            {
                "microsite_about_text": "Panaderia familiar desde 1952.",
                "microsite_parking_info": "Aparcamiento a 50 m",
            }
        )

    def _jobs(self, company=None, lang=None):
        domain = [
            ("model_name", "=", "res.company"),
            ("res_id", "=", (company or self.shop).id),
        ]
        if lang:
            domain.append(("lang", "=", lang))
        return self.Job.search(domain)

    def _run_queue(self):
        with patch.object(type(self.engine), "translate", fake_translate):
            return self._jobs().filtered(lambda j: j.state == "pending")._run()

    def _raw(self, company, field_name):
        company.flush_recordset([field_name])
        self.env.cr.execute(
            SQL(
                "SELECT %s FROM res_company WHERE id = %s",
                SQL.identifier(field_name),
                company.id,
            )
        )
        return self.env.cr.fetchone()[0] or {}

    def test_every_merchant_text_is_translatable(self):
        for name in TEXT_FIELDS:
            self.assertTrue(self.env["res.company"]._fields[name].translate, name)

    def test_opening_hours_stay_untranslated(self):
        """Computed from rows and format-checked: not free text."""
        self.assertFalse(
            self.env["res.company"]._fields["microsite_opening_hours"].translate
        )

    def test_writing_a_text_queues_each_target_language(self):
        self._jobs().unlink()
        self.shop.write({"microsite_about_text": "Panaderia familiar, desde 1952."})
        jobs = self._jobs()
        self.assertEqual(set(jobs.mapped("field_name")), {"microsite_about_text"})
        langs = set(jobs.mapped("lang"))
        self.assertIn(TARGET, langs)
        self.assertNotIn(SOURCE, langs, "the source language is not a target")
        self.assertEqual(len(jobs), len(langs), "one job per language")

    def test_rewriting_the_same_value_queues_nothing(self):
        """The editor writes the whole form back on every save."""
        self._jobs().unlink()
        self.shop.write(
            {
                "microsite_about_text": "Panaderia familiar desde 1952.",
                "microsite_parking_info": "Aparcamiento a 50 m",
            }
        )
        self.assertFalse(self._jobs())

    def test_only_the_changed_field_is_queued(self):
        self._jobs().unlink()
        self.shop.write(
            {
                "microsite_about_text": "Panaderia familiar desde 1952.",
                "microsite_parking_info": "Aparcamiento a 80 m",
            }
        )
        self.assertEqual(
            set(self._jobs().mapped("field_name")), {"microsite_parking_info"}
        )

    def test_a_skipped_context_queues_nothing(self):
        self._jobs().unlink()
        self.shop.with_context(auto_translate_skip=True).write(
            {"microsite_about_title": "Nuestra historia"}
        )
        self.assertFalse(self._jobs())

    def test_editing_in_another_language_queues_nothing(self):
        """Somebody typing the French page is not editing the Spanish source."""
        self._jobs().unlink()
        self.shop.with_context(lang=TARGET).write(
            {"microsite_about_title": "Notre histoire"}
        )
        self.assertFalse(self._jobs())

    def test_a_shop_that_opted_out_is_left_alone(self):
        outsider = self.Company.create(
            {"name": "Fuera de la prueba", "auto_translate_enabled": False}
        )
        outsider.write({"microsite_about_text": "No traducir"})
        self.assertFalse(self._jobs(outsider))

    def test_the_queue_fills_french_and_keeps_spanish(self):
        self._run_queue()
        french = self.shop.with_context(lang=TARGET)
        spanish = self.shop.with_context(lang=SOURCE)
        self.assertEqual(
            french.microsite_about_text, "[fr_FR] Panaderia familiar desde 1952."
        )
        self.assertEqual(french.microsite_parking_info, "[fr_FR] Aparcamiento a 50 m")
        self.assertEqual(spanish.microsite_about_text, "Panaderia familiar desde 1952.")
        self.assertEqual(spanish.microsite_parking_info, "Aparcamiento a 50 m")

    def test_the_spanish_keeps_its_own_key_after_a_run(self):
        """``en_US`` is the jsonb base; English must never replace the Spanish."""
        self._run_queue()
        stored = self._raw(self.shop, "microsite_about_text")
        self.assertEqual(stored.get(SOURCE), "Panaderia familiar desde 1952.")

    def test_a_hand_written_translation_is_never_overwritten(self):
        self.shop.with_context(lang=TARGET).write(
            {"microsite_about_text": "Boulangerie"}
        )
        self.shop.write({"microsite_about_text": "Panaderia familiar y artesana."})
        self._run_queue()
        self.assertEqual(
            self.shop.with_context(lang=TARGET).microsite_about_text, "Boulangerie"
        )
        job = self._jobs(lang=TARGET).filtered(
            lambda j: j.field_name == "microsite_about_text"
        )
        self.assertEqual(job.state, "locked")

    def test_a_finished_job_empties_the_homepage_cache(self):
        self.env.cr.postcommit.data.pop(_CLEAR_CACHE_KEY, None)
        self._run_queue()
        self.assertTrue(self.env.cr.postcommit.data.get(_CLEAR_CACHE_KEY))

    def _merchant_editor(self):
        self.shop.website_id = self.env["website"].create(
            {"name": "Textos Traducibles", "company_id": self.shop.id}
        )
        merchant = new_test_user(
            self.env,
            login="company_text_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=self.shop.id,
            company_ids=[(6, 0, self.shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )
        return self.env["microsite.content.editor"].with_user(merchant)

    def test_the_editor_opens_on_the_spanish_whatever_the_ui_language(self):
        """A merchant working in French must see the original, not the machine."""
        self._run_queue()
        self.assertEqual(
            self.shop.with_context(lang=TARGET).microsite_about_text,
            "[fr_FR] Panaderia familiar desde 1952.",
        )
        editor = self._merchant_editor().with_context(lang=TARGET)
        values = editor.default_get(["microsite_about_text"])
        self.assertEqual(
            values["microsite_about_text"], "Panaderia familiar desde 1952."
        )

    def test_the_editor_saves_the_spanish_whatever_the_ui_language(self):
        """...and what they save is the source: it is queued, French untouched."""
        self._run_queue()
        editor = self._merchant_editor().with_context(lang=TARGET)
        wizard = editor.create({"microsite_about_text": "Panaderia artesana."})
        wizard.action_save()
        self.assertEqual(
            self.shop.with_context(lang=SOURCE).microsite_about_text,
            "Panaderia artesana.",
        )
        self.assertEqual(
            self.shop.with_context(lang=TARGET).microsite_about_text,
            "[fr_FR] Panaderia familiar desde 1952.",
            "the French stays until the queue replaces it",
        )
        job = self._jobs(lang=TARGET).filtered(
            lambda j: j.field_name == "microsite_about_text"
        )
        self.assertEqual(job.state, "pending")
        self._run_queue()
        self.assertEqual(
            self.shop.with_context(lang=TARGET).microsite_about_text,
            "[fr_FR] Panaderia artesana.",
        )

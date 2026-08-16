# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.text_tools import mask, section_at, section_markers, term_has_words, unmask

SOURCE = "es_ES"
TARGET = "en_US"

PAGE = """<div>
  <section data-name="Cover">
    <h1>Zona Comercial Tamaraceite</h1>
    <p>Bienvenido a la zona.</p>
  </section>
  <section data-name="Text">
    <h2>Quiénes Somos</h2>
    <p>En <strong>ZCA Tamaraceite</strong>, somos un equipo.</p>
    <p>&amp;nbsp;</p>
    <a href="/shop"><font>&amp;nbsp;<i class="fa fa-play"/> Ver más&amp;nbsp;</font></a>
  </section>
</div>"""


def fake_translate(engine, texts, source_lang, target_lang, is_html=False):
    return ["[%s] %s" % (target_lang, text) for text in texts]


@tagged("post_install", "-at_install")
class TestTextTools(TransactionCase):
    """The markup a person should never have to look at, and never lose."""

    def test_a_sentence_with_no_letters_is_never_sent_to_an_engine(self):
        self.assertFalse(term_has_words("&amp;nbsp;"))
        self.assertFalse(term_has_words('<i class="fa fa-play"/>'))
        self.assertFalse(term_has_words("&amp;nbsp;&amp;nbsp;"))
        self.assertTrue(term_has_words("Ver más"))
        self.assertTrue(term_has_words('<i class="fa fa-play"/> Ver más'))

    def test_a_number_on_its_own_is_not_something_to_translate(self):
        self.assertFalse(term_has_words("1.250"))
        self.assertFalse(term_has_words("— 2026 —"))

    def test_the_markup_of_a_sentence_survives_being_hidden_and_restored(self):
        term = 'En <strong>ZCA</strong>, somos un <i class="fa fa-star"/> equipo.'
        shown = mask(term)
        self.assertNotIn("<", shown, "a person must not be shown a tag")
        self.assertEqual(unmask(shown, term), term)

    def test_a_person_can_retype_around_the_markers_and_keep_the_markup(self):
        term = "En <strong>ZCA</strong>, somos un equipo."
        corrected = mask(term).replace("somos un equipo", "we are a team")
        self.assertEqual(
            unmask(corrected, term), "En <strong>ZCA</strong>, we are a team."
        )

    def test_deleting_a_marker_costs_the_tag_and_nothing_else(self):
        term = "Hola <strong>mundo</strong>"
        self.assertEqual(unmask("Hola mundo", term), "Hola mundo")

    def test_a_hard_space_keeps_the_spelling_the_page_uses(self):
        term = "&amp;nbsp;Ver más&amp;nbsp;"
        self.assertEqual(unmask(mask(term), term), term)

    def test_a_sentence_is_filed_under_the_heading_above_it(self):
        markers = section_markers(PAGE)
        self.assertIn("Quiénes Somos", [label for _, label in markers])
        offset = PAGE.find("somos un equipo")
        self.assertEqual(section_at(markers, offset), "Quiénes Somos")

    def test_a_snippet_names_the_part_of_the_page_when_there_is_no_heading(self):
        markers = section_markers('<section data-name="Cover"><p>Hola</p></section>')
        self.assertEqual(section_at(markers, 30), "Cover")


@tagged("post_install", "-at_install")
class TestAutoTranslateTerms(TransactionCase):
    """A page is read, corrected and protected one sentence at a time.

    Reported on 2026-08-16: "veo que en las traducciones te estás trayendo html
    completo, solo debes colocar los valores en los textos no en los div
    sections y data ni ninguna etiqueta html".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang(SOURCE)
        cls.env["res.lang"]._activate_lang(TARGET)
        cls.company = cls.env.ref("base.main_company")
        cls.company.auto_translate_enabled = True
        cls.engine = cls.env["auto.translate.engine"].create(
            {"name": "Term Test Engine", "engine_type": "libretranslate"}
        )
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("website_auto_translate.enabled", "True")
        params.set_param("website_auto_translate.source_lang", SOURCE)
        params.set_param("website_auto_translate.mode", "single")
        params.set_param("website_auto_translate.engine_id", str(cls.engine.id))
        cls.Job = cls.env["auto.translate.job"]
        cls.website = cls.env["website"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )

    def _page(self):
        view = (
            self.env["ir.ui.view"]
            .with_context(lang=SOURCE)
            .create(
                {
                    "name": "Página de prueba",
                    "type": "qweb",
                    "key": "website_auto_translate.test_page",
                    "website_id": self.website.id,
                    "arch": PAGE,
                }
            )
        )
        return view

    def _job(self, view, lang=TARGET):
        return self.Job.search(
            [
                ("model_name", "=", "ir.ui.view"),
                ("res_id", "=", view.id),
                ("lang", "=", lang),
            ],
            limit=1,
        )

    def _run(self):
        with patch.object(type(self.engine), "translate", fake_translate):
            return self.Job.search([("state", "=", "pending")])._run()

    # ------------------------------------------------------------------
    def test_a_page_is_listed_as_sentences_and_never_as_a_blob(self):
        job = self._job(self._page())
        self.assertTrue(job, "editing a page has to queue it")
        self._run()
        terms = job.term_ids
        self.assertTrue(terms, "the page has to be broken into sentences")
        for term in terms:
            self.assertNotIn(
                "<", term.source_text, "no markup may reach the correction screen"
            )
            self.assertNotIn("data-name", term.source_text)
        self.assertNotIn(
            "<", job.source_text, "the queue must not show the page markup either"
        )

    def test_the_sentences_come_out_in_reading_order_under_their_heading(self):
        job = self._job(self._page())
        self._run()
        ordered = job.term_ids.sorted("sequence")
        self.assertEqual(ordered[0].source_text, "Zona Comercial Tamaraceite")
        somos = ordered.filtered(lambda row: "somos un equipo" in row.source_text)
        self.assertEqual(somos.section, "Quiénes Somos")

    def test_a_sentence_with_nothing_to_translate_is_left_out(self):
        job = self._job(self._page())
        self._run()
        self.assertFalse(
            job.term_ids.filtered(lambda row: not row.source_text.strip()),
            "an empty sentence is not worth a row, or a request",
        )

    def test_correcting_one_sentence_leaves_the_rest_to_the_machine(self):
        view = self._page()
        job = self._job(view)
        self._run()
        target = job.term_ids.filtered(
            lambda row: "somos un equipo" in row.source_text
        )
        self.assertEqual(len(target), 1)
        target.translated_text = mask(
            "En <strong>ZCA Tamaraceite</strong>, we are a team."
        )
        self.assertEqual(target.state, "locked")
        self.assertNotEqual(
            job.state, "locked", "one corrected line must not freeze the page"
        )
        self.assertIn(
            "we are a team",
            view.with_context(lang=TARGET).arch_db,
            "the correction has to reach the page itself",
        )

    def test_a_correction_survives_the_page_being_translated_again(self):
        view = self._page()
        job = self._job(view)
        self._run()
        target = job.term_ids.filtered(
            lambda row: "somos un equipo" in row.source_text
        )
        target.translated_text = mask(
            "En <strong>ZCA Tamaraceite</strong>, we are a team."
        )
        job.action_translate_again()
        self._run()
        arch = view.with_context(lang=TARGET).arch_db
        self.assertIn("we are a team", arch, "the correction was overwritten")
        self.assertIn(
            "[%s] Bienvenido a la zona." % TARGET,
            arch,
            "the sentences nobody touched still have to improve",
        )

    def test_a_sentence_retyped_on_the_website_is_adopted_as_hand_written(self):
        view = self._page()
        job = self._job(view)
        self._run()
        row = job.term_ids.filtered(lambda r: "Bienvenido a la zona" in r.source_text)
        view.with_context(auto_translate_skip=True).update_field_translations(
            "arch_db",
            {TARGET: {"Bienvenido a la zona.": "Welcome, written by a person."}},
            source_lang=SOURCE,
        )
        job._sync_terms()
        self.assertEqual(
            row.state, "locked", "a sentence somebody retyped is theirs now"
        )

    def test_giving_a_sentence_back_to_the_machine_re_translates_it(self):
        view = self._page()
        job = self._job(view)
        self._run()
        row = job.term_ids.filtered(lambda r: "Bienvenido a la zona" in r.source_text)
        row.translated_text = "Welcome, written by a person."
        self.assertEqual(row.state, "locked")
        row.action_unlock()
        self.assertEqual(row.state, "auto")
        self._run()
        self.assertIn(
            "[%s] Bienvenido a la zona." % TARGET,
            view.with_context(lang=TARGET).arch_db,
        )

    def test_the_engine_is_never_asked_for_a_sentence_somebody_fixed(self):
        view = self._page()
        job = self._job(view)
        self._run()
        row = job.term_ids.filtered(lambda r: "Bienvenido a la zona" in r.source_text)
        row.translated_text = "Welcome, written by a person."
        job.action_translate_again()
        seen = []

        def spy(engine, texts, source_lang, target_lang, is_html=False):
            seen.extend(texts)
            return fake_translate(engine, texts, source_lang, target_lang, is_html)

        with patch.object(type(self.engine), "translate", spy):
            self.Job.search([("state", "=", "pending")])._run()
        self.assertNotIn("Bienvenido a la zona.", seen)
        self.assertNotIn("&amp;nbsp;", seen, "an entity is not a translatable text")

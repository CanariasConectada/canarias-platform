# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

SOURCE = "es_ES"


@tagged("post_install", "-at_install")
class TestAutoTranslateGlossary(TransactionCase):
    """A brand is not a word, and the machine must never get the chance.

    Asked for on 2026-08-15 after the first run turned "Cheetos" into "Käse"
    and "Estrella Galicia mini" into "Ministern Galicia".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang(SOURCE)
        cls.env["res.lang"]._activate_lang("de_DE")
        cls.Glossary = cls.env["auto.translate.glossary"]
        cls.Glossary.search([]).unlink()
        cls.Glossary.create(
            [
                {"name": "Cheetos"},
                {"name": "Estrella Galicia"},
                {"name": "Galicia"},
                {"name": "Silver Economy", "replacement": "Silberwirtschaft",
                 "lang": "de_DE"},
            ]
        )

    # ------------------------------------------------------------------
    # Fencing
    # ------------------------------------------------------------------
    def test_a_brand_is_fenced_off_before_it_reaches_the_engine(self):
        guarded = self.Glossary._protect("Bolsa de Cheetos grande", is_html=False)
        self.assertIn('<span translate="no">Cheetos</span>', guarded)
        self.assertIn("Bolsa de ", guarded)
        self.assertIn(" grande", guarded)

    def test_the_longest_term_wins(self):
        """With both terms listed, half a brand must not escape the fence.

        "Galicia" alone would leave "Estrella" outside, and the engine turns
        that into "Ministern" -- a wrong product that still reads deliberate.
        """
        guarded = self.Glossary._protect("Estrella Galicia mini", is_html=False)
        self.assertIn('<span translate="no">Estrella Galicia</span>', guarded)
        self.assertNotIn("Estrella <span", guarded)

    def test_matching_ignores_case_but_not_word_boundaries(self):
        guarded = self.Glossary._protect("CHEETOS y Cheetoslandia", is_html=False)
        self.assertIn('<span translate="no">CHEETOS</span>', guarded)
        self.assertNotIn("Cheetos</span>landia", guarded)

    def test_an_html_entity_is_fenced_off_too(self):
        """Both formats damage entities, so neither may see one.

        Measured against our own LibreTranslate on 2026-08-15: as text,
        "&nbsp;" came back as the literal "& nbsp;" -- the corruption found in
        eight footers. As HTML it was swallowed together with the words around
        it.
        """
        guarded = self.Glossary._protect("<p>Uno&nbsp;dos</p>", is_html=True)
        self.assertIn('<span translate="no">&nbsp;</span>', guarded)

    def test_a_term_inside_markup_is_left_alone(self):
        """Protecting the "Cheetos" of ``alt="Cheetos"`` would rewrite the tag."""
        guarded = self.Glossary._protect('<img alt="Cheetos"/>Cheetos', is_html=True)
        self.assertIn('<img alt="Cheetos"/>', guarded)
        self.assertEqual(guarded.count("<span"), 1)

    # ------------------------------------------------------------------
    # Coming back
    # ------------------------------------------------------------------
    def test_the_brand_comes_back_exactly_as_it_went_in(self):
        restored = self.Glossary._restore(
            'Große Tüte <span translate="no">Cheetos</span>', "de_DE", is_html=False
        )
        self.assertEqual(restored, "Große Tüte Cheetos")

    def test_a_fixed_wording_is_applied_for_its_own_language_only(self):
        guarded = 'Die <span translate="no">Silver Economy</span> hier'
        self.assertEqual(
            self.Glossary._restore(guarded, "de_DE", is_html=False),
            "Die Silberwirtschaft hier",
        )
        self.assertEqual(
            self.Glossary._restore(guarded, "it_IT", is_html=False),
            "Die Silver Economy hier",
        )

    def test_a_guarded_term_comes_back_in_the_case_it_went_out_in(self):
        """Measured on 2026-08-15: the Italian model returned ``&Nbsp;``.

        An HTML entity is case-sensitive. ``&nbsp;`` is a non-breaking space
        and ``&Nbsp;`` is not an entity at all -- it is five characters the
        visitor reads on the page. Blindly lower-casing what comes back is not
        the answer either, because ``&Aacute;`` and ``&aacute;`` are different
        letters. The only safe source of truth is what we sent.
        """
        held = {}
        guarded = self.Glossary._protect("Uno&nbsp;dos CHEETOS", is_html=True, held=held)
        self.assertIn('<span translate="no">&nbsp;</span>', guarded)

        # The engine hands both guards back with the case changed.
        mangled = guarded.replace("&nbsp;", "&Nbsp;").replace("CHEETOS", "Cheetos")
        restored = self.Glossary._restore(mangled, "it_IT", is_html=True, held=held)

        self.assertIn("&nbsp;", restored)
        self.assertNotIn("&Nbsp;", restored)
        self.assertIn("CHEETOS", restored, "a brand keeps the case it was written in")

    def test_a_reformatted_guard_is_still_recognised(self):
        """The engine may rewrite the attribute, and a guard we cannot find
        again is a guard that deletes the brand."""
        for variant in (
            "<span translate='no'>Cheetos</span>",
            '<span  translate = "no" >Cheetos</span>',
            '<span class="x" translate="no">Cheetos</span>',
        ):
            self.assertEqual(
                self.Glossary._restore(variant, "de_DE", is_html=False),
                "Cheetos",
                variant,
            )

    def test_plain_text_survives_the_html_round_trip(self):
        """A plain field goes out as HTML because that is the only format the
        guard survives, so it has to come back plain."""
        guarded = self.Glossary._protect("Tortas & Dulces Cheetos", is_html=False)
        self.assertIn("&amp;", guarded)
        self.assertEqual(
            self.Glossary._restore(guarded, "de_DE", is_html=False),
            "Tortas & Dulces Cheetos",
        )

    # ------------------------------------------------------------------
    # Repairing what was already translated
    # ------------------------------------------------------------------
    def test_adding_a_term_queues_the_content_that_mentions_it(self):
        """A brand added today has to repair the 1424 products of yesterday.

        Guarding only future translations is no use when the reason for adding
        the term is content that is already wrong.
        """
        company = self.env.ref("base.main_company")
        company.auto_translate_enabled = True
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("website_auto_translate.enabled", "True")
        params.set_param("website_auto_translate.source_lang", SOURCE)
        Product = self.env["product.template"].with_context(lang=SOURCE)

        mentions = Product.create({"name": "Bolsa de Cheetos"})
        unrelated = Product.create({"name": "Gofio escaldado"})
        Job = self.env["auto.translate.job"]
        Job.search(
            [("model_name", "=", "product.template"), ("field_name", "!=", "name")]
        ).unlink()
        Job.search([]).write({"state": "done", "source_hash": "stale"})

        self.Glossary.search([("name", "=", "Cheetos")]).action_retranslate_affected()

        def states(product):
            return set(
                Job.search(
                    [
                        ("model_name", "=", "product.template"),
                        ("res_id", "=", product.id),
                    ]
                ).mapped("state")
            )

        self.assertEqual(
            states(mentions),
            {"pending"},
            "the product that mentions the brand goes back in the queue",
        )
        self.assertEqual(
            states(unrelated),
            {"done"},
            "content that never mentions the brand is left alone",
        )

    def test_a_hand_corrected_row_is_never_dragged_back_in(self):
        """Regenerating a language must not undo somebody's correction."""
        Job = self.env["auto.translate.job"]
        job = Job.create(
            {
                "model_name": "product.template",
                # An id nothing owns: this test is about the state machine, and
                # a real product would collide with the queue the database
                # copy already carries.
                "res_id": 999999999,
                "field_name": "name",
                "lang": "de_DE",
                "state": "locked",
            }
        )
        self.assertEqual(job.action_translate_again(), 0)
        self.assertEqual(job.state, "locked")

    # ------------------------------------------------------------------
    # Through the engine
    # ------------------------------------------------------------------
    def test_the_engine_never_receives_the_brand(self):
        """The whole point: not "the brand is repaired afterwards" but "the
        engine was never given the chance to touch it"."""
        engine = self.env["auto.translate.engine"].create(
            {"name": "Glossary Test Engine", "engine_type": "libretranslate"}
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "website_auto_translate.engine_id", str(engine.id)
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "website_auto_translate.mode", "single"
        )
        seen = []

        def spy(this, texts, source_lang, target_lang, is_html=False):
            seen.append((list(texts), is_html))
            return list(texts)

        with patch.object(type(engine), "translate", spy):
            self.env["auto.translate.engine"]._run(
                ["Bolsa de Cheetos"], SOURCE, "de_DE", is_html=False
            )

        sent, as_html = seen[0]
        self.assertTrue(as_html, "the request must go out as HTML or the guard is lost")
        self.assertNotIn(
            "Bolsa de Cheetos",
            sent,
            "the raw brand must never be handed to the engine",
        )
        self.assertIn('<span translate="no">Cheetos</span>', sent[0])

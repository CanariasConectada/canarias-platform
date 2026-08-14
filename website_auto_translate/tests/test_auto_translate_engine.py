# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

PATH = "odoo.addons.website_auto_translate.models.auto_translate_engine"


@tagged("post_install", "-at_install")
class TestAutoTranslateEngine(TransactionCase):
    """What each provider is asked for, and what comes back.

    Nothing here touches the network: every test patches the single HTTP call
    so the assertions are about our request shaping and response parsing, which
    is where the bugs actually live.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Engine = cls.env["auto.translate.engine"]
        cls.libre = Engine.create(
            {
                "name": "Test LibreTranslate",
                "engine_type": "libretranslate",
                "endpoint_url": "http://libretranslate:5000",
            }
        )
        cls.google = Engine.create(
            {"name": "Test Google", "engine_type": "google", "api_key": "k"}
        )
        cls.deepl = Engine.create(
            {"name": "Test DeepL", "engine_type": "deepl", "api_key": "k"}
        )
        cls.claude = Engine.create(
            {"name": "Test Claude", "engine_type": "anthropic", "api_key": "k"}
        )

    # ------------------------------------------------------------------
    # Language codes
    # ------------------------------------------------------------------
    def test_locales_become_plain_language_codes(self):
        self.assertEqual(self.libre._engine_lang("es_ES"), "es")
        self.assertEqual(self.google._engine_lang("de_DE"), "de")

    def test_deepl_demands_a_region_when_translating_into_english(self):
        """The one provider quirk that silently 400s if you get it wrong."""
        self.assertEqual(self.deepl._engine_lang("en_US"), "EN")
        self.assertEqual(self.deepl._engine_lang("en_US", is_target=True), "EN-GB")

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------
    def test_libretranslate_sends_the_batch_and_reads_the_batch_back(self):
        with patch.object(
            type(self.libre),
            "_post",
            return_value={"translatedText": ["Good morning", "Good night"]},
        ) as post:
            result = self.libre.translate(
                ["Buenos días", "Buenas noches"], "es_ES", "en_US"
            )
        self.assertEqual(result, ["Good morning", "Good night"])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["source"], "es")
        self.assertEqual(payload["target"], "en")
        self.assertEqual(payload["format"], "text")

    def test_libretranslate_tolerates_a_bare_string_for_one_item(self):
        """Some builds unwrap a single-item batch; that must not crash."""
        with patch.object(
            type(self.libre), "_post", return_value={"translatedText": "Good morning"}
        ):
            self.assertEqual(
                self.libre.translate(["Buenos días"], "es_ES", "en_US"),
                ["Good morning"],
            )

    def test_google_unwraps_its_nested_reply(self):
        with patch.object(
            type(self.google),
            "_post",
            return_value={"data": {"translations": [{"translatedText": "Hello"}]}},
        ):
            self.assertEqual(
                self.google.translate(["Hola"], "es_ES", "en_US"), ["Hello"]
            )

    def test_deepl_asks_for_html_handling_only_for_html(self):
        with patch.object(
            type(self.deepl), "_post", return_value={"translations": [{"text": "Hi"}]}
        ) as post:
            self.deepl.translate(["<p>Hola</p>"], "es_ES", "en_US", is_html=True)
        self.assertEqual(post.call_args.kwargs["json"]["tag_handling"], "html")

    def test_claude_survives_a_fenced_json_answer(self):
        """Models wrap the array in ``` even when told not to."""
        with patch.object(
            type(self.claude),
            "_post",
            return_value={"content": [{"text": '```json\n["Hello"]\n```'}]},
        ):
            self.assertEqual(
                self.claude.translate(["Hola"], "es_ES", "en_US"), ["Hello"]
            )

    # ------------------------------------------------------------------
    # The contract that keeps translations on the right terms
    # ------------------------------------------------------------------
    def test_a_short_answer_is_refused_instead_of_misaligned(self):
        """Zipping a short reply onto the terms would shift every translation.

        This is the failure that would quietly rewrite a product's description
        with its neighbour's text, so it has to be loud.
        """
        with patch.object(
            type(self.libre), "_post", return_value={"translatedText": ["only one"]}
        ):
            with self.assertRaises(UserError):
                self.libre.translate(["uno", "dos"], "es_ES", "en_US")

    def test_an_empty_batch_never_calls_the_service(self):
        with patch.object(type(self.libre), "_post") as post:
            self.assertEqual(self.libre.translate([], "es_ES", "en_US"), [])
        post.assert_not_called()

    # ------------------------------------------------------------------
    # Jury
    # ------------------------------------------------------------------
    def test_only_an_llm_may_arbitrate(self):
        with self.assertRaises(UserError):
            self.libre.is_arbiter = True

    def test_the_arbiter_choice_is_what_ships(self):
        self.libre.in_jury = True
        self.google.in_jury = True
        self.claude.in_jury = False
        self.claude.is_arbiter = True
        self.env["ir.config_parameter"].sudo().set_param(
            "website_auto_translate.mode", "jury"
        )
        jury = self.libre | self.google

        def fake_translate(engine, texts, source, target, is_html=False):
            return ["%s output" % engine.name]

        with patch.object(type(self.libre), "translate", fake_translate), patch.object(
            type(self.claude), "_pick_winner", return_value=1
        ):
            translated, winner = self.env["auto.translate.engine"]._run_jury(
                jury, ["Hola"], "es_ES", "en_US", False
            )
        self.assertEqual(winner, self.google)
        self.assertEqual(translated, ["Test Google output"])

    def test_a_juror_that_is_down_does_not_sink_the_jury(self):
        """Running several engines is pointless if one outage stops all of them."""
        self.libre.in_jury = True
        self.google.in_jury = True
        jury = self.libre | self.google

        def flaky(engine, texts, source, target, is_html=False):
            if engine == self.libre:
                raise ValueError("connection refused")
            return ["survivor"]

        with patch.object(type(self.libre), "translate", flaky):
            translated, winner = self.env["auto.translate.engine"]._run_jury(
                jury, ["Hola"], "es_ES", "en_US", False
            )
        self.assertEqual(translated, ["survivor"])
        self.assertEqual(winner, self.google)
        self.assertTrue(self.libre.last_error)

    def test_a_silent_arbiter_falls_back_to_the_first_candidate(self):
        """A broken judge must degrade to a translation, not to an exception."""
        self.claude.is_arbiter = True
        with patch.object(
            type(self.claude), "_post", side_effect=ValueError("gateway timeout")
        ):
            index = self.claude._pick_winner(
                ["Hola"], [(self.libre, ["a"]), (self.google, ["b"])], "es_ES", "en_US"
            )
        self.assertEqual(index, 0)

    def test_an_out_of_range_verdict_is_ignored(self):
        self.claude.is_arbiter = True
        with patch.object(
            type(self.claude),
            "_post",
            return_value={"content": [{"text": '{"winner": 9, "why": "x"}'}]},
        ):
            index = self.claude._pick_winner(
                ["Hola"], [(self.libre, ["a"]), (self.google, ["b"])], "es_ES", "en_US"
            )
        self.assertEqual(index, 0)

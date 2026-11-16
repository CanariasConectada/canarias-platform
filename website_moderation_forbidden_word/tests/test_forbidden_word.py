# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from psycopg2.errors import UniqueViolation

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.website_moderation_forbidden_word.models.moderation_forbidden_word import (  # noqa: E501
    normalize_text,
)


@tagged("post_install", "-at_install")
class TestForbiddenWord(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Word = cls.env["moderation.forbidden.word"]
        # The tests reason on their own entries only: the seed is removed
        # (inside the test transaction, so it is rolled back) because its
        # 300+ words would otherwise both match and collide with the
        # entries created below (uniqueness ignores ``active``).
        cls.Word.with_context(active_test=False).search([]).unlink()

    def _add(self, name, **vals):
        return self.Word.create(dict(vals, name=name))

    # --- Normalization ----------------------------------------------------
    def test_normalize_folds_case_accents_and_whitespace(self):
        self.assertEqual(normalize_text("  IMBÉCIL   Total "), "imbecil total")
        self.assertEqual(normalize_text("Sinvergüenza"), "sinverguenza")
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")

    def test_normalize_keeps_the_enye(self):
        """The enye is a letter of its own: coño must never become cono."""
        self.assertEqual(normalize_text("Coño"), "coño")
        self.assertNotEqual(normalize_text("coño"), normalize_text("cono"))

    def test_normalized_form_is_stored(self):
        word = self._add("Hijo De   Puta")
        self.assertEqual(word.name_normalized, "hijo de puta")

    # --- Uniqueness -------------------------------------------------------
    @mute_logger("odoo.sql_db")
    def test_duplicate_by_normalized_form_is_rejected(self):
        self._add("imbécil")
        for variant in ("imbecil", "IMBÉCIL", "Imbécil", " imbécil "):
            with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
                self._add(variant)

    def test_empty_word_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._add("   ")

    def test_punctuation_only_word_is_rejected(self):
        """An entry needs at least one letter or digit once normalized."""
        for name in ("...", "!!!", "%", "¿?"):
            with self.assertRaises(ValidationError, msg=name):
                self._add(name)
        self._add("100% gratis")  # digits count, punctuation may surround them

    def test_import_reports_the_friendly_duplicate_message(self):
        """The import path (``load``) surfaces the constraint's message, not a
        raw psycopg2 error, when a file repeats a word in another spelling."""
        result = self.Word.load(["name"], [["imbécil"], ["IMBECIL"]])
        messages = " ".join(m["message"] for m in result["messages"])
        self.assertIn("already in the forbidden list", messages)
        self.assertFalse(result["ids"])

    # --- Matcher ----------------------------------------------------------
    def test_match_folds_case_and_accents_both_sides(self):
        self._add("imbécil")
        for text in ("IMBÉCIL", "imbecil", "Imbécil", "un ImbECil cualquiera"):
            self.assertTrue(self.Word._contains_forbidden(text), text)
            self.assertEqual(self.Word._find_matches(text), ["imbécil"])
        self._add("estupido")
        self.assertTrue(self.Word._contains_forbidden("Qué ESTÚPIDO"))

    def test_match_is_whole_word_only(self):
        self._add("imbécil")
        self.assertFalse(self.Word._contains_forbidden("imbecilidad"))
        self.assertFalse(self.Word._contains_forbidden("preimbecil"))
        self.assertTrue(self.Word._contains_forbidden("imbécil."))
        self.assertTrue(self.Word._contains_forbidden("(imbecil)"))
        self.assertTrue(self.Word._contains_forbidden("¡IMBÉCIL!"))
        self._add("cialis")
        self.assertFalse(self.Word._contains_forbidden("Un gran especialista"))

    def test_match_does_not_tolerate_repeated_letters(self):
        """Documented limitation: no fuzzy matching, by design."""
        self._add("imbécil")
        self.assertFalse(self.Word._contains_forbidden("imbeeecil"))
        self.assertFalse(self.Word._contains_forbidden("imb3cil"))

    def test_plural_forms_need_their_own_entry(self):
        """Documented limitation: no stemming. ``imbécil`` does not cover
        ``imbéciles``; inflected forms are listed one by one (the seed does
        so for the common ones)."""
        self._add("imbécil")
        self.assertFalse(self.Word._contains_forbidden("imbéciles"))
        self.assertFalse(self.Word._contains_forbidden("IMBECILES"))
        self._add("imbéciles")
        self.assertTrue(self.Word._contains_forbidden("unos IMBECILES"))

    def test_multi_word_entries(self):
        self._add("hijo de puta")
        self.assertTrue(self.Word._contains_forbidden("eres un HIJO  DE\nPUTA."))
        self.assertFalse(self.Word._contains_forbidden("hijo de un gran cocinero"))
        self.assertFalse(self.Word._contains_forbidden("puta"))
        self.assertEqual(
            self.Word._find_matches("Hijo de puta y hijo de puta otra vez"),
            ["hijo de puta"],
        )

    def test_entries_with_non_word_edges(self):
        self._add("100% gratis")
        self._add("www")
        self.assertTrue(self.Word._contains_forbidden("Todo 100% GRATIS aquí"))
        self.assertTrue(self.Word._contains_forbidden("mira www.ejemplo.com"))
        self.assertFalse(self.Word._contains_forbidden("wwww"))

    def test_find_matches_lists_every_hit_sorted(self):
        self._add("timo")
        self._add("estafa")
        self._add("hijo de puta")
        matches = self.Word._find_matches("Un TIMO, una estafa, hijo de puta")
        self.assertEqual(matches, ["estafa", "hijo de puta", "timo"])
        self.assertEqual(self.Word._find_matches("todo correcto"), [])
        self.assertEqual(self.Word._find_matches(""), [])
        self.assertEqual(self.Word._find_matches(False), [])

    def test_archived_words_are_ignored(self):
        word = self._add("meh")
        self.assertTrue(self.Word._contains_forbidden("it was meh"))
        word.active = False
        self.assertFalse(self.Word._contains_forbidden("it was meh"))

    def test_empty_list_matches_nothing(self):
        self.assertFalse(self.Word._contains_forbidden("hijo de puta"))
        self.assertEqual(self.Word._find_matches("hijo de puta"), [])
        # The empty pattern is a real, never-matching regex (never None), so
        # batch callers can always pass it down.
        pattern = self.Word._get_pattern()
        self.assertIsNotNone(pattern)
        self.assertFalse(self.Word._contains_forbidden("anything", pattern=pattern))

    def test_precompiled_pattern_can_be_passed_down(self):
        """Batch callers compute the pattern once and hand it to the matchers;
        the result must be the same as the on-demand path."""
        self._add("timo")
        self._add("hijo de puta")
        pattern = self.Word._get_pattern()
        texts = ("Un TIMO", "hijo de puta", "todo bien")
        expected = [self.Word._contains_forbidden(t) for t in texts]
        self.assertEqual(expected, [True, True, False])
        self.assertEqual(
            [self.Word._contains_forbidden(t, pattern=pattern) for t in texts],
            expected,
        )
        self.assertEqual(
            self.Word._find_matches("timo y hijo de puta", pattern=pattern),
            ["hijo de puta", "timo"],
        )


@tagged("post_install", "-at_install")
class TestForbiddenWordSeed(TransactionCase):
    def test_seed_is_installed_and_consistent(self):
        Word = self.env["moderation.forbidden.word"]
        seeded = Word.search([])
        self.assertGreaterEqual(len(seeded), 300)
        # Entries with frequent legitimate use ship archived, one toggle away.
        archived = Word.with_context(active_test=False).search([("active", "=", False)])
        self.assertEqual(
            set(archived.mapped("name_normalized")),
            {
                "basura",
                "paja",
                "timo",
                "racista",
                "tonto",
                "boludo",
                "boluda",
                "verga",
                "tetas",
            },
        )
        self.assertTrue(all(archived.mapped("note")))
        for still_active in ("cojones", "hostia", "ostia"):
            self.assertTrue(Word._contains_forbidden(still_active), still_active)
        self.assertFalse(Word._contains_forbidden("Qué timo de precios"))
        # Every legacy word of both merged lists made it in.
        for legacy in ("hijo de puta", "gilipollas", "estafa", "sudaca", "xxx"):
            self.assertTrue(Word._contains_forbidden(legacy), legacy)
        # Everyday homographs are not flagged.
        for clean in (
            "Un cono de helado enorme",
            "chochos con sal",
            "El antiguo casino del pueblo",
            "Murió a los 90 años",
            "Un gran especialista",
        ):
            self.assertFalse(Word._contains_forbidden(clean), clean)

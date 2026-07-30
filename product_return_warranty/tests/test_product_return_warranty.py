# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests.common import TransactionCase

TERMS_TEMPLATE = "website_sale.product_terms_and_conditions"

# The two claims Odoo hardcodes for every product of every website.
ODOO_HARDCODED = ("money-back guarantee", "Shipping: 2-3 Business Days")


class TestProductReturnWarranty(TransactionCase):
    """The sentences are translated at render time, so every assertion on text
    pins the language explicitly: this database may have any set of languages
    installed, and a test that reads whatever `env.lang` happens to be would
    pass or fail depending on the deployment."""

    def _product(self, lang="en_US", **vals):
        return (
            self.env["product.template"]
            .with_context(lang=lang)
            .create({"name": "Test product", **vals})
        )

    def _render_terms(self, product, lang="en_US"):
        return (
            self.env["ir.qweb"]
            .with_context(lang=lang)
            ._render(TERMS_TEMPLATE, {"product": product.with_context(lang=lang)})
        )

    def _lang_installed(self, code):
        return bool(
            self.env["res.lang"]
            .with_context(active_test=False)
            .search([("code", "=", code), ("active", "=", True)], limit=1)
        )

    # ── Stored values ─────────────────────────────────────────────────────
    def test_both_policies_default_to_hidden(self):
        """Installing the module must not put any claim on a product page."""
        product = self._product()
        self.assertEqual(product.return_warranty, "hidden")
        self.assertEqual(product.delivery_days, "hidden")

    def test_every_fixed_warranty_option_is_stored(self):
        for option in ("none", "14_days", "30_days", "60_days", "90_days"):
            self.assertEqual(
                self._product(return_warranty=option).return_warranty, option
            )

    def test_every_fixed_delivery_option_is_stored(self):
        for option in ("none", "24h", "2_3_days", "3_5_days", "5_7_days"):
            self.assertEqual(self._product(delivery_days=option).delivery_days, option)

    def test_custom_values_are_stored(self):
        product = self._product(
            return_warranty="custom",
            return_warranty_custom_value=45,
            return_warranty_custom_period="days",
            delivery_days="custom",
            delivery_days_custom_value=36,
            delivery_days_custom_period="hours",
        )
        self.assertEqual(product.return_warranty_custom_value, 45)
        self.assertEqual(product.return_warranty_custom_period, "days")
        self.assertEqual(product.delivery_days_custom_value, 36)
        self.assertEqual(product.delivery_days_custom_period, "hours")

    # ── Display sentences ─────────────────────────────────────────────────
    def test_hidden_policies_produce_no_sentence(self):
        product = self._product()
        self.assertFalse(product.return_warranty_display)
        self.assertFalse(product.delivery_days_display)

    def test_fixed_policies_produce_their_sentence(self):
        product = self._product(return_warranty="30_days", delivery_days="2_3_days")
        self.assertEqual(product.return_warranty_display, "Return warranty: 30 days")
        self.assertEqual(product.delivery_days_display, "Delivery in 2-3 days")

    def test_negative_policies_produce_their_sentence(self):
        product = self._product(return_warranty="none", delivery_days="none")
        self.assertEqual(product.return_warranty_display, "No return warranty")
        self.assertEqual(product.delivery_days_display, "No home delivery")

    def test_custom_policies_compose_value_and_unit(self):
        product = self._product(
            return_warranty="custom",
            return_warranty_custom_value=6,
            return_warranty_custom_period="months",
            delivery_days="custom",
            delivery_days_custom_value=48,
            delivery_days_custom_period="hours",
        )
        self.assertEqual(product.return_warranty_display, "Return warranty: 6 months")
        self.assertEqual(product.delivery_days_display, "Delivery in 48 hours")

    def test_sentence_follows_the_stored_policy(self):
        """The sentence is computed, so editing the policy must refresh it."""
        product = self._product(delivery_days="24h")
        self.assertEqual(product.delivery_days_display, "Delivery in 24 hours")
        product.delivery_days = "5_7_days"
        self.assertEqual(product.delivery_days_display, "Delivery in 5-7 days")
        product.delivery_days = "hidden"
        self.assertFalse(product.delivery_days_display)

    def test_sentences_are_translated(self):
        """The shop-facing text must reach the visitor in their language."""
        if not self._lang_installed("es_ES"):
            self.skipTest("es_ES is not installed in this database")
        product = self._product(
            lang="es_ES", return_warranty="30_days", delivery_days="none"
        )
        self.assertEqual(
            product.return_warranty_display, "Garantía de devolución: 30 días"
        )
        self.assertEqual(product.delivery_days_display, "Sin entrega a domicilio")

    def test_custom_unit_is_translated(self):
        if not self._lang_installed("es_ES"):
            self.skipTest("es_ES is not installed in this database")
        product = self._product(
            lang="es_ES",
            delivery_days="custom",
            delivery_days_custom_value=48,
            delivery_days_custom_period="hours",
        )
        self.assertEqual(product.delivery_days_display, "Entrega en 48 horas")

    # ── Rendering ─────────────────────────────────────────────────────────
    def test_odoo_hardcoded_claims_are_gone(self):
        """The whole point of the override: Odoo's promises must not render."""
        html = self._render_terms(self._product())
        for claim in ODOO_HARDCODED:
            self.assertNotIn(claim, html)

    def test_terms_link_survives(self):
        """Removing the fake claims must not remove the legal link."""
        self.assertIn("/terms", self._render_terms(self._product()))

    def test_hidden_policies_render_nothing(self):
        html = self._render_terms(self._product())
        self.assertNotIn("product_return_warranty", html)
        self.assertNotIn("product_delivery_days", html)

    def test_fixed_options_render_their_text(self):
        html = self._render_terms(
            self._product(return_warranty="30_days", delivery_days="2_3_days")
        )
        self.assertIn("Return warranty: 30 days", html)
        self.assertIn("Delivery in 2-3 days", html)

    def test_negative_options_render_their_text(self):
        html = self._render_terms(
            self._product(return_warranty="none", delivery_days="none")
        )
        self.assertIn("No return warranty", html)
        self.assertIn("No home delivery", html)

    def test_each_policy_renders_independently(self):
        """A shop may publish delivery time without committing to returns."""
        html = self._render_terms(self._product(delivery_days="24h"))
        self.assertIn("Delivery in 24 hours", html)
        self.assertNotIn("product_return_warranty", html)

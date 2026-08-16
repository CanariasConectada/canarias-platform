# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

SOURCE = "es_ES"
TARGET = "en_US"


@tagged("post_install", "-at_install")
class TestAutoTranslateCoverage(TransactionCase):
    """Content created anywhere reaches the queue, not only in the four places.

    Asked for on 2026-08-16: "verifica que al crear un contenido en cualquier
    lado se esté generando la traducción". The answer at the time was no. The
    hook fired correctly, but it was only mounted on products, categories,
    pages, menus and events, so a shop's own description, the shop filters and
    the drop-down panels were never translated at all -- a shop whose products
    read in German while the paragraph introducing it stayed in Spanish.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang(SOURCE)
        cls.env["res.lang"]._activate_lang(TARGET)
        cls.company = cls.env.ref("base.main_company")
        cls.company.auto_translate_enabled = True
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("website_auto_translate.enabled", "True")
        params.set_param("website_auto_translate.source_lang", SOURCE)
        cls.Job = cls.env["auto.translate.job"]

    def _queued(self, record):
        return self.Job.search(
            [("model_name", "=", record._name), ("res_id", "=", record.id)]
        )

    def test_a_shop_filter_is_content_too(self):
        attribute = (
            self.env["product.attribute"]
            .with_context(lang=SOURCE)
            .create({"name": "Sin gluten"})
        )
        self.assertTrue(
            self._queued(attribute), "the words on /shop are read by visitors"
        )
        value = (
            self.env["product.attribute.value"]
            .with_context(lang=SOURCE)
            .create({"name": "Talla mediana", "attribute_id": attribute.id})
        )
        self.assertTrue(self._queued(value))

    def test_a_product_tag_is_queued(self):
        tag = (
            self.env["product.tag"]
            .with_context(lang=SOURCE)
            .create({"name": "Producto canario"})
        )
        self.assertTrue(self._queued(tag))

    def test_the_shop_own_description_is_queued(self):
        partner = self.company.partner_id
        partner.with_context(lang=SOURCE).write(
            {"website_description": "<p>Somos una tienda de barrio.</p>"}
        )
        self.assertTrue(
            self._queued(partner).filtered(
                lambda job: job.field_name == "website_description"
            ),
            "the paragraph introducing the shop is the first thing a visitor reads",
        )

    def test_a_customer_is_not_public_content_and_stays_out_of_it(self):
        customer = (
            self.env["res.partner"]
            .with_context(lang=SOURCE)
            .create(
                {
                    "name": "Cliente Particular",
                    "website_description": "<p>Notas internas.</p>",
                }
            )
        )
        self.assertFalse(
            self._queued(customer),
            "a partner table holds customers, and none of that is public",
        )

    def test_a_mega_menu_panel_is_queued_with_its_menu(self):
        website = self.env["website"].search(
            [("company_id", "=", self.company.id)], limit=1
        )
        menu = (
            self.env["website.menu"]
            .with_context(lang=SOURCE)
            .create(
                {
                    "name": "Tienda",
                    "url": "/shop",
                    "website_id": website.id,
                    "mega_menu_content": "<section><p>Nuestras marcas</p></section>",
                }
            )
        )
        fields_queued = self._queued(menu).mapped("field_name")
        self.assertIn("name", fields_queued)
        self.assertIn("mega_menu_content", fields_queued)

    def test_the_product_page_paragraph_is_queued(self):
        product = (
            self.env["product.template"]
            .with_context(lang=SOURCE)
            .create({"name": "Queso de flor", "description_ecommerce": "<p>Curado.</p>"})
        )
        self.assertIn("description_ecommerce", self._queued(product).mapped("field_name"))

    def test_a_field_nobody_filled_in_does_not_take_a_row_in_the_queue(self):
        product = (
            self.env["product.template"]
            .with_context(lang=SOURCE)
            .create({"name": "Gofio de millo"})
        )
        self.assertEqual(
            set(self._queued(product).mapped("field_name")),
            {"name"},
            "an empty field is not content, and a row for it is noise",
        )

    def test_a_shop_category_page_is_queued_whole(self):
        category = (
            self.env["product.public.category"]
            .with_context(lang=SOURCE)
            .create({"name": "Quesos", "website_description": "<p>De la isla.</p>"})
        )
        self.assertIn("website_description", self._queued(category).mapped("field_name"))
        category.with_context(lang=SOURCE).write(
            {"website_footer": "<p>Envíos a toda Canarias.</p>"}
        )
        self.assertIn("website_footer", self._queued(category).mapped("field_name"))

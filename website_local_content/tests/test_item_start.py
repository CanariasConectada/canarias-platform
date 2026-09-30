# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import create_taxonomy


@tagged("post_install", "-at_install")
class TestItemStart(TransactionCase):
    """Creating an item has to say WHICH kind of item.

    Reported on 2026-08-16: "cuando creas nuevo de memoria viva y lugares de
    interés, no veo que permitas definir cuál vamos a crear".

    One list for both is the right way to read them. It is not the right way
    to create in: plain New opens a record that could become either, and the
    field that decides sits eight rows down inside Classification.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.memories, cls.memories_category, _sub = create_taxonomy(cls.env, "MEM")
        cls.places, cls.places_category, _sub = create_taxonomy(cls.env, "PLA")

    def test_the_picker_carries_the_answer_into_the_form(self):
        wizard = self.env["website.local.content.item.start"].create(
            {"type_id": self.places.id, "name": "Playa de Las Canteras"}
        )

        action = wizard.action_create()

        self.assertEqual(action["res_model"], "website.local.content.item")
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["context"]["default_type_id"], self.places.id)
        self.assertEqual(action["context"]["default_name"], "Playa de Las Canteras")

    def test_the_form_actually_opens_on_the_type_that_was_picked(self):
        """The default has to reach the record, not just the context.

        `default_type_id` is only a promise until something creates with it.
        """
        wizard = self.env["website.local.content.item.start"].create(
            {"type_id": self.memories.id}
        )
        action = wizard.action_create()

        item = (
            self.env["website.local.content.item"]
            .with_context(**action["context"])
            .create(
                {
                    "name": "Kiosco de la Música",
                    "category_id": self.memories_category.id,
                }
            )
        )

        self.assertEqual(item.type_id, self.memories)

    def test_no_title_leaves_the_form_blank_rather_than_inventing_one(self):
        wizard = self.env["website.local.content.item.start"].create(
            {"type_id": self.places.id}
        )
        self.assertNotIn("default_name", wizard.action_create()["context"])

    def test_the_category_is_left_for_the_author_to_choose(self):
        """Guessing it would put a value in front of somebody who did not pick it.

        The category is required and its domain follows the type, so a guess
        is not even guaranteed to be legal.
        """
        wizard = self.env["website.local.content.item.start"].create(
            {"type_id": self.places.id}
        )
        self.assertNotIn("default_category_id", wizard.action_create()["context"])

    def test_the_list_no_longer_offers_a_create_that_does_not_ask(self):
        """Two create buttons, one of which asks and one of which does not,
        is a worse screen than either alone."""
        action = self.env.ref("website_local_content.local_content_item_action")
        self.assertIn(
            "'create': False",
            action.context,
            "the plain New has to hand over to the picker",
        )

    def test_there_is_a_way_in_from_the_menu_as_well(self):
        menu = self.env.ref(
            "website_local_content.menu_local_content_item_start",
            raise_if_not_found=False,
        )
        self.assertTrue(menu, "removing New without a replacement leaves no way in")
        self.assertTrue(menu.active)

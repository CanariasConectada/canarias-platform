# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The picker's candidate set, and what happens when it is empty.

`_get_own_microsite_companies()` is the picker's ONLY source of truth: what
it excludes here is what a merchant never sees as an option there.
"""

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestMicrositeCompanyPicker(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env["res.company"]
        Website = cls.env["website"]

        cls.shop_a = Company.create({"name": "Comercio Picker A"})
        cls.shop_a.website_id = Website.create(
            {"name": "Comercio Picker A", "company_id": cls.shop_a.id}
        )
        cls.shop_b = Company.create({"name": "Comercio Picker B"})
        cls.shop_b.website_id = Website.create(
            {"name": "Comercio Picker B", "company_id": cls.shop_b.id}
        )
        # No website: must never be a pickable candidate. `auto_microsite_generator`
        # provisions a website for every new company by default (see
        # `auto_microsite_generator/models/res_company.py`), so a website-less
        # fixture must opt out explicitly via `no_microsite_auto`, or it would
        # never actually be website-less.
        cls.shop_without_site = Company.with_context(no_microsite_auto=True).create(
            {"name": "Comercio Sin Web"}
        )

        # A real shop the owner does NOT own: never in `company_ids`. Plays
        # the "attacker's target" for the forged-picker-selection test below.
        cls.stranger = Company.create({"name": "Comercio de Otro Dueno"})
        cls.stranger.website_id = Website.create(
            {"name": "Comercio de Otro Dueno", "company_id": cls.stranger.id}
        )

        cls.main = cls.env.ref("base.main_company")

        cls.owner = new_test_user(
            cls.env,
            login="picker_owner",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop_a.id,
            company_ids=[
                (
                    6,
                    0,
                    (cls.shop_a | cls.shop_b | cls.shop_without_site | cls.main).ids,
                )
            ],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _as_owner(self):
        return self.env(user=self.owner.id)["res.company"]

    def _env_as_owner(self):
        return self.env(user=self.owner.id)

    def test_the_platform_company_never_appears(self):
        candidates = self._as_owner()._get_own_microsite_companies()
        self.assertNotIn(self.main, candidates)

    def test_a_shop_without_a_website_never_appears(self):
        candidates = self._as_owner()._get_own_microsite_companies()
        self.assertNotIn(self.shop_without_site, candidates)

    def test_real_shops_with_a_website_appear(self):
        candidates = self._as_owner()._get_own_microsite_companies()
        self.assertEqual(candidates, self.shop_a | self.shop_b)

    def test_the_zone_company_never_appears_when_the_module_is_present(self):
        """Guarded: `zone_company_ownership` is not a hard dependency of this
        module, so the field only exists when it happens to be installed
        alongside it (as it is in the platform's real deployment).
        """
        Company = self.env["res.company"]
        if "zone_company_key" not in Company._fields:
            self.skipTest("zone_company_ownership is not installed here")

        zone = Company.create({"name": "Comercio de Zona"})
        zone.website_id = self.env["website"].create(
            {"name": "Comercio de Zona", "company_id": zone.id}
        )
        zone.zone_company_key = "guanarteme"
        self.owner.company_ids = [(4, zone.id)]

        candidates = self._as_owner()._get_own_microsite_companies()
        self.assertNotIn(zone, candidates)

    def test_the_no_website_fallback_message_is_shown_not_an_empty_picker(self):
        """Owns 2+ real shops, none with a `website_id`: a sentence, not an
        empty or broken picker step.
        """
        Company = self.env["res.company"].with_context(no_microsite_auto=True)
        homeless_a = Company.create({"name": "Sin Web A"})
        homeless_b = Company.create({"name": "Sin Web B"})
        homeless_owner = new_test_user(
            self.env,
            login="picker_homeless_owner",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=homeless_a.id,
            company_ids=[(6, 0, (homeless_a | homeless_b).ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )
        editor = self.env["microsite.content.editor"].with_user(homeless_owner)
        with self.assertRaises(UserError):
            editor.action_open_page_content()

    # ------------------------------------------------------------------
    # The wizard itself, end to end -- not just the set it is built on
    # ------------------------------------------------------------------

    def test_the_picker_lists_the_owned_set_and_opens_the_chosen_shop(self):
        """`company_ids` on the picker IS the owned set, not a copy of it,
        and choosing a shop opens the editor pre-loaded with THAT company.
        """
        Picker = self._env_as_owner()["microsite.company.picker"]
        picker = Picker.create({})
        self.assertEqual(picker.company_ids, self.shop_a | self.shop_b)

        picker.selected_company_id = self.shop_b
        action = picker.action_open_editor()
        self.assertEqual(action["res_model"], "microsite.content.editor")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["microsite_company_id"], self.shop_b.id)

    def test_action_open_editor_with_a_foreign_company_id_is_rejected(self):
        """Assigning `selected_company_id` directly bypasses the view's own
        domain, exactly as writing straight onto a form field would: the
        wizard delegates to `_resolve_target_company`, so a shop the owner
        does not own is refused with `AccessError`, not silently opened.
        """
        Picker = self._env_as_owner()["microsite.company.picker"]
        picker = Picker.create({})
        picker.selected_company_id = self.stranger
        with self.assertRaises(AccessError):
            picker.action_open_editor()

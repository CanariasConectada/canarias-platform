# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools.translate import code_translations

from odoo.addons.partner_microsite_manager.wizards.microsite_content_editor import (
    ADDRESS_FIELDS,
)


@tagged("post_install", "-at_install")
class TestMicrositeContentEditor(TransactionCase):
    """A merchant editing the content of their own page, and only their own.

    Reported on 2026-08-16: "el tema de que los contactos no tengan el espacio
    de la pestaña para añadir su contenido de página no está […] creo que va a
    ser mejor colocarlo en sitio web en las pestañas de configuración".

    The screen has to do two things that the company form could not: save at
    all for somebody who is not an administrator, and refuse to save anything
    but the page.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shop = cls.env["res.company"].create({"name": "Mi Comercio"})
        cls.shop.website_id = cls.env["website"].create(
            {"name": "Mi Comercio", "company_id": cls.shop.id}
        )
        cls.neighbour = cls.env["res.company"].create({"name": "El de al lado"})
        cls.neighbour.website_id = cls.env["website"].create(
            {"name": "El de al lado", "company_id": cls.neighbour.id}
        )
        # A real shop the merchant does NOT own: never in `company_ids`.
        # Plays the "attacker's target" in the tampered-id tests below.
        cls.stranger = cls.env["res.company"].create({"name": "Comercio Ajeno"})
        cls.stranger.website_id = cls.env["website"].create(
            {"name": "Comercio Ajeno", "company_id": cls.stranger.id}
        )
        # A new website copies the main company's social links (core's
        # _default_social_*). On a CI database that is Odoo's own Facebook
        # and Instagram, and the social tests below assert what the merchant
        # typed, so the fixtures start blank -- as a merchant's site does.
        (cls.shop | cls.neighbour | cls.stranger).website_id.write(
            {
                "social_facebook": False,
                "social_instagram": False,
                "social_twitter": False,
                "social_youtube": False,
                "social_linkedin": False,
            }
        )
        cls.merchant = new_test_user(
            cls.env,
            login="microsite_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, (cls.shop | cls.neighbour).ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )
        # Owner of exactly ONE real shop: the "sole owner" fixture for the
        # single-shop / no-picker requirement.
        cls.solo_merchant = new_test_user(
            cls.env,
            login="microsite_solo_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, cls.shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _editor(self, user=None):
        return self.env["microsite.content.editor"].with_user(user or self.merchant)

    def test_the_screen_opens_on_the_merchants_own_shop(self):
        values = self._editor().default_get(["company_id", "microsite_about_title"])
        self.assertEqual(values["company_id"], self.shop.id)

    def test_it_opens_filled_in_with_what_is_already_published(self):
        self.shop.sudo().microsite_about_title = "Nuestra historia"
        values = self._editor().default_get(["microsite_about_title"])
        self.assertEqual(values["microsite_about_title"], "Nuestra historia")

    def test_a_merchant_can_actually_save(self):
        """The whole point.

        `res.company` is writable by `base.group_erp_manager` alone, so the
        company form loads for a merchant and then refuses to save. If this
        test ever fails with an AccessError, the screen has been quietly
        turned back into that.
        """
        editor = self._editor().create(
            {
                "microsite_about_title": "Quiénes somos",
                "opening_slot_ids": [
                    (0, 0, {"weekday": str(day), "open_time": 10, "close_time": 14})
                    for day in range(5)
                ],
            }
        )
        editor.action_save()
        self.assertEqual(self.shop.microsite_about_title, "Quiénes somos")
        self.assertEqual(self.shop.microsite_opening_hours, "L-V 10:00-14:00")

    def test_a_forged_company_id_on_the_form_is_rejected(self):
        """A company id that came back from a browser is a request, not a fact.

        `self.stranger` is a real shop but NEVER in this merchant's
        `company_ids`: it stands for an attacker's target, reachable only by
        writing the id straight onto the (readonly, in the view) form field,
        bypassing the UI entirely. `_resolve_target_company` must catch this
        exactly as it would catch a forged context, and neither shop's
        content may change.
        """
        editor = self._editor().create({"microsite_about_title": "Mío"})
        editor.company_id = self.stranger
        with self.assertRaises(AccessError):
            editor.action_save()
        self.assertFalse(self.shop.microsite_about_title)
        self.assertFalse(self.stranger.microsite_about_title)

    def test_default_get_with_a_foreign_company_id_in_context_is_rejected(self):
        """The context transport is not trusted any more than the form field.

        `self.stranger` is never in `self.merchant`'s `company_ids`; a
        tampered context (e.g. a stale or forged picker action) must be
        refused exactly like the tampered form field is.
        """
        editor = self._editor().with_context(microsite_company_id=self.stranger.id)
        with self.assertRaises(AccessError):
            editor.default_get(["company_id"])

    def test_garbage_company_ids_are_rejected(self):
        """Neither a non-numeric id nor an out-of-range one is a shop."""
        for garbage in ("abc", 999999, -1):
            with self.subTest(garbage=garbage):
                with self.assertRaises(AccessError):
                    self._editor()._resolve_target_company(garbage)

    def test_a_falsy_company_id_falls_back_to_the_session_shop_like_no_id_at_all(
        self,
    ):
        """``0`` is never a real ``res.company`` id -- ids start at 1.

        `_resolve_target_company` treats it as "no id was given", not as an
        invalid candidate, and resolves the session company exactly like
        ``None`` would. This is documented behaviour, not an oversight: see
        the docstring on `_resolve_target_company`.
        """
        company = self._editor()._resolve_target_company(0)
        self.assertEqual(company, self.shop)

    def test_an_owned_shop_can_be_targeted_through_the_action_context(self):
        """The whole point of the picker: a request MAY name a different,
        but still OWNED, shop -- and it is honoured, not just tolerated.
        """
        editor = (
            self._editor()
            .with_context(microsite_company_id=self.neighbour.id)
            .create({"microsite_about_title": "De al lado"})
        )
        editor.action_save()
        self.assertEqual(self.neighbour.microsite_about_title, "De al lado")
        self.assertFalse(self.shop.microsite_about_title)

    def test_it_writes_the_page_and_nothing_else(self):
        """The VAT number is not part of the page."""
        self.shop.sudo().vat = "ESB00000000"
        editor = self._editor().create({"microsite_about_title": "Hola"})
        editor.action_save()
        self.assertEqual(
            self.shop.vat,
            "ESB00000000",
            "only the whitelist may be written by this screen",
        )

    def test_the_validation_on_the_company_still_runs(self):
        """sudo skips the access rules. It must not skip the constraints.

        The map URL scheme check lives on ``res.company`` (opening hours are
        rows now, validated before they reach the company, see
        ``test_opening_slots``).
        """
        editor = self._editor().create({"microsite_map_url": "javascript:alert(1)"})
        with self.assertRaises(Exception):
            editor.action_save()
        self.assertFalse(self.shop.microsite_map_url)


    def test_social_links_open_with_the_websites_value_first(self):
        """The footer reads website first, company second. So does the screen."""
        self.shop.website_id.sudo().social_facebook = "https://www.facebook.com/web"
        self.shop.sudo().social_instagram = "https://www.instagram.com/cia"
        values = self._editor().default_get(["social_facebook", "social_instagram"])
        self.assertEqual(values["social_facebook"], "https://www.facebook.com/web")
        self.assertEqual(values["social_instagram"], "https://www.instagram.com/cia")

    def test_saving_a_social_link_reaches_the_footer(self):
        editor = self._editor().create(
            {"social_facebook": "https://www.facebook.com/micomercio"}
        )
        editor.action_save()
        links = self.shop.website_id._pmm_footer_social_links()
        self.assertIn(
            "https://www.facebook.com/micomercio", [l["href"] for l in links]
        )

    def test_clearing_a_social_link_clears_both_sides(self):
        """An emptied link must not resurrect through the company fallback."""
        self.shop.website_id.sudo().social_youtube = "https://www.youtube.com/a"
        self.shop.sudo().social_youtube = "https://www.youtube.com/b"
        editor = self._editor().create({"social_youtube": False})
        editor.action_save()
        self.assertFalse(self.shop.website_id.social_youtube)
        self.assertFalse(self.shop.social_youtube)
        self.assertEqual(self.shop.website_id._pmm_footer_social_links(), [])

    def test_an_account_with_no_shop_is_told_so_rather_than_shown_a_traceback(self):
        nobody = new_test_user(
            self.env,
            login="microsite_nobody",
            groups="base.group_user,website.group_website_restricted_editor",
            context={"no_reset_password": True, "tracking_disable": True},
        )
        nobody.company_id = self.env.ref("base.main_company")
        with self.assertRaises(UserError):
            self._editor(nobody).default_get(["company_id"])

    # ------------------------------------------------------------------
    # What the menu opens, which is not the same screen for everybody
    # ------------------------------------------------------------------

    def test_the_sole_owner_of_a_shop_gets_their_own_editor_with_zero_extra_clicks(
        self,
    ):
        """The single-shop path is unchanged: straight to the editor."""
        action = self._editor(self.solo_merchant).action_open_page_content()
        self.assertEqual(action["res_model"], "microsite.content.editor")
        self.assertEqual(action["target"], "new")
        self.assertEqual(
            action["context"]["microsite_company_id"],
            self.shop.id,
        )

    def test_the_owner_of_two_shops_gets_their_shops_instead(self):
        """`self.merchant` owns two real shops (see setUpClass).

        Until 2026-09-14 this was a modal asking which one, and nothing
        else. It is now the list of their sites -- the same decision, made
        on a screen they can also work from -- so the editor is still never
        opened on a guess.
        """
        action = self._editor().action_open_page_content()
        self.assertEqual(action["res_model"], "website")
        self.assertEqual(action["target"], "current")
        listed = self.env["website"].search(action["domain"])
        self.assertEqual(
            listed.company_id, self.shop | self.neighbour,
            "their own two shops, and no more",
        )
        self.assertNotIn(self.stranger, listed.company_id)

    def test_a_button_of_that_list_refuses_somebody_elses_site(self):
        """The rows are the caller's own, but a button carries an id."""
        with self.assertRaises(AccessError):
            self.stranger.website_id.with_user(
                self.merchant
            ).action_microsite_content()

    def test_a_row_of_the_list_opens_the_content_as_its_button_does(self):
        """Reported 2026-09-15: the row landed on the website form.

        The list names the `js_class` whose controller answers a click on
        the row with the row's `action_microsite_content`, the very method
        behind the Content button -- so the ownership guard above is the
        one the row goes through as well. The button itself stays.
        """
        view = self.env.ref("partner_microsite_manager.website_view_list_merchant")
        root = etree.fromstring(view.arch)
        self.assertEqual(root.tag, "list")
        self.assertEqual(root.get("js_class"), "merchant_website_list")
        self.assertTrue(
            root.xpath("//button[@name='action_microsite_content']"),
            "the Content button is still on the row",
        )

    def test_the_buttons_open_the_right_screens_for_their_own_site(self):
        site = self.shop.website_id.with_user(self.merchant)
        content = site.action_microsite_content()
        self.assertEqual(content["res_model"], "microsite.content.editor")
        self.assertEqual(content["context"]["microsite_company_id"], self.shop.id)
        for method, model in (
            ("action_microsite_pages", "website.page"),
            ("action_microsite_orders", "sale.order"),
        ):
            with self.subTest(method=method):
                action = getattr(site, method)()
                self.assertEqual(action["res_model"], model)
                self.assertEqual(action["domain"], [("website_id", "=", site.id)])

    def test_an_administrator_gets_the_shops_instead_of_an_error(self):
        """Reported on 2026-08-17 with a screenshot of the dialog.

        The menu is gated on `group_website_restricted_editor`, which every
        administrator holds as well, and an administrator has no shop of their
        own -- so the only thing the entry ever did for them was raise
        "Operación no válida". The same fields already sit on a page of the
        company form, which they may write; the menu now takes them there.
        """
        admin = new_test_user(
            self.env,
            login="microsite_admin",
            groups="base.group_user,base.group_erp_manager,"
            "website.group_website_restricted_editor",
            context={"no_reset_password": True, "tracking_disable": True},
        )
        admin.company_id = self.env.ref("base.main_company")
        action = self._editor(admin).action_open_page_content()
        self.assertEqual(action["res_model"], "res.company")
        self.assertIn(("website_id", "!=", False), action["domain"])

    def test_somebody_with_neither_still_gets_told_why(self):
        """No shop and no right to manage others: a sentence, not a traceback."""
        nobody = new_test_user(
            self.env,
            login="microsite_neither",
            groups="base.group_user,website.group_website_restricted_editor",
            context={"no_reset_password": True, "tracking_disable": True},
        )
        nobody.company_id = self.env.ref("base.main_company")
        with self.assertRaises(UserError):
            self._editor(nobody).action_open_page_content()

    def test_the_way_in_is_where_a_merchant_already_works(self):
        menu = self.env.ref(
            "partner_microsite_manager.menu_own_microsite_content",
            raise_if_not_found=False,
        )
        self.assertTrue(menu, "the screen needs a door a merchant can reach")
        self.assertEqual(
            menu.parent_id, self.env.ref("website.menu_website_configuration")
        )

    # ------------------------------------------------------------------
    # The shop's own website (client request 2026-09-16)
    # ------------------------------------------------------------------

    def test_the_own_website_opens_with_the_companys_value(self):
        self.shop.sudo().website = "https://www.abinformatica.es"
        values = self._editor().default_get(["company_website"])
        self.assertEqual(values["company_website"], "https://www.abinformatica.es")

    def test_saving_the_own_website_adds_the_missing_scheme(self):
        """Merchants type the host; the page needs an absolute URL."""
        editor = self._editor().create({"company_website": "  www.abinformatica.es "})
        editor.action_save()
        self.assertEqual(self.shop.website, "https://www.abinformatica.es")
        self.assertEqual(
            self.shop.website_id._pmm_own_website_link(),
            {
                "href": "https://www.abinformatica.es",
                "title": "www.abinformatica.es",
                "icon": "fa-globe",
            },
        )

    def test_a_full_url_is_stored_as_typed(self):
        editor = self._editor().create({"company_website": "http://abinformatica.es/tienda"})
        editor.action_save()
        self.assertEqual(self.shop.website, "http://abinformatica.es/tienda")

    def test_a_link_that_is_not_a_website_is_refused(self):
        """The value lands in a public href: only http(s) gets through."""
        self.shop.sudo().website = "https://www.kept.example"
        for bad in ("javascript:alert(1)", "ftp://files.example", "mailto:a@b.c", "https://"):
            editor = self._editor().create({"company_website": bad})
            with self.assertRaises(ValidationError, msg=bad):
                editor.action_save()
        self.assertEqual(self.shop.website, "https://www.kept.example")

    def test_clearing_the_own_website_clears_it(self):
        self.shop.sudo().website = "https://www.abinformatica.es"
        editor = self._editor().create({"company_website": "   "})
        editor.action_save()
        self.assertFalse(self.shop.website)
        self.assertIsNone(self.shop.website_id._pmm_own_website_link())

    # ------------------------------------------------------------------
    # The dialog title speaks the merchant's language
    # ------------------------------------------------------------------

    def test_the_dialog_title_is_translated_for_a_spanish_merchant(self):
        """Reported 2026-09-16: the dialog opened as "Page content" in Spanish.

        Odoo 19 takes a Python term from the ``.po`` only when its block
        carries the ``#. odoo-python`` comment; the ``code:`` reference
        alone is not enough. Both halves are asserted: the term is loaded
        from ``es.po``, and the action built through the same server action
        the menu runs carries it.
        """
        terms = code_translations.get_python_translations(
            "partner_microsite_manager", "es_ES"
        )
        self.assertEqual(terms.get("Page content"), "Contenido de la página")
        self.env["res.lang"]._activate_lang("es_ES")
        self.solo_merchant.lang = "es_ES"
        action = (
            self.env.ref("partner_microsite_manager.action_own_microsite_content")
            .with_user(self.solo_merchant)
            .with_context(lang="es_ES", allowed_company_ids=self.shop.ids)
            .run()
        )
        self.assertEqual(action["res_model"], "microsite.content.editor")
        self.assertEqual(action["name"], "Contenido de la página")

    # ------------------------------------------------------------------
    # Postal address. Owner report 2026-11-03 (churreriaastridolafpalme):
    # "Find us" showed only the city because the partner had no street,
    # and this screen had nowhere to type one.
    # ------------------------------------------------------------------

    @staticmethod
    def _address_writes(calls):
        """The ``res.partner.write`` calls among ``calls`` that carried an
        address field (the company write also reaches the partner, through
        the related ``website`` field; those calls are not counted)."""
        found = []
        for call in calls:
            vals = call.args[1] if len(call.args) > 1 else call.kwargs.get("vals", {})
            if set(vals) & set(ADDRESS_FIELDS):
                found.append(call)
        return found

    def _watching_partner_writes(self):
        """Patch ``res.partner.write`` so its calls are recorded AND still run."""
        partner_cls = type(self.shop.partner_id)
        return patch.object(
            partner_cls, "write", autospec=True, side_effect=partner_cls.write
        )

    def test_the_address_opens_cleaned_from_the_partner(self):
        """The 2026 importer left a literal ``&nbsp;`` in 31 streets. The
        merchant sees plain text, as the page prints it."""
        self.shop.partner_id.sudo().write(
            {
                "street": "Calle Castillejos 37-39&nbsp;35010",
                "zip": "35010",
                "city": "Las Palmas de Gran Canaria",
            }
        )
        values = self._editor().default_get(["street", "zip", "city"])
        self.assertNotIn("&nbsp;", values["street"])
        self.assertTrue(values["street"].startswith("Calle Castillejos 37-39"))
        self.assertEqual(values["zip"], "35010")
        self.assertEqual(values["city"], "Las Palmas de Gran Canaria")

    def test_saving_the_address_reaches_the_partner_and_the_page(self):
        editor = self._editor().create(
            {
                "street": "Calle Lepanto 10",
                "zip": "35010",
                "city": "Las Palmas de Gran Canaria",
            }
        )
        editor.action_save()
        partner = self.shop.partner_id
        self.assertEqual(partner.street, "Calle Lepanto 10")
        self.assertEqual(partner.zip, "35010")
        self.assertEqual(partner.city, "Las Palmas de Gran Canaria")
        self.assertEqual(
            self.shop._get_microsite_live_address(),
            "Calle Lepanto 10, 35010 Las Palmas de Gran Canaria",
        )

    def test_saving_the_address_writes_the_partner_once(self):
        """Every ``res.partner.write`` flushes the page cache and relinks the
        legacy homepage; the four fields must travel in ONE write, not in one
        write each as ``res.company``'s related inverses would do it."""
        editor = self._editor().create(
            {"street": "Calle Lepanto 10", "city": "Las Palmas de Gran Canaria"}
        )
        with self._watching_partner_writes() as write:
            editor.action_save()
        self.assertEqual(len(self._address_writes(write.call_args_list)), 1)
        self.assertEqual(self.shop.partner_id.street, "Calle Lepanto 10")
        self.assertEqual(self.shop.partner_id.city, "Las Palmas de Gran Canaria")

    def test_opening_and_saving_does_not_touch_an_untouched_address(self):
        """Opening the screen cleans the entity out of the street; saving the
        screen unchanged must not write the cleaned text back. A partner write
        makes the address line of a legacy homepage live, and only a human
        edit may do that."""
        raw = "Calle Castillejos 37-39&nbsp;35010"
        self.shop.partner_id.sudo().write({"street": raw, "zip": "35010"})
        opened = self._editor().default_get(list(ADDRESS_FIELDS))
        editor = self._editor().create({name: opened[name] for name in ADDRESS_FIELDS})
        with self._watching_partner_writes() as write:
            editor.action_save()
        # The recorder did see the save (the company write reaches the
        # partner through its related fields), so an empty list below is a
        # real absence, not a patch that recorded nothing.
        self.assertTrue(write.called, "the recorder must have seen the save")
        self.assertEqual(self._address_writes(write.call_args_list), [])
        self.assertEqual(self.shop.partner_id.street, raw)

    def test_only_the_fields_that_changed_are_written(self):
        """Changing the postal code must not rewrite the street the importer
        left with a literal entity: the partner keeps it as it was, and the
        one write carries the postal code alone."""
        raw = "Calle Castillejos 37-39&nbsp;35010"
        self.shop.partner_id.sudo().write({"street": raw, "zip": "35010"})
        opened = self._editor().default_get(list(ADDRESS_FIELDS))
        values = {name: opened[name] for name in ADDRESS_FIELDS}
        values["zip"] = "35011"
        editor = self._editor().create(values)
        with self._watching_partner_writes() as write:
            editor.action_save()
        writes = self._address_writes(write.call_args_list)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].args[1], {"zip": "35011"})
        self.assertEqual(self.shop.partner_id.street, raw)
        self.assertEqual(self.shop.partner_id.zip, "35011")

    def test_clearing_the_address_clears_it_on_the_partner(self):
        """An emptied field is written as ``False``: the address is the
        shop's own, and the page then shows no "Find us" line."""
        self.shop.partner_id.sudo().write(
            {"street": "Calle Lepanto 10", "zip": "35010", "city": "Las Palmas"}
        )
        editor = self._editor().create({"street": " ", "zip": False, "city": ""})
        editor.action_save()
        partner = self.shop.partner_id
        self.assertFalse(partner.street)
        self.assertFalse(partner.zip)
        self.assertFalse(partner.city)
        self.assertFalse(self.shop._get_microsite_live_address())

    def test_a_merchant_cannot_write_the_partner_directly_but_the_screen_can(self):
        """Why the address goes through the screen: ``res.partner`` is
        read-only for ``base.group_user`` (writing it takes
        ``base.group_partner_manager``, implied by ``base.group_system``
        alone), and a merchant is neither."""
        with self.assertRaises(AccessError):
            self.shop.partner_id.with_user(self.merchant).write({"street": "x"})
        editor = self._editor().create({"street": "Calle Lepanto 10"})
        editor.action_save()
        self.assertEqual(self.shop.partner_id.street, "Calle Lepanto 10")

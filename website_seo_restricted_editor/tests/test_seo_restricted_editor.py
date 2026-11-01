# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSeoRestrictedEditor(TransactionCase):
    """A restricted editor optimises the SEO of their own site's pages and
    can do nothing else to a page."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env["res.company"]
        cls.own_company = Company.create({"name": "SEO RE Own Shop"})
        cls.other_company = Company.create({"name": "SEO RE Other Shop"})
        Website = cls.env["website"]
        cls.own_site = Website.create(
            {"name": "SEO RE own site", "company_id": cls.own_company.id}
        )
        cls.other_site = Website.create(
            {"name": "SEO RE other site", "company_id": cls.other_company.id}
        )
        cls.own_page = cls._page(cls.own_site, "/seo-re-own")
        cls.other_page = cls._page(cls.other_site, "/seo-re-other")

        cls.editor = cls.env["res.users"].create(
            {
                "name": "SEO RE Editor",
                "login": "seo_re_editor",
                "company_id": cls.own_company.id,
                "company_ids": [(6, 0, cls.own_company.ids)],
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("website.group_website_restricted_editor").id),
                ],
            }
        )
        cls.designer = cls.env["res.users"].create(
            {
                "name": "SEO RE Designer",
                "login": "seo_re_designer",
                "company_id": cls.own_company.id,
                "company_ids": [(6, 0, cls.own_company.ids)],
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("website.group_website_designer").id),
                ],
            }
        )

    @classmethod
    def _page(cls, site, url):
        return cls.env["website.page"].create(
            {
                "name": "SEO RE page %s" % url,
                "url": url,
                "type": "qweb",
                "arch": "<t t-name=\"seo_re%s\"><div/></t>" % url.replace("/", "_"),
                "website_id": site.id,
                "is_published": True,
            }
        )

    def _as_editor(self, page):
        return page.with_user(self.editor).with_context(website_id=self.own_site.id)

    def test_the_editor_saves_seo_on_their_own_page(self):
        self._as_editor(self.own_page).write(
            {
                "website_meta_title": "Own title",
                "website_meta_description": "Own description",
                "website_meta_keywords": "own,keywords",
                "website_indexed": False,
            }
        )
        self.assertEqual(self.own_page.website_meta_title, "Own title")
        self.assertFalse(self.own_page.website_indexed)

    def test_another_site_stays_out_of_reach(self):
        with self.assertRaises(AccessError):
            self._as_editor(self.other_page).write({"website_meta_title": "Not yours"})
        self.assertFalse(self.other_page.website_meta_title)

    def test_only_the_seo_fields_are_theirs(self):
        for vals in (
            {"name": "Renamed"},
            {"url": "/moved"},
            {"is_published": False},
            {"website_meta_title": "ok", "url": "/smuggled"},
        ):
            with self.subTest(vals=vals), self.assertRaises(AccessError):
                self._as_editor(self.own_page).write(vals)
        self.assertEqual(self.own_page.url, "/seo-re-own")
        self.assertTrue(self.own_page.is_published)

    def test_no_creating_or_deleting_pages(self):
        with self.assertRaises(AccessError):
            self.env["website.page"].with_user(self.editor).create(
                {
                    "name": "New",
                    "url": "/seo-re-new",
                    "type": "qweb",
                    "arch": "<t t-name=\"seo_re_new\"><div/></t>",
                    "website_id": self.own_site.id,
                }
            )
        with self.assertRaises(AccessError):
            self._as_editor(self.own_page).unlink()
        self.assertTrue(self.own_page.exists())

    def test_designers_are_unaffected(self):
        self.other_page.with_user(self.designer).write({"name": "Designer renamed"})
        self.assertEqual(self.other_page.name, "Designer renamed")

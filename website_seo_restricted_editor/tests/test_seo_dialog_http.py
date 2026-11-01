# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSeoDialogHttp(HttpCase):
    """The Optimize SEO dialog saves through ``/web/dataset/call_kw`` with the
    editor's own session: the same path, end to end."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env["res.company"].create({"name": "SEO HTTP Shop"})
        cls.site = cls.env["website"].create(
            {"name": "SEO HTTP site", "company_id": company.id}
        )
        cls.page = cls.env["website.page"].create(
            {
                "name": "SEO HTTP page",
                "url": "/seo-http-page",
                "type": "qweb",
                "arch": '<t t-name="seo_http_page"><div/></t>',
                "website_id": cls.site.id,
                "is_published": True,
            }
        )
        cls.env["res.users"].create(
            {
                "name": "SEO HTTP Editor",
                "login": "seo_http_editor",
                "password": "seo_http_editor_pw",
                "company_id": company.id,
                "company_ids": [(6, 0, company.ids)],
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("website.group_website_restricted_editor").id),
                ],
            }
        )

    def _call_kw(self, model, method, args, kwargs=None):
        response = self.url_open(
            "/web/dataset/call_kw/%s/%s" % (model, method),
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {"model": model, "method": method, "args": args, "kwargs": kwargs or {}},
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        return response.json()

    def test_the_dialog_save_lands_and_anything_else_is_refused(self):
        self.authenticate("seo_http_editor", "seo_http_editor_pw")
        seo = self._call_kw(
            "website.page",
            "write",
            [[self.page.id], {"website_meta_title": "From the dialog", "website_meta_description": "d"}],
            {"context": {"website_id": self.site.id}},
        )
        self.assertNotIn("error", seo, seo)
        self.assertEqual(self.page.website_meta_title, "From the dialog")

        other = self._call_kw(
            "website.page",
            "write",
            [[self.page.id], {"url": "/renamed-from-the-dialog"}],
            {"context": {"website_id": self.site.id}},
        )
        self.assertIn("error", other)
        self.assertEqual(self.page.url, "/seo-http-page")

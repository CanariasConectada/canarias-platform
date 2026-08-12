# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from .common import NO_MAIL_CTX


@tagged("post_install", "-at_install")
class TestCertificationLanding(HttpCase):
    """The public page at /certification/<code> and its training material."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, **NO_MAIL_CTX))
        cls.group = cls.env["res.groups"].create({"name": "Landing Cert User"})
        cls.cert_type = cls.env["certification.type"].create(
            {
                "name": "Landing Vertical",
                "code": "landing-vertical",
                "group_user_id": cls.group.id,
                "website_title": "Become Landing certified",
                "website_description": "What this seal means.",
                "landing_description": "<p>The long story of the seal.</p>",
                "landing_published": True,
            }
        )

    def _add_material(self, name, **values):
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"{name}.pdf",
                "datas": base64.b64encode(b"%PDF-1.4 test"),
                "mimetype": "application/pdf",
            }
        )
        return self.env["certification.material"].create(
            dict(
                {
                    "name": name,
                    "type_id": self.cert_type.id,
                    "attachment_id": attachment.id,
                },
                **values,
            )
        )

    # -- the page -------------------------------------------------------
    def test_published_landing_is_public(self):
        response = self.url_open("/certification/landing-vertical")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Become Landing certified", response.text)
        self.assertIn("The long story of the seal.", response.text)

    def test_unpublished_landing_is_a_404_not_an_empty_page(self):
        # Answering 200 with nothing would get the page indexed.
        self.cert_type.landing_published = False

        response = self.url_open("/certification/landing-vertical")

        self.assertEqual(response.status_code, 404)

    def test_unknown_code_is_a_404(self):
        response = self.url_open("/certification/no-such-vertical")

        self.assertEqual(response.status_code, 404)

    def test_material_is_listed_in_order(self):
        self._add_material("Module 2", sequence=20)
        self._add_material("Module 1", sequence=10)

        response = self.url_open("/certification/landing-vertical")

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            response.text.index("Module 1"),
            response.text.index("Module 2"),
            "material must follow its sequence",
        )

    def test_a_material_without_a_file_is_never_listed(self):
        # attachment_id is required, so the only way to lose the file is for
        # it to be deleted underneath: the page must not render a dead link.
        material = self._add_material("Orphan module")
        material.attachment_id.unlink()

        response = self.url_open("/certification/landing-vertical")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Orphan module", response.text)

    # -- the certified-business list ------------------------------------
    def _certify(self, name, level="gold", score=100, with_site=True):
        """A company holding this seal, optionally with a microsite."""
        company = self.env["res.company"].create({"name": name})
        if with_site:
            self.env["website"].create(
                {
                    "name": name,
                    "company_id": company.id,
                    "domain": "https://%s.example.com" % name.lower().replace(" ", ""),
                }
            )
        return self.env["res.company.certification"].create(
            {
                "company_id": company.id,
                "type_id": self.cert_type.id,
                "level": level,
                "score": score,
                "expiry_date": "2099-01-01",
            }
        )

    def test_certified_companies_are_listed_strongest_first(self):
        self._certify("Bronze Shop", level="bronze", score=45)
        self._certify("Gold Shop", level="gold", score=95)

        response = self.url_open("/certification/landing-vertical")

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            response.text.index("Gold Shop"),
            response.text.index("Bronze Shop"),
            "the strongest seals lead the list",
        )

    def test_level_filter_narrows_the_list(self):
        self._certify("Bronze Shop", level="bronze", score=45)
        self._certify("Gold Shop", level="gold", score=95)

        response = self.url_open("/certification/landing-vertical?level=bronze")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Bronze Shop", response.text)
        self.assertNotIn("Gold Shop", response.text)

    def test_an_unknown_level_shows_everything_rather_than_nothing(self):
        # The value arrives from the query string, so it is attacker-chosen;
        # it must not become a domain leaf or an empty page.
        self._certify("Gold Shop", level="gold", score=95)

        response = self.url_open("/certification/landing-vertical?level=platinum")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Gold Shop", response.text)

    def test_an_expired_seal_is_not_listed(self):
        status = self._certify("Lapsed Shop")
        status.expiry_date = "2000-01-01"

        response = self.url_open("/certification/landing-vertical")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Lapsed Shop", response.text)

    def test_a_company_without_a_microsite_is_not_listed(self):
        # The card is a link to the shop; with no site there is nowhere to go.
        self._certify("Siteless Shop", with_site=False)

        response = self.url_open("/certification/landing-vertical")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Siteless Shop", response.text)

    # -- the badge image ------------------------------------------------
    # A 1x1 PNG: enough to prove the bytes travel, small enough to inline.
    BADGE_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
        b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def test_a_visitor_can_fetch_the_badge(self):
        # The seal used to be inlined as a data URI in every microsite
        # homepage; it is now a URL, and that URL has to answer to visitors
        # who cannot read certification.type.
        self.cert_type.badge_image = base64.b64encode(self.BADGE_PNG)

        response = self.url_open("/certification/landing-vertical/badge")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["Content-Type"].startswith("image/"))
        self.assertGreater(
            response.headers.get("Cache-Control", "").find("max-age"), -1
        )

    def test_the_badge_of_an_unpublished_vertical_is_a_404(self):
        # The route reads as sudo, so the published flag is the only thing
        # standing between a draft vertical's artwork and the public.
        self.cert_type.badge_image = base64.b64encode(self.BADGE_PNG)
        self.cert_type.landing_published = False

        response = self.url_open("/certification/landing-vertical/badge")

        self.assertEqual(response.status_code, 404)

    def test_a_vertical_without_a_badge_is_a_404_not_a_placeholder(self):
        response = self.url_open("/certification/landing-vertical/badge")

        self.assertEqual(response.status_code, 404)

    # -- the download ---------------------------------------------------
    def test_attaching_material_publishes_the_file(self):
        # A private attachment would answer 403 to exactly the visitors this
        # material exists for.
        material = self._add_material("Module 1")

        self.assertTrue(material.attachment_id.public)

    def test_a_visitor_can_download_the_material(self):
        material = self._add_material("Module 1")

        response = self.url_open(material.download_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.4 test")

    def test_relinking_a_file_publishes_the_new_one(self):
        material = self._add_material("Module 1")
        replacement = self.env["ir.attachment"].create(
            {
                "name": "replacement.pdf",
                "datas": base64.b64encode(b"%PDF-1.4 new"),
                "mimetype": "application/pdf",
            }
        )
        self.assertFalse(replacement.public)

        material.attachment_id = replacement

        self.assertTrue(replacement.public)

    def test_material_dies_with_its_vertical(self):
        material = self._add_material("Module 1")

        self.cert_type.unlink()

        self.assertFalse(material.exists())

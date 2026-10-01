# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import BaseCase

from ..tools.safe_url import safe_http_url


class TestSafeHttpUrl(BaseCase):
    """Pure helper: no database involved."""

    def test_script_and_data_schemes_are_refused(self):
        for value in (
            "javascript://x%0aalert(1)",
            "javascript:alert(1)",
            "JaVaScRiPt:alert(1)",
            "java\tscript:alert(1)",
            "java\nscript:alert(1)",
            "java script:alert(1)",
            " vbscript:msgbox(1)",
            "data:text/html,<script>alert(1)</script>",
            "mailto:shop@example.com",
            "https://",
        ):
            self.assertEqual(safe_http_url(value), "", repr(value))

    def test_http_links_are_kept_or_completed(self):
        self.assertEqual(safe_http_url("//host.example/x"), "https://host.example/x")
        self.assertEqual(safe_http_url("shop.example"), "https://shop.example")
        self.assertEqual(safe_http_url("localhost:8080/x"), "https://localhost:8080/x")
        self.assertEqual(
            safe_http_url(" https://shop.example/a "), "https://shop.example/a"
        )
        self.assertEqual(safe_http_url("HTTP://shop.example"), "HTTP://shop.example")
        self.assertEqual(safe_http_url(""), "")
        self.assertEqual(safe_http_url(None), "")

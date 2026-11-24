# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
from datetime import date
from unittest.mock import patch

from PIL import Image

from odoo.tests import TransactionCase

TODAY = date(2026, 12, 10)


def make_image(fmt="PNG", size=(40, 40), color=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


class RaffleCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].create({"name": "Raffle test site"})
        cls.merchant = cls.env["res.company"].create({"name": "Shop A"})
        cls.merchant_b = cls.env["res.company"].create({"name": "Shop B"})
        cls.outsider = cls.env["res.company"].create({"name": "Outsider"})
        cls.campaign = cls.env["raffle.campaign"].create(
            {
                "name": "Test raffle",
                "website_id": cls.website.id,
                "slug": "test-raffle",
                "short_path": "/test-raffle-short",
                "alias_paths": "/test-raffle-typo,/test-raffle-tipo",
                "date_start": "2026-12-01",
                "date_end": "2026-12-31",
                "draw_date": "2027-01-02",
                "min_amount": 15,
                "participating_company_ids": [
                    (6, 0, (cls.merchant | cls.merchant_b).ids)
                ],
                "terms_html": "<p>Legal terms</p>",
                "banner_image": base64.b64encode(make_image(size=(800, 300))),
                "state": "open",
            }
        )
        patcher = patch.object(
            type(cls.env["raffle.campaign"]),
            "_raffle_today",
            lambda self: TODAY,
        )
        patcher.start()
        cls.addClassCleanup(patcher.stop)

    def _data(self, **overrides):
        data = {
            "participant_name": "Ana Perez",
            "email": "ana@example.com",
            "phone": "600 123 456",
            "merchant_id": str(self.merchant.id),
            "amount": "15,01",
            "purchase_date": "2026-12-05",
            "is_adult": "1",
            "terms_accepted": "1",
            "honeypot": "",
        }
        data.update(overrides)
        return data

    _counter = 0

    def _upload(self, fmt="PNG"):
        # Unique pixels so the checksum differs between calls.
        type(self)._counter += 1
        n = type(self)._counter
        return ("ticket.png", make_image(fmt, color=(n % 255, 50, (n * 7) % 255)))

    def _submit(self, ip="10.0.0.1", upload=None, **overrides):
        return self.campaign._submit_entry(
            self._data(**overrides), upload or self._upload(), ip
        )

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import io

from PIL import Image

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import RaffleCommon, make_image


@tagged("post_install", "-at_install")
class TestRaffleSubmission(RaffleCommon):
    def test_valid_submit_creates_entry_and_private_attachment_no_partner(self):
        partners = self.env["res.partner"].search_count([])
        entry = self._submit()
        self.assertTrue(entry.reference.startswith("SRT-"))
        self.assertEqual(entry.state, "pending")
        self.assertEqual(entry.amount, 15.01)
        self.assertTrue(entry.terms_version)
        att = entry.receipt_attachment_id
        self.assertTrue(att)
        self.assertFalse(att.public)
        self.assertEqual((att.res_model, att.res_id), ("raffle.entry", entry.id))
        self.assertEqual(self.env["res.partner"].search_count([]), partners)

    def test_rules_reject_bad_input(self):
        cases = {
            "amount equal to minimum": {"amount": "15"},
            "amount below minimum": {"amount": "3,50"},
            "amount garbage": {"amount": "abc"},
            "date before window": {"purchase_date": "2026-11-30"},
            "date after window": {"purchase_date": "2027-01-01"},
            "date in the future": {"purchase_date": "2026-12-20"},
            "foreign merchant": {"merchant_id": str(self.outsider.id)},
            "missing merchant": {"merchant_id": ""},
            "not adult": {"is_adult": ""},
            "terms not accepted": {"terms_accepted": ""},
            "bad email": {"email": "not-an-email"},
            "short phone": {"phone": "12345"},
            "honeypot": {"honeypot": "http://spam"},
        }
        for label, overrides in cases.items():
            with self.subTest(label), self.assertRaises(UserError):
                with self.env.cr.savepoint():
                    self._submit(**overrides)
        self.assertFalse(self.campaign.entry_ids)

    def test_closed_window_and_state(self):
        self.campaign.state = "closed"
        with self.assertRaises(UserError):
            self._submit()
        self.campaign.state = "open"
        self.campaign.date_end = "2026-12-09"
        with self.assertRaises(UserError):
            self._submit(purchase_date="2026-12-05")

    def test_amount_just_over_minimum_is_accepted(self):
        self.assertTrue(self._submit(amount="15.01"))

    def test_file_validation(self):
        with self.assertRaises(UserError):
            self._submit(upload=("x.png", b"just text pretending to be an image"))
        with self.assertRaises(UserError):
            self._submit(upload=("x.png", b""))
        with self.assertRaises(UserError):
            self.campaign._submit_entry(self._data(), None, "10.0.0.1")
        big = b"%PDF-1.4" + b"0" * (10 * 1024 * 1024)
        with self.assertRaises(UserError):
            self._submit(upload=("big.pdf", big))
        # The extension is irrelevant: a PDF named .png is a PDF.
        entry = self._submit(upload=("fake.png", b"%PDF-1.4 tiny"))
        self.assertEqual(entry.receipt_attachment_id.mimetype, "application/pdf")
        heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20
        entry = self._submit(upload=("p.heic", heic), email="h@example.com")
        self.assertEqual(entry.receipt_attachment_id.mimetype, "image/heic")

    def test_large_image_is_downscaled(self):
        entry = self._submit(upload=("big.jpg", make_image("JPEG", size=(3000, 2400))))
        stored = entry.receipt_attachment_id.raw
        self.assertLessEqual(max(Image.open(io.BytesIO(stored)).size), 2000)

    def test_duplicate_checksum_blocked_but_same_triplet_only_flagged(self):
        upload = self._upload()
        first = self._submit(upload=upload)
        with self.assertRaises(UserError):
            self._submit(upload=upload, email="other@example.com")
        # Same merchant, date and amount with a DIFFERENT file: accepted, flagged.
        second = self._submit()
        self.assertTrue(first.possible_duplicate)
        self.assertTrue(second.possible_duplicate)
        third = self._submit(amount="99")
        self.assertFalse(third.possible_duplicate)

    def test_rate_limit_per_ip(self):
        for i in range(10):
            self._submit(ip="10.9.9.9", email=f"user{i}@example.com")
        with self.assertRaises(UserError):
            self._submit(ip="10.9.9.9", email="user99@example.com")
        # Another address is unaffected.
        self.assertTrue(self._submit(ip="10.9.9.8", email="fine@example.com"))

    def test_rate_limit_per_email(self):
        for i in range(20):
            self._submit(ip=f"10.1.0.{i}")
        with self.assertRaises(UserError):
            self._submit(ip="10.1.1.1")


@tagged("post_install", "-at_install")
class TestRaffleDraw(RaffleCommon):
    def _entries(self, n, valid=True):
        entries = self.env["raffle.entry"]
        for i in range(n):
            entries |= self._submit(ip=f"10.2.0.{i}", email=f"p{i}@example.com")
        if valid:
            entries.action_validate()
        return entries

    def test_draw_only_valid_no_repeats_audited_and_not_repeatable(self):
        valid = self._entries(6)
        pending = self._entries(3, valid=False)
        pending[1:2].write({"state": "rejected"})
        self.campaign.action_close()
        self.campaign.action_draw()
        self.assertEqual(self.campaign.state, "drawn")
        ranked = self.campaign.entry_ids.filtered("draw_rank").sorted("draw_rank")
        self.assertEqual(len(ranked), 4)  # winner + 3 alternates
        self.assertLessEqual(set(ranked.ids), set(valid.ids))
        self.assertEqual(len(set(ranked.ids)), 4)
        self.assertEqual(self.campaign.winner_entry_id, ranked[0])
        self.assertEqual(self.campaign.alternate_entry_ids, ranked[1:])
        self.assertEqual(self.campaign.drawn_by, self.env.user)
        self.assertTrue(self.campaign.drawn_at)
        self.assertIn("Winner", self.campaign.message_ids[0].body)
        with self.assertRaises(UserError):
            self.campaign.action_draw()

    def test_draw_needs_closed_and_valid_entries(self):
        with self.assertRaises(UserError):
            self.campaign.action_draw()
        self.campaign.action_close()
        with self.assertRaises(UserError):
            self.campaign.action_draw()

    def test_reset_draw_leaves_trace_and_allows_redraw(self):
        self._entries(2)
        self.campaign.action_close()
        self.campaign.action_draw()
        self.campaign.action_reset_draw()
        self.assertEqual(self.campaign.state, "closed")
        self.assertFalse(self.campaign.winner_entry_id)
        self.assertIn("RESET", self.campaign.message_ids[0].body)
        self.campaign.action_draw()
        self.assertEqual(self.campaign.state, "drawn")

    def test_anonymize_keeps_winner_and_alternates(self):
        entries = self._entries(8)
        self.campaign.action_close()
        self.campaign.action_draw()
        drawn = self.campaign.entry_ids.filtered("draw_rank")
        self.campaign.action_anonymize_entries()
        for entry in drawn:
            self.assertFalse(entry.anonymized)
            self.assertTrue(entry.email)
            self.assertTrue(entry.receipt_attachment_id)
        for entry in entries - drawn:
            self.assertTrue(entry.anonymized)
            self.assertFalse(entry.email or entry.phone or entry.submit_ip)
            self.assertFalse(entry.receipt_attachment_id)
        self.assertFalse(
            self.env["ir.attachment"].search(
                [
                    ("res_model", "=", "raffle.entry"),
                    ("res_id", "in", (entries - drawn).ids),
                ]
            )
        )
        with self.assertRaises(UserError):
            self.campaign.action_reset_draw()

    def test_reject_wizard(self):
        entry = self._entries(1, valid=False)
        wizard = self.env["raffle.entry.reject.wizard"].create(
            {"entry_ids": [(6, 0, entry.ids)], "reason": "Illegible"}
        )
        wizard.action_confirm()
        self.assertEqual((entry.state, entry.reject_reason), ("rejected", "Illegible"))


@tagged("post_install", "-at_install")
class TestRaffleAccessAndConfig(RaffleCommon):
    def test_non_admin_cannot_read_entries(self):
        entry = self._submit()
        internal = new_test_user(self.env, "raffle_internal", groups="base.group_user")
        portal = new_test_user(self.env, "raffle_portal", groups="base.group_portal")
        for user in (internal, portal):
            with self.assertRaises(AccessError):
                entry.with_user(user).read(["participant_name"])
            with self.assertRaises(AccessError):
                self.env["raffle.entry"].with_user(user).search([])
            with self.assertRaises(AccessError):
                self.campaign.with_user(user).read(["name"])
        admin = new_test_user(self.env, "raffle_admin", groups="base.group_system")
        self.assertTrue(entry.with_user(admin).read(["participant_name"]))

    def test_aliases_become_301_rewrites_and_follow_edits(self):
        rewrites = self.env["website.rewrite"].search(
            [("name", "=like", f"raffle.campaign:{self.campaign.id}:%")]
        )
        self.assertEqual(
            {(r.url_from, r.url_to, r.redirect_type) for r in rewrites},
            {
                ("/test-raffle-typo", "/test-raffle-short", "301"),
                ("/test-raffle-tipo", "/test-raffle-short", "301"),
            },
        )
        self.campaign.alias_paths = "/test-raffle-tipo, /Another/"
        rewrites = self.env["website.rewrite"].search(
            [("name", "=like", f"raffle.campaign:{self.campaign.id}:%")]
        )
        self.assertEqual(
            sorted(rewrites.mapped("url_from")),
            ["/another", "/test-raffle-tipo"],
        )
        self.campaign.active = False
        self.assertFalse(
            self.env["website.rewrite"].search(
                [("name", "=like", f"raffle.campaign:{self.campaign.id}:%")]
            )
            and self.env["website.rewrite"]
            .search([("name", "=like", f"raffle.campaign:{self.campaign.id}:%")])
            .filtered("active")
        )
        self.campaign.unlink()
        self.assertFalse(
            self.env["website.rewrite"]
            .with_context(active_test=False)
            .search([("name", "=like", "raffle.campaign:%")])
            .filtered(lambda r: "test-raffle" in r.url_from)
        )

    def test_address_validation(self):
        for field, value in (
            ("slug", "Bad Slug"),
            ("short_path", "/with space"),
            ("short_path", "/shop"),
            ("short_path", "/web/login"),
            ("alias_paths", "/ok,/test-raffle-short"),
        ):
            with self.subTest(value), self.assertRaises(ValidationError):
                with self.env.cr.savepoint():
                    self.campaign.write({field: value})
        with self.assertRaises(ValidationError):
            self.campaign.date_end = "2026-11-01"

    def test_open_requires_merchants_and_terms(self):
        draft = self.campaign.copy(
            {
                "slug": "draft-one",
                "short_path": False,
                "alias_paths": False,
                "participating_company_ids": False,
            }
        )
        with self.assertRaises(UserError):
            draft.action_open()

    def test_zone_helper(self):
        if "commercial_zone" not in self.env["res.company"]._fields:
            self.skipTest("res_company_zone not installed")
        shop = self.env["res.company"].create(
            {"name": "Zone shop", "commercial_zone": "guanarteme"}
        )
        self.campaign.zone_to_add = "guanarteme"
        self.campaign.action_add_zone_merchants()
        self.assertIn(shop, self.campaign.participating_company_ids)

    def test_qr_png(self):
        self.assertTrue(self.campaign._qr_png().startswith(b"\x89PNG"))

    def test_only_open_campaign_in_window_is_banner_campaign(self):
        model = self.env["raffle.campaign"]
        self.assertEqual(model._open_campaign(self.website), self.campaign)
        self.campaign.date_end = "2026-12-09"
        self.assertFalse(model._open_campaign(self.website))
        self.campaign.date_end = "2026-12-31"
        self.campaign.state = "closed"
        self.assertFalse(model._open_campaign(self.website))

    def test_translatable_fields_and_terms_not_translated(self):
        fields = self.env["raffle.campaign"]._fields
        for name in ("name", "banner_button_label", "intro_html", "success_message"):
            self.assertTrue(fields[name].translate, name)
        self.assertFalse(fields["terms_html"].translate)
        self.assertEqual(
            set(self.campaign._auto_translate_fields()),
            {"name", "banner_button_label", "intro_html", "success_message"},
        )

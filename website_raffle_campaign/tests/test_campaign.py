# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import io
from datetime import datetime, timezone
from unittest.mock import patch

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

    def test_same_ip_never_blocks(self):
        """Behind the proxy everyone shares one address: no per-IP decision."""
        for i in range(12):
            self._submit(ip="172.17.0.1", email=f"user{i}@example.com")
        self.assertEqual(len(self.campaign.entry_ids), 12)

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
        rewrite = self.env["website.rewrite"].with_context(active_test=False)
        domain = [("name", "=like", f"raffle.campaign:{self.campaign.id}:%")]
        self.campaign.active = False
        found = rewrite.search(domain)
        self.assertEqual(len(found), 2)
        self.assertFalse(any(found.mapped("active")))
        self.campaign.active = True
        self.assertTrue(all(rewrite.search(domain).mapped("active")))
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


@tagged("post_install", "-at_install")
class TestRaffleAccent(RaffleCommon):
    def test_default_accent(self):
        self.assertEqual(self.campaign.accent_color, "#b3122e")
        self.assertIn("--raffle-accent: #b3122e", self.campaign._accent_style())

    def test_valid_accents(self):
        for value in ("#fff", "#F2C46D", "#123abc"):
            with self.subTest(value):
                self.campaign.accent_color = value
        self.campaign.accent_color = "#abc"
        self.assertIn("--raffle-accent: #aabbcc", self.campaign._accent_style())

    def test_invalid_accents_are_refused(self):
        for value in (
            "red",
            "#12",
            "#12345",
            "#1234567",
            "b3122e",
            "#ggg",
            "",
            "#fff; background:url(x)",
            "#fff\n",
            '#fff"><script>',
        ):
            with (
                self.subTest(value),
                self.assertRaises(ValidationError),
                self.env.cr.savepoint(),
            ):
                self.campaign.accent_color = value

    def test_text_colour_follows_contrast(self):
        self.campaign.accent_color = "#ffffff"
        self.assertIn("--raffle-on-accent: #2b1a1f", self.campaign._accent_style())
        self.campaign.accent_color = "#000000"
        self.assertIn("--raffle-on-accent: #ffffff", self.campaign._accent_style())


class TestRaffleOptionalQuestions(RaffleCommon):
    def test_defaults_keep_the_old_rules(self):
        self.assertTrue(self.campaign.ask_merchant)
        self.assertTrue(self.campaign.ask_amount)
        with self.assertRaises(UserError):
            self._submit(merchant_id="")
        with self.assertRaises(UserError):
            self._submit(amount="15")

    def test_no_merchant_no_amount(self):
        self.campaign.write({"ask_merchant": False, "ask_amount": False})
        entry = self._submit(merchant_id="", amount="")
        self.assertFalse(entry.merchant_id)
        self.assertEqual(entry.amount, 0)
        self.assertEqual(entry.amount_label, "—")
        # Whatever is posted is ignored, not validated.
        entry2 = self._submit(merchant_id="999999", amount="1", email="b@example.com")
        self.assertFalse(entry2.merchant_id)
        self.assertEqual(entry2.amount, 0)

    def test_no_merchant_still_checks_amount(self):
        self.campaign.ask_merchant = False
        with self.assertRaises(UserError):
            self._submit(merchant_id="", amount="10")
        entry = self._submit(merchant_id="", amount="20")
        self.assertFalse(entry.merchant_id)
        self.assertEqual(entry.amount, 20)

    def test_duplicates_without_merchant(self):
        self.campaign.ask_merchant = False
        first = self._submit(amount="20", email="a@example.com")
        second = self._submit(amount="20", email="b@example.com")
        other = self._submit(amount="21", email="c@example.com")
        self.assertTrue(first.possible_duplicate and second.possible_duplicate)
        self.assertFalse(other.possible_duplicate)

    def test_no_duplicate_hint_without_both_questions(self):
        self.campaign.write({"ask_merchant": False, "ask_amount": False})
        first = self._submit(email="a@example.com")
        second = self._submit(email="b@example.com")
        self.assertFalse(first.possible_duplicate or second.possible_duplicate)

    def test_open_without_merchants_when_not_asked(self):
        draft = self.campaign.copy(
            {"slug": "no-merchants", "state": "draft", "short_path": False}
        )
        draft.participating_company_ids = False
        with self.assertRaises(UserError):
            draft.action_open()
        draft.ask_merchant = False
        draft.action_open()
        self.assertEqual(draft.state, "open")


class TestRaffleHardening(RaffleCommon):
    def test_amount_formats(self):
        parse = self.env["raffle.campaign"]._parse_amount
        for raw, expected in (
            ("1.500,50", 1500.5),
            ("15,5", 15.5),
            ("15.50", 15.5),
            ("1.500", 1500.0),
            ("1500", 1500.0),
            ("20 €", 20.0),
            ("0,99", 0.99),
        ):
            self.assertEqual(parse(raw), expected, raw)
        for raw in ("", "abc", "1,2,3", "-5", "nan", "1e3"):
            self.assertIsNone(parse(raw), raw)

    def test_invalid_calendar_date(self):
        with self.assertRaises(UserError):
            self._submit(purchase_date="2026-02-30")

    def test_exact_boundary_purchase_dates(self):
        self.campaign.date_end = "2026-12-10"  # patched today
        self.assertTrue(self._submit(purchase_date="2026-12-01"))
        self.assertTrue(self._submit(purchase_date="2026-12-10"))
        with self.assertRaises(UserError):
            self._submit(purchase_date="2026-11-30")
        with self.assertRaises(UserError):
            self._submit(purchase_date="2026-12-11")

    def test_upload_size_at_limit(self):
        pad = 10 * 1024 * 1024 - len(b"%PDF-")
        entry = self._submit(upload=("max.pdf", b"%PDF-" + b"0" * pad))
        self.assertEqual(entry.receipt_attachment_id.mimetype, "application/pdf")
        with self.assertRaises(UserError):
            self._submit(upload=("big.pdf", b"%PDF-" + b"0" * (pad + 1)))

    def test_pdf_receipt_url_downloads_image_does_not(self):
        pdf = self._submit(upload=("a.pdf", b"%PDF-1.4 x"))
        self.assertIn("download=true", pdf.receipt_url)
        img = self._submit(email="img@example.com")
        self.assertIn("download=false", img.receipt_url)

    def test_images_are_reencoded_without_exif(self):
        buffer = io.BytesIO()
        exif = Image.Exif()
        exif[0x010F] = "SecretCamera"  # Make
        gps = exif.get_ifd(0x8825)
        gps[2] = (28.0, 8.0, 0.0)
        Image.new("RGB", (50, 50), (9, 9, 9)).save(buffer, format="JPEG", exif=exif)
        original = buffer.getvalue()
        self.assertIn(b"SecretCamera", original)
        entry = self._submit(upload=("p.jpg", original))
        stored = entry.receipt_attachment_id.raw
        self.assertNotIn(b"SecretCamera", stored)
        self.assertFalse(Image.open(io.BytesIO(stored)).getexif())

    def test_decompression_bomb_rejected_before_decoding(self):
        buffer = io.BytesIO()
        Image.new("1", (9000, 9000)).save(buffer, format="PNG")  # 81 Mpx, tiny file
        self.assertLess(len(buffer.getvalue()), 1024 * 1024)
        with self.assertRaises(UserError):
            self._submit(upload=("bomb.png", buffer.getvalue()))

    def test_duplicate_checksum_race_hits_integrity_path(self):
        upload = self._upload()
        self._submit(upload=upload)
        model = type(self.env["raffle.campaign"])
        with patch.object(model, "_check_limits", lambda *a, **k: None):
            with self.assertRaises(UserError) as ctx:
                self._submit(upload=upload, email="race@example.com")
        self.assertIn("ya está registrado", str(ctx.exception))

    def test_state_guards(self):
        with self.assertRaises(UserError):
            self.campaign.action_open()  # already open
        self._submit_valid()
        self.campaign.action_close()
        with self.assertRaises(UserError):
            self.campaign.action_close()
        self.campaign.action_draw()
        for method in (
            "action_open",
            "action_close",
            "action_reopen",
            "action_set_draft",
        ):
            with self.subTest(method), self.assertRaises(UserError):
                getattr(self.campaign, method)()

    def _submit_valid(self, n=1):
        entries = self.env["raffle.entry"]
        for i in range(n):
            entries |= self._submit(email=f"v{i}@example.com")
        entries.action_validate()
        return entries

    def test_drawn_campaign_locks_entry_review(self):
        entries = self._submit_valid(2)
        self.campaign.action_close()
        self.campaign.action_draw()
        for vals in (
            {"state": "rejected"},
            {"amount": 99.0},
            {"merchant_id": self.merchant_b.id},
        ):
            with self.subTest(vals), self.assertRaises(UserError):
                entries[0].write(vals)
        with self.assertRaises(UserError):
            entries[0].unlink()
        self.campaign.action_reset_draw()
        entries[0].write({"state": "rejected"})

    def test_draw_with_fewer_valid_than_slots(self):
        entries = self._submit_valid(2)
        self.campaign.action_close()
        self.campaign.action_draw()
        self.assertEqual(len(self.campaign.entry_ids.filtered("draw_rank")), 2)
        self.assertEqual(len(self.campaign.alternate_entry_ids), 1)
        self.assertEqual(set(entries.mapped("draw_rank")), {1, 2})

    def test_draw_chatter_has_references_only_and_snapshot(self):
        entries = self._submit_valid(3)
        self.campaign.action_close()
        self.campaign.action_draw()
        body = str(self.campaign.message_ids[0].body)
        self.assertIn("<li>", body)
        self.assertIn(self.campaign.winner_entry_id.reference, body)
        for entry in entries:
            self.assertNotIn(entry.participant_name, body)
            self.assertNotIn(entry.email, body)
        refs = sorted(entries.mapped("reference"))
        self.assertEqual(self.campaign.draw_candidates_snapshot.split("\n"), refs)
        self.assertEqual(
            self.campaign.draw_candidates_hash,
            hashlib.sha256("\n".join(refs).encode()).hexdigest(),
        )

    def test_draw_clears_stale_ranks(self):
        entries = self._submit_valid(3)
        entries[2].draw_rank = 7  # stale value from an interrupted run
        self.campaign.action_close()
        self.campaign.action_draw()
        self.assertEqual(sorted(entries.mapped("draw_rank")), [1, 2, 3])

    def test_entry_has_no_public_follower_or_creation_log(self):
        entry = self._submit()
        self.assertFalse(entry.message_follower_ids)

    def test_anonymize_wipes_chatter_and_reject_reason(self):
        entries = self._submit_valid(2)
        entries[0].write({"state": "rejected", "reject_reason": "Illegible ticket"})
        entries[0].message_post(body="Reviewer note")
        self.assertTrue(entries[0].message_ids)
        self.campaign.action_close()
        self.campaign.action_draw()
        self.campaign.action_anonymize_all()
        for entry in entries:
            self.assertTrue(entry.anonymized)
            self.assertFalse(
                entry.reject_reason or entry.email or entry.receipt_attachment_id
            )
            self.assertFalse(entry.message_ids)
            self.assertEqual(entry.participant_name, "[anonymized]")

    def test_address_clashes_with_pages_and_foreign_rewrites(self):
        page = self.env["website.page"].create(
            {
                "url": "/clash-page",
                "website_id": self.website.id,
                "type": "qweb",
                "arch": "<t t-call='website.layout'><div>x</div></t>",
            }
        )
        self.assertTrue(page)
        with self.assertRaises(ValidationError):
            self.campaign.short_path = "/clash-page"
        self.env["website.rewrite"].create(
            {
                "name": "foreign",
                "website_id": self.website.id,
                "url_from": "/clash-redirect",
                "url_to": "/elsewhere",
                "redirect_type": "301",
            }
        )
        with self.assertRaises(ValidationError):
            self.campaign.alias_paths = "/clash-redirect"

    def test_moving_website_rechecks_addresses(self):
        other = self.env["website"].create({"name": "Other site"})
        self.env["website.rewrite"].create(
            {
                "name": "foreign2",
                "website_id": other.id,
                "url_from": "/test-raffle-short",
                "url_to": "/elsewhere",
                "redirect_type": "301",
            }
        )
        with self.assertRaises(ValidationError):
            self.campaign.website_id = other

    def test_uninstall_hook_cleans_up(self):
        from odoo.addons.website_raffle_campaign import uninstall_hook

        entry = self._submit()
        att = entry.receipt_attachment_id
        uninstall_hook(self.env)
        self.assertFalse(att.exists())
        self.assertFalse(
            self.env["website.rewrite"]
            .with_context(active_test=False)
            .search([("name", "=like", "raffle.campaign:%")])
        )


@tagged("post_install", "-at_install")
class TestRaffleTimezone(RaffleCommon):
    """Real clock, server in UTC, campaign days decided in Atlantic/Canary.

    In July the Canaries are UTC+1, so local midnight is 23:00 UTC.
    """

    patch_today = False

    def _at(self, iso_utc):
        fixed = datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc)
        mocked = patch(
            "odoo.addons.website_raffle_campaign.models.raffle_campaign.datetime"
        )
        fake = mocked.start()
        fake.now.side_effect = lambda tz=None: fixed.astimezone(tz)
        self.addCleanup(mocked.stop)

    def setUp(self):
        super().setUp()
        self.campaign.write({"date_start": "2026-07-01", "date_end": "2026-07-31"})

    def test_last_second_of_last_day_is_open(self):
        self._at("2026-07-31T22:59:59")  # 23:59:59 local
        self.assertTrue(self.campaign._is_open())

    def test_midnight_after_last_day_is_closed(self):
        self._at("2026-07-31T23:00:00")  # 00:00 on 1 August local
        self.assertFalse(self.campaign._is_open())

    def test_first_instant_of_first_day_is_open(self):
        self._at("2026-06-30T23:00:00")  # 00:00 on 1 July local
        self.assertTrue(self.campaign._is_open())

    def test_just_before_first_day_is_closed(self):
        self._at("2026-06-30T22:59:59")
        self.assertFalse(self.campaign._is_open())

    def test_purchase_today_in_local_time_not_future(self):
        # 23:30 UTC on 30 June is already 1 July in the Canaries.
        self._at("2026-06-30T23:30:00")
        self.assertTrue(self._submit(purchase_date="2026-07-01"))

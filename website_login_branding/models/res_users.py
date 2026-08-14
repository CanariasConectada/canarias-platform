# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Non-routable domain for guest logins. No mail server is authoritative for it,
# so a stray notification can never be delivered to a real inbox and the
# address can never collide with a genuine account.
GUEST_EMAIL_DOMAIN = "guests.canariasconectada.es"

# The shared community channel guests are dropped into so they have something
# in Discuss and a res.users to hang a web-push subscription on. Resolved once
# and cached in this config parameter (an admin can repoint it -- see
# ``_get_community_channel``).
COMMUNITY_CHANNEL_PARAM = "website_login_branding.community_channel_id"
COMMUNITY_CHANNEL_NAME = "Comunidad Canarias Conectada"

# The sibling module ``discuss_channel_zone`` already ships a platform-wide
# "Canarias Conectada" channel that EVERY account belongs to. When it is
# installed we reuse it instead of creating a second, near-identical channel
# that would fragment the community. Referenced softly (raise_if_not_found=
# False) so this module keeps no hard dependency on it.
ZONE_GENERAL_CHANNEL_XMLID = "discuss_channel_zone.channel_canarias"

# A guest is purged once it has been idle this long AND carries no meaningful
# data. Seven days matches the product decision; change it here only.
GUEST_STALE_DAYS = 7


class ResUsers(models.Model):
    """Anonymous portal guests created by the ``/guest/enter`` controller.

    A guest is an ordinary ``share`` portal account flagged with
    ``is_platform_guest`` so we can find, reuse and garbage-collect it without
    ever confusing it with a real customer. The flag is the single source of
    truth for "this account is disposable".
    """

    _inherit = "res.users"

    is_platform_guest = fields.Boolean(
        string="Platform Guest",
        default=False,
        copy=False,
        index=True,
        help="Anonymous throwaway account created from the website's "
        "'Entrar como invitado' button. Reused via a signed cookie and "
        "garbage-collected once idle. Never set this by hand.",
    )

    def _notify_security_setting_update(self, subject, content, **kwargs):
        """Never warn a guest that their password changed.

        Core sends this whenever ``password`` is in the vals of a
        ``res.users.write`` (``mail/models/res_users.py:234-238``), and
        ``/guest/enter`` rotates a throwaway password on EVERY entry, not only
        at creation. So each anonymous visit was queueing a "Security Update:
        Password Changed" email addressed to
        ``guest_xxx@guests.canariasconectada.es``.

        The non-routable domain above already guaranteed no stray notification
        could reach a real inbox, and that still holds; what it could not stop
        was the attempt. Ten of them were sitting in the queue in ``exception``
        state on 2026-08-14 with a single-digit guest population, so at cutover
        volume this is a steady stream of undeliverable mail leaving the
        platform's own SMTP account — bounces to a domain with no MX, charged
        against the sender reputation of every real email the platform sends.

        Only the notification is dropped, and only for guests. The password is
        still rotated, the account is still written, and a real user's account
        still gets every warning core sends.
        """
        recipients = self.filtered(lambda user: not user.is_platform_guest)
        if not recipients:
            return
        return super(ResUsers, recipients)._notify_security_setting_update(
            subject, content, **kwargs
        )

    # ------------------------------------------------------------------
    # Guest lifecycle
    # ------------------------------------------------------------------

    @api.model
    def _create_platform_guest(self):
        """Create a fresh anonymous portal guest and return it (sudo).

        Shape, and why each part matters:

        * **Portal group ONLY.** ``group_ids`` is set to exactly
          ``base.group_portal``. A guest must never carry an internal group;
          ``share`` is a stored compute that turns True precisely because the
          account holds no internal group, so we do not (and cannot cleanly)
          force it -- portal membership *is* what makes it a share user.
        * **``notification_type = 'email'``.** Core enforces
          ``CHECK (notification_type = 'email' OR NOT share)``: a share/portal
          account may never use the Discuss inbox for chatter notifications.
          That is fine here -- Discuss chat rides on channel membership and the
          bus, and web push on the user's push subscription, neither of which
          depends on this field. Any chatter mail aims at the non-routable
          guest domain and dies quietly, by design.
        * **A password at birth.** The account is not left password-less; the
          controller rotates it to a throwaway value on every entry anyway.
        """
        token = secrets.token_urlsafe(8)
        login = "guest_%s@%s" % (token, GUEST_EMAIL_DOMAIN)
        portal = self.env.ref("base.group_portal")
        main_company = self.env.ref("base.main_company")
        user = (
            self.sudo()
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Invitado %s" % token[:6],
                    "login": login,
                    "email": login,
                    "password": secrets.token_urlsafe(24),
                    "company_id": main_company.id,
                    "company_ids": [(6, 0, main_company.ids)],
                    "group_ids": [(6, 0, portal.ids)],
                    "notification_type": "email",
                    "is_platform_guest": True,
                }
            )
        )
        return user

    # ------------------------------------------------------------------
    # Discuss + web push
    # ------------------------------------------------------------------

    @api.model
    def _get_community_channel(self):
        """The shared community channel, created on first need (idempotent).

        Resolution order, first hit wins:

        1. The cached id in ``COMMUNITY_CHANNEL_PARAM`` (fast path, and the
           admin override -- point it at any channel to consolidate).
        2. ``discuss_channel_zone``'s platform-wide channel, if that module is
           installed. Reuse beats a duplicate.
        3. An existing channel with our name.
        4. A freshly created open channel.

        ``group_public_id`` is passed explicitly False on create so the
        ``_compute_group_public_id`` default (which fills ``base.group_user``
        on a falsy value) does not quietly lock portal users and guests out of
        the one channel meant to be open to them.
        """
        channel_model = self.env["discuss.channel"].sudo()
        icp = self.env["ir.config_parameter"].sudo()

        cached = icp.get_param(COMMUNITY_CHANNEL_PARAM)
        channel = channel_model.browse()
        if cached and cached.isdigit():
            channel = channel_model.browse(int(cached)).exists()

        if not channel:
            channel = (
                self.env.ref(ZONE_GENERAL_CHANNEL_XMLID, raise_if_not_found=False)
                or channel_model.browse()
            )

        if not channel:
            channel = channel_model.search(
                [
                    ("name", "=", COMMUNITY_CHANNEL_NAME),
                    ("channel_type", "=", "channel"),
                ],
                limit=1,
            )

        if not channel:
            channel = channel_model.create(
                {
                    "name": COMMUNITY_CHANNEL_NAME,
                    "channel_type": "channel",
                    "group_public_id": False,
                }
            )

        if str(channel.id) != cached:
            icp.set_param(COMMUNITY_CHANNEL_PARAM, str(channel.id))
        return channel

    def _join_community_channel(self):
        """Seat this guest in the community channel; never break login on error.

        Discuss/push wiring is a nicety, not a prerequisite for being logged
        in, so any failure here is logged and swallowed. ``post_joined_message``
        is False: a "channel" posts no join notice anyway, and we want the seat
        to be silent.
        """
        self.ensure_one()
        try:
            channel = self.env["res.users"]._get_community_channel()
            if channel and self.partner_id:
                channel.sudo()._add_members(
                    partners=self.partner_id.sudo(),
                    post_joined_message=False,
                )
        except Exception:  # noqa: BLE001 - best effort, must not block login
            _logger.exception(
                "website_login_branding: guest %s could not join the "
                "community channel",
                self.id,
            )

    # ------------------------------------------------------------------
    # Garbage collection (daily cron)
    # ------------------------------------------------------------------

    @api.model
    def _gc_platform_guests(self):
        """Delete idle, empty guest accounts. Returns the number removed.

        "Idle" is expressed against ``login_date`` the way core does it
        (``login_date >= cutoff`` -> a login inside the window; the field is a
        related over ``log_ids.create_date`` and only that direction has clean
        semantics). Everything NOT in that recent set, and older than the
        window, is a candidate. Each deletion runs inside its own savepoint so
        one undeletable account (a lingering foreign-key reference) cannot roll
        back the whole sweep.
        """
        cutoff = fields.Datetime.now() - timedelta(days=GUEST_STALE_DAYS)
        guests = self.sudo().search([("is_platform_guest", "=", True)])
        if not guests:
            return 0

        recent = self.sudo().search(
            [
                ("is_platform_guest", "=", True),
                ("login_date", ">=", cutoff),
            ]
        )
        stale = guests - recent
        # A guest created moments ago has no log row yet and would look "idle";
        # never delete an account younger than the window.
        stale = stale.filtered(
            lambda user: user.create_date and user.create_date < cutoff
        )

        removed = 0
        for guest in stale:
            if guest._platform_guest_has_data():
                continue
            try:
                with self.env.cr.savepoint():
                    guest.sudo().unlink()
                    removed += 1
            except Exception:  # noqa: BLE001 - skip, keep sweeping
                _logger.exception(
                    "website_login_branding: could not purge guest %s",
                    guest.id,
                )
        _logger.info(
            "website_login_branding: guest GC removed %s of %s stale guests",
            removed,
            len(stale),
        )
        return removed

    def _platform_guest_has_data(self):
        """Whether this guest is worth keeping despite being idle.

        Deliberately conservative and dependency-light: if the Sales app is
        installed and the guest's partner placed any order, the account is not
        disposable. Extend this method (never the cron) as more "meaningful"
        signals appear.
        """
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return False
        if "sale.order" in self.env:
            if (
                self.env["sale.order"]
                .sudo()
                .search_count([("partner_id", "=", partner.id)])
            ):
                return True
        return False

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import secrets
from datetime import timedelta

from odoo import Command, api, fields, models

# The non-routable domain guest logins live under. Imported, not copied: the
# guarantee ("no mail server is authoritative for it, a stray notification can
# never reach a real inbox") is website_login_branding's and there must be ONE
# spelling of it on the platform.
from odoo.addons.website_login_branding.models.res_users import GUEST_EMAIL_DOMAIN

_logger = logging.getLogger(__name__)

# The Discuss client action every community member lands on after login.
DISCUSS_ACTION_XMLID = "mail.action_discuss"

# A community guest is purged once it has been idle this long AND never posted
# a message. Same window as website_login_branding's portal guests: the two
# populations should age out at the same speed.
COMMUNITY_GUEST_STALE_DAYS = 7


class ResUsers(models.Model):
    """Community members: internal users whose whole backend is Discuss.

    Two ways in, one shape out:

    * **Signup on a website** (``/web/signup`` served by any of the platform's
      sites): ``_signup_create_user`` promotes the freshly copied portal
      template user to a community member. Only when the controller flagged the
      request as a website signup and only for UNINVITED signups -- a
      backend-invited portal user stays portal.
    * **The guest button** (``POST /community/guest``):
      ``_create_community_guest`` mints the account directly, mirroring
      ``website_login_branding._create_platform_guest`` but internal instead of
      portal.

    Either way the account holds exactly ``base.group_user`` +
    ``discuss_community.group_community_member`` (the zone-channel gate comes
    along by implication), carries the arrival zone in ``chat_zone`` so
    ``discuss_channel_zone`` seats it in the right channel, and has
    ``mail.action_discuss`` as home action so the backend opens on Discuss.
    """

    _inherit = "res.users"

    is_community_guest = fields.Boolean(
        string="Community Guest",
        default=False,
        copy=False,
        index=True,
        help="Anonymous throwaway account created from the community page's "
        "'Enter as guest' button. Internal (Discuss-only), reused via a "
        "signed cookie and garbage-collected once idle. Never set this "
        "by hand.",
    )

    # ------------------------------------------------------------------
    # The shape of a community member
    # ------------------------------------------------------------------

    @api.model
    def _community_group_ids(self):
        """The exact groups a community member holds, as a list of ids.

        THE single source of truth for the account shape.
        ``base.group_user`` makes the account internal (product decision:
        community members live in the Discuss backend, and this platform is
        Community edition so internal seats carry no licensing cost).
        ``group_community_member`` is the marker every other piece pivots on
        (menu stripping, the auto-subscription carve-out, the guest GC).
        ``discuss_channel_zone.group_zone_channel_member`` is NOT listed:
        it arrives twice by implication (from ``base.group_user`` and from
        ``group_community_member``) and listing implied groups explicitly is
        how group lists rot.
        """
        return [
            self.env.ref("base.group_user").id,
            self.env.ref("discuss_community.group_community_member").id,
        ]

    @api.model
    def _community_home_action(self):
        """The Discuss client action, or an empty recordset if mail moved it.

        Soft ref on purpose: an orphan ``action_id`` renders a blank backend
        (that exact incident is documented at ``zca_platform/hooks.py``, step
        8), so the action is only ever assigned when it demonstrably exists.
        """
        action = self.env.ref(DISCUSS_ACTION_XMLID, raise_if_not_found=False)
        return action if action and action.exists() else self.env["ir.actions.actions"]

    def _promote_to_community_member(self, zone=False):
        """Turn ``self`` (fresh signup users) into community members.

        One write per user, on purpose: ``group_ids`` and ``chat_zone``
        together, so ``discuss_channel_zone``'s write trigger re-seats the
        user exactly once, already with the final groups in place (the
        auto-subscription carve-out in ``discuss_channel.py`` reads the
        CURRENT groups of the user).

        ``zone`` is the commercial zone of the arrival website. It is always
        normalised and always stored -- ``canarias`` included: an explicit
        general-zone value records that arrival WAS resolved, and
        ``_get_chat_zone`` treats it identically to an empty field.

        The company is FORCED back to ``base.main_company``. Not decoration:
        core's ``website`` module sets a signup user's ``company_id`` to the
        serving website's company (``website/models/res_users.py:52-59``), so
        a resident registering on a merchant's microsite would otherwise walk
        away OWNING that merchant's company -- record-rule access to its
        contacts, its documents, its everything. The platform already paid
        for that exact leak once (a zone company stored on the user); the
        arrival zone travels in ``chat_zone`` and NOWHERE else.
        """
        group_ids = self._community_group_ids()
        action = self._community_home_action()
        normalised = self.env["res.company"].sudo()._normalise_zone(zone)
        main_company = self.env.ref("base.main_company")
        for user in self.sudo():
            vals = {
                "group_ids": [Command.set(group_ids)],
                "chat_zone": normalised,
                "company_id": main_company.id,
                "company_ids": [Command.set(main_company.ids)],
            }
            if action:
                vals["action_id"] = action.id
            user.write(vals)
        return self

    # ------------------------------------------------------------------
    # Way in #1: website signup
    # ------------------------------------------------------------------

    @api.model
    def _signup_create_user(self, values):
        """Website signups become community members; everybody else does not.

        The gate is double, and both halves matter:

        * ``community_signup`` in the context -- set ONLY by the signup
          controller override, ONLY when the request is served by a website
          and carries no invitation token. A user created from the backend
          (or through XML-RPC, or by any module calling ``signup()``
          directly) never sees the flag and keeps core's portal default.
        * ``"partner_id" not in values`` -- core puts ``partner_id`` in the
          values precisely when the signup redeems an invitation token
          (``auth_signup/models/res_users.py:72-79``), and an invited user
          was invited AS a portal user. Belt and braces: the controller
          already refuses to flag token signups.
        """
        user = super()._signup_create_user(values)
        if self.env.context.get("community_signup") and "partner_id" not in values:
            user._promote_to_community_member(
                zone=self.env.context.get("community_signup_zone")
            )
        return user

    # ------------------------------------------------------------------
    # Way in #2: the guest button
    # ------------------------------------------------------------------

    @api.model
    def _create_community_guest(self, zone=False):
        """Create a fresh anonymous INTERNAL community guest (sudo).

        The mirror of ``website_login_branding._create_platform_guest`` with
        the one product-decided difference -- the groups. Everything else is
        kept deliberately identical, because every guard there exists for a
        reason that applies here too:

        * **Non-routable login domain.** Same imported constant; the
          ``cguest_`` prefix (vs ``guest_``) keeps the two populations
          distinguishable at a glance in the user list.
        * **``notification_type = 'email'``.** An internal user MAY use the
          Discuss inbox, but a throwaway account must not queue inbox
          notifications nobody will read; any chatter mail aims at the
          non-routable domain and dies quietly, by design.
        * **Platform company only.** ``base.main_company``, never the arrival
          website's company: putting a zone company on a user is exactly the
          multi-company leak the platform already got burned by once. The
          zone travels in ``chat_zone``, nothing else.
        * **A password at birth**, rotated by the controller on every entry.
        """
        token = secrets.token_urlsafe(8)
        login = "cguest_%s@%s" % (token, GUEST_EMAIL_DOMAIN)
        main_company = self.env.ref("base.main_company")
        action = self._community_home_action()
        vals = {
            "name": "Invitado %s" % token[:6],
            "login": login,
            "email": login,
            "password": secrets.token_urlsafe(24),
            "company_id": main_company.id,
            "company_ids": [(6, 0, main_company.ids)],
            "group_ids": [(6, 0, self._community_group_ids())],
            "notification_type": "email",
            "is_community_guest": True,
            "chat_zone": self.env["res.company"].sudo()._normalise_zone(zone),
        }
        if action:
            vals["action_id"] = action.id
        return self.sudo().with_context(no_reset_password=True).create(vals)

    def _notify_security_setting_update(self, subject, content, **kwargs):
        """Never warn a community guest that their password changed.

        Same reasoning, verbatim, as ``website_login_branding``'s override for
        portal guests (see the long docstring there): the controller rotates a
        throwaway password on EVERY entry, and each rotation would otherwise
        queue an undeliverable "Security Update" mail to the non-routable
        guest domain, bouncing against the platform's sender reputation. That
        override filters on ``is_platform_guest`` and therefore does not cover
        this module's guests; this one closes the same hole for
        ``is_community_guest``. The two compose: each strips its own
        population and passes the rest along.
        """
        recipients = self.filtered(lambda user: not user.is_community_guest)
        if not recipients:
            return
        return super(ResUsers, recipients)._notify_security_setting_update(
            subject, content, **kwargs
        )

    # ------------------------------------------------------------------
    # Garbage collection (daily cron)
    # ------------------------------------------------------------------

    @api.model
    def _gc_community_guests(self):
        """Delete idle, silent community guests. Returns the number removed.

        Same sweep as ``website_login_branding._gc_platform_guests`` (idleness
        read from ``login_date`` the way core does it, never delete an account
        younger than the window, one savepoint per deletion so a single
        undeletable row cannot roll back the sweep), over THIS module's
        population and with THIS module's definition of "worth keeping":
        a guest who posted a message is a participant in a conversation, and
        conversations are not ours to amputate.
        """
        cutoff = fields.Datetime.now() - timedelta(days=COMMUNITY_GUEST_STALE_DAYS)
        guests = self.sudo().search([("is_community_guest", "=", True)])
        if not guests:
            return 0

        recent = self.sudo().search(
            [
                ("is_community_guest", "=", True),
                ("login_date", ">=", cutoff),
            ]
        )
        stale = guests - recent
        stale = stale.filtered(
            lambda user: user.create_date and user.create_date < cutoff
        )

        removed = 0
        for guest in stale:
            if guest._community_guest_has_data():
                continue
            try:
                with self.env.cr.savepoint():
                    guest.sudo().unlink()
                    removed += 1
            except Exception:  # noqa: BLE001 - skip, keep sweeping
                _logger.exception(
                    "discuss_community: could not purge guest %s", guest.id
                )
        _logger.info(
            "discuss_community: guest GC removed %s of %s stale guests",
            removed,
            len(stale),
        )
        return removed

    def _community_guest_has_data(self):
        """Whether this guest is worth keeping despite being idle.

        "Has posted a message" is the community equivalent of the branding
        module's "has placed an order": the guest took part in a conversation,
        and deleting the account would orphan the authorship of messages other
        residents can still read. ``message_type = 'comment'`` on purpose --
        notifications and tracking rows are things done TO the account, not
        BY it.
        """
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return False
        return bool(
            self.env["mail.message"]
            .sudo()
            .search_count(
                [
                    ("author_id", "=", partner.id),
                    ("message_type", "=", "comment"),
                ],
                limit=1,
            )
        )

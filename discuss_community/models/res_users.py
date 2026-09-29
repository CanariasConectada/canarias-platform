# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import secrets
from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.tools import SQL

# The non-routable domain guest logins live under. Imported, not copied: the
# guarantee ("no mail server is authoritative for it, a stray notification can
# never reach a real inbox") is website_login_branding's and there must be ONE
# spelling of it on the platform.
from odoo.addons.website_login_branding.models.res_users import GUEST_EMAIL_DOMAIN

_logger = logging.getLogger(__name__)

# The Discuss client action every community member lands on after login.
DISCUSS_ACTION_XMLID = "mail.action_discuss"

# A community guest is removed once it has been inactive this long (owner
# decision of 2026-09-29: "guests only exist while they have no more than one
# week of inactivity"). The system parameter overrides the default.
COMMUNITY_GUEST_STALE_DAYS = 7
GUEST_INACTIVITY_DAYS_PARAM = "discuss_community.guest_inactivity_days"
# At most this many guests are removed per cron run; the cron is looped by
# the ``ir.cron`` progress API while more remain.
COMMUNITY_GUEST_CLEANUP_BATCH = 200
GUEST_CLEANUP_BATCH_PARAM = "discuss_community.guest_cleanup_batch_size"

# The staff channels ``mail`` seeds: "general" (every employee) and
# "Administrators". A community guest is internal, so core would let it read
# and join the first; the guest record rules and the guest cleanup keep it out
# of both.
STAFF_CHANNEL_XMLIDS = ("mail.channel_all_employees", "mail.channel_admin")

# The one channel a community guest opens on after login.
COMMUNITY_DEFAULT_CHANNEL_XMLID = "discuss_channel_zone.channel_canarias"


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

    community_hidden_channel_ids = fields.Many2many(
        comodel_name="discuss.channel",
        string="Hidden Staff Channels",
        compute="_compute_community_hidden_channel_ids",
        help="Staff channels a community guest may never read or join, even "
        "when seated there by mistake. Read by the guest channel record "
        "rules; empty for everybody who is not a community guest.",
    )

    # Both computed channel lists below feed ``ir.rule`` domains, and
    # ``ir.rule._compute_domain`` is ormcached per uid. They must only depend
    # on things that never change for a given user (``is_community_guest``,
    # which ``write`` guards with a registry cache clear, and channels
    # resolved by xmlid). Never make them depend on mutable per-user state
    # (zone, memberships, groups) without clearing the registry cache on
    # every change of it, or the rules keep applying stale ids.
    community_channel_ids = fields.Many2many(
        comodel_name="discuss.channel",
        string="Joinable Community Channels",
        compute="_compute_community_channel_ids",
        help="Community channels a community guest may see and join or leave "
        "at will: the platform-wide channel and the neighbourhood channels. "
        "Read by the guest channel record rules; empty for everybody who is "
        "not a community guest.",
    )

    @api.depends("is_community_guest")
    def _compute_community_channel_ids(self):
        """The four community channels, for guests only.

        The neighbourhood channels are gated on
        ``discuss_channel_zone.group_zone_channel_member``, so the "open
        channels" branch of the guest rules does not cover them; this list
        does. Non-stored for the same reason as the hidden staff channels.
        """
        channels = (
            self.env["discuss.channel"]
            .sudo()
            .browse(sorted(self.env["discuss.channel"]._community_channel_ids()))
        )
        for user in self:
            user.community_channel_ids = (
                channels if user.is_community_guest else self.env["discuss.channel"]
            )

    @api.depends("is_community_guest")
    def _compute_community_hidden_channel_ids(self):
        """The staff channels, for guests only; nothing for anybody else.

        Non-stored on purpose: the record rules read it once per user and the
        rule domain is then cached (``ir.rule._compute_domain``), so the only
        thing that matters is that the ids are stable -- and they are: they
        are the two channels ``mail`` seeds, resolved by xmlid.
        """
        hidden = self._community_staff_channels()
        for user in self:
            user.community_hidden_channel_ids = (
                hidden if user.is_community_guest else self.env["discuss.channel"]
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
            # Never onboarded by OdooBot: a throwaway resident account has no
            # use for a tour of the employee chat features.
            "odoobot_state": "disabled",
            "chat_zone": self.env["res.company"].sudo()._normalise_zone(zone),
        }
        if action:
            vals["action_id"] = action.id
        return self.sudo().with_context(no_reset_password=True).create(vals)

    def write(self, vals):
        """Drop the cached record-rule domains when a user changes population.

        The guest record rules branch on ``user.is_community_guest`` and
        ``ir.rule._compute_domain`` caches the evaluated domain per user, so
        flipping the flag on an existing account would otherwise keep
        applying the old rules until the next restart.
        """
        result = super().write(vals)
        if "is_community_guest" in vals:
            self.env.registry.clear_cache()
        return result

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
    # Community channels: seated on arrival, then the guest's own choice
    # ------------------------------------------------------------------

    def _zone_self_managed_users(self):
        """Community guests choose their channels after the first seat.

        ``discuss_channel_zone`` seats them in the general channel and in the
        channel of their zone when they are created (or when their zone
        changes) and never unseats them afterwards, so they can join and leave
        each community channel from the Channels view.
        """
        return super()._zone_self_managed_users() | self.filtered("is_community_guest")

    def _community_guest_adopt_zone(self, zone):
        """Give a guest with no neighbourhood the one of ``zone``.

        Called on every entry through the guest door. Only a real
        neighbourhood is adopted, and only by a guest that has none yet
        (empty or the platform-wide ``canarias``): a guest's zone is never
        moved from one neighbourhood to another behind its back.
        """
        general = "canarias"
        normalised = self.env["res.company"].sudo()._normalise_zone(zone)
        if normalised == general:
            return self.browse()
        guests = self.filtered(
            lambda user: user.is_community_guest
            and (user.chat_zone or general) == general
        )
        if guests:
            guests.sudo().write({"chat_zone": normalised})
        return guests

    @api.model
    def _seat_community_guests(self):
        """Seat every active guest in its community channels. Idempotent.

        Adds the general channel and the guest's zone channel when missing,
        and nothing else (guests are self-managed: nothing is removed). Run
        once by the 19.0.1.7.0 migration for the guests created while the
        zone of a zone site was not detected.
        """
        guests = self.sudo().search([("is_community_guest", "=", True)])
        counters = guests._sync_zone_channels()
        _logger.info(
            "discuss_community: seated %s guests, %s seats added",
            len(guests),
            counters["added"],
        )
        return counters

    # ------------------------------------------------------------------
    # The guest profile: no OdooBot, no staff channels
    # ------------------------------------------------------------------

    def _on_webclient_bootstrap(self):
        """Keep OdooBot away from community guests.

        ``mail_bot`` opens a DM with OdooBot on the first backend load of any
        internal user whose ``odoobot_state`` is still unset
        (``mail_bot/models/res_users.py``). New guests are born ``disabled``;
        this covers guests created before that, or by any other path, by
        disabling the bot BEFORE the core hook decides.
        """
        if self.is_community_guest and self.odoobot_state in (
            False,
            "not_initialized",
        ):
            self.sudo().odoobot_state = "disabled"
        return super()._on_webclient_bootstrap()

    @api.model
    def _community_staff_channels(self):
        """The staff channels ``mail`` seeds that are installed, as a recordset."""
        channels = self.env["discuss.channel"]
        for xmlid in STAFF_CHANNEL_XMLIDS:
            channel = self.env.ref(xmlid, raise_if_not_found=False)
            if channel:
                channels |= channel
        return channels

    @api.model
    def _community_default_channel(self):
        """The channel a community guest opens on, or an empty recordset."""
        channel = self.env.ref(
            COMMUNITY_DEFAULT_CHANNEL_XMLID, raise_if_not_found=False
        )
        return channel.sudo() if channel else self.env["discuss.channel"]

    @api.model
    def _cleanup_community_guests(self):
        """Bring existing guests to the guest profile. Returns counters.

        Idempotent, and run by the module migration: the create path and the
        auto-subscription carve-out already keep NEW guests clean, this fixes
        the ones seated before they existed.

        * **Staff channels.** Memberships in "general" and "Administrators"
          are removed (plain ``unlink``, silent: core posts no leave notice on
          a ``channel``).
        * **OdooBot.** The guest leaves its DM with OdooBot (its member row is
          removed, the conversation itself is kept for OdooBot's side) and the
          bot is disabled so the DM is never re-created.
        """
        guests = (
            self.sudo()
            .with_context(active_test=False)
            .search([("is_community_guest", "=", True)])
        )
        counters = {"staff_seats": 0, "odoobot_chats": 0, "odoobot_disabled": 0}
        if not guests:
            return counters
        member_model = self.env["discuss.channel.member"].sudo()
        staff_channels = self.sudo()._community_staff_channels()
        if staff_channels:
            staff_seats = member_model.search(
                [
                    ("channel_id", "in", staff_channels.ids),
                    ("partner_id", "in", guests.partner_id.ids),
                ]
            )
            counters["staff_seats"] = len(staff_seats)
            staff_seats.unlink()

        odoobot = self.env.ref("base.partner_root", raise_if_not_found=False)
        if odoobot:
            bot_chats = member_model.search(
                [
                    ("channel_id.channel_type", "=", "chat"),
                    ("partner_id", "=", odoobot.id),
                ]
            ).channel_id
            guest_seats = member_model.search(
                [
                    ("channel_id", "in", bot_chats.ids),
                    ("partner_id", "in", guests.partner_id.ids),
                ]
            )
            counters["odoobot_chats"] = len(guest_seats)
            guest_seats.unlink()

        to_disable = guests.filtered(lambda user: user.odoobot_state != "disabled")
        counters["odoobot_disabled"] = len(to_disable)
        if to_disable:
            to_disable.write({"odoobot_state": "disabled"})
        _logger.info(
            "discuss_community: guest cleanup removed %(staff_seats)s staff "
            "seats and %(odoobot_chats)s OdooBot chats, disabled OdooBot for "
            "%(odoobot_disabled)s guests",
            counters,
        )
        return counters

    # ------------------------------------------------------------------
    # Garbage collection (daily cron)
    # ------------------------------------------------------------------

    @api.model
    def _community_positive_int_param(self, key, default):
        """A positive integer system parameter, ``default`` when it is not."""
        raw = self.env["ir.config_parameter"].sudo().get_param(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        return value if value > 0 else default

    @api.model
    def _community_guest_inactivity_days(self):
        """The inactivity window in days, from the system parameter.

        ``discuss_community.guest_inactivity_days``; the default (7) when the
        parameter is missing or not a positive integer, so a typo can never
        turn the sweep into "remove every guest now".
        """
        return self._community_positive_int_param(
            GUEST_INACTIVITY_DAYS_PARAM, COMMUNITY_GUEST_STALE_DAYS
        )

    def _community_guest_last_activity(self):
        """``{user_id: datetime}``: the last sign of life of each user.

        The latest of the last login (``res.users.log``), the last message
        authored, the last presence (``mail.presence`` poll or activity) and
        the account creation, so an account younger than the window is never
        seen as inactive.
        """
        if not self:
            return {}
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                """
                SELECT u.id,
                       GREATEST(u.create_date, l.last_login, m.last_message,
                                p.last_poll, p.last_presence)
                  FROM res_users u
             LEFT JOIN (SELECT create_uid, MAX(create_date) AS last_login
                          FROM res_users_log
                         WHERE create_uid = ANY(%(user_ids)s)
                      GROUP BY create_uid) l ON l.create_uid = u.id
             LEFT JOIN (SELECT author_id, MAX(date) AS last_message
                          FROM mail_message
                         WHERE author_id = ANY(%(partner_ids)s)
                      GROUP BY author_id) m ON m.author_id = u.partner_id
             LEFT JOIN mail_presence p ON p.user_id = u.id
                 WHERE u.id = ANY(%(user_ids)s)
                """,
                user_ids=self.ids,
                partner_ids=self.partner_id.ids,
            )
        )
        return dict(self.env.cr.fetchall())

    @api.model
    def _gc_community_guests(self):
        """Remove the community guests inactive for longer than the window.

        Only ``is_community_guest`` accounts, and only active ones (an
        archived guest was already handled, which keeps the sweep
        idempotent). For each one, in its own savepoint so one failure never
        rolls back the sweep:

        * its channel memberships and push devices are deleted;
        * the user is deleted, or archived when the delete fails (a foreign
          key somewhere);
        * its partner is deleted when nothing else needs it, and ARCHIVED when
          it authored messages (they stay readable, author included) or when
          the delete fails.

        Returns the counters it logs.
        """
        counters = dict.fromkeys(
            (
                "users_removed",
                "users_archived",
                "partners_removed",
                "partners_archived",
                "memberships",
                "devices",
            ),
            0,
        )
        days = self._community_guest_inactivity_days()
        cutoff = fields.Datetime.now() - timedelta(days=days)
        guests = self.sudo().search([("is_community_guest", "=", True)])
        last_activity = guests._community_guest_last_activity()
        stale = guests.filtered(
            lambda user: (last_activity.get(user.id) or user.create_date) < cutoff
        ).sorted("id")
        batch_size = self._community_positive_int_param(
            GUEST_CLEANUP_BATCH_PARAM, COMMUNITY_GUEST_CLEANUP_BATCH
        )
        batch = stale[:batch_size]
        processed = 0
        for guest in batch:
            try:
                with self.env.cr.savepoint():
                    guest._community_guest_remove(counters)
                    processed += 1
            except Exception:  # noqa: BLE001 - skip, keep sweeping
                _logger.exception(
                    "discuss_community: could not remove guest %s", guest.id
                )
        counters["remaining"] = len(stale) - len(batch)
        _logger.info(
            "discuss_community: guest cleanup (%(days)s days inactive): "
            "%(batch)s of %(stale)s stale guests (%(guests)s guests) this run, "
            "%(remaining)s left; users removed %(users_removed)s, archived "
            "%(users_archived)s; partners removed %(partners_removed)s, "
            "archived %(partners_archived)s; %(memberships)s memberships and "
            "%(devices)s push devices deleted",
            dict(
                counters,
                days=days,
                batch=len(batch),
                stale=len(stale),
                guests=len(guests),
            ),
        )
        if self.env.context.get("cron_id"):
            # Commits this batch; with ``remaining`` > 0 the cron runner loops
            # the job again (and stops if a run processes nothing, so guests
            # that cannot be removed never make it spin).
            self.env["ir.cron"]._commit_progress(
                processed, remaining=counters["remaining"]
            )
        return counters

    def _community_guest_remove(self, counters):
        """Remove one inactive guest (see ``_gc_community_guests``)."""
        self.ensure_one()
        if not self.is_community_guest:  # never anybody else, whatever called
            return
        guest = self.sudo()
        partner = guest.partner_id
        members = (
            self.env["discuss.channel.member"]
            .sudo()
            .search([("partner_id", "=", partner.id)])
        )
        counters["memberships"] += len(members)
        members.unlink()
        devices = (
            self.env["mail.push.device"]
            .sudo()
            .search([("partner_id", "=", partner.id)])
        )
        counters["devices"] += len(devices)
        devices.unlink()

        user_removed = False
        try:
            with self.env.cr.savepoint():
                guest.unlink()
                user_removed = True
        except Exception:  # noqa: BLE001 - archive instead
            _logger.info(
                "discuss_community: guest %s cannot be deleted, archiving it",
                guest.id,
            )
        if user_removed:
            counters["users_removed"] += 1
        else:
            guest.write({"active": False})
            counters["users_archived"] += 1

        partner = partner.with_context(active_test=False).exists()
        if not partner or (partner.user_ids - guest):
            return
        has_messages = bool(
            self.env["mail.message"]
            .sudo()
            .search_count([("author_id", "=", partner.id)], limit=1)
        )
        if user_removed and not has_messages:
            try:
                with self.env.cr.savepoint():
                    partner.unlink()
                    counters["partners_removed"] += 1
                    return
            except Exception:  # noqa: BLE001 - archive instead
                _logger.info(
                    "discuss_community: partner %s of guest %s cannot be "
                    "deleted, archiving it",
                    partner.id,
                    self.id,
                )
        if partner.active:
            partner.write({"active": False})
        counters["partners_archived"] += 1

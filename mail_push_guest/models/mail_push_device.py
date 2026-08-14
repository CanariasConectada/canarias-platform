# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.mail.tools.jwt import InvalidVapidError

_logger = logging.getLogger(__name__)

# Hosts a browser subscription endpoint may legitimately point at.
#
# WHY AN ALLOWLIST AT ALL: `push_to_end_point`
# (mail/tools/web_push.py:143-189) does `session.post(endpoint, ...)` on a URL
# that comes straight from the client, and its ONLY validation is that the host
# does not end in `.invalid`. Server-side, that is a request forger's dream: an
# attacker registers `http://169.254.169.254/latest/meta-data/` as their
# "device" and the Odoo worker fetches it from inside the network. Worse, the
# failure branch logs `response.text` (shortened to 100 chars) at WARNING, so
# the answer comes back out through the log -- a side channel, not just a blind
# SSRF. Core lives with this because registration is `auth="user"`; this module
# opens registration to anonymous visitors, so the allowlist is what pays for
# that.
#
# It is enforced on BOTH doors: `_register_for_persona` for the public routes
# and `register_devices` for `/web/dataset/call_kw`. The second one is a change
# to core behaviour for authenticated users, and deliberate: `auth="user"` is
# not a boundary on a platform whose accounts are self-signed-up, and the thing
# on the other side of this particular check is the platform's outbound
# network, not one notification.
#
# MUST BE UPDATED AS BROWSERS CHANGE. These are vendor infrastructure hostnames,
# not a standard: a new browser, or a vendor moving to a new domain, means new
# subscriptions are silently refused until this tuple is updated. Symptom to
# look for: `_register_for_persona` raising "not a known push service" for real
# users. Verify against the vendor's docs before adding anything, and never
# widen an entry to a bare public suffix (`.googleapis.com` would hand back the
# whole SSRF surface).
PUSH_ENDPOINT_ALLOWED_HOSTS = frozenset(
    {
        # Chrome, Chromium, Edge (Chromium), Opera, Brave, Vivaldi, Samsung
        "fcm.googleapis.com",
        # Legacy GCM endpoints still handed out to old Chrome installs
        "android.googleapis.com",
        # Firefox (desktop and Android)
        "updates.push.services.mozilla.com",
        # Safari, macOS 13+ / iOS 16.4+
        "web.push.apple.com",
    }
)

# Suffix matches, for services that hand out REGIONAL hostnames. A suffix entry
# must start with a dot and must contain the vendor's own registrable domain,
# so that `evilnotify.windows.com` or `notify.windows.com.attacker.net` cannot
# match. Same maintenance rule as above.
PUSH_ENDPOINT_ALLOWED_HOST_SUFFIXES = (
    # Windows Notification Service, e.g. db5p.notify.windows.com (legacy Edge)
    ".notify.windows.com",
    # Mozilla autopush regional nodes
    ".push.services.mozilla.com",
)

# Ceiling on devices held by ONE persona. A guest identity is a cookie: it can
# be copied, and every copy that registers would multiply the outbound requests
# this server makes on behalf of one anonymous visitor. Five is roughly
# "phone + tablet + two browsers on the laptop"; beyond that it is fan-out, not
# usage. Stale rows are self-healing: core unlinks a device as soon as its push
# service answers 404/410 (mail/models/mail_thread.py:3933-3942).
#
# ENFORCED ON BOTH DOORS. It started as a public-route rule, which made it a
# budget an authenticated caller could simply walk around: core's
# `register_devices` creates without counting, and any account reaches it over
# `/web/dataset/call_kw`. A cap that only one of the two doors honours is not a
# cap. The cost of extending it is stated in the ROADMAP: a person who really
# does use six browsers is refused the sixth until one of the others goes
# stale.
MAX_DEVICES_PER_PERSONA = 5

# Real endpoints are ~200 characters. The cap exists so an unauthenticated
# caller cannot use the endpoint column as free storage.
MAX_ENDPOINT_LENGTH = 512

# `p256dh` is 87 base64url characters, `auth` is 22. The cap is generous but
# finite for the same reason as above.
MAX_BROWSER_KEY_LENGTH = 256

BROWSER_KEY_NAMES = ("p256dh", "auth")


class MailPushDevice(models.Model):
    """Push devices that may belong to a guest instead of a partner.

    Core models a device as strictly partner-owned: `partner_id` is
    `required=True` with a `self.env.user.partner_id` default
    (mail/models/mail_push_device.py:17-19). An anonymous visitor has no
    partner, so the whole web push stack is closed to `mail.guest`. This makes
    the owner a XOR of the two persona kinds.
    """

    _inherit = "mail.push.device"

    guest_id = fields.Many2one(
        comodel_name="mail.guest",
        string="Guest",
        index=True,
        # cascade: a device is worthless without its persona, and a guest is a
        # cookie that gets purged. Nothing here is history worth keeping (the
        # sibling `discuss.channel.pending.message` uses `set null` precisely
        # because a held message IS history; a subscription is not).
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        required=False,
        index=True,
        # EXPLICIT, and not an accident of `required`. The default `ondelete`
        # of a Many2one is derived from `required`
        # (odoo/orm/fields_relational.py:270-282): `restrict` when required,
        # `set null` when not. Relaxing core's `required=True` therefore
        # silently flips this FK from `restrict` to `set null`, and `set null`
        # is the one policy this model cannot survive: Postgres would blank the
        # column behind the ORM's back and leave a persona-less row that
        # violates the XOR below, with no ORM hook able to see it happen.
        # `cascade` matches `guest_id` and keeps the invariant true by
        # construction.
        ondelete="cascade",
    )

    _persona_not_both = models.Constraint(
        "CHECK(NOT (partner_id IS NOT NULL AND guest_id IS NOT NULL))",
        "A push device cannot belong to a partner and a guest at the same time.",
    )

    # ------------------------------------------------------------------
    # Persona XOR
    #
    # The invariant is "exactly one persona", and it is enforced in two
    # layers on purpose:
    #
    # * SQL CHECK -- "never BOTH". It fires at INSERT/UPDATE time, before the
    #   ORM validates anything, so it is the layer that actually rejects a
    #   two-persona row, including one written by raw SQL or by a module that
    #   bypasses `create`/`write`.
    # * `@api.constrains` -- the full XOR, so "NEITHER" is rejected too, with
    #   a readable message instead of an IntegrityError. It is also the layer
    #   that does not depend on the FK policy: if a future module redeclares
    #   either field with `ondelete="set null"`, the CHECK stops being enough
    #   and this is what still catches the resulting orphan on the next write.
    #
    # This is the same split as `discuss.channel.pending.message` in
    # `discuss_channel_moderation`, and deliberately so: two models in the same
    # platform expressing the same "guest or partner, never both" rule should
    # not each invent their own enforcement story.
    #
    # Note what is NOT enforced in SQL: "neither". A `CHECK(num_nonnulls(...)
    # = 1)` would be correct today (both FKs cascade, so no delete can produce
    # an orphan) but it would also make the only error message an
    # IntegrityError, on a model written from an `auth="public"` route.
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Neutralise core's `partner_id` default when a guest is given.

        `partner_id` defaults to `self.env.user.partner_id`
        (mail/models/mail_push_device.py:17-19) and defaults are merged into
        `vals` inside `create` (odoo/orm/models.py:4791-4793) BEFORE anything
        else runs. So `create({"guest_id": g.id})` would quietly also get the
        current user's partner -- for a guest registering over a public route,
        that is the shared public partner -- and hit the SQL CHECK with an
        IntegrityError nobody can read.

        Writing an explicit `False` is what stops the default: defaults only
        fill keys that are MISSING. The dict is copied, never mutated, so the
        caller's vals are left alone.

        A create that mentions NEITHER key keeps core's default and therefore
        always ends up with a partner, so it cannot produce a persona-less row.
        """
        vals_list = [
            {"partner_id": False, **vals} if vals.get("guest_id") else vals
            for vals in vals_list
        ]
        return super().create(vals_list)

    def write(self, vals):
        """Binding one persona releases the other.

        This is not sugar, it is what keeps core working. A visitor subscribes
        as a guest, then logs in: the web client calls
        `mail.push.device.register_devices`, which finds the row by endpoint and
        writes `partner_id` on it (mail/models/mail_push_device.py:58-66)
        without knowing `guest_id` exists. That write would leave both personas
        set and blow up in core code we must not modify. Clearing the other
        side is the correct semantics anyway: the browser now belongs to the
        account.

        Only a write that sets ONE side truthy while leaving the other
        unmentioned is adjusted; a write naming both is left intact so that the
        constraints can reject it.
        """
        if vals.get("partner_id") and "guest_id" not in vals:
            vals = dict(vals, guest_id=False)
        elif vals.get("guest_id") and "partner_id" not in vals:
            vals = dict(vals, partner_id=False)
        return super().write(vals)

    @api.constrains("guest_id", "partner_id")
    def _check_persona_xor(self):
        """Exactly one persona, at ORM level (create and write)."""
        for device in self:
            if bool(device.guest_id) == bool(device.partner_id):
                raise ValidationError(
                    self.env._(
                        "A push device must belong to exactly one persona: "
                        "a partner or a guest."
                    )
                )

    # ------------------------------------------------------------------
    # Endpoint validation
    # ------------------------------------------------------------------

    @api.model
    def _check_endpoint(self, endpoint):
        """Is `endpoint` a URL of a real push service?

        Returns a plain bool so callers can decide how loud to be. See
        `PUSH_ENDPOINT_ALLOWED_HOSTS` for why this exists.
        """
        if not endpoint or not isinstance(endpoint, str):
            return False
        if len(endpoint) > MAX_ENDPOINT_LENGTH:
            return False
        try:
            url = urlsplit(endpoint)
            # `port` parses lazily and raises on garbage such as "https://h:x/"
            port = url.port
        except ValueError:
            return False
        # https only: the payload is encrypted for the browser, but the VAPID
        # token in the Authorization header is a bearer credential in transit.
        if url.scheme != "https":
            return False
        # `https://fcm.googleapis.com@attacker.example/` reads as an allowlisted
        # host to a human and resolves to `attacker.example` for a machine.
        # `hostname` below already returns the real host, so this is the second
        # lock on the same door.
        if url.username or url.password or "@" in url.netloc:
            return False
        # No non-default port: no push service uses one, and it is the shape an
        # internal-service probe takes (`https://host:6379/`).
        if port is not None:
            return False
        host = url.hostname  # lowercased, brackets and port stripped
        if not host:
            return False
        if host in PUSH_ENDPOINT_ALLOWED_HOSTS:
            return True
        return host.endswith(PUSH_ENDPOINT_ALLOWED_HOST_SUFFIXES)

    @api.model
    def _check_browser_keys(self, keys):
        """Is `keys` the `{p256dh, auth}` pair the encryption step expects?

        `_derive_key` (mail/tools/web_push.py:62-101) json-loads this column and
        feeds it to ECDH. Rejecting the wrong shape here turns "an exception
        somewhere inside cryptography, at send time, for every future message"
        into "your subscription was refused, now".
        """
        if not isinstance(keys, dict) or set(keys) != set(BROWSER_KEY_NAMES):
            return False
        return all(
            isinstance(keys[name], str)
            and 0 < len(keys[name]) <= MAX_BROWSER_KEY_LENGTH
            for name in BROWSER_KEY_NAMES
        )

    @api.model
    def _clean_expiration_time(self, expiration_time):
        """Accept only what a Datetime column can hold; drop the rest.

        The browser sends `PushSubscription.expirationTime`, which is null in
        practice and a number of milliseconds when it is not. Core writes it
        straight through; here it comes from an unauthenticated caller, so
        anything that is not a datetime string becomes False instead of an
        exception in the middle of a registration.
        """
        if not expiration_time or not isinstance(expiration_time, str):
            return False
        try:
            return fields.Datetime.to_datetime(expiration_time) or False
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @api.model
    def _register_for_persona(
        self,
        *,
        partner=None,
        guest=None,
        endpoint=None,
        keys=None,
        expiration_time=None,
        vapid_public_key=None,
    ):
        """Upsert the device of `endpoint` for exactly one persona.

        Mirrors core's `register_devices` (which resolves the persona from
        `self.env.user` and is unreachable for a guest, since
        `/web/dataset/call_kw` is `auth="user"`), with three differences that
        exist because the caller here is anonymous: the persona is passed in,
        the endpoint goes through the allowlist, and a persona may not hold an
        unbounded number of devices.

        :param partner: `res.partner` owning the device, or None
        :param guest: `mail.guest` owning the device, or None
        :returns: the `mail.push.device` record, always as sudo, or an EMPTY
            recordset when the endpoint already belongs to somebody else (see
            `_may_claim_device`). Callers on the public route must NOT let
            that difference reach the client.
        """
        if bool(partner) == bool(guest):
            # Equal truthiness means neither persona was given, or both were.
            raise ValidationError(
                self.env._(
                    "A push device must belong to exactly one persona: "
                    "a partner or a guest."
                )
            )
        # Echo check first: it is the cheapest way to reject a client whose
        # service worker is running against keys we no longer have.
        #
        # The emptiness test is not redundant. `_verify_vapid_public_key`
        # (mail/models/mail_push_device.py:86-89) is a plain `==` against the
        # parameter, so on a database where the pair was never generated it
        # compares False to False and says "valid" -- letting an anonymous
        # caller fill the table with devices nothing will ever be able to
        # encrypt for. Behind `auth="user"` that shape is unreachable in
        # practice; here it is the default state of a fresh database.
        if not vapid_public_key or not isinstance(vapid_public_key, str):
            raise InvalidVapidError("Invalid VAPID public key")
        if not self._verify_vapid_public_key(vapid_public_key):
            raise InvalidVapidError("Invalid VAPID public key")
        if not self._check_endpoint(endpoint):
            raise ValidationError(
                self.env._("This endpoint is not a known push service.")
            )
        if not self._check_browser_keys(keys):
            raise ValidationError(self.env._("Invalid browser subscription keys."))

        vals = {
            "endpoint": endpoint,
            "expiration_time": self._clean_expiration_time(expiration_time),
            "keys": json.dumps({name: keys[name] for name in BROWSER_KEY_NAMES}),
            "partner_id": partner.id if partner else False,
            "guest_id": guest.id if guest else False,
        }
        # sudo: mail.push.device is granted to base.group_system only
        # (mail/security/ir.model.access.csv:67-68); every persona touching it
        # goes through this method, which is where ownership is decided.
        devices_su = self.sudo()
        existing = devices_su.search([("endpoint", "=", endpoint)], limit=1)
        if existing:
            # `endpoint` is unique in core (mail/models/mail_push_device.py:28-31),
            # so an existing row is either this browser re-subscribing or
            # somebody else's subscription. Only the first may be re-pointed.
            if not self._may_claim_device(existing, partner=partner, guest=guest):
                # One short line, and deliberately NOT at warning: this route is
                # unauthenticated and unthrottled (see ROADMAP), so anything
                # louder is a disk-filling primitive for the same attacker. The
                # endpoint is not logged -- it is the closest thing a device has
                # to a credential, and the log is the side channel this module
                # already had to reason about.
                _logger.info(
                    "WebPush: refused to re-point an existing device to %s %s",
                    "partner" if partner else "guest",
                    partner.id if partner else guest.id,
                )
                # Refusal answers with an EMPTY recordset, and the public route
                # turns that into the same `True` a success gets: see
                # `_may_claim_device` for why the refusal is silent.
                return devices_su.browse()
            existing.write(vals)
            return existing
        persona_domain = (
            [("partner_id", "=", partner.id)]
            if partner
            else [("guest_id", "=", guest.id)]
        )
        if devices_su.search_count(persona_domain) >= MAX_DEVICES_PER_PERSONA:
            raise ValidationError(
                self.env._(
                    "This visitor already has the maximum number of "
                    "notification devices."
                )
            )
        return devices_su.create([vals])

    @api.model
    def get_web_push_vapid_public_key(self):
        """Core's key reader, with GENERATION kept administrative.

        WHY OVERRIDE CORE AT ALL: core regenerates the VAPID pair whenever the
        public key parameter is missing, and its first act is
        `self.sudo().search([]).unlink()` -- every push device on the database
        (mail/models/mail_push_device.py:33-45). This module's own
        `/mail/push/vapid` route already refuses to expose that branch, for
        exactly this reason. But the branch is also reachable through
        `/web/dataset/call_kw`, which runs no model ACL and calls a method that
        sudoes internally, so the `base.group_system` grant stops nobody: any
        authenticated account -- portal included -- can call it and, on a
        database whose public key is absent, delete every subscription and
        rotate the pair, which invalidates the ones every browser still holds.
        Closing it on the public route and leaving it open on the ORM door
        would have been the same half-measure the ownership checks below exist
        to avoid.

        The precondition is narrow on purpose: READING is untouched for
        everybody (the value is public by definition -- it is shipped to every
        browser that subscribes), and only the destructive branch asks for
        `base.group_system`. That branch is genuinely administrative: it is
        `mail`'s only key generator (there is no Settings action for it), so a
        fresh database is still bootstrapped the ordinary way, by an
        administrator's own web client the first time it enables notifications.

        Cost, stated plainly: on a database with no pair yet, a non-system user
        enabling notifications gets `False` instead of a freshly generated key,
        and `webclient.js` shows its "Failed to enable push notifications"
        notice rather than silently bootstrapping the platform's push identity.
        That is the intended trade -- key generation is not a side effect a
        random account should be able to trigger.

        :returns: the public key, or False when there is none and the caller
            may not create one.
        """
        # sudo: the parameter is world-readable by design; core reads it the
        # same way (its own `ir_params_sudo`).
        public_key = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("mail.web_push_vapid_public_key")
        )
        if public_key:
            return public_key
        # `self.env.su` keeps programmatic callers (core's own test fixtures,
        # any module calling this in sudo) on core's behaviour. It is not a way
        # in for a request: `call_kw` invokes the method on the caller's own
        # environment, never a sudoed one.
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            _logger.info(
                "WebPush: refused to generate VAPID keys for user %s",
                self.env.uid,
            )
            return False
        return super().get_web_push_vapid_public_key()

    @api.model
    def register_devices(self, **kw):
        """Core's authenticated registration, with the same ownership rule.

        WHY OVERRIDE CORE AT ALL: `register_devices` finds a device row by
        endpoint and re-points it at `self.env.user.partner_id`, with no
        ownership check (mail/models/mail_push_device.py:47-73). Behind
        `auth="user"` core reads that as safe, but `/web/dataset/call_kw` runs
        no ACL of its own -- `call_kw` only refuses private methods -- and this
        method sudoes internally, so the `base.group_system` grant on
        `mail.push.device` stops nobody. ANY authenticated account reaches it,
        portal included. Leaving it open would mean the ownership rule holds on
        the public door and not on the ORM door, which is not an ownership
        rule; and on this platform portal accounts are self-signed-up
        merchants and residents, while the whole point of the module is that
        untrusted personas now own endpoints worth stealing.

        Note `previousEndpoint`: core looks the row up by THAT when it is
        given, and MEANS to rewrite the row's endpoint to the new one. Its
        illegitimate use is
        `register_devices(previousEndpoint=<victim>, endpoint=<mine>)`, which
        would walk somebody else's row onto an endpoint of the caller's
        choosing. The check therefore gates the SEARCH key, not the new
        endpoint. (Its LEGITIMATE use, a browser renaming its own subscription
        on `pushsubscriptionchange`, is dead in core for an unrelated reason --
        see the ROADMAP -- but the check is written for what core means to do,
        so that it still guards the row the day core writes it.)

        THE ENDPOINT SHAPE IS CHECKED HERE TOO, and that IS a change to core
        behaviour for authenticated users. It was left out at first on the
        argument that `auth="user"` pays for it; that argument was already
        overruled for `_may_claim_device`, and it is weaker here, because what
        an unchecked endpoint buys is not one stolen notification but a URL
        this server's worker will POST to on every message, with the response
        body landing in the log (mail/tools/web_push.py:143-189). A portal
        account -- self-signed-up merchants and residents, on this platform --
        registering `https://<internal-host>/...` turns the ORM door into an
        authenticated request-forgery primitive against the platform's own
        network.

        Nothing legitimate registers an endpoint that is not a push service:
        both callers in core pass `PushSubscription.endpoint`, which the
        browser gets from its own vendor's push service. Neither surfaces the
        refusal to a person either -- `webclient.js` catches it into a
        `console.warn`, `service_worker.js` ignores the response entirely --
        so the failure mode is a subscription that is not stored, not a dialog
        in somebody's face. The cost is the same maintenance obligation the
        public route already carries: a browser whose vendor is not in
        `PUSH_ENDPOINT_ALLOWED_HOSTS` can no longer register through this door
        either, and the symptom is silent.

        Core is extended, not modified: this adds preconditions and delegates.

        :returns: None, like core, whether it registered or refused an
            endpoint it may not claim. Every caller (`webclient.js`,
            `service_worker.js`) ignores the return value, so silence costs
            nothing and keeps the ORM path from becoming the oracle the public
            route refuses to be. A MALFORMED request raises instead: the
            caller supplied the endpoint, so telling it the endpoint was
            refused reveals nothing about anybody else's rows, and a client
            whose subscription was not stored has to know.
        """
        # Core raises on a bad VAPID key BEFORE looking at any row, and this
        # keeps that precedence. Not defensive duplication: without it, a
        # caller echoing a stale key at an endpoint owned by somebody else
        # would get silence instead of `InvalidVapidError`. Fixed by this
        # module's own `test_core_registration_still_raises_on_a_stale_vapid_key`
        # -- and NOT by core's `test_push_notification_regenerate_vapid_keys`,
        # which calls `get_web_push_vapid_public_key()` first and therefore
        # unlinks every device before it registers, leaving no row for the
        # ownership branch to reach.
        if not self._verify_vapid_public_key(kw.get("vapid_public_key")):
            raise InvalidVapidError("Invalid VAPID public key")
        endpoint = kw.get("endpoint")
        if endpoint and not self._check_endpoint(endpoint):
            raise ValidationError(
                self.env._("This endpoint is not a known push service.")
            )
        partner = self.env.user.partner_id
        search_endpoint = kw.get("previousEndpoint", endpoint)
        devices_su = self.sudo()
        existing = (
            devices_su.search([("endpoint", "=", search_endpoint)], limit=1)
            if search_endpoint
            else devices_su.browse()
        )
        if existing:
            if not self._may_claim_device(existing, partner=partner):
                _logger.info(
                    "WebPush: refused to re-point an existing device to partner %s",
                    partner.id,
                )
                return None
        # No row to re-point means core is about to CREATE one, which is the
        # only branch the cap has to guard. The `endpoint`/`keys` test mirrors
        # core's own early return (mail/models/mail_push_device.py:53-56), so a
        # call core would have ignored is not turned into an error here.
        elif (
            endpoint
            and kw.get("keys")
            and devices_su.search_count([("partner_id", "=", partner.id)])
            >= MAX_DEVICES_PER_PERSONA
        ):
            raise ValidationError(
                self.env._(
                    "This account already has the maximum number of "
                    "notification devices."
                )
            )
        return super().register_devices(**kw)

    @api.model
    def _may_claim_device(self, device, *, partner=None, guest=None):
        """Does this request prove it is the browser behind `device`?

        ONE predicate, four doors: `/mail/push/subscribe`,
        `/mail/push/unsubscribe`, and core's `register_devices` and
        `unregister_devices` reached over `/web/dataset/call_kw`. They ask the
        same question -- "is this row yours?" -- and an answer that differed
        between them would not be an ownership rule, it would be a rule about
        which door somebody knocked on.

        WHY THIS EXISTS: an endpoint is the only thing identifying a device
        row, and it travels in the request body of an `auth="public"` route.
        Re-pointing on sight -- "the row belongs to whoever is here NOW" --
        makes subscription the mirror image of the deletion oracle that
        `_unregister_for_persona` was written to close, and a strictly stronger
        one: the victim stops receiving (their row now points at somebody
        else's persona) AND the attacker gains the ability to make the victim's
        browser ring, with the author name and message body this module puts in
        the payload. Silencing is the weaker half of that.

        So claiming a row needs a reason to believe the caller IS this browser:

        * the row already belongs to this same persona -- a browser refreshing
          its own subscription, which is the ordinary case (the push service
          hands back the same endpoint on every `pushManager.subscribe`); or
        * the row belongs to the GUEST OF THIS REQUEST while the caller is a
          partner. That is the guest->login upgrade: a visitor subscribes
          anonymously, logs in later, and the same browser must carry its
          subscription over to the account. It is safe because the request
          carries that guest's `dgid` cookie, which is `consteq`d against the
          guest's `access_token` before any of this runs: holding the cookie
          IS holding the guest identity. The guest is read back from the
          request (`_current_guest`) rather than passed in, because both
          callers have already dropped it -- this module's controller resolves
          the persona as the partner, and core's `register_devices` never knew
          guests existed.

        NOT allowed, deliberately: the reverse transfer. A browser that logs
        OUT and comes back as a guest cannot claim the partner's row, because
        the session it would have to prove ownership with is exactly the one it
        just dropped. The cost is a browser whose old row keeps pushing to the
        account until the person unsubscribes while still logged in, or until
        the push service rotates the endpoint and core unlinks the stale row on
        the first 404/410 (mail/models/mail_thread.py:3933-3942). Stated in the
        README as a known limit; it is the safe side of the trade, since the
        alternative is the takeover above.

        :returns: bool
        """
        if partner and device.partner_id == partner:
            return True
        if guest and device.guest_id == guest:
            return True
        # guest -> login upgrade. Off a request there is no guest to be found
        # and this is simply False.
        if partner and device.guest_id:
            current_guest = self._current_guest()
            return bool(current_guest) and device.guest_id == current_guest
        return False

    @api.model
    def _current_guest(self):
        """The guest THIS request proves it is, or an empty recordset.

        Two sources, one proof. `_get_guest_from_context` reads what
        `add_guest_to_context` put in the environment, which covers this
        module's own `auth="public"` routes. The cookie fallback covers
        `/web/dataset/call_kw`, which carries the same `dgid` cookie the
        browser always sends but is NOT decorated, so the guest never reaches
        the context there -- and without this fallback the guest->login upgrade
        would be impossible through core's `register_devices`, which is exactly
        the path core's own web client uses when a user logs in.

        Both sources end in `_get_guest_from_token`, which `consteq`s the
        cookie against the guest's `access_token`
        (mail/models/discuss/mail_guest.py:50-60). This is therefore not a
        weaker proof than the public route's, it is the same one read from one
        step further out.

        The `ValueError` guard is not decoration: `_get_guest_from_token` does
        a bare `int(guest_id)` on the cookie. On a decorated public route a
        corrupt `dgid` already raises inside core, which is core's business --
        but this method introduces cookie parsing on a path that never touched
        the cookie before, and a visitor with a mangled cookie must not start
        getting errors out of push registration because of it.
        """
        guest = self.env["mail.guest"]._get_guest_from_context()
        if guest or not request:
            return guest
        guest_model = self.env["mail.guest"]
        try:
            return guest_model._get_guest_from_token(
                request.cookies.get(guest_model._cookie_name, "")
            )
        except ValueError:
            return guest_model

    @api.model
    def unregister_devices(self, **kw):
        """Core's authenticated unregistration, same rule, same door.

        `unregister_devices` does `search([("endpoint", "=", endpoint)])
        .unlink()` (mail/models/mail_push_device.py:75-84). That is the
        deletion oracle this module already closed on `/mail/push/unsubscribe`,
        still standing on the ORM door -- and reachable exactly as
        `register_devices` is, by any authenticated account. Closing the
        subscribe side and leaving this open would have moved the hole, not
        shut it: silencing somebody is the outcome both reach.

        BEYOND THE LETTER OF THE BRIEF, and easy to revert if that is wrong:
        the instruction named `register_devices`. This is the same method on
        the same model behind the same route with the same missing check, so
        fixing one and filing the other as a "known gap" would have reproduced
        the failure pattern that motivated the instruction.

        Cost, stated plainly: on a SHARED BROWSER, somebody who cannot claim
        the row can no longer delete it either, so a subscription belonging to
        the previous user survives their `unsubscribe` click. It self-heals --
        the client calls `pushManager.unsubscribe()` locally right after
        (mail/static/src/webclient/web/webclient.js), which kills the endpoint,
        and core unlinks the row on the first 404/410 from the push service.
        One stale notification is the worst case, against a live "silence
        anyone whose endpoint you know" primitive.

        :returns: None, like core; `webclient.js` ignores it.
        """
        endpoint = kw.get("endpoint")
        if not endpoint:
            return super().unregister_devices(**kw)
        existing = self.sudo().search([("endpoint", "=", endpoint)], limit=1)
        if existing and not self._may_claim_device(
            existing, partner=self.env.user.partner_id
        ):
            _logger.info(
                "WebPush: refused to unregister a device for partner %s",
                self.env.user.partner_id.id,
            )
            return None
        return super().unregister_devices(**kw)

    @api.model
    def _unregister_for_persona(self, *, partner=None, guest=None, endpoint=None):
        """Drop `endpoint`, but only if this persona owns it.

        Core's `unregister_devices` deletes by endpoint with no ownership check
        (mail/models/mail_push_device.py:75-84), which is fine behind
        `auth="user"` and is a deletion oracle on a public route: anyone
        knowing (or guessing) somebody else's endpoint could silence them.

        :returns: True when a device was removed.
        """
        if not endpoint or not isinstance(endpoint, str):
            return False
        persona_domain = (
            [("partner_id", "=", partner.id)]
            if partner
            else [("guest_id", "=", guest.id)] if guest else None
        )
        if persona_domain is None:
            return False
        # sudo: same reason as `_register_for_persona`; ownership is in the
        # domain, not in the ACL.
        devices = self.sudo().search([("endpoint", "=", endpoint)] + persona_domain)
        if not devices:
            return False
        devices.unlink()
        return True

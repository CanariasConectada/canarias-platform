# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.mail.tools.discuss import add_guest_to_context


class MailPushGuestController(http.Controller):
    """Public registration endpoints for web push subscriptions.

    WHY THESE ROUTES EXIST AT ALL: core registers a device through the ORM
    method `mail.push.device.register_devices`, reached over
    `/web/dataset/call_kw`, which is `auth="user"`. A guest is the public user
    plus a cookie, and `ir.http._authenticate` rejects the public user for
    `auth="user"` routes, so there is no way for a guest to reach that method.
    `auth="public"` routes are the only door, and `add_guest_to_context` is what
    puts the guest of the `dgid` cookie into the environment
    (mail/tools/discuss.py:16-38).
    """

    # ------------------------------------------------------------------
    # Persona
    # ------------------------------------------------------------------

    def _mail_push_guest_persona(self):
        """Resolve who is calling, from the session only.

        Never from the payload: on an `auth="public"` route every parameter is
        attacker-chosen, so a `partner_id` or `guest_id` argument would be an
        invitation to subscribe somebody else's browser -- or to have this
        server push somebody else's messages to an endpoint of one's choosing.

        A real account wins over a guest cookie: the two can coexist in one
        browser (log in without clearing `dgid`), and the account is the
        identity that survives.

        :returns: tuple (partner, guest), exactly one of which is truthy
        :raises NotFound: when there is neither. An anonymous, persona-less
            device would be a subscription nothing could ever address, and its
            row would still be an endpoint this server posts to.
        """
        user = request.env.user
        if user and not user._is_public():
            return user.partner_id, None
        guest = request.env["mail.guest"]._get_guest_from_context()
        if guest:
            return None, guest
        raise NotFound()

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @http.route("/mail/push/vapid", methods=["POST"], type="jsonrpc", auth="public")
    @add_guest_to_context
    def mail_push_guest_vapid(self, **kwargs):
        """Return the VAPID public key, and ONLY read it.

        Deliberately NOT `mail.push.device.get_web_push_vapid_public_key()`.
        That method regenerates the key pair when the public key parameter is
        missing, and its first act is `self.sudo().search([]).unlink()` --
        every push device on the database, gone
        (mail/models/mail_push_device.py:33-45). Behind `auth="user"` that is a
        footgun; exposed on a public route it would be an unauthenticated
        "delete every subscription" button, triggerable by anyone the moment
        the parameter is absent.

        So: read the parameter, and when it is not there answer False. Key
        GENERATION stays an administrative act (Settings, or the authenticated
        core path), because the pair is effectively immutable once published --
        rotating it invalidates every subscription every browser holds.

        The value is public by definition: it is shipped to every browser that
        subscribes, and it is not a persona-bearing secret, which is why this
        route does not require a persona.
        """
        vapid_public_key = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("mail.web_push_vapid_public_key")
        )
        return {"vapid_public_key": vapid_public_key or False}

    @http.route("/mail/push/subscribe", methods=["POST"], type="jsonrpc", auth="public")
    @add_guest_to_context
    def mail_push_guest_subscribe(
        self,
        endpoint=None,
        keys=None,
        vapid_public_key=None,
        expiration_time=None,
        **kwargs,
    ):
        """Bind a browser subscription to the caller's persona.

        `keys` is the `{p256dh, auth}` pair from
        `PushSubscription.toJSON().keys`; `vapid_public_key` is the key the
        service worker subscribed with, echoed back so a client running against
        a rotated pair is refused instead of registering a device nothing can
        ever encrypt for.

        ALWAYS ANSWERS `True` WHEN THE INPUT IS WELL FORMED, including when
        `_register_for_persona` refused to hand somebody else's endpoint to
        this caller (it answers an empty recordset then, and that difference
        stops here ON PURPOSE). Telling the caller "that endpoint is not
        yours" would confirm that the endpoint EXISTS to anyone holding one
        they should not -- the same class of oracle `/mail/push/unsubscribe`
        avoids by returning False. Malformed input keeps raising, because a
        client that sent a bad key pair has to know.

        To be explicit about the size of what this buys: a push endpoint ends
        in a vendor-generated token of roughly 100 bits, so nobody is
        ENUMERATING endpoints through this route -- an attacker has to have
        obtained one already (a shared browser, a leaked log, a service worker
        someone read). The silence therefore is not what stops the attack;
        `_may_claim_device` is. It stops the route from confirming a stolen
        endpoint is live, and it keeps the successful and the refused call
        indistinguishable to a client that should not be able to tell them
        apart. The refusal is logged server-side, where an administrator can
        see it.
        """
        partner, guest = self._mail_push_guest_persona()
        request.env["mail.push.device"]._register_for_persona(
            partner=partner,
            guest=guest,
            endpoint=endpoint,
            keys=keys,
            expiration_time=expiration_time,
            vapid_public_key=vapid_public_key,
        )
        return True

    @http.route(
        "/mail/push/unsubscribe", methods=["POST"], type="jsonrpc", auth="public"
    )
    @add_guest_to_context
    def mail_push_guest_unsubscribe(self, endpoint=None, **kwargs):
        """Drop a subscription owned by the caller.

        Returns True only when something was removed, so a client can tell
        "unsubscribed" from "that was never yours".
        """
        partner, guest = self._mail_push_guest_persona()
        return request.env["mail.push.device"]._unregister_for_persona(
            partner=partner, guest=guest, endpoint=endpoint
        )

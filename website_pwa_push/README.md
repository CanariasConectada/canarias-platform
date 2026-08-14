# Website PWA Push

**Version:** 19.0.1.0.0 | **License:** AGPL-3 | **Author:** Canarias Conectada

Web Push for the **public** website app. `website_pwa` made each microsite
installable and serves it a service worker; `mail_push_guest` made an anonymous
visitor a first-class owner of a push subscription and pushes channel messages
to guests. Neither half was connected to the other: the worker had no `push`
handler and no page ever asked the visitor for permission. This module is that
connection, and nothing else.

## What a visitor sees on a locked screen

The notification carries **the author's name and the beginning of what they
wrote** — "Maria in Guanarteme: does anybody know if…" — rendered by the
operating system on a phone that may be locked, in front of whoever is holding
it. That is a deliberate product decision inherited from `mail_push_guest`
(`_web_push_guest_prepare_payload`): a notification that says only "New message"
is one nobody acts on. The body is truncated by
`_web_push_truncate_payload`, which owns the 4 KB payload limit — it is
truncation for size, **not** redaction for privacy. Anybody who can see the
screen can read the first line of the message.

Messages from one conversation share a notification `tag`, so a burst replaces
the previous notification instead of stacking twenty of them. The replacement is
silent (`renotify` is left unset): one buzz per conversation, not one per
message.

## Two switches, not one

| Field | Meaning |
| --- | --- |
| `website.pwa_enabled` | this website is installable (`website_pwa`) |
| `website.pwa_push_enabled` | …and it also does Web Push |

Separate on purpose, so push can be piloted on the main website while the other
217 keep the app exactly as it is today. Push **requires** the app: the handlers
live inside the service worker, and `/service-worker.js` answers 404 when
`pwa_enabled` is off, so a website with push on and the app off is exactly as
silent as one with both off. `website._pwa_push_active()` is the single place
that says so.

## What is appended to the service worker, and what is not

`website_pwa` exposes `_pwa_service_worker_content(website)` so extensions can
`super()` and append. This module appends three handlers, **only** when the
website has push on:

- `push` → `event.data.json()` → `showNotification(title, options)`, with a
  `tag` derived from the channel. A payload that cannot be parsed still shows a
  generic notification, because `userVisibleOnly: true` is a promise to the
  browser that every push produces one; breaking it makes Chrome display its own
  "This site has been updated in the background" notice and eventually revoke
  the subscription.
- `notificationclick` → focus a tab already on that page
  (`clients.matchAll({includeUncontrolled: true})` — a tab opened before the
  worker took control is usually the very tab the visitor is looking at), else
  `clients.openWindow`.
- `pushsubscriptionchange` → re-subscribe with the old options and POST the new
  subscription to `/mail/push/subscribe`, carrying `previous_endpoint`.

The reference read while writing them was
`mail/static/src/service_worker.js` **as it runs in the container**
(`/opt/odoo/custom/src/odoo/addons/mail/static/src/service_worker.js`; the copy
under `/home/odoo/odoo` is an older snapshot and differs). What was deliberately
left there:

- **`importScripts("/mail/static/lib/idb-keyval/idb-keyval.js")`** — a backend
  library, and a failing import aborts the installation of the whole service
  worker, which would take `website_pwa`'s offline cache down with it.
- **`/odoo/...` click targets.** Core opens
  `/odoo/action-mail.action_discuss`, which answers a login screen to the
  anonymous visitors this stack exists for. We open
  `/discuss/channel/<res_id>`, the `auth="public"` page core itself serves
  (`mail/controllers/discuss/public_page.py`), exactly as `mail_push_guest`'s
  ROADMAP said a guest worker would have to.
- **The `postMessage` handshake with an open web client.** Core asks every open
  tab whether it wants to display the notification itself and waits 500 ms
  before falling back. That negotiation is with the Discuss web client; on a
  public microsite there is nobody on the other end, so it is 500 ms of nothing.
- **The IndexedDB unread badge and the RTC log store.** Both are backend
  features (`navigator.setAppBadge`, `POST_RTC_LOGS`), and the second one keeps
  a database of call logs on the visitor's phone.
- **The `CALL` / `CANCEL` notification types and their actions.** Guests do not
  receive call invitations at all: `_rtc_invite_members` builds its payload from
  `devices.partner_id`.
- **`/web/dataset/call_kw/mail.push.device/register_devices`** on
  `pushsubscriptionchange`. It is `auth="user"`; the public route is
  `/mail/push/subscribe`.

What was reused, because it is not core's to own: the shape of the JSON payload,
and the base64url re-encoding of `subscription.options.applicationServerKey` —
that property reads back as an `ArrayBuffer` even when subscribed with a string,
and the server compares the echoed key against the stored parameter, so without
the re-encoding the renewed subscription is refused as an invalid VAPID key.

## `CACHE_VERSION`: no bump needed

`website_pwa`'s `CACHE_VERSION` names the cache holding the **offline page**,
and its `activate` handler deletes every cache that is not the current one.
Nothing appended here caches anything, touches the offline page or changes the
fetch rules, so **the constant does not need to move** — and bumping it would
have a real cost: every visitor of every microsite would drop and re-fetch their
offline shell for a change that does not concern them.

Turning push on for a website does change the worker's **bytes**, and that is
the mechanism that matters: the browser byte-compares the script it has with the
one the server sends and installs the new version by itself. That is also why
the worker must stay byte-identical for websites **without** push — pinned by
`test_worker_is_byte_identical_to_website_pwa_when_push_is_off`.

## The permission prompt

`Notification.requestPermission()` is called from the click on "Activar avisos"
and **from nowhere else**. Asking on page load is not merely rude: Chrome counts
unprompted requests as an abuse signal and can put the site under a quieter
permission UI for every visitor, and Safari ignores a request that does not come
from a user gesture — so the call would be a silent no-op that also spends the
one chance the visitor had to say yes.

The card is a snippet (like `website_pwa`'s install card) and shows exactly one
branch, decided in the browser:

| Situation | What is shown |
| --- | --- |
| push not supported, or not enabled for this website | nothing |
| iOS, not installed to the home screen | install instructions |
| permission `denied` | where to undo it in the browser settings |
| permission `granted` | a confirmation; the subscription is refreshed silently |
| permission `default` | the button |

## iOS

Safari grants `pushManager.subscribe` **only** inside a PWA installed to the
home screen. On an iPhone browsing the site normally the button cannot work, so
it is not shown; the card explains Share → "Añadir a pantalla de inicio"
instead. The detection is `website_pwa`'s own (`PWAInstall.prototype.isIOS` /
`isStandalone`), called rather than copied, so the install card and this card
cannot drift apart on the same page — and any future fix over there (iPadOS
reporting itself as a Mac, for instance) arrives here for free.

## Dependencies

- `website_pwa` — the manifest, the worker and its extension hook
- `mail_push_guest` — the public `/mail/push/*` routes and the guest persona

Core is extended, never modified.

## Credits

### Contributors

- Mike Colangelo

### License

AGPL-3. See the LICENSE file at the root of the repository.

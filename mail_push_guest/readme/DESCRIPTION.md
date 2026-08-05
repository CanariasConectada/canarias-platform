Web Push notifications for anonymous visitors.

Odoo's push stack is partner-shaped from end to end. `mail.push.device`
requires a `partner_id`, recipient resolution collects partner ids, and the
channel member query filters on `partner_id` — so a `mail.guest`, the persona
an anonymous visitor gets when they open a public channel, is not "excluded"
from push notifications: it structurally never enters the computation. This
module adds the missing half.

It ships the server side only: the model, the persona resolution and three
public routes. There is no JavaScript, no service worker and no UI. A browser
still needs a service worker calling `/mail/push/subscribe` before anything is
delivered — see USAGE.

## What it adds

- **A device can belong to a guest.** `mail.push.device.guest_id`, with the
  owner constrained to be exactly one persona: a partner or a guest, never
  both, never neither.
- **A public registration door.** `POST /mail/push/vapid`,
  `/mail/push/subscribe` and `/mail/push/unsubscribe`, all `auth="public"`,
  with the persona read from the session (the `dgid` cookie or a real login)
  and never from the request body. No persona, no device: the route answers
  404. An endpoint that already belongs to somebody else is not taken over —
  the only transfer allowed is a guest handing its own subscription to the
  account it just logged into, proven by the cookie the request carries. The
  same rules — ownership, the host allowlist, the device cap — are applied to
  core's own `register_devices` and `unregister_devices`, which any
  authenticated account can reach over `/web/dataset/call_kw`.
- **Guest members of a channel get pushed.** A second pass next to core's,
  honouring the same rules core honours for partners: never the author, never
  a muted member, never a member who turned notifications off.

## What it means for privacy

**The notification carries the author's name and the beginning of the
message** — "Maria in Guanarteme: does anybody know if…" — because a
notification that says only "New message" is one nobody acts on. That text is
rendered by the operating system on a **locked screen**, next to whatever else
is on it, and the person holding the phone is by definition not authenticated.
Anyone who can see the screen can read who wrote and roughly what.

This is a deliberate product decision, and it is the module's main privacy
cost. Two consequences worth stating plainly:

- A guest subscription is a **cookie plus an endpoint**. Whoever holds the
  browser holds the subscription; there is no password to lose and none to
  change. Clearing site data ends it.
- The endpoint itself is a stable per-browser identifier held by a third party
  (Google, Mozilla, Apple, Microsoft), and every notification tells that third
  party that this browser is receiving something, from this server, right now.
  The message content is end-to-end encrypted for the browser; the metadata is
  not.

## What it does not do

- It does not generate VAPID keys. See USAGE.
- It does not push anything outside `discuss.channel`.
- It does not ship a front end.

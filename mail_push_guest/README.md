# Mail Push Guest

**Version:** 19.0.1.0.0 | **License:** AGPL-3 | **Author:** Canarias Conectada

Web Push notifications for anonymous visitors. Odoo's push stack only knows
`res.partner`; this module makes a `mail.guest` — the persona an anonymous
visitor gets on a public channel — a first-class owner of a push subscription,
and pushes channel messages to the guest members core cannot see.

Server side only: the model, the persona resolution and three `auth="public"`
routes. No JavaScript, no service worker, no UI. See `readme/USAGE.md` for what
a client has to call.

**This makes push work for people who are not logged in, and the notification
carries the author's name and the start of the message** — "Maria in
Guanarteme: does anybody know if…". That text is rendered by the operating
system on a **locked screen**. It is a deliberate product decision and the
module's main privacy cost; `readme/DESCRIPTION.md` states the rest.

## Why core cannot do this

`mail.push.device.partner_id` is `required=True` with an
`env.user.partner_id` default, `_web_push_get_partners_parameters` searches
devices by `partner_id`, and `discuss_channel._notify_get_recipients` filters
members on `partner_id.active`. A guest is therefore not filtered out of push
notifications — it never enters the computation. Registration is unreachable
too: core registers devices through an ORM method behind
`/web/dataset/call_kw`, which is `auth="user"`, and the public user is rejected
there.

Core is extended, never modified.

## Three things this module refuses to do

- **Generate VAPID keys on anybody's say-so.**
  `get_web_push_vapid_public_key()` unlinks *every* push device on the database
  when the public key parameter is missing, and then rotates the pair, which
  invalidates the subscription every browser still holds. `/mail/push/vapid`
  reads the parameter directly and answers `false` when it is absent; the ORM
  method is overridden so that the *generating* branch requires
  `base.group_system`. Reading the key stays open to everybody — it is public
  by definition, shipped to every browser that subscribes.
- **Post to an arbitrary URL.** A subscription endpoint is a URL this server
  will `POST` to, and core only checks that it does not end in `.invalid`.
  Without a host allowlist that is a request-forgery primitive with a log side
  channel — unauthenticated through the public route, and *authenticated* but
  just as effective through core's `register_devices`, which any account
  reaches over `/web/dataset/call_kw`. Both doors therefore accept only the
  real push services (FCM/Google, Mozilla, Apple, WNS). That list must be
  maintained as browsers change.
- **Hand somebody else's endpoint to whoever asks for it.** Core resolves a
  device by endpoint alone, on both `register_devices` and
  `unregister_devices`, which is fine behind `auth="user"` in stock Odoo's
  threat model and is not fine here. Deleting by endpoint silences a stranger;
  *re-pointing* by endpoint does that **and** gives the caller the stranger's
  browser to ring — with an author name and a message body in the payload.
  See below.

## Endpoint ownership: one rule, four doors

The rule is enforced on **every** way into the model, not just the new ones:

| Door | Auth | Enforced by |
| --- | --- | --- |
| `/mail/push/subscribe` | public | `_register_for_persona` |
| `/mail/push/unsubscribe` | public | `_unregister_for_persona` |
| `mail.push.device.register_devices` | user | override, delegates to core |
| `mail.push.device.unregister_devices` | user | override, delegates to core |

Endpoint **shape** (the host allowlist) and the **device cap** are enforced on
the two registering doors, and `get_web_push_vapid_public_key` is overridden on
the ORM side too, so no check lives on one door and not on its twin.

The last two rows matter more than they look. `/web/dataset/call_kw` performs no
model ACL of its own — `call_kw` only refuses private methods — and both core
methods sudo internally, so the `base.group_system` grant on
`mail.push.device` stops nobody: **any** authenticated account reaches them,
portal included. With self-signup enabled, "any authenticated account" means
anyone. A rule that held on the public door and not on the ORM door would not
be an ownership rule, it would be a rule about which door somebody knocked on.

All four ask one predicate, `_may_claim_device`: *does this request prove it
is the browser behind this row?* A row is claimable only when the caller has a
reason to be believed to be that browser:

- the row already belongs to the same persona — the ordinary case, since a
  push service hands back the same endpoint on every `pushManager.subscribe`
  and a browser re-registers its own subscription routinely; or
- the row belongs to the **guest of this very request** and the caller is now a
  partner. That is the guest → login upgrade: a visitor subscribes
  anonymously, logs in later, and the same browser carries its subscription to
  the account. The request proves it by carrying that guest's `dgid` cookie,
  which is checked against the guest's `access_token` before anything else
  runs. On the public routes the cookie is already in the environment; on
  `/web/dataset/call_kw`, which is not decorated to put it there, it is read
  straight off the request — the same proof one step further out. Without that
  fallback the upgrade would be impossible through core's `register_devices`,
  which is precisely the call the web client makes when a user logs in.

On `previousEndpoint`: core looks the row up by *that* when it is given and
*means* to rename the row to the new endpoint. The check therefore gates the
**search key**, not the new endpoint — otherwise
`register_devices(previousEndpoint=<victim>, endpoint=<mine>)` would walk
somebody else's row onto an endpoint of the caller's choosing. The legitimate
use of the same field, a browser renaming its own subscription on
`pushsubscriptionchange`, is unaffected by this check — though it does not
work in stock Odoo 19 either, for a core reason described in the ROADMAP.

Anything else is refused, and **the caller cannot tell**: the public route
still answers `true`, and the core methods still return `None`, exactly as
they do on success (every core caller ignores the return value, so silence
costs nothing there). Replying "that endpoint is not yours" would confirm the
endpoint exists to somebody holding one they should not. Endpoints carry
roughly 100 bits of vendor-generated entropy, so nobody enumerates them — an
attacker has to have obtained one already (a shared browser, a leaked log, a
service worker somebody read). The silence is not what stops the attack; the
ownership check is. Refusals are logged at INFO, without the endpoint.

Nothing legitimate loses to the ownership check: a browser claiming its own
row, a guest upgrading to an account, and a user unsubscribing their own device
all still work, and each has a regression test. Two of those paths — refreshing
your own subscription and renaming it via `previousEndpoint` — do nothing in
stock Odoo 19 regardless, because core skips the write for a row the caller
already owns; the tests assert that our check *permits* the row and that core
is what declines to write it. See the ROADMAP.

**Known limit — the reverse transfer is not allowed.** A browser that
registered while logged in, then logs out and comes back as a guest, cannot
claim that row: the session that would prove ownership is the one it just
dropped. The old row keeps notifying the account until the person unsubscribes
*before* logging out, or until the push service rotates the endpoint and core
unlinks the stale row on the first 404/410. On a shared computer, log out from
the notification subscription first.

## Upgrading an existing install: `partner_id` now cascades

Making `partner_id` optional (core has it `required=True`) changes the
foreign-key policy, because a Many2one derives its `ondelete` from `required`.
This module pins it explicitly to `ondelete="cascade"`, which is the only
policy the persona XOR survives — but it is a **real behaviour change against
stock Odoo**:

> Deleting a `res.partner` used to be **blocked** while they held a push device
> (`restrict`). It now **succeeds and silently deletes their devices**
> (`cascade`).

Nothing else in the platform depends on that delete being blocked, and a
subscription is not history worth keeping — but any tooling that relied on the
error to notice "this partner is still in use" will stop seeing it.

## Dependencies

- `mail` (Odoo core)

## Credits

### Contributors

- Mike Colangelo

### License

AGPL-3. See the LICENSE file at the root of the repository.

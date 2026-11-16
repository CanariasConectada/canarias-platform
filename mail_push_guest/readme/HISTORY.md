## 19.0.1.3.1 (2026-09-29)

- Registering the same endpoint twice at once is no longer an error. The
  Discuss banner's "Activate and verify" (`/mail/push/subscribe`) and core's
  web client (`register_devices`, woken by the same permission grant) both
  inserted the row, and the loser got "The endpoint must be unique". Both
  doors now insert inside a savepoint: a conflicting row visible to the
  transaction goes through the usual ownership rule (same persona: success;
  another persona: the same silent refusal), and a row committed by a
  concurrent transaction raises `ConcurrencyError`, so Odoo replays the
  request, which then finds the row.

## 19.0.1.3.0 (2026-09-26)

- No web push leaves the server silent: every payload gets `silent: false`,
  an Android vibration pattern (`[120, 60, 120]`, kept if the payload has
  its own) and `renotify: true` when it carries a `tag` (only then: with no
  tag the browser rejects the notification). Applied in `mail.thread`
  before core truncates the payload (so the 4 KB limit still holds) and
  again at `_web_push_send_notification`, the one door every push goes
  through: core's partner pushes, guest pushes, call invitations and
  `cc_push_test`, direct or queued.
- Shared foreground chime (`@mail_push_guest/js/chime`, in the backend and
  frontend bundles): core's "new message" sound, at most once every 2
  seconds across the tabs and frames of an origin, never for the listener's
  own message or the conversation on screen, muted by core's own "message
  sound" preference (default on).
- Message push payloads name their author in `data` (`author_partner_id`,
  `author_guest_id`, ids only), so an open page can skip the chime for its
  own message.

## 19.0.1.2.1 (2026-09-26)

- Pushes are written in the reader's language. Core builds one payload in
  the poster's environment, so its translatable parts (attachment wording,
  "%(author)s in %(channel)s") reached a Spanish phone in English whenever
  the poster's language was English. Partner recipients are now grouped by
  their language and core's step runs once per group in that language;
  guest devices are grouped by `mail.guest.lang` the same way. The test
  push body (`cc_push_test`) uses the owner's language, not the request's.

## 19.0.1.2.0 (2026-09-25)

- `mail.push.device.cc_push_status(endpoint)`: tells the authenticated web
  client whether its own subscription is `registered` for the current user,
  `not_registered`, or `owned_by_other` (never who owns it). Every
  registration door stays silent on refusal; this is the question the client
  can now ask afterwards.
- `mail.push.device.cc_push_test()`: sends a real test web push through
  core's sender to the current user's own devices only, at most once a
  minute per user (`cc_test_push_dt`).

## 19.0.1.1.0 (2026-09-25)

- `mail.push.device.cc_worker` records which service worker owns a device:
  the website's (scope `/`) or core's backend one (scope `/odoo`).
  `/mail/push/subscribe` takes an optional `worker` (anything else reads as
  `website`); core's `register_devices` tags `backend`.
- Safety net against double notifications: registering a backend device for
  an internal user deletes that user's `website` devices. The server cannot
  tell browsers apart, so it removes all of them, which matches the routing
  rule (internal users are pushed through the backend worker only). Rows with
  no recorded worker, and portal users and guests, are left alone.

## 19.0.1.0.0 (2026-08-05)

- First release: `mail.push.device` may belong to a `mail.guest`, with the
  owner constrained to exactly one persona (SQL CHECK for "never both", ORM
  constraint for the full XOR) and both foreign keys pinned to an explicit
  `ondelete="cascade"`.
- Public registration routes (`/mail/push/vapid`, `/mail/push/subscribe`,
  `/mail/push/unsubscribe`), with the persona resolved from the session, a
  host allowlist on the subscription endpoint, and a cap of 5 devices per
  persona.
- Endpoint ownership is checked on all four ways into the model — the two
  public routes and core's `register_devices` / `unregister_devices`, which
  any authenticated account can reach over `/web/dataset/call_kw`. A caller
  may only claim a device row that already belongs to it, or that belongs to
  the guest whose cookie the same request carries (the guest → login
  upgrade). Refusals are silent: the routes answer as they do on success, and
  the core methods keep returning `None`.
- The host allowlist and the device cap are enforced on core's
  `register_devices` as well as on the public route, and
  `get_web_push_vapid_public_key` only regenerates the pair (deleting every
  device on the database) for `base.group_system`. All three are **behaviour
  changes against stock Odoo for authenticated users**, taken because
  `/web/dataset/call_kw` performs no model ACL and portal accounts are
  self-signed-up. See the ROADMAP for what each costs.
- **Behaviour change against stock Odoo:** deleting a `res.partner` that holds
  push devices used to be blocked and now deletes those devices, because
  `partner_id` is no longer `required` and is pinned to `ondelete="cascade"`.
  See the README.
- `discuss.channel` pushes to its guest members as well as its partners,
  honouring mute and per-member notification settings, with the author's name
  and a truncated body in the notification.

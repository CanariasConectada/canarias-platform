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

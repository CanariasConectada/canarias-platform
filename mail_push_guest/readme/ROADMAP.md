## Known limits

- **No front end.** No service worker, no subscription prompt, no click
  handler. This module is the server half; without a client calling
  `/mail/push/subscribe` nothing is ever registered and nothing is ever
  delivered.
- **The click target is a backend action.** The payload keeps core's
  `data.action = "mail.action_discuss"` (set by
  `discuss_channel._notify_by_web_push_prepare_payload`), which a guest cannot
  open. A service worker for guests has to map the notification to
  `/discuss/channel/<res_id>` itself.
- **One language per notification.** A single payload is built for all the
  guest devices of a channel and rendered in the environment's language — the
  poster's. Per-language rendering is what core's `payload_by_lang` is for, and
  that path indexes the dict with `device.partner_id.lang`, which for a
  partner-less device evaluates to `False` and raises. Doing it properly means
  grouping guest devices by `mail.guest.lang` and sending one payload per
  group; it is not done here.
- **The allowlist is a maintenance obligation.** `PUSH_ENDPOINT_ALLOWED_HOSTS`
  is a list of vendor hostnames, not a standard. A new browser, or a vendor
  moving domains, means real subscriptions are refused until somebody updates
  the tuple. The failure is visible ("this endpoint is not a known push
  service"), which is the intended trade against a permissive check.
- **The allowlist now guards both doors, and that changes core behaviour.**
  `_check_endpoint` runs on `/mail/push/subscribe` *and* on core's
  `register_devices`. It was public-route-only at first, on the argument that
  `auth="user"` paid for the core path; it does not, because
  `/web/dataset/call_kw` performs no model ACL and a portal account on this
  platform is anybody who signed themselves up. The consequence for internal
  users: a browser whose push vendor is not in `PUSH_ENDPOINT_ALLOWED_HOSTS`
  can no longer register through the backend either, and the symptom is
  silent — `webclient.js` catches the `ValidationError` into a `console.warn`
  and `service_worker.js` ignores the response altogether. Core's own Python
  tests are unaffected: the only one that calls `register_devices`
  (`test_push_notification_regenerate_vapid_keys`) raises `InvalidVapidError`
  before the endpoint is looked at.
- **The allowlist survives the request, but not a redirect.** `push_to_end_point`
  (`mail/tools/web_push.py`) calls `session.post(endpoint, ...)` **without**
  `allow_redirects=False`, so `requests` follows a `3xx` by default. A host that
  passed the allowlist could therefore hand the worker a `Location:` pointing
  anywhere — including an internal address — and the allowlist would have been
  checked against the first URL only. Residual, not urgent: the only hosts that
  can reach that branch are Google, Mozilla, Apple and Microsoft push
  infrastructure, so exploiting it means one of them being compromised or
  malicious. It is also **core's code**, so fixing it here would mean patching
  core, which this platform does not do. The honest remedies, in order: get
  `allow_redirects=False` upstream, or (if the risk ever stops being
  theoretical) send through a wrapper of our own instead of core's helper.
- **No asymmetry is left between the public routes and the ORM door.**
  Ownership, endpoint shape, the device cap and the refusal to generate VAPID
  keys are all enforced on both. That is deliberate: a rule that holds on one
  door and not on the other is not a rule, it is a statement about which door
  somebody knocked on.
- **A stale row can outlive an `unsubscribe` on a shared browser.** Since
  `unregister_devices` now refuses to delete a row the caller cannot claim,
  somebody clicking "turn notifications off" on a browser whose subscription
  belongs to a *previous* user does not remove it. The client kills the
  endpoint locally in the same breath (`pushManager.unsubscribe()`), so the
  push service answers 404/410 on the next message and core unlinks the row
  then — one stale notification, worst case.
- **Core never rewrites a row that already belongs to the caller, so the
  rename path is dead on *both* callers.** `register_devices` guards its only
  `write` with

  ```python
  if mail_push_device.partner_id != self.env.user.partner_id:
  ```

  (`mail/models/mail_push_device.py:59-66`), which is false exactly when the
  row is yours. Two things follow, and neither is caused by this module —
  both reproduce on a control database with it uninstalled:

  - **Refreshing your own subscription is a no-op.** New `keys` and a new
    `expirationTime` sent for a row you already own are discarded.
  - **`previousEndpoint` never renames anything.** Both callers spell the
    argument correctly (`webclient.js:96` and `service_worker.js:325` both
    send `previousEndpoint`, matching `kw.get('previousEndpoint', endpoint)`),
    core finds the row by it, and then skips the write because the row is the
    caller's own. So a browser whose endpoint rotates keeps a row pointing at
    the endpoint it no longer has, until the push service answers 404/410 and
    core unlinks it (`mail/models/mail_thread.py:3933-3942`). This is why
    stale device rows accumulate.

  Reported here rather than worked around: the fix belongs in core, and this
  platform does not patch core. The ownership check deliberately reads the
  search key the same way core does, so that it still guards the right row the
  day core starts writing it. Two tests
  (`test_core_registration_lets_the_caller_claim_its_own_device`,
  `test_core_registration_does_not_rename_the_caller_own_endpoint`) pin the
  current behaviour and will fail loudly, with a message naming the core line,
  if it changes.
- **A logged-out browser cannot reclaim its own subscription.** Endpoint
  ownership only transfers guest → account, because only that direction carries
  proof (the guest's `dgid` cookie). See the README section on endpoint
  ownership for what that costs on a shared computer.
- **A scheduled message reaches guests immediately when it has no partner
  recipients.** `_notify_thread` returns before the scheduling branch when
  `recipients_data` is empty, and that early return is precisely where the
  guest pass had to be hooked (otherwise a guest-only channel would never
  notify at all). So on a channel with no partner recipients, a message posted
  with `scheduled_date` still pushes to guests now, while partners would have
  been notified later. Fixing this properly means teaching
  `mail.message.schedule` about guest recipients.
- **No rate limiting.** A persona may hold 5 devices — enforced on the public
  route *and* on core's `register_devices`, since core creates without
  counting and a cap only one door honours is not a cap — and that is the
  whole budget. Nothing limits how often a caller may register, re-register or
  ask for the VAPID key. Real limiting needs a store shared by all workers.
  The cost of extending the cap to the ORM door: a person who genuinely uses
  six browsers is refused the sixth until one of the other rows goes stale.
  Re-registering an endpoint that is already theirs is never refused — the cap
  guards creation only.
- **Generating the VAPID pair now requires `base.group_system`.** Core's
  `get_web_push_vapid_public_key` regenerates the pair when the public key
  parameter is missing, and starts by unlinking *every* push device on the
  database. Reading is still open to everybody (the key is public by
  definition); only that destructive branch is gated. Consequence: on a
  database with no pair yet, a non-system user enabling notifications gets
  `false` and `webclient.js` shows "Failed to enable push notifications"
  instead of silently bootstrapping the platform's push identity. Since this
  method is `mail`'s only key generator — there is no Settings action for it —
  a fresh database must be bootstrapped by an administrator's own web client.
- **A cookie-less visitor cannot subscribe at all**, by design: the route
  answers 404 rather than binding a device to the shared public partner, which
  is where everybody's messages would then arrive.
- **Devices are cleaned up only by the push service.** A row disappears when
  its endpoint answers 404/410 (core unlinks it) or when the persona is
  deleted (cascade). There is no cron pruning subscriptions that simply stopped
  being used, and an expired `expiration_time` is stored but never acted on.

## Missing features

- No per-guest opt-out UI. `discuss.channel.member.custom_notifications` and
  `mute_until_dt` are honoured, but nothing in the guest-facing client sets
  them.
- No `discuss.channel` call notifications for guests: `_rtc_invite_members`
  builds a `payload_by_lang` from `devices.partner_id`
  (`mail/models/discuss/discuss_channel_member.py`), so an incoming call still
  reaches partners only.
- Nothing outside `discuss.channel`. Any other `mail.thread` notifies through
  followers, which are partners.

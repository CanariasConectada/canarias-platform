## Known limits

- **The worker is executed by the tests; the browser around it is not.**
  `tests/test_service_worker_js.py` fetches `/service-worker.js` and runs the
  served bytes inside a `ServiceWorkerGlobalScope` emulator
  (`tests/service_worker_harness.js`, driven through `node`), so the push
  handlers, the click target, the tag and the base64url re-encoding of the
  VAPID key are all checked by *running* them. What that emulator cannot cover
  is the browser around the worker: the permission prompt, a real
  `pushManager.subscribe`, a notification actually drawn on a lock screen, the
  real tab being focused. None of that was verified on a device, and a tour
  cannot reach it either — `Notification.requestPermission` and
  `pushManager.subscribe` need a real browser profile with real permissions.
  The emulator also *models* the browser contract (notably the two ways
  `showNotification` rejects); a browser that rejects for a third reason would
  not be noticed here.
- **The frontend script `static/src/js/pwa_push.js` is still unexecuted.** The
  harness covers the service worker only. The card's branch logic (iOS,
  denied, unsupported) is pinned by nothing but reading.
- **`previous_endpoint` is sent and currently ignored.**
  `pushsubscriptionchange` POSTs it, but `/mail/push/subscribe` passes it into
  `**kwargs` and `_register_for_persona` searches by the *new* endpoint only. So
  a rotated endpoint produces a new row, and the old one survives until the push
  service answers 404/410 and core unlinks it. It is sent anyway because that
  event is the only moment the pairing between the two endpoints is known; the
  day the route learns to rename, no browser has to change. Note that core's own
  rename path is dead too, for a different reason documented in
  `mail_push_guest`'s ROADMAP.
- **The click target is a guess for anything that is not a channel.** A payload
  naming `discuss.channel` opens `/discuss/channel/<res_id>`; a payload carrying
  its own `data.url` (same-origin paths only) opens that; anything else opens
  `/`. A module serving conversations on its own page should either add `url` to
  the payload or override `_pwa_push_worker_values`.
- **One notification per conversation, and no unread badge.** The `tag` collapses
  a burst, which means the count is lost: the visitor sees the last message, not
  "3 new". Core keeps a counter in IndexedDB and calls `navigator.setAppBadge`;
  that was left out deliberately (see the README) and could be added later
  without touching anything else.
- **No "desactivar avisos" button.** `/mail/push/unsubscribe` exists and the
  browser's own `pushManager.unsubscribe()` is one call away, but the card only
  offers the positive action. Today the way out is the browser's site settings,
  which the denied branch of the card points at.
- **Nothing renders the card server-side.** It is a snippet an editor has to
  place. A website with push enabled and the snippet nowhere will never ask
  anybody for permission, and there is no warning that says so.
- **iOS detection is a user-agent test**, inherited from `website_pwa` on
  purpose so the two cards agree. iPadOS reporting itself as a Mac is the known
  hole; the cost here is an iPad that sees the button instead of the install
  hint, and the failed `subscribe` is caught into a `console.warn`.
- **Payload language.** A single payload is built per channel, in the poster's
  language — `mail_push_guest`'s limit, unchanged here.

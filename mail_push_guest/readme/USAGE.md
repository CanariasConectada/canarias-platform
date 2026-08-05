## 1. Generate the VAPID key pair (once, by an administrator)

The pair lives in `ir.config_parameter` as `mail.web_push_vapid_private_key`
and `mail.web_push_vapid_public_key`. **Neither exists on a fresh database.**
Until they do, nothing is sent: both core and this module return early when
the parameters are missing.

There is no Settings action for it: the core method below is `mail`'s only
generator, and it runs on its own the first time an administrator's web client
enables notifications. To do it deliberately, **as a user with
`base.group_system`**:

```python
env["mail.push.device"].get_web_push_vapid_public_key()
```

**Treat the pair as immutable once generated.** The public key is baked into
every subscription every browser holds; regenerating it invalidates all of
them. The core method above makes that easy to do by accident: when the public
key parameter is missing it **unlinks every device on the database** before
generating a new pair. Two guards, because the method was reachable by any
authenticated account over `/web/dataset/call_kw`:

- `/mail/push/vapid` never calls it — it reads the parameter directly and
  answers `false` when it is absent;
- the method itself is overridden so that only `base.group_system` reaches the
  generating branch. Everybody else reads the existing key, or gets `false`.

## 2. Register a subscription from the browser

All three routes are `type="jsonrpc"`, `method="POST"`, `auth="public"`. The
persona comes from the session: the `dgid` guest cookie, or a logged-in user.

```js
// 1. ask for the key
const {vapid_public_key} = await rpc("/mail/push/vapid");
if (!vapid_public_key) return;  // not configured yet

// 2. subscribe with the service worker
const registration = await navigator.serviceWorker.ready;
const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: vapid_public_key,
});
const {endpoint, keys, expirationTime} = subscription.toJSON();

// 3. bind it to whoever this session is
await rpc("/mail/push/subscribe", {
    endpoint,
    keys,                              // {p256dh, auth}
    expiration_time: expirationTime,   // may be null
    vapid_public_key,                  // echoed back for verification
});
```

`/mail/push/unsubscribe` takes `{endpoint}` and returns `true` only when a
device owned by the caller was removed.

Errors are the JSON-RPC error envelope: `404` when the session has no persona
at all, and a `ValidationError` when the endpoint is not a known push service,
when the browser keys are malformed, or when the persona already holds the
maximum number of devices (5).

**`/mail/push/subscribe` returning `true` does not prove the caller owns the
device.** When the endpoint already belongs to another persona the route
refuses the registration and answers `true` anyway, on purpose — an error
there would tell the caller that somebody else's endpoint exists (see the
README). A client that needs certainty should verify by receiving, not by
reading the return value; in practice a browser only ever sees its own
endpoint, so the case does not arise outside an attack or a
subscribe-after-logout on a shared browser.

## 3. Who gets notified

A message posted to a `discuss.channel` reaches the devices of every **guest
member** of that channel, except:

- the author of the message;
- a member whose `mute_until_dt` is set;
- a member whose `custom_notifications` is `no_notif` or `mentions`.

`mentions` means "never" for a guest, on purpose: a `mail.message` addresses
partners (`partner_ids`), so there is no such thing as mentioning a guest.
An **unset** setting means "all" for a guest, where core resolves it through
`res.users.settings` — a record a guest does not have. Both divergences are in
one constant, `GUEST_NOTIFYING_SETTINGS`.

Partners keep behaving exactly as before; core's pass runs untouched, and this
module's pass only ever looks at devices with a `guest_id`.
